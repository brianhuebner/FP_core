# tests/persistence/test_serializers.py — Verify Cypher generation (pure, no driver)

from domain.types import (
    GraphPattern,
    Node,
    NodeLabel,
    Relationship,
    RelationshipType,
)
from persistence.serializers import (
    serialize_node,
    serialize_pattern,
    serialize_relationship,
)

# ============================================================================
# Helpers
# ============================================================================


def _schema_node(node_id="schema1"):
    return Node(
        id=node_id,
        labels={NodeLabel.SOURCE_SCHEMA},
        properties={"recipe_id": "r1", "name": "Stripe Charges", "source_system": "stripe"},
    )


def _column_node(node_id="col1"):
    return Node(
        id=node_id,
        labels={NodeLabel.COLUMN},
        properties={
            "recipe_id": "r1",
            "name": "amount",
            "position": 0,
            "data_type": "decimal",
            "role": "amount",
        },
    )


def _account_node(node_id="acct1"):
    return Node(
        id=node_id,
        labels={NodeLabel.ACCOUNT},
        properties={
            "code": "1200",
            "name": "AR",
            "account_type": "asset",
            "normal_balance": "debit",
        },
    )


def _reference_node(node_id="ref1"):
    return Node(
        id=node_id,
        labels={NodeLabel.REFERENCE},
        properties={},
        extra_labels=frozenset({"ChartOfAccounts"}),
    )


def _rel(rel_id, rel_type, start, end, props=None):
    return Relationship(
        id=rel_id,
        type=rel_type,
        start_node_id=start,
        end_node_id=end,
        properties=props or {},
    )


# ============================================================================
# serialize_node
# ============================================================================


class TestSerializeNode:
    def test_basic_node_cypher_shape(self):
        node = _schema_node()
        cypher, params = serialize_node(node, index=0)

        assert "MERGE" in cypher
        assert ":SourceSchema" in cypher
        assert "recipe_id: $n0_recipe_id" in cypher
        assert "name: $n0_name" in cypher
        assert params["n0_recipe_id"] == "r1"
        assert params["n0_name"] == "Stripe Charges"

    def test_node_id_stored_via_set(self):
        node = _schema_node()
        cypher, params = serialize_node(node, index=0)

        assert "SET" in cypher
        assert "n0._node_id = $n0__node_id" in cypher
        assert params["n0__node_id"] == "schema1"

    def test_remaining_props_in_set(self):
        node = _schema_node()
        cypher, params = serialize_node(node, index=0)

        assert "n0.source_system = $n0_source_system" in cypher
        assert params["n0_source_system"] == "stripe"

    def test_merge_keys_not_in_set(self):
        node = _schema_node()
        cypher, params = serialize_node(node, index=0)

        # recipe_id and name should be in MERGE, not duplicated in SET
        set_section = cypher.split("SET")[1] if "SET" in cypher else ""
        assert "n0.recipe_id =" not in set_section
        assert "n0.name =" not in set_section

    def test_different_index(self):
        node = _schema_node()
        cypher, params = serialize_node(node, index=5)

        assert "n5" in cypher
        assert "n5_recipe_id" in params

    def test_multi_label_node(self):
        node = Node(
            id="ref1",
            labels={NodeLabel.REFERENCE},
            properties={},
            extra_labels=frozenset({"ChartOfAccounts"}),
        )
        cypher, params = serialize_node(node, index=0)

        assert ":ChartOfAccounts" in cypher
        assert ":Reference" in cypher

    def test_reference_node_uses_node_id_in_merge(self):
        node = _reference_node()
        cypher, params = serialize_node(node, index=0)

        # Reference has empty merge keys, so _node_id goes in MERGE
        assert "_node_id: $n0__node_id" in cypher
        assert params["n0__node_id"] == "ref1"

    def test_account_node_single_key(self):
        node = _account_node()
        cypher, params = serialize_node(node, index=0)

        assert "code: $n0_code" in cypher
        assert params["n0_code"] == "1200"
        assert "n0._node_id = $n0__node_id" in cypher


# ============================================================================
# serialize_relationship
# ============================================================================


class TestSerializeRelationship:
    def test_basic_relationship_cypher(self):
        schema = _schema_node()
        col = _column_node()
        rel = _rel("r1", RelationshipType.HAS_COLUMN, "schema1", "col1")
        node_map = {"schema1": schema, "col1": col}
        node_index_map = {"schema1": 0, "col1": 1}

        cypher, params = serialize_relationship(
            rel,
            index=0,
            node_map=node_map,
            node_index_map=node_index_map,
        )

        assert "MATCH" in cypher
        assert "MERGE" in cypher
        assert ":HAS_COLUMN" in cypher

    def test_start_and_end_matched_by_merge_keys(self):
        schema = _schema_node()
        col = _column_node()
        rel = _rel("r1", RelationshipType.HAS_COLUMN, "schema1", "col1")
        node_map = {"schema1": schema, "col1": col}

        cypher, params = serialize_relationship(
            rel,
            index=0,
            node_map=node_map,
        )

        assert "s0_recipe_id" in params
        assert "e0_recipe_id" in params

    def test_relationship_with_properties(self):
        schema = _schema_node()
        col = _column_node()
        rel = _rel("r1", RelationshipType.HAS_COLUMN, "schema1", "col1", props={"weight": 1.0})
        node_map = {"schema1": schema, "col1": col}

        cypher, params = serialize_relationship(
            rel,
            index=0,
            node_map=node_map,
        )

        assert "weight" in cypher
        assert params["r0_weight"] == 1.0

    def test_unknown_node_falls_back_to_node_id(self):
        rel = _rel("r1", RelationshipType.HAS_COLUMN, "unknown1", "unknown2")

        cypher, params = serialize_relationship(rel, index=0)

        assert "_node_id" in cypher
        assert params["s0__node_id"] == "unknown1"
        assert params["e0__node_id"] == "unknown2"


# ============================================================================
# serialize_pattern
# ============================================================================


class TestSerializePattern:
    def test_nodes_before_relationships(self):
        schema = _schema_node()
        col = _column_node()
        rel = _rel("r1", RelationshipType.HAS_COLUMN, "schema1", "col1")
        pattern = GraphPattern(nodes=[schema, col], relationships=[rel])

        statements = serialize_pattern(pattern)

        # 2 node statements + 1 relationship statement
        assert len(statements) == 3
        # First two should be MERGE (nodes), last should contain MATCH (rel)
        assert "MERGE" in statements[0][0]
        assert "MERGE" in statements[1][0]
        assert "MATCH" in statements[2][0]

    def test_empty_pattern(self):
        pattern = GraphPattern(nodes=[], relationships=[])
        statements = serialize_pattern(pattern)
        assert statements == []

    def test_nodes_only_pattern(self):
        schema = _schema_node()
        pattern = GraphPattern(nodes=[schema], relationships=[])
        statements = serialize_pattern(pattern)
        assert len(statements) == 1

    def test_multiple_nodes_get_unique_indices(self):
        n1 = _schema_node("s1")
        n2 = _column_node("c1")
        n3 = _account_node("a1")
        pattern = GraphPattern(nodes=[n1, n2, n3], relationships=[])

        statements = serialize_pattern(pattern)

        assert len(statements) == 3
        # Verify different variable names used
        assert "n0" in statements[0][0]
        assert "n1" in statements[1][0]
        assert "n2" in statements[2][0]

    def test_full_pattern_round_trip_shapes(self):
        schema = _schema_node()
        col = _column_node()
        acct = _account_node()
        r1 = _rel("r1", RelationshipType.HAS_COLUMN, "schema1", "col1")
        r2 = _rel("r2", RelationshipType.POSTS_TO, "col1", "acct1")

        pattern = GraphPattern(
            nodes=[schema, col, acct],
            relationships=[r1, r2],
        )

        statements = serialize_pattern(pattern)
        assert len(statements) == 5  # 3 nodes + 2 rels

        # All node statements should use MERGE
        for i in range(3):
            assert statements[i][0].startswith("MERGE")

        # All rel statements should start with MATCH
        for i in range(3, 5):
            assert statements[i][0].startswith("MATCH")
