# Product Architecture: FP_core as an Accounting Knowledge Platform

> **Status:** Living document
> **Created:** 2026-02-17

---

## 1. The Product Thesis

FP_core is an accounting knowledge platform where an AI model encodes, queries, and executes accounting knowledge through a graph.

The model is not a script follower. It is a reasoning agent that understands accounting and uses the graph to make that understanding specific to *this* user. The model knows double-entry bookkeeping, depreciation methods, revenue recognition principles, and accrual accounting. What it doesn't know — until the graph tells it — is which accounts this user has, what their chart of accounts looks like, how their payroll maps to journal entries, and what format their ERP expects for import.

The recipe pipeline is one pattern the graph supports. But the graph can hold any accounting knowledge: depreciation schedules, vendor payment terms, dimensional hierarchies, allocation rules, tax tables, asset registers, lease amortization schedules. Each of these is just nodes and relationships — knowledge encoded once and queryable forever.

The product moat is knowledge accumulation. Every piece of knowledge encoded makes the model more useful. The first session might handle payroll. By month twelve, the model handles most of the accounting close — because the graph remembers everything the user has taught it.

---

## 2. The Virtuous Cycle

The system operates through a cycle where each pass adds value:

```
    User describes                    Model writes
    their world                       to the graph
         │                                │
         ▼                                ▼
  "We have 50 assets,            Uses MCP tools to build
   here's the depreciation       asset nodes, depreciation
   schedule, straight-line,      rules, account mappings,
   here are the accounts"        validation constraints
         │                                │
         │          ┌─────────┐           │
         └─────────►│  GRAPH  │◄──────────┘
                    │ STORES  │
                    └────┬────┘
                         │
         ┌───────────────┼───────────────┐
         │                               │
         ▼                               ▼
  User requests                   Model reads + reasons
         │                               │
         ▼                               ▼
  "We sold Asset #1234       Loads asset data from graph,
   for $50,000"              computes gain/loss, generates
                             journal entries, validates
  "Run monthly                via Gate 2
   depreciation"
                                         │
  "What's our net                        ▼
   book value?"                   Graph grows
                             (new transactions recorded,
                              new knowledge added)
```

**User describes** — The user talks to the model in natural language. "We have 50 assets, here's the depreciation schedule, we use straight-line, here are the accounts." Or: "Our payroll comes from ADP, here's what the export looks like." Or simply: "Here's our chart of accounts CSV."

**Model writes** — The model uses MCP tools to encode this knowledge as graph patterns: asset nodes, depreciation rules, account mappings, source schemas, validation constraints. The model decides *how* to represent the knowledge; the user just describes it.

**Graph stores** — The knowledge persists across sessions. The user's accounting setup IS the graph. No re-explanation next month.

**User requests** — "We sold Asset #1234 for $50,000." Or: "Run monthly depreciation." Or: "What's our net book value?" The user states what they need; they don't specify the procedure.

**Model reads + reasons** — The model loads relevant knowledge from the graph, applies its accounting expertise, computes the answer, generates journal entries, and validates via Gate 2. The model knows the accounting; the graph supplies the specifics.

**Graph grows** — Each interaction potentially adds knowledge. A new asset. An updated account mapping. A corrected depreciation schedule. The graph becomes more complete with use.

---

## 3. Why the Model Shouldn't Be Boxed In

The model knows accounting. Consider a concrete example: asset disposal.

**What the model knows from its training:**
- Depreciation methods — straight-line, declining balance, units of production, sum-of-years-digits
- When an asset is sold, it needs to compute gain/loss: selling price minus net book value
- The journal entry structure: DR Cash, DR Accumulated Depreciation, CR Asset, CR/DR Gain/Loss on Disposal
- It needs to book partial-period depreciation before the disposal date
- If the asset was fully depreciated, accumulated depreciation equals the asset's cost

**What the model needs from the graph** — the user's specifics:
- Which assets exist, their original costs, useful lives, salvage values, in-service dates
- Which accounts to use: 1510 for Equipment, 1519 for Accumulated Depreciation, 4500 for Gain on Disposal, 7200 for Loss on Disposal
- What output format the user's ERP system expects
- Any company-specific policies (e.g., half-year convention, minimum capitalization threshold)

The model reasons from general accounting knowledge + specific graph data = correct journal entries for this user's situation. No "asset disposal recipe" is needed as a prescribed workflow. The tools give the model capabilities; the graph gives it context; the model supplies the intelligence.

This is why FP_core exposes **tools as capabilities, not workflow steps.** The model decides which tools to use and in what order based on the task at hand. A routine payroll run follows a predictable pattern. An unusual asset disposal requires judgment. The same tools serve both — the model adapts.

---

## 4. The Model's Perspective: What It Gets

### Knowledge It Doesn't Need to Memorize

The model's training data contains generic accounting knowledge — textbook chart of accounts, standard journal entry patterns. But this user's world is specific:

- Their chart of accounts has 500 accounts with custom numbering, not the generic ones in any textbook
- Their mapping rules say gross pay goes to debit 6100, not some example from training data
- Their depreciation schedules have specific useful lives and salvage values for 50 real assets
- Their vendor payment terms, dimensional hierarchies, and allocation methods are unique to their business

All of this is queryable through the graph. The model doesn't carry it in a prompt or reconstruct it each session. It loads what it needs, when it needs it.

### A Persistent Memory Across Sessions

The graph survives between conversations. Knowledge encoded in session 1 is available in session 50. The model doesn't re-learn the user's setup every time — it loads it.

This is what makes the system practical for recurring work. Payroll runs monthly. Depreciation runs monthly. Month-end close runs monthly. The graph remembers how to do each of these. The user says "run payroll" and the model knows exactly what that means for *this user* because the recipe is in the graph.

### Self-Correcting Feedback

The validation gates give the model structured feedback:

- **Gate 1:** "Your template has a problem — MappingRule 'tax_withholding' is missing a CREDITS edge." The model fixes the template before saving.
- **Gate 2:** "Your journal entries don't balance — entry 3 has debits of $5,000 and credits of $4,800." The model fixes the computation before output.

The model can try approaches knowing the gates will catch errors. This is not "guess and check" — it's the same workflow a human accountant follows. Prepare the entries, verify the balance, fix any issues, then post. The gates make model flexibility safe.

### Inspectable Structure

The model can introspect the system itself:

- `ontology://merged` — what's possible: what node types exist, what properties they require, what values are valid
- `constraints://merged` — what's allowed: which relationships can connect which node types
- `load_recipe` / `get_processing_instructions` — what's configured: this user's specific setup, mapping rules, output format

The model can read the ontology to understand what a `Measure` node needs before creating one. It can read the constraints to know that `MAPPED_TO` connects `AccountSlot` to `Account`. The system teaches the model about itself.

---

## 5. The User's Perspective: What They Get

### Natural Language to Correct Results

- "Process this month's payroll" — the model loads the payroll recipe, computes measures from the source data, generates journal entries, validates via Gate 2, writes the output CSV
- "We sold the delivery truck for $15,000" — the model reads the asset data from the graph, looks up the original cost and accumulated depreciation, computes the gain or loss, generates the disposal entries with the right accounts
- "Show me depreciation expense by department for Q4" — the model queries the graph for assets, groups by department dimension, computes three months of depreciation, presents the breakdown

The user states the goal. The model figures out the procedure.

### Their Knowledge, Not Generic Accounting

The graph encodes THIS user's chart of accounts, THIS user's business rules, THIS user's output format. The model's general accounting knowledge plus their specific data equals exactly right answers — not textbook examples, but entries that match their ERP's import format with their account codes and their memo templates.

### Onboarding Through Conversation

The user doesn't build graphs. They describe their world to the model:

- "Here's our chart of accounts CSV" — the model reads the file and uses tools to encode each account as a node in the graph, with the right account types and normal balances
- "We depreciate equipment over 5 years straight-line with no salvage value" — the model writes the depreciation rule to the graph
- "Our payroll comes from ADP, here's what the export looks like" — the model examines the file, builds the source schema, and asks clarifying questions about which columns map to which accounts

The model does the encoding. The user provides the knowledge. No graph query language, no JSON specs, no configuration files. Just conversation.

### Repetitive Work Automated

Set it up once through conversation; run it every period with one sentence.

The graph IS the automation. It remembers how payroll maps to journal entries. It remembers which accounts to use. It remembers what the output file should look like. Next month, "run payroll" is all the user needs to say.

### Growing Value Over Time

- **Month 1:** The model can process payroll
- **Month 3:** The model also handles depreciation, accounts payable, and month-end accruals
- **Month 6:** The model handles intercompany allocations and revenue deferrals
- **Month 12:** The model handles most of the accounting close — payroll, depreciation, AP, AR, accruals, allocations, reclassifications

Each piece of knowledge added multiplies what the model can do. Payroll knowledge plus chart of accounts knowledge plus output format knowledge means the model can process payroll end-to-end. Add depreciation knowledge and it handles that too — using the same chart of accounts and output format already in the graph.

---

## 6. The Technical Architecture That Enables This

### The Two-Zone Architecture

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

**Accounting Zone** (strict): Accounts, transactions, mapping rules — enforced invariants, typed properties, double-entry semantics. FP_core guarantees structural correctness here. This is the journal, the ledger, the trial balance — the parts governed by GAAP, audited by external parties, reported to regulators.

**Knowledge Zone** (flexible): Depreciation schedules, vendor lists, asset registers, employee rosters, product catalogs, lease amortization tables — anything the user's business needs. No schema enforcement. The model writes whatever structure makes sense for the data. This zone varies wildly between organizations and changes frequently. No accounting system should force a schema on it.

**The Boundary** (USES_REFERENCE): Mapping rules, conditions, and recipes can reach into the knowledge zone. This is how "depreciation schedule row" becomes "journal entry." Only three recipe-layer node types may source these edges — the boundary is guarded, not open.

The knowledge zone is the onboarding surface. It's where the user's world gets encoded with zero schema friction. The model can write employee records, asset registers, vendor lists — whatever the user's business needs — without fighting a predefined schema.

### Server-Side State

The model works with handles (recipe_id, format_id), not raw graph data:

- `load_recipe("payroll_monthly_v1")` caches the full graph server-side and returns a lean summary
- `get_processing_instructions("payroll_monthly_v1")` reads from the cache and returns structured instructions
- Source data stays server-side; the model sees aggregated values, not individual employee records
- Privacy by architecture: PII doesn't enter the model's context

This is both a token efficiency pattern and a privacy pattern. A payroll recipe has 33 nodes and 36 relationships — the model doesn't need all of that in its context window. It needs to know: three measures to compute, three mapping rules with resolved account codes, and an output format with column positions. The server distills the graph into exactly what the model needs for the task.

### Tool Tiers: Capabilities, Not Steps

**Tier 1** (coarse, available now): `load_recipe`, `load_format`, `get_processing_instructions`, `build_and_save_pipeline`, `build_output`, `validate_entries` — covers the recipe pipeline use case in 2-3 calls. The model loads a recipe, gets instructions, and processes data. Routine work stays efficient.

**Tier 2** (fine-grained, planned): `build_schema`, `build_recipe`, individual node operations — for incremental knowledge building, the model adding one piece at a time. When the user says "add a new account" or "update the depreciation method for the delivery truck," the model uses fine-grained tools to make a targeted change without rebuilding the entire pipeline.

**Tier 3** (escape hatch, planned): `run_cypher` — for novel queries the model invents. "What accounts have no activity in 6 months?" is not a pre-built tool; it's a Cypher query the model writes on the fly. "Show me all mapping rules that post to expense accounts" — same thing. The model's ability to write graph queries means it's never limited to pre-built capabilities.

The model picks the tier based on the task. Routine payroll processing uses Tier 1. Building a new depreciation graph uses Tier 2. Ad-hoc general ledger analysis uses Tier 3. The tiers are not a progression — they're a toolkit.

### Validation Gates as Safety Nets

**Gate 1** validates templates before save. The model can build any graph pattern — a payroll recipe, a depreciation schedule, a revenue recognition rule. Gate 1 tells it whether the pattern is structurally sound: Does every mapping rule have both debit and credit sides? Does every measure reference a valid column? Are all required properties present? The model gets specific, actionable error messages and can fix issues before persisting.

**Gate 2** validates output before delivery. The model can take any approach to computing journal entries — summing measures, applying conditions, splitting by dimension. Gate 2 tells it whether the entries balance: Do debits equal credits? Are all target accounts active? The model gets structured validation results and can correct errors before the user sees them.

The gates don't prescribe HOW the model should work. They verify WHAT it produced. This is what makes model flexibility safe — any path is fine as long as the output is valid. A prescriptive workflow says "do step 1, then step 2, then step 3." Validation gates say "whatever you did, here's whether the result is correct." The model retains its reasoning freedom; the gates ensure accounting integrity.

---

## 7. The Product Moat: Knowledge Accumulation

Why this gets better over time:

**Each piece of knowledge multiplies capability.** When the graph has the chart of accounts, the model can answer "what type of account is 6100?" When it also has the payroll recipe, the model can process payroll. When it also has the depreciation schedule, the model can run depreciation — using the same chart of accounts already in the graph. Knowledge compounds.

**The graph becomes infrastructure.** The user's chart of accounts, business rules, and output formats encoded in the graph become the foundation everything else builds on. Adding a new recipe is easy when the accounts already exist. Adding a new report is easy when the dimensional hierarchies are already mapped. Switching costs increase naturally — not because of lock-in, but because the graph genuinely holds the user's accounting world.

**Standard patterns emerge.** Payroll recipes, depreciation recipes, AP recipes, month-end accrual recipes — these patterns recur across organizations. Templates can be shared: "Start with the standard payroll recipe, customize it for your chart of accounts." The model writes the customization; the template provides the structure.

**Onboarding IS usage.** The model writing knowledge into the graph IS the setup process. There's no separate configuration workflow, no admin console, no implementation project. The user describes their world through conversation; the model encodes it. By the time they've processed their first payroll, the graph already knows their source format, their account mappings, and their output requirements.

**The graph is also documentation.** A new team member asks the model "how do we handle payroll?" The model reads the payroll recipe from the graph and explains: "Payroll comes from ADP as a CSV. We sum gross pay, net pay, and tax withholding. Gross pay debits Salary Expense (6100) and credits Payroll Payable (2200). Tax withholding debits Payroll Payable (2200) and credits Tax Payable (2300)." The documentation is live, queryable, and always current — because it IS the processing logic.

---

## 8. Design Principles

1. **The model is the author and the consumer.** It writes knowledge into the graph and reads it back to execute tasks. The graph is not a configuration store that a human fills out — it's a knowledge base that the model builds and queries.

2. **The graph is the accounting expert for THIS user.** General accounting lives in the model's weights. Specific accounting — this user's chart of accounts, this user's depreciation schedules, this user's mapping rules — lives in the graph. Neither is complete without the other.

3. **Tools are capabilities, not workflow steps.** The model chooses which tools to use and in what order based on the task. A prescribed step-by-step workflow is appropriate for teaching (and the MCP prompts serve that role), but production use should be flexible. The model is the reasoning engine; the tools are its hands.

4. **Validation gates, not scripts, enforce correctness.** Any path to the answer is acceptable as long as the output is valid. Gate 1 validates templates. Gate 2 validates entries. The model can be creative in how it gets there — the gates ensure the destination is correct.

5. **The knowledge zone is the onboarding surface.** Getting user-specific knowledge into the graph should be frictionless. No schema to learn, no configuration format to master. The model reads a CSV, asks clarifying questions, and encodes the result. The knowledge zone accepts whatever structure the model decides is appropriate.

6. **Progressive accumulation.** Every interaction can add knowledge. The system gets more valuable over time — not because of software updates, but because the graph grows. Month 1 is payroll. Month 12 is the full accounting close.

7. **The user is the authority.** The model proposes, the user approves. Account selection for unusual transactions, threshold decisions, policy interpretations — judgment calls stay with the human. The model handles mechanical correctness (arithmetic, format compliance, structural validation) so the human can focus on professional judgment.
