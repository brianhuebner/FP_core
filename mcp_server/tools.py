# mcp_server/tools.py — MCP tool handlers (Tier 1)
from __future__ import annotations

import json
import logging
from decimal import Decimal

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
from domain.types import BalanceDirection, GraphPattern, NodeLabel, TransactionLine
from mcp_server import get_connection, get_loaded_formats, get_loaded_recipes, mcp
from mcp_server.builders import build_format_from_spec, build_pipeline_from_spec
from mcp_server.summarizers import (
    summarize_build_result,
    summarize_format_load,
    summarize_processing_instructions,
    summarize_recipe_load,
    summarize_validation_result,
)
from persistence.operations import (
    list_available as persistence_list_available,
)
from persistence.operations import (
    load_format_by_id,
    load_pattern_by_recipe,
    save_pattern,
)

logger = logging.getLogger("mcp_server")


def _error(msg: str, hint: str | None = None) -> str:
    """Build a consistent JSON error response."""
    result: dict[str, str] = {"error": msg}
    if hint is not None:
        result["hint"] = hint
    return json.dumps(result, default=str)


def _require_format(format_id: str) -> GraphPattern | None:
    """Return a cached format pattern, auto-loading from Neo4j if needed.

    Returns the GraphPattern, or None if loading fails (caller should
    check and return an error).
    """
    loaded_formats = get_loaded_formats()
    pattern = loaded_formats.get(format_id)
    if pattern is not None:
        return pattern
    try:
        conn = get_connection()
        pattern = load_format_by_id(conn, format_id)
        if pattern.nodes:
            loaded_formats[format_id] = pattern
            return pattern
    except Exception as e:
        logger.error("Failed to load format %s: %s", format_id, e)
    return None


@mcp.tool()
def list_available(placeholder: str | None = None) -> str:
    """List all saved recipes and output formats in the knowledge graph.

    Returns a JSON summary of all available recipes and formats with
    identity fields and summary counts. No parameters required.

    Use this to discover what's available before calling load_recipe
    or load_format.
    """
    try:
        conn = get_connection()
        result = persistence_list_available(conn)
    except Exception as e:
        logger.error("Failed to list available: %s", e)
        return _error(f"Neo4j error: {e}")

    return json.dumps(result, indent=2, default=str)


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
        return _error(f"Neo4j error: {e}")

    if not pattern.nodes:
        return _error(f"No nodes found for recipe_id '{recipe_id}'")

    loaded = get_loaded_recipes()
    loaded[recipe_id] = pattern
    logger.info(
        "Loaded recipe %s: %d nodes, %d relationships",
        recipe_id,
        len(pattern.nodes),
        len(pattern.relationships),
    )

    summary = summarize_recipe_load(pattern, recipe_id)
    return json.dumps(summary, indent=2, default=str)


@mcp.tool()
def load_format(format_id: str) -> str:
    """Load an output format from Neo4j and return a structured summary.

    Loads all OutputFormat, OutputColumn, ValidationRule, and EntryStructure
    nodes for the given format_id, caches in server-side state.

    The loaded format can be referenced in get_processing_instructions.
    """
    try:
        conn = get_connection()
        pattern = load_format_by_id(conn, format_id)
    except Exception as e:
        logger.error("Failed to load format %s: %s", format_id, e)
        return _error(f"Neo4j error: {e}")

    if not pattern.nodes:
        return _error(f"No nodes found for format_id '{format_id}'")

    loaded = get_loaded_formats()
    loaded[format_id] = pattern
    logger.info(
        "Loaded format %s: %d nodes, %d relationships",
        format_id,
        len(pattern.nodes),
        len(pattern.relationships),
    )

    summary = summarize_format_load(pattern, format_id)
    return json.dumps(summary, indent=2, default=str)


@mcp.tool()
def get_processing_instructions(recipe_id: str, format_id: str | None = None) -> str:
    """Return processing instructions for a previously loaded recipe.

    Extracts measures, mapping rules with resolved account codes,
    and output format specification from the cached recipe graph.

    Call load_recipe first to load the recipe into server-side state.
    If format_id is provided, includes output format columns and
    validation rules from the cached format (auto-loads from Neo4j
    if not already cached).
    """
    loaded = get_loaded_recipes()
    pattern = loaded.get(recipe_id)
    if pattern is None:
        return _error(f"Recipe '{recipe_id}' not loaded. Call load_recipe first.")

    # Resolve format pattern if format_id provided
    format_pattern = None
    if format_id:
        format_pattern = _require_format(format_id)
        if format_pattern is None:
            return _error(f"No nodes found for format_id '{format_id}'")

    instructions = summarize_processing_instructions(pattern, recipe_id, format_pattern)
    return json.dumps(instructions, indent=2, default=str)


@mcp.tool()
def build_and_save_pipeline(pipeline_spec: str) -> str:
    """Build a recipe pipeline from a JSON spec, validate it, and save to Neo4j.

    Runs Gate 1 validators (recipe structure, pipeline connectivity, output
    format, node properties). If valid, saves to Neo4j and caches the pattern.
    Returns a JSON summary with validation results and save counts.

    Required spec shape (pass as a JSON string):
    {
      "recipe_id": "my_payroll_v1",
      "schema": {
        "name": "payroll_export",
        "source_system": "csv_import",
        "columns": [
          {"name": "gross_pay", "position": 1, "data_type": "decimal", "role": "amount"},
          {"name": "department", "position": 2, "data_type": "string",  "role": "category"}
        ],
        "measures": [
          {"name": "total_gross", "operation": "sum", "source_column": "gross_pay"}
        ]
      },
      "recipe": {
        "name": "Payroll Journal",
        "rules": [
          {
            "rule_name": "gross_pay_entry",
            "source_measure": "total_gross",
            "priority": 1,
            "memo_template": "Gross pay",
            "debit":  {"slot_id": "salary_dr", "role": "expense",
                       "account_code": "6100", "account_name": "Salary Expense",
                       "account_type": "expense", "normal_balance": "debit"},
            "credit": {"slot_id": "payroll_cr", "role": "liability",
                       "account_code": "2200", "account_name": "Payroll Payable",
                       "account_type": "liability", "normal_balance": "credit"}
          }
        ]
      }
    }

    Key constraints:
    - "debit" and "credit" are singular dict objects (not arrays).
    - "slot_id" must be unique across all rules in the recipe.
    - "source_measure" must match a measure "name" in schema.measures.
    - Valid data_type values: "string", "decimal", "date", "integer", "boolean".
    - Valid column role values: "identifier", "amount", "date", "category", "text".
    - Valid account_type values: "asset", "liability", "equity", "expense", "revenue".
    - Valid normal_balance values: "debit", "credit".
    - Valid measure operation values: "sum", "count", "avg", "min", "max".

    Optional recipe fields:
    - "conditions": list of {condition_id, column, operator, value} objects.
      Valid operators: "equals", "not_equals", "greater_than", "less_than",
      "is_null", "is_not_null", "always". "value" may be omitted for is_null/
      is_not_null/always.
    - Rule "when": a condition_id string referencing an entry in recipe.conditions.
    """
    try:
        spec = json.loads(pipeline_spec)
    except json.JSONDecodeError as e:
        return _error(f"Invalid JSON: {e}")

    recipe_id = spec.get("recipe_id")
    if not recipe_id:
        return _error("Missing required field: recipe_id")

    # Build the graph pattern from spec
    try:
        pattern = build_pipeline_from_spec(spec)
    except KeyError as e:
        logger.error("Failed to build pipeline %s: missing key %s", recipe_id, e)
        return _error(
            f"Build error: missing required field {e}",
            hint=(
                "Check that all required fields are present. Common issues: "
                "recipe section needs 'name'; each rule needs 'rule_name', 'source_measure', "
                "'debit' (singular dict), and 'credit' (singular dict); each account slot "
                "needs 'slot_id', 'role', 'account_code', 'account_name', 'account_type', "
                "'normal_balance'. See tool description for a complete example."
            ),
        )
    except (TypeError, ValueError) as e:
        logger.error("Failed to build pipeline %s: %s", recipe_id, e)
        return _error(
            f"Build error: {e}",
            hint=(
                "'debit' and 'credit' must be single dict objects, not arrays. "
                "Column and measure entries must be dicts with named fields, not lists. "
                "See tool description for the expected spec shape."
            ),
        )

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
        return _error(f"Neo4j save error: {e}")

    # Cache the recipe pattern (without output nodes if they were included for compat)
    loaded = get_loaded_recipes()
    loaded[recipe_id] = pattern
    logger.info(
        "Built and saved pipeline %s: %d nodes, %d relationships",
        recipe_id,
        len(pattern.nodes),
        len(pattern.relationships),
    )

    summary = summarize_build_result(merged, save_counts, recipe_id, pattern)
    return json.dumps(summary, indent=2, default=str)


@mcp.tool()
def build_output(output_spec: str) -> str:
    """Build an output format from a JSON spec, validate it, and save to Neo4j.

    Accepts a JSON string containing a format specification with format_id,
    name, target_system, file_format, columns, optional validation_rules,
    and optional entry_structure.

    Runs Gate 1 validators (output format structure, node properties).
    If valid, saves to Neo4j and caches the format pattern.

    Returns a JSON summary with validation results and save counts.
    """
    try:
        spec = json.loads(output_spec)
    except json.JSONDecodeError as e:
        return _error(f"Invalid JSON: {e}")

    format_id = spec.get("format_id")
    if not format_id:
        return _error("Missing required field: format_id")

    # Build the format pattern from spec
    try:
        pattern = build_format_from_spec(spec)
    except (KeyError, TypeError, ValueError) as e:
        logger.error("Failed to build format %s: %s", format_id, e)
        return _error(f"Build error: {e}")

    # Gate 1 validation
    ontology = merged_ontology()
    validation_results = [
        validate_output_format(pattern),
    ]

    # Node property validation
    node_results = [validate_node_properties(n, ontology) for n in pattern.nodes]
    validation_results.extend(node_results)

    merged = ValidationResult.merge(*validation_results)

    if not merged.is_valid:
        logger.warning("Format %s failed validation: %s", format_id, merged.errors)
        result = {
            "format_id": format_id,
            "gate1_validation": {
                "is_valid": False,
                "errors": list(merged.errors),
                "warnings": list(merged.warnings),
            },
            "saved": False,
            "counts": None,
        }
        return json.dumps(result, indent=2, default=str)

    # Save to Neo4j
    try:
        conn = get_connection()
        save_counts = save_pattern(conn, pattern)
    except Exception as e:
        logger.error("Failed to save format %s: %s", format_id, e)
        return _error(f"Neo4j save error: {e}")

    # Cache the format
    loaded = get_loaded_formats()
    loaded[format_id] = pattern
    logger.info(
        "Built and saved format %s: %d nodes, %d relationships",
        format_id,
        len(pattern.nodes),
        len(pattern.relationships),
    )

    # Get the format name from the OutputFormat node
    fmt_name = None
    for n in pattern.nodes:
        if NodeLabel.OUTPUT_FORMAT in n.labels:
            fmt_name = n.properties.get("name")
            break

    total_nodes = sum(r.get("nodes_created", 0) for r in save_counts)
    total_rels = sum(r.get("relationships_created", 0) for r in save_counts)

    result = {
        "format_id": format_id,
        "format_name": fmt_name,
        "gate1_validation": {
            "is_valid": True,
            "errors": [],
            "warnings": list(merged.warnings),
        },
        "saved": True,
        "counts": {
            "nodes_created": total_nodes,
            "relationships_created": total_rels,
        },
    }
    return json.dumps(result, indent=2, default=str)


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
        return _error(f"Invalid JSON: {e}")

    if not isinstance(entries_list, list):
        return _error("entries must be a JSON array")

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
            transaction_lines.append(
                TransactionLine(
                    line_id=f"entry_{idx}_{line.get('account_code', 'unknown')}",
                    amount=amount,
                    direction=direction,
                )
            )
            if direction == BalanceDirection.DEBIT:
                debit_total += amount
            else:
                credit_total += amount

        result = validate_transaction_balance(tuple(transaction_lines))
        all_validation_results.append(result)

        entries_results.append(
            {
                "entry_index": idx,
                "is_valid": result.is_valid,
                "debit_total": str(debit_total),
                "credit_total": str(credit_total),
            }
        )

    # Account-level checks if recipe is loaded
    if account_map:
        referenced_codes = {
            line.get("account_code") for entry in entries_list for line in entry.get("lines", [])
        } & account_map.keys()

        for acct_code in sorted(referenced_codes):
            acct_node = account_map[acct_code]
            is_active = acct_node.properties.get("is_active", True)
            all_validation_results.append(validate_posting_allowed(is_active))
            account_results.append(
                {
                    "account_code": acct_code,
                    "is_active": is_active,
                }
            )

    merged = ValidationResult.merge(*all_validation_results) if all_validation_results else ValidationResult.success()

    summary = summarize_validation_result(entries_results, account_results, merged)
    return json.dumps(summary, indent=2, default=str)
