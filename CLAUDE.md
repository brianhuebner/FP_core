# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FP_core is an **accounting knowledge graph** built on a domain-driven ontology. It models accounting concepts (accounts, transactions, entities, dimensions) as a graph with typed nodes and relationships, designed for Neo4j. The system enforces double-entry accounting semantics while allowing professional flexibility — it guides but doesn't block. It also models recipe/pipeline concepts for transforming source data into accounting entries. Implements Layers 1-4: types, ontology/validation, pure logic, and Neo4j persistence.

## Branch

Main branch: `main`

## Commands

```bash
# Run all tests
pytest

# Run a single test file
pytest tests/domain/test_types.py
pytest tests/domain/test_ontology.py
pytest tests/domain/test_types_recipe.py
pytest tests/domain/test_ontology_recipe.py
pytest tests/domain/test_logic.py
pytest tests/persistence/test_merge_keys.py
pytest tests/persistence/test_serializers.py
pytest tests/persistence/test_deserializers.py

# Run a specific test class or method
pytest tests/domain/test_ontology.py::TestValidateTransactionBalance::test_balanced_transaction

# Integration tests (requires NEO4J_URI, NEO4J_PASSWORD env vars)
pytest tests/persistence/test_operations.py

# Activate virtualenv
source .venv/bin/activate
```

Python 3.12, no build step, no linter configured. Dependencies beyond stdlib: pytest, neo4j>=5.0.

## File Map

```
domain/
  __init__.py          # Public API — re-exports everything via __all__ (~180 lines)
  types.py             # Layer 1: core enums + frozen dataclasses (~237 lines)
  types_recipe.py      # Layer 1: recipe enums + frozen dataclasses (~150 lines)
  ontology.py          # Layer 2: core schema, constraints, validators (~500 lines)
  ontology_recipe.py   # Layer 2: recipe schema, constraints, validators (~686 lines)
  logic.py             # Layer 3: pure functions for recipe graph building (~277 lines)
persistence/
  __init__.py          # Public API — re-exports everything via __all__
  merge_keys.py        # Layer 4: NodeLabel -> MERGE identity properties
  serializers.py       # Layer 4: pure GraphPattern -> (cypher, params)
  deserializers.py     # Layer 4: pure Neo4j records -> domain objects
  connection.py        # Layer 4: Neo4jConnection wrapper (only neo4j import)
  operations.py        # Layer 4: save/load/delete/verify pattern
tests/
  domain/
    test_types.py          # Layer 1 core type tests (~160 lines)
    test_types_recipe.py   # Layer 1 recipe type tests (~237 lines)
    test_ontology.py       # Layer 2 core ontology tests (~649 lines)
    test_ontology_recipe.py # Layer 2 recipe ontology tests (~643 lines)
    test_logic.py          # Layer 3 logic tests (~740 lines)
  persistence/
    conftest.py            # Neo4j fixtures + skip markers
    test_merge_keys.py     # Merge key registry tests
    test_serializers.py    # Cypher generation tests (pure, no driver)
    test_deserializers.py  # Record->domain conversion tests (pure, no driver)
    test_operations.py     # Integration tests (skipped without NEO4J_URI)
docs/ontology.md       # Design doc: full ontology rationale (~453 lines)
main.py                # Placeholder entry point (~16 lines)
```

## Architecture

**Layer 1 — Types** (`types.py`, `types_recipe.py`): Frozen dataclasses and enums. Core: 7 accounting node types + graph primitives (Node, Relationship, GraphPattern, QueryIntent, Knowledge). Recipe: 5 enums + 9 dataclasses for pipeline modeling. `Node.extra_labels` (FrozenSet[str]) supports reference data labels outside NodeLabel.

**Layer 2 — Ontology & Validation** (`ontology.py`, `ontology_recipe.py`): Schema definitions (PropertySchema, EntitySchema, RelationshipConstraint), ontology dicts, constraint dicts, and pure validation functions returning `ValidationResult`. Hard blocks return errors; soft warnings return warnings but stay valid. `merged_ontology()` and `merged_relationship_constraints()` combine core + recipe schemas — not a naive dict merge, because cross-layer relationships require updating both sides.

**Layer 3 — Logic** (`logic.py`): Pure functions (no I/O) for building and validating recipe graph patterns: `build_source_schema_pattern`, `build_recipe_pattern`, `validate_recipe`, `extract_measures_for_schema`, `extract_debit_credit_slots`, `build_output_format_pattern`, `extract_output_columns`, `extract_validation_rules`, `extract_batch_format`, `validate_output_format`, `compose_pipeline_pattern`, `validate_pipeline_connectivity`.

**Layer 4 — Persistence** (`persistence/`): Neo4j I/O layer. `domain/` stays pure — zero I/O imports. `merge_keys.py` maps NodeLabel to MERGE identity properties. `serializers.py` and `deserializers.py` are pure functions (testable without Neo4j). Only `connection.py` imports the `neo4j` driver. `operations.py` composes serializers + connection for save/load/delete. Uses MERGE for idempotent writes. `Node.id` round-trips via a `_node_id` property stored in Neo4j.

**Public API** (`domain/__init__.py`): Re-exports everything from all layers via `__all__`. Import from `domain` directly. Persistence has its own package: import from `persistence`.

### Canonical Counts

These are test-asserted — do not change without updating both code and tests:

| Constant | Count | Notes |
|---|---|---|
| `NodeLabel` | 19 | 7 core accounting + 12 recipe/pipeline |
| `RelationshipType` | 26 | All relationship types |
| `ONTOLOGY` | 7 | Core accounting schemas |
| `RECIPE_ONTOLOGY` | 12 | Recipe/pipeline schemas (includes Reference sentinel) |
| `merged_ontology()` | 19 | All schemas combined |
| `RELATIONSHIP_CONSTRAINTS` | 11 | Core allowed edges (SYNCED_BY excluded) |
| `RECIPE_RELATIONSHIP_CONSTRAINTS` | 14 | Recipe allowed edges (all resolved) |
| `merged_relationship_constraints()` | 25 | All constraints combined |
| `ACCOUNT_TYPE_BALANCE_MAP` | 7 | Account type → normal balance direction |
| `MERGE_KEYS`                       | 19  | One per NodeLabel                              |
| Total tests                        | 197 | Across 5 domain test files (+ persistence)     |

## Key Design Constraints

- All domain types use `frozen=True` — never make them mutable
- All validators are pure functions returning `ValidationResult` — no side effects, no exceptions for validation
- Debits must equal credits — hard invariant in `validate_transaction_balance`
- Enum values in property maps are stored as strings (not enum instances) at the graph layer
- `recipe_id` is a template reference — NOT a multi-tenancy key
- Reference data nodes carry `NodeLabel.REFERENCE` (sentinel) in `Node.labels` and their actual type in `Node.extra_labels`; FP_core validates the accounting side of `USES_REFERENCE` edges but treats the reference side as opaque (empty PropertySchema, no required fields)
- Only `MappingRule`, `Condition`, and `AccountingRecipe` may source `USES_REFERENCE` edges (defined in `REFERENCE_RELATIONSHIP_SOURCES`); core accounting nodes cannot reach into the knowledge zone directly
- `ValidationResult.merge()` combines results — valid only if all have zero errors
- `compose_validators()` creates a single validator from multiple, using `merge` internally

## Import Patterns

Always import from `domain`, not submodules:
```python
from domain import Node, NodeLabel, validate_transaction_balance, merged_ontology
```

In tests, direct submodule imports are acceptable:
```python
from domain.ontology import ONTOLOGY, PropertySchema
```

## Extension Patterns

**Adding a new node type:**
1. Add member to `NodeLabel` in `types.py` (or `types_recipe.py` if recipe-layer)
2. Create frozen dataclass for the type in the same file
3. Add `PropertySchema` and `EntitySchema` entry in `ontology.py` (or `ontology_recipe.py`)
4. Export from `domain/__init__.py`
5. Update count tests (NodeLabel count, ONTOLOGY/RECIPE_ONTOLOGY count, merged count)

**Adding a new relationship type:**
1. Add member to `RelationshipType` in `types.py`
2. Add `RelationshipConstraint` entry in the appropriate constraints dict
3. Update count tests (RelationshipType count, constraints count, merged count)
4. EntitySchema `allowed_relationships` auto-populates from constraints — no manual update needed

**Adding a new validator:**
1. Write pure function: `def validate_xxx(arg) -> ValidationResult:`
2. Hard blocks return `ValidationResult(is_valid=False, errors=[...])`, soft warnings return `ValidationResult(is_valid=True, warnings=[...])`
3. Export from `domain/__init__.py`
4. Add test class following existing patterns in the corresponding test file

## Ontology Reference

See `docs/ontology.md` for the full design document including node type definitions, relationship semantics, validation strategy (hard blocks vs soft warnings vs no validation), traceability patterns, and implementation phases.
