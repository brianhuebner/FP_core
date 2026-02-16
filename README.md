# FP_core

An accounting knowledge graph built on a domain-driven ontology, designed for Neo4j.

## Overview

FP_core models accounting concepts as a **typed graph** with nodes (accounts, transactions, entities, dimensions) and typed relationships between them. It enforces double-entry accounting semantics — debits must equal credits — while allowing professional flexibility. The system **guides but doesn't block**: hard validation catches structural errors, while soft warnings flag things that deserve a second look.

The **recipe/pipeline layer** models how source data (timeclock entries, invoices, bank feeds) gets transformed into journal entries. Recipes define column mappings, measures, conditions, and account slots that map source fields to the accounting graph.

All domain types are **immutable** (frozen dataclasses). All validation is done by **pure functions** that return result objects — no exceptions, no side effects. This makes the domain logic easy to test, compose, and reason about.

## Architecture

```
Layer 5 — MCP Server     Model Context Protocol server exposing graph to AI agents
            |
Layer 4 — Persistence    Neo4j adapter (serializers, deserializers, MERGE-based I/O)
            |
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
- **Recipe/pipeline** (12 node types): SourceSchema, Column, Measure, Condition, AccountSlot, MappingRule, AccountingRecipe, OutputFormat, OutputColumn, Reference, ValidationRule, BatchFormat

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
                         ONTOLOGY dict, RELATIONSHIP_CONSTRAINTS, and validation functions
    ontology_recipe.py   Layer 2: recipe schema definitions, RECIPE_ONTOLOGY,
                         RECIPE_RELATIONSHIP_CONSTRAINTS, merged_ontology(),
                         and recipe validation functions
    logic.py             Layer 3: pure functions for building recipe graph patterns
                         and composing validation across layers
  persistence/
    merge_keys.py        Layer 4: NodeLabel -> MERGE identity properties
    serializers.py       Layer 4: pure GraphPattern -> (cypher, params)
    deserializers.py     Layer 4: pure Neo4j records -> domain objects
    connection.py        Layer 4: Neo4jConnection wrapper
    operations.py        Layer 4: save/load/delete/verify pattern
  mcp_server/
    __init__.py          Layer 5: FastMCP server instance, state, Neo4j connection
    __main__.py          Entry point: python -m mcp_server
    summarizers.py       Layer 5: pure functions — GraphPattern -> JSON summaries
    tools.py             Layer 5: tool handlers (load_recipe, get_processing_instructions)
    resources.py         Layer 5: resource handlers (ontology, constraints)
  tests/
    domain/              Layer 1-3 tests
    persistence/         Layer 4 tests (pure + Neo4j integration)
    mcp_server/          Layer 5 tests (pure, no Neo4j)
  docs/
    fp_core_skill.md     MCP-driven skill: guided workflows for AI agents
    mcp_architecture.md  MCP server architecture and design decisions
    user_flow.md         End-to-end user flow documentation
  dogfood/
    load_payroll.py      Builds & saves payroll recipe pipeline to Neo4j
    run_payroll.py       Processes payroll data through recipe graph -> journal CSV
  CLAUDE.md              Claude Code development guide
```

## Quickstart

```bash
# Clone and set up
git clone <repo-url> && cd FP_core
python3.12 -m venv .venv
source .venv/bin/activate
pip install pytest neo4j mcp[cli]

# Run tests (domain + persistence pure tests + MCP server tests)
pytest
# Expected: 197 passed

# Integration tests (requires Neo4j)
NEO4J_URI=bolt://localhost:7687 NEO4J_PASSWORD=your_password pytest tests/persistence/test_operations.py

# Run MCP server
python -m mcp_server
```

No `pyproject.toml` or formal packaging yet. Dependencies beyond stdlib: pytest, neo4j>=5.0, mcp[cli].

## Project Status

**What exists (Layers 1-5):**
- Complete type system with 19 node types and 26 relationship types
- Full ontology with schema definitions and typed constraints
- Validation functions covering balance enforcement, property validation, relationship constraints, and recipe completeness
- Pure logic functions for building and validating recipe graph patterns
- Neo4j persistence layer with MERGE-based idempotent writes, serializers, and deserializers
- MCP server exposing the knowledge graph to AI agents with recipe loading and processing instruction tools
- 197 tests across domain, persistence, and MCP server test files
- Dogfood examples: end-to-end payroll recipe pipeline

## Key Invariants

- **Double-entry balance**: Every transaction's debit lines must equal its credit lines. Enforced by `validate_transaction_balance` as a hard block.
- **Immutable domain types**: All dataclasses use `frozen=True`. Domain objects are never mutated after creation.
- **Pure validation**: Validators are pure functions returning `ValidationResult` with `is_valid`, `errors`, and `warnings`. No exceptions for validation failures, no side effects.
- **Typed constraints**: `RELATIONSHIP_CONSTRAINTS` and `RECIPE_RELATIONSHIP_CONSTRAINTS` define exactly which (source, target) node type pairs are allowed for each relationship type.

## Design Documents

- **`docs/fp_core_skill.md`** — MCP-driven skill file: guided workflows for AI agents using MCP tools.
- **`docs/mcp_architecture.md`** — MCP server architecture and design decisions.
- **`docs/user_flow.md`** — End-to-end user flow documentation.
- **`CLAUDE.md`** — Claude Code development guide with file map, architecture summary, canonical counts, and extension patterns.
