# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FP_core is an **accounting knowledge graph** built on a domain-driven ontology. It models accounting concepts (accounts, transactions, entities, dimensions) as a graph with typed nodes and relationships, designed for Neo4j. The system enforces double-entry accounting semantics while allowing professional flexibility — it guides but doesn't block. It also models recipe/pipeline concepts for transforming source data into accounting entries. Implements Layers 1-5: types, ontology/validation, pure logic, Neo4j persistence, and MCP server. The MCP server supports both STDIO (local) and Streamable HTTP (remote) transport.

## Branch

Main branch: `main`

## Per-Package Documentation

Each package has its own CLAUDE.md with layer-specific architecture, autonomy boundaries, data contracts, and extension patterns:

| Package | Layer | File |
|---------|-------|------|
| `domain/` | 1-3 (Types, Ontology, Logic) | [`domain/CLAUDE.md`](domain/CLAUDE.md) |
| `persistence/` | 4 (Neo4j I/O) | [`persistence/CLAUDE.md`](persistence/CLAUDE.md) |
| `mcp_server/` | 5 (MCP Server) | [`mcp_server/CLAUDE.md`](mcp_server/CLAUDE.md) |

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

# Layer 5 MCP server tests (pure, no Neo4j needed)
pytest tests/mcp_server/test_summarizers.py
pytest tests/mcp_server/test_builders.py

# Integration tests (requires NEO4J_URI, NEO4J_PASSWORD env vars)
pytest tests/persistence/test_operations.py

# Activate virtualenv
source .venv/bin/activate

# Run MCP server locally (STDIO, default)
python -m mcp_server

# Run MCP server with HTTP transport
MCP_TRANSPORT=streamable-http MCP_PORT=8000 python -m mcp_server

# Run with Auth0 OAuth
MCP_TRANSPORT=streamable-http AUTH0_DOMAIN=your-tenant.us.auth0.com AUTH0_AUDIENCE=https://your-app.example.com/mcp python -m mcp_server
```

Python 3.12, no build step, no linter configured. Dependencies beyond stdlib: pytest, neo4j>=5.0, mcp[cli], python-dotenv, uvicorn, PyJWT[crypto]. See `requirements.txt`.

## File Map

```
domain/
  CLAUDE.md            # Package docs: Layers 1-3 architecture & contracts
  __init__.py          # Public API — re-exports everything via __all__ (~180 lines)
  types.py             # Layer 1: core enums + frozen dataclasses (~237 lines)
  types_recipe.py      # Layer 1: recipe enums + frozen dataclasses (~150 lines)
  ontology.py          # Layer 2: core schema, constraints, validators (~500 lines)
  ontology_recipe.py   # Layer 2: recipe schema, constraints, validators (~686 lines)
  logic.py             # Layer 3: pure functions for recipe graph building (~277 lines)
persistence/
  CLAUDE.md            # Package docs: Layer 4 architecture & contracts
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
  mcp_server/
    __init__.py            # Empty package marker
    test_builders.py       # Layer 5 builder tests (pure, no Neo4j)
    test_summarizers.py    # Layer 5 summarizer tests (pure, no Neo4j)
    test_transport.py      # Layer 5 transport selection tests (mocked)
    test_auth.py           # Layer 5 bearer token middleware tests
mcp_server/
  CLAUDE.md            # Package docs: Layer 5 architecture & contracts
  __init__.py          # Layer 5: FastMCP server instance, state, Neo4j connection, transport selection
  __main__.py          # Entry point: python -m mcp_server
  auth.py              # Layer 5: BearerTokenMiddleware for HTTP transport
  builders.py          # Layer 5: pure functions — JSON pipeline spec → domain objects
  summarizers.py       # Layer 5: pure functions — GraphPattern → JSON-serializable dicts
  tools.py             # Layer 5: Tier 1 tool handlers (6 tools: load_recipe, load_format, get_processing_instructions, build_and_save_pipeline, build_output, validate_entries)
  prompts.py           # Layer 5: MCP prompt workflow templates (build-pipeline, process-data, gate2-checklist)
  resources.py         # Layer 5: resource handlers (ontology://merged, constraints://merged)
docs/
  vision_and_roadmap.md  # Project vision, feature list, Lean Six Sigma alignment, eval targets
  fp_core_skill.md     # MCP-driven skill: guided workflows for AI agents using MCP tools
  mcp_architecture.md  # MCP server architecture and design decisions
  user_flow.md         # End-to-end user flow documentation
  old/                 # Archived docs (ontology.md, outline_skill.md, etc.)
dogfood/
  load_payroll.py        # Builds & saves payroll recipe pipeline to Neo4j
  run_payroll.py         # Processes payroll data through recipe graph → journal CSV
  sample_payroll_data.csv      # Sample input: 5 employees, one pay period
  payroll_journal_export.csv   # Output from run_payroll.py
  payroll_journal_output.csv   # Output from MCP-driven session
requirements.txt             # Python dependencies for Railway deployment
specs/
  template.md               # Spec template adapted for FP_core's 5-layer architecture
  features/                  # Feature-level specs (cross-layer)
    measure_aggregation.md   # Measure group_by/split_by/split_column through builder
  workflows/                 # End-to-end workflow specs (eval targets)
    build_pipeline.md        # Agent builds & saves recipe via MCP tools
```

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
| MCP Tools                          | 6   | load_recipe, load_format, get_processing_instructions, build_and_save_pipeline, build_output, validate_entries |
| Total tests                        | 408 | Across 5 domain + 4 MCP + persistence test files |

## Known Constraints

None currently open.

## Import Patterns

Always import from `domain`, not submodules:
```python
from domain import Node, NodeLabel, validate_transaction_balance, merged_ontology
```

In tests, direct submodule imports are acceptable:
```python
from domain.ontology import ONTOLOGY, PropertySchema
```
