# Spec: Structured Gate 1 Error Objects

> **Status:** Ready
> **Created:** 2026-02-21
> **Spec type:** Feature

---

## Purpose

Gate 1 validation errors are currently returned as plain strings (e.g., `"Node SourceSchema missing required property: name"`). When an agent receives a failed `build_and_save_pipeline` or `build_output` response, it must parse these strings to determine which node failed, which property is missing, and what kind of error occurred. This is fragile and error-prone. Structured error objects (`{"error_type": "missing_required_property", "node_label": "SourceSchema", "field": "name"}`) let agents programmatically react to specific error types — for example, prompting the user for a missing field or auto-fixing a type mismatch.

---

## Layer Placement

**Primary layer:** L5 — MCP Server (summarizer only)
**Layers touched:**

| Layer | Package | What changes |
|-------|---------|--------------|
| L1 Types | `domain/types.py` / `types_recipe.py` | No changes |
| L2 Ontology | `domain/ontology.py` / `ontology_recipe.py` | No changes — error strings are preserved as-is |
| L3 Logic | `domain/logic.py` | No changes |
| L4 Persistence | `persistence/` | No changes |
| L5 MCP Server | `mcp_server/summarizers.py` | New `structurize_gate1_errors` function |

**Key design decision:** Error structuring happens **only in L5 summarizers**. L1-L3 validators continue to produce plain strings — this avoids changing the well-tested validation layer and keeps the structured parsing co-located with the JSON output formatting.

---

## Domain Types (L1)

No Layer 1 changes required. `ValidationResult.errors` remains `Tuple[str, ...]`. The structuring is a presentation-layer concern.

---

## Schema Definitions (L2)

No Layer 2 changes required. Validators continue to return `ValidationResult` with string errors. The L2 contract is unchanged.

---

## Pure Functions (L3)

No Layer 3 changes required. `validate_recipe`, `validate_pipeline_connectivity`, and `validate_output_format` continue to return `ValidationResult` with string errors.

---

## Persistence Contract (L4)

No Layer 4 changes required.

---

## MCP Interface (L5)

### New summarizer function (`mcp_server/summarizers.py`)

```python
def structurize_gate1_errors(
    errors: List[str],
) -> List[Dict[str, Any]]:
    """Parse Gate 1 error strings into structured dicts.

    Each known error format is matched by regex and decomposed into
    typed fields. Unknown formats fall back to {"error_type": "unknown",
    "message": original_string}.

    Returns a list of structured error dicts, one per input error string.
    """
```

**Regex pattern registry:**

The function maintains an internal list of `(compiled_regex, error_type, field_extractor)` tuples. Each regex matches a known error format from L2/L3 validators:

| # | Error source | Example error string | Structured output |
|---|-------------|---------------------|-------------------|
| 1 | `validate_node_properties` | `"Node SourceSchema missing required property: name"` | `{"error_type": "missing_required_property", "node_label": "SourceSchema", "field": "name"}` |
| 2 | `validate_node_properties` | `"Node Column property 'position' expected int, got str"` | `{"error_type": "wrong_type", "node_label": "Column", "field": "position", "expected": "int", "got": "str"}` |
| 3 | `validate_node_properties` | `"Node MappingRule has unknown property: foo"` | `{"error_type": "unknown_property", "node_label": "MappingRule", "field": "foo"}` |
| 4 | `validate_recipe` | `"Recipe node not found"` | `{"error_type": "missing_node", "node_label": "AccountingRecipe"}` |
| 5 | `validate_recipe` | `"Schema node not found"` | `{"error_type": "missing_node", "node_label": "SourceSchema"}` |
| 6 | `validate_recipe` | `"Rule 'gross_pay_entry' references unknown measure 'total_xyz'"` | `{"error_type": "unknown_measure_ref", "rule_name": "gross_pay_entry", "measure_name": "total_xyz"}` |
| 7 | `validate_pipeline_connectivity` | `"Measure 'total_gross' has no AGGREGATES relationship"` | `{"error_type": "missing_relationship", "node_label": "Measure", "node_name": "total_gross", "rel_type": "AGGREGATES"}` |
| 8 | `validate_pipeline_connectivity` | `"AccountSlot 'salary_dr' has no MAPPED_TO relationship"` | `{"error_type": "missing_relationship", "node_label": "AccountSlot", "node_name": "salary_dr", "rel_type": "MAPPED_TO"}` |
| 9 | `validate_pipeline_connectivity` | `"MappingRule 'gross_pay_entry' has no debit AccountSlot"` | `{"error_type": "missing_slot", "rule_name": "gross_pay_entry", "slot_role": "debit"}` |
| 10 | `validate_pipeline_connectivity` | `"MappingRule 'gross_pay_entry' has no credit AccountSlot"` | `{"error_type": "missing_slot", "rule_name": "gross_pay_entry", "slot_role": "credit"}` |
| 11 | `validate_output_format` | `"OutputFormat node not found"` | `{"error_type": "missing_node", "node_label": "OutputFormat"}` |
| 12 | `validate_output_format` | `"OutputFormat has no columns"` | `{"error_type": "no_columns", "node_label": "OutputFormat"}` |
| 13 | `validate_output_format` | `"Duplicate column position: 2"` | `{"error_type": "duplicate_position", "position": 2}` |
| 14 | `validate_node_properties` | `"Node AccountSlot property 'role' value 'invalid' not in allowed values"` | `{"error_type": "invalid_value", "node_label": "AccountSlot", "field": "role", "value": "invalid"}` |

**Fallback:** Any error string that doesn't match a known pattern produces:
```json
{"error_type": "unknown", "message": "the original error string"}
```

### Integration into existing summarizers

The `structurize_gate1_errors` function is called from two places:

**1. `summarize_build_result` (for `build_and_save_pipeline`):**

```python
# Current (line 328-329):
"errors": list(validation_result.errors),

# After:
"errors": structurize_gate1_errors(list(validation_result.errors)),
```

**2. `build_output` tool handler inline error dict (for `build_output`):**

```python
# Current (tools.py line 331):
"errors": list(merged.errors),

# After:
"errors": structurize_gate1_errors(list(merged.errors)),
```

### Breaking change

This changes `gate1_validation.errors` from `List[str]` to `List[Dict[str, Any]]`. Agents that parse the error list as strings will need to update. However:
- The `is_valid` boolean is unchanged — agents that only check validity are unaffected.
- The `message` field on unknown errors preserves the original string for backward compatibility.
- The `error_type` field is always present, making programmatic handling straightforward.

### Summarizer output

Before (current):
```json
{
  "gate1_validation": {
    "is_valid": false,
    "errors": [
      "Node SourceSchema missing required property: name",
      "Rule 'gross_pay_entry' references unknown measure 'total_xyz'"
    ],
    "warnings": []
  }
}
```

After:
```json
{
  "gate1_validation": {
    "is_valid": false,
    "errors": [
      {
        "error_type": "missing_required_property",
        "node_label": "SourceSchema",
        "field": "name"
      },
      {
        "error_type": "unknown_measure_ref",
        "rule_name": "gross_pay_entry",
        "measure_name": "total_xyz"
      }
    ],
    "warnings": []
  }
}
```

---

## Data Flow

```
build_and_save_pipeline / build_output
    |
    v
Gate 1 validators (L2/L3) → ValidationResult(errors=("string", ...))
    |
    v
summarize_build_result / inline build_output result
    |
    v
structurize_gate1_errors(["string", ...])
    |  Match each string against regex pattern list
    |  Extract typed fields (node_label, field, etc.)
    |  Fallback to {"error_type": "unknown", "message": original}
    v
List[Dict] — structured error objects in JSON response
```

---

## Examples

### Happy path: valid pipeline

No change — `errors` is an empty list regardless of format:

```json
{
  "gate1_validation": {
    "is_valid": true,
    "errors": [],
    "warnings": []
  }
}
```

### Error case: multiple structured errors

```json
{
  "gate1_validation": {
    "is_valid": false,
    "errors": [
      {
        "error_type": "missing_required_property",
        "node_label": "SourceSchema",
        "field": "name"
      },
      {
        "error_type": "wrong_type",
        "node_label": "Column",
        "field": "position",
        "expected": "int",
        "got": "str"
      },
      {
        "error_type": "missing_relationship",
        "node_label": "Measure",
        "node_name": "total_gross",
        "rel_type": "AGGREGATES"
      }
    ]
  }
}
```

### Edge case: unknown error format

```json
{
  "gate1_validation": {
    "is_valid": false,
    "errors": [
      {
        "error_type": "unknown",
        "message": "Some future validator produced this unexpected format"
      }
    ]
  }
}
```

### Edge case: no errors (validation passes)

```json
{
  "gate1_validation": {
    "is_valid": true,
    "errors": [],
    "warnings": []
  }
}
```

---

## Invariants

### Graph semantics
- No graph changes — this is a presentation-layer transformation only

### Functional constraints
- `structurize_gate1_errors` is a pure function (List[str] → List[Dict])
- Every input string produces exactly one output dict (1:1 mapping, order preserved)
- Unknown patterns always produce a valid dict with `error_type: "unknown"` (never raises)
- The function is additive — adding new regex patterns for future error formats does not affect existing patterns

### Layer boundaries
- L1-L3 validators are unchanged — they continue producing string errors
- Only L5 summarizers call `structurize_gate1_errors`
- No new imports needed in summarizers.py (uses `re` from stdlib)

---

## Integration

### Files modified

| File | Change |
|------|--------|
| `mcp_server/summarizers.py` | Add `structurize_gate1_errors(errors) -> List[Dict]` function; add `import re` |
| `mcp_server/summarizers.py` | Modify `summarize_build_result` to use `structurize_gate1_errors` for errors |
| `mcp_server/tools.py` | Modify `build_output` inline error dict to use `structurize_gate1_errors` |
| `tests/mcp_server/test_summarizers.py` | Add `TestStructurizeGate1Errors` class (~14 tests) |

### Files created

None.

### Canonical counts affected

| Constant | Before | After | Delta |
|----------|--------|-------|-------|
| Total tests | ~422 | ~436 | +~14 |

No changes to MCP tool count, NodeLabel, RelationshipType, or any other canonical constant.

---

## Test Strategy

### New tests (`tests/mcp_server/test_summarizers.py`)

| Test class / method | What it verifies |
|---------------------|-----------------|
| `TestStructurizeGate1Errors::test_missing_required_property` | Parses "Node X missing required property: Y" |
| `TestStructurizeGate1Errors::test_wrong_type` | Parses "Node X property 'Y' expected T1, got T2" |
| `TestStructurizeGate1Errors::test_unknown_property` | Parses "Node X has unknown property: Y" |
| `TestStructurizeGate1Errors::test_missing_recipe_node` | Parses "Recipe node not found" |
| `TestStructurizeGate1Errors::test_missing_schema_node` | Parses "Schema node not found" |
| `TestStructurizeGate1Errors::test_unknown_measure_ref` | Parses "Rule 'X' references unknown measure 'Y'" |
| `TestStructurizeGate1Errors::test_missing_aggregates_rel` | Parses "Measure 'X' has no AGGREGATES relationship" |
| `TestStructurizeGate1Errors::test_missing_mapped_to_rel` | Parses "AccountSlot 'X' has no MAPPED_TO relationship" |
| `TestStructurizeGate1Errors::test_missing_debit_slot` | Parses "MappingRule 'X' has no debit AccountSlot" |
| `TestStructurizeGate1Errors::test_missing_credit_slot` | Parses "MappingRule 'X' has no credit AccountSlot" |
| `TestStructurizeGate1Errors::test_missing_output_format_node` | Parses "OutputFormat node not found" |
| `TestStructurizeGate1Errors::test_no_columns` | Parses "OutputFormat has no columns" |
| `TestStructurizeGate1Errors::test_duplicate_position` | Parses "Duplicate column position: N" |
| `TestStructurizeGate1Errors::test_unknown_error_fallback` | Unrecognized string → `{"error_type": "unknown", "message": ...}` |
| `TestStructurizeGate1Errors::test_empty_list` | Empty input → empty output |
| `TestStructurizeGate1Errors::test_invalid_value` | Parses "Node X property 'Y' value 'Z' not in allowed values" |

### Existing tests

- `test_summarizers.py` tests for `summarize_build_result` that check `errors` field content will need updating — they currently assert `List[str]` and must be updated to assert `List[Dict]`.
- All other tests pass unchanged.

### Expected new test count

Current: ~422 | Added: ~14 | New total: ~436

---

## Success Criteria

- [ ] All 14+ known error formats are correctly parsed to structured dicts
- [ ] Unknown error strings produce `{"error_type": "unknown", "message": ...}` (never raise)
- [ ] `build_and_save_pipeline` errors section returns `List[Dict]` instead of `List[str]`
- [ ] `build_output` errors section returns `List[Dict]` instead of `List[str]`
- [ ] Empty error list → empty list (no change)
- [ ] Valid pipelines still return `"errors": []`
- [ ] `structurize_gate1_errors` is a pure function with no side effects
- [ ] All existing tests pass (updated assertions where needed)

---

## Out of Scope

- **L2/L3 error format changes:** Validators continue producing strings. A future spec could change validators to return structured errors natively, making the regex parsing unnecessary.
- **Gate 2 error structuring:** `validate_entries` errors follow a different format. A separate spec would handle Gate 2 structured errors.
- **Warning structuring:** Only errors are structured. Warnings remain as strings (they are rare and informational).
- **Error codes / numeric IDs:** No stable numeric error codes. The `error_type` string enum is sufficient for programmatic handling.
- **Localization:** Error messages are English only.

---

## Open Questions

None. The error string formats are deterministic (produced by known L2/L3 validators), and the regex patterns can be verified against the actual validator code.
