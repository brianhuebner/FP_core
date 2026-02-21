# Spec: Server-Side Measure Computation (Draft)

> **Status:** Draft
> **Created:** 2026-02-21
> **Spec type:** Feature

---

## Purpose

Currently, after an agent calls `get_processing_instructions`, it must perform all measure aggregation (sum, count, avg, etc.) client-side — parsing the source data, applying group_by/split_by dimensions, evaluating conditions, and computing results. This is error-prone: the agent must correctly interpret the processing instructions and translate them into aggregation code. A `compute_measures` tool would accept source data and a loaded recipe, run the aggregations server-side using the graph-defined measure definitions, and return the computed results. This eliminates a major source of LLM processing errors.

**This spec is a design exploration document. Implementation is deferred pending resolution of open questions.**

---

## Layer Placement (Projected)

**Primary layer:** L3 (Pure Logic) + L5 (MCP Server)
**Layers touched:**

| Layer | Package | What changes |
|-------|---------|--------------|
| L1 Types | `domain/types_recipe.py` | New `MeasureResult` frozen dataclass |
| L2 Ontology | `domain/ontology_recipe.py` | No changes (MeasureResult is not a graph node) |
| L3 Logic | `domain/logic.py` | New `compute_measures(data, pattern) -> List[MeasureResult]` pure function |
| L4 Persistence | `persistence/` | No changes — computation is pure, no graph writes |
| L5 MCP Server | `mcp_server/tools.py` | New `compute_measures` tool handler |

---

## Domain Types (L1) — Projected

```python
@dataclass(frozen=True)
class MeasureResult:
    """Result of computing a single measure against source data."""
    measure_name: str
    operation: AggregationOp
    value: Decimal
    group_key: Optional[Dict[str, str]] = None  # e.g. {"pay_date": "2026-01-15"}
    split_key: Optional[str] = None              # e.g. "Engineering"
    row_count: int = 0                           # rows contributing to this result
```

**Open:** Should `group_key` be a `Dict[str, str]` or a `Tuple[Tuple[str, str], ...]` (frozen/hashable)? The dataclass is frozen, so mutable dict fields would need to be excluded from hashing or replaced with a frozenset.

---

## Schema Definitions (L2)

No Layer 2 changes required. `MeasureResult` is a computation output, not a graph node — it has no `PropertySchema` or `EntitySchema` entry. It is never persisted to Neo4j.

---

## Pure Functions (L3) — Projected

```python
def compute_measures(
    data: List[Dict[str, Any]],
    pattern: GraphPattern,
) -> List[MeasureResult]:
    """Compute all measures defined in the recipe against source data rows.

    Extracts measures from the pattern, applies conditions, performs
    aggregation (sum/count/avg/min/max), and respects group_by/split_by.

    Args:
        data: List of row dicts (column_name → value)
        pattern: Recipe GraphPattern with measures, conditions, columns

    Returns:
        List of MeasureResult objects, one per measure per group/split key.
    """
```

**Internal decomposition (projected):**
- `_filter_rows(rows, conditions) -> List[Dict]` — apply condition predicates
- `_group_rows(rows, group_by_cols) -> Dict[tuple, List[Dict]]` — partition by group key
- `_aggregate(rows, operation, column) -> Decimal` — apply aggregation operation
- `_split_rows(rows, split_column) -> Dict[str, List[Dict]]` — partition by split dimension

---

## Persistence Contract (L4)

No Layer 4 changes required. Measure computation is a pure function operating on in-memory data and a cached GraphPattern. No Neo4j reads or writes.

---

## MCP Interface (L5) — Projected

### Tool signature (projected)

```python
@mcp.tool()
def compute_measures(recipe_id: str, data: str) -> str:
    """Compute all measures for a loaded recipe against source data.

    Args:
        recipe_id: Previously loaded recipe
        data: JSON string — list of row objects [{"col": "val", ...}, ...]

    Returns:
        JSON with computed measure results, grouped/split as defined.
    """
```

### Projected output

```json
{
  "recipe_id": "payroll_v1",
  "results": [
    {
      "measure_name": "total_gross",
      "operation": "sum",
      "value": "15000.00",
      "row_count": 5,
      "group_key": null,
      "split_key": null
    },
    {
      "measure_name": "dept_gross",
      "operation": "sum",
      "value": "8000.00",
      "row_count": 3,
      "group_key": {"pay_date": "2026-01-15"},
      "split_key": "Engineering"
    }
  ]
}
```

---

## Data Flow (Projected)

```
Agent has source data (CSV parsed to JSON rows)
    |
    v
compute_measures(recipe_id, data_json)
    |
    v
tools.py — look up pattern in _loaded_recipes
    |
    v
logic.py — compute_measures(parsed_rows, pattern)
    |  1. Extract measures from pattern
    |  2. For each measure:
    |     a. Resolve source column via AGGREGATES relationship
    |     b. Apply conditions (if rule has "when" clause)
    |     c. Group rows by group_by columns
    |     d. Split rows by split_by/split_column
    |     e. Compute aggregation (sum/count/avg/min/max)
    |  3. Return List[MeasureResult]
    v
JSON response with computed values
```

---

## Open Questions

These must be resolved before implementation can proceed:

### 1. Data transport format
**Question:** How should source data be passed to the tool?
- **Option A:** JSON string of row dicts (current design) — simple, works for small datasets
- **Option B:** File path to CSV — avoids serializing large datasets into tool parameters
- **Option C:** Row-by-row streaming — complex but handles arbitrary sizes
- **Concern:** MCP tool parameters have practical size limits. A 10,000-row CSV serialized as JSON could be 5-10 MB.
- **Decide by:** Before implementation

### 2. Privacy and data sensitivity
**Question:** Should the MCP server process raw financial data?
- The server currently only stores templates (recipes, formats) — it never sees actual transaction amounts or employee data.
- `compute_measures` would require raw source data to flow through the server.
- **Concern:** This changes the trust model. The MCP server would need to handle PII and financial data.
- **Decide by:** Before implementation

### 3. Decimal precision
**Question:** What precision should aggregation results use?
- `Decimal` is the right type, but what context? `Decimal('0.00')` (2 places) or full precision?
- Accounting systems typically require 2-4 decimal places depending on currency.
- Should precision be configurable per recipe or per measure?
- **Decide by:** Before implementation

### 4. group_by and split_by interaction
**Question:** How do group_by and split_by compose?
- If a measure has `group_by: ["pay_date"]` and `split_by: "department"`, does the output produce one result per (pay_date, department) pair?
- Or is split_by applied after group_by as a second dimension?
- The current spec is ambiguous — `summarize_processing_instructions` emits both fields but doesn't define their interaction.
- **Decide by:** Before implementation

### 5. Condition evaluation
**Question:** How are conditions applied to measures?
- Conditions are defined at the rule level (`MappingRule.when → Condition`), not at the measure level.
- A single measure can be referenced by multiple rules with different conditions.
- Should `compute_measures` compute the measure once (unfiltered) or once per rule (filtered by that rule's condition)?
- **Decide by:** Before implementation

### 6. Function decomposition
**Question:** Should computation live in L3 (`logic.py`) or L5 (new file)?
- **L3 argument:** Pure computation on domain types — fits the logic layer's purpose.
- **L5 argument:** Computation depends on data parsing (CSV/JSON) which is an I/O concern. The pure core could be L3 but the parsing wrapper would be L5.
- **Hybrid approach:** L3 gets `compute_measures(data: List[Dict], pattern: GraphPattern)` (pure), L5 handles JSON parsing and tool wrapping.
- **Decide by:** Before implementation

### 7. CSV parsing responsibility
**Question:** If the tool accepts raw CSV, who parses it?
- Option A: Agent parses CSV to JSON rows before calling the tool (current assumption)
- Option B: Tool accepts CSV string and parses internally (requires CSV schema from the SourceSchema)
- Option C: Separate `parse_source_data` tool that returns structured rows
- **Decide by:** Before implementation

---

## Examples (Projected)

### Happy path: simple sum

```json
// Source data
[
  {"gross_pay": "5000.00", "employee_id": "E001"},
  {"gross_pay": "6000.00", "employee_id": "E002"},
  {"gross_pay": "4000.00", "employee_id": "E003"}
]

// Measure: total_gross = sum(gross_pay)
// Result
{
  "measure_name": "total_gross",
  "operation": "sum",
  "value": "15000.00",
  "row_count": 3
}
```

### Happy path: grouped aggregation

```json
// Source data
[
  {"gross_pay": "5000.00", "pay_date": "2026-01-15"},
  {"gross_pay": "6000.00", "pay_date": "2026-01-15"},
  {"gross_pay": "4000.00", "pay_date": "2026-01-31"}
]

// Measure: total_gross = sum(gross_pay), group_by: ["pay_date"]
// Result (two MeasureResults)
[
  {"measure_name": "total_gross", "value": "11000.00", "group_key": {"pay_date": "2026-01-15"}, "row_count": 2},
  {"measure_name": "total_gross", "value": "4000.00", "group_key": {"pay_date": "2026-01-31"}, "row_count": 1}
]
```

---

## Invariants (Projected)

### Functional constraints
- Computation is pure — `compute_measures(data, pattern)` has no side effects
- Results are deterministic for the same input data and pattern
- Decimal arithmetic — no floating-point rounding errors

### Layer boundaries
- L3 `compute_measures` must not import from persistence/ or mcp_server/
- L5 tool handler wraps L3 pure function with JSON parsing and error handling

---

## Integration (Projected)

### Files modified

| File | Change |
|------|--------|
| `domain/types_recipe.py` | Add `MeasureResult` frozen dataclass |
| `domain/__init__.py` | Export `MeasureResult` in `__all__` |
| `domain/logic.py` | Add `compute_measures` and internal helpers |
| `mcp_server/tools.py` | Add `compute_measures` tool handler |
| `tests/domain/test_logic.py` | Add `TestComputeMeasures` class (~15-20 tests) |
| `tests/mcp_server/test_builders.py` or new file | Add tool-level tests |

### Canonical counts affected (projected)

| Constant | Before | After | Delta |
|----------|--------|-------|-------|
| MCP Tools | 9 | 10 | +1 |
| Total tests | ~422 | ~442 | +~20 |

---

## Test Strategy (Projected)

Tests would cover:
- Simple sum/count/avg/min/max operations
- group_by with single and multiple columns
- split_by producing separate results
- Empty data → zero/empty results
- Decimal precision preserved
- Missing columns in data → clear error
- Condition filtering (once semantics are defined)

---

## Success Criteria (Deferred)

These criteria apply once open questions are resolved and implementation proceeds:

- [ ] `compute_measures` returns correct aggregation results for all 5 operations
- [ ] group_by produces separate results per group key
- [ ] split_by produces separate results per split value
- [ ] Decimal precision is maintained (no float rounding)
- [ ] Empty data returns empty results (not errors)
- [ ] All existing tests pass (no regressions)

---

## Out of Scope

- **Data persistence:** Computed results are not stored in Neo4j — they are transient computation outputs.
- **Incremental computation:** No support for streaming or incremental aggregation.
- **Custom aggregation functions:** Only the 5 standard operations (sum, count, avg, min, max) defined in `AggregationOp`.
- **Multi-recipe computation:** One recipe per call. Cross-recipe aggregation is not supported.

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-02-21 | Draft status — defer implementation | 7 open questions require design decisions before code can be written |
| 2026-02-21 | L3 for pure computation, L5 for tool wrapper | Follows existing layer separation pattern |
| 2026-02-21 | `MeasureResult` as frozen dataclass | Consistent with all other domain types |
