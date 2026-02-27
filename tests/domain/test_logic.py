# tests/domain/test_logic.py — Tests for Layer 3 pure domain logic

from domain.logic import (
    build_output_format_pattern,
    build_recipe_pattern,
    build_source_schema_pattern,
    compose_pipeline_pattern,
    extract_conditions_for_rule,
    extract_debit_credit_slots,
    extract_entry_structure,
    extract_measures_for_schema,
    extract_output_columns,
    extract_validation_rules,
    validate_output_format,
    validate_pipeline_connectivity,
    validate_recipe,
    validate_when_targets,
)
from domain.types import (
    GraphPattern,
    Node,
    NodeLabel,
    Relationship,
    RelationshipType,
)

# ============================================================================
# Helpers — reusable test fixtures
# ============================================================================


def _schema_node(node_id="schema1"):
    return Node(
        id=node_id,
        labels={NodeLabel.SOURCE_SCHEMA},
        properties={"recipe_id": "r1", "name": "Stripe Charges", "source_system": "stripe"},
    )


def _column_node(node_id="col1", name="amount"):
    return Node(
        id=node_id,
        labels={NodeLabel.COLUMN},
        properties={
            "recipe_id": "r1",
            "name": name,
            "position": 0,
            "data_type": "decimal",
            "role": "amount",
        },
    )


def _measure_node(node_id="m1", name="total_amount"):
    return Node(
        id=node_id,
        labels={NodeLabel.MEASURE},
        properties={"recipe_id": "r1", "name": name, "operation": "sum"},
    )


def _condition_node(node_id="cond1"):
    return Node(
        id=node_id,
        labels={NodeLabel.CONDITION},
        properties={
            "recipe_id": "r1",
            "condition_id": "c1",
            "column": "status",
            "operator": "equals",
            "value": "paid",
        },
    )


def _recipe_node(node_id="recipe1"):
    return Node(
        id=node_id,
        labels={NodeLabel.ACCOUNTING_RECIPE},
        properties={"recipe_id": "r1", "name": "Stripe Revenue", "source_schema": "stripe_charges"},
    )


def _rule_node(node_id="rule1"):
    return Node(
        id=node_id,
        labels={NodeLabel.MAPPING_RULE},
        properties={"recipe_id": "r1", "rule_name": "charge_rule", "source_measure": "total_amount"},
    )


def _slot_node(node_id="slot1", role="receivable", entry_type="debit"):
    return Node(
        id=node_id,
        labels={NodeLabel.ACCOUNT_SLOT},
        properties={
            "recipe_id": "r1",
            "slot_id": node_id,
            "role": role,
            "entry_type": entry_type,
        },
    )


def _rel(rel_id, rel_type, start, end):
    return Relationship(
        id=rel_id,
        type=rel_type,
        start_node_id=start,
        end_node_id=end,
        properties={},
    )


# ============================================================================
# build_source_schema_pattern
# ============================================================================


class TestBuildSourceSchemaPattern:
    def test_produces_valid_graph_pattern(self):
        schema = _schema_node()
        col = _column_node()
        measure = _measure_node()
        col_rel = _rel("r1", RelationshipType.HAS_COLUMN, "schema1", "col1")
        meas_rel = _rel("r2", RelationshipType.HAS_MEASURE, "schema1", "m1")
        agg_rel = _rel("r3", RelationshipType.AGGREGATES, "m1", "col1")

        pattern = build_source_schema_pattern(
            schema_node=schema,
            column_nodes=[col],
            measure_nodes=[measure],
            column_rels=[col_rel],
            measure_rels=[meas_rel],
            aggregates_rels=[agg_rel],
        )

        assert isinstance(pattern, GraphPattern)
        assert len(pattern.nodes) == 3
        assert len(pattern.relationships) == 3

    def test_without_aggregates(self):
        schema = _schema_node()
        col = _column_node()
        col_rel = _rel("r1", RelationshipType.HAS_COLUMN, "schema1", "col1")

        pattern = build_source_schema_pattern(
            schema_node=schema,
            column_nodes=[col],
            measure_nodes=[],
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


def _base_recipe_graph():
    """Build the common nodes and rels for a valid recipe graph.

    Returns (nodes, relationships) with: recipe, schema, rule, debit/credit slots,
    transforms, has_rule, debits, credits relationships.
    """
    recipe = _recipe_node()
    schema = _schema_node()
    rule = _rule_node()
    debit_slot = _slot_node("ds1", "receivable", "debit")
    credit_slot = _slot_node("cs1", "revenue", "credit")

    transforms = _rel("t1", RelationshipType.TRANSFORMS, "recipe1", "schema1")
    rule_rel = _rel("rr1", RelationshipType.HAS_RULE, "recipe1", "rule1")
    dr = _rel("dr1", RelationshipType.DEBITS, "rule1", "ds1")
    cr = _rel("cr1", RelationshipType.CREDITS, "rule1", "cs1")

    nodes = [recipe, schema, rule, debit_slot, credit_slot]
    rels = [transforms, rule_rel, dr, cr]
    return nodes, rels


class TestValidateRecipe:
    def test_valid_recipe_passes(self):
        nodes, rels = _base_recipe_graph()
        acct1 = Node(
            id="acct1",
            labels={NodeLabel.ACCOUNT},
            properties={"code": "1200", "name": "AR", "account_type": "asset", "normal_balance": "debit"},
        )
        acct2 = Node(
            id="acct2",
            labels={NodeLabel.ACCOUNT},
            properties={"code": "4000", "name": "Revenue", "account_type": "revenue", "normal_balance": "credit"},
        )
        mapped_dr = _rel("md1", RelationshipType.MAPPED_TO, "ds1", "acct1")
        mapped_cr = _rel("mc1", RelationshipType.MAPPED_TO, "cs1", "acct2")

        pattern = GraphPattern(
            nodes=nodes + [acct1, acct2],
            relationships=rels + [mapped_dr, mapped_cr],
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
        nodes, rels = _base_recipe_graph()
        pattern = GraphPattern(nodes=nodes, relationships=rels)
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


# ============================================================================
# Helpers — output format test fixtures
# ============================================================================


def _format_node(node_id="fmt1"):
    return Node(
        id=node_id,
        labels={NodeLabel.OUTPUT_FORMAT},
        properties={"format_id": "f1", "name": "JE Export", "target_system": "sage", "file_format": "csv"},
    )


def _output_column_node(node_id="oc1", name="date", position=0):
    return Node(
        id=node_id,
        labels={NodeLabel.OUTPUT_COLUMN},
        properties={"format_id": "fmt1", "name": name, "position": position, "data_type": "date"},
    )


def _validation_rule_node(node_id="vr1", name="balance_check"):
    return Node(
        id=node_id,
        labels={NodeLabel.VALIDATION_RULE},
        properties={"format_id": "fmt1", "name": name, "expression": "sum(debit) == sum(credit)", "scope": "batch"},
    )


def _entry_structure_node(node_id="es1"):
    return Node(
        id=node_id,
        labels={NodeLabel.ENTRY_STRUCTURE},
        properties={
            "format_id": "f1",
            "entry_separator": "newline",
            "grouping_column": "entity",
            "date_column": "posting_date",
        },
    )


# ============================================================================
# build_output_format_pattern
# ============================================================================


class TestBuildOutputFormatPattern:
    def test_produces_valid_graph_pattern(self):
        fmt = _format_node()
        col1 = _output_column_node("oc1", "date", 0)
        col2 = _output_column_node("oc2", "amount", 1)
        cr1 = _rel("cr1", RelationshipType.HAS_COLUMN, "fmt1", "oc1")
        cr2 = _rel("cr2", RelationshipType.HAS_COLUMN, "fmt1", "oc2")

        pattern = build_output_format_pattern(
            format_node=fmt,
            column_nodes=[col1, col2],
            column_rels=[cr1, cr2],
        )

        assert isinstance(pattern, GraphPattern)
        assert len(pattern.nodes) == 3
        assert len(pattern.relationships) == 2

    def test_with_validation_and_entry_structure(self):
        fmt = _format_node()
        col = _output_column_node()
        cr = _rel("cr1", RelationshipType.HAS_COLUMN, "fmt1", "oc1")
        vr = _validation_rule_node()
        vr_rel = _rel("vr1", RelationshipType.HAS_VALIDATION, "fmt1", "vr1")
        es = _entry_structure_node()
        es_rel = _rel("es1", RelationshipType.HAS_ENTRY_STRUCTURE, "fmt1", "es1")

        pattern = build_output_format_pattern(
            format_node=fmt,
            column_nodes=[col],
            column_rels=[cr],
            validation_nodes=[vr],
            validation_rels=[vr_rel],
            entry_structure_node=es,
            entry_structure_rel=es_rel,
        )

        assert len(pattern.nodes) == 4
        assert len(pattern.relationships) == 3

    def test_format_node_is_first(self):
        fmt = _format_node()
        col = _output_column_node()
        cr = _rel("cr1", RelationshipType.HAS_COLUMN, "fmt1", "oc1")

        pattern = build_output_format_pattern(
            format_node=fmt,
            column_nodes=[col],
            column_rels=[cr],
        )

        assert pattern.nodes[0].id == "fmt1"

    def test_without_optional_params(self):
        fmt = _format_node()
        col = _output_column_node()
        cr = _rel("cr1", RelationshipType.HAS_COLUMN, "fmt1", "oc1")

        pattern = build_output_format_pattern(
            format_node=fmt,
            column_nodes=[col],
            column_rels=[cr],
        )

        assert len(pattern.nodes) == 2
        assert len(pattern.relationships) == 1


# ============================================================================
# extract_output_columns
# ============================================================================


class TestExtractOutputColumns:
    def test_extracts_connected_columns(self):
        fmt = _format_node()
        col1 = _output_column_node("oc1", "date", 0)
        col2 = _output_column_node("oc2", "amount", 1)
        col3 = _output_column_node("oc3", "other", 2)  # not connected
        r1 = _rel("r1", RelationshipType.HAS_COLUMN, "fmt1", "oc1")
        r2 = _rel("r2", RelationshipType.HAS_COLUMN, "fmt1", "oc2")

        pattern = GraphPattern(
            nodes=[fmt, col1, col2, col3],
            relationships=[r1, r2],
        )
        columns = extract_output_columns(pattern, "fmt1")
        assert len(columns) == 2
        col_ids = {c.id for c in columns}
        assert "oc1" in col_ids
        assert "oc2" in col_ids
        assert "oc3" not in col_ids

    def test_returns_empty_for_no_connections(self):
        fmt = _format_node()
        col = _output_column_node()
        pattern = GraphPattern(nodes=[fmt, col], relationships=[])
        columns = extract_output_columns(pattern, "fmt1")
        assert len(columns) == 0

    def test_returns_empty_for_unknown_format(self):
        pattern = GraphPattern(nodes=[], relationships=[])
        columns = extract_output_columns(pattern, "nonexistent")
        assert len(columns) == 0


# ============================================================================
# extract_validation_rules
# ============================================================================


class TestExtractValidationRules:
    def test_extracts_connected_rules(self):
        fmt = _format_node()
        vr1 = _validation_rule_node("vr1", "balance_check")
        vr2 = _validation_rule_node("vr2", "date_check")
        r1 = _rel("r1", RelationshipType.HAS_VALIDATION, "fmt1", "vr1")
        r2 = _rel("r2", RelationshipType.HAS_VALIDATION, "fmt1", "vr2")

        pattern = GraphPattern(
            nodes=[fmt, vr1, vr2],
            relationships=[r1, r2],
        )
        rules = extract_validation_rules(pattern, "fmt1")
        assert len(rules) == 2

    def test_returns_empty_for_no_connections(self):
        fmt = _format_node()
        vr = _validation_rule_node()
        pattern = GraphPattern(nodes=[fmt, vr], relationships=[])
        rules = extract_validation_rules(pattern, "fmt1")
        assert len(rules) == 0

    def test_returns_empty_for_unknown_format(self):
        pattern = GraphPattern(nodes=[], relationships=[])
        rules = extract_validation_rules(pattern, "nonexistent")
        assert len(rules) == 0


# ============================================================================
# extract_entry_structure
# ============================================================================


class TestExtractEntryStructure:
    def test_extracts_connected_entry_structure(self):
        fmt = _format_node()
        es = _entry_structure_node()
        rel = _rel("er1", RelationshipType.HAS_ENTRY_STRUCTURE, "fmt1", "es1")

        pattern = GraphPattern(nodes=[fmt, es], relationships=[rel])
        result = extract_entry_structure(pattern, "fmt1")
        assert result is not None
        assert result.id == "es1"

    def test_returns_none_for_no_entry_structure(self):
        fmt = _format_node()
        pattern = GraphPattern(nodes=[fmt], relationships=[])
        result = extract_entry_structure(pattern, "fmt1")
        assert result is None

    def test_returns_none_for_unknown_format(self):
        pattern = GraphPattern(nodes=[], relationships=[])
        result = extract_entry_structure(pattern, "nonexistent")
        assert result is None


# ============================================================================
# validate_output_format
# ============================================================================


class TestValidateOutputFormat:
    def test_valid_output_format_passes(self):
        fmt = _format_node()
        col1 = _output_column_node("oc1", "entity", 0)
        col2 = _output_column_node("oc2", "posting_date", 1)
        cr1 = _rel("cr1", RelationshipType.HAS_COLUMN, "fmt1", "oc1")
        cr2 = _rel("cr2", RelationshipType.HAS_COLUMN, "fmt1", "oc2")
        es = _entry_structure_node()
        er = _rel("er1", RelationshipType.HAS_ENTRY_STRUCTURE, "fmt1", "es1")

        pattern = GraphPattern(
            nodes=[fmt, col1, col2, es],
            relationships=[cr1, cr2, er],
        )
        result = validate_output_format(pattern)
        assert result.is_valid is True

    def test_missing_columns_fails(self):
        fmt = _format_node()
        pattern = GraphPattern(nodes=[fmt], relationships=[])
        result = validate_output_format(pattern)
        assert result.is_valid is False
        assert any("no HAS_COLUMN" in e for e in result.errors)

    def test_duplicate_positions_fails(self):
        fmt = _format_node()
        col1 = _output_column_node("oc1", "date", 0)
        col2 = _output_column_node("oc2", "amount", 0)  # duplicate position
        cr1 = _rel("cr1", RelationshipType.HAS_COLUMN, "fmt1", "oc1")
        cr2 = _rel("cr2", RelationshipType.HAS_COLUMN, "fmt1", "oc2")

        pattern = GraphPattern(
            nodes=[fmt, col1, col2],
            relationships=[cr1, cr2],
        )
        result = validate_output_format(pattern)
        assert result.is_valid is False
        assert any("duplicate" in e for e in result.errors)

    def test_entry_structure_column_mismatch_warns(self):
        fmt = _format_node()
        col1 = _output_column_node("oc1", "date", 0)
        cr1 = _rel("cr1", RelationshipType.HAS_COLUMN, "fmt1", "oc1")
        es = _entry_structure_node()  # references "entity" and "posting_date", neither match "date"
        er = _rel("er1", RelationshipType.HAS_ENTRY_STRUCTURE, "fmt1", "es1")

        pattern = GraphPattern(
            nodes=[fmt, col1, es],
            relationships=[cr1, er],
        )
        result = validate_output_format(pattern)
        assert result.is_valid is True
        assert len(result.warnings) > 0


# ============================================================================
# compose_pipeline_pattern
# ============================================================================


class TestComposePipelinePattern:
    def test_two_patterns(self):
        schema = _schema_node()
        col = _column_node()
        cr = _rel("cr1", RelationshipType.HAS_COLUMN, "schema1", "col1")
        schema_pattern = GraphPattern(nodes=[schema, col], relationships=[cr])

        recipe = _recipe_node()
        transforms = _rel("t1", RelationshipType.TRANSFORMS, "recipe1", "schema1")
        recipe_pattern = GraphPattern(nodes=[recipe], relationships=[transforms])

        result = compose_pipeline_pattern(schema_pattern, recipe_pattern)
        assert len(result.nodes) == 3
        assert len(result.relationships) == 2

    def test_three_patterns(self):
        schema_pattern = GraphPattern(nodes=[_schema_node()], relationships=[])
        recipe_pattern = GraphPattern(nodes=[_recipe_node()], relationships=[])
        output_pattern = GraphPattern(nodes=[_format_node()], relationships=[])

        result = compose_pipeline_pattern(schema_pattern, recipe_pattern, output_pattern)
        assert len(result.nodes) == 3

    def test_output_optional(self):
        schema_pattern = GraphPattern(nodes=[_schema_node()], relationships=[])
        recipe_pattern = GraphPattern(nodes=[_recipe_node()], relationships=[])

        result = compose_pipeline_pattern(schema_pattern, recipe_pattern)
        assert len(result.nodes) == 2

    def test_preserves_all_relationships(self):
        r1 = _rel("r1", RelationshipType.HAS_COLUMN, "schema1", "col1")
        r2 = _rel("r2", RelationshipType.TRANSFORMS, "recipe1", "schema1")
        r3 = _rel("r3", RelationshipType.HAS_COLUMN, "fmt1", "oc1")

        schema_pattern = GraphPattern(nodes=[_schema_node()], relationships=[r1])
        recipe_pattern = GraphPattern(nodes=[_recipe_node()], relationships=[r2])
        output_pattern = GraphPattern(nodes=[_format_node()], relationships=[r3])

        result = compose_pipeline_pattern(schema_pattern, recipe_pattern, output_pattern)
        assert len(result.relationships) == 3


# ============================================================================
# validate_pipeline_connectivity
# ============================================================================


class TestValidatePipelineConnectivity:
    def test_connected_passes(self):
        schema = _schema_node()
        recipe = _recipe_node()
        transforms = _rel("t1", RelationshipType.TRANSFORMS, "recipe1", "schema1")

        pattern = GraphPattern(
            nodes=[schema, recipe],
            relationships=[transforms],
        )
        result = validate_pipeline_connectivity(pattern)
        assert result.is_valid is True

    def test_disconnected_fails(self):
        recipe = _recipe_node()
        transforms = _rel("t1", RelationshipType.TRANSFORMS, "recipe1", "schema1")
        # schema1 node is missing from pattern
        pattern = GraphPattern(
            nodes=[recipe],
            relationships=[transforms],
        )
        result = validate_pipeline_connectivity(pattern)
        assert result.is_valid is False
        assert any("not found" in e for e in result.errors)

    def test_no_transforms_passes(self):
        pattern = GraphPattern(nodes=[_schema_node()], relationships=[])
        result = validate_pipeline_connectivity(pattern)
        assert result.is_valid is True

    def test_multiple_recipes_one_disconnected(self):
        schema = _schema_node()
        recipe1 = _recipe_node("recipe1")
        recipe2 = Node(
            id="recipe2",
            labels={NodeLabel.ACCOUNTING_RECIPE},
            properties={"recipe_id": "r2", "name": "Other", "source_schema": "other_schema"},
        )
        t1 = _rel("t1", RelationshipType.TRANSFORMS, "recipe1", "schema1")
        t2 = _rel("t2", RelationshipType.TRANSFORMS, "recipe2", "schema2")
        # schema2 missing

        pattern = GraphPattern(
            nodes=[schema, recipe1, recipe2],
            relationships=[t1, t2],
        )
        result = validate_pipeline_connectivity(pattern)
        assert result.is_valid is False
        assert len(result.errors) == 1
        assert "schema2" in result.errors[0]


# ============================================================================
# extract_conditions_for_rule
# ============================================================================


class TestExtractConditionsForRule:
    def test_single_when_condition(self):
        rule = _rule_node("rule1")
        cond = _condition_node("cond1")
        when_rel = _rel("w1", RelationshipType.WHEN, "rule1", "cond1")

        pattern = GraphPattern(nodes=[rule, cond], relationships=[when_rel])
        result = extract_conditions_for_rule(pattern, "rule1")

        assert len(result) == 1
        assert result[0].id == "cond1"

    def test_multiple_when_conditions(self):
        rule = _rule_node("rule1")
        cond1 = _condition_node("cond1")
        cond2 = Node(
            id="cond2",
            labels={NodeLabel.CONDITION},
            properties={"recipe_id": "r1", "condition_id": "c2", "column": "type", "operator": "equals"},
        )
        w1 = _rel("w1", RelationshipType.WHEN, "rule1", "cond1")
        w2 = _rel("w2", RelationshipType.WHEN, "rule1", "cond2")

        pattern = GraphPattern(nodes=[rule, cond1, cond2], relationships=[w1, w2])
        result = extract_conditions_for_rule(pattern, "rule1")

        assert len(result) == 2
        cond_ids = {c.id for c in result}
        assert "cond1" in cond_ids
        assert "cond2" in cond_ids

    def test_no_when_conditions(self):
        rule = _rule_node("rule1")
        pattern = GraphPattern(nodes=[rule], relationships=[])
        result = extract_conditions_for_rule(pattern, "rule1")

        assert len(result) == 0

    def test_only_returns_for_specified_rule(self):
        rule1 = _rule_node("rule1")
        rule2 = Node(
            id="rule2",
            labels={NodeLabel.MAPPING_RULE},
            properties={"recipe_id": "r1", "rule_name": "other_rule", "source_measure": "m"},
        )
        cond1 = _condition_node("cond1")
        cond2 = Node(
            id="cond2",
            labels={NodeLabel.CONDITION},
            properties={"recipe_id": "r1", "condition_id": "c2", "column": "type", "operator": "equals"},
        )
        w1 = _rel("w1", RelationshipType.WHEN, "rule1", "cond1")
        w2 = _rel("w2", RelationshipType.WHEN, "rule2", "cond2")

        pattern = GraphPattern(nodes=[rule1, rule2, cond1, cond2], relationships=[w1, w2])
        result = extract_conditions_for_rule(pattern, "rule1")

        assert len(result) == 1
        assert result[0].id == "cond1"


# ============================================================================
# validate_when_targets
# ============================================================================


class TestValidateWhenTargets:
    def test_valid_when_targets(self):
        rule = _rule_node("rule1")
        cond = _condition_node("cond1")
        when_rel = _rel("w1", RelationshipType.WHEN, "rule1", "cond1")

        pattern = GraphPattern(nodes=[rule, cond], relationships=[when_rel])
        result = validate_when_targets(pattern)

        assert result.is_valid is True

    def test_dangling_when_target(self):
        rule = _rule_node("rule1")
        # cond1 node is absent from pattern
        when_rel = _rel("w1", RelationshipType.WHEN, "rule1", "cond1")

        pattern = GraphPattern(nodes=[rule], relationships=[when_rel])
        result = validate_when_targets(pattern)

        assert result.is_valid is False
        assert any("cond1" in e for e in result.errors)

    def test_no_when_rels_passes(self):
        rule = _rule_node("rule1")
        pattern = GraphPattern(nodes=[rule], relationships=[])
        result = validate_when_targets(pattern)

        assert result.is_valid is True
