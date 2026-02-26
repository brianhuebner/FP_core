# tests/mcp_server/test_auth.py — bearer token middleware tests
from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from mcp_server.auth import BearerTokenMiddleware


def _make_app(token: str) -> Starlette:
    """Build a minimal Starlette app with BearerTokenMiddleware."""
    async def homepage(request: Request) -> PlainTextResponse:
        return PlainTextResponse("OK")

    app = Starlette(routes=[Route("/", homepage)])
    app.add_middleware(BearerTokenMiddleware, token=token)
    return app


class TestBearerTokenMiddleware:
    """Verify bearer token auth middleware."""

    def test_valid_token_passes(self):
        """Request with correct bearer token receives 200."""
        app = _make_app("secret-token")
        client = TestClient(app)
        resp = client.get("/", headers={"Authorization": "Bearer secret-token"})
        assert resp.status_code == 200
        assert resp.text == "OK"

    def test_missing_token_returns_401(self):
        """Request without Authorization header receives 401."""
        app = _make_app("secret-token")
        client = TestClient(app)
        resp = client.get("/")
        assert resp.status_code == 401
        assert resp.json() == {"error": "Unauthorized"}

    def test_wrong_token_returns_401(self):
        """Request with incorrect token receives 401."""
        app = _make_app("secret-token")
        client = TestClient(app)
        resp = client.get("/", headers={"Authorization": "Bearer wrong-token"})
        assert resp.status_code == 401

    def test_non_bearer_scheme_returns_401(self):
        """Request with non-Bearer auth scheme receives 401."""
        app = _make_app("secret-token")
        client = TestClient(app)
        resp = client.get("/", headers={"Authorization": "Basic dXNlcjpwYXNz"})
        assert resp.status_code == 401