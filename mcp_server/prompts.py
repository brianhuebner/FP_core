# mcp_server/prompts.py — MCP prompt workflow templates
from __future__ import annotations

from mcp_server import mcp


@mcp.prompt(
    name="build-pipeline",
    description="Step-by-step workflow for building and saving a recipe pipeline",
)
def build_pipeline_prompt() -> str:
    return """\
# Build Pipeline Workflow

Follow these steps to build and save a recipe pipeline:

## Step 1: Gather Schema Information
Ask the user about their source data:
- What is the source system? (CSV, API, database export, etc.)
- What columns does the data contain? (name, position, data type, role)
- What file pattern should match input files?
- What is the row grain? (e.g., "employee_pay_period", "invoice_line")

## Step 2: Define Measures
For each amount column that needs aggregation:
- What operation? (sum, count, count_distinct, average)
- Which source column does it aggregate?

## Step 3: Define Mapping Rules
For each journal entry line pair:
- What measure drives this entry?
- What is the debit account? (code, name, type, normal balance)
- What is the credit account? (code, name, type, normal balance)
- What memo template should be used?
- What priority order?

## Step 4: Define Output Format (Optional)
If the user needs a specific export format:
- What is the target system?
- What columns should appear in the output?
- What validation rules apply?
- How should entries be batched?

## Step 5: Build and Save
Assemble the pipeline specification and call `build_and_save_pipeline` with the JSON spec.
Review the Gate 1 validation results:
- If errors: fix the spec and retry
- If warnings only: inform the user and proceed
- If clean: confirm the pipeline is saved and ready

## Step 6: Verify
Call `load_recipe` with the recipe_id to verify the round-trip.
"""


@mcp.prompt(
    name="process-data",
    description="Workflow for processing source data through a recipe",
)
def process_data_prompt(recipe_id: str) -> str:
    return f"""\
# Process Data Workflow

Recipe: `{recipe_id}`

## Step 1: Load Recipe
Call `load_recipe(recipe_id="{recipe_id}")` to load the pipeline graph.
Review the schema, rules, and output format.

## Step 2: Get Processing Instructions
Call `get_processing_instructions(recipe_id="{recipe_id}")` to get:
- Measures: which columns to aggregate and how
- Rules: mapping rules with resolved account codes
- Output format: column layout and validation rules

## Step 3: Read Source Data
Read the source data file matching the schema's file_pattern.
Parse according to the column definitions (positions, data types).

## Step 4: Compute Measures
For each measure, compute the aggregation:
- Apply any group_by or split_by dimensions
- Apply any conditions (WHEN clauses)

## Step 5: Generate Journal Entries
For each mapping rule (in priority order):
- Look up the computed measure value
- Create debit line (account from rule's debit side)
- Create credit line (account from rule's credit side)
- Apply memo template with data values

## Step 6: Validate Entries (Gate 2)
Call `validate_entries` with the generated entries.
Check that:
- Every entry balances (debits == credits)
- All referenced accounts are active

## Step 7: Write Output
Format entries according to the output specification:
- Column order and data types
- Batch grouping and separators
- Journal numbering format
"""


@mcp.prompt(
    name="gate2-checklist",
    description="Validation checklist for journal entries before output",
)
def gate2_checklist_prompt() -> str:
    return """\
# Gate 2 Validation Checklist

Before writing journal entry output, verify all of the following:

## Hard Blocks (Errors — must fix before proceeding)

- [ ] **Balance Check**: Every journal entry must have equal debit and credit totals.
      `SUM(debit_amounts) == SUM(credit_amounts)` per entry.
      Severity: HARD BLOCK — unbalanced entries violate double-entry accounting.

- [ ] **Active Account Check**: All referenced accounts must be active (`is_active=True`).
      Severity: HARD BLOCK — posting to inactive accounts is not allowed.

- [ ] **Required Fields**: Every entry line must have account_code, direction, and amount.
      Severity: HARD BLOCK — incomplete lines cannot be processed.

## Soft Warnings (Informational — review but can proceed)

- [ ] **Memo Templates**: Verify memo templates resolved correctly with data values.
      Severity: WARNING — missing memos are allowed but reduce traceability.

- [ ] **Account Direction**: Check that debit entries go to accounts with
      normal_balance=debit and credit entries to normal_balance=credit.
      Severity: WARNING — contra entries are valid but unusual.

- [ ] **Zero Amounts**: Flag any entry lines with amount=0.
      Severity: WARNING — zero-amount lines are technically valid but likely errors.

## How to Run Gate 2

Call `validate_entries` with your entries JSON:
```json
[
  {
    "lines": [
      {"account_code": "6100", "direction": "debit", "amount": "24500.00"},
      {"account_code": "2100", "direction": "credit", "amount": "24500.00"}
    ]
  }
]
```

Optionally pass `recipe_id` to enable account-level checks against the loaded recipe.
"""
