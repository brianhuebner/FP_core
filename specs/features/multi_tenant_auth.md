# Spec: Multi-Tenant Auth with Per-Tenant KuzuDB Isolation

> **Status:** Draft
> **Created:** 2026-02-23
> **Spec type:** Feature
> **Depends on:** Neo4j to KuzuDB Migration (must be completed first)

---

## Purpose

Enable multiple tenants to use a single deployed FP_core MCP server, each with isolated accounting data. Tenants authenticate via API key, which resolves to a dedicated KuzuDB database directory. This is the prerequisite for hosting FP_core on Railway (or any platform) as a shared service that clients connect to remotely.

---

## Layer Placement

**Primary layer:** L5 — MCP Server (auth middleware + transport change)
**Layers touched:**

| Layer | Package | What changes |
|-------|---------|--------------|
| L1 Types | `domain/types.py`, `types_recipe.py` | No changes |
| L2 Ontology | `domain/ontology.py`, `ontology_recipe.py` | No changes |
| L3 Logic | `domain/logic.py` | No changes |
| L4 Persistence | `persistence/` | No changes (connection interface unchanged; callers pass `conn`) |
| L5 MCP Server | `mcp_server/` | New `auth.py`, new `tenant.py`; transport swap in `__init__.py`; connection routing in `tools.py` |

---

## Domain Types (L1)

No Layer 1 changes required. Multi-tenancy is an infrastructure concern, not a domain concern. All frozen dataclasses, enums, and `GraphPattern` contracts remain unchanged.

---

## Schema Definitions (L2)

No Layer 2 changes required. Tenant isolation is achieved at the database level (separate KuzuDB directories), not at the ontology level. Each tenant's database has the same schema — `ensure_schema()` runs on every new connection.

**Validators affected:** None.

**Gate classification:**
- Gate 1 (template-time): No changes
- Gate 2 (runtime): No changes

---

## Pure Functions (L3)

No Layer 3 changes required. Builders, extractors, and validators operate on `GraphPattern` objects with no awareness of which tenant produced them.

---

## Persistence Contract (L4)

No Layer 4 changes required. The key insight is that all persistence functions (`save_pattern`, `load_pattern_by_recipe`, `load_format_by_id`) already accept a `conn` parameter. Tenant routing is handled by passing a different `KuzuConnection` (pointing to a different `db_path`) — the persistence layer doesn't know or care which tenant it's serving.

---

## MCP Interface (L5)

This is the primary layer of change. Three new concerns are introduced: authentication, tenant-scoped connections, and HTTP transport.

### Transport change

Replace STDIO with Streamable HTTP (or SSE fallback). This is required for remote client access.

```python
# Before (mcp_server/__init__.py):
def main():
    mcp.run(transport="stdio")

# After:
def main():
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
    )
```

**STDIO preservation:** A `--stdio` CLI flag allows local development to continue using STDIO transport. The default becomes HTTP for deployment.

```python
def main():
    import sys
    transport = "stdio" if "--stdio" in sys.argv else "streamable-http"
    kwargs = {}
    if transport != "stdio":
        kwargs["host"] = "0.0.0.0"
        kwargs["port"] = int(os.environ.get("PORT", 8000))
    mcp.run(transport=transport, **kwargs)
```

### New module: `mcp_server/auth.py`

Manages API keys and tenant resolution. Uses SQLite as a lightweight control plane — no additional infrastructure needed on Railway (SQLite file lives alongside KuzuDB tenant directories).

```python
import hashlib
import secrets
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Tenant:
    tenant_id: str
    name: str
    is_active: bool


def init_auth_db(db_path: str) -> None:
    """Create the auth SQLite database and tables if they don't exist.
    Idempotent — safe to call on every startup."""

edef generate_api_key() -> str:
    """Generate an API key with fpk_ prefix + 32 bytes of secrets.token_urlsafe (~47 chars)."""

def hash_api_key(api_key: str) -> str:
    """SHA-256 hash of the API key for storage. Plain keys are never stored."""

def create_tenant(db_path: str, tenant_id: str, name: str) -> str:
    """Create a new tenant and return a generated API key (fpk_... format).
    The key is returned exactly once — only the hash is stored."""

def resolve_tenant(db_path: str, api_key: str) -> Tenant | None:
    """Look up a tenant by API key. Returns None if key is invalid or tenant is inactive."""

def deactivate_tenant(db_path: str, tenant_id: str) -> bool:
    """Soft-delete: set is_active=False. Data is preserved, access is revoked."""
```

**SQLite schema:**

```sql
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id   TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS api_keys (
    key_hash    TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL REFERENCES tenants(tenant_id),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    last_used   TEXT
);

CREATE INDEX IF NOT EXISTS idx_api_keys_tenant ON api_keys(tenant_id);
```

**Design decisions:**
- API keys are hashed with SHA-256 before storage. The plain key is returned exactly once at creation time.
- One tenant can have multiple API keys (key rotation without downtime).
- Soft-delete via `is_active` flag — tenant data directories are preserved, only access is revoked.
- No roles/permissions within a tenant — all keys for a tenant have full access to that tenant's data. Role-based access is out of scope.

### New module: `mcp_server/tenant.py`

Manages per-tenant KuzuDB connections, server-side state, LRU eviction, and the `contextvars`-based tenant resolution for tool handlers.

```python
from __future__ import annotations

import contextvars
import os
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict

from domain.types import GraphPattern
from persistence.connection import KuzuConnection

# Per-request tenant context, set by TenantAuthMiddleware
tenant_var: contextvars.ContextVar[TenantContext] = contextvars.ContextVar("tenant_context")

# Configurable limits
MAX_CONNECTIONS = int(os.environ.get("MAX_TENANT_CONNECTIONS", "20"))
BUFFER_POOL_SIZE = int(os.environ.get("KUZU_BUFFER_POOL_MB", "64")) * 1024 * 1024


@dataclass
class TenantContext:
    tenant_id: str
    connection: KuzuConnection
    loaded_recipes: Dict[str, GraphPattern] = field(default_factory=dict)
    loaded_formats: Dict[str, GraphPattern] = field(default_factory=dict)
    last_accessed: float = field(default_factory=time.monotonic)


# Active tenant contexts, keyed by tenant_id. OrderedDict for LRU ordering.
_contexts: OrderedDict[str, TenantContext] = OrderedDict()


def get_tenant_context(tenant_id: str, data_root: str) -> TenantContext:
    """Get or create a TenantContext for the given tenant.

    Opens a KuzuConnection to {data_root}/tenants/{tenant_id}/ on first access.
    Connection uses BUFFER_POOL_SIZE (default 64 MB) per database.
    Evicts least-recently-used tenant if MAX_CONNECTIONS cap is reached.
    """

def _evict_lru() -> None:
    """Close and remove the least-recently-used tenant context."""

def close_tenant_context(tenant_id: str) -> None:
    """Close and remove a tenant's connection and cached state."""

def close_all() -> None:
    """Close all tenant connections. Called on server shutdown."""
```

**Directory layout on disk:**

```
$DATA_ROOT/
  auth.db                    # SQLite control plane
  tenants/
    acme_corp/               # KuzuDB database directory
    widgets_inc/             # KuzuDB database directory
    ...
```

**Design decisions:**
- Connections are lazily created and cached in `_contexts`. A tenant's first request opens the connection; subsequent requests reuse it.
- `last_accessed` is updated on every `get_tenant_context` call. When `_contexts` reaches `MAX_CONNECTIONS`, the oldest idle context is evicted (connection closed, caches dropped). Eviction is not data loss — the KuzuDB directory persists, and the next request re-opens it.
- Each `kuzu.Database` is opened with `buffer_pool_size=BUFFER_POOL_SIZE` (default 64 MB). At the default cap of 20 tenants, this is ~1.3 GB max buffer pool usage.
- Each `TenantContext` holds its own `loaded_recipes` and `loaded_formats` dicts, replacing the current global `_loaded_recipes` / `_loaded_formats`.
- `DATA_ROOT` env var points to the persistent volume (e.g., Railway volume mount).
- Connection cleanup happens on server shutdown via `close_all()`.

**Env vars:**

| Env var | Default | Purpose |
|---------|---------|---------|
| `DATA_ROOT` | (required) | Root directory for auth.db and tenant KuzuDB directories |
| `MAX_TENANT_CONNECTIONS` | `20` | Max concurrent open tenant databases before LRU eviction |
| `KUZU_BUFFER_POOL_MB` | `64` | Buffer pool size per tenant database in MB |
| `PORT` | `8000` | HTTP listen port (used by Streamable HTTP transport) |

### Tool signatures affected

**No tool signature changes.** All 6 tools keep the same parameters and return the same JSON shapes. The change is internal — instead of calling `get_connection()` (global singleton), tools call `get_tenant_context(tenant_id, data_root)` to get a tenant-scoped connection and cache.

The tenant_id is resolved from the API key in the request headers *before* the tool handler runs. Tools receive the tenant context via MCP server state, not via tool parameters — tenants never see or pass their own tenant_id.

### How tenant resolution reaches tools

FastMCP's Streamable HTTP transport runs as a Starlette ASGI app, supporting standard Starlette middleware. The auth flow uses Python's `contextvars` module (the same pattern FastMCP's own `AuthContextMiddleware` uses internally):

```python
# mcp_server/tenant.py
import contextvars
from starlette.requests import Request

tenant_var: contextvars.ContextVar[TenantContext] = contextvars.ContextVar("tenant_context")

class TenantAuthMiddleware:
    """Starlette ASGI middleware: extracts Bearer token, resolves tenant,
    sets TenantContext in contextvar for the duration of the request."""

    def __init__(self, app, auth_db_path: str, data_root: str):
        self.app = app
        self.auth_db_path = auth_db_path
        self.data_root = data_root

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            request = Request(scope, receive)
            api_key = _extract_bearer(request.headers.get("authorization"))
            if api_key is None:
                # Return 401
                ...
            tenant = resolve_tenant(self.auth_db_path, api_key)
            if tenant is None or not tenant.is_active:
                # Return 401
                ...
            context = get_tenant_context(tenant.tenant_id, self.data_root)
            token = tenant_var.set(context)
            try:
                await self.app(scope, receive, send)
            finally:
                tenant_var.reset(token)
        else:
            await self.app(scope, receive, send)
```

Tool handlers access the resolved context via `tenant_var.get()`:

```python
# mcp_server/tools.py
from mcp_server.tenant import tenant_var

@mcp.tool()
def load_recipe(recipe_id: str) -> str:
    ctx = tenant_var.get()          # Per-request, async-safe
    conn = ctx.connection            # Tenant-scoped KuzuDB
    loaded = ctx.loaded_recipes      # Tenant-scoped cache
    ...
```

This is async-safe (each async task gets its own contextvar value) and keeps auth logic entirely out of tool handler code.

### JSON spec format

No changes. Pipeline specs and format specs are unchanged.

### Summarizer output

No changes. Summarizers consume `GraphPattern` objects, not tenant metadata.

---

## Data Flow

```
Client request + Authorization: Bearer <api_key>
    |
    v
HTTP transport (Streamable HTTP / SSE)
    |
    v
auth.py — resolve_tenant(api_key) → Tenant
    |
    v
tenant.py — get_tenant_context(tenant_id) → TenantContext
    |                                          ├── connection: KuzuConnection(/data/tenants/{tenant_id}/)
    |                                          ├── loaded_recipes: {}
    |                                          └── loaded_formats: {}
    |
    v
tools.py — tool handler uses TenantContext.connection and TenantContext.loaded_*
    |
    v
[Existing flow unchanged from here down]
    |
    v
builders.py → GraphPattern → Gate 1 → serializers.py → KuzuDB → deserializers.py → summarizers.py
    |
    v
JSON response (to authenticated client)
```

---

## Examples

### Happy path: tenant creation (admin CLI)

```bash
# Admin creates a new tenant (CLI tool, not MCP endpoint)
$ python -m mcp_server.admin create-tenant --id acme_corp --name "Acme Corporation"
Tenant created: acme_corp
API key: fpk_xxxxxxxxxxxx...  (store this — it cannot be retrieved later)
```

### Happy path: authenticated MCP tool call

```
POST /mcp HTTP/1.1
Authorization: Bearer fpk_xxxxxxxxxxxx...
Content-Type: application/json

{
  "method": "tools/call",
  "params": {
    "name": "load_recipe",
    "arguments": {"recipe_id": "payroll_v1"}
  }
}

// Response: same JSON shape as today
{
  "schema": { "name": "payroll_export", ... },
  "recipe": { "name": "Payroll Journal", "rules": [...] }
}
```

### Error case: invalid API key

```
POST /mcp HTTP/1.1
Authorization: Bearer invalid_key_here

// Response: HTTP 401
{"error": "Invalid or inactive API key"}
```

### Error case: missing Authorization header

```
POST /mcp HTTP/1.1

// Response: HTTP 401
{"error": "Missing Authorization header. Provide: Authorization: Bearer <api_key>"}
```

### Edge case: deactivated tenant

A deactivated tenant's API key resolves to `is_active=False`. The request is rejected with 401. The tenant's KuzuDB directory is preserved — reactivation restores access to existing data.

### Edge case: first request for a new tenant

The tenant's KuzuDB directory doesn't exist yet. `KuzuConnection(db_path)` creates it, `ensure_schema()` runs DDL. The first `build_and_save_pipeline` call works without any setup. This is the same behavior as the single-tenant case — KuzuDB auto-creates.

### Edge case: tenant data isolation

Tenant A's `load_recipe("payroll_v1")` and Tenant B's `load_recipe("payroll_v1")` return different data — they query different KuzuDB directories. Recipe IDs are scoped to the tenant, not globally unique.

---

## Invariants

### Graph semantics
- All existing graph invariants hold per-tenant (double-entry balance, ontology validation, etc.)
- Recipe IDs are unique within a tenant, not globally
- No cross-tenant queries are possible — physical directory isolation

### Functional constraints
- `auth.py` functions are pure lookups against SQLite (no domain logic)
- `tenant.py` manages connection lifecycle only (no domain logic)
- All domain/persistence functions remain unchanged and tenant-unaware
- API keys are never stored in plain text — only SHA-256 hashes
- `TenantContext` replaces global state (`_loaded_recipes`, `_loaded_formats`, `_connection`) with per-tenant equivalents

### Purity boundaries
- **New functions that are pure** (no I/O, no side effects): `hash_api_key`
- **New functions that touch I/O**: `init_auth_db`, `create_tenant`, `resolve_tenant`, `deactivate_tenant` (SQLite), `get_tenant_context` (KuzuDB connection), `authenticate_request` (reads request headers + SQLite)
- **Composition approach**: Tool handlers swap `get_connection()` → `context.connection` and `get_loaded_recipes()` → `context.loaded_recipes`. No other composition changes.
- domain/ must never import from persistence/ or mcp_server/
- Pure functions (builders, summarizers) must not import from persistence/

---

## Integration

### Files modified

| File | Change |
|------|--------|
| `mcp_server/__init__.py` | Remove global `_loaded_recipes`, `_loaded_formats`, `_connection`; remove `get_connection()`, `get_loaded_recipes()`, `get_loaded_formats()`; add transport selection (`--stdio` flag); add `DATA_ROOT` and `AUTH_DB_PATH` env var reads; register shutdown hook for `close_all()` |
| `mcp_server/tools.py` | Replace `get_connection()` calls with tenant-context-scoped connection; replace `get_loaded_recipes()`/`get_loaded_formats()` with tenant-context-scoped caches |
| `mcp_server/__main__.py` | Pass CLI args through to `main()` |
| `mcp_server/CLAUDE.md` | Update architecture docs for multi-tenant, auth, HTTP transport |
| `CLAUDE.md` | Update env vars, dependency list, file map |

### Files created

| File | Why an existing file can't absorb this |
|------|----------------------------------------|
| `mcp_server/auth.py` | Auth/tenant-resolution is a distinct concern from tool handling, connection management, and domain logic. Mixing it into `__init__.py` or `tools.py` would violate single-responsibility. |
| `mcp_server/tenant.py` | Per-tenant connection pooling and state management is a distinct lifecycle concern. It replaces the global singleton pattern in `__init__.py` with something more complex that warrants its own module. |
| `mcp_server/admin.py` | CLI entry point for tenant management (create, deactivate, list, rotate-key). This is an admin interface, not an MCP tool — separate module prevents mixing admin operations with agent-facing tools. |
| `tests/mcp_server/test_auth.py` | Tests for API key hashing, tenant creation, resolution, deactivation |
| `tests/mcp_server/test_tenant.py` | Tests for TenantContext lifecycle, connection isolation, cache isolation |

### Canonical counts affected

| Constant | Before | After | Delta |
|----------|--------|-------|-------|
| `NodeLabel` | 19 | 19 | 0 |
| `RelationshipType` | 26 | 26 | 0 |
| `MERGE_KEYS` | 19 | 19 | 0 |
| MCP Tools | 6 | 6 | 0 |
| Total tests | ~410 | ~450 | ~+40 |

**Count-assertion tests:** No canonical domain counts change. The test count increase comes from new test files for auth and tenant modules.

---

## Test Strategy

### New tests

| Test file | Test class / method | What it verifies |
|-----------|-------------------|-----------------|
| `tests/mcp_server/test_auth.py` | `test_hash_api_key_deterministic` | Same input always produces same hash |
| `tests/mcp_server/test_auth.py` | `test_hash_api_key_different_inputs` | Different keys produce different hashes |
| `tests/mcp_server/test_auth.py` | `test_init_auth_db_creates_tables` | SQLite schema created on first call |
| `tests/mcp_server/test_auth.py` | `test_init_auth_db_idempotent` | Second call doesn't error |
| `tests/mcp_server/test_auth.py` | `test_create_tenant_returns_key` | Key is returned and is non-empty |
| `tests/mcp_server/test_auth.py` | `test_create_tenant_duplicate_id_errors` | Duplicate tenant_id raises error |
| `tests/mcp_server/test_auth.py` | `test_resolve_tenant_valid_key` | Valid key returns correct Tenant |
| `tests/mcp_server/test_auth.py` | `test_resolve_tenant_invalid_key` | Invalid key returns None |
| `tests/mcp_server/test_auth.py` | `test_resolve_tenant_inactive` | Inactive tenant returns None |
| `tests/mcp_server/test_auth.py` | `test_deactivate_tenant` | Tenant becomes inactive, key stops resolving |
| `tests/mcp_server/test_auth.py` | `test_multiple_keys_per_tenant` | Both keys resolve to same tenant |
| `tests/mcp_server/test_tenant.py` | `test_get_tenant_context_creates_connection` | First call opens KuzuDB at correct path |
| `tests/mcp_server/test_tenant.py` | `test_get_tenant_context_reuses_connection` | Second call returns same context |
| `tests/mcp_server/test_tenant.py` | `test_separate_tenants_separate_connections` | Two tenants get different db_paths |
| `tests/mcp_server/test_tenant.py` | `test_tenant_context_has_isolated_caches` | Tenant A's loaded_recipes is separate from Tenant B's |
| `tests/mcp_server/test_tenant.py` | `test_close_tenant_context` | Connection closed, context removed |
| `tests/mcp_server/test_tenant.py` | `test_close_all` | All connections closed |
| `tests/mcp_server/test_tenant.py` | `test_tenant_directory_auto_created` | KuzuDB directory created on first access |
| `tests/mcp_server/test_tenant.py` | `test_lru_eviction_at_max_connections` | Oldest idle context evicted when cap reached |
| `tests/mcp_server/test_tenant.py` | `test_lru_eviction_preserves_active` | Recently accessed context survives eviction |
| `tests/mcp_server/test_tenant.py` | `test_evicted_tenant_reconnects` | Evicted tenant gets fresh context on next access |
| `tests/mcp_server/test_auth.py` | `test_generate_api_key_format` | Key starts with `fpk_` and is ~47 chars |
| `tests/mcp_server/test_auth.py` | `test_generate_api_key_unique` | Two calls produce different keys |

### Existing tests

| Test file | Status | Reason |
|-----------|--------|--------|
| `tests/domain/*` (5 files) | Unchanged | No domain layer changes |
| `tests/persistence/*` (5 files) | Unchanged | No persistence layer changes |
| `tests/mcp_server/test_builders.py` | Unchanged | Pure functions, no connection dependency |
| `tests/mcp_server/test_summarizers.py` | Unchanged | Pure functions, no connection dependency |

### Expected new test count

Current (post-KuzuDB migration): ~410 | Added: ~40 | New total: ~450

---

## Success Criteria

- [ ] `pytest` passes with all ~450 tests (0 failures)
- [ ] Auth tests use `tmp_path` for SQLite — no external dependencies
- [ ] Tenant tests use `tmp_path` for KuzuDB directories — no external dependencies
- [ ] Two tenants can save and load recipes with the same `recipe_id` and get different data
- [ ] Invalid API key returns 401, not a tool error
- [ ] Deactivated tenant's API key is rejected; reactivation restores access
- [ ] `--stdio` flag preserves single-tenant local development workflow
- [ ] Admin CLI can create tenants, list tenants, deactivate tenants, rotate keys
- [ ] No plain-text API keys stored in SQLite — only hashes
- [ ] All domain and persistence tests pass without modification (zero L1-L4 changes)
- [ ] Server starts and accepts HTTP connections on Railway with `PORT` env var

---

## Out of Scope

- Rate limiting / request throttling — deferred until usage patterns are observed
- Role-based access control within a tenant (read-only vs read-write keys) — deferred
- Tenant usage metrics / billing integration — deferred
- Tenant data export / migration tooling — deferred
- OAuth / SSO integration — API keys are sufficient for machine-to-machine MCP access
- Horizontal scaling / multiple server instances — single-process embedded KuzuDB precludes this; would require a future architecture change
- Automatic tenant provisioning via MCP tool — admin CLI only for now
- TLS termination — handled by Railway's proxy, not by the application

---

## Open Questions

All resolved — see findings below.

- [x] **FastMCP per-request context in HTTP mode.** FastMCP's Streamable HTTP and SSE transports pass a Starlette `Request` object through `RequestContext`, accessible in tool handlers via `ctx.request_context.request`. FastMCP also ships its own `AuthContextMiddleware` using Python's `contextvars` module (`mcp.server.auth.middleware.auth_context`). **Decision: Use the `contextvars` middleware pattern (Option A).** A custom Starlette middleware reads the `Authorization: Bearer <key>` header, calls `resolve_tenant()`, and sets a `contextvars.ContextVar[TenantContext]`. Tool handlers call `tenant_var.get()` — no auth logic in tool code. This matches FastMCP's own internal auth pattern.

  ```python
  # mcp_server/tenant.py
  import contextvars
  tenant_var: contextvars.ContextVar[TenantContext] = contextvars.ContextVar("tenant_context")

  # Middleware sets it:
  token = tenant_var.set(context)

  # Tool handlers read it:
  ctx = tenant_var.get()
  conn = ctx.connection
  ```

- [x] **Connection pool limits.** Each `kuzu.Database` object allocates its own buffer pool (default: ~80% of system RAM) and reserves `max_db_size` virtual address space (default: 8 TB mmap). Multiple databases in one process are supported but memory is additive. The `Connection` object itself is lightweight (a handle to shared Database internals). **Decision: LRU eviction with configurable max and explicit buffer pool sizing.** Set `buffer_pool_size` to 64 MB per tenant database. Cap max open databases via `MAX_TENANT_CONNECTIONS` env var (default: 20). Evict least-recently-used idle tenant contexts when the cap is hit (close database, remove from `_contexts`). At 20 tenants x 64 MB = ~1.3 GB buffer pool ceiling, well within Railway's typical container sizes.

  ```python
  # mcp_server/tenant.py
  MAX_CONNECTIONS = int(os.environ.get("MAX_TENANT_CONNECTIONS", "20"))
  BUFFER_POOL_SIZE = int(os.environ.get("KUZU_BUFFER_POOL_MB", "64")) * 1024 * 1024

  # In KuzuConnection init:
  db = kuzu.Database(db_path, buffer_pool_size=BUFFER_POOL_SIZE)
  ```

- [x] **Admin CLI authentication.** **Decision: Direct filesystem access, no auth needed (Option A).** The admin CLI (`python -m mcp_server.admin`) operates directly on `auth.db` via filesystem access. If you can access the server's filesystem (SSH, Railway shell, CI/CD), you can manage tenants. This is the standard pattern for embedded database admin tools — filesystem access *is* the authentication. No separate admin API key or env var secret required.

- [x] **Key format and prefix.** **Decision: `fpk_` prefix + 32 bytes of `secrets.token_urlsafe`.** This produces keys like `fpk_7Kx9mPq2RtL5nW8vB3jF6hY0cA4eD1gIzXw...` (~47 characters total). The prefix makes keys identifiable in logs, config files, and env vars without revealing their content. 32 bytes provides 256 bits of entropy — more than sufficient for API key security. Keys are hashed with SHA-256 before storage; the plain key is returned exactly once at creation time.

  ```python
  def generate_api_key() -> str:
      return f"fpk_{secrets.token_urlsafe(32)}"
  ```