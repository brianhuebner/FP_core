"""Validate Eval 3: Build Output Format.

Connects to Neo4j and checks the agent-built output format for structural correctness.

Usage: python evals/validators/validate_eval_03.py <format_id> <results_dir>
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from domain import NodeLabel, RelationshipType
from domain.logic import validate_output_format
from domain.ontology import ValidationResult, validate_node_properties
from domain.ontology_recipe import merged_ontology
from persistence import Neo4jConnection
from persistence.operations import load_format_by_id


def validate(format_id: str, results_dir: str) -> dict:
    results_path = Path(results_dir)
    results_path.mkdir(parents=True, exist_ok=True)

    report = {
        "eval": "eval_03_build_format",
        "format_id": format_id,
        "checks": {},
        "scores": {},
        "total_score": 0.0,
    }

    # --- Check: Format loads ---
    try:
        conn = Neo4jConnection()
        conn.verify_connection()
        pattern = load_format_by_id(conn, format_id)
        conn.close()
    except Exception as e:
        report["checks"]["format_loads"] = {"pass": False, "error": str(e)}
        report["scores"]["format_loads"] = 0.0
        _write_report(report, results_path)
        return report

    if not pattern.nodes:
        report["checks"]["format_loads"] = {"pass": False, "error": "No nodes found"}
        report["scores"]["format_loads"] = 0.0
        _write_report(report, results_path)
        return report

    report["checks"]["format_loads"] = {
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

    expected = {
        "OutputFormat": (1, 1),     # exactly 1
        "OutputColumn": (6, 99),    # exactly 6
        "ValidationRule": (1, 99),  # at least 1
    }

    count_pass = True
    count_details = {}
    for label_name, (min_count, max_count) in expected.items():
        actual = node_counts.get(label_name, 0)
        ok = min_count <= actual <= max_count
        count_details[label_name] = {
            "expected_min": min_count,
            "actual": actual,
            "pass": ok,
        }
        if not ok:
            count_pass = False

    report["checks"]["node_counts"] = {"pass": count_pass, "details": count_details}

    # --- Check: EntryStructure present ---
    entry_nodes = [n for n in pattern.nodes if NodeLabel.ENTRY_STRUCTURE in n.labels]
    entry_present = len(entry_nodes) >= 1
    entry_details = {}
    if entry_present:
        entry_node = entry_nodes[0]
        entry_details = {
            "grouping_column": entry_node.properties.get("grouping_column"),
            "entry_separator": entry_node.properties.get("entry_separator"),
            "date_column": entry_node.properties.get("date_column"),
        }
        # Verify key properties are present
        if not all(entry_details.values()):
            entry_present = False
            entry_details["error"] = "Missing required properties"

    report["checks"]["entry_structure_present"] = {
        "pass": entry_present,
        "details": entry_details,
    }

    # --- Check: Gate 1 clean ---
    ontology = merged_ontology()
    validation_results = [
        validate_output_format(pattern),
    ]
    node_results = [validate_node_properties(n, ontology) for n in pattern.nodes]
    validation_results.extend(node_results)
    merged = ValidationResult.merge(*validation_results)

    report["checks"]["gate1_clean"] = {
        "pass": merged.is_valid,
        "errors": list(merged.errors),
        "warnings": list(merged.warnings),
    }

    # --- Check: First-attempt success (from agent output) ---
    agent_output_path = results_path / "eval_03_agent_output.txt"
    first_attempt = True
    ontology_consulted = False
    if agent_output_path.exists():
        agent_text = agent_output_path.read_text()
        agent_text_lower = agent_text.lower()
        # Count build_output calls or retry evidence
        build_calls = agent_text.count("build_output")
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
            agent_text.find("build_output"),
            agent_text_lower.find("output format"),
        )
        if ontology_pos >= 0 and build_pos >= 0 and ontology_pos < build_pos:
            ontology_consulted = True

    report["checks"]["first_attempt"] = {"pass": first_attempt}
    report["checks"]["ontology_consulted"] = {"pass": ontology_consulted}

    # --- Scoring ---
    # Format found in Neo4j: 30%
    report["scores"]["format_loads"] = (
        1.0 if report["checks"]["format_loads"]["pass"] else 0.0
    ) * 0.3

    # Node counts correct: 20%
    report["scores"]["node_counts"] = (1.0 if count_pass else 0.0) * 0.2

    # EntryStructure present with correct properties: 10%
    report["scores"]["entry_structure_present"] = (
        1.0 if entry_present else 0.0
    ) * 0.1

    # Gate 1 clean: 15%
    report["scores"]["gate1_clean"] = (
        1.0 if merged.is_valid else 0.0
    ) * 0.15

    # First-attempt success: 15%
    report["scores"]["first_attempt"] = (1.0 if first_attempt else 0.0) * 0.15

    # Ontology consulted: 10%
    report["scores"]["ontology_consulted"] = (
        1.0 if ontology_consulted else 0.0
    ) * 0.1

    report["total_score"] = sum(report["scores"].values())

    _write_report(report, results_path)
    return report


def _write_report(report: dict, results_path: Path):
    report_path = results_path / "eval_03_validation_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    # Print summary
    print(f"\n{'='*60}")
    print(f"  Eval 3: Build Output Format — Validation Report")
    print(f"{'='*60}")
    print(f"  Format ID: {report['format_id']}")
    print()

    for check_name, check_data in report["checks"].items():
        status = "PASS" if check_data.get("pass") else "FAIL"
        print(f"  [{status}] {check_name}")
        if not check_data.get("pass") and "details" in check_data:
            details = check_data["details"]
            if isinstance(details, dict):
                for k, v in details.items():
                    if isinstance(v, dict) and not v.get("pass", True):
                        print(f"         {k}: expected min {v.get('expected_min')}, got {v.get('actual')}")
                    elif k == "error":
                        print(f"         {v}")
        if not check_data.get("pass") and "error" in check_data:
            print(f"         {check_data['error']}")
        if not check_data.get("pass") and "errors" in check_data:
            for err in check_data["errors"]:
                print(f"         {err}")

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
        print("Usage: python evals/validators/validate_eval_03.py <format_id> <results_dir>")
        sys.exit(1)
    validate(sys.argv[1], sys.argv[2])
