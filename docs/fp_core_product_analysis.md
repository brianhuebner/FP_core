# fp_core Product Analysis: From MVP to "Wow"

## What fp_core Is Today

fp_core is a **knowledge-graph-powered accounting recipe engine**. It stores declarative pipeline definitions in Neo4j — schemas, measures, mapping rules, account slots, conditions — and exposes them through an MCP toolset so an AI agent (Claude) can load a recipe, process source data, generate balanced journal entries, validate them, and produce output files for import into QuickBooks (via SaasAnt) or other accounting systems.

**The core value proposition:** Take a messy CSV export from a payment processor (Stripe, Square, PayPal, Shopify, etc.), apply a pre-built recipe, and produce clean, validated, import-ready journal entries — with an AI that understands double-entry accounting acting as the "staff accountant."

---

## Use Cases Beyond Stripe Payout Reconciliation

### 1. Payment Processor Reconciliation (Immediate Expansion)
The Stripe recipe is the template. The same pattern applies to:
- **Square** — daily deposits with fees, refunds, disputes, tips
- **PayPal** — settlements with currency conversion, holds, buyer protection claims
- **Shopify Payments** — multi-gateway settlements (Shopify Payments + PayPal + Klarna + Afterpay), each needing clearing accounts
- **Amazon Seller** — complex settlements with referral fees, FBA fees, reimbursements, advertising charges
- **Braintree / Adyen / Authorize.net** — enterprise payment processor reconciliation

Each processor has its own CSV export format, fee categories, and edge cases — but the underlying accounting pattern (gross → clearing → bank, with fees expensed and disputes handled) is remarkably consistent.

### 2. Payroll Journal Entries
One of the biggest pain points in small business accounting. Third-party payroll providers (ADP, Gusto, Paychex) calculate and remit, but don't write journal entries to QuickBooks. Bookkeepers manually create multi-line entries every pay period:
- Debit: Gross Wages (expense)
- Debit: Employer Taxes — FICA, FUTA, SUTA (expense)
- Credit: Employee withholdings — FIT, SIT, FICA (liability)
- Credit: Benefits deductions — 401k, health insurance (liability)
- Credit: Net Pay / Checking (asset)

A recipe could map a payroll summary CSV (from any provider) into balanced journal entries, handling the 8-12 line items that make payroll entries notoriously error-prone.

### 3. Revenue Recognition / Subscription Accruals
SaaS companies collecting annual payments need to recognize revenue monthly. A recipe could:
- Read a billing export (Stripe Billing, Chargebee, Recurly)
- Compute deferred revenue schedules
- Generate monthly recognition entries (Debit: Deferred Revenue → Credit: Revenue)

### 4. Multi-Entity / Multi-Location Consolidation
Businesses with multiple locations (like the JACD/JACT pattern we saw) need entries split by location, class, or department. Recipes with `group_by` and conditional rules handle this well. Expand to:
- Franchise operations
- Multi-store retail
- Property management (per-property income/expense allocation)

### 5. Credit Card Expense Reconciliation
Corporate credit card statements → journal entries that categorize expenses by GL account, department, and project code. Think: an Amex CSV with 200 transactions that need to be coded and posted.

### 6. Bank Feed Categorization
When bank feeds don't auto-categorize well, a recipe could take a bank transaction export and apply rules to generate properly coded entries — especially useful for businesses with complex chart of accounts.

### 7. Intercompany Transactions
Parent/subsidiary transactions that need mirrored entries in both entities. A recipe could generate the paired journal entries from a single intercompany billing export.

### 8. Sales Tax Reconciliation
Match collected sales tax (from Shopify/Square/Stripe) against what's owed per jurisdiction, generating accrual or payment entries.

---

## What's Missing / What Makes It Hard Today

### Friction Point 1: "I Don't Know My Recipe ID"
**Problem:** There's no `list_recipes` tool. Users can't discover what's in the graph without `run_cypher`. If you don't know the exact ID, you're stuck.

**Fix:** Add a `list_recipes()` tool that returns all recipe IDs with name, description, and last-modified date. This is table-stakes for discoverability.

### Friction Point 2: No Compound Conditions on Rules
**Problem:** Each rule supports only a single `when` condition. We hit this today — the A/R clearing rules need to filter on BOTH LocCode AND exclude dispute rows, but can only wire one condition. The dispute exclusion has to be enforced at processing time by the AI, which is fragile.

**Fix:** Support `when_all: [condition_id_1, condition_id_2]` (AND logic) and `when_any: [...]` (OR logic) on rules. This makes recipes self-contained — no reliance on the AI to remember processing-time exclusions.

### Friction Point 3: No Patch/Update — Only Full Rebuild
**Problem:** To add one rule to a 6-rule recipe, you must reconstruct the *entire* pipeline spec and re-save. This is error-prone and tedious. One wrong field in the reconstruction and you've silently changed something.

**Fix:** Add `add_rule(recipe_id, rule_spec)`, `update_rule(recipe_id, rule_name, changes)`, `remove_rule(recipe_id, rule_name)`. Surgical edits instead of full rebuilds.

### Friction Point 4: No Schema Inference from CSV
**Problem:** Building a new recipe requires manually specifying every column with name, position, data_type, and role. For a 12-column Stripe export, that's 48 fields to define by hand.

**Fix:** Add `infer_schema(csv_path)` — read the CSV headers, detect data types, guess roles (amount columns, date columns, identifiers), and return a draft schema. The user confirms/tweaks; the AI doesn't have to type it all out.

### Friction Point 5: No Recipe Templates / Cloning
**Problem:** Payment processor recipes share 80% of their structure (clearing account pattern, fee handling, dispute handling). Starting from scratch each time wastes effort.

**Fix:** Add `clone_recipe(source_id, new_id)` and/or maintain a template library. "Start from the Stripe template, swap account codes and column names for Square."

### Friction Point 6: Measures Don't Have Conditions
**Problem:** Conditions live on rules, but measures (the aggregations) don't have their own filter criteria. The `dispute_gross` measure sums ALL `gross` values — it relies on the rule's condition to filter to dispute rows only. If someone queries the measure independently, they get the wrong number.

**Fix:** Allow measures to have optional `where` clauses: `{"name": "dispute_gross", "operation": "sum", "column": "gross", "where": "is_dispute"}`. This makes measures self-describing and independently correct.

### Friction Point 7: No Dry-Run / Preview Mode
**Problem:** You can't test a recipe against sample data before committing it to the graph. You build, save, load, then hope it works when you process real data.

**Fix:** Add `preview_pipeline(pipeline_spec, csv_path)` — runs the recipe logic against actual data WITHOUT saving, returns the would-be journal entries. This is the "confidence builder" that turns uncertainty into trust.

### Friction Point 8: No Version History / Diff
**Problem:** We saved v2 and v3 side by side, but there's no way to see what changed between them. If someone overwrites a recipe, the old version is gone.

**Fix:** Version tracking in the graph. `recipe_history(recipe_id)` shows versions with timestamps. `diff_recipes(id_1, id_2)` shows what changed.

### Friction Point 9: Output Format Is Disconnected
**Problem:** Output formats (SaasAnt column layouts, field rules like `suppress_clearing` or `amount_sign_convention`) exist as separate objects. The connection between "recipe produces entries" and "entries get formatted for QuickBooks import" has a gap where the AI has to manually apply formatting rules.

**Fix:** Tighter integration — `generate_output(recipe_id, format_id, entries_json)` that applies all formatting rules and returns the ready-to-import CSV. The AI shouldn't have to remember to apply `suppress_clearing` manually.

### Friction Point 10: No Feedback Loop from QuickBooks
**Problem:** After import, there's no way to know if entries posted successfully. The pipeline ends at "CSV generated." Any QBO import errors (account name mismatch, duplicate journal numbers) are discovered manually.

**Fix (aspirational):** A `validate_against_coa(recipe_id, qbo_chart_of_accounts)` tool that checks account codes/names against the actual QuickBooks chart of accounts *before* generating output. Catches mismatches before they become import failures.

---

## The "Wow" Features — What Makes Users Instantly Productive and Confident

### 🌟 1. "Upload CSV, Get Journal Entries" (Zero-Config First Run)
The ultimate onboarding experience:
1. User uploads a Stripe/Square/PayPal CSV
2. System auto-detects the payment processor from column headers
3. Matches to a pre-built recipe (or the closest template)
4. Shows a preview: "Here's what I'd produce — 5 journal entries, all balanced"
5. User reviews, adjusts account codes to match their chart of accounts, approves

**Why it's wow:** No recipe-building required for common processors. Works in 60 seconds.

### 🌟 2. Interactive Recipe Builder (Guided Wizard)
Instead of writing raw JSON specs, a conversational flow:
- "What processor is this from?" → auto-fills schema
- "What's your bank account for deposits?" → fills clearing rule
- "Do you track by location/class/department?" → adds group_by
- "Show me the entries this would produce from your sample data" → preview

**Why it's wow:** Non-technical bookkeepers can build recipes without understanding JSON or graph databases.

### 🌟 3. Confidence Dashboard
After processing, show:
- ✅ All entries balance (Gate 2 passed)
- ✅ All account codes exist in your chart of accounts
- ✅ Clearing account nets to zero
- ⚠️ 3 rows didn't match any condition (orphan rows)
- 📊 Summary: $45,230 gross | $1,290 fees | $43,940 net deposit

**Why it's wow:** Accountants need to *trust* the output. A clear validation summary replaces the anxiety of "did I miss something?"

### 🌟 4. Anomaly Detection
Compare this period's entries to historical patterns:
- "Stripe fees are 4.2% this month vs. your usual 2.9% — investigate?"
- "Dispute volume is 3x higher than average"
- "This payout has no transactions for location JACT — first time in 6 months"

**Why it's wow:** Catches problems the human might miss. Turns the tool from "automation" into "intelligent oversight."

### 🌟 5. Recipe Marketplace / Community Library
Pre-built, tested recipes for:
- Stripe (charges, payouts, disputes, subscriptions)
- Square (transactions, deposits, tips)
- PayPal (settlements, disputes, currency conversion)
- Shopify (multi-gateway)
- ADP/Gusto/Paychex payroll
- Common accrual patterns

Users browse, fork, customize. Like GitHub for accounting recipes.

**Why it's wow:** Eliminates the cold-start problem. Every new user starts with a working recipe.

### 🌟 6. Natural Language Recipe Modification
Instead of rebuilding JSON:
- "Add a rule for dispute reversals — mirror of the dispute rule but flip debit/credit"
- "Split the fee rule by location"
- "Change the bank account from 1002 to 1005"

The AI interprets, modifies the graph, and shows the diff.

**Why it's wow:** This is what makes the AI + graph combination uniquely powerful. No other tool lets you modify accounting pipelines in plain English.

---

## Competitive Positioning

| Feature | Synder/A2X/Link My Books | BlackLine/HighRadius | fp_core |
|---|---|---|---|
| Target | SMB ecommerce sellers | Enterprise finance teams | SMB bookkeepers & accountants |
| Approach | Pre-built connectors | Full ERP integration | Declarative recipes + AI agent |
| Flexibility | Limited to supported platforms | Highly customizable but complex | Fully customizable via graph |
| AI involvement | None (rule-based only) | Some ML for anomaly detection | AI is the processing engine |
| Price point | $20-200/mo | $50K+/year | TBD |
| Setup time | Minutes (but rigid) | Months | Minutes (with templates) to hours (custom) |

**fp_core's unique moat:** The knowledge graph makes recipes *inspectable, modifiable, and composable* in ways that hard-coded integrations can't match. And having an AI agent that understands accounting semantics means the system can reason about edge cases (like the dispute reversal we just built) rather than just following rigid rules.

---

## Priority Roadmap Recommendation

### Phase 1: Remove Friction (Make it reliable)
1. `list_recipes` — discoverability
2. Compound conditions (`when_all` / `when_any`)
3. Patch operations (`add_rule`, `update_rule`, `remove_rule`)
4. `preview_pipeline` — dry-run against sample data

### Phase 2: Accelerate Onboarding (Make it fast)
5. `infer_schema` — auto-detect from CSV
6. Recipe templates + `clone_recipe`
7. Pre-built recipes for top 5 payment processors
8. Guided recipe builder flow

### Phase 3: Build Trust (Make it confident)
9. Validation dashboard with orphan-row detection
10. `generate_output` — end-to-end formatted CSV
11. Chart of accounts pre-validation
12. Anomaly detection vs. historical patterns

### Phase 4: Scale (Make it a platform)
13. Recipe marketplace / community library
14. Version history + diff
15. Multi-entity support
16. Webhook/scheduled processing
