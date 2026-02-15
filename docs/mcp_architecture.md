# Layer 5 as MCP Server — Architecture Design

This document captures the architectural decision to implement Layer 5 as an MCP (Model Context Protocol) server rather than a hardcoded pipeline executor. It replaces the `KnowledgeAgent` class from `fp_ach_structure.md` with a design that exposes the knowledge graph as tools for an AI agent.

---

## Why Not a Hardcoded Pipeline?

The payroll demo (`run_payroll.py`) proved the graph-driven approach works: load a recipe, extract instructions, process data, produce output. But it also revealed that hardcoding this as a Python pipeline is the wrong abstraction.

The original `fp_ach_structure.md` blueprint defined Layer 5 as a `KnowledgeAgent` class — a reactive agent that explores the graph, ranks entities, and decides next actions. FP_core's actual need is different: it needs a pipeline executor that transforms source data into journal entries using recipes stored in the graph. These are two different problems.

Both approaches share the same flaw: **they predetermine what the system can do.** A hardcoded `execute_pipeline()` function can only process data the way it was programmed. A hardcoded `KnowledgeAgent` can only explore the graph the way its `ActionType` enum allows. Neither can adapt to a new recipe structure, a new output format, or a new validation requirement without code changes.

The knowledge graph already encodes all processing logic declaratively. The right Layer 5 doesn't re-encode that logic in Python — it **exposes the graph's knowledge as tools** and lets an AI agent decide how to use them.

---

## The Three-Layer Connection

```
┌─────────────────────────────────────────────────────────────┐
│  Skill (outline_skill.md)                                   │
│  HOW TO THINK                                               │
│  - Accounting semantics (debits = credits, normal balances) │
│  - Workflow patterns (build → validate → save → execute)    │
│  - Anti-patterns (never modify posted transactions)         │
│  - Traceability patterns (trace, track, drilldown)          │
│  - When to use Gate 1 vs Gate 2 validation                  │
└──────────────────────────┬──────────────────────────────────┘
                           │ teaches the agent
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  MCP Server (Layer 5)                                       │
│  HOW TO ACCESS                                              │
│  - Tools: load_recipe, save_pattern, validate_template, ... │
│  - Resources: ontology schema, relationship constraints     │
│  - Prompts: recipe-building workflow, validation checklist   │
└──────────────────────────┬──────────────────────────────────┘
                           │ reads and writes
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Knowledge Graph (Neo4j via Layers 1-4)                     │
│  WHAT TO DO                                                 │
│  - Recipe: which columns to read, how to aggregate          │
│  - Mapping: which accounts to debit/credit, amounts         │
│  - Output: column order, sign conventions, formatting       │
│  - Validation: balance checks, clearing account rules       │
└─────────────────────────────────────────────────────────────┘
```

**Skill** = the culinary school curriculum. It teaches an agent accounting semantics, graph patterns, workflow discipline, and anti-patterns. It doesn't know about any specific recipe.

**MCP Server** = the kitchen. It has tools (ovens, mixers, thermometers) that can work with any recipe. It doesn't know what dish you're making.

**Knowledge Graph** = the recipe book. Each recipe (graph pattern) declares what ingredients to use, what steps to follow, and what the result should look like. It doesn't know how to operate the kitchen.

An AI agent trained with the skill uses the MCP tools to read a specific recipe from the graph and execute it. No hardcoded pipeline. No predetermined automation. The agent applies accounting knowledge to graph-declared instructions using tool-provided capabilities.

---

## What the MCP Server Exposes

### Tools (Actions the agent can take)

These map directly to existing Layers 1-4 functions:

| Tool | Layer | Underlying Function | Purpose |
|------|-------|---------------------|---------|
| `load_recipe` | 4 | `load_pattern_by_recipe()` | Load a complete recipe graph from Neo4j |
| `save_pattern` | 4 | `save_pattern()` | Write a validated graph pattern to Neo4j |
| `delete_recipe` | 4 | `delete_pattern_by_recipe()` | Remove a recipe from Neo4j |
| `verify_recipe` | 4 | `verify_pattern()` | Count nodes/relationships for a recipe |
| `validate_template` | 2/3 | `validate_recipe()` + `validate_pipeline_connectivity()` + `validate_output_format()` | Gate 1: validate recipe structure |
| `validate_node` | 2 | `validate_node_properties()` | Validate a single node against ontology |
| `build_schema` | 3 | `build_source_schema_pattern()` | Build a SourceSchema subgraph |
| `build_recipe` | 3 | `build_recipe_pattern()` | Build an AccountingRecipe subgraph |
| `build_output` | 3 | `build_output_format_pattern()` | Build an OutputFormat subgraph |
| `compose_pipeline` | 3 | `compose_pipeline_pattern()` | Merge subgraphs into a full pipeline |
| `extract_measures` | 3 | `extract_measures_for_schema()` | Get measures for a schema |
| `extract_slots` | 3 | `extract_debit_credit_slots()` | Get DR/CR account slots for a rule |
| `extract_columns` | 3 | `extract_output_columns()` | Get output column definitions |
| `extract_validations` | 3 | `extract_validation_rules()` | Get validation rules for a format |
| `extract_batch` | 3 | `extract_batch_format()` | Get batch formatting spec |
| `validate_balance` | 2 | `validate_transaction_balance()` | Gate 2: check debits = credits |
| `validate_posting` | 2 | `validate_posting_allowed()` | Gate 2: check account is active |
| `validate_direction` | 2 | `validate_account_balance_direction()` | Gate 2: check normal balance |
| `get_ontology` | 2 | `merged_ontology()` | Get full schema definitions |
| `get_constraints` | 2 | `merged_relationship_constraints()` | Get allowed relationship types |
| `run_cypher` | 4 | `conn.run_query()` | Execute arbitrary read-only Cypher |

### Resources (Read-only context the agent can access)

| Resource | Content |
|----------|---------|
| `ontology://core` | Core accounting node schemas (7 types) |
| `ontology://recipe` | Recipe pipeline node schemas (12 types) |
| `ontology://merged` | All 19 schemas combined |
| `constraints://core` | Core relationship constraints (11) |
| `constraints://recipe` | Recipe relationship constraints (14) |
| `constraints://merged` | All 25 constraints combined |
| `balance-map://accounts` | Account type → normal balance direction (7 entries) |

### Prompts (Workflow templates the agent can invoke)

| Prompt | Purpose |
|--------|---------|
| `build-pipeline` | Step-by-step workflow: schema → recipe → output → validate → save |
| `validate-all` | Run Gate 1 on a pipeline pattern, report errors and warnings |
| `process-data` | Load recipe, extract instructions, guide through data processing |
| `gate2-checklist` | Run all Gate 2 validators on computed journal entries |

---

## How the Skill Evolves

`outline_skill.md` already IS the accounting skill — it teaches Cypher patterns, accounting semantics, traceability, and anti-patterns. To work with the MCP server, it needs to additionally teach:

### 1. MCP Tool References

Instead of raw Cypher for common operations, the skill should reference MCP tools:

```
Before (raw Cypher):
  "To check if a transaction balances, run this query..."

After (MCP-aware):
  "Use the validate_balance tool to check transaction balance.
   If you need to inspect the raw data, use run_cypher."
```

### 2. Workflow Discipline

The skill should teach the two-gate workflow:

```
Building a recipe:
  1. Use build_schema to create the source schema pattern
  2. Use build_recipe to create the accounting recipe pattern
  3. Use build_output to create the output format pattern
  4. Use compose_pipeline to merge them
  5. Use validate_template (Gate 1) to check structural validity
  6. Only if Gate 1 passes: use save_pattern to persist

Processing data:
  1. Use load_recipe to get the recipe graph
  2. Use extract_measures, extract_slots, extract_columns to read instructions
  3. Compute measures and generate journal entries
  4. Use validate_balance, validate_posting (Gate 2) before writing output
  5. Only if Gate 2 passes: write the output file
```

### 3. When to Use Which Tool

The skill should teach judgment about tool selection:

- Use `validate_template` for the whole pipeline, `validate_node` for individual nodes
- Use `extract_measures` to understand a schema, `run_cypher` for ad-hoc exploration
- Use `get_ontology` to understand what properties a node type requires
- Never use `save_pattern` before `validate_template` passes

---

## What FP_core Actually Is

FP_core is more than a single skill. In the kitchen analogy:

| Kitchen Concept | FP_core Equivalent |
|-----------------|-------------------|
| Culinary school | `outline_skill.md` — teaches accounting semantics |
| Recipe format standard | Layer 1 types — defines what a valid recipe looks like |
| Recipe book | Neo4j graph — stores specific recipes as graph patterns |
| Kitchen skills | Layer 2 validators — knows how to check if a dish is right |
| Ingredient prep | Layer 3 builders/extractors — assembles and reads recipe components |
| Kitchen equipment | Layer 4 persistence — reads/writes to the pantry (Neo4j) |
| **The kitchen itself** | **Layer 5 MCP server — exposes all capabilities as tools** |

The knowledge graph holds three kinds of accounting knowledge:

1. **Structural knowledge** — relationships define valid connections (Account → TransactionLine → Transaction)
2. **Semantic knowledge** — properties encode meaning (account_type, normal_balance, is_active)
3. **Procedural knowledge** — recipe graphs encode processing logic (source columns → measures → mapping rules → journal entries → output columns)

A hardcoded pipeline can only execute procedural knowledge. An MCP server exposes all three kinds for an agent to use as needed.

---

## What Changes from the Original Blueprint

| Aspect | `fp_ach_structure.md` | MCP Design |
|--------|----------------------|------------|
| Layer 5 | `KnowledgeAgent` class with `process_query()` | MCP server with tool/resource/prompt handlers |
| Layer 6 | FastAPI HTTP endpoints | Not needed — MCP protocol IS the interface |
| Agent logic | Hardcoded in `decide_next_action()` | Lives in the AI agent, guided by the skill |
| `QueryIntent` | Used to build Cypher queries | Replaced by MCP tool parameters |
| `Knowledge` | Return type from agent | Agent builds its own understanding from tool results |
| `ActionType` | Enum of predetermined actions | Agent decides freely, constrained by available tools |
| `AgentContext` | Conversation history in Python | Managed by the AI runtime (Claude, etc.) |

### Types that remain useful

- `Node`, `Relationship`, `GraphPattern` — core graph primitives, used everywhere
- `ValidationResult` — returned by validators, surfaced through MCP tools
- All Layer 1-3 types and functions — unchanged, they ARE the domain

### Types that may not be needed

- `QueryIntent` — MCP tool parameters replace this
- `Knowledge` — the AI agent builds its own context
- `ActionType`, `AgentAction`, `AgentContext` — agent reasoning happens in the AI, not in Python
- `OperationResult` — MCP has its own result protocol

These types exist in `types.py` but are currently unused. They can remain as-is for now; if the MCP server finds a use for them (e.g., `QueryIntent` as a structured input to a `run_cypher` tool), they're available.

---

## Implementation Phases

### Phase 1: MCP Server Skeleton

- Set up MCP server using the Python MCP SDK
- Expose `get_ontology` and `get_constraints` as resources
- Expose `load_recipe` and `verify_recipe` as tools (read-only)
- Test with Claude Desktop or Claude Code as the MCP client

### Phase 2: Full Tool Surface

- Expose all Layer 3 builders as tools (`build_schema`, `build_recipe`, `build_output`)
- Expose `compose_pipeline` and `validate_template` (Gate 1)
- Expose `save_pattern` and `delete_recipe` (write operations)
- Expose all extractors as tools

### Phase 3: Gate 2 + Data Processing Support

- Expose Gate 2 validators (`validate_balance`, `validate_posting`, `validate_direction`)
- Add `run_cypher` tool for ad-hoc graph queries
- Add MCP prompts for guided workflows (`build-pipeline`, `process-data`)

### Phase 4: Skill Evolution

- Update `outline_skill.md` with MCP tool references
- Add workflow discipline sections (Gate 1 → Gate 2 flow)
- Add tool selection guidance
- Test end-to-end: agent + skill + MCP server + Neo4j

### Phase 5: Measure Engine (if needed)

- If agents need help computing measures, add a `compute_measures` tool
- If agents need help generating journal entries, add a `generate_entries` tool
- These are optional — a skilled agent can do the computation itself using extracted instructions
- The decision depends on how well agents handle Decimal arithmetic and aggregation

---

## Directory Structure

```
mcp_server/
  __init__.py          # MCP server entry point
  tools.py             # Tool handlers (thin wrappers around Layers 2-4)
  resources.py         # Resource handlers (ontology, constraints)
  prompts.py           # Prompt templates (workflow guidance)
```

The MCP server is a thin wrapper. Each tool handler:
1. Receives parameters from the MCP protocol
2. Calls the appropriate Layer 2/3/4 function
3. Serializes the result for MCP transport

No business logic lives in the MCP server. All logic stays in the pure domain layers where it's testable without MCP infrastructure.

---

## Relationship to Existing Layers

```
Layer 1 (Types)           — unchanged, provides domain vocabulary
Layer 2 (Ontology)        — unchanged, provides validation
Layer 3 (Logic)           — unchanged, provides builders/extractors
Layer 4 (Persistence)     — unchanged, provides Neo4j I/O
Layer 5 (MCP Server)      — NEW: thin tool/resource/prompt wrappers
Layer 6 (FastAPI)         — NOT NEEDED: MCP protocol replaces HTTP API

outline_skill.md          — EVOLVES: adds MCP tool references
```

The key architectural property is preserved: **Layers 1-3 remain pure.** The MCP server (Layer 5) is the only new I/O boundary, and it's thin — just protocol translation between MCP messages and domain function calls.
