# Spec: Summarizer Bug Fixes + Patch Recipe Feedback Loop

> **Status:** Draft
> **Created:** 2026-02-21
> **Spec type:** Feature

---

## Purpose

The LLM processing pipeline has two reliability problems: (1) `summarize_processing_instructions` strips critical metadata from OutputColumn nodes and silently omits `group_by` when absent, making the LLM unable to distinguish "aggregate all rows" from "instructions incomplete"; (2) when the LLM makes a processing mistake and the user corrects it, there is no way to persist those corrections back to the graph — the next `get_processing_instructions` call returns the same stale metadata. This spec fixes both summarizer bugs and adds a `patch_recipe` tool that closes the feedback loop.

---

## Layer Placement

**Primary layer:** L4 (Persistence) + L5 (MCP Server)
**Layers touched:**

| Layer | Package | What changes |
|-------|---------|--------------|
| L1 Types | `domain/types.py` / `types_recipe.py` | No changes — all types already exist |
| L2 Ontology | `domain/ontology.py` / `ontology_recipe.py` | No changes — property schemas already define required/optional fields |
| L3 Logic | `domain/logic.py` | No changes — extractors are unchanged |
| L4 Persistence | `persistence/operations.py` | New `patch_node` function (MATCH + SET) |
| L5 MCP Server | `mcp_server/summarizers.py`, `mcp_server/tools.py` | Bug fixes + new `patch_recipe` tool |

---

## Domain Types (L1)

No Layer 1 changes required. All node types targeted by `patch_recipe` — `Measure`, `MappingRule`, `AccountSlot`, `OutputColumn` — already exist as frozen dataclasses with the correct fields.

**Immutability check:** No new dataclasses. Existing frozen dataclasses are not modified.

---

## Schema Definitions (L2)

No Layer 2 changes required. The `_validate_patch_request` helper (L5) reads from the existing `merged_ontology()` property schemas to determine which fields are optional (patchable) vs required (immutable). No new schemas, validators, or ontology entries are needed.

**Declarative check:** Patch validation is driven by existing `PropertySchema.optional` and `PropertySchema.types` — no scattered `if` statements.

**Validators affected:** None modified. `_validate_patch_request` (new, L5) consumes schema data but is not an ontology validator.

**Gate classification:**
- Gate 1: No new Gate 1 validators. Existing `validate_node_properties` already validates any properties on nodes.
- Gate 2: No Gate 2 impact — patches modify template-level metadata, not runtime entries.

---

## Pure Functions (L3)

No Layer 3 changes required. Extractors (`extract_measures_for_schema`, `extract_output_columns`, etc.) and builders are unchanged.

---

## Persistence Contract (L4)

### New operation: `patch_node`

```python
def patch_node(
    conn: Neo4jConnection,
    label: str,
    merge_props: Dict[str, Any],
    patch_props: Dict[str, Any],
) -> Dict[str, Any]:
    """Partially update optional properties on an existing node.

    Uses MATCH + SET (not MERGE) so it fails clearly if the node doesn't exist.
    Returns the node's properties after update (internal _-prefixed keys excluded).
    Raises ValueError if no node matches merge_props.
    """
```

**Design decision — MATCH + SET, not MERGE:** MERGE would silently create a new node if the identity props don't match. `patch_node` targets existing graph nodes for property updates, so a missing node is always a caller error. MATCH + SET surfaces this clearly via `ValueError`.

- **Merge keys:** No changes to `MERGE_KEYS` registry.
- **Serialization:** No changes — `patch_node` writes directly via Cypher, not through the serializer pipeline.
- **Deserialization:** No changes — `patch_node` returns raw properties dict, not a domain `Node`.

**Security constraint:** The `label` parameter and `merge_props`/`patch_props` keys are interpolated into Cypher via f-string. The caller (`patch_recipe` tool) must ensure these values come from the validated `_PATCHABLE_NODES` registry (enum `.value` strings and ontology-validated property names), never from raw user input.

---

## MCP Interface (L5)

### Part A: Summarizer bug fixes

#### Bug A — OutputColumn metadata stripped (`summarizers.py:246-248`)

Current code emits only `{position, name}` per column. The fix emits all non-None properties from the OutputColumn schema, using `if v is not None` (not `if v`) to preserve boolean `False` values like `required=False` and `exclude_from_output=False`.

Current (lines 246-248):
```python
"columns": [
    {"position": _prop(c, "position"), "name": _prop(c, "name")}
    for c in out_cols_sorted
],
```

After:
```python
"columns": [
    {
        k: v for k, v in {
            "position":            _prop(c, "position"),
            "name":                _prop(c, "name"),
            "data_type":           _prop(c, "data_type"),
            "required":            _prop(c, "required"),
            "description":         _prop(c, "description"),
            "source_mapping":      _prop(c, "source_mapping"),
            "sign_convention":     _prop(c, "sign_convention"),
            "format_pattern":      _prop(c, "format_pattern"),
            "exclude_from_output": _prop(c, "exclude_from_output"),
        }.items()
        if v is not None
    }
    for c in out_cols_sorted
],
```

#### Bug B — `group_by` silently absent (`summarizers.py:184-186`)

When a Measure has no `group_by`, the key is omitted. The LLM cannot distinguish "aggregate all rows" from "instructions incomplete."

Current (lines 184-186):
```python
group_by_str = _prop(m, "group_by")
if group_by_str:
    measure_entry["group_by"] = json.loads(group_by_str)
```

After:
```python
group_by_str = _prop(m, "group_by")
if group_by_str:
    measure_entry["group_by"] = json.loads(group_by_str)
else:
    measure_entry["group_by"] = []
```

**Note:** The storage format is JSON (via `json.dumps`/`json.loads` in `builders.py:99` / `summarizers.py:186`), not comma-separated. The fix preserves `json.loads` and adds the `else: []` branch.

### Part B: New `patch_recipe` tool

#### Tool signature

```python
@mcp.tool()
def patch_recipe(
    recipe_id: str,
    node_type: str,
    node_key: str,
    patches: str,
) -> str:
    """Partially update optional properties on a recipe or format node.

    Persists corrections to the graph so future get_processing_instructions
    calls include the updated metadata. Only optional properties can be
    patched — required/identity fields are immutable.

    Args:
        recipe_id: The recipe_id (or format_id for output_column) scoping the node
        node_type: One of "measure", "mapping_rule", "account_slot", "output_column"
        node_key: JSON object with identity fields (e.g. {"name": "total_gross"})
        patches: JSON object with properties to update (e.g. {"description": "..."})
    """
```

#### Registry (`_PATCHABLE_NODES`)

```python
_PATCHABLE_NODES = {
    # node_type: (NodeLabel, identity_fields, scope_key)
    "measure":       (NodeLabel.MEASURE,      ("recipe_id", "name"),      "recipe_id"),
    "mapping_rule":  (NodeLabel.MAPPING_RULE,  ("recipe_id", "rule_name"), "recipe_id"),
    "account_slot":  (NodeLabel.ACCOUNT_SLOT,  ("recipe_id", "slot_id"),   "recipe_id"),
    "output_column": (NodeLabel.OUTPUT_COLUMN, ("format_id",  "name"),     "format_id"),
}
```

#### Pure validation helper

```python
def _validate_patch_request(
    node_type: str,
    node_key: dict,
    patches: dict,
) -> Optional[str]:
    """Validate a patch request against the ontology. Returns error string or None."""
```

Validates:
1. `node_type` is in `_PATCHABLE_NODES`
2. `node_key` has all identity fields for that type
3. All `patches` keys are in `PropertySchema.optional` (not required)
4. All `patches` values match `PropertySchema.types` for their key

#### Cache invalidation

After a successful `patch_node` write, the tool evicts the stale cached pattern:
- `_loaded_recipes.pop(recipe_id, None)` for recipe-scoped nodes
- `_loaded_formats.pop(format_id, None)` for format-scoped nodes

This forces the next `get_processing_instructions` or `load_recipe` call to re-fetch from Neo4j with the updated properties.

### Summarizer output

After Bug A fix, the output columns section of `get_processing_instructions` gains all OutputColumn properties:

```json
{
  "output_format": {
    "columns": [
      {
        "position": 1,
        "name": "Transaction Date",
        "data_type": "date",
        "required": true,
        "source_mapping": "pay_date",
        "format_pattern": "MM/DD/YYYY"
      },
      {
        "position": 2,
        "name": "Memo",
        "data_type": "string",
        "required": false
      }
    ]
  }
}
```

After Bug B fix, measures always include `group_by`:

```json
{
  "measures": [
    {
      "name": "total_gross",
      "operation": "sum",
      "column": "gross_pay",
      "group_by": []
    }
  ]
}
```

---

## Data Flow

### Bug fixes (Part A)

```
Neo4j (existing OutputColumn/Measure nodes)
    |
    v
load_recipe / load_format → cached GraphPattern
    |
    v
summarizers.py — summarize_processing_instructions()
    |  Bug A fix: emit all non-None OutputColumn properties
    |  Bug B fix: always emit group_by ([] when absent)
    v
JSON response (LLM reads complete instructions)
```

### Patch feedback loop (Part B)

```
LLM makes processing error → User corrects
    |
    v
patch_recipe(recipe_id, node_type, node_key, patches)
    |
    v
tools.py _validate_patch_request()
    |  Check: node_type valid, identity fields present,
    |  patches are optional-only, types match schema
    v
persistence/operations.py patch_node()
    |  MATCH (n:Label) WHERE identity props
    |  SET n.prop = value
    v
Neo4j (node updated in place)
    |
    v
Cache eviction: _loaded_recipes.pop(recipe_id)
    |
    v
Next get_processing_instructions() → re-loads from Neo4j
    |
    v
JSON response (LLM reads corrected instructions)
```

---

## Examples

### Happy path: patch a Measure description

```json
// Tool call
{
  "recipe_id": "payroll_v1",
  "node_type": "measure",
  "node_key": "{\"name\": \"total_gross\"}",
  "patches": "{\"description\": \"Sum of gross pay, aggregate all rows\"}"
}

// Response
{
  "node_type": "measure",
  "node_key": {"recipe_id": "payroll_v1", "name": "total_gross"},
  "patches_applied": {"description": "Sum of gross pay, aggregate all rows"},
  "updated_properties": {
    "recipe_id": "payroll_v1",
    "name": "total_gross",
    "operation": "sum",
    "description": "Sum of gross pay, aggregate all rows"
  },
  "cache_invalidated": "payroll_v1"
}
```

### Happy path: patch an OutputColumn source_mapping

```json
// Tool call
{
  "recipe_id": "qb_journal_v1",
  "node_type": "output_column",
  "node_key": "{\"name\": \"Transaction Date\"}",
  "patches": "{\"source_mapping\": \"pay_date\", \"format_pattern\": \"MM/DD/YYYY\"}"
}

// Response
{
  "node_type": "output_column",
  "node_key": {"format_id": "qb_journal_v1", "name": "Transaction Date"},
  "patches_applied": {"source_mapping": "pay_date", "format_pattern": "MM/DD/YYYY"},
  "updated_properties": {
    "format_id": "qb_journal_v1",
    "name": "Transaction Date",
    "position": 1,
    "data_type": "date",
    "required": true,
    "source_mapping": "pay_date",
    "format_pattern": "MM/DD/YYYY"
  },
  "cache_invalidated": "qb_journal_v1"
}
```

### Error case: patching a required field

```json
// Tool call
{
  "recipe_id": "payroll_v1",
  "node_type": "measure",
  "node_key": "{\"name\": \"total_gross\"}",
  "patches": "{\"name\": \"renamed_gross\"}"
}

// Response
{
  "error": "Cannot patch required field(s): name. Only optional properties can be patched.",
  "hint": "Optional fields for measure: description, group_by, split_by, split_column"
}
```

### Error case: invalid node_type

```json
// Tool call
{
  "recipe_id": "payroll_v1",
  "node_type": "account",
  "node_key": "{\"code\": \"6100\"}",
  "patches": "{\"name\": \"Updated\"}"
}

// Response
{
  "error": "Invalid node_type 'account'. Must be one of: measure, mapping_rule, account_slot, output_column"
}
```

### Edge case: node not found in graph

```json
// Tool call
{
  "recipe_id": "payroll_v1",
  "node_type": "measure",
  "node_key": "{\"name\": \"nonexistent_measure\"}",
  "patches": "{\"description\": \"test\"}"
}

// Response
{
  "error": "No Measure node found matching {'recipe_id': 'payroll_v1', 'name': 'nonexistent_measure'}"
}
```

### Edge case: Bug B — group_by absent vs present

```json
// Measure with no group_by stored
// Before fix: {"name": "total_gross", "operation": "sum", "column": "gross_pay"}
// After fix:  {"name": "total_gross", "operation": "sum", "column": "gross_pay", "group_by": []}

// Measure with group_by stored as JSON string '["pay_date"]'
// Output:     {"name": "total_gross", "operation": "sum", "column": "gross_pay", "group_by": ["pay_date"]}
```

### Edge case: Bug A — boolean False preserved

```json
// OutputColumn with required=false, exclude_from_output=false
// Before fix: {"position": 3, "name": "Notes"}
// After fix:  {"position": 3, "name": "Notes", "data_type": "string", "required": false, "exclude_from_output": false}
```

---

## Invariants

### Graph semantics
- `patch_node` uses MATCH + SET — it never creates new nodes
- Only optional properties can be patched — required/identity fields are immutable
- Patches are additive — they add or update properties but do not remove them
- No structural changes — relationships, labels, and node identity are untouched

### Functional constraints
- `_validate_patch_request` is a pure function (no I/O, no side effects)
- `summarize_processing_instructions` remains a pure function
- `group_by` is always present in processing instructions output (`[]` or populated list)
- OutputColumn properties use `is not None` filtering — boolean `False` is preserved

### Purity boundaries
- **New functions that are pure** (no I/O): `_validate_patch_request` (in `tools.py`)
- **New functions that touch I/O**: `patch_node` (in `operations.py` — runs Cypher via `conn`), `patch_recipe` (in `tools.py` — calls `patch_node`, reads/writes cache)
- **Composition approach**: `_validate_patch_request` reads from `merged_ontology()` (existing L2 merge function) and returns an error string or None. The tool handler composes validation → persistence → cache eviction sequentially.
- domain/ must never import from persistence/ or mcp_server/
- Pure functions (builders, summarizers) must not import from persistence/

---

## Integration

### Files modified

| File | Change |
|------|--------|
| `mcp_server/summarizers.py` | Bug A: emit all OutputColumn properties with `is not None` filter. Bug B: always emit `group_by` (add `else: []` branch) |
| `mcp_server/tools.py` | Add `_PATCHABLE_NODES` registry, `_validate_patch_request` helper, `patch_recipe` tool handler |
| `persistence/operations.py` | Add `patch_node` function |
| `persistence/__init__.py` | Add `"patch_node"` to imports and `__all__` |
| `tests/mcp_server/test_summarizers.py` | Fix broken assertion (line 642) + 5 new tests |
| `tests/persistence/test_operations.py` | Add `TestPatchNode` class (2 integration tests) |
| `CLAUDE.md` | Update canonical counts: MCP Tools 6→7, Total tests 394→~408 |
| `mcp_server/CLAUDE.md` | Add `patch_recipe` to tools table (6→7 rows) |
| `persistence/CLAUDE.md` | Add `patch_node` to operations list |

### Files created (justify each)

| File | Why an existing file can't absorb this |
|------|----------------------------------------|
| `tests/mcp_server/test_patch_recipe.py` | `_validate_patch_request` is a new pure validation function with its own test matrix (7 cases). Adding these to `test_summarizers.py` or `test_builders.py` would mix concerns — those files test data transformation, not patch validation. |

### Canonical counts affected

| Constant | Before | After | Delta |
|----------|--------|-------|-------|
| MCP Tools | 6 | 7 | +1 |
| Total tests | 394 | ~408 | +~14 |

**Count-assertion tests:**
- MCP Tools count: currently not test-asserted (documented in CLAUDE.md only). No new count test needed.
- Total tests count: documented in CLAUDE.md, not test-asserted. Update the documented count.

---

## Test Strategy

### New tests

| Test file | Test class / method | What it verifies |
|-----------|-------------------|-----------------|
| `tests/mcp_server/test_summarizers.py` | `TestSummarizeProcessingInstructions::test_group_by_always_emitted` | `group_by` present on every measure, `[]` when not set |
| `tests/mcp_server/test_summarizers.py` | `TestSummarizeProcessingInstructions::test_output_columns_include_data_type_and_required` | `data_type` and `required` present when set on OutputColumn |
| `tests/mcp_server/test_summarizers.py` | `TestSummarizeProcessingInstructions::test_output_column_required_false_is_present` | Boolean `False` survives `is not None` filter |
| `tests/mcp_server/test_summarizers.py` | `TestSummarizeProcessingInstructions::test_output_columns_include_source_mapping_when_set` | Optional `source_mapping` field appears when set |
| `tests/mcp_server/test_summarizers.py` | `TestSummarizeProcessingInstructions::test_output_columns_omit_absent_optionals` | Absent optional properties not in JSON output |
| `tests/mcp_server/test_patch_recipe.py` | `TestValidatePatchRequest::test_invalid_node_type_rejected` | Unknown node_type returns error |
| `tests/mcp_server/test_patch_recipe.py` | `TestValidatePatchRequest::test_valid_node_types_accepted` | All 4 registered types pass |
| `tests/mcp_server/test_patch_recipe.py` | `TestValidatePatchRequest::test_required_field_patch_rejected` | Patching `name` on Measure returns error |
| `tests/mcp_server/test_patch_recipe.py` | `TestValidatePatchRequest::test_unknown_field_patch_rejected` | Patching `nonexistent_field` returns error |
| `tests/mcp_server/test_patch_recipe.py` | `TestValidatePatchRequest::test_optional_field_patch_accepted` | Patching `description` on Measure passes |
| `tests/mcp_server/test_patch_recipe.py` | `TestValidatePatchRequest::test_wrong_type_in_patch_rejected` | String value for `priority` (int field) on MappingRule returns error |
| `tests/mcp_server/test_patch_recipe.py` | `TestValidatePatchRequest::test_missing_identity_field_rejected` | Node key missing required identity field returns error |
| `tests/persistence/test_operations.py` | `TestPatchNode::test_patch_updates_property_and_returns_new_props` | Successful patch returns updated properties |
| `tests/persistence/test_operations.py` | `TestPatchNode::test_patch_nonexistent_node_raises_value_error` | Missing node raises ValueError |

### Existing tests

- `test_measure_no_aggregation_fields` (line 638-644): assertion changes from `assert "group_by" not in m` to `assert m["group_by"] == []`. All other assertions in this test (`split_by`, `split_column`) remain unchanged.
- All other existing summarizer, builder, persistence, and domain tests must pass unchanged.

### Expected new test count

Current: 394 | Added: ~14 | New total: ~408

---

## Success Criteria

- [ ] `group_by` always present in processing instructions measures (`[]` when absent, populated list when set)
- [ ] OutputColumn processing instructions include `data_type`, `required`, `description`, `source_mapping`, `sign_convention`, `format_pattern`, `exclude_from_output` when set
- [ ] Boolean `False` values (`required=False`, `exclude_from_output=False`) survive the `is not None` filter
- [ ] `patch_recipe` tool validates node_type against `_PATCHABLE_NODES` registry
- [ ] `patch_recipe` rejects patches to required/identity fields
- [ ] `patch_recipe` rejects patches with wrong value types
- [ ] `patch_recipe` successfully updates optional properties via MATCH + SET
- [ ] `patch_recipe` evicts stale cache entries after successful write
- [ ] `patch_node` raises `ValueError` when target node doesn't exist
- [ ] All existing tests pass (no regressions)
- [ ] Canonical counts updated in CLAUDE.md and package CLAUDE.md files

---

## Out of Scope

- **Part 1 (MCP setup):** User manually edits `~/.config/Claude/claude_desktop_config.json`. No code changes needed — documented in `docs/Patch_feedback_feature.md`.
- **Property removal:** `patch_node` adds/updates properties but cannot remove them. A future `REMOVE n.prop` operation could be added if needed.
- **Structural patching:** Changing relationships, labels, or identity fields requires delete + rebuild, not patch. This is intentional — structural changes should go through `build_and_save_pipeline`.
- **Batch patching:** The tool patches one node per call. A batch variant (multiple nodes in one request) is deferred.
- **Force-reload flag:** Adding a `force_reload=True` parameter to `load_recipe`/`get_processing_instructions` would complement cache eviction but is not part of this spec.

---

## Open Questions

None. The design is fully determined by the existing ontology schemas and persistence patterns.