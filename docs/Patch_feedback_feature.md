# Fix LLM Processing Reliability — MCP Setup + Summarizer Bugs + Feedback Loop

## Context

The LLM is using the **Neo4j published MCP** (raw Cypher queries) instead of the **FP_core MCP** tools. This is the root cause of inconsistent output — the LLM receives raw graph node properties and must reverse-engineer the processing logic itself: which accounts link to which slots, rule ordering, condition wiring, aggregation scope. It gets this wrong intermittently.

The FP_core MCP was designed to solve this. `get_processing_instructions` resolves all graph traversal and returns clean, ordered JSON — explicit `group_by: []`, resolved account codes, ordered rules, output column specs. The LLM reads instructions and executes rather than navigating the graph manually.

Two bugs in the summarizer also exist that would cause problems even with the FP_core MCP active. A `patch_recipe` tool provides the feedback loop: when the LLM makes a mistake, the correction can be saved back to the graph so future `get_processing_instructions` calls include the right metadata.

---

## Part 1: Set Up FP_core MCP in Claude Desktop

**This is the highest-priority fix** — it addresses the root cause immediately.

### Claude Desktop Config File
Location on Linux: `~/.config/Claude/claude_desktop_config.json`

Add the FP_core server entry to the `mcpServers` object:

```json
{
  "mcpServers": {
    "neo4j": {
      "...existing neo4j config..."
    },
    "fp_core": {
      "command": "/home/jarvis/Python Projects/FP_core/.venv/bin/python",
      "args": ["-m", "mcp_server"],
      "cwd": "/home/jarvis/Python Projects/FP_core",
      "env": {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "<password>"
      }
    }
  }
}
```

Key details:
- Uses the **virtualenv python** (`.venv/bin/python`), not system python
- `cwd` must be the project root so relative imports work
- `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` must match the running Neo4j instance
- The server reads `.env` via `load_dotenv()` but Claude Desktop env vars take precedence

### Intended Workflow After Setup

```
LLM calls: load_recipe("payroll_v1")
         → get_processing_instructions("payroll_v1", format_id="qb_journal_v1")
         → [reads source CSV]
         → [computes measures per instructions]
         → [generates journal entries]
         → validate_entries(...)
         → [writes output]
```

The Neo4j MCP can remain active alongside for inspection/debugging ("show me what's in the graph"), but processing should always go through the FP_core tools.

### Files to create/modify
- `~/.config/Claude/claude_desktop_config.json` — add fp_core server entry (user does this manually)
- No code changes needed for Part 1

---

## Part 2: Fix Two Bugs in `summarize_processing_instructions`

These bugs cause problems even when using the FP_core MCP.

**File:** `mcp_server/summarizers.py`

### Bug A — OutputColumn metadata stripped (lines 240–243)

Current code emits only `position` + `name` per column. Replace:

```python
"columns": [
    {"position": _prop(c, "position"), "name": _prop(c, "name")}
    for c in out_cols_sorted
],
```

With:

```python
"columns": [
    {
        k: v for k, v in {
            "position":            _prop(c, "position"),
            "name":                _prop(c, "name"),
            "data_type":           _prop(c, "data_type"),
            "required":            _prop(c, "required"),
            "description":         _prop(c, "description"),
            "source_mapping":      _prop(c, "source_mapping"),
            "sign_convention":     _prop(c, "sign_convention"),
            "format_pattern":      _prop(c, "format_pattern"),
            "exclude_from_output": _prop(c, "exclude_from_output"),
        }.items()
        if v is not None
    }
    for c in out_cols_sorted
],
```

`if v is not None` (NOT `if v`) preserves `required=False` and `exclude_from_output=False` — boolean `False` is a meaningful instruction the LLM must see.

### Bug B — `group_by` silently absent (lines 167–169)

When a Measure has no `group_by`, the key is omitted entirely. The LLM can't distinguish "aggregate all rows" from "instructions incomplete." Replace:

```python
group_by_str = _prop(m, "group_by")
if group_by_str:
    measure_entry["group_by"] = group_by_str.split(",")
```

With:

```python
group_by_str = _prop(m, "group_by")
if group_by_str:
    measure_entry["group_by"] = [s.strip() for s in group_by_str.split(",")]
else:
    measure_entry["group_by"] = []
```

`group_by` is now always present. `[]` means "aggregate all rows as a single total." The `.strip()` also fixes a latent whitespace bug in the truthy path.

### Part 2 Tests (`tests/mcp_server/test_summarizers.py`)

**Update broken test** (line 704–710) — `test_measure_no_aggregation_fields`:
```python
# Change assertion from:
assert "group_by" not in m
# To:
assert m["group_by"] == []
```

**Add 5 new tests** to `TestSummarizeProcessingInstructions`:
1. `test_group_by_always_emitted` — present on every measure, `[]` when not set
2. `test_output_columns_include_data_type_and_required` — both present when format_pattern given
3. `test_output_column_required_false_is_present` — `False` survives `is not None` filter
4. `test_output_columns_include_source_mapping_when_set` — optional field appears when set
5. `test_output_columns_omit_absent_optionals` — absent properties not in JSON

---

## Part 3: `patch_recipe` Tool (Feedback Loop)

When the LLM processes a file and gets something wrong, the user corrects it. Those corrections should be saved to the graph so future `get_processing_instructions` calls include the right metadata (e.g. add `source_mapping` to an OutputColumn, add `description` to a Measure).

### Step 1 — `patch_node` in `persistence/operations.py`

Add after `verify_format` (after line 178):

```python
def patch_node(
    conn: Neo4jConnection,
    label: str,
    merge_props: Dict[str, Any],
    patch_props: Dict[str, Any],
) -> Dict[str, Any]:
    """Partially update optional properties on an existing node.

    Uses MATCH + SET (not MERGE) so it fails clearly if the node doesn't exist.
    Returns the node's properties after update (internal _-prefixed keys excluded).
    Raises ValueError if no node matches merge_props.
    """
    where_clause = " AND ".join(f"n.{k} = ${k}" for k in merge_props)
    set_clause   = ", ".join(f"n.{k} = $p_{k}" for k in patch_props)
    params: Dict[str, Any] = {**merge_props, **{f"p_{k}": v for k, v in patch_props.items()}}
    query = f"""
    MATCH (n:{label})
    WHERE {where_clause}
    SET {set_clause}
    RETURN properties(n) AS props
    """
    records = conn.run_query(query, params)
    if not records:
        raise ValueError(f"No {label} node found matching {merge_props}")
    return {k: v for k, v in records[0]["props"].items() if not k.startswith("_")}
```

Export in `persistence/__init__.py` — add `"patch_node"` to `__all__`.

### Step 2 — `patch_recipe` in `mcp_server/tools.py`

**Registry** (module-level constant in tools.py):
```python
_PATCHABLE_NODES = {
    # node_type: (NodeLabel, identity_fields, scope_key)
    "measure":       (NodeLabel.MEASURE,      ("recipe_id", "name"),      "recipe_id"),
    "mapping_rule":  (NodeLabel.MAPPING_RULE,  ("recipe_id", "rule_name"), "recipe_id"),
    "account_slot":  (NodeLabel.ACCOUNT_SLOT,  ("recipe_id", "slot_id"),   "recipe_id"),
    "output_column": (NodeLabel.OUTPUT_COLUMN, ("format_id",  "name"),     "format_id"),
}
```

**Pure validation helper** (extracted for unit testing):
```python
def _validate_patch_request(node_type, node_key, patches) -> Optional[str]:
```
Validates: node_type in registry, node_key has all identity fields, patches keys are all `optional` (from `merged_ontology()[label].properties.optional`), no required-field patches, value types match schema.

**Tool handler logic:**
1. Validate node_type → return error if invalid
2. Parse `node_key` and `patches` from JSON strings
3. Call `_validate_patch_request` → return error string on failure
4. Inject `recipe_id` / `format_id` from tool parameter into merge props
5. Call `patch_node(conn, label.value, merge_props, patch_props)`
6. Evict stale cache: `_loaded_recipes.pop(recipe_id, None)` or `_loaded_formats.pop(format_id, None)`
7. Return JSON: `{node_type, node_key, patches_applied, updated_properties, cache_invalidated}`

### Step 3 — Tests

**`tests/mcp_server/test_patch_recipe.py`** (pure, ~7 tests on `_validate_patch_request`):
- Invalid node_type rejected
- Valid node types accepted
- Required field patch rejected (e.g. patching `name` on a Measure)
- Unknown field patch rejected
- Optional field patch accepted (e.g. `description`)
- Wrong type in patch rejected
- Missing identity field in node_key rejected

**`tests/persistence/test_operations.py`** (integration, `TestPatchNode`, ~2 tests, skipped without `NEO4J_URI`):
- `test_patch_updates_property_and_returns_new_props`
- `test_patch_nonexistent_node_raises_value_error`

---

## Canonical Count Updates

| File | Field | Before | After |
|------|-------|--------|-------|
| `CLAUDE.md` | MCP Tools | 6 | 7 |
| `CLAUDE.md` | Total tests | 394 | ~410 |
| `mcp_server/CLAUDE.md` | Tools table | 6 rows | 7 rows (add patch_recipe) |
| `persistence/CLAUDE.md` | Operations table | 7 entries | 8 entries (add patch_node) |

---

## Implementation Order

1. **Part 1:** User edits `~/.config/Claude/claude_desktop_config.json` to add fp_core server entry — no code changes
2. `mcp_server/summarizers.py` — Fix Bug A + Bug B
3. `tests/mcp_server/test_summarizers.py` — Update broken test + 5 new tests
4. `persistence/operations.py` — Add `patch_node`
5. `persistence/__init__.py` — Export `patch_node`
6. `mcp_server/tools.py` — Add `_PATCHABLE_NODES`, `_validate_patch_request`, `patch_recipe`
7. `tests/mcp_server/test_patch_recipe.py` — New pure test file
8. `tests/persistence/test_operations.py` — Add `TestPatchNode`
9. `CLAUDE.md`, `mcp_server/CLAUDE.md`, `persistence/CLAUDE.md` — Update counts/tables

---

## Verification

```bash
# Part 2: summarizer changes
pytest tests/mcp_server/test_summarizers.py -v

# Part 3: new pure tests
pytest tests/mcp_server/test_patch_recipe.py -v

# Integration (requires NEO4J_URI)
pytest tests/persistence/test_operations.py -v

# Full suite — no regressions
pytest
```

After adding fp_core to Claude Desktop: restart Claude Desktop, ask the LLM to call `load_recipe("payroll_v1")` and confirm the tool appears in the available tools list.