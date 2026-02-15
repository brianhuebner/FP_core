# FP_core

An accounting knowledge graph built on a domain-driven ontology, designed for Neo4j.

## Overview

FP_core models accounting concepts as a **typed graph** with nodes (accounts, transactions, entities, dimensions) and typed relationships between them. It enforces double-entry accounting semantics — debits must equal credits — while allowing professional flexibility. The system **guides but doesn't block**: hard validation catches structural errors, while soft warnings flag things that deserve a second look.

The **recipe/pipeline layer** models how source data (timeclock entries, invoices, bank feeds) gets transformed into journal entries. Recipes define column mappings, measures, conditions, and account slots that map source fields to the accounting graph.

All domain types are **immutable** (frozen dataclasses). All validation is done by **pure functions** that return result objects — no exceptions, no side effects. This makes the domain logic easy to test, compose, and reason about.

## Architecture

```
Layer 3 — Logic          Pure functions for building/validating recipe graphs
            |
Layer 2 — Ontology       Schema definitions, constraints, validation functions
            |
Layer 1 — Types          Enums, frozen dataclasses, graph primitives
            |
        Public API        domain/__init__.py re-exports everything
```

The domain has two sides:

- **Core accounting** (7 node types): Account, Transaction, TransactionLine, Entity, AnalyticalDimension, AllocationRule, DataSource
- **Recipe/pipeline** (9 node types): SourceSchema, Column, Measure, Condition, AccountSlot, MappingRule, AccountingRecipe, OutputFormat, OutputColumn

These are connected by 26 relationship types with typed constraints defining which node types can connect to which.

### Key Graph Edges

```
Entity --HAS_ACCOUNT--> Account
Transaction --HAS_LINE--> TransactionLine --POSTS_TO--> Account
Account --HAS_DIMENSION--> AnalyticalDimension
AccountingRecipe --HAS_SCHEMA--> SourceSchema --HAS_COLUMN--> Column
AccountingRecipe --HAS_SLOT--> AccountSlot --MAPPED_TO--> Account
MappingRule --MAPS_COLUMN--> Column
```

## Directory Structure

```
FP_core/
  domain/
    __init__.py          Public API — re-exports all types, validators, and logic
    types.py             Layer 1: core enums (NodeLabel, RelationshipType, AccountType, ...)
                         and frozen dataclasses (Node, Relationship, GraphPattern, ...)
    types_recipe.py      Layer 1: recipe enums (ColumnDataType, SemanticRole, ...)
                         and frozen dataclasses (SourceSchema, Column, AccountSlot, ...)
    ontology.py          Layer 2: core schema definitions (PropertySchema, EntitySchema),
                         ONTOLOGY dict (7 entries), RELATIONSHIP_CONSTRAINTS (11 entries),
                         and 9 validation functions
    ontology_recipe.py   Layer 2: recipe schema definitions, RECIPE_ONTOLOGY (9 entries),
                         RECIPE_RELATIONSHIP_CONSTRAINTS (11 entries), merged_ontology(),
                         and 5 recipe validation functions
    logic.py             Layer 3: pure functions for building recipe graph patterns
                         and composing validation across layers
  tests/
    domain/
      test_types.py            Tests for core types and enums
      test_types_recipe.py     Tests for recipe types and enums
      test_ontology.py         Tests for core ontology and all core validators
      test_ontology_recipe.py  Tests for recipe ontology and recipe validators
      test_logic.py            Tests for Layer 3 logic functions
  ontology.md            Design document with full ontology rationale
  main.py                Placeholder entry point
  CLAUDE.md              Claude Code development guide
```

## Quickstart

```bash
# Clone and set up
git clone <repo-url> && cd FP_core
python3.12 -m venv .venv
source .venv/bin/activate
pip install pytest

# Run tests
pytest
# Expected: 158 passed
```

No `pyproject.toml` or formal packaging yet. The only dependency beyond stdlib is pytest.

## Project Status

**What exists (Layers 1-3):**
- Complete type system with 16 node types and 26 relationship types
- Full ontology with schema definitions and typed constraints
- 14 validation functions (9 core + 5 recipe) covering balance enforcement, property validation, relationship constraints, and recipe completeness
- Pure logic functions for building and validating recipe graph patterns
- 158 tests across 5 test files

**What's next:**
- Layer 4 — Neo4j adapter (graph persistence)
- Layer 5 — Services (use cases, orchestration)
- Layer 6 — API (external interface)

## Key Invariants

- **Double-entry balance**: Every transaction's debit lines must equal its credit lines. Enforced by `validate_transaction_balance` as a hard block.
- **Immutable domain types**: All dataclasses use `frozen=True`. Domain objects are never mutated after creation.
- **Pure validation**: Validators are pure functions returning `ValidationResult` with `is_valid`, `errors`, and `warnings`. No exceptions for validation failures, no side effects.
- **Typed constraints**: `RELATIONSHIP_CONSTRAINTS` and `RECIPE_RELATIONSHIP_CONSTRAINTS` define exactly which (source, target) node type pairs are allowed for each relationship type.

## Design Documents

- **`ontology.md`** — Full design rationale including node type definitions, relationship semantics, validation strategy, traceability patterns, and implementation phases.
- **`CLAUDE.md`** — Claude Code development guide with file map, architecture summary, canonical counts, and extension patterns.
