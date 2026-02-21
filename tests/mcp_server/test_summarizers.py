# tests/mcp_server/test_summarizers.py — Pure unit tests for summarizers
"""Tests for mcp_server.summarizers — no Neo4j needed.

Builds a minimal payroll pipeline graph in-memory and verifies
that the summarizer functions extract the correct structure.
"""
import pytest

from domain.types import GraphPattern, Node, NodeLabel, Relationship, RelationshipType
from domain.ontology import ValidationResult
from mcp_server.summarizers import (
    _find_nodes_by_label,
    _find_related_nodes,
    _find_single_node_by_label,
    _prop,
    _resolve_account_for_slot,
    summarize_build_result,
    summarize_format_load,
    summarize_processing_instructions,
    summarize_recipe_load,
    summarize_validation_result,
)

RECIPE_ID = "payroll_monthly_v1"
FORMAT_ID = RECIPE_ID


# ============================================================================
# Fixture: minimal payroll pipeline graph
# ============================================================================

def _minimal_pipeline() -> GraphPattern:
    """Build a complete payroll pipeline graph in memory.

    Same structure as load_payroll.py:
    - 1 SourceSchema + 6 Columns + 3 Measures (+ AGGREGATES)
    - 1 AccountingRecipe + 3 MappingRules + 6 AccountSlots + 4 Accounts
    - 1 OutputFormat + 6 OutputColumns + 1 ValidationRule + 1 EntryStructure
    Total: 27 nodes, 36 relationships (approx, matching load_payroll.py)
    """
    # --- Source Schema ---
    schema = Node(
        id="schema_payroll", labels={NodeLabel.SOURCE_SCHEMA},
        properties={
            "recipe_id": RECIPE_ID, "name": "payroll_export",
            "source_system": "csv_import", "file_pattern": "payroll_*.csv",
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
            "operation": "sum", "description": "Sum of gross pay",
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

    # Schema relationships
    col_rels = [
        Relationship(id=f"rel_has_col_{c.id}", type=RelationshipType.HAS_COLUMN,
                     start_node_id="schema_payroll", end_node_id=c.id, properties={})
        for c in columns
    ]
    msr_rels = [
        Relationship(id=f"rel_has_msr_{m.id}", type=RelationshipType.HAS_MEASURE,
                     start_node_id="schema_payroll", end_node_id=m.id, properties={})
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

    # --- Accounting Recipe ---
    recipe = Node(
        id="recipe_payroll", labels={NodeLabel.ACCOUNTING_RECIPE},
        properties={
            "recipe_id": RECIPE_ID, "name": "Monthly Payroll Journal",
            "source_schema": "payroll_export", "batch_key": "pay_date",
            "journal_no_format": "PY-{date:%Y%m}-{seq:04d}", "visibility": "private",
        },
    )
    transforms_rel = Relationship(
        id="rel_transforms", type=RelationshipType.TRANSFORMS,
        start_node_id="recipe_payroll", end_node_id="schema_payroll", properties={},
    )

    # Mapping rules
    rule_gross = Node(id="rule_gross", labels={NodeLabel.MAPPING_RULE}, properties={
        "recipe_id": RECIPE_ID, "rule_name": "gross_pay_entry",
        "source_measure": "total_gross_pay",
        "memo_template": "Salary expense - {pay_date:%B %Y}", "priority": 1,
    })
    rule_tax = Node(id="rule_tax", labels={NodeLabel.MAPPING_RULE}, properties={
        "recipe_id": RECIPE_ID, "rule_name": "tax_withholding_entry",
        "source_measure": "total_tax_withheld",
        "memo_template": "Tax withholding - {pay_date:%B %Y}", "priority": 2,
    })
    rule_net = Node(id="rule_net", labels={NodeLabel.MAPPING_RULE}, properties={
        "recipe_id": RECIPE_ID, "rule_name": "net_pay_entry",
        "source_measure": "total_net_pay",
        "memo_template": "Net pay disbursement - {pay_date:%B %Y}", "priority": 3,
    })
    rules = [rule_gross, rule_tax, rule_net]

    # Account slots
    slot_salary_dr = Node(id="slot_salary_dr", labels={NodeLabel.ACCOUNT_SLOT}, properties={
        "recipe_id": RECIPE_ID, "slot_id": "salary_expense_debit",
        "role": "primary", "entry_type": "debit",
    })
    slot_payroll_cr_gross = Node(id="slot_payroll_cr_gross", labels={NodeLabel.ACCOUNT_SLOT}, properties={
        "recipe_id": RECIPE_ID, "slot_id": "payroll_payable_credit_gross",
        "role": "offset", "entry_type": "credit",
    })
    slot_payroll_dr_tax = Node(id="slot_payroll_dr_tax", labels={NodeLabel.ACCOUNT_SLOT}, properties={
        "recipe_id": RECIPE_ID, "slot_id": "payroll_payable_debit_tax",
        "role": "primary", "entry_type": "debit",
    })
    slot_tax_cr = Node(id="slot_tax_cr", labels={NodeLabel.ACCOUNT_SLOT}, properties={
        "recipe_id": RECIPE_ID, "slot_id": "tax_payable_credit",
        "role": "offset", "entry_type": "credit",
    })
    slot_payroll_dr_net = Node(id="slot_payroll_dr_net", labels={NodeLabel.ACCOUNT_SLOT}, properties={
        "recipe_id": RECIPE_ID, "slot_id": "payroll_payable_debit_net",
        "role": "primary", "entry_type": "debit",
    })
    slot_cash_cr = Node(id="slot_cash_cr", labels={NodeLabel.ACCOUNT_SLOT}, properties={
        "recipe_id": RECIPE_ID, "slot_id": "cash_credit",
        "role": "offset", "entry_type": "credit",
    })
    slots = [slot_salary_dr, slot_payroll_cr_gross, slot_payroll_dr_tax,
             slot_tax_cr, slot_payroll_dr_net, slot_cash_cr]

    # Accounts
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

    # Recipe relationships
    rule_rels = [
        Relationship(id="rel_has_rule_gross", type=RelationshipType.HAS_RULE,
                     start_node_id="recipe_payroll", end_node_id="rule_gross", properties={}),
        Relationship(id="rel_has_rule_tax", type=RelationshipType.HAS_RULE,
                     start_node_id="recipe_payroll", end_node_id="rule_tax", properties={}),
        Relationship(id="rel_has_rule_net", type=RelationshipType.HAS_RULE,
                     start_node_id="recipe_payroll", end_node_id="rule_net", properties={}),
        # Gross rule slots
        Relationship(id="rel_dr_gross", type=RelationshipType.DEBITS,
                     start_node_id="rule_gross", end_node_id="slot_salary_dr", properties={}),
        Relationship(id="rel_cr_gross", type=RelationshipType.CREDITS,
                     start_node_id="rule_gross", end_node_id="slot_payroll_cr_gross", properties={}),
        # Tax rule slots
        Relationship(id="rel_dr_tax", type=RelationshipType.DEBITS,
                     start_node_id="rule_tax", end_node_id="slot_payroll_dr_tax", properties={}),
        Relationship(id="rel_cr_tax", type=RelationshipType.CREDITS,
                     start_node_id="rule_tax", end_node_id="slot_tax_cr", properties={}),
        # Net rule slots
        Relationship(id="rel_dr_net", type=RelationshipType.DEBITS,
                     start_node_id="rule_net", end_node_id="slot_payroll_dr_net", properties={}),
        Relationship(id="rel_cr_net", type=RelationshipType.CREDITS,
                     start_node_id="rule_net", end_node_id="slot_cash_cr", properties={}),
    ]
    # MAPPED_TO: slot → account
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

    # --- Output Format ---
    output_fmt = Node(
        id="fmt_journal", labels={NodeLabel.OUTPUT_FORMAT},
        properties={
            "format_id": FORMAT_ID, "name": "journal_entry_export",
            "target_system": "quickbooks", "file_format": "csv", "version": "1.0",
        },
    )
    out_columns = [
        Node(id="ocol_journal_no", labels={NodeLabel.OUTPUT_COLUMN}, properties={
            "format_id": FORMAT_ID, "name": "journal_number", "position": 1,
            "data_type": "string", "required": True,
        }),
        Node(id="ocol_date", labels={NodeLabel.OUTPUT_COLUMN}, properties={
            "format_id": FORMAT_ID, "name": "journal_date", "position": 2,
            "data_type": "date", "required": True,
        }),
        Node(id="ocol_account", labels={NodeLabel.OUTPUT_COLUMN}, properties={
            "format_id": FORMAT_ID, "name": "account_code", "position": 3,
            "data_type": "string", "required": True,
        }),
        Node(id="ocol_debit", labels={NodeLabel.OUTPUT_COLUMN}, properties={
            "format_id": FORMAT_ID, "name": "debit_amount", "position": 4,
            "data_type": "decimal", "required": True,
        }),
        Node(id="ocol_credit", labels={NodeLabel.OUTPUT_COLUMN}, properties={
            "format_id": FORMAT_ID, "name": "credit_amount", "position": 5,
            "data_type": "decimal", "required": True,
        }),
        Node(id="ocol_memo", labels={NodeLabel.OUTPUT_COLUMN}, properties={
            "format_id": FORMAT_ID, "name": "memo", "position": 6,
            "data_type": "string", "required": False,
        }),
    ]
    out_col_rels = [
        Relationship(id=f"rel_fmt_col_{c.id}", type=RelationshipType.HAS_COLUMN,
                     start_node_id="fmt_journal", end_node_id=c.id, properties={})
        for c in out_columns
    ]
    val_rule = Node(id="val_balance", labels={NodeLabel.VALIDATION_RULE}, properties={
        "format_id": FORMAT_ID, "name": "balanced_entry",
        "expression": "SUM(debit_amount) == SUM(credit_amount)",
        "scope": "batch",
    })
    val_rels = [
        Relationship(id="rel_has_val", type=RelationshipType.HAS_VALIDATION,
                     start_node_id="fmt_journal", end_node_id="val_balance", properties={}),
    ]
    entry_struct = Node(id="entry_payroll", labels={NodeLabel.ENTRY_STRUCTURE}, properties={
        "format_id": FORMAT_ID, "entry_separator": "blank_row",
        "grouping_column": "journal_number", "date_column": "journal_date",
    })
    entry_struct_rel = Relationship(
        id="rel_has_entry", type=RelationshipType.HAS_ENTRY_STRUCTURE,
        start_node_id="fmt_journal", end_node_id="entry_payroll", properties={},
    )

    # Assemble all nodes and relationships
    all_nodes = (
        [schema] + columns + measures
        + [recipe] + rules + slots + accounts
        + [output_fmt] + out_columns + [val_rule, entry_struct]
    )
    all_rels = (
        col_rels + msr_rels + agg_rels
        + [transforms_rel] + rule_rels + slot_rels
        + out_col_rels + val_rels + [entry_struct_rel]
    )
    return GraphPattern(nodes=all_nodes, relationships=all_rels)


def _minimal_format() -> GraphPattern:
    """Build a standalone output format graph for testing format-related summarizers."""
    output_fmt = Node(
        id="fmt_journal", labels={NodeLabel.OUTPUT_FORMAT},
        properties={
            "format_id": FORMAT_ID, "name": "journal_entry_export",
            "target_system": "quickbooks", "file_format": "csv", "version": "1.0",
        },
    )
    out_columns = [
        Node(id="ocol_journal_no", labels={NodeLabel.OUTPUT_COLUMN}, properties={
            "format_id": FORMAT_ID, "name": "journal_number", "position": 1,
            "data_type": "string", "required": True,
        }),
        Node(id="ocol_date", labels={NodeLabel.OUTPUT_COLUMN}, properties={
            "format_id": FORMAT_ID, "name": "journal_date", "position": 2,
            "data_type": "date", "required": True,
        }),
        Node(id="ocol_account", labels={NodeLabel.OUTPUT_COLUMN}, properties={
            "format_id": FORMAT_ID, "name": "account_code", "position": 3,
            "data_type": "string", "required": True,
        }),
        Node(id="ocol_debit", labels={NodeLabel.OUTPUT_COLUMN}, properties={
            "format_id": FORMAT_ID, "name": "debit_amount", "position": 4,
            "data_type": "decimal", "required": True,
        }),
        Node(id="ocol_credit", labels={NodeLabel.OUTPUT_COLUMN}, properties={
            "format_id": FORMAT_ID, "name": "credit_amount", "position": 5,
            "data_type": "decimal", "required": True,
        }),
        Node(id="ocol_memo", labels={NodeLabel.OUTPUT_COLUMN}, properties={
            "format_id": FORMAT_ID, "name": "memo", "position": 6,
            "data_type": "string", "required": False,
        }),
    ]
    out_col_rels = [
        Relationship(id=f"rel_fmt_col_{c.id}", type=RelationshipType.HAS_COLUMN,
                     start_node_id="fmt_journal", end_node_id=c.id, properties={})
        for c in out_columns
    ]
    val_rule = Node(id="val_balance", labels={NodeLabel.VALIDATION_RULE}, properties={
        "format_id": FORMAT_ID, "name": "balanced_entry",
        "expression": "SUM(debit_amount) == SUM(credit_amount)",
        "scope": "batch",
    })
    val_rels = [
        Relationship(id="rel_has_val", type=RelationshipType.HAS_VALIDATION,
                     start_node_id="fmt_journal", end_node_id="val_balance", properties={}),
    ]
    entry_struct = Node(id="entry_payroll", labels={NodeLabel.ENTRY_STRUCTURE}, properties={
        "format_id": FORMAT_ID, "entry_separator": "blank_row",
        "grouping_column": "journal_number", "date_column": "journal_date",
    })
    entry_struct_rel = Relationship(
        id="rel_has_entry", type=RelationshipType.HAS_ENTRY_STRUCTURE,
        start_node_id="fmt_journal", end_node_id="entry_payroll", properties={},
    )

    all_nodes = [output_fmt] + out_columns + [val_rule, entry_struct]
    all_rels = out_col_rels + val_rels + [entry_struct_rel]
    return GraphPattern(nodes=all_nodes, relationships=all_rels)


@pytest.fixture
def pipeline():
    return _minimal_pipeline()


@pytest.fixture
def format_pattern():
    return _minimal_format()


@pytest.fixture
def empty_pattern():
    return GraphPattern(nodes=[], relationships=[])


# ============================================================================
# TestFindNodesByLabel
# ============================================================================

class TestFindNodesByLabel:
    def test_finds_matching_nodes(self, pipeline):
        columns = _find_nodes_by_label(pipeline, NodeLabel.COLUMN)
        assert len(columns) == 6

    def test_returns_empty_for_no_matches(self, pipeline):
        # TRANSACTION is not in the pipeline
        result = _find_nodes_by_label(pipeline, NodeLabel.TRANSACTION)
        assert result == []

    def test_single_node_label(self, pipeline):
        schemas = _find_nodes_by_label(pipeline, NodeLabel.SOURCE_SCHEMA)
        assert len(schemas) == 1
        assert schemas[0].id == "schema_payroll"

    def test_empty_pattern(self, empty_pattern):
        result = _find_nodes_by_label(empty_pattern, NodeLabel.ACCOUNT)
        assert result == []


# ============================================================================
# TestFindSingleNodeByLabel
# ============================================================================

class TestFindSingleNodeByLabel:
    def test_finds_schema(self, pipeline):
        node = _find_single_node_by_label(pipeline, NodeLabel.SOURCE_SCHEMA)
        assert node is not None
        assert node.id == "schema_payroll"

    def test_returns_none_for_missing(self, pipeline):
        result = _find_single_node_by_label(pipeline, NodeLabel.TRANSACTION)
        assert result is None

    def test_empty_pattern(self, empty_pattern):
        result = _find_single_node_by_label(empty_pattern, NodeLabel.ACCOUNT)
        assert result is None


# ============================================================================
# TestFindRelatedNodes
# ============================================================================

class TestFindRelatedNodes:
    def test_follows_outgoing_has_column(self, pipeline):
        columns = _find_related_nodes(
            pipeline, "schema_payroll", RelationshipType.HAS_COLUMN,
        )
        assert len(columns) == 6

    def test_follows_outgoing_has_rule(self, pipeline):
        rules = _find_related_nodes(
            pipeline, "recipe_payroll", RelationshipType.HAS_RULE,
        )
        assert len(rules) == 3

    def test_returns_empty_for_no_edges(self, pipeline):
        # Schema has no HAS_RULE edges
        result = _find_related_nodes(
            pipeline, "schema_payroll", RelationshipType.HAS_RULE,
        )
        assert result == []

    def test_returns_empty_for_unknown_node(self, pipeline):
        result = _find_related_nodes(
            pipeline, "nonexistent_node", RelationshipType.HAS_COLUMN,
        )
        assert result == []


# ============================================================================
# TestResolveAccountForSlot
# ============================================================================

class TestResolveAccountForSlot:
    def test_resolves_salary_expense(self, pipeline):
        acct = _resolve_account_for_slot(pipeline, "slot_salary_dr")
        assert acct is not None
        assert acct.properties["code"] == "6100"
        assert acct.properties["name"] == "Salary Expense"

    def test_resolves_cash(self, pipeline):
        acct = _resolve_account_for_slot(pipeline, "slot_cash_cr")
        assert acct is not None
        assert acct.properties["code"] == "1010"

    def test_returns_none_for_unmapped_slot(self, pipeline):
        # Create a pattern with a slot but no MAPPED_TO
        slot = Node(id="orphan_slot", labels={NodeLabel.ACCOUNT_SLOT}, properties={
            "recipe_id": "test", "slot_id": "orphan", "role": "primary", "entry_type": "debit",
        })
        pattern = GraphPattern(nodes=[slot], relationships=[])
        result = _resolve_account_for_slot(pattern, "orphan_slot")
        assert result is None

    def test_returns_none_for_unknown_slot(self, pipeline):
        result = _resolve_account_for_slot(pipeline, "nonexistent")
        assert result is None


# ============================================================================
# TestProp
# ============================================================================

class TestProp:
    def test_existing_property(self, pipeline):
        schema = _find_single_node_by_label(pipeline, NodeLabel.SOURCE_SCHEMA)
        assert _prop(schema, "name") == "payroll_export"

    def test_missing_property_returns_default(self, pipeline):
        schema = _find_single_node_by_label(pipeline, NodeLabel.SOURCE_SCHEMA)
        assert _prop(schema, "nonexistent") is None
        assert _prop(schema, "nonexistent", "fallback") == "fallback"


# ============================================================================
# TestSummarizeRecipeLoad
# ============================================================================

class TestSummarizeRecipeLoad:
    def test_has_correct_recipe_id(self, pipeline):
        result = summarize_recipe_load(pipeline, RECIPE_ID)
        assert result["recipe_id"] == RECIPE_ID

    def test_graph_structure_counts(self, pipeline):
        result = summarize_recipe_load(pipeline, RECIPE_ID)
        gs = result["graph_structure"]
        assert gs["total_nodes"] == len(pipeline.nodes)
        assert gs["total_relationships"] == len(pipeline.relationships)

    def test_schema_has_columns(self, pipeline):
        result = summarize_recipe_load(pipeline, RECIPE_ID)
        schema = result["schema"]
        assert schema["name"] == "payroll_export"
        assert schema["file_pattern"] == "payroll_*.csv"
        assert len(schema["columns"]) == 6
        # Columns sorted by position
        positions = [c["position"] for c in schema["columns"]]
        assert positions == sorted(positions)

    def test_recipe_has_rules(self, pipeline):
        result = summarize_recipe_load(pipeline, RECIPE_ID)
        recipe = result["recipe"]
        assert recipe["name"] == "Monthly Payroll Journal"
        assert recipe["journal_no_format"] == "PY-{date:%Y%m}-{seq:04d}"
        assert len(recipe["rules"]) == 3
        # Rules sorted by priority
        priorities = [r["priority"] for r in recipe["rules"]]
        assert priorities == sorted(priorities)

    def test_recipe_name_at_top_level(self, pipeline):
        result = summarize_recipe_load(pipeline, RECIPE_ID)
        assert result["recipe_name"] == "Monthly Payroll Journal"

    def test_no_output_in_recipe_load(self, pipeline):
        """Recipe load should not include output format section (formats are independent)."""
        result = summarize_recipe_load(pipeline, RECIPE_ID)
        assert "output" not in result

    def test_handles_empty_pattern(self, empty_pattern):
        result = summarize_recipe_load(empty_pattern, RECIPE_ID)
        assert result["recipe_id"] == RECIPE_ID
        assert result["graph_structure"]["total_nodes"] == 0
        assert "schema" not in result
        assert "recipe" not in result

    def test_has_condition_flag(self):
        """Rule with WHEN relationship shows has_condition: True in recipe load summary."""
        schema = Node(
            id="schema_test", labels={NodeLabel.SOURCE_SCHEMA},
            properties={"recipe_id": RECIPE_ID, "name": "charges", "source_system": "stripe"},
        )
        recipe = Node(
            id="recipe_test", labels={NodeLabel.ACCOUNTING_RECIPE},
            properties={"recipe_id": RECIPE_ID, "name": "Test Recipe", "source_schema": "charges"},
        )
        rule = Node(
            id="rule_paid", labels={NodeLabel.MAPPING_RULE},
            properties={
                "recipe_id": RECIPE_ID, "rule_name": "paid_entry",
                "source_measure": "total_amount", "priority": 1,
            },
        )
        cond = Node(
            id="cond_is_paid", labels={NodeLabel.CONDITION},
            properties={
                "recipe_id": RECIPE_ID, "condition_id": "is_paid",
                "column": "status", "operator": "equals", "value": "paid",
            },
        )
        rels = [
            Relationship(id="r_transforms", type=RelationshipType.TRANSFORMS,
                         start_node_id="recipe_test", end_node_id="schema_test", properties={}),
            Relationship(id="r_has_rule", type=RelationshipType.HAS_RULE,
                         start_node_id="recipe_test", end_node_id="rule_paid", properties={}),
            Relationship(id="r_when", type=RelationshipType.WHEN,
                         start_node_id="rule_paid", end_node_id="cond_is_paid", properties={}),
        ]
        pattern = GraphPattern(nodes=[schema, recipe, rule, cond], relationships=rels)
        result = summarize_recipe_load(pattern, RECIPE_ID)
        rules = result["recipe"]["rules"]
        assert len(rules) == 1
        assert rules[0]["has_condition"] is True

    def test_no_condition_flag_without_when(self, pipeline):
        """Rules without WHEN edges do not have has_condition key."""
        result = summarize_recipe_load(pipeline, RECIPE_ID)
        for rule in result["recipe"]["rules"]:
            assert "has_condition" not in rule


# ============================================================================
# TestSummarizeProcessingInstructions
# ============================================================================

class TestSummarizeProcessingInstructions:
    def test_has_correct_recipe_id(self, pipeline):
        result = summarize_processing_instructions(pipeline, RECIPE_ID)
        assert result["recipe_id"] == RECIPE_ID

    def test_measures_have_column_names(self, pipeline):
        result = summarize_processing_instructions(pipeline, RECIPE_ID)
        measures = result["measures"]
        assert len(measures) == 3
        # Each measure should have a resolved column name
        for m in measures:
            assert m["column"] is not None
        col_names = {m["column"] for m in measures}
        assert "gross_pay" in col_names
        assert "tax_withheld" in col_names
        assert "net_pay" in col_names

    def test_measures_have_operations(self, pipeline):
        result = summarize_processing_instructions(pipeline, RECIPE_ID)
        for m in result["measures"]:
            assert m["operation"] == "sum"

    def test_rules_sorted_by_priority(self, pipeline):
        result = summarize_processing_instructions(pipeline, RECIPE_ID)
        rules = result["rules"]
        assert len(rules) == 3
        priorities = [r["priority"] for r in rules]
        assert priorities == [1, 2, 3]

    def test_rules_have_resolved_accounts(self, pipeline):
        result = summarize_processing_instructions(pipeline, RECIPE_ID)
        rules = result["rules"]
        # First rule (gross): DR 6100 Salary Expense / CR 2100 Payroll Payable
        gross_rule = rules[0]
        assert gross_rule["name"] == "gross_pay_entry"
        assert len(gross_rule["debits"]) == 1
        assert gross_rule["debits"][0]["account_code"] == "6100"
        assert len(gross_rule["credits"]) == 1
        assert gross_rule["credits"][0]["account_code"] == "2100"

    def test_rules_have_memo_templates(self, pipeline):
        result = summarize_processing_instructions(pipeline, RECIPE_ID)
        for rule in result["rules"]:
            assert rule["memo_template"] is not None

    def test_output_columns_sorted_by_position(self, pipeline, format_pattern):
        result = summarize_processing_instructions(pipeline, RECIPE_ID, format_pattern=format_pattern)
        output = result["output_format"]
        positions = [c["position"] for c in output["columns"]]
        assert positions == [1, 2, 3, 4, 5, 6]

    def test_output_has_validation_rules(self, pipeline, format_pattern):
        result = summarize_processing_instructions(pipeline, RECIPE_ID, format_pattern=format_pattern)
        val_rules = result["output_format"]["validation_rules"]
        assert len(val_rules) == 1
        assert val_rules[0]["name"] == "balanced_entry"

    def test_output_has_entry_structure(self, pipeline, format_pattern):
        result = summarize_processing_instructions(pipeline, RECIPE_ID, format_pattern=format_pattern)
        entry = result["output_format"]["entry_structure"]
        assert entry["grouping_column"] == "journal_number"
        assert entry["entry_separator"] == "blank_row"

    def test_no_output_without_format_pattern(self, pipeline):
        """Without format_pattern, processing instructions omit output_format."""
        result = summarize_processing_instructions(pipeline, RECIPE_ID)
        assert "output_format" not in result

    def test_handles_missing_components(self, empty_pattern):
        result = summarize_processing_instructions(empty_pattern, RECIPE_ID)
        assert result["recipe_id"] == RECIPE_ID
        assert "measures" not in result
        assert "rules" not in result
        assert "output_format" not in result

    def test_measure_group_by_emitted(self, pipeline):
        """group_by comma string on Measure node is split into array in output."""
        # Add group_by to the first measure node
        for n in pipeline.nodes:
            if NodeLabel.MEASURE in n.labels and n.properties["name"] == "total_gross_pay":
                n.properties["group_by"] = "pay_date,location"
                break
        result = summarize_processing_instructions(pipeline, RECIPE_ID)
        gross_measure = next(m for m in result["measures"] if m["name"] == "total_gross_pay")
        assert gross_measure["group_by"] == ["pay_date", "location"]

    def test_measure_split_by_emitted(self, pipeline):
        """split_by on Measure node appears in output."""
        for n in pipeline.nodes:
            if NodeLabel.MEASURE in n.labels and n.properties["name"] == "total_gross_pay":
                n.properties["split_by"] = "department"
                break
        result = summarize_processing_instructions(pipeline, RECIPE_ID)
        gross_measure = next(m for m in result["measures"] if m["name"] == "total_gross_pay")
        assert gross_measure["split_by"] == "department"

    def test_measure_split_column_emitted(self, pipeline):
        """split_column on Measure node appears in output."""
        for n in pipeline.nodes:
            if NodeLabel.MEASURE in n.labels and n.properties["name"] == "total_gross_pay":
                n.properties["split_column"] = "dept_code"
                break
        result = summarize_processing_instructions(pipeline, RECIPE_ID)
        gross_measure = next(m for m in result["measures"] if m["name"] == "total_gross_pay")
        assert gross_measure["split_column"] == "dept_code"

    def test_measure_no_aggregation_fields(self, pipeline):
        """Measures without group_by/split_by/split_column omit those keys (backward compat)."""
        result = summarize_processing_instructions(pipeline, RECIPE_ID)
        for m in result["measures"]:
            assert "group_by" not in m
            assert "split_by" not in m
            assert "split_column" not in m

    def test_handles_no_entry_structure(self):
        """Output format without entry structure omits the entry_structure key."""
        fmt = Node(id="fmt1", labels={NodeLabel.OUTPUT_FORMAT}, properties={
            "format_id": "test", "name": "test_fmt",
            "target_system": "test", "file_format": "csv",
        })
        ocol = Node(id="oc1", labels={NodeLabel.OUTPUT_COLUMN}, properties={
            "format_id": "test", "name": "col1", "position": 1, "data_type": "string",
        })
        rel = Relationship(id="r1", type=RelationshipType.HAS_COLUMN,
                           start_node_id="fmt1", end_node_id="oc1", properties={})
        fmt_pattern = GraphPattern(nodes=[fmt, ocol], relationships=[rel])
        result = summarize_processing_instructions(
            GraphPattern(nodes=[], relationships=[]), "test", format_pattern=fmt_pattern,
        )
        output = result["output_format"]
        assert "entry_structure" not in output
        assert len(output["columns"]) == 1

    def _pipeline_with_condition(self, operator="equals", value="paid"):
        """Build a minimal pipeline containing one rule wired to one Condition via WHEN."""
        schema = Node(
            id="schema_test", labels={NodeLabel.SOURCE_SCHEMA},
            properties={"recipe_id": RECIPE_ID, "name": "charges", "source_system": "stripe"},
        )
        measure = Node(
            id="msr_total", labels={NodeLabel.MEASURE},
            properties={"recipe_id": RECIPE_ID, "name": "total_amount", "operation": "sum"},
        )
        recipe = Node(
            id="recipe_test", labels={NodeLabel.ACCOUNTING_RECIPE},
            properties={"recipe_id": RECIPE_ID, "name": "Test Recipe", "source_schema": "charges"},
        )
        rule = Node(
            id="rule_paid", labels={NodeLabel.MAPPING_RULE},
            properties={
                "recipe_id": RECIPE_ID, "rule_name": "paid_entry",
                "source_measure": "total_amount", "priority": 1,
            },
        )
        cond_props = {
            "recipe_id": RECIPE_ID, "condition_id": "is_paid",
            "column": "status", "operator": operator,
        }
        if value is not None:
            cond_props["value"] = value
        cond = Node(id="cond_is_paid", labels={NodeLabel.CONDITION}, properties=cond_props)

        slot_dr = Node(id="slot_dr", labels={NodeLabel.ACCOUNT_SLOT}, properties={
            "recipe_id": RECIPE_ID, "slot_id": "dr", "role": "primary", "entry_type": "debit",
        })
        slot_cr = Node(id="slot_cr", labels={NodeLabel.ACCOUNT_SLOT}, properties={
            "recipe_id": RECIPE_ID, "slot_id": "cr", "role": "offset", "entry_type": "credit",
        })
        acct_dr = Node(id="acct_1200", labels={NodeLabel.ACCOUNT}, properties={
            "code": "1200", "name": "AR", "account_type": "asset", "normal_balance": "debit", "is_active": True,
        })
        acct_cr = Node(id="acct_4000", labels={NodeLabel.ACCOUNT}, properties={
            "code": "4000", "name": "Revenue", "account_type": "revenue", "normal_balance": "credit", "is_active": True,
        })

        rels = [
            Relationship(id="r_transforms", type=RelationshipType.TRANSFORMS,
                         start_node_id="recipe_test", end_node_id="schema_test", properties={}),
            Relationship(id="r_has_msr", type=RelationshipType.HAS_MEASURE,
                         start_node_id="schema_test", end_node_id="msr_total", properties={}),
            Relationship(id="r_has_rule", type=RelationshipType.HAS_RULE,
                         start_node_id="recipe_test", end_node_id="rule_paid", properties={}),
            Relationship(id="r_when", type=RelationshipType.WHEN,
                         start_node_id="rule_paid", end_node_id="cond_is_paid", properties={}),
            Relationship(id="r_dr", type=RelationshipType.DEBITS,
                         start_node_id="rule_paid", end_node_id="slot_dr", properties={}),
            Relationship(id="r_cr", type=RelationshipType.CREDITS,
                         start_node_id="rule_paid", end_node_id="slot_cr", properties={}),
            Relationship(id="r_map_dr", type=RelationshipType.MAPPED_TO,
                         start_node_id="slot_dr", end_node_id="acct_1200", properties={}),
            Relationship(id="r_map_cr", type=RelationshipType.MAPPED_TO,
                         start_node_id="slot_cr", end_node_id="acct_4000", properties={}),
        ]
        nodes = [schema, measure, recipe, rule, cond, slot_dr, slot_cr, acct_dr, acct_cr]
        return GraphPattern(nodes=nodes, relationships=rels)

    def test_when_condition_emitted(self):
        """Rule with WHEN has a 'conditions' key in processing instructions output."""
        pattern = self._pipeline_with_condition()
        result = summarize_processing_instructions(pattern, RECIPE_ID)
        rules = result["rules"]
        assert len(rules) == 1
        assert "conditions" in rules[0]

    def test_condition_fields_complete(self):
        """Condition entry has condition_id, column, and operator."""
        pattern = self._pipeline_with_condition()
        result = summarize_processing_instructions(pattern, RECIPE_ID)
        cond = result["rules"][0]["conditions"][0]
        assert cond["condition_id"] == "is_paid"
        assert cond["column"] == "status"
        assert cond["operator"] == "equals"

    def test_condition_value_present(self):
        """Equals condition includes 'value' in output."""
        pattern = self._pipeline_with_condition(operator="equals", value="paid")
        result = summarize_processing_instructions(pattern, RECIPE_ID)
        cond = result["rules"][0]["conditions"][0]
        assert cond["value"] == "paid"

    def test_condition_without_value(self):
        """is_null condition omits 'value' from output."""
        pattern = self._pipeline_with_condition(operator="is_null", value=None)
        result = summarize_processing_instructions(pattern, RECIPE_ID)
        cond = result["rules"][0]["conditions"][0]
        assert "value" not in cond

    def test_no_condition_backward_compat(self, pipeline):
        """Rules without WHEN edges have no 'conditions' key in output."""
        result = summarize_processing_instructions(pipeline, RECIPE_ID)
        for rule in result["rules"]:
            assert "conditions" not in rule


# ============================================================================
# TestSummarizeBuildResult
# ============================================================================

class TestSummarizeBuildResult:
    def test_valid_build_with_save_counts(self, pipeline):
        vr = ValidationResult.success(warnings=("Slot orphan has no MAPPED_TO",))
        save_counts = [
            {"nodes_created": 10, "relationships_created": 15, "properties_set": 80},
            {"nodes_created": 5, "relationships_created": 5, "properties_set": 30},
        ]
        result = summarize_build_result(vr, save_counts, RECIPE_ID, pipeline)

        assert result["recipe_id"] == RECIPE_ID
        assert result["gate1_validation"]["is_valid"] is True
        assert result["gate1_validation"]["warnings"] == ["Slot orphan has no MAPPED_TO"]
        assert result["saved"] is True
        assert result["counts"]["nodes"] == len(pipeline.nodes)
        assert result["counts"]["relationships"] == len(pipeline.relationships)
        assert result["counts"]["nodes_created"] == 15
        assert result["counts"]["relationships_created"] == 20
        assert result["counts"]["properties_set"] == 110

    def test_failed_validation_no_save(self, pipeline):
        vr = ValidationResult.failure(("Missing TRANSFORMS",), ("Some warning",))
        result = summarize_build_result(vr, None, RECIPE_ID, pipeline)

        assert result["recipe_id"] == RECIPE_ID
        assert result["gate1_validation"]["is_valid"] is False
        assert result["gate1_validation"]["errors"] == ["Missing TRANSFORMS"]
        assert result["saved"] is False
        assert result["counts"] is None

    def test_no_warnings_no_errors(self, pipeline):
        vr = ValidationResult.success()
        save_counts = [{"nodes_created": 1, "relationships_created": 0, "properties_set": 5}]
        result = summarize_build_result(vr, save_counts, RECIPE_ID, pipeline)

        assert result["gate1_validation"]["errors"] == []
        assert result["gate1_validation"]["warnings"] == []
        assert result["saved"] is True


# ============================================================================
# TestSummarizeValidationResult
# ============================================================================

class TestSummarizeValidationResult:
    def test_valid_entries(self):
        entries_results = [
            {"entry_index": 0, "is_valid": True, "debit_total": "24500.00", "credit_total": "24500.00"},
            {"entry_index": 1, "is_valid": True, "debit_total": "6125.00", "credit_total": "6125.00"},
        ]
        account_results = [
            {"account_code": "6100", "is_active": True},
            {"account_code": "2100", "is_active": True},
        ]
        merged = ValidationResult.success()
        result = summarize_validation_result(entries_results, account_results, merged)

        assert result["gate2_validation"]["is_valid"] is True
        assert result["gate2_validation"]["entries_checked"] == 2
        assert result["gate2_validation"]["accounts_checked"] == 2
        assert len(result["entry_details"]) == 2

    def test_unbalanced_entry(self):
        entries_results = [
            {"entry_index": 0, "is_valid": False, "debit_total": "100.00", "credit_total": "50.00"},
        ]
        merged = ValidationResult.failure(
            ("Transaction is unbalanced: debits=100.00, credits=50.00",),
        )
        result = summarize_validation_result(entries_results, [], merged)

        assert result["gate2_validation"]["is_valid"] is False
        assert len(result["gate2_validation"]["errors"]) == 1
        assert result["gate2_validation"]["entries_checked"] == 1
        assert result["gate2_validation"]["accounts_checked"] == 0

    def test_inactive_account_warning(self):
        entries_results = [
            {"entry_index": 0, "is_valid": True, "debit_total": "100.00", "credit_total": "100.00"},
        ]
        account_results = [
            {"account_code": "6100", "is_active": False},
        ]
        merged = ValidationResult.failure(("Cannot post to inactive account",))
        result = summarize_validation_result(entries_results, account_results, merged)

        assert result["gate2_validation"]["is_valid"] is False
        assert result["gate2_validation"]["accounts_checked"] == 1

    def test_empty_entries(self):
        merged = ValidationResult.success()
        result = summarize_validation_result([], [], merged)

        assert result["gate2_validation"]["is_valid"] is True
        assert result["gate2_validation"]["entries_checked"] == 0
        assert result["gate2_validation"]["accounts_checked"] == 0
        assert result["entry_details"] == []


# ============================================================================
# TestSummarizeFormatLoad
# ============================================================================

class TestSummarizeFormatLoad:
    def test_has_format_id(self, format_pattern):
        result = summarize_format_load(format_pattern, FORMAT_ID)
        assert result["format_id"] == FORMAT_ID

    def test_graph_structure_counts(self, format_pattern):
        result = summarize_format_load(format_pattern, FORMAT_ID)
        gs = result["graph_structure"]
        assert gs["total_nodes"] == len(format_pattern.nodes)
        assert gs["total_relationships"] == len(format_pattern.relationships)

    def test_format_name(self, format_pattern):
        result = summarize_format_load(format_pattern, FORMAT_ID)
        assert result["format_name"] == "journal_entry_export"

    def test_target_system_and_file_format(self, format_pattern):
        result = summarize_format_load(format_pattern, FORMAT_ID)
        assert result["target_system"] == "quickbooks"
        assert result["file_format"] == "csv"

    def test_columns_sorted_by_position(self, format_pattern):
        result = summarize_format_load(format_pattern, FORMAT_ID)
        assert len(result["columns"]) == 6
        positions = [c["position"] for c in result["columns"]]
        assert positions == [1, 2, 3, 4, 5, 6]

    def test_validation_rules(self, format_pattern):
        result = summarize_format_load(format_pattern, FORMAT_ID)
        assert len(result["validation_rules"]) == 1
        assert result["validation_rules"][0]["name"] == "balanced_entry"

    def test_entry_structure(self, format_pattern):
        result = summarize_format_load(format_pattern, FORMAT_ID)
        assert result["entry_structure"]["grouping_column"] == "journal_number"
        assert result["entry_structure"]["entry_separator"] == "blank_row"
        assert result["entry_structure"]["date_column"] == "journal_date"

    def test_empty_pattern(self, empty_pattern):
        result = summarize_format_load(empty_pattern, "test")
        assert result["format_id"] == "test"
        assert result["graph_structure"]["total_nodes"] == 0
        assert "format_name" not in result
