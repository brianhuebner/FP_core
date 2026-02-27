# tests/persistence/test_deserializers.py — Verify record->domain conversion (pure, no driver)
import pytest

from domain.types import (
    GraphPattern,
    Node,
    NodeLabel,
    Relationship,
    RelationshipType,
)
from persistence.deserializers import (
    deserialize_node,
    deserialize_pattern,
    deserialize_relationship,
)

# ============================================================================
# deserialize_node
# ============================================================================


class TestDeserializeNode:
    def test_basic_node(self):
        node = deserialize_node(
            labels=["SourceSchema"],
            properties={
                "_node_id": "schema1",
                "recipe_id": "r1",
                "name": "Stripe Charges",
                "source_system": "stripe",
            },
        )

        assert node.id == "schema1"
        assert NodeLabel.SOURCE_SCHEMA in node.labels
        assert node.properties["recipe_id"] == "r1"
        assert node.properties["name"] == "Stripe Charges"
        assert "_node_id" not in node.properties

    def test_multiple_known_labels(self):
        node = deserialize_node(
            labels=["Account", "Entity"],
            properties={"_node_id": "x1"},
        )

        assert NodeLabel.ACCOUNT in node.labels
        assert NodeLabel.ENTITY in node.labels

    def test_unknown_labels_go_to_extra_labels(self):
        node = deserialize_node(
            labels=["Reference", "ChartOfAccounts"],
            properties={"_node_id": "ref1"},
        )

        assert NodeLabel.REFERENCE in node.labels
        assert "ChartOfAccounts" in node.extra_labels

    def test_all_unknown_labels(self):
        node = deserialize_node(
            labels=["CustomType", "AnotherType"],
            properties={"_node_id": "c1"},
        )

        assert len(node.labels) == 0
        assert "CustomType" in node.extra_labels
        assert "AnotherType" in node.extra_labels

    def test_missing_node_id_gives_empty_string(self):
        node = deserialize_node(
            labels=["Account"],
            properties={"code": "1200"},
        )

        assert node.id == ""

    def test_empty_properties(self):
        node = deserialize_node(
            labels=["Account"],
            properties={"_node_id": "a1"},
        )

        assert node.id == "a1"
        assert node.properties == {}

    def test_does_not_mutate_input(self):
        props = {"_node_id": "a1", "code": "1200"}
        original_keys = set(props.keys())
        deserialize_node(labels=["Account"], properties=props)
        assert set(props.keys()) == original_keys


# ============================================================================
# deserialize_relationship
# ============================================================================


class TestDeserializeRelationship:
    def test_basic_relationship(self):
        rel = deserialize_relationship(
            rel_type="HAS_COLUMN",
            start_id="schema1",
            end_id="col1",
        )

        assert rel.type == RelationshipType.HAS_COLUMN
        assert rel.start_node_id == "schema1"
        assert rel.end_node_id == "col1"
        assert rel.id == "schema1_HAS_COLUMN_col1"
        assert rel.properties == {}

    def test_with_properties(self):
        rel = deserialize_relationship(
            rel_type="MAPPED_TO",
            start_id="slot1",
            end_id="acct1",
            properties={"profile_id": "company1"},
        )

        assert rel.properties == {"profile_id": "company1"}

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown relationship type"):
            deserialize_relationship(
                rel_type="NONEXISTENT",
                start_id="a",
                end_id="b",
            )

    def test_id_format(self):
        rel = deserialize_relationship(
            rel_type="TRANSFORMS",
            start_id="recipe1",
            end_id="schema1",
        )

        assert rel.id == "recipe1_TRANSFORMS_schema1"

    def test_none_properties_gives_empty_dict(self):
        rel = deserialize_relationship(
            rel_type="HAS_COLUMN",
            start_id="a",
            end_id="b",
            properties=None,
        )
        assert rel.properties == {}


# ============================================================================
# deserialize_pattern
# ============================================================================


class TestDeserializePattern:
    def test_basic_pattern(self):
        node_records = [
            {
                "labels": ["SourceSchema"],
                "properties": {
                    "_node_id": "schema1",
                    "recipe_id": "r1",
                    "name": "Stripe",
                    "source_system": "stripe",
                },
            },
            {
                "labels": ["Column"],
                "properties": {
                    "_node_id": "col1",
                    "recipe_id": "r1",
                    "name": "amount",
                    "position": 0,
                    "data_type": "decimal",
                    "role": "amount",
                },
            },
        ]
        rel_records = [
            {
                "type": "HAS_COLUMN",
                "start_id": "schema1",
                "end_id": "col1",
                "properties": {},
            },
        ]

        pattern = deserialize_pattern(node_records, rel_records)

        assert isinstance(pattern, GraphPattern)
        assert len(pattern.nodes) == 2
        assert len(pattern.relationships) == 1
        assert pattern.nodes[0].id == "schema1"
        assert pattern.relationships[0].type == RelationshipType.HAS_COLUMN

    def test_deduplicates_nodes(self):
        record = {
            "labels": ["Account"],
            "properties": {"_node_id": "a1", "code": "1200"},
        }
        pattern = deserialize_pattern([record, record], [])

        assert len(pattern.nodes) == 1

    def test_deduplicates_relationships(self):
        node_records = [
            {"labels": ["Account"], "properties": {"_node_id": "a1"}},
        ]
        rel_record = {
            "type": "HAS_COLUMN",
            "start_id": "a1",
            "end_id": "b1",
            "properties": {},
        }
        pattern = deserialize_pattern(node_records, [rel_record, rel_record])

        assert len(pattern.relationships) == 1

    def test_empty_records(self):
        pattern = deserialize_pattern([], [])
        assert len(pattern.nodes) == 0
        assert len(pattern.relationships) == 0

    def test_extra_labels_preserved(self):
        node_records = [
            {
                "labels": ["Reference", "TaxCode"],
                "properties": {"_node_id": "ref1"},
            },
        ]
        pattern = deserialize_pattern(node_records, [])

        assert len(pattern.nodes) == 1
        assert NodeLabel.REFERENCE in pattern.nodes[0].labels
        assert "TaxCode" in pattern.nodes[0].extra_labels


# ============================================================================
# Round-trip: serialize -> deserialize fidelity
# ============================================================================


class TestSerializeDeserializeRoundTrip:
    def test_node_round_trip(self):
        """Verify that a node's key data survives serialize -> deserialize."""
        original = Node(
            id="schema1",
            labels={NodeLabel.SOURCE_SCHEMA},
            properties={
                "recipe_id": "r1",
                "name": "Stripe",
                "source_system": "stripe",
            },
        )

        # Simulate what Neo4j would return after a serialize + query
        reconstructed = deserialize_node(
            labels=["SourceSchema"],
            properties={
                "_node_id": "schema1",
                "recipe_id": "r1",
                "name": "Stripe",
                "source_system": "stripe",
            },
        )

        assert reconstructed.id == original.id
        assert reconstructed.labels == original.labels
        assert reconstructed.properties == original.properties

    def test_relationship_round_trip(self):
        original_rel = Relationship(
            id="schema1_HAS_COLUMN_col1",
            type=RelationshipType.HAS_COLUMN,
            start_node_id="schema1",
            end_node_id="col1",
            properties={},
        )

        reconstructed = deserialize_relationship(
            rel_type="HAS_COLUMN",
            start_id="schema1",
            end_id="col1",
        )

        assert reconstructed.id == original_rel.id
        assert reconstructed.type == original_rel.type
        assert reconstructed.start_node_id == original_rel.start_node_id
        assert reconstructed.end_node_id == original_rel.end_node_id
