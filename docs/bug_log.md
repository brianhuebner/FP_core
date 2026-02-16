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
