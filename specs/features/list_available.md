# Spec: Combined Discoverability Tool

> **Status:** Ready
> **Created:** 2026-02-21
> **Spec type:** Feature

---

## Purpose

An agent starting a new session has no way to discover which recipes and output formats already exist in the graph. The only option is to guess a `recipe_id` and call `load_recipe`, which returns an error if wrong. A `list_available` tool provides a single-call inventory of all saved recipes and formats, enabling agents to browse, select, and load without trial-and-error.

---

## Layer Placement

**Primary layer:** L4 (Persistence) + L5 (MCP Server)
**Layers touched:**

| Layer | Package | What changes |
|-------|---------|--------------|
| L1 Types | `domain/types.py` / `types_recipe.py` | No changes |
| L2 Ontology | `domain/ontology.py` / `ontology_recipe.py` | No changes |
| L3 Logic | `domain/logic.py` | No changes |
| L4 Persistence | `persistence/operations.py` | New `list_available` function |
| L5 MCP Server | `mcp_server/tools.py` | New `list_available` tool handler |

---

## Domain Types (L1)

No Layer 1 changes required. The query returns lightweight dicts (recipe_id, name, rule count, etc.) — no new domain types needed.

---

## Schema Definitions (L2)

No Layer 2 changes required. No validators or schemas affected.

**Gate classification:**
- Gate 1: No impact
- Gate 2: No impact

---

## Pure Functions (L3)

No Layer 3 changes required.

---

## Persistence Contract (L4)

### New operation: `list_available`

```python
def list_available(
    conn: Neo4jConnection,
) -> Dict[str, List[Dict[str, Any]]]:
    """Query Neo4j for all saved recipes and output formats.

    Returns {"recipes": [...], "formats": [...]} where each entry
    contains identity and summary fields.

    Always queries Neo4j directly — no caching.
    """
```

**Recipe query:**
```cypher
MATCH (r:AccountingRecipe)
OPTIONAL MATCH (r)-[:HAS_RULE]->(rule:MappingRule)
RETURN r.recipe_id AS recipe_id,
       r.name AS name,
       count(rule) AS rule_count
ORDER BY r.recipe_id
```

**Format query:**
```cypher
MATCH (f:OutputFormat)
OPTIONAL MATCH (f)-[:HAS_COLUMN]->(col:OutputColumn)
RETURN f.format_id AS format_id,
       f.name AS name,
       f.target_system AS target_system,
       count(col) AS column_count
ORDER BY f.format_id
```

**Design decisions:**
- **No caching:** Results are always fresh from Neo4j. The list is cheap to compute (two index lookups) and staleness would be confusing for agents.
- **Aggregation in Cypher:** Rule count and column count are computed server-side to minimize data transfer and give agents useful summary info.
- **Separate queries:** Two simple queries are easier to maintain and debug than a single UNION query.

- **Merge keys:** No changes to `MERGE_KEYS` registry.
- **Serialization:** No changes — `list_available` returns raw query results, not domain objects.
- **Deserialization:** No changes — results are plain dicts from the Neo4j driver.

---

## MCP Interface (L5)

### New tool handler (`mcp_server/tools.py`)

```python
@mcp.tool()
def list_available() -> str:
    """List all saved recipes and output formats in the knowledge graph.

    No parameters required. Returns a JSON summary of all available
    recipes and formats with identity fields and summary counts.

    Use this to discover what's available before calling load_recipe
    or load_format.
    """
```

**Behavior:**
1. Get Neo4j connection
2. Call `list_available(conn)`
3. Return JSON-serialized result

### Tool signatures affected

No existing tool signatures change. This adds one new tool with zero parameters.

### JSON spec format

N/A — no input spec.

### Summarizer output

No new summarizer function needed — the tool formats the result directly:

```json
{
  "recipes": [
    {
      "recipe_id": "payroll_v1",
      "name": "Payroll Journal",
      "rule_count": 4
    },
    {
      "recipe_id": "ap_invoice_v1",
      "name": "AP Invoice Journal",
      "rule_count": 2
    }
  ],
  "formats": [
    {
      "format_id": "qb_journal_v1",
      "name": "QuickBooks Journal Import",
      "target_system": "quickbooks_desktop",
      "column_count": 8
    }
  ]
}
```

---

## Data Flow

```
list_available() — tool call (no params)
    |
    v
tools.py — get Neo4j connection
    |
    v
persistence/operations.py — list_available(conn)
    |  Query 1: MATCH (r:AccountingRecipe) ... → recipe list
    |  Query 2: MATCH (f:OutputFormat) ... → format list
    v
{"recipes": [...], "formats": [...]}
    |
    v
JSON response (agent reads inventory)
```

---

## Examples

### Happy path: recipes and formats exist

```json
// Tool call
list_available()

// Response
{
  "recipes": [
    {"recipe_id": "payroll_v1", "name": "Payroll Journal", "rule_count": 4}
  ],
  "formats": [
    {"format_id": "qb_journal_v1", "name": "QuickBooks Journal Import", "target_system": "quickbooks_desktop", "column_count": 8}
  ]
}
```

### Edge case: empty graph

```json
// Tool call
list_available()

// Response
{
  "recipes": [],
  "formats": []
}
```

### Edge case: recipes exist but no formats

```json
// Tool call
list_available()

// Response
{
  "recipes": [
    {"recipe_id": "payroll_v1", "name": "Payroll Journal", "rule_count": 4}
  ],
  "formats": []
}
```

### Error case: Neo4j connection failure

```json
// Tool call
list_available()

// Response
{"error": "Neo4j error: <connection error details>"}
```

---

## Invariants

### Graph semantics
- Read-only — `list_available` does not modify the graph
- Returns only identity/summary fields — no full node properties exposed

### Functional constraints
- Always fresh from Neo4j — no caching layer
- Results are deterministic for a given graph state (ORDER BY recipe_id / format_id)
- Empty lists for missing node types (never null)

### Layer boundaries
- `operations.py` uses only `Neo4jConnection` — no domain type dependencies for this function
- `tools.py` imports `list_available` from `persistence.operations`
- No new summarizer needed — the tool formats results directly

---

## Integration

### Files modified

| File | Change |
|------|--------|
| `persistence/operations.py` | Add `list_available(conn) -> Dict` function |
| `persistence/__init__.py` | Add `"list_available"` to imports and `__all__` |
| `mcp_server/tools.py` | Add `list_available` tool handler; import from persistence |
| `tests/persistence/test_operations.py` | Add `TestListAvailable` class (~4 integration tests) |

### Files created

None.

### Canonical counts affected

| Constant | Before | After | Delta |
|----------|--------|-------|-------|
| MCP Tools | 8 | 9 | +1 |
| Total tests | ~418 | ~422 | +~4 |

Note: MCP Tools count starts at 8 assuming `patch_recipe` and `explain_recipe` are implemented first.

---

## Test Strategy

### New tests (`tests/persistence/test_operations.py`)

| Test class / method | What it verifies |
|---------------------|-----------------|
| `TestListAvailable::test_list_with_recipe_and_format` | Both recipes and formats returned after save |
| `TestListAvailable::test_list_empty_graph` | Empty lists returned when no recipes/formats exist |
| `TestListAvailable::test_list_recipe_rule_count` | `rule_count` matches actual number of rules |
| `TestListAvailable::test_list_format_column_count` | `column_count` matches actual number of columns |

### Existing tests

All existing persistence tests must pass unchanged. The new function is additive.

### Expected new test count

Current: ~418 | Added: ~4 | New total: ~422

---

## Success Criteria

- [ ] `list_available` returns `{"recipes": [...], "formats": [...]}` with correct identity fields
- [ ] Recipe entries include `recipe_id`, `name`, `rule_count`
- [ ] Format entries include `format_id`, `name`, `target_system`, `column_count`
- [ ] Empty graph returns `{"recipes": [], "formats": []}`
- [ ] Results ordered by recipe_id / format_id
- [ ] Neo4j errors returned as structured error JSON
- [ ] All existing tests pass (no regressions)
- [ ] Canonical counts updated in CLAUDE.md

---

## Out of Scope

- **Filtering/search:** No query parameters for filtering by name, system, etc. The full list is small enough for agents to filter client-side.
- **Pagination:** Not needed — accounting knowledge graphs typically have tens of recipes, not thousands.
- **Caching:** Deliberately omitted. The query is cheap and freshness is more important than speed for a discovery tool.
- **Detailed metadata:** Only identity + summary count fields. Use `load_recipe` / `load_format` for full details.

---

## Open Questions

None. The design follows the existing `load_pattern_by_recipe` / `load_format_by_id` patterns in `operations.py`.
