# Spec: Auth0 Next Steps — MVP to Multi-Tenant

> **Status:** Draft
> **Created:** 2026-02-26
> **Spec type:** Feature (roadmap)
> **Depends on:** `specs/features/oauth_auth0.md` (implemented), `specs/features/multi_tenant_auth.md` (future)

---

## Current State

OAuth 2.1 via Auth0 is deployed on Railway. The server-side implementation is complete:

- `Auth0TokenVerifier` validates RS256 JWTs against Auth0's JWKS
- FastMCP serves RFC 9728 protected resource metadata at `/.well-known/oauth-protected-resource/mcp`
- Claude Desktop discovers Auth0, performs DCR, and initiates the OAuth flow

**What's blocking:** Auth0 does not auto-authorize dynamically registered clients (DCR) to access a specific API resource. Claude Desktop registers itself via DCR, gets a `client_id`, but Auth0 rejects the `/authorize` request with:

> Client "9gpWuKkVWJbcSzLzuji05WpbVfvPcWJ2" is not authorized to access resource server "https://fpcore-production.up.railway.app/mcp"

---

## Auth0 Concepts (Plain English)

| Concept | What it is |
|---------|-----------|
| **Tenant** | Your Auth0 account (e.g., `dev-10pbd7y6s0kmedbr.us.auth0.com`) |
| **API (Resource Server)** | The thing being protected — our MCP server. Identified by an "audience" URL. |
| **Application (Client)** | Something that wants to access the API — Claude Desktop, Claude Code, etc. |
| **DCR** | Dynamic Client Registration — lets clients auto-register as Applications without manual dashboard setup |
| **JWKS** | Public keys Auth0 publishes so our server can verify tokens are authentic |
| **Audience** | The identifier that scopes a token to a specific API. Without it, Auth0 issues opaque tokens. |
| **Default Audience** | Auth0 tenant setting — if set, all token requests get this audience automatically |

---

## Immediate Fix: Authorize DCR Clients

The core problem: Auth0 requires explicit per-client authorization to access an API. DCR clients don't get it automatically.

### Option A: Manual authorization (quickest)

1. Auth0 Dashboard → Applications → Applications
2. Find the DCR-created client (client ID from the error log)
3. Go to its **APIs** tab → toggle on the FP_core API

**Downside:** Must repeat for every new DCR client. If Claude re-registers (new device, cleared cache), you get a new client_id.

### Option B: Auth0 Action to auto-authorize (recommended for MVP)

Create an Auth0 Action that runs on every client credential grant / authorization, auto-authorizing any registered client for the FP_core API. This is done via the Auth0 Management API.

1. Auth0 Dashboard → Actions → Flows → **Post Login** (or **Machine to Machine**)
2. Create a custom Action that grants API access to the requesting client
3. All DCR clients are automatically authorized

### Option C: Set Default Audience + skip resource validation

1. Auth0 Dashboard → Settings → General → **Default Audience** → set to `https://fpcore-production.up.railway.app/mcp`
2. This ensures all tokens are JWTs scoped to your API by default
3. Combined with Option A or B to authorize the client

**Recommendation:** Do Option C (Default Audience) + Option A (manual authorize) to unblock immediately. Then implement Option B for longer-term convenience.

---

## MVP Stage: Friendly Users

At MVP, the goal is simple: **you and a handful of trusted users can connect Claude Desktop/Code to the MCP server.**

### What's needed

| Step | Status | Notes |
|------|--------|-------|
| Auth0 API created (audience) | Done | `https://fpcore-production.up.railway.app/mcp` |
| DCR enabled | Done | `registration_endpoint` confirmed in discovery doc |
| Default Audience set | **TODO** | Required so Auth0 issues JWTs, not opaque tokens |
| DCR client authorized for API | **TODO** | Option A (manual) or Option B (Action) |
| Auth0 user accounts created | **TODO** | Create users in Auth0 Dashboard → User Management for each friendly user |
| Callback URLs configured | Verify | `https://claude.ai/api/mcp/auth_callback` in the DCR-created app's Allowed Callbacks |
| Railway env vars set | Done | `AUTH0_DOMAIN`, `AUTH0_AUDIENCE`, `MCP_RESOURCE_URL` |

### User experience at MVP

1. You create an Auth0 user account for each friendly user (email + password)
2. User opens Claude Desktop → Settings → Connectors → enters `https://fpcore-production.up.railway.app/mcp`
3. Auth0 login page appears, user enters credentials
4. Claude Desktop gets a JWT, attaches to all MCP requests
5. All 6 tools work — user shares the single Neo4j Aura database

### Limitations at MVP

- **No data isolation** — all users share the same Neo4j instance and see the same data
- **No user-level permissions** — any authenticated user has full access to all 6 tools
- **No audit trail** — no logging of which user called which tool
- **Manual user management** — you create/remove users in Auth0 Dashboard
- **Single Neo4j instance** — no per-user or per-org databases

---

## Multi-Tenant Stage: Production

Multi-tenancy (see `specs/features/multi_tenant_auth.md`) adds data isolation and scales to many organizations.

### What changes from MVP

| Concern | MVP | Multi-Tenant |
|---------|-----|-------------|
| **Data isolation** | Shared Neo4j | Per-tenant database (separate Neo4j databases or namespaces) |
| **User management** | Auth0 Dashboard (manual) | Auth0 Organizations — each tenant is an Org |
| **Auth model** | Any valid JWT → full access | JWT contains `org_id` claim → routes to tenant's database |
| **Connection routing** | Single global `get_connection()` | Per-tenant `TenantContext` with isolated connection + caches |
| **Server-side state** | Global `_loaded_recipes`, `_loaded_formats` | Per-tenant caches in `TenantContext` |
| **Admin** | Auth0 Dashboard | Admin CLI or admin API for tenant CRUD |
| **Billing** | N/A | Per-tenant usage tracking (future) |

### Auth0 Organizations

Auth0 Organizations is the natural fit for multi-tenancy:

- Each organization = one tenant (e.g., "Acme Corp")
- Users belong to one or more organizations
- Login flow includes org selection
- JWT includes `org_id` claim → server routes to correct database
- Invite flow: org admin invites users via email
- RBAC: per-org roles (viewer, editor, admin) — maps to tool-level permissions

### Implementation path

1. **MVP** (current) → single Neo4j, Auth0 users, no isolation
2. **Soft multi-tenancy** → Auth0 Organizations, `org_id` in JWT, per-org Neo4j namespace/labels, shared database
3. **Hard multi-tenancy** → per-tenant database instances, connection routing via `TenantContext`, LRU connection pooling

The `multi_tenant_auth.md` spec covers stage 3 with KuzuDB (now dead path). The architecture translates to Neo4j with per-tenant databases on Aura or per-tenant label prefixes on a shared instance.

---

## Auth0 Free Tier Constraints

| Limit | Free Tier | Impact |
|-------|-----------|--------|
| Monthly active users | 25,000 | More than enough for MVP + early multi-tenant |
| Machine-to-machine tokens | Unlimited | No limit on Claude connections |
| Organizations | Not available on free tier | Multi-tenant stage requires paid plan (Essentials or above) |
| DCR | Available | Confirmed working |
| Custom Actions | Available | Option B auto-authorization is possible on free tier |
| Social connections | 2 (Google, GitHub) | Sufficient for MVP; promotion to domain-level needed for DCR apps |

**Key constraint:** Auth0 Organizations requires a paid plan. MVP with manual user management works on free tier. Multi-tenant stage requires upgrading.

---

## Checklist

### Unblock now
- [ ] Set Default Audience in Auth0 tenant settings
- [ ] Manually authorize the DCR client for the FP_core API (Option A)
- [ ] Verify Claude Desktop completes the full OAuth flow and calls tools

### MVP hardening
- [ ] Create Auth0 Action to auto-authorize DCR clients (Option B)
- [ ] Create user accounts for friendly users
- [ ] Add Claude callback URLs to allowed callbacks list
- [ ] Test with a second user on a different machine
- [ ] Add request logging (which user called which tool) — optional

### Multi-tenant preparation
- [ ] Evaluate Auth0 paid plans for Organizations support
- [ ] Design per-tenant Neo4j isolation strategy (Aura databases vs label prefixes)
- [ ] Update `multi_tenant_auth.md` to reflect Neo4j (not KuzuDB) and Auth0 Organizations (not API keys)

---

## Open Questions

- [ ] **Auth0 Action for auto-authorize:** What's the exact Action code needed? Does it require Management API permissions? (Resolve during MVP hardening.)
- [ ] **Social login promotion:** Auth0 doesn't enable social logins for DCR apps by default. Do friendly users need Google login, or is email/password sufficient for MVP? (Resolve based on user preference.)
- [ ] **Token lifetime:** Auth0 default access token lifetime is 24 hours. Is this appropriate, or should it be shorter/longer? Claude Desktop handles refresh automatically. (Resolve during testing.)
- [ ] **MCP spec version:** Claude Desktop supports both 2025-03-26 and 2025-06-18 authorization specs. The 06-18 spec has stricter requirements. Which version does our installed FastMCP SDK implement? (Resolve during testing.)