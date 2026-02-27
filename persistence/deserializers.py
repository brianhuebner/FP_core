# persistence/deserializers.py — Pure functions: Neo4j records -> domain objects
from __future__ import annotations

from typing import Any

from domain.types import (
    GraphPattern,
    Node,
    NodeLabel,
    Relationship,
    RelationshipType,
)

NODE_ID_KEY = "_node_id"


# Pre-compute reverse lookup: label value string -> NodeLabel enum
_LABEL_VALUE_MAP: dict[str, NodeLabel] = {label.value: label for label in NodeLabel}

# Pre-compute reverse lookup: rel type string -> RelationshipType enum
_REL_TYPE_MAP: dict[str, RelationshipType] = {rt.value: rt for rt in RelationshipType}


def deserialize_node(
    labels: list[str],
    properties: dict[str, Any],
) -> Node:
    """Convert Neo4j node labels + properties to a domain Node.

    - Label strings matching NodeLabel enum values go to Node.labels
    - Unknown label strings go to Node.extra_labels
    - _node_id property is popped and used as Node.id
    """
    props = dict(properties)  # defensive copy: pop(_node_id) below would mutate caller's dict
    node_id = str(props.pop(NODE_ID_KEY, ""))

    node_labels: set[NodeLabel] = set()
    extra_labels: set[str] = set()

    for label_str in labels:
        enum_val = _LABEL_VALUE_MAP.get(label_str)
        if enum_val is not None:
            node_labels.add(enum_val)
        else:
            extra_labels.add(label_str)

    return Node(
        id=node_id,
        labels=node_labels,
        properties=props,
        extra_labels=frozenset(extra_labels),
    )


def deserialize_relationship(
    rel_type: str,
    start_id: str,
    end_id: str,
    properties: dict[str, Any] | None = None,
) -> Relationship:
    """Convert Neo4j relationship data to a domain Relationship.

    Generates Relationship.id from f"{start_id}_{rel_type}_{end_id}".
    """
    rel_enum = _REL_TYPE_MAP.get(rel_type)
    if rel_enum is None:
        raise ValueError(f"Unknown relationship type: {rel_type}")

    rel_id = f"{start_id}_{rel_type}_{end_id}"

    return Relationship(
        id=rel_id,
        type=rel_enum,
        start_node_id=start_id,
        end_node_id=end_id,
        properties=dict(properties) if properties else {},
    )


def deserialize_pattern(
    node_records: list[dict[str, Any]],
    rel_records: list[dict[str, Any]],
) -> GraphPattern:
    """Assemble a GraphPattern from lists of node and relationship records.

    Expected node_record format:
        {"labels": ["SourceSchema"], "properties": {"_node_id": "...", ...}}

    Expected rel_record format:
        {"type": "HAS_COLUMN", "start_id": "...", "end_id": "...",
         "properties": {...}}

    Deduplicates nodes by _node_id. Silently skips relationships with
    unknown types (not in RelationshipType enum).
    """
    seen_ids: set[str] = set()
    nodes: list[Node] = []

    for record in node_records:
        node = deserialize_node(
            labels=record["labels"],
            properties=record["properties"],
        )
        if node.id not in seen_ids:
            seen_ids.add(node.id)
            nodes.append(node)

    relationships: list[Relationship] = []
    seen_rel_ids: set[str] = set()

    for record in rel_records:
        rel_type_str = record["type"]
        if rel_type_str not in _REL_TYPE_MAP:
            continue
        rel = deserialize_relationship(
            rel_type=rel_type_str,
            start_id=record["start_id"],
            end_id=record["end_id"],
            properties=record.get("properties", {}),
        )
        if rel.id not in seen_rel_ids:
            seen_rel_ids.add(rel.id)
            relationships.append(rel)

    return GraphPattern(nodes=nodes, relationships=relationships)
