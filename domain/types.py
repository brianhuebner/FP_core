# data_layer.py — Accounting Knowledge Graph Domain Types
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Set


# ============================================================================
# DOMAIN ENUMS — Maps directly to ontology enum definitions
# ============================================================================

class AccountType(Enum):
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    EXPENSE = "expense"
    CONTRA_REVENUE = "contra_revenue"
    CONTRA_EXPENSE = "contra_expense"


class BalanceDirection(Enum):
    DEBIT = "debit"
    CREDIT = "credit"


class SemanticType(Enum):
    CLEARING = "clearing"
    BANK = "bank"
    RECEIVABLE = "receivable"
    PAYABLE = "payable"


class EntityType(Enum):
    LEGAL_ENTITY = "legal_entity"
    DIVISION = "division"
    CONSOLIDATION_GROUP = "consolidation_group"


class DimensionType(Enum):
    LOCATION = "location"
    DEPARTMENT = "department"
    COST_CENTER = "cost_center"
    PRODUCT = "product"
    CUSTOMER = "customer"
    PROJECT = "project"
    CUSTOM = "custom"


class RuleType(Enum):
    SPLIT_BY_DIMENSION = "split_by_dimension"
    PERCENTAGE = "percentage"
    FORMULA = "formula"
    CUSTOM = "custom"


class SourceType(Enum):
    STRIPE = "stripe"
    QUICKBOOKS = "quickbooks"
    XERO = "xero"
    BANK_FEED = "bank_feed"
    MANUAL = "manual"
    API = "api"
    CSV_IMPORT = "csv_import"


# ============================================================================
# GRAPH SCHEMA ENUMS — For graph-level operations (Cypher, validation)
# ============================================================================

class NodeLabel(Enum):
    ACCOUNT = "Account"
    TRANSACTION = "Transaction"
    TRANSACTION_LINE = "TransactionLine"
    ENTITY = "Entity"
    ANALYTICAL_DIMENSION = "AnalyticalDimension"
    ALLOCATION_RULE = "AllocationRule"
    DATA_SOURCE = "DataSource"


class RelationshipType(Enum):
    BELONGS_TO = "BELONGS_TO"
    POSTS_TO = "POSTS_TO"
    ALLOCATED_BY = "ALLOCATED_BY"
    DIMENSIONED_BY = "DIMENSIONED_BY"
    OWNS = "OWNS"
    PARENT_OF = "PARENT_OF"
    CHILD_OF = "CHILD_OF"
    CREATED_FROM = "CREATED_FROM"
    USES_DIMENSION = "USES_DIMENSION"
    APPLIED_TO = "APPLIED_TO"
    PROVIDES = "PROVIDES"
    SYNCED_BY = "SYNCED_BY"


# ============================================================================
# CORE NODE DATACLASSES — 7 Phase 1 domain types (all frozen/immutable)
# ============================================================================

@dataclass(frozen=True)
class Account:
    code: str
    name: str
    account_type: AccountType
    normal_balance: BalanceDirection
    is_active: bool = True
    semantic_type: Optional[SemanticType] = None
    expected_behavior: Optional[str] = None


@dataclass(frozen=True)
class Transaction:
    transaction_id: str
    transaction_date: datetime
    posting_date: datetime
    period: str
    description: str
    is_posted: bool
    created_by: str
    created_at: datetime
    source_system_id: str


@dataclass(frozen=True)
class TransactionLine:
    line_id: str
    amount: Decimal
    direction: BalanceDirection
    memo: Optional[str] = None


@dataclass(frozen=True)
class Entity:
    entity_id: str
    legal_name: str
    entity_type: EntityType
    base_currency: str
    tax_id: Optional[str] = None


@dataclass(frozen=True)
class AnalyticalDimension:
    dimension_id: str
    dimension_type: DimensionType
    name: str
    is_hierarchical: bool = False
    is_required: bool = False
    code: Optional[str] = None
    parent_id: Optional[str] = None


@dataclass(frozen=True)
class AllocationRule:
    rule_id: str
    rule_name: str
    rule_type: RuleType
    is_active: bool
    created_by: str
    created_at: datetime
    version: int


@dataclass(frozen=True)
class DataSource:
    source_id: str
    source_type: SourceType
    connection_config: Dict[str, Any] = field(default_factory=dict)
    last_sync: Optional[datetime] = None


# ============================================================================
# GRAPH INFRASTRUCTURE — Generic graph primitives for Neo4j interaction
# ============================================================================

@dataclass(frozen=True)
class Node:
    id: str
    labels: Set[NodeLabel]
    properties: Dict[str, Any]


@dataclass(frozen=True)
class Relationship:
    id: str
    type: RelationshipType
    start_node_id: str
    end_node_id: str
    properties: Dict[str, Any]


@dataclass(frozen=True)
class GraphPattern:
    nodes: List[Node]
    relationships: List[Relationship]


@dataclass(frozen=True)
class QueryIntent:
    entity_types: Set[NodeLabel]
    relationship_types: Set[RelationshipType]
    filters: Dict[str, Any]
    depth: int


@dataclass(frozen=True)
class Knowledge:
    entities: List[Node]
    connections: List[Relationship]
    context: Dict[str, Any]
    confidence: float
