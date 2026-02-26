# Spec: Remote MCP Server (Streamable HTTP Transport)

> **Status:** Draft
> **Created:** 2026-02-25
> **Spec type:** Feature
> **Supersedes:** `specs/features/neo4j_to_kuzudb_migration.md` (KuzuDB acquired by Apple Oct 2025; repo archived; migration path closed)

---

## Purpose

Make the FP_core MCP server accessible from any machine over the network. Today the server runs over STDIO transport, meaning the client must be a local subprocess on the same machine. Switching to Streamable HTTP transport lets any MCP client — Claude Code on a laptop, a CI agent, a colleague's workstation — connect to a single hosted FP_core instance backed by a shared Neo4j database.

This is the smallest change that unlocks remote access. Neo4j is already managed on Aura — no database infrastructure work needed. Layers 1-4 are untouched. The only moving part is the transport and startup configuration in Layer 5.

**Target deployment platform:** Railway.app (Hobby or Pro plan), connecting to the existing Neo4j Aura instance.

---

## Layer Placement

**Primary layer:** L5 — MCP Server
**Layers touched:**

| Layer | Package | What changes |
|-------|---------|--------------|
| L1 Types | `domain/types.py`, `types_recipe.py` | No changes |
| L2 Ontology | `domain/ontology.py`, `ontology_recipe.py` | No changes |
| L3 Logic | `domain/logic.py` | No changes |
| L4 Persistence | `persistence/` | No changes |
| L5 MCP Server | `mcp_server/` | Transport selection in `__init__.py` and `__main__.py`; optional bearer-token auth middleware |

---

## Domain Types (L1)

No Layer 1 changes required. Transport is an infrastructure concern with no domain model impact.

---

## Schema Definitions (L2)

No Layer 2 changes required. Validators, ontology, and constraints are unaffected.

---

## Pure Functions (L3)

No Layer 3 changes required. Builders, extractors, and validators are pure functions with no transport dependency.

---

## Persistence Contract (L4)

No Layer 4 changes required. Neo4j Aura is the existing managed database — no migration, no new infrastructure. `Neo4jConnection` is unchanged. The MCP server still calls `save_pattern`, `load_pattern_by_recipe`, etc. exactly as before. The `NEO4J_URI` (Aura bolt+s:// endpoint) and `NEO4J_PASSWORD` are set as Railway service variables pointing to the existing Aura instance.

---

## MCP Interface (L5)

### Tool signatures affected

None. All 6 tool signatures (`load_recipe`, `load_format`, `get_processing_instructions`, `build_and_save_pipeline`, `build_output`, `validate_entries`) remain identical. Transport is below the tool layer.

### Transport change

The MCP spec (revision 2025-03-26) defines two standard transports: **stdio** and **Streamable HTTP**. SSE is deprecated. Streamable HTTP is the recommended transport for any network-accessible MCP server:

- Single endpoint (`/mcp`) handles both POST (client→server) and GET (server→client SSE streaming)
- Works behind standard load balancers (no sticky sessions required in stateless mode)
- Native HTTP middleware for auth, CORS, rate limiting

### `mcp_server/__init__.py` changes

The `main()` function becomes transport-aware via environment variables:

```python
def main():
    """Run the MCP server. Transport selected by MCP_TRANSPORT env var."""
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    logger.info("Starting FP_core MCP server (transport=%s)", transport)

    if transport in ("streamable-http", "http"):
        host = os.environ.get("MCP_HOST", "0.0.0.0")
        port = int(os.environ.get("MCP_PORT", "8000"))
        mcp.run(transport="streamable-http", host=host, port=port)
    else:
        mcp.run(transport="stdio")
```

### `mcp_server/__main__.py` changes

No structural change — it still calls `main()`. The transport is determined by env vars, not by `__main__.py`.

### Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `MCP_TRANSPORT` | `stdio` | Transport mode: `stdio` or `streamable-http` |
| `MCP_HOST` | `0.0.0.0` | Bind address for HTTP transport |
| `MCP_PORT` | `8000` | Listen port for HTTP transport |
| `MCP_AUTH_TOKEN` | *(none)* | If set, enables bearer-token auth on HTTP transport |
| `NEO4J_URI` | *(required)* | Neo4j Aura bolt+s:// endpoint (existing instance) |
| `NEO4J_USER` | `neo4j` | Neo4j Aura username |
| `NEO4J_PASSWORD` | *(required)* | Neo4j Aura password |

### Auth middleware (optional, bearer token)

When `MCP_AUTH_TOKEN` is set and transport is HTTP, a simple bearer-token check rejects unauthenticated requests. This is the minimal viable auth — not a full OAuth flow, but sufficient for a single-user or small-team deployment behind a VPN or SSH tunnel.

```python
# mcp_server/auth.py — bearer token middleware

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class BearerTokenMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, token: str):
        super().__init__(app)
        self.token = token

    async def dispatch(self, request: Request, call_next):
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer ") or auth.removeprefix("Bearer ").strip() != self.token:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return await call_next(request)
```

Integration in `__init__.py`:

```python
if transport in ("streamable-http", "http"):
    auth_token = os.environ.get("MCP_AUTH_TOKEN")
    if auth_token:
        app = mcp.streamable_http_app()
        app.add_middleware(BearerTokenMiddleware, token=auth_token)
        import uvicorn
        uvicorn.run(app, host=host, port=port)
    else:
        mcp.run(transport="streamable-http", host=host, port=port)
```

### JSON spec format

No changes. Pipeline specs and format specs are consumed by builders, not by transport.

### Summarizer output

No changes. Summarizers produce JSON dicts regardless of transport.

---

## Data Flow

```
MCP Client (Claude Code, agent, etc.)
    |
    | HTTP POST → /mcp  (Streamable HTTP)
    | — OR —
    | stdin/stdout       (STDIO, unchanged)
    |
    v
FastMCP transport layer (handles framing, sessions)
    |
    v
mcp_server/tools.py — tool handlers (UNCHANGED)
    |
    v
domain/ + persistence/ — business logic + Neo4j (UNCHANGED)
    |
    v
FastMCP transport layer (response framing)
    |
    v
MCP Client (receives JSON response)
```

---

## Examples

### Happy path: local stdio (unchanged)

```bash
# Current behavior — nothing changes
python -m mcp_server
# Server reads from stdin, writes to stdout
```

### Happy path: remote HTTP server (local)

```bash
# Start server with HTTP transport, pointing to Aura
export NEO4J_URI=neo4j+s://xxxxx.databases.neo4j.io
export NEO4J_PASSWORD=aura-password
export MCP_TRANSPORT=streamable-http
export MCP_PORT=8000

python -m mcp_server
# Server listening on http://0.0.0.0:8000/mcp
```

### Happy path: Railway deployment

All env vars set in Railway dashboard. Railway runs `python -m mcp_server`. Server binds to `$PORT`, gets a public HTTPS URL automatically. Client connects to `https://fp-core-production.up.railway.app/mcp` with bearer token.

### Happy path: HTTP with auth

```bash
export MCP_TRANSPORT=streamable-http
export MCP_AUTH_TOKEN=my-secret-token
export MCP_PORT=8000

python -m mcp_server
# Clients must send: Authorization: Bearer my-secret-token
```

### Client configuration (Claude Code)

```json
{
  "mcpServers": {
    "fp_core": {
      "type": "streamable-http",
      "url": "https://fp-core-production.up.railway.app/mcp",
      "headers": {
        "Authorization": "Bearer my-secret-token"
      }
    }
  }
}
```

### Edge case: no MCP_TRANSPORT set

Falls back to `stdio` — identical to current behavior. Zero breaking changes.

### Edge case: MCP_AUTH_TOKEN set but transport is stdio

Auth token is ignored. Bearer auth only applies to HTTP transport. No error, no warning — stdio doesn't have HTTP headers.

---

## Invariants

### Functional constraints
- `MCP_TRANSPORT=stdio` (or unset) produces identical behavior to today's server
- All 6 MCP tools return identical JSON responses regardless of transport
- Server-side state (`_loaded_recipes`, `_loaded_formats`) works identically in both modes
- Neo4j connection is lazy-initialized on first tool call, same as today

### Purity boundaries
- **New functions that are pure:** None
- **New functions that touch I/O:** `BearerTokenMiddleware.dispatch()` (HTTP middleware — Starlette/ASGI boundary)
- `domain/` must never import from `persistence/` or `mcp_server/`
- Pure functions (builders, summarizers) must not import from `persistence/`

### Security constraints
- When `MCP_AUTH_TOKEN` is set and transport is HTTP, every request without a valid bearer token gets a 401
- When `MCP_AUTH_TOKEN` is not set, the server is open (suitable for localhost, VPN, or SSH-tunnel deployments)
- The token is a shared secret, not a JWT — no expiration, no scopes. Appropriate for single-user/small-team; full OAuth is out of scope

---

## Integration

### Files modified

| File | Change |
|------|--------|
| `mcp_server/__init__.py` | `main()` reads `MCP_TRANSPORT`, `MCP_HOST`, `MCP_PORT`, `MCP_AUTH_TOKEN`; conditionally starts HTTP or stdio transport; wires auth middleware when token is set |
| `mcp_server/CLAUDE.md` | Update "runs over STDIO transport" to document both transport modes |
| `CLAUDE.md` | Add env vars to Commands section; note HTTP transport in project overview |

### Files created

| File | Why an existing file can't absorb this |
|------|----------------------------------------|
| `mcp_server/auth.py` | Starlette middleware class — separate from tool handlers and server init to keep concerns isolated. Only created if auth is in scope (see Open Questions). |

### Canonical counts affected

No canonical count changes. No new NodeLabels, RelationshipTypes, tools, ontology entries, or merge keys.

| Constant | Before | After | Delta |
|----------|--------|-------|-------|
| MCP Tools | 6 | 6 | 0 |
| Total tests | 394 | ~400 | ~+6 |

---

## Test Strategy

### New tests

| Test file | Test class / method | What it verifies |
|-----------|-------------------|-----------------|
| `tests/mcp_server/test_transport.py` | `test_default_transport_is_stdio` | `MCP_TRANSPORT` unset → `main()` calls `mcp.run(transport="stdio")` |
| `tests/mcp_server/test_transport.py` | `test_http_transport_selection` | `MCP_TRANSPORT=streamable-http` → `main()` calls `mcp.run(transport="streamable-http", ...)` |
| `tests/mcp_server/test_transport.py` | `test_host_and_port_from_env` | `MCP_HOST` and `MCP_PORT` env vars are passed through |
| `tests/mcp_server/test_transport.py` | `test_default_host_and_port` | Defaults to `0.0.0.0:8000` when env vars not set |
| `tests/mcp_server/test_auth.py` | `test_bearer_token_valid` | Request with correct token passes through middleware |
| `tests/mcp_server/test_auth.py` | `test_bearer_token_missing_or_invalid` | Request without token or wrong token gets 401 |

### Existing tests

| Test file | Status | Reason |
|-----------|--------|--------|
| `tests/domain/*` (5 files) | Unchanged | No domain changes |
| `tests/mcp_server/test_builders.py` | Unchanged | Pure functions, no transport dependency |
| `tests/mcp_server/test_summarizers.py` | Unchanged | Pure functions, no transport dependency |
| `tests/persistence/*` (4 files) | Unchanged | No persistence changes |

### Expected new test count

Current: 394 | Added: ~6 | New total: ~400

---

## Deployment: Railway.app

### Infrastructure Overview

```
┌──────────────────────────┐         ┌──────────────────────────┐
│     Railway (Hobby)      │         │     Neo4j Aura           │
│                          │  bolt+s │     (existing)           │
│  FP_core MCP Server      │────────►│                          │
│  Python 3.12 + Uvicorn   │         │  Graph database          │
│  Streamable HTTP on $PORT│         │  Managed, always-on      │
│                          │         │                          │
└────────┬─────────────────┘         └──────────────────────────┘
         │
         │ HTTPS (auto TLS)
         │ *.up.railway.app
         │
    ┌────┴─────┐
    │ MCP      │
    │ Clients  │
    │ anywhere │
    └──────────┘
```

**Why this works:**
- Neo4j is already on Aura — no database to host, no volumes, no memory headroom needed on Railway
- Railway only runs the Python MCP server — lightweight, ~128MB RAM
- Railway auto-provisions HTTPS with Let's Encrypt on a `*.up.railway.app` domain
- Streamable HTTP uses standard request/response — no issues with Railway's 60-second idle connection timeout (which kills idle SSE streams, but doesn't affect POST-based Streamable HTTP)

### Railway Service Configuration

**Build:** Railpack auto-detects Python from `requirements.txt`. No Dockerfile needed unless pinning specific system deps.

**Start command:**
```
python -m mcp_server
```

**Railway service variables (set in dashboard):**

| Variable | Value | Notes |
|----------|-------|-------|
| `MCP_TRANSPORT` | `streamable-http` | Selects HTTP transport |
| `MCP_HOST` | `0.0.0.0` | Bind all interfaces (required for Railway) |
| `MCP_PORT` | `${{PORT}}` | Railway reference variable — injects the assigned port |
| `MCP_AUTH_TOKEN` | *(generate a secret)* | Bearer token for client auth |
| `NEO4J_URI` | `neo4j+s://xxxxx.databases.neo4j.io` | Existing Aura bolt endpoint |
| `NEO4J_USER` | `neo4j` | Aura default |
| `NEO4J_PASSWORD` | *(Aura password)* | Use Railway sealed variable |

**Important:** Railway injects `PORT` dynamically. The server must bind to `$PORT`, not a hardcoded port. The `MCP_PORT` variable should reference Railway's `PORT` using the `${{PORT}}` template syntax, or the `__init__.py` code should read `PORT` as a fallback:

```python
port = int(os.environ.get("MCP_PORT", os.environ.get("PORT", "8000")))
```

### `requirements.txt` additions

```
mcp[cli]>=1.0
neo4j>=5.0
python-dotenv
uvicorn
```

Verify whether `mcp[cli]` already bundles `uvicorn` and `starlette`. If so, explicit `uvicorn` is redundant but harmless.

### Client Configuration

Once deployed, Railway provides a public URL like `https://fp-core-production.up.railway.app`. Configure MCP clients to connect:

```json
{
  "mcpServers": {
    "fp_core": {
      "type": "streamable-http",
      "url": "https://fp-core-production.up.railway.app/mcp",
      "headers": {
        "Authorization": "Bearer <your-MCP_AUTH_TOKEN>"
      }
    }
  }
}
```

### Railway Plan Recommendation

**Hobby plan ($5/month)** is sufficient. The MCP server is a lightweight Python process:
- No database hosting on Railway (Neo4j is on Aura)
- No persistent volumes needed
- Low memory footprint (~128MB)
- Intermittent usage — Railway charges by resource consumption, not reserved capacity
- $5/month included credit covers a low-traffic MCP server comfortably

Pro plan ($20/month) is only needed if traffic grows or you want multiple services.

### Alternative Deployment Options

For reference, other deployment paths that also work with this spec:

| Method | When to use |
|--------|-------------|
| **SSH tunnel** | Quick remote access from one machine; no deployment needed; `ssh -L 8000:localhost:8000 server` |
| **VPN / LAN** | Server on local network; set `MCP_AUTH_TOKEN` as shared secret; no TLS needed |
| **Cloudflare Tunnel** | Free, exposes a local server to the internet with TLS; no cloud hosting needed |
| **Any PaaS** | Render, Fly.io, Google Cloud Run — same env vars, same `python -m mcp_server` entry point |

---

## Success Criteria

- [ ] `python -m mcp_server` with no env vars starts in stdio mode (backward compatible)
- [ ] `MCP_TRANSPORT=streamable-http python -m mcp_server` starts an HTTP server on `0.0.0.0:$PORT`
- [ ] Server reads `PORT` env var (Railway-injected) with fallback to `MCP_PORT` or `8000`
- [ ] An MCP client can connect over HTTP and call all 6 tools with identical results to stdio
- [ ] `MCP_AUTH_TOKEN` set → unauthenticated requests get 401
- [ ] `MCP_AUTH_TOKEN` unset → server is open (no auth check)
- [ ] Deployed on Railway, connecting to existing Neo4j Aura instance, accessible via HTTPS
- [ ] All existing 394 tests pass without modification
- [ ] New transport and auth tests pass (~6 new tests)

---

## Out of Scope

- **KuzuDB migration** — superseded; KuzuDB acquired by Apple, repo archived Oct 2025
- **Neo4j hosting / migration** — Neo4j is already managed on Aura; no database infrastructure work in this spec
- **Full OAuth 2.1 / OIDC** — bearer token is sufficient for single-user/small-team; OAuth deferred to multi-tenancy phase
- **TLS termination** — Railway handles this automatically via `*.up.railway.app` domains
- **Multi-tenancy** — all clients share the same Neo4j Aura instance and server-side state; per-tenant isolation deferred
- **Horizontal scaling** — single-process server; stateless HTTP mode noted for future scaling but not required now
- **Rate limiting** — can be added via Starlette middleware later if needed
- **CI/CD pipeline** — Railway auto-deploys from GitHub on push; no custom pipeline needed initially
- **Client configuration management** — documenting how to configure specific MCP clients (Claude Code, Cursor, etc.) is outside this spec; examples provided for guidance only

---

## Open Questions

- [ ] **Auth scope:** Should bearer-token auth (`mcp_server/auth.py`) be included in this initial implementation, or deferred? It's ~20 lines of code. Since Railway exposes a public HTTPS URL, bearer auth is recommended even for single-user use — without it, anyone who discovers the URL can call all 6 MCP tools against your Aura database. (Decide before implementation.)
- [ ] **Dependency:** Streamable HTTP transport requires `uvicorn` (ASGI server). FastMCP may bundle it, or it may need to be added to dependencies. Verify with `pip install mcp[cli]` and check if `uvicorn` is included. (Resolve during implementation.)
- [ ] **Railway plan:** Hobby ($5/mo) vs Pro ($20/mo). Hobby is likely sufficient since Neo4j is on Aura and the MCP server is lightweight. Monitor memory usage after initial deployment. (Decide at deploy time.)