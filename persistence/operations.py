# persistence/operations.py — High-level save/load/delete operations
from __future__ import annotations

from typing import Any, Dict, List

from domain.types import GraphPattern
from persistence.connection import Neo4jConnection
from persistence.deserializers import deserialize_pattern
from persistence.serializers import serialize_pattern


def save_pattern(
    conn: Neo4jConnection,
    pattern: GraphPattern,
) -> List[Dict[str, int]]:
    """Serialize a GraphPattern and write all statements to Neo4j.

    Returns a list of counter dicts (one per statement).
    No pre-validation — caller decides when to validate.
    """
    statements = serialize_pattern(pattern)
    results: List[Dict[str, int]] = []
    for cypher, params in statements:
        result = conn.run_write(cypher, params)
        results.append(result)
    return results


def load_pattern_by_recipe(
    conn: Neo4jConnection,
    recipe_id: str,
) -> GraphPattern:
    """Load all nodes and relationships for a recipe from Neo4j.

    Queries nodes where recipe_id matches, plus one hop
    outward for cross-layer nodes (e.g. Account via MAPPED_TO).
    """
    # Find all recipe-scoped nodes
    node_query = """
    MATCH (n)
    WHERE n.recipe_id = $id
    RETURN labels(n) AS labels, properties(n) AS properties
    """
    node_records = conn.run_query(node_query, {"id": recipe_id})

    # Also find nodes one hop away (e.g. Account nodes via MAPPED_TO)
    hop_query = """
    MATCH (n)-[r]-(m)
    WHERE n.recipe_id = $id
      AND NOT coalesce(m.recipe_id, '') = $id
    RETURN DISTINCT labels(m) AS labels, properties(m) AS properties
    """
    hop_records = conn.run_query(hop_query, {"id": recipe_id})
    all_node_records = node_records + hop_records

    # Find all relationships between found nodes
    rel_query = """
    MATCH (n)-[r]->(m)
    WHERE (n.recipe_id = $id OR n._node_id IN $hop_ids)
      AND (m.recipe_id = $id OR m._node_id IN $hop_ids)
    RETURN type(r) AS type,
           n._node_id AS start_id,
           m._node_id AS end_id,
           properties(r) AS properties
    """
    # Collect hop node IDs for relationship query
    hop_ids: List[str] = []
    for record in hop_records:
        node_id = record.get("properties", {}).get("_node_id")
        if node_id:
            hop_ids.append(node_id)

    rel_records = conn.run_query(rel_query, {"id": recipe_id, "hop_ids": hop_ids})

    return deserialize_pattern(all_node_records, rel_records)


def load_format_by_id(
    conn: Neo4jConnection,
    format_id: str,
) -> GraphPattern:
    """Load all nodes and relationships for an output format from Neo4j.

    Queries OutputFormat + OutputColumn + ValidationRule + EntryStructure
    nodes where format_id matches.
    """
    node_query = """
    MATCH (n)
    WHERE n.format_id = $id
    RETURN labels(n) AS labels, properties(n) AS properties
    """
    node_records = conn.run_query(node_query, {"id": format_id})

    rel_query = """
    MATCH (n)-[r]->(m)
    WHERE n.format_id = $id AND m.format_id = $id
    RETURN type(r) AS type,
           n._node_id AS start_id,
           m._node_id AS end_id,
           properties(r) AS properties
    """
    rel_records = conn.run_query(rel_query, {"id": format_id})

    return deserialize_pattern(node_records, rel_records)


def delete_pattern_by_recipe(
    conn: Neo4jConnection,
    recipe_id: str,
) -> Dict[str, int]:
    """Delete all nodes (and their relationships) for a recipe."""
    query = """
    MATCH (n)
    WHERE n.recipe_id = $id
    DETACH DELETE n
    """
    return conn.run_write(query, {"id": recipe_id})


def delete_format_by_id(
    conn: Neo4jConnection,
    format_id: str,
) -> Dict[str, int]:
    """Delete all nodes (and their relationships) for an output format."""
    query = """
    MATCH (n)
    WHERE n.format_id = $id
    DETACH DELETE n
    """
    return conn.run_write(query, {"id": format_id})


def verify_pattern(
    conn: Neo4jConnection,
    recipe_id: str,
) -> Dict[str, int]:
    """Count nodes and relationships for a recipe (diagnostic)."""
    node_query = """
    MATCH (n)
    WHERE n.recipe_id = $id
    RETURN count(n) AS node_count
    """
    rel_query = """
    MATCH (n)-[r]->(m)
    WHERE n.recipe_id = $id AND m.recipe_id = $id
    RETURN count(r) AS rel_count
    """
    node_result = conn.run_query(node_query, {"id": recipe_id})
    rel_result = conn.run_query(rel_query, {"id": recipe_id})

    return {
        "nodes": node_result[0]["node_count"] if node_result else 0,
        "relationships": rel_result[0]["rel_count"] if rel_result else 0,
    }


def verify_format(
    conn: Neo4jConnection,
    format_id: str,
) -> Dict[str, int]:
    """Count nodes and relationships for an output format (diagnostic)."""
    node_query = """
    MATCH (n)
    WHERE n.format_id = $id
    RETURN count(n) AS node_count
    """
    rel_query = """
    MATCH (n)-[r]->(m)
    WHERE n.format_id = $id AND m.format_id = $id
    RETURN count(r) AS rel_count
    """
    node_result = conn.run_query(node_query, {"id": format_id})
    rel_result = conn.run_query(rel_query, {"id": format_id})

    return {
        "nodes": node_result[0]["node_count"] if node_result else 0,
        "relationships": rel_result[0]["rel_count"] if rel_result else 0,
    }
