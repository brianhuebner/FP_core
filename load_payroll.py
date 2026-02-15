
"""Load a payroll recipe pipeline into Neo4j.

Demonstrates the full Layer 1→4 workflow:
  1. Build Node/Relationship objects (Layer 1 types)
  2. Assemble GraphPatterns using Layer 3 logic functions
  3. Validate with Layer 2/3 validators
  4. Save to Neo4j via Layer 4 persistence

Scenario: Monthly payroll CSV → journal entries
  Source:  payroll export (employee_id, pay_date, gross_pay, tax_withheld, net_pay, department)
  Rules:   gross → DR Salary Expense / CR Payroll Payable
           tax  → DR Payroll Payable / CR Tax Payable
           net  → DR Payroll Payable / CR Cash
  Output:  journal entry CSV for QuickBooks import
"""

import sys

from domain import (
    Node,
    NodeLabel,
    Relationship,
    RelationshipType,
    build_output_format_pattern,
    build_recipe_pattern,
    build_source_schema_pattern,
    compose_pipeline_pattern,
    validate_output_format,
    validate_pipeline_connectivity,
    validate_recipe,
)
from domain.ontology import ValidationResult, validate_node_properties
from domain.ontology_recipe import merged_ontology
from persistence import Neo4jConnection, save_pattern, verify_pattern

RECIPE_ID = "payroll_monthly_v1"


# =============================================================================
# STAGE 1: Source Schema — What the payroll CSV looks like
# =============================================================================

schema = Node(
    id="schema_payroll",
    labels={NodeLabel.SOURCE_SCHEMA},
    properties={
        "recipe_id": RECIPE_ID,
        "name": "payroll_export",
        "source_system": "csv_import",
        "file_pattern": "payroll_*.csv",
        "row_grain": "employee_pay_period",
    },
)

columns = [
    Node(id="col_emp_id", labels={NodeLabel.COLUMN}, properties={
        "recipe_id": RECIPE_ID, "name": "employee_id", "position": 1,
        "data_type": "string", "role": "identifier", "required": True,
    }),
    Node(id="col_pay_date", labels={NodeLabel.COLUMN}, properties={
        "recipe_id": RECIPE_ID, "name": "pay_date", "position": 2,
        "data_type": "date", "role": "date", "required": True,
    }),
    Node(id="col_gross", labels={NodeLabel.COLUMN}, properties={
        "recipe_id": RECIPE_ID, "name": "gross_pay", "position": 3,
        "data_type": "decimal", "role": "amount", "required": True,
    }),
    Node(id="col_tax", labels={NodeLabel.COLUMN}, properties={
        "recipe_id": RECIPE_ID, "name": "tax_withheld", "position": 4,
        "data_type": "decimal", "role": "amount", "required": True,
    }),
    Node(id="col_net", labels={NodeLabel.COLUMN}, properties={
        "recipe_id": RECIPE_ID, "name": "net_pay", "position": 5,
        "data_type": "decimal", "role": "amount", "required": True,
    }),
    Node(id="col_dept", labels={NodeLabel.COLUMN}, properties={
        "recipe_id": RECIPE_ID, "name": "department", "position": 6,
        "data_type": "string", "role": "category", "required": False,
    }),
]

measures = [
    Node(id="msr_total_gross", labels={NodeLabel.MEASURE}, properties={
        "recipe_id": RECIPE_ID, "name": "total_gross_pay",
        "operation": "sum", "description": "Sum of gross pay across all employees",
    }),
    Node(id="msr_total_tax", labels={NodeLabel.MEASURE}, properties={
        "recipe_id": RECIPE_ID, "name": "total_tax_withheld",
        "operation": "sum", "description": "Sum of tax withheld",
    }),
    Node(id="msr_total_net", labels={NodeLabel.MEASURE}, properties={
        "recipe_id": RECIPE_ID, "name": "total_net_pay",
        "operation": "sum", "description": "Sum of net pay",
    }),
]

col_rels = [
    Relationship(
        id=f"rel_has_col_{c.id}", type=RelationshipType.HAS_COLUMN,
        start_node_id="schema_payroll", end_node_id=c.id, properties={},
    )
    for c in columns
]

msr_rels = [
    Relationship(
        id=f"rel_has_msr_{m.id}", type=RelationshipType.HAS_MEASURE,
        start_node_id="schema_payroll", end_node_id=m.id, properties={},
    )
    for m in measures
]

agg_rels = [
    Relationship(id="rel_agg_gross", type=RelationshipType.AGGREGATES,
                 start_node_id="msr_total_gross", end_node_id="col_gross", properties={}),
    Relationship(id="rel_agg_tax", type=RelationshipType.AGGREGATES,
                 start_node_id="msr_total_tax", end_node_id="col_tax", properties={}),
    Relationship(id="rel_agg_net", type=RelationshipType.AGGREGATES,
                 start_node_id="msr_total_net", end_node_id="col_net", properties={}),
]

schema_pattern = build_source_schema_pattern(
    schema_node=schema,
    column_nodes=columns,
    measure_nodes=measures,
    condition_nodes=[],
    column_rels=col_rels,
    measure_rels=msr_rels,
    aggregates_rels=agg_rels,
)


# =============================================================================
# STAGE 2: Accounting Recipe — How payroll data becomes journal entries
# =============================================================================

recipe = Node(
    id="recipe_payroll",
    labels={NodeLabel.ACCOUNTING_RECIPE},
    properties={
        "recipe_id": RECIPE_ID,
        "name": "Monthly Payroll Journal",
        "source_schema": "payroll_export",
        "batch_key": "pay_date",
        "journal_no_format": "PY-{date:%Y%m}-{seq:04d}",
        "visibility": "private",
    },
)

transforms_rel = Relationship(
    id="rel_transforms", type=RelationshipType.TRANSFORMS,
    start_node_id="recipe_payroll", end_node_id="schema_payroll", properties={},
)

# --- 3 Mapping Rules (one per journal entry line pair) ---

rule_gross = Node(id="rule_gross", labels={NodeLabel.MAPPING_RULE}, properties={
    "recipe_id": RECIPE_ID, "rule_name": "gross_pay_entry",
    "source_measure": "total_gross_pay",
    "memo_template": "Salary expense - {pay_date:%B %Y}",
    "priority": 1,
})

rule_tax = Node(id="rule_tax", labels={NodeLabel.MAPPING_RULE}, properties={
    "recipe_id": RECIPE_ID, "rule_name": "tax_withholding_entry",
    "source_measure": "total_tax_withheld",
    "memo_template": "Tax withholding - {pay_date:%B %Y}",
    "priority": 2,
})

rule_net = Node(id="rule_net", labels={NodeLabel.MAPPING_RULE}, properties={
    "recipe_id": RECIPE_ID, "rule_name": "net_pay_entry",
    "source_measure": "total_net_pay",
    "memo_template": "Net pay disbursement - {pay_date:%B %Y}",
    "priority": 3,
})

rules = [rule_gross, rule_tax, rule_net]

# --- 6 Account Slots (debit + credit per rule) ---

slot_salary_dr = Node(id="slot_salary_dr", labels={NodeLabel.ACCOUNT_SLOT}, properties={
    "recipe_id": RECIPE_ID, "slot_id": "salary_expense_debit",
    "role": "primary", "entry_type": "debit",
    "description": "Salary expense recognition",
})
slot_payroll_cr_gross = Node(id="slot_payroll_cr_gross", labels={NodeLabel.ACCOUNT_SLOT}, properties={
    "recipe_id": RECIPE_ID, "slot_id": "payroll_payable_credit_gross",
    "role": "offset", "entry_type": "credit",
    "description": "Payroll payable (gross accrual)",
})
slot_payroll_dr_tax = Node(id="slot_payroll_dr_tax", labels={NodeLabel.ACCOUNT_SLOT}, properties={
    "recipe_id": RECIPE_ID, "slot_id": "payroll_payable_debit_tax",
    "role": "primary", "entry_type": "debit",
    "description": "Payroll payable (tax reduction)",
})
slot_tax_cr = Node(id="slot_tax_cr", labels={NodeLabel.ACCOUNT_SLOT}, properties={
    "recipe_id": RECIPE_ID, "slot_id": "tax_payable_credit",
    "role": "offset", "entry_type": "credit",
    "description": "Tax payable accrual",
})
slot_payroll_dr_net = Node(id="slot_payroll_dr_net", labels={NodeLabel.ACCOUNT_SLOT}, properties={
    "recipe_id": RECIPE_ID, "slot_id": "payroll_payable_debit_net",
    "role": "primary", "entry_type": "debit",
    "description": "Payroll payable (net pay reduction)",
})
slot_cash_cr = Node(id="slot_cash_cr", labels={NodeLabel.ACCOUNT_SLOT}, properties={
    "recipe_id": RECIPE_ID, "slot_id": "cash_credit",
    "role": "offset", "entry_type": "credit",
    "description": "Cash disbursement",
})

slots = [
    slot_salary_dr, slot_payroll_cr_gross,
    slot_payroll_dr_tax, slot_tax_cr,
    slot_payroll_dr_net, slot_cash_cr,
]

# --- 4 Core Account nodes (chart of accounts) ---

acct_salary = Node(id="acct_6100", labels={NodeLabel.ACCOUNT}, properties={
    "code": "6100", "name": "Salary Expense",
    "account_type": "expense", "normal_balance": "debit", "is_active": True,
})
acct_payroll = Node(id="acct_2100", labels={NodeLabel.ACCOUNT}, properties={
    "code": "2100", "name": "Payroll Payable",
    "account_type": "liability", "normal_balance": "credit", "is_active": True,
})
acct_tax = Node(id="acct_2200", labels={NodeLabel.ACCOUNT}, properties={
    "code": "2200", "name": "Tax Payable",
    "account_type": "liability", "normal_balance": "credit", "is_active": True,
})
acct_cash = Node(id="acct_1010", labels={NodeLabel.ACCOUNT}, properties={
    "code": "1010", "name": "Cash",
    "account_type": "asset", "normal_balance": "debit", "is_active": True,
})

accounts = [acct_salary, acct_payroll, acct_tax, acct_cash]

# --- Recipe relationships ---

# HAS_RULE: recipe → each mapping rule
# DEBITS/CREDITS: each rule → its debit/credit slot
rule_rels = [
    # recipe → rules
    Relationship(id="rel_has_rule_gross", type=RelationshipType.HAS_RULE,
                 start_node_id="recipe_payroll", end_node_id="rule_gross", properties={}),
    Relationship(id="rel_has_rule_tax", type=RelationshipType.HAS_RULE,
                 start_node_id="recipe_payroll", end_node_id="rule_tax", properties={}),
    Relationship(id="rel_has_rule_net", type=RelationshipType.HAS_RULE,
                 start_node_id="recipe_payroll", end_node_id="rule_net", properties={}),
    # gross rule: DR Salary Expense / CR Payroll Payable
    Relationship(id="rel_dr_gross", type=RelationshipType.DEBITS,
                 start_node_id="rule_gross", end_node_id="slot_salary_dr", properties={}),
    Relationship(id="rel_cr_gross", type=RelationshipType.CREDITS,
                 start_node_id="rule_gross", end_node_id="slot_payroll_cr_gross", properties={}),
    # tax rule: DR Payroll Payable / CR Tax Payable
    Relationship(id="rel_dr_tax", type=RelationshipType.DEBITS,
                 start_node_id="rule_tax", end_node_id="slot_payroll_dr_tax", properties={}),
    Relationship(id="rel_cr_tax", type=RelationshipType.CREDITS,
                 start_node_id="rule_tax", end_node_id="slot_tax_cr", properties={}),
    # net rule: DR Payroll Payable / CR Cash
    Relationship(id="rel_dr_net", type=RelationshipType.DEBITS,
                 start_node_id="rule_net", end_node_id="slot_payroll_dr_net", properties={}),
    Relationship(id="rel_cr_net", type=RelationshipType.CREDITS,
                 start_node_id="rule_net", end_node_id="slot_cash_cr", properties={}),
]

# MAPPED_TO: each slot → its target account
slot_rels = [
    Relationship(id="rel_map_salary", type=RelationshipType.MAPPED_TO,
                 start_node_id="slot_salary_dr", end_node_id="acct_6100", properties={}),
    Relationship(id="rel_map_payroll_cr", type=RelationshipType.MAPPED_TO,
                 start_node_id="slot_payroll_cr_gross", end_node_id="acct_2100", properties={}),
    Relationship(id="rel_map_payroll_dr_tax", type=RelationshipType.MAPPED_TO,
                 start_node_id="slot_payroll_dr_tax", end_node_id="acct_2100", properties={}),
    Relationship(id="rel_map_tax", type=RelationshipType.MAPPED_TO,
                 start_node_id="slot_tax_cr", end_node_id="acct_2200", properties={}),
    Relationship(id="rel_map_payroll_dr_net", type=RelationshipType.MAPPED_TO,
                 start_node_id="slot_payroll_dr_net", end_node_id="acct_2100", properties={}),
    Relationship(id="rel_map_cash", type=RelationshipType.MAPPED_TO,
                 start_node_id="slot_cash_cr", end_node_id="acct_1010", properties={}),
]

recipe_pattern = build_recipe_pattern(
    recipe_node=recipe,
    schema_node=schema,
    transforms_rel=transforms_rel,
    rule_nodes=rules,
    rule_rels=rule_rels,
    slot_nodes=slots,
    slot_rels=slot_rels,
    additional_nodes=accounts,
)


# =============================================================================
# STAGE 3: Output Format — What the journal entry export looks like
# =============================================================================

output_fmt = Node(
    id="fmt_journal",
    labels={NodeLabel.OUTPUT_FORMAT},
    properties={
        "recipe_id": RECIPE_ID,
        "name": "journal_entry_export",
        "target_system": "quickbooks",
        "file_format": "csv",
        "version": "1.0",
    },
)

# format_id must equal recipe_id so load_pattern_by_recipe / verify_pattern can find them
FORMAT_ID = RECIPE_ID

out_columns = [
    Node(id="ocol_journal_no", labels={NodeLabel.OUTPUT_COLUMN}, properties={
        "format_id": FORMAT_ID, "name": "journal_number", "position": 1,
        "data_type": "string", "required": True, "source_mapping": "journal_no_format",
    }),
    Node(id="ocol_date", labels={NodeLabel.OUTPUT_COLUMN}, properties={
        "format_id": FORMAT_ID, "name": "journal_date", "position": 2,
        "data_type": "date", "required": True, "source_mapping": "pay_date",
    }),
    Node(id="ocol_account", labels={NodeLabel.OUTPUT_COLUMN}, properties={
        "format_id": FORMAT_ID, "name": "account_code", "position": 3,
        "data_type": "string", "required": True, "source_mapping": "account.code",
    }),
    Node(id="ocol_debit", labels={NodeLabel.OUTPUT_COLUMN}, properties={
        "format_id": FORMAT_ID, "name": "debit_amount", "position": 4,
        "data_type": "decimal", "required": True,
        "source_mapping": "line.amount[direction=debit]",
        "sign_convention": "positive",
    }),
    Node(id="ocol_credit", labels={NodeLabel.OUTPUT_COLUMN}, properties={
        "format_id": FORMAT_ID, "name": "credit_amount", "position": 5,
        "data_type": "decimal", "required": True,
        "source_mapping": "line.amount[direction=credit]",
        "sign_convention": "positive",
    }),
    Node(id="ocol_memo", labels={NodeLabel.OUTPUT_COLUMN}, properties={
        "format_id": FORMAT_ID, "name": "memo", "position": 6,
        "data_type": "string", "required": False, "source_mapping": "memo_template",
    }),
]

out_col_rels = [
    Relationship(
        id=f"rel_fmt_col_{c.id}", type=RelationshipType.HAS_COLUMN,
        start_node_id="fmt_journal", end_node_id=c.id, properties={},
    )
    for c in out_columns
]

val_rule = Node(id="val_balance", labels={NodeLabel.VALIDATION_RULE}, properties={
    "format_id": FORMAT_ID, "name": "balanced_entry",
    "expression": "SUM(debit_amount) == SUM(credit_amount)",
    "scope": "batch",
    "description": "Double-entry balance check per journal",
})

val_rels = [
    Relationship(id="rel_has_val", type=RelationshipType.HAS_VALIDATION,
                 start_node_id="fmt_journal", end_node_id="val_balance", properties={}),
]

batch = Node(id="batch_payroll", labels={NodeLabel.BATCH_FORMAT}, properties={
    "recipe_id": RECIPE_ID, "entry_separator": "blank_row",
    "grouping_column": "journal_number", "date_column": "journal_date",
    "description": "Group lines by journal number with blank row separators",
})

batch_rel = Relationship(
    id="rel_has_batch", type=RelationshipType.HAS_BATCH_FORMAT,
    start_node_id="fmt_journal", end_node_id="batch_payroll", properties={},
)

output_pattern = build_output_format_pattern(
    format_node=output_fmt,
    column_nodes=out_columns,
    column_rels=out_col_rels,
    validation_nodes=[val_rule],
    validation_rels=val_rels,
    batch_node=batch,
    batch_rel=batch_rel,
)


# =============================================================================
# STAGE 4: Compose, Validate, Save
# =============================================================================

pipeline = compose_pipeline_pattern(schema_pattern, recipe_pattern, output_pattern)

print(f"Pipeline: {len(pipeline.nodes)} nodes, {len(pipeline.relationships)} relationships\n")

# Run all validators
recipe_result = validate_recipe(pipeline)
conn_result = validate_pipeline_connectivity(pipeline)
output_result = validate_output_format(pipeline)

# Node property validation against merged ontology (core + recipe schemas)
ontology = merged_ontology()
node_results = [validate_node_properties(n, ontology) for n in pipeline.nodes]
props_result = ValidationResult.merge(*node_results)

print("--- Validation ---")
all_valid = True
for name, result in [
    ("Recipe structure", recipe_result),
    ("Pipeline connectivity", conn_result),
    ("Output format", output_result),
    ("Node properties", props_result),
]:
    status = "PASS" if result.is_valid else "FAIL"
    print(f"  {name}: {status}")
    for e in result.errors:
        print(f"    ERROR: {e}")
    for w in result.warnings:
        print(f"    WARN:  {w}")
    if not result.is_valid:
        all_valid = False

if not all_valid:
    print("\nValidation failed. Fix errors before saving.")
    sys.exit(1)

print("\nAll validations passed.")

# Save to Neo4j
try:
    with Neo4jConnection() as conn:
        conn.verify_connection()
        print("Connected to Neo4j.\n")

        results = save_pattern(conn, pipeline)

        total_nodes = sum(r.get("nodes_created", 0) for r in results)
        total_rels = sum(r.get("relationships_created", 0) for r in results)
        total_props = sum(r.get("properties_set", 0) for r in results)
        print(f"Executed {len(results)} statements:")
        print(f"  Nodes created:         {total_nodes}")
        print(f"  Relationships created: {total_rels}")
        print(f"  Properties set:        {total_props}")

        counts = verify_pattern(conn, RECIPE_ID)
        print(f"\nVerification (recipe_id='{RECIPE_ID}'):")
        print(f"  Nodes in DB:         {counts['nodes']}")
        print(f"  Relationships in DB: {counts['relationships']}")

        print(f"\nDone! Open Neo4j Browser and run:")
        print(f"  MATCH (n) WHERE n.recipe_id = '{RECIPE_ID}' OR n.format_id = '{RECIPE_ID}' RETURN n")

except Exception as e:
    print(f"\nCould not save to Neo4j: {e}")
    print("Set NEO4J_URI and NEO4J_PASSWORD env vars, then re-run.")
    sys.exit(1)
