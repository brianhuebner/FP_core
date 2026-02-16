# Spec: Measure Aggregation Properties Through Builder

> **Status:** Ready
> **Created:** 2026-02-16
> **Spec type:** Feature

---

## Purpose

The `Measure` dataclass (L1) and ontology schema (L2) already support `group_by`, `split_by`, and `split_column` properties, but the MCP builder (`mcp_server/builders.py:85-95`) silently drops them when parsing JSON pipeline specs. This means agents cannot configure per-measure grouping or splitting when building recipes through the MCP interface. Wiring these fields through the builder and surfacing them in the summarizer completes the data path so that agents processing data can apply the correct aggregation semantics.

---

## Layer Placement

**Primary layer:** L5 — MCP Server (builder + summarizer)
**Layers touched:**

| Layer | Package | What changes |
|-------|---------|--------------|
| L1 Types | `domain/types_recipe.py` | Nothing — `Measure` dataclass already has all three fields |
| L2 Ontology | `domain/ontology_recipe.py` | Nothing — `_MEASURE_PROPS` already declares all three as optional `str` |
| L3 Logic | `domain/logic.py` | Nothing — builders pass through node properties |
| L4 Persistence | `persistence/` | Nothing — properties serialize as node properties automatically |
| L5 MCP Server | `mcp_server/builders.py`, `mcp_server/summarizers.py` | Read fields from spec, emit in instructions |

---

## Domain Types (L1)

No Layer 1 changes required. The `Measure` dataclass already defines all three fields:

```python
# domain/types_recipe.py:77-85
@dataclass(frozen=True)
class Measure:
    recipe_id: str
    name: str
    operation: AggregationOp
    group_by: Tuple[str, ...] = ()      # Already exists
    split_by: Optional[str] = None       # Already exists
    split_column: Optional[str] = None   # Already exists
    description: Optional[str] = None
```

---

## Schema Definitions (L2)

No Layer 2 changes required. The ontology already declares these as optional string properties:

```python
# domain/ontology_recipe.py:109-121
_MEASURE_PROPS = PropertySchema(
    required=frozenset({"recipe_id", "name", "operation"}),
    optional=frozenset({"group_by", "split_by", "split_column", "description"}),
    types={
        ...
        "group_by": str,       # Already exists
        "split_by": str,       # Already exists
        "split_column": str,   # Already exists
        ...
    },
)
```

**Serialization convention for `group_by`:**

The domain type is `Tuple[str, ...]` (multiple column names) but the ontology stores it as `str` (single Neo4j property). Convention: **comma-separated string**, no spaces around commas.

```
Domain:   ("employee_id", "pay_date")
Graph:    "employee_id,pay_date"
JSON in:  ["employee_id", "pay_date"]
JSON out: ["employee_id", "pay_date"]
```

The builder joins on input; the summarizer splits on output. The Neo4j property stores the comma-joined form.

**Gate classification:**
- Gate 1 (template-time): `validate_node_properties` already validates these fields against `_MEASURE_PROPS` — no new Gate 1 logic needed
- Gate 2 (runtime): No Gate 2 impact — these are structural properties, not entry-level checks

---

## Pure Functions (L3)

No Layer 3 changes required. The `build_source_schema_pattern` function receives `measure_nodes` as pre-built `Node` objects — it does not inspect or filter their properties.

---

## Persistence Contract (L4)

No Layer 4 changes required. Node properties are serialized generically — any properties present on the `Node` object flow through to Cypher `SET` clauses via `serializers.py`. The merge key for `Measure` is `{"recipe_id", "name"}`, which is unchanged.

---

## MCP Interface (L5)

### Builder changes (`mcp_server/builders.py`)

In `_build_schema_nodes`, the measure-building loop (lines 85-101) currently reads only `name`, `operation`, `source_column`, and `description`. Add reading of `group_by`, `split_by`, and `split_column`:

```python
# Current (lines 87-93):
msr_props: Dict[str, Any] = {
    "recipe_id": recipe_id,
    "name": msr_spec["name"],
    "operation": msr_spec["operation"],
}
if msr_spec.get("description"):
    msr_props["description"] = msr_spec["description"]

# After:
msr_props: Dict[str, Any] = {
    "recipe_id": recipe_id,
    "name": msr_spec["name"],
    "operation": msr_spec["operation"],
}
if msr_spec.get("description"):
    msr_props["description"] = msr_spec["description"]

# group_by: JSON array → comma-separated string
group_by = msr_spec.get("group_by")
if group_by:
    msr_props["group_by"] = ",".join(group_by)

# split_by / split_column: pass through as-is
if msr_spec.get("split_by"):
    msr_props["split_by"] = msr_spec["split_by"]
if msr_spec.get("split_column"):
    msr_props["split_column"] = msr_spec["split_column"]
```

### JSON spec format

The measure section of the pipeline spec JSON gains three optional fields:

```json
{
  "schema": {
    "measures": [
      {
        "name": "total_gross_pay",
        "operation": "sum",
        "source_column": "gross_pay",
        "group_by": ["pay_date"],
        "description": "Total gross pay per pay date"
      },
      {
        "name": "total_net_pay",
        "operation": "sum",
        "source_column": "net_pay",
        "split_by": "department",
        "split_column": "department",
        "description": "Net pay split by department"
      }
    ]
  }
}
```

Field definitions:
- `group_by` (optional, `string[]`): Column names to group this measure by. Each name must match a column defined in the same schema's `columns` array.
- `split_by` (optional, `string`): Dimension name for splitting this measure into separate journal entry lines.
- `split_column` (optional, `string`): Source column whose distinct values drive the split. Must match a column name in the schema.

### Summarizer changes (`mcp_server/summarizers.py`)

In `summarize_processing_instructions`, the measures list construction (lines 166-170) currently emits `name`, `operation`, and `column`. Add `group_by`, `split_by`, and `split_column`:

```python
# Current (lines 166-170):
measures_list.append({
    "name": _prop(m, "name"),
    "operation": _prop(m, "operation"),
    "column": col_name,
})

# After:
measure_entry: Dict[str, Any] = {
    "name": _prop(m, "name"),
    "operation": _prop(m, "operation"),
    "column": col_name,
}
# group_by: comma-separated string → JSON array
group_by_str = _prop(m, "group_by")
if group_by_str:
    measure_entry["group_by"] = group_by_str.split(",")
# split_by / split_column: pass through
split_by = _prop(m, "split_by")
if split_by:
    measure_entry["split_by"] = split_by
split_column = _prop(m, "split_column")
if split_column:
    measure_entry["split_column"] = split_column
measures_list.append(measure_entry)
```

### Tool signatures affected

No tool signature changes. `build_and_save_pipeline` and `get_processing_instructions` already accept/return JSON strings — the change is in the content of those JSON payloads, not the function signatures.

---

## Data Flow

```
JSON spec (agent provides measure with group_by/split_by/split_column)
    |
    v
builders.py _build_schema_nodes()
    |  group_by: ["col_a", "col_b"] → ",".join → "col_a,col_b"
    |  split_by: "department" → pass through
    |  split_column: "department" → pass through
    v
Node(labels={MEASURE}, properties={"group_by": "col_a,col_b", ...})
    |
    v
Gate 1: validate_node_properties checks against _MEASURE_PROPS (already valid)
    |
    v
Neo4j: MERGE (Measure {recipe_id: ..., name: ...}) SET group_by = "col_a,col_b"
    |
    v
load_recipe → cached GraphPattern
    |
    v
summarizers.py summarize_processing_instructions()
    |  group_by: "col_a,col_b" → .split(",") → ["col_a", "col_b"]
    |  split_by: "department" → pass through
    |  split_column: "department" → pass through
    v
JSON response: {"measures": [{"group_by": ["col_a", "col_b"], ...}]}
```

---

## Examples

### Happy path: measure with group_by

```json
// Input (in pipeline spec measures array)
{
  "name": "total_gross_pay",
  "operation": "sum",
  "source_column": "gross_pay",
  "group_by": ["pay_date"],
  "description": "Gross pay grouped by pay date"
}

// Resulting Node properties
{
  "recipe_id": "payroll_monthly_v1",
  "name": "total_gross_pay",
  "operation": "sum",
  "group_by": "pay_date",
  "description": "Gross pay grouped by pay date"
}

// Processing instructions output
{
  "name": "total_gross_pay",
  "operation": "sum",
  "column": "gross_pay",
  "group_by": ["pay_date"]
}
```

### Happy path: measure with split_by and split_column

```json
// Input
{
  "name": "net_pay_by_dept",
  "operation": "sum",
  "source_column": "net_pay",
  "split_by": "department",
  "split_column": "department"
}

// Processing instructions output
{
  "name": "net_pay_by_dept",
  "operation": "sum",
  "column": "net_pay",
  "split_by": "department",
  "split_column": "department"
}
```

### Happy path: multiple group_by columns

```json
// Input
{
  "name": "total_gross_pay",
  "operation": "sum",
  "source_column": "gross_pay",
  "group_by": ["pay_date", "department"]
}

// Node property
{ "group_by": "pay_date,department" }

// Processing instructions output
{ "group_by": ["pay_date", "department"] }
```

### Edge case: empty group_by array

```json
// Input
{
  "name": "total_net_pay",
  "operation": "sum",
  "source_column": "net_pay",
  "group_by": []
}

// Behavior: empty array is falsy, so group_by is NOT stored as a property.
// Equivalent to omitting group_by entirely.
// Node properties: no "group_by" key
// Processing instructions: no "group_by" key in output
```

### Edge case: fields omitted (backward compatibility)

```json
// Input — existing specs without these fields continue to work unchanged
{
  "name": "total_gross_pay",
  "operation": "sum",
  "source_column": "gross_pay"
}

// Behavior: no group_by, split_by, or split_column in Node properties.
// Processing instructions: no group_by, split_by, or split_column in output.
// Fully backward compatible.
```

---

## Invariants

### Graph semantics
- Measure nodes are per-recipe — `group_by` on one Measure does not affect other Measures in the same schema
- The AGGREGATES relationship (Measure -> Column) is independent of group_by — AGGREGATES identifies *which* column provides the values, group_by identifies *how* to partition the aggregation
- `split_by` and `split_column` are independent of `group_by` — a measure can have any combination

### Functional constraints
- `_build_schema_nodes` remains a pure function (no I/O)
- `summarize_processing_instructions` remains a pure function (no I/O)
- Comma-join/split is a lossless round-trip for column names (column names cannot contain commas per the Column schema — `name` is a required string validated by the ontology)

### Layer boundaries
- No new imports needed — builders.py and summarizers.py already have all required imports
- domain/ is not modified — the boundary rule (domain/ never imports from persistence/ or mcp_server/) is preserved

---

## Integration

### Files modified

| File | Change |
|------|--------|
| `mcp_server/builders.py` | Read `group_by`, `split_by`, `split_column` from measure spec dict in `_build_schema_nodes` |
| `mcp_server/summarizers.py` | Emit `group_by`, `split_by`, `split_column` in measure entries in `summarize_processing_instructions` |
| `tests/mcp_server/test_builders.py` | Add tests for new measure properties |
| `tests/mcp_server/test_summarizers.py` | Add tests for new measure output fields |

### Files created

None.

### Canonical counts affected

No canonical count changes. No new NodeLabels, RelationshipTypes, ontology entries, or relationship constraints. The only change is the total test count:

| Constant | Before | After | Delta |
|----------|--------|-------|-------|
| `Total tests` | 347 | ~357 | +~10 |

---

## Test Strategy

### New builder tests (`tests/mcp_server/test_builders.py`)

| Test class / method | What it verifies |
|---------------------|-----------------|
| `TestBuildSchemaNodes::test_measure_group_by_single_column` | Single-element `group_by` array stores as simple string |
| `TestBuildSchemaNodes::test_measure_group_by_multiple_columns` | Multi-element `group_by` array stores as comma-joined string |
| `TestBuildSchemaNodes::test_measure_group_by_empty_array` | Empty `group_by` array does not create a property |
| `TestBuildSchemaNodes::test_measure_split_by` | `split_by` passes through as string property |
| `TestBuildSchemaNodes::test_measure_split_column` | `split_column` passes through as string property |
| `TestBuildSchemaNodes::test_measure_all_aggregation_fields` | All three fields together on one measure |
| `TestBuildPipeline::test_full_pipeline_with_measure_aggregation` | End-to-end: spec with aggregation fields builds valid graph |

### New summarizer tests (`tests/mcp_server/test_summarizers.py`)

| Test class / method | What it verifies |
|---------------------|-----------------|
| `TestProcessingInstructions::test_measure_group_by_emitted` | `group_by` string split into array in output |
| `TestProcessingInstructions::test_measure_split_by_emitted` | `split_by` appears in measure output |
| `TestProcessingInstructions::test_measure_no_aggregation_fields` | Omitted fields do not appear in output (backward compat) |

### Existing tests

All existing builder and summarizer tests must continue to pass. Existing measure specs that omit `group_by`, `split_by`, and `split_column` are unaffected because the new code only activates when those keys are present and truthy.

### Expected new test count

Current: 347 | Added: ~10 | New total: ~357

---

## Success Criteria

- [ ] `group_by: ["col_a", "col_b"]` in JSON spec produces `group_by: "col_a,col_b"` on Measure node
- [ ] `split_by` and `split_column` pass through from JSON spec to Measure node properties
- [ ] `summarize_processing_instructions` emits `group_by` as a JSON array (split from comma-separated)
- [ ] `summarize_processing_instructions` emits `split_by` and `split_column` when present
- [ ] Omitting all three fields produces identical behavior to current code (backward compatible)
- [ ] Empty `group_by: []` does not store a property (same as omitting)
- [ ] Full pipeline round-trip: build spec with fields -> save -> load -> instructions include fields
- [ ] All existing tests pass (no regressions)
- [ ] No canonical count changes needed (no new enums, schemas, or constraints)

---

## Out of Scope

- **Column name validation against schema**: Verifying that `group_by` column names exist in the schema's `columns` list. This is a useful validation but belongs in a new Gate 1 validator, not in the builder. Track as a future spec.
- **Propagation to process-data workflow**: The `process-data` prompt (Step 4) mentions "Apply any group_by or split_by dimensions" but the actual data processing logic is agent-side, not in FP_core. This spec only ensures the values are available in the processing instructions.
- **Changing the L1 type for group_by**: The `Measure.group_by` field is `Tuple[str, ...]` in the domain type but stored as `str` in the graph. This type mismatch is intentional — the graph layer uses string properties, and the serialization convention (comma-join) bridges the two.

---

## Open Questions

None. The design is fully determined by the existing type definitions and ontology schema.
