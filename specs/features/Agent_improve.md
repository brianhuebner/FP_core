# What Would Make FP_core Even Better for Agents

Improvements that reduce human-in-the-loop friction and let agents operate more autonomously against the knowledge graph.

| # | Feature | Priority | Layer Impact |
|---|---------|----------|--------------|
| 1 | `explain_recipe` | High | L3 logic, L5 tool |
| 2 | `list_recipes` | High | L4 query, L5 tool |
| 3 | `compute_measures` | Medium | L3 logic, L5 tool |
| 4 | Structured Gate 1 errors | Medium | L2 ontology, L5 tool |
| 5 | Evaluation suite | Invest eventually | Tests / CI |

---

## 1. `explain_recipe` — Narrative Description Tool

**Priority:** High

Return a plain-English description of what a recipe does before Claude processes data through it. The graph already has all the information — it just needs a summarizer that produces prose rather than structured data.

This enables the "explain before you act" pattern that dramatically increases human trust in agent output.

> *"This recipe processes monthly payroll from a CSV, computes gross pay, tax withheld, and net pay, and posts them to Salary Expense, Tax Payable, and Payroll Payable."*

---

## 2. `list_recipes` — Discoverability

**Priority:** High

Currently Claude must know the `recipe_id` to use a recipe. A tool that returns available recipes — searchable by name, source system, or account type — removes humans from the lookup workflow entirely.

Even a bare `list_recipes()` returning names and IDs would close this gap.

---

## 3. `compute_measures` — Server-Side Aggregation

**Priority:** Medium

Claude handles `SUM` and `COUNT` reliably. For multi-dimensional aggregations with `group_by` columns, decimal precision, and conditional filters across large CSVs, a server-side compute tool is more reliable than in-context arithmetic.

It also completes the privacy model: source data never enters the model's context at any stage of processing.

---

## 4. Structured Error Objects from Gate 1

**Priority:** Medium

Currently Gate 1 returns error strings. Structured errors let Claude self-correct without re-reading the full spec:

```json
{
  "field": "rules[1].source_measure",
  "error": "no_match",
  "value": "total_gross",
  "available": ["gross_total", "tax_withheld"]
}
```

This is a server-side change with no skill file impact. Anthropic's tool research found structured error responses dramatically reduce retry loops.

---

## 5. Evaluation Suite for the Skill

**Priority:** Invest eventually

Build 10 realistic task prompts and run them programmatically against the skill + MCP server with reasoning output captured.

Example tasks:

- *"Process this payroll CSV through recipe X and validate"*
- *"Build a recipe from this spec and verify the round-trip"*
- *"What accounts does recipe Y post to?"*

This tells you where Claude actually gets confused — not where you think it does. It's how you iterate the skill reliably.