# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FP_core is an **accounting knowledge graph** built on a domain-driven ontology. It models accounting concepts (accounts, transactions, entities, dimensions) as a graph with typed nodes and relationships, designed for Neo4j. The system enforces double-entry accounting semantics while allowing professional flexibility — it guides but doesn't block. It also models recipe/pipeline concepts for transforming source data into accounting entries. Currently implements Layers 1-3 only. No I/O layer, no Neo4j driver, no API.

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

# Run a specific test class or method
pytest tests/domain/test_ontology.py::TestValidateTransactionBalance::test_balanced_transaction

# Activate virtualenv
source .venv/bin/activate
```

Python 3.12, no build step, no linter configured. Only dependency beyond stdlib is pytest.

## File Map

```
domain/
  __init__.py          # Public API — re-exports everything via __all__ (~156 lines)
  types.py             # Layer 1: core enums + frozen dataclasses (~237 lines)
  types_recipe.py      # Layer 1: recipe enums + frozen dataclasses (~150 lines)
  ontology.py          # Layer 2: core schema, constraints, validators (~500 lines)
  ontology_recipe.py   # Layer 2: recipe schema, constraints, validators (~515 lines)
  logic.py             # Layer 3: pure functions for recipe graph building (~140 lines)
tests/
  domain/
    test_types.py          # Layer 1 core type tests (~160 lines)
    test_types_recipe.py   # Layer 1 recipe type tests (~237 lines)
    test_ontology.py       # Layer 2 core ontology tests (~649 lines)
    test_ontology_recipe.py # Layer 2 recipe ontology tests (~417 lines)
    test_logic.py          # Layer 3 logic tests (~369 lines)
docs/ontology.md       # Design doc: full ontology rationale (~453 lines)
main.py                # Placeholder entry point (~16 lines)
```

## Architecture

**Layer 1 — Types** (`types.py`, `types_recipe.py`): Frozen dataclasses and enums. Core: 7 accounting node types + graph primitives (Node, Relationship, GraphPattern, QueryIntent, Knowledge). Recipe: 5 enums + 9 dataclasses for pipeline modeling. `Node.extra_labels` (FrozenSet[str]) supports reference data labels outside NodeLabel.

**Layer 2 — Ontology & Validation** (`ontology.py`, `ontology_recipe.py`): Schema definitions (PropertySchema, EntitySchema, RelationshipConstraint), ontology dicts, constraint dicts, and pure validation functions returning `ValidationResult`. Hard blocks return errors; soft warnings return warnings but stay valid. `merged_ontology()` and `merged_relationship_constraints()` combine core + recipe schemas — not a naive dict merge, because cross-layer relationships require updating both sides.

**Layer 3 — Logic** (`logic.py`): Pure functions (no I/O) for building and validating recipe graph patterns: `build_source_schema_pattern`, `build_recipe_pattern`, `validate_recipe`, `extract_measures_for_schema`, `extract_debit_credit_slots`.

**Public API** (`domain/__init__.py`): Re-exports everything from all layers via `__all__`. Import from `domain` directly.

### Canonical Counts

These are test-asserted — do not change without updating both code and tests:

| Constant | Count | Notes |
|---|---|---|
| `NodeLabel` | 16 | 7 core accounting + 9 recipe/pipeline |
| `RelationshipType` | 26 | All relationship types |
| `ONTOLOGY` | 7 | Core accounting schemas |
| `RECIPE_ONTOLOGY` | 9 | Recipe/pipeline schemas |
| `merged_ontology()` | 16 | All schemas combined |
| `RELATIONSHIP_CONSTRAINTS` | 11 | Core allowed edges (SYNCED_BY excluded) |
| `RECIPE_RELATIONSHIP_CONSTRAINTS` | 11 | Recipe allowed edges (3 excluded — target types TBD) |
| `merged_relationship_constraints()` | 22 | All constraints combined |
| `ACCOUNT_TYPE_BALANCE_MAP` | 7 | Account type → normal balance direction |
| Total tests | 158 | Across 5 test files |

## Key Design Constraints

- All domain types use `frozen=True` — never make them mutable
- All validators are pure functions returning `ValidationResult` — no side effects, no exceptions for validation
- Debits must equal credits — hard invariant in `validate_transaction_balance`
- Enum values in property maps are stored as strings (not enum instances) at the graph layer
- `recipe_id` is a template reference — NOT a multi-tenancy key
- Reference data uses `Node.extra_labels` for labels outside `NodeLabel`; treated as opaque by validation
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
