# domain/logic.py — Layer 3: Pure domain logic (no I/O)
from __future__ import annotations

from typing import List, Tuple

from domain.types import (
    GraphPattern,
    Node,
    NodeLabel,
    Relationship,
    RelationshipType,
)
from domain.ontology import ValidationResult
from domain.ontology_recipe import (
    validate_mapping_rule_completeness,
    validate_measure_references_column,
    validate_recipe_has_schema,
    validate_slot_has_mapping,
    validate_uses_reference,
)


def build_source_schema_pattern(
    schema_node: Node,
    column_nodes: List[Node],
    measure_nodes: List[Node],
    condition_nodes: List[Node],
    column_rels: List[Relationship],
    measure_rels: List[Relationship],
    aggregates_rels: List[Relationship] | None = None,
) -> GraphPattern:
    """Construct a GraphPattern for a complete source schema subgraph.

    Includes: schema + columns + measures + conditions and all connecting
    relationships (HAS_COLUMN, HAS_MEASURE, AGGREGATES).
    """
    nodes = [schema_node] + column_nodes + measure_nodes + condition_nodes
    relationships = list(column_rels) + list(measure_rels)
    if aggregates_rels:
        relationships.extend(aggregates_rels)
    return GraphPattern(nodes=nodes, relationships=relationships)


def build_recipe_pattern(
    recipe_node: Node,
    schema_node: Node,
    transforms_rel: Relationship,
    rule_nodes: List[Node],
    rule_rels: List[Relationship],
    slot_nodes: List[Node],
    slot_rels: List[Relationship],
    additional_nodes: List[Node] | None = None,
    additional_rels: List[Relationship] | None = None,
) -> GraphPattern:
    """Construct a GraphPattern for a complete accounting recipe subgraph.

    Includes: recipe + schema + mapping rules + account slots + all
    connecting relationships.
    """
    nodes = [recipe_node, schema_node] + rule_nodes + slot_nodes
    if additional_nodes:
        nodes.extend(additional_nodes)
    relationships = [transforms_rel] + rule_rels + slot_rels
    if additional_rels:
        relationships.extend(additional_rels)
    return GraphPattern(nodes=nodes, relationships=relationships)


def validate_recipe(pattern: GraphPattern) -> ValidationResult:
    """Orchestrate all recipe validators against a GraphPattern.

    Runs: validate_recipe_has_schema, validate_mapping_rule_completeness,
    validate_measure_references_column, validate_slot_has_mapping (soft),
    validate_uses_reference.
    """
    return ValidationResult.merge(
        validate_recipe_has_schema(pattern),
        validate_mapping_rule_completeness(pattern),
        validate_measure_references_column(pattern),
        validate_slot_has_mapping(pattern),
        validate_uses_reference(pattern),
    )


def extract_measures_for_schema(
    pattern: GraphPattern,
    schema_node_id: str,
) -> Tuple[Node, ...]:
    """Extract Measure nodes connected to a SourceSchema via HAS_MEASURE."""
    measure_ids = {
        rel.end_node_id
        for rel in pattern.relationships
        if (
            rel.type == RelationshipType.HAS_MEASURE
            and rel.start_node_id == schema_node_id
        )
    }
    return tuple(
        n for n in pattern.nodes
        if n.id in measure_ids and NodeLabel.MEASURE in n.labels
    )


def extract_debit_credit_slots(
    pattern: GraphPattern,
    rule_node_id: str,
) -> Tuple[Tuple[Node, ...], Tuple[Node, ...]]:
    """Extract (debit_slots, credit_slots) AccountSlot nodes for a MappingRule.

    Returns a tuple of (debit_slots, credit_slots).
    """
    debit_ids = {
        rel.end_node_id
        for rel in pattern.relationships
        if (
            rel.type == RelationshipType.DEBITS
            and rel.start_node_id == rule_node_id
        )
    }
    credit_ids = {
        rel.end_node_id
        for rel in pattern.relationships
        if (
            rel.type == RelationshipType.CREDITS
            and rel.start_node_id == rule_node_id
        )
    }

    node_map = {n.id: n for n in pattern.nodes}

    debit_slots = tuple(
        node_map[nid] for nid in sorted(debit_ids)
        if nid in node_map and NodeLabel.ACCOUNT_SLOT in node_map[nid].labels
    )
    credit_slots = tuple(
        node_map[nid] for nid in sorted(credit_ids)
        if nid in node_map and NodeLabel.ACCOUNT_SLOT in node_map[nid].labels
    )

    return (debit_slots, credit_slots)
