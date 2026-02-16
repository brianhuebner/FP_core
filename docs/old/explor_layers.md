# LedgerSkill Knowledge Graph: Three-Layer Node Taxonomy

This document describes the three-layer architecture of the LedgerSkill knowledge graph, how the Python application interacts with Neo4j, and how the workflow builder agent generates Cypher to populate the graph.

---

## The Three Layers

The knowledge graph is organized into three composable layers. A user selects one of each to form a complete pipeline:

```
[Source Schema] + [Accounting Recipe] + [Output Format] = Prompt Pipeline
```

Each layer is stored as a self-contained subgraph in Neo4j, linked by `recipe_id`. The prompt engine queries all three at runtime and merges them into a single LLM prompt.

---

## Layer 1: Source Schema

**Purpose:** Describes the structure and semantics of an input data file (CSV export from Stripe, bank, etc.)

**Root node:** `SourceSchema`

### Node Types

| Node | Key Properties | Description |
|------|----------------|-------------|
| `SourceSchema` | `recipe_id`, `name`, `source_system`, `file_pattern`, `row_grain` | Root node. Identifies where the data comes from and what each row represents. |
| `Column` | `recipe_id`, `name`, `position`, `data_type`, `role`, `required`, `description` | One per field in the source file. Carries both a primitive type and a semantic role. |
| `Measure` | `recipe_id`, `name`, `operation`, `group_by`, `split_by`, `split_column`, `description` | A declarative aggregation to perform on the source data (e.g. "sum the `fee` column, grouped by payout date"). |
| `Condition` | `recipe_id`, `condition_id`, `column`, `operator`, `value` | A filter attached to a Measure. Multiple Conditions on one Measure are AND logic. |
| `LocationSplit` | `recipe_id`, `code`, `description` | A company-specific location code used to split a Measure into per-location sub-totals. Moves to PostgreSQL in Phase 2. |

### Relationships

```
(SourceSchema)-[:HAS_COLUMN]->(Column)
(SourceSchema)-[:HAS_MEASURE]->(Measure)
(Measure)-[:AGGREGATES]->(Column)          // which column to aggregate
(Measure)-[:WHEN]->(Condition)             // filter before aggregating
(Measure)-[:SPLIT_BY]->(LocationSplit)     // break into sub-groups
```

### Data Types and Semantic Roles

Columns carry two classification dimensions:

**Primitive data types** (stored in `data_type`):

| Type | Usage |
|------|-------|
| `string` | Text, identifiers, categories |
| `decimal` | Currency amounts, rates |
| `integer` | Counts, whole numbers, amounts in cents |
| `timestamp` | Date/time values with time component |
| `date` | Date-only values |

**Semantic roles** (stored in `role`):

| Role | Meaning | Detection Heuristic |
|------|---------|---------------------|
| `identifier` | Unique keys, IDs | Name contains `_id`, `_key`, `_ref` |
| `date` | Temporal values | Name contains `_at`, `_on`, `_date`, `time` |
| `amount` | Currency/monetary values | Decimal type AND represents money |
| `category` | Classification/grouping | Low-cardinality string |
| `description` | Free text, notes | High-cardinality string |

Roles matter more than raw types for prompt generation. An `amount` role tells the LLM "this is money you need to aggregate," while a `category` role signals "group or filter by this."

### Declarative Measures

Measures use a controlled vocabulary instead of embedded expressions:

| Property | Allowed Values |
|----------|----------------|
| `operation` | `sum`, `count`, `count_distinct`, `average` |
| Condition `operator` | `equals`, `not_equals`, `greater_than`, `less_than`, `is_null`, `is_not_null` |
| `transform` (on `[:AGGREGATES]`) | `divide_by_100`, `divide_by_1000`, `absolute_value`, `negate` |

**Example — "Sum of fees, excluding disputes":**

```
(total_fees:Measure {operation: "sum"})
    -[:AGGREGATES]-> (fee:Column {name: "fee"})
    -[:WHEN]-> (exclude_disputes:Condition {column: "reporting_category", operator: "not_equals", value: "dispute"})
```

This replaces an embedded SQL expression like `SUM(CASE WHEN reporting_category != 'dispute' THEN fee END)` with traversable graph relationships.

---

## Layer 2: Accounting Recipe

**Purpose:** Defines the journal entry template — which accounts to debit/credit and under what conditions. Contains a template sub-layer (universal) and a mapping sub-layer (company-specific).

**Root node:** `AccountingRecipe`

### Node Types

| Node | Key Properties | Description |
|------|----------------|-------------|
| `AccountingRecipe` | `recipe_id`, `name`, `source_schema`, `batch_key`, `journal_no_format`, `entries_per_file`, `visibility` | Root node. Defines the journal entry pattern and links to its source schema. |
| `AccountSlot` | `recipe_id`, `slot_id`, `role`, `entry_type`, `description` | **Template layer.** Describes a role in the journal entry (e.g. "bank account", "processing fees") without naming any GL number. Reusable across companies. |
| `Account` | `recipe_id`, `account_id`, `name`, `account_type`, `normal_balance`, `profile_id`, `description` | **Mapping layer.** A company-specific GL account. Linked to an AccountSlot via `[:MAPPED_TO]`. |
| `MappingRule` | `recipe_id`, `rule_name`, `source_measure`, `condition_operator`, `condition_value`, `memo_template`, `priority`, `split_by`, `sign_treatment` | Connects a source Measure to AccountSlots via `[:DEBITS]`/`[:CREDITS]` relationships. |

### Relationships

```
(AccountingRecipe)-[:TRANSFORMS]->(SourceSchema)      // links to Layer 1
(AccountingRecipe)-[:HAS_SLOT]->(AccountSlot)
(AccountingRecipe)-[:HAS_ACCOUNT]->(Account)
(AccountingRecipe)-[:HAS_RULE]->(MappingRule)

(AccountSlot)-[:MAPPED_TO]->(Account)                  // template -> company mapping
(MappingRule)-[:DEBITS]->(AccountSlot)                  // which slot to debit
(MappingRule)-[:CREDITS]->(AccountSlot)                 // which slot to credit
(Account)-[:CHILD_OF]->(Account)                        // account hierarchy
```

### Template vs. Mapping Separation

This is the key multi-tenancy mechanism. The AccountSlot layer is universal:

```cypher
// Universal — every Stripe settlement needs a bank account slot
MERGE (slot:AccountSlot {recipe_id: 'stripe-settlement-v1', slot_id: 'bank_account'})
SET slot.role = 'bank', slot.entry_type = 'debit',
    slot.description = 'The bank account receiving the payout deposit'
```

The Account layer is company-specific:

```cypher
// Alpine's bank account
MERGE (a:Account {recipe_id: 'stripe-settlement-v1', account_id: '1002'})
SET a.name = 'Alpine Bank Corporate', a.account_type = 'Asset'

// Boulder Coffee's bank account
MERGE (b:Account {recipe_id: 'stripe-settlement-v1', account_id: '1010'})
SET b.name = 'Chase Business Checking', b.account_type = 'Asset',
    b.profile_id = 'boulder-coffee'
```

The `[:MAPPED_TO]` relationship bridges the two:

```cypher
(slot:AccountSlot {slot_id: 'bank_account'})-[:MAPPED_TO]->(a:Account {account_id: '1002'})
```

The prompt builder traverses `MappingRule -> AccountSlot -> Account` and can filter by `profile_id` to produce company-specific prompts from the same recipe template.

### MappingRule Conditions

| `condition_operator` | Meaning | Example |
|----------------------|---------|---------|
| `always` | Rule always fires | Net payout to bank |
| `greater_than` | Fire when measure > value | Fees only when > 0 |
| `not_equals` | Fire when measure != value | A/R clearing when gross != 0 |
| `equals` | Fire when measure = value | Special handling for specific categories |

---

## Layer 3: Output Format

**Purpose:** Defines the structure of the exported file that the LLM generates (column layout, formatting, validations).

**Root node:** `OutputFormat`

### Node Types

| Node | Key Properties | Description |
|------|----------------|-------------|
| `OutputFormat` | `recipe_id`, `name`, `target_system`, `file_format`, `version` | Root node. Identifies the target accounting system and file type. |
| `OutputColumn` | `format_id`, `name`, `position`, `data_type`, `required`, `description`, `source_mapping`, `sign_convention`, `format_pattern`, `exclude_from_output` | One per column in the output file. Position defines column order. |
| `FormattingRule` | `format_id`, `name`, `description`, `expression` | Formatting logic for specific columns (sign convention, date format). |
| `ValidationRule` | `format_id`, `name`, `description`, `expression`, `scope` | Constraints the output must satisfy (e.g. balanced journal, required fields). |
| `BatchFormat` | `recipe_id`, `entry_separator`, `grouping_column`, `date_column`, `validation`, `description` | Controls multi-entry output behavior — how rows group into separate journal entries. |

### Relationships

```
(OutputFormat)-[:HAS_COLUMN]->(OutputColumn)
(OutputFormat)-[:HAS_RULE]->(FormattingRule)
(OutputFormat)-[:HAS_VALIDATION]->(ValidationRule)
(OutputFormat)-[:HAS_BATCH_FORMAT]->(BatchFormat)
```

### Sign Convention

The SaaSant format uses a single Amount column where sign encodes debit/credit:

```
positive value = debit
negative value = credit
```

This is stored on the OutputColumn node as `sign_convention: 'positive_debit_negative_credit'`. The prompt builder reads this property and injects a "Sign Convention (Critical)" section into the LLM prompt.

### Validation Rules

Declared in the graph but currently only passed to the LLM as prompt instructions (not enforced deterministically — that is Phase 3):

| Rule | Scope | Expression |
|------|-------|------------|
| `balanced_journal` | `journal_entry` | `SUM(Amount) = 0` |
| `required_account` | `line` | `Account IS NOT NULL` |
| `required_date` | `line` | `Journal Date IS NOT NULL` |

---

## How the Layers Compose

At runtime the prompt builder in `pipeline/build_stripe_prompt.py` makes three queries and merges the results:

```
1. get_source_schema()    → Layer 1 (columns, measures, conditions, location splits)
2. get_accounting_recipe() → Layer 2 (slots, accounts, mapping rules)
3. get_output_format()     → Layer 3 (output columns, formatting, validations, batch rules)
```

The `build_system_prompt()` function then assembles these into a markdown document with six sections:

| Section | Source Layer | Content |
|---------|-------------|---------|
| Source File Structure | Layer 1 | Column table with types and roles |
| Aggregation Measures | Layer 1 | Declarative measure definitions |
| Journal Entry Rules | Layer 2 | DR/CR rules with resolved account names |
| Output Format | Layer 3 | Output column table with sign convention |
| Batch Output Rules | Layer 3 | Journal numbering and grouping logic |
| Validations | Layer 3 | Balance and completeness checks |

The resulting prompt is what the user pastes into an LLM alongside their CSV data.

---

## Neo4j Interaction

### Connection

All Neo4j access goes through `knowledge_graph/connection.py`, which wraps the official `neo4j` Python driver:

```python
from neo4j import GraphDatabase

class Neo4jConnection:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def run_query(self, query, parameters=None):
        """Read query — returns list of dicts."""
        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]

    def run_write(self, query, parameters=None):
        """Write query — returns counters (nodes_created, relationships_created, properties_set)."""
        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            summary = result.consume()
            return {
                "nodes_created": summary.counters.nodes_created,
                "relationships_created": summary.counters.relationships_created,
                "properties_set": summary.counters.properties_set
            }
```

The connection targets a Neo4j Aura instance ("Atomic Ledger") via `neo4j+s://` encrypted connection. Credentials are read from `.env`.

### Loading Cypher into Neo4j

The loader script `knowledge_graph/load_stripe_workflow.py` handles the full lifecycle:

**1. Parse:** Reads a `.cypher` file, strips comments, splits on semicolons into individual statements.

```python
def parse_cypher_file(file_path):
    content = Path(file_path).read_text()
    # Strip // comments, split on ;, clean whitespace
    return [stmt.strip() for stmt in content.split(';') if stmt.strip()]
```

**2. Execute:** Sends each statement to Neo4j individually via `run_write()`. Neo4j requires one statement per query — multi-statement batches will error.

```python
for stmt in statements:
    result = conn.run_write(stmt)
    # Logs: nodes created, relationships created, properties set
```

**3. Verify:** After loading, runs targeted read queries to confirm the graph was populated correctly:

- Does the `SourceSchema` node exist?
- How many `Column` nodes are linked?
- How many `Measure` nodes are linked?
- Does the `AccountingRecipe` node exist?
- Are `AccountSlot` → `Account` mappings present?
- Does the `[:TRANSFORMS]` relationship connect recipe to schema?

**4. Recipe registry:** Known recipes are registered with their file dependencies:

```python
RECIPES = {
    'stripe-settlement-v1': {
        'schema': 'schemas/stripe_payout_reconciliation.cypher',
        'mapping': 'mappings/stripe_settlement.cypher',
        'output': 'outputs/saasant_journal_entry.cypher',
    },
}
```

Load order matters: schema first (mapping depends on it via `[:TRANSFORMS]`), then mapping, then output.

### Idempotency

All Cypher uses `MERGE` instead of `CREATE`. MERGE matches on the specified properties and only creates the node/relationship if it doesn't already exist. This means re-running the loader is safe — it updates properties via `SET` without creating duplicates.

```cypher
MERGE (c:Column {recipe_id: 'stripe-payout-reconciliation-v1', name: 'gross'})
SET c.position = 7, c.data_type = 'decimal', c.role = 'amount', c.required = true
```

The `recipe_id` property on every node is the multi-tenancy key that prevents cross-recipe collisions during MERGE.

---

## How the Workflow Builder Agent Creates Cypher

The workflow builder agent (`agents/workflow_builder/CLAUDE.md`) is a Claude sub-agent that semi-autonomously generates `.cypher` files for new data sources. It operates in two phases with a human checkpoint.

### Phase 1: Discovery (Autonomous)

The agent reads a source data file (CSV) and performs schema inference:

1. **Column detection** — Identifies every column header in the file
2. **Type inference** — Classifies each column as `string`, `decimal`, `integer`, `timestamp`, or `date` based on the values
3. **Role assignment** — Applies heuristics to assign semantic roles:
   - Column name contains `_id`, `_key`, `_ref` → `identifier`
   - Column name contains `_at`, `_on`, `_date`, `time` → `date`
   - Decimal type representing money → `amount`
   - Low-cardinality string → `category`
   - High-cardinality string → `description`
4. **Row grain inference** — Determines what each row represents (e.g. "balance_transaction", "line_item")
5. **Measure proposal** — Based on the user's stated goal, proposes aggregation measures using the controlled vocabulary (`sum`, `count`, etc.) with appropriate filters and transforms
6. **Accounting treatment** — Proposes a DR/CR journal entry pattern based on standard accounting conventions (assets increase with debits, revenue increases with credits, etc.)

### Checkpoint: Human Review

The agent presents its findings in a structured format and pauses:

```
## Schema Discovery Results

**Source:** Itemized_payout_reconciliation_2026.csv
**Row Grain:** balance_transaction
**Proposed Recipe ID:** stripe-payout-reconciliation-v1

### Columns Identified
| # | Column | Type | Role | Notes |
|---|--------|------|------|-------|
| 1 | automatic_payout_id | string | identifier | Payout batch ID |
| 2 | gross | decimal | amount | Gross transaction amount |
...

### Proposed Accounting Treatment
- DR: Bank/Cash (Asset) ← net_payout
- DR: Processing Fees (Expense) ← total_fees
- CR: A/R (Asset) ← gross_by_location

**Does this look correct? Should I adjust anything before generating the Cypher files?**
```

The user confirms or corrects before the agent proceeds.

### Phase 2: Generation (After Approval)

The agent generates two `.cypher` files:

**Schema file** (`knowledge_graph/schemas/{source}_{type}.cypher`):
- `SourceSchema` node with metadata (source system, file pattern, row grain)
- `Column` nodes with position, data type, role, required flag, description
- `[:HAS_COLUMN]` relationships linking columns to schema
- `Measure` nodes with declarative operation and group_by
- `[:AGGREGATES]` relationships linking measures to columns
- `Condition` nodes with column/operator/value
- `[:WHEN]` relationships linking conditions to measures
- `[:HAS_MEASURE]` relationships linking measures to schema

**Mapping file** (`knowledge_graph/mappings/{workflow}.cypher`):
- `AccountingRecipe` node with batch key and journal format
- `AccountSlot` nodes describing each role in the entry (template layer)
- `Account` nodes with GL numbers and account types (mapping layer)
- `[:HAS_SLOT]`, `[:HAS_ACCOUNT]` relationships
- `[:MAPPED_TO]` relationships bridging slots to accounts
- `MappingRule` nodes with source measure, condition, and memo template
- `[:DEBITS]` / `[:CREDITS]` relationships from rules to slots
- `[:TRANSFORMS]` relationship linking recipe to source schema
- `[:HAS_RULE]` relationships linking rules to recipe

Every generated statement uses `MERGE` with `recipe_id` for idempotency. Every statement is semicolon-delimited and independently executable (Neo4j's one-statement-per-query constraint).

### Cypher Generation Constraints

The agent follows these rules when generating Cypher:

| Constraint | Reason |
|------------|--------|
| `MERGE` only, never `CREATE` | Idempotent reloads |
| `recipe_id` on every node | Multi-tenant isolation and MERGE key |
| One statement per semicolon | Neo4j driver limitation |
| No single quotes in property values | Cypher string escaping breaks |
| Declarative measures only | No embedded SQL/code expressions |
| Separate `SET` from `MERGE` pattern | Properties can change; merge keys cannot |
| Comments above each section | Human readability of `.cypher` files |

### After Generation

The agent provides the user with load instructions:

```bash
~/.virtualenvs/neo4j_prompt/bin/python knowledge_graph/load_stripe_workflow.py
```

Or, if the recipe is new and not yet registered in the `RECIPES` dict, the agent provides the `--files` flag:

```bash
~/.virtualenvs/neo4j_prompt/bin/python knowledge_graph/load_stripe_workflow.py \
    --files knowledge_graph/schemas/new_source.cypher \
            knowledge_graph/mappings/new_workflow.cypher
```

The loader parses, executes, and verifies. The `.cypher` files remain version-controlled as the source of truth, with Neo4j as the runtime store.

---

## Summary

The three-layer taxonomy separates concerns cleanly:

- **Layer 1 (Source Schema)** answers: "What data do I have?"
- **Layer 2 (Accounting Recipe)** answers: "What journal entries should I create from it?"
- **Layer 3 (Output Format)** answers: "What file format should the result be in?"

The agent generates Cypher for Layers 1 and 2 from raw CSV files. Layer 3 is typically authored manually since output formats are standardized per target system. All three layers are stored in Neo4j, queried at runtime by Python, and merged into a single LLM prompt that drives the actual data transformation.

---

## Mapping LedgerSkill onto FP_core's Foundation

The two systems use "layer" to mean different things. FP_core layers are **Python abstraction layers** (types → ontology → ...). LedgerSkill layers are **graph subgraph layers** (source → recipe → output). The question is where LedgerSkill's graph concepts land in FP_core's stack.

### What FP_core already provides

| FP_core | What it defines | LedgerSkill concepts it covers |
|---------|----------------|-------------------------------|
| Layer 1 (types.py) | 7 node dataclasses, 9 enums, graph primitives | `Account` (partially), `AccountType`, `BalanceDirection`, `DataSource`/`SourceType`, `AllocationRule`/`RuleType` |
| Layer 2 (ontology.py) | Schema definitions, relationship constraints, validators | `ACCOUNT_TYPE_BALANCE_MAP` already enforces the same DR/CR logic LedgerSkill's MappingRules depend on; `validate_transaction_balance` enforces the same `SUM(Amount) = 0` that LedgerSkill declares as a ValidationRule |

### Where LedgerSkill introduces concepts FP_core doesn't have yet

**1. Source structure modeling (LedgerSkill Layer 1)**

FP_core has `DataSource` — but it's just a connection handle (`source_id`, `source_type`, `connection_config`). LedgerSkill's `SourceSchema` goes deeper: it describes the *shape* of the data (columns with types and semantic roles, declarative measures, conditions). FP_core has no equivalent of:

- `Column` (typed, positioned fields with semantic roles)
- `Measure` (declarative aggregation: operation + group_by + conditions)
- `Condition` (filter predicates on measures)

These are **data source semantics** — not accounting semantics. They describe what the data *looks like*, not what it *means* in accounting terms. FP_core's `DataSource` knows *where* data comes from; LedgerSkill knows *what structure* it has when it arrives.

**2. Template/mapping separation (LedgerSkill Layer 2)**

FP_core has `AllocationRule` but it's a single flat type. LedgerSkill splits this into three concepts:

- `AccountSlot` — a **role** in a journal entry pattern (template layer, reusable across companies)
- `Account` — a **concrete GL account** (mapping layer, company-specific, linked to slot via `[:MAPPED_TO]`)
- `MappingRule` — the **logic** connecting a source measure to slots via `[:DEBITS]`/`[:CREDITS]`

This is the multi-tenancy mechanism. FP_core's `Account` dataclass has the right properties (`code`, `name`, `account_type`, `normal_balance`) but no notion of slots or template reuse. FP_core's `AllocationRule` has `rule_type` but no structure for DR/CR routing.

**3. Output format definition (LedgerSkill Layer 3)**

Now implemented in FP_core. `OutputFormat`, `OutputColumn`, `ValidationRule`, `BatchFormat` are all defined as frozen dataclasses in `types_recipe.py` with corresponding `PropertySchema` and `EntitySchema` entries in `ontology_recipe.py`. `OutputFormat -[:HAS_VALIDATION]-> ValidationRule` and `OutputFormat -[:HAS_BATCH_FORMAT]-> BatchFormat` are constrained relationships. `FormattingRule` was not carried forward — formatting logic is handled via `OutputColumn.format_pattern` and `OutputColumn.sign_convention` properties instead.

### Where the concepts align naturally

Some LedgerSkill concepts map directly onto FP_core's existing types and just need the FP_core foundation to be aware of them:

| LedgerSkill | FP_core equivalent | Gap |
|------------|-------------------|-----|
| `Account.account_type` values (Asset, Liability...) | `AccountType` enum | None — direct match |
| `Account.normal_balance` | `BalanceDirection` enum | None — direct match |
| `SourceSchema.source_system` | `SourceType` enum | None — "stripe" is already a member |
| `AccountingRecipe` | `AllocationRule` (conceptually) | AllocationRule is too flat — needs decomposition |
| `[:CHILD_OF]` on Account | `RelationshipType.CHILD_OF` | Already exists, but only constrained for Entity and AnalyticalDimension, not Account |
| `ValidationRule.balanced_journal` | `validate_transaction_balance()` | Same invariant, FP_core enforces it in Python, LedgerSkill declares it for LLM prompts |
| `Column.role` semantic roles | No equivalent | New enum needed |
| `Measure.operation` | No equivalent | New enum needed |

### Proposed FP_core Layer 3: Graph Operations

Layer 3 would be the bridge between FP_core's pure Python domain model and Neo4j. It answers: **how do FP_core types get stored in, queried from, and validated against a graph database?**

Responsibilities:

1. **Node serialization/deserialization** — Convert between FP_core frozen dataclasses and Neo4j node property maps. FP_core Layer 2 already defines `PropertySchema` with expected types per `NodeLabel` — Layer 3 uses this to serialize/deserialize correctly.

2. **Cypher generation** — Produce valid Cypher statements that conform to FP_core's ontology. Every generated statement must:
   - Use `MERGE` (idempotency)
   - Include `recipe_id` on every node (multi-tenancy)
   - Respect `RELATIONSHIP_CONSTRAINTS` (no invalid edges)
   - Validate via Layer 2 before writing

3. **Graph pattern operations** — FP_core already has `GraphPattern`, `Node`, `Relationship` primitives and `validate_graph_pattern()`. Layer 3 would use these to validate subgraphs before persisting them to Neo4j.

4. **Recipe composition** — The three-layer pipeline query pattern (`get_source_schema` + `get_accounting_recipe` + `get_output_format`) becomes a typed operation that returns FP_core domain objects, not raw dicts.

### What Layer 1/2 need to grow to support this

**New enums needed in types.py:**

- `ColumnDataType` — `string`, `decimal`, `integer`, `timestamp`, `date`
- `SemanticRole` — `identifier`, `date`, `amount`, `category`, `description`
- `AggregationOp` — `sum`, `count`, `count_distinct`, `average`
- `ConditionOp` — `equals`, `not_equals`, `greater_than`, `less_than`, `is_null`, `is_not_null`, `always`
- `TransformOp` — `divide_by_100`, `divide_by_1000`, `absolute_value`, `negate`

**New node types needed in types.py:**

- `SourceSchema` — extends DataSource with structural metadata (columns, measures)
- `Column` — typed field with position and semantic role
- `Measure` — declarative aggregation specification
- `Condition` — predicate filter on a measure
- `AccountSlot` — template role in a journal entry pattern
- `MappingRule` — connects a measure to slots with DR/CR routing
- `OutputFormat` — target system file structure definition
- `OutputColumn` — positioned column in output with formatting rules

**New relationship types needed:**

All implemented. 26 total `RelationshipType` members:
- Core: `BELONGS_TO`, `POSTS_TO`, `ALLOCATED_BY`, `DIMENSIONED_BY`, `OWNS`, `PARENT_OF`, `CHILD_OF`, `CREATED_FROM`, `USES_DIMENSION`, `APPLIED_TO`, `PROVIDES`, `SYNCED_BY`
- Recipe: `HAS_COLUMN`, `HAS_MEASURE`, `AGGREGATES`, `WHEN`, `SPLIT_BY`, `TRANSFORMS`, `HAS_SLOT`, `HAS_RULE`, `MAPPED_TO`, `DEBITS`, `CREDITS`, `HAS_VALIDATION`, `HAS_BATCH_FORMAT`, `USES_REFERENCE`

**New ontology entries — all implemented:**

- `ONTOLOGY` = 7 (core accounting, unchanged)
- `RECIPE_ONTOLOGY` = 12 (9 pipeline types + ValidationRule + BatchFormat + Reference sentinel)
- `merged_ontology()` = 19 (all schemas combined)
- `RELATIONSHIP_CONSTRAINTS` = 11 (core, SYNCED_BY excluded)
- `RECIPE_RELATIONSHIP_CONSTRAINTS` = 14 (all resolved, no TBDs remaining)
- `merged_relationship_constraints()` = 25

Validators implemented: `validate_measure_references_column`, `validate_mapping_rule_completeness`, `validate_recipe_has_schema`, `validate_slot_has_mapping` (soft), `validate_uses_reference`

### The AccountSlot question

The biggest architectural decision: **does FP_core's `Account` type absorb the slot concept, or does `AccountSlot` remain separate?**

Option A — Separate types (matches LedgerSkill):
```
AccountSlot(slot_id, role, entry_type)  ←  template, reusable
Account(code, name, account_type)       ←  concrete, company-specific
AccountSlot -[:MAPPED_TO]-> Account     ←  binding
```

Option B — Account gains a `slot_role` field:
```
Account(code, name, account_type, slot_role=None)
```

Option A preserves the multi-tenancy separation that LedgerSkill needs. Option B is simpler but conflates template and instance. Given the ontology.md principle that "recipes operate on concepts, not implementations," Option A is the right call — the slot *is* the concept, the account *is* the implementation.

### Open questions — status

1. **Where do LocationSplit and BatchFormat live?** RESOLVED. `BatchFormat` is now a node type in `RECIPE_ONTOLOGY` with constraint `OutputFormat -[:HAS_BATCH_FORMAT]-> BatchFormat`. LocationSplit is company-specific reference data — it lives in the knowledge zone as a `Reference` node with `extra_labels={"LocationSplit"}`, connected via `USES_REFERENCE`.

2. **Should OutputFormat be in the ontology at all?** RESOLVED — yes. `OutputFormat`, `OutputColumn`, `ValidationRule`, and `BatchFormat` are all in `RECIPE_ONTOLOGY`. The sign convention (`positive_debit_negative_credit`) is accounting semantics encoded in output structure — it belongs in the domain model.

3. **Validation duality** — OPEN. FP_core validates deterministically in Python. LedgerSkill declares validation rules as graph nodes (`ValidationRule`) that get passed to an LLM as prompt instructions. The `ValidationRule` node type now exists in FP_core, so the graph can store declarative rules. Whether FP_core's I/O layer (Layer 4) should also enforce them deterministically at write-time is a Layer 4 design question.

4. **recipe_id as first-class concept** — RESOLVED. Per the "Revised Understanding" section below: `recipe_id` is a template reference, NOT a multi-tenancy key. It belongs only on recipe/template nodes (`SourceSchema`, `AccountSlot`, `MappingRule`, etc.), not on core accounting nodes.

---

## Revised Understanding: Per-User Graphs and Extensibility

### Each user gets their own Neo4j instance

This changes the `recipe_id` story fundamentally. It is **not** a multi-tenancy isolation key (there's only one tenant per graph). Instead, `recipe_id` is a **template reference** — a way for an accountant to quickly find a pre-built pattern and map their own accounts to it. Think of it like a starter kit: "load the Stripe settlement recipe, swap in my GL numbers, done."

This means:
- `recipe_id` is a property of recipe/template nodes, not a universal key stamped on every node in the graph
- The user's own Account nodes, Entity nodes, Transactions, etc. exist independently of any recipe
- A recipe's AccountSlots get `[:MAPPED_TO]` edges pointing at the user's real accounts — that's the binding
- The user can have nodes in their graph that no recipe references at all

### The graph is the user's entire accounting world

A per-user graph is not just a recipe execution environment. It's the user's **complete accounting knowledge base**. This means the graph will contain:

**Core accounting structures** (FP_core's 7 node types):
- Their chart of accounts
- Their entities and consolidation hierarchy
- Their transactions and journal entries
- Their analytical dimensions (departments, locations, cost centers)

**Recipe infrastructure** (LedgerSkill's pipeline nodes):
- Source schemas describing their data feeds
- Accounting recipes mapping source data to journal patterns
- Output formats for their target systems

**Reference data that supports transformations** — and this is the key extensibility question:

### Reference data subgraphs

An accountant's graph may contain structures that aren't accounting concepts at all, but exist because some transformation needs them. Examples:

| Reference Structure | Why it's in the graph | How it feeds accounting |
|--------------------|-----------------------|----------------------|
| Employee list with current roles | Cost allocation by headcount | `AllocationRule` uses it to split salary expense across departments |
| Timeclock data (hours per role per employee) | Labor cost distribution | Allocate payroll costs proportionally by hours worked per cost center |
| Product catalog with categories | Revenue categorization | Split revenue transactions by product line into different accounts |
| Lease schedule with terms | Accrual calculations | Generate monthly journal entries for prepaid rent amortization |
| Customer tier classifications | Revenue recognition rules | Different recognition patterns per tier |

These are not accounting nodes. They don't have account types or normal balances. But they are **graph-native** — they have their own internal structure (employees have roles, roles have rates, timeclock entries link employees to roles to time periods) and they connect to accounting nodes via relationships.

### Does FP_core's paradigm permit this?

Yes — and as of the current implementation, it does. FP_core has 19 `NodeLabel` values (7 core + 12 recipe/pipeline including `REFERENCE`) and 26 `RelationshipType` values. Reference data nodes use `NodeLabel.REFERENCE` as a sentinel in `Node.labels` and carry their actual type in `Node.extra_labels`. See implementation details above.

Three possible approaches:

**Approach A — Open node labels (graph-native extensibility)**

Don't restrict `NodeLabel` to a fixed enum. Let users define arbitrary node labels. FP_core's ontology validates the *accounting* nodes strictly (accounts must have types, transactions must balance) but treats unrecognized labels as **opaque reference data** — no schema enforcement, no validation, just stored in the graph.

```
NodeLabel enum: keeps the 7 core labels
User-defined labels: "Employee", "Role", "TimeclockEntry", "Product" — no schema in ONTOLOGY
Relationship to accounting: validated only at the accounting boundary
  e.g., AllocationRule -[:USES_REFERENCE]-> (anything)
```

Pros: Maximum flexibility, matches "guide but don't block" philosophy.
Cons: No validation on reference data, could become a mess.

**Approach B — ReferenceData as a meta-type**

Add a single new node type: `ReferenceData`. It's a generic container with a `reference_type` discriminator (like `DimensionType` on `AnalyticalDimension`). All non-accounting data goes through it.

```python
class ReferenceType(Enum):
    EMPLOYEE = "employee"
    ROLE = "role"
    TIMECLOCK = "timeclock"
    PRODUCT = "product"
    CUSTOM = "custom"

@dataclass(frozen=True)
class ReferenceData:
    reference_id: str
    reference_type: ReferenceType
    name: str
    properties: Dict[str, Any]  # schema-free payload
```

Pros: Single extension point, FP_core stays aware of it, can validate the boundary.
Cons: Loses the internal structure of reference data (an employee-role hierarchy becomes flat property bags).

**Approach C — Typed reference schemas (ontology extension)**

Let users register new `EntitySchema` entries in the ontology at runtime. FP_core provides a mechanism to say "here's a new node type called Employee with these required properties and these allowed relationships." The ontology grows per-user.

```python
# User registers at runtime:
ONTOLOGY[NodeLabel("Employee")] = EntitySchema(
    label=NodeLabel("Employee"),
    properties=PropertySchema(
        required=frozenset({"employee_id", "name", "role"}),
        optional=frozenset({"department_id", "hire_date"}),
        types={"employee_id": str, "name": str, "role": str, ...},
    ),
    outgoing_relationships=(...),
    incoming_relationships=(...),
)
```

Pros: Full validation on reference data, graph stays clean.
Cons: More complex, `NodeLabel` can't be a fixed enum, ontology becomes mutable (conflicts with frozen-everything philosophy).

### Implementation — RESOLVED

**Approach A was chosen and implemented**, refined with a sentinel label mechanism.

The original Approach A proposed that `NodeLabel` stay fixed and `Node.labels` be relaxed to accept strings. The actual implementation went further: `NodeLabel.REFERENCE` was added as a sentinel label that reference data nodes carry in `Node.labels`, while their actual type identity (`"Employee"`, `"TimeclockEntry"`) lives in `Node.extra_labels`.

This keeps the constraint system uniform — every constraint entry is still `(NodeLabel, NodeLabel)` pairs — while making the boundary between the accounting zone and the knowledge zone explicit and machine-readable.

What this looks like in practice:

```python
# Reference data node in FP_core
Node(
    id="emp1",
    labels={NodeLabel.REFERENCE},              # sentinel for constraint matching
    extra_labels=frozenset({"Employee"}),       # actual type identity (user's domain)
    properties={"employee_id": "E001", "name": "Jane", "role": "engineer"},
)
```

In Neo4j:
```cypher
(:Reference:Employee {employee_id: "E001", name: "Jane", role: "engineer"})
```

The constraint entry:
```python
RelationshipType.USES_REFERENCE: (
    (NodeLabel.MAPPING_RULE, NodeLabel.REFERENCE),
    (NodeLabel.CONDITION, NodeLabel.REFERENCE),
    (NodeLabel.ACCOUNTING_RECIPE, NodeLabel.REFERENCE),
),
```

Only three recipe-layer node types (`MappingRule`, `Condition`, `AccountingRecipe`) may source `USES_REFERENCE` edges. Core accounting nodes (Account, Transaction, etc.) cannot reach into the knowledge zone directly.

`validate_uses_reference()` enforces the source-side constraint. The target side has an empty `PropertySchema` — no required fields, no type checks, fully opaque.

See `docs/uses_reference_decision.md` for the full boundary architecture documentation.

### Updated recipe_id story

With per-user graphs, `recipe_id` belongs **only on recipe/template nodes** (SourceSchema, AccountSlot, MappingRule, AccountingRecipe, OutputFormat). It does not go on:

- The user's Account nodes (those are their chart of accounts, recipe-independent)
- Transaction/TransactionLine nodes (those are their real journal entries)
- Entity nodes (their company structure)
- Reference data nodes (their operational data)

A recipe is a reusable pattern that *references* the user's accounts via `[:MAPPED_TO]`. The user might have 5 recipes all pointing at the same Bank Account node. The recipe is the template; the user's graph is the territory.