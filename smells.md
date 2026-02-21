# Code Smells — FP_core

Systematic review across all 5 layers. Organized by layer/file with severity, location, description, and suggested fix.

Severity scale: **High** (correctness risk or significant maintenance burden) · **Medium** (readability/maintainability) · **Low** (minor cleanup)

---

## Layer 2: Domain Ontology

### `domain/ontology.py`

| ID | Lines | Type | Severity |
|----|-------|------|----------|
| H1a | 238–272 | Duplicate logic | **High** |

**Description:** `_outgoing` and `_incoming` constraint helpers differ only in which side of the relationship is used as the filter key (source vs. target). The entire iteration and error-building logic is copy-pasted.

**Suggested fix:** Extract a single `_check_relationship_constraints(constraints, rel, key_side)` helper parameterised on which endpoint to look up.

---

### `domain/ontology_recipe.py`

| ID | Lines | Type | Severity |
|----|-------|------|----------|
| H1b | 250–293 | Duplicate logic | **High** |
| M1a | 469–503 | Long method | **Medium** |
| M1b | 554–596 | Long method + deep nesting (3 levels) | **Medium** |
| M1c | 599–653 | Long method + deep nesting (4 levels) | **Medium** |
| M6 | 2, 4, 6 | Unused imports | **Low** |

**H1b — Duplicate constraint helpers:**
Same `_outgoing` / `_incoming` duplication as H1a, but for recipe relationship constraints. Should be consolidated with the same fix applied to `ontology.py`, or extracted to a shared utility.

**M1a — `validate_mapping_rule_completeness` (35 lines):**
Mixes graph traversal (walking rels to find slots), validation logic, and error-message formatting in a single function body. Should be split: one helper to collect slot nodes, one to check completeness, one to format the error.

**M1b — `validate_output_column_positions_unique` (43 lines):**
Accumulates a position→column mapping with a nested conditional inside a loop, then formats errors in the same pass. Three levels of nesting make the intent hard to follow. Extract the accumulation step and the uniqueness check into separate concerns.

**M1c — `validate_entry_structure_references_column` (55 lines):**
Four levels of nesting (function → loop over entry structures → loop over column refs → conditional on match). Hardest function in the file to reason about. Candidate for early-return / guard-clause refactor and extraction of the inner match logic.

**M6 — Unused imports:**
`from __future__ import annotations` (line 2), `List` from `typing` (line 4), `Node` and `Relationship` from `domain` (line 6) are imported but never referenced. Remove them.

---

## Layer 3: Pure Logic

### `domain/logic.py`

| ID | Lines | Type | Severity |
|----|-------|------|----------|
| H2 | 88–104, 189–246 | Duplicate extraction helpers | **High** |
| H2b | 115–129 | Duplicate debit/credit loop | **High** |
| L6 | 46–55, 162–169 | Long parameter lists (8 params) | **Low** |

**H2 — Four near-identical extraction helpers:**
`_get_condition_nodes`, `_get_slot_nodes`, `_get_measure_nodes`, and similar helpers (lines 189–246) all follow the same template: filter relationships by type and start-node, collect the target nodes by label. The template is copy-pasted four times with only the label/type constants changed.

**Suggested fix:** Extract a single `_collect_nodes(rels, rel_type, start_id, node_label, nodes_by_id)` helper; call it with the appropriate constants.

**H2b — Debit/credit extraction loops (lines 115–129):**
The loops that build `debit_ids` and `credit_ids` are structurally identical (filter by `RelationshipType.DEBIT` / `CREDIT`, collect `rel.end_node_id`). A single parameterised helper would eliminate the duplication.

**L6 — Long parameter lists:**
`build_recipe_pattern` (line 46–55) and `build_output_format_pattern` (line 162–169) each accept 8 positional parameters. Consider grouping related parameters into a small dataclass or config object to reduce the call-site noise.

---

## Layer 4: Persistence

### `persistence/operations.py`

| ID | Lines | Type | Severity |
|----|-------|------|----------|
| H3 | 107–130, 157–178 | Duplicate delete/verify functions | **High** |

**H3 — `delete_recipe` / `delete_format` and `verify_recipe` / `verify_format`:**
The delete functions and the verify functions are structurally identical — they differ only in the root label and the set of related labels to cascade-delete or count. The implementation is copy-pasted with label constants swapped.

**Suggested fix:** Parameterise on a `root_label` and `related_labels: list[NodeLabel]`; expose typed wrappers that call the generic implementation.

---

### `persistence/serializers.py`

| ID | Lines | Type | Severity |
|----|-------|------|----------|
| H4 | 29–35, 149–153 | Duplicate merge-key resolution | **High** |
| H5a | multiple | Magic string `"_node_id"` | **High** |
| M7 | 73–139 | Long method (67 lines) | **Medium** |

**H4 — Merge-key resolution appears twice:**
The logic that looks up `MERGE_KEYS[node.label]` and builds the identity property dict is duplicated between `serialize_node` and the inline relationship serialiser. Extract a `_merge_props(node)` helper called from both sites.

**H5a — Magic string `"_node_id"`:**
The string literal `"_node_id"` is hardcoded in 7+ places across this file with no named constant. A typo would produce a silent runtime failure rather than a `NameError`.

**Suggested fix:** `NODE_ID_KEY = "_node_id"` at module level; replace all occurrences.

**M7 — `serialize_relationship` (67 lines):**
Handles four concerns in one method: resolving start/end merge keys, building the MERGE clause, building SET clauses, and assembling the final Cypher string. Should be split into focused helpers.

---

### `persistence/deserializers.py`

| ID | Lines | Type | Severity |
|----|-------|------|----------|
| H5b | multiple | Magic string `"_node_id"` | **High** |
| L7 | 36 | Undocumented defensive copy | **Low** |

**H5b:** Same magic string issue as H5a. Should use the same `NODE_ID_KEY` constant once it is defined (ideally in a shared `persistence/constants.py` or at the top of each module).

**L7 — Defensive copy at line 36:**
`records = list(records)` (or equivalent) is performed without a comment explaining why. If this is guarding against an exhausted cursor or a mutable default, document it. If it is unnecessary, remove it.

---

## Layer 5: MCP Server

### `mcp_server/tools.py`

| ID | Lines | Type | Severity |
|----|-------|------|----------|
| M2 | 117–133+ | Duplicate "auto-load if not cached" pattern | **Medium** |
| M3 | 45–50, 75–80, 207–215 | Inconsistent error response shape | **Medium** |
| M5 | 436–451 | O(n³) account-validation loop | **Medium** |

**M2 — Repeated cache-miss / auto-load pattern:**
The pattern "if recipe_id not in cache → load from Neo4j → store in cache → raise if still missing" appears at least three times across tool handlers. Extract a `_require_recipe(recipe_id)` and `_require_format(format_id)` helper that centralises cache access and error raising.

**M3 — Inconsistent error response shape:**
Some tool handlers return `{"error": "..."}`, others return `{"error": "...", "hint": "..."}`. Callers cannot reliably check for the presence of `"hint"`. Define a small `_error(msg, hint=None)` builder and use it consistently.

**M5 — O(n³) account-validation loop (lines 436–451):**
Validates journal entry accounts by iterating over all entries × all lines × all known accounts for each check. Build a `set` of valid account codes once before the loop; reduce the inner check to O(1).

---

### `mcp_server/builders.py`

| ID | Lines | Type | Severity |
|----|-------|------|----------|
| M4 | 98 | Implicit `group_by` encoding | **Medium** |
| L5 | 200–208, 470–476 | Workaround code lacks issue links / sunset dates | **Low** |
| L8 | 96–98 | Magic encoding convention undocumented at definition | **Low** |

**M4 / L8 — `group_by` stored as comma-joined string:**
`group_by` list is serialised as `",".join(group_by)` and deserialised by splitting on `","`. This silently corrupts any column name that contains a comma. The encoding is undocumented at the definition site.

**Suggested fix:** Store as a JSON array string (`json.dumps(group_by)`) or as a repeated property if Neo4j supports it; document the encoding choice inline.

**L5 — BUG-001 workaround and backward-compat blocks:**
Comments reference "BUG-001" and "backward-compat" but contain no issue tracker link, no explicit test asserting the workaround behaviour, and no sunset condition. Add a link to the tracking issue and a `# TODO(sunset): remove after X` note.

---

### `mcp_server/summarizers.py`

| ID | Lines | Type | Severity |
|----|-------|------|----------|
| M4 | 169 | Same implicit `group_by` decoding | **Medium** |
| M8 | 191–200 | Closure defined inside loop | **Medium** |

**M8 — Closure inside loop:**
A lambda or nested function defined inside a `for` loop captures the loop variable by reference, which is a classic Python gotcha. If the closure is used after the loop iteration advances, it will see the final value of the loop variable, not the value at definition time.

**Suggested fix:** Promote the closure to a named module-level function and pass the loop variable as an explicit argument.

---

### `mcp_server/__init__.py`

| ID | Lines | Type | Severity |
|----|-------|------|----------|
| L4 | 34 | Weak type annotation | **Low** |

**L4 — `_connection: Optional[object]`:**
The module-level connection is typed as `Optional[object]` instead of `Optional[Neo4jConnection]`. This suppresses IDE type-checking on every access of `_connection`. Change to `Optional[Neo4jConnection]` and import the type at the top of the file.

---

## Tests

| ID | File | Lines | Type | Severity |
|----|------|-------|------|----------|
| T1 | test_summarizers.py | 32–298 | Massive fixture | **Medium** |
| T2 | test_types_recipe.py | 49–120 | Repetitive immutability tests | **Low** |
| T3 | test_ontology_recipe.py | 35–44 | Magic count assertions | **Low** |
| T4 | test_logic.py | 214–285 | Repeated test setup | **Low** |

**T1 — 260-line fixture in `test_summarizers.py`:**
A single `@pytest.fixture` builds the entire graph pattern used by all summariser tests. It is hard to scan and breaks the principle of minimal fixtures. Break it into composable sub-builders (one per node/relationship group) and compose them per test class.

**T2 — 8 near-identical immutability tests in `test_types_recipe.py`:**
Each test checks that a different frozen dataclass raises `FrozenInstanceError` on mutation. The test bodies are structurally identical. Replace with a single `@pytest.mark.parametrize` over the list of dataclass types and the field to mutate.

**T3 — Magic count assertions in `test_ontology_recipe.py`:**
Assertions like `assert len(RECIPE_ONTOLOGY) == 12` hardcode the expected count as a literal. If the count changes, the failure message does not indicate what constant was intended. Reference the canonical-count constants from `CLAUDE.md` (or define them as module-level constants) so failures are self-explanatory.

**T4 — Repeated setup in `test_logic.py` (lines 214–285):**
The same recipe graph construction block (nodes + relationships) is copy-pasted into 4+ test methods. Extract a shared `@pytest.fixture` or a module-level builder function to DRY this up.

---

## Summary Table

| ID | File | Severity | Theme |
|----|------|----------|-------|
| H1a | ontology.py | High | Duplicate constraint helpers |
| H1b | ontology_recipe.py | High | Duplicate constraint helpers |
| H2 | logic.py | High | Duplicate extraction helpers |
| H2b | logic.py | High | Duplicate debit/credit loops |
| H3 | operations.py | High | Duplicate delete/verify functions |
| H4 | serializers.py | High | Duplicate merge-key resolution |
| H5a | serializers.py | High | Magic string `"_node_id"` |
| H5b | deserializers.py | High | Magic string `"_node_id"` |
| M1a | ontology_recipe.py | Medium | Long method |
| M1b | ontology_recipe.py | Medium | Long method + deep nesting |
| M1c | ontology_recipe.py | Medium | Long method + deep nesting |
| M2 | tools.py | Medium | Duplicate cache-miss pattern |
| M3 | tools.py | Medium | Inconsistent error shape |
| M4 | builders.py, summarizers.py | Medium | Fragile `group_by` encoding |
| M5 | tools.py | Medium | O(n³) validation loop |
| M7 | serializers.py | Medium | Long method (4 concerns) |
| M8 | summarizers.py | Medium | Closure defined inside loop |
| T1 | test_summarizers.py | Medium | Massive fixture |
| L4 | mcp_server/__init__.py | Low | Weak type annotation |
| L5 | builders.py | Low | Workaround lacks issue link/sunset |
| L6 | logic.py | Low | Long parameter lists |
| L7 | deserializers.py | Low | Undocumented defensive copy |
| L8 | builders.py | Low | Undocumented encoding convention |
| M6 | ontology_recipe.py | Low | Unused imports |
| T2 | test_types_recipe.py | Low | Repetitive parametrizable tests |
| T3 | test_ontology_recipe.py | Low | Magic count assertions |
| T4 | test_logic.py | Low | Repeated test setup |
