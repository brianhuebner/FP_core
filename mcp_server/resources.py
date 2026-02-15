# mcp_server/resources.py — MCP resource handlers
from __future__ import annotations

import json
from typing import Any, Dict

from domain.ontology import EntitySchema, PropertySchema, RelationshipConstraint
from domain.ontology_recipe import merged_ontology, merged_relationship_constraints
from domain.types import NodeLabel, RelationshipType

from mcp_server import mcp


def _property_schema_to_dict(ps: PropertySchema) -> Dict[str, Any]:
    """Convert a PropertySchema to a JSON-safe dict."""
    return {
        "required": sorted(ps.required),
        "optional": sorted(ps.optional),
        "types": {k: v.__name__ for k, v in ps.types.items()},
    }


def _relationship_constraint_to_dict(rc: RelationshipConstraint) -> Dict[str, Any]:
    """Convert a RelationshipConstraint to a JSON-safe dict."""
    return {
        "relationship_type": rc.relationship_type.value,
        "source_labels": sorted(l.value for l in rc.source_labels),
        "target_labels": sorted(l.value for l in rc.target_labels),
        "properties": _property_schema_to_dict(rc.properties),
    }


def _entity_schema_to_dict(es: EntitySchema) -> Dict[str, Any]:
    """Convert an EntitySchema to a JSON-safe dict."""
    return {
        "label": es.label.value,
        "properties": _property_schema_to_dict(es.properties),
        "outgoing_relationships": [
            _relationship_constraint_to_dict(rc)
            for rc in es.outgoing_relationships
        ],
        "incoming_relationships": [
            _relationship_constraint_to_dict(rc)
            for rc in es.incoming_relationships
        ],
    }


@mcp.resource("ontology://merged")
def get_merged_ontology() -> str:
    """Full merged ontology (core + recipe) as JSON.

    Contains all 19 EntitySchema entries with property schemas
    and relationship constraints.
    """
    ontology = merged_ontology()
    result = {
        label.value: _entity_schema_to_dict(schema)
        for label, schema in ontology.items()
    }
    return json.dumps(result, indent=2)


@mcp.resource("constraints://merged")
def get_merged_constraints() -> str:
    """All 25 merged relationship constraints as JSON.

    Maps each RelationshipType to its allowed (source, target) label pairs.
    """
    constraints = merged_relationship_constraints()
    result = {
        rel_type.value: [
            {"source": src.value, "target": tgt.value}
            for src, tgt in pairs
        ]
        for rel_type, pairs in constraints.items()
    }
    return json.dumps(result, indent=2)
