# FP_core — Core Setup Before Skill Development

## Current State

- **`data_layer.py`** — 7 domain enums, 7 frozen dataclasses, 5 graph infrastructure types. Solid.
- **`ontology.md`** — Design vision, philosophy, implementation phases.
- **`outline_skill.md`** — Neo4j Cypher skill reference (build later).
- **`main.py`** — Placeholder.

## What's Missing

### 1. Project Packaging
- `pyproject.toml` with dependencies (`neo4j` driver, etc.)
- No dependency management exists yet

### 2. Neo4j Connection Layer
- Driver setup, session management, connection config
- Schema bootstrapping (constraints on IDs, indexes on `code`, `period`, etc.)

### 3. Dataclass <-> Neo4j Mapping
- Serialization: frozen dataclasses to Neo4j node properties
- Deserialization: Neo4j records back to dataclasses
- Type handling: `Decimal`, `datetime`, `Enum` to Neo4j-compatible types

### 4. Repository Layer
- CRUD operations for all 7 node types
- Relationship creation (BELONGS_TO, POSTS_TO, DIMENSIONED_BY, etc.)
- Query methods aligned with traceability patterns (trace, track, drilldown)

### 5. Validation Logic
- Accounting equation: `sum(debits) == sum(credits)` per transaction
- Clearing account balance check (should net to zero)
- Normal balance anomaly detection
- Hard blocks vs. soft warnings (per ontology.md)

### 6. Transaction Builder
- Factory/builder for constructing balanced transactions with lines
- Frozen dataclasses need a construction pattern to enforce invariants

### 7. Tests
- Nothing is testable yet

## Build Order

```
packaging -> connection -> mapping -> repository -> validation -> transaction builder -> tests
```