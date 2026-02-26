# mcp_server/auth.py — Auth0 JWT verification for OAuth 2.1
from __future__ import annotations

import jwt
from mcp.server.auth.provider import AccessToken


class Auth0TokenVerifier:
    """Verify Auth0-issued JWTs against the tenant's JWKS."""

    def __init__(self, domain: str, audience: str):
        self.domain = domain
        self.audience = audience
        self.jwks_url = f"https://{domain}/.well-known/jwks.json"
        self._jwks_client = jwt.PyJWKClient(self.jwks_url, cache_keys=True)

    async def verify_token(self, token: str) -> AccessToken | None:
        """Verify a bearer token and return access info if valid."""
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
