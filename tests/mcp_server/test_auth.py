# tests/mcp_server/test_auth.py — Auth0 JWT verification tests
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from mcp_server.auth import Auth0TokenVerifier


# --- Test RSA key pair (generated once per module) ---

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_public_key = _private_key.public_key()

DOMAIN = "test-tenant.us.auth0.com"
AUDIENCE = "https://fpcore-production.up.railway.app/mcp"


def _make_token(payload: dict, key=_private_key) -> str:
    """Encode a JWT signed with the test RSA key."""
    return jwt.encode(payload, key, algorithm="RS256")


def _valid_payload(**overrides) -> dict:
    """Return a valid Auth0 JWT payload with optional overrides."""
    now = int(time.time())
    base = {
        "iss": f"https://{DOMAIN}/",
        "aud": AUDIENCE,
        "sub": "auth0|user123",
        "azp": "client-abc",
        "scope": "read:recipes write:recipes",
        "exp": now + 3600,
        "iat": now,
    }
    base.update(overrides)
    return base


def _mock_jwks_client(verifier: Auth0TokenVerifier):
    """Patch the JWKS client to return our test public key."""
    mock_signing_key = MagicMock()
    mock_signing_key.key = _public_key
    verifier._jwks_client = MagicMock()
    verifier._jwks_client.get_signing_key_from_jwt = MagicMock(
        return_value=mock_signing_key
    )


class TestAuth0TokenVerifier:
    """Verify Auth0 JWT verification logic."""

    def test_constructor_sets_jwks_url(self):
        """JWKS URL is derived from domain."""
        verifier = Auth0TokenVerifier(domain=DOMAIN, audience=AUDIENCE)
        assert verifier.jwks_url == f"https://{DOMAIN}/.well-known/jwks.json"

    @pytest.mark.anyio
    async def test_valid_jwt_returns_access_token(self):
        """Valid JWT with correct audience/issuer returns AccessToken."""
        verifier = Auth0TokenVerifier(domain=DOMAIN, audience=AUDIENCE)
        _mock_jwks_client(verifier)

        token = _make_token(_valid_payload())
        result = await verifier.verify_token(token)

        assert result is not None
        assert result.token == token
        assert result.client_id == "client-abc"
        assert "read:recipes" in result.scopes
        assert "write:recipes" in result.scopes
        assert result.expires_at is not None

    @pytest.mark.anyio
    async def test_expired_jwt_returns_none(self):
        """Expired JWT returns None."""
        verifier = Auth0TokenVerifier(domain=DOMAIN, audience=AUDIENCE)
        _mock_jwks_client(verifier)

        token = _make_token(_valid_payload(exp=int(time.time()) - 3600))
        result = await verifier.verify_token(token)

        assert result is None

    @pytest.mark.anyio
    async def test_wrong_audience_returns_none(self):
        """JWT with wrong audience returns None."""
        verifier = Auth0TokenVerifier(domain=DOMAIN, audience=AUDIENCE)
        _mock_jwks_client(verifier)

        token = _make_token(_valid_payload(aud="https://wrong-api.example.com"))
        result = await verifier.verify_token(token)

        assert result is None

    @pytest.mark.anyio
    async def test_wrong_issuer_returns_none(self):
        """JWT with wrong issuer returns None."""
        verifier = Auth0TokenVerifier(domain=DOMAIN, audience=AUDIENCE)
        _mock_jwks_client(verifier)

        token = _make_token(_valid_payload(iss="https://wrong-tenant.auth0.com/"))
        result = await verifier.verify_token(token)

        assert result is None

    @pytest.mark.anyio
    async def test_malformed_token_returns_none(self):
        """Non-JWT string returns None."""
        verifier = Auth0TokenVerifier(domain=DOMAIN, audience=AUDIENCE)
        _mock_jwks_client(verifier)

        # Make get_signing_key_from_jwt raise for malformed tokens
        verifier._jwks_client.get_signing_key_from_jwt.side_effect = jwt.PyJWTError(
            "Invalid token"
        )
        result = await verifier.verify_token("not-a-jwt")

        assert result is None
