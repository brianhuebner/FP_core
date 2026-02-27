"""Validate Eval 2: Process Data.

Reads the agent's output CSV and validates correctness against known expected values.

Usage: python evals/validators/validate_eval_02.py <results_dir>
"""

import csv
import json
import sys
from decimal import Decimal
from pathlib import Path

# Expected values from the fixture data (payroll_5emp_jan.csv)
EXPECTED_GROSS = Decimal("24500.00")  # 5500 + 4200 + 6800 + 3500 + 4500
EXPECTED_TAX = Decimal("6125.00")  # 1375 + 1050 + 1700 + 875 + 1125
EXPECTED_NET = Decimal("18375.00")  # 4125 + 3150 + 5100 + 2625 + 3375

EXPECTED_ACCOUNTS = {"6100", "2100", "2200", "1010"}

EXPECTED_COLUMNS = [
    "journal_number",
    "journal_date",
    "account_code",
    "debit_amount",
    "credit_amount",
    "memo",
]


def validate(results_dir: str) -> dict:
    results_path = Path(results_dir)
    results_path.mkdir(parents=True, exist_ok=True)

    report = {
        "eval": "eval_02_process_data",
        "checks": {},
        "scores": {},
        "total_score": 0.0,
    }

    # --- Check: Output file exists ---
    output_path = results_path / "eval_02_output.csv"
    if not output_path.exists():
        # Also check the evals/results/ directory directly
        alt_path = Path(__file__).resolve().parent.parent / "results" / "eval_02_output.csv"
        if alt_path.exists():
            output_path = alt_path
        else:
            report["checks"]["output_exists"] = {"pass": False, "error": "Output file not found"}
            report["scores"]["entries_balance"] = 0.0
            report["scores"]["correct_amounts"] = 0.0
            report["scores"]["gate2_invoked"] = 0.0
            report["scores"]["output_format"] = 0.0
            report["scores"]["processing_instructions"] = 0.0
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
        report["checks"]["output_exists"] = {"pass": False, "error": f"CSV parse error: {e}"}
        _write_report(report, results_path)
        return report

    # --- Check: Entry balance ---
    # Group lines by journal_number and check each entry balances
    entries = {}
    for row in rows:
        jn = row.get("journal_number", "unknown")
        if jn not in entries:
            entries[jn] = {"debits": Decimal("0"), "credits": Decimal("0"), "lines": []}
        dr = Decimal(row.get("debit_amount", "0") or "0")
        cr = Decimal(row.get("credit_amount", "0") or "0")
        entries[jn]["debits"] += dr
        entries[jn]["credits"] += cr
        entries[jn]["lines"].append(row)

    all_balanced = True
    balance_details = []
    for jn, entry in entries.items():
        balanced = entry["debits"] == entry["credits"]
        balance_details.append(
            {
                "journal_number": jn,
                "debits": str(entry["debits"]),
                "credits": str(entry["credits"]),
                "balanced": balanced,
            }
        )
        if not balanced:
            all_balanced = False

    report["checks"]["entry_balance"] = {
        "pass": all_balanced,
        "entries": balance_details,
    }

    # --- Check: Correct amounts ---
    total_debits = sum(Decimal(row.get("debit_amount", "0") or "0") for row in rows)
    total_credits = sum(Decimal(row.get("credit_amount", "0") or "0") for row in rows)

    # Collect per-account debit and credit totals
    account_totals = {}
    for row in rows:
        code = row.get("account_code", "")
        dr = Decimal(row.get("debit_amount", "0") or "0")
        cr = Decimal(row.get("credit_amount", "0") or "0")
        if code not in account_totals:
            account_totals[code] = {"debits": Decimal("0"), "credits": Decimal("0")}
        account_totals[code]["debits"] += dr
        account_totals[code]["credits"] += cr

    # Check gross: 6100 debit = 24500, 2100 credit includes 24500
    # Check tax: 2100 debit includes 6125, 2200 credit = 6125
    # Check net: 2100 debit includes 18375, 1010 credit = 18375
    amounts_correct = True
    amount_details = {}

    # 6100 (Salary Expense) should be debited for gross
    salary_dr = account_totals.get("6100", {}).get("debits", Decimal("0"))
    amount_details["6100_debit"] = {
        "expected": str(EXPECTED_GROSS),
        "actual": str(salary_dr),
        "pass": salary_dr == EXPECTED_GROSS,
    }
    if salary_dr != EXPECTED_GROSS:
        amounts_correct = False

    # 2200 (Tax Payable) should be credited for tax
    tax_cr = account_totals.get("2200", {}).get("credits", Decimal("0"))
    amount_details["2200_credit"] = {
        "expected": str(EXPECTED_TAX),
        "actual": str(tax_cr),
        "pass": tax_cr == EXPECTED_TAX,
    }
    if tax_cr != EXPECTED_TAX:
        amounts_correct = False

    # 1010 (Cash) should be credited for net
    cash_cr = account_totals.get("1010", {}).get("credits", Decimal("0"))
    amount_details["1010_credit"] = {
        "expected": str(EXPECTED_NET),
        "actual": str(cash_cr),
        "pass": cash_cr == EXPECTED_NET,
    }
    if cash_cr != EXPECTED_NET:
        amounts_correct = False

    # Total debits == total credits
    amount_details["totals_balanced"] = {
        "total_debits": str(total_debits),
        "total_credits": str(total_credits),
        "pass": total_debits == total_credits,
    }
    if total_debits != total_credits:
        amounts_correct = False

    report["checks"]["correct_amounts"] = {"pass": amounts_correct, "details": amount_details}

    # --- Check: Account codes ---
    used_codes = {row.get("account_code", "") for row in rows}
    codes_correct = used_codes == EXPECTED_ACCOUNTS
    report["checks"]["account_codes"] = {
        "pass": codes_correct,
        "expected": sorted(EXPECTED_ACCOUNTS),
        "actual": sorted(used_codes),
    }

    # --- Check: Entry count ---
    # 3 journal entries, 6 lines total
    entry_count_ok = len(entries) == 3
    line_count_ok = len(rows) == 6
    report["checks"]["entry_count"] = {
        "pass": entry_count_ok and line_count_ok,
        "entries": len(entries),
        "lines": len(rows),
        "expected_entries": 3,
        "expected_lines": 6,
    }

    # --- Check: Output columns ---
    columns_match = all(col in fieldnames for col in EXPECTED_COLUMNS)
    report["checks"]["output_columns"] = {
        "pass": columns_match,
        "expected": EXPECTED_COLUMNS,
        "actual": list(fieldnames),
    }

    # --- Check: Gate 2 invoked (from agent output) ---
    # The agent transcript from `claude --print` contains final text, not raw
    # tool call names. Check for both literal tool names and semantic evidence.
    agent_output_path = results_path / "eval_02_agent_output.txt"
    gate2_invoked = False
    processing_instructions_used = False
    if agent_output_path.exists():
        agent_text = agent_output_path.read_text().lower()
        gate2_invoked = "validate_entries" in agent_text or "gate 2" in agent_text or "gate2" in agent_text
        processing_instructions_used = (
            "get_processing_instructions" in agent_text or "processing instructions" in agent_text
        )

    report["checks"]["gate2_invoked"] = {"pass": gate2_invoked}
    report["checks"]["processing_instructions_used"] = {"pass": processing_instructions_used}

    # --- Scoring ---
    # All entries balance: 30%
    report["scores"]["entries_balance"] = (1.0 if all_balanced else 0.0) * 0.3

    # Correct amounts: 30%
    report["scores"]["correct_amounts"] = (1.0 if amounts_correct else 0.0) * 0.3

    # Gate 2 invoked: 15%
    report["scores"]["gate2_invoked"] = (1.0 if gate2_invoked else 0.0) * 0.15

    # Output format correct: 15%
    report["scores"]["output_format"] = (1.0 if columns_match else 0.0) * 0.15

    # Processing instructions used: 10%
    report["scores"]["processing_instructions"] = (1.0 if processing_instructions_used else 0.0) * 0.1

    report["total_score"] = sum(report["scores"].values())

    _write_report(report, results_path)
    return report


def _write_report(report: dict, results_path: Path):
    report_path = results_path / "eval_02_validation_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    # Print summary
    print(f"\n{'=' * 60}")
    print("  Eval 2: Process Data — Validation Report")
    print(f"{'=' * 60}")
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
    print("  Scores:")
    for score_name, score_val in report["scores"].items():
        print(f"    {score_name}: {score_val:.1%}")
    print(f"  {'─' * 40}")
    print(f"    TOTAL: {report['total_score']:.1%}")
    print(f"{'=' * 60}")

    print(f"\n  Full report: {report_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python evals/validators/validate_eval_02.py <results_dir>")
        sys.exit(1)
    validate(sys.argv[1])
