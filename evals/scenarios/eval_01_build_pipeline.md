# Task: Build a Payroll Recipe Pipeline

You are an accounting automation agent. Your task is to build a recipe pipeline that transforms payroll CSV data into double-entry journal entries, then save it to the knowledge graph.

## Recipe ID

Use this recipe_id for all operations: `{{RECIPE_ID}}`

## Source Data

Read the file `evals/fixtures/source_data/payroll_5emp_jan.csv` to understand the data schema. This is a monthly payroll export with one row per employee per pay period.

## Chart of Accounts

Read the file `evals/fixtures/knowledge_zone/chart_of_accounts.json` for the available accounts. You must select the correct accounts from this list — do not invent account codes.

## Accounting Requirements

Build journal entries for three transactions per pay period:

1. **Gross Pay Recognition** — Record salary expense
   - Debit: Salary Expense (the expense account)
   - Credit: Payroll Payable (the liability for total compensation owed)

2. **Tax Withholding** — Record employer's obligation to remit taxes
   - Debit: Payroll Payable (reduces the payroll liability)
   - Credit: Tax Payable (liability for taxes to be remitted)

3. **Net Pay Disbursement** — Record the actual payment to employees
   - Debit: Payroll Payable (reduces the payroll liability)
   - Credit: Cash (asset reduction from payment)

Each transaction uses a SUM measure that aggregates the corresponding column across all employee rows.

## Output Format

The output should be a CSV journal entry export suitable for QuickBooks import, with these columns:
1. journal_number (string)
2. journal_date (date)
3. account_code (string)
4. debit_amount (decimal)
5. credit_amount (decimal)
6. memo (string)

Include a validation rule that checks SUM(debit_amount) == SUM(credit_amount) per batch, and a batch format that groups lines by journal_number.

## Instructions

1. First, read the MCP resource `ontology://merged` to understand the required and optional properties for each node type
2. Read the source data CSV to understand column names and data types
3. Read the chart of accounts to identify the correct account codes
4. Build a complete pipeline JSON spec following the ontology requirements
5. Call `build_and_save_pipeline` with your spec
6. If validation fails, fix the specific errors and retry
7. After successful save, call `load_recipe` with the recipe_id to verify the round-trip

Report the final result: whether the pipeline was saved successfully, how many nodes and relationships were created, and any warnings.
