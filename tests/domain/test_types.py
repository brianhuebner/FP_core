# tests/domain/test_types.py — Smoke tests for Layer 1 domain types
from datetime import datetime
from decimal import Decimal

import pytest

from domain.types import (
    Account,
    AccountType,
    AnalyticalDimension,
    BalanceDirection,
    DataSource,
    DimensionType,
    Entity,
    EntityType,
    Node,
    NodeLabel,
    RelationshipType,
    RuleType,
    SemanticType,
    SourceType,
    Transaction,
    TransactionLine,
)

# ============================================================================
# Enum member counts
# ============================================================================


class TestEnumMemberCounts:
    def test_account_type_has_7_members(self):
        assert len(AccountType) == 7

    def test_balance_direction_has_2_members(self):
        assert len(BalanceDirection) == 2

    def test_semantic_type_has_4_members(self):
        assert len(SemanticType) == 4

    def test_entity_type_has_3_members(self):
        assert len(EntityType) == 3

    def test_dimension_type_has_7_members(self):
        assert len(DimensionType) == 7

    def test_rule_type_has_4_members(self):
        assert len(RuleType) == 4

    def test_source_type_has_7_members(self):
        assert len(SourceType) == 7

    def test_node_label_has_19_members(self):
        assert len(NodeLabel) == 19

    def test_relationship_type_has_26_members(self):
        assert len(RelationshipType) == 26


# ============================================================================
# Frozen dataclass checks
# ============================================================================


class TestFrozenDataclasses:
    def test_account_is_frozen(self):
        acct = Account(
            code="1000",
            name="Cash",
            account_type=AccountType.ASSET,
            normal_balance=BalanceDirection.DEBIT,
        )
        with pytest.raises(AttributeError):
            acct.code = "2000"

    def test_transaction_is_frozen(self):
        now = datetime.now()
        txn = Transaction(
            transaction_id="t1",
            transaction_date=now,
            posting_date=now,
            period="2024-01",
            description="Test",
            is_posted=True,
            created_by="user",
            created_at=now,
            source_system_id="sys1",
        )
        with pytest.raises(AttributeError):
            txn.description = "changed"

    def test_transaction_line_is_frozen(self):
        line = TransactionLine(
            line_id="l1",
            amount=Decimal("100"),
            direction=BalanceDirection.DEBIT,
        )
        with pytest.raises(AttributeError):
            line.amount = Decimal("200")

    def test_entity_is_frozen(self):
        ent = Entity(
            entity_id="e1",
            legal_name="Acme",
            entity_type=EntityType.LEGAL_ENTITY,
            base_currency="USD",
        )
        with pytest.raises(AttributeError):
            ent.legal_name = "changed"

    def test_analytical_dimension_is_frozen(self):
        dim = AnalyticalDimension(
            dimension_id="d1",
            dimension_type=DimensionType.DEPARTMENT,
            name="Sales",
        )
        with pytest.raises(AttributeError):
            dim.name = "changed"

    def test_node_is_frozen(self):
        node = Node(id="n1", labels={NodeLabel.ACCOUNT}, properties={})
        with pytest.raises(AttributeError):
            node.id = "n2"


# ============================================================================
# Default values
# ============================================================================


class TestDefaults:
    def test_account_defaults(self):
        acct = Account(
            code="1000",
            name="Cash",
            account_type=AccountType.ASSET,
            normal_balance=BalanceDirection.DEBIT,
        )
        assert acct.is_active is True
        assert acct.semantic_type is None
        assert acct.expected_behavior is None

    def test_transaction_line_defaults(self):
        line = TransactionLine(
            line_id="l1",
            amount=Decimal("100"),
            direction=BalanceDirection.DEBIT,
        )
        assert line.memo is None

    def test_analytical_dimension_defaults(self):
        dim = AnalyticalDimension(
            dimension_id="d1",
            dimension_type=DimensionType.DEPARTMENT,
            name="Sales",
        )
        assert dim.is_hierarchical is False
        assert dim.is_required is False
        assert dim.code is None
        assert dim.parent_id is None

    def test_data_source_defaults(self):
        ds = DataSource(
            source_id="s1",
            source_type=SourceType.MANUAL,
        )
        assert ds.connection_config == {}
        assert ds.last_sync is None
