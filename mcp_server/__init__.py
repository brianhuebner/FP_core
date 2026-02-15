# mcp_server/__init__.py — FastMCP server instance, state, and connection management
from __future__ import annotations

import logging
import os
import sys
from typing import Dict, Optional

from mcp.server.fastmcp import FastMCP

from domain.types import GraphPattern

# Configure logging to stderr (required for STDIO transport)
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("mcp_server")

# FastMCP server instance
mcp = FastMCP("FP_core")

# Server-side state: loaded recipe graphs keyed by recipe_id
_loaded_recipes: Dict[str, GraphPattern] = {}

# Lazy Neo4j connection singleton
_connection: Optional[object] = None


def get_loaded_recipes() -> Dict[str, GraphPattern]:
    """Access the server-side recipe cache."""
    return _loaded_recipes


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


# Register tool and resource handlers by importing their modules
import mcp_server.tools  # noqa: E402, F401
import mcp_server.resources  # noqa: E402, F401


def main():
    """Run the MCP server over STDIO transport."""
    logger.info("Starting FP_core MCP server")
    mcp.run(transport="stdio")
