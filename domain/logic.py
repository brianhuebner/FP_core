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
    validate_entry_structure_references_column,
    validate_mapping_rule_completeness,
    validate_measure_references_column,
    validate_output_column_positions_unique,
    validate_output_format_has_columns,
    validate_recipe_has_schema,
    validate_slot_has_mapping,
    validate_uses_reference,
)


def build_source_schema_pattern(
    schema_node: Node,
    column_nodes: List[Node],
    measure_nodes: List[Node],
    column_rels: List[Relationship],
    measure_rels: List[Relationship],
    aggregates_rels: List[Relationship] | None = None,
) -> GraphPattern:
    """Construct a GraphPattern for a complete source schema subgraph.

    Includes: schema + columns + measures and all connecting
    relationships (HAS_COLUMN, HAS_MEASURE, AGGREGATES).
    """
    nodes = [schema_node] + column_nodes + measure_nodes
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
        validate_when_targets(pattern),
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


def extract_conditions_for_rule(
    pattern: GraphPattern,
    rule_node_id: str,
) -> Tuple[Node, ...]:
    """Extract Condition nodes connected to a MappingRule via WHEN."""
    condition_ids = {
        rel.end_node_id
        for rel in pattern.relationships
        if rel.type == RelationshipType.WHEN and rel.start_node_id == rule_node_id
    }
    return tuple(
        n for n in pattern.nodes
        if n.id in condition_ids and NodeLabel.CONDITION in n.labels
    )


def build_output_format_pattern(
    format_node: Node,
    column_nodes: List[Node],
    column_rels: List[Relationship],
    validation_nodes: List[Node] | None = None,
    validation_rels: List[Relationship] | None = None,
    entry_structure_node: Node | None = None,
    entry_structure_rel: Relationship | None = None,
) -> GraphPattern:
    """Construct a GraphPattern for a complete output format subgraph.

    Includes: format + output columns + optional validation rules + optional
    entry structure and all connecting relationships.
    """
    nodes: List[Node] = [format_node] + column_nodes
    relationships = list(column_rels)
    if validation_nodes:
        nodes.extend(validation_nodes)
    if validation_rels:
        relationships.extend(validation_rels)
    if entry_structure_node is not None:
        nodes.append(entry_structure_node)
    if entry_structure_rel is not None:
        relationships.append(entry_structure_rel)
    return GraphPattern(nodes=nodes, relationships=relationships)


def extract_output_columns(
    pattern: GraphPattern,
    format_node_id: str,
) -> Tuple[Node, ...]:
    """Extract OutputColumn nodes connected to an OutputFormat via HAS_COLUMN."""
    column_ids = {
        rel.end_node_id
        for rel in pattern.relationships
        if (
            rel.type == RelationshipType.HAS_COLUMN
            and rel.start_node_id == format_node_id
        )
    }
    return tuple(
        n for n in pattern.nodes
        if n.id in column_ids and NodeLabel.OUTPUT_COLUMN in n.labels
    )


def extract_validation_rules(
    pattern: GraphPattern,
    format_node_id: str,
) -> Tuple[Node, ...]:
    """Extract ValidationRule nodes connected to an OutputFormat via HAS_VALIDATION."""
    rule_ids = {
        rel.end_node_id
        for rel in pattern.relationships
        if (
            rel.type == RelationshipType.HAS_VALIDATION
            and rel.start_node_id == format_node_id
        )
    }
    return tuple(
        n for n in pattern.nodes
        if n.id in rule_ids and NodeLabel.VALIDATION_RULE in n.labels
    )


def extract_entry_structure(
    pattern: GraphPattern,
    format_node_id: str,
) -> Node | None:
    """Extract the EntryStructure node connected to an OutputFormat via HAS_ENTRY_STRUCTURE.

    Returns a single node or None (one-to-one relationship).
    """
    entry_ids = {
        rel.end_node_id
        for rel in pattern.relationships
        if (
            rel.type == RelationshipType.HAS_ENTRY_STRUCTURE
            and rel.start_node_id == format_node_id
        )
    }
    for n in pattern.nodes:
        if n.id in entry_ids and NodeLabel.ENTRY_STRUCTURE in n.labels:
            return n
    return None


def validate_output_format(pattern: GraphPattern) -> ValidationResult:
    """Orchestrate all output format validators against a GraphPattern."""
    return ValidationResult.merge(
        validate_output_format_has_columns(pattern),
        validate_output_column_positions_unique(pattern),
        validate_entry_structure_references_column(pattern),
    )


def compose_pipeline_pattern(
    schema_pattern: GraphPattern,
    recipe_pattern: GraphPattern,
    output_pattern: GraphPattern | None = None,
) -> GraphPattern:
    """Concatenate nodes and relationships from all input patterns into one GraphPattern.

    Output pattern is optional — a pipeline can be valid without an output format.
    """
    nodes = list(schema_pattern.nodes) + list(recipe_pattern.nodes)
    relationships = list(schema_pattern.relationships) + list(recipe_pattern.relationships)
    if output_pattern is not None:
        nodes.extend(output_pattern.nodes)
        relationships.extend(output_pattern.relationships)
    return GraphPattern(nodes=nodes, relationships=relationships)


def validate_pipeline_connectivity(pattern: GraphPattern) -> ValidationResult:
    """Verify every AccountingRecipe's TRANSFORMS target node exists in the pattern.

    Ensures the subgraphs are actually wired together, not just concatenated.
    """
    node_ids = {n.id for n in pattern.nodes}
    errors: list[str] = []

    for rel in pattern.relationships:
        if rel.type == RelationshipType.TRANSFORMS:
            if rel.end_node_id not in node_ids:
                errors.append(
                    f"TRANSFORMS target '{rel.end_node_id}' from recipe "
                    f"'{rel.start_node_id}' not found in pattern"
                )

    if errors:
        return ValidationResult.failure(tuple(errors))
    return ValidationResult.success()


def validate_when_targets(pattern: GraphPattern) -> ValidationResult:
    """Verify every WHEN relationship's target node exists in the pattern."""
    node_ids = {n.id for n in pattern.nodes}
    errors: list[str] = []
    for rel in pattern.relationships:
        if rel.type == RelationshipType.WHEN:
            if rel.end_node_id not in node_ids:
                errors.append(
                    f"WHEN target '{rel.end_node_id}' from rule "
                    f"'{rel.start_node_id}' not found in pattern"
                )
    if errors:
        return ValidationResult.failure(tuple(errors))
    return ValidationResult.success()
