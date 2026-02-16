"""Standalone MCP client smoke test.

Connects to the FP_core MCP server as an external client over STDIO,
exercises all 4 tools, reads resources, and fetches prompts.
No internal codebase knowledge — only what the MCP protocol exposes.

Usage:
    cd dogfood/
    python mcp_smoke_test.py

Requires: NEO4J_URI and NEO4J_PASSWORD env vars for save/load tests.
Without Neo4j, build validation still runs (save will fail gracefully).
"""

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Project root for launching the server
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)

# ============================================================================
# Pipeline spec — same payroll scenario, defined purely as JSON
# ============================================================================

PIPELINE_SPEC = {
    "recipe_id": "smoke_test_payroll_v1",
    "schema": {
        "name": "payroll_export",
        "source_system": "csv_import",
        "file_pattern": "payroll_*.csv",
        "row_grain": "employee_pay_period",
        "columns": [
            {"name": "employee_id", "position": 1, "data_type": "string", "role": "identifier", "required": True},
            {"name": "pay_date", "position": 2, "data_type": "date", "role": "date", "required": True},
            {"name": "gross_pay", "position": 3, "data_type": "decimal", "role": "amount", "required": True},
            {"name": "tax_withheld", "position": 4, "data_type": "decimal", "role": "amount", "required": True},
            {"name": "net_pay", "position": 5, "data_type": "decimal", "role": "amount", "required": True},
            {"name": "department", "position": 6, "data_type": "string", "role": "category", "required": False},
        ],
        "measures": [
            {"name": "total_gross_pay", "operation": "sum", "source_column": "gross_pay"},
            {"name": "total_tax_withheld", "operation": "sum", "source_column": "tax_withheld"},
            {"name": "total_net_pay", "operation": "sum", "source_column": "net_pay"},
        ],
    },
    "recipe": {
        "name": "Monthly Payroll Journal",
        "source_schema": "payroll_export",
        "batch_key": "pay_date",
        "journal_no_format": "PY-{date:%Y%m}-{seq:04d}",
        "rules": [
            {
                "rule_name": "gross_pay_entry",
                "source_measure": "total_gross_pay",
                "priority": 1,
                "memo_template": "Salary expense - {pay_date:%B %Y}",
                "debit": {"slot_id": "salary_expense_debit", "role": "primary", "account_code": "6100", "account_name": "Salary Expense", "account_type": "expense", "normal_balance": "debit"},
                "credit": {"slot_id": "payroll_payable_credit_gross", "role": "offset", "account_code": "2100", "account_name": "Payroll Payable", "account_type": "liability", "normal_balance": "credit"},
            },
            {
                "rule_name": "tax_withholding_entry",
                "source_measure": "total_tax_withheld",
                "priority": 2,
                "memo_template": "Tax withholding - {pay_date:%B %Y}",
                "debit": {"slot_id": "payroll_payable_debit_tax", "role": "primary", "account_code": "2100", "account_name": "Payroll Payable", "account_type": "liability", "normal_balance": "credit"},
                "credit": {"slot_id": "tax_payable_credit", "role": "offset", "account_code": "2200", "account_name": "Tax Payable", "account_type": "liability", "normal_balance": "credit"},
            },
            {
                "rule_name": "net_pay_entry",
                "source_measure": "total_net_pay",
                "priority": 3,
                "memo_template": "Net pay disbursement - {pay_date:%B %Y}",
                "debit": {"slot_id": "payroll_payable_debit_net", "role": "primary", "account_code": "2100", "account_name": "Payroll Payable", "account_type": "liability", "normal_balance": "credit"},
                "credit": {"slot_id": "cash_credit", "role": "offset", "account_code": "1010", "account_name": "Cash", "account_type": "asset", "normal_balance": "debit"},
            },
        ],
    },
    "output": {
        "name": "journal_entry_export",
        "target_system": "quickbooks",
        "file_format": "csv",
        "columns": [
            {"name": "journal_number", "position": 1, "data_type": "string", "required": True, "source_mapping": "journal_no_format"},
            {"name": "journal_date", "position": 2, "data_type": "date", "required": True},
            {"name": "account_code", "position": 3, "data_type": "string", "required": True},
            {"name": "debit_amount", "position": 4, "data_type": "decimal", "required": True},
            {"name": "credit_amount", "position": 5, "data_type": "decimal", "required": True},
            {"name": "memo", "position": 6, "data_type": "string", "required": False},
        ],
        "validation_rules": [
            {"name": "balanced_entry", "expression": "SUM(debit_amount) == SUM(credit_amount)", "scope": "batch"},
        ],
        "batch": {
            "grouping_column": "journal_number",
            "entry_separator": "blank_row",
            "date_column": "journal_date",
        },
    },
}

BALANCED_ENTRIES = [
    {
        "lines": [
            {"account_code": "6100", "direction": "debit", "amount": "24500.00"},
            {"account_code": "2100", "direction": "credit", "amount": "24500.00"},
        ]
    },
    {
        "lines": [
            {"account_code": "2100", "direction": "debit", "amount": "6125.00"},
            {"account_code": "2200", "direction": "credit", "amount": "6125.00"},
        ]
    },
]

UNBALANCED_ENTRIES = [
    {
        "lines": [
            {"account_code": "6100", "direction": "debit", "amount": "1000.00"},
            {"account_code": "2100", "direction": "credit", "amount": "500.00"},
        ]
    },
]


# ============================================================================
# Helpers
# ============================================================================

def _print_section(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def _print_result(label: str, data: str):
    """Pretty-print a JSON tool result."""
    try:
        parsed = json.loads(data)
        print(f"\n--- {label} ---")
        print(json.dumps(parsed, indent=2))
    except json.JSONDecodeError:
        print(f"\n--- {label} (raw) ---")
        print(data)


def _extract_text(result) -> str:
    """Extract text content from a CallToolResult."""
    parts = []
    for block in result.content:
        if hasattr(block, "text"):
            parts.append(block.text)
    return "\n".join(parts)


# ============================================================================
# Test scenarios
# ============================================================================

async def test_list_capabilities(session: ClientSession):
    """List all tools, resources, and prompts the server exposes."""
    _print_section("Server Capabilities")

    tools = await session.list_tools()
    print(f"\nTools ({len(tools.tools)}):")
    for tool in tools.tools:
        print(f"  - {tool.name}: {tool.description[:80]}...")

    resources = await session.list_resources()
    print(f"\nResources ({len(resources.resources)}):")
    for res in resources.resources:
        print(f"  - {res.uri}: {res.name}")

    prompts = await session.list_prompts()
    print(f"\nPrompts ({len(prompts.prompts)}):")
    for prompt in prompts.prompts:
        print(f"  - {prompt.name}: {prompt.description}")


async def test_read_resources(session: ClientSession):
    """Read both MCP resources."""
    _print_section("Read Resources")

    ontology = await session.read_resource("ontology://merged")
    text = ontology.contents[0].text if ontology.contents else ""
    parsed = json.loads(text)
    print(f"\nontology://merged — {len(parsed)} entity schemas")
    print(f"  Labels: {', '.join(sorted(parsed.keys()))}")

    constraints = await session.read_resource("constraints://merged")
    text = constraints.contents[0].text if constraints.contents else ""
    parsed = json.loads(text)
    print(f"\nconstraints://merged — {len(parsed)} relationship types")
    print(f"  Types: {', '.join(sorted(parsed.keys()))}")


async def test_get_prompts(session: ClientSession):
    """Fetch each prompt template."""
    _print_section("Prompt Templates")

    for name, args in [
        ("build-pipeline", None),
        ("process-data", {"recipe_id": "smoke_test_payroll_v1"}),
        ("gate2-checklist", None),
    ]:
        result = await session.get_prompt(name, arguments=args)
        # Show first 3 lines of each prompt
        text = result.messages[0].content.text if result.messages else ""
        lines = text.strip().split("\n")[:3]
        print(f"\n--- {name} ---")
        for line in lines:
            print(f"  {line}")
        print(f"  ... ({len(text)} chars total)")


async def test_build_and_save(session: ClientSession) -> bool:
    """Build and save the payroll pipeline. Returns True if saved."""
    _print_section("build_and_save_pipeline")

    result = await session.call_tool(
        "build_and_save_pipeline",
        {"pipeline_spec": json.dumps(PIPELINE_SPEC)},
    )
    text = _extract_text(result)
    _print_result("Build result", text)

    parsed = json.loads(text)
    if "error" in parsed:
        print(f"\n  ** Save failed (expected without Neo4j): {parsed['error']}")
        return False
    if parsed.get("saved"):
        print("\n  ** Pipeline saved successfully!")
        return True
    if not parsed.get("gate1_validation", {}).get("is_valid"):
        print("\n  ** Gate 1 validation FAILED")
        return False
    return False


async def test_load_recipe(session: ClientSession):
    """Reload the pipeline from Neo4j."""
    _print_section("load_recipe (round-trip)")

    result = await session.call_tool(
        "load_recipe",
        {"recipe_id": "smoke_test_payroll_v1"},
    )
    text = _extract_text(result)
    _print_result("Load result", text)


async def test_get_instructions(session: ClientSession):
    """Get processing instructions from cached recipe."""
    _print_section("get_processing_instructions")

    result = await session.call_tool(
        "get_processing_instructions",
        {"recipe_id": "smoke_test_payroll_v1"},
    )
    text = _extract_text(result)
    _print_result("Instructions", text)


async def test_validate_balanced(session: ClientSession):
    """Validate balanced journal entries."""
    _print_section("validate_entries — balanced")

    result = await session.call_tool(
        "validate_entries",
        {
            "entries": json.dumps(BALANCED_ENTRIES),
            "recipe_id": "smoke_test_payroll_v1",
        },
    )
    text = _extract_text(result)
    _print_result("Balanced entries", text)

    parsed = json.loads(text)
    is_valid = parsed.get("gate2_validation", {}).get("is_valid")
    print(f"\n  ** Gate 2 result: {'PASS' if is_valid else 'FAIL'}")


async def test_validate_unbalanced(session: ClientSession):
    """Validate unbalanced journal entries (should fail)."""
    _print_section("validate_entries — unbalanced (expect FAIL)")

    result = await session.call_tool(
        "validate_entries",
        {"entries": json.dumps(UNBALANCED_ENTRIES)},
    )
    text = _extract_text(result)
    _print_result("Unbalanced entries", text)

    parsed = json.loads(text)
    is_valid = parsed.get("gate2_validation", {}).get("is_valid")
    print(f"\n  ** Gate 2 result: {'PASS' if is_valid else 'FAIL (expected)'}")


# ============================================================================
# Main
# ============================================================================

async def main():
    print("FP_core MCP Smoke Test")
    print(f"Server: python -m mcp_server (from {PROJECT_ROOT})")

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server"],
        cwd=PROJECT_ROOT,
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 1. Discover capabilities
            await test_list_capabilities(session)

            # 2. Read resources
            await test_read_resources(session)

            # 3. Fetch prompt templates
            await test_get_prompts(session)

            # 4. Build and save pipeline
            saved = await test_build_and_save(session)

            # 5. Round-trip: reload from Neo4j (only if save succeeded)
            if saved:
                await test_load_recipe(session)
                await test_get_instructions(session)
            else:
                print("\n  Skipping load/instructions (no Neo4j save)")

            # 6. Validate entries (works without Neo4j — pure validation)
            await test_validate_balanced(session)
            await test_validate_unbalanced(session)

            _print_section("DONE")
            print("\nAll smoke tests completed.")


if __name__ == "__main__":
    asyncio.run(main())
