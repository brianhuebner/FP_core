# Task: Process Payroll Data with Independent Format

You are an accounting automation agent. Your task is to process payroll data through a pre-loaded recipe, build a standalone output format, then generate journal entries using both together.

## IDs

- Recipe ID: `{{RECIPE_ID}}`
- Format ID: `{{FORMAT_ID}}`

## Steps

### 1. Load the Recipe

Call `load_recipe` with recipe_id `{{RECIPE_ID}}` to load the pre-existing payroll recipe from the knowledge graph.

### 2. Build the Output Format

Read `evals/fixtures/knowledge_zone/quickbooks_csv_spec.json` for the target system specification. Then build a QuickBooks CSV output format using `build_output` (NOT embedded in a pipeline). Use format_id `{{FORMAT_ID}}`.

The format should have these 6 columns:
1. journal_number (string, required) — sourced from `journal_no_format`
2. journal_date (date, required) — sourced from `pay_date`
3. account_code (string, required) — sourced from `account.code`
4. debit_amount (decimal, required) — sourced from `line.amount[direction=debit]`, positive sign convention
5. credit_amount (decimal, required) — sourced from `line.amount[direction=credit]`, positive sign convention
6. memo (string, optional) — sourced from `memo_template`

Include a validation rule (`balanced_entry`: `SUM(debit_amount) == SUM(credit_amount)`, scope `batch`).
Include an entry structure (grouping by `journal_number`, separator `blank_row`, date column `journal_date`).

Format metadata: name `quickbooks_journal_csv`, target system `quickbooks`, file format `csv`.

### 3. Get Processing Instructions with Format

Call `get_processing_instructions` with BOTH `recipe_id` = `{{RECIPE_ID}}` AND `format_id` = `{{FORMAT_ID}}`. This combines the recipe's mapping rules with the independently-built format's output specification.

### 4. Process the Data

Read the source data from `evals/fixtures/source_data/payroll_5emp_jan.csv`.

Using the processing instructions:
- Compute the SUM measures: total_gross_pay, total_tax_withheld, total_net_pay
- Apply mapping rules to generate journal entries with the correct account codes
- Format output according to the output column specifications

### 5. Validate Entries

Call `validate_entries` with your journal entries to verify double-entry balance.

### 6. Write Output

Write the final CSV to `evals/results/eval_04_output.csv` with the 6 columns specified in the output format.

Report the final result: the computed totals, whether all entries balanced, and the output file location.
