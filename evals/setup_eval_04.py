"""Pre-load a payroll recipe pipeline (without output format) into Neo4j for Eval 4.

Builds the same payroll recipe structure as setup_eval_02.py but omits the
OutputFormat/OutputColumn/ValidationRule/EntryStructure nodes. This forces
the agent to build the format independently using build_output.

Usage: python evals/setup_eval_04.py [recipe_id]
  Default recipe_id: eval_payroll_v1
"""

import sys
from pathlib import Path

# Allow running from project root or evals/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from domain import (
    Node,
    NodeLabel,
    Relationship,
    RelationshipType,
    build_recipe_pattern,
    build_source_schema_pattern,
    compose_pipeline_pattern,
    validate_pipeline_connectivity,
    validate_recipe,
)
from domain.ontology import ValidationResult, validate_node_properties
from domain.ontology_recipe import merged_ontology
from persistence import Neo4jConnection, save_pattern, verify_pattern
from persistence.operations import delete_pattern_by_recipe

RECIPE_ID = sys.argv[1] if len(sys.argv) > 1 else "eval_payroll_v1"


# =============================================================================
# Source Schema
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
    column_rels=col_rels,
    measure_rels=msr_rels,
    aggregates_rels=agg_rels,
)


# =============================================================================
# Accounting Recipe (no output format)
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

rule_rels = [
    Relationship(id="rel_has_rule_gross", type=RelationshipType.HAS_RULE,
                 start_node_id="recipe_payroll", end_node_id="rule_gross", properties={}),
    Relationship(id="rel_has_rule_tax", type=RelationshipType.HAS_RULE,
                 start_node_id="recipe_payroll", end_node_id="rule_tax", properties={}),
    Relationship(id="rel_has_rule_net", type=RelationshipType.HAS_RULE,
                 start_node_id="recipe_payroll", end_node_id="rule_net", properties={}),
    Relationship(id="rel_dr_gross", type=RelationshipType.DEBITS,
                 start_node_id="rule_gross", end_node_id="slot_salary_dr", properties={}),
    Relationship(id="rel_cr_gross", type=RelationshipType.CREDITS,
                 start_node_id="rule_gross", end_node_id="slot_payroll_cr_gross", properties={}),
    Relationship(id="rel_dr_tax", type=RelationshipType.DEBITS,
                 start_node_id="rule_tax", end_node_id="slot_payroll_dr_tax", properties={}),
    Relationship(id="rel_cr_tax", type=RelationshipType.CREDITS,
                 start_node_id="rule_tax", end_node_id="slot_tax_cr", properties={}),
    Relationship(id="rel_dr_net", type=RelationshipType.DEBITS,
                 start_node_id="rule_net", end_node_id="slot_payroll_dr_net", properties={}),
    Relationship(id="rel_cr_net", type=RelationshipType.CREDITS,
                 start_node_id="rule_net", end_node_id="slot_cash_cr", properties={}),
]

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
# Compose, Validate, Save (no output format)
# =============================================================================

pipeline = compose_pipeline_pattern(schema_pattern, recipe_pattern)

# Run all validators
recipe_result = validate_recipe(pipeline)
conn_result = validate_pipeline_connectivity(pipeline)

ontology = merged_ontology()
node_results = [validate_node_properties(n, ontology) for n in pipeline.nodes]
props_result = ValidationResult.merge(*node_results)

all_valid = True
for name, result in [
    ("Recipe structure", recipe_result),
    ("Pipeline connectivity", conn_result),
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

print(f"\nAll validations passed. Saving recipe '{RECIPE_ID}' (no output format)...")

try:
    with Neo4jConnection() as conn:
        conn.verify_connection()

        # Clean up any existing recipe with same ID
        delete_pattern_by_recipe(conn, RECIPE_ID)

        results = save_pattern(conn, pipeline)

        total_nodes = sum(r.get("nodes_created", 0) for r in results)
        total_rels = sum(r.get("relationships_created", 0) for r in results)
        print(f"  Nodes created:         {total_nodes}")
        print(f"  Relationships created: {total_rels}")

        counts = verify_pattern(conn, RECIPE_ID)
        print(f"\nVerification (recipe_id='{RECIPE_ID}'):")
        print(f"  Nodes in DB:         {counts['nodes']}")
        print(f"  Relationships in DB: {counts['relationships']}")
        print(f"\nSetup complete (recipe only, no output format).")

except Exception as e:
    print(f"\nCould not save to Neo4j: {e}")
    print("Set NEO4J_URI and NEO4J_PASSWORD env vars, then re-run.")
    sys.exit(1)
