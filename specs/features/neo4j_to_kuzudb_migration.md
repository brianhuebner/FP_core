# Spec: Neo4j to KuzuDB Migration

> **Status:** Superseded
> **Created:** 2026-02-23
> **Spec type:** Feature
> **Superseded by:** `specs/features/remote_mcp_server.md` (KuzuDB acquired by Apple Oct 2025; repo archived; migration path closed)

---

## Purpose

Replace Neo4j (external graph server) with KuzuDB (embedded, file-based graph database) as FP_core's persistence backend. This eliminates an infrastructure dependency, enables file-per-tenant isolation for future multi-tenancy, and simplifies deployment to a single Python process with a data directory. KuzuDB speaks Cypher, making this a persistence-layer swap rather than a full rewrite.

---

## Layer Placement

**Primary layer:** L4 — Persistence
**Layers touched:**

| Layer | Package | What changes |
|-------|---------|--------------|
| L1 Types | `domain/types.py`, `types_recipe.py` | No changes |
| L2 Ontology | `domain/ontology.py`, `ontology_recipe.py` | No changes (read-only source for schema generation) |
| L3 Logic | `domain/logic.py` | No changes |
| L4 Persistence | `persistence/` | New `schema.py`; rewrite `connection.py`, `serializers.py`, `operations.py`; minor `deserializers.py` update |
| L5 MCP Server | `mcp_server/` | Connection wiring swap in `__init__.py`; docstring updates in `tools.py` |

---

## Domain Types (L1)

No Layer 1 changes required. All frozen dataclasses (`Node`, `Relationship`, `GraphPattern`), enums (`NodeLabel`, `RelationshipType`), and recipe types remain unchanged. The `GraphPattern` contract is the boundary between domain logic and persistence — it survives intact.

---

## Schema Definitions (L2)

No Layer 2 changes required. The ontology (`ONTOLOGY`, `RECIPE_ONTOLOGY`, `merged_ontology()`) and relationship constraints (`RELATIONSHIP_CONSTRAINTS`, `RECIPE_RELATIONSHIP_CONSTRAINTS`, `merged_relationship_constraints()`) are consumed read-only by the new `persistence/schema.py` to derive KuzuDB DDL. Python types remain the single source of truth.

**Validators affected:** None. All Gate 1 and Gate 2 validators are pure functions operating on domain types, not database records.

**Gate classification:**
- Gate 1 (template-time): No changes — validators operate on `GraphPattern` before persistence
- Gate 2 (runtime): No changes — `validate_entries` operates on in-memory domain objects

---

## Pure Functions (L3)

No Layer 3 changes required. All builder, extractor, and validator functions (`build_source_schema_pattern`, `build_recipe_pattern`, `compose_pipeline_pattern`, `validate_recipe`, `validate_pipeline_connectivity`, etc.) produce and consume `GraphPattern` objects. They have no persistence dependency.

---

## Persistence Contract (L4)

This is the primary layer of change.

### New module: `persistence/schema.py`

KuzuDB requires upfront schema definition (`CREATE NODE TABLE`, `CREATE REL TABLE`) unlike Neo4j's schema-free model. This module derives DDL from the existing Python ontology.

**Functions:**

```python
def generate_node_table_ddl(label: NodeLabel, schema: EntitySchema) -> str:
    """Generate CREATE NODE TABLE IF NOT EXISTS for one NodeLabel."""

def generate_rel_table_ddl(
    rel_type: RelationshipType,
    constraint: RelationshipConstraint
) -> str:
    """Generate CREATE REL TABLE IF NOT EXISTS for one RelationshipType."""

def generate_all_ddl() -> list[str]:
    """Generate all DDL statements (19 node tables + rel tables)."""

def ensure_schema(conn) -> None:
    """Idempotent: run all DDL. Safe to call on every connection open."""

def tables_with_property(prop_name: str) -> list[NodeLabel]:
    """Return NodeLabels whose PropertySchema includes prop_name.
    Used by operations.py for multi-table queries."""
```

**Sources of truth (all read-only):**
- `merged_ontology()` → 19 `EntitySchema` entries with `PropertySchema` defs → column names + types
- `MERGE_KEYS` → primary key columns per table
- `merged_relationship_constraints()` → 25 constraints → FROM/TO pairs per rel table

**Type mapping:**

| Python type | KuzuDB type |
|-------------|-------------|
| `str` | `STRING` |
| `int` | `INT64` |
| `float` | `DOUBLE` |
| `bool` | `BOOLEAN` |

**Design decisions:**
- **Multi-label handling:** KuzuDB nodes have a single table name. `Reference` nodes (which use `extra_labels`) store extra labels as a `STRING[]` column. All other nodes map 1:1 to their `NodeLabel` table.
- **`_node_id` column:** Added to every node table as a `STRING` column (stores `Node.id`). Not the primary key — merge keys from `MERGE_KEYS` serve that role.

### Connection: `persistence/connection.py`

Replace `Neo4jConnection` with `KuzuConnection`. Same public interface shape.

```python
class KuzuConnection:
    def __init__(self, db_path: str | None = None):
        """Opens/creates embedded KuzuDB at db_path.
        Reads KUZU_DB_PATH env var if db_path not provided.
        Calls ensure_schema() on init."""

    def __enter__(self) -> KuzuConnection: ...
    def __exit__(self, exc_type, exc_val, exc_tb) -> None: ...
    def close(self) -> None: ...
    def verify_connection(self) -> bool: ...
    def run_query(self, query: str, parameters: dict | None = None) -> list[dict]: ...
    def run_write(self, query: str, parameters: dict | None = None) -> dict: ...
```

**Key differences from Neo4j:**
- `kuzu.Database(db_path)` + `kuzu.Connection(db)` — no auth, no server
- `conn.execute(query, parameters)` → `QueryResult` with `has_next()`/`get_next()` iteration
- `run_write` returns synthetic counters `{"nodes_created": 0, "relationships_created": 0, "properties_set": 0}` (KuzuDB doesn't provide mutation counters)
- Env var: `KUZU_DB_PATH` (replaces `NEO4J_URI` + `NEO4J_PASSWORD`)
- Schema auto-initialized on first connection open

### Serializers: `persistence/serializers.py`

KuzuDB does not support `MERGE`. Strategy: **delete-then-create** (idempotent at the pattern level, matching actual usage — `save_pattern` always saves a complete pattern).

**Function signatures preserved:**

```python
def serialize_node(node: Node, index: int) -> tuple[str, dict]:
    """Node → CREATE statement (was MERGE)."""

def serialize_relationship(
    rel: Relationship, index: int, node_map: dict
) -> tuple[str, dict]:
    """Relationship → MATCH...WHERE...CREATE statement (was MATCH{...}MERGE)."""

def serialize_pattern(pattern: GraphPattern) -> list[tuple[str, dict]]:
    """Full pattern → list of (cypher, params) statements."""
```

**Cypher syntax changes:**

```cypher
-- Before (Neo4j MERGE):
MERGE (n0:SourceSchema {recipe_id: $n0_recipe_id, name: $n0_name})
SET n0._node_id = $n0__node_id, n0.source_system = $n0_source_system

-- After (KuzuDB CREATE):
CREATE (n0:SourceSchema {recipe_id: $n0_recipe_id, name: $n0_name,
        _node_id: $n0__node_id, source_system: $n0_source_system})
```

```cypher
-- Before (Neo4j relationship MERGE):
MATCH (s0:SourceSchema {recipe_id: $s0_recipe_id, name: $s0_name})
MATCH (e0:Column {recipe_id: $e0_recipe_id, name: $e0_name})
MERGE (s0)-[r0:HAS_COLUMN]->(e0)

-- After (KuzuDB relationship CREATE):
MATCH (s0:SourceSchema) WHERE s0.recipe_id = $s0_recipe_id AND s0.name = $s0_name
MATCH (e0:Column) WHERE e0.recipe_id = $e0_recipe_id AND e0.name = $e0_name
CREATE (s0)-[:HAS_COLUMN]->(e0)
```

**`merge_keys.py` unchanged** — still used to determine identity properties for relationship MATCH/WHERE lookups.

### Operations: `persistence/operations.py`

Most impacted file. KuzuDB cannot do schema-less `MATCH (n) WHERE n.recipe_id = $id` across all node tables — must query each table separately.

**`save_pattern(conn, pattern)` changes:**
1. Determine scope from pattern nodes (`recipe_id` or `format_id`)
2. Delete existing nodes in that scope via `_delete_by_property`
3. Execute CREATE statements for all nodes
4. Execute CREATE statements for all relationships

**`load_pattern_by_recipe(conn, recipe_id)` changes:**
- Call `tables_with_property("recipe_id")` from `schema.py` for the list of relevant tables
- Query each table: `MATCH (n:TableName) WHERE n.recipe_id = $id RETURN n.*`
- Query one-hop neighbors (Account nodes via MAPPED_TO)
- Query relationships between found nodes
- Assemble into dict format for deserializers

**`load_format_by_id(conn, format_id)` changes:**
- Same multi-table pattern, filtering on `format_id`

**`_delete_by_property` changes:**
- One `DELETE` per table instead of single cross-table `DETACH DELETE`

**KuzuDB function mapping:**

| Neo4j | KuzuDB |
|-------|--------|
| `labels(n)` | `label(n)` (single string) |
| `properties(n)` | `n.*` column access |
| `type(r)` | `label(r)` |
| `coalesce(x, '')` | `COALESCE(x, '')` (same) |
| `DETACH DELETE n` | `DELETE n` |

### Deserializers: `persistence/deserializers.py`

Minor adaptations:
- `deserialize_node` handles single label string (wrap in list) vs Neo4j's label list
- `deserialize_pattern` adjusts for operations.py's new result format
- `_LABEL_VALUE_MAP` and `_REL_TYPE_MAP` lookups unchanged

---

## MCP Interface (L5)

### Tool signatures affected

None. All 6 tool signatures remain identical. The tools call `save_pattern`, `load_pattern_by_recipe`, and `load_format_by_id` — whose signatures are preserved.

### Connection wiring (`mcp_server/__init__.py`)

```python
# Before:
from persistence.connection import Neo4jConnection
_connection = Neo4jConnection(uri=..., user=..., password=...)

# After:
from persistence.connection import KuzuConnection
_connection = KuzuConnection(db_path=os.environ.get("KUZU_DB_PATH"))
```

### JSON spec format

No changes. Pipeline specs and format specs are consumed by builders (L3/L5 pure functions), not by persistence.

### Summarizer output

No changes. Summarizers consume `GraphPattern` objects, not database records.

---

## Data Flow

```
JSON spec (agent input)
    |
    v
builders.py — parse spec → domain objects (UNCHANGED)
    |
    v
GraphPattern (frozen dataclass) (UNCHANGED)
    |
    v
Gate 1 validation (ontology checks) (UNCHANGED)
    |
    v
serializers.py — GraphPattern → KuzuDB Cypher (CHANGED: MERGE → CREATE)
    |
    v
operations.py — execute via KuzuConnection (CHANGED: multi-table queries)
    |
    v
KuzuDB embedded database (CHANGED: replaces Neo4j server)
    |
    v
operations.py — query results → dict format (CHANGED: per-table queries)
    |
    v
deserializers.py — dicts → GraphPattern (MINOR CHANGE: single label handling)
    |
    v
summarizers.py — GraphPattern → JSON response (UNCHANGED)
    |
    v
JSON response (agent output)
```

---

## Examples

### Happy path: save and load round-trip

```python
# Save a recipe pipeline (same as today)
conn = KuzuConnection(db_path="/data/test_db")
save_pattern(conn, pattern)  # delete-then-create internally

# Load it back (same interface as today)
loaded = load_pattern_by_recipe(conn, "payroll_v1")
assert len(loaded.nodes) == len(pattern.nodes)
assert len(loaded.relationships) == len(pattern.relationships)
```

### Happy path: MCP tool usage (unchanged)

```json
// build_and_save_pipeline input — identical to current
{
  "recipe_id": "payroll_v1",
  "schema": { "name": "payroll_export", "columns": [...], "measures": [...] },
  "recipe": { "name": "Payroll Journal", "rules": [...] }
}

// Response — same shape
{
  "validation": { "valid": true, "errors": [], "warnings": [...] },
  "save_counts": { "total_nodes": 12, "total_relationships": 11 },
  "recipe_id": "payroll_v1"
}
```

### Edge case: empty database

KuzuDB connection auto-creates the database directory and runs `ensure_schema()`. First `save_pattern` call works without any setup. No migration scripts needed.

### Edge case: idempotent save

Calling `save_pattern(conn, same_pattern)` twice produces the same final state. The second call deletes the existing nodes, then re-creates them. Node count after second save equals node count after first save.

---

## Invariants

### Graph semantics
- `_node_id` round-trip: `Node.id` stored as `_node_id` column in KuzuDB, reconstituted on load
- Enum pass-through: enum values stored as strings in KuzuDB, reconstituted by deserializers
- Idempotency: `save_pattern` called twice produces identical graph state (delete-then-create)
- All 19 node tables and relationship tables derived from Python ontology — schema.py is a pure function of `merged_ontology()`, `MERGE_KEYS`, and `merged_relationship_constraints()`

### Functional constraints
- `serialize_pattern` remains a pure function: `GraphPattern → list[(str, dict)]`
- `deserialize_pattern` remains a pure function: `list[dict] → GraphPattern`
- `schema.py` functions are pure: ontology → DDL strings
- Only `connection.py` imports `kuzu` (single point of driver dependency)

### Layer boundaries
- `domain/` must never import from `persistence/` or `mcp_server/`
- `persistence/` imports from `domain/` only
- Pure functions (`builders.py`, `summarizers.py`) must not import from `persistence/`
- Only `connection.py` may import the `kuzu` package

---

## Integration

### Files modified

| File | Change |
|------|--------|
| `persistence/connection.py` | Replace `Neo4jConnection` with `KuzuConnection` (KuzuDB embedded driver) |
| `persistence/serializers.py` | Rewrite Cypher generation: MERGE → CREATE, inline props → WHERE clause |
| `persistence/deserializers.py` | Handle single label string from KuzuDB (vs label list from Neo4j) |
| `persistence/operations.py` | Multi-table queries, delete-then-create save strategy, KuzuDB functions |
| `persistence/__init__.py` | Export `KuzuConnection` instead of `Neo4jConnection` |
| `mcp_server/__init__.py` | Import `KuzuConnection`, read `KUZU_DB_PATH` env var |
| `mcp_server/tools.py` | Docstring updates (Neo4j → database references) |
| `tests/persistence/conftest.py` | Replace `neo4j_conn` fixture with `kuzu_conn` using `tmp_path` |
| `tests/persistence/test_serializers.py` | Assert KuzuDB Cypher syntax in output |
| `tests/persistence/test_deserializers.py` | Adjust input dict shapes for single-label format |
| `tests/persistence/test_operations.py` | Remove `@requires_neo4j` skip markers, use `kuzu_conn` fixture |
| `persistence/CLAUDE.md` | Update architecture docs for KuzuDB |
| `mcp_server/CLAUDE.md` | Update connection reference |
| `CLAUDE.md` | Update canonical counts, env vars, dependency list |

### Files created

| File | Purpose |
|------|---------|
| `persistence/schema.py` | Derive KuzuDB DDL from Python ontology (node tables + rel tables) |
| `tests/persistence/test_schema.py` | Verify DDL generation covers all 19 labels with correct types/keys |

### Canonical counts affected

| Constant | Before | After | Delta |
|----------|--------|-------|-------|
| `NodeLabel` | 19 | 19 | 0 |
| `RelationshipType` | 26 | 26 | 0 |
| `MERGE_KEYS` | 19 | 19 | 0 |
| MCP Tools | 6 | 6 | 0 |
| Total tests | 394 | ~410 | ~+16 (new test_schema.py) |

---

## Test Strategy

### New tests

| Test file | Test class / method | What it verifies |
|-----------|-------------------|-----------------|
| `tests/persistence/test_schema.py` | `test_generate_all_ddl_covers_all_labels` | DDL generated for all 19 NodeLabels |
| `tests/persistence/test_schema.py` | `test_node_table_ddl_column_types` | Python→KuzuDB type mapping correctness |
| `tests/persistence/test_schema.py` | `test_node_table_ddl_primary_keys` | Primary keys match MERGE_KEYS |
| `tests/persistence/test_schema.py` | `test_rel_table_ddl_from_to_pairs` | Relationship tables have correct FROM/TO |
| `tests/persistence/test_schema.py` | `test_tables_with_property` | Correct NodeLabels returned for recipe_id, format_id |
| `tests/persistence/test_schema.py` | `test_node_id_column_on_every_table` | `_node_id STRING` present on all node tables |
| `tests/persistence/test_schema.py` | `test_reference_extra_labels_column` | Reference table has `STRING[]` extra_labels column |
| `tests/persistence/test_schema.py` | `test_ensure_schema_idempotent` | Calling `ensure_schema` twice doesn't error |

### Existing tests

| Test file | Status | Reason |
|-----------|--------|--------|
| `tests/domain/*` (5 files, 197 tests) | Unchanged | No domain layer changes |
| `tests/mcp_server/*` (2 files, 109 tests) | Unchanged | Pure builders/summarizers, no persistence dependency |
| `tests/persistence/test_merge_keys.py` (~13 tests) | Unchanged | Pure data mapping, no Cypher |
| `tests/persistence/test_serializers.py` (~25 tests) | Assertions rewritten | Check KuzuDB Cypher syntax (CREATE, WHERE) instead of Neo4j (MERGE, SET) |
| `tests/persistence/test_deserializers.py` (~20 tests) | Minor adjustments | Single-label input format |
| `tests/persistence/test_operations.py` (~11 tests) | Fixture swap + always-on | `kuzu_conn(tmp_path)` replaces `neo4j_conn`; no skip markers needed |

### Expected new test count

Current: 394 | Added: ~16 | New total: ~410

---

## Success Criteria

- [ ] `pytest` passes with all ~410 tests (0 failures, 0 skips for persistence)
- [ ] Integration tests (`test_operations.py`) run without external database (embedded KuzuDB via `tmp_path`)
- [ ] `build_and_save_pipeline` MCP tool saves payroll recipe to KuzuDB and `load_recipe` loads it back with identical node/relationship counts
- [ ] `get_processing_instructions` returns correct measures and resolved account codes from KuzuDB
- [ ] No imports of `neo4j` anywhere in the codebase
- [ ] Only `persistence/connection.py` imports `kuzu`
- [ ] `ensure_schema()` is idempotent — safe to call on every connection open
- [ ] All domain tests pass without modification (zero L1-L3 changes)
- [ ] Canonical counts updated in `CLAUDE.md` and count tests

---

## Out of Scope

- Multi-tenancy (`TenantContext`, per-tenant directories) — deferred to next phase
- Auth system (API keys, SQLite control plane) — deferred to next phase
- HTTP/SSE transport (stdio → hosted MCP server) — deferred to next phase
- DuckDB analytics layer — not needed yet
- YAML ontology files — rejected in favor of keeping Python types as source of truth
- `GraphStore` interface abstraction — not justified until a second backend exists
- Ontology versioning — deferred to later phase

---

## Open Questions

All resolved — see findings below.

- [x] **Multi-FROM/TO relationship tables.** KuzuDB (v0.8.0+) natively supports multiple FROM/TO pairs in a single `CREATE REL TABLE` using comma-separated pairs. The old `CREATE REL TABLE GROUP` syntax is deprecated. FP_core has 4 multi-pair relationship types: `PARENT_OF` (Entity→Entity, AnalyticalDimension→AnalyticalDimension), `CHILD_OF` (same pairs), `HAS_COLUMN` (SourceSchema→Column, OutputFormat→OutputColumn), and `USES_REFERENCE` (MappingRule→Reference, Condition→Reference, AccountingRecipe→Reference). KuzuDB infers the correct pair from node labels in the MATCH clause, so serializer CREATE statements need no special handling.

  ```cypher
  CREATE REL TABLE HAS_COLUMN(
      FROM SourceSchema TO Column,
      FROM OutputFormat TO OutputColumn
  );
  ```

- [x] **Parameterized query syntax.** `$param_name` works identically to Neo4j. Parameters are passed as `dict[str, Any]` to `conn.execute(query, parameters={...})` with keys without the `$` prefix (same convention as Neo4j). Two gotchas: `SET n += $map` (bulk property merge) is **not supported** — must set properties individually; `REMOVE n.prop` is **not supported** — use `SET n.prop = NULL`. FP_core's serializers already set properties individually, so no adaptation needed beyond the driver call site change (`session.run()` → `conn.execute()`).

- [x] **STRING[] array columns.** KuzuDB supports variable-length `STRING[]` (LIST) columns. The Reference node's `extra_labels` column is declared as `STRING[]` in `CREATE NODE TABLE`. Insert with bracket literals (`['Account', 'Expense']`), query with `list_contains(r.extra_labels, 'Account')`. Key difference from Neo4j: the column type must be declared upfront in DDL, and list predicate functions use the `list_` prefix (e.g., `list_contains` instead of Neo4j's `IN` operator on properties).