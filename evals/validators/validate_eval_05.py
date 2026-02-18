"""Validate Eval 5: Build Pipeline with Aggregation Properties.

Connects to Neo4j and checks that the agent-built recipe correctly stores
group_by and split_by on Measure nodes, and that they round-trip correctly
through summarize_processing_instructions (group_by as list, split_by as string).

Usage: python evals/validators/validate_eval_05.py <recipe_id> <results_dir>
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from domain import NodeLabel
from domain.logic import validate_recipe, validate_pipeline_connectivity
from domain.ontology import ValidationResult, validate_node_properties
from domain.ontology_recipe import merged_ontology
from mcp_server.summarizers import summarize_processing_instructions
from persistence import Neo4jConnection, load_pattern_by_recipe


def validate(recipe_id: str, results_dir: str) -> dict:
    results_path = Path(results_dir)
    results_path.mkdir(parents=True, exist_ok=True)

    report = {
        "eval": "eval_05_group_by_split_by",
        "recipe_id": recipe_id,
        "checks": {},
        "scores": {},
        "total_score": 0.0,
    }

    # --- Check: Recipe loads from Neo4j ---
    try:
        conn = Neo4jConnection()
        conn.verify_connection()
        pattern = load_pattern_by_recipe(conn, recipe_id)
        conn.close()
    except Exception as e:
        report["checks"]["recipe_loads"] = {"pass": False, "error": str(e)}
        report["scores"]["recipe_saved"] = 0.0
        report["scores"]["has_group_by"] = 0.0
        report["scores"]["group_by_roundtrip"] = 0.0
        report["scores"]["has_split_by"] = 0.0
        report["scores"]["gate1_clean"] = 0.0
        _write_report(report, results_path)
        return report

    if not pattern.nodes:
        report["checks"]["recipe_loads"] = {"pass": False, "error": "No nodes found"}
        report["scores"]["recipe_saved"] = 0.0
        report["scores"]["has_group_by"] = 0.0
        report["scores"]["group_by_roundtrip"] = 0.0
        report["scores"]["has_split_by"] = 0.0
        report["scores"]["gate1_clean"] = 0.0
        _write_report(report, results_path)
        return report

    report["checks"]["recipe_loads"] = {
        "pass": True,
        "nodes": len(pattern.nodes),
        "relationships": len(pattern.relationships),
    }

    # --- Check: Measure nodes with group_by ---
    measure_nodes = [n for n in pattern.nodes if NodeLabel.MEASURE in n.labels]

    group_by_measures = [m for m in measure_nodes if m.properties.get("group_by")]
    has_group_by = len(group_by_measures) > 0
    # group_by must be stored as a comma-separated string, not a list
    group_by_is_string = all(
        isinstance(m.properties.get("group_by"), str)
        for m in group_by_measures
    )

    report["checks"]["has_group_by"] = {
        "pass": has_group_by and group_by_is_string,
        "count": len(group_by_measures),
        "stored_as_string": group_by_is_string,
        "details": [
            {
                "name": m.properties.get("name"),
                "group_by": m.properties.get("group_by"),
            }
            for m in group_by_measures
        ],
    }

    # --- Check: Measure nodes with split_by ---
    split_by_measures = [m for m in measure_nodes if m.properties.get("split_by")]
    has_split_by = len(split_by_measures) > 0

    report["checks"]["has_split_by"] = {
        "pass": has_split_by,
        "count": len(split_by_measures),
        "details": [
            {
                "name": m.properties.get("name"),
                "split_by": m.properties.get("split_by"),
                "split_column": m.properties.get("split_column"),
            }
            for m in split_by_measures
        ],
    }

    # --- Check: Round-trip via summarize_processing_instructions ---
    # group_by must come back as a list (not a string); split_by as a string.
    roundtrip_ok = False
    roundtrip_details = {}
    try:
        instructions = summarize_processing_instructions(pattern, recipe_id)
        measures_out = instructions.get("measures", [])

        group_by_in_output = [m for m in measures_out if "group_by" in m]
        split_by_in_output = [m for m in measures_out if "split_by" in m]

        group_by_is_list = all(
            isinstance(m.get("group_by"), list)
            for m in group_by_in_output
        )
        split_by_is_string = all(
            isinstance(m.get("split_by"), str)
            for m in split_by_in_output
        )

        roundtrip_ok = (
            len(group_by_in_output) > 0
            and group_by_is_list
        )

        roundtrip_details = {
            "measures_with_group_by_in_output": len(group_by_in_output),
            "group_by_returned_as_list": group_by_is_list,
            "measures_with_split_by_in_output": len(split_by_in_output),
            "split_by_returned_as_string": split_by_is_string,
            "sample_group_by": group_by_in_output[0].get("group_by") if group_by_in_output else None,
        }
    except Exception as e:
        roundtrip_details = {"error": str(e)}

    report["checks"]["group_by_roundtrip"] = {
        "pass": roundtrip_ok,
        "details": roundtrip_details,
    }

    # --- Check: Gate 1 clean ---
    ontology = merged_ontology()
    validation_results = [
        validate_recipe(pattern),
        validate_pipeline_connectivity(pattern),
    ]
    node_results = [validate_node_properties(n, ontology) for n in pattern.nodes]
    validation_results.extend(node_results)
    merged = ValidationResult.merge(*validation_results)

    report["checks"]["gate1_clean"] = {
        "pass": merged.is_valid,
        "errors": list(merged.errors),
        "warnings": list(merged.warnings),
    }

    # --- Scoring ---
    # Recipe saved and loads: 30%
    report["scores"]["recipe_saved"] = 1.0 * 0.30

    # At least one measure has group_by stored as a string: 25%
    report["scores"]["has_group_by"] = (
        1.0 if (has_group_by and group_by_is_string) else 0.0
    ) * 0.25

    # group_by round-trips as a list via summarize_processing_instructions: 20%
    report["scores"]["group_by_roundtrip"] = (1.0 if roundtrip_ok else 0.0) * 0.20

    # At least one measure has split_by: 15%
    report["scores"]["has_split_by"] = (1.0 if has_split_by else 0.0) * 0.15

    # Gate 1 valid: 10%
    report["scores"]["gate1_clean"] = (1.0 if merged.is_valid else 0.0) * 0.10

    report["total_score"] = sum(report["scores"].values())

    _write_report(report, results_path)
    return report


def _write_report(report: dict, results_path: Path):
    report_path = results_path / "eval_05_validation_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"\n{'='*60}")
    print(f"  Eval 5: Group-By / Split-By — Validation Report")
    print(f"{'='*60}")
    print(f"  Recipe ID: {report['recipe_id']}")
    print()

    for check_name, check_data in report["checks"].items():
        status = "PASS" if check_data.get("pass") else "FAIL"
        print(f"  [{status}] {check_name}")
        if not check_data.get("pass") and "error" in check_data:
            print(f"         {check_data['error']}")
        if not check_data.get("pass") and "details" in check_data:
            details = check_data["details"]
            if isinstance(details, dict):
                for k, v in details.items():
                    print(f"         {k}: {v}")
            elif isinstance(details, list):
                for item in details:
                    print(f"         {item}")

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
        print("Usage: python evals/validators/validate_eval_05.py <recipe_id> <results_dir>")
        sys.exit(1)
    validate(sys.argv[1], sys.argv[2])