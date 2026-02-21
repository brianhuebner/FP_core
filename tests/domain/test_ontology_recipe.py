# tests/domain/test_ontology_recipe.py — Tests for recipe ontology & validators
import pytest

from domain.types import (
    GraphPattern,
    Node,
    NodeLabel,
    Relationship,
    RelationshipType,
)
from domain.ontology import ValidationResult
from domain.ontology_recipe import (
    RECIPE_ONTOLOGY,
    RECIPE_RELATIONSHIP_CONSTRAINTS,
    REFERENCE_RELATIONSHIP_SOURCES,
    merged_ontology,
    merged_relationship_constraints,
    validate_entry_structure_references_column,
    validate_mapping_rule_completeness,
    validate_measure_references_column,
    validate_output_column_positions_unique,
    validate_output_format_has_columns,
    validate_recipe_has_schema,
    validate_slot_has_mapping,
    validate_uses_reference,
)


# ============================================================================
# Constraint map completeness
# ============================================================================

_EXPECTED_RECIPE_ONTOLOGY_COUNT = 12
_EXPECTED_RECIPE_CONSTRAINTS_COUNT = 14
_EXPECTED_MERGED_ONTOLOGY_COUNT = 19
_EXPECTED_MERGED_CONSTRAINTS_COUNT = 25


class TestRecipeConstraintMaps:
    def test_recipe_ontology_count(self):
        assert len(RECIPE_ONTOLOGY) == _EXPECTED_RECIPE_ONTOLOGY_COUNT

    def test_recipe_relationship_constraints_count(self):
        assert len(RECIPE_RELATIONSHIP_CONSTRAINTS) == _EXPECTED_RECIPE_CONSTRAINTS_COUNT

    def test_merged_ontology_count(self):
        assert len(merged_ontology()) == _EXPECTED_MERGED_ONTOLOGY_COUNT

    def test_merged_relationship_constraints_count(self):
        assert len(merged_relationship_constraints()) == _EXPECTED_MERGED_CONSTRAINTS_COUNT

    def test_recipe_ontology_labels(self):
        expected = {
            NodeLabel.SOURCE_SCHEMA, NodeLabel.COLUMN, NodeLabel.MEASURE,
            NodeLabel.CONDITION, NodeLabel.ACCOUNT_SLOT, NodeLabel.MAPPING_RULE,
            NodeLabel.ACCOUNTING_RECIPE, NodeLabel.OUTPUT_FORMAT,
            NodeLabel.OUTPUT_COLUMN, NodeLabel.VALIDATION_RULE,
            NodeLabel.ENTRY_STRUCTURE, NodeLabel.REFERENCE,
        }
        assert set(RECIPE_ONTOLOGY.keys()) == expected

    def test_merged_ontology_contains_all_core_labels(self):
        merged = merged_ontology()
        core_labels = {
            NodeLabel.ACCOUNT, NodeLabel.TRANSACTION,
            NodeLabel.TRANSACTION_LINE, NodeLabel.ENTITY,
            NodeLabel.ANALYTICAL_DIMENSION, NodeLabel.ALLOCATION_RULE,
            NodeLabel.DATA_SOURCE,
        }
        for label in core_labels:
            assert label in merged, f"{label.value} missing from merged_ontology"

    def test_merged_ontology_contains_all_recipe_labels(self):
        merged = merged_ontology()
        for label in RECIPE_ONTOLOGY:
            assert label in merged, f"{label.value} missing from merged_ontology"


# ============================================================================
# Schema detail tests
# ============================================================================

class TestRecipeSchemaDetails:
    def test_source_schema_required_properties(self):
        schema = RECIPE_ONTOLOGY[NodeLabel.SOURCE_SCHEMA]
        assert "recipe_id" in schema.properties.required
        assert "name" in schema.properties.required
        assert "source_system" in schema.properties.required

    def test_column_required_properties(self):
        schema = RECIPE_ONTOLOGY[NodeLabel.COLUMN]
        assert "recipe_id" in schema.properties.required
        assert "name" in schema.properties.required
        assert "position" in schema.properties.required
        assert "data_type" in schema.properties.required
        assert "role" in schema.properties.required

    def test_mapping_rule_required_properties(self):
        schema = RECIPE_ONTOLOGY[NodeLabel.MAPPING_RULE]
        assert "recipe_id" in schema.properties.required
        assert "rule_name" in schema.properties.required
        assert "source_measure" in schema.properties.required

    def test_accounting_recipe_has_outgoing_transforms(self):
        schema = RECIPE_ONTOLOGY[NodeLabel.ACCOUNTING_RECIPE]
        transforms_rels = [
            r for r in schema.outgoing_relationships
            if r.relationship_type == RelationshipType.TRANSFORMS
        ]
        assert len(transforms_rels) == 1
        assert NodeLabel.SOURCE_SCHEMA in transforms_rels[0].target_labels

    def test_accounting_recipe_has_outgoing_has_rule(self):
        schema = RECIPE_ONTOLOGY[NodeLabel.ACCOUNTING_RECIPE]
        rule_rels = [
            r for r in schema.outgoing_relationships
            if r.relationship_type == RelationshipType.HAS_RULE
        ]
        assert len(rule_rels) == 1
        assert NodeLabel.MAPPING_RULE in rule_rels[0].target_labels

    def test_source_schema_has_outgoing_has_column(self):
        schema = RECIPE_ONTOLOGY[NodeLabel.SOURCE_SCHEMA]
        col_rels = [
            r for r in schema.outgoing_relationships
            if r.relationship_type == RelationshipType.HAS_COLUMN
        ]
        assert len(col_rels) == 1
        assert NodeLabel.COLUMN in col_rels[0].target_labels

    def test_mapping_rule_has_outgoing_debits_and_credits(self):
        schema = RECIPE_ONTOLOGY[NodeLabel.MAPPING_RULE]
        debit_rels = [
            r for r in schema.outgoing_relationships
            if r.relationship_type == RelationshipType.DEBITS
        ]
        credit_rels = [
            r for r in schema.outgoing_relationships
            if r.relationship_type == RelationshipType.CREDITS
        ]
        assert len(debit_rels) == 1
        assert len(credit_rels) == 1
        assert NodeLabel.ACCOUNT_SLOT in debit_rels[0].target_labels
        assert NodeLabel.ACCOUNT_SLOT in credit_rels[0].target_labels

    def test_account_slot_has_outgoing_mapped_to(self):
        schema = RECIPE_ONTOLOGY[NodeLabel.ACCOUNT_SLOT]
        mapped_rels = [
            r for r in schema.outgoing_relationships
            if r.relationship_type == RelationshipType.MAPPED_TO
        ]
        assert len(mapped_rels) == 1
        assert NodeLabel.ACCOUNT in mapped_rels[0].target_labels


# ============================================================================
# Cross-layer relationship merging
# ============================================================================

class TestCrossLayerMerging:
    def test_account_incoming_includes_mapped_to(self):
        merged = merged_ontology()
        acct_schema = merged[NodeLabel.ACCOUNT]
        mapped_incoming = [
            r for r in acct_schema.incoming_relationships
            if r.relationship_type == RelationshipType.MAPPED_TO
        ]
        assert len(mapped_incoming) == 1
        assert NodeLabel.ACCOUNT_SLOT in mapped_incoming[0].source_labels

    def test_account_retains_core_incoming_relationships(self):
        merged = merged_ontology()
        acct_schema = merged[NodeLabel.ACCOUNT]
        posts_to = [
            r for r in acct_schema.incoming_relationships
            if r.relationship_type == RelationshipType.POSTS_TO
        ]
        assert len(posts_to) == 1

    def test_column_incoming_includes_aggregates(self):
        merged = merged_ontology()
        col_schema = merged[NodeLabel.COLUMN]
        agg_incoming = [
            r for r in col_schema.incoming_relationships
            if r.relationship_type == RelationshipType.AGGREGATES
        ]
        assert len(agg_incoming) == 1
        assert NodeLabel.MEASURE in agg_incoming[0].source_labels


# ============================================================================
# validate_recipe_has_schema
# ============================================================================

class TestValidateRecipeHasSchema:
    def test_recipe_with_transforms_valid(self):
        recipe = Node(
            id="recipe1", labels={NodeLabel.ACCOUNTING_RECIPE},
            properties={"recipe_id": "r1", "name": "Test", "source_schema": "s1"},
        )
        schema = Node(
            id="schema1", labels={NodeLabel.SOURCE_SCHEMA},
            properties={"recipe_id": "r1", "name": "Source", "source_system": "csv_import"},
        )
        rel = Relationship(
            id="rel1", type=RelationshipType.TRANSFORMS,
            start_node_id="recipe1", end_node_id="schema1", properties={},
        )
        pattern = GraphPattern(nodes=[recipe, schema], relationships=[rel])
        result = validate_recipe_has_schema(pattern)
        assert result.is_valid is True

    def test_recipe_without_transforms_fails(self):
        recipe = Node(
            id="recipe1", labels={NodeLabel.ACCOUNTING_RECIPE},
            properties={"recipe_id": "r1", "name": "Test", "source_schema": "s1"},
        )
        pattern = GraphPattern(nodes=[recipe], relationships=[])
        result = validate_recipe_has_schema(pattern)
        assert result.is_valid is False
        assert any("no TRANSFORMS" in e for e in result.errors)

    def test_no_recipe_nodes_succeeds(self):
        pattern = GraphPattern(nodes=[], relationships=[])
        result = validate_recipe_has_schema(pattern)
        assert result.is_valid is True


# ============================================================================
# validate_slot_has_mapping (soft warning)
# ============================================================================

class TestValidateSlotHasMapping:
    def test_slot_with_mapping_valid(self):
        slot = Node(
            id="slot1", labels={NodeLabel.ACCOUNT_SLOT},
            properties={"recipe_id": "r1", "slot_id": "s1", "role": "revenue", "entry_type": "credit"},
        )
        acct = Node(
            id="acct1", labels={NodeLabel.ACCOUNT},
            properties={"code": "4000", "name": "Revenue", "account_type": "revenue", "normal_balance": "credit"},
        )
        rel = Relationship(
            id="rel1", type=RelationshipType.MAPPED_TO,
            start_node_id="slot1", end_node_id="acct1", properties={},
        )
        pattern = GraphPattern(nodes=[slot, acct], relationships=[rel])
        result = validate_slot_has_mapping(pattern)
        assert result.is_valid is True
        assert result.warnings == ()

    def test_slot_without_mapping_warns(self):
        slot = Node(
            id="slot1", labels={NodeLabel.ACCOUNT_SLOT},
            properties={"recipe_id": "r1", "slot_id": "s1", "role": "revenue", "entry_type": "credit"},
        )
        pattern = GraphPattern(nodes=[slot], relationships=[])
        result = validate_slot_has_mapping(pattern)
        assert result.is_valid is True
        assert any("no MAPPED_TO" in w for w in result.warnings)

    def test_no_slots_succeeds(self):
        pattern = GraphPattern(nodes=[], relationships=[])
        result = validate_slot_has_mapping(pattern)
        assert result.is_valid is True


# ============================================================================
# validate_mapping_rule_completeness
# ============================================================================

class TestValidateMappingRuleCompleteness:
    def test_rule_with_debits_and_credits_valid(self):
        rule = Node(
            id="rule1", labels={NodeLabel.MAPPING_RULE},
            properties={"recipe_id": "r1", "rule_name": "charge", "source_measure": "total"},
        )
        debit_slot = Node(
            id="ds1", labels={NodeLabel.ACCOUNT_SLOT},
            properties={"recipe_id": "r1", "slot_id": "ds1", "role": "receivable", "entry_type": "debit"},
        )
        credit_slot = Node(
            id="cs1", labels={NodeLabel.ACCOUNT_SLOT},
            properties={"recipe_id": "r1", "slot_id": "cs1", "role": "revenue", "entry_type": "credit"},
        )
        dr = Relationship(
            id="r1", type=RelationshipType.DEBITS,
            start_node_id="rule1", end_node_id="ds1", properties={},
        )
        cr = Relationship(
            id="r2", type=RelationshipType.CREDITS,
            start_node_id="rule1", end_node_id="cs1", properties={},
        )
        pattern = GraphPattern(
            nodes=[rule, debit_slot, credit_slot],
            relationships=[dr, cr],
        )
        result = validate_mapping_rule_completeness(pattern)
        assert result.is_valid is True

    def test_rule_missing_credits_fails(self):
        rule = Node(
            id="rule1", labels={NodeLabel.MAPPING_RULE},
            properties={"recipe_id": "r1", "rule_name": "charge", "source_measure": "total"},
        )
        debit_slot = Node(
            id="ds1", labels={NodeLabel.ACCOUNT_SLOT},
            properties={"recipe_id": "r1", "slot_id": "ds1", "role": "receivable", "entry_type": "debit"},
        )
        dr = Relationship(
            id="r1", type=RelationshipType.DEBITS,
            start_node_id="rule1", end_node_id="ds1", properties={},
        )
        pattern = GraphPattern(nodes=[rule, debit_slot], relationships=[dr])
        result = validate_mapping_rule_completeness(pattern)
        assert result.is_valid is False
        assert any("CREDITS" in e for e in result.errors)

    def test_rule_missing_both_fails(self):
        rule = Node(
            id="rule1", labels={NodeLabel.MAPPING_RULE},
            properties={"recipe_id": "r1", "rule_name": "charge", "source_measure": "total"},
        )
        pattern = GraphPattern(nodes=[rule], relationships=[])
        result = validate_mapping_rule_completeness(pattern)
        assert result.is_valid is False
        assert any("DEBITS" in e for e in result.errors)
        assert any("CREDITS" in e for e in result.errors)

    def test_no_rules_succeeds(self):
        pattern = GraphPattern(nodes=[], relationships=[])
        result = validate_mapping_rule_completeness(pattern)
        assert result.is_valid is True


# ============================================================================
# validate_measure_references_column
# ============================================================================

class TestValidateMeasureReferencesColumn:
    def test_measure_with_aggregates_valid(self):
        measure = Node(
            id="m1", labels={NodeLabel.MEASURE},
            properties={"recipe_id": "r1", "name": "total", "operation": "sum"},
        )
        col = Node(
            id="c1", labels={NodeLabel.COLUMN},
            properties={"recipe_id": "r1", "name": "amount", "position": 0, "data_type": "decimal", "role": "amount"},
        )
        rel = Relationship(
            id="r1", type=RelationshipType.AGGREGATES,
            start_node_id="m1", end_node_id="c1", properties={},
        )
        pattern = GraphPattern(nodes=[measure, col], relationships=[rel])
        result = validate_measure_references_column(pattern)
        assert result.is_valid is True

    def test_measure_without_aggregates_fails(self):
        measure = Node(
            id="m1", labels={NodeLabel.MEASURE},
            properties={"recipe_id": "r1", "name": "total", "operation": "sum"},
        )
        pattern = GraphPattern(nodes=[measure], relationships=[])
        result = validate_measure_references_column(pattern)
        assert result.is_valid is False
        assert any("no AGGREGATES" in e for e in result.errors)

    def test_no_measures_succeeds(self):
        pattern = GraphPattern(nodes=[], relationships=[])
        result = validate_measure_references_column(pattern)
        assert result.is_valid is True


# ============================================================================
# validate_uses_reference
# ============================================================================

class TestValidateUsesReference:
    def test_valid_uses_reference_from_mapping_rule(self):
        rule = Node(
            id="rule1", labels={NodeLabel.MAPPING_RULE},
            properties={"recipe_id": "r1", "rule_name": "charge", "source_measure": "total"},
        )
        ref = Node(
            id="emp1", labels=set(), properties={"name": "John"},
            extra_labels=frozenset({"Employee"}),
        )
        rel = Relationship(
            id="r1", type=RelationshipType.USES_REFERENCE,
            start_node_id="rule1", end_node_id="emp1", properties={},
        )
        pattern = GraphPattern(nodes=[rule, ref], relationships=[rel])
        result = validate_uses_reference(pattern)
        assert result.is_valid is True

    def test_invalid_uses_reference_source(self):
        acct = Node(
            id="acct1", labels={NodeLabel.ACCOUNT},
            properties={"code": "1000", "name": "Cash", "account_type": "asset", "normal_balance": "debit"},
        )
        ref = Node(
            id="emp1", labels=set(), properties={"name": "John"},
            extra_labels=frozenset({"Employee"}),
        )
        rel = Relationship(
            id="r1", type=RelationshipType.USES_REFERENCE,
            start_node_id="acct1", end_node_id="emp1", properties={},
        )
        pattern = GraphPattern(nodes=[acct, ref], relationships=[rel])
        result = validate_uses_reference(pattern)
        assert result.is_valid is False
        assert any("may source USES_REFERENCE" in e for e in result.errors)

    def test_no_uses_reference_succeeds(self):
        pattern = GraphPattern(nodes=[], relationships=[])
        result = validate_uses_reference(pattern)
        assert result.is_valid is True

    def test_uses_reference_unknown_source_node(self):
        rel = Relationship(
            id="r1", type=RelationshipType.USES_REFERENCE,
            start_node_id="missing", end_node_id="emp1", properties={},
        )
        pattern = GraphPattern(nodes=[], relationships=[rel])
        result = validate_uses_reference(pattern)
        assert result.is_valid is False
        assert any("unknown source" in e for e in result.errors)


# ============================================================================
# HAS_COLUMN constraint fix verification
# ============================================================================

class TestHasColumnConstraintFix:
    def test_has_column_includes_output_format_pair(self):
        pairs = RECIPE_RELATIONSHIP_CONSTRAINTS[RelationshipType.HAS_COLUMN]
        assert (NodeLabel.OUTPUT_FORMAT, NodeLabel.OUTPUT_COLUMN) in pairs

    def test_output_format_has_outgoing_has_column(self):
        schema = RECIPE_ONTOLOGY[NodeLabel.OUTPUT_FORMAT]
        col_rels = [
            r for r in schema.outgoing_relationships
            if r.relationship_type == RelationshipType.HAS_COLUMN
        ]
        assert len(col_rels) == 1
        assert NodeLabel.OUTPUT_COLUMN in col_rels[0].target_labels

    def test_output_column_has_incoming_has_column(self):
        schema = RECIPE_ONTOLOGY[NodeLabel.OUTPUT_COLUMN]
        col_rels = [
            r for r in schema.incoming_relationships
            if r.relationship_type == RelationshipType.HAS_COLUMN
        ]
        assert len(col_rels) == 1
        assert NodeLabel.OUTPUT_FORMAT in col_rels[0].source_labels

    def test_merged_output_format_has_column(self):
        merged = merged_ontology()
        of = merged[NodeLabel.OUTPUT_FORMAT]
        col_rels = [
            r for r in of.outgoing_relationships
            if r.relationship_type == RelationshipType.HAS_COLUMN
        ]
        assert len(col_rels) == 1


# ============================================================================
# validate_output_format_has_columns
# ============================================================================

class TestValidateOutputFormatHasColumns:
    def test_format_with_columns_valid(self):
        fmt = Node(
            id="fmt1", labels={NodeLabel.OUTPUT_FORMAT},
            properties={"format_id": "f1", "name": "JE", "target_system": "sage", "file_format": "csv"},
        )
        col = Node(
            id="oc1", labels={NodeLabel.OUTPUT_COLUMN},
            properties={"format_id": "fmt1", "name": "date", "position": 0, "data_type": "date"},
        )
        rel = Relationship(
            id="r1", type=RelationshipType.HAS_COLUMN,
            start_node_id="fmt1", end_node_id="oc1", properties={},
        )
        pattern = GraphPattern(nodes=[fmt, col], relationships=[rel])
        result = validate_output_format_has_columns(pattern)
        assert result.is_valid is True

    def test_format_without_columns_fails(self):
        fmt = Node(
            id="fmt1", labels={NodeLabel.OUTPUT_FORMAT},
            properties={"format_id": "f1", "name": "JE", "target_system": "sage", "file_format": "csv"},
        )
        pattern = GraphPattern(nodes=[fmt], relationships=[])
        result = validate_output_format_has_columns(pattern)
        assert result.is_valid is False
        assert any("no HAS_COLUMN" in e for e in result.errors)

    def test_no_formats_succeeds(self):
        pattern = GraphPattern(nodes=[], relationships=[])
        result = validate_output_format_has_columns(pattern)
        assert result.is_valid is True


# ============================================================================
# validate_output_column_positions_unique
# ============================================================================

class TestValidateOutputColumnPositionsUnique:
    def test_unique_positions_valid(self):
        fmt = Node(
            id="fmt1", labels={NodeLabel.OUTPUT_FORMAT},
            properties={"format_id": "f1", "name": "JE", "target_system": "sage", "file_format": "csv"},
        )
        col1 = Node(
            id="oc1", labels={NodeLabel.OUTPUT_COLUMN},
            properties={"format_id": "fmt1", "name": "date", "position": 0, "data_type": "date"},
        )
        col2 = Node(
            id="oc2", labels={NodeLabel.OUTPUT_COLUMN},
            properties={"format_id": "fmt1", "name": "amount", "position": 1, "data_type": "decimal"},
        )
        r1 = Relationship(
            id="r1", type=RelationshipType.HAS_COLUMN,
            start_node_id="fmt1", end_node_id="oc1", properties={},
        )
        r2 = Relationship(
            id="r2", type=RelationshipType.HAS_COLUMN,
            start_node_id="fmt1", end_node_id="oc2", properties={},
        )
        pattern = GraphPattern(nodes=[fmt, col1, col2], relationships=[r1, r2])
        result = validate_output_column_positions_unique(pattern)
        assert result.is_valid is True

    def test_duplicate_positions_fails(self):
        fmt = Node(
            id="fmt1", labels={NodeLabel.OUTPUT_FORMAT},
            properties={"format_id": "f1", "name": "JE", "target_system": "sage", "file_format": "csv"},
        )
        col1 = Node(
            id="oc1", labels={NodeLabel.OUTPUT_COLUMN},
            properties={"format_id": "fmt1", "name": "date", "position": 0, "data_type": "date"},
        )
        col2 = Node(
            id="oc2", labels={NodeLabel.OUTPUT_COLUMN},
            properties={"format_id": "fmt1", "name": "amount", "position": 0, "data_type": "decimal"},
        )
        r1 = Relationship(
            id="r1", type=RelationshipType.HAS_COLUMN,
            start_node_id="fmt1", end_node_id="oc1", properties={},
        )
        r2 = Relationship(
            id="r2", type=RelationshipType.HAS_COLUMN,
            start_node_id="fmt1", end_node_id="oc2", properties={},
        )
        pattern = GraphPattern(nodes=[fmt, col1, col2], relationships=[r1, r2])
        result = validate_output_column_positions_unique(pattern)
        assert result.is_valid is False
        assert any("duplicate" in e for e in result.errors)

    def test_no_formats_succeeds(self):
        pattern = GraphPattern(nodes=[], relationships=[])
        result = validate_output_column_positions_unique(pattern)
        assert result.is_valid is True


# ============================================================================
# validate_entry_structure_references_column
# ============================================================================

class TestValidateEntryStructureReferencesColumn:
    def test_matching_columns_valid(self):
        fmt = Node(
            id="fmt1", labels={NodeLabel.OUTPUT_FORMAT},
            properties={"format_id": "f1", "name": "JE", "target_system": "sage", "file_format": "csv"},
        )
        col1 = Node(
            id="oc1", labels={NodeLabel.OUTPUT_COLUMN},
            properties={"format_id": "fmt1", "name": "entity", "position": 0, "data_type": "string"},
        )
        col2 = Node(
            id="oc2", labels={NodeLabel.OUTPUT_COLUMN},
            properties={"format_id": "fmt1", "name": "posting_date", "position": 1, "data_type": "date"},
        )
        entry = Node(
            id="e1", labels={NodeLabel.ENTRY_STRUCTURE},
            properties={
                "format_id": "f1", "entry_separator": "newline",
                "grouping_column": "entity", "date_column": "posting_date",
            },
        )
        cr1 = Relationship(id="cr1", type=RelationshipType.HAS_COLUMN, start_node_id="fmt1", end_node_id="oc1", properties={})
        cr2 = Relationship(id="cr2", type=RelationshipType.HAS_COLUMN, start_node_id="fmt1", end_node_id="oc2", properties={})
        er = Relationship(id="er1", type=RelationshipType.HAS_ENTRY_STRUCTURE, start_node_id="fmt1", end_node_id="e1", properties={})
        pattern = GraphPattern(nodes=[fmt, col1, col2, entry], relationships=[cr1, cr2, er])
        result = validate_entry_structure_references_column(pattern)
        assert result.is_valid is True
        assert result.warnings == ()

    def test_mismatched_grouping_column_warns(self):
        fmt = Node(
            id="fmt1", labels={NodeLabel.OUTPUT_FORMAT},
            properties={"format_id": "f1", "name": "JE", "target_system": "sage", "file_format": "csv"},
        )
        col1 = Node(
            id="oc1", labels={NodeLabel.OUTPUT_COLUMN},
            properties={"format_id": "fmt1", "name": "date", "position": 0, "data_type": "date"},
        )
        entry = Node(
            id="e1", labels={NodeLabel.ENTRY_STRUCTURE},
            properties={
                "format_id": "f1", "entry_separator": "newline",
                "grouping_column": "entity", "date_column": "date",
            },
        )
        cr1 = Relationship(id="cr1", type=RelationshipType.HAS_COLUMN, start_node_id="fmt1", end_node_id="oc1", properties={})
        er = Relationship(id="er1", type=RelationshipType.HAS_ENTRY_STRUCTURE, start_node_id="fmt1", end_node_id="e1", properties={})
        pattern = GraphPattern(nodes=[fmt, col1, entry], relationships=[cr1, er])
        result = validate_entry_structure_references_column(pattern)
        assert result.is_valid is True
        assert any("grouping_column" in w for w in result.warnings)

    def test_mismatched_date_column_warns(self):
        fmt = Node(
            id="fmt1", labels={NodeLabel.OUTPUT_FORMAT},
            properties={"format_id": "f1", "name": "JE", "target_system": "sage", "file_format": "csv"},
        )
        col1 = Node(
            id="oc1", labels={NodeLabel.OUTPUT_COLUMN},
            properties={"format_id": "fmt1", "name": "entity", "position": 0, "data_type": "string"},
        )
        entry = Node(
            id="e1", labels={NodeLabel.ENTRY_STRUCTURE},
            properties={
                "format_id": "f1", "entry_separator": "newline",
                "grouping_column": "entity", "date_column": "posting_date",
            },
        )
        cr1 = Relationship(id="cr1", type=RelationshipType.HAS_COLUMN, start_node_id="fmt1", end_node_id="oc1", properties={})
        er = Relationship(id="er1", type=RelationshipType.HAS_ENTRY_STRUCTURE, start_node_id="fmt1", end_node_id="e1", properties={})
        pattern = GraphPattern(nodes=[fmt, col1, entry], relationships=[cr1, er])
        result = validate_entry_structure_references_column(pattern)
        assert result.is_valid is True
        assert any("date_column" in w for w in result.warnings)

    def test_no_entry_structures_succeeds(self):
        pattern = GraphPattern(nodes=[], relationships=[])
        result = validate_entry_structure_references_column(pattern)
        assert result.is_valid is True
