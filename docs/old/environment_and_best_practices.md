# Environment, Neo4j Driver, and Implemented Best Practices

---

## Environment Variables

All configuration is loaded from a `.env` file in the project root via `python-dotenv`. See `.env.example` for the template.

### Knowledge Graph (Core Pipeline)

| Variable | Purpose | Example | Used By |
|----------|---------|---------|---------|
| `NEO4J_URI` | Neo4j Aura connection string | `neo4j+s://e05a364c.databases.neo4j.io` | `knowledge_graph/connection.py` |
| `NEO4J_USER` | Neo4j username | `neo4j` | `knowledge_graph/connection.py` |
| `NEO4J_PASSWORD` | Neo4j instance password | (from Aura console) | `knowledge_graph/connection.py` |

The connection uses the `neo4j+s://` scheme, which means encrypted TLS to a Neo4j Aura cloud instance named "Atomic Ledger."

### MVP Web Application

| Variable | Purpose | Example | Used By |
|----------|---------|---------|---------|
| `ADMIN_KEY` | Secret key for admin panel access | (generate a strong random string) | `mvp/main.py` |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signature verification | `whsec_...` | `mvp/main.py` |
| `STRIPE_PAYMENT_LINK` | Stripe Payment Link URL (public-facing) | `https://buy.stripe.com/...` | `mvp/main.py` |
| `DATA_DIR` | SQLite database directory (Railway volume mount) | `/app/data` | `mvp/database.py` |

### Planned (Phase 4+)

| Variable | Purpose | When |
|----------|---------|------|
| `DATABASE_URL` | PostgreSQL connection string (replaces SQLite) | Phase 4 |
| `STRIPE_SECRET_KEY` | Stripe API key for server-side calls | Phase 4 |
| `EMAIL_API_KEY` | Resend or Postmark API key for prompt delivery | Phase 4 |
| `APP_ENV` | Environment flag (`development` / `production`) | Phase 4 |

---

## Python Neo4j Driver

### Library

The project uses the official **`neo4j` Python driver** (version `>=5.0`), maintained by Neo4j Inc.

```
# pyproject.toml
dependencies = [
    "neo4j>=5.0",
    "python-dotenv>=1.0",
]
```

```
# requirements.txt (includes MVP dependencies)
neo4j>=5.0
python-dotenv>=1.0
fastapi>=0.115.0
uvicorn[standard]
stripe
aiofiles
```

### Driver Initialization

```python
from neo4j import GraphDatabase

class Neo4jConnection:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
```

The driver is instantiated once per operation and explicitly closed when done. The project does not use connection pooling or async sessions — each script creates a `Neo4jConnection`, runs its queries, and calls `close()`.

### Two Query Methods

The `Neo4jConnection` class exposes two methods that map to Neo4j's read/write distinction:

**`run_query()`** — for read operations (MATCH, RETURN):

```python
def run_query(self, query, parameters=None):
    with self.driver.session() as session:
        result = session.run(query, parameters or {})
        return [record.data() for record in result]
```

Returns a list of dicts. Each dict is one result row with keys matching the Cypher `RETURN` aliases.

**`run_write()`** — for write operations (MERGE, CREATE, SET):

```python
def run_write(self, query, parameters=None):
    with self.driver.session() as session:
        result = session.run(query, parameters or {})
        summary = result.consume()
        return {
            "nodes_created": summary.counters.nodes_created,
            "relationships_created": summary.counters.relationships_created,
            "properties_set": summary.counters.properties_set
        }
```

Returns a counter dict so the caller can log what changed. The loader script uses this to report progress statement-by-statement.

### Connection Verification

```python
def verify_connection(self):
    with self.driver.session() as session:
        result = session.run("RETURN 1 AS test")
        record = result.single()
        return record["test"] == 1
```

Every script that connects to Neo4j calls `verify_connection()` before proceeding. The loader aborts if this fails.

---

## Implemented Code Examples

### 1. Context Manager Pattern for Neo4j in FastAPI

The MVP uses a context manager to ensure the Neo4j connection is always closed, even when an exception occurs:

```python
# mvp/main.py
@contextmanager
def neo4j_conn():
    from knowledge_graph.connection import Neo4jConnection
    conn = Neo4jConnection()
    try:
        yield conn
    finally:
        conn.close()

# Usage in a route:
with neo4j_conn() as conn:
    result = build_prompt(conn, recipe_id='stripe-settlement-v1',
                          output_format_id='saasant-journal-entry-v1')
```

The import is lazy (inside the function) so the FastAPI app can start without Neo4j credentials if only serving static pages.

### 2. Parameterized Cypher Queries

All queries use `$parameter` placeholders instead of string interpolation, preventing Cypher injection:

```python
# pipeline/build_stripe_prompt.py — parameterized query
result = conn.run_query(
    "MATCH (ss:SourceSchema {recipe_id: $id}) RETURN ss.name AS name",
    {"id": source_schema_id}
)
```

```python
# pipeline/build_prompt.py — parameterized with dynamic filter
params = {"rule_name": rule_name}
if recipe_id:
    recipe_filter = " {recipe_id: $recipe_id}"
    params["recipe_id"] = recipe_id

query = f"""
MATCH (mr:MappingRule{recipe_filter} {{rule_name: $rule_name}})
...
"""
results = conn.run_query(query, params)
```

The `$recipe_id` and `$rule_name` values are passed as parameters, never interpolated into the query string.

### 3. Idempotent Graph Loading with MERGE

Every `.cypher` file uses `MERGE` instead of `CREATE` to make loads repeatable:

```cypher
-- MERGE matches on the specified properties.
-- If a node with these exact properties exists, it's reused.
-- If not, it's created. Either way, SET updates the remaining properties.
MERGE (c7:Column {recipe_id: 'stripe-payout-reconciliation-v1', name: 'gross'})
SET c7.position = 7,
    c7.data_type = 'decimal',
    c7.role = 'amount',
    c7.required = true,
    c7.description = 'Gross transaction amount'
```

The `recipe_id` in the MERGE key prevents collisions between different recipes sharing the same Neo4j database. You can run the loader any number of times safely — it will update properties but never create duplicates.

### 4. Statement-by-Statement Execution with Progress Logging

The loader parses `.cypher` files into individual statements and executes them one at a time, because Neo4j does not support multi-statement queries:

```python
# knowledge_graph/load_stripe_workflow.py
def load_cypher_file(conn, file_path):
    statements = parse_cypher_file(file_path)
    for i, stmt in enumerate(statements, 1):
        try:
            result = conn.run_write(stmt)
            print(f"  [{i}/{len(statements)}] OK - nodes:{result['nodes_created']}, "
                  f"rels:{result['relationships_created']}, props:{result['properties_set']}")
        except Exception as e:
            print(f"  [{i}/{len(statements)}] ERROR: {e}")
            print(f"    Statement: {stmt[:100]}...")
```

Each statement logs its counters, so you can see exactly which statement failed and what it was trying to do.

### 5. Post-Load Verification Queries

After loading, the loader runs targeted queries to verify the graph was populated correctly:

```python
# knowledge_graph/load_stripe_workflow.py
def verify_load(conn, recipe_id):
    # Check source schema node exists
    result = conn.run_query(
        "MATCH (ss:SourceSchema {recipe_id: $id}) RETURN ss.name AS name",
        {"id": source_schema_id}
    )
    if not result:
        print(f"WARNING: Source schema not found for {source_schema_id}")

    # Count linked columns
    result = conn.run_query(
        "MATCH (ss:SourceSchema {recipe_id: $id})-[:HAS_COLUMN]->(c:Column) "
        "RETURN count(c) AS cnt",
        {"id": source_schema_id}
    )
    print(f"  Columns: {result[0]['cnt']}")

    # Verify AccountSlot -> Account mappings exist
    result = conn.run_query(
        "MATCH (ar:AccountingRecipe {recipe_id: $id})-[:HAS_SLOT]->(slot:AccountSlot)"
        "-[:MAPPED_TO]->(a:Account) "
        "RETURN slot.slot_id AS slot_id, a.account_id AS acct_id",
        {"id": recipe_id}
    )
    print(f"  Slot->Account Mappings: {len(result)}")
```

This catches issues like missing `[:TRANSFORMS]` relationships or orphaned nodes that didn't get linked.

### 6. Balance Validation (Sum-to-Zero)

The test pipeline generates journal entries from graph context and validates that debits equal credits:

```python
# pipeline/test_loc_release.py
lines = generate_journal_entry(context, sign_info, je_date, fleet_items)

total = sum(line['Amount'] for line in lines)
if total == 0:
    print("Journal entry is balanced!")
else:
    print("WARNING: Journal entry is NOT balanced!")
```

This is the only deterministic validation currently implemented. It enforces the fundamental accounting equation: every journal entry must net to zero.

### 7. Recipe Registry with Ordered Dependencies

The loader maintains a registry of known recipes with their file dependencies and load order:

```python
# knowledge_graph/load_stripe_workflow.py
RECIPES = {
    'stripe-settlement-v1': {
        'schema': 'schemas/stripe_payout_reconciliation.cypher',   # loaded first
        'mapping': 'mappings/stripe_settlement.cypher',            # depends on schema
        'output': 'outputs/saasant_journal_entry.cypher',          # independent
        'source_schema_id': 'stripe-payout-reconciliation-v1',
    },
}
```

Schema loads before mapping because the mapping's `[:TRANSFORMS]` relationship needs the `SourceSchema` node to already exist.

### 8. Profile-Filtered Queries for Multi-Tenancy

The prompt builder supports optional `profile_id` filtering so the same recipe serves different companies:

```python
# pipeline/build_stripe_prompt.py
if profile_id:
    debit_mapped = ("(mr)-[:DEBITS]->(debit_slot:AccountSlot)"
                    "-[:MAPPED_TO {profile_id: $profile_id}]->(debit:Account)")
else:
    debit_mapped = ("(mr)-[:DEBITS]->(debit_slot:AccountSlot)"
                    "-[:MAPPED_TO]->(debit:Account)")
```

When `profile_id` is provided, the query filters `[:MAPPED_TO]` relationships by that property, returning only the specified company's GL accounts. When omitted, it returns all mappings (useful for the default/first customer).

### 9. Stripe Webhook Signature Verification

The MVP verifies Stripe webhook signatures using HMAC before processing events:

```python
# mvp/main.py
if STRIPE_WEBHOOK_SECRET:
    sig_header = request.headers.get("stripe-signature", "")
    event = stripe.Webhook.construct_event(
        payload, sig_header, STRIPE_WEBHOOK_SECRET
    )
```

And admin routes use constant-time comparison to prevent timing attacks:

```python
def _check_admin(admin_key):
    if not admin_key or not hmac.compare_digest(admin_key, ADMIN_KEY):
        raise HTTPException(status_code=401, detail="Invalid admin key")
```

### 10. Defensive Query Result Handling

All query results use `.get()` with defaults to handle missing properties gracefully:

```python
# pipeline/build_stripe_prompt.py
pos = col.get('position', '')
name = col.get('name', '')
dtype = col.get('data_type', '')
role = col.get('role', '')
desc = col.get('description', '')
```

And top-level results are checked for None before accessing nested properties:

```python
schema_results = conn.run_query(schema_query, {"recipe_id": recipe_id})
schema = schema_results[0] if schema_results else None

if not schema or not schema.get('schema_id'):
    return None
```

---

## Best Practices Summary

| Practice | Where Implemented | Why It Matters |
|----------|-------------------|----------------|
| Parameterized queries | All pipeline scripts | Prevents Cypher injection |
| MERGE over CREATE | All `.cypher` files | Safe reloads, no duplicates |
| `recipe_id` on every node | All `.cypher` files | Multi-tenancy isolation |
| One statement per query | Loader script | Neo4j driver constraint |
| Post-load verification | Loader script | Catches broken relationships |
| Context manager for connections | MVP routes | Guarantees cleanup on error |
| Balance validation (sum = 0) | Test pipeline | Fundamental accounting check |
| Constant-time auth comparison | MVP admin routes | Prevents timing attacks |
| Ordered dependency loading | Recipe registry | Schema must exist before mapping links to it |
| Defensive `.get()` on results | Prompt builders | Handles missing/optional graph properties |
| Lazy imports in FastAPI | MVP routes | App starts without Neo4j for static serving |
| Webhook signature verification | Stripe handler | Validates event authenticity |