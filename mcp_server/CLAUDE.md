# Agent Instructions: mcp_server/

## Quick Context

Model Context Protocol (MCP) server exposing the FP_core knowledge graph to AI agents. Runs over STDIO transport. Contains pure builder/summarizer functions plus tool handlers that compose domain logic with persistence operations. This is the top layer — it consumes from both domain/ and persistence/ but nothing consumes from it.

**Architecture Layer:** 5 (MCP Server)
**Primary Responsibility:** Expose accounting knowledge graph operations as MCP tools, resources, and prompts

---

## Autonomy Boundaries

### Safe to Modify Independently
- Prompt text and workflow step descriptions in `prompts.py`
- JSON formatting and field ordering in summarizer output
- Internal helper functions in builders/summarizers
- Error messages returned to agents

### Requires Careful Review
- Summarizer output fields (agents may depend on specific field names)
- Builder spec expectations (changes affect what JSON agents must provide)
- Tool parameter descriptions (agents read these to understand usage)
- Adding new tools, resources, or prompts

### DO NOT Change Without Coordination
- Tool names and signatures (`load_recipe`, `get_processing_instructions`, `build_and_save_pipeline`, `validate_entries`)
- Resource URIs (`ontology://merged`, `constraints://merged`)
- Builder spec JSON schema (the expected shape of pipeline_spec input)
- Server-side state structure (`_loaded_recipes` dict)
- Gate 1/Gate 2 sequencing (build validates before save; validate_entries checks balance then accounts)

---

## Data Contracts

### MCP Tools (4) — `tools.py`

| Tool | Input | Output | Side Effects |
|------|-------|--------|--------------|
| `load_recipe` | recipe_id (str) | Schema summary, recipe rules, output format | Reads Neo4j, caches GraphPattern |
| `get_processing_instructions` | recipe_id (str) | Measures, mapping rules with resolved accounts, output spec | Reads from cache |
| `build_and_save_pipeline` | pipeline_spec (JSON str) | Validation results, save counts | Writes to Neo4j |
| `validate_entries` | entries (JSON str), optional recipe_id | Per-entry balance validation, account checks | None (read-only) |

### MCP Resources (2) — `resources.py`

| URI | Returns |
|-----|---------|
| `ontology://merged` | Full merged ontology (19 EntitySchema entries) as JSON |
| `constraints://merged` | All 25 relationship constraints as JSON |

### MCP Prompts (3) — `prompts.py`

| Prompt | Purpose |
|--------|---------|
| `build-pipeline` | 6-step workflow for building and saving recipes |
| `process-data` | 7-step workflow for processing source data through recipe |
| `gate2-checklist` | Validation checklist for journal entries |

### Builders (`builders.py`) — Pure Functions

- `build_pipeline_from_spec(spec_dict) → GraphPattern`: Converts a JSON pipeline specification into domain objects. This is the inverse of summarizers — it takes agent-provided JSON and constructs the graph pattern that gets validated and saved.

**Expected spec shape:**
```json
{
  "schema": { "recipe_id": "...", "columns": [...], "measures": [...] },
  "recipe": { "mapping_rules": [...], "accounts": [...] },
  "output_format": { "columns": [...], "validation_rules": [...] }
}
```

### Summarizers (`summarizers.py`) — Pure Functions

- `summarize_recipe_load(pattern) → dict`: GraphPattern to load response
- `summarize_processing_instructions(pattern) → dict`: GraphPattern to processing instructions
- `summarize_build_result(validation, counts) → dict`: Validation + save counts to response
- `summarize_validation_result(results) → dict`: Entry validation to Gate 2 response

---

## Server-Side State

Defined in `mcp_server/__init__.py`:

- `_loaded_recipes: dict[str, GraphPattern]` — Cache of loaded recipe graph patterns, keyed by recipe_id. Populated by `load_recipe`, read by `get_processing_instructions`.
- Neo4j connection — Lazy initialization, created on first tool call that needs it.

---

## Testing Contract

| Test File | Type | Tests |
|-----------|------|-------|
| `tests/mcp_server/test_builders.py` | Pure | ~40 |
| `tests/mcp_server/test_summarizers.py` | Pure | ~44 |

**Total: 84 tests, all pure (no Neo4j, no MCP transport)**

```bash
pytest tests/mcp_server/
```

Builder tests verify JSON spec → GraphPattern conversion. Summarizer tests verify GraphPattern → JSON dict conversion. Both test suites construct domain objects directly — no database or server required.

---

## Layer Integration Points

**Consumes from domain/:**
- All Layer 3 logic functions (builders use build_source_schema_pattern, build_recipe_pattern, etc.)
- All Layer 2 validators (Gate 1 runs validate_recipe, validate_pipeline_connectivity, etc.)
- Ontology merge functions (resources expose merged_ontology, merged_relationship_constraints)
- All Layer 1 types (Node, NodeLabel, GraphPattern, etc.)

**Consumes from persistence/:**
- `Neo4jConnection` (held in server state)
- `save_pattern` (used by build_and_save_pipeline)
- `load_pattern_by_recipe` (used by load_recipe)

**Provides to:** External AI agents via MCP protocol (STDIO transport)

**Boundary Rules:**
- mcp_server/ may import from both domain/ and persistence/
- Neither domain/ nor persistence/ may import from mcp_server/
- Pure functions (builders, summarizers) must not import from persistence/ — only tools.py touches I/O
