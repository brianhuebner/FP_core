# persistence/__init__.py — Public API for the persistence package
from persistence.connection import Neo4jConnection
from persistence.deserializers import (
    deserialize_node,
    deserialize_pattern,
    deserialize_relationship,
)
from persistence.merge_keys import MERGE_KEYS, validate_merge_keys
from persistence.operations import (
    delete_format_by_id,
    delete_pattern_by_recipe,
    load_format_by_id,
    load_pattern_by_recipe,
    save_pattern,
    verify_format,
    verify_pattern,
)
from persistence.serializers import (
    serialize_node,
    serialize_pattern,
    serialize_relationship,
)

__all__ = [
    # Merge keys
    "MERGE_KEYS",
    "validate_merge_keys",
    # Serializers (pure)
    "serialize_node",
    "serialize_pattern",
    "serialize_relationship",
    # Deserializers (pure)
    "deserialize_node",
    "deserialize_pattern",
    "deserialize_relationship",
    # Connection
    "Neo4jConnection",
    # Operations
    "delete_format_by_id",
    "delete_pattern_by_recipe",
    "load_format_by_id",
    "load_pattern_by_recipe",
    "save_pattern",
    "verify_format",
    "verify_pattern",
]
