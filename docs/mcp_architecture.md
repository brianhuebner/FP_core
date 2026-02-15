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

## Code Execution Pattern

A naive MCP design exposes every function as a separate tool. For FP_core that would mean 20+ tool definitions loaded into the agent's context upfront, plus every intermediate result (full graph patterns, node lists, validation results) flowing through the model's context window on every call. This is the token inefficiency problem identified in [Anthropic's code execution research](https://www.anthropic.com/engineering/code-execution-with-mcp).

### The Problem with Flat Tool Lists

Consider what happens when an agent processes payroll data with a flat tool design:

```
Agent calls: load_recipe("payroll_monthly_v1")
  → 33 nodes, 36 relationships flow INTO the model context
Agent calls: extract_measures(pipeline, schema_id)
  → The full pipeline is described AGAIN as a parameter
  → 3 measure nodes flow back into context
Agent calls: extract_slots(pipeline, rule_id)       ← repeated 3x
Agent calls: extract_columns(pipeline, format_id)
Agent calls: extract_batch(pipeline, format_id)
```

That's 7+ round trips, with the full graph pattern described repeatedly. The recipe data flows through the model's context window multiple times despite never changing.

### The Solution: Server-Side State + Coarse Tools

The MCP server holds state server-side. The agent works with **handles** (recipe IDs), not raw graph data. Coarse-grained tools compose multiple Layer 2-4 calls internally and return only what the agent needs to make decisions.

```
Agent calls: load_recipe("payroll_monthly_v1")
  → Server loads graph, holds it in memory
  → Returns: summary (node counts, schema name, rule names, column list)

Agent calls: get_processing_instructions("payroll_monthly_v1")
  → Server runs ALL extractors internally
  → Returns: measures, DR/CR mappings, output spec — structured for action
```

Two calls instead of seven. No raw graph data in the context. The agent gets exactly the information it needs to compute measures and generate journal entries.

### Progressive Disclosure

Not every agent session needs every tool. The server organizes capabilities into tiers:

**Tier 1 — Always loaded** (3-4 tools): The tools an agent needs for any interaction. These are the only tool definitions sent upfront.

**Tier 2 — On-demand** (discovered via `list_tools`): Detailed tools the agent can request when it needs fine-grained control. The agent learns about these from the skill or by asking.

**Tier 3 — Escape hatch** (`run_cypher`): Raw Cypher for exploration and edge cases. Available but not advertised.

This reduces initial context from ~20 tool definitions to ~4, matching the 98%+ token reduction the Anthropic research demonstrated.

---

## What the MCP Server Exposes

### Tier 1 Tools — Core Operations (always loaded)

These are coarse-grained tools that compose multiple internal functions. They work with recipe IDs (handles), not raw graph data.

| Tool | What It Does Internally | Returns to Agent |
|------|------------------------|------------------|
| `load_recipe` | `load_pattern_by_recipe()` → holds graph server-side | Summary: node/rel counts, schema name, rule names with DR/CR accounts, output columns, validation rules |
| `build_and_save_pipeline` | Runs builders → `compose_pipeline_pattern()` → Gate 1 validators → `save_pattern()` | Validation result + node/rel counts (or errors if Gate 1 fails) |
| `get_processing_instructions` | Runs all extractors on a loaded recipe | Structured instructions: measures (name, operation, column), mapping rules (priority, source_measure, DR/CR accounts, memo), output spec (columns, positions, format patterns) |
| `validate_entries` | Runs all Gate 2 validators on submitted journal entries | Merged `ValidationResult`: balanced?, accounts active?, normal balance warnings |

Note: `load_recipe` and `get_processing_instructions` are separate because the agent may want to inspect a recipe (load) without processing data through it (get instructions). But both avoid dumping raw graph data into the context.

### Tier 2 Tools — Fine-Grained Control (on-demand)

Available when the agent needs to build, modify, or inspect individual components. Discovered via `list_tools` or taught by the skill.

| Tool | Underlying Function | When Needed |
|------|---------------------|-------------|
| `build_schema` | `build_source_schema_pattern()` | Building a new recipe step by step |
| `build_recipe` | `build_recipe_pattern()` | Building a new recipe step by step |
| `build_output` | `build_output_format_pattern()` | Building a new recipe step by step |
| `validate_template` | `validate_recipe()` + `validate_pipeline_connectivity()` + `validate_output_format()` | Validating without saving |
| `validate_node` | `validate_node_properties()` | Debugging a specific node |
| `delete_recipe` | `delete_pattern_by_recipe()` | Cleanup |
| `get_ontology` | `merged_ontology()` | Understanding what properties a node type requires |
| `get_constraints` | `merged_relationship_constraints()` | Understanding allowed relationships |

### Tier 3 — Escape Hatch

| Tool | Purpose |
|------|---------|
| `run_cypher` | Execute read-only Cypher for ad-hoc exploration, debugging, or queries not covered by other tools |

### Resources (Read-only context)

| Resource | Content |
|----------|---------|
| `ontology://merged` | All 19 node schemas (loaded on-demand, not upfront) |
| `constraints://merged` | All 25 relationship constraints |
| `balance-map://accounts` | Account type → normal balance direction (7 entries) |

### Prompts (Workflow templates)

| Prompt | Purpose |
|--------|---------|
| `build-pipeline` | Step-by-step workflow: schema → recipe → output → validate → save |
| `process-data` | Load recipe, extract instructions, guide through data processing |
| `gate2-checklist` | Run all Gate 2 validators on computed journal entries |

### Server-Side State

The MCP server maintains state between tool calls within a session:

```python
# Server holds loaded recipes in memory — agent works with IDs, not data
_loaded_recipes: Dict[str, GraphPattern] = {}

# load_recipe stores the graph server-side
def handle_load_recipe(recipe_id: str) -> dict:
    pattern = load_pattern_by_recipe(conn, recipe_id)
    _loaded_recipes[recipe_id] = pattern    # server-side state
    return summarize_pattern(pattern)        # agent gets summary only

# get_processing_instructions reads from server-side state
def handle_get_instructions(recipe_id: str) -> dict:
    pattern = _loaded_recipes[recipe_id]     # no re-fetch needed
    return {
        "measures": extract_and_summarize_measures(pattern),
        "mapping_rules": extract_and_summarize_rules(pattern),
        "output_spec": extract_and_summarize_output(pattern),
    }
```

This is the key architectural difference from the flat tool design. Data stays server-side. The agent receives structured summaries optimized for decision-making, not raw graph objects.

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

The skill should teach the two-gate workflow using the tiered tools:

```
Building a recipe (simple path — Tier 1):
  1. Use build_and_save_pipeline with all components
     → Server builds, composes, validates (Gate 1), saves in one call
     → Returns validation result + counts, or errors

Building a recipe (step-by-step — Tier 2):
  1. Use build_schema to create the source schema pattern
  2. Use build_recipe to create the accounting recipe pattern
  3. Use build_output to create the output format pattern
  4. Use validate_template (Gate 1) to check before saving
  5. Only if Gate 1 passes: use build_and_save_pipeline to persist

Processing data (Tier 1):
  1. Use load_recipe to get a summary of the recipe
  2. Use get_processing_instructions to read all instructions at once
  3. Compute measures and generate journal entries
  4. Use validate_entries (Gate 2) before writing output
  5. Only if Gate 2 passes: write the output file
```

### 3. Tool Tier Selection

The skill should teach when to use which tier:

- **Start with Tier 1** — `load_recipe` + `get_processing_instructions` handles most processing
- **Drop to Tier 2** when building new recipes step-by-step, or debugging validation failures
- **Use Tier 3** (`run_cypher`) only for ad-hoc exploration or edge cases not covered by tools
- Use `get_ontology` (Tier 2) to understand what properties a node type requires
- Never skip Gate 1 (`validate_template` or `build_and_save_pipeline`) before persisting

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

### Phase 1: MCP Server Skeleton + Tier 1 Read Tools

- Set up MCP server using the Python MCP SDK
- Implement server-side state management (`_loaded_recipes` dict)
- Implement `load_recipe` (coarse-grained: load graph → hold server-side → return summary)
- Implement `get_processing_instructions` (coarse-grained: run all extractors → return structured instructions)
- Expose `ontology://merged` and `constraints://merged` as resources
- Test with Claude Desktop or Claude Code as the MCP client
- Validate: agent can load a recipe and read its instructions with 2 tool calls

### Phase 2: Tier 1 Write Tools + Gate Validation

- Implement `build_and_save_pipeline` (coarse-grained: build → compose → Gate 1 → save)
- Implement `validate_entries` (coarse-grained: run all Gate 2 validators)
- Add MCP prompts for guided workflows (`build-pipeline`, `process-data`)
- Validate: agent can build, validate, save a recipe and validate output entries

### Phase 3: Tier 2 Tools (Progressive Disclosure)

- Implement fine-grained builders (`build_schema`, `build_recipe`, `build_output`)
- Implement `validate_template`, `validate_node`, `delete_recipe`
- Implement `get_ontology`, `get_constraints`
- Register as discoverable via `list_tools` but not loaded upfront
- Validate: agent can drop to fine-grained mode for step-by-step recipe building

### Phase 4: Tier 3 + Skill Evolution

- Implement `run_cypher` escape hatch
- Update `outline_skill.md` with MCP tool references and tier selection guidance
- Add workflow discipline sections (Gate 1 → Gate 2 flow)
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
  __init__.py          # MCP server entry point, session state
  tools.py             # Tool handlers (Tier 1 coarse + Tier 2 fine-grained)
  resources.py         # Resource handlers (ontology, constraints)
  prompts.py           # Prompt templates (workflow guidance)
  summarizers.py       # Pure functions: GraphPattern → agent-friendly summaries
```

The MCP server is a thin wrapper with one key responsibility beyond protocol translation: **server-side state management.** Loaded recipes are held in memory so the agent works with IDs (handles), not raw graph data.

Each tool handler:
1. Receives parameters from the MCP protocol
2. Reads/writes server-side state as needed
3. Calls the appropriate Layer 2/3/4 function(s) — potentially composing several
4. Uses `summarizers.py` to convert domain objects into agent-friendly responses

`summarizers.py` is the new piece. It contains pure functions that transform `GraphPattern`, `Node`, and `ValidationResult` objects into concise dicts optimized for the agent's context window. This is where the token efficiency gains are realized — the summarizer decides what the agent needs to see vs. what stays server-side.

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
