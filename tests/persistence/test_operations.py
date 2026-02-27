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
