# domain/ontology.py — Accounting Ontology Schema, Constraints & Validators
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from domain.types import (
    AccountType,
    BalanceDirection,
    GraphPattern,
    Node,
    NodeLabel,
    Relationship,
    RelationshipType,
    SemanticType,
    TransactionLine,
)

# ============================================================================
# SCHEMA DEFINITION TYPES
# ============================================================================


@dataclass(frozen=True)
class PropertySchema:
    required: frozenset[str]
    optional: frozenset[str]
    types: dict[str, type]


@dataclass(frozen=True)
class RelationshipConstraint:
    relationship_type: RelationshipType
    source_labels: frozenset[NodeLabel]
    target_labels: frozenset[NodeLabel]
    properties: PropertySchema


@dataclass(frozen=True)
class EntitySchema:
    label: NodeLabel
    properties: PropertySchema
    outgoing_relationships: tuple[RelationshipConstraint, ...]
    incoming_relationships: tuple[RelationshipConstraint, ...]


# ============================================================================
# VALIDATION RESULT
# ============================================================================


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @staticmethod
    def success(warnings: tuple[str, ...] = ()) -> ValidationResult:
        return ValidationResult(is_valid=True, errors=(), warnings=warnings)

    @staticmethod
    def failure(errors: tuple[str, ...], warnings: tuple[str, ...] = ()) -> ValidationResult:
        return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

    @staticmethod
    def merge(*results: ValidationResult) -> ValidationResult:
        all_errors: list[str] = []
        all_warnings: list[str] = []
        for r in results:
            all_errors.extend(r.errors)
            all_warnings.extend(r.warnings)
        return ValidationResult(
            is_valid=len(all_errors) == 0,
            errors=tuple(all_errors),
            warnings=tuple(all_warnings),
        )


# ============================================================================
# CONSTRAINT DATA CONSTANTS
# ============================================================================

ACCOUNT_TYPE_BALANCE_MAP: dict[AccountType, BalanceDirection] = {
    AccountType.ASSET: BalanceDirection.DEBIT,
    AccountType.EXPENSE: BalanceDirection.DEBIT,
    AccountType.CONTRA_REVENUE: BalanceDirection.DEBIT,
    AccountType.LIABILITY: BalanceDirection.CREDIT,
    AccountType.EQUITY: BalanceDirection.CREDIT,
    AccountType.REVENUE: BalanceDirection.CREDIT,
    AccountType.CONTRA_EXPENSE: BalanceDirection.CREDIT,
}

# Maps RelationshipType -> list of (source_label, target_label) pairs
RELATIONSHIP_CONSTRAINTS: dict[RelationshipType, tuple[tuple[NodeLabel, NodeLabel], ...]] = {
    RelationshipType.BELONGS_TO: ((NodeLabel.TRANSACTION_LINE, NodeLabel.TRANSACTION),),
    RelationshipType.POSTS_TO: ((NodeLabel.TRANSACTION_LINE, NodeLabel.ACCOUNT),),
    RelationshipType.OWNS: ((NodeLabel.ENTITY, NodeLabel.ACCOUNT),),
    RelationshipType.PARENT_OF: (
        (NodeLabel.ENTITY, NodeLabel.ENTITY),
        (NodeLabel.ANALYTICAL_DIMENSION, NodeLabel.ANALYTICAL_DIMENSION),
    ),
    RelationshipType.CHILD_OF: (
        (NodeLabel.ENTITY, NodeLabel.ENTITY),
        (NodeLabel.ANALYTICAL_DIMENSION, NodeLabel.ANALYTICAL_DIMENSION),
    ),
    RelationshipType.ALLOCATED_BY: ((NodeLabel.TRANSACTION_LINE, NodeLabel.ALLOCATION_RULE),),
    RelationshipType.DIMENSIONED_BY: ((NodeLabel.TRANSACTION_LINE, NodeLabel.ANALYTICAL_DIMENSION),),
    RelationshipType.CREATED_FROM: ((NodeLabel.TRANSACTION, NodeLabel.DATA_SOURCE),),
    RelationshipType.USES_DIMENSION: ((NodeLabel.ALLOCATION_RULE, NodeLabel.ANALYTICAL_DIMENSION),),
    RelationshipType.APPLIED_TO: ((NodeLabel.ALLOCATION_RULE, NodeLabel.ACCOUNT),),
    RelationshipType.PROVIDES: ((NodeLabel.DATA_SOURCE, NodeLabel.TRANSACTION),),
}

# ============================================================================
# ONTOLOGY — Entity schemas for all 7 node types
# ============================================================================

_ACCOUNT_PROPS = PropertySchema(
    required=frozenset({"code", "name", "account_type", "normal_balance"}),
    optional=frozenset({"is_active", "semantic_type", "expected_behavior"}),
    types={
        "code": str,
        "name": str,
        "account_type": str,
        "normal_balance": str,
        "is_active": bool,
        "semantic_type": str,
        "expected_behavior": str,
    },
)

_TRANSACTION_PROPS = PropertySchema(
    required=frozenset(
        {
            "transaction_id",
            "transaction_date",
            "posting_date",
            "period",
            "description",
            "is_posted",
            "created_by",
            "created_at",
            "source_system_id",
        }
    ),
    optional=frozenset(),
    types={
        "transaction_id": str,
        "transaction_date": str,
        "posting_date": str,
        "period": str,
        "description": str,
        "is_posted": bool,
        "created_by": str,
        "created_at": str,
        "source_system_id": str,
    },
)

_TRANSACTION_LINE_PROPS = PropertySchema(
    required=frozenset({"line_id", "amount", "direction"}),
    optional=frozenset({"memo"}),
    types={
        "line_id": str,
        "amount": float,
        "direction": str,
        "memo": str,
    },
)

_ENTITY_PROPS = PropertySchema(
    required=frozenset({"entity_id", "legal_name", "entity_type", "base_currency"}),
    optional=frozenset({"tax_id"}),
    types={
        "entity_id": str,
        "legal_name": str,
        "entity_type": str,
        "base_currency": str,
        "tax_id": str,
    },
)

_DIMENSION_PROPS = PropertySchema(
    required=frozenset({"dimension_id", "dimension_type", "name"}),
    optional=frozenset({"is_hierarchical", "is_required", "code", "parent_id"}),
    types={
        "dimension_id": str,
        "dimension_type": str,
        "name": str,
        "is_hierarchical": bool,
        "is_required": bool,
        "code": str,
        "parent_id": str,
    },
)

_ALLOCATION_RULE_PROPS = PropertySchema(
    required=frozenset(
        {
            "rule_id",
            "rule_name",
            "rule_type",
            "is_active",
            "created_by",
            "created_at",
            "version",
        }
    ),
    optional=frozenset(),
    types={
        "rule_id": str,
        "rule_name": str,
        "rule_type": str,
        "is_active": bool,
        "created_by": str,
        "created_at": str,
        "version": int,
    },
)

_DATA_SOURCE_PROPS = PropertySchema(
    required=frozenset({"source_id", "source_type"}),
    optional=frozenset({"connection_config", "last_sync"}),
    types={
        "source_id": str,
        "source_type": str,
        "connection_config": str,
        "last_sync": str,
    },
)


def _gather_constraints(
    label: NodeLabel,
    constraints: dict[RelationshipType, tuple[tuple[NodeLabel, NodeLabel], ...]],
    direction: str,
) -> tuple[RelationshipConstraint, ...]:
    """Gather RelationshipConstraints where label appears on the given side.

    direction='source' gathers outgoing constraints (label is source).
    direction='target' gathers incoming constraints (label is target).
    """
    result: list[RelationshipConstraint] = []
    for rel_type, pairs in constraints.items():
        if direction == "source":
            matched = frozenset(t for s, t in pairs if s == label)
            if matched:
                result.append(
                    RelationshipConstraint(
                        relationship_type=rel_type,
                        source_labels=frozenset({label}),
                        target_labels=matched,
                        properties=PropertySchema(
                            required=frozenset(),
                            optional=frozenset(),
                            types={},
                        ),
                    )
                )
        else:
            matched = frozenset(s for s, t in pairs if t == label)
            if matched:
                result.append(
                    RelationshipConstraint(
                        relationship_type=rel_type,
                        source_labels=matched,
                        target_labels=frozenset({label}),
                        properties=PropertySchema(
                            required=frozenset(),
                            optional=frozenset(),
                            types={},
                        ),
                    )
                )
    return tuple(result)


def _outgoing(label: NodeLabel) -> tuple[RelationshipConstraint, ...]:
    return _gather_constraints(label, RELATIONSHIP_CONSTRAINTS, "source")


def _incoming(label: NodeLabel) -> tuple[RelationshipConstraint, ...]:
    return _gather_constraints(label, RELATIONSHIP_CONSTRAINTS, "target")


ONTOLOGY: dict[NodeLabel, EntitySchema] = {
    NodeLabel.ACCOUNT: EntitySchema(
        label=NodeLabel.ACCOUNT,
        properties=_ACCOUNT_PROPS,
        outgoing_relationships=_outgoing(NodeLabel.ACCOUNT),
        incoming_relationships=_incoming(NodeLabel.ACCOUNT),
    ),
    NodeLabel.TRANSACTION: EntitySchema(
        label=NodeLabel.TRANSACTION,
        properties=_TRANSACTION_PROPS,
        outgoing_relationships=_outgoing(NodeLabel.TRANSACTION),
        incoming_relationships=_incoming(NodeLabel.TRANSACTION),
    ),
    NodeLabel.TRANSACTION_LINE: EntitySchema(
        label=NodeLabel.TRANSACTION_LINE,
        properties=_TRANSACTION_LINE_PROPS,
        outgoing_relationships=_outgoing(NodeLabel.TRANSACTION_LINE),
        incoming_relationships=_incoming(NodeLabel.TRANSACTION_LINE),
    ),
    NodeLabel.ENTITY: EntitySchema(
        label=NodeLabel.ENTITY,
        properties=_ENTITY_PROPS,
        outgoing_relationships=_outgoing(NodeLabel.ENTITY),
        incoming_relationships=_incoming(NodeLabel.ENTITY),
    ),
    NodeLabel.ANALYTICAL_DIMENSION: EntitySchema(
        label=NodeLabel.ANALYTICAL_DIMENSION,
        properties=_DIMENSION_PROPS,
        outgoing_relationships=_outgoing(NodeLabel.ANALYTICAL_DIMENSION),
        incoming_relationships=_incoming(NodeLabel.ANALYTICAL_DIMENSION),
    ),
    NodeLabel.ALLOCATION_RULE: EntitySchema(
        label=NodeLabel.ALLOCATION_RULE,
        properties=_ALLOCATION_RULE_PROPS,
        outgoing_relationships=_outgoing(NodeLabel.ALLOCATION_RULE),
        incoming_relationships=_incoming(NodeLabel.ALLOCATION_RULE),
    ),
    NodeLabel.DATA_SOURCE: EntitySchema(
        label=NodeLabel.DATA_SOURCE,
        properties=_DATA_SOURCE_PROPS,
        outgoing_relationships=_outgoing(NodeLabel.DATA_SOURCE),
        incoming_relationships=_incoming(NodeLabel.DATA_SOURCE),
    ),
}


# ============================================================================
# VALIDATION FUNCTIONS — All pure, all return ValidationResult
# ============================================================================

# --- Hard blocks (errors) ---


def validate_node_properties(
    node: Node,
    ontology: dict[NodeLabel, EntitySchema] = ONTOLOGY,
) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    for label in node.labels:
        schema = ontology.get(label)
        if schema is None:
            errors.append(f"Unknown node label: {label.value}")
            continue

        props = schema.properties
        for req in props.required:
            if req not in node.properties:
                errors.append(f"[{label.value}] Missing required property: {req}")

        for key, value in node.properties.items():
            if key not in props.required and key not in props.optional:
                warnings.append(f"[{label.value}] Unknown property: {key}")
            elif key in props.types and not isinstance(value, props.types[key]):
                errors.append(
                    f"[{label.value}] Property '{key}' expected {props.types[key].__name__}, got {type(value).__name__}"
                )

    if errors:
        return ValidationResult.failure(tuple(errors), tuple(warnings))
    return ValidationResult.success(tuple(warnings))


def validate_account_balance_direction(
    account_type: AccountType,
    normal_balance: BalanceDirection,
) -> ValidationResult:
    expected = ACCOUNT_TYPE_BALANCE_MAP.get(account_type)
    if expected is None:
        return ValidationResult.failure((f"Unknown account type: {account_type.value}",))
    if normal_balance != expected:
        return ValidationResult.failure(
            (f"Account type {account_type.value} requires normal_balance={expected.value}, got {normal_balance.value}",)
        )
    return ValidationResult.success()


def validate_relationship(
    rel: Relationship,
    source: Node,
    target: Node,
    ontology: dict[NodeLabel, EntitySchema] = ONTOLOGY,
) -> ValidationResult:
    allowed_pairs = RELATIONSHIP_CONSTRAINTS.get(rel.type)
    if allowed_pairs is None:
        return ValidationResult.failure((f"Unknown relationship type: {rel.type.value}",))

    for source_label in source.labels:
        for target_label in target.labels:
            if (source_label, target_label) in allowed_pairs:
                return ValidationResult.success()

    source_labels = ", ".join(l.value for l in source.labels)
    target_labels = ", ".join(l.value for l in target.labels)
    return ValidationResult.failure(
        (f"Relationship {rel.type.value} not allowed between [{source_labels}] and [{target_labels}]",)
    )


def validate_graph_pattern(
    pattern: GraphPattern,
    ontology: dict[NodeLabel, EntitySchema] = ONTOLOGY,
) -> ValidationResult:
    results: list[ValidationResult] = []

    for node in pattern.nodes:
        results.append(validate_node_properties(node, ontology))

    node_map: dict[str, Node] = {n.id: n for n in pattern.nodes}
    for rel in pattern.relationships:
        source = node_map.get(rel.start_node_id)
        target = node_map.get(rel.end_node_id)
        if source is None or target is None:
            results.append(
                ValidationResult.failure(
                    (
                        f"Relationship {rel.type.value} references "
                        f"unknown node(s): start={rel.start_node_id}, "
                        f"end={rel.end_node_id}",
                    )
                )
            )
        else:
            results.append(validate_relationship(rel, source, target, ontology))

    return ValidationResult.merge(*results)


def validate_transaction_balance(
    transaction_lines: tuple[TransactionLine, ...],
) -> ValidationResult:
    debit_sum = Decimal("0")
    credit_sum = Decimal("0")
    for line in transaction_lines:
        if line.direction == BalanceDirection.DEBIT:
            debit_sum += line.amount
        else:
            credit_sum += line.amount

    if debit_sum != credit_sum:
        return ValidationResult.failure((f"Transaction is unbalanced: debits={debit_sum}, credits={credit_sum}",))
    return ValidationResult.success()


def validate_posting_allowed(is_active: bool) -> ValidationResult:
    if not is_active:
        return ValidationResult.failure(("Cannot post to inactive account",))
    return ValidationResult.success()


# --- Soft warnings ---


def validate_clearing_account_balance(
    semantic_type: str | None,
    balance: Decimal,
) -> ValidationResult:
    if semantic_type == SemanticType.CLEARING.value and balance != Decimal("0"):
        return ValidationResult.success(warnings=(f"Clearing account has non-zero balance: {balance}",))
    return ValidationResult.success()


def validate_temporal_ordering(
    transaction_date: datetime,
    posting_date: datetime,
) -> ValidationResult:
    if posting_date < transaction_date:
        return ValidationResult.success(
            warnings=(f"posting_date ({posting_date}) is before transaction_date ({transaction_date})",)
        )
    return ValidationResult.success()


def validate_dimension_hierarchy(
    parent_id: str | None,
    is_hierarchical: bool,
) -> ValidationResult:
    if parent_id is not None and not is_hierarchical:
        return ValidationResult.success(warnings=("parent_id is set but is_hierarchical is False",))
    return ValidationResult.success()


# --- Composition ---


def compose_validators(
    *validators: Callable[..., ValidationResult],
) -> Callable[..., ValidationResult]:
    def composed(*args: Any, **kwargs: Any) -> ValidationResult:
        results = tuple(v(*args, **kwargs) for v in validators)
        return ValidationResult.merge(*results)

    return composed
