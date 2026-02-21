# tests/domain/test_types_recipe.py — Tests for recipe domain types
import pytest

from domain.types import Node, NodeLabel, SourceType
from domain.types_recipe import (
    AccountingRecipe,
    AccountSlot,
    AggregationOp,
    Column,
    ColumnDataType,
    Condition,
    ConditionOp,
    MappingRule,
    Measure,
    OutputColumn,
    OutputFormat,
    SemanticRole,
    SourceSchema,
    TransformOp,
)


# ============================================================================
# Enum member counts
# ============================================================================

class TestRecipeEnumMemberCounts:
    def test_column_data_type_has_5_members(self):
        assert len(ColumnDataType) == 5

    def test_semantic_role_has_5_members(self):
        assert len(SemanticRole) == 5

    def test_aggregation_op_has_4_members(self):
        assert len(AggregationOp) == 4

    def test_condition_op_has_7_members(self):
        assert len(ConditionOp) == 7

    def test_transform_op_has_4_members(self):
        assert len(TransformOp) == 4


# ============================================================================
# Frozen dataclass checks
# ============================================================================

class TestRecipeFrozenDataclasses:
    @pytest.mark.parametrize("instance, attr, value", [
        (SourceSchema(recipe_id="r1", name="Stripe Charges", source_system=SourceType.STRIPE), "name", "changed"),
        (Column(recipe_id="r1", name="amount", position=0, data_type=ColumnDataType.DECIMAL, role=SemanticRole.AMOUNT), "position", 1),
        (Measure(recipe_id="r1", name="total_amount", operation=AggregationOp.SUM), "operation", AggregationOp.COUNT),
        (Condition(recipe_id="r1", condition_id="c1", column="status", operator=ConditionOp.EQUALS, value="paid"), "value", "refunded"),
        (AccountSlot(recipe_id="r1", slot_id="s1", role="revenue", entry_type="credit"), "role", "expense"),
        (MappingRule(recipe_id="r1", rule_name="charge_rule", source_measure="total_amount"), "rule_name", "changed"),
        (AccountingRecipe(recipe_id="r1", name="Stripe Revenue", source_schema="stripe_charges"), "name", "changed"),
        (OutputFormat(format_id="f1", name="QBO Import", target_system="quickbooks", file_format="iif"), "file_format", "csv"),
        (OutputColumn(format_id="f1", name="Account", position=0, data_type=ColumnDataType.STRING), "name", "changed"),
    ], ids=[
        "SourceSchema", "Column", "Measure", "Condition", "AccountSlot",
        "MappingRule", "AccountingRecipe", "OutputFormat", "OutputColumn",
    ])
    def test_frozen_dataclass_rejects_mutation(self, instance, attr, value):
        with pytest.raises(AttributeError):
            setattr(instance, attr, value)


# ============================================================================
# Default value tests
# ============================================================================

class TestRecipeDefaults:
    def test_source_schema_defaults(self):
        ss = SourceSchema(
            recipe_id="r1", name="Test",
            source_system=SourceType.CSV_IMPORT,
        )
        assert ss.file_pattern is None
        assert ss.row_grain is None

    def test_column_defaults(self):
        col = Column(
            recipe_id="r1", name="id", position=0,
            data_type=ColumnDataType.STRING, role=SemanticRole.IDENTIFIER,
        )
        assert col.required is True
        assert col.description is None

    def test_measure_defaults(self):
        m = Measure(
            recipe_id="r1", name="count",
            operation=AggregationOp.COUNT,
        )
        assert m.group_by == ()
        assert m.split_by is None
        assert m.split_column is None
        assert m.description is None

    def test_condition_defaults(self):
        c = Condition(
            recipe_id="r1", condition_id="c1",
            column="status", operator=ConditionOp.IS_NOT_NULL,
        )
        assert c.value is None

    def test_account_slot_defaults(self):
        s = AccountSlot(
            recipe_id="r1", slot_id="s1",
            role="revenue", entry_type="credit",
        )
        assert s.description is None

    def test_mapping_rule_defaults(self):
        mr = MappingRule(
            recipe_id="r1", rule_name="rule1",
            source_measure="total",
        )
        assert mr.condition_operator == ConditionOp.ALWAYS
        assert mr.condition_value is None
        assert mr.memo_template is None
        assert mr.priority == 0
        assert mr.split_by is None
        assert mr.sign_treatment is None

    def test_accounting_recipe_defaults(self):
        ar = AccountingRecipe(
            recipe_id="r1", name="Test",
            source_schema="schema1",
        )
        assert ar.batch_key is None
        assert ar.journal_no_format is None
        assert ar.entries_per_file is None
        assert ar.visibility == "private"

    def test_output_format_defaults(self):
        of = OutputFormat(
            format_id="f1", name="Export",
            target_system="csv", file_format="csv",
        )
        assert of.version is None

    def test_output_column_defaults(self):
        oc = OutputColumn(
            format_id="f1", name="Col1",
            position=0, data_type=ColumnDataType.STRING,
        )
        assert oc.required is True
        assert oc.description is None
        assert oc.source_mapping is None
        assert oc.sign_convention is None
        assert oc.format_pattern is None
        assert oc.exclude_from_output is False


# ============================================================================
# Node.extra_labels backward compatibility
# ============================================================================

class TestNodeExtraLabels:
    def test_node_default_extra_labels(self):
        node = Node(id="n1", labels={NodeLabel.ACCOUNT}, properties={})
        assert node.extra_labels == frozenset()

    def test_node_with_extra_labels(self):
        node = Node(
            id="n1", labels={NodeLabel.MAPPING_RULE}, properties={},
            extra_labels=frozenset({"Employee", "TimeclockEntry"}),
        )
        assert "Employee" in node.extra_labels
        assert "TimeclockEntry" in node.extra_labels

    def test_node_extra_labels_is_frozen(self):
        node = Node(
            id="n1", labels={NodeLabel.ACCOUNT}, properties={},
            extra_labels=frozenset({"Custom"}),
        )
        with pytest.raises(AttributeError):
            node.extra_labels = frozenset()

    def test_node_without_extra_labels_backward_compat(self):
        node = Node(id="n1", labels={NodeLabel.ACCOUNT}, properties={"code": "1000"})
        assert node.id == "n1"
        assert node.extra_labels == frozenset()
