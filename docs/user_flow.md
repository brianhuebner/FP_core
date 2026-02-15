# User Flow & Layer 5 Planning

This document captures the end-to-end user workflow from raw data to validated journal entry export, maps where each existing layer participates, and identifies what Layer 5 (the execution engine) must provide to close the gaps.

---

## The Two Validation Gates

The system has two distinct validation moments. Confusing them is the primary design risk for Layer 5.

### Gate 1: Template Validation (before writing to Neo4j)

**When:** Before `save_pattern()` persists the recipe graph.

**What it checks:** Is the recipe *structurally sound*? Could it, in theory, produce correct journal entries?

**Validators (Layer 2/3):**

| Validator | Type | Question it answers |
|-----------|------|---------------------|
| `validate_recipe_has_schema` | Hard block | Does the recipe have a TRANSFORMS link to a SourceSchema? |
| `validate_mapping_rule_completeness` | Hard block | Does every MappingRule have both DEBITS and CREDITS edges? |
| `validate_measure_references_column` | Hard block | Does every Measure have an AGGREGATES link to a Column? |
| `validate_slot_has_mapping` | Soft warning | Does every AccountSlot have a MAPPED_TO link to an Account? |
| `validate_uses_reference` | Hard block | Do only allowed node types source USES_REFERENCE edges? |
| `validate_pipeline_connectivity` | Hard block | Does every TRANSFORMS target exist in the pattern? |
| `validate_output_format_has_columns` | Hard block | Does the OutputFormat have at least one OutputColumn? |
| `validate_output_column_positions_unique` | Hard block | Are output column positions unique within each format? |
| `validate_batch_format_references_column` | Soft warning | Do BatchFormat column references match OutputColumn names? |
| `validate_node_properties` | Hard block | Does every node have its required properties with correct types? |

**Analogy:** Validating a blueprint before building the house. A structurally sound blueprint doesn't guarantee the house won't leak — it guarantees the house *can* be built.

### Gate 2: Transaction Validation (when actual data flows through)

**When:** After the execution engine computes measures and generates journal lines, before writing the output file.

**What it checks:** Did the engine *actually produce* correct accounting entries from this specific data?

**Validators (Layer 2, existing but currently uncalled at runtime):**

| Validator | Type | Question it answers |
|-----------|------|---------------------|
| `validate_transaction_balance` | Hard block | Do debits equal credits for each journal entry? |
| `validate_posting_allowed` | Hard block | Is every target account active? |
| `validate_account_balance_direction` | Informational | Does the posting direction match the account's normal balance? |
| `validate_clearing_account_balance` | Soft warning | Do clearing accounts net to zero after this batch? |
| `validate_temporal_ordering` | Soft warning | Is the posting date on or after the transaction date? |

**Analogy:** Inspecting the house after construction. The blueprint was valid, but did the builder follow it correctly?

### Why both gates matter

A recipe can pass Gate 1 perfectly and still produce bad output at Gate 2:
- A MappingRule with `source_measure: "total_fees"` is structurally valid, but if the source data has no fee column, the measure computes to zero and the journal entry is empty
- The recipe wires DR Salary Expense / CR Payroll Payable correctly, but if the data has a sign error, debits won't equal credits
- An Account node has `is_active: True` when the recipe is built, but is deactivated before the batch runs

Gate 1 validates the *template*. Gate 2 validates the *result*. Layer 5 must enforce both.

---

## End-to-End User Flow

### Phase 1: Define the Pipeline (Layers 1-4)

```
User provides:
  - Source file description (what columns, what format)
  - Accounting intent (what journal entries to create)
  - Output requirements (target system, file format)

            │
            ▼

Build graph pattern (Layer 1 types + Layer 3 builders):
  schema_pattern  = build_source_schema_pattern(...)
  recipe_pattern  = build_recipe_pattern(...)
  output_pattern  = build_output_format_pattern(...)
  pipeline        = compose_pipeline_pattern(schema, recipe, output)

            │
            ▼

Validate template ◄── GATE 1
  validate_recipe(pipeline)
  validate_pipeline_connectivity(pipeline)
  validate_output_format(pipeline)
  validate_node_properties(node, merged_ontology())  ← per node

            │  errors? → stop, show errors, user fixes
            ▼

Save to Neo4j (Layer 4):
  save_pattern(conn, pipeline)
```

This phase happens once per recipe. The graph is the durable artifact.

### Phase 2: Process Data (Layer 5 — not yet built)

```
User provides:
  - Actual data file (CSV, API response, etc.)

            │
            ▼

Load recipe from Neo4j (Layer 4):
  pipeline = load_pattern_by_recipe(conn, recipe_id)

            │
            ▼

Extract processing instructions (Layer 3 extractors):
  measures      = extract_measures_for_schema(pipeline, schema_id)
  debit, credit = extract_debit_credit_slots(pipeline, rule_id)
  out_columns   = extract_output_columns(pipeline, format_id)
  val_rules     = extract_validation_rules(pipeline, format_id)
  batch_fmt     = extract_batch_format(pipeline, format_id)

            │
            ▼

Compute measures:
  For each Measure node:
    - Find its AGGREGATES → Column (which source column)
    - Apply the operation (sum, count, etc.)
    - Apply any WHEN → Condition filters
    - Apply any SPLIT_BY grouping

            │
            ▼

Generate journal entries:
  For each MappingRule (ordered by priority):
    - Look up source_measure → computed value
    - Resolve DEBITS → AccountSlot → MAPPED_TO → Account
    - Resolve CREDITS → AccountSlot → MAPPED_TO → Account
    - Create TransactionLine objects (debit + credit)
    - Apply memo_template

            │
            ▼

Validate output ◄── GATE 2
  For each journal entry:
    validate_transaction_balance(lines)      ← hard block
  For each target account:
    validate_posting_allowed(is_active)      ← hard block
    validate_account_balance_direction(...)  ← informational
  For clearing accounts in scope:
    validate_clearing_account_balance(...)   ← soft warning

            │  errors? → stop, show errors, do NOT write file
            ▼

Format output (per OutputFormat spec):
  - Order columns by OutputColumn.position
  - Apply sign_convention, format_pattern
  - Group by BatchFormat.grouping_column
  - Separate entries by BatchFormat.entry_separator

            │
            ▼

Write export file
```

---

## What Layer 5 Must Provide

### Core Execution Engine

The minimum viable Layer 5 is a function with this signature:

```
execute_pipeline(
    pipeline: GraphPattern,       # loaded from Neo4j
    source_data: List[Dict],      # raw input rows
) -> ExecutionResult
```

Where `ExecutionResult` contains:
- `journal_entries`: list of validated journal entries (TransactionLine tuples)
- `validation_result`: merged ValidationResult from Gate 2
- `output_rows`: formatted output rows (per OutputFormat spec)
- `warnings`: soft warnings accumulated during processing
- `measures`: computed measure values (for diagnostics)

### Measure Computation

Layer 5 needs a measure engine that:
1. Reads `Measure.operation` and dispatches to the right aggregation (sum, count, etc.)
2. Follows `AGGREGATES` edges to find the source column name
3. Follows `WHEN` edges to find filter conditions
4. Applies `Condition.operator` / `Condition.value` as predicates
5. Handles `SPLIT_BY` grouping (produces per-group subtotals)

The graph already encodes all of this declaratively. The engine just walks the graph and executes.

### Journal Entry Generation

Layer 5 needs a journal builder that:
1. Iterates MappingRules in priority order
2. Maps `source_measure` (string) → computed measure value
3. Creates `TransactionLine` objects with proper `BalanceDirection`
4. Resolves AccountSlot → Account via `MAPPED_TO` for the account code
5. Evaluates `MappingRule.condition_operator` / `condition_value` to decide if the rule fires
6. Handles `sign_treatment` (negate, absolute value, etc.)

### Output Formatting

Layer 5 needs a formatter that:
1. Reads `OutputColumn` nodes ordered by position
2. Maps each column's `source_mapping` to the right data field
3. Applies `sign_convention` (e.g., positive = debit, negative = credit)
4. Applies `format_pattern` (date formats, decimal precision)
5. Respects `exclude_from_output` flag
6. Groups rows per `BatchFormat.grouping_column`
7. Inserts separators per `BatchFormat.entry_separator`

### ValidationRule Execution

The graph stores `ValidationRule` nodes with declarative expressions like `SUM(debit_amount) == SUM(credit_amount)`. Currently these are metadata — nothing executes them. Layer 5 has two options:

**Option A — Map to existing validators:** Each known expression pattern maps to an existing Layer 2 validator. `SUM(debit_amount) == SUM(credit_amount)` → `validate_transaction_balance()`. The graph serves as a declaration of intent; Python enforces it.

**Option B — Expression evaluator:** Build a small evaluator that can execute the expression strings against the output data. More flexible, but more complex and harder to trust.

**Recommendation:** Option A for the MVP. The Layer 2 validators already exist and are tested. The `ValidationRule` nodes declare *what* should be checked; the engine maps that to *how* it's checked. Option B can come later if users need custom validation expressions.

---

## The Graph Tells You Everything

A key design principle: **the graph is the single source of truth for processing logic.** Layer 5 should read all its instructions from the graph, not from hardcoded logic. This means:

- Column names come from `Column.name`, not from hardcoded strings
- Aggregation operations come from `Measure.operation`, not from if/else chains
- Account codes come from traversing `AccountSlot → MAPPED_TO → Account`, not from a lookup table
- Output column order comes from `OutputColumn.position`, not from a format template
- Validation rules come from `ValidationRule` nodes, not from a separate config

The only things Layer 5 hardcodes are:
- **How** to execute a `sum` operation (the implementation of the aggregation)
- **How** to format a `decimal` value (the implementation of the formatter)
- **How** to enforce `validate_transaction_balance` (already in Layer 2)

Everything else — **what** to aggregate, **which** accounts to post to, **what** columns to output — comes from the graph.

---

## Lessons from the Payroll Demo

The `load_payroll.py` and `run_payroll.py` scripts demonstrated the full flow and revealed several things:

### What worked

1. Layer 3 builders assembled the graph cleanly from raw Node/Relationship objects
2. Gate 1 validation caught structural issues before Neo4j write
3. Layer 4 persistence round-tripped the full graph (33 nodes, 36 relationships)
4. Layer 3 extractors successfully pulled processing instructions back out of the loaded graph
5. The graph-driven processing produced correct, balanced journal entries

### What the demo exposed

1. **Hop query NULL bug** — `load_pattern_by_recipe` failed to load Account nodes because Neo4j's `NOT (NULL = $id)` evaluates to NULL, not TRUE. Fixed with `coalesce`. This is the kind of bug that only surfaces with cross-layer relationships (recipe nodes → core accounting nodes).

2. **No Gate 2 enforcement** — The demo computed correct results, but nothing *prevented* writing incorrect results. The balance check was a print statement, not a validator call. A sign error in the data would have produced an unbalanced CSV with no warning.

3. **No TransactionLine creation** — The demo went straight from measure values to output rows, skipping the intermediate `TransactionLine` objects that Layer 2's `validate_transaction_balance` expects. Layer 5 must create proper `TransactionLine` tuples as an intermediate step.

4. **validate_graph_pattern scope** — `validate_graph_pattern()` uses `RELATIONSHIP_CONSTRAINTS` (core only), so it rejects recipe-layer relationships as "unknown." For mixed patterns, node property validation works (pass `merged_ontology()`), but relationship validation needs the merged constraints. This is a Layer 2 gap worth addressing.

5. **format_id convention** — `load_pattern_by_recipe` and `verify_pattern` find nodes by `recipe_id` or `format_id`. For OutputColumn and ValidationRule nodes (keyed by `format_id`), the `format_id` must equal `recipe_id` for these operations to find them. This works but is an implicit convention that should be documented or enforced.

---

## Layer 5 Implementation Phases

### Phase 1: Measure Engine + Gate 2

- Measure computation from graph instructions
- `TransactionLine` creation from mapping rules
- Gate 2 validation using existing Layer 2 validators
- Hard block on unbalanced entries before file write

### Phase 2: Condition Evaluation + Rule Filtering

- `MappingRule.condition_operator` / `condition_value` evaluation
- Rules that only fire when conditions are met
- `WHEN` → `Condition` filtering on measures
- `SPLIT_BY` grouping support

### Phase 3: Output Formatting

- Full `OutputColumn` spec compliance (sign_convention, format_pattern, exclude_from_output)
- `BatchFormat` grouping and separation
- File writing per `OutputFormat.file_format` (CSV initially, extensible)

### Phase 4: ValidationRule Execution

- Map declarative `ValidationRule.expression` to Layer 2 validators
- Report validation results per scope (line, batch, file)
- Optional: expression evaluator for custom rules
