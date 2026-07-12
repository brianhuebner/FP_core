# persistence/serializers.py — Pure functions: GraphPattern -> (cypher, params) tuples
from __future__ import annotations

import re
from typing import Any

from domain.types import GraphPattern, Node, NodeLabel, Relationship
from persistence.merge_keys import MERGE_KEYS

NODE_ID_KEY = "_node_id"

# Neo4j cannot parameterize labels or property keys — they are interpolated as
# raw Cypher text. Any label/key that reaches serialization must be a plain
# identifier so a caller-supplied value (e.g. a Reference node's type or
# property keys, which the ontology treats as opaque) cannot inject Cypher.
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_identifier(name: str, kind: str) -> str:
    """Return name unchanged if it is a plain identifier; else raise.

    Guards every label and property key that is concatenated into a Cypher
    string. Values remain fully parameterized and are never checked here.
    """
    if not isinstance(name, str) or not _SAFE_IDENTIFIER.match(name):
        raise ValueError(
            f"Unsafe {kind} {name!r}: must match [A-Za-z_][A-Za-z0-9_]* "
            f"(labels and property keys cannot be parameterized in Cypher)."
        )
    return name


def _resolve_merge_keys(
    node: Node,
    merge_keys: dict[NodeLabel, tuple[str, ...]],
) -> tuple[str, ...]:
    """Look up merge key names for a node from its first matching label."""
    for label in node.labels:
        if label in merge_keys:
            return merge_keys[label]
    return ()


def _label_string(node: Node) -> str:
    """Build Neo4j label string like ':SourceSchema:Column'."""
    labels = [label.value for label in sorted(node.labels, key=lambda l: l.value)]
    labels.extend(sorted(node.extra_labels))
    return ":" + ":".join(_safe_identifier(label, "label") for label in labels)


def serialize_node(
    node: Node,
    index: int = 0,
    merge_keys: dict[NodeLabel, tuple[str, ...]] = MERGE_KEYS,
) -> tuple[str, dict[str, Any]]:
    """Serialize a single Node to a MERGE Cypher statement with params.

    Returns (cypher_string, params_dict).
    """
    var = f"n{index}"
    label_str = _label_string(node)

    merge_key_names = _resolve_merge_keys(node, merge_keys)

    params: dict[str, Any] = {}

    # For Reference nodes with no merge keys, use _node_id as the merge key
    if not merge_key_names:
        merge_props = f"{NODE_ID_KEY}: ${var}__node_id"
        params[f"{var}__node_id"] = node.id
    else:
        merge_parts = []
        for key in merge_key_names:
            param_name = f"{var}_{key}"
            merge_parts.append(f"{key}: ${param_name}")
            params[param_name] = node.properties.get(key)
        merge_props = ", ".join(merge_parts)

    # SET clause: _node_id + all remaining properties
    set_parts: list[str] = []

    # Always store _node_id via SET (unless it's already in MERGE for Reference)
    if merge_key_names:
        set_parts.append(f"{var}.{NODE_ID_KEY} = ${var}__node_id")
        params[f"{var}__node_id"] = node.id

    for key, value in node.properties.items():
        if key in merge_key_names:
            continue  # already in MERGE clause
        _safe_identifier(key, "property key")
        param_name = f"{var}_{key}"
        set_parts.append(f"{var}.{key} = ${param_name}")
        params[param_name] = value

    cypher = f"MERGE ({var}{label_str} {{{merge_props}}})"
    if set_parts:
        cypher += "\nSET " + ", ".join(set_parts)

    return cypher, params


def _build_node_match(
    node: Node | None,
    node_id: str,
    var: str,
    merge_keys: dict[NodeLabel, tuple[str, ...]],
    params: dict[str, Any],
) -> str:
    """Build a MATCH clause for a single node endpoint."""
    if node is not None:
        label_str = _label_string(node)
        match_props = _match_props_for_node(node, var, merge_keys, params)
        return f"MATCH ({var}{label_str} {{{match_props}}})"
    params[f"{var}__node_id"] = node_id
    return f"MATCH ({var} {{{NODE_ID_KEY}: ${var}__node_id}})"


def serialize_relationship(
    rel: Relationship,
    index: int = 0,
    node_map: dict[str, Node] | None = None,
    node_index_map: dict[str, int] | None = None,
    merge_keys: dict[NodeLabel, tuple[str, ...]] = MERGE_KEYS,
) -> tuple[str, dict[str, Any]]:
    """Serialize a Relationship to MATCH + MERGE Cypher.

    Requires node_map (id -> Node) and node_index_map (id -> index) to
    build MATCH clauses for the start/end nodes using their merge keys.
    """
    if node_map is None:
        node_map = {}
    if node_index_map is None:
        node_index_map = {}

    params: dict[str, Any] = {}
    lines: list[str] = []

    start_var = f"s{index}"
    end_var = f"e{index}"
    lines.append(
        _build_node_match(
            node_map.get(rel.start_node_id),
            rel.start_node_id,
            start_var,
            merge_keys,
            params,
        )
    )
    lines.append(
        _build_node_match(
            node_map.get(rel.end_node_id),
            rel.end_node_id,
            end_var,
            merge_keys,
            params,
        )
    )

    # MERGE the relationship
    rel_type = rel.type.value
    rel_var = f"r{index}"

    if rel.properties:
        prop_parts = []
        for key, value in rel.properties.items():
            _safe_identifier(key, "property key")
            param_name = f"{rel_var}_{key}"
            prop_parts.append(f"{key}: ${param_name}")
            params[param_name] = value
        props_str = " {" + ", ".join(prop_parts) + "}"
        lines.append(f"MERGE ({start_var})-[{rel_var}:{rel_type}{props_str}]->({end_var})")
    else:
        lines.append(f"MERGE ({start_var})-[{rel_var}:{rel_type}]->({end_var})")

    return "\n".join(lines), params


def _match_props_for_node(
    node: Node,
    var: str,
    merge_keys: dict[NodeLabel, tuple[str, ...]],
    params: dict[str, Any],
) -> str:
    """Build the property matching string for a MATCH clause."""
    merge_key_names = _resolve_merge_keys(node, merge_keys)

    if not merge_key_names:
        # Reference-style: match by _node_id
        param_name = f"{var}__node_id"
        params[param_name] = node.id
        return f"{NODE_ID_KEY}: ${param_name}"

    parts = []
    for key in merge_key_names:
        param_name = f"{var}_{key}"
        parts.append(f"{key}: ${param_name}")
        params[param_name] = node.properties.get(key)
    return ", ".join(parts)


def serialize_pattern(
    pattern: GraphPattern,
    merge_keys: dict[NodeLabel, tuple[str, ...]] = MERGE_KEYS,
) -> list[tuple[str, dict[str, Any]]]:
    """Serialize a full GraphPattern to a list of (cypher, params) statements.

    Returns node statements first, then relationship statements.
    One statement per node/relationship.
    """
    statements: list[tuple[str, dict[str, Any]]] = []

    # Build node index map for relationship serialization
    node_map: dict[str, Node] = {}
    node_index_map: dict[str, int] = {}
    for i, node in enumerate(pattern.nodes):
        node_map[node.id] = node
        node_index_map[node.id] = i
        statements.append(serialize_node(node, i, merge_keys))

    # Serialize relationships
    for j, rel in enumerate(pattern.relationships):
        statements.append(
            serialize_relationship(
                rel,
                j,
                node_map,
                node_index_map,
                merge_keys,
            )
        )

    return statements
