# mcp_server/tools.py — MCP tool handlers (Tier 1)
from __future__ import annotations

import json
import logging
from decimal import Decimal

from mcp_server import get_connection, get_loaded_recipes, mcp
from mcp_server.builders import build_pipeline_from_spec
from mcp_server.summarizers import (
    summarize_build_result,
    summarize_processing_instructions,
    summarize_recipe_load,
    summarize_validation_result,
)
from domain.logic import (
    validate_output_format,
    validate_pipeline_connectivity,
    validate_recipe,
)
from domain.ontology import (
    ValidationResult,
    validate_node_properties,
    validate_posting_allowed,
    validate_transaction_balance,
)
from domain.ontology_recipe import merged_ontology
from domain.types import BalanceDirection, NodeLabel, RelationshipType, TransactionLine
from persistence.operations import load_pattern_by_recipe, save_pattern

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


@mcp.tool()
def build_and_save_pipeline(pipeline_spec: str) -> str:
    """Build a recipe pipeline from a JSON spec, validate it, and save to Neo4j.

    Accepts a JSON string containing a pipeline specification with schema,
    recipe (mapping rules + accounts), and optional output format.
    Runs Gate 1 validators (recipe structure, pipeline connectivity, output
    format, node properties). If valid, saves to Neo4j and caches the pattern.

    Returns a JSON summary with validation results and save counts.
    """
    try:
        spec = json.loads(pipeline_spec)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid JSON: {e}"})

    recipe_id = spec.get("recipe_id")
    if not recipe_id:
        return json.dumps({"error": "Missing required field: recipe_id"})

    # Build the graph pattern from spec
    try:
        pattern = build_pipeline_from_spec(spec)
    except (KeyError, TypeError, ValueError) as e:
        logger.error("Failed to build pipeline %s: %s", recipe_id, e)
        return json.dumps({"error": f"Build error: {e}"}, default=str)

    # Gate 1 validation
    ontology = merged_ontology()
    validation_results = [
        validate_recipe(pattern),
        validate_pipeline_connectivity(pattern),
    ]

    # Output format validation (only if output nodes exist)
    has_output = any(NodeLabel.OUTPUT_FORMAT in n.labels for n in pattern.nodes)
    if has_output:
        validation_results.append(validate_output_format(pattern))

    # Node property validation
    node_results = [validate_node_properties(n, ontology) for n in pattern.nodes]
    validation_results.extend(node_results)

    merged = ValidationResult.merge(*validation_results)

    if not merged.is_valid:
        logger.warning("Pipeline %s failed validation: %s", recipe_id, merged.errors)
        summary = summarize_build_result(merged, None, recipe_id, None)
        return json.dumps(summary, indent=2, default=str)

    # Save to Neo4j
    try:
        conn = get_connection()
        save_counts = save_pattern(conn, pattern)
    except Exception as e:
        logger.error("Failed to save pipeline %s: %s", recipe_id, e)
        return json.dumps({"error": f"Neo4j save error: {e}"}, default=str)

    # Cache the pattern
    loaded = get_loaded_recipes()
    loaded[recipe_id] = pattern
    logger.info(
        "Built and saved pipeline %s: %d nodes, %d relationships",
        recipe_id, len(pattern.nodes), len(pattern.relationships),
    )

    summary = summarize_build_result(merged, save_counts, recipe_id, pattern)
    return json.dumps(summary, indent=2, default=str)


@mcp.tool()
def validate_entries(entries: str, recipe_id: str | None = None) -> str:
    """Validate journal entries against double-entry accounting rules (Gate 2).

    Accepts a JSON string containing a list of journal entries, each with
    a 'lines' array of debit/credit entries. Validates that debits equal
    credits for each entry. If recipe_id is provided and loaded, also
    checks that referenced accounts are active.

    Returns a JSON summary with per-entry validation details.
    """
    try:
        entries_list = json.loads(entries)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid JSON: {e}"})

    if not isinstance(entries_list, list):
        return json.dumps({"error": "entries must be a JSON array"})

    # Look up cached recipe for account checks
    cached_pattern = None
    if recipe_id:
        loaded = get_loaded_recipes()
        cached_pattern = loaded.get(recipe_id)

    entries_results = []
    account_results = []
    all_validation_results = []

    # Build account lookup from cached pattern if available
    account_map = {}
    if cached_pattern:
        for node in cached_pattern.nodes:
            if NodeLabel.ACCOUNT in node.labels:
                code = node.properties.get("code")
                if code:
                    account_map[code] = node

    for idx, entry in enumerate(entries_list):
        lines = entry.get("lines", [])
        transaction_lines = []
        debit_total = Decimal("0")
        credit_total = Decimal("0")

        for line in lines:
            amount = Decimal(str(line["amount"]))
            direction = BalanceDirection.DEBIT if line["direction"] == "debit" else BalanceDirection.CREDIT
            transaction_lines.append(TransactionLine(
                line_id=f"entry_{idx}_{line.get('account_code', 'unknown')}",
                amount=amount,
                direction=direction,
            ))
            if direction == BalanceDirection.DEBIT:
                debit_total += amount
            else:
                credit_total += amount

        result = validate_transaction_balance(tuple(transaction_lines))
        all_validation_results.append(result)

        entries_results.append({
            "entry_index": idx,
            "is_valid": result.is_valid,
            "debit_total": str(debit_total),
            "credit_total": str(credit_total),
        })

    # Account-level checks if recipe is loaded
    checked_accounts = set()
    if account_map:
        for entry in entries_list:
            for line in entry.get("lines", []):
                acct_code = line.get("account_code")
                if acct_code and acct_code in account_map and acct_code not in checked_accounts:
                    checked_accounts.add(acct_code)
                    acct_node = account_map[acct_code]
                    is_active = acct_node.properties.get("is_active", True)
                    posting_result = validate_posting_allowed(is_active)
                    all_validation_results.append(posting_result)
                    account_results.append({
                        "account_code": acct_code,
                        "is_active": is_active,
                    })

    merged = ValidationResult.merge(*all_validation_results) if all_validation_results else ValidationResult.success()

    summary = summarize_validation_result(entries_results, account_results, merged)
    return json.dumps(summary, indent=2, default=str)
