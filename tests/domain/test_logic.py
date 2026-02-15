# tests/domain/test_logic.py — Tests for Layer 3 pure domain logic
import pytest

from domain.types import (
    GraphPattern,
    Node,
    NodeLabel,
    Relationship,
    RelationshipType,
)
from domain.logic import (
    build_recipe_pattern,
    build_source_schema_pattern,
    extract_debit_credit_slots,
    extract_measures_for_schema,
    validate_recipe,
)


# ============================================================================
# Helpers — reusable test fixtures
# ============================================================================

def _schema_node(node_id="schema1"):
    return Node(
        id=node_id, labels={NodeLabel.SOURCE_SCHEMA},
        properties={"recipe_id": "r1", "name": "Stripe Charges", "source_system": "stripe"},
    )


def _column_node(node_id="col1", name="amount"):
    return Node(
        id=node_id, labels={NodeLabel.COLUMN},
        properties={
            "recipe_id": "r1", "name": name, "position": 0,
            "data_type": "decimal", "role": "amount",
        },
    )


def _measure_node(node_id="m1", name="total_amount"):
    return Node(
        id=node_id, labels={NodeLabel.MEASURE},
        properties={"recipe_id": "r1", "name": name, "operation": "sum"},
    )


def _condition_node(node_id="cond1"):
    return Node(
        id=node_id, labels={NodeLabel.CONDITION},
        properties={
            "recipe_id": "r1", "condition_id": "c1",
            "column": "status", "operator": "equals", "value": "paid",
        },
    )


def _recipe_node(node_id="recipe1"):
    return Node(
        id=node_id, labels={NodeLabel.ACCOUNTING_RECIPE},
        properties={"recipe_id": "r1", "name": "Stripe Revenue", "source_schema": "stripe_charges"},
    )


def _rule_node(node_id="rule1"):
    return Node(
        id=node_id, labels={NodeLabel.MAPPING_RULE},
        properties={"recipe_id": "r1", "rule_name": "charge_rule", "source_measure": "total_amount"},
    )


def _slot_node(node_id="slot1", role="receivable", entry_type="debit"):
    return Node(
        id=node_id, labels={NodeLabel.ACCOUNT_SLOT},
        properties={
            "recipe_id": "r1", "slot_id": node_id,
            "role": role, "entry_type": entry_type,
        },
    )


def _rel(rel_id, rel_type, start, end):
    return Relationship(
        id=rel_id, type=rel_type,
        start_node_id=start, end_node_id=end, properties={},
    )


# ============================================================================
# build_source_schema_pattern
# ============================================================================

class TestBuildSourceSchemaPattern:
    def test_produces_valid_graph_pattern(self):
        schema = _schema_node()
        col = _column_node()
        measure = _measure_node()
        cond = _condition_node()
        col_rel = _rel("r1", RelationshipType.HAS_COLUMN, "schema1", "col1")
        meas_rel = _rel("r2", RelationshipType.HAS_MEASURE, "schema1", "m1")
        agg_rel = _rel("r3", RelationshipType.AGGREGATES, "m1", "col1")

        pattern = build_source_schema_pattern(
            schema_node=schema,
            column_nodes=[col],
            measure_nodes=[measure],
            condition_nodes=[cond],
            column_rels=[col_rel],
            measure_rels=[meas_rel],
            aggregates_rels=[agg_rel],
        )

        assert isinstance(pattern, GraphPattern)
        assert len(pattern.nodes) == 4
        assert len(pattern.relationships) == 3

    def test_without_aggregates(self):
        schema = _schema_node()
        col = _column_node()
        col_rel = _rel("r1", RelationshipType.HAS_COLUMN, "schema1", "col1")

        pattern = build_source_schema_pattern(
            schema_node=schema,
            column_nodes=[col],
            measure_nodes=[],
            condition_nodes=[],
            column_rels=[col_rel],
            measure_rels=[],
        )

        assert len(pattern.nodes) == 2
        assert len(pattern.relationships) == 1

    def test_schema_node_is_first(self):
        schema = _schema_node()
        col = _column_node()
        col_rel = _rel("r1", RelationshipType.HAS_COLUMN, "schema1", "col1")

        pattern = build_source_schema_pattern(
            schema_node=schema,
            column_nodes=[col],
            measure_nodes=[],
            condition_nodes=[],
            column_rels=[col_rel],
            measure_rels=[],
        )

        assert pattern.nodes[0].id == "schema1"


# ============================================================================
# build_recipe_pattern
# ============================================================================

class TestBuildRecipePattern:
    def test_produces_valid_graph_pattern(self):
        recipe = _recipe_node()
        schema = _schema_node()
        transforms = _rel("t1", RelationshipType.TRANSFORMS, "recipe1", "schema1")
        rule = _rule_node()
        rule_rel = _rel("rr1", RelationshipType.HAS_RULE, "recipe1", "rule1")
        debit_slot = _slot_node("ds1", "receivable", "debit")
        credit_slot = _slot_node("cs1", "revenue", "credit")
        dr = _rel("dr1", RelationshipType.DEBITS, "rule1", "ds1")
        cr = _rel("cr1", RelationshipType.CREDITS, "rule1", "cs1")

        pattern = build_recipe_pattern(
            recipe_node=recipe,
            schema_node=schema,
            transforms_rel=transforms,
            rule_nodes=[rule],
            rule_rels=[rule_rel],
            slot_nodes=[debit_slot, credit_slot],
            slot_rels=[dr, cr],
        )

        assert isinstance(pattern, GraphPattern)
        assert len(pattern.nodes) == 5
        assert len(pattern.relationships) == 4

    def test_with_additional_nodes_and_rels(self):
        recipe = _recipe_node()
        schema = _schema_node()
        transforms = _rel("t1", RelationshipType.TRANSFORMS, "recipe1", "schema1")
        extra_node = _condition_node("extra1")
        extra_rel = _rel("e1", RelationshipType.WHEN, "rule1", "extra1")

        pattern = build_recipe_pattern(
            recipe_node=recipe,
            schema_node=schema,
            transforms_rel=transforms,
            rule_nodes=[],
            rule_rels=[],
            slot_nodes=[],
            slot_rels=[],
            additional_nodes=[extra_node],
            additional_rels=[extra_rel],
        )

        assert len(pattern.nodes) == 3
        assert len(pattern.relationships) == 2


# ============================================================================
# validate_recipe
# ============================================================================

class TestValidateRecipe:
    def test_valid_recipe_passes(self):
        recipe = _recipe_node()
        schema = _schema_node()
        rule = _rule_node()
        debit_slot = _slot_node("ds1", "receivable", "debit")
        credit_slot = _slot_node("cs1", "revenue", "credit")

        transforms = _rel("t1", RelationshipType.TRANSFORMS, "recipe1", "schema1")
        rule_rel = _rel("rr1", RelationshipType.HAS_RULE, "recipe1", "rule1")
        dr = _rel("dr1", RelationshipType.DEBITS, "rule1", "ds1")
        cr = _rel("cr1", RelationshipType.CREDITS, "rule1", "cs1")
        mapped_dr = _rel("md1", RelationshipType.MAPPED_TO, "ds1", "acct1")
        mapped_cr = _rel("mc1", RelationshipType.MAPPED_TO, "cs1", "acct2")
        acct1 = Node(
            id="acct1", labels={NodeLabel.ACCOUNT},
            properties={"code": "1200", "name": "AR", "account_type": "asset", "normal_balance": "debit"},
        )
        acct2 = Node(
            id="acct2", labels={NodeLabel.ACCOUNT},
            properties={"code": "4000", "name": "Revenue", "account_type": "revenue", "normal_balance": "credit"},
        )

        pattern = GraphPattern(
            nodes=[recipe, schema, rule, debit_slot, credit_slot, acct1, acct2],
            relationships=[transforms, rule_rel, dr, cr, mapped_dr, mapped_cr],
        )
        result = validate_recipe(pattern)
        assert result.is_valid is True

    def test_recipe_missing_transforms_fails(self):
        recipe = _recipe_node()
        pattern = GraphPattern(nodes=[recipe], relationships=[])
        result = validate_recipe(pattern)
        assert result.is_valid is False
        assert any("TRANSFORMS" in e for e in result.errors)

    def test_recipe_with_incomplete_rule_fails(self):
        recipe = _recipe_node()
        schema = _schema_node()
        rule = _rule_node()
        transforms = _rel("t1", RelationshipType.TRANSFORMS, "recipe1", "schema1")
        rule_rel = _rel("rr1", RelationshipType.HAS_RULE, "recipe1", "rule1")

        pattern = GraphPattern(
            nodes=[recipe, schema, rule],
            relationships=[transforms, rule_rel],
        )
        result = validate_recipe(pattern)
        assert result.is_valid is False
        assert any("DEBITS" in e for e in result.errors)

    def test_recipe_unmapped_slot_warns(self):
        recipe = _recipe_node()
        schema = _schema_node()
        rule = _rule_node()
        debit_slot = _slot_node("ds1", "receivable", "debit")
        credit_slot = _slot_node("cs1", "revenue", "credit")

        transforms = _rel("t1", RelationshipType.TRANSFORMS, "recipe1", "schema1")
        rule_rel = _rel("rr1", RelationshipType.HAS_RULE, "recipe1", "rule1")
        dr = _rel("dr1", RelationshipType.DEBITS, "rule1", "ds1")
        cr = _rel("cr1", RelationshipType.CREDITS, "rule1", "cs1")

        pattern = GraphPattern(
            nodes=[recipe, schema, rule, debit_slot, credit_slot],
            relationships=[transforms, rule_rel, dr, cr],
        )
        result = validate_recipe(pattern)
        assert result.is_valid is True
        assert len(result.warnings) > 0
        assert any("MAPPED_TO" in w for w in result.warnings)


# ============================================================================
# extract_measures_for_schema
# ============================================================================

class TestExtractMeasuresForSchema:
    def test_extracts_connected_measures(self):
        schema = _schema_node()
        m1 = _measure_node("m1", "total")
        m2 = _measure_node("m2", "count")
        m3 = _measure_node("m3", "other")  # not connected
        r1 = _rel("r1", RelationshipType.HAS_MEASURE, "schema1", "m1")
        r2 = _rel("r2", RelationshipType.HAS_MEASURE, "schema1", "m2")

        pattern = GraphPattern(
            nodes=[schema, m1, m2, m3],
            relationships=[r1, r2],
        )
        measures = extract_measures_for_schema(pattern, "schema1")
        assert len(measures) == 2
        measure_ids = {m.id for m in measures}
        assert "m1" in measure_ids
        assert "m2" in measure_ids
        assert "m3" not in measure_ids

    def test_returns_empty_for_no_connections(self):
        schema = _schema_node()
        m1 = _measure_node("m1", "total")
        pattern = GraphPattern(nodes=[schema, m1], relationships=[])
        measures = extract_measures_for_schema(pattern, "schema1")
        assert len(measures) == 0

    def test_returns_empty_for_unknown_schema(self):
        pattern = GraphPattern(nodes=[], relationships=[])
        measures = extract_measures_for_schema(pattern, "nonexistent")
        assert len(measures) == 0


# ============================================================================
# extract_debit_credit_slots
# ============================================================================

class TestExtractDebitCreditSlots:
    def test_extracts_slots_correctly(self):
        rule = _rule_node()
        ds = _slot_node("ds1", "receivable", "debit")
        cs = _slot_node("cs1", "revenue", "credit")
        dr = _rel("dr1", RelationshipType.DEBITS, "rule1", "ds1")
        cr = _rel("cr1", RelationshipType.CREDITS, "rule1", "cs1")

        pattern = GraphPattern(
            nodes=[rule, ds, cs],
            relationships=[dr, cr],
        )
        debit_slots, credit_slots = extract_debit_credit_slots(pattern, "rule1")
        assert len(debit_slots) == 1
        assert debit_slots[0].id == "ds1"
        assert len(credit_slots) == 1
        assert credit_slots[0].id == "cs1"

    def test_multiple_debit_slots(self):
        rule = _rule_node()
        ds1 = _slot_node("ds1", "receivable", "debit")
        ds2 = _slot_node("ds2", "expense", "debit")
        cs = _slot_node("cs1", "revenue", "credit")
        dr1 = _rel("dr1", RelationshipType.DEBITS, "rule1", "ds1")
        dr2 = _rel("dr2", RelationshipType.DEBITS, "rule1", "ds2")
        cr = _rel("cr1", RelationshipType.CREDITS, "rule1", "cs1")

        pattern = GraphPattern(
            nodes=[rule, ds1, ds2, cs],
            relationships=[dr1, dr2, cr],
        )
        debit_slots, credit_slots = extract_debit_credit_slots(pattern, "rule1")
        assert len(debit_slots) == 2
        assert len(credit_slots) == 1

    def test_returns_empty_for_no_connections(self):
        rule = _rule_node()
        pattern = GraphPattern(nodes=[rule], relationships=[])
        debit_slots, credit_slots = extract_debit_credit_slots(pattern, "rule1")
        assert len(debit_slots) == 0
        assert len(credit_slots) == 0

    def test_returns_empty_for_unknown_rule(self):
        pattern = GraphPattern(nodes=[], relationships=[])
        debit_slots, credit_slots = extract_debit_credit_slots(pattern, "nonexistent")
        assert len(debit_slots) == 0
        assert len(credit_slots) == 0
