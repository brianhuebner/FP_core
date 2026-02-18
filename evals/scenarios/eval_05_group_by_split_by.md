# Task: Build a Payroll Recipe with Aggregation Properties

You are an accounting automation agent. Your task is to build a recipe pipeline that processes payroll data with department-level aggregation, then save it to the knowledge graph.

## Recipe ID

Use this recipe_id for all operations: `{{RECIPE_ID}}`

## Source Data

Read `evals/fixtures/source_data/payroll_5emp_jan.csv`. This is a monthly payroll export with one row per employee per pay period. Note the `department` column — employees belong to Engineering, Marketing, Sales, and Operations.

## Chart of Accounts

Read `evals/fixtures/knowledge_zone/chart_of_accounts.json` for available account codes. Do not invent account codes.

## Accounting Requirements

Build three journal entries per pay period:

1. **Gross Pay Recognition** — grouped by department
   - Debit: Salary Expense
   - Credit: Payroll Payable

2. **Tax Withholding** — aggregate total (no department grouping)
   - Debit: Payroll Payable
   - Credit: Tax Payable

3. **Net Pay Disbursement** — split by department
   - Debit: Payroll Payable
   - Credit: Cash

## Required Aggregation Properties

This recipe specifically tests measure aggregation properties:

- The **gross_pay** measure **MUST** include `"group_by": ["department"]`. This tells the processor to produce one gross pay journal entry per department rather than a single total.
- The **net_pay** measure **MUST** include `"split_by": "department"` and `"split_column": "department"`. This tells the processor to split the net pay disbursement into one journal line per department value.
- The **tax_withheld** measure uses a plain `sum` with no grouping or splitting.

## Instructions

1. Read the MCP resource `ontology://merged` to understand required and optional properties for each node type
2. Read the source data CSV and chart of accounts
3. Build a complete pipeline JSON spec. Include `group_by` and `split_by`/`split_column` on the appropriate measures as described above
4. Call `build_and_save_pipeline` with your spec
5. If validation fails, fix the specific errors and retry
6. After a successful save, call `load_recipe` with the recipe_id, then call `get_processing_instructions` to verify the aggregation fields appear in the output
7. Report: whether the pipeline was saved successfully, and confirm that `group_by` and `split_by` appear in the processing instructions for the correct measures