# mcp_server/summarizers.py — Pure functions: GraphPattern → JSON-serializable dicts
from __future__ import annotations

from typing import Any, Dict, List, Optional

from domain.types import GraphPattern, Node, NodeLabel, RelationshipType
from domain.ontology import ValidationResult
from domain.logic import (
    extract_entry_structure,
    extract_debit_credit_slots,
    extract_measures_for_schema,
    extract_output_columns,
    extract_validation_rules,
)


# ============================================================================
# Graph traversal helpers
# ============================================================================

def _find_nodes_by_label(pattern: GraphPattern, label: NodeLabel) -> List[Node]:
    """Return all nodes in the pattern that carry the given label."""
    return [n for n in pattern.nodes if label in n.labels]


def _find_single_node_by_label(pattern: GraphPattern, label: NodeLabel) -> Optional[Node]:
    """Return the first node with the given label, or None."""
    for n in pattern.nodes:
        if label in n.labels:
            return n
    return None


def _find_related_nodes(
    pattern: GraphPattern, start_node_id: str, rel_type: RelationshipType,
) -> List[Node]:
    """Follow outgoing edges of rel_type from start_node_id, return target nodes."""
    target_ids = {
        rel.end_node_id
        for rel in pattern.relationships
        if rel.type == rel_type and rel.start_node_id == start_node_id
    }
    node_map = {n.id: n for n in pattern.nodes}
    return [node_map[nid] for nid in target_ids if nid in node_map]


def _resolve_account_for_slot(
    pattern: GraphPattern, slot_node_id: str,
) -> Optional[Node]:
    """AccountSlot → MAPPED_TO → Account. Returns the Account node or None."""
    for rel in pattern.relationships:
        if (
            rel.type == RelationshipType.MAPPED_TO
            and rel.start_node_id == slot_node_id
        ):
            for n in pattern.nodes:
                if n.id == rel.end_node_id:
                    return n
    return None


def _prop(node: Node, key: str, default: Any = None) -> Any:
    """Safe property access on a Node."""
    return node.properties.get(key, default)


# ============================================================================
# Top-level summarizers
# ============================================================================

def summarize_recipe_load(pattern: GraphPattern, recipe_id: str) -> Dict[str, Any]:
    """Summarize a loaded recipe graph for the load_recipe tool response."""
    result: Dict[str, Any] = {
        "recipe_id": recipe_id,
        "graph_structure": {
            "total_nodes": len(pattern.nodes),
            "total_relationships": len(pattern.relationships),
        },
    }

    # Schema section
    schema_node = _find_single_node_by_label(pattern, NodeLabel.SOURCE_SCHEMA)
    if schema_node:
        columns = _find_related_nodes(pattern, schema_node.id, RelationshipType.HAS_COLUMN)
        columns.sort(key=lambda n: _prop(n, "position", 0))
        result["schema"] = {
            "name": _prop(schema_node, "name"),
            "file_pattern": _prop(schema_node, "file_pattern"),
            "row_grain": _prop(schema_node, "row_grain"),
            "columns": [
                {
                    "name": _prop(c, "name"),
                    "position": _prop(c, "position"),
                    "data_type": _prop(c, "data_type"),
                    "role": _prop(c, "role"),
                }
                for c in columns
            ],
        }

    # Recipe section
    recipe_node = _find_single_node_by_label(pattern, NodeLabel.ACCOUNTING_RECIPE)
    if recipe_node:
        rule_nodes = _find_related_nodes(
            pattern, recipe_node.id, RelationshipType.HAS_RULE,
        )
        rule_nodes.sort(key=lambda n: _prop(n, "priority", 0))
        result["recipe_name"] = _prop(recipe_node, "name")
        result["recipe"] = {
            "name": _prop(recipe_node, "name"),
            "journal_no_format": _prop(recipe_node, "journal_no_format"),
            "batch_key": _prop(recipe_node, "batch_key"),
            "rules": [
                {
                    "rule_name": _prop(r, "rule_name"),
                    "source_measure": _prop(r, "source_measure"),
                    "priority": _prop(r, "priority"),
                    "memo_template": _prop(r, "memo_template"),
                }
                for r in rule_nodes
            ],
        }

    return result


def summarize_processing_instructions(
    pattern: GraphPattern,
    recipe_id: str,
    format_pattern: Optional[GraphPattern] = None,
) -> Dict[str, Any]:
    """Summarize processing instructions for the get_processing_instructions tool.

    If format_pattern is provided, includes output format columns, validation
    rules, and entry structure in the response.
    """
    result: Dict[str, Any] = {"recipe_id": recipe_id}

    # Measures — with resolved column names via AGGREGATES
    schema_node = _find_single_node_by_label(pattern, NodeLabel.SOURCE_SCHEMA)
    if schema_node:
        measures = extract_measures_for_schema(pattern, schema_node.id)
        node_map = {n.id: n for n in pattern.nodes}
        measures_list = []
        for m in measures:
            # Resolve the column this measure aggregates
            col_name = None
            for rel in pattern.relationships:
                if (
                    rel.type == RelationshipType.AGGREGATES
                    and rel.start_node_id == m.id
                ):
                    col_node = node_map.get(rel.end_node_id)
                    if col_node:
                        col_name = _prop(col_node, "name")
                    break
            measure_entry: Dict[str, Any] = {
                "name": _prop(m, "name"),
                "operation": _prop(m, "operation"),
                "column": col_name,
            }
            group_by_str = _prop(m, "group_by")
            if group_by_str:
                measure_entry["group_by"] = group_by_str.split(",")
            split_by = _prop(m, "split_by")
            if split_by:
                measure_entry["split_by"] = split_by
            split_column = _prop(m, "split_column")
            if split_column:
                measure_entry["split_column"] = split_column
            measures_list.append(measure_entry)
        result["measures"] = measures_list

    # Rules — with resolved accounts via debit/credit slots → MAPPED_TO
    recipe_node = _find_single_node_by_label(pattern, NodeLabel.ACCOUNTING_RECIPE)
    if recipe_node:
        rule_nodes = _find_related_nodes(
            pattern, recipe_node.id, RelationshipType.HAS_RULE,
        )
        rule_nodes.sort(key=lambda n: _prop(n, "priority", 0))

        rules_list = []
        for rule in rule_nodes:
            debit_slots, credit_slots = extract_debit_credit_slots(pattern, rule.id)

            def _slot_accounts(slots):
                accounts = []
                for slot in slots:
                    acct = _resolve_account_for_slot(pattern, slot.id)
                    if acct:
                        accounts.append({
                            "account_code": _prop(acct, "code"),
                            "account_name": _prop(acct, "name"),
                        })
                return accounts

            rules_list.append({
                "priority": _prop(rule, "priority"),
                "name": _prop(rule, "rule_name"),
                "source_measure": _prop(rule, "source_measure"),
                "memo_template": _prop(rule, "memo_template"),
                "debits": _slot_accounts(debit_slots),
                "credits": _slot_accounts(credit_slots),
            })
        result["rules"] = rules_list

    # Output format — from separately loaded format pattern
    fmt_pattern = format_pattern
    if fmt_pattern is not None:
        fmt_node = _find_single_node_by_label(fmt_pattern, NodeLabel.OUTPUT_FORMAT)
        if fmt_node:
            out_cols = extract_output_columns(fmt_pattern, fmt_node.id)
            out_cols_sorted = sorted(out_cols, key=lambda n: _prop(n, "position", 0))
            val_rules = extract_validation_rules(fmt_pattern, fmt_node.id)
            entry_struct = extract_entry_structure(fmt_pattern, fmt_node.id)

            output_section: Dict[str, Any] = {
                "columns": [
                    {"position": _prop(c, "position"), "name": _prop(c, "name")}
                    for c in out_cols_sorted
                ],
                "validation_rules": [
                    {
                        "name": _prop(v, "name"),
                        "expression": _prop(v, "expression"),
                        "scope": _prop(v, "scope"),
                    }
                    for v in val_rules
                ],
            }
            if entry_struct:
                output_section["entry_structure"] = {
                    "grouping_column": _prop(entry_struct, "grouping_column"),
                    "entry_separator": _prop(entry_struct, "entry_separator"),
                }
            result["output_format"] = output_section

    return result


def summarize_format_load(pattern: GraphPattern, format_id: str) -> Dict[str, Any]:
    """Summarize a loaded output format graph for the load_format tool response."""
    result: Dict[str, Any] = {
        "format_id": format_id,
        "graph_structure": {
            "total_nodes": len(pattern.nodes),
            "total_relationships": len(pattern.relationships),
        },
    }

    fmt_node = _find_single_node_by_label(pattern, NodeLabel.OUTPUT_FORMAT)
    if fmt_node:
        result["format_name"] = _prop(fmt_node, "name")
        result["target_system"] = _prop(fmt_node, "target_system")
        result["file_format"] = _prop(fmt_node, "file_format")

        out_cols = extract_output_columns(pattern, fmt_node.id)
        out_cols_sorted = sorted(out_cols, key=lambda n: _prop(n, "position", 0))
        result["columns"] = [
            {"name": _prop(c, "name"), "position": _prop(c, "position")}
            for c in out_cols_sorted
        ]

        val_rules = extract_validation_rules(pattern, fmt_node.id)
        result["validation_rules"] = [
            {
                "name": _prop(v, "name"),
                "expression": _prop(v, "expression"),
                "scope": _prop(v, "scope"),
            }
            for v in val_rules
        ]

        entry_struct = extract_entry_structure(pattern, fmt_node.id)
        if entry_struct:
            result["entry_structure"] = {
                "grouping_column": _prop(entry_struct, "grouping_column"),
                "entry_separator": _prop(entry_struct, "entry_separator"),
                "date_column": _prop(entry_struct, "date_column"),
            }

    return result


# ============================================================================
# Build & Validation result summarizers
# ============================================================================

def summarize_build_result(
    validation_result: ValidationResult,
    save_counts: List[Dict[str, int]] | None,
    recipe_id: str,
    pattern: GraphPattern | None,
) -> Dict[str, Any]:
    """Summarize the result of build_and_save_pipeline for the tool response."""
    result: Dict[str, Any] = {
        "recipe_id": recipe_id,
        "gate1_validation": {
            "is_valid": validation_result.is_valid,
            "errors": list(validation_result.errors),
            "warnings": list(validation_result.warnings),
        },
    }

    if not validation_result.is_valid or save_counts is None:
        result["saved"] = False
        result["counts"] = None
        return result

    total_nodes = sum(r.get("nodes_created", 0) for r in save_counts)
    total_rels = sum(r.get("relationships_created", 0) for r in save_counts)
    total_props = sum(r.get("properties_set", 0) for r in save_counts)

    result["saved"] = True
    result["counts"] = {
        "nodes": len(pattern.nodes) if pattern else 0,
        "relationships": len(pattern.relationships) if pattern else 0,
        "nodes_created": total_nodes,
        "relationships_created": total_rels,
        "properties_set": total_props,
    }
    return result


def summarize_validation_result(
    entries_results: List[Dict[str, Any]],
    account_results: List[Dict[str, Any]],
    merged: ValidationResult,
) -> Dict[str, Any]:
    """Summarize the result of validate_entries for the tool response."""
    return {
        "gate2_validation": {
            "is_valid": merged.is_valid,
            "errors": list(merged.errors),
            "warnings": list(merged.warnings),
            "entries_checked": len(entries_results),
            "accounts_checked": len(account_results),
        },
        "entry_details": entries_results,
    }
