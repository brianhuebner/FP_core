# tests/mcp_server/test_transport.py — transport selection and OAuth wiring tests
from __future__ import annotations

from unittest.mock import patch


class TestTransportSelection:
    """Verify main() selects transport based on MCP_TRANSPORT env var."""

    def test_default_transport_is_stdio(self):
        """MCP_TRANSPORT unset → main() calls mcp.run(transport='stdio')."""
        env = {"MCP_TRANSPORT": "stdio"}
        with patch.dict("os.environ", env, clear=False):
            # Re-import to pick up env vars
            import importlib

            import mcp_server

            importlib.reload(mcp_server)

            with patch.object(mcp_server.mcp, "run") as mock_run:
                mcp_server.main()
                mock_run.assert_called_once_with(transport="stdio")

    def test_http_transport_selection(self):
        """MCP_TRANSPORT=streamable-http → main() calls mcp.run(transport='streamable-http')."""
        env = {"MCP_TRANSPORT": "streamable-http", "MCP_ALLOW_UNAUTHENTICATED": "true"}
        with patch.dict("os.environ", env, clear=False):
            import importlib

            import mcp_server

            importlib.reload(mcp_server)

            with patch.object(mcp_server.mcp, "run") as mock_run:
                mcp_server.main()
                mock_run.assert_called_once_with(transport="streamable-http")

    def test_http_alias_transport_selection(self):
        """MCP_TRANSPORT=http → same as streamable-http."""
        env = {"MCP_TRANSPORT": "http", "MCP_ALLOW_UNAUTHENTICATED": "true"}
        with patch.dict("os.environ", env, clear=False):
            import importlib

            import mcp_server

            importlib.reload(mcp_server)

            with patch.object(mcp_server.mcp, "run") as mock_run:
                mcp_server.main()
                mock_run.assert_called_once_with(transport="streamable-http")

    def test_host_and_port_from_env(self):
        """MCP_HOST and MCP_PORT env vars are passed to FastMCP constructor."""
        env = {
            "MCP_TRANSPORT": "streamable-http",
            "MCP_HOST": "192.168.1.1",
            "MCP_PORT": "9999",
            "MCP_ALLOW_UNAUTHENTICATED": "true",
        }
        with patch.dict("os.environ", env, clear=False):
            import importlib

            import mcp_server

            importlib.reload(mcp_server)

            assert mcp_server._host == "192.168.1.1"
            assert mcp_server._port == 9999
            assert mcp_server.mcp.settings.host == "192.168.1.1"
            assert mcp_server.mcp.settings.port == 9999

    def test_default_host_and_port(self):
        """Defaults to 0.0.0.0:8000 when env vars not set."""
        env = {"MCP_TRANSPORT": "streamable-http", "MCP_ALLOW_UNAUTHENTICATED": "true"}
        # Remove MCP_HOST, MCP_PORT, PORT if present
        with patch.dict("os.environ", env, clear=False):
            import os

            os.environ.pop("MCP_HOST", None)
            os.environ.pop("MCP_PORT", None)
            os.environ.pop("PORT", None)

            import importlib

            import mcp_server

            importlib.reload(mcp_server)

            assert mcp_server._host == "0.0.0.0"
            assert mcp_server._port == 8000

    def test_railway_port_fallback(self):
        """PORT env var (Railway-injected) is used when MCP_PORT is not set."""
        env = {
            "MCP_TRANSPORT": "streamable-http",
            "PORT": "3000",
            "MCP_ALLOW_UNAUTHENTICATED": "true",
        }
        with patch.dict("os.environ", env, clear=False):
            import os

            os.environ.pop("MCP_PORT", None)

            import importlib

            import mcp_server

            importlib.reload(mcp_server)

            assert mcp_server._port == 3000


class TestOAuthWiring:
    """Verify Auth0 env vars configure OAuth on FastMCP."""

    def test_auth0_env_vars_configure_oauth(self):
        """AUTH0_DOMAIN + AUTH0_AUDIENCE → FastMCP gets token_verifier + auth."""
        env = {
            "MCP_TRANSPORT": "streamable-http",
            "AUTH0_DOMAIN": "test-tenant.us.auth0.com",
            "AUTH0_AUDIENCE": "https://fpcore.example.com/mcp",
        }
        with patch.dict("os.environ", env, clear=False):
            import importlib

            import mcp_server

            importlib.reload(mcp_server)

            assert mcp_server._token_verifier is not None
            assert mcp_server._auth_settings is not None
            assert mcp_server.mcp._token_verifier is not None
            assert mcp_server.mcp.settings.auth is not None

    def test_http_without_auth0_fails_closed(self):
        """HTTP transport + no AUTH0 vars + no override → refuse to start."""
        import os

        import pytest

        env = {"MCP_TRANSPORT": "streamable-http"}
        with patch.dict("os.environ", env, clear=False):
            os.environ.pop("AUTH0_DOMAIN", None)
            os.environ.pop("AUTH0_AUDIENCE", None)
            os.environ.pop("MCP_ALLOW_UNAUTHENTICATED", None)

            import importlib

            import mcp_server

            with pytest.raises(RuntimeError, match="requires AUTH0_DOMAIN"):
                importlib.reload(mcp_server)

    def test_http_unauthenticated_override_allows_no_oauth(self):
        """HTTP + no AUTH0 vars + MCP_ALLOW_UNAUTHENTICATED=true → starts without auth."""
        env = {
            "MCP_TRANSPORT": "streamable-http",
            "MCP_ALLOW_UNAUTHENTICATED": "true",
        }
        with patch.dict("os.environ", env, clear=False):
            import os

            os.environ.pop("AUTH0_DOMAIN", None)
            os.environ.pop("AUTH0_AUDIENCE", None)

            import importlib

            import mcp_server

            importlib.reload(mcp_server)

            assert mcp_server._token_verifier is None
            assert mcp_server._auth_settings is None
            assert mcp_server.mcp._token_verifier is None
            assert mcp_server.mcp.settings.auth is None

    def test_stdio_ignores_auth0_vars(self):
        """STDIO transport → no auth regardless of AUTH0 vars."""
        env = {
            "MCP_TRANSPORT": "stdio",
            "AUTH0_DOMAIN": "test-tenant.us.auth0.com",
            "AUTH0_AUDIENCE": "https://fpcore.example.com/mcp",
        }
        with patch.dict("os.environ", env, clear=False):
            import importlib

            import mcp_server

            importlib.reload(mcp_server)

            assert mcp_server._token_verifier is None
            assert mcp_server._auth_settings is None
            assert mcp_server.mcp._token_verifier is None
            assert mcp_server.mcp.settings.auth is None
