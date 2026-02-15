# persistence/serializers.py — Pure functions: GraphPattern -> (cypher, params) tuples
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from domain.types import GraphPattern, Node, NodeLabel, Relationship
from persistence.merge_keys import MERGE_KEYS


def _label_string(node: Node) -> str:
    """Build Neo4j label string like ':SourceSchema:Column'."""
    labels = [label.value for label in sorted(node.labels, key=lambda l: l.value)]
    labels.extend(sorted(node.extra_labels))
    return ":" + ":".join(labels)


def serialize_node(
    node: Node,
    index: int = 0,
    merge_keys: Dict[NodeLabel, Tuple[str, ...]] = MERGE_KEYS,
) -> Tuple[str, Dict[str, Any]]:
    """Serialize a single Node to a MERGE Cypher statement with params.

    Returns (cypher_string, params_dict).
    """
    var = f"n{index}"
    label_str = _label_string(node)

    # Determine which label to look up merge keys for
    # Use the first NodeLabel found (most nodes have exactly one)
    merge_key_names: Tuple[str, ...] = ()
    for label in node.labels:
        if label in merge_keys:
            merge_key_names = merge_keys[label]
            break

    params: Dict[str, Any] = {}

    # For Reference nodes with no merge keys, use _node_id as the merge key
    if not merge_key_names:
        merge_props = f"{var}._node_id: ${var}__node_id"
        params[f"{var}__node_id"] = node.id
    else:
        merge_parts = []
        for key in merge_key_names:
            param_name = f"{var}_{key}"
            merge_parts.append(f"{var}.{key}: ${param_name}")
            params[param_name] = node.properties.get(key)
        merge_props = ", ".join(merge_parts)

    # SET clause: _node_id + all remaining properties
    set_parts: List[str] = []

    # Always store _node_id via SET (unless it's already in MERGE for Reference)
    if merge_key_names:
        set_parts.append(f"{var}._node_id = ${var}__node_id")
        params[f"{var}__node_id"] = node.id

    for key, value in node.properties.items():
        if key in merge_key_names:
            continue  # already in MERGE clause
        param_name = f"{var}_{key}"
        set_parts.append(f"{var}.{key} = ${param_name}")
        params[param_name] = value

    cypher = f"MERGE ({var}{label_str} {{{merge_props}}})"
    if set_parts:
        cypher += "\nSET " + ", ".join(set_parts)

    return cypher, params


def serialize_relationship(
    rel: Relationship,
    index: int = 0,
    node_map: Dict[str, Node] | None = None,
    node_index_map: Dict[str, int] | None = None,
    merge_keys: Dict[NodeLabel, Tuple[str, ...]] = MERGE_KEYS,
) -> Tuple[str, Dict[str, Any]]:
    """Serialize a Relationship to MATCH + MERGE Cypher.

    Requires node_map (id -> Node) and node_index_map (id -> index) to
    build MATCH clauses for the start/end nodes using their merge keys.
    """
    if node_map is None:
        node_map = {}
    if node_index_map is None:
        node_index_map = {}

    start_node = node_map.get(rel.start_node_id)
    end_node = node_map.get(rel.end_node_id)

    params: Dict[str, Any] = {}
    lines: List[str] = []

    # Build MATCH for start node
    start_var = f"s{index}"
    if start_node is not None:
        start_label_str = _label_string(start_node)
        start_match_props = _match_props_for_node(
            start_node, start_var, merge_keys, params
        )
        lines.append(f"MATCH ({start_var}{start_label_str} {{{start_match_props}}})")
    else:
        lines.append(f"MATCH ({start_var} {{_node_id: ${start_var}__node_id}})")
        params[f"{start_var}__node_id"] = rel.start_node_id

    # Build MATCH for end node
    end_var = f"e{index}"
    if end_node is not None:
        end_label_str = _label_string(end_node)
        end_match_props = _match_props_for_node(
            end_node, end_var, merge_keys, params
        )
        lines.append(f"MATCH ({end_var}{end_label_str} {{{end_match_props}}})")
    else:
        lines.append(f"MATCH ({end_var} {{_node_id: ${end_var}__node_id}})")
        params[f"{end_var}__node_id"] = rel.end_node_id

    # MERGE the relationship
    rel_type = rel.type.value
    rel_var = f"r{index}"

    if rel.properties:
        prop_parts = []
        for key, value in rel.properties.items():
            param_name = f"{rel_var}_{key}"
            prop_parts.append(f"{key}: ${param_name}")
            params[param_name] = value
        props_str = " {" + ", ".join(prop_parts) + "}"
        lines.append(
            f"MERGE ({start_var})-[{rel_var}:{rel_type}{props_str}]->({end_var})"
        )
    else:
        lines.append(
            f"MERGE ({start_var})-[{rel_var}:{rel_type}]->({end_var})"
        )

    return "\n".join(lines), params


def _match_props_for_node(
    node: Node,
    var: str,
    merge_keys: Dict[NodeLabel, Tuple[str, ...]],
    params: Dict[str, Any],
) -> str:
    """Build the property matching string for a MATCH clause."""
    merge_key_names: Tuple[str, ...] = ()
    for label in node.labels:
        if label in merge_keys:
            merge_key_names = merge_keys[label]
            break

    if not merge_key_names:
        # Reference-style: match by _node_id
        param_name = f"{var}__node_id"
        params[param_name] = node.id
        return f"{var}._node_id: ${param_name}"

    parts = []
    for key in merge_key_names:
        param_name = f"{var}_{key}"
        parts.append(f"{var}.{key}: ${param_name}")
        params[param_name] = node.properties.get(key)
    return ", ".join(parts)


def serialize_pattern(
    pattern: GraphPattern,
    merge_keys: Dict[NodeLabel, Tuple[str, ...]] = MERGE_KEYS,
) -> List[Tuple[str, Dict[str, Any]]]:
    """Serialize a full GraphPattern to a list of (cypher, params) statements.

    Returns node statements first, then relationship statements.
    One statement per node/relationship.
    """
    statements: List[Tuple[str, Dict[str, Any]]] = []

    # Build node index map for relationship serialization
    node_map: Dict[str, Node] = {}
    node_index_map: Dict[str, int] = {}
    for i, node in enumerate(pattern.nodes):
        node_map[node.id] = node
        node_index_map[node.id] = i
        statements.append(serialize_node(node, i, merge_keys))

    # Serialize relationships
    for j, rel in enumerate(pattern.relationships):
        statements.append(serialize_relationship(
            rel, j, node_map, node_index_map, merge_keys,
        ))

    return statements
