# Bug Log

Tracking issues discovered during real agent sessions using the FP_core MCP server.

---

## BUG-001: Agent uses plural `debits`/`credits` keys instead of singular `debit`/`credit`

**Date:** 2026-02-15

**Context:** Agent session from `fp_workspace/` calling `build_and_save_pipeline` via MCP.

**Symptom:** Pipeline saved successfully but DEBITS/CREDITS edges were missing. MappingRule nodes existed but had no connections to AccountSlot nodes. Gate 1 validation (`validate_mapping_rule_completeness`) should have caught this, but the rules were orphaned — no slots, no edges, no error.

**Root cause:** The agent passed `"debits"` and `"credits"` (plural) as keys in the rule spec. The builder (`builders.py:215`) expects `"debit"` and `"credit"` (singular). The `rule_spec.get("debit")` returned `None`, the `continue` on line 218 skipped slot/edge creation silently, and the pipeline saved without the accounting wiring.

**Why the agent got it wrong:** The MCP tool has no schema documentation for the `pipeline_spec` JSON structure. The agent inferred key names from the RelationshipType enum (`DEBITS`, `CREDITS`) and the domain vocabulary, which are all plural. Singular `debit`/`credit` is a non-obvious convention.

**Fix options:**
1. **Accept both** — normalize plural to singular in `_build_recipe_nodes` before processing
2. **Document the spec** — add a JSON schema or example to the `build_and_save_pipeline` tool description so the agent sees the exact keys
3. **Fail loudly** — if a rule spec has no `debit`/`credit` keys, return a warning or error instead of silently skipping

**Status:** Open — workaround is to use singular keys. Underlying issue (silent skip + no spec docs) remains.

---

## BUG-002: `get_processing_instructions` omits `account_type` and `normal_balance` from account details

**Date:** 2026-02-26

**Context:** User session building and inspecting a recipe with income/expense accounts via MCP tools.

**Symptom:** The `get_processing_instructions` response includes `account_code` and `account_name` for each debit/credit slot, but does not include `account_type` or `normal_balance`. The user cannot determine from the API response alone whether an account is an income, expense, asset, or liability account — or which direction (debit/credit) is its normal balance.

**Impact:** Processing logic cannot infer debit/credit direction automatically from the recipe instructions. The agent (or user) must know the account type out-of-band or trust the recipe author's intent. This undermines the "graph tells you everything" design principle — the data is stored on the Account/AccountSlot nodes in Neo4j but not surfaced in the summarizer output.

**Root cause:** `summarize_processing_instructions` in `mcp_server/summarizers.py` only extracts `account_code` and `account_name` when building the debits/credits arrays. The `account_type` and `normal_balance` properties exist on the Account nodes in the cached GraphPattern but are not included in the output dict.

**Fix:** Add `account_type` and `normal_balance` fields to each account entry in the `debits` and `credits` arrays of the processing instructions output. This is a summarizer-only change (L5), no domain or persistence changes needed.

**Status:** Fixed — 2 lines added to `_slot_accounts` in `mcp_server/summarizers.py`, 3 tests added. See `specs/features/account_metadata_in_instructions.md`.

---

## BUG-003: `rule.when` only supports a single condition — no AND/OR compound conditions

**Date:** 2026-02-26

**Context:** User session building an A/R (accounts receivable) recipe that needed two filters on a rule: a location code filter AND a dispute exclusion filter.

**Symptom:** The `rule.when` field accepts a single `condition_id` string. There is no way to combine multiple conditions (e.g., `LocCode = "US" AND status != "disputed"`). The user had to choose one filter dimension per rule and handle the other exclusion separately — either at the measure level or in post-processing.

**Impact:** Real-world accounting rules frequently have compound conditions (e.g., "this rule fires for domestic invoices that are not in dispute"). The current single-condition model forces workarounds: duplicating rules per condition combination, pre-filtering at the measure level, or accepting incomplete filtering.

**Root cause:** The condition system (L1 types, L3 logic, L5 builder) was designed with a 1:1 relationship between MappingRule and Condition via the `WHEN` edge. The `when` field in the JSON spec is a single string, not an array. The builder creates one WHEN relationship per rule. There is no `AND`/`OR` combinator in the Condition model.

**Fix options:**
1. **Compound condition node** — Add a `CompoundCondition` node type with `operator: "and" | "or"` and `COMBINES` edges to child Condition nodes. `rule.when` points to the compound node. Touches L1 (new type), L2 (schema), L3 (builder), L5 (spec format).
2. **`when` as array with implicit AND** — Change `rule.when` from a single string to an array of condition_ids. All conditions must be true for the rule to fire (implicit AND). Simpler but no OR support. Touches L3 (builder), L5 (spec format + builder).
3. **Expression-based conditions** — Replace simple column/operator/value conditions with a mini-expression language (e.g., `"when": "is_domestic AND NOT is_disputed"`). Most flexible but hardest to implement and validate.

**Recommendation:** Option 2 (array with implicit AND) covers the most common case (multiple filters that all must pass) with the least architectural change. OR conditions are rarer in accounting rule filtering and can be modeled as separate rules.

**Status:** Open
