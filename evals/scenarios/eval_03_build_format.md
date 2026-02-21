# Task: Build a Standalone Output Format

You are an accounting automation agent. Your task is to build a standalone output format definition that describes how journal entries should be exported as a QuickBooks-compatible CSV file. Save it to the knowledge graph using the `build_output` tool.

## Format ID

Use this format_id for all operations: `{{FORMAT_ID}}`

## Reference Files

- **Target system spec:** Read `evals/fixtures/knowledge_zone/quickbooks_csv_spec.json` — this describes the QuickBooks CSV import format you need to model
- **Sample output:** Read `evals/fixtures/source_data/sample_journal_output.csv` — a concrete example of what the format produces

## Output Format Requirements

Build a QuickBooks CSV import format with these 6 columns:

1. **journal_number** (string, required) — Journal entry identifier, sourced from `journal_no_format`
2. **journal_date** (date, required) — Transaction date, sourced from `pay_date`
3. **account_code** (string, required) — Account code, sourced from `account.code`
4. **debit_amount** (decimal, required) — Debit amount with positive sign convention, sourced from `line.amount[direction=debit]`
5. **credit_amount** (decimal, required) — Credit amount with positive sign convention, sourced from `line.amount[direction=credit]`
6. **memo** (string, optional) — Transaction memo, sourced from `memo_template`

### Validation Rule

Include a validation rule named `balanced_entry` that checks:
- Expression: `SUM(debit_amount) == SUM(credit_amount)`
- Scope: `batch`
- Description: Double-entry balance check per journal

### Entry Structure

Include an entry structure that defines how journal lines are grouped:
- Grouping column: `journal_number`
- Entry separator: `blank_row`
- Date column: `journal_date`

### Format Metadata

- Name: `quickbooks_journal_csv`
- Target system: `quickbooks`
- File format: `csv`
- Version: `1.0`

## Instructions

1. First, read the MCP resource `ontology://merged` to understand the required and optional properties for OutputFormat, OutputColumn, ValidationRule, and EntryStructure node types
2. Build a complete output format JSON spec following the ontology requirements
3. Call `build_output` with your spec — do NOT embed this in a pipeline spec
4. If validation fails, fix the specific errors and retry
5. After successful save, call `load_format` with the format_id to verify the round-trip

Report the final result: whether the format was saved successfully, how many nodes and relationships were created, and any warnings.
