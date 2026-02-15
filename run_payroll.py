"""Process sample payroll data through the recipe graph → journal entry export.

Demonstrates how the knowledge graph drives data processing:
  1. Load the recipe graph from Neo4j (Layer 4)
  2. Extract processing instructions from graph structure (Layer 3 extractors)
  3. Apply those instructions to sample data
  4. Produce a formatted journal entry CSV

This is what a future Layer 5 execution engine would automate.
"""

import csv
import io
import sys
from decimal import Decimal

from domain import (
    NodeLabel,
    RelationshipType,
    extract_batch_format,
    extract_debit_credit_slots,
    extract_measures_for_schema,
    extract_output_columns,
    extract_validation_rules,
)
from persistence import Neo4jConnection, load_pattern_by_recipe

RECIPE_ID = "payroll_monthly_v1"


# =============================================================================
# SAMPLE PAYROLL DATA
# =============================================================================

PAYROLL_DATA = [
    {"employee_id": "EMP001", "pay_date": "2026-01-31", "gross_pay": Decimal("5000.00"),
     "tax_withheld": Decimal("1250.00"), "net_pay": Decimal("3750.00"), "department": "Engineering"},
    {"employee_id": "EMP002", "pay_date": "2026-01-31", "gross_pay": Decimal("4500.00"),
     "tax_withheld": Decimal("1125.00"), "net_pay": Decimal("3375.00"), "department": "Marketing"},
    {"employee_id": "EMP003", "pay_date": "2026-01-31", "gross_pay": Decimal("6000.00"),
     "tax_withheld": Decimal("1500.00"), "net_pay": Decimal("4500.00"), "department": "Engineering"},
    {"employee_id": "EMP004", "pay_date": "2026-01-31", "gross_pay": Decimal("3800.00"),
     "tax_withheld": Decimal("950.00"),  "net_pay": Decimal("2850.00"), "department": "Sales"},
    {"employee_id": "EMP005", "pay_date": "2026-01-31", "gross_pay": Decimal("5200.00"),
     "tax_withheld": Decimal("1300.00"), "net_pay": Decimal("3900.00"), "department": "Operations"},
]


# =============================================================================
# STEP 1: Load the recipe graph from Neo4j
# =============================================================================

print("--- Step 1: Load recipe graph from Neo4j ---\n")

try:
    conn = Neo4jConnection()
    conn.verify_connection()
except Exception as e:
    print(f"Could not connect to Neo4j: {e}")
    print("Set NEO4J_URI and NEO4J_PASSWORD env vars.")
    sys.exit(1)

pipeline = load_pattern_by_recipe(conn, RECIPE_ID)
conn.close()

print(f"Loaded: {len(pipeline.nodes)} nodes, {len(pipeline.relationships)} relationships\n")

# Build lookup helpers
node_map = {n.id: n for n in pipeline.nodes}


# =============================================================================
# STEP 2: Extract processing instructions from the graph
# =============================================================================

print("--- Step 2: Extract processing instructions from graph ---\n")

# Find the SourceSchema
schema_node = next(
    n for n in pipeline.nodes if NodeLabel.SOURCE_SCHEMA in n.labels
)
print(f"Source schema: {schema_node.properties['name']}")
print(f"  file_pattern: {schema_node.properties.get('file_pattern')}")
print(f"  row_grain:    {schema_node.properties.get('row_grain')}")

# Extract columns (from HAS_COLUMN relationships)
schema_columns = [
    node_map[rel.end_node_id]
    for rel in pipeline.relationships
    if rel.type == RelationshipType.HAS_COLUMN
    and rel.start_node_id == schema_node.id
    and NodeLabel.COLUMN in node_map.get(rel.end_node_id, node_map[rel.end_node_id]).labels
]
schema_columns.sort(key=lambda n: n.properties.get("position", 0))
print(f"  columns: {[c.properties['name'] for c in schema_columns]}")

# Extract measures using Layer 3
measures = extract_measures_for_schema(pipeline, schema_node.id)
print(f"  measures: {[m.properties['name'] for m in measures]}")

# Find the recipe node and its mapping rules
recipe_node = next(
    n for n in pipeline.nodes if NodeLabel.ACCOUNTING_RECIPE in n.labels
)
print(f"\nRecipe: {recipe_node.properties['name']}")
print(f"  journal_no_format: {recipe_node.properties.get('journal_no_format')}")
print(f"  batch_key: {recipe_node.properties.get('batch_key')}")

# Extract mapping rules (via HAS_RULE from recipe)
rule_ids = [
    rel.end_node_id
    for rel in pipeline.relationships
    if rel.type == RelationshipType.HAS_RULE and rel.start_node_id == recipe_node.id
]
rule_nodes = [node_map[rid] for rid in rule_ids]
rule_nodes.sort(key=lambda n: n.properties.get("priority", 0))

print(f"\n  Mapping rules ({len(rule_nodes)}):")
for rule in rule_nodes:
    debit_slots, credit_slots = extract_debit_credit_slots(pipeline, rule.id)
    # Resolve account for each slot via MAPPED_TO
    def resolve_account(slot):
        for rel in pipeline.relationships:
            if rel.type == RelationshipType.MAPPED_TO and rel.start_node_id == slot.id:
                acct = node_map.get(rel.end_node_id)
                if acct:
                    return acct
        return None

    dr_accounts = [(s, resolve_account(s)) for s in debit_slots]
    cr_accounts = [(s, resolve_account(s)) for s in credit_slots]

    print(f"    [{rule.properties['priority']}] {rule.properties['rule_name']}")
    print(f"        source_measure: {rule.properties['source_measure']}")
    for slot, acct in dr_accounts:
        acct_str = f"{acct.properties['code']} {acct.properties['name']}" if acct else "?"
        print(f"        DR → {acct_str}")
    for slot, acct in cr_accounts:
        acct_str = f"{acct.properties['code']} {acct.properties['name']}" if acct else "?"
        print(f"        CR → {acct_str}")
    print(f"        memo: {rule.properties.get('memo_template', '')}")

# Extract output format
fmt_node = next(
    (n for n in pipeline.nodes if NodeLabel.OUTPUT_FORMAT in n.labels), None
)
if fmt_node:
    out_cols = extract_output_columns(pipeline, fmt_node.id)
    out_cols_sorted = sorted(out_cols, key=lambda n: n.properties.get("position", 0))
    val_rules = extract_validation_rules(pipeline, fmt_node.id)
    batch_fmt = extract_batch_format(pipeline, fmt_node.id)

    print(f"\nOutput format: {fmt_node.properties['name']}")
    print(f"  target_system: {fmt_node.properties['target_system']}")
    print(f"  file_format:   {fmt_node.properties['file_format']}")
    print(f"  columns: {[c.properties['name'] for c in out_cols_sorted]}")
    if val_rules:
        print(f"  validation: {[v.properties['name'] for v in val_rules]}")
    if batch_fmt:
        print(f"  batch: group by '{batch_fmt.properties['grouping_column']}', "
              f"sep='{batch_fmt.properties['entry_separator']}'")


# =============================================================================
# STEP 3: Process the sample data using graph-extracted instructions
# =============================================================================

print("\n\n--- Step 3: Process sample data ---\n")

# Show the raw data
print(f"Input: {len(PAYROLL_DATA)} payroll rows")
for row in PAYROLL_DATA:
    print(f"  {row['employee_id']}  {row['department']:12s}  "
          f"gross={row['gross_pay']:>9}  tax={row['tax_withheld']:>8}  net={row['net_pay']:>9}")

# Compute measures (the graph told us to SUM these columns)
measure_values = {}
for measure in measures:
    measure_name = measure.properties["name"]
    operation = measure.properties["operation"]
    # Find which column this measure aggregates (via AGGREGATES relationship)
    agg_col_id = next(
        (rel.end_node_id for rel in pipeline.relationships
         if rel.type == RelationshipType.AGGREGATES and rel.start_node_id == measure.id),
        None,
    )
    if agg_col_id:
        col_name = node_map[agg_col_id].properties["name"]
        if operation == "sum":
            measure_values[measure_name] = sum(row[col_name] for row in PAYROLL_DATA)

print(f"\nComputed measures:")
for name, val in measure_values.items():
    print(f"  {name}: {val:,.2f}")

# Verify: gross = tax + net
total_gross = measure_values.get("total_gross_pay", Decimal("0"))
total_tax = measure_values.get("total_tax_withheld", Decimal("0"))
total_net = measure_values.get("total_net_pay", Decimal("0"))
print(f"\n  Check: {total_gross:,.2f} = {total_tax:,.2f} + {total_net:,.2f} → "
      f"{'OK' if total_gross == total_tax + total_net else 'MISMATCH'}")


# =============================================================================
# STEP 4: Generate journal entries from mapping rules
# =============================================================================

print("\n\n--- Step 4: Generate journal entries ---\n")

pay_date = PAYROLL_DATA[0]["pay_date"]
journal_no_format = recipe_node.properties.get("journal_no_format", "JE-{seq:04d}")

journal_lines = []
journal_seq = 1

for rule in rule_nodes:
    rule_name = rule.properties["rule_name"]
    source_measure = rule.properties["source_measure"]
    memo = rule.properties.get("memo_template", "")
    # Simple template substitution for the memo
    memo = memo.replace("{pay_date:%B %Y}", "January 2026")

    amount = measure_values.get(source_measure, Decimal("0"))
    if amount == 0:
        continue

    journal_no = journal_no_format.replace("{date:%Y%m}", "202601").replace(
        "{seq:04d}", f"{journal_seq:04d}"
    )

    debit_slots, credit_slots = extract_debit_credit_slots(pipeline, rule.id)

    # Debit line(s)
    for slot in debit_slots:
        acct = resolve_account(slot)
        if acct:
            journal_lines.append({
                "journal_number": journal_no,
                "journal_date": pay_date,
                "account_code": acct.properties["code"],
                "debit_amount": amount,
                "credit_amount": Decimal("0.00"),
                "memo": memo,
                "_rule": rule_name,
                "_account_name": acct.properties["name"],
            })

    # Credit line(s)
    for slot in credit_slots:
        acct = resolve_account(slot)
        if acct:
            journal_lines.append({
                "journal_number": journal_no,
                "journal_date": pay_date,
                "account_code": acct.properties["code"],
                "debit_amount": Decimal("0.00"),
                "credit_amount": amount,
                "memo": memo,
                "_rule": rule_name,
                "_account_name": acct.properties["name"],
            })

    journal_seq += 1

# Display journal entries
print(f"Generated {len(journal_lines)} journal lines across {journal_seq - 1} entries:\n")

header = f"{'Journal #':<18} {'Date':<12} {'Account':>7} {'Account Name':<20} {'Debit':>12} {'Credit':>12}  Memo"
print(header)
print("-" * len(header))

total_debits = Decimal("0")
total_credits = Decimal("0")
prev_journal = None

for line in journal_lines:
    # Blank line between journal entries (batch separator)
    if prev_journal and line["journal_number"] != prev_journal:
        print()
    prev_journal = line["journal_number"]

    dr = line["debit_amount"]
    cr = line["credit_amount"]
    total_debits += dr
    total_credits += cr

    dr_str = f"{dr:>12,.2f}" if dr else "            "
    cr_str = f"{cr:>12,.2f}" if cr else "            "

    print(f"{line['journal_number']:<18} {line['journal_date']:<12} "
          f"{line['account_code']:>7} {line['_account_name']:<20} "
          f"{dr_str} {cr_str}  {line['memo']}")

print("-" * len(header))
print(f"{'TOTALS':<18} {'':12} {'':>7} {'':20} {total_debits:>12,.2f} {total_credits:>12,.2f}")
balanced = total_debits == total_credits
print(f"\nBalance check: {total_debits:,.2f} DR == {total_credits:,.2f} CR → {'BALANCED' if balanced else 'UNBALANCED'}")


# =============================================================================
# STEP 5: Export as CSV (per output format spec)
# =============================================================================

print("\n\n--- Step 5: CSV export (per OutputFormat spec) ---\n")

if fmt_node and out_cols_sorted:
    col_names = [c.properties["name"] for c in out_cols_sorted]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=col_names, extrasaction="ignore")
    writer.writeheader()
    for line in journal_lines:
        writer.writerow({
            "journal_number": line["journal_number"],
            "journal_date": line["journal_date"],
            "account_code": line["account_code"],
            "debit_amount": f"{line['debit_amount']:.2f}",
            "credit_amount": f"{line['credit_amount']:.2f}",
            "memo": line["memo"],
        })

    csv_content = output.getvalue()
    print(csv_content)

    # Write to file
    with open("payroll_journal_export.csv", "w", newline="") as f:
        f.write(csv_content)
    print(f"Written to payroll_journal_export.csv")
else:
    print("No output format found in graph — skipping CSV export.")
