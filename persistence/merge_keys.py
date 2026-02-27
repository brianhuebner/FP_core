# persistence/merge_keys.py — MERGE key registry for Neo4j persistence
from __future__ import annotations

from domain.ontology_recipe import merged_ontology
from domain.types import NodeLabel

# Maps each NodeLabel to the property names used in the MERGE clause.
# Remaining properties go in SET. Keys must be a subset of the label's
# PropertySchema.required fields (enforced by validate_merge_keys).
MERGE_KEYS: dict[NodeLabel, tuple[str, ...]] = {
    # Core accounting — natural business keys
    NodeLabel.ACCOUNT: ("code",),
    NodeLabel.TRANSACTION: ("transaction_id",),
    NodeLabel.TRANSACTION_LINE: ("line_id",),
    NodeLabel.ENTITY: ("entity_id",),
    NodeLabel.ANALYTICAL_DIMENSION: ("dimension_id",),
    NodeLabel.ALLOCATION_RULE: ("rule_id",),
    NodeLabel.DATA_SOURCE: ("source_id",),
    # Recipe-scoped — recipe_id + type-specific identity
    NodeLabel.SOURCE_SCHEMA: ("recipe_id", "name"),
    NodeLabel.COLUMN: ("recipe_id", "name"),
    NodeLabel.MEASURE: ("recipe_id", "name"),
    NodeLabel.CONDITION: ("recipe_id", "condition_id"),
    NodeLabel.ACCOUNT_SLOT: ("recipe_id", "slot_id"),
    NodeLabel.MAPPING_RULE: ("recipe_id", "rule_name"),
    NodeLabel.ACCOUNTING_RECIPE: ("recipe_id",),
    NodeLabel.OUTPUT_FORMAT: ("format_id",),
    NodeLabel.OUTPUT_COLUMN: ("format_id", "name"),
    NodeLabel.VALIDATION_RULE: ("format_id", "name"),
    NodeLabel.ENTRY_STRUCTURE: ("format_id",),
    NodeLabel.REFERENCE: (),  # Opaque — falls back to _node_id
}


def validate_merge_keys(
    merge_keys: dict[NodeLabel, tuple[str, ...]] = MERGE_KEYS,
) -> list[str]:
    """Check that every merge key is in the label's PropertySchema.required.

    Returns a list of error strings (empty = all valid).
    Reference is exempt since it has no required properties.
    """
    ontology = merged_ontology()
    errors: list[str] = []

    for label in NodeLabel:
        if label not in merge_keys:
            errors.append(f"NodeLabel.{label.name} has no entry in MERGE_KEYS")
            continue

        keys = merge_keys[label]
        schema = ontology.get(label)
        if schema is None:
            errors.append(f"NodeLabel.{label.name} not found in merged_ontology()")
            continue

        # Reference has empty keys and empty required — skip subset check
        if label == NodeLabel.REFERENCE:
            continue

        required = schema.properties.required
        for key in keys:
            if key not in required:
                errors.append(
                    f"MERGE_KEYS[{label.name}] key '{key}' is not in PropertySchema.required {sorted(required)}"
                )

    return errors
