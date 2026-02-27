# mcp_server/builders.py — Pure functions: JSON pipeline spec → domain objects
from __future__ import annotations

import json
from typing import Any

from domain.logic import (
    build_output_format_pattern,
    build_recipe_pattern,
    build_source_schema_pattern,
    compose_pipeline_pattern,
)
from domain.types import (
    GraphPattern,
    Node,
    NodeLabel,
    Relationship,
    RelationshipType,
)


def _generate_node_id(recipe_id: str, prefix: str, name: str) -> str:
    """Deterministic ID generation: e.g. 'payroll_monthly_v1_col_gross_pay'."""
    return f"{recipe_id}_{prefix}_{name}"


def _build_schema_nodes(
    schema_spec: dict[str, Any],
    recipe_id: str,
) -> tuple[Node, list[Node], list[Node], list[Relationship]]:
    """Build SourceSchema + Column + Measure nodes and all rels.

    Returns: (schema_node, column_nodes, measure_nodes, relationships)
    """
    schema_id = _generate_node_id(recipe_id, "schema", schema_spec["name"])

    schema_props: dict[str, Any] = {
        "recipe_id": recipe_id,
        "name": schema_spec["name"],
        "source_system": schema_spec["source_system"],
    }
    if schema_spec.get("file_pattern"):
        schema_props["file_pattern"] = schema_spec["file_pattern"]
    if schema_spec.get("row_grain"):
        schema_props["row_grain"] = schema_spec["row_grain"]

    schema_node = Node(
        id=schema_id,
        labels={NodeLabel.SOURCE_SCHEMA},
        properties=schema_props,
    )

    # Columns
    column_nodes: list[Node] = []
    col_rels: list[Relationship] = []
    for col_spec in schema_spec.get("columns", []):
        col_id = _generate_node_id(recipe_id, "col", col_spec["name"])
        col_props: dict[str, Any] = {
            "recipe_id": recipe_id,
            "name": col_spec["name"],
            "position": col_spec["position"],
            "data_type": col_spec["data_type"],
            "role": col_spec["role"],
        }
        if "required" in col_spec:
            col_props["required"] = col_spec["required"]
        if col_spec.get("description"):
            col_props["description"] = col_spec["description"]

        column_nodes.append(Node(id=col_id, labels={NodeLabel.COLUMN}, properties=col_props))
        col_rels.append(
            Relationship(
                id=_generate_node_id(recipe_id, "rel_has_col", col_spec["name"]),
                type=RelationshipType.HAS_COLUMN,
                start_node_id=schema_id,
                end_node_id=col_id,
                properties={},
            )
        )

    # Build a column name → column ID map for AGGREGATES
    col_name_to_id = {c.properties["name"]: c.id for c in column_nodes}

    # Measures
    measure_nodes: list[Node] = []
    msr_rels: list[Relationship] = []
    agg_rels: list[Relationship] = []
    for msr_spec in schema_spec.get("measures", []):
        msr_id = _generate_node_id(recipe_id, "msr", msr_spec["name"])
        msr_props: dict[str, Any] = {
            "recipe_id": recipe_id,
            "name": msr_spec["name"],
            "operation": msr_spec["operation"],
        }
        if msr_spec.get("description"):
            msr_props["description"] = msr_spec["description"]

        # Aggregation properties: group_by (array → JSON string), split_by, split_column
        group_by = msr_spec.get("group_by")
        if group_by:
            msr_props["group_by"] = json.dumps(group_by)
        if msr_spec.get("split_by"):
            msr_props["split_by"] = msr_spec["split_by"]
        if msr_spec.get("split_column"):
            msr_props["split_column"] = msr_spec["split_column"]

        measure_nodes.append(Node(id=msr_id, labels={NodeLabel.MEASURE}, properties=msr_props))
        msr_rels.append(
            Relationship(
                id=_generate_node_id(recipe_id, "rel_has_msr", msr_spec["name"]),
                type=RelationshipType.HAS_MEASURE,
                start_node_id=schema_id,
                end_node_id=msr_id,
                properties={},
            )
        )

        # AGGREGATES: measure → column
        source_col = msr_spec.get("source_column")
        if source_col and source_col in col_name_to_id:
            agg_rels.append(
                Relationship(
                    id=_generate_node_id(recipe_id, "rel_agg", msr_spec["name"]),
                    type=RelationshipType.AGGREGATES,
                    start_node_id=msr_id,
                    end_node_id=col_name_to_id[source_col],
                    properties={},
                )
            )

    all_rels = col_rels + msr_rels + agg_rels
    return schema_node, column_nodes, measure_nodes, all_rels


def _build_recipe_nodes(
    recipe_spec: dict[str, Any],
    schema_node_id: str,
    recipe_id: str,
) -> tuple[Node, list[Node], list[Node], list[Node], list[Node], list[Node], list[Relationship]]:
    """Build AccountingRecipe + MappingRule + AccountSlot + Account + Reference + Condition nodes and all rels.

    Returns: (recipe_node, rule_nodes, slot_nodes, account_nodes, reference_nodes, condition_nodes, relationships)
    """
    recipe_node_id = _generate_node_id(recipe_id, "recipe", recipe_spec["name"].replace(" ", "_").lower())

    recipe_props: dict[str, Any] = {
        "recipe_id": recipe_id,
        "name": recipe_spec["name"],
        "source_schema": recipe_spec.get("source_schema", ""),
    }
    if recipe_spec.get("batch_key"):
        recipe_props["batch_key"] = recipe_spec["batch_key"]
    if recipe_spec.get("journal_no_format"):
        recipe_props["journal_no_format"] = recipe_spec["journal_no_format"]
    if recipe_spec.get("visibility"):
        recipe_props["visibility"] = recipe_spec["visibility"]

    recipe_node = Node(
        id=recipe_node_id,
        labels={NodeLabel.ACCOUNTING_RECIPE},
        properties=recipe_props,
    )

    # TRANSFORMS: recipe → schema
    transforms_rel = Relationship(
        id=_generate_node_id(recipe_id, "rel_transforms", recipe_spec["name"].replace(" ", "_").lower()),
        type=RelationshipType.TRANSFORMS,
        start_node_id=recipe_node_id,
        end_node_id=schema_node_id,
        properties={},
    )

    rule_nodes: list[Node] = []
    slot_nodes: list[Node] = []
    account_nodes_map: dict[str, Node] = {}  # account_code → Node (dedup)
    reference_nodes_map: dict[str, Node] = {}  # ref id → Node
    condition_nodes: list[Node] = []
    condition_id_map: dict[str, str] = {}  # condition_id → node ID
    relationships: list[Relationship] = [transforms_rel]

    # Build condition nodes so rules can reference them via WHEN
    for cond_spec in recipe_spec.get("conditions", []):
        cond_id = _generate_node_id(recipe_id, "cond", cond_spec["condition_id"])
        cond_props: dict[str, Any] = {
            "recipe_id": recipe_id,
            "condition_id": cond_spec["condition_id"],
            "column": cond_spec["column"],
            "operator": cond_spec["operator"],
        }
        if cond_spec.get("value") is not None:
            cond_props["value"] = cond_spec["value"]
        condition_nodes.append(Node(id=cond_id, labels={NodeLabel.CONDITION}, properties=cond_props))
        condition_id_map[cond_spec["condition_id"]] = cond_id

    # Build reference nodes first so rules can link to them
    for ref_spec in recipe_spec.get("references", []):
        ref_id = _generate_node_id(recipe_id, "ref", ref_spec["id"])
        ref_props = dict(ref_spec.get("properties", {}))
        reference_nodes_map[ref_spec["id"]] = Node(
            id=ref_id,
            labels={NodeLabel.REFERENCE},
            properties=ref_props,
            extra_labels=frozenset({ref_spec["type"]}),
        )

    for rule_spec in recipe_spec.get("rules", []):
        # BUG-001: normalize plural/singular key variants and unwrap single-item lists.
        # Workaround for agents that send "debits":[{...}] instead of "debit":{...}.
        # TODO(sunset): remove once all callers conform to the singular-dict spec.
        rule_spec = dict(rule_spec)
        for singular, plural in [("debit", "debits"), ("credit", "credits")]:
            if plural in rule_spec and singular not in rule_spec:
                val = rule_spec.pop(plural)
                rule_spec[singular] = val[0] if isinstance(val, list) and len(val) == 1 else val
            elif singular in rule_spec and isinstance(rule_spec[singular], list):
                lst = rule_spec[singular]
                rule_spec[singular] = lst[0] if len(lst) == 1 else lst

        rule_id = _generate_node_id(recipe_id, "rule", rule_spec["rule_name"])
        rule_props: dict[str, Any] = {
            "recipe_id": recipe_id,
            "rule_name": rule_spec["rule_name"],
            "source_measure": rule_spec["source_measure"],
        }
        if "priority" in rule_spec:
            rule_props["priority"] = rule_spec["priority"]
        if rule_spec.get("memo_template"):
            rule_props["memo_template"] = rule_spec["memo_template"]

        rule_node = Node(id=rule_id, labels={NodeLabel.MAPPING_RULE}, properties=rule_props)
        rule_nodes.append(rule_node)

        # HAS_RULE: recipe → rule
        relationships.append(
            Relationship(
                id=_generate_node_id(recipe_id, "rel_has_rule", rule_spec["rule_name"]),
                type=RelationshipType.HAS_RULE,
                start_node_id=recipe_node_id,
                end_node_id=rule_id,
                properties={},
            )
        )

        # WHEN: rule → condition (optional)
        when_cond_id = rule_spec.get("when")
        if when_cond_id and when_cond_id in condition_id_map:
            relationships.append(
                Relationship(
                    id=_generate_node_id(recipe_id, "rel_when", rule_spec["rule_name"]),
                    type=RelationshipType.WHEN,
                    start_node_id=rule_id,
                    end_node_id=condition_id_map[when_cond_id],
                    properties={},
                )
            )

        # Validate both sides present before creating slots
        for required_key in ("debit", "credit"):
            if required_key not in rule_spec or rule_spec[required_key] is None:
                raise KeyError(
                    f"Rule '{rule_spec['rule_name']}' is missing '{required_key}'. "
                    f"Each rule must have both 'debit' and 'credit' (singular dict, not plural 'debits'/'credits')."
                )

        # Process debit and credit sides
        for side_key, rel_type in [("debit", RelationshipType.DEBITS), ("credit", RelationshipType.CREDITS)]:
            side_spec = rule_spec[side_key]

            slot_id_str = side_spec["slot_id"]
            slot_node_id = _generate_node_id(recipe_id, "slot", slot_id_str)
            slot_props: dict[str, Any] = {
                "recipe_id": recipe_id,
                "slot_id": slot_id_str,
                "role": side_spec["role"],
                "entry_type": side_key,
            }
            slot_node = Node(id=slot_node_id, labels={NodeLabel.ACCOUNT_SLOT}, properties=slot_props)
            slot_nodes.append(slot_node)

            # DEBITS/CREDITS: rule → slot
            relationships.append(
                Relationship(
                    id=_generate_node_id(recipe_id, f"rel_{side_key}", f"{rule_spec['rule_name']}_{slot_id_str}"),
                    type=rel_type,
                    start_node_id=rule_id,
                    end_node_id=slot_node_id,
                    properties={},
                )
            )

            # Account node (deduplicated by account_code)
            acct_code = side_spec.get("account_code")
            if acct_code:
                if acct_code not in account_nodes_map:
                    acct_id = _generate_node_id(recipe_id, "acct", acct_code)
                    acct_props: dict[str, Any] = {
                        "code": acct_code,
                        "name": side_spec.get("account_name", ""),
                        "account_type": side_spec.get("account_type", ""),
                        "normal_balance": side_spec.get("normal_balance", ""),
                        "is_active": True,
                    }
                    account_nodes_map[acct_code] = Node(
                        id=acct_id,
                        labels={NodeLabel.ACCOUNT},
                        properties=acct_props,
                    )

                # MAPPED_TO: slot → account
                acct_node = account_nodes_map[acct_code]
                relationships.append(
                    Relationship(
                        id=_generate_node_id(recipe_id, "rel_map", f"{slot_id_str}_{acct_code}"),
                        type=RelationshipType.MAPPED_TO,
                        start_node_id=slot_node_id,
                        end_node_id=acct_node.id,
                        properties={},
                    )
                )

        # USES_REFERENCE: rule → reference nodes
        for ref_key in rule_spec.get("uses_references", []):
            if ref_key in reference_nodes_map:
                ref_node = reference_nodes_map[ref_key]
                relationships.append(
                    Relationship(
                        id=_generate_node_id(recipe_id, "rel_uses_ref", f"{rule_spec['rule_name']}_{ref_key}"),
                        type=RelationshipType.USES_REFERENCE,
                        start_node_id=rule_id,
                        end_node_id=ref_node.id,
                        properties={},
                    )
                )

    account_nodes = list(account_nodes_map.values())
    reference_nodes = list(reference_nodes_map.values())
    return recipe_node, rule_nodes, slot_nodes, account_nodes, reference_nodes, condition_nodes, relationships


def _build_output_nodes(
    output_spec: dict[str, Any],
    format_id: str,
) -> tuple[Node, list[Node], list[Node], Node | None, list[Relationship]]:
    """Build OutputFormat + OutputColumn + ValidationRule + EntryStructure nodes and all rels.

    Returns: (format_node, column_nodes, validation_nodes, entry_structure_node, relationships)
    """
    fmt_id = _generate_node_id(format_id, "fmt", output_spec["name"])

    fmt_props: dict[str, Any] = {
        "format_id": format_id,
        "name": output_spec["name"],
        "target_system": output_spec["target_system"],
        "file_format": output_spec["file_format"],
    }
    if output_spec.get("version"):
        fmt_props["version"] = output_spec["version"]

    format_node = Node(id=fmt_id, labels={NodeLabel.OUTPUT_FORMAT}, properties=fmt_props)

    # Output columns
    column_nodes: list[Node] = []
    col_rels: list[Relationship] = []
    for col_spec in output_spec.get("columns", []):
        ocol_id = _generate_node_id(format_id, "ocol", col_spec["name"])
        ocol_props: dict[str, Any] = {
            "format_id": format_id,
            "name": col_spec["name"],
            "position": col_spec["position"],
            "data_type": col_spec["data_type"],
        }
        if "required" in col_spec:
            ocol_props["required"] = col_spec["required"]
        if col_spec.get("source_mapping"):
            ocol_props["source_mapping"] = col_spec["source_mapping"]

        column_nodes.append(Node(id=ocol_id, labels={NodeLabel.OUTPUT_COLUMN}, properties=ocol_props))
        col_rels.append(
            Relationship(
                id=_generate_node_id(format_id, "rel_fmt_col", col_spec["name"]),
                type=RelationshipType.HAS_COLUMN,
                start_node_id=fmt_id,
                end_node_id=ocol_id,
                properties={},
            )
        )

    # Validation rules
    validation_nodes: list[Node] = []
    val_rels: list[Relationship] = []
    for val_spec in output_spec.get("validation_rules", []):
        val_id = _generate_node_id(format_id, "val", val_spec["name"])
        val_props: dict[str, Any] = {
            "format_id": format_id,
            "name": val_spec["name"],
            "expression": val_spec["expression"],
            "scope": val_spec["scope"],
        }
        if val_spec.get("description"):
            val_props["description"] = val_spec["description"]

        validation_nodes.append(Node(id=val_id, labels={NodeLabel.VALIDATION_RULE}, properties=val_props))
        val_rels.append(
            Relationship(
                id=_generate_node_id(format_id, "rel_has_val", val_spec["name"]),
                type=RelationshipType.HAS_VALIDATION,
                start_node_id=fmt_id,
                end_node_id=val_id,
                properties={},
            )
        )

    # Entry structure
    entry_node: Node | None = None
    entry_rel: Relationship | None = None
    entry_spec = output_spec.get("entry_structure")
    if entry_spec:
        entry_id = _generate_node_id(format_id, "entry", output_spec["name"])
        entry_props: dict[str, Any] = {
            "format_id": format_id,
            "grouping_column": entry_spec["grouping_column"],
            "entry_separator": entry_spec["entry_separator"],
            "date_column": entry_spec["date_column"],
        }
        entry_node = Node(id=entry_id, labels={NodeLabel.ENTRY_STRUCTURE}, properties=entry_props)
        entry_rel = Relationship(
            id=_generate_node_id(format_id, "rel_has_entry", output_spec["name"]),
            type=RelationshipType.HAS_ENTRY_STRUCTURE,
            start_node_id=fmt_id,
            end_node_id=entry_id,
            properties={},
        )

    relationships = col_rels + val_rels
    if entry_rel:
        relationships.append(entry_rel)

    return format_node, column_nodes, validation_nodes, entry_node, relationships


def build_format_from_spec(spec: dict[str, Any]) -> GraphPattern:
    """Top-level: convert an output format spec → standalone GraphPattern.

    The spec must include format_id at the top level.
    """
    format_id = spec["format_id"]

    fmt_node, col_nodes, val_nodes, entry_node, output_rels = _build_output_nodes(
        spec,
        format_id,
    )

    col_rels = [r for r in output_rels if r.type == RelationshipType.HAS_COLUMN]
    val_rels = [r for r in output_rels if r.type == RelationshipType.HAS_VALIDATION]
    entry_rel = next(
        (r for r in output_rels if r.type == RelationshipType.HAS_ENTRY_STRUCTURE),
        None,
    )

    return build_output_format_pattern(
        format_node=fmt_node,
        column_nodes=col_nodes,
        column_rels=col_rels,
        validation_nodes=val_nodes if val_nodes else None,
        validation_rels=val_rels if val_rels else None,
        entry_structure_node=entry_node,
        entry_structure_rel=entry_rel,
    )


def build_pipeline_from_spec(spec: dict[str, Any]) -> GraphPattern:
    """Top-level: convert full pipeline spec → composed GraphPattern.

    Output format handling: if an 'output' key is present, it is built as a
    separate format pattern (using format_id derived from the output name)
    and composed into the pipeline for validation purposes.
    """
    recipe_id = spec["recipe_id"]

    # 1. Build schema subgraph
    schema_spec = spec["schema"]
    schema_node, col_nodes, msr_nodes, schema_rels = _build_schema_nodes(
        schema_spec,
        recipe_id,
    )

    # Separate relationship types for build_source_schema_pattern
    col_rels = [r for r in schema_rels if r.type == RelationshipType.HAS_COLUMN]
    msr_rels = [r for r in schema_rels if r.type == RelationshipType.HAS_MEASURE]
    agg_rels = [r for r in schema_rels if r.type == RelationshipType.AGGREGATES]

    schema_pattern = build_source_schema_pattern(
        schema_node=schema_node,
        column_nodes=col_nodes,
        measure_nodes=msr_nodes,
        column_rels=col_rels,
        measure_rels=msr_rels,
        aggregates_rels=agg_rels if agg_rels else None,
    )

    # 2. Build recipe subgraph
    recipe_spec = spec["recipe"]
    # Default source_schema to schema name if not provided
    if "source_schema" not in recipe_spec:
        recipe_spec = dict(recipe_spec, source_schema=schema_spec["name"])
    # Backward compat: conditions in schema_spec migrate silently to recipe_spec
    if "conditions" in schema_spec and "conditions" not in recipe_spec:
        recipe_spec = dict(recipe_spec, conditions=schema_spec["conditions"])

    recipe_node, rule_nodes, slot_nodes, account_nodes, ref_nodes, cond_nodes, recipe_rels = _build_recipe_nodes(
        recipe_spec,
        schema_node.id,
        recipe_id,
    )

    # Separate out TRANSFORMS for build_recipe_pattern
    transforms_rel = next(r for r in recipe_rels if r.type == RelationshipType.TRANSFORMS)
    rule_rels = [
        r
        for r in recipe_rels
        if r.type
        in (
            RelationshipType.HAS_RULE,
            RelationshipType.DEBITS,
            RelationshipType.CREDITS,
        )
    ]
    slot_rels = [r for r in recipe_rels if r.type == RelationshipType.MAPPED_TO]
    additional_rels = [
        r
        for r in recipe_rels
        if r.type
        in (
            RelationshipType.USES_REFERENCE,
            RelationshipType.WHEN,
        )
    ]

    additional_nodes: list[Node] = account_nodes + ref_nodes + cond_nodes

    recipe_pattern = build_recipe_pattern(
        recipe_node=recipe_node,
        schema_node=schema_node,
        transforms_rel=transforms_rel,
        rule_nodes=rule_nodes,
        rule_rels=rule_rels,
        slot_nodes=slot_nodes,
        slot_rels=slot_rels,
        additional_nodes=additional_nodes if additional_nodes else None,
        additional_rels=additional_rels if additional_rels else None,
    )

    # 3. Build output subgraph (backward compat — if 'output' key present,
    #    build as independent format and compose for validation)
    output_pattern = None
    if "output" in spec:
        output_spec = dict(spec["output"])
        # Derive format_id for backward compat
        if "format_id" not in output_spec:
            output_spec["format_id"] = output_spec.get("name", recipe_id)
        output_pattern = build_format_from_spec(output_spec)

    # 4. Compose full pipeline
    return compose_pipeline_pattern(schema_pattern, recipe_pattern, output_pattern)
