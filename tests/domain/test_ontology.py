# tests/domain/test_ontology.py — Tests for Layer 2 ontology & validation
from datetime import datetime
from decimal import Decimal
from functools import partial

import pytest

from domain.ontology import (
    ACCOUNT_TYPE_BALANCE_MAP,
    ONTOLOGY,
    RELATIONSHIP_CONSTRAINTS,
    EntitySchema,
    PropertySchema,
    RelationshipConstraint,
    ValidationResult,
    compose_validators,
    validate_account_balance_direction,
    validate_clearing_account_balance,
    validate_dimension_hierarchy,
    validate_graph_pattern,
    validate_node_properties,
    validate_posting_allowed,
    validate_relationship,
    validate_temporal_ordering,
    validate_transaction_balance,
)
from domain.types import (
    AccountType,
    BalanceDirection,
    GraphPattern,
    Node,
    NodeLabel,
    Relationship,
    RelationshipType,
    TransactionLine,
)

# ============================================================================
# Schema type tests
# ============================================================================


class TestSchemaTypes:
    def test_property_schema_is_frozen(self):
        ps = PropertySchema(
            required=frozenset({"a"}),
            optional=frozenset({"b"}),
            types={"a": str, "b": int},
        )
        with pytest.raises(AttributeError):
            ps.required = frozenset()

    def test_relationship_constraint_is_frozen(self):
        rc = RelationshipConstraint(
            relationship_type=RelationshipType.OWNS,
            source_labels=frozenset({NodeLabel.ENTITY}),
            target_labels=frozenset({NodeLabel.ACCOUNT}),
            properties=PropertySchema(
                required=frozenset(),
                optional=frozenset(),
                types={},
            ),
        )
        with pytest.raises(AttributeError):
            rc.relationship_type = RelationshipType.POSTS_TO

    def test_entity_schema_is_frozen(self):
        es = EntitySchema(
            label=NodeLabel.ACCOUNT,
            properties=PropertySchema(
                required=frozenset(),
                optional=frozenset(),
                types={},
            ),
            outgoing_relationships=(),
            incoming_relationships=(),
        )
        with pytest.raises(AttributeError):
            es.label = NodeLabel.ENTITY


# ============================================================================
# ValidationResult tests
# ============================================================================


class TestValidationResult:
    def test_success_factory(self):
        r = ValidationResult.success()
        assert r.is_valid is True
        assert r.errors == ()
        assert r.warnings == ()

    def test_success_with_warnings(self):
        r = ValidationResult.success(warnings=("watch out",))
        assert r.is_valid is True
        assert r.warnings == ("watch out",)

    def test_failure_factory(self):
        r = ValidationResult.failure(("bad thing",))
        assert r.is_valid is False
        assert r.errors == ("bad thing",)
        assert r.warnings == ()

    def test_failure_with_warnings(self):
        r = ValidationResult.failure(("error",), ("warn",))
        assert r.is_valid is False
        assert r.errors == ("error",)
        assert r.warnings == ("warn",)

    def test_merge_all_valid(self):
        r = ValidationResult.merge(
            ValidationResult.success(),
            ValidationResult.success(("w1",)),
        )
        assert r.is_valid is True
        assert r.errors == ()
        assert r.warnings == ("w1",)

    def test_merge_with_failure(self):
        r = ValidationResult.merge(
            ValidationResult.success(("w1",)),
            ValidationResult.failure(("e1",), ("w2",)),
        )
        assert r.is_valid is False
        assert r.errors == ("e1",)
        assert r.warnings == ("w1", "w2")

    def test_merge_multiple_failures(self):
        r = ValidationResult.merge(
            ValidationResult.failure(("e1",)),
            ValidationResult.failure(("e2",), ("w1",)),
        )
        assert r.is_valid is False
        assert r.errors == ("e1", "e2")
        assert r.warnings == ("w1",)

    def test_merge_empty(self):
        r = ValidationResult.merge()
        assert r.is_valid is True
        assert r.errors == ()


# ============================================================================
# Constraint map completeness
# ============================================================================


class TestConstraintMaps:
    def test_all_account_types_in_balance_map(self):
        for at in AccountType:
            assert at in ACCOUNT_TYPE_BALANCE_MAP, f"{at.value} missing from ACCOUNT_TYPE_BALANCE_MAP"

    def test_balance_map_has_7_entries(self):
        assert len(ACCOUNT_TYPE_BALANCE_MAP) == 7

    def test_core_node_labels_in_ontology(self):
        core_labels = {
            NodeLabel.ACCOUNT,
            NodeLabel.TRANSACTION,
            NodeLabel.TRANSACTION_LINE,
            NodeLabel.ENTITY,
            NodeLabel.ANALYTICAL_DIMENSION,
            NodeLabel.ALLOCATION_RULE,
            NodeLabel.DATA_SOURCE,
        }
        for nl in core_labels:
            assert nl in ONTOLOGY, f"{nl.value} missing from ONTOLOGY"

    def test_ontology_has_7_entries(self):
        assert len(ONTOLOGY) == 7

    def test_relationship_constraints_cover_11_types(self):
        # 12 RelationshipTypes minus SYNCED_BY (not in MVP)
        assert len(RELATIONSHIP_CONSTRAINTS) == 11

    def test_debit_account_types(self):
        debit_types = {AccountType.ASSET, AccountType.EXPENSE, AccountType.CONTRA_REVENUE}
        for at in debit_types:
            assert ACCOUNT_TYPE_BALANCE_MAP[at] == BalanceDirection.DEBIT

    def test_credit_account_types(self):
        credit_types = {
            AccountType.LIABILITY,
            AccountType.EQUITY,
            AccountType.REVENUE,
            AccountType.CONTRA_EXPENSE,
        }
        for at in credit_types:
            assert ACCOUNT_TYPE_BALANCE_MAP[at] == BalanceDirection.CREDIT


# ============================================================================
# Ontology schema detail tests
# ============================================================================


class TestOntologySchemas:
    def test_account_required_properties(self):
        schema = ONTOLOGY[NodeLabel.ACCOUNT]
        assert "code" in schema.properties.required
        assert "name" in schema.properties.required
        assert "account_type" in schema.properties.required
        assert "normal_balance" in schema.properties.required

    def test_account_optional_properties(self):
        schema = ONTOLOGY[NodeLabel.ACCOUNT]
        assert "is_active" in schema.properties.optional
        assert "semantic_type" in schema.properties.optional

    def test_transaction_line_amount_type_is_float(self):
        schema = ONTOLOGY[NodeLabel.TRANSACTION_LINE]
        assert schema.properties.types["amount"] is float

    def test_entity_has_outgoing_owns(self):
        schema = ONTOLOGY[NodeLabel.ENTITY]
        owns_rels = [r for r in schema.outgoing_relationships if r.relationship_type == RelationshipType.OWNS]
        assert len(owns_rels) == 1
        assert NodeLabel.ACCOUNT in owns_rels[0].target_labels

    def test_transaction_line_has_outgoing_belongs_to(self):
        schema = ONTOLOGY[NodeLabel.TRANSACTION_LINE]
        bt_rels = [r for r in schema.outgoing_relationships if r.relationship_type == RelationshipType.BELONGS_TO]
        assert len(bt_rels) == 1
        assert NodeLabel.TRANSACTION in bt_rels[0].target_labels


# ============================================================================
# validate_node_properties
# ============================================================================


class TestValidateNodeProperties:
    def test_valid_account_node(self):
        node = Node(
            id="a1",
            labels={NodeLabel.ACCOUNT},
            properties={
                "code": "1000",
                "name": "Cash",
                "account_type": "asset",
                "normal_balance": "debit",
            },
        )
        result = validate_node_properties(node)
        assert result.is_valid is True

    def test_missing_required_property(self):
        node = Node(
            id="a1",
            labels={NodeLabel.ACCOUNT},
            properties={"code": "1000"},
        )
        result = validate_node_properties(node)
        assert result.is_valid is False
        assert any("Missing required" in e for e in result.errors)

    def test_wrong_property_type(self):
        node = Node(
            id="a1",
            labels={NodeLabel.ACCOUNT},
            properties={
                "code": "1000",
                "name": "Cash",
                "account_type": "asset",
                "normal_balance": "debit",
                "is_active": "yes",  # should be bool
            },
        )
        result = validate_node_properties(node)
        assert result.is_valid is False
        assert any("expected bool" in e for e in result.errors)

    def test_unknown_property_generates_warning(self):
        node = Node(
            id="a1",
            labels={NodeLabel.ACCOUNT},
            properties={
                "code": "1000",
                "name": "Cash",
                "account_type": "asset",
                "normal_balance": "debit",
                "mystery_field": "x",
            },
        )
        result = validate_node_properties(node)
        assert result.is_valid is True
        assert any("Unknown property" in w for w in result.warnings)

    def test_unknown_node_label(self):
        # Create a node with labels that aren't in the ontology
        # We'll use a mock ontology for this
        node = Node(
            id="x1",
            labels={NodeLabel.ACCOUNT},
            properties={},
        )
        empty_ontology = {}
        result = validate_node_properties(node, empty_ontology)
        assert result.is_valid is False
        assert any("Unknown node label" in e for e in result.errors)


# ============================================================================
# validate_account_balance_direction
# ============================================================================


class TestValidateAccountBalanceDirection:
    def test_asset_debit_valid(self):
        result = validate_account_balance_direction(
            AccountType.ASSET,
            BalanceDirection.DEBIT,
        )
        assert result.is_valid is True

    def test_revenue_credit_valid(self):
        result = validate_account_balance_direction(
            AccountType.REVENUE,
            BalanceDirection.CREDIT,
        )
        assert result.is_valid is True

    def test_asset_credit_invalid(self):
        result = validate_account_balance_direction(
            AccountType.ASSET,
            BalanceDirection.CREDIT,
        )
        assert result.is_valid is False
        assert any("requires normal_balance=debit" in e for e in result.errors)

    def test_liability_debit_invalid(self):
        result = validate_account_balance_direction(
            AccountType.LIABILITY,
            BalanceDirection.DEBIT,
        )
        assert result.is_valid is False

    def test_all_types_have_valid_combo(self):
        for at, bd in ACCOUNT_TYPE_BALANCE_MAP.items():
            result = validate_account_balance_direction(at, bd)
            assert result.is_valid is True, f"{at.value}/{bd.value} should be valid"


# ============================================================================
# validate_relationship
# ============================================================================


class TestValidateRelationship:
    def test_valid_belongs_to(self):
        rel = Relationship(
            id="r1",
            type=RelationshipType.BELONGS_TO,
            start_node_id="l1",
            end_node_id="t1",
            properties={},
        )
        source = Node(id="l1", labels={NodeLabel.TRANSACTION_LINE}, properties={})
        target = Node(id="t1", labels={NodeLabel.TRANSACTION}, properties={})
        result = validate_relationship(rel, source, target)
        assert result.is_valid is True

    def test_invalid_relationship_labels(self):
        rel = Relationship(
            id="r1",
            type=RelationshipType.BELONGS_TO,
            start_node_id="a1",
            end_node_id="a2",
            properties={},
        )
        source = Node(id="a1", labels={NodeLabel.ACCOUNT}, properties={})
        target = Node(id="a2", labels={NodeLabel.ACCOUNT}, properties={})
        result = validate_relationship(rel, source, target)
        assert result.is_valid is False
        assert any("not allowed" in e for e in result.errors)

    def test_valid_owns(self):
        rel = Relationship(
            id="r1",
            type=RelationshipType.OWNS,
            start_node_id="e1",
            end_node_id="a1",
            properties={},
        )
        source = Node(id="e1", labels={NodeLabel.ENTITY}, properties={})
        target = Node(id="a1", labels={NodeLabel.ACCOUNT}, properties={})
        result = validate_relationship(rel, source, target)
        assert result.is_valid is True

    def test_valid_parent_of_entity(self):
        rel = Relationship(
            id="r1",
            type=RelationshipType.PARENT_OF,
            start_node_id="e1",
            end_node_id="e2",
            properties={},
        )
        source = Node(id="e1", labels={NodeLabel.ENTITY}, properties={})
        target = Node(id="e2", labels={NodeLabel.ENTITY}, properties={})
        result = validate_relationship(rel, source, target)
        assert result.is_valid is True

    def test_valid_parent_of_dimension(self):
        rel = Relationship(
            id="r1",
            type=RelationshipType.PARENT_OF,
            start_node_id="d1",
            end_node_id="d2",
            properties={},
        )
        source = Node(id="d1", labels={NodeLabel.ANALYTICAL_DIMENSION}, properties={})
        target = Node(id="d2", labels={NodeLabel.ANALYTICAL_DIMENSION}, properties={})
        result = validate_relationship(rel, source, target)
        assert result.is_valid is True


# ============================================================================
# validate_graph_pattern
# ============================================================================


class TestValidateGraphPattern:
    def test_valid_pattern(self):
        line_node = Node(
            id="l1",
            labels={NodeLabel.TRANSACTION_LINE},
            properties={
                "line_id": "l1",
                "amount": 100.0,
                "direction": "debit",
            },
        )
        txn_node = Node(
            id="t1",
            labels={NodeLabel.TRANSACTION},
            properties={
                "transaction_id": "t1",
                "transaction_date": "2024-01-01",
                "posting_date": "2024-01-01",
                "period": "2024-01",
                "description": "Test",
                "is_posted": True,
                "created_by": "user",
                "created_at": "2024-01-01",
                "source_system_id": "sys1",
            },
        )
        rel = Relationship(
            id="r1",
            type=RelationshipType.BELONGS_TO,
            start_node_id="l1",
            end_node_id="t1",
            properties={},
        )
        pattern = GraphPattern(nodes=[line_node, txn_node], relationships=[rel])
        result = validate_graph_pattern(pattern)
        assert result.is_valid is True

    def test_pattern_with_dangling_relationship(self):
        node = Node(
            id="l1",
            labels={NodeLabel.TRANSACTION_LINE},
            properties={
                "line_id": "l1",
                "amount": 100.0,
                "direction": "debit",
            },
        )
        rel = Relationship(
            id="r1",
            type=RelationshipType.BELONGS_TO,
            start_node_id="l1",
            end_node_id="missing",
            properties={},
        )
        pattern = GraphPattern(nodes=[node], relationships=[rel])
        result = validate_graph_pattern(pattern)
        assert result.is_valid is False
        assert any("unknown node" in e for e in result.errors)

    def test_pattern_aggregates_errors(self):
        bad_node = Node(id="n1", labels={NodeLabel.ACCOUNT}, properties={})
        pattern = GraphPattern(nodes=[bad_node], relationships=[])
        result = validate_graph_pattern(pattern)
        assert result.is_valid is False
        assert len(result.errors) > 0


# ============================================================================
# validate_transaction_balance
# ============================================================================


class TestValidateTransactionBalance:
    def test_balanced_transaction(self):
        lines = (
            TransactionLine(
                line_id="l1",
                amount=Decimal("100.00"),
                direction=BalanceDirection.DEBIT,
            ),
            TransactionLine(
                line_id="l2",
                amount=Decimal("100.00"),
                direction=BalanceDirection.CREDIT,
            ),
        )
        result = validate_transaction_balance(lines)
        assert result.is_valid is True

    def test_unbalanced_transaction(self):
        lines = (
            TransactionLine(
                line_id="l1",
                amount=Decimal("100.00"),
                direction=BalanceDirection.DEBIT,
            ),
            TransactionLine(
                line_id="l2",
                amount=Decimal("50.00"),
                direction=BalanceDirection.CREDIT,
            ),
        )
        result = validate_transaction_balance(lines)
        assert result.is_valid is False
        assert any("unbalanced" in e for e in result.errors)

    def test_multi_line_balanced(self):
        lines = (
            TransactionLine(
                line_id="l1",
                amount=Decimal("100.00"),
                direction=BalanceDirection.DEBIT,
            ),
            TransactionLine(
                line_id="l2",
                amount=Decimal("60.00"),
                direction=BalanceDirection.CREDIT,
            ),
            TransactionLine(
                line_id="l3",
                amount=Decimal("40.00"),
                direction=BalanceDirection.CREDIT,
            ),
        )
        result = validate_transaction_balance(lines)
        assert result.is_valid is True

    def test_empty_lines_is_balanced(self):
        result = validate_transaction_balance(())
        assert result.is_valid is True


# ============================================================================
# validate_posting_allowed
# ============================================================================


class TestValidatePostingAllowed:
    def test_active_account_allowed(self):
        result = validate_posting_allowed(is_active=True)
        assert result.is_valid is True

    def test_inactive_account_blocked(self):
        result = validate_posting_allowed(is_active=False)
        assert result.is_valid is False
        assert any("inactive" in e for e in result.errors)


# ============================================================================
# Soft warning validators
# ============================================================================


class TestClearingAccountBalance:
    def test_clearing_with_zero_balance_no_warning(self):
        result = validate_clearing_account_balance("clearing", Decimal("0"))
        assert result.is_valid is True
        assert result.warnings == ()

    def test_clearing_with_nonzero_balance_warns(self):
        result = validate_clearing_account_balance("clearing", Decimal("50.00"))
        assert result.is_valid is True
        assert any("non-zero" in w for w in result.warnings)

    def test_non_clearing_no_warning(self):
        result = validate_clearing_account_balance("bank", Decimal("1000"))
        assert result.is_valid is True
        assert result.warnings == ()

    def test_none_semantic_type_no_warning(self):
        result = validate_clearing_account_balance(None, Decimal("500"))
        assert result.is_valid is True
        assert result.warnings == ()


class TestTemporalOrdering:
    def test_posting_after_transaction_ok(self):
        result = validate_temporal_ordering(
            transaction_date=datetime(2024, 1, 1),
            posting_date=datetime(2024, 1, 5),
        )
        assert result.is_valid is True
        assert result.warnings == ()

    def test_posting_before_transaction_warns(self):
        result = validate_temporal_ordering(
            transaction_date=datetime(2024, 1, 5),
            posting_date=datetime(2024, 1, 1),
        )
        assert result.is_valid is True
        assert any("before" in w for w in result.warnings)

    def test_same_date_ok(self):
        dt = datetime(2024, 1, 1)
        result = validate_temporal_ordering(
            transaction_date=dt,
            posting_date=dt,
        )
        assert result.is_valid is True
        assert result.warnings == ()


class TestDimensionHierarchy:
    def test_hierarchical_with_parent_ok(self):
        result = validate_dimension_hierarchy(
            parent_id="p1",
            is_hierarchical=True,
        )
        assert result.is_valid is True
        assert result.warnings == ()

    def test_non_hierarchical_with_parent_warns(self):
        result = validate_dimension_hierarchy(
            parent_id="p1",
            is_hierarchical=False,
        )
        assert result.is_valid is True
        assert any("is_hierarchical is False" in w for w in result.warnings)

    def test_no_parent_no_warning(self):
        result = validate_dimension_hierarchy(
            parent_id=None,
            is_hierarchical=False,
        )
        assert result.is_valid is True
        assert result.warnings == ()


# ============================================================================
# compose_validators
# ============================================================================


class TestComposeValidators:
    def test_compose_two_passing_validators(self):
        def v1(x):
            return ValidationResult.success()

        def v2(x):
            return ValidationResult.success(("info",))

        composed = compose_validators(v1, v2)
        result = composed("anything")
        assert result.is_valid is True
        assert result.warnings == ("info",)

    def test_compose_with_failure(self):
        def v1(x):
            return ValidationResult.success()

        def v2(x):
            return ValidationResult.failure(("broken",))

        composed = compose_validators(v1, v2)
        result = composed("anything")
        assert result.is_valid is False
        assert result.errors == ("broken",)

    def test_compose_aggregates_all(self):
        def v1(x):
            return ValidationResult.failure(("e1",), ("w1",))

        def v2(x):
            return ValidationResult.failure(("e2",))

        def v3(x):
            return ValidationResult.success(("w2",))

        composed = compose_validators(v1, v2, v3)
        result = composed("anything")
        assert result.is_valid is False
        assert result.errors == ("e1", "e2")
        assert result.warnings == ("w1", "w2")

    def test_compose_with_partial(self):
        validator = partial(
            validate_account_balance_direction,
            AccountType.ASSET,
        )
        composed = compose_validators(validator)
        result = composed(BalanceDirection.DEBIT)
        assert result.is_valid is True
