# Fable Project Analysis

> **Status:** Point-in-time engineering analysis
> **Date:** 2026-07-12
> **Source:** Architecture/strategy review session (EM lens), competitive read of Ramp Stack (launched 2026-06-03)
> **Scope:** Concrete defects, architectural decision records, feature forks, and per-layer doc impacts. Not a roadmap replacement — see `docs/vision_and_roadmap.md`.

---

## 1. Context

FP_core targets the "last mile" of bookkeeping: small-business workflows too odd and too small for ERP customization, currently done in one-off spreadsheets. The declarative recipe graph is the right encoding for that thesis. This analysis captures what the current implementation actually is (vs. what the docs imply), and the smallest set of moves that convert the foundation into something testers can use and the vision can compound on.

**Honest classification of the layers as built:**

| Layer | Docs say | Actually is |
|---|---|---|
| L1–L3 (`domain/`) | Types, ontology, logic | A **correctness substrate**: type system + referee. It validates structure; it does not compute, execute, or infer. Solid, well-tested, cheap to extend. |
| L4 (`persistence/`) | Neo4j I/O | **Single-user prototype**: unindexed full-graph property scans, no tenancy, shared graph for all connected users. |
| L5 (`mcp_server/`) | MCP server | Working remote server (Streamable HTTP + Auth0 on Railway), but recipe state cached **in process memory** — concurrent users collide. |
| Execution | "Planned, medium term" | **Does not exist.** The LLM computes measures and generates entries in-context; gates check the result. |
| Evals | 5 scenarios, passing runs | Real harness (`evals/run_eval.sh` → `claude --print` → Python validators against live Neo4j). Better than most; corpus is synthetic-only. |

**The load-bearing gap:** a *balanced hallucination passes every gate*. If the model invents numbers that net to zero, Gate 2 approves. The gates only close the loop end-to-end once computation is deterministic (server-side).

**The second load-bearing gap:** the system is a **template store, not a ledger**. Generated entries exit as CSV and are never written back. `Transaction`, `TransactionLine`, `CREATED_FROM` provenance — defined, validated, tested, and unpopulated. Every month of tester usage without this loop closed is longitudinal data lost permanently.

---

## 2. Concrete Defects Found

### DEF-1: Money typed as `float` at the graph boundary
`domain/ontology.py:169` — `_TRANSACTION_LINE_PROPS` types `amount: float` while the `TransactionLine` dataclass uses `Decimal` and `validate_transaction_balance` sums `Decimal`. Money-as-float at the persistence boundary is a correctness and credibility defect for an accounting product.

- **Fix:** store amounts as string (serialize `Decimal` → str, reconstitute on load) or integer minor units. Touches L2 (`PropertySchema` type), L4 (serializer/deserializer round-trip), tests.
- **Priority:** P0. Fix before any tester data flows.

### DEF-2: Unindexed full-graph scans in L4
`persistence/operations.py` — `load_pattern_by_recipe`, `load_format_by_id`, delete/verify helpers all run `MATCH (n) WHERE n.recipe_id = $id` with no label and no index. Works at demo scale; degrades linearly with graph size and becomes untenable the moment tenancy multiplies node counts.

- **Fix:** create indexes on `recipe_id`, `format_id`, `_node_id` (Aura supports `CREATE INDEX ... FOR (n:Label) ON ...`; unlabeled scans also need label-scoping in the queries). Add a one-time `ensure_indexes(conn)` operation.
- **Priority:** P0. Cheap, prerequisite for everything below.

### DEF-3: No tenancy; shared mutable server state
`recipe_id` is explicitly *not* a multi-tenancy key (per `domain/CLAUDE.md`). All users of the Railway deployment share one graph, and `mcp_server/__init__.py` caches loaded recipes in process memory keyed without a user dimension. Two concurrent testers interleave state.

- **Fix:** `tenant_id` property on every node (derived from Auth0 subject), scoped into every L4 query and MERGE key; server-side cache keyed by (tenant, recipe). Spec exists: `specs/features/multi_tenant_auth.md`.
- **Priority:** P1. Hard prerequisite for multiple testers and for FORK-3 (evals on user data).

### Security review findings (2026-07-12)

DEF-4 through DEF-6 come from a security review of the Railway/Auth0 deployment. Two higher-severity findings from that same review are already remediated: Cypher injection via Reference labels/property keys (fixed with an identifier allowlist at the serialization boundary in `persistence/serializers.py`), and fail-open auth on misconfiguration (HTTP transport now refuses to start without `AUTH0_DOMAIN`/`AUTH0_AUDIENCE` unless `MCP_ALLOW_UNAUTHENTICATED=true`). The three below remain open.

### DEF-4: No scope / authorization enforcement on tokens
`mcp_server/auth.py:31` parses the token's `scope` claim into `AccessToken.scopes`, but nothing downstream enforces it — every tool handler in `mcp_server/tools.py` is reachable by *any* token Auth0 issues for the audience, including the write/destructive paths (`build_and_save_pipeline`, `build_output`). If the Auth0 tenant permits broad sign-up or machine-to-machine grants, a valid token is effectively an admin token. This compounds DEF-3: no tenancy *and* no scope check means one credential reaches the whole shared graph.

- **Fix:** define required scopes (e.g. `recipe:read`, `recipe:write`) and enforce them in the tool layer — reject calls whose `AccessToken.scopes` lack the scope the tool requires. Pairs naturally with the `tenant_id` work in DEF-3.
- **Priority:** P1. Should land with tenancy (DEF-3), before multiple testers share the deployment.

### DEF-5: Overly broad exception swallow in token verification
`mcp_server/auth.py:34` — `except (jwt.PyJWTError, Exception)` catches everything and returns `None`. It fails closed (denies access, which is correct), but it also collapses operational failures — JWKS fetch errors, network timeouts, key-rotation issues — into an indistinguishable "invalid token." An auth outage would look identical to ordinary bad credentials, making it very hard to diagnose in production.

- **Fix:** catch `jwt.PyJWTError` specifically for the deny path; let unexpected exceptions propagate (or log them at `error` with a distinct message) so infrastructure failures are observable in telemetry. Ties into the FORK-3.3 telemetry work.
- **Priority:** P2. Not exploitable; operability and incident-response risk.

### DEF-6: Raw exception text leaked to clients
`mcp_server/tools.py` — every Neo4j failure path returns the raw exception string to the caller, e.g. `_error(f"Neo4j error: {e}")` (lines 86, 106, 138, 306) and `_error(f"Neo4j save error: {e}")` (383). Driver exceptions can include the connection URI, host, and internal query fragments — information disclosure to any authenticated client, and more of a concern once the deployment is multi-tenant.

- **Fix:** return a generic client-facing message ("internal error processing request") and log the exception detail server-side only. Fold into the telemetry/logging contract in `mcp_server/CLAUDE.md`.
- **Priority:** P2. Information disclosure; low severity today, rises with tenancy.

---

## 3. Architectural Decision Records

### ADR-1: Keep Neo4j — with explicit revisit triggers
Current usage (property scans + one-hop traversal) does not require a graph database; Postgres/JSONB could serve it. Neo4j is retained because (a) every moat feature on the roadmap — provenance chains, consolidation, anomaly detection, cash-flow reasoning — is traversal-shaped; (b) isolation is already clean (only `persistence/connection.py` imports the driver; serializers are pure), so exit cost stays low indefinitely; (c) one migration deliberation (KuzuDB, now dead) was already spent.

**Do not relitigate unless:** Aura cost becomes material at tenant scale, or entry history volume forces FORK-1 below. Decision deferral here has negative cost — spend the cycles on users.

### ADR-2: Positioning vs. Ramp Stack
Ramp Stack (accounting firms, direct QBO read/write, plain-English "skills", human-sign-off guardrails, 4,500 partner firms, free through Aug 2026) wins on integration, onboarding, and distribution. FP_core does not compete for accounting firms. Differentiation is **semantic, machine-checked correctness**: prose skills are unverifiable; a recipe graph provably has both legs of every entry, valid account types, correct normal balances, before anything runs. Viable positions: (a) SMB owner / solo bookkeeper doing their own last-mile work; (b) open MCP-native validation substrate usable by any agent stack.

**Implication:** the end-state that prose-skill products cannot retrofit is *declarative recipe + deterministic execution + semantic gates*. That makes the execution engine strategic, not medium-term (see FORK-2).

### ADR-3: Persist generated entries into the graph (close the ledger loop)
`build_output` (or successor) must write generated entries back as `Transaction`/`TransactionLine` nodes with `CREATED_FROM` provenance, tenant-scoped. Types, validators, and `MERGE_KEYS` already exist; this is wiring, not design. This single change converts FP_core from a stateless transformer into an accumulating knowledge asset and is the precondition for anomaly detection, cash-flow reasoning, and longitudinal evals. Data not captured now is gone.

- **Layer impact:** L5 tool (side-effect write), L4 (entry save path, needs DEF-1 fixed first), L2 (Gate 2 runs before persist — entries that fail balance are never written).
- **Priority:** P1, immediately after tenancy.

---

## 4. Feature Forks

Decision points where the architecture branches. Recorded so each fork is taken deliberately, not by drift.

### FORK-1: Persistence topology — pure graph vs. hybrid
Once ADR-3 lands and entries accumulate monthly, transaction *history* at volume is time-series/columnar-shaped, not graph-shaped. The fork: keep everything in Neo4j vs. graph-for-knowledge + relational/columnar-for-entry-history.
**Position:** stay pure-graph until a real tenant has >~12 months of entries and query latency or Aura cost signals otherwise. The L4 isolation makes the hybrid split mechanical later. Do not pre-build.

### FORK-2: Computation locus — agent-computed vs. server-computed
Today the model computes; the server validates shape. The fork is whether measure computation, rule filtering, and entry generation move server-side (`compute_measures`, then the full L5 execution engine per `docs/user_flow.md` Phase 1–4).
**Position:** take the server-side fork, staged. Two independent arguments compound: (1) **trust** — numbers from code, not the model; kills the balanced-hallucination gap; (2) **evaluability** — every computation moved server-side becomes observable/loggable; everything left in the model's head is invisible to telemetry. Start with `compute_measures` (already spec'd, `specs/features/compute_measures.md`); it is the highest-leverage single tool.

### FORK-3: Eval corpus — synthetic-only vs. user-derived
Three distinct capabilities, in feasibility order:
1. **User-recipe replay** — recipes are structure, not PII. With consent, snapshot tenant recipes as eval fixtures; the existing harness already parameterizes by `recipe_id`. This is the corpus the last-mile thesis actually needs (odd recipes, not the synthetic payroll one). Requires DEF-3.
2. **Schema-conforming synthetic data** — the recipe graph contains `SourceSchema` (columns, types, semantic roles); generate fake rows + known-answer outputs per user recipe automatically. Never touch real transaction rows.
3. **Production telemetry as implicit evals** — the hosted MCP server sees every tool call and every `ValidationResult`. Log (anonymized, consented): Gate 1 first-pass yield, retries per recipe build, Gate 2 failure taxonomy. These are the `vision_and_roadmap.md` success metrics, collected for free. Limit: agent reasoning between tool calls is client-side and unobservable — another argument for FORK-2.

**Position:** build 3 (telemetry) alongside tenancy; 1 and 2 after first testers exist.

### FORK-4: Discovery layer — workflow tool vs. reasoning asset
Cash-flow warnings and anomaly detection are pure L3 functions over an accumulated ledger: `SemanticType.BANK/CLEARING/RECEIVABLE/PAYABLE` already gives the vocabulary ("cash position" is a semantic query, not a hardcoded account list); the knowledge zone supplies specificity ("Customer X is 40% of receivables, paying slower").
**Position:** this is post-PMF *value*, but its *precondition* (ADR-3) is cheap and must land pre-PMF. Do not build the discovery engine now; do start depositing the data it will need.

---

## 5. Sequenced Actions

| # | Action | Layers | Depends on | Size |
|---|--------|--------|------------|------|
| 1 | DEF-1: Decimal-safe amount serialization | L2, L4 | — | S |
| 2 | DEF-2: Indexes + label-scoped queries | L4 | — | S |
| 3 | DEF-3: `tenant_id` end-to-end + per-tenant server cache | L4, L5 | 2 | M |
| 4 | Telemetry: log tool calls + ValidationResults (FORK-3.3) | L5 | 3 | S |
| 5 | ADR-3: persist entries with provenance on `build_output` | L2, L4, L5 | 1, 3 | M |
| 6 | Seed 2 pre-built recipes (Stripe payout, one payroll provider) + 1-page tester quickstart | docs, fixtures | 3 | S |
| 7 | **Recruit 3–5 testers; watch first sessions; bug-log everything** | — | 6 | — |
| 8 | `compute_measures` server-side (FORK-2 stage 1) | L3, L5 | — (parallel ok) | M |
| 9 | User-recipe eval replay + synthetic data gen (FORK-3.1/3.2) | evals | 3, 7 | M |
| 10 | Full execution engine (user_flow Phase 1–4) | L3, L5 | 8, tester signal | L |

Spec freeze remains in effect (per prior review): no new `specs/features/*.md` until step 7 has produced its first external bug-log entry. `docs/bug_log.md` is the feedback engine; point it at people who aren't the author.

---

## 6. Per-Layer Doc Impacts

When the above lands, the package docs must not drift:

- **`domain/CLAUDE.md`** — DEF-1 changes the `TransactionLine` property type contract; ADR-3 means `Transaction`/`TransactionLine` graduate from "unused scaffolding" to live write path (note Gate 2 as pre-persist gate). FORK-2 adds computation functions to L3's inventory ("Builders/Extractors" gains "Computors" or similar — L3 stays pure; source data in, values out).
- **`persistence/CLAUDE.md`** — index inventory + `ensure_indexes` operation; `tenant_id` joins the MERGE-key/identity conventions ("DO NOT change without coordination" section); entry-history save path; revisit-triggers from ADR-1 recorded so the Neo4j question has a documented answer.
- **`mcp_server/CLAUDE.md`** — cache keying contract (tenant, recipe); telemetry contract (what is logged, what is never logged — raw source rows never leave the tool layer); `build_output` side-effect semantics (persists on Gate 2 pass, never on fail).
- **Root `CLAUDE.md`** — canonical counts table will move (tool count, test count) at steps 5 and 8; "Known Constraints" should carry the tenancy and float items until closed.
- **`docs/vision_and_roadmap.md`** — re-sequence: execution engine and entry persistence promoted out of "medium term"; pre-built recipes reframed from scale feature to onboarding prerequisite; add revisit triggers to the Aura infrastructure note.

---

## 7. One-Paragraph Summary

The foundation is better than it needs to be; the product around it doesn't exist yet. Two cheap, compounding architectural moves (tenancy, entry persistence) must land before testers arrive, one defect (float money) must land before any real data flows, and one strategic promotion (server-side computation) converts the gate architecture from "catches unbalanced entries" to "numbers provably from code" — which is simultaneously the trust story, the evaluability story, and the moat against prose-skill competitors. Everything else waits for tester signal.