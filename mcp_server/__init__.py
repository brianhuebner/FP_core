# mcp_server/__init__.py — FastMCP server instance, state, and connection management
from __future__ import annotations

import logging
import os
import sys
from typing import TYPE_CHECKING

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from domain.types import GraphPattern

if TYPE_CHECKING:
    from persistence.connection import Neo4jConnection

load_dotenv()

# Configure logging to stderr (required for STDIO transport)
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("mcp_server")

# Transport configuration from environment
_transport = os.environ.get("MCP_TRANSPORT", "stdio")
_host = os.environ.get("MCP_HOST", "0.0.0.0")
_port = int(os.environ.get("MCP_PORT") or os.environ.get("PORT") or "8000")

# Auth0 OAuth configuration (only active for HTTP transport)
_auth0_domain = os.environ.get("AUTH0_DOMAIN")
_auth0_audience = os.environ.get("AUTH0_AUDIENCE")

if _transport in ("streamable-http", "http") and _auth0_domain and _auth0_audience:
    from mcp.server.auth.settings import AuthSettings

    from mcp_server.auth import Auth0TokenVerifier

    _token_verifier = Auth0TokenVerifier(domain=_auth0_domain, audience=_auth0_audience)
    _resource_url = os.environ.get("MCP_RESOURCE_URL", f"http://localhost:{_port}/mcp")
    _auth_settings = AuthSettings(
        issuer_url=f"https://{_auth0_domain}",
        resource_server_url=_resource_url,
    )
else:
    _token_verifier = None
    _auth_settings = None

# FastMCP server instance — host/port configured for HTTP transport
mcp = FastMCP(
    "FP_core",
    host=_host,
    port=_port,
    token_verifier=_token_verifier,
    auth=_auth_settings,
)

# Server-side state: loaded recipe graphs keyed by recipe_id
_loaded_recipes: dict[str, GraphPattern] = {}

# Server-side state: loaded format graphs keyed by format_id
_loaded_formats: dict[str, GraphPattern] = {}

# Lazy Neo4j connection singleton
_connection: Neo4jConnection | None = None


def get_loaded_recipes() -> dict[str, GraphPattern]:
    """Access the server-side recipe cache."""
    return _loaded_recipes


def get_loaded_formats() -> dict[str, GraphPattern]:
    """Access the server-side format cache."""
    return _loaded_formats


def get_connection():
    """Lazy singleton for Neo4jConnection. Reads env vars on first call."""
    global _connection
    if _connection is None:
        from persistence.connection import Neo4jConnection

        _connection = Neo4jConnection(
            uri=os.environ.get("NEO4J_URI"),
            user=os.environ.get("NEO4J_USER", "neo4j"),
            password=os.environ.get("NEO4J_PASSWORD"),
        )
        logger.info("Connected to Neo4j at %s", _connection.uri)
    return _connection


# Register tool, resource, and prompt handlers by importing their modules
import mcp_server.prompts  # noqa: E402, F401
import mcp_server.resources  # noqa: E402, F401
import mcp_server.tools  # noqa: E402, F401


def main():
    """Run the MCP server. Transport selected by MCP_TRANSPORT env var."""
    logger.info("Starting FP_core MCP server (transport=%s)", _transport)

    if _transport in ("streamable-http", "http"):
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")
