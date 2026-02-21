# Spec: Output Format Selection

> **Status:** Draft
> **Created:** 2026-02-16
> **Spec type:** Feature

---

## Purpose

A recipe defines *accounting logic* — how source data becomes journal entries. An output format defines *presentation* — how those entries are delivered. Today these are welded together: `format_id = recipe_id`, one format per recipe, baked into the pipeline spec. A user processing the same payroll recipe should be able to say "show me a general journal" for review, then "give me the QuickBooks import file" for production — without rebuilding the recipe. Future output types (payment files, invoices, AP vouchers) should be addable without touching recipe logic.

This spec decouples output formats from recipes, enables multiple formats per recipe, and gives agents a way to select which format to use at processing time.  

---

## Layer Placement

**Primary layer:** L5 — MCP Server (builder, summarizer, tools)
**Layers touched:**

| Layer | Package | What changes |
|-------|---------|--------------|
| L1 Types | `domain/types_recipe.py` | Nothing — OutputFormat already has its own `recipe_id` + `name` identity |
| L2 Ontology | `domain/ontology_recipe.py` | Add `PRODUCES_FORMAT` relationship constraint (AccountingRecipe → OutputFormat) |
| L3 Logic | `domain/logic.py` | Add `build_produces_format_rel`, update `compose_pipeline_pattern` to accept multiple output patterns |
| L4 Persistence | `persistence/operations.py` | Update `load_pattern_by_recipe` to find formats via relationship traversal, not `format_id = recipe_id` |
| L5 MCP Server | `mcp_server/builders.py`, `summarizers.py`, `tools.py` | Support `formats[]` array in pipeline spec, format selection in processing instructions |

---

## Current State (What's Broken)

The coupling lives in four places:

| Location | What it does | Problem |
|----------|--------------|---------|
| `mcp_server/builders.py:310,335` | Sets `format_id = recipe_id` on OutputColumn and ValidationRule | Cannot have format_id distinct from recipe_id |
| `persistence/operations.py:41` | `WHERE n.recipe_id = $id OR n.format_id = $id` | Assumes format_id equals recipe_id; a distinct format_id would be invisible |
| `dogfood/load_payroll.py:319` | `FORMAT_ID = RECIPE_ID` comment: "must equal recipe_id" | Documents the coupling as intentional |
| `mcp_server/builders.py:298` | `"recipe_id": recipe_id` on OutputFormat node | OutputFormat keyed to recipe, not independently identifiable |

The domain types and ontology already support separation — `OutputColumn.format_id` and `OutputFormat.recipe_id` are distinct fields. The coupling is purely in the builder and persistence queries.

---

## Design

### Core Concept: `format_id` becomes a first-class identity

Each output format gets its own `format_id`, derived from `recipe_id` + format name:
```
format_id = "{recipe_id}::{format_name}"
```

Example:
```
recipe_id:  "payroll_monthly_v1"
format_id:  "payroll_monthly_v1::general_journal"
format_id:  "payroll_monthly_v1::quickbooks_csv"
```

The `::` separator is unambiguous — recipe_id and format names use underscores/hyphens.

### Relationship: PRODUCES_FORMAT

A new relationship connects recipe to its output formats:

```
(AccountingRecipe) -[:PRODUCES_FORMAT]-> (OutputFormat)
```

This replaces the implicit coupling where output formats were "found" by matching `format_id = recipe_id` in queries.

### Pipeline spec: `output` becomes `formats[]`

The current single `output` section becomes an array of format definitions. The existing single-format spec remains supported for backward compatibility.

### Processing-time format selection

`get_processing_instructions` gains an optional `format_name` parameter. If omitted, it returns the first (or only) format. If provided, it returns the named format's columns, validation rules, and batch spec.

---

## Domain Types (L1)

No Layer 1 changes required. The existing types already support this:

- `OutputFormat.recipe_id` — links back to recipe (unchanged)
- `OutputColumn.format_id` — will now be the derived `format_id`, not `recipe_id`
- `ValidationRule.format_id` — same
- `BatchFormat.recipe_id` — unchanged (batch semantics are recipe-level)

---

## Schema Definitions (L2)

### New relationship constraint

```python
# In domain/ontology_recipe.py — RECIPE_RELATIONSHIP_CONSTRAINTS
RelationshipConstraint(
    relationship_type=RelationshipType.PRODUCES_FORMAT,
    start_label=NodeLabel.ACCOUNTING_RECIPE,
    end_label=NodeLabel.OUTPUT_FORMAT,
)
```

### New relationship type

```python
# In domain/types.py — RelationshipType enum
PRODUCES_FORMAT = "PRODUCES_FORMAT"
```

**Gate classification:**
- Gate 1: `validate_pipeline_connectivity` will verify PRODUCES_FORMAT edges exist when OutputFormat nodes are present
- Gate 2: No impact — output format is structural, not entry-level

**Canonical count changes:**

| Constant | Before | After | Delta |
|----------|--------|-------|-------|
| `RelationshipType` | 26 | 27 | +1 |
| `RECIPE_RELATIONSHIP_CONSTRAINTS` | 14 | 15 | +1 |
| `merged_relationship_constraints()` | 25 | 26 | +1 |

---

## Pure Functions (L3)

### New function

```python
def build_produces_format_rel(
    recipe_node: Node,
    format_node: Node,
) -> Relationship:
    """Create PRODUCES_FORMAT relationship from recipe to output format."""
```

### Modified function

```python
def compose_pipeline_pattern(
    schema_pattern: GraphPattern,
    recipe_pattern: GraphPattern,
    output_pattern: GraphPattern | List[GraphPattern] | None = None,  # <-- CHANGED: accept list
) -> GraphPattern:
```

Backward compatible — single `GraphPattern` still works.

---

## Persistence Contract (L4)

### Modified: `load_pattern_by_recipe`

Currently finds output nodes via `format_id = recipe_id`. Change to relationship traversal:

```cypher
-- Current (broken for decoupled formats):
MATCH (n) WHERE n.recipe_id = $id OR n.format_id = $id

-- New (follows PRODUCES_FORMAT edges):
MATCH (n) WHERE n.recipe_id = $id
UNION
MATCH (recipe)-[:PRODUCES_FORMAT]->(fmt)
WHERE recipe.recipe_id = $id
MATCH (fmt)-[*0..1]->(child)
RETURN labels(child) AS labels, properties(child) AS properties
```

This naturally loads all formats and their children (OutputColumn, ValidationRule, BatchFormat) for a given recipe.

### No merge key changes

OutputFormat merge key remains `("recipe_id", "name")`. OutputColumn and ValidationRule merge keys remain `("format_id", "name")`. The values change (format_id is now distinct), but the key structure doesn't.

---

## MCP Interface (L5)

### Pipeline spec format

**New format (multiple outputs):**

```json
{
  "recipe_id": "payroll_monthly_v1",
  "schema": { ... },
  "recipe": { ... },
  "formats": [
    {
      "name": "general_journal",
      "target_system": "general",
      "file_format": "csv",
      "columns": [
        {"name": "journal_date", "position": 1, "data_type": "date", "required": true},
        {"name": "account_code", "position": 2, "data_type": "string", "required": true},
        {"name": "account_name", "position": 3, "data_type": "string", "required": false},
        {"name": "debit_amount", "position": 4, "data_type": "decimal", "required": true},
        {"name": "credit_amount", "position": 5, "data_type": "decimal", "required": true},
        {"name": "memo", "position": 6, "data_type": "string", "required": false}
      ],
      "validation_rules": [
        {"name": "balanced_entry", "expression": "SUM(debit_amount) == SUM(credit_amount)", "scope": "batch"}
      ]
    },
    {
      "name": "quickbooks_iif",
      "target_system": "quickbooks",
      "file_format": "iif",
      "version": "1.0",
      "columns": [
        {"name": "!TRNS", "position": 1, "data_type": "string", "required": true, "source_mapping": "record_type"},
        {"name": "DATE", "position": 2, "data_type": "date", "required": true, "source_mapping": "pay_date"},
        {"name": "ACCNT", "position": 3, "data_type": "string", "required": true, "source_mapping": "account.name"},
        {"name": "AMOUNT", "position": 4, "data_type": "decimal", "required": true, "source_mapping": "line.signed_amount"},
        {"name": "MEMO", "position": 5, "data_type": "string", "required": false, "source_mapping": "memo_template"}
      ],
      "validation_rules": [],
      "batch": {
        "grouping_column": "!TRNS",
        "entry_separator": "ENDTRNS",
        "date_column": "DATE"
      }
    }
  ]
}
```

**Backward-compatible format (single output):**

The existing `"output": { ... }` key continues to work. The builder treats it as `"formats": [{ ... }]`.

### Tool changes

**`get_processing_instructions`** — add optional `format_name`:

```python
@mcp.tool()
def get_processing_instructions(recipe_id: str, format_name: str | None = None) -> str:
    """Return processing instructions for a previously loaded recipe.

    If format_name is provided, returns instructions for that specific output
    format. If omitted and the recipe has one format, returns it. If omitted
    and the recipe has multiple formats, lists available format names.
    """
```

**`load_recipe`** — response includes available formats list:

```json
{
  "recipe_id": "payroll_monthly_v1",
  "formats": [
    {"name": "general_journal", "target_system": "general", "file_format": "csv"},
    {"name": "quickbooks_iif", "target_system": "quickbooks", "file_format": "iif"}
  ],
  ...
}
```

**`build_and_save_pipeline`** — no signature change, reads `formats[]` from spec.

### Summarizer changes

`summarize_recipe_load` emits a `formats` array instead of a single `output` section.

`summarize_processing_instructions` accepts a `format_name` parameter and returns the matching format's columns/validation/batch. If no format_name and multiple exist, returns the list of available names.

---

## Data Flow

```
JSON spec (agent provides formats[] array or single output)
    |
    v
builders.py _build_output_nodes()
    |  format_id = "{recipe_id}::{format_name}"  (not recipe_id)
    |  Called once per format in the array
    v
[OutputFormat, OutputColumn, ValidationRule, BatchFormat] nodes per format
    |
    v
builders.py build_pipeline_from_spec()
    |  Creates PRODUCES_FORMAT rel: recipe → each OutputFormat
    v
compose_pipeline_pattern(schema, recipe, [output_1, output_2, ...])
    |
    v
Gate 1 validation (per format: columns, positions, batch refs)
    |
    v
Neo4j: MERGE nodes, MERGE PRODUCES_FORMAT rels
    |
    v
load_recipe → all formats loaded via relationship traversal
    |
    v
get_processing_instructions(recipe_id, format_name="general_journal")
    |  Filters to matching OutputFormat by name
    v
JSON response with format-specific columns/validation/batch
```

---

## Examples

### Happy path: recipe with two output formats

```json
// build_and_save_pipeline input
{
  "recipe_id": "payroll_monthly_v1",
  "schema": { "name": "payroll_export", ... },
  "recipe": { "name": "Monthly Payroll Journal", ... },
  "formats": [
    {"name": "general_journal", "target_system": "general", "file_format": "csv", "columns": [...]},
    {"name": "quickbooks_csv", "target_system": "quickbooks", "file_format": "csv", "columns": [...]}
  ]
}

// load_recipe response
{
  "recipe_id": "payroll_monthly_v1",
  "formats": [
    {"name": "general_journal", "target_system": "general", "file_format": "csv"},
    {"name": "quickbooks_csv", "target_system": "quickbooks", "file_format": "csv"}
  ]
}

// get_processing_instructions("payroll_monthly_v1", "quickbooks_csv")
{
  "recipe_id": "payroll_monthly_v1",
  "measures": [...],
  "rules": [...],
  "output_format": {
    "name": "quickbooks_csv",
    "columns": [...],
    "validation_rules": [...]
  }
}
```

### Happy path: single output (backward compatible)

```json
// Existing format — still works
{
  "recipe_id": "payroll_monthly_v1",
  "schema": { ... },
  "recipe": { ... },
  "output": { "name": "journal_export", "target_system": "quickbooks", ... }
}

// Internally treated as formats: [{ "name": "journal_export", ... }]
```

### Edge case: no format_name with multiple formats

```json
// get_processing_instructions("payroll_monthly_v1")  — no format_name
{
  "recipe_id": "payroll_monthly_v1",
  "available_formats": ["general_journal", "quickbooks_csv"],
  "hint": "This recipe has multiple output formats. Call get_processing_instructions with format_name to select one."
}
```

### Edge case: unknown format_name

```json
// get_processing_instructions("payroll_monthly_v1", "xero_csv")
{
  "error": "Format 'xero_csv' not found for recipe 'payroll_monthly_v1'. Available: general_journal, quickbooks_csv"
}
```

### Edge case: recipe with no output formats

```json
// load_recipe response — no formats section
{
  "recipe_id": "payroll_monthly_v1",
  "schema": { ... },
  "recipe": { ... }
}

// get_processing_instructions — no output_format section
{
  "recipe_id": "payroll_monthly_v1",
  "measures": [...],
  "rules": [...]
}
```

---

## Example Output Format Types

These are not prescriptive — the system stores whatever the user defines. But these illustrate the range:

| Format Name | target_system | file_format | Use Case |
|-------------|---------------|-------------|----------|
| `general_journal` | `general` | `csv` | Human review — date, account, DR/CR, memo |
| `quickbooks_csv` | `quickbooks` | `csv` | QuickBooks journal import |
| `quickbooks_iif` | `quickbooks` | `iif` | QuickBooks IIF import (TRNS/ENDTRNS structure) |
| `xero_csv` | `xero` | `csv` | Xero manual journal import |
| `payment_file` | `bank` | `csv` | ACH/wire payment batch file |
| `ap_voucher` | `erp` | `json` | AP voucher creation for ERP system |
| `invoice_lines` | `billing` | `csv` | Invoice line items for billing system |

The `target_system` + `file_format` + column definitions fully describe the output. No special code per format type — the agent reads the columns/validation/batch spec and generates accordingly.

---

## Invariants

### Graph semantics
- A recipe MAY have zero, one, or many PRODUCES_FORMAT relationships
- Each OutputFormat has exactly one parent recipe (enforced by recipe_id on the node)
- OutputColumn.format_id and ValidationRule.format_id match their parent OutputFormat's derived format_id
- BatchFormat remains keyed by recipe_id (batch grouping is recipe-level, not format-specific)

### Functional constraints
- `compose_pipeline_pattern` remains a pure function
- Backward compatibility: single `output` key treated as `formats: [output]`
- `format_id` derivation is deterministic: `f"{recipe_id}::{format_name}"`
- An agent that never provides `format_name` gets the same behavior as today (single format assumed)

### Layer boundaries
- domain/ must never import from persistence/ or mcp_server/
- Pure functions (builders, summarizers) must not import from persistence/
- Only `tools.py` accesses Neo4j via persistence layer

---

## Integration

### Files modified

| File | Change |
|------|--------|
| `domain/types.py` | Add `PRODUCES_FORMAT` to `RelationshipType` enum |
| `domain/ontology_recipe.py` | Add `PRODUCES_FORMAT` to `RECIPE_RELATIONSHIP_CONSTRAINTS` |
| `domain/logic.py` | Accept `List[GraphPattern]` for output in `compose_pipeline_pattern` |
| `persistence/operations.py` | Update `load_pattern_by_recipe` to traverse PRODUCES_FORMAT |
| `mcp_server/builders.py` | Support `formats[]`, derive `format_id`, build PRODUCES_FORMAT rels |
| `mcp_server/summarizers.py` | Emit `formats[]` in load summary, accept `format_name` filter |
| `mcp_server/tools.py` | Add `format_name` param to `get_processing_instructions` |
| `tests/` (multiple files) | New tests for multi-format scenarios, update canonical counts |

### Files created

None.

### Canonical counts affected

| Constant | Before | After | Delta |
|----------|--------|-------|-------|
| `RelationshipType` | 26 | 27 | +1 |
| `RECIPE_RELATIONSHIP_CONSTRAINTS` | 14 | 15 | +1 |
| `merged_relationship_constraints()` | 25 | 26 | +1 |
| `Total tests` | 347 | ~370 | +~23 |

---

## Test Strategy

### New tests

| Test file | Test class / method | What it verifies |
|-----------|-------------------|-----------------|
| `test_types.py` | `test_relationship_type_count` | RelationshipType count = 27 |
| `test_ontology_recipe.py` | `test_produces_format_constraint` | PRODUCES_FORMAT in constraints |
| `test_logic.py` | `test_compose_with_multiple_outputs` | compose_pipeline_pattern accepts list |
| `test_builders.py` | `test_formats_array_builds_multiple` | formats[] creates multiple OutputFormat subgraphs |
| `test_builders.py` | `test_format_id_derived` | format_id = recipe_id::format_name |
| `test_builders.py` | `test_produces_format_rels_created` | PRODUCES_FORMAT rels connect recipe to each format |
| `test_builders.py` | `test_single_output_backward_compat` | `output: {}` still works, treated as single format |
| `test_summarizers.py` | `test_formats_list_in_load` | load summary includes formats array |
| `test_summarizers.py` | `test_format_selection_by_name` | processing instructions filter by format_name |
| `test_summarizers.py` | `test_multiple_formats_no_selection` | returns available_formats list when ambiguous |
| `test_operations.py` | `test_load_multi_format_recipe` | Integration: multi-format round-trip through Neo4j |

### Existing tests

All existing tests pass unchanged. The `output` key in existing pipeline specs is treated as `formats: [output]` — no behavioral difference for single-format recipes.

### Expected new test count

Current: 347 | Added: ~23 | New total: ~370

---

## Success Criteria

- [ ] `formats: [{...}, {...}]` in pipeline spec creates multiple OutputFormat subgraphs with distinct format_ids
- [ ] `output: {...}` (single format, old syntax) continues to work identically
- [ ] Each OutputFormat has a PRODUCES_FORMAT relationship from its recipe
- [ ] `load_recipe` response lists all available formats by name
- [ ] `get_processing_instructions(recipe_id, format_name)` returns the correct format's columns
- [ ] `get_processing_instructions(recipe_id)` with one format returns it; with multiple, lists options
- [ ] `format_id` on OutputColumn/ValidationRule uses derived `recipe_id::format_name`, not bare `recipe_id`
- [ ] `load_pattern_by_recipe` finds all formats via PRODUCES_FORMAT traversal
- [ ] All existing tests pass (no regressions)
- [ ] Canonical counts updated in CLAUDE.md and count tests

---

## Out of Scope

- **Format template library** — pre-built formats for QuickBooks, Xero, etc. that users can reference by name. Useful but separate feature.
- **Format inheritance** — a "quickbooks_csv" format that extends "general_journal" with additional columns. Adds complexity without clear need yet.
- **Runtime format switching** — changing output format mid-processing. The format is selected at the start of processing via `get_processing_instructions`.
- **Format versioning** — OutputFormat already has an optional `version` field, but version migration logic is out of scope.
- **BatchFormat decoupling** — BatchFormat currently uses `recipe_id`. Whether it should move to `format_id` (batch config per format) is a reasonable future change but not required here.

---

## Open Questions

None. BatchFormat stays recipe-level — it defines the accounting grain (how entries are grouped by date or other dimensions), not the file-level presentation. Different output formats render the same batch structure in their own way.
