"""Validate Eval 1: Build Pipeline.

Connects to Neo4j and checks the agent-built recipe for structural correctness.

Usage: python evals/validators/validate_eval_01.py <recipe_id> <results_dir>
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from domain import NodeLabel, RelationshipType
from domain.logic import validate_recipe, validate_pipeline_connectivity, validate_output_format, extract_conditions_for_rule
from domain.ontology import ValidationResult, validate_node_properties
from domain.ontology_recipe import merged_ontology
from mcp_server.summarizers import summarize_processing_instructions
from persistence import Neo4jConnection, load_pattern_by_recipe


def validate(recipe_id: str, results_dir: str) -> dict:
    results_path = Path(results_dir)
    results_path.mkdir(parents=True, exist_ok=True)

    # Load chart of accounts for account code checking
    coa_path = Path(__file__).resolve().parent.parent / "fixtures" / "knowledge_zone" / "chart_of_accounts.json"
    with open(coa_path) as f:
        coa = json.load(f)
    valid_codes = {a["code"] for a in coa}

    report = {
        "eval": "eval_01_build_pipeline",
        "recipe_id": recipe_id,
        "checks": {},
        "scores": {},
        "total_score": 0.0,
    }

    # --- Check: Recipe loads ---
    try:
        conn = Neo4jConnection()
        conn.verify_connection()
        pattern = load_pattern_by_recipe(conn, recipe_id)
        conn.close()
    except Exception as e:
        report["checks"]["recipe_loads"] = {"pass": False, "error": str(e)}
        report["scores"]["recipe_saved"] = 0.0
        _write_report(report, results_path)
        return report

    if not pattern.nodes:
        report["checks"]["recipe_loads"] = {"pass": False, "error": "No nodes found"}
        report["scores"]["recipe_saved"] = 0.0
        _write_report(report, results_path)
        return report

    report["checks"]["recipe_loads"] = {
        "pass": True,
        "nodes": len(pattern.nodes),
        "relationships": len(pattern.relationships),
    }

    # --- Check: Node counts ---
    node_counts = {}
    for node in pattern.nodes:
        for label in node.labels:
            label_name = label.value if hasattr(label, "value") else str(label)
            node_counts[label_name] = node_counts.get(label_name, 0) + 1

    expected_minimums = {
        "SourceSchema": 1,
        "Column": 6,
        "Measure": 3,
        "MappingRule": 3,
        "AccountSlot": 6,
        "Account": 4,
    }

    count_pass = True
    count_details = {}
    for label_name, min_count in expected_minimums.items():
        actual = node_counts.get(label_name, 0)
        ok = actual >= min_count
        count_details[label_name] = {"expected_min": min_count, "actual": actual, "pass": ok}
        if not ok:
            count_pass = False

    report["checks"]["node_counts"] = {"pass": count_pass, "details": count_details}

    # --- Check: Relationship structure ---
    node_map = {n.id: n for n in pattern.nodes}
    rel_checks = {"pass": True, "details": []}

    # Every MappingRule should have DEBITS and CREDITS
    rule_nodes = [n for n in pattern.nodes if NodeLabel.MAPPING_RULE in n.labels]
    for rule in rule_nodes:
        has_debits = any(
            r.type == RelationshipType.DEBITS and r.start_node_id == rule.id
            for r in pattern.relationships
        )
        has_credits = any(
            r.type == RelationshipType.CREDITS and r.start_node_id == rule.id
            for r in pattern.relationships
        )
        if not has_debits or not has_credits:
            rel_checks["pass"] = False
            rel_checks["details"].append(
                f"Rule '{rule.properties.get('rule_name', rule.id)}' missing "
                f"{'DEBITS' if not has_debits else 'CREDITS'}"
            )

    # Every Measure should have AGGREGATES
    measure_nodes = [n for n in pattern.nodes if NodeLabel.MEASURE in n.labels]
    for m in measure_nodes:
        has_agg = any(
            r.type == RelationshipType.AGGREGATES and r.start_node_id == m.id
            for r in pattern.relationships
        )
        if not has_agg:
            rel_checks["pass"] = False
            rel_checks["details"].append(
                f"Measure '{m.properties.get('name', m.id)}' missing AGGREGATES"
            )

    # Recipe should have TRANSFORMS
    recipe_nodes = [n for n in pattern.nodes if NodeLabel.ACCOUNTING_RECIPE in n.labels]
    for rn in recipe_nodes:
        has_transforms = any(
            r.type == RelationshipType.TRANSFORMS and r.start_node_id == rn.id
            for r in pattern.relationships
        )
        if not has_transforms:
            rel_checks["pass"] = False
            rel_checks["details"].append("Recipe missing TRANSFORMS relationship")

    report["checks"]["relationship_structure"] = rel_checks

    # --- Check: Conditional rule (WHEN wiring) ---
    condition_nodes = [n for n in pattern.nodes if NodeLabel.CONDITION in n.labels]
    when_rels = [r for r in pattern.relationships if r.type == RelationshipType.WHEN]

    condition_props_ok = any(
        n.properties.get("column") == "department"
        and n.properties.get("operator") == "equals"
        and n.properties.get("value") == "Engineering"
        for n in condition_nodes
    )

    conditional_rule_exists = any(
        r.type == RelationshipType.WHEN and r.start_node_id in {n.id for n in rule_nodes}
        for r in pattern.relationships
    )

    roundtrip_ok = False
    try:
        pi = summarize_processing_instructions(pattern, recipe_id)
        rules_out = pi.get("rules", [])
        roundtrip_ok = any("conditions" in rule for rule in rules_out)
    except Exception:
        pass

    cond_all_pass = (
        len(condition_nodes) >= 1
        and len(when_rels) >= 1
        and condition_props_ok
        and conditional_rule_exists
        and roundtrip_ok
    )

    report["checks"]["conditional_rule"] = {
        "pass": cond_all_pass,
        "details": {
            "condition_node_count": len(condition_nodes),
            "when_rel_count": len(when_rels),
            "condition_props_ok": condition_props_ok,
            "conditional_rule_exists": conditional_rule_exists,
            "roundtrip_ok": roundtrip_ok,
        },
    }

    # --- Check: Account codes match chart_of_accounts ---
    account_nodes = [n for n in pattern.nodes if NodeLabel.ACCOUNT in n.labels]
    matched = 0
    total = len(account_nodes)
    unmatched = []
    for acct in account_nodes:
        code = acct.properties.get("code", "")
        if code in valid_codes:
            matched += 1
        else:
            unmatched.append(code)

    report["checks"]["account_codes"] = {
        "pass": matched == total,
        "matched": matched,
        "total": total,
        "unmatched": unmatched,
    }

    # --- Check: Gate 1 clean ---
    ontology = merged_ontology()
    validation_results = [
        validate_recipe(pattern),
        validate_pipeline_connectivity(pattern),
    ]
    has_output = any(NodeLabel.OUTPUT_FORMAT in n.labels for n in pattern.nodes)
    if has_output:
        validation_results.append(validate_output_format(pattern))
    node_results = [validate_node_properties(n, ontology) for n in pattern.nodes]
    validation_results.extend(node_results)
    merged = ValidationResult.merge(*validation_results)

    report["checks"]["gate1_clean"] = {
        "pass": merged.is_valid,
        "errors": list(merged.errors),
        "warnings": list(merged.warnings),
    }

    # --- Check: Output format completeness ---
    has_output_format = any(NodeLabel.OUTPUT_FORMAT in n.labels for n in pattern.nodes)
    has_output_columns = any(NodeLabel.OUTPUT_COLUMN in n.labels for n in pattern.nodes)
    has_validation_rule = any(NodeLabel.VALIDATION_RULE in n.labels for n in pattern.nodes)
    has_entry_structure = any(NodeLabel.ENTRY_STRUCTURE in n.labels for n in pattern.nodes)

    report["checks"]["output_completeness"] = {
        "pass": has_output_format and has_output_columns,
        "output_format": has_output_format,
        "output_columns": has_output_columns,
        "validation_rules": has_validation_rule,
        "entry_structure": has_entry_structure,
    }

    # --- Check: First-attempt success (from agent output) ---
    # The agent transcript from `claude --print` contains final text, not raw
    # tool call names. Check for both literal tool names and semantic evidence.
    agent_output_path = results_path / "eval_01_agent_output.txt"
    first_attempt = True
    ontology_consulted = False
    if agent_output_path.exists():
        agent_text = agent_output_path.read_text()
        agent_text_lower = agent_text.lower()
        # Count build_and_save_pipeline calls or retry evidence
        build_calls = agent_text.count("build_and_save_pipeline")
        retry_evidence = (
            "retry" in agent_text_lower
            or "failed validation" in agent_text_lower
            or "fix" in agent_text_lower and "error" in agent_text_lower
        )
        if build_calls > 1 or retry_evidence:
            first_attempt = False
        # Check ontology was read before build
        ontology_pos = max(
            agent_text.find("ontology://merged"),
            agent_text_lower.find("ontology"),
        )
        build_pos = max(
            agent_text.find("build_and_save_pipeline"),
            agent_text_lower.find("pipeline"),
        )
        if ontology_pos >= 0 and build_pos >= 0 and ontology_pos < build_pos:
            ontology_consulted = True

    report["checks"]["first_attempt"] = {"pass": first_attempt}
    report["checks"]["ontology_consulted"] = {"pass": ontology_consulted}

    # --- Scoring ---
    # Recipe saved successfully: 35%
    recipe_saved_score = 1.0 if report["checks"]["recipe_loads"]["pass"] else 0.0
    report["scores"]["recipe_saved"] = recipe_saved_score * 0.35

    # First-attempt success: 15%
    report["scores"]["first_attempt"] = (1.0 if first_attempt else 0.0) * 0.15

    # All mapping rules correct: 15%
    rules_correct = (
        report["checks"]["relationship_structure"]["pass"]
        and len(rule_nodes) >= 3
        and report["checks"]["account_codes"]["pass"]
    )
    report["scores"]["mapping_rules"] = (1.0 if rules_correct else 0.0) * 0.15

    # Conditional rule (WHEN wiring): 15%
    report["scores"]["conditional_rule"] = (1.0 if cond_all_pass else 0.0) * 0.15

    # Output format present: 10%
    report["scores"]["output_format"] = (1.0 if has_output_format and has_output_columns else 0.0) * 0.1

    # Ontology consulted first: 10%
    report["scores"]["ontology_consulted"] = (1.0 if ontology_consulted else 0.0) * 0.1

    report["total_score"] = sum(report["scores"].values())

    _write_report(report, results_path)
    return report


def _write_report(report: dict, results_path: Path):
    report_path = results_path / "eval_01_validation_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    # Print summary
    print(f"\n{'='*60}")
    print(f"  Eval 1: Build Pipeline — Validation Report")
    print(f"{'='*60}")
    print(f"  Recipe ID: {report['recipe_id']}")
    print()

    for check_name, check_data in report["checks"].items():
        status = "PASS" if check_data.get("pass") else "FAIL"
        print(f"  [{status}] {check_name}")
        if not check_data.get("pass") and "details" in check_data:
            for detail in check_data["details"]:
                print(f"         {detail}")
        if not check_data.get("pass") and "error" in check_data:
            print(f"         {check_data['error']}")

    print()
    print(f"  Scores:")
    for score_name, score_val in report["scores"].items():
        print(f"    {score_name}: {score_val:.1%}")
    print(f"  {'─'*40}")
    print(f"    TOTAL: {report['total_score']:.1%}")
    print(f"{'='*60}")

    print(f"\n  Full report: {report_path}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python evals/validators/validate_eval_01.py <recipe_id> <results_dir>")
        sys.exit(1)
    validate(sys.argv[1], sys.argv[2])
