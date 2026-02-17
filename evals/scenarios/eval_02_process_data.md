# Task: Process Payroll Data Through a Recipe

You are an accounting automation agent. A payroll recipe pipeline has already been saved in the knowledge graph. Your task is to load the recipe, process source data through it, generate balanced journal entries, validate them, and write the output CSV.

## Recipe ID

The recipe to use is: `eval_payroll_v1`

## Source Data

Read the file `evals/fixtures/source_data/payroll_5emp_jan.csv` — this contains 5 employees' payroll data for January 2026.

## Instructions

1. Call `load_recipe("eval_payroll_v1")` to get the recipe structure (schema, rules, output format)
2. Call `get_processing_instructions("eval_payroll_v1")` to get the detailed processing instructions (measures with resolved column names, mapping rules with resolved account codes, output format spec)
3. Read the source CSV file
4. Compute the measures as specified in the processing instructions:
   - For each measure, apply the operation (SUM) to the specified source column across all rows
5. Generate journal entries by applying each mapping rule:
   - Each rule produces one journal entry with a debit line and a credit line
   - The amount for each entry comes from the measure named in `source_measure`
   - Use the account codes from the resolved debit/credit accounts
   - Generate journal numbers using the recipe's journal_no_format
6. Call `validate_entries` with your journal entries JSON to run Gate 2 validation. Format entries as:
   ```json
   [
     {
       "lines": [
         {"account_code": "6100", "amount": 24500.00, "direction": "debit"},
         {"account_code": "2100", "amount": 24500.00, "direction": "credit"}
       ]
     }
   ]
   ```
7. Write the output CSV to `evals/results/eval_02_output.csv` with the columns specified in the output format (journal_number, journal_date, account_code, debit_amount, credit_amount, memo)

## Expected Results

- 3 journal entries (gross pay, tax withholding, net pay disbursement)
- 6 journal lines total (one debit + one credit per entry)
- All entries must balance (debit == credit per entry)
- Total debits across all entries == Total credits across all entries

Report the computed measure values, the journal entries generated, and the Gate 2 validation result.
