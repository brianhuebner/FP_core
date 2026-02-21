# Spec: Knowledge Zone Reference Data Import

> **Status:** Draft
> **Created:** 2026-02-17
> **Spec type:** Feature

---

## Purpose

The two-zone architecture defines a knowledge zone for user-specific business data (employee rosters, tax tables, allocation schedules, vendor lists) that recipes reference via USES_REFERENCE edges. Today, reference data can only be embedded inline in a pipeline spec's `recipe.references[]` array — tightly coupled to a single recipe, re-declared every build, and impossible to import in bulk. A standalone `build_reference` tool imports reference data independently, and a `load_reference` tool reads it back. The data persists across sessions, can be linked to any recipe via the existing inline mechanism or future Tier 2 tools, and enables the knowledge accumulation that makes the system more valuable over time.

---

## Design Decisions

### 1. Standalone import, no cross-tool linking

`build_reference` creates Reference nodes in Neo4j. It does NOT create USES_REFERENCE edges to recipes. Linking reference data to a recipe is a separate concern handled by:
- **Existing mechanism:** Inline `recipe.references[]` in pipeline specs (creates both nodes and USES_REFERENCE edges in the same `build_and_save_pipeline` call — no cross-tool coupling).
- **Future mechanism:** A Tier 2 `link_reference` tool that queries Neo4j for the target node (not regenerating IDs by convention).

This avoids the cross-tool ID coupling antipattern. Two tool calls cannot share a node-ID map, so any mechanism that computes `_node_id` from `reference_id + record_id` in a different tool call is implicit coupling via naming convention. The condition wiring spec fixed this within a single tool call by building a map; across tool calls, the only clean option is a query-based lookup (future Tier 2).

### 2. `reference_id` + `record_id` are persistence identity, not domain schema

The knowledge zone is schema-free — `_REFERENCE_PROPS` has empty `required` and `optional` sets, and `validate_node_properties` is a no-op for Reference nodes. This spec does not change that.

However, MERGE requires a deterministic identity for idempotent writes. `reference_id` (collection) + `record_id` (record within collection) form the persistence identity:
- `_node_id = _generate_node_id(reference_id, "ref", record_id)`
- MERGE matches on `_node_id` (the existing empty-merge-key fallback in `serializers.py:39-42`)

These fields are a Layer 4 persistence concern — they enable idempotent writes — not a Layer 2 schema concern. The rest of each record's properties remain schema-free.

### 3. `type` in `extra_labels` only

The existing inline mechanism stores business type in `Node.extra_labels`:
```python
Node(labels={NodeLabel.REFERENCE}, extra_labels=frozenset({"Employee"}), ...)
```

This spec follows that pattern. The `type` is NOT duplicated as a property. `extra_labels` is the canonical location — it becomes a Neo4j label (`:Reference:Employee`), making it queryable via label-based MATCH.

### 4. `load_reference` completes the read/write cycle

Every data type has paired tools: `build_and_save_pipeline` / `load_recipe`, `build_output` / `load_format`. A write-only `build_reference` without a read tool means the agent can't verify or inspect imported data. `load_reference` follows the same pattern: load from Neo4j, cache server-side, return a summary.

### 5. Recipe loading already handles linked references

`load_pattern_by_recipe` (operations.py:29-75) has a hop query that follows relationships one hop out from recipe-scoped nodes. When a recipe has USES_REFERENCE edges to Reference nodes (via inline mechanism), the hop query finds them. No changes to the load query are needed.

---

## Layer Placement

**Primary layer:** L5 — MCP Server (new tools + builder + summarizer)
**Layers touched:**

| Layer | Package | What changes |
|-------|---------|--------------|
| L1 Types | `domain/types_recipe.py` | Nothing — Reference uses NodeLabel.REFERENCE sentinel + extra_labels |
| L2 Ontology | `domain/ontology_recipe.py` | Nothing — `_REFERENCE_PROPS` (empty), USES_REFERENCE constraint all exist |
| L3 Logic | `domain/logic.py` | Add `build_reference_pattern` builder function |
| L4 Persistence | `persistence/operations.py` | Add `load_reference_by_id` query function, add `delete_reference_by_id` |
| L5 MCP Server | `mcp_server/builders.py`, `mcp_server/summarizers.py`, `mcp_server/tools.py`, `mcp_server/__init__.py` | New `build_reference` + `load_reference` tools, builder, summarizer, state |

---

## Domain Types (L1)

No Layer 1 changes required. Reference data uses existing mechanisms:

```python
# How reference nodes are constructed (existing pattern from builders.py:180-188):
Node(
    id="employee_roster_2026_q1_ref_emp_001",
    labels={NodeLabel.REFERENCE},
    properties={"name": "Jane Doe", "department": "Engineering"},
    extra_labels=frozenset({"Employee"}),
)
```

- `NodeLabel.REFERENCE` — sentinel label marking knowledge-zone data
- `Node.extra_labels` — business type (e.g., `{"Employee"}`, `{"TaxBracket"}`)
- `Node.properties` — arbitrary key-value pairs, no schema enforcement

---

## Schema Definitions (L2)

No Layer 2 changes required:

```python
# domain/ontology_recipe.py — already exists
_REFERENCE_PROPS = PropertySchema(
    required=frozenset(),   # No required properties — schema-free
    optional=frozenset(),   # No declared optional — anything goes
    types={},               # No type enforcement
)

# USES_REFERENCE — already exists
RelationshipType.USES_REFERENCE: (
    (NodeLabel.MAPPING_RULE, NodeLabel.REFERENCE),
    (NodeLabel.CONDITION, NodeLabel.REFERENCE),
    (NodeLabel.ACCOUNTING_RECIPE, NodeLabel.REFERENCE),
),

# Only these three may source USES_REFERENCE
REFERENCE_RELATIONSHIP_SOURCES = frozenset({
    NodeLabel.MAPPING_RULE, NodeLabel.CONDITION, NodeLabel.ACCOUNTING_RECIPE,
})
```

**Gate classification:**
- Gate 1: `validate_node_properties` is a no-op for Reference (empty PropertySchema). `validate_uses_reference` validates the source side of USES_REFERENCE edges (already exists). No new validation needed.
- Gate 2: No impact — reference data is structural context, not entry-level validation.

---

## Pure Functions (L3)

### New: `build_reference_pattern`

```python
def build_reference_pattern(
    reference_nodes: List[Node],
) -> GraphPattern:
    """Construct a GraphPattern for a set of reference data nodes.

    Reference nodes are standalone — no inter-node relationships.
    Returns a GraphPattern with nodes only, empty relationship list.
    Maintains the pattern that all GraphPattern construction goes through L3.
    """
    return GraphPattern(nodes=reference_nodes, relationships=[])
```

This is minimal by design. Reference nodes are standalone data points — unlike schema nodes (connected via HAS_COLUMN, HAS_MEASURE) or recipe nodes (connected via HAS_RULE, DEBITS, CREDITS), reference nodes have no inter-node relationships. USES_REFERENCE edges are created by the recipe builder's inline mechanism, not by the reference builder.

---

## Persistence Contract (L4)

### New: `load_reference_by_id`

```python
def load_reference_by_id(
    conn: Neo4jConnection,
    reference_id: str,
) -> GraphPattern:
    """Load all Reference nodes for a given reference_id from Neo4j.

    Queries nodes with the Reference label that have a matching
    reference_id property. Returns a GraphPattern with nodes only
    (reference collections have no inter-node relationships).
    """
```

Cypher:
```cypher
MATCH (n:Reference)
WHERE n.reference_id = $id
RETURN labels(n) AS labels, properties(n) AS properties
```

Note: no relationship query needed — reference collections have no internal edges.

### New: `delete_reference_by_id`

Follows the `delete_format_by_id` pattern:
```python
def delete_reference_by_id(conn: Neo4jConnection, reference_id: str) -> Dict[str, int]:
    """Delete all Reference nodes for a given reference_id."""
```

### Existing MERGE behavior

Reference nodes have `MERGE_KEYS[REFERENCE] = ()`. The serializer falls back to `_node_id`:

```python
# serializers.py:39-42
if not merge_key_names:
    merge_props = f"_node_id: ${var}__node_id"
    params[f"{var}__node_id"] = node.id
```

The builder generates `_node_id` deterministically from `reference_id + record_id`. Re-importing the same spec produces the same `_node_id` values, so MERGE matches existing nodes and SET updates their properties. Idempotent by construction.

### No merge key changes

`MERGE_KEYS[REFERENCE] = ()` — unchanged. The empty-key fallback to `_node_id` is the correct behavior for schema-free nodes.

---

## MCP Interface (L5)

### New tool: `build_reference`

```python
@mcp.tool()
def build_reference(reference_spec: str) -> str:
    """Import reference data into the knowledge zone.

    Accepts a JSON string containing a reference collection with a
    reference_id, type label, and array of records. Each record becomes
    a Reference node with arbitrary properties in the knowledge zone.

    Reference data is schema-free — FP_core stores whatever properties
    you provide without validation. Idempotent: re-importing the same
    spec updates existing records.

    Returns a JSON summary with record count and save counts.
    """
```

### New tool: `load_reference`

```python
@mcp.tool()
def load_reference(reference_id: str) -> str:
    """Load reference data from Neo4j and return a structured summary.

    Loads all Reference nodes for the given reference_id, caches
    in server-side state, and returns a summary of the collection
    (type, record count, field names).
    """
```

### JSON spec format (`build_reference`)

```json
{
  "reference_id": "employee_roster_2026_q1",
  "type": "Employee",
  "description": "Q1 2026 employee roster from ADP export",
  "records": [
    {
      "record_id": "emp_001",
      "name": "Jane Doe",
      "department": "Engineering",
      "employee_type": "salaried",
      "annual_salary": "95000"
    },
    {
      "record_id": "emp_002",
      "name": "John Smith",
      "department": "Sales",
      "employee_type": "hourly",
      "hourly_rate": "28.50"
    }
  ]
}
```

Field definitions:
- `reference_id` (required, `string`): Collection identifier. Used for loading, querying, and `_node_id` generation. Convention: `{data_type}_{period}` (e.g., `employee_roster_2026_q1`).
- `type` (required, `string`): Business type label stored in `Node.extra_labels`. Becomes a Neo4j label (`:Reference:Employee`).
- `description` (optional, `string`): Human-readable description of the collection. Stored on the first node or as tool response metadata (not on every node).
- `records` (required, `array`): Array of objects. Each becomes a Reference node.
  - `record_id` (required per record, `string`): Unique identifier within this collection. Used for `_node_id` generation.
  - All other fields: Arbitrary key-value pairs stored as node properties. Schema-free.

### Builder (`mcp_server/builders.py`)

New function:

```python
def build_reference_from_spec(spec: Dict[str, Any]) -> GraphPattern:
    """Convert a reference data spec → GraphPattern of Reference nodes.

    Validates record_id uniqueness. Each record becomes a Reference node
    with NodeLabel.REFERENCE and the business type in extra_labels.

    Raises ValueError if duplicate record_ids are found.
    """
    reference_id = spec["reference_id"]
    ref_type = spec["type"]

    # Validate record_id uniqueness
    record_ids: List[str] = []
    for i, record in enumerate(spec.get("records", [])):
        rid = record.get("record_id")
        if rid is None:
            raise ValueError(f"Record at index {i} is missing required field: record_id")
        if rid in record_ids:
            raise ValueError(
                f"Duplicate record_id '{rid}' at index {i} in reference '{reference_id}'"
            )
        record_ids.append(rid)

    nodes: List[Node] = []
    for record in spec.get("records", []):
        record_id = record["record_id"]
        node_id = _generate_node_id(reference_id, "ref", record_id)

        # All record fields (except record_id) become node properties
        # Add reference_id and record_id as properties for queryability
        props: Dict[str, Any] = {}
        for key, value in record.items():
            props[key] = value
        props["reference_id"] = reference_id

        nodes.append(Node(
            id=node_id,
            labels={NodeLabel.REFERENCE},
            properties=props,
            extra_labels=frozenset({ref_type}),
        ))

    return build_reference_pattern(nodes)
```

Note: `record_id` IS stored as a property (it's part of the record). `reference_id` is added as a property for collection-level queries. `type` is NOT stored as a property — it's in `extra_labels` only.

### Summarizer (`mcp_server/summarizers.py`)

New function:

```python
def summarize_reference_load(
    pattern: GraphPattern,
    reference_id: str,
) -> Dict[str, Any]:
    """Summarize loaded reference data for the load_reference tool response."""
    ref_nodes = _find_nodes_by_label(pattern, NodeLabel.REFERENCE)

    # Extract type from extra_labels
    types: set[str] = set()
    for n in ref_nodes:
        types.update(n.extra_labels)

    # Extract field names from all records (union of all property keys)
    all_fields: set[str] = set()
    for n in ref_nodes:
        all_fields.update(n.properties.keys())
    # Remove internal fields from the summary
    all_fields.discard("reference_id")

    return {
        "reference_id": reference_id,
        "type": sorted(types)[0] if len(types) == 1 else sorted(types),
        "record_count": len(ref_nodes),
        "fields": sorted(all_fields),
        "graph_structure": {
            "total_nodes": len(pattern.nodes),
            "total_relationships": len(pattern.relationships),
        },
    }
```

### Tool handler (`mcp_server/tools.py`)

```python
@mcp.tool()
def build_reference(reference_spec: str) -> str:
    try:
        spec = json.loads(reference_spec)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid JSON: {e}"})

    reference_id = spec.get("reference_id")
    if not reference_id:
        return json.dumps({"error": "Missing required field: reference_id"})

    try:
        pattern = build_reference_from_spec(spec)
    except (KeyError, TypeError, ValueError) as e:
        return json.dumps({"error": f"Build error: {e}"}, default=str)

    # No Gate 1 validation needed — Reference has empty PropertySchema
    # record_id uniqueness is validated in the builder

    try:
        conn = get_connection()
        save_counts = save_pattern(conn, pattern)
    except Exception as e:
        return json.dumps({"error": f"Neo4j save error: {e}"}, default=str)

    # Cache
    loaded = get_loaded_references()
    loaded[reference_id] = pattern

    total_nodes = sum(r.get("nodes_created", 0) for r in save_counts)

    return json.dumps({
        "reference_id": reference_id,
        "type": spec.get("type"),
        "record_count": len(pattern.nodes),
        "saved": True,
        "counts": {"nodes_created": total_nodes, "relationships_created": 0},
    }, indent=2, default=str)


@mcp.tool()
def load_reference(reference_id: str) -> str:
    try:
        conn = get_connection()
        pattern = load_reference_by_id(conn, reference_id)
    except Exception as e:
        return json.dumps({"error": f"Neo4j error: {e}"}, default=str)

    if not pattern.nodes:
        return json.dumps({"error": f"No records found for reference_id '{reference_id}'"})

    loaded = get_loaded_references()
    loaded[reference_id] = pattern

    summary = summarize_reference_load(pattern, reference_id)
    return json.dumps(summary, indent=2, default=str)
```

### Server-side state (`mcp_server/__init__.py`)

```python
_loaded_references: dict[str, GraphPattern] = {}

def get_loaded_references() -> dict[str, GraphPattern]:
    return _loaded_references
```

Follows the exact pattern of `_loaded_recipes` and `_loaded_formats`.

### Tool response: `build_reference`

```json
{
  "reference_id": "employee_roster_2026_q1",
  "type": "Employee",
  "record_count": 50,
  "saved": true,
  "counts": {
    "nodes_created": 50,
    "relationships_created": 0
  }
}
```

### Tool response: `load_reference`

```json
{
  "reference_id": "employee_roster_2026_q1",
  "type": "Employee",
  "record_count": 50,
  "fields": ["annual_salary", "department", "employee_type", "name", "record_id", "start_date"],
  "graph_structure": {
    "total_nodes": 50,
    "total_relationships": 0
  }
}
```

---

## Data Flow

```
JSON spec (agent provides reference collection)
    |
    v
builders.py build_reference_from_spec()
    |  Validates: reference_id present, record_id on every record, no duplicates
    |  Each record → Node(labels={REFERENCE}, extra_labels={type}, properties={...})
    |  _node_id = _generate_node_id(reference_id, "ref", record_id)
    v
logic.py build_reference_pattern(nodes)
    |  GraphPattern(nodes=..., relationships=[])
    v
tools.py build_reference()
    |  No Gate 1 needed (empty PropertySchema)
    |  save_pattern → MERGE on _node_id (idempotent)
    |  Cache in _loaded_references
    v
Neo4j: (:Reference:Employee {reference_id: "...", record_id: "...", name: "...", ...})
    |
    v
[Later] load_reference("employee_roster_2026_q1")
    |  load_reference_by_id → MATCH (n:Reference) WHERE n.reference_id = $id
    |  Cache in _loaded_references
    |  Return: type, record_count, fields
    v
Agent sees: 50 Employee records with fields [name, department, employee_type, ...]
    |
    v
[Later] Agent builds recipe with inline references (existing mechanism)
    OR agent reads reference data from cache and uses it in processing code
    |
    v
[Later] load_recipe loads recipe + hop query finds linked Reference nodes
```

---

## Examples

### Happy path: import employee roster

```json
// build_reference input
{
  "reference_id": "employee_roster_2026_q1",
  "type": "Employee",
  "records": [
    {"record_id": "emp_001", "name": "Jane Doe", "department": "Engineering", "employee_type": "salaried"},
    {"record_id": "emp_002", "name": "John Smith", "department": "Sales", "employee_type": "hourly"}
  ]
}

// build_reference response
{
  "reference_id": "employee_roster_2026_q1",
  "type": "Employee",
  "record_count": 2,
  "saved": true,
  "counts": {"nodes_created": 2, "relationships_created": 0}
}

// load_reference("employee_roster_2026_q1") response
{
  "reference_id": "employee_roster_2026_q1",
  "type": "Employee",
  "record_count": 2,
  "fields": ["department", "employee_type", "name", "record_id"],
  "graph_structure": {"total_nodes": 2, "total_relationships": 0}
}
```

### Happy path: import tax brackets

```json
// build_reference input
{
  "reference_id": "federal_tax_brackets_2026",
  "type": "TaxBracket",
  "records": [
    {"record_id": "bracket_1", "min_income": "0", "max_income": "11600", "rate": "0.10"},
    {"record_id": "bracket_2", "min_income": "11601", "max_income": "47150", "rate": "0.12"},
    {"record_id": "bracket_3", "min_income": "47151", "max_income": "100525", "rate": "0.22"}
  ]
}
```

### Happy path: import department allocation schedule

```json
// build_reference input
{
  "reference_id": "dept_allocation_2026",
  "type": "DepartmentAllocation",
  "records": [
    {"record_id": "alloc_eng", "department": "Engineering", "overhead_pct": "0.35", "cost_center": "CC100"},
    {"record_id": "alloc_sales", "department": "Sales", "overhead_pct": "0.25", "cost_center": "CC200"}
  ]
}
```

### Happy path: re-import (idempotent update)

```json
// Same reference_id, same record_ids, updated values
{
  "reference_id": "employee_roster_2026_q1",
  "type": "Employee",
  "records": [
    {"record_id": "emp_001", "name": "Jane Doe", "department": "Engineering", "annual_salary": "100000"},
    {"record_id": "emp_002", "name": "John Smith", "department": "Sales", "hourly_rate": "30.00"}
  ]
}

// Behavior: MERGE on _node_id matches existing nodes.
// SET updates all properties. Jane's salary updates to 100000.
// No duplicate nodes created.
// Note: properties from previous import that are NOT in the new import
// remain on the node (SET adds/updates, does not remove).
```

### Error case: missing record_id

```json
// Input — record without record_id
{
  "reference_id": "bad_roster",
  "type": "Employee",
  "records": [
    {"name": "Jane Doe", "department": "Engineering"}
  ]
}

// Response
{"error": "Build error: Record at index 0 is missing required field: record_id"}
```

### Error case: duplicate record_id

```json
// Input — two records with same record_id
{
  "reference_id": "dup_roster",
  "type": "Employee",
  "records": [
    {"record_id": "emp_001", "name": "Jane Doe"},
    {"record_id": "emp_001", "name": "John Smith"}
  ]
}

// Response
{"error": "Build error: Duplicate record_id 'emp_001' at index 1 in reference 'dup_roster'"}
```

### Edge case: empty records array

```json
// Input
{
  "reference_id": "empty_collection",
  "type": "Placeholder",
  "records": []
}

// Response
{
  "reference_id": "empty_collection",
  "type": "Placeholder",
  "record_count": 0,
  "saved": true,
  "counts": {"nodes_created": 0, "relationships_created": 0}
}
```

### Edge case: load nonexistent reference

```json
// load_reference("does_not_exist")
{"error": "No records found for reference_id 'does_not_exist'"}
```

---

## Invariants

### Graph semantics
- Reference nodes carry `NodeLabel.REFERENCE` in `Node.labels` and their business type in `Node.extra_labels`
- Reference nodes are standalone — no inter-node relationships within a reference collection
- Only `MappingRule`, `Condition`, and `AccountingRecipe` may source USES_REFERENCE edges (enforced by `validate_uses_reference`, unchanged)
- USES_REFERENCE edges are created by the recipe builder's inline mechanism, NOT by `build_reference`
- `reference_id` property on every node enables collection-level queries
- `_node_id` is deterministic: `_generate_node_id(reference_id, "ref", record_id)`
- Re-importing with same `reference_id` + `record_id` is idempotent (MERGE on `_node_id`)

### Functional constraints
- `build_reference_from_spec` is a pure function — validates inputs, creates Nodes, returns GraphPattern
- `build_reference_pattern` is a pure function — wraps nodes in GraphPattern
- `summarize_reference_load` is a pure function — extracts summary from GraphPattern
- `record_id` uniqueness validated in the builder (ValueError for duplicates)
- `type` stored in `extra_labels` only — not duplicated as a property

### Layer boundaries
- domain/ not modified at L1 or L2
- New L3 function follows existing builder pattern
- New L4 functions follow existing `load_format_by_id` / `delete_format_by_id` patterns
- Pure functions (builders, summarizers) do not import from persistence/
- Only tools.py accesses Neo4j via persistence layer

---

## Integration

### Files modified

| File | Change |
|------|--------|
| `domain/logic.py` | Add `build_reference_pattern` |
| `domain/__init__.py` | Export `build_reference_pattern` |
| `persistence/operations.py` | Add `load_reference_by_id`, `delete_reference_by_id` |
| `persistence/__init__.py` | Export new functions |
| `mcp_server/__init__.py` | Add `_loaded_references` state dict, `get_loaded_references` accessor |
| `mcp_server/builders.py` | Add `build_reference_from_spec` |
| `mcp_server/summarizers.py` | Add `summarize_reference_load` |
| `mcp_server/tools.py` | Add `build_reference` and `load_reference` tool handlers |
| `tests/domain/test_logic.py` | Add tests for `build_reference_pattern` |
| `tests/mcp_server/test_builders.py` | Add tests for `build_reference_from_spec` |
| `tests/mcp_server/test_summarizers.py` | Add tests for `summarize_reference_load` |

### Files created

None.

### Canonical counts affected

| Constant | Before | After | Delta |
|----------|--------|-------|-------|
| MCP Tools | 6 | 8 | +2 |
| `Total tests` | 362 | ~382 | +~20 |

No changes to NodeLabel, RelationshipType, ontology, or constraint counts.

---

## Test Strategy

### New logic tests (`tests/domain/test_logic.py`)

| Test class / method | What it verifies |
|---------------------|-----------------|
| `TestBuildReferencePattern::test_single_node` | One node produces GraphPattern with 1 node, 0 rels |
| `TestBuildReferencePattern::test_multiple_nodes` | Multiple nodes all present in pattern |
| `TestBuildReferencePattern::test_empty_list` | Empty list produces empty GraphPattern |
| `TestBuildReferencePattern::test_no_relationships` | Relationships list is always empty |

### New builder tests (`tests/mcp_server/test_builders.py`)

| Test class / method | What it verifies |
|---------------------|-----------------|
| `TestBuildReference::test_node_ids_deterministic` | `_node_id = reference_id_ref_record_id` |
| `TestBuildReference::test_properties_stored` | All record fields become node properties |
| `TestBuildReference::test_reference_id_on_all_nodes` | Every node has `reference_id` property |
| `TestBuildReference::test_record_id_on_all_nodes` | Every node has `record_id` property |
| `TestBuildReference::test_type_in_extra_labels` | Business type in `extra_labels`, NOT in properties |
| `TestBuildReference::test_type_not_in_properties` | `type` key absent from `Node.properties` |
| `TestBuildReference::test_missing_record_id_raises` | Missing `record_id` raises ValueError with index |
| `TestBuildReference::test_duplicate_record_id_raises` | Duplicate `record_id` raises ValueError with index |
| `TestBuildReference::test_empty_records` | Empty records array produces empty pattern |

### New summarizer tests (`tests/mcp_server/test_summarizers.py`)

| Test class / method | What it verifies |
|---------------------|-----------------|
| `TestReferenceLoad::test_record_count` | Correct count in summary |
| `TestReferenceLoad::test_type_from_extra_labels` | Type extracted from `extra_labels` |
| `TestReferenceLoad::test_fields_extracted` | Union of all property keys in `fields` list |
| `TestReferenceLoad::test_reference_id_excluded_from_fields` | `reference_id` not in `fields` |
| `TestReferenceLoad::test_empty_pattern` | Empty pattern handled gracefully |

### Existing tests

All existing tests pass unchanged. No existing tool signatures, builder functions, or summarizer functions are modified. The inline `references[]` mechanism in `_build_recipe_nodes` is untouched.

### Expected new test count

Current: 362 | Added: ~20 | New total: ~382

---

## Success Criteria

- [ ] `build_reference` accepts JSON spec and creates Reference nodes in Neo4j
- [ ] Each record becomes a Reference node with `NodeLabel.REFERENCE` and business type in `extra_labels`
- [ ] `_node_id` is deterministic: `_generate_node_id(reference_id, "ref", record_id)`
- [ ] `reference_id` stored as property on every node for collection queries
- [ ] `type` stored in `extra_labels` only — NOT duplicated in properties
- [ ] Re-importing same spec updates existing nodes (idempotent via MERGE on `_node_id`)
- [ ] Missing `record_id` returns clear error with record index
- [ ] Duplicate `record_id` returns clear error with record index
- [ ] `load_reference` loads from Neo4j, caches in `_loaded_references`, returns summary
- [ ] Summary includes type, record_count, and field names
- [ ] `load_reference` for nonexistent `reference_id` returns clear error
- [ ] Inline `references[]` in pipeline specs continues to work unchanged
- [ ] `load_pattern_by_recipe` hop query finds Reference nodes linked via USES_REFERENCE (existing behavior, no changes needed)
- [ ] All existing tests pass (no regressions)
- [ ] MCP tool count updated to 8 in CLAUDE.md and count tests

---

## Out of Scope

- **Cross-tool linking (`external_references`)**: Creating USES_REFERENCE edges from a recipe to pre-imported Reference nodes requires computing `_node_id` across tool boundaries — implicit coupling via naming convention. Deferred to a future Tier 2 `link_reference` tool that would query Neo4j for the target node by `reference_id` + `record_id`, not regenerate its `_node_id`.
- **CSV import parsing**: `build_reference` accepts JSON. Converting CSV to the JSON spec format is the agent's responsibility. The agent reads the CSV, structures the records, and calls the tool. This keeps the tool simple and format-agnostic.
- **Reference data schema enforcement**: The knowledge zone is deliberately schema-free. Optional schema validation for reference data would contradict the two-zone design principle.
- **Reference data versioning**: Tracking changes over time. The `reference_id` naming convention supports temporal collections (`employee_roster_2026_q1` vs `_q2`), but there's no built-in diff or migration mechanism.
- **Stale property removal on re-import**: MERGE + SET adds/updates properties but does not remove properties from previous imports. If a field existed in a prior import but not in the new one, it persists on the node. A `replace` mode (DELETE + CREATE instead of MERGE) could address this but is not included in this spec.
- **Surfacing reference data in `get_processing_instructions`**: The summarizer for processing instructions could include a `reference_data` section when USES_REFERENCE edges exist. This is useful but couples reference awareness into the recipe workflow. Defer to a follow-on spec that wires reference data into the condition and processing instruction pipeline.

---

## Open Questions

- [ ] **Should `build_reference` support a `replace` mode?** Current behavior: MERGE + SET updates properties but doesn't remove old ones. A `replace: true` flag could DELETE existing nodes for the `reference_id` before creating new ones, ensuring a clean import. Trade-off: simpler mental model but destructive if USES_REFERENCE edges exist from recipes. (Decide by: first user who re-imports with changed record structure.)
