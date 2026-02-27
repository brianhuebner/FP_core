# tests/persistence/test_operations.py — Integration tests (skipped without NEO4J_URI)
import uuid

from domain.types import (
    GraphPattern,
    Node,
    NodeLabel,
    Relationship,
    RelationshipType,
)

# Import skip marker from conftest
from tests.persistence.conftest import requires_neo4j

# ============================================================================
# Helpers — unique recipe_id per test to avoid collisions
# ============================================================================


def _unique_recipe_id() -> str:
    return f"test-{uuid.uuid4().hex[:8]}"


def _test_pattern(recipe_id: str) -> GraphPattern:
    """Build a small but complete pattern for integration testing."""
    schema = Node(
        id=f"{recipe_id}-schema",
        labels={NodeLabel.SOURCE_SCHEMA},
        properties={
            "recipe_id": recipe_id,
            "name": "Test Schema",
            "source_system": "manual",
        },
    )
    col = Node(
        id=f"{recipe_id}-col",
        labels={NodeLabel.COLUMN},
        properties={
            "recipe_id": recipe_id,
            "name": "amount",
            "position": 0,
            "data_type": "decimal",
            "role": "amount",
        },
    )
    rel = Relationship(
        id=f"{recipe_id}-r1",
        type=RelationshipType.HAS_COLUMN,
        start_node_id=f"{recipe_id}-schema",
        end_node_id=f"{recipe_id}-col",
        properties={},
    )
    return GraphPattern(nodes=[schema, col], relationships=[rel])


# ============================================================================
# Integration tests
# ============================================================================


@requires_neo4j
class TestSavePattern:
    def test_save_creates_nodes_and_relationships(self, neo4j_conn):
        from persistence.operations import delete_pattern_by_recipe, save_pattern

        recipe_id = _unique_recipe_id()
        pattern = _test_pattern(recipe_id)

        try:
            results = save_pattern(neo4j_conn, pattern)
            assert len(results) == 3  # 2 nodes + 1 relationship

            # At least one statement should create nodes
            total_nodes = sum(r["nodes_created"] for r in results)
            assert total_nodes >= 2
        finally:
            delete_pattern_by_recipe(neo4j_conn, recipe_id)


@requires_neo4j
class TestLoadPattern:
    def test_save_then_load_round_trip(self, neo4j_conn):
        from persistence.operations import (
            delete_pattern_by_recipe,
            load_pattern_by_recipe,
            save_pattern,
        )

        recipe_id = _unique_recipe_id()
        pattern = _test_pattern(recipe_id)

        try:
            save_pattern(neo4j_conn, pattern)
            loaded = load_pattern_by_recipe(neo4j_conn, recipe_id)

            assert len(loaded.nodes) >= 2
            assert len(loaded.relationships) >= 1

            # Verify node IDs round-tripped
            loaded_ids = {n.id for n in loaded.nodes}
            assert f"{recipe_id}-schema" in loaded_ids
            assert f"{recipe_id}-col" in loaded_ids
        finally:
            delete_pattern_by_recipe(neo4j_conn, recipe_id)


@requires_neo4j
class TestDeletePattern:
    def test_delete_removes_all(self, neo4j_conn):
        from persistence.operations import (
            delete_pattern_by_recipe,
            save_pattern,
            verify_pattern,
        )

        recipe_id = _unique_recipe_id()
        pattern = _test_pattern(recipe_id)

        save_pattern(neo4j_conn, pattern)
        delete_pattern_by_recipe(neo4j_conn, recipe_id)

        counts = verify_pattern(neo4j_conn, recipe_id)
        assert counts["nodes"] == 0
        assert counts["relationships"] == 0


@requires_neo4j
class TestIdempotentSave:
    def test_save_twice_no_duplicates(self, neo4j_conn):
        from persistence.operations import (
            delete_pattern_by_recipe,
            save_pattern,
            verify_pattern,
        )

        recipe_id = _unique_recipe_id()
        pattern = _test_pattern(recipe_id)

        try:
            save_pattern(neo4j_conn, pattern)
            counts_first = verify_pattern(neo4j_conn, recipe_id)

            save_pattern(neo4j_conn, pattern)
            counts_second = verify_pattern(neo4j_conn, recipe_id)

            assert counts_first == counts_second
        finally:
            delete_pattern_by_recipe(neo4j_conn, recipe_id)


@requires_neo4j
class TestListAvailable:
    def test_list_empty_graph(self, neo4j_conn):
        from persistence.operations import list_available

        result = list_available(neo4j_conn)
        assert "recipes" in result
        assert "formats" in result
        assert isinstance(result["recipes"], list)
        assert isinstance(result["formats"], list)

    def test_list_with_recipe(self, neo4j_conn):
        from persistence.operations import (
            delete_pattern_by_recipe,
            list_available,
            save_pattern,
        )

        recipe_id = _unique_recipe_id()
        # Build a pattern with a recipe node and a rule
        recipe_node = Node(
            id=f"{recipe_id}-recipe",
            labels={NodeLabel.ACCOUNTING_RECIPE},
            properties={
                "recipe_id": recipe_id,
                "name": "Test Recipe",
            },
        )
        rule_node = Node(
            id=f"{recipe_id}-rule1",
            labels={NodeLabel.MAPPING_RULE},
            properties={
                "recipe_id": recipe_id,
                "rule_name": "test_rule",
                "priority": 1,
                "memo_template": "Test",
            },
        )
        rule_rel = Relationship(
            id=f"{recipe_id}-has-rule",
            type=RelationshipType.HAS_RULE,
            start_node_id=f"{recipe_id}-recipe",
            end_node_id=f"{recipe_id}-rule1",
            properties={},
        )
        pattern = GraphPattern(
            nodes=[recipe_node, rule_node],
            relationships=[rule_rel],
        )

        try:
            save_pattern(neo4j_conn, pattern)
            result = list_available(neo4j_conn)

            matching = [r for r in result["recipes"] if r["recipe_id"] == recipe_id]
            assert len(matching) == 1
            assert matching[0]["name"] == "Test Recipe"
            assert matching[0]["rule_count"] == 1
        finally:
            delete_pattern_by_recipe(neo4j_conn, recipe_id)

    def test_list_with_format(self, neo4j_conn):
        from persistence.operations import (
            delete_format_by_id,
            list_available,
            save_pattern,
        )

        format_id = f"test-fmt-{uuid.uuid4().hex[:8]}"
        fmt_node = Node(
            id=f"{format_id}-fmt",
            labels={NodeLabel.OUTPUT_FORMAT},
            properties={
                "format_id": format_id,
                "name": "Test Format",
                "target_system": "test_system",
                "file_format": "csv",
            },
        )
        col_node = Node(
            id=f"{format_id}-col1",
            labels={NodeLabel.OUTPUT_COLUMN},
            properties={
                "format_id": format_id,
                "name": "date",
                "position": 1,
                "source_field": "date",
            },
        )
        col_rel = Relationship(
            id=f"{format_id}-has-col",
            type=RelationshipType.HAS_COLUMN,
            start_node_id=f"{format_id}-fmt",
            end_node_id=f"{format_id}-col1",
            properties={},
        )
        pattern = GraphPattern(
            nodes=[fmt_node, col_node],
            relationships=[col_rel],
        )

        try:
            save_pattern(neo4j_conn, pattern)
            result = list_available(neo4j_conn)

            matching = [f for f in result["formats"] if f["format_id"] == format_id]
            assert len(matching) == 1
            assert matching[0]["name"] == "Test Format"
            assert matching[0]["target_system"] == "test_system"
            assert matching[0]["column_count"] == 1
        finally:
            delete_format_by_id(neo4j_conn, format_id)

    def test_list_with_recipe_and_format(self, neo4j_conn):
        from persistence.operations import (
            delete_format_by_id,
            delete_pattern_by_recipe,
            list_available,
            save_pattern,
        )

        recipe_id = _unique_recipe_id()
        format_id = f"test-fmt-{uuid.uuid4().hex[:8]}"

        recipe_node = Node(
            id=f"{recipe_id}-recipe",
            labels={NodeLabel.ACCOUNTING_RECIPE},
            properties={
                "recipe_id": recipe_id,
                "name": "Both Test Recipe",
            },
        )
        fmt_node = Node(
            id=f"{format_id}-fmt",
            labels={NodeLabel.OUTPUT_FORMAT},
            properties={
                "format_id": format_id,
                "name": "Both Test Format",
                "target_system": "test_system",
                "file_format": "csv",
            },
        )

        try:
            save_pattern(
                neo4j_conn,
                GraphPattern(nodes=[recipe_node], relationships=[]),
            )
            save_pattern(
                neo4j_conn,
                GraphPattern(nodes=[fmt_node], relationships=[]),
            )
            result = list_available(neo4j_conn)

            recipe_match = [r for r in result["recipes"] if r["recipe_id"] == recipe_id]
            format_match = [f for f in result["formats"] if f["format_id"] == format_id]
            assert len(recipe_match) == 1
            assert len(format_match) == 1
        finally:
            delete_pattern_by_recipe(neo4j_conn, recipe_id)
            delete_format_by_id(neo4j_conn, format_id)


@requires_neo4j
class TestVerifyPattern:
    def test_verify_returns_counts(self, neo4j_conn):
        from persistence.operations import (
            delete_pattern_by_recipe,
            save_pattern,
            verify_pattern,
        )

        recipe_id = _unique_recipe_id()
        pattern = _test_pattern(recipe_id)

        try:
            save_pattern(neo4j_conn, pattern)
            counts = verify_pattern(neo4j_conn, recipe_id)

            assert counts["nodes"] == 2
            assert counts["relationships"] == 1
        finally:
            delete_pattern_by_recipe(neo4j_conn, recipe_id)
