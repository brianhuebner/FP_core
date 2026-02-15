# domain/ontology_recipe.py — Recipe Ontology Schema, Constraints & Validators
from __future__ import annotations

from typing import Dict, FrozenSet, List, Tuple

from domain.types import (
    GraphPattern,
    Node,
    NodeLabel,
    Relationship,
    RelationshipType,
)
from domain.ontology import (
    ONTOLOGY,
    RELATIONSHIP_CONSTRAINTS,
    EntitySchema,
    PropertySchema,
    RelationshipConstraint,
    ValidationResult,
)


# ============================================================================
# RECIPE RELATIONSHIP CONSTRAINTS
# ============================================================================

# 14 entries — excludes only SYNCED_BY equivalent gaps (none remaining)
RECIPE_RELATIONSHIP_CONSTRAINTS: Dict[
    RelationshipType, Tuple[Tuple[NodeLabel, NodeLabel], ...]
] = {
    RelationshipType.HAS_COLUMN: (
        (NodeLabel.SOURCE_SCHEMA, NodeLabel.COLUMN),
    ),
    RelationshipType.HAS_MEASURE: (
        (NodeLabel.SOURCE_SCHEMA, NodeLabel.MEASURE),
    ),
    RelationshipType.AGGREGATES: (
        (NodeLabel.MEASURE, NodeLabel.COLUMN),
    ),
    RelationshipType.WHEN: (
        (NodeLabel.MAPPING_RULE, NodeLabel.CONDITION),
    ),
    RelationshipType.SPLIT_BY: (
        (NodeLabel.MAPPING_RULE, NodeLabel.COLUMN),
    ),
    RelationshipType.TRANSFORMS: (
        (NodeLabel.ACCOUNTING_RECIPE, NodeLabel.SOURCE_SCHEMA),
    ),
    RelationshipType.HAS_SLOT: (
        (NodeLabel.MAPPING_RULE, NodeLabel.ACCOUNT_SLOT),
    ),
    RelationshipType.HAS_RULE: (
        (NodeLabel.ACCOUNTING_RECIPE, NodeLabel.MAPPING_RULE),
    ),
    RelationshipType.MAPPED_TO: (
        (NodeLabel.ACCOUNT_SLOT, NodeLabel.ACCOUNT),
    ),
    RelationshipType.DEBITS: (
        (NodeLabel.MAPPING_RULE, NodeLabel.ACCOUNT_SLOT),
    ),
    RelationshipType.CREDITS: (
        (NodeLabel.MAPPING_RULE, NodeLabel.ACCOUNT_SLOT),
    ),
    RelationshipType.HAS_VALIDATION: (
        (NodeLabel.OUTPUT_FORMAT, NodeLabel.VALIDATION_RULE),
    ),
    RelationshipType.HAS_BATCH_FORMAT: (
        (NodeLabel.OUTPUT_FORMAT, NodeLabel.BATCH_FORMAT),
    ),
    RelationshipType.USES_REFERENCE: (
        (NodeLabel.MAPPING_RULE, NodeLabel.REFERENCE),
        (NodeLabel.CONDITION, NodeLabel.REFERENCE),
        (NodeLabel.ACCOUNTING_RECIPE, NodeLabel.REFERENCE),
    ),
}


# ============================================================================
# PROPERTY SCHEMAS — One per recipe node type
# ============================================================================

_SOURCE_SCHEMA_PROPS = PropertySchema(
    required=frozenset({"recipe_id", "name", "source_system"}),
    optional=frozenset({"file_pattern", "row_grain"}),
    types={
        "recipe_id": str,
        "name": str,
        "source_system": str,
        "file_pattern": str,
        "row_grain": str,
    },
)

_COLUMN_PROPS = PropertySchema(
    required=frozenset({"recipe_id", "name", "position", "data_type", "role"}),
    optional=frozenset({"required", "description"}),
    types={
        "recipe_id": str,
        "name": str,
        "position": int,
        "data_type": str,
        "role": str,
        "required": bool,
        "description": str,
    },
)

_MEASURE_PROPS = PropertySchema(
    required=frozenset({"recipe_id", "name", "operation"}),
    optional=frozenset({"group_by", "split_by", "split_column", "description"}),
    types={
        "recipe_id": str,
        "name": str,
        "operation": str,
        "group_by": str,
        "split_by": str,
        "split_column": str,
        "description": str,
    },
)

_CONDITION_PROPS = PropertySchema(
    required=frozenset({"recipe_id", "condition_id", "column", "operator"}),
    optional=frozenset({"value"}),
    types={
        "recipe_id": str,
        "condition_id": str,
        "column": str,
        "operator": str,
        "value": str,
    },
)

_ACCOUNT_SLOT_PROPS = PropertySchema(
    required=frozenset({"recipe_id", "slot_id", "role", "entry_type"}),
    optional=frozenset({"description"}),
    types={
        "recipe_id": str,
        "slot_id": str,
        "role": str,
        "entry_type": str,
        "description": str,
    },
)

_MAPPING_RULE_PROPS = PropertySchema(
    required=frozenset({"recipe_id", "rule_name", "source_measure"}),
    optional=frozenset({
        "condition_operator", "condition_value", "memo_template",
        "priority", "split_by", "sign_treatment",
    }),
    types={
        "recipe_id": str,
        "rule_name": str,
        "source_measure": str,
        "condition_operator": str,
        "condition_value": str,
        "memo_template": str,
        "priority": int,
        "split_by": str,
        "sign_treatment": str,
    },
)

_ACCOUNTING_RECIPE_PROPS = PropertySchema(
    required=frozenset({"recipe_id", "name", "source_schema"}),
    optional=frozenset({
        "batch_key", "journal_no_format", "entries_per_file", "visibility",
    }),
    types={
        "recipe_id": str,
        "name": str,
        "source_schema": str,
        "batch_key": str,
        "journal_no_format": str,
        "entries_per_file": int,
        "visibility": str,
    },
)

_OUTPUT_FORMAT_PROPS = PropertySchema(
    required=frozenset({"recipe_id", "name", "target_system", "file_format"}),
    optional=frozenset({"version"}),
    types={
        "recipe_id": str,
        "name": str,
        "target_system": str,
        "file_format": str,
        "version": str,
    },
)

_VALIDATION_RULE_PROPS = PropertySchema(
    required=frozenset({"format_id", "name", "expression", "scope"}),
    optional=frozenset({"description"}),
    types={
        "format_id": str,
        "name": str,
        "expression": str,
        "scope": str,
        "description": str,
    },
)

_BATCH_FORMAT_PROPS = PropertySchema(
    required=frozenset({"recipe_id", "entry_separator", "grouping_column", "date_column"}),
    optional=frozenset({"validation", "description"}),
    types={
        "recipe_id": str,
        "entry_separator": str,
        "grouping_column": str,
        "date_column": str,
        "validation": str,
        "description": str,
    },
)

_REFERENCE_PROPS = PropertySchema(
    required=frozenset(),
    optional=frozenset(),
    types={},
)

_OUTPUT_COLUMN_PROPS = PropertySchema(
    required=frozenset({"format_id", "name", "position", "data_type"}),
    optional=frozenset({
        "required", "description", "source_mapping",
        "sign_convention", "format_pattern", "exclude_from_output",
    }),
    types={
        "format_id": str,
        "name": str,
        "position": int,
        "data_type": str,
        "required": bool,
        "description": str,
        "source_mapping": str,
        "sign_convention": str,
        "format_pattern": str,
        "exclude_from_output": bool,
    },
)


# ============================================================================
# RECIPE ONTOLOGY — Entity schemas for 12 recipe/pipeline node types
# ============================================================================

def _outgoing_recipe(
    label: NodeLabel,
    constraints: Dict[RelationshipType, Tuple[Tuple[NodeLabel, NodeLabel], ...]] | None = None,
) -> Tuple[RelationshipConstraint, ...]:
    """Gather all RelationshipConstraints where label is a valid source."""
    if constraints is None:
        constraints = RECIPE_RELATIONSHIP_CONSTRAINTS
    result: list[RelationshipConstraint] = []
    for rel_type, pairs in constraints.items():
        source_labels = frozenset(s for s, t in pairs if s == label)
        if source_labels:
            target_labels = frozenset(t for s, t in pairs if s == label)
            result.append(RelationshipConstraint(
                relationship_type=rel_type,
                source_labels=frozenset({label}),
                target_labels=target_labels,
                properties=PropertySchema(
                    required=frozenset(), optional=frozenset(), types={},
                ),
            ))
    return tuple(result)


def _incoming_recipe(
    label: NodeLabel,
    constraints: Dict[RelationshipType, Tuple[Tuple[NodeLabel, NodeLabel], ...]] | None = None,
) -> Tuple[RelationshipConstraint, ...]:
    """Gather all RelationshipConstraints where label is a valid target."""
    if constraints is None:
        constraints = RECIPE_RELATIONSHIP_CONSTRAINTS
    result: list[RelationshipConstraint] = []
    for rel_type, pairs in constraints.items():
        target_labels = frozenset(t for s, t in pairs if t == label)
        if target_labels:
            source_labels = frozenset(s for s, t in pairs if t == label)
            result.append(RelationshipConstraint(
                relationship_type=rel_type,
                source_labels=source_labels,
                target_labels=frozenset({label}),
                properties=PropertySchema(
                    required=frozenset(), optional=frozenset(), types={},
                ),
            ))
    return tuple(result)


_RECIPE_PROPS_MAP: Dict[NodeLabel, PropertySchema] = {
    NodeLabel.SOURCE_SCHEMA: _SOURCE_SCHEMA_PROPS,
    NodeLabel.COLUMN: _COLUMN_PROPS,
    NodeLabel.MEASURE: _MEASURE_PROPS,
    NodeLabel.CONDITION: _CONDITION_PROPS,
    NodeLabel.ACCOUNT_SLOT: _ACCOUNT_SLOT_PROPS,
    NodeLabel.MAPPING_RULE: _MAPPING_RULE_PROPS,
    NodeLabel.ACCOUNTING_RECIPE: _ACCOUNTING_RECIPE_PROPS,
    NodeLabel.OUTPUT_FORMAT: _OUTPUT_FORMAT_PROPS,
    NodeLabel.OUTPUT_COLUMN: _OUTPUT_COLUMN_PROPS,
    NodeLabel.VALIDATION_RULE: _VALIDATION_RULE_PROPS,
    NodeLabel.BATCH_FORMAT: _BATCH_FORMAT_PROPS,
    NodeLabel.REFERENCE: _REFERENCE_PROPS,
}

RECIPE_ONTOLOGY: Dict[NodeLabel, EntitySchema] = {
    label: EntitySchema(
        label=label,
        properties=props,
        outgoing_relationships=_outgoing_recipe(label),
        incoming_relationships=_incoming_recipe(label),
    )
    for label, props in _RECIPE_PROPS_MAP.items()
}


# ============================================================================
# REFERENCE DATA SUPPORT
# ============================================================================

# Which accounting labels may be the source of a USES_REFERENCE edge
REFERENCE_RELATIONSHIP_SOURCES: FrozenSet[NodeLabel] = frozenset({
    NodeLabel.MAPPING_RULE,
    NodeLabel.CONDITION,
    NodeLabel.ACCOUNTING_RECIPE,
})


# ============================================================================
# MERGED ONTOLOGY — Combines core + recipe constraints
# ============================================================================

def merged_relationship_constraints() -> Dict[
    RelationshipType, Tuple[Tuple[NodeLabel, NodeLabel], ...]
]:
    """Combine core and recipe relationship constraints into one dict."""
    combined: Dict[RelationshipType, list[Tuple[NodeLabel, NodeLabel]]] = {}
    for rel_type, pairs in RELATIONSHIP_CONSTRAINTS.items():
        combined.setdefault(rel_type, []).extend(pairs)
    for rel_type, pairs in RECIPE_RELATIONSHIP_CONSTRAINTS.items():
        combined.setdefault(rel_type, []).extend(pairs)
    return {rt: tuple(pairs) for rt, pairs in combined.items()}


def _outgoing_merged(
    label: NodeLabel,
    constraints: Dict[RelationshipType, Tuple[Tuple[NodeLabel, NodeLabel], ...]],
) -> Tuple[RelationshipConstraint, ...]:
    """Gather outgoing RelationshipConstraints from merged constraints."""
    result: list[RelationshipConstraint] = []
    for rel_type, pairs in constraints.items():
        target_labels = frozenset(t for s, t in pairs if s == label)
        if target_labels:
            result.append(RelationshipConstraint(
                relationship_type=rel_type,
                source_labels=frozenset({label}),
                target_labels=target_labels,
                properties=PropertySchema(
                    required=frozenset(), optional=frozenset(), types={},
                ),
            ))
    return tuple(result)


def _incoming_merged(
    label: NodeLabel,
    constraints: Dict[RelationshipType, Tuple[Tuple[NodeLabel, NodeLabel], ...]],
) -> Tuple[RelationshipConstraint, ...]:
    """Gather incoming RelationshipConstraints from merged constraints."""
    result: list[RelationshipConstraint] = []
    for rel_type, pairs in constraints.items():
        source_labels = frozenset(s for s, t in pairs if t == label)
        if source_labels:
            result.append(RelationshipConstraint(
                relationship_type=rel_type,
                source_labels=source_labels,
                target_labels=frozenset({label}),
                properties=PropertySchema(
                    required=frozenset(), optional=frozenset(), types={},
                ),
            ))
    return tuple(result)


def merged_ontology() -> Dict[NodeLabel, EntitySchema]:
    """Rebuild all 16 EntitySchema entries using combined constraints.

    Cannot be a naive {**ONTOLOGY, **RECIPE_ONTOLOGY} because cross-layer
    relationships (e.g. MAPPED_TO from AccountSlot→Account) require that
    Account's incoming_relationships include the recipe-layer edges.
    """
    combined_constraints = merged_relationship_constraints()

    # Collect all properties from both ontologies
    all_props: Dict[NodeLabel, PropertySchema] = {}
    for label, schema in ONTOLOGY.items():
        all_props[label] = schema.properties
    for label, schema in RECIPE_ONTOLOGY.items():
        all_props[label] = schema.properties

    return {
        label: EntitySchema(
            label=label,
            properties=props,
            outgoing_relationships=_outgoing_merged(label, combined_constraints),
            incoming_relationships=_incoming_merged(label, combined_constraints),
        )
        for label, props in all_props.items()
    }


# ============================================================================
# RECIPE VALIDATION FUNCTIONS — All pure, all return ValidationResult
# ============================================================================

def validate_recipe_has_schema(pattern: GraphPattern) -> ValidationResult:
    """AccountingRecipe must have TRANSFORMS relationship to a SourceSchema."""
    recipe_ids = {
        n.id for n in pattern.nodes
        if NodeLabel.ACCOUNTING_RECIPE in n.labels
    }
    if not recipe_ids:
        return ValidationResult.success()

    transforms_sources = {
        rel.start_node_id
        for rel in pattern.relationships
        if rel.type == RelationshipType.TRANSFORMS
    }

    missing = recipe_ids - transforms_sources
    if missing:
        return ValidationResult.failure(tuple(
            f"AccountingRecipe '{rid}' has no TRANSFORMS relationship to a SourceSchema"
            for rid in sorted(missing)
        ))
    return ValidationResult.success()


def validate_slot_has_mapping(pattern: GraphPattern) -> ValidationResult:
    """AccountSlot should have MAPPED_TO to an Account (soft warning)."""
    slot_ids = {
        n.id for n in pattern.nodes
        if NodeLabel.ACCOUNT_SLOT in n.labels
    }
    if not slot_ids:
        return ValidationResult.success()

    mapped_sources = {
        rel.start_node_id
        for rel in pattern.relationships
        if rel.type == RelationshipType.MAPPED_TO
    }

    unmapped = slot_ids - mapped_sources
    if unmapped:
        return ValidationResult.success(warnings=tuple(
            f"AccountSlot '{sid}' has no MAPPED_TO relationship to an Account"
            for sid in sorted(unmapped)
        ))
    return ValidationResult.success()


def validate_mapping_rule_completeness(pattern: GraphPattern) -> ValidationResult:
    """MappingRule must have both DEBITS and CREDITS edges."""
    rule_ids = {
        n.id for n in pattern.nodes
        if NodeLabel.MAPPING_RULE in n.labels
    }
    if not rule_ids:
        return ValidationResult.success()

    debit_sources = {
        rel.start_node_id
        for rel in pattern.relationships
        if rel.type == RelationshipType.DEBITS
    }
    credit_sources = {
        rel.start_node_id
        for rel in pattern.relationships
        if rel.type == RelationshipType.CREDITS
    }

    errors: list[str] = []
    for rid in sorted(rule_ids):
        missing: list[str] = []
        if rid not in debit_sources:
            missing.append("DEBITS")
        if rid not in credit_sources:
            missing.append("CREDITS")
        if missing:
            errors.append(
                f"MappingRule '{rid}' is missing {', '.join(missing)} edge(s)"
            )

    if errors:
        return ValidationResult.failure(tuple(errors))
    return ValidationResult.success()


def validate_measure_references_column(pattern: GraphPattern) -> ValidationResult:
    """Measure must have AGGREGATES to a Column."""
    measure_ids = {
        n.id for n in pattern.nodes
        if NodeLabel.MEASURE in n.labels
    }
    if not measure_ids:
        return ValidationResult.success()

    aggregates_sources = {
        rel.start_node_id
        for rel in pattern.relationships
        if rel.type == RelationshipType.AGGREGATES
    }

    missing = measure_ids - aggregates_sources
    if missing:
        return ValidationResult.failure(tuple(
            f"Measure '{mid}' has no AGGREGATES relationship to a Column"
            for mid in sorted(missing)
        ))
    return ValidationResult.success()


def validate_uses_reference(pattern: GraphPattern) -> ValidationResult:
    """Validates only the accounting (source) side of USES_REFERENCE; target is opaque."""
    uses_ref_rels = [
        rel for rel in pattern.relationships
        if rel.type == RelationshipType.USES_REFERENCE
    ]
    if not uses_ref_rels:
        return ValidationResult.success()

    node_map = {n.id: n for n in pattern.nodes}
    errors: list[str] = []

    for rel in uses_ref_rels:
        source = node_map.get(rel.start_node_id)
        if source is None:
            errors.append(
                f"USES_REFERENCE relationship '{rel.id}' has unknown source node '{rel.start_node_id}'"
            )
            continue
        source_labels = source.labels & {l for l in REFERENCE_RELATIONSHIP_SOURCES}
        if not source_labels:
            allowed = ", ".join(l.value for l in sorted(REFERENCE_RELATIONSHIP_SOURCES, key=lambda x: x.value))
            actual = ", ".join(l.value for l in source.labels)
            errors.append(
                f"USES_REFERENCE source '{rel.start_node_id}' has labels [{actual}], "
                f"but only [{allowed}] may source USES_REFERENCE"
            )

    if errors:
        return ValidationResult.failure(tuple(errors))
    return ValidationResult.success()
