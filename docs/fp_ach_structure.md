# Functional Programming Architecture for Neo4j-Based Systems
## Complete Reference Guide

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Architectural Overview](#architectural-overview)
3. [Directory Structure](#directory-structure)
4. [Layer 1: Domain Types](#layer-1-domain-types)
5. [Layer 2: Ontology & Validation](#layer-2-ontology--validation)
6. [Layer 3: Pure Domain Logic](#layer-3-pure-domain-logic)
7. [Layer 4: I/O Boundary](#layer-4-io-boundary)
8. [Layer 5: Application/Service Layer](#layer-5-applicationservice-layer)
9. [Layer 6: API/Interface Layer](#layer-6-apiinterface-layer)
10. [Testing Strategy](#testing-strategy)
11. [Key Architectural Principles](#key-architectural-principles)
12. [Benefits](#benefits)
13. [Migration Path](#migration-path)
14. [Quick Start Guide](#quick-start-guide)

---

## Executive Summary

This document outlines a **functional programming (FP) architecture** for building robust, maintainable systems on top of Neo4j graph databases. 

**Core Principle**: Separate pure domain logic from effectful I/O operations, treating the ontology/schema as a type system that enforces correctness.

**Key Benefits**:
- 80%+ of code is pure functions (easy to test, reason about, refactor)
- Schema validation enforced at compile-time and runtime
- Clear data flow through the system
- Trivial parallelization
- High confidence refactoring

---

## Architectural Overview

### Layer Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 6: API/Interface (FastAPI)                           │
│  - HTTP endpoints                                            │
│  - Request/Response handling                                 │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Layer 5: Application/Service                               │
│  - Workflow orchestration                                    │
│  - Composes pure + impure functions                          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────┐                  ┌──────────────────┐
│  Layer 4: I/O        │                  │  Layer 3: Pure   │
│  - Neo4j adapter     │◄─────────────────┤  Domain Logic    │
│  - Database calls    │                  │  - Business rules│
│  - Side effects      │                  │  - Transformations│
└──────────────────────┘                  └──────────────────┘
                                                    ↓
                                          ┌──────────────────┐
                                          │  Layer 2: Schema │
                                          │  - Ontology      │
                                          │  - Validation    │
                                          └──────────────────┘
                                                    ↓
                                          ┌──────────────────┐
                                          │  Layer 1: Types  │
                                          │  - Domain models │
                                          │  - Immutable     │
                                          └──────────────────┘
```

### Dependency Flow

```
API → Application → Domain ← Infrastructure
                      ↑
                  (Zero deps)
```

**Critical**: All dependencies point inward toward the domain. The domain layer has ZERO external dependencies.

---

## Directory Structure

```
neo4j_fp_project/
│
├── domain/                         # Pure domain logic (Layers 1-3)
│   ├── __init__.py
│   ├── types.py                    # Domain types (immutable)
│   ├── ontology.py                 # Schema & validation rules
│   └── logic.py                    # Business logic (pure functions)
│
├── infrastructure/                 # I/O layer (Layer 4)
│   ├── __init__.py
│   └── neo4j_adapter.py            # Database client & adapters
│
├── application/                    # Service layer (Layer 5)
│   ├── __init__.py
│   └── agent_service.py            # Workflow orchestration
│
├── api/                            # Interface layer (Layer 6)
│   ├── __init__.py
│   └── main.py                     # FastAPI endpoints
│
├── tests/
│   ├── __init__.py
│   ├── domain/                     # Pure function tests (fast)
│   │   ├── test_types.py
│   │   ├── test_ontology.py
│   │   └── test_logic.py
│   ├── integration/                # Integration tests (with Neo4j)
│   │   └── test_agent_service.py
│   └── e2e/                        # End-to-end API tests
│       └── test_api.py
│
├── scripts/
│   ├── setup_neo4j.py              # Database initialization
│   └── seed_data.py                # Sample data for testing
│
├── requirements.txt
├── pyproject.toml
├── README.md
└── .env.example
```

---

## Layer 1: Domain Types

**File**: `domain/types.py`

**Purpose**: Encode your Neo4j ontology as immutable types. This is your single source of truth for what exists in your domain.

**Characteristics**:
- Zero dependencies
- 100% immutable (`frozen=True`)
- Type-safe
- Self-documenting

```python
# domain/types.py
from dataclasses import dataclass
from typing import List, Set, Dict, Optional, Literal, Any
from datetime import datetime
from enum import Enum
from decimal import Decimal

# ============================================================================
# ONTOLOGY DEFINITION - Your Neo4j schema as types
# ============================================================================

class NodeLabel(Enum):
    """All valid node labels in your graph"""
    PERSON = "Person"
    COMPANY = "Company"
    TRANSACTION = "Transaction"
    ACCOUNT = "Account"
    DOCUMENT = "Document"
    ADDRESS = "Address"

class RelationshipType(Enum):
    """All valid relationship types"""
    WORKS_FOR = "WORKS_FOR"
    OWNS = "OWNS"
    TRANSACTED_WITH = "TRANSACTED_WITH"
    LINKED_TO = "LINKED_TO"
    REPORTED_IN = "REPORTED_IN"
    LOCATED_AT = "LOCATED_AT"
    MANAGES = "MANAGES"

@dataclass(frozen=True)  # Immutable
class PropertySchema:
    """Defines what properties an entity type must/can have"""
    required: Set[str]
    optional: Set[str]
    types: Dict[str, type]

@dataclass(frozen=True)
class RelationshipSchema:
    """Defines valid relationships for an entity"""
    relationship_type: RelationshipType
    target_labels: Set[NodeLabel]
    properties: PropertySchema

@dataclass(frozen=True)
class EntitySchema:
    """Complete schema definition for a node type"""
    label: NodeLabel
    properties: PropertySchema
    outgoing_relationships: List[RelationshipSchema]
    incoming_relationships: List[RelationshipSchema]

# ============================================================================
# DOMAIN ENTITIES - Runtime representations
# ============================================================================

@dataclass(frozen=True)
class Node:
    """Pure representation of a Neo4j node"""
    id: str  # Neo4j internal ID or custom ID
    labels: Set[NodeLabel]
    properties: Dict[str, Any]
    
@dataclass(frozen=True)
class Relationship:
    """Pure representation of a Neo4j relationship"""
    id: str
    type: RelationshipType
    start_node_id: str
    end_node_id: str
    properties: Dict[str, Any]

@dataclass(frozen=True)
class GraphPattern:
    """A subgraph pattern retrieved from Neo4j"""
    nodes: List[Node]
    relationships: List[Relationship]
    
    def get_node_by_id(self, node_id: str) -> Optional[Node]:
        """Helper to find node by ID"""
        return next((n for n in self.nodes if n.id == node_id), None)
    
    def get_relationships_for_node(self, node_id: str) -> List[Relationship]:
        """Helper to get all relationships for a node"""
        return [
            r for r in self.relationships
            if r.start_node_id == node_id or r.end_node_id == node_id
        ]

# ============================================================================
# QUERY DOMAIN TYPES
# ============================================================================

@dataclass(frozen=True)
class QueryIntent:
    """Represents what the user/agent wants to find"""
    entity_types: Set[NodeLabel]
    relationship_types: Set[RelationshipType]
    filters: Dict[str, Any]
    depth: int
    limit: Optional[int] = None

@dataclass(frozen=True)
class Knowledge:
    """Structured knowledge extracted from graph"""
    entities: List[Node]
    connections: List[Relationship]
    context: Dict[str, Any]
    confidence: float
    
    def get_focus_entity(self) -> Optional[Node]:
        """Get the primary entity of interest"""
        return self.entities[0] if self.entities else None
    
    def get_related_entities(self) -> List[Node]:
        """Get all entities except the focus entity"""
        return self.entities[1:] if len(self.entities) > 1 else []

# ============================================================================
# AGENT DOMAIN TYPES
# ============================================================================

class ActionType(Enum):
    """Types of actions an agent can take"""
    QUERY = "query"
    EXPAND = "expand"
    AGGREGATE = "aggregate"
    RESPOND = "respond"
    ANALYZE = "analyze"

@dataclass(frozen=True)
class AgentAction:
    """An action the agent should take"""
    action_type: ActionType
    parameters: Dict[str, Any]
    reasoning: str
    priority: float = 1.0

@dataclass(frozen=True)
class AgentContext:
    """Context for agent decision-making"""
    current_knowledge: Knowledge
    original_intent: QueryIntent
    conversation_history: List[str]
    previous_actions: List[AgentAction]

# ============================================================================
# RESULT TYPES
# ============================================================================

@dataclass(frozen=True)
class ValidationResult:
    """Result of a validation operation"""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    
    @staticmethod
    def success() -> 'ValidationResult':
        return ValidationResult(is_valid=True, errors=[], warnings=[])
    
    @staticmethod
    def failure(errors: List[str]) -> 'ValidationResult':
        return ValidationResult(is_valid=False, errors=errors, warnings=[])

@dataclass(frozen=True)
class OperationResult:
    """Generic result wrapper"""
    success: bool
    data: Optional[Any]
    error: Optional[str]
    metadata: Dict[str, Any]
    
    @staticmethod
    def ok(data: Any, metadata: Dict[str, Any] = None) -> 'OperationResult':
        return OperationResult(
            success=True,
            data=data,
            error=None,
            metadata=metadata or {}
        )
    
    @staticmethod
    def err(error: str, metadata: Dict[str, Any] = None) -> 'OperationResult':
        return OperationResult(
            success=False,
            data=None,
            error=error,
            metadata=metadata or {}
        )
```

---

## Layer 2: Ontology & Validation

**File**: `domain/ontology.py`

**Purpose**: Enforce schema constraints through pure functions. This is where your business rules about data integrity live.

**Characteristics**:
- Pure functions only
- Composable validations
- Type-driven

```python
# domain/ontology.py
from typing import Tuple, Optional, Dict, List
from domain.types import *

# ============================================================================
# ONTOLOGY REGISTRY - Define your complete schema
# ============================================================================

def create_ontology() -> Dict[NodeLabel, EntitySchema]:
    """
    Central definition of your graph ontology.
    This is your single source of truth for the schema.
    
    Usage:
        ontology = create_ontology()
        person_schema = ontology[NodeLabel.PERSON]
    """
    return {
        NodeLabel.PERSON: EntitySchema(
            label=NodeLabel.PERSON,
            properties=PropertySchema(
                required={"name", "id"},
                optional={"email", "phone", "date_of_birth", "nationality"},
                types={
                    "name": str,
                    "id": str,
                    "email": str,
                    "phone": str,
                    "date_of_birth": str,
                    "nationality": str
                }
            ),
            outgoing_relationships=[
                RelationshipSchema(
                    relationship_type=RelationshipType.WORKS_FOR,
                    target_labels={NodeLabel.COMPANY},
                    properties=PropertySchema(
                        required={"since"},
                        optional={"position", "department", "salary"},
                        types={
                            "since": str,
                            "position": str,
                            "department": str,
                            "salary": float
                        }
                    )
                ),
                RelationshipSchema(
                    relationship_type=RelationshipType.OWNS,
                    target_labels={NodeLabel.ACCOUNT, NodeLabel.COMPANY},
                    properties=PropertySchema(
                        required=set(),
                        optional={"ownership_percentage", "acquired_date"},
                        types={
                            "ownership_percentage": float,
                            "acquired_date": str
                        }
                    )
                ),
                RelationshipSchema(
                    relationship_type=RelationshipType.LOCATED_AT,
                    target_labels={NodeLabel.ADDRESS},
                    properties=PropertySchema(
                        required=set(),
                        optional={"since", "address_type"},
                        types={"since": str, "address_type": str}
                    )
                )
            ],
            incoming_relationships=[
                RelationshipSchema(
                    relationship_type=RelationshipType.MANAGES,
                    target_labels={NodeLabel.PERSON},
                    properties=PropertySchema(
                        required=set(),
                        optional={"since"},
                        types={"since": str}
                    )
                )
            ]
        ),
        
        NodeLabel.COMPANY: EntitySchema(
            label=NodeLabel.COMPANY,
            properties=PropertySchema(
                required={"name", "id", "registration_number"},
                optional={"industry", "founded_date", "country", "revenue"},
                types={
                    "name": str,
                    "id": str,
                    "registration_number": str,
                    "industry": str,
                    "founded_date": str,
                    "country": str,
                    "revenue": float
                }
            ),
            outgoing_relationships=[
                RelationshipSchema(
                    relationship_type=RelationshipType.TRANSACTED_WITH,
                    target_labels={NodeLabel.COMPANY},
                    properties=PropertySchema(
                        required={"amount", "date"},
                        optional={"currency", "description", "transaction_type"},
                        types={
                            "amount": float,
                            "date": str,
                            "currency": str,
                            "description": str,
                            "transaction_type": str
                        }
                    )
                ),
                RelationshipSchema(
                    relationship_type=RelationshipType.LOCATED_AT,
                    target_labels={NodeLabel.ADDRESS},
                    properties=PropertySchema(
                        required=set(),
                        optional={"is_headquarters"},
                        types={"is_headquarters": bool}
                    )
                )
            ],
            incoming_relationships=[]
        ),
        
        NodeLabel.ACCOUNT: EntitySchema(
            label=NodeLabel.ACCOUNT,
            properties=PropertySchema(
                required={"account_number", "id"},
                optional={"balance", "currency", "account_type", "status"},
                types={
                    "account_number": str,
                    "id": str,
                    "balance": float,
                    "currency": str,
                    "account_type": str,
                    "status": str
                }
            ),
            outgoing_relationships=[
                RelationshipSchema(
                    relationship_type=RelationshipType.TRANSACTED_WITH,
                    target_labels={NodeLabel.ACCOUNT},
                    properties=PropertySchema(
                        required={"amount", "date"},
                        optional={"reference", "description"},
                        types={
                            "amount": float,
                            "date": str,
                            "reference": str,
                            "description": str
                        }
                    )
                )
            ],
            incoming_relationships=[]
        ),
        
        NodeLabel.ADDRESS: EntitySchema(
            label=NodeLabel.ADDRESS,
            properties=PropertySchema(
                required={"id", "country"},
                optional={"street", "city", "state", "postal_code", "coordinates"},
                types={
                    "id": str,
                    "country": str,
                    "street": str,
                    "city": str,
                    "state": str,
                    "postal_code": str,
                    "coordinates": str
                }
            ),
            outgoing_relationships=[],
            incoming_relationships=[]
        )
    }

# ============================================================================
# VALIDATION FUNCTIONS - Pure ontology enforcement
# ============================================================================

def validate_node_schema(
    node: Node,
    schema: EntitySchema
) -> ValidationResult:
    """
    Validate a node conforms to its schema definition.
    
    Pure function - same inputs always give same output.
    
    Args:
        node: The node to validate
        schema: The schema it should conform to
        
    Returns:
        ValidationResult with errors if any
    """
    errors = []
    warnings = []
    
    # Check label
    if schema.label not in node.labels:
        errors.append(f"Node missing required label: {schema.label.value}")
    
    # Check required properties
    missing = schema.properties.required - set(node.properties.keys())
    if missing:
        errors.append(f"Node missing required properties: {missing}")
    
    # Check property types
    for prop_name, prop_value in node.properties.items():
        if prop_name in schema.properties.types:
            expected_type = schema.properties.types[prop_name]
            if not isinstance(prop_value, expected_type):
                errors.append(
                    f"Property '{prop_name}' has wrong type: "
                    f"expected {expected_type.__name__}, got {type(prop_value).__name__}"
                )
    
    # Check no unexpected properties
    all_allowed = schema.properties.required | schema.properties.optional
    unexpected = set(node.properties.keys()) - all_allowed
    if unexpected:
        warnings.append(f"Node has unexpected properties: {unexpected}")
    
    if errors:
        return ValidationResult.failure(errors)
    
    return ValidationResult(is_valid=True, errors=[], warnings=warnings)

def validate_relationship_schema(
    rel: Relationship,
    source_node: Node,
    target_node: Node,
    ontology: Dict[NodeLabel, EntitySchema]
) -> ValidationResult:
    """
    Validate a relationship conforms to ontology rules.
    
    Checks:
    - Relationship type is allowed from source
    - Target node label is allowed for this relationship
    - Required properties are present
    """
    errors = []
    
    # Get source schema
    source_labels = list(source_node.labels)
    if not source_labels:
        return ValidationResult.failure(["Source node has no labels"])
    
    source_label = source_labels[0]  # Use primary label
    if source_label not in ontology:
        return ValidationResult.failure([f"Unknown source node label: {source_label.value}"])
    
    source_schema = ontology[source_label]
    
    # Find matching relationship schema
    valid_rel = None
    for rel_schema in source_schema.outgoing_relationships:
        if rel_schema.relationship_type == rel.type:
            valid_rel = rel_schema
            break
    
    if not valid_rel:
        errors.append(
            f"Relationship type {rel.type.value} not allowed from {source_label.value}"
        )
        return ValidationResult.failure(errors)
    
    # Check target node label is allowed
    target_labels = list(target_node.labels)
    if not target_labels:
        return ValidationResult.failure(["Target node has no labels"])
    
    target_label = target_labels[0]
    if target_label not in valid_rel.target_labels:
        errors.append(
            f"Relationship {rel.type.value} cannot connect to {target_label.value}. "
            f"Allowed targets: {[l.value for l in valid_rel.target_labels]}"
        )
    
    # Validate relationship properties
    missing = valid_rel.properties.required - set(rel.properties.keys())
    if missing:
        errors.append(f"Relationship missing required properties: {missing}")
    
    # Check property types
    for prop_name, prop_value in rel.properties.items():
        if prop_name in valid_rel.properties.types:
            expected_type = valid_rel.properties.types[prop_name]
            if not isinstance(prop_value, expected_type):
                errors.append(
                    f"Relationship property '{prop_name}' has wrong type: "
                    f"expected {expected_type.__name__}, got {type(prop_value).__name__}"
                )
    
    if errors:
        return ValidationResult.failure(errors)
    
    return ValidationResult.success()

def validate_graph_pattern(
    pattern: GraphPattern,
    ontology: Dict[NodeLabel, EntitySchema]
) -> ValidationResult:
    """
    Validate an entire subgraph conforms to ontology.
    
    Validates all nodes and relationships in the pattern.
    Returns aggregated errors and warnings.
    """
    all_errors = []
    all_warnings = []
    
    # Validate all nodes
    for node in pattern.nodes:
        if not node.labels:
            all_errors.append(f"Node {node.id} has no labels")
            continue
            
        node_label = list(node.labels)[0]
        if node_label in ontology:
            result = validate_node_schema(node, ontology[node_label])
            if not result.is_valid:
                all_errors.extend([f"Node {node.id}: {e}" for e in result.errors])
            all_warnings.extend([f"Node {node.id}: {w}" for w in result.warnings])
        else:
            all_warnings.append(f"Node {node.id} has unknown label: {node_label.value}")
    
    # Validate all relationships
    node_map = {n.id: n for n in pattern.nodes}
    for rel in pattern.relationships:
        if rel.start_node_id not in node_map:
            all_errors.append(f"Relationship {rel.id} has unknown start node: {rel.start_node_id}")
            continue
        if rel.end_node_id not in node_map:
            all_errors.append(f"Relationship {rel.id} has unknown end node: {rel.end_node_id}")
            continue
            
        source = node_map[rel.start_node_id]
        target = node_map[rel.end_node_id]
        result = validate_relationship_schema(rel, source, target, ontology)
        if not result.is_valid:
            all_errors.extend([f"Relationship {rel.id}: {e}" for e in result.errors])
    
    return ValidationResult(
        is_valid=len(all_errors) == 0,
        errors=all_errors,
        warnings=all_warnings
    )

# ============================================================================
# COMPOSABLE VALIDATION RULES
# ============================================================================

def validate_business_rule_no_self_relationships(
    pattern: GraphPattern
) -> ValidationResult:
    """Business rule: No relationship can connect a node to itself"""
    errors = []
    
    for rel in pattern.relationships:
        if rel.start_node_id == rel.end_node_id:
            errors.append(
                f"Self-relationship detected: {rel.id} connects {rel.start_node_id} to itself"
            )
    
    if errors:
        return ValidationResult.failure(errors)
    return ValidationResult.success()

def validate_business_rule_unique_account_numbers(
    pattern: GraphPattern
) -> ValidationResult:
    """Business rule: Account numbers must be unique"""
    account_numbers = {}
    errors = []
    
    for node in pattern.nodes:
        if NodeLabel.ACCOUNT in node.labels:
            account_num = node.properties.get("account_number")
            if account_num:
                if account_num in account_numbers:
                    errors.append(
                        f"Duplicate account number {account_num} found in nodes "
                        f"{account_numbers[account_num]} and {node.id}"
                    )
                else:
                    account_numbers[account_num] = node.id
    
    if errors:
        return ValidationResult.failure(errors)
    return ValidationResult.success()

def compose_validations(
    *validators
) -> callable:
    """
    Compose multiple validation functions into one.
    
    Example:
        full_validation = compose_validations(
            validate_schema,
            validate_no_self_relationships,
            validate_unique_accounts
        )
    """
    def combined_validator(pattern: GraphPattern, ontology: Dict[NodeLabel, EntitySchema]) -> ValidationResult:
        all_errors = []
        all_warnings = []
        
        for validator in validators:
            # Handle validators that need ontology vs those that don't
            try:
                result = validator(pattern, ontology)
            except TypeError:
                result = validator(pattern)
            
            all_errors.extend(result.errors)
            all_warnings.extend(result.warnings)
        
        return ValidationResult(
            is_valid=len(all_errors) == 0,
            errors=all_errors,
            warnings=all_warnings
        )
    
    return combined_validator
```

---

## Layer 3: Pure Domain Logic

**File**: `domain/logic.py`

**Purpose**: All business logic as pure transformations. This is where your application intelligence lives.

**Characteristics**:
- No I/O
- Composable
- Deterministic
- Easily testable

```python
# domain/logic.py
from typing import List, Set, Dict, Optional, Tuple
from collections import deque
from domain.types import *
from domain.ontology import *

# ============================================================================
# QUERY CONSTRUCTION - Pure functions to build Cypher
# ============================================================================

def intent_to_cypher(
    intent: QueryIntent,
    ontology: Dict[NodeLabel, EntitySchema]
) -> str:
    """
    Convert a query intent into valid Cypher query.
    
    Pure function - same intent always produces same query.
    
    Args:
        intent: What we want to find
        ontology: Schema to ensure we build valid queries
        
    Returns:
        Cypher query string
    """
    
    # Build label clause
    if len(intent.entity_types) == 1:
        label = list(intent.entity_types)[0].value
        match_clause = f"MATCH (n:{label})"
    elif len(intent.entity_types) > 1:
        labels = "|".join([l.value for l in intent.entity_types])
        match_clause = f"MATCH (n:{labels})"
    else:
        match_clause = "MATCH (n)"
    
    # Build filter clause
    where_clauses = []
    for prop, value in intent.filters.items():
        if isinstance(value, str):
            where_clauses.append(f"n.{prop} = '{value}'")
        elif isinstance(value, bool):
            where_clauses.append(f"n.{prop} = {str(value).lower()}")
        elif value is None:
            where_clauses.append(f"n.{prop} IS NULL")
        else:
            where_clauses.append(f"n.{prop} = {value}")
    
    where_clause = " AND ".join(where_clauses) if where_clauses else ""
    
    # Build relationship traversal if depth > 0
    if intent.depth > 0:
        if intent.relationship_types:
            rel_types = "|".join([rt.value for rt in intent.relationship_types])
            rel_pattern = f"-[r:{rel_types}*1..{intent.depth}]->(m)"
        else:
            rel_pattern = f"-[r*1..{intent.depth}]->(m)"
        return_clause = "RETURN n, r, m"
    else:
        rel_pattern = ""
        return_clause = "RETURN n"
    
    # Add limit if specified
    limit_clause = f"LIMIT {intent.limit}" if intent.limit else ""
    
    # Combine all parts
    query_parts = [match_clause]
    if rel_pattern:
        query_parts[0] += rel_pattern
    if where_clause:
        query_parts.append(f"WHERE {where_clause}")
    query_parts.append(return_clause)
    if limit_clause:
        query_parts.append(limit_clause)
    
    return "\n".join(query_parts)

def build_expansion_query(
    entity_id: str,
    depth: int,
    relationship_types: Optional[Set[RelationshipType]] = None
) -> str:
    """
    Build a Cypher query to expand from a specific entity.
    
    Pure function.
    """
    rel_filter = ""
    if relationship_types:
        types = "|".join([rt.value for rt in relationship_types])
        rel_filter = f":{types}"
    
    return f"""
    MATCH (start)
    WHERE elementId(start) = '{entity_id}'
    MATCH path = (start)-[r{rel_filter}*1..{depth}]-(connected)
    RETURN start, r, connected
    """

def build_shortest_path_query(
    start_id: str,
    end_id: str,
    max_depth: int = 5
) -> str:
    """Build query to find shortest path between two nodes"""
    return f"""
    MATCH (start), (end)
    WHERE elementId(start) = '{start_id}' AND elementId(end) = '{end_id}'
    MATCH path = shortestPath((start)-[*1..{max_depth}]-(end))
    RETURN path
    """

# ============================================================================
# KNOWLEDGE EXTRACTION - Transform graph data into structured knowledge
# ============================================================================

def extract_entities_by_type(
    pattern: GraphPattern,
    entity_type: NodeLabel
) -> List[Node]:
    """
    Extract all nodes of a specific type from a graph pattern.
    
    Pure function - filtering operation.
    """
    return [n for n in pattern.nodes if entity_type in n.labels]

def extract_entities_by_property(
    pattern: GraphPattern,
    property_name: str,
    property_value: Any
) -> List[Node]:
    """Extract nodes with a specific property value"""
    return [
        n for n in pattern.nodes
        if n.properties.get(property_name) == property_value
    ]

def find_shortest_path_in_pattern(
    pattern: GraphPattern,
    start_node_id: str,
    end_node_id: str
) -> Optional[List[str]]:
    """
    Find shortest path between two nodes in a pattern.
    
    Pure graph algorithm - deterministic output.
    Uses BFS to find shortest path.
    """
    # Build adjacency list
    graph = {}
    for rel in pattern.relationships:
        if rel.start_node_id not in graph:
            graph[rel.start_node_id] = []
        if rel.end_node_id not in graph:
            graph[rel.end_node_id] = []
        graph[rel.start_node_id].append(rel.end_node_id)
        graph[rel.end_node_id].append(rel.start_node_id)  # Undirected
    
    # BFS
    queue = deque([(start_node_id, [start_node_id])])
    visited = {start_node_id}
    
    while queue:
        current, path = queue.popleft()
        
        if current == end_node_id:
            return path
        
        if current in graph:
            for neighbor in graph[current]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))
    
    return None

def compute_node_degree(
    node: Node,
    pattern: GraphPattern
) -> Tuple[int, int, int]:
    """
    Calculate in-degree, out-degree, and total degree of a node.
    
    Returns: (in_degree, out_degree, total_degree)
    """
    incoming = sum(1 for r in pattern.relationships if r.end_node_id == node.id)
    outgoing = sum(1 for r in pattern.relationships if r.start_node_id == node.id)
    return incoming, outgoing, incoming + outgoing

def compute_entity_importance(
    node: Node,
    pattern: GraphPattern
) -> float:
    """
    Calculate importance score based on connectivity.
    
    Pure function - same inputs always give same score.
    Simple PageRank-style calculation.
    """
    _, _, total_degree = compute_node_degree(node, pattern)
    
    # Normalize by total number of nodes
    max_possible_connections = len(pattern.nodes) - 1
    if max_possible_connections == 0:
        return 0.0
    
    return float(total_degree) / max_possible_connections

def rank_entities_by_relevance(
    entities: List[Node],
    pattern: GraphPattern,
    query_intent: QueryIntent
) -> List[Tuple[Node, float]]:
    """
    Rank entities by relevance to query intent.
    
    Scoring factors:
    - Graph connectivity (importance)
    - Label match with intent
    - Property match with filters
    """
    scored = []
    
    for entity in entities:
        # Base score from importance
        score = compute_entity_importance(entity, pattern)
        
        # Boost if entity type matches intent
        if entity.labels & query_intent.entity_types:
            score *= 1.5
        
        # Boost if properties match filters
        matching_props = sum(
            1 for key, value in query_intent.filters.items()
            if entity.properties.get(key) == value
        )
        score *= (1.0 + 0.2 * matching_props)
        
        scored.append((entity, score))
    
    return sorted(scored, key=lambda x: x[1], reverse=True)

def find_common_neighbors(
    node_a: Node,
    node_b: Node,
    pattern: GraphPattern
) -> List[Node]:
    """Find nodes connected to both node_a and node_b"""
    neighbors_a = set()
    neighbors_b = set()
    
    for rel in pattern.relationships:
        if rel.start_node_id == node_a.id:
            neighbors_a.add(rel.end_node_id)
        if rel.end_node_id == node_a.id:
            neighbors_a.add(rel.start_node_id)
        if rel.start_node_id == node_b.id:
            neighbors_b.add(rel.end_node_id)
        if rel.end_node_id == node_b.id:
            neighbors_b.add(rel.start_node_id)
    
    common_ids = neighbors_a & neighbors_b
    return [n for n in pattern.nodes if n.id in common_ids]

def build_knowledge_context(
    pattern: GraphPattern,
    focus_entity: Node,
    ontology: Dict[NodeLabel, EntitySchema]
) -> Knowledge:
    """
    Build structured knowledge context around a focus entity.
    
    Pure transformation from graph pattern to knowledge structure.
    """
    
    # Find all directly connected entities
    connected_ids = set()
    for rel in pattern.relationships:
        if rel.start_node_id == focus_entity.id:
            connected_ids.add(rel.end_node_id)
        if rel.end_node_id == focus_entity.id:
            connected_ids.add(rel.start_node_id)
    
    connected_entities = [n for n in pattern.nodes if n.id in connected_ids]
    
    # Validate pattern and compute confidence
    validation = validate_graph_pattern(pattern, ontology)
    confidence = 1.0 if validation.is_valid else 0.5
    
    # Compute additional metrics
    in_deg, out_deg, total_deg = compute_node_degree(focus_entity, pattern)
    importance = compute_entity_importance(focus_entity, pattern)
    
    # Build context metadata
    context = {
        "focus_entity_id": focus_entity.id,
        "focus_entity_type": list(focus_entity.labels)[0].value if focus_entity.labels else "unknown",
        "connection_count": len(connected_ids),
        "in_degree": in_deg,
        "out_degree": out_deg,
        "total_degree": total_deg,
        "importance_score": importance,
        "validation_errors": validation.errors,
        "validation_warnings": validation.warnings
    }
    
    # Get relevant relationships
    relevant_rels = [
        r for r in pattern.relationships
        if r.start_node_id == focus_entity.id or r.end_node_id == focus_entity.id
    ]
    
    return Knowledge(
        entities=[focus_entity] + connected_entities,
        connections=relevant_rels,
        context=context,
        confidence=confidence
    )

def aggregate_knowledge(
    knowledge_list: List[Knowledge]
) -> Knowledge:
    """
    Combine multiple knowledge objects into one.
    
    Deduplicates entities and relationships.
    """
    all_entities = []
    all_connections = []
    seen_entity_ids = set()
    seen_rel_ids = set()
    
    for knowledge in knowledge_list:
        for entity in knowledge.entities:
            if entity.id not in seen_entity_ids:
                all_entities.append(entity)
                seen_entity_ids.add(entity.id)
        
        for conn in knowledge.connections:
            if conn.id not in seen_rel_ids:
                all_connections.append(conn)
                seen_rel_ids.add(conn.id)
    
    # Average confidence
    avg_confidence = sum(k.confidence for k in knowledge_list) / len(knowledge_list)
    
    # Combine contexts
    combined_context = {
        "source_count": len(knowledge_list),
        "total_entities": len(all_entities),
        "total_connections": len(all_connections)
    }
    
    return Knowledge(
        entities=all_entities,
        connections=all_connections,
        context=combined_context,
        confidence=avg_confidence
    )

# ============================================================================
# AGENT DECISION LOGIC - Pure reasoning
# ============================================================================

def decide_next_action(
    knowledge: Knowledge,
    original_intent: QueryIntent,
    conversation_history: List[str]
) -> AgentAction:
    """
    Decide what action the agent should take next.
    
    Pure function - deterministic decision making based on:
    - Knowledge quality/confidence
    - Amount of data gathered
    - Validation results
    """
    
    # Check for validation errors
    errors = knowledge.context.get("validation_errors", [])
    if errors:
        return AgentAction(
            action_type=ActionType.RESPOND,
            parameters={
                "message": f"Data quality issues detected",
                "errors": errors
            },
            reasoning="Found schema validation errors that should be reported"
        )
    
    # If confidence is low, need more data
    if knowledge.confidence < 0.7:
        focus_entity = knowledge.get_focus_entity()
        if focus_entity:
            return AgentAction(
                action_type=ActionType.EXPAND,
                parameters={
                    "entity_id": focus_entity.id,
                    "depth": 2
                },
                reasoning="Low confidence - expanding search to gather more context"
            )
    
    # If we have very few entities, broaden search
    if len(knowledge.entities) < 3:
        return AgentAction(
            action_type=ActionType.QUERY,
            parameters={
                "intent": QueryIntent(
                    entity_types=original_intent.entity_types,
                    relationship_types=original_intent.relationship_types,
                    filters={},  # Remove filters to broaden
                    depth=original_intent.depth + 1
                )
            },
            reasoning="Insufficient entities found - broadening search parameters"
        )
    
    # If we have good data, analyze it
    if len(knowledge.entities) >= 3 and knowledge.confidence >= 0.7:
        return AgentAction(
            action_type=ActionType.ANALYZE,
            parameters={
                "knowledge": knowledge
            },
            reasoning="Sufficient high-quality data gathered - ready for analysis"
        )
    
    # Default: respond with what we have
    return AgentAction(
        action_type=ActionType.RESPOND,
        parameters={
            "knowledge": knowledge,
            "summary": f"Found {len(knowledge.entities)} entities with {len(knowledge.connections)} connections"
        },
        reasoning="Gathered available data - ready to respond"
    )

def analyze_entity_relationships(
    entity: Node,
    pattern: GraphPattern
) -> Dict[str, Any]:
    """
    Analyze the relationship structure around an entity.
    
    Returns insights about the entity's connections.
    """
    relationships = pattern.get_relationships_for_node(entity.id)
    
    # Group by type
    by_type = {}
    for rel in relationships:
        rel_type = rel.type.value
        if rel_type not in by_type:
            by_type[rel_type] = []
        by_type[rel_type].append(rel)
    
    # Compute metrics
    in_deg, out_deg, total_deg = compute_node_degree(entity, pattern)
    
    return {
        "total_relationships": len(relationships),
        "in_degree": in_deg,
        "out_degree": out_deg,
        "relationship_types": list(by_type.keys()),
        "type_distribution": {k: len(v) for k, v in by_type.items()},
        "is_hub": total_deg > (len(pattern.nodes) * 0.3)  # Connected to >30% of nodes
    }

def detect_suspicious_patterns(
    pattern: GraphPattern,
    ontology: Dict[NodeLabel, EntitySchema]
) -> List[Dict[str, Any]]:
    """
    Detect potentially suspicious patterns in the graph.
    
    Pure analysis function that looks for:
    - Nodes with unusually high connectivity
    - Circular transaction patterns
    - Isolated subgraphs
    
    Returns list of findings.
    """
    findings = []
    
    # Check for high-degree nodes (potential hubs)
    for node in pattern.nodes:
        _, _, degree = compute_node_degree(node, pattern)
        if degree > len(pattern.nodes) * 0.5:  # Connected to >50% of nodes
            findings.append({
                "type": "high_connectivity",
                "node_id": node.id,
                "degree": degree,
                "message": f"Node has unusually high connectivity ({degree} connections)"
            })
    
    # Check for isolated components
    # (nodes with no connections)
    connected_nodes = set()
    for rel in pattern.relationships:
        connected_nodes.add(rel.start_node_id)
        connected_nodes.add(rel.end_node_id)
    
    isolated = [n for n in pattern.nodes if n.id not in connected_nodes]
    if isolated:
        findings.append({
            "type": "isolated_nodes",
            "count": len(isolated),
            "node_ids": [n.id for n in isolated],
            "message": f"Found {len(isolated)} isolated nodes with no connections"
        })
    
    return findings
```

---

## Layer 4: I/O Boundary

**File**: `infrastructure/neo4j_adapter.py`

**Purpose**: All database interactions isolated here. This is the only place that talks to Neo4j.

**Characteristics**:
- Async operations
- Minimal logic
- Delegates to pure functions
- Clear separation of concerns

```python
# infrastructure/neo4j_adapter.py
from typing import List, Optional, Dict, Any
from neo4j import AsyncGraphDatabase, AsyncDriver
from domain.types import *
from domain.logic import *
from domain.ontology import *
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# NEO4J CLIENT - Effectful operations isolated
# ============================================================================

class Neo4jClient:
    """
    Handles all Neo4j I/O operations.
    
    This is the ONLY place that talks to the database.
    All methods are async and handle connection management.
    Delegates to pure functions for data transformation.
    """
    
    def __init__(self, uri: str, user: str, password: str):
        """
        Initialize Neo4j connection.
        
        Args:
            uri: Neo4j connection URI (e.g., "bolt://localhost:7687")
            user: Username
            password: Password
        """
        self.uri = uri
        self.user = user
        self.driver: Optional[AsyncDriver] = None
        logger.info(f"Neo4j client initialized for {uri}")
    
    async def connect(self):
        """Establish database connection"""
        if not self.driver:
            self.driver = AsyncGraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password)
            )
            logger.info("Neo4j connection established")
    
    async def close(self):
        """Close database connection"""
        if self.driver:
            await self.driver.close()
            self.driver = None
            logger.info("Neo4j connection closed")
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
    
    # ------------------------------------------------------------------------
    # Low-level I/O - minimal logic, just serialization/deserialization
    # ------------------------------------------------------------------------
    
    async def execute_cypher(self, query: str, parameters: Dict = None) -> List[Dict]:
        """
        Execute raw Cypher query and return results.
        
        Args:
            query: Cypher query string
            parameters: Optional query parameters
            
        Returns:
            List of result records as dictionaries
        """
        if not self.driver:
            await self.connect()
        
        async with self.driver.session() as session:
            logger.debug(f"Executing Cypher: {query[:100]}...")
            result = await session.run(query, parameters or {})
            records = await result.data()
            logger.debug(f"Retrieved {len(records)} records")
            return records
    
    async def fetch_node_by_id(self, node_id: str) -> Optional[Node]:
        """
        Fetch a single node by its element ID.
        
        Args:
            node_id: Neo4j element ID
            
        Returns:
            Node object or None if not found
        """
        query = "MATCH (n) WHERE elementId(n) = $node_id RETURN n"
        
        async with self.driver.session() as session:
            result = await session.run(query, {"node_id": node_id})
            record = await result.single()
            
            if not record:
                logger.warning(f"Node {node_id} not found")
                return None
            
            neo4j_node = record["n"]
            return self._neo4j_node_to_domain(neo4j_node)
    
    async def fetch_pattern(self, cypher: str, parameters: Dict = None) -> GraphPattern:
        """
        Execute query and convert results to GraphPattern.
        
        Uses pure conversion functions to transform Neo4j objects
        into domain objects.
        
        Args:
            cypher: Cypher query that returns nodes and relationships
            parameters: Optional query parameters
            
        Returns:
            GraphPattern containing all nodes and relationships from results
        """
        records = await self.execute_cypher(cypher, parameters)
        
        nodes = []
        relationships = []
        seen_nodes = set()
        seen_rels = set()
        
        for record in records:
            # Extract all values from record
            for key, value in record.items():
                # Handle Node objects
                if self._is_neo4j_node(value):
                    node_id = value.element_id
                    if node_id not in seen_nodes:
                        nodes.append(self._neo4j_node_to_domain(value))
                        seen_nodes.add(node_id)
                
                # Handle Relationship objects
                elif self._is_neo4j_relationship(value):
                    rel_id = value.element_id
                    if rel_id not in seen_rels:
                        relationships.append(self._neo4j_rel_to_domain(value))
                        seen_rels.add(rel_id)
                
                # Handle Path objects
                elif self._is_neo4j_path(value):
                    path_nodes, path_rels = self._extract_from_path(value)
                    for node in path_nodes:
                        node_id = node.element_id
                        if node_id not in seen_nodes:
                            nodes.append(self._neo4j_node_to_domain(node))
                            seen_nodes.add(node_id)
                    for rel in path_rels:
                        rel_id = rel.element_id
                        if rel_id not in seen_rels:
                            relationships.append(self._neo4j_rel_to_domain(rel))
                            seen_rels.add(rel_id)
                
                # Handle lists (might contain nodes/rels)
                elif isinstance(value, list):
                    for item in value:
                        if self._is_neo4j_node(item):
                            node_id = item.element_id
                            if node_id not in seen_nodes:
                                nodes.append(self._neo4j_node_to_domain(item))
                                seen_nodes.add(node_id)
                        elif self._is_neo4j_relationship(item):
                            rel_id = item.element_id
                            if rel_id not in seen_rels:
                                relationships.append(self._neo4j_rel_to_domain(item))
                                seen_rels.add(rel_id)
        
        logger.info(f"Fetched pattern: {len(nodes)} nodes, {len(relationships)} relationships")
        return GraphPattern(nodes=nodes, relationships=relationships)
    
    # ------------------------------------------------------------------------
    # Pure conversion functions - could be in separate module
    # ------------------------------------------------------------------------
    
    def _is_neo4j_node(self, obj: Any) -> bool:
        """Check if object is a Neo4j Node"""
        return hasattr(obj, '__class__') and obj.__class__.__name__ == 'Node'
    
    def _is_neo4j_relationship(self, obj: Any) -> bool:
        """Check if object is a Neo4j Relationship"""
        return hasattr(obj, '__class__') and obj.__class__.__name__ == 'Relationship'
    
    def _is_neo4j_path(self, obj: Any) -> bool:
        """Check if object is a Neo4j Path"""
        return hasattr(obj, '__class__') and obj.__class__.__name__ == 'Path'
    
    def _extract_from_path(self, path) -> Tuple[List, List]:
        """Extract nodes and relationships from a Neo4j Path object"""
        nodes = list(path.nodes)
        relationships = list(path.relationships)
        return nodes, relationships
    
    def _neo4j_node_to_domain(self, neo4j_node) -> Node:
        """
        Convert Neo4j node to domain Node.
        
        Pure function - just data transformation.
        """
        try:
            labels = {NodeLabel(label) for label in neo4j_node.labels}
        except ValueError as e:
            # Unknown label - log warning and use string representation
            logger.warning(f"Unknown node label in Neo4j node: {e}")
            labels = set()
        
        return Node(
            id=neo4j_node.element_id,
            labels=labels,
            properties=dict(neo4j_node.items())
        )
    
    def _neo4j_rel_to_domain(self, neo4j_rel) -> Relationship:
        """
        Convert Neo4j relationship to domain Relationship.
        
        Pure function - just data transformation.
        """
        try:
            rel_type = RelationshipType(neo4j_rel.type)
        except ValueError as e:
            # Unknown relationship type
            logger.warning(f"Unknown relationship type: {e}")
            # Use a default or raise
            raise ValueError(f"Relationship type {neo4j_rel.type} not in ontology")
        
        return Relationship(
            id=neo4j_rel.element_id,
            type=rel_type,
            start_node_id=neo4j_rel.start_node.element_id,
            end_node_id=neo4j_rel.end_node.element_id,
            properties=dict(neo4j_rel.items())
        )
    
    # ------------------------------------------------------------------------
    # High-level operations - compose pure functions with I/O
    # ------------------------------------------------------------------------
    
    async def query_by_intent(
        self,
        intent: QueryIntent,
        ontology: Dict[NodeLabel, EntitySchema]
    ) -> GraphPattern:
        """
        Query Neo4j based on intent.
        
        Composes:
        1. Pure function (intent_to_cypher) to build query
        2. Effectful execution (fetch_pattern)
        
        Args:
            intent: What to search for
            ontology: Schema to validate against
            
        Returns:
            GraphPattern with results
        """
        # Pure function builds query
        cypher = intent_to_cypher(intent, ontology)
        logger.info(f"Generated query from intent: {cypher[:100]}...")
        
        # Effectful execution
        pattern = await self.fetch_pattern(cypher)
        
        return pattern
    
    async def expand_from_entity(
        self,
        entity_id: str,
        depth: int,
        relationship_types: Optional[Set[RelationshipType]] = None
    ) -> GraphPattern:
        """
        Expand graph from a specific entity.
        
        Args:
            entity_id: Starting node element ID
            depth: How many hops to traverse
            relationship_types: Optional filter on relationship types
            
        Returns:
            GraphPattern of expanded neighborhood
        """
        # Pure function builds query
        cypher = build_expansion_query(entity_id, depth, relationship_types)
        logger.info(f"Expanding from entity {entity_id} with depth {depth}")
        
        # Effectful execution
        return await self.fetch_pattern(cypher)
    
    async def find_path(
        self,
        start_id: str,
        end_id: str,
        max_depth: int = 5
    ) -> Optional[GraphPattern]:
        """
        Find shortest path between two nodes.
        
        Returns GraphPattern containing the path, or None if no path exists.
        """
        cypher = build_shortest_path_query(start_id, end_id, max_depth)
        logger.info(f"Finding path from {start_id} to {end_id}")
        
        pattern = await self.fetch_pattern(cypher)
        
        # Check if path was found
        if not pattern.nodes:
            logger.info("No path found")
            return None
        
        return pattern
    
    async def create_node(
        self,
        labels: Set[NodeLabel],
        properties: Dict[str, Any],
        ontology: Dict[NodeLabel, EntitySchema]
    ) -> Node:
        """
        Create a new node in Neo4j.
        
        Validates against schema before creating.
        
        Args:
            labels: Node labels
            properties: Node properties
            ontology: Schema to validate against
            
        Returns:
            Created Node
            
        Raises:
            ValueError: If node doesn't match schema
        """
        # Create temporary node for validation
        temp_node = Node(id="temp", labels=labels, properties=properties)
        
        # Validate against schema (pure function)
        if labels:
            primary_label = list(labels)[0]
            if primary_label in ontology:
                validation = validate_node_schema(temp_node, ontology[primary_label])
                if not validation.is_valid:
                    raise ValueError(f"Schema validation failed: {validation.errors}")
        
        # Build create query
        label_str = ":".join([l.value for l in labels])
        
        # Use parameters for safety
        cypher = f"CREATE (n:{label_str} $props) RETURN n"
        
        async with self.driver.session() as session:
            result = await session.run(cypher, {"props": properties})
            record = await result.single()
            created_node = record["n"]
            
            logger.info(f"Created node with labels {label_str}")
            return self._neo4j_node_to_domain(created_node)
    
    async def create_relationship(
        self,
        start_node_id: str,
        end_node_id: str,
        rel_type: RelationshipType,
        properties: Dict[str, Any],
        ontology: Dict[NodeLabel, EntitySchema]
    ) -> Relationship:
        """
        Create a new relationship in Neo4j.
        
        Validates against schema before creating.
        """
        # Fetch nodes to validate relationship
        start_node = await self.fetch_node_by_id(start_node_id)
        end_node = await self.fetch_node_by_id(end_node_id)
        
        if not start_node or not end_node:
            raise ValueError("Start or end node not found")
        
        # Create temporary relationship for validation
        temp_rel = Relationship(
            id="temp",
            type=rel_type,
            start_node_id=start_node_id,
            end_node_id=end_node_id,
            properties=properties
        )
        
        # Validate (pure function)
        validation = validate_relationship_schema(temp_rel, start_node, end_node, ontology)
        if not validation.is_valid:
            raise ValueError(f"Schema validation failed: {validation.errors}")
        
        # Create relationship
        cypher = f"""
        MATCH (start), (end)
        WHERE elementId(start) = $start_id AND elementId(end) = $end_id
        CREATE (start)-[r:{rel_type.value} $props]->(end)
        RETURN r
        """
        
        async with self.driver.session() as session:
            result = await session.run(cypher, {
                "start_id": start_node_id,
                "end_id": end_node_id,
                "props": properties
            })
            record = await result.single()
            created_rel = record["r"]
            
            logger.info(f"Created relationship {rel_type.value}")
            return self._neo4j_rel_to_domain(created_rel)
    
    async def health_check(self) -> bool:
        """Check if database connection is healthy"""
        try:
            await self.execute_cypher("RETURN 1")
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
```

---

## Layer 5: Application/Service Layer

**File**: `application/agent_service.py`

**Purpose**: Orchestrate workflows by composing pure and impure functions.

**Characteristics**:
- Thin orchestration layer
- Clear data flow
- Testable composition

```python
# application/agent_service.py
from typing import List, Optional, Dict, Any
from domain.types import *
from domain.logic import *
from domain.ontology import *
from infrastructure.neo4j_adapter import Neo4jClient
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# AGENT SERVICE - Orchestrates the workflow
# ============================================================================

class KnowledgeAgent:
    """
    High-level agent service that orchestrates queries and reasoning.
    
    Composes pure domain logic with effectful I/O operations.
    This is where the "application flow" lives.
    """
    
    def __init__(
        self,
        neo4j_client: Neo4jClient,
        ontology: Dict[NodeLabel, EntitySchema]
    ):
        """
        Initialize the knowledge agent.
        
        Args:
            neo4j_client: Database client for I/O
            ontology: Schema definition for validation
        """
        self.client = neo4j_client
        self.ontology = ontology
        self.conversation_history: List[str] = []
        logger.info("KnowledgeAgent initialized")
    
    async def process_query(
        self,
        user_query: str,
        entity_types: Set[NodeLabel],
        filters: Optional[Dict[str, Any]] = None,
        depth: int = 1
    ) -> Knowledge:
        """
        Main entry point for processing user queries.
        
        Workflow:
        1. Build intent (pure)
        2. Execute query (impure I/O)
        3. Validate results (pure)
        4. Rank entities (pure)
        5. Build knowledge (pure)
        6. Decide next action (pure)
        7. Execute action if needed (impure)
        
        Args:
            user_query: Natural language query
            entity_types: Types of entities to search for
            filters: Property filters
            depth: Relationship traversal depth
            
        Returns:
            Knowledge object with results and context
        """
        logger.info(f"Processing query: {user_query}")
        
        # Step 1: Build intent (pure)
        intent = QueryIntent(
            entity_types=entity_types,
            relationship_types=set(),  # Empty = all types
            filters=filters or {},
            depth=depth
        )
        
        # Step 2: Execute query (impure I/O)
        pattern = await self.client.query_by_intent(intent, self.ontology)
        logger.info(f"Query returned {len(pattern.nodes)} nodes, {len(pattern.relationships)} relationships")
        
        # Step 3: Validate against ontology (pure)
        validation = validate_graph_pattern(pattern, self.ontology)
        if not validation.is_valid:
            logger.warning(f"Schema validation errors: {validation.errors}")
        if validation.warnings:
            logger.info(f"Schema validation warnings: {validation.warnings}")
        
        # Step 4: Extract and rank entities (pure)
        entities = []
        for entity_type in entity_types:
            entities.extend(extract_entities_by_type(pattern, entity_type))
        
        if not entities:
            logger.info("No entities found matching criteria")
            return Knowledge(
                entities=[],
                connections=[],
                context={"message": "No entities found", "query": user_query},
                confidence=0.0
            )
        
        ranked = rank_entities_by_relevance(entities, pattern, intent)
        logger.info(f"Ranked {len(ranked)} entities")
        
        # Step 5: Build knowledge context (pure)
        focus_entity = ranked[0][0]  # Top ranked entity
        knowledge = build_knowledge_context(pattern, focus_entity, self.ontology)
        
        # Step 6: Decide next action (pure)
        action = decide_next_action(knowledge, intent, self.conversation_history)
        logger.info(f"Decided action: {action.action_type.value} - {action.reasoning}")
        
        # Step 7: Execute action if needed (impure)
        if action.action_type == ActionType.EXPAND:
            expanded_pattern = await self.client.expand_from_entity(
                action.parameters["entity_id"],
                action.parameters["depth"]
            )
            # Rebuild knowledge with expanded data (pure)
            knowledge = build_knowledge_context(expanded_pattern, focus_entity, self.ontology)
            logger.info("Expanded knowledge after low confidence detection")
        
        elif action.action_type == ActionType.QUERY:
            # Recursive query with new intent
            new_intent = action.parameters["intent"]
            pattern = await self.client.query_by_intent(new_intent, self.ontology)
            entities = []
            for et in new_intent.entity_types:
                entities.extend(extract_entities_by_type(pattern, et))
            if entities:
                ranked = rank_entities_by_relevance(entities, pattern, new_intent)
                knowledge = build_knowledge_context(pattern, ranked[0][0], self.ontology)
                logger.info("Re-queried with broader parameters")
        
        # Update conversation history
        self.conversation_history.append(user_query)
        
        return knowledge
    
    async def investigate_entity(
        self,
        entity_id: str,
        investigation_depth: int = 2
    ) -> Knowledge:
        """
        Deep investigation of a specific entity.
        
        Workflow:
        1. Fetch entity (impure)
        2. Validate entity (pure)
        3. Expand neighborhood (impure)
        4. Build comprehensive knowledge (pure)
        5. Enrich with analysis (pure)
        
        Args:
            entity_id: Entity to investigate
            investigation_depth: How deep to expand
            
        Returns:
            Knowledge with detailed entity context
        """
        logger.info(f"Investigating entity {entity_id} with depth {investigation_depth}")
        
        # Step 1: Fetch entity (impure)
        entity = await self.client.fetch_node_by_id(entity_id)
        if not entity:
            raise ValueError(f"Entity {entity_id} not found")
        
        # Step 2: Validate entity (pure)
        if entity.labels:
            entity_label = list(entity.labels)[0]
            if entity_label in self.ontology:
                validation = validate_node_schema(entity, self.ontology[entity_label])
                if not validation.is_valid:
                    logger.warning(f"Entity validation failed: {validation.errors}")
        
        # Step 3: Expand neighborhood (impure)
        pattern = await self.client.expand_from_entity(
            entity_id,
            depth=investigation_depth
        )
        logger.info(f"Expanded to {len(pattern.nodes)} nodes")
        
        # Step 4: Build comprehensive knowledge (pure)
        knowledge = build_knowledge_context(pattern, entity, self.ontology)
        
        # Step 5: Enrich with analysis (pure)
        analysis = analyze_entity_relationships(entity, pattern)
        knowledge.context.update({
            "relationship_analysis": analysis,
            "investigation_depth": investigation_depth
        })
        
        # Detect suspicious patterns (pure)
        suspicious = detect_suspicious_patterns(pattern, self.ontology)
        if suspicious:
            knowledge.context["suspicious_patterns"] = suspicious
            logger.warning(f"Detected {len(suspicious)} suspicious patterns")
        
        return knowledge
    
    async def find_connections(
        self,
        entity_a_id: str,
        entity_b_id: str,
        max_depth: int = 3
    ) -> Optional[List[str]]:
        """
        Find path between two entities.
        
        Workflow:
        1. Fetch path pattern (impure)
        2. Extract path using pure algorithm
        
        Args:
            entity_a_id: First entity
            entity_b_id: Second entity
            max_depth: Maximum path length
            
        Returns:
            List of node IDs forming the path, or None if no path
        """
        logger.info(f"Finding connections between {entity_a_id} and {entity_b_id}")
        
        # Try using Neo4j's built-in shortest path
        pattern = await self.client.find_path(entity_a_id, entity_b_id, max_depth)
        
        if not pattern:
            return None
        
        # Extract path using pure algorithm
        path = find_shortest_path_in_pattern(pattern, entity_a_id, entity_b_id)
        
        if path:
            logger.info(f"Found path of length {len(path)-1}")
        else:
            logger.info("No path found")
        
        return path
    
    async def compare_entities(
        self,
        entity_a_id: str,
        entity_b_id: str
    ) -> Dict[str, Any]:
        """
        Compare two entities by analyzing their neighborhoods.
        
        Pure analysis combining data from multiple sources.
        """
        logger.info(f"Comparing entities {entity_a_id} and {entity_b_id}")
        
        # Fetch both entities with neighborhoods
        pattern_a = await self.client.expand_from_entity(entity_a_id, depth=1)
        pattern_b = await self.client.expand_from_entity(entity_b_id, depth=1)
        
        # Combine patterns
        combined = GraphPattern(
            nodes=pattern_a.nodes + pattern_b.nodes,
            relationships=pattern_a.relationships + pattern_b.relationships
        )
        
        # Get entities
        entity_a = pattern_a.get_node_by_id(entity_a_id)
        entity_b = pattern_b.get_node_by_id(entity_b_id)
        
        if not entity_a or not entity_b:
            raise ValueError("One or both entities not found")
        
        # Analyze each (pure)
        analysis_a = analyze_entity_relationships(entity_a, pattern_a)
        analysis_b = analyze_entity_relationships(entity_b, pattern_b)
        
        # Find common neighbors (pure)
        common = find_common_neighbors(entity_a, entity_b, combined)
        
        # Find path between them (pure)
        path = find_shortest_path_in_pattern(combined, entity_a_id, entity_b_id)
        
        return {
            "entity_a": {
                "id": entity_a_id,
                "labels": [l.value for l in entity_a.labels],
                "analysis": analysis_a
            },
            "entity_b": {
                "id": entity_b_id,
                "labels": [l.value for l in entity_b.labels],
                "analysis": analysis_b
            },
            "common_neighbors": len(common),
            "common_neighbor_ids": [n.id for n in common],
            "shortest_path_length": len(path) - 1 if path else None,
            "directly_connected": len(path) == 2 if path else False
        }
    
    async def aggregate_insights(
        self,
        entity_ids: List[str]
    ) -> Knowledge:
        """
        Aggregate insights across multiple entities.
        
        Gathers knowledge about each entity and combines them.
        """
        logger.info(f"Aggregating insights for {len(entity_ids)} entities")
        
        knowledge_list = []
        
        for entity_id in entity_ids:
            try:
                knowledge = await self.investigate_entity(entity_id, investigation_depth=1)
                knowledge_list.append(knowledge)
            except Exception as e:
                logger.error(f"Failed to investigate {entity_id}: {e}")
        
        # Combine knowledge (pure)
        if not knowledge_list:
            return Knowledge(
                entities=[],
                connections=[],
                context={"message": "No valid entities found"},
                confidence=0.0
            )
        
        aggregated = aggregate_knowledge(knowledge_list)
        logger.info(f"Aggregated {len(aggregated.entities)} unique entities")
        
        return aggregated
    
    async def validate_and_report(
        self,
        pattern: GraphPattern
    ) -> Dict[str, Any]:
        """
        Comprehensive validation report for a graph pattern.
        
        Pure validation with detailed reporting.
        """
        # Schema validation
        schema_validation = validate_graph_pattern(pattern, self.ontology)
        
        # Business rule validations
        no_self_rels = validate_business_rule_no_self_relationships(pattern)
        unique_accounts = validate_business_rule_unique_account_numbers(pattern)
        
        # Suspicious pattern detection
        suspicious = detect_suspicious_patterns(pattern, self.ontology)
        
        return {
            "schema_validation": {
                "is_valid": schema_validation.is_valid,
                "errors": schema_validation.errors,
                "warnings": schema_validation.warnings
            },
            "business_rules": {
                "no_self_relationships": no_self_rels.is_valid,
                "unique_account_numbers": unique_accounts.is_valid
            },
            "suspicious_patterns": suspicious,
            "summary": {
                "total_nodes": len(pattern.nodes),
                "total_relationships": len(pattern.relationships),
                "has_errors": not schema_validation.is_valid,
                "has_warnings": len(schema_validation.warnings) > 0,
                "has_suspicious": len(suspicious) > 0
            }
        }
```

---

## Layer 6: API/Interface Layer

**File**: `api/main.py`

**Purpose**: HTTP interface for the system.

**Characteristics**:
- FastAPI endpoints
- Request/response handling
- Delegates to service layer

```python
# api/main.py
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Set, Dict, Optional, Any
from contextlib import asynccontextmanager
import logging

from application.agent_service import KnowledgeAgent
from infrastructure.neo4j_adapter import Neo4jClient
from domain.types import NodeLabel, RelationshipType
from domain.ontology import create_ontology

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# API MODELS (Request/Response schemas)
# ============================================================================

class QueryRequest(BaseModel):
    """Request model for querying the knowledge graph"""
    query: str = Field(..., description="Natural language query")
    entity_types: List[str] = Field(..., description="Entity types to search for")
    filters: Optional[Dict[str, Any]] = Field(None, description="Property filters")
    depth: int = Field(1, ge=0, le=5, description="Relationship traversal depth (0-5)")

class InvestigateRequest(BaseModel):
    """Request model for investigating an entity"""
    entity_id: str = Field(..., description="Entity ID to investigate")
    depth: int = Field(2, ge=1, le=5, description="Investigation depth (1-5)")

class ConnectionRequest(BaseModel):
    """Request model for finding connections"""
    entity_a_id: str = Field(..., description="First entity ID")
    entity_b_id: str = Field(..., description="Second entity ID")
    max_depth: int = Field(3, ge=1, le=6, description="Maximum path length (1-6)")

class CompareRequest(BaseModel):
    """Request model for comparing entities"""
    entity_a_id: str = Field(..., description="First entity ID")
    entity_b_id: str = Field(..., description="Second entity ID")

class AggregateRequest(BaseModel):
    """Request model for aggregating insights"""
    entity_ids: List[str] = Field(..., description="List of entity IDs")

class NodeResponse(BaseModel):
    """Response model for a node"""
    id: str
    labels: List[str]
    properties: Dict[str, Any]

class RelationshipResponse(BaseModel):
    """Response model for a relationship"""
    id: str
    type: str
    from_node: str = Field(..., alias="from")
    to_node: str = Field(..., alias="to")
    properties: Dict[str, Any]

class KnowledgeResponse(BaseModel):
    """Response model for knowledge"""
    entities: List[NodeResponse]
    connections: List[RelationshipResponse]
    context: Dict[str, Any]
    confidence: float

# ============================================================================
# APPLICATION LIFESPAN
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    # Startup
    logger.info("Starting up application")
    # Initialize any startup tasks here
    yield
    # Shutdown
    logger.info("Shutting down application")

# ============================================================================
# FASTAPI APPLICATION
# ============================================================================

app = FastAPI(
    title="FP Knowledge Graph API",
    description="Functional programming architecture for Neo4j-based knowledge graphs",
    version="1.0.0",
    lifespan=lifespan
)

# ============================================================================
# DEPENDENCY INJECTION
# ============================================================================

async def get_neo4j_client():
    """Dependency: Get Neo4j client"""
    client = Neo4jClient(
        uri="bolt://localhost:7687",
        user="neo4j",
        password="password"  # In production, use environment variables
    )
    try:
        await client.connect()
        yield client
    finally:
        await client.close()

async def get_agent(client: Neo4jClient = Depends(get_neo4j_client)) -> KnowledgeAgent:
    """Dependency: Get knowledge agent"""
    ontology = create_ontology()
    return KnowledgeAgent(client, ontology)

# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get("/health")
async def health_check(client: Neo4jClient = Depends(get_neo4j_client)):
    """Health check endpoint"""
    is_healthy = await client.health_check()
    
    if is_healthy:
        return {"status": "healthy", "database": "connected"}
    else:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed"
        )

@app.post("/query", response_model=KnowledgeResponse)
async def query_knowledge(
    request: QueryRequest,
    agent: KnowledgeAgent = Depends(get_agent)
):
    """
    Query the knowledge graph.
    
    Returns entities matching the query with their relationships.
    """
    try:
        # Convert string labels to enum
        entity_types = {NodeLabel(et) for et in request.entity_types}
        
        # Delegate to service layer
        knowledge = await agent.process_query(
            user_query=request.query,
            entity_types=entity_types,
            filters=request.filters,
            depth=request.depth
        )
        
        # Convert domain types to API response
        return KnowledgeResponse(
            entities=[
                NodeResponse(
                    id=e.id,
                    labels=[l.value for l in e.labels],
                    properties=e.properties
                )
                for e in knowledge.entities
            ],
            connections=[
                RelationshipResponse(
                    id=r.id,
                    type=r.type.value,
                    **{"from": r.start_node_id, "to": r.end_node_id},
                    properties=r.properties
                )
                for r in knowledge.connections
            ],
            context=knowledge.context,
            confidence=knowledge.confidence
        )
    
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Query failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.post("/investigate")
async def investigate_entity(
    request: InvestigateRequest,
    agent: KnowledgeAgent = Depends(get_agent)
):
    """
    Deep investigation of a specific entity.
    
    Returns detailed information about the entity and its neighborhood.
    """
    try:
        knowledge = await agent.investigate_entity(
            entity_id=request.entity_id,
            investigation_depth=request.depth
        )
        
        focus = knowledge.get_focus_entity()
        
        return {
            "focus_entity": NodeResponse(
                id=focus.id,
                labels=[l.value for l in focus.labels],
                properties=focus.properties
            ) if focus else None,
            "neighborhood": [
                NodeResponse(
                    id=e.id,
                    labels=[l.value for l in e.labels],
                    properties=e.properties
                )
                for e in knowledge.get_related_entities()
            ],
            "connections": [
                RelationshipResponse(
                    id=r.id,
                    type=r.type.value,
                    **{"from": r.start_node_id, "to": r.end_node_id},
                    properties=r.properties
                )
                for r in knowledge.connections
            ],
            "analysis": knowledge.context,
            "confidence": knowledge.confidence
        }
    
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Investigation failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.post("/connections")
async def find_connections(
    request: ConnectionRequest,
    agent: KnowledgeAgent = Depends(get_agent)
):
    """
    Find connections between two entities.
    
    Returns the shortest path if one exists.
    """
    try:
        path = await agent.find_connections(
            entity_a_id=request.entity_a_id,
            entity_b_id=request.entity_b_id,
            max_depth=request.max_depth
        )
        
        if path is None:
            return {
                "connected": False,
                "path": None,
                "distance": None
            }
        
        return {
            "connected": True,
            "path": path,
            "distance": len(path) - 1
        }
    
    except Exception as e:
        logger.error(f"Connection search failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.post("/compare")
async def compare_entities(
    request: CompareRequest,
    agent: KnowledgeAgent = Depends(get_agent)
):
    """
    Compare two entities.
    
    Returns analysis of both entities and their relationships.
    """
    try:
        comparison = await agent.compare_entities(
            entity_a_id=request.entity_a_id,
            entity_b_id=request.entity_b_id
        )
        
        return comparison
    
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Comparison failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.post("/aggregate", response_model=KnowledgeResponse)
async def aggregate_insights(
    request: AggregateRequest,
    agent: KnowledgeAgent = Depends(get_agent)
):
    """
    Aggregate insights across multiple entities.
    
    Returns combined knowledge from all entities.
    """
    try:
        knowledge = await agent.aggregate_insights(entity_ids=request.entity_ids)
        
        return KnowledgeResponse(
            entities=[
                NodeResponse(
                    id=e.id,
                    labels=[l.value for l in e.labels],
                    properties=e.properties
                )
                for e in knowledge.entities
            ],
            connections=[
                RelationshipResponse(
                    id=r.id,
                    type=r.type.value,
                    **{"from": r.start_node_id, "to": r.end_node_id},
                    properties=r.properties
                )
                for r in knowledge.connections
            ],
            context=knowledge.context,
            confidence=knowledge.confidence
        )
    
    except Exception as e:
        logger.error(f"Aggregation failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.get("/ontology")
async def get_ontology():
    """
    Get the current ontology/schema definition.
    
    Returns the complete schema for all entity types.
    """
    ontology = create_ontology()
    
    return {
        label.value: {
            "required_properties": list(schema.properties.required),
            "optional_properties": list(schema.properties.optional),
            "property_types": {k: v.__name__ for k, v in schema.properties.types.items()},
            "outgoing_relationships": [
                {
                    "type": rel.relationship_type.value,
                    "target_labels": [l.value for l in rel.target_labels]
                }
                for rel in schema.outgoing_relationships
            ]
        }
        for label, schema in ontology.items()
    }

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"}
    )

# ============================================================================
# STARTUP MESSAGE
# ============================================================================

@app.on_event("startup")
async def startup_event():
    logger.info("="*60)
    logger.info("FP Knowledge Graph API Started")
    logger.info("Functional Programming Architecture")
    logger.info("="*60)
```

---

## Testing Strategy

### Unit Tests (Pure Functions)

**File**: `tests/domain/test_logic.py`

```python
# tests/domain/test_logic.py
import pytest
from domain.types import *
from domain.logic import *
from domain.ontology import create_ontology

def test_intent_to_cypher_basic():
    """Test basic Cypher query generation"""
    intent = QueryIntent(
        entity_types={NodeLabel.PERSON},
        relationship_types=set(),
        filters={"name": "John"},
        depth=0
    )
    
    cypher = intent_to_cypher(intent, {})
    
    assert "MATCH (n:Person)" in cypher
    assert "n.name = 'John'" in cypher
    assert "RETURN n" in cypher

def test_intent_to_cypher_with_depth():
    """Test Cypher generation with relationship traversal"""
    intent = QueryIntent(
        entity_types={NodeLabel.PERSON},
        relationship_types={RelationshipType.WORKS_FOR},
        filters={},
        depth=2
    )
    
    cypher = intent_to_cypher(intent, {})
    
    assert "MATCH (n:Person)" in cypher
    assert "-[r:WORKS_FOR*1..2]->" in cypher
    assert "RETURN n, r, m" in cypher

def test_extract_entities_by_type():
    """Test entity extraction by type"""
    nodes = [
        Node("1", {NodeLabel.PERSON}, {"name": "Alice"}),
        Node("2", {NodeLabel.COMPANY}, {"name": "Acme"}),
        Node("3", {NodeLabel.PERSON}, {"name": "Bob"})
    ]
    pattern = GraphPattern(nodes=nodes, relationships=[])
    
    people = extract_entities_by_type(pattern, NodeLabel.PERSON)
    
    assert len(people) == 2
    assert all(NodeLabel.PERSON in n.labels for n in people)

def test_compute_entity_importance():
    """Test importance calculation"""
    node = Node("1", {NodeLabel.PERSON}, {})
    pattern = GraphPattern(
        nodes=[
            node,
            Node("2", {NodeLabel.COMPANY}, {}),
            Node("3", {NodeLabel.ACCOUNT}, {})
        ],
        relationships=[
            Relationship("r1", RelationshipType.WORKS_FOR, "1", "2", {}),
            Relationship("r2", RelationshipType.OWNS, "1", "3", {}),
        ]
    )
    
    score = compute_entity_importance(node, pattern)
    
    # Node has 2 connections out of max 2 possible (3 nodes - 1)
    assert score == 1.0

def test_find_shortest_path():
    """Test shortest path algorithm"""
    nodes = [
        Node("1", {NodeLabel.PERSON}, {}),
        Node("2", {NodeLabel.COMPANY}, {}),
        Node("3", {NodeLabel.ACCOUNT}, {})
    ]
    rels = [
        Relationship("r1", RelationshipType.WORKS_FOR, "1", "2", {}),
        Relationship("r2", RelationshipType.OWNS, "2", "3", {}),
    ]
    pattern = GraphPattern(nodes=nodes, relationships=rels)
    
    path = find_shortest_path_in_pattern(pattern, "1", "3")
    
    assert path == ["1", "2", "3"]

def test_rank_entities_by_relevance():
    """Test entity ranking"""
    nodes = [
        Node("1", {NodeLabel.PERSON}, {"name": "Alice"}),
        Node("2", {NodeLabel.PERSON}, {"name": "Bob"}),
    ]
    pattern = GraphPattern(
        nodes=nodes,
        relationships=[
            Relationship("r1", RelationshipType.WORKS_FOR, "1", "3", {}),
            Relationship("r2", RelationshipType.WORKS_FOR, "1", "4", {}),
        ]
    )
    intent = QueryIntent(
        entity_types={NodeLabel.PERSON},
        relationship_types=set(),
        filters={"name": "Alice"},
        depth=0
    )
    
    ranked = rank_entities_by_relevance(nodes, pattern, intent)
    
    # Alice should rank higher (matches filter)
    assert ranked[0][0].properties["name"] == "Alice"
    assert ranked[0][1] > ranked[1][1]
```

**File**: `tests/domain/test_ontology.py`

```python
# tests/domain/test_ontology.py
import pytest
from domain.types import *
from domain.ontology import *

def test_validate_node_schema_valid():
    """Test validation of valid node"""
    ontology = create_ontology()
    node = Node(
        id="1",
        labels={NodeLabel.PERSON},
        properties={
            "id": "p1",
            "name": "Alice",
            "email": "alice@example.com"
        }
    )
    
    result = validate_node_schema(node, ontology[NodeLabel.PERSON])
    
    assert result.is_valid
    assert len(result.errors) == 0

def test_validate_node_schema_missing_required():
    """Test validation catches missing required properties"""
    ontology = create_ontology()
    node = Node(
        id="1",
        labels={NodeLabel.PERSON},
        properties={"email": "alice@example.com"}  # Missing 'name' and 'id'
    )
    
    result = validate_node_schema(node, ontology[NodeLabel.PERSON])
    
    assert not result.is_valid
    assert any("missing required properties" in err.lower() for err in result.errors)

def test_validate_node_schema_wrong_type():
    """Test validation catches wrong property types"""
    ontology = create_ontology()
    node = Node(
        id="1",
        labels={NodeLabel.PERSON},
        properties={
            "id": "p1",
            "name": 12345  # Should be string
        }
    )
    
    result = validate_node_schema(node, ontology[NodeLabel.PERSON])
    
    assert not result.is_valid
    assert any("wrong type" in err.lower() for err in result.errors)

def test_validate_relationship_schema_valid():
    """Test validation of valid relationship"""
    ontology = create_ontology()
    
    person = Node("1", {NodeLabel.PERSON}, {"id": "p1", "name": "Alice"})
    company = Node("2", {NodeLabel.COMPANY}, {"id": "c1", "name": "Acme", "registration_number": "123"})
    rel = Relationship(
        "r1",
        RelationshipType.WORKS_FOR,
        "1",
        "2",
        {"since": "2020"}
    )
    
    result = validate_relationship_schema(rel, person, company, ontology)
    
    assert result.is_valid

def test_validate_relationship_schema_invalid_target():
    """Test validation catches invalid target type"""
    ontology = create_ontology()
    
    person = Node("1", {NodeLabel.PERSON}, {"id": "p1", "name": "Alice"})
    account = Node("2", {NodeLabel.ACCOUNT}, {"id": "a1", "account_number": "123"})
    rel = Relationship(
        "r1",
        RelationshipType.WORKS_FOR,  # Can only go to COMPANY
        "1",
        "2",
        {"since": "2020"}
    )
    
    result = validate_relationship_schema(rel, person, account, ontology)
    
    assert not result.is_valid
    assert any("cannot connect to" in err.lower() for err in result.errors)

def test_validate_graph_pattern():
    """Test validation of complete graph pattern"""
    ontology = create_ontology()
    
    pattern = GraphPattern(
        nodes=[
            Node("1", {NodeLabel.PERSON}, {"id": "p1", "name": "Alice"}),
            Node("2", {NodeLabel.COMPANY}, {"id": "c1", "name": "Acme", "registration_number": "123"})
        ],
        relationships=[
            Relationship("r1", RelationshipType.WORKS_FOR, "1", "2", {"since": "2020"})
        ]
    )
    
    result = validate_graph_pattern(pattern, ontology)
    
    assert result.is_valid
    assert len(result.errors) == 0

def test_business_rule_no_self_relationships():
    """Test business rule validation"""
    pattern = GraphPattern(
        nodes=[Node("1", {NodeLabel.PERSON}, {})],
        relationships=[
            Relationship("r1", RelationshipType.MANAGES, "1", "1", {})  # Self-loop
        ]
    )
    
    result = validate_business_rule_no_self_relationships(pattern)
    
    assert not result.is_valid
    assert any("self-relationship" in err.lower() for err in result.errors)
```

### Integration Tests

**File**: `tests/integration/test_agent_service.py`

```python
# tests/integration/test_agent_service.py
import pytest
import asyncio
from application.agent_service import KnowledgeAgent
from infrastructure.neo4j_adapter import Neo4jClient
from domain.types import NodeLabel
from domain.ontology import create_ontology

@pytest.fixture
async def neo4j_client():
    """Fixture: Neo4j client"""
    client = Neo4jClient(
        uri="bolt://localhost:7687",
        user="neo4j",
        password="test_password"
    )
    await client.connect()
    yield client
    await client.close()

@pytest.fixture
async def agent(neo4j_client):
    """Fixture: Knowledge agent"""
    ontology = create_ontology()
    return KnowledgeAgent(neo4j_client, ontology)

@pytest.mark.asyncio
async def test_process_query_integration(agent):
    """Integration test: Process query end-to-end"""
    knowledge = await agent.process_query(
        user_query="Find all people",
        entity_types={NodeLabel.PERSON},
        filters={}
    )
    
    assert knowledge.confidence >= 0
    assert isinstance(knowledge.entities, list)
    assert isinstance(knowledge.connections, list)

@pytest.mark.asyncio
async def test_investigate_entity_integration(agent, neo4j_client):
    """Integration test: Investigate entity"""
    # First, create a test entity
    node = await neo4j_client.create_node(
        labels={NodeLabel.PERSON},
        properties={"id": "test123", "name": "Test Person"},
        ontology=create_ontology()
    )
    
    # Investigate it
    knowledge = await agent.investigate_entity(node.id, investigation_depth=1)
    
    assert knowledge.get_focus_entity() is not None
    assert knowledge.confidence > 0
```

---

## Key Architectural Principles

### 1. Immutability
All domain types are immutable (`frozen=True`). State changes are expressed as transformations that return new values.

### 2. Separation of Concerns
- **Domain** = what (pure logic, no dependencies)
- **Infrastructure** = how (I/O, frameworks)
- **Application** = when (orchestration)

### 3. Dependency Direction
```
API → Application → Domain ← Infrastructure
                      ↑
                  (Zero deps)
```
All arrows point inward. Domain has ZERO external dependencies.

### 4. Explicit Data Flow
Every function signature tells you exactly what goes in and what comes out. No hidden state.

### 5. Validation at Boundaries
- Validate when data enters (API layer)
- Validate when data leaves external systems (Infrastructure layer)
- Domain assumes valid data

---

## Benefits

### 1. Testability
- 80%+ of code is pure functions
- No mocks needed for domain logic
- Fast, deterministic tests

### 2. Debugging
- Follow data transformations
- No hidden mutations
- Clear cause and effect

### 3. Refactoring
- Change implementation, keep interface
- Type system catches errors
- High confidence changes

### 4. Concurrency
- Pure functions parallelize trivially
- No race conditions in domain logic
- Safe async operations

### 5. Reasoning
- Read any function in isolation
- Understand behavior completely
- No global state to track

---

## Migration Path

If you have existing code:

1. **Start with types** (Week 1)
   - Define your ontology as immutable types
   - No code changes yet

2. **Extract pure logic** (Week 2-3)
   - Move business rules to pure functions
   - Keep old code working alongside

3. **Wrap I/O** (Week 4)
   - Isolate Neo4j calls in adapter layer
   - Use adapter from both old and new code

4. **Compose gradually** (Week 5-6)
   - Build service layer using both approaches
   - Migrate one workflow at a time

5. **Test incrementally** (Ongoing)
   - Add unit tests for pure functions first
   - Integration tests as you migrate

---

## Quick Start Guide

### 1. Install Dependencies

```bash
pip install fastapi uvicorn neo4j python-dotenv pydantic
```

### 2. Set Up Neo4j

```bash
# Using Docker
docker run \
    --name neo4j \
    -p 7474:7474 -p 7687:7687 \
    -e NEO4J_AUTH=neo4j/password \
    neo4j:latest
```

### 3. Create Project Structure

```bash
mkdir -p neo4j_fp_project/{domain,infrastructure,application,api,tests}
touch neo4j_fp_project/domain/{__init__.py,types.py,ontology.py,logic.py}
touch neo4j_fp_project/infrastructure/{__init__.py,neo4j_adapter.py}
touch neo4j_fp_project/application/{__init__.py,agent_service.py}
touch neo4j_fp_project/api/{__init__.py,main.py}
```

### 4. Copy Code Files

Copy the code from each section into the corresponding files.

### 5. Run the API

```bash
cd neo4j_fp_project
uvicorn api.main:app --reload
```

### 6. Test the API

```bash
curl http://localhost:8000/health
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Find people",
    "entity_types": ["Person"],
    "depth": 1
  }'
```

---

## Conclusion

This FP architecture provides:

- **Correctness** through type-driven development
- **Maintainability** through pure functions
- **Testability** through separation of concerns
- **Scalability** through composable design

The ontology/schema is your single source of truth, enforced at every layer through pure validation functions. Business logic is expressed as composable transformations. I/O is isolated at the edges.

**Result**: A system that's easy to understand, test, refactor, and extend.