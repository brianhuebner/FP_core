# Spec: Programmatic Tool Calling — Designing MCP Tools for Code Execution

> **Status:** Draft
> **Created:** 2026-02-26
> **Spec type:** Feature

---

## Purpose

Today, an agent processing data through an FP_core recipe makes 4+ sequential MCP round-trips: `load_recipe` → `get_processing_instructions` → (agent computes) → `validate_entries`. Each round-trip passes full JSON results through the model's context window, consuming tokens and adding latency. The Anthropic blog ["Code Execution with MCP"](https://www.anthropic.com/engineering/code-execution-with-mcp) describes a pattern where agents write code that calls MCP tools programmatically — the model emits a code block once, and the execution environment runs it without the model in the loop for intermediate results.

This spec redesigns FP_core's MCP tool responses to support programmatic calling by adding **dynamic filtering** (return only what the caller asks for), **detail levels** (progressive disclosure), and **structured, code-friendly output** (stable field contracts that code can chain without model interpretation).

---

## Layer Placement

**Primary layer:** L5 — MCP Server
**Layers touched:**

| Layer | Package | What changes |
|-------|---------|--------------|
| L1 Types | `domain/types.py` or `types_recipe.py` | No changes |
| L2 Ontology | `domain/ontology.py` or `ontology_recipe.py` | No changes |
| L3 Logic | `domain/logic.py` | No changes |
| L4 Persistence | `persistence/` | No changes |
| L5 MCP Server | `mcp_server/tools.py`, `mcp_server/summarizers.py` | Add filtering params to tools, add detail levels to summarizers |

---

## Domain Types (L1)

No Layer 1 changes required. This feature modifies how existing data is surfaced through MCP responses, not the underlying domain model.

---

## Schema Definitions (L2)

No Layer 2 changes required. No new validators, schemas, or ontology entries.

**Gate classification:**
- Gate 1: No changes
- Gate 2: `validate_entries` gains a `filter` parameter but the underlying validation logic is unchanged

---

## Pure Functions (L3)

No Layer 3 changes required.

---

## Persistence Contract (L4)

No Layer 4 changes required.

---

## MCP Interface (L5)

### Design Principles

The blog identifies three patterns that make MCP tools efficient for programmatic calling:

1. **Dynamic filtering** — Large results are filtered before returning to the model. The execution environment handles the full dataset; the model sees only what it needs.
2. **Progressive disclosure** — Tools offer detail levels so callers can request minimal info first, then drill down.
3. **Code-chainable output** — Tool responses use stable field names and structures that code can destructure and pipe to the next tool without model interpretation.

### Tool signatures affected

#### 1. `get_processing_instructions` — Add `detail` and `filter_rules` parameters

This is the highest-value change. Processing instructions can be large (many rules × resolved accounts × conditions). A programmatic caller often needs only specific rules or just the measure list.

**Current signature:**
```python
def get_processing_instructions(recipe_id: str, format_id: str | None = None) -> str
```

**New signature:**
```python
def get_processing_instructions(
    recipe_id: str,
    format_id: str | None = None,
    detail: str | None = None,
    filter_rules: str | None = None,
) -> str
```

**`detail` parameter** (progressive disclosure):
| Value | What's returned | Token estimate |
|-------|----------------|---------------|
| `None` (default) | Full response (current behavior) | ~2000-5000 |
| `"measures_only"` | Only the `measures` array | ~200-500 |
| `"rules_only"` | Only the `rules` array (no output spec) | ~500-2000 |
| `"format_only"` | Only the `output_format` object | ~200-500 |
| `"summary"` | Counts only: `{measure_count, rule_count, has_format}` | ~50 |

**`filter_rules` parameter** (dynamic filtering):
- Comma-separated list of rule names to include
- When set, only matching rules appear in the `rules` array
- Other sections (measures, output_format) are unaffected
- Example: `filter_rules="gross_pay_entry,tax_entry"`

#### 2. `validate_entries` — Add `filter` parameter

**Current signature:**
```python
def validate_entries(entries: str, recipe_id: str | None = None) -> str
```

**New signature:**
```python
def validate_entries(
    entries: str,
    recipe_id: str | None = None,
    filter: str | None = None,
) -> str
```

**`filter` parameter** (dynamic filtering):
| Value | What's returned |
|-------|----------------|
| `None` (default) | Full response (current behavior) |
| `"errors_only"` | Only entries that failed validation (omit passing entries from `entries` array) |
| `"summary"` | Counts only: `{total, passed, failed, errors: [...]}` — no per-entry detail |

This is critical for programmatic calling. An agent processing 500 entries doesn't need 500 `"is_valid": true` objects in context — it needs to know if any failed, and which ones.

#### 3. `load_recipe` — Add `detail` parameter

**Current signature:**
```python
def load_recipe(recipe_id: str) -> str
```

**New signature:**
```python
def load_recipe(recipe_id: str, detail: str | None = None) -> str
```

**`detail` parameter:**
| Value | What's returned |
|-------|----------------|
| `None` (default) | Full response (current behavior) |
| `"summary"` | Node/relationship counts only: `{recipe_id, total_nodes, total_relationships, has_schema, has_output}` |

A programmatic caller that already knows the recipe structure (e.g., it just built and saved it) can use `detail="summary"` to confirm the load succeeded without re-reading the full summary.

#### 4. `load_format` — Add `detail` parameter

Same pattern as `load_recipe`:

```python
def load_format(format_id: str, detail: str | None = None) -> str
```

| Value | What's returned |
|-------|----------------|
| `None` (default) | Full response (current behavior) |
| `"summary"` | Counts only: `{format_id, column_count, has_validation_rules, has_entry_structure}` |

#### 5. `build_and_save_pipeline` and `build_output` — No changes

These tools already return concise, structured responses. Their output is naturally code-chainable: `saved: true/false`, `counts`, `errors[]`. No filtering needed.

### JSON spec format

No changes to input spec formats. This feature only affects response shaping.

### Summarizer output

New summarizer functions and modifications:

```python
# New function
def summarize_processing_summary(pattern: GraphPattern, recipe_id: str) -> dict:
    """Minimal summary: counts only, no content."""
    return {
        "recipe_id": recipe_id,
        "measure_count": ...,
        "rule_count": ...,
        "has_format": ...,
    }

# Modified function signature
def summarize_processing_instructions(
    pattern: GraphPattern,
    recipe_id: str,
    format_pattern: GraphPattern | None = None,
    detail: str | None = None,
    filter_rules: list[str] | None = None,
) -> dict:
    """Extended to support detail levels and rule filtering."""
    ...

# New function
def summarize_validation_summary(
    entries_results: list[dict],
    account_results: list[dict],
    merged: ValidationResult,
) -> dict:
    """Counts-only validation summary."""
    return {
        "total_entries": len(entries_results),
        "passed": sum(1 for e in entries_results if e["is_valid"]),
        "failed": sum(1 for e in entries_results if not e["is_valid"]),
        "errors": list(merged.errors),
        "warnings": list(merged.warnings),
    }

# New function
def summarize_recipe_summary(pattern: GraphPattern, recipe_id: str) -> dict:
    """Minimal recipe load summary: counts only."""
    return {
        "recipe_id": recipe_id,
        "total_nodes": len(pattern.nodes),
        "total_relationships": len(pattern.relationships),
        "has_schema": any(NodeLabel.SOURCE_SCHEMA in n.labels for n in pattern.nodes),
        "has_output": any(NodeLabel.OUTPUT_FORMAT in n.labels for n in pattern.nodes),
    }
```

---

## Data Flow

### Current: Model-in-the-loop for every step

```
Agent (model) ──call──► load_recipe ──full JSON──► Agent (model reads all)
Agent (model) ──call──► get_processing_instructions ──full JSON──► Agent (model reads all)
Agent (model) ──computes measures, generates entries──
Agent (model) ──call──► validate_entries ──full JSON──► Agent (model reads all)

Total: 3 round-trips, model processes ~6000-10000 tokens of tool output
```

### New: Code execution with filtered responses

```
Agent (model) emits code block:
┌──────────────────────────────────────────────────────────────────┐
│  recipe = load_recipe("payroll_v1", detail="summary")           │
│  instructions = get_processing_instructions("payroll_v1")       │
│  # ... compute measures from CSV using instructions ...         │
│  result = validate_entries(entries_json, "payroll_v1",           │
│                            filter="errors_only")                │
│  if result.failed > 0:                                          │
│      print(result)  # only failures surface to model            │
│  else:                                                          │
│      print(f"All {result.total} entries valid")                  │
└──────────────────────────────────────────────────────────────────┘

Execution environment runs all 3 calls without model.
Model sees only the final print output.

Total: 1 round-trip (model emits code), execution environment handles the rest
Token savings: ~80% reduction in tool output tokens
```

### Filtered response flow through summarizers

```
tool parameter (detail="measures_only")
    |
    v
tools.py — parse detail param, pass to summarizer
    |
    v
summarizers.py — branch on detail level:
    "summary"       → summarize_processing_summary()
    "measures_only" → summarize_processing_instructions(detail="measures_only")
    "rules_only"    → summarize_processing_instructions(detail="rules_only")
    "format_only"   → summarize_processing_instructions(detail="format_only")
    None            → summarize_processing_instructions() (full, current behavior)
    |
    v
JSON response (filtered, smaller)
```

---

## Examples

### Happy path: Programmatic data processing

An agent in a code execution environment writes:

```python
# Agent emits this code block — execution environment runs it
import json

# Step 1: Load recipe (minimal — just confirm it loaded)
recipe = json.loads(load_recipe("payroll_v1", detail="summary"))
assert recipe["total_nodes"] > 0, f"Recipe not found"

# Step 2: Get just the measures to know what to compute
measures = json.loads(get_processing_instructions(
    "payroll_v1", detail="measures_only"
))

# Step 3: Compute measures from source data
# (agent wrote this logic based on earlier inspection of full instructions)
import csv
totals = {}
with open("payroll_data.csv") as f:
    for row in csv.DictReader(f):
        for m in measures["measures"]:
            col = m["column"]
            totals[m["name"]] = totals.get(m["name"], 0) + float(row[col])

# Step 4: Get only the rules needed for the entries we're generating
rules = json.loads(get_processing_instructions(
    "payroll_v1", detail="rules_only"
))

# Step 5: Generate and validate entries
entries = []
for rule in rules["rules"]:
    amount = totals[rule["source_measure"]]
    entries.append({"lines": [
        {"account_code": rule["debits"][0]["account_code"],
         "direction": "debit", "amount": amount},
        {"account_code": rule["credits"][0]["account_code"],
         "direction": "credit", "amount": amount},
    ]})

result = json.loads(validate_entries(
    json.dumps(entries), "payroll_v1", filter="errors_only"
))
print(json.dumps(result, indent=2))
```

The model sees only the final `print` output. If all entries pass, the output is:

```json
{
  "total_entries": 3,
  "passed": 3,
  "failed": 0,
  "errors": [],
  "warnings": []
}
```

~50 tokens instead of ~1500.

### Happy path: Filtered rule lookup

```python
# Agent only needs the gross pay rule
instructions = json.loads(get_processing_instructions(
    "payroll_v1",
    filter_rules="gross_pay_entry"
))
```

Response:
```json
{
  "recipe_id": "payroll_v1",
  "measures": [...],
  "rules": [
    {
      "priority": 1,
      "name": "gross_pay_entry",
      "source_measure": "total_gross",
      "memo_template": "Gross pay accrual",
      "debits": [{"account_code": "6100", "account_name": "Salary Expense"}],
      "credits": [{"account_code": "2200", "account_name": "Payroll Payable"}]
    }
  ]
}
```

Only 1 rule instead of potentially many.

### Happy path: Validate 500 entries, only see failures

```python
result = json.loads(validate_entries(entries_json, "payroll_v1", filter="errors_only"))
```

If 2 of 500 fail:
```json
{
  "total_entries": 500,
  "passed": 498,
  "failed": 2,
  "entries": [
    {"entry_index": 47, "is_valid": false, "debit_total": "1500.00", "credit_total": "1400.00"},
    {"entry_index": 203, "is_valid": false, "debit_total": "800.00", "credit_total": "900.00"}
  ],
  "errors": ["Transaction is not balanced: debit=1500.00 credit=1400.00", "..."],
  "warnings": []
}
```

~200 tokens instead of ~5000.

### Edge case: Invalid detail level

```python
get_processing_instructions("payroll_v1", detail="invalid_value")
```

Response:
```json
{
  "error": "Invalid detail level: 'invalid_value'. Valid values: summary, measures_only, rules_only, format_only",
  "hint": "Omit the detail parameter for the full response."
}
```

### Edge case: filter_rules matches no rules

```python
get_processing_instructions("payroll_v1", filter_rules="nonexistent_rule")
```

Response: Full response structure but with `"rules": []` — empty array, not an error. The caller's code can check `len(rules) == 0`.

### Edge case: Backward compatibility

All new parameters default to `None`, so existing callers see zero behavior change:

```python
# These two calls produce identical output:
get_processing_instructions("payroll_v1")
get_processing_instructions("payroll_v1", detail=None, filter_rules=None)
```

---

## Invariants

### Graph semantics
- No changes to the Neo4j graph. Filtering is response-side only.
- Cached `GraphPattern` objects are never modified by filtering — summarizers read from them and produce filtered output dicts.

### Functional constraints
- All new summarizer functions are pure (no I/O, no side effects)
- `detail` and `filter` parameters are validated in `tools.py` before reaching summarizers
- Default behavior (`None` for all new params) is identical to current behavior — zero regression risk
- `filter_rules` is applied after full summarization, as a post-filter on the `rules` list. This means rule filtering doesn't affect measure extraction or output format logic.

### Purity boundaries
- **New functions that are pure** (no I/O):
  - `summarize_processing_summary()` — counts only
  - `summarize_validation_summary()` — counts only
  - `summarize_recipe_summary()` — counts only
  - `summarize_format_summary()` — counts only
- **New functions that touch I/O**: None — filtering logic lives in `tools.py` (which already does I/O) and delegates to pure summarizers
- **Composition approach**: New summarizer functions compose alongside existing ones. `tools.py` dispatches to the appropriate summarizer based on the `detail` parameter.
- domain/ must never import from persistence/ or mcp_server/
- Pure functions (builders, summarizers) must not import from persistence/

---

## Integration

### Files modified

| File | Change |
|------|--------|
| `mcp_server/tools.py` | Add `detail` param to `load_recipe`, `load_format`, `get_processing_instructions`; add `filter` param to `validate_entries`; add `filter_rules` param to `get_processing_instructions`; validate param values; dispatch to appropriate summarizer |
| `mcp_server/summarizers.py` | Add `summarize_processing_summary`, `summarize_validation_summary`, `summarize_recipe_summary`, `summarize_format_summary`; modify `summarize_processing_instructions` to accept `detail` and `filter_rules` params |
| `tests/mcp_server/test_summarizers.py` | Tests for new summarizer functions and filtered output |
| `tests/mcp_server/test_tools_filtering.py` | Tests for parameter validation, dispatch logic, backward compatibility |
| `docs/fp_core_skill.md` | Document new parameters in tool reference table |

### Files created (justify each)

| File | Why an existing file can't absorb this |
|------|----------------------------------------|
| `tests/mcp_server/test_tools_filtering.py` | Filtering tests are conceptually distinct from existing builder/summarizer tests and would clutter those files. Could alternatively add to existing test files if preferred. |

### Canonical counts affected

| Constant | Before | After | Delta |
|----------|--------|-------|-------|
| `Total tests` | 413 | ~438 | +~25 |

No changes to NodeLabel, RelationshipType, ontology, constraint, or merge key counts. MCP tool count stays at 6 — existing tools gain new optional parameters but no new tools are created.

**Count-assertion tests:** The total test count in CLAUDE.md updates from 413 to the new total. No new count-assertion tests needed since no canonical enum or schema counts change.

---

## Test Strategy

### New summarizer tests (`tests/mcp_server/test_summarizers.py`)

| Test class / method | What it verifies |
|---------------------|-----------------|
| `TestProcessingSummary::test_summary_returns_counts` | `summarize_processing_summary` returns measure_count, rule_count, has_format |
| `TestProcessingSummary::test_summary_with_format` | has_format is True when format pattern provided |
| `TestProcessingSummary::test_summary_without_format` | has_format is False when no format |
| `TestProcessingInstructions::test_detail_measures_only` | Only `measures` key in response, no `rules` or `output_format` |
| `TestProcessingInstructions::test_detail_rules_only` | Only `rules` key in response |
| `TestProcessingInstructions::test_detail_format_only` | Only `output_format` key in response |
| `TestProcessingInstructions::test_filter_rules_single` | Only matching rule in `rules` array |
| `TestProcessingInstructions::test_filter_rules_multiple` | Multiple matching rules, others excluded |
| `TestProcessingInstructions::test_filter_rules_no_match` | Empty `rules` array when no rules match |
| `TestProcessingInstructions::test_default_detail_unchanged` | `detail=None` produces identical output to current behavior |
| `TestValidationSummary::test_summary_all_pass` | Counts correct when all entries valid |
| `TestValidationSummary::test_summary_with_failures` | Counts correct, errors populated |
| `TestValidationSummary::test_errors_only_filters_passing` | Only failed entries in output |
| `TestRecipeSummary::test_summary_returns_counts` | recipe_id, total_nodes, total_relationships, has_schema, has_output |
| `TestFormatSummary::test_summary_returns_counts` | format_id, column_count, has_validation_rules, has_entry_structure |

### New tool-level tests (`tests/mcp_server/test_tools_filtering.py`)

| Test class / method | What it verifies |
|---------------------|-----------------|
| `TestDetailValidation::test_invalid_detail_returns_error` | Unrecognized detail value returns error JSON |
| `TestDetailValidation::test_valid_detail_values_accepted` | Each valid detail value is dispatched correctly |
| `TestFilterValidation::test_invalid_filter_returns_error` | Unrecognized filter value returns error JSON |
| `TestBackwardCompat::test_no_params_matches_current` | Calling with no new params produces identical output |
| `TestFilterRules::test_comma_separated_parsing` | `filter_rules="a,b"` correctly parsed to `["a", "b"]` |

### Existing tests

All existing tests in `test_summarizers.py`, `test_builders.py`, `test_transport.py`, and `test_auth.py` must continue to pass. Since all new parameters default to `None` and the `None` code path is identical to current behavior, no existing test should break.

### Expected new test count

Current: 413 | Added: ~25 | New total: ~438

---

## Success Criteria

- [ ] `get_processing_instructions(recipe_id, detail="measures_only")` returns only the measures array
- [ ] `get_processing_instructions(recipe_id, detail="summary")` returns counts only (~50 tokens)
- [ ] `get_processing_instructions(recipe_id, filter_rules="rule_a,rule_b")` returns only matching rules
- [ ] `validate_entries(entries, filter="errors_only")` omits passing entries from response
- [ ] `validate_entries(entries, filter="summary")` returns counts only
- [ ] `load_recipe(recipe_id, detail="summary")` returns node/relationship counts only
- [ ] `load_format(format_id, detail="summary")` returns column/rule counts only
- [ ] All new parameters default to `None` with zero behavior change (backward compatible)
- [ ] Invalid parameter values return descriptive error JSON with valid options listed
- [ ] All existing tests pass (no regressions)
- [ ] Canonical counts updated in CLAUDE.md (test count only)

---

## Out of Scope

- **Code execution environment**: This spec designs tools to be code-execution-friendly. It does not build the sandbox/runtime that executes agent-generated code. That is an agent-side concern (e.g., Claude Code's Bash tool, a Jupyter kernel, or a dedicated sandbox).
- **Filesystem-based tool discovery**: With only 6 tools, upfront schema loading costs ~1500 tokens — not enough to justify a filesystem discovery pattern. Revisit if tool count exceeds ~20.
- **PII tokenization**: Important for payroll/HR data but architecturally separate. Tokenization would live in a middleware layer between the MCP client and the execution environment, not in the tool responses themselves. Track as a separate spec (referenced in roadmap as "Privacy-preserving data handling").
- **New tools**: No new tools are added. Existing tools gain optional parameters.
- **Execution engine (Layer 5 compute)**: The `execute_pipeline` function described in `user_flow.md` is a separate feature. This spec makes the existing tools more efficient for agents that implement computation in code.
- **Persistence of agent skills**: The blog's pattern of saving reusable functions to `./skills/` is an agent-side convention. FP_core's MCP prompts (`build-pipeline`, `process-data`) already serve a similar purpose by encoding workflows declaratively.

---

## Open Questions

- [ ] **Should `filter_rules` also filter measures?** Currently it only filters the `rules` array. If a rule references `source_measure: "total_gross"`, should `filter_rules="gross_pay_entry"` also limit measures to only `total_gross`? Pro: smaller response. Con: adds coupling between filtering dimensions. **Recommendation:** Keep measures unfiltered for now — they're small and agents often need the full list. (Decide by: implementation time)
- [ ] **Should `detail` and `filter_rules` be combinable?** e.g., `detail="rules_only", filter_rules="gross_pay_entry"` — return only the matching rule, no measures or format. **Recommendation:** Yes, they should compose. `detail` controls which sections appear; `filter_rules` filters within the rules section. (Decide by: implementation time)