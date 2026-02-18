# FP_core MCP Skill — Guided Workflow for Accounting Knowledge Graph

## 1. Purpose & When to Use This Skill

You have an FP_core MCP server connected. This skill guides you through interacting with the accounting knowledge graph via MCP tools — loading recipes, building new pipelines, processing data, and producing journal entries.

**Use this skill when:**
- Building a new recipe pipeline from a JSON spec
- Processing source data (CSV) through a recipe pipeline to produce journal entries
- Inspecting a recipe's structure, rules, and output specification
- Answering questions about the accounting domain model

**Don't use this skill when:**
- Writing raw Cypher queries — see `docs/outline_skill.md` (Tier 3)
- Modifying FP_core source code — see `CLAUDE.md`

---

## 2. Available MCP Tools & Resources

### Tier 1 — Core Tools (always available)

| Tool | Parameters | Purpose |
|---|---|---|
| `load_recipe` | `recipe_id: str` | Load a recipe graph from Neo4j, cache it, return a structural summary |
| `load_format` | `format_id: str` | Load an output format from Neo4j, cache it, return a summary |
| `get_processing_instructions` | `recipe_id: str`, `format_id: str` (optional) | Extract measures, mapping rules with resolved accounts, and output spec from cache |
| `build_and_save_pipeline` | `pipeline_spec: str` (JSON) | Build a recipe from a JSON spec, run Gate 1 validation, save to Neo4j |
| `build_output` | `output_spec: str` (JSON) | Build an output format from a JSON spec, validate, save to Neo4j |
| `validate_entries` | `entries: str` (JSON), `recipe_id: str` (optional) | Validate journal entries against double-entry rules (Gate 2) |

**Calling sequence for processing data:** `load_recipe` → `get_processing_instructions` → compute → `validate_entries`

**Calling sequence for building a recipe:** `build_and_save_pipeline` → `load_recipe` → `get_processing_instructions` (verify round-trip)

### Resources

| URI | Purpose |
|---|---|
| `ontology://merged` | Full merged ontology (19 entity schemas with property schemas and relationship constraints) |
| `constraints://merged` | All 25 relationship constraints mapping each RelationshipType to allowed (source, target) pairs |

Resources are read-only reference data. Read `ontology://merged` before building a spec to understand required vs. optional properties for each node type.

---

## 3. User Journey: Build a New Recipe Pipeline

### Step 1: Read the ontology

```
Resource: ontology://merged
```

Read this before writing any spec. It shows required and optional properties for each node type (`SourceSchema`, `Column`, `Measure`, `AccountingRecipe`, `MappingRule`, `AccountSlot`, `Account`, `Condition`, etc.).

### Step 2: Build the spec

Construct a JSON object matching the pipeline spec shape below, then call:

```
Tool: build_and_save_pipeline
Args: pipeline_spec = "<JSON string>"
```

### Pipeline spec shape

```json
{
  "recipe_id": "my_payroll_v1",
  "schema": {
    "name": "payroll_export",
    "source_system": "csv_import",
    "columns": [
      {"name": "gross_pay",   "position": 1, "data_type": "decimal", "role": "amount"},
      {"name": "tax_withheld","position": 2, "data_type": "decimal", "role": "amount"},
      {"name": "net_pay",     "position": 3, "data_type": "decimal", "role": "amount"},
      {"name": "department",  "position": 4, "data_type": "string",  "role": "category"}
    ],
    "measures": [
      {"name": "total_gross",   "operation": "sum", "source_column": "gross_pay"},
      {"name": "total_tax",     "operation": "sum", "source_column": "tax_withheld"},
      {"name": "total_net",     "operation": "sum", "source_column": "net_pay"}
    ]
  },
  "recipe": {
    "name": "Payroll Journal",
    "conditions": [
      {
        "condition_id": "is_engineering",
        "column": "department",
        "operator": "equals",
        "value": "Engineering"
      }
    ],
    "rules": [
      {
        "rule_name": "gross_pay_entry",
        "source_measure": "total_gross",
        "priority": 1,
        "memo_template": "Gross pay accrual",
        "debit":  {"slot_id": "salary_dr",  "role": "expense",   "account_code": "6100", "account_name": "Salary Expense",  "account_type": "expense",   "normal_balance": "debit"},
        "credit": {"slot_id": "payroll_cr", "role": "liability", "account_code": "2200", "account_name": "Payroll Payable", "account_type": "liability", "normal_balance": "credit"}
      },
      {
        "rule_name": "benefits_accrual",
        "source_measure": "total_gross",
        "priority": 2,
        "when": "is_engineering",
        "memo_template": "Benefits accrual - Engineering",
        "debit":  {"slot_id": "benefits_dr", "role": "expense",   "account_code": "6200", "account_name": "Benefits Expense",  "account_type": "expense",   "normal_balance": "debit"},
        "credit": {"slot_id": "benefits_cr", "role": "liability", "account_code": "2300", "account_name": "Benefits Payable", "account_type": "liability", "normal_balance": "credit"}
      }
    ]
  }
}
```

### Field reference

**Top level**
| Field | Required | Notes |
|---|---|---|
| `recipe_id` | Yes | Unique identifier for this pipeline. Used as the primary key in Neo4j. |
| `schema` | Yes | Describes the source data file structure. |
| `recipe` | Yes | Declares the accounting mapping logic. |

**`schema`**
| Field | Required | Notes |
|---|---|---|
| `name` | Yes | Human-readable name for the schema. |
| `source_system` | Yes | Origin system. Common value: `"csv_import"`. |
| `columns[]` | Yes | List of column definitions. |
| `measures[]` | Yes | List of measure (aggregation) definitions. |

**`schema.columns[]`**
| Field | Required | Valid values |
|---|---|---|
| `name` | Yes | Must match column header in source CSV. |
| `position` | Yes | 1-based integer column position. |
| `data_type` | Yes | `"string"`, `"decimal"`, `"date"`, `"integer"`, `"boolean"` |
| `role` | Yes | `"identifier"`, `"amount"`, `"date"`, `"category"`, `"text"` |

**`schema.measures[]`**
| Field | Required | Valid values |
|---|---|---|
| `name` | Yes | Identifier used in `rule.source_measure`. |
| `operation` | Yes | `"sum"`, `"count"`, `"avg"`, `"min"`, `"max"` |
| `source_column` | Yes | Must match a column `name` in `schema.columns`. |
| `group_by` | No | List of column names to group by before aggregating. |

**`recipe`**
| Field | Required | Notes |
|---|---|---|
| `name` | Yes | Human-readable recipe name. |
| `conditions[]` | No | Condition definitions for conditional rules. See below. |
| `rules[]` | Yes | Mapping rules that produce journal entries. |

**`recipe.conditions[]`**
| Field | Required | Valid values |
|---|---|---|
| `condition_id` | Yes | Referenced by `rule.when`. Unique within this recipe. |
| `column` | Yes | Source column name to evaluate. |
| `operator` | Yes | `"equals"`, `"not_equals"`, `"greater_than"`, `"less_than"`, `"is_null"`, `"is_not_null"`, `"always"` |
| `value` | No | Comparison value (string). Omit for `is_null`, `is_not_null`, `always`. |

**`recipe.rules[]`**
| Field | Required | Notes |
|---|---|---|
| `rule_name` | Yes | Unique identifier for this rule within the recipe. |
| `source_measure` | Yes | Must match a measure `name` in `schema.measures`. |
| `priority` | No | Integer. Lower fires first. |
| `memo_template` | No | Memo string for generated journal entries. |
| `when` | No | A `condition_id` from `recipe.conditions`. Rule fires only when condition is true. |
| `debit` | Yes | A single dict (not a list) describing the debit account slot. |
| `credit` | Yes | A single dict (not a list) describing the credit account slot. |

**`rule.debit` / `rule.credit`** — each is a single dict object:
| Field | Required | Valid values |
|---|---|---|
| `slot_id` | Yes | Unique across all rules in the recipe. |
| `role` | Yes | Semantic role, e.g. `"expense"`, `"liability"`, `"asset"`, `"revenue"`. |
| `account_code` | Yes | Must match an account in the chart of accounts. |
| `account_name` | Yes | Display name for the account. |
| `account_type` | Yes | `"asset"`, `"liability"`, `"equity"`, `"expense"`, `"revenue"` |
| `normal_balance` | Yes | `"debit"` or `"credit"` |

### Step 3: Handle Gate 1 validation errors

If the response contains `"gate1_validation": {"is_valid": false}`, read the `errors` list and fix the spec. Common errors:
- Missing required field → add it
- `source_measure` doesn't match any measure name → check spelling
- Duplicate `slot_id` → make each slot_id unique across all rules
- Dangling WHEN target → ensure `rule.when` matches a `condition_id` in `recipe.conditions`

### Step 4: Verify the round-trip

After a successful save:

```
Tool: load_recipe      → recipe_id="my_payroll_v1"
Tool: get_processing_instructions → recipe_id="my_payroll_v1"
```

Confirm the returned measures and rules match what you specified. If a rule has a `when` condition, it should appear as a `"conditions"` list in the rule's processing instructions entry.

---

## 4. User Journey: Process Data Through a Recipe

### Step 1: Load the recipe

```
Tool: load_recipe
Args: recipe_id = "<recipe_id>"
```

**What you get back:** A JSON summary containing:
- `graph_structure` — node and relationship counts
- `schema` — source file structure (name, columns with positions and data types)
- `recipe` — recipe name and rule summaries (name, source_measure, priority, has_condition)
- `output` — output format summary (if attached to recipe)

### Step 2: Get processing instructions

```
Tool: get_processing_instructions
Args: recipe_id = "<recipe_id>"
```

**What you get back:**
- `measures` — what to compute: `name`, `operation`, `column`
- `rules` — mapping rules with resolved accounts:
  - `priority`, `name`, `source_measure`, `memo_template`
  - `debits` — list of `{account_code, account_name}`
  - `credits` — list of `{account_code, account_name}`
  - `conditions` — list of `{condition_id, column, operator, value}` (only present if rule has a WHEN condition)

### Step 3: Read the source data

Read the source CSV. Match columns to the schema from Step 1.

### Step 4: Compute measures

For each measure: apply `operation` to the `column` across all qualifying rows.

If a rule has `conditions`, only include rows where the condition is true when computing that rule's amount. For example, a rule with `WHEN department = "Engineering"` should aggregate only rows where `department == "Engineering"`.

### Step 5: Generate journal entries

For each rule (in priority order):
1. Look up the measure value using `rule.source_measure`
2. If the rule has `conditions`, skip it if the condition was not met
3. Create journal lines for each debit and credit account

### Step 6: Validate (Gate 2)

```
Tool: validate_entries
Args: entries = "<JSON array of entries>", recipe_id = "<recipe_id>"
```

Each entry format:
```json
{"lines": [
  {"account_code": "6100", "direction": "debit",  "amount": 24500.00},
  {"account_code": "2200", "direction": "credit", "amount": 24500.00}
]}
```

Gate 2 checks: debits equal credits per entry, accounts are active.

### Step 7: Format and write output

Structure output according to `output_format.columns` (position order). Group by `batch.grouping_column` if specified.

---

## 5. User Journey: Inspect a Recipe (Read-Only)

```
1. load_recipe(recipe_id="<id>")              → structure, schema, rules, output
2. get_processing_instructions(recipe_id="<id>") → measures, resolved accounts, conditions
3. ontology://merged                           → property schemas for any node type
```

---

## 6. Accounting Semantics (Compact Reference)

### Double-entry invariant

Every journal entry must balance: **total debits = total credits**. Hard block — never produce unbalanced entries.

### Account types and normal balances

| Account Type | Normal Balance | Equation Side |
|---|---|---|
| asset | debit | Left (A = L + E) |
| liability | credit | Right |
| equity | credit | Right |
| revenue | credit | Increases equity |
| expense | debit | Decreases equity |
| contra_revenue | debit | Offsets revenue |
| contra_expense | credit | Offsets expense |

### Gate 1 vs Gate 2

- **Gate 1 (template validation):** Structural correctness of the recipe — slots wired to accounts, measures reference columns, WHEN edges point to existing conditions. Runs automatically inside `build_and_save_pipeline`.
- **Gate 2 (transaction validation):** Actual data being processed — debits equal credits, accounts active. Use `validate_entries` before writing output.

### Naming conventions

Properties use **snake_case** (`account_type`, `normal_balance`, `recipe_id`). Node labels use **PascalCase** (`Account`, `MappingRule`). Relationship types use **UPPER_SNAKE_CASE** (`HAS_RULE`, `MAPPED_TO`, `WHEN`).

---

## 7. Anti-Patterns

**Don't pass `debit`/`credit` as arrays.**
Each rule takes a single `"debit": {...}` and `"credit": {...}` dict. Passing a list causes a build error. The builder will normalize `"debits": [{...}]` (single-item list) automatically, but passing multi-item lists is not supported.

**Don't reuse `slot_id` across rules.**
Every account slot must have a unique `slot_id` within the recipe. Reusing one causes the second rule's slot to overwrite the first in Neo4j.

**Don't put conditions in the schema section.**
`conditions[]` belong in the `recipe` section, not `schema`. The builder migrates `schema.conditions` silently for backward compatibility, but the canonical location is `recipe.conditions`.

**Don't skip Gate 2 before writing output.**
Always validate that debits equal credits before producing the final file. An unbalanced journal entry is an accounting error.

**Don't hardcode account codes.**
Get account codes from the recipe's resolved mapping rules via `get_processing_instructions`. The recipe graph resolves `AccountSlot → MAPPED_TO → Account`.

**Don't skip `load_recipe` and jump to `get_processing_instructions`.**
The server caches the graph on load. `get_processing_instructions` reads from the cache. Calling it without loading first returns an error.

**Don't invent measures or accounts not in the recipe.**
Follow the processing instructions literally.

---

## 8. Tier Selection Guide

```
Start here
    │
    ▼
┌─────────────────────────────────────────────┐
│ Need to build or save a recipe?             │
│                                             │
│ YES → build_and_save_pipeline               │
│ NO  ↓                                       │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│ Need to process data through a recipe?      │
│                                             │
│ YES → load_recipe → get_processing_         │
│       instructions → validate_entries       │
│ NO  ↓                                       │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│ Need to understand the ontology or schema?  │
│                                             │
│ YES → ontology://merged or                  │
│       constraints://merged                  │
│ NO  ↓                                       │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│ Ad-hoc exploration or debugging?            │
│                                             │
│ YES → Use Tier 3: run_cypher                │
│       (see docs/outline_skill.md)           │
└─────────────────────────────────────────────┘
```
