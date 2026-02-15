# mcp_server/tools.py — MCP tool handlers (Tier 1: coarse-grained reads)
from __future__ import annotations

import json
import logging

from mcp_server import get_connection, get_loaded_recipes, mcp
from mcp_server.summarizers import summarize_processing_instructions, summarize_recipe_load
from persistence.operations import load_pattern_by_recipe

logger = logging.getLogger("mcp_server")


@mcp.tool()
def load_recipe(recipe_id: str) -> str:
    """Load a recipe pipeline graph from Neo4j and return a structured summary.

    Loads all nodes and relationships for the given recipe_id, caches the
    graph in server-side state, and returns a JSON summary of the schema,
    recipe rules, and output format.

    Must be called before get_processing_instructions.
    """
    try:
        conn = get_connection()
        pattern = load_pattern_by_recipe(conn, recipe_id)
    except Exception as e:
        logger.error("Failed to load recipe %s: %s", recipe_id, e)
        return json.dumps({"error": f"Neo4j error: {e}"}, default=str)

    if not pattern.nodes:
        return json.dumps({"error": f"No nodes found for recipe_id '{recipe_id}'"})

    loaded = get_loaded_recipes()
    loaded[recipe_id] = pattern
    logger.info(
        "Loaded recipe %s: %d nodes, %d relationships",
        recipe_id, len(pattern.nodes), len(pattern.relationships),
    )

    summary = summarize_recipe_load(pattern, recipe_id)
    return json.dumps(summary, indent=2, default=str)


@mcp.tool()
def get_processing_instructions(recipe_id: str) -> str:
    """Return processing instructions for a previously loaded recipe.

    Extracts measures, mapping rules with resolved account codes,
    and output format specification from the cached recipe graph.

    Call load_recipe first to load the recipe into server-side state.
    """
    loaded = get_loaded_recipes()
    pattern = loaded.get(recipe_id)
    if pattern is None:
        return json.dumps({
            "error": f"Recipe '{recipe_id}' not loaded. Call load_recipe first.",
        })

    instructions = summarize_processing_instructions(pattern, recipe_id)
    return json.dumps(instructions, indent=2, default=str)
