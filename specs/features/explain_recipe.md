# Spec: Narrative Recipe Explanation Tool

> **Status:** Ready
> **Created:** 2026-02-21
> **Spec type:** Feature

---

## Purpose

When an agent loads a recipe via `load_recipe`, the response is a structured JSON summary — useful for programmatic consumption but hard for a human (or an LLM reasoning about data) to read holistically. An `explain_recipe` tool would return a **prose narrative** describing the full pipeline in natural language: what data it expects, how it aggregates, which accounts it maps to, and under what conditions. This gives agents a quick way to verify their understanding of a recipe without parsing nested JSON.

---

## Layer Placement

**Primary layer:** L5 — MCP Server (summarizer + tool)
**Layers touched:**

| Layer | Package | What changes |
|-------|---------|--------------|
| L1 Types | `domain/types.py` / `types_recipe.py` | No changes |
| L2 Ontology | `domain/ontology.py` / `ontology_recipe.py` | No changes |
| L3 Logic | `domain/logic.py` | No changes |
| L4 Persistence | `persistence/` | No changes |
| L5 MCP Server | `mcp_server/summarizers.py`, `mcp_server/tools.py` | New summarizer function + new tool handler |

---

## Domain Types (L1)

No Layer 1 changes required. The tool reads from existing cached `GraphPattern` objects — no new domain types are needed.

---

## Schema Definitions (L2)

No Layer 2 changes required. No new validators or schemas.

**Gate classification:**
- Gate 1: No impact
- Gate 2: No impact

---

## Pure Functions (L3)

No Layer 3 changes required. The new summarizer reuses existing L3 extractors (`extract_measures_for_schema`, `extract_debit_credit_slots`, `extract_conditions_for_rule`).

---

## Persistence Contract (L4)

No Layer 4 changes required.

---

## MCP Interface (L5)

### New summarizer function (`mcp_server/summarizers.py`)

```python
def summarize_recipe_narrative(pattern: GraphPattern, recipe_id: str) -> str:
    """Build a human-readable prose description of a recipe pipeline.

    Traverses: Schema → Columns → Measures → Rules (by priority) →
    AccountSlots → Accounts → Conditions.

    Returns a multi-paragraph string, not JSON.
    """
```

**Traversal order:**
1. **Schema header:** recipe name, schema name, source system
2. **Columns:** enumerate all columns with position, data type, and semantic role
3. **Measures:** for each measure (sorted by name), describe aggregation operation, source column, and group_by/split_by if present
4. **Rules:** for each rule (sorted by priority), describe:
   - The source measure it consumes
   - The debit account (code + name + type)
   - The credit account (code + name + type)
   - The memo template
   - Any conditions (column, operator, value)
5. **Conditions summary:** list all conditions defined on the recipe, noting which rules reference them

**Output style:** Plain text paragraphs with light Markdown formatting (bold for account codes, bullet lists for columns/rules). No JSON wrapping — the tool returns the string directly.

### New tool handler (`mcp_server/tools.py`)

```python
@mcp.tool()
def explain_recipe(recipe_id: str) -> str:
    """Return a narrative description of a previously loaded recipe.

    Produces a human-readable prose summary describing the data schema,
    measures, mapping rules, account assignments, and conditions.
    Call load_recipe first to load the recipe into server-side state.
    """
```

**Behavior:**
1. Look up `recipe_id` in `_loaded_recipes` cache
2. If not found, return error JSON: `{"error": "Recipe 'X' not loaded. Call load_recipe first."}`
3. Call `summarize_recipe_narrative(pattern, recipe_id)`
4. Return the prose string directly (not JSON-wrapped)

### Tool signatures affected

No existing tool signatures change. This adds one new tool.

### JSON spec format

N/A — this tool takes only `recipe_id` (string), no JSON spec input.

### Summarizer output

The output is **prose text**, not JSON. Example:

```
## Recipe: Payroll Journal (payroll_v1)

### Source Schema: payroll_export

**Source system:** csv_import

**Columns (5):**
- gross_pay (position 1, decimal, amount)
- net_pay (position 2, decimal, amount)
- fed_tax (position 3, decimal, amount)
- state_tax (position 4, decimal, amount)
- employee_id (position 5, string, identifier)

### Measures (2)

- **total_gross**: sum of `gross_pay`
- **total_net**: sum of `net_pay`

### Mapping Rules (2)

**Rule 1 — gross_pay_entry** (priority 1):
Takes measure `total_gross` and creates a journal entry:
- Debit: **6100** Salary Expense (expense)
- Credit: **2200** Payroll Payable (liability)
- Memo: "Gross pay"

**Rule 2 — tax_withholding** (priority 2):
Takes measure `total_fed_tax` and creates a journal entry:
- Debit: **2200** Payroll Payable (liability)
- Credit: **2100** Federal Tax Payable (liability)
- Memo: "Federal tax withholding"
- Condition: pay_type equals "regular"
```

---

## Data Flow

```
load_recipe (existing) → cached GraphPattern in _loaded_recipes
    |
    v
explain_recipe(recipe_id)
    |
    v
tools.py — look up pattern in _loaded_recipes
    |
    v
summarizers.py — summarize_recipe_narrative(pattern, recipe_id)
    |  Traverse: Schema → Columns → Measures → Rules → Accounts → Conditions
    |  Build multi-paragraph prose string
    v
Plain text response (returned directly, not JSON-wrapped)
```

---

## Examples

### Happy path: recipe with conditions

```
// Tool call
explain_recipe(recipe_id="payroll_v1")

// Response: plain text (see Summarizer output section above)
```

### Error case: recipe not loaded

```json
// Tool call
explain_recipe(recipe_id="unknown_recipe")

// Response
{"error": "Recipe 'unknown_recipe' not loaded. Call load_recipe first."}
```

### Edge case: recipe with no rules

```
## Recipe: Empty Schema (empty_v1)

### Source Schema: raw_data

**Source system:** csv_import

**Columns (2):**
- amount (position 1, decimal, amount)
- date (position 2, date, date)

### Measures (1)

- **total_amount**: sum of `amount`

### Mapping Rules

No mapping rules defined.
```

### Edge case: measure with group_by and split_by

```
### Measures (1)

- **dept_gross**: sum of `gross_pay`, grouped by [pay_date, department], split by department (column: dept_code)
```

---

## Invariants

### Graph semantics
- Read-only — `explain_recipe` does not modify the graph or cache
- Traversal follows the same relationships as `summarize_processing_instructions` but produces prose instead of JSON

### Functional constraints
- `summarize_recipe_narrative` is a pure function (GraphPattern → str, no I/O)
- Output is deterministic for a given GraphPattern (rules sorted by priority, columns by position, measures by name)

### Layer boundaries
- `summarizers.py` imports only from `domain/` — no persistence imports
- `tools.py` reads from `_loaded_recipes` cache — no new Neo4j queries

---

## Integration

### Files modified

| File | Change |
|------|--------|
| `mcp_server/summarizers.py` | Add `summarize_recipe_narrative(pattern, recipe_id) -> str` function |
| `mcp_server/tools.py` | Add `explain_recipe` tool handler; import `summarize_recipe_narrative` |
| `tests/mcp_server/test_summarizers.py` | Add `TestRecipeNarrative` test class (~10 tests) |

### Files created

None.

### Canonical counts affected

| Constant | Before | After | Delta |
|----------|--------|-------|-------|
| MCP Tools | 7 | 8 | +1 |
| Total tests | ~408 | ~418 | +~10 |

Note: MCP Tools count starts at 7 assuming `patch_recipe` (from `patch_feedback.md`) is implemented first.

---

## Test Strategy

### New tests (`tests/mcp_server/test_summarizers.py`)

| Test class / method | What it verifies |
|---------------------|-----------------|
| `TestRecipeNarrative::test_narrative_includes_recipe_name` | Recipe name appears in header |
| `TestRecipeNarrative::test_narrative_includes_schema_columns` | All columns listed with position, type, role |
| `TestRecipeNarrative::test_narrative_includes_measures` | Each measure listed with operation and source column |
| `TestRecipeNarrative::test_narrative_rules_sorted_by_priority` | Rules appear in priority order |
| `TestRecipeNarrative::test_narrative_includes_debit_credit_accounts` | Account codes and names appear for each rule |
| `TestRecipeNarrative::test_narrative_includes_memo_template` | Memo text appears per rule |
| `TestRecipeNarrative::test_narrative_includes_conditions` | Condition column/operator/value shown for conditional rules |
| `TestRecipeNarrative::test_narrative_no_rules` | "No mapping rules defined" when recipe has no rules |
| `TestRecipeNarrative::test_narrative_measure_with_group_by` | group_by columns mentioned in measure description |
| `TestRecipeNarrative::test_narrative_measure_with_split_by` | split_by/split_column mentioned in measure description |

### Existing tests

All existing summarizer and tool tests must pass unchanged. The new function is additive — it does not modify any existing function.

### Expected new test count

Current: ~408 | Added: ~10 | New total: ~418

---

## Success Criteria

- [ ] `summarize_recipe_narrative` returns a multi-paragraph string (not JSON)
- [ ] Narrative covers schema, columns, measures, rules, accounts, and conditions
- [ ] Rules appear sorted by priority
- [ ] Columns appear sorted by position
- [ ] Measures include group_by/split_by when present
- [ ] Conditions shown per rule where applicable
- [ ] Tool returns error JSON when recipe not loaded
- [ ] All existing tests pass (no regressions)
- [ ] Canonical counts updated in CLAUDE.md

---

## Out of Scope

- **Output format narrative:** The explain tool covers recipe pipelines only. A similar `explain_format` could be added later for output formats.
- **Markdown rendering:** The prose uses light Markdown (bold, bullets, headers) but no HTML or rich formatting. Rendering is the caller's responsibility.
- **Localization:** English only. No i18n infrastructure.
- **Diff mode:** Comparing two recipes or showing what changed after a patch is deferred.

---

## Open Questions

None. The design is fully determined by the existing graph traversal patterns in `summarize_recipe_load` and `summarize_processing_instructions`.
