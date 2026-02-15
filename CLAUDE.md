# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FP_core is an **accounting knowledge graph** built on a domain-driven ontology. It models accounting concepts (accounts, transactions, entities, dimensions) as a graph with typed nodes and relationships, designed for Neo4j. The system enforces double-entry accounting semantics while allowing professional flexibility — it guides but doesn't block.

## Commands

```bash
# Run all tests
pytest

# Run a single test file
pytest tests/domain/test_types.py
pytest tests/domain/test_ontology.py

# Run a specific test class or method
pytest tests/domain/test_ontology.py::TestValidateTransactionBalance::test_balanced_transaction

# Activate virtualenv
source .venv/bin/activate
```

Python 3.12, no build step, no linter configured. Only dependency beyond stdlib is pytest.

## Architecture

The codebase follows a **layered domain model** built bottom-up:

**Layer 1 — Domain Types** (`domain/types.py`): Frozen (immutable) dataclasses and enums representing the 7 core node types (Account, Transaction, TransactionLine, Entity, AnalyticalDimension, AllocationRule, DataSource) plus graph primitives (Node, Relationship, GraphPattern, QueryIntent, Knowledge). All dataclasses use `frozen=True`. Enum values in property maps are stored as strings (not enum instances) at the graph/Neo4j layer.

**Layer 2 — Ontology & Validation** (`domain/ontology.py`): Schema definitions (`PropertySchema`, `EntitySchema`, `RelationshipConstraint`), the `ONTOLOGY` dict mapping each `NodeLabel` to its schema, `RELATIONSHIP_CONSTRAINTS` for allowed edge types, and pure validation functions. Validators return `ValidationResult` (frozen dataclass with `is_valid`, `errors`, `warnings`). There are two categories:
- **Hard blocks** (return errors): `validate_transaction_balance`, `validate_posting_allowed`, `validate_node_properties`, `validate_account_balance_direction`, `validate_relationship`, `validate_graph_pattern`
- **Soft warnings** (return warnings, always valid): `validate_clearing_account_balance`, `validate_temporal_ordering`, `validate_dimension_hierarchy`

**Public API** (`domain/__init__.py`): Re-exports everything from both layers via `__all__`. Import from `domain` directly.

## Key Design Constraints

- All domain types are **immutable** (`frozen=True` dataclasses) — never make them mutable
- All validators are **pure functions** returning `ValidationResult` — no side effects, no exceptions for validation failures
- The accounting equation (debits = credits) is a **hard invariant** enforced by `validate_transaction_balance`
- `ACCOUNT_TYPE_BALANCE_MAP` defines the canonical mapping of account types to normal balance directions (7 entries)
- `RELATIONSHIP_CONSTRAINTS` defines allowed (source_label, target_label) pairs for each relationship type (11 of 12 types; SYNCED_BY is excluded from MVP)
- `ONTOLOGY` has exactly 7 entries, one per `NodeLabel`
- `ValidationResult.merge()` combines multiple results — valid only if all results have zero errors
- `compose_validators()` creates a single validator from multiple, using `merge` internally

## Ontology Reference

See `ontology.md` for the full design document including node type definitions, relationship semantics, validation strategy (hard blocks vs soft warnings vs no validation), traceability patterns, and implementation phases.
