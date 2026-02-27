# FP_core Vision & Roadmap

> **Status:** Living document
> **Created:** 2026-02-16
> **Last updated:** 2026-02-26

---

## The Problem

Accounting teams operate under intense process control requirements — month-end closes, reconciliations, journal entry reviews, audit trails, segregation of duties. These controls exist for good reason (SOX, GAAP, internal policy), but the mechanisms enforcing them are overwhelmingly manual: spreadsheets passed between people, copy-paste from source systems, eyeball validation of debit/credit balance, email chains for approval.

The result is a process that is **high-effort, error-prone, and opaque:**

- **Waste** — Staff re-key data that already exists in source systems. Reconciliation is manual comparison of two lists. Reviewers re-derive numbers the preparer already computed.
- **Defects** — Transposition errors, missed accruals, formula breaks in inherited spreadsheets. Errors found in review cost more to fix than errors caught at entry.
- **Waiting** — Entries sit in approval queues. Close calendars are driven by handoff delays, not by computation time.
- **Overprocessing** — Teams apply the same level of scrutiny to a routine $200 office supplies entry as to a $2M revenue recognition adjustment, because the process doesn't distinguish them.

These are not technology problems in the traditional sense. ERP systems exist. Automation tools exist. The gap is that **current automation replaces the human entirely or not at all.** There is no middle ground where the system handles what it can prove is correct and surfaces what needs professional judgment.

---

## The Vision: Human-Machine Collaboration for Accounting

FP_core is an accounting knowledge graph that enables a **collaborative operating model** between accounting professionals and AI agents. The system encodes accounting knowledge — chart of accounts, transaction rules, validation constraints, processing recipes — as a graph that both humans and machines can read, reason about, and act on.

The design principle is **augmentation, not replacement:**

| Manual Process | FP_core Augmented Process |
|---------------|--------------------------|
| Accountant reads source data and decides which accounts to debit/credit | Recipe graph declares the mapping; agent executes it; accountant reviews exceptions |
| Reviewer re-derives journal entry math to verify balance | Gate 2 validates debit = credit automatically; reviewer focuses on account selection and business logic |
| Close checklist tracked in spreadsheet with manual status updates | Recipe graph declares all processing steps; execution produces provenance trail |
| New hire learns the process by reading a binder and shadowing | Recipe graph is the documentation — it declares what to do, the skill teaches why |

The human stays in the loop for **judgment calls** — account selection for unusual transactions, threshold decisions, policy interpretation. The machine handles **mechanical correctness** — arithmetic balance, schema conformance, format compliance, audit trail generation.

---

## Two-Zone Architecture

The graph has two fundamentally different zones, and the boundary between them is the key architectural decision:

```
┌─────────────────────────────────────┐     ┌─────────────────────────────────────┐
│         ACCOUNTING ZONE             │     │         KNOWLEDGE ZONE              │
│                                     │     │                                     │
│  Strict. Validated. Typed.          │     │  Flexible. User-defined. Opaque.    │
│                                     │     │                                     │
│  - Account must have account_type   │     │  - Employee has... whatever the     │
│  - Transaction must balance         │     │    user puts on it                  │
│  - MappingRule must have DR + CR    │     │  - TimeclockEntry, Product, Role,   │
│  - Every edge is constrained        │     │    LeaseSchedule... anything        │
│  - FP_core enforces all of this     │     │  - No schema enforcement            │
│                                     │     │  - FP_core doesn't know or care     │
└────────────────┬────────────────────┘     └────────────────┬────────────────────┘
                 │                                           │
                 │         USES_REFERENCE                    │
                 │  (the only edge that crosses)             │
                 └──────────────────►────────────────────────┘
```

### Why Two Zones

**The accounting zone** is where double-entry semantics, balance validation, and audit constraints live. FP_core enforces invariants here: transactions balance, mapping rules have both debit and credit sides, accounts carry correct normal balance directions. This is the domain the system understands deeply.

**The knowledge zone** is where the user's business context lives — employee rosters for payroll allocation, product catalogs for revenue categorization, lease schedules for accrual calculations, vendor lists for AP processing. These structures have meaning to the user's business but are not accounting concepts. FP_core has no business dictating their schema.

**The boundary** (`USES_REFERENCE`) is guarded: only three recipe-layer node types (`MappingRule`, `Condition`, `AccountingRecipe`) may reach into the knowledge zone. Core accounting nodes stay inside the accounting zone. The system validates the source side of every boundary crossing but treats the target as opaque.

### Why This Matters for Accounting Teams

This architecture maps directly to how accounting work actually divides:

- **Accounting zone = the journal, the ledger, the trial balance.** The parts governed by GAAP, audited by external parties, reported to regulators. These must be structurally correct.
- **Knowledge zone = the supporting detail.** The employee list, the allocation schedule, the rate table. These vary wildly between organizations and change frequently. No accounting system should force a schema on them.
- **The boundary = the mapping rules.** The professional judgment that says "this payroll data becomes these journal entries." This is where the accountant's expertise lives, and it's exactly where human-machine collaboration adds the most value.

---

## Lean Six Sigma Alignment

FP_core's architecture maps to Lean Six Sigma concepts not as an afterthought, but as a design consequence. The knowledge graph structure naturally supports waste elimination and variation reduction.

### DMAIC Through the Lens of the Knowledge Graph

| DMAIC Phase | FP_core Mechanism | What It Enables |
|-------------|-------------------|-----------------|
| **Define** | Recipe graph declares the process (schema, measures, mapping rules, output format) | The process definition is machine-readable, version-controlled, and inspectable — not buried in a spreadsheet or someone's head |
| **Measure** | Gate 1 (template validation) and Gate 2 (transaction validation) produce structured results | Every validation produces a `ValidationResult` with typed errors and warnings — these are process metrics, not just pass/fail |
| **Analyze** | Two-zone architecture separates what the system controls (accounting zone) from what varies (knowledge zone) | Root cause analysis can distinguish between recipe defects (accounting zone) and data quality issues (knowledge zone) |
| **Improve** | Recipe versioning (recipe_id) and the MCP tool interface | Process changes are graph mutations, not code changes — an accountant can modify a mapping rule without touching Python |
| **Control** | Hard-block validators (Gate 1 + Gate 2) enforce invariants; soft-warning validators flag risks without blocking | Control limits are encoded in the graph: hard blocks are specification limits, soft warnings are control limits |

### Eight Wastes Applied to the Accounting Close

| Waste | Current State | FP_core Target State |
|-------|---------------|----------------------|
| **Defects** | Unbalanced entries caught in review, requiring rework | Gate 2 catches balance violations before output; reviewer sees only structurally valid entries |
| **Overproduction** | Teams prepare entries "just in case," duplicate work across preparers | Recipe graph declares exactly which entries to produce from which source data |
| **Waiting** | Entries queue for review; reviewers wait for supporting detail | Provenance trail (CREATED_FROM edges) links every entry to its source — reviewer has context immediately |
| **Non-utilized talent** | Senior accountants spend time checking arithmetic instead of exercising judgment | Machine handles mechanical validation; professionals focus on account selection, threshold decisions, policy interpretation |
| **Transportation** | Data copied between systems — payroll export to Excel to journal entry template to ERP import file | Recipe graph reads source data and produces output format directly; no intermediate manual steps |
| **Inventory** | Accumulated unposted entries, backlog of unreconciled items | Pipeline processes data through to validated output in one pass; backlog is a queue management problem, not a computation problem |
| **Motion** | Staff navigate between multiple systems, cross-reference screens, manually look up account codes | Knowledge graph holds all reference data; agent resolves account codes from mapping rules automatically |
| **Overprocessing** | Every entry gets the same review depth regardless of risk or materiality | Soft-warning validators flag high-risk items (clearing account balance, temporal ordering) — review effort follows risk |

### Variation Reduction

The accounting close is a repeated process — it runs monthly (or more frequently). Variation in cycle time, error rate, and rework volume directly impacts team capacity and reporting deadlines.

FP_core reduces variation through **standardized recipes:**

- **Same source data structure** (SourceSchema) every period — column names, types, and semantic roles are declared, not discovered each time
- **Same mapping logic** (MappingRule + AccountSlot) — the debit/credit decision is encoded once and executed consistently
- **Same validation gates** — identical checks every period, producing comparable metrics
- **Same output format** (OutputFormat + OutputColumn) — downstream consumers get identical structure

The recipe is the **standard work instruction**. When it runs through the MCP server, the execution is reproducible. When it needs to change (new account code, new allocation method), the change is a graph mutation with clear before/after state — not an undocumented spreadsheet edit.

---

## Feature List

### Delivered (Layers 1-5)

| Feature | Layer | What It Does |
|---------|-------|--------------|
| Typed accounting domain model | L1 | 7 core accounting types + 12 recipe/pipeline types as frozen dataclasses |
| Two-zone graph architecture | L1-L2 | Accounting zone (strict) and knowledge zone (opaque) with guarded USES_REFERENCE boundary |
| Double-entry validation | L2 | Gate 2 hard block: debits must equal credits on every transaction |
| Recipe pipeline model | L1-L3 | Declarative graph: SourceSchema -> Measures -> MappingRules -> AccountSlots -> Accounts -> OutputFormat |
| Gate 1 template validation | L2-L3 | 10 validators (7 hard blocks, 3 soft warnings) verify recipe structure before persistence |
| Gate 2 entry validation | L2, L5 | Validates generated journal entries against double-entry rules |
| Neo4j persistence | L4 | Save, load, delete, verify graph patterns with MERGE-based idempotent writes |
| MCP server (Tier 1 tools) | L5 | 6 tools: load_recipe, load_format, get_processing_instructions, build_and_save_pipeline, build_output, validate_entries |
| Server-side state | L5 | Recipe graph cached in server memory; agent works with handles, not raw graph data |
| MCP prompts | L5 | Workflow templates: build-pipeline, process-data, gate2-checklist |
| MCP resources | L5 | Ontology and constraint schemas available for agent introspection |
| Measure aggregation wiring | L5 | Per-measure `group_by`, `split_by`, and `split_column` properties wired through builder and summarizer; measures declare their own aggregation level |
| Condition wiring (WHEN clauses) | L3, L5 | Mapping rules that fire only when conditions are met; `recipe.conditions[]` + `rule.when` in spec; WHEN relationships in graph; conditions emitted in processing instructions |
| Account metadata in processing instructions | L5 | `get_processing_instructions` includes `account_type` and `normal_balance` on every debit/credit account entry; agents can infer direction without out-of-band knowledge (BUG-002 fix) |

### Planned — Near Term

| Feature | Layer | What It Enables | Lean Alignment | Product Analysis Ref |
|---------|-------|-----------------|----------------|---------------------|
| BUG-001 fix (plural/singular key normalization) | L5 | Builder accepts both `"debit"`/`"debits"` in JSON specs | Defect prevention — eliminate a known error source | — |
| Compound conditions on rules (BUG-003) | L1-L5 | `rule.when` accepts array of condition_ids (implicit AND); rules can filter on multiple dimensions simultaneously | Defect prevention — recipes are self-contained, no reliance on agent to remember processing-time exclusions | Friction Point 2 |
| `list_recipes` tool | L5 | Discover all recipe IDs with name and description; agents and users can browse without `run_cypher` | Reduces waiting — table-stakes discoverability | Friction Point 1 |
| Programmatic tool calling (detail levels + filtering) | L5 | `detail` and `filter` params on tool responses; agents in code execution environments see only what they need | Reduces overprocessing — 80%+ token reduction for programmatic callers | Spec: `programmatic_tool_calling.md` |
| Merged relationship constraint validation | L2 | `validate_graph_pattern()` works with mixed core + recipe patterns | Defect prevention — catch invalid relationships at template time | — |
| Patch operations (`add_rule`, `update_rule`, `remove_rule`) | L5 | Surgical edits to recipes without full rebuild; add one rule to a 6-rule recipe without reconstructing the entire spec | Reduces motion — eliminates error-prone full-spec reconstruction | Friction Point 3 |

### Planned — Medium Term

| Feature | Layer | What It Enables | Lean Alignment | Product Analysis Ref |
|---------|-------|-----------------|----------------|---------------------|
| Layer 5 execution engine | L5 | Automated: measure computation, rule filtering, output formatting, Gate 2 enforcement | Eliminates transportation waste — source data to validated output in one automated pass | — |
| `infer_schema` from CSV | L5 | Auto-detect column names, data types, and roles from CSV headers; return draft schema for user confirmation | Reduces motion — eliminates manual specification of 48+ fields for a 12-column file | Friction Point 4 |
| `preview_pipeline` dry-run | L5 | Run recipe logic against sample data WITHOUT saving; return would-be journal entries for review | Defect prevention — builds confidence before committing; catches data-recipe mismatches early | Friction Point 7 |
| Recipe templates + `clone_recipe` | L5 | Fork existing recipes as starting points; payment processor recipes share 80% structure | Standard work — eliminates cold-start problem for common patterns | Friction Point 5 |
| `generate_output` end-to-end formatting | L5 | Apply output format rules (sign convention, suppress clearing, column layout) and return import-ready CSV | Eliminates transportation — closes the gap between "entries generated" and "file ready for import" | Friction Point 9 |
| Privacy-preserving data handling | L5 | PII tokenization for row-level agent access; server-side aggregation so source data stays out of model context by default; de-tokenization on output | Control mechanism — regulatory compliance (SOX, GDPR) by construction | — |
| Tier 3 MCP tool (run_cypher) | L5 | Ad-hoc read-only Cypher queries for exploration and debugging | Reduces waiting — accountants and auditors can query the graph directly | — |
| Recipe versioning and comparison | L4-L5 | Track changes to recipes over time; diff two versions | Supports DMAIC Control phase — changes are visible, auditable, and reversible | Friction Point 8 |

### Planned — Longer Term

| Feature | Layer | What It Enables | Lean Alignment | Product Analysis Ref |
|---------|-------|-----------------|----------------|---------------------|
| Process metrics dashboard / confidence dashboard | L5+ | Aggregate Gate 1/Gate 2 validation results over time — error rates, warning trends, cycle times; per-run summary showing balance status, orphan rows, clearing account net | DMAIC Measure/Analyze — quantitative SPC for the accounting close | Wow Feature 3 |
| Anomaly detection | L3-L5 | Flag entries that deviate significantly from historical patterns (amount, account, timing); "Stripe fees are 4.2% vs usual 2.9%" | Variation reduction — statistical control limits on journal entry characteristics | Wow Feature 4 |
| Measure-level conditions | L1-L5 | Measures have optional `where` clauses so aggregations are independently correct without relying on rule-level filtering | Defect prevention — measures are self-describing; querying a measure directly gives the right number | Friction Point 6 |
| Chart of accounts pre-validation | L5 | `validate_against_coa(recipe_id, coa_json)` checks account codes/names against actual QuickBooks chart before generating output | Defect prevention — catches mismatches before they become import failures | Friction Point 10 |
| Pre-built recipe library | L5+ | Tested recipes for top payment processors (Stripe, Square, PayPal, Shopify, Amazon), payroll providers (ADP, Gusto), and common accrual patterns | Standard work — eliminates cold-start; every new user starts with a working recipe | Wow Feature 5 |
| Multi-entity consolidation | L3-L5 | Process data across entities with intercompany elimination rules | Reduces transportation — consolidation is a graph traversal, not a spreadsheet assembly | — |
| Automated suggestions | L3-L5 | Recommend account mappings, flag missing accruals, suggest reconciliation matches | Augments professional judgment — system surfaces likely answers, human confirms or overrides | — |

---

## Future Eval Targets

Each planned feature should have an eval that validates both correctness and agent usability. These evals measure whether an AI agent, given the MCP tools and the FP_core skill, can complete the workflow end-to-end.

### Eval 1: Build and Validate a Recipe Pipeline

**What the agent does:** Given a natural language description of a data source and desired journal entries (including at least one conditional rule), build a complete recipe pipeline spec, save it via `build_and_save_pipeline`, and verify Gate 1 passes.

**Measures:**
- Gate 1 validation passes (zero errors)
- All expected nodes and relationships present
- Conditional rule: `recipe.conditions[]` defined, WHEN relationship wired, condition properties correct
- Round-trip: `get_processing_instructions` returns correct measures, mappings, and `conditions` array on conditional rules

**Lean connection:** Can the system produce a defect-free process template from a verbal description?

### Eval 2: Process Data Through a Recipe

**What the agent does:** Given a loaded recipe and sample source data (CSV), compute measures, apply mapping rules, generate journal entries, and validate via Gate 2.

**Measures:**
- All journal entries balance (debits = credits)
- Account codes match the recipe's mapping rules
- Output format matches the recipe's OutputFormat spec
- Agent handles condition logic (WHEN clauses) correctly when present

**Lean connection:** Can the system execute standard work with zero defects?

### Eval 3: Two-Zone Boundary Integrity

**What the agent does:** Build a recipe that uses reference data (knowledge zone). Verify that USES_REFERENCE edges are valid, that only allowed node types source them, and that the system does not attempt to validate reference data internals.

**Measures:**
- `validate_uses_reference` passes for valid boundary crossings
- System correctly rejects boundary crossings from unauthorized node types
- Reference data with arbitrary properties is accepted (no schema enforcement on knowledge zone)

**Lean connection:** Does the control mechanism (accounting zone validation) stay within its scope?

### Eval 4: Error Recovery and Rework Reduction

**What the agent does:** Submit a deliberately flawed recipe (unbalanced mapping, missing schema link, invalid relationship). Verify that Gate 1 produces actionable error messages. Fix the errors based on the messages. Resubmit.

**Measures:**
- First submission fails with clear, specific error messages
- Agent can fix errors without human intervention
- Second submission passes Gate 1
- Total round-trips to success (lower is better — measures rework cost)

**Lean connection:** How much rework does a defect cost? Can error messages drive first-time-right corrections?

### Eval 5: Recipe Consistency Across Periods

**What the agent does:** Process the same recipe with two different periods of source data. Compare outputs for structural consistency (same accounts, same output columns, same validation checks).

**Measures:**
- Output structure is identical across periods (column names, account codes, format)
- Only data values differ
- Gate 2 results are comparable (same validators fire, same pass/fail pattern)

**Lean connection:** Does the system reduce variation in the repeated close process?

### Eval 6: Measure Aggregation Semantics

**What the agent does:** Build a recipe with multiple measures using different `group_by` columns. Process source data and verify that each measure aggregates at its declared level.

**Measures:**
- `total_net` grouped by `created_date` produces per-date totals
- `total_gross` grouped by `deposit_date` produces per-deposit totals
- Measures without `group_by` aggregate across all rows

**Lean connection:** Can the system support per-metric granularity without overprocessing?

---

## Design Philosophy

### Guide, Don't Block

FP_core distinguishes between hard blocks (structural impossibility — an unbalanced transaction cannot be correct) and soft warnings (professional judgment — a clearing account with a residual balance is unusual but may be intentional). The system makes the right thing easy and the wrong thing visible, but does not substitute its judgment for the professional's.

This maps to the Lean concept of **poka-yoke** (mistake-proofing): hard blocks are contact-method poka-yoke (physically prevent the error), soft warnings are attention-method poka-yoke (signal that something unusual happened).

### Recipes Are Standard Work

A recipe graph is a machine-readable standard work instruction. It declares:
- **What** data to read (SourceSchema, Column)
- **How** to aggregate it (Measure, AggregationOp)
- **Where** to post it (MappingRule, AccountSlot, Account)
- **What** the output looks like (OutputFormat, OutputColumn)
- **What** must be true (ValidationRule, Gate 1 + Gate 2 validators)

When an accountant changes a mapping rule, they are performing **kaizen** — a documented, incremental improvement to the standard work instruction. The change is a graph mutation with clear provenance, not an undocumented edit to a shared spreadsheet.

### The Knowledge Graph Is the Gemba

In Lean, **gemba** is "the real place" — where the work actually happens. For FP_core, the gemba is the knowledge graph. The recipe, the reference data, the validation results, and the generated entries all live in the same graph. There is no gap between "the documentation" and "what the system does" — they are the same artifact.

When something goes wrong, you go to the graph. The provenance trail (CREATED_FROM edges, POSTS_TO edges) traces from output back to source. The recipe structure shows why the system made the mapping decisions it did. The validation results show what was checked and what passed.

---

## Success Metrics

| Metric | What It Measures | Target |
|--------|-----------------|--------|
| Gate 1 first-pass yield | % of recipe submissions that pass validation on first attempt | Increasing over time (agent learning) |
| Gate 2 defect rate | % of generated journal entries with balance violations | 0% (hard invariant) |
| Recipe reuse rate | % of periods that use an existing recipe vs. building new | >90% for recurring processes |
| Time to validated output | Wall-clock time from source data availability to Gate 2 pass | Decreasing over time |
| Human intervention rate | % of entries requiring manual correction after automated processing | Decreasing over time |
| Rework loops | Average Gate 1 submissions before pass (per recipe build) | Approaching 1.0 |
| Soft warning acknowledgment rate | % of soft warnings reviewed by a human | 100% (warnings exist to be seen) |

---

## Cross-Reference: Product Analysis Friction Points

Mapping from [`docs/fp_core_product_analysis.md`](fp_core_product_analysis.md) friction points and "wow" features to roadmap items. Added 2026-02-26.

| Product Analysis Item | Roadmap Placement | Status | Notes |
|----------------------|-------------------|--------|-------|
| Friction 1: `list_recipes` | Near Term | Planned | Highest-impact, lowest-effort discoverability fix |
| Friction 2: Compound conditions | Near Term (BUG-003) | Planned | `when` as array with implicit AND; see `docs/bug_log.md` |
| Friction 3: Patch operations | Near Term | Planned | `add_rule`, `update_rule`, `remove_rule` |
| Friction 4: `infer_schema` from CSV | Medium Term | Planned | Auto-detect columns, types, roles from headers |
| Friction 5: Recipe templates + cloning | Medium Term | Planned | `clone_recipe` + template library |
| Friction 6: Measure-level conditions | Longer Term | Planned | Optional `where` clauses on measures |
| Friction 7: `preview_pipeline` dry-run | Medium Term | Planned | Run recipe against data without saving |
| Friction 8: Version history + diff | Medium Term | Planned | Already in roadmap as "Recipe versioning and comparison" |
| Friction 9: `generate_output` formatting | Medium Term | Planned | End-to-end formatted CSV; closes recipe→import gap |
| Friction 10: Chart of accounts pre-validation | Longer Term | Planned | Validate against actual QBO chart before output |
| Wow 3: Confidence dashboard | Longer Term | Planned | Merged with "Process metrics dashboard" |
| Wow 4: Anomaly detection | Longer Term | Planned | Already in roadmap |
| Wow 5: Recipe marketplace | Longer Term | Planned | Merged with "Pre-built recipe library" |
| BUG-002: Account metadata in instructions | Delivered | **Done** | `account_type` + `normal_balance` in processing instructions |
| Programmatic tool calling | Near Term | Spec written | `specs/features/programmatic_tool_calling.md` |
