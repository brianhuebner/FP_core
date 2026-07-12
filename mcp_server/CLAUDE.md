# Agent Instructions: mcp_server/

## Quick Context

Model Context Protocol (MCP) server exposing the FP_core knowledge graph to AI agents. Supports both STDIO transport (local, default) and Streamable HTTP transport (remote, network-accessible). Contains pure builder/summarizer functions plus tool handlers that compose domain logic with persistence operations. This is the top layer — it consumes from both domain/ and persistence/ but nothing consumes from it.

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
- Tool names and signatures (`load_recipe`, `load_format`, `get_processing_instructions`, `build_and_save_pipeline`, `build_output`, `validate_entries`)
- Resource URIs (`ontology://merged`, `constraints://merged`)
- Builder spec JSON schema (the expected shape of pipeline_spec and format_spec input)
- Server-side state structure (`_loaded_recipes` and `_loaded_formats` dicts)
- Gate 1/Gate 2 sequencing (build validates before save; validate_entries checks balance then accounts)

---

## Data Contracts

### MCP Tools (6) — `tools.py`

| Tool | Input | Output | Side Effects |
|------|-------|--------|--------------|
| `load_recipe` | recipe_id (str) | Schema summary, recipe rules | Reads Neo4j, caches GraphPattern in `_loaded_recipes` |
| `load_format` | format_id (str) | Format summary (columns, validation, entry structure) | Reads Neo4j, caches GraphPattern in `_loaded_formats` |
| `get_processing_instructions` | recipe_id (str), optional format_id (str) | Measures, mapping rules with resolved accounts, optional output spec | Reads from cache, auto-loads format from Neo4j if needed |
| `build_and_save_pipeline` | pipeline_spec (JSON str) | Validation results, save counts | Writes to Neo4j |
| `build_output` | output_spec (JSON str) | Validation results, save counts, format_id | Writes to Neo4j, caches in `_loaded_formats` |
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

- `build_pipeline_from_spec(spec_dict) → GraphPattern`: Converts a JSON pipeline specification into domain objects (schema + recipe). If an `output` key is present, builds format separately for backward compatibility.
- `build_format_from_spec(spec_dict) → GraphPattern`: Converts a JSON output format specification into a standalone GraphPattern.

**Expected pipeline spec shape:**
```json
{
  "recipe_id": "...",
  "schema": { "name": "...", "columns": [...], "measures": [...] },
  "recipe": { "name": "...", "rules": [...] }
}
```

**Expected format spec shape:**
```json
{
  "format_id": "...",
  "name": "...", "target_system": "...", "file_format": "...",
  "columns": [...], "validation_rules": [...],
  "entry_structure": { "grouping_column": "...", "entry_separator": "...", "date_column": "..." }
}
```

### Summarizers (`summarizers.py`) — Pure Functions

- `summarize_recipe_load(pattern, recipe_id) → dict`: Recipe GraphPattern to load response (schema + recipe only, no output)
- `summarize_format_load(pattern, format_id) → dict`: Format GraphPattern to load response (columns, validation, entry structure)
- `summarize_processing_instructions(pattern, recipe_id, format_pattern=None) → dict`: Recipe + optional format to processing instructions
- `summarize_build_result(validation, counts, recipe_id, pattern) → dict`: Validation + save counts to response
- `summarize_validation_result(entries_results, account_results, merged) → dict`: Entry validation to Gate 2 response

---

## Server-Side State

Defined in `mcp_server/__init__.py`:

- `_loaded_recipes: dict[str, GraphPattern]` — Cache of loaded recipe graph patterns, keyed by recipe_id. Populated by `load_recipe`, read by `get_processing_instructions`.
- `_loaded_formats: dict[str, GraphPattern]` — Cache of loaded output format graph patterns, keyed by format_id. Populated by `load_format` and `build_output`, read by `get_processing_instructions`.
- Neo4j connection — Lazy initialization, created on first tool call that needs it.

---

## Testing Contract

| Test File | Type | Tests |
|-----------|------|-------|
| `tests/mcp_server/test_builders.py` | Pure | ~54 |
| `tests/mcp_server/test_summarizers.py` | Pure | ~55 |
| `tests/mcp_server/test_transport.py` | Pure (mocked) | 9 |
| `tests/mcp_server/test_auth.py` | Pure (mocked JWKS) | 6 |

**Total: ~124 tests, all pure (no Neo4j, no live server)**

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
- `save_pattern` (used by build_and_save_pipeline, build_output)
- `load_pattern_by_recipe` (used by load_recipe)
- `load_format_by_id` (used by load_format, get_processing_instructions)

**Provides to:** External AI agents via MCP protocol (STDIO or Streamable HTTP transport)

**Boundary Rules:**
- mcp_server/ may import from both domain/ and persistence/
- Neither domain/ nor persistence/ may import from mcp_server/
- Pure functions (builders, summarizers) must not import from persistence/ — only tools.py touches I/O

---

## Transport Configuration

Transport is selected via environment variables. Default is STDIO (backward compatible).

| Variable | Default | Purpose |
|----------|---------|---------|
| `MCP_TRANSPORT` | `stdio` | Transport mode: `stdio` or `streamable-http` (alias: `http`) |
| `MCP_HOST` | `0.0.0.0` | Bind address for HTTP transport |
| `MCP_PORT` | `8000` | Listen port (falls back to `PORT` env var for Railway) |
| `AUTH0_DOMAIN` | *(none)* | Auth0 tenant domain, e.g. `your-tenant.us.auth0.com` |
| `AUTH0_AUDIENCE` | *(none)* | Auth0 API identifier / audience claim |
| `MCP_RESOURCE_URL` | *(derived)* | Public URL of MCP server for RFC 9728 metadata |
| `MCP_ALLOW_UNAUTHENTICATED` | *(none)* | Set to `true` to allow HTTP transport without OAuth (local dev only) |

**Fail-closed auth:** HTTP transport refuses to start unless both `AUTH0_DOMAIN` and `AUTH0_AUDIENCE` are set — a missing or mistyped var raises `RuntimeError` rather than silently exposing an unauthenticated public server. Set `MCP_ALLOW_UNAUTHENTICATED=true` to override for local development only. STDIO transport is unaffected (local process, auth vars ignored).

### OAuth Authentication (`auth.py`)

When `AUTH0_DOMAIN` and `AUTH0_AUDIENCE` are set and transport is HTTP, `Auth0TokenVerifier` validates Auth0-issued JWTs (RS256, JWKS-verified). FastMCP's built-in OAuth middleware handles bearer extraction, token verification, and RFC 9728 protected resource metadata. STDIO transport ignores all auth env vars.

Auto-generated endpoints (when OAuth is active):
- `GET /.well-known/oauth-protected-resource/mcp` — RFC 9728 metadata (points Claude Desktop to Auth0)
- `POST /mcp` — MCP requests (requires valid bearer token)
