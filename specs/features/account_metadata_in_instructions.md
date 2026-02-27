# Spec: Surface account_type and normal_balance in Processing Instructions

> **Status:** Draft
> **Created:** 2026-02-26
> **Spec type:** Feature

---

## Purpose

The `get_processing_instructions` tool returns `account_code` and `account_name` for each debit/credit slot but omits `account_type` and `normal_balance`. These properties are required on every Account node in the ontology and are stored in Neo4j, but the summarizer silently drops them. This means agents processing data cannot infer debit/credit direction from the recipe alone — they must know account metadata out-of-band. Surfacing these two fields completes the data path so the recipe graph truly "tells you everything" needed for journal entry generation.

Discovered via user feedback during a live recipe-building session (logged as BUG-002).

---

## Layer Placement

**Primary layer:** L5 — MCP Server (summarizer only)
**Layers touched:**

| Layer | Package | What changes |
|-------|---------|--------------|
| L1 Types | `domain/types.py` or `types_recipe.py` | No changes |
| L2 Ontology | `domain/ontology.py` or `ontology_recipe.py` | No changes |
| L3 Logic | `domain/logic.py` | No changes |
| L4 Persistence | `persistence/` | No changes |
| L5 MCP Server | `mcp_server/summarizers.py` | Add two fields to `_slot_accounts` output |

---

## Domain Types (L1)

No Layer 1 changes required. The `Account` dataclass and `_ACCOUNT_PROPS` ontology schema already define `account_type` and `normal_balance` as required properties.

---

## Schema Definitions (L2)

No Layer 2 changes required. `_ACCOUNT_PROPS` in `domain/ontology.py:122-134` already declares:

```python
_ACCOUNT_PROPS = PropertySchema(
    required=frozenset({"code", "name", "account_type", "normal_balance"}),
    optional=frozenset({"is_active", "semantic_type", "expected_behavior"}),
    types={
        "code": str,
        "name": str,
        "account_type": str,
        "normal_balance": str,
        "is_active": bool,
        "semantic_type": str,
        "expected_behavior": str,
    },
)
```

Both fields are **required** — they are guaranteed present on every Account node that passes Gate 1 validation.

**Gate classification:**
- Gate 1: No changes
- Gate 2: No changes

---

## Pure Functions (L3)

No Layer 3 changes required.

---

## Persistence Contract (L4)

No Layer 4 changes required.

---

## MCP Interface (L5)

### Tool signatures affected

No tool signature changes. `get_processing_instructions` returns a JSON string — the change is in the content of the JSON payload, not the function signature.

### Summarizer change (`mcp_server/summarizers.py`)

The fix is in `_slot_accounts` (lines 67-82), which resolves AccountSlot → MAPPED_TO → Account and builds the account summary dict. Currently it extracts only `code` and `name`:

```python
# Current (lines 67-82):
def _slot_accounts(
    pattern: GraphPattern,
    slots: tuple[Node, ...],
) -> list[dict[str, Any]]:
    accounts = []
    for slot in slots:
        acct = _resolve_account_for_slot(pattern, slot.id)
        if acct:
            accounts.append(
                {
                    "account_code": _prop(acct, "code"),
                    "account_name": _prop(acct, "name"),
                }
            )
    return accounts

# After:
def _slot_accounts(
    pattern: GraphPattern,
    slots: tuple[Node, ...],
) -> list[dict[str, Any]]:
    accounts = []
    for slot in slots:
        acct = _resolve_account_for_slot(pattern, slot.id)
        if acct:
            accounts.append(
                {
                    "account_code": _prop(acct, "code"),
                    "account_name": _prop(acct, "name"),
                    "account_type": _prop(acct, "account_type"),
                    "normal_balance": _prop(acct, "normal_balance"),
                }
            )
    return accounts
```

### JSON spec format

No input spec changes.

### Summarizer output

The `debits` and `credits` arrays in processing instructions gain two fields per account entry:

```json
{
  "rules": [
    {
      "name": "gross_pay_entry",
      "source_measure": "total_gross",
      "debits": [
        {
          "account_code": "6100",
          "account_name": "Salary Expense",
          "account_type": "expense",
          "normal_balance": "debit"
        }
      ],
      "credits": [
        {
          "account_code": "2200",
          "account_name": "Payroll Payable",
          "account_type": "liability",
          "normal_balance": "credit"
        }
      ]
    }
  ]
}
```

---

## Data Flow

```
Account node in cached GraphPattern
  properties: {code, name, account_type, normal_balance, is_active, ...}
    |
    v
_slot_accounts() — extract code, name, account_type, normal_balance
    |
    v
summarize_processing_instructions() — include in debits/credits arrays
    |
    v
JSON response to agent
```

No new data paths — the Account node is already resolved via `_resolve_account_for_slot`. The change adds two more `_prop()` reads from the same node.

---

## Examples

### Happy path

```json
// Processing instructions output (before)
{
  "debits": [{"account_code": "6100", "account_name": "Salary Expense"}]
}

// Processing instructions output (after)
{
  "debits": [
    {
      "account_code": "6100",
      "account_name": "Salary Expense",
      "account_type": "expense",
      "normal_balance": "debit"
    }
  ]
}
```

### Edge case: Account missing account_type (should not happen after Gate 1)

If an Account node somehow lacks `account_type` or `normal_balance` (e.g., loaded from an old graph before validation was enforced), `_prop()` returns `None`:

```json
{
  "account_code": "6100",
  "account_name": "Salary Expense",
  "account_type": null,
  "normal_balance": null
}
```

This is acceptable — `None` in JSON signals the data is missing, and the agent can handle it. No need for a fallback or error.

---

## Invariants

### Graph semantics
- No changes to the Neo4j graph or cached GraphPattern objects
- `account_type` and `normal_balance` are read-only from the Account node

### Functional constraints
- `_slot_accounts` remains a pure function (no I/O)
- The function reads from the same Account node it already resolves — no new graph traversal
- Backward-compatible in the sense that existing consumers gain additional fields; no fields are removed or renamed

### Purity boundaries
- **Modified function that is pure**: `_slot_accounts` (no I/O, no side effects)
- **New functions that touch I/O**: None
- **Composition approach**: No change — `_slot_accounts` is called by `summarize_processing_instructions` exactly as before
- domain/ must never import from persistence/ or mcp_server/
- Pure functions (builders, summarizers) must not import from persistence/

---

## Integration

### Files modified

| File | Change |
|------|--------|
| `mcp_server/summarizers.py` | Add `account_type` and `normal_balance` to dict in `_slot_accounts` (2 lines added) |
| `tests/mcp_server/test_summarizers.py` | Add assertions for new fields in existing and new tests |

### Files created

None.

### Canonical counts affected

| Constant | Before | After | Delta |
|----------|--------|-------|-------|
| `Total tests` | 413 | ~417 | +~4 |

No changes to NodeLabel, RelationshipType, ontology, constraint, merge key, or MCP tool counts.

**Count-assertion tests:** Only the total test count in CLAUDE.md updates. No new count-assertion tests needed.

---

## Test Strategy

### New tests (`tests/mcp_server/test_summarizers.py`)

| Test class / method | What it verifies |
|---------------------|-----------------|
| `TestSlotAccounts::test_account_type_included` | Each account entry includes `account_type` |
| `TestSlotAccounts::test_normal_balance_included` | Each account entry includes `normal_balance` |
| `TestProcessingInstructions::test_debit_account_metadata` | Debit accounts in processing instructions include `account_type` and `normal_balance` |
| `TestProcessingInstructions::test_credit_account_metadata` | Credit accounts in processing instructions include `account_type` and `normal_balance` |

### Existing tests

The existing test `TestProcessingInstructions::test_debits_credits_resolved` (which asserts `account_code` == "6100") will continue to pass — we're adding fields, not changing existing ones. The test fixtures already include `account_type` and `normal_balance` on all Account nodes (e.g., `acct_6100` has `"account_type": "expense"`, `"normal_balance": "debit"`).

### Expected new test count

Current: 413 | Added: ~4 | New total: ~417

---

## Success Criteria

- [ ] `get_processing_instructions` response includes `account_type` and `normal_balance` on every debit/credit account entry
- [ ] Values match the Account node properties in the graph (expense, liability, asset, revenue, debit, credit)
- [ ] Existing processing instruction tests pass unchanged
- [ ] No changes to any layer except L5 summarizer
- [ ] Canonical counts updated in CLAUDE.md (test count only)

---

## Out of Scope

- **Surfacing `is_active` in processing instructions**: Useful but a separate concern — `is_active` is an optional property and relates to Gate 2 validation, not processing logic. Can be added later if needed.
- **Surfacing slot metadata** (`slot_id`, `role`, `entry_type`): The AccountSlot properties are recipe-internal wiring. Processing instructions show the resolved Account, not the intermediate slot. Revisit if agents need slot-level detail.
- **Changing `load_recipe` summary**: The recipe load response shows rule summaries (name, measure, priority) but not account details. Adding accounts there is a separate scope.

---

## Open Questions

None. The design is fully determined by the existing ontology schema and the `_slot_accounts` helper.