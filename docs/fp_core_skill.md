# FP_core MCP Skill — Guided Workflow for Accounting Knowledge Graph

## 1. Purpose & When to Use This Skill

You have an FP_core MCP server connected. This skill guides you through interacting with the accounting knowledge graph via MCP tools — loading recipes, processing data, and producing journal entries.

**Use this skill when:**
- Processing source data (CSV) through a recipe pipeline to produce journal entries
- Inspecting a recipe's structure, rules, and output specification
- Building a new recipe (future — Tier 2 tools)
- Answering questions about the accounting domain model

**Don't use this skill when:**
- Writing raw Cypher queries — see `docs/outline_skill.md` (Tier 3)
- Modifying FP_core source code — see `CLAUDE.md`

---

## 2. Available MCP Tools & Resources

### Tier 1 — Coarse-Grained Read Tools (available now)

| Tool | Parameters | Purpose |
|---|---|---|
| `load_recipe` | `recipe_id: str` | Load a recipe graph from Neo4j, cache it, return a structural summary |
| `get_processing_instructions` | `recipe_id: str` | Extract measures, mapping rules with resolved accounts, and output spec from cache |

**Calling sequence:** Always call `load_recipe` before `get_processing_instructions`. The server caches the graph on load; instructions are derived from the cache.

### Tier 2 — Fine-Grained Write Tools (planned, Phase 2)

These tools will be added in a future phase:
- `build_schema` — define source file structure
- `build_recipe` — create accounting recipe with mapping rules
- `build_output` — define output format specification
- `save_pipeline` — validate and persist a complete pipeline
- `validate_pipeline` — run Gate 1 validation without saving

> Do not attempt to call Tier 2 tools — they are not yet registered.

### Tier 3 — Raw Cypher (planned, Phase 3)

- `run_cypher` — execute ad-hoc Cypher queries against Neo4j
- For Cypher query patterns, see `docs/outline_skill.md`

> Do not attempt to call Tier 3 tools — they are not yet registered.

### Resources

| URI | Purpose |
|---|---|
| `ontology://merged` | Full merged ontology (19 entity schemas with property schemas and relationship constraints) |
| `constraints://merged` | All 25 relationship constraints mapping each RelationshipType to allowed (source, target) pairs |

Resources are read-only reference data. Use them to understand what node types, properties, and relationships exist in the domain model.

---

## 3. User Journey: Process Data Through a Recipe

This is the primary workflow — taking source data and producing accounting journal entries.

### Step 1: Load the recipe

```
Tool: load_recipe
Args: recipe_id = "<recipe_id>"
```

**What you get back:** A JSON summary containing:
- `graph_structure` — node and relationship counts
- `schema` — source file structure (name, file_pattern, row_grain, columns with positions and data types)
- `recipe` — accounting recipe name, journal number format, batch key, and rule summaries (name, source_measure, priority, memo_template)
- `output` — output format name, target system, file format, and column positions

**What to do:** Read the schema section to understand what columns exist in the source data. Note the `row_grain` — it tells you what each row represents (e.g., "one row per employee per pay period").

### Step 2: Get processing instructions

```
Tool: get_processing_instructions
Args: recipe_id = "<recipe_id>"
```

**What you get back:** A JSON with:
- `measures` — what to compute from the source data:
  - `name` — measure identifier (e.g., "total_gross_pay")
  - `operation` — aggregation type (e.g., "SUM", "COUNT")
  - `column` — which source column to aggregate
- `rules` — mapping rules that produce journal entries:
  - `priority` — execution order (lower = first)
  - `name` — rule identifier
  - `source_measure` — which measure this rule uses as its amount
  - `memo_template` — template string for the journal entry memo
  - `debits` — list of `{account_code, account_name}` to debit
  - `credits` — list of `{account_code, account_name}` to credit
- `output_format` — how to structure the output:
  - `columns` — ordered output columns with positions
  - `validation_rules` — rules to check before writing (e.g., debits == credits)
  - `batch` — grouping and separator info (if applicable)

**What to do:** This is the instruction set. You now have everything needed to process the data.

### Step 3: Read the source data

Read the source CSV file. Match the columns to the schema from Step 1. Verify the columns are present and the data types are compatible.

### Step 4: Compute measures

For each measure in the processing instructions:

1. Identify the source column (from `measure.column`)
2. Apply the operation (from `measure.operation`):
   - `SUM` — sum all values in the column
   - `COUNT` — count the rows
3. Store the result keyed by the measure name

**Example:**
If `measures` says `{name: "total_gross_pay", operation: "SUM", column: "gross_pay"}`, then compute the sum of the `gross_pay` column across all rows.

### Step 5: Generate journal entries

For each rule (in priority order):

1. Look up the measure value using `rule.source_measure`
2. For each debit account in `rule.debits`:
   - Create a journal line: direction = DEBIT, amount = measure value, account = `account_code`
3. For each credit account in `rule.credits`:
   - Create a journal line: direction = CREDIT, amount = measure value, account = `account_code`
4. Render the memo using `rule.memo_template` (substitute variables like `{period}`, `{batch_key}`)

### Step 6: Validate (Gate 2 — transaction-level)

Before writing output, check:

1. **Debits must equal credits** — for each journal entry, total debit amounts must equal total credit amounts. This is a hard invariant; do not proceed if unbalanced.
2. **Accounts are active** — all account codes referenced in the rules should be active (`is_active: true`). The recipe's resolved accounts come pre-validated, but if you've modified anything, re-check.
3. **Validation rules from output_format** — apply each rule from `output_format.validation_rules`. Common rules:
   - `sum_debits_equals_sum_credits` — total debits across the batch must equal total credits
   - Scope `batch` means check per batch group; scope `entry` means check per journal entry

### Step 7: Format and write output

Structure the output according to `output_format.columns` (in position order). If `batch` is specified, group entries by the `grouping_column` and separate groups with `entry_separator`.

Write the result as the specified `file_format` (e.g., CSV).

---

## 4. User Journey: Inspect a Recipe (Read-Only)

When you just need to understand what a recipe does without processing data.

### Quick inspection

```
1. load_recipe(recipe_id="<id>")       → see structure, schema, rules, output
2. get_processing_instructions("<id>")  → see computed measures, resolved accounts, validation
```

### Deep inspection

After loading the recipe:
- Read `ontology://merged` to understand the property schemas and allowed relationships for any node type you see in the recipe
- Read `constraints://merged` to see which relationships are valid between which node types
- For Cypher-level exploration, use Tier 3 tools (when available) or see `docs/outline_skill.md`

---

## 5. User Journey: Build a New Recipe (Future — Phase 2)

> This journey requires Tier 2 write tools that are not yet available.

The intended workflow:

1. **Describe source file** — provide column names, types, and row grain → `build_schema`
2. **Describe accounting intent** — what accounts to debit/credit, how to compute amounts → `build_recipe` with mapping rules
3. **Describe output requirements** — target system, file format, columns → `build_output`
4. **Gate 1 validation** — `validate_pipeline` checks the template for structural correctness (all slots have accounts, all measures have columns, relationship constraints satisfied)
5. **Fix errors** — iterate on any Gate 1 failures
6. **Save** — `save_pipeline` persists to Neo4j

This workflow is planned for Phase 2. Until then, recipes must be built via direct Neo4j operations (see `docs/outline_skill.md` for Cypher patterns).

---

## 6. Accounting Semantics (Compact Reference)

### Double-entry invariant

Every journal entry must balance: **total debits = total credits**. This is a hard block — never produce unbalanced entries.

### Account types and normal balances

| Account Type | Normal Balance | Equation Side |
|---|---|---|
| asset | debit | Left (A = L + E) |
| liability | credit | Right (A = L + E) |
| equity | credit | Right (A = L + E) |
| revenue | credit | Increases equity |
| expense | debit | Decreases equity |
| contra_revenue | debit | Offsets revenue |
| contra_expense | credit | Offsets expense |

A debit **increases** accounts with a debit normal balance and **decreases** accounts with a credit normal balance. Vice versa for credits.

### Clearing accounts

Accounts with `semantic_type: clearing` should net to zero over time. If a clearing account has a non-zero balance, it's a warning (not an error) — investigate the cause.

### Reversals, not modifications

Never modify posted transactions. To correct an error, create a reversal (equal and opposite entry) followed by the corrected entry. This preserves the audit trail.

### Gate 1 vs Gate 2

- **Gate 1 (template validation):** Checks the recipe template itself — structural correctness, relationship constraints, all slots wired to accounts. Run before saving a recipe to Neo4j.
- **Gate 2 (transaction validation):** Checks actual data being processed — debits equal credits, accounts are active, validation rules pass. Run before writing output.

For full accounting semantics, see `docs/ontology.md`.

### Naming conventions

Node labels use **PascalCase** (`Account`, `TransactionLine`, `SourceSchema`) and relationship types use **UPPER_SNAKE_CASE** (`BELONGS_TO`, `HAS_RULE`, `MAPPED_TO`) — both per Neo4j recommendations. Property names use **snake_case** (`account_type`, `normal_balance`, `recipe_id`) — a deliberate divergence from Neo4j's `camelCase` recommendation, chosen for consistency with the Python codebase. This applies to all properties across core and recipe ontologies.

---

## 7. Anti-Patterns

**Don't skip Gate 2 before writing output.**
Always validate that debits equal credits and check the output format's validation rules before producing the final file. An unbalanced journal entry is an accounting error.

**Don't hardcode account codes.**
Get account codes from the recipe's resolved mapping rules (via `get_processing_instructions`). The recipe graph already resolves `AccountSlot → MAPPED_TO → Account`. Hardcoding bypasses this and breaks when accounts change.

**Don't dump raw graph data into context.**
Use the summarized tool responses from `load_recipe` and `get_processing_instructions`. These are pre-summarized for efficient consumption. Loading the full `GraphPattern` with all nodes/relationships into the conversation wastes context window.

**Don't use Tier 3 (raw Cypher) when a Tier 1 tool exists.**
If `load_recipe` + `get_processing_instructions` covers your need, use them. They return structured, validated summaries. Drop to Tier 3 only for ad-hoc exploration or debugging that the higher tools don't cover.

**Don't skip `load_recipe` and jump to `get_processing_instructions`.**
The server caches the graph on load. `get_processing_instructions` reads from the cache. Calling it without loading first returns an error.

**Don't invent measures or accounts not in the recipe.**
The recipe defines exactly which columns to aggregate, what operations to use, and which accounts to post to. Follow the instructions literally — don't add extra measures or remap accounts unless the user explicitly asks.

---

## 8. Tier Selection Guide

```
Start here
    │
    ▼
┌─────────────────────────────────────────────┐
│ Can load_recipe + get_processing_instructions│
│ answer the question?                         │
│                                              │
│ YES → Use Tier 1 (covers ~90% of tasks)     │
│ NO  ↓                                        │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│ Do you need to build/modify a recipe         │
│ step by step?                                │
│                                              │
│ YES → Use Tier 2 (when available)            │
│ NO  ↓                                        │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│ Ad-hoc exploration or debugging?             │
│                                              │
│ YES → Use Tier 3: run_cypher                 │
│       (see docs/outline_skill.md for         │
│        Cypher query patterns)                │
│ NO  → Check if the ontology or constraints   │
│       resources answer your question         │
└─────────────────────────────────────────────┘
```

**Rule of thumb:** Start with Tier 1. Drop to a lower tier only when the higher tier doesn't have what you need. Each tier increases flexibility but also increases the risk of malformed queries and the amount of context consumed.
