# Spec: Build Pipeline Workflow

> **Status:** Ready
> **Created:** 2026-02-16
> **Spec type:** Workflow

---

## Purpose

Define the end-to-end workflow an AI agent follows to build and save a recipe pipeline through the FP_core MCP server. This is the primary write path — an agent with CSV data and accounting intent transforms that intent into a validated, persisted knowledge graph. This spec becomes the first eval target: can an agent successfully complete this workflow given source data and accounting requirements?

---

## Preconditions

Before starting this workflow, the agent must have:

1. **Source data context** — either a CSV file to read or a description of the data schema (column names, types, grain)
2. **Accounting intent** — what journal entries should be produced (which accounts, debit/credit sides, measures to aggregate)
3. **MCP connection** — the FP_core MCP server is running and the agent has access to its 4 tools and 2 resources

---

## Workflow Steps

### Step 1: Read the ontology resource

**MCP call:** Read resource `ontology://merged`

**Purpose:** Understand the node types, required/optional properties, and allowed relationships before drafting a spec. The ontology tells the agent what fields are required vs optional for each node type.

**What the agent learns:**
- `SourceSchema` requires `recipe_id`, `name`, `source_system`
- `Column` requires `recipe_id`, `name`, `position`, `data_type`, `role`
- `Measure` requires `recipe_id`, `name`, `operation`; optionally `group_by`, `split_by`, `split_column`, `description`
- `MappingRule` requires `recipe_id`, `rule_name`, `source_measure`
- `AccountSlot` requires `recipe_id`, `slot_id`, `role`, `entry_type`
- `Account` requires `code`, `name`; optionally `account_type`, `normal_balance`, `is_active`
- `OutputFormat` requires `recipe_id`, `name`, `target_system`, `file_format`

**Success:** Agent receives a JSON object with 19 EntitySchema entries.

**Failure modes:**
- MCP server not running: agent gets connection error
- Resource not found: should not happen if server is correctly configured

---

### Step 2: Read the constraints resource (optional)

**MCP call:** Read resource `constraints://merged`

**Purpose:** Understand which relationship types connect which node types. Useful for agents that want to verify their spec will pass connectivity validation.

**What the agent learns:**
- `TRANSFORMS`: AccountingRecipe -> SourceSchema
- `HAS_COLUMN`: SourceSchema -> Column, OutputFormat -> OutputColumn
- `HAS_MEASURE`: SourceSchema -> Measure
- `AGGREGATES`: Measure -> Column
- `HAS_RULE`: AccountingRecipe -> MappingRule
- `DEBITS` / `CREDITS`: MappingRule -> AccountSlot
- `MAPPED_TO`: AccountSlot -> Account
- etc. (25 total constraints)

**Success:** Agent receives a JSON object with 25 relationship constraint entries.

---

### Step 3: Draft the JSON pipeline spec

**No MCP call** — this is agent-side reasoning.

**Purpose:** Assemble a complete pipeline specification JSON from the source data context and accounting intent.

**Required spec structure:**

```json
{
  "recipe_id": "string (unique identifier, e.g. payroll_monthly_v1)",
  "schema": {
    "name": "string",
    "source_system": "string (e.g. csv_import, api_export)",
    "file_pattern": "string (optional, e.g. payroll_*.csv)",
    "row_grain": "string (optional, e.g. employee_pay_period)",
    "columns": [
      {
        "name": "string",
        "position": "integer (1-based)",
        "data_type": "string (string|decimal|integer|timestamp|date)",
        "role": "string (identifier|date|amount|category|description)",
        "required": "boolean (optional, default true)",
        "description": "string (optional)"
      }
    ],
    "measures": [
      {
        "name": "string",
        "operation": "string (sum|count|count_distinct|average)",
        "source_column": "string (must match a column name)",
        "group_by": ["string array (optional, column names)"],
        "split_by": "string (optional)",
        "split_column": "string (optional)",
        "description": "string (optional)"
      }
    ]
  },
  "recipe": {
    "name": "string (human-readable recipe name)",
    "batch_key": "string (optional)",
    "journal_no_format": "string (optional, e.g. PAY-{batch_key}-{seq})",
    "visibility": "string (optional, default private)",
    "rules": [
      {
        "rule_name": "string",
        "source_measure": "string (must match a measure name)",
        "priority": "integer (optional, default 0)",
        "memo_template": "string (optional)",
        "debit": {
          "slot_id": "string",
          "role": "string (e.g. salary_expense)",
          "account_code": "string",
          "account_name": "string",
          "account_type": "string (e.g. expense, liability, asset)",
          "normal_balance": "string (debit|credit)"
        },
        "credit": {
          "slot_id": "string",
          "role": "string (e.g. payroll_payable)",
          "account_code": "string",
          "account_name": "string",
          "account_type": "string",
          "normal_balance": "string"
        }
      }
    ],
    "references": [
      {
        "id": "string",
        "type": "string (extra label for Reference node)",
        "properties": {}
      }
    ]
  },
  "output": {
    "name": "string",
    "target_system": "string (e.g. quickbooks, xero, general)",
    "file_format": "string (e.g. csv, json)",
    "version": "string (optional)",
    "columns": [
      {
        "name": "string",
        "position": "integer (1-based)",
        "data_type": "string",
        "required": "boolean (optional)",
        "source_mapping": "string (optional)"
      }
    ],
    "validation_rules": [
      {
        "name": "string",
        "expression": "string (e.g. SUM(debit) == SUM(credit))",
        "scope": "string (entry|batch)",
        "description": "string (optional)"
      }
    ],
    "batch": {
      "grouping_column": "string (must match an output column name)",
      "entry_separator": "string",
      "date_column": "string (must match an output column name)"
    }
  }
}
```

**Key constraints the agent should follow:**
- `recipe_id` must be unique across all recipes in the Neo4j database
- Each `rule` must have both `debit` and `credit` sides (double-entry)
- `source_measure` in each rule must match a `name` in the `measures` array
- `source_column` in each measure must match a `name` in the `columns` array
- Column `position` values should be sequential and unique within their parent
- Account codes should follow the user's chart of accounts conventions
- The `output` section is optional — omit it if no specific export format is needed

---

### Step 4: Call build_and_save_pipeline

**MCP call:** `build_and_save_pipeline(pipeline_spec=<JSON string>)`

**Purpose:** Build the graph pattern from the spec, run Gate 1 validation, and save to Neo4j if valid.

**What happens internally:**
1. JSON is parsed
2. `build_pipeline_from_spec(spec)` constructs Nodes and Relationships
3. Gate 1 validators run:
   - `validate_recipe(pattern)` — checks recipe has schema, rules have both debit/credit sides, measures reference columns
   - `validate_pipeline_connectivity(pattern)` — checks TRANSFORMS and overall graph structure
   - `validate_output_format(pattern)` — checks output columns, positions, batch format (if output section exists)
   - `validate_node_properties(node, ontology)` — checks each node against its PropertySchema (required fields, types)
4. If valid: save to Neo4j, cache pattern, return success
5. If invalid: return validation errors, do NOT save

**Success response:**

```json
{
  "recipe_id": "payroll_monthly_v1",
  "gate1_validation": {
    "is_valid": true,
    "errors": [],
    "warnings": []
  },
  "saved": true,
  "counts": {
    "nodes": 27,
    "relationships": 36,
    "nodes_created": 27,
    "relationships_created": 36,
    "properties_set": 150
  }
}
```

**Failure response (validation errors):**

```json
{
  "recipe_id": "payroll_monthly_v1",
  "gate1_validation": {
    "is_valid": false,
    "errors": [
      "MappingRule 'payroll_monthly_v1_rule_gross_pay' is missing CREDITS edge(s)"
    ],
    "warnings": []
  },
  "saved": false,
  "counts": null
}
```

---

### Step 5: Interpret Gate 1 results and revise if needed

**No MCP call** — agent-side reasoning.

**If `is_valid: true` with no warnings:** Proceed to Step 6.

**If `is_valid: true` with warnings:** Inform the user of warnings, proceed to Step 6. Common warnings:
- `AccountSlot 'x' has no MAPPED_TO relationship to an Account` — slot exists but no account linked
- `BatchFormat 'x' grouping_column 'y' does not match any OutputColumn name` — batch config references missing column

**If `is_valid: false`:** Fix the spec and retry Step 4. Common errors and fixes:

| Error | Likely cause | Fix |
|-------|-------------|-----|
| `MappingRule 'x' is missing DEBITS/CREDITS edge(s)` | Rule has only one side | Add the missing debit or credit section |
| `Measure 'x' has no AGGREGATES relationship to a Column` | `source_column` doesn't match any column name | Fix the `source_column` to match an existing column's `name` |
| `AccountingRecipe 'x' has no TRANSFORMS relationship` | Schema name mismatch | Ensure recipe's `source_schema` matches the schema's `name` |
| `Node 'x' missing required property 'y'` | Required field omitted | Add the missing property to the spec |
| `Build error: KeyError: 'name'` | Malformed JSON structure | Check spec structure against the format above |
| `Invalid JSON: ...` | Syntax error in JSON string | Fix JSON syntax |

**Retry behavior:** The agent should fix only the specific errors reported, not rewrite the entire spec. Each retry should be targeted.

---

### Step 6: Verify the round-trip

**MCP call:** `load_recipe(recipe_id="<the recipe_id>")`

**Purpose:** Confirm the recipe was saved correctly by loading it back from Neo4j and reviewing the summary.

**What the agent verifies:**
- `graph_structure.total_nodes` matches the `counts.nodes` from Step 4
- Schema section shows the correct columns and file pattern
- Recipe section shows the correct rules with expected measures
- Output section (if present) shows the correct output columns

**Success:** The loaded summary matches the agent's intent. The recipe is ready for use with `get_processing_instructions` and data processing.

---

## Error Scenarios

### Invalid JSON

```
Agent sends: build_and_save_pipeline('{"recipe_id": bad json')
Response: {"error": "Invalid JSON: Expecting value: line 1 column 20 (char 19)"}
```

Agent action: Fix JSON syntax and retry.

### Missing recipe_id

```
Agent sends: build_and_save_pipeline('{"schema": {...}}')
Response: {"error": "Missing required field: recipe_id"}
```

Agent action: Add `recipe_id` to the top level of the spec.

### Missing required field on a node

```
Response: {
  "gate1_validation": {
    "is_valid": false,
    "errors": ["Node 'payroll_monthly_v1_col_employee_id' missing required property 'position'"]
  }
}
```

Agent action: Add the `position` field to the column spec that's missing it.

### Measure references nonexistent column

```
Response: {
  "gate1_validation": {
    "is_valid": false,
    "errors": ["Measure 'payroll_monthly_v1_msr_total_gross_pay' has no AGGREGATES relationship to a Column"]
  }
}
```

Agent action: The `source_column` in the measure spec doesn't match any column `name`. Fix the spelling or add the missing column.

### Neo4j connection failure

```
Response: {"error": "Neo4j error: ServiceUnavailable(...)"}
```

Agent action: Report the connection error to the user. This is an infrastructure issue, not a spec issue.

---

## Observable Behavior

The expected sequence of MCP calls for a successful workflow:

```
1. READ  ontology://merged              → 19 EntitySchema entries
2. READ  constraints://merged           → 25 relationship constraints (optional)
3. CALL  build_and_save_pipeline(spec)  → {saved: true, counts: {...}}
4. CALL  load_recipe(recipe_id)         → {schema: {...}, recipe: {...}, ...}
```

For a workflow with one validation failure and retry:

```
1. READ  ontology://merged              → 19 EntitySchema entries
2. CALL  build_and_save_pipeline(spec)  → {saved: false, errors: [...]}
3. CALL  build_and_save_pipeline(fixed) → {saved: true, counts: {...}}
4. CALL  load_recipe(recipe_id)         → {schema: {...}, recipe: {...}, ...}
```

---

## Invariants

### Workflow invariants
- The agent must not call `get_processing_instructions` before `load_recipe` (or `build_and_save_pipeline` which also caches)
- A recipe that fails Gate 1 validation is never saved to Neo4j
- A recipe that passes Gate 1 validation is always saved and cached
- The `load_recipe` call after a successful save should return a graph with the same node/relationship count

### Data invariants
- Every MappingRule has exactly one DEBITS and one CREDITS relationship
- Every Measure has exactly one AGGREGATES relationship to a Column
- Every AccountingRecipe has exactly one TRANSFORMS relationship to a SourceSchema
- Every AccountSlot should have a MAPPED_TO relationship to an Account (soft warning if missing)

### Agent behavior invariants
- The agent reads the ontology before drafting a spec (prevents guessing at required fields)
- The agent does not retry indefinitely — after 3 failed attempts, it should ask the user for help
- The agent reports validation errors to the user with actionable explanations

---

## Eval Criteria (Future)

When this spec becomes an eval target, the eval should measure:

### Pass/fail criteria
- [ ] Agent produces a valid JSON spec (parseable, has recipe_id)
- [ ] `build_and_save_pipeline` returns `saved: true` (within 3 attempts)
- [ ] `load_recipe` returns a non-error response with matching node counts

### Quality criteria (scored 0.0-1.0)
- **First-attempt success rate:** Did the spec pass Gate 1 on the first try?
- **Ontology consultation:** Did the agent read `ontology://merged` before drafting?
- **Error recovery:** When Gate 1 fails, does the agent fix only the reported errors?
- **Completeness:** Does the spec include an output section when the user needs one?
- **Accuracy:** Do account codes, types, and normal balances match accounting conventions?

### Eval input
- A CSV file with sample data (e.g., `dogfood/sample_payroll_data.csv`)
- A natural language description of the accounting intent (e.g., "Create journal entries for payroll: gross pay to salary expense, tax withholding to tax payable, net pay to cash")

### Eval output
- The sequence of MCP calls made
- The final JSON spec submitted
- The Gate 1 validation result
- The loaded recipe summary

---

## Success Criteria

- [ ] Spec accurately describes all 4 MCP tools involved and their parameters
- [ ] JSON spec format matches what `build_pipeline_from_spec` actually parses
- [ ] All Gate 1 validator behaviors are documented with error messages
- [ ] Error scenarios cover the common failure modes agents encounter
- [ ] Observable behavior section defines the expected MCP call sequence
- [ ] Eval criteria are concrete enough to implement as automated checks

---

## Out of Scope

- **Data processing workflow** — what happens after the pipeline is built (see `process-data` prompt in `mcp_server/prompts.py`)
- **Gate 2 validation** — validating journal entries against double-entry rules (separate workflow)
- **Recipe deletion/update** — modifying or removing an existing recipe
- **Multi-recipe composition** — combining multiple recipes into a single workflow
- **Agent prompt engineering** — how to phrase instructions to the agent (that's the eval's job)

---

## Open Questions

None. The workflow is fully defined by the existing MCP tool implementations.
