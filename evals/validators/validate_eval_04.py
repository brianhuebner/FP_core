"""Validate Eval 4: Process Data with Independent Format.

Validates that the agent built a standalone format, used it with the recipe,
and produced correct journal entries.

Usage: python evals/validators/validate_eval_04.py <format_id> <results_dir>
"""

import csv
import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from domain import NodeLabel
from domain.logic import validate_output_format
from domain.ontology import ValidationResult, validate_node_properties
from domain.ontology_recipe import merged_ontology
from persistence import Neo4jConnection
from persistence.operations import load_format_by_id


# Expected values from the fixture data (payroll_5emp_jan.csv)
EXPECTED_GROSS = Decimal("24500.00")  # 5500 + 4200 + 6800 + 3500 + 4500
EXPECTED_TAX = Decimal("6125.00")     # 1375 + 1050 + 1700 + 875 + 1125
EXPECTED_NET = Decimal("18375.00")    # 4125 + 3150 + 5100 + 2625 + 3375

EXPECTED_COLUMNS = [
    "journal_number", "journal_date", "account_code",
    "debit_amount", "credit_amount", "memo",
]


def validate(format_id: str, results_dir: str) -> dict:
    results_path = Path(results_dir)
    results_path.mkdir(parents=True, exist_ok=True)

    report = {
        "eval": "eval_04_process_with_format",
        "format_id": format_id,
        "checks": {},
        "scores": {},
        "total_score": 0.0,
    }

    # --- Check: Format built independently ---
    format_exists = False
    try:
        conn = Neo4jConnection()
        conn.verify_connection()
        pattern = load_format_by_id(conn, format_id)
        conn.close()
        if pattern.nodes:
            format_exists = True
            # Verify it has the expected structure
            has_fmt = any(NodeLabel.OUTPUT_FORMAT in n.labels for n in pattern.nodes)
            has_cols = any(NodeLabel.OUTPUT_COLUMN in n.labels for n in pattern.nodes)
            format_exists = has_fmt and has_cols
    except Exception as e:
        report["checks"]["format_built_independently"] = {
            "pass": False, "error": str(e),
        }

    if format_exists:
        # Gate 1 on the format
        ontology = merged_ontology()
        fmt_validation = [validate_output_format(pattern)]
        fmt_validation.extend(
            validate_node_properties(n, ontology) for n in pattern.nodes
        )
        fmt_merged = ValidationResult.merge(*fmt_validation)
        report["checks"]["format_built_independently"] = {
            "pass": True,
            "nodes": len(pattern.nodes),
            "relationships": len(pattern.relationships),
            "gate1_clean": fmt_merged.is_valid,
        }
    elif "format_built_independently" not in report["checks"]:
        report["checks"]["format_built_independently"] = {
            "pass": False,
            "error": "No format nodes found",
        }

    # --- Check: Output file exists ---
    output_path = results_path / "eval_04_output.csv"
    if not output_path.exists():
        alt_path = Path(__file__).resolve().parent.parent / "results" / "eval_04_output.csv"
        if alt_path.exists():
            output_path = alt_path
        else:
            report["checks"]["output_exists"] = {
                "pass": False, "error": "Output file not found",
            }
            report["scores"]["format_built_independently"] = 0.0
            report["scores"]["entries_balance"] = 0.0
            report["scores"]["correct_amounts"] = 0.0
            report["scores"]["output_columns"] = 0.0
            report["scores"]["format_id_used"] = 0.0
            report["scores"]["gate2_invoked"] = 0.0
            report["scores"]["build_output_used"] = 0.0
            _write_report(report, results_path)
            return report

    report["checks"]["output_exists"] = {"pass": True, "path": str(output_path)}

    # Parse the CSV
    try:
        with open(output_path, newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            fieldnames = reader.fieldnames or []
    except Exception as e:
        report["checks"]["output_exists"] = {
            "pass": False, "error": f"CSV parse error: {e}",
        }
        _write_report(report, results_path)
        return report

    # --- Check: Entry balance ---
    entries = {}
    for row in rows:
        jn = row.get("journal_number", "unknown")
        if jn not in entries:
            entries[jn] = {"debits": Decimal("0"), "credits": Decimal("0")}
        dr = Decimal(row.get("debit_amount", "0") or "0")
        cr = Decimal(row.get("credit_amount", "0") or "0")
        entries[jn]["debits"] += dr
        entries[jn]["credits"] += cr

    all_balanced = True
    balance_details = []
    for jn, entry in entries.items():
        balanced = entry["debits"] == entry["credits"]
        balance_details.append({
            "journal_number": jn,
            "debits": str(entry["debits"]),
            "credits": str(entry["credits"]),
            "balanced": balanced,
        })
        if not balanced:
            all_balanced = False

    report["checks"]["entries_balance"] = {
        "pass": all_balanced,
        "entries": balance_details,
    }

    # --- Check: Correct amounts ---
    account_totals = {}
    for row in rows:
        code = row.get("account_code", "")
        dr = Decimal(row.get("debit_amount", "0") or "0")
        cr = Decimal(row.get("credit_amount", "0") or "0")
        if code not in account_totals:
            account_totals[code] = {"debits": Decimal("0"), "credits": Decimal("0")}
        account_totals[code]["debits"] += dr
        account_totals[code]["credits"] += cr

    amounts_correct = True
    amount_details = {}

    # 6100 (Salary Expense) debit = 24500
    salary_dr = account_totals.get("6100", {}).get("debits", Decimal("0"))
    amount_details["6100_debit"] = {
        "expected": str(EXPECTED_GROSS),
        "actual": str(salary_dr),
        "pass": salary_dr == EXPECTED_GROSS,
    }
    if salary_dr != EXPECTED_GROSS:
        amounts_correct = False

    # 2200 (Tax Payable) credit = 6125
    tax_cr = account_totals.get("2200", {}).get("credits", Decimal("0"))
    amount_details["2200_credit"] = {
        "expected": str(EXPECTED_TAX),
        "actual": str(tax_cr),
        "pass": tax_cr == EXPECTED_TAX,
    }
    if tax_cr != EXPECTED_TAX:
        amounts_correct = False

    # 1010 (Cash) credit = 18375
    cash_cr = account_totals.get("1010", {}).get("credits", Decimal("0"))
    amount_details["1010_credit"] = {
        "expected": str(EXPECTED_NET),
        "actual": str(cash_cr),
        "pass": cash_cr == EXPECTED_NET,
    }
    if cash_cr != EXPECTED_NET:
        amounts_correct = False

    report["checks"]["correct_amounts"] = {
        "pass": amounts_correct, "details": amount_details,
    }

    # --- Check: Output columns ---
    columns_match = all(col in fieldnames for col in EXPECTED_COLUMNS)
    report["checks"]["output_columns"] = {
        "pass": columns_match,
        "expected": EXPECTED_COLUMNS,
        "actual": list(fieldnames),
    }

    # --- Check: Agent behavior (from agent output) ---
    agent_output_path = results_path / "eval_04_agent_output.txt"
    format_id_used = False
    gate2_invoked = False
    build_output_used = False

    if agent_output_path.exists():
        agent_text = agent_output_path.read_text()
        agent_text_lower = agent_text.lower()

        # Check format_id was passed to get_processing_instructions
        format_id_used = (
            "format_id" in agent_text
            and "get_processing_instructions" in agent_text_lower
        )

        # Check gate 2 invoked
        gate2_invoked = (
            "validate_entries" in agent_text
            or "gate 2" in agent_text_lower
            or "gate2" in agent_text_lower
        )

        # Check build_output was used (not build_and_save_pipeline for format)
        build_output_used = "build_output" in agent_text

    report["checks"]["format_id_used"] = {"pass": format_id_used}
    report["checks"]["gate2_invoked"] = {"pass": gate2_invoked}
    report["checks"]["build_output_used"] = {"pass": build_output_used}

    # --- Scoring ---
    # Format built independently: 15%
    report["scores"]["format_built_independently"] = (
        1.0 if report["checks"]["format_built_independently"]["pass"] else 0.0
    ) * 0.15

    # All entries balance: 20%
    report["scores"]["entries_balance"] = (
        1.0 if all_balanced else 0.0
    ) * 0.2

    # Correct amounts: 20%
    report["scores"]["correct_amounts"] = (
        1.0 if amounts_correct else 0.0
    ) * 0.2

    # Output columns correct: 10%
    report["scores"]["output_columns"] = (
        1.0 if columns_match else 0.0
    ) * 0.1

    # format_id used in get_processing_instructions: 15%
    report["scores"]["format_id_used"] = (
        1.0 if format_id_used else 0.0
    ) * 0.15

    # Gate 2 invoked: 10%
    report["scores"]["gate2_invoked"] = (
        1.0 if gate2_invoked else 0.0
    ) * 0.1

    # build_output used: 10%
    report["scores"]["build_output_used"] = (
        1.0 if build_output_used else 0.0
    ) * 0.1

    report["total_score"] = sum(report["scores"].values())

    _write_report(report, results_path)
    return report


def _write_report(report: dict, results_path: Path):
    report_path = results_path / "eval_04_validation_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    # Print summary
    print(f"\n{'='*60}")
    print(f"  Eval 4: Process with Format — Validation Report")
    print(f"{'='*60}")
    print(f"  Format ID: {report['format_id']}")
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
                    if isinstance(v, dict) and not v.get("pass", True):
                        print(f"         {k}: expected {v.get('expected')}, got {v.get('actual')}")
            elif isinstance(details, list):
                for item in details:
                    if isinstance(item, dict) and not item.get("balanced", True):
                        print(f"         {item.get('journal_number')}: DR={item['debits']} CR={item['credits']}")

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
        print("Usage: python evals/validators/validate_eval_04.py <format_id> <results_dir>")
        sys.exit(1)
    validate(sys.argv[1], sys.argv[2])
