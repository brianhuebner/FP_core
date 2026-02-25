# Spec: TypeScript Tool Interfaces

> **Status:** Draft
> **Created:** 2026-02-23
> **Spec type:** Feature

---

## Purpose

LLMs parse TypeScript interfaces more reliably than JSON examples or prose descriptions. Two of the three MCP tools that accept JSON string parameters (`build_output`, `validate_entries`) have no input shape documentation at all — agents must reverse-engineer the expected format from the `build_and_save_pipeline` example or fail through trial and error. Defining TypeScript interfaces for all three tools closes these gaps and establishes a pattern for future tools.

---

## Layer Placement

**Primary layer:** L5 — MCP Server
**Layers touched:**

| Layer | Package | What changes |
|-------|---------|--------------|
| L1 Types | — | No changes |
| L2 Ontology | — | No changes |
| L3 Logic | — | No changes |
| L4 Persistence | — | No changes |
| L5 MCP Server | `mcp_server/tools.py` | Docstrings on `build_and_save_pipeline`, `build_output`, `validate_entries` gain TS interface blocks |

---

## Domain Types (L1)

No Layer 1 changes required. This spec adds documentation only.

---

## Schema Definitions (L2)

No Layer 2 changes required. This spec adds documentation only.

---

## Pure Functions (L3)

No Layer 3 changes required. This spec adds documentation only.

---

## Persistence Contract (L4)

No Layer 4 changes required.

---

## MCP Interface (L5)

### TypeScript Interface Definitions

All interfaces are derived from field access patterns in `mcp_server/builders.py` and `mcp_server/tools.py`. The ground truth is what the builder code actually reads — these interfaces codify that contract.

#### `build_and_save_pipeline` — `PipelineSpec`

```typescript
interface PipelineSpec {
  recipe_id: string;
  schema: SchemaSpec;
  recipe: RecipeSpec;
}

interface SchemaSpec {
  name: string;
  source_system: string;
  file_pattern?: string;
  row_grain?: string;
  columns: ColumnSpec[];
  measures: MeasureSpec[];
}

interface ColumnSpec {
  name: string;
  position: number;
  data_type: "string" | "decimal" | "date" | "integer" | "boolean";
  role: "identifier" | "amount" | "date" | "category" | "text";
  required?: boolean;
  description?: string;
}

interface MeasureSpec {
  name: string;
  operation: "sum" | "count" | "avg" | "min" | "max";
  source_column?: string;
  description?: string;
  group_by?: string[];
  split_by?: string;
  split_column?: string;
}

interface RecipeSpec {
  name: string;
  source_schema?: string;
  batch_key?: string;
  journal_no_format?: string;
  visibility?: string;
  rules: RuleSpec[];
  conditions?: ConditionSpec[];
  references?: ReferenceSpec[];
}

interface RuleSpec {
  rule_name: string;
  source_measure: string;
  priority?: number;
  memo_template?: string;
  debit: SlotSpec;
  credit: SlotSpec;
  when?: string;            // references a condition_id
  uses_references?: string[]; // references Reference.id values
}

interface SlotSpec {
  slot_id: string;
  role: string;
  account_code?: string;
  account_name?: string;
  account_type?: "asset" | "liability" | "equity" | "expense" | "revenue";
  normal_balance?: "debit" | "credit";
}

interface ConditionSpec {
  condition_id: string;
  column: string;
  operator: "equals" | "not_equals" | "greater_than" | "less_than"
          | "is_null" | "is_not_null" | "always";
  value?: string;  // omit for is_null, is_not_null, always
}

interface ReferenceSpec {
  id: string;
  type: string;
  properties?: Record<string, unknown>;
}
```

#### `build_output` — `OutputFormatSpec`

```typescript
interface OutputFormatSpec {
  format_id: string;
  name: string;
  target_system: string;
  file_format: string;
  version?: string;
  columns: OutputColumnSpec[];
  validation_rules?: ValidationRuleSpec[];
  entry_structure?: EntryStructureSpec;
}

interface OutputColumnSpec {
  name: string;
  position: number;
  data_type: string;
  required?: boolean;
  source_mapping?: string;
}

interface ValidationRuleSpec {
  name: string;
  expression: string;
  scope: string;
  description?: string;
}

interface EntryStructureSpec {
  grouping_column: string;
  entry_separator: string;
  date_column: string;
}
```

#### `validate_entries` — `JournalEntry[]`

```typescript
// Top-level input is JournalEntry[]
interface JournalEntry {
  lines: JournalLine[];
}

interface JournalLine {
  amount: number | string;   // parsed via Decimal(str(value))
  direction: "debit" | "credit";
  account_code?: string;     // used for account-level checks when recipe_id provided
}
```

### Tool signatures affected

No tool signatures change. The three tools already accept JSON strings — this spec defines what shape those strings must have.

### Integration pattern

Each tool's docstring gains a TypeScript interface block between the prose description and the constraints/notes section. The interface block is fenced with ` ```typescript ` and appears after the opening description paragraph. The existing JSON example in `build_and_save_pipeline` is kept as-is below the interface — both representations serve different purposes (the interface defines the shape precisely, the example shows a concrete instance).

### Summarizer output

No summarizer changes. This spec covers input types only.

---

## Data Flow

```
Tool docstring (contains TS interface)
    |
    v
MCP protocol exposes docstring as tool description
    |
    v
Agent LLM reads interface definition
    |
    v
Agent generates conforming JSON string
    |
    v
Tool handler: json.loads(input_str) → dict
    |
    v
builders.py accesses fields matching the interface
```

---

## Examples

### build_output — currently undocumented, interface makes shape explicit

```json
{
  "format_id": "journal_csv_v1",
  "name": "Journal CSV Export",
  "target_system": "csv_export",
  "file_format": "csv",
  "columns": [
    {"name": "journal_no", "position": 1, "data_type": "string", "required": true},
    {"name": "date", "position": 2, "data_type": "date", "required": true},
    {"name": "account_code", "position": 3, "data_type": "string", "required": true},
    {"name": "debit", "position": 4, "data_type": "decimal"},
    {"name": "credit", "position": 5, "data_type": "decimal"},
    {"name": "memo", "position": 6, "data_type": "string"}
  ],
  "validation_rules": [
    {"name": "balance_check", "expression": "sum(debit) == sum(credit)", "scope": "entry"}
  ],
  "entry_structure": {
    "grouping_column": "journal_no",
    "entry_separator": "journal_no",
    "date_column": "date"
  }
}
```

### validate_entries — currently undocumented, interface makes shape explicit

```json
[
  {
    "lines": [
      {"amount": "1500.00", "direction": "debit", "account_code": "6100"},
      {"amount": "1500.00", "direction": "credit", "account_code": "2200"}
    ]
  }
]
```

---

## Invariants

### Functional constraints
- Docstring-only change — no runtime behavior changes
- Interfaces must exactly match the field access patterns in `builders.py` and `tools.py`
- If `builders.py` changes field access, the corresponding interface must be updated

### Purity boundaries
- No new functions
- No new imports
- domain/ boundary rule preserved — this is L5-only

---

## Integration

### Files modified

| File | Change |
|------|--------|
| `mcp_server/tools.py` | Add TS interface blocks to docstrings of `build_and_save_pipeline`, `build_output`, `validate_entries` |

### Files created

None.

### Canonical counts affected

No canonical count changes.

---

## Test Strategy

### New tests

None. This is a documentation-only change — docstrings are not tested.

### Existing tests

All existing tests pass unchanged. No runtime behavior is modified.

### Expected new test count

Current: 394 | Added: 0 | New total: 394

---

## Success Criteria

- [ ] `build_and_save_pipeline` docstring contains `PipelineSpec` interface matching `builders.py` field access
- [ ] `build_output` docstring contains `OutputFormatSpec` interface matching `builders.py` field access
- [ ] `validate_entries` docstring contains `JournalEntry[]` interface matching `tools.py` field access
- [ ] All interfaces derived from actual code, not invented
- [ ] Existing JSON example in `build_and_save_pipeline` preserved below the interface
- [ ] All existing tests pass (no regressions)

---

## Out of Scope

- **Response type interfaces**: Output shapes from summarizers are not covered. They change more frequently and agents consume them reactively rather than constructing them.
- **Simple parameter tools**: `load_recipe(recipe_id: str)`, `load_format(format_id: str)`, and `get_processing_instructions(recipe_id: str, format_id: str | None)` take scalar parameters that are already self-documenting — no interface needed.
- **Verbatim docstring text**: This spec defines the interfaces and integration pattern. The exact prose surrounding the interface blocks is left to implementation.

---

## Open Questions

None. The interfaces are fully determined by the existing builder code.
