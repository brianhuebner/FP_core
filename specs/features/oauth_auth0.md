# Spec: OAuth 2.1 Authentication via Auth0

> **Status:** Draft
> **Created:** 2026-02-26
> **Spec type:** Feature
> **Depends on:** `specs/features/remote_mcp_server.md` (Streamable HTTP transport, implemented)

---

## Purpose

Enable Claude Desktop (and claude.ai) to connect to the remote FP_core MCP server on Railway. Claude Desktop does not support bearer-token auth — it requires the full OAuth 2.1 flow with discovery endpoints, PKCE, and dynamic client registration. This spec adds Auth0 as the external authorization server and implements a `TokenVerifier` in FP_core to validate Auth0-issued JWTs.

The existing `BearerTokenMiddleware` (simple shared-secret auth) is replaced by FastMCP's built-in OAuth middleware, which handles bearer extraction, token verification, scope enforcement, and RFC 9728 protected resource metadata — all wired through the `token_verifier` + `auth` constructor params.

**Target:** Claude Desktop connects to `https://fpcore-production.up.railway.app/mcp` via Settings > Connectors, completes the Auth0 OAuth flow, and calls all 6 MCP tools.

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
| L5 MCP Server | `mcp_server/` | Replace `BearerTokenMiddleware` with FastMCP-native OAuth via `token_verifier` + `AuthSettings`; new `Auth0TokenVerifier` class |

---

## Domain Types (L1)

No Layer 1 changes required. Authentication is an infrastructure concern with no domain model impact.

---

## Schema Definitions (L2)

No Layer 2 changes required.

---

## Pure Functions (L3)

No Layer 3 changes required.

---

## Persistence Contract (L4)

No Layer 4 changes required.

---

## MCP Interface (L5)

### Tool signatures affected

None. All 6 tool signatures remain identical. Auth is below the tool layer.

### Auth architecture change

**Before:** Custom `BearerTokenMiddleware` (Starlette middleware) checks `MCP_AUTH_TOKEN` shared secret.

**After:** FastMCP's built-in OAuth support via constructor params:

```python
from mcp.server.auth.provider import TokenVerifier, AccessToken
from mcp.server.auth.settings import AuthSettings

mcp = FastMCP(
    "FP_core",
    host=_host,
    port=_port,
    token_verifier=Auth0TokenVerifier(
        domain=os.environ["AUTH0_DOMAIN"],
        audience=os.environ["AUTH0_AUDIENCE"],
    ),
    auth=AuthSettings(
        issuer_url=f"https://{os.environ['AUTH0_DOMAIN']}",
        resource_server_url=os.environ.get("MCP_RESOURCE_URL", f"http://localhost:{_port}/mcp"),
    ),
)
```

### `mcp_server/auth.py` — rewritten

Replace `BearerTokenMiddleware` with `Auth0TokenVerifier`:

```python
class Auth0TokenVerifier:
    """Verify Auth0-issued JWTs against the tenant's JWKS."""

    def __init__(self, domain: str, audience: str):
        self.domain = domain
        self.audience = audience
        self.jwks_url = f"https://{domain}/.well-known/jwks.json"
        self._jwks_client = jwt.PyJWKClient(self.jwks_url, cache_keys=True)

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=f"https://{self.domain}/",
            )
            return AccessToken(
                token=token,
                client_id=payload.get("azp", payload.get("sub", "")),
                scopes=payload.get("scope", "").split(),
                expires_at=payload.get("exp"),
            )
        except (jwt.PyJWTError, Exception):
            return None
```

### `mcp_server/__init__.py` — changes

The `main()` function simplifies. When Auth0 env vars are set and transport is HTTP, FastMCP handles everything — no manual middleware wiring:

```python
# Auth configuration (only for HTTP transport)
_auth0_domain = os.environ.get("AUTH0_DOMAIN")
_auth0_audience = os.environ.get("AUTH0_AUDIENCE")

if _transport in ("streamable-http", "http") and _auth0_domain and _auth0_audience:
    from mcp_server.auth import Auth0TokenVerifier
    from mcp.server.auth.settings import AuthSettings

    _token_verifier = Auth0TokenVerifier(domain=_auth0_domain, audience=_auth0_audience)
    _resource_url = os.environ.get("MCP_RESOURCE_URL", f"http://localhost:{_port}/mcp")
    _auth_settings = AuthSettings(
        issuer_url=f"https://{_auth0_domain}",
        resource_server_url=_resource_url,
    )
else:
    _token_verifier = None
    _auth_settings = None

mcp = FastMCP("FP_core", host=_host, port=_port,
              token_verifier=_token_verifier, auth=_auth_settings)
```

The `main()` function simplifies — no more manual middleware branching:

```python
def main():
    if _transport in ("streamable-http", "http"):
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")
```

### Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `MCP_TRANSPORT` | `stdio` | Transport mode (unchanged) |
| `MCP_HOST` | `0.0.0.0` | Bind address (unchanged) |
| `MCP_PORT` | `8000` | Listen port (unchanged) |
| `AUTH0_DOMAIN` | *(none)* | Auth0 tenant domain, e.g. `your-tenant.us.auth0.com` |
| `AUTH0_AUDIENCE` | *(none)* | Auth0 API identifier, e.g. `https://fpcore-production.up.railway.app/mcp` |
| `MCP_RESOURCE_URL` | *(derived)* | Public URL of MCP server for RFC 9728 metadata |
| `MCP_AUTH_TOKEN` | *(removed)* | **Removed** — replaced by Auth0 OAuth |
| `NEO4J_URI` | *(required)* | Neo4j Aura endpoint (unchanged) |
| `NEO4J_USER` | `neo4j` | Neo4j username (unchanged) |
| `NEO4J_PASSWORD` | *(required)* | Neo4j password (unchanged) |

### Auto-generated endpoints (by FastMCP)

When `token_verifier` + `auth` are set, FastMCP automatically generates:

| Endpoint | Purpose |
|----------|---------|
| `GET /.well-known/oauth-protected-resource/mcp` | RFC 9728 metadata — tells Claude Desktop where the Auth0 authorization server is |
| `POST /mcp` | MCP requests — requires valid bearer token |

Claude Desktop reads the protected resource metadata, discovers Auth0 as the authorization server, performs OAuth 2.1 flow (PKCE + DCR), obtains an access token, and uses it for all subsequent MCP calls.

### JSON spec format

No changes. Pipeline specs and format specs are unaffected.

### Summarizer output

No changes.

---

## Data Flow

```
Claude Desktop
    |
    | 1. GET /.well-known/oauth-protected-resource/mcp
    |    → {"authorization_servers": ["https://your-tenant.us.auth0.com"], ...}
    |
    | 2. GET https://your-tenant.us.auth0.com/.well-known/openid-configuration
    |    → Auth0 discovery document (endpoints, PKCE support, DCR)
    |
    | 3. POST https://your-tenant.us.auth0.com/oidc/register  (Dynamic Client Registration)
    |    → {client_id: "auto-generated"}
    |
    | 4. Redirect user to Auth0 /authorize (with PKCE challenge)
    |    → User logs in / consents
    |
    | 5. POST https://your-tenant.us.auth0.com/oauth/token (code + PKCE verifier)
    |    → {access_token: "eyJ...", token_type: "Bearer"}
    |
    | 6. POST /mcp (Authorization: Bearer eyJ...)
    |    → FastMCP validates JWT via Auth0TokenVerifier
    |    → Tool call executed, response returned
    v
FP_core MCP Server (Railway)
    |
    v
Neo4j Aura (unchanged)
```

---

## Examples

### Happy path: Claude Desktop connection

1. User opens Claude Desktop → Settings → Connectors → Add
2. Enters URL: `https://fpcore-production.up.railway.app/mcp`
3. Claude Desktop discovers Auth0 via `/.well-known/oauth-protected-resource/mcp`
4. Auth0 login page appears, user authenticates
5. Claude Desktop obtains JWT, attaches to all requests
6. All 6 MCP tools work identically to STDIO mode

### Happy path: Claude Code (unchanged)

Claude Code supports streamable-http natively. With Auth0 OAuth, configure:

```json
{
  "mcpServers": {
    "fp_core": {
      "type": "streamable-http",
      "url": "https://fpcore-production.up.railway.app/mcp"
    }
  }
}
```

Claude Code will perform the OAuth flow automatically when it encounters the 401 + protected resource metadata.

### Happy path: STDIO mode (unchanged)

```bash
python -m mcp_server
# No auth env vars set → no auth middleware → STDIO as before
```

### Edge case: AUTH0_DOMAIN not set, HTTP transport

Server starts without auth — open access. Same as current behavior when `MCP_AUTH_TOKEN` is unset. Suitable for localhost or VPN.

### Edge case: expired JWT

`Auth0TokenVerifier.verify_token()` returns `None` → FastMCP returns 401 with `WWW-Authenticate` header → Claude Desktop refreshes the token automatically.

---

## Auth0 Tenant Configuration

### 1. Create Auth0 API

In Auth0 Dashboard → Applications → APIs → Create API:

| Setting | Value |
|---------|-------|
| Name | `FP_core MCP Server` |
| Identifier (Audience) | `https://fpcore-production.up.railway.app/mcp` |
| Signing Algorithm | RS256 |

### 2. Enable Dynamic Client Registration

Dashboard → Settings → Advanced → Enable "OIDC Dynamic Application Registration"

This allows Claude Desktop to auto-register as a client at `https://{domain}/oidc/register`.

### 3. Auth0 OAuth Discovery

Auth0 automatically serves:
- `GET https://{domain}/.well-known/openid-configuration` — discovery document with all endpoints
- `GET https://{domain}/.well-known/jwks.json` — public keys for JWT verification

No additional Auth0 configuration needed — these are automatic for every tenant.

### 4. Callback URL

Claude Desktop uses callback URL: `https://claude.ai/api/mcp/auth_callback`
(Also allowlist `https://claude.com/api/mcp/auth_callback` for future compatibility)

Add both to Auth0 Application → Allowed Callback URLs.

---

## Invariants

### Functional constraints
- `MCP_TRANSPORT=stdio` (or unset) produces identical behavior to today — no auth
- All 6 MCP tools return identical JSON responses regardless of auth mode
- Server-side state (`_loaded_recipes`, `_loaded_formats`) works identically
- Neo4j connection is lazy-initialized on first tool call, same as today

### Purity boundaries
- **New functions that are pure:** None
- **New functions that touch I/O:** `Auth0TokenVerifier.verify_token()` — fetches JWKS from Auth0 (cached by PyJWKClient)
- `domain/` must never import from `persistence/` or `mcp_server/`
- Pure functions (builders, summarizers) must not import from `persistence/`

### Security constraints
- JWTs are verified against Auth0's JWKS (RS256 asymmetric keys — no shared secret)
- Token audience is checked — tokens for other APIs are rejected
- Token issuer is checked — tokens from other Auth0 tenants are rejected
- Expired tokens are rejected (FastMCP checks `expires_at`)

---

## Integration

### Files modified

| File | Change |
|------|--------|
| `mcp_server/__init__.py` | Replace manual middleware wiring with `token_verifier` + `auth` constructor params; read `AUTH0_DOMAIN`, `AUTH0_AUDIENCE`, `MCP_RESOURCE_URL` env vars; simplify `main()` |
| `mcp_server/auth.py` | Replace `BearerTokenMiddleware` with `Auth0TokenVerifier` (JWT verification via PyJWKClient) |
| `mcp_server/CLAUDE.md` | Update auth docs to document OAuth mode |
| `CLAUDE.md` | Update env vars, note OAuth support |
| `requirements.txt` | Add `PyJWT[crypto]` dependency |

### Files created

None. Existing files absorb all changes.

### Canonical counts affected

No canonical count changes. No new NodeLabels, RelationshipTypes, tools, ontology entries, or merge keys.

| Constant | Before | After | Delta |
|----------|--------|-------|-------|
| MCP Tools | 6 | 6 | 0 |
| Total tests | 408 | ~416 | ~+8 |

---

## Test Strategy

### New tests

| Test file | Test class / method | What it verifies |
|-----------|-------------------|-----------------|
| `tests/mcp_server/test_auth.py` | `TestAuth0TokenVerifier::test_valid_jwt_returns_access_token` | Valid JWT with correct audience/issuer returns AccessToken |
| `tests/mcp_server/test_auth.py` | `TestAuth0TokenVerifier::test_expired_jwt_returns_none` | Expired JWT returns None |
| `tests/mcp_server/test_auth.py` | `TestAuth0TokenVerifier::test_wrong_audience_returns_none` | JWT with wrong audience returns None |
| `tests/mcp_server/test_auth.py` | `TestAuth0TokenVerifier::test_wrong_issuer_returns_none` | JWT with wrong issuer returns None |
| `tests/mcp_server/test_auth.py` | `TestAuth0TokenVerifier::test_malformed_token_returns_none` | Non-JWT string returns None |
| `tests/mcp_server/test_transport.py` | `test_auth0_env_vars_configure_oauth` | AUTH0_DOMAIN + AUTH0_AUDIENCE → FastMCP gets token_verifier + auth |
| `tests/mcp_server/test_transport.py` | `test_no_auth0_env_vars_no_oauth` | No AUTH0 vars → FastMCP has no token_verifier |
| `tests/mcp_server/test_transport.py` | `test_stdio_ignores_auth0_vars` | STDIO transport → no auth regardless of AUTH0 vars |

### Existing tests

| Test file | Status | Reason |
|-----------|--------|--------|
| `tests/mcp_server/test_auth.py` (current 4 tests) | **Replaced** | `BearerTokenMiddleware` tests replaced by `Auth0TokenVerifier` tests |
| `tests/mcp_server/test_transport.py` (current 6 tests) | **Updated** | Transport tests updated to reflect new auth wiring |
| `tests/domain/*` (5 files) | Unchanged | No domain changes |
| `tests/mcp_server/test_builders.py` | Unchanged | Pure functions |
| `tests/mcp_server/test_summarizers.py` | Unchanged | Pure functions |
| `tests/persistence/*` (4 files) | Unchanged | No persistence changes |

### Dependencies for testing

JWT tests use `PyJWT` to generate test tokens signed with a test RSA key. No Auth0 network calls — the JWKS endpoint is mocked.

### Expected new test count

Current: 408 | Replaced: 4 bearer tests | Added: ~8 | Net change: ~+4 | New total: ~412

---

## Success Criteria

- [ ] `python -m mcp_server` with no auth env vars starts in STDIO mode (backward compatible)
- [ ] `MCP_TRANSPORT=streamable-http` with `AUTH0_DOMAIN` + `AUTH0_AUDIENCE` starts with OAuth protection
- [ ] `GET /.well-known/oauth-protected-resource/mcp` returns RFC 9728 metadata pointing to Auth0
- [ ] Valid Auth0 JWT grants access to all 6 MCP tools
- [ ] Invalid/expired/wrong-audience JWT gets 401
- [ ] Claude Desktop connects via Settings > Connectors, completes Auth0 login, calls tools
- [ ] `MCP_TRANSPORT=streamable-http` without `AUTH0_DOMAIN` starts without auth (open access)
- [ ] STDIO mode ignores all auth env vars
- [ ] All existing tests pass (no regressions)
- [ ] New auth + transport tests pass

---

## Out of Scope

- **Full `OAuthAuthorizationServerProvider`** — we use Auth0 as the AS, not self-hosted
- **Multi-tenancy** — all authenticated users share the same Neo4j instance
- **Per-user scopes / RBAC** — all authenticated users get full access to all 6 tools
- **Token refresh logic** — handled by Claude Desktop / Claude Code client-side
- **Auth0 dashboard automation** — tenant setup is manual (documented above)
- **Rate limiting** — can be added via Starlette middleware later
- **`MCP_AUTH_TOKEN` backward compatibility** — simple bearer token auth is removed in favor of OAuth

---

## Open Questions

- [ ] **Auth0 plan:** Free tier supports up to 25,000 monthly active users and unlimited machine-to-machine tokens. Sufficient for single-user/small-team. Verify DCR is available on free tier. (Resolve during Auth0 setup.)
- [ ] **MCP spec version:** Claude Desktop supports both 2025-03-26 and 2025-06-18 authorization specs. The 06-18 spec has stricter requirements (HEAD method on root path, explicit session management). Verify which version our FastMCP SDK implements. (Resolve during implementation.)
- [ ] **Scopes:** Should we define custom scopes (e.g., `fp_core:read`, `fp_core:write`) or leave `required_scopes` as None (any valid Auth0 token gets access)? For single-user, None is simpler. (Decide before implementation.)