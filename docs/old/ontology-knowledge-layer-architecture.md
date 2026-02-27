# Ontology Knowledge Layer — Phased Architecture Plan

## Current State (Phase 0)

```
Accountant → Claude Desktop (stdio MCP) → Python core → Neo4j
                                              ↓
                                         YAML ontology
                                         (validates before graph writes)
```

**What exists:**
- Python service with ontology validation logic
- Neo4j as the graph query engine for the ontology
- YAML files as the source of truth for ontology definitions
- Local MCP server running via stdio transport
- Core validation: entries are checked against the ontology before writes to the knowledge graph

**What doesn't exist yet:**
- Multi-tenancy
- Hosted deployment
- DuckDB analytics layer
- Auth system
- Read/Write/Review/Version tool surface exposed via MCP

---

## Target State (After All Phases)

```
Accountant A (Claude)─────┐
Accountant B (ChatGPT)────┤
Accountant C (Claude)─────┤
                           ▼
                ┌─────────────────────┐
                │  Hosted MCP Server  │
                │  (Python, HTTP/SSE) │
                │                     │
                │  API Key Auth       │
                │       ↓             │
                │  TenantContext      │
                │       ↓             │
                │  Tool Router        │
                └────────┬────────────┘
                         │
                ┌────────▼────────┐
                │  Service Layer  │
                │  (tenant-scoped │
                │   business logic│
                └───┬─────┬────┬──┘
                    │     │    │
          ┌─────────┘     │    └──────────┐
          ▼               ▼               ▼
   ┌────────────┐  ┌────────────┐  ┌────────────┐
   │  KùzuDB    │  │  DuckDB    │  │  YAML      │
   │  (graph)   │  │  (analytics│  │  (ontology  │
   │            │  │            │  │   source of │
   │  per-tenant│  │  per-tenant│  │   truth)    │
   │  directory │  │  .duckdb   │  │  per-tenant │
   └────────────┘  └────────────┘  └────────────┘

        All three live under /data/{tenant_id}/
```

### Tenant Directory Structure

```
/data/{tenant_id}/
  ├── ontology/
  │   ├── versions/
  │   │   ├── v1.0.yaml
  │   │   └── v1.1.yaml
  │   ├── periods.yaml
  │   ├── metrics.yaml
  │   ├── write_recipes.yaml
  │   ├── review_recipes.yaml
  │   └── validation_rules.yaml
  ├── graph/                     ← KùzuDB embedded database
  │   └── (kuzu db files)
  ├── analytics/
  │   └── workspace.duckdb       ← DuckDB per-tenant file
  └── audit/
      └── events.jsonl           ← append-only action log
```

Every tenant is a folder. Backup = copy the folder. Delete tenant = delete the folder. Migrate = move the folder. This is the simplest operational model possible.

---

## Phase 1: Multi-Tenant Foundation + Auth

**Goal:** Establish tenant isolation, API key auth, and the hosted server skeleton. Nothing new is exposed to accountants yet — this phase is pure infrastructure.

### 1.1 Tenant Data Model

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    user_id: str
    tenant_dir: Path          # /data/{tenant_id}
    
    @property
    def ontology_dir(self) -> Path:
        return self.tenant_dir / "ontology"
    
    @property
    def graph_dir(self) -> Path:
        return self.tenant_dir / "graph"
    
    @property
    def duckdb_path(self) -> Path:
        return self.tenant_dir / "analytics" / "workspace.duckdb"
    
    @property
    def audit_path(self) -> Path:
        return self.tenant_dir / "audit" / "events.jsonl"
```

Every function in your service layer accepts a `TenantContext` as its first argument. This is the single mechanism that scopes all operations to the right tenant. No global state, no implicit tenant resolution.

### 1.2 API Key Auth

Simple model: each tenant gets one or more API keys. Accountants configure this key in their Claude MCP settings.

```python
# Storage: a single SQLite file (not per-tenant — this is the control plane)
# /data/_control/auth.db

# Schema:
# api_keys(key_hash TEXT PK, tenant_id TEXT, user_id TEXT, created_at, expires_at, revoked BOOL)
# tenants(tenant_id TEXT PK, name TEXT, created_at, status TEXT)

class AuthService:
    """Resolves API key → TenantContext. Lives outside tenant directories."""
    
    def __init__(self, control_db_path: Path, data_root: Path):
        self.db = sqlite3.connect(control_db_path)
        self.data_root = data_root
    
    def authenticate(self, api_key: str) -> TenantContext:
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        row = self.db.execute(
            "SELECT tenant_id, user_id FROM api_keys WHERE key_hash = ? AND NOT revoked",
            (key_hash,)
        ).fetchone()
        if not row:
            raise AuthError("Invalid or revoked API key")
        
        tenant_id, user_id = row
        return TenantContext(
            tenant_id=tenant_id,
            user_id=user_id,
            tenant_dir=self.data_root / tenant_id
        )
```

**How accountants configure this in Claude:**

```json
// Claude Desktop MCP config (claude_desktop_config.json)
{
  "mcpServers": {
    "accounting-knowledge": {
      "url": "https://your-server.com/mcp/sse",
      "headers": {
        "Authorization": "Bearer ak_tenant123_xxxxx"
      }
    }
  }
}
```

### 1.3 Hosted MCP Server Shell

Swap from stdio to HTTP/SSE transport. The Python MCP SDK (`mcp` package) supports both.

```python
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Route

mcp_server = Server("ontology-knowledge-layer")
auth_service = AuthService(CONTROL_DB, DATA_ROOT)

async def handle_sse(request):
    # Extract API key from Authorization header
    api_key = request.headers.get("Authorization", "").removeprefix("Bearer ")
    ctx = auth_service.authenticate(api_key)
    
    # Attach tenant context to the MCP session
    # (implementation depends on your session management approach)
    transport = SseServerTransport("/mcp/messages")
    async with transport.connect_sse(request.scope, request.receive, request._send) as streams:
        await mcp_server.run(streams[0], streams[1], ctx)

app = Starlette(routes=[
    Route("/mcp/sse", handle_sse),
])
```

### 1.4 Neo4j → KùzuDB Migration

This is the right time to do this — before you have real tenants in production.

**Why migrate now:**
- File-per-tenant parity: KùzuDB is embedded, so each tenant gets a directory — just like DuckDB and YAML
- No network dependency: removes Neo4j as infrastructure to manage
- Simpler deployment: your entire server is a single Python process + a data directory
- KùzuDB supports the Cypher query language, so your existing Neo4j queries likely port with minimal changes

**Migration approach:**
1. Write a `GraphStore` interface that your service layer programs against
2. Implement `Neo4jGraphStore` (what you have now) and `KuzuGraphStore` (new)
3. Run both in parallel during development, validate query parity
4. Drop Neo4j once KùzuDB is verified

```python
from abc import ABC, abstractmethod

class GraphStore(ABC):
    """Interface for ontology graph operations. Tenant-scoped."""
    
    @abstractmethod
    def resolve_accounts(self, concept_name: str) -> list[AccountMapping]: ...
    
    @abstractmethod
    def resolve_period(self, reference: str) -> PeriodBoundaries: ...
    
    @abstractmethod
    def get_validation_rules(self, entry_type: str) -> list[ValidationRule]: ...
    
    @abstractmethod
    def rebuild_from_yaml(self, ontology_dir: Path) -> None:
        """Rebuild the graph from YAML source of truth."""
        ...


class KuzuGraphStore(GraphStore):
    """Embedded KùzuDB implementation. One database directory per tenant."""
    
    def __init__(self, graph_dir: Path):
        import kuzu
        self.db = kuzu.Database(str(graph_dir))
        self.conn = kuzu.Connection(self.db)
    
    def resolve_accounts(self, concept_name: str) -> list[AccountMapping]:
        result = self.conn.execute(
            "MATCH (c:Concept {name: $name})-[:MAPS_TO]->(a:Account) "
            "RETURN a.code, a.name, a.normal_balance",
            {"name": concept_name}
        )
        return [AccountMapping(**row) for row in result.get_as_df().to_dict("records")]
```

### 1.5 TenantStore — Connection Lifecycle Management

Manages lazy opening and caching of per-tenant DuckDB and KùzuDB connections.

```python
import duckdb
from functools import lru_cache

class TenantStore:
    """Manages per-tenant database connections with lazy initialization."""
    
    def __init__(self, data_root: Path):
        self.data_root = data_root
        self._duckdb_connections: dict[str, duckdb.DuckDBPyConnection] = {}
        self._graph_stores: dict[str, KuzuGraphStore] = {}
    
    def get_duckdb(self, ctx: TenantContext) -> duckdb.DuckDBPyConnection:
        if ctx.tenant_id not in self._duckdb_connections:
            ctx.duckdb_path.parent.mkdir(parents=True, exist_ok=True)
            self._duckdb_connections[ctx.tenant_id] = duckdb.connect(str(ctx.duckdb_path))
        return self._duckdb_connections[ctx.tenant_id]
    
    def get_graph(self, ctx: TenantContext) -> KuzuGraphStore:
        if ctx.tenant_id not in self._graph_stores:
            ctx.graph_dir.mkdir(parents=True, exist_ok=True)
            self._graph_stores[ctx.tenant_id] = KuzuGraphStore(ctx.graph_dir)
        return self._graph_stores[ctx.tenant_id]
    
    def provision_tenant(self, tenant_id: str) -> None:
        """Create directory structure for a new tenant."""
        tenant_dir = self.data_root / tenant_id
        (tenant_dir / "ontology" / "versions").mkdir(parents=True, exist_ok=True)
        (tenant_dir / "graph").mkdir(parents=True, exist_ok=True)
        (tenant_dir / "analytics").mkdir(parents=True, exist_ok=True)
        (tenant_dir / "audit").mkdir(parents=True, exist_ok=True)
```

### Phase 1 Deliverables Checklist

- [ ] `TenantContext` dataclass
- [ ] Control plane SQLite DB for auth (api_keys, tenants tables)
- [ ] `AuthService` with API key → TenantContext resolution
- [ ] `GraphStore` interface + `KuzuGraphStore` implementation
- [ ] `TenantStore` for connection lifecycle
- [ ] Hosted MCP server (HTTP/SSE) with auth middleware
- [ ] Tenant provisioning script (creates directory structure)
- [ ] Neo4j → KùzuDB query migration (port existing Cypher queries)
- [ ] Smoke test: connect from Claude Desktop with API key, server resolves tenant

---

## Phase 2: MCP Tool Surface (Read-Only)

**Goal:** Expose the ontology query tools so accountants can ask questions through Claude. No writes, no analytics — just ontology resolution.

### 2.1 Tool Registration Pattern

Every tool follows the same shape: receive request → resolve tenant → call service → return result. The tenant context is injected from the auth middleware, never from the LLM.

```python
@mcp_server.tool()
async def resolve_period(reference: str) -> dict:
    """Convert a natural language time reference to exact date boundaries.
    
    Examples: 'last quarter', 'January', 'Q3 2024', 'YTD'
    Returns: start_date, end_date, period_label, period_status (open/closed)
    """
    ctx = get_current_tenant_context()  # from session/middleware
    graph = tenant_store.get_graph(ctx)
    ontology = load_ontology(ctx)
    
    period = ontology.resolve_period(reference, graph)
    return {
        "start_date": period.start_date.isoformat(),
        "end_date": period.end_date.isoformat(),
        "label": period.label,
        "status": period.status,
        "fiscal_year": period.fiscal_year
    }


@mcp_server.tool()
async def resolve_accounts(concept: str) -> dict:
    """Map an accounting concept to specific account codes in the tenant's chart of accounts.
    
    Examples: 'Revenue', 'Rent Expense', 'Accrued Liabilities'
    Returns: list of account codes, names, normal balances, and the concept hierarchy
    """
    ctx = get_current_tenant_context()
    graph = tenant_store.get_graph(ctx)
    
    accounts = graph.resolve_accounts(concept)
    return {
        "concept": concept,
        "accounts": [
            {"code": a.code, "name": a.name, "normal_balance": a.normal_balance}
            for a in accounts
        ]
    }


@mcp_server.tool()
async def resolve_metric(metric_name: str) -> dict:
    """Look up the recipe for a metric: formula, data sources, constraints.
    
    Examples: 'revenue per unit', 'gross margin', 'burn rate'
    Returns: formula, required data sources, period constraints, account inputs
    """
    ctx = get_current_tenant_context()
    ontology = load_ontology(ctx)
    graph = tenant_store.get_graph(ctx)
    
    metric = ontology.resolve_metric(metric_name, graph)
    return {
        "name": metric.name,
        "formula": metric.formula,
        "inputs": metric.inputs,
        "sources": metric.sources,
        "period_constraint": metric.period_constraint
    }


@mcp_server.tool()
async def validate_query(query_plan: dict) -> dict:
    """Validate a proposed query against ontology rules before execution.
    
    Checks: account codes exist, period is valid, date fields are correct,
    entity isolation is maintained.
    """
    ctx = get_current_tenant_context()
    ontology = load_ontology(ctx)
    graph = tenant_store.get_graph(ctx)
    
    result = ontology.validate_query(query_plan, graph)
    return {
        "valid": result.is_valid,
        "errors": result.errors,
        "warnings": result.warnings
    }


@mcp_server.tool()
async def list_topics() -> dict:
    """List all available analytical topics and metrics for this tenant."""
    ctx = get_current_tenant_context()
    ontology = load_ontology(ctx)
    
    return {
        "metrics": [m.name for m in ontology.metrics],
        "account_concepts": [c.name for c in ontology.concepts],
        "available_periods": [p.label for p in ontology.periods]
    }
```

### 2.2 Ontology Loader (YAML → In-Memory)

```python
import yaml
from functools import lru_cache
from pathlib import Path

class OntologyLoader:
    """Loads and caches ontology from tenant's YAML files.
    
    Cache is invalidated when YAML files change (check mtime).
    """
    
    def __init__(self):
        self._cache: dict[str, tuple[float, Ontology]] = {}
    
    def load(self, ctx: TenantContext) -> Ontology:
        ontology_dir = ctx.ontology_dir
        current_mtime = self._latest_mtime(ontology_dir)
        
        if ctx.tenant_id in self._cache:
            cached_mtime, cached_ontology = self._cache[ctx.tenant_id]
            if cached_mtime >= current_mtime:
                return cached_ontology
        
        # Load fresh from YAML
        periods = yaml.safe_load((ontology_dir / "periods.yaml").read_text())
        metrics = yaml.safe_load((ontology_dir / "metrics.yaml").read_text())
        rules = yaml.safe_load((ontology_dir / "validation_rules.yaml").read_text())
        
        # Load active version
        versions_dir = ontology_dir / "versions"
        active_version = self._find_active_version(versions_dir)
        
        ontology = Ontology(
            periods=periods,
            metrics=metrics,
            validation_rules=rules,
            active_version=active_version
        )
        
        self._cache[ctx.tenant_id] = (current_mtime, ontology)
        return ontology
```

### Phase 2 Deliverables Checklist

- [ ] 5 MCP tools registered: resolve_period, resolve_accounts, resolve_metric, validate_query, list_topics
- [ ] `OntologyLoader` with YAML parsing and caching
- [ ] Tool responses shaped for LLM consumption (clear, structured dicts)
- [ ] Audit logging: every tool invocation logged to tenant's events.jsonl
- [ ] Integration test: accountant asks Claude "What does revenue per unit mean?" → Claude calls resolve_metric → gets back formula and sources

---

## Phase 3: Read Mode (DuckDB Analytics)

**Goal:** Accountants can ask quantitative questions. The LLM uses ontology tools from Phase 2 to understand the question, then executes against DuckDB for actual numbers.

### 3.1 Data Sync Pipeline

Before DuckDB can answer questions, it needs data. Each tenant's DuckDB file is populated from their accounting system.

```python
@mcp_server.tool()
async def sync_data(source: str = "accounting") -> dict:
    """Trigger a data sync from the accounting system into the analytics workspace.
    
    This pulls current data from QBO/Xero into the tenant's DuckDB for querying.
    """
    ctx = get_current_tenant_context()
    db = tenant_store.get_duckdb(ctx)
    
    # Pull from accounting system via the accounting MCP
    # (your existing QBO/Xero integration)
    raw_data = await fetch_from_accounting(ctx)
    
    # Load into DuckDB
    db.execute("CREATE TABLE IF NOT EXISTS journal_entries AS SELECT * FROM raw_data")
    db.execute("CREATE TABLE IF NOT EXISTS chart_of_accounts AS SELECT * FROM accounts_data")
    
    return {"status": "synced", "records": len(raw_data)}


@mcp_server.tool()
async def execute_read(query_plan: dict) -> dict:
    """Execute a validated read query against the tenant's analytics workspace.
    
    The query_plan should first be validated via validate_query.
    Returns: query results as structured data.
    """
    ctx = get_current_tenant_context()
    
    # Validate first (defense in depth)
    ontology = load_ontology(ctx)
    graph = tenant_store.get_graph(ctx)
    validation = ontology.validate_query(query_plan, graph)
    if not validation.is_valid:
        return {"error": "Query failed validation", "reasons": validation.errors}
    
    # Execute against DuckDB
    db = tenant_store.get_duckdb(ctx)
    sql = build_sql_from_plan(query_plan, ontology)
    result = db.execute(sql).fetchdf()
    
    return {
        "columns": list(result.columns),
        "rows": result.to_dict("records"),
        "row_count": len(result),
        "query_metadata": {
            "period": query_plan.get("period"),
            "ontology_version": ontology.active_version.id
        }
    }
```

### 3.2 The Read Flow (End to End)

```
Accountant: "What was revenue per unit last quarter?"

Claude calls: resolve_metric("revenue per unit")
  → formula: revenue / units_shipped
  → sources: accounting (revenue), snowflake (units)

Claude calls: resolve_period("last quarter")  
  → Q4 2024: 2024-10-01 to 2024-12-31, status: closed

Claude calls: resolve_accounts("Revenue")
  → accounts 4000, 4010

Claude calls: execute_read({
    "metric": "revenue",
    "accounts": [4000, 4010],
    "period": {"start": "2024-10-01", "end": "2024-12-31"},
    "date_field": "transaction_date"
})
  → {"total_revenue": 450000}

Claude calls: execute_read({...units query...})
  → {"units_shipped": 1500}

Claude responds: "Revenue per unit last quarter was $300 
                  ($450K revenue / 1,500 units shipped, Q4 2024)"
```

### Phase 3 Deliverables Checklist

- [ ] Data sync pipeline (accounting system → tenant DuckDB)
- [ ] `execute_read` tool with ontology-validated SQL generation
- [ ] `sync_status` tool (when was data last synced?)
- [ ] SQL builder that respects ontology constraints (period boundaries, account scoping, entity isolation)
- [ ] Query result formatting for LLM consumption
- [ ] Integration test: full read flow from natural language → ontology resolution → DuckDB query → answer

---

## Phase 4: Write Mode

**Goal:** LLM proposes journal entries, ontology validates them, accountant approves in chat, entries are booked to the accounting system.

### 4.1 Write Tools

```python
@mcp_server.tool()
async def propose_entry(description: str) -> dict:
    """Construct a validated journal entry from a natural language description.
    
    Example: 'Accrue $12,000 for January rent'
    Returns: proposed journal entry with full validation results.
    The accountant must approve before booking.
    """
    ctx = get_current_tenant_context()
    ontology = load_ontology(ctx)
    graph = tenant_store.get_graph(ctx)
    
    # LLM has already figured out the entry structure from the ontology;
    # this tool validates and formats it
    entry = ontology.construct_entry(description, graph)
    validation = ontology.validate_entry(entry)
    
    return {
        "entry": entry.to_dict(),  # date, memo, lines (DR/CR)
        "validation": {
            "valid": validation.is_valid,
            "checks_passed": validation.checks_passed,
            "errors": validation.errors,
            "warnings": validation.warnings
        },
        "requires_approval": True,
        "confidence": entry.confidence_tier  # HIGH / MEDIUM / LOW
    }


@mcp_server.tool()
async def book_entry(entry_id: str, approved: bool = False) -> dict:
    """Book an approved journal entry to the accounting system.
    
    The entry must have been previously proposed and validated.
    Set approved=True only after the accountant has explicitly confirmed.
    """
    if not approved:
        return {"error": "Entry must be explicitly approved by the accountant before booking."}
    
    ctx = get_current_tenant_context()
    
    # Retrieve the proposed entry (stored temporarily)
    entry = get_pending_entry(ctx, entry_id)
    if not entry:
        return {"error": "Entry not found or expired."}
    
    # Re-validate (defense in depth — state may have changed)
    ontology = load_ontology(ctx)
    validation = ontology.validate_entry(entry)
    if not validation.is_valid:
        return {"error": "Entry no longer passes validation", "reasons": validation.errors}
    
    # Book via accounting system
    result = await book_to_accounting_system(ctx, entry)
    
    # Audit log
    log_audit_event(ctx, "ENTRY_BOOKED", {
        "entry": entry.to_dict(),
        "booked_by": ctx.user_id,
        "ontology_version": ontology.active_version.id
    })
    
    return {"status": "booked", "confirmation": result}
```

### 4.2 Pending Entry Storage

Proposed entries need to persist between the "propose" and "book" tool calls (accountant reviews in between). Store these in DuckDB or a simple JSON file per tenant.

```python
# Pending entries: short-lived, stored in tenant's DuckDB or a temp table
# Expire after 1 hour if not approved
# Keyed by entry_id (UUID)
```

### Phase 4 Deliverables Checklist

- [ ] `propose_entry` tool with full ontology validation
- [ ] `validate_entry` standalone validation tool
- [ ] `book_entry` tool with approval gate
- [ ] `run_write_recipe` tool for batch operations (month-end accruals, etc.)
- [ ] Pending entry storage with expiration
- [ ] Confidence tier classification (HIGH/MEDIUM/LOW/ZERO)
- [ ] Audit logging for all write operations
- [ ] Integration test: propose → accountant approves in chat → book → verify in QBO

---

## Cross-Cutting Concerns (All Phases)

### Audit Logging

Every action appends to the tenant's `audit/events.jsonl`:

```json
{"timestamp": "2025-02-23T10:15:00Z", "tenant_id": "acme", "user_id": "jane@acme.com", "action": "TOOL_CALL", "tool": "resolve_period", "input": {"reference": "last quarter"}, "ontology_version": "v1.0"}
{"timestamp": "2025-02-23T10:15:01Z", "tenant_id": "acme", "user_id": "jane@acme.com", "action": "ENTRY_BOOKED", "entry_id": "uuid-123", "ontology_version": "v1.0"}
```

### Error Handling Strategy

Tools should return structured errors, never raise exceptions to the LLM:

```python
# Good: structured error the LLM can reason about
return {"error": "Period Q3 2024 is closed. Cannot book entries.", "suggestion": "Reopen the period or use a different date."}

# Bad: raw exception that produces garbage in the chat
raise ValueError("Period closed")
```

### Future Phases (Not Designed Yet)

These come after the four core phases are solid:

- **Phase 5: Review Mode** — audit recipes, classification checks, period cutoff review
- **Phase 6: Version Mode** — ontology versioning, alternative P&L views, version DAG
- **Phase 7: Multi-Entity** — consolidated reporting, intercompany elimination
- **Phase 8: Recipe Engine** — month-end close workflow automation
- **Phase 9: Tenant Admin** — self-service onboarding, usage dashboards, billing

---

## Technology Stack Summary

| Component | Technology | Reason |
|-----------|-----------|--------|
| Language | Python | Existing codebase |
| MCP SDK | `mcp` (Python) | Official Anthropic SDK, supports HTTP/SSE |
| Web Framework | Starlette / Uvicorn | Lightweight, async, wraps MCP transport |
| Ontology Source of Truth | YAML files | Human-readable, diffable, git-friendly |
| Graph Query Engine | KùzuDB (embedded) | File-per-tenant, Cypher-compatible, no infra |
| Analytics Engine | DuckDB (embedded) | File-per-tenant, fast OLAP, Python-native |
| Auth / Control Plane | SQLite | Single file, no infra, sufficient for API key lookups |
| Audit Log | JSONL files | Append-only, per-tenant, simple to query with DuckDB |
| Deployment | Single Python process | Reads/writes a data directory, no network DBs |

### Key Dependencies

```
# Python packages
mcp                  # MCP server SDK
kuzu                 # Embedded graph database
duckdb               # Embedded analytics database
pyyaml               # Ontology YAML parsing
starlette            # HTTP framework for SSE transport
uvicorn              # ASGI server
```

---

## Architecture Principles

1. **Tenant = folder.** All tenant state lives in `/data/{tenant_id}/`. No shared mutable state between tenants.

2. **YAML is the source of truth.** KùzuDB is a derived, rebuildable cache. If the graph is corrupted, rebuild it from YAML. The YAML files are what you version in git.

3. **The LLM never sees tenant IDs.** Tenant context is resolved from the API key in the auth middleware. Tools receive a scoped context, not raw identifiers.

4. **Validate twice, book once.** Ontology validation happens at proposal time AND at booking time. State can change between the two calls.

5. **Structured errors, not exceptions.** Every tool returns a dict with either results or a clear error message the LLM can relay to the accountant.

6. **Audit everything.** Every tool call, every write, every approval — appended to the tenant's JSONL log with timestamp, user, and ontology version.

7. **Phase incrementally.** Each phase produces a working system. Phase 1 is infrastructure with no user-facing tools. Phase 2 adds read-only ontology tools. Phase 3 adds analytics. Phase 4 adds writes. You can ship and get feedback at each boundary.
