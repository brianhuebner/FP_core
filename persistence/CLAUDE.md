# Agent Instructions: persistence/

## Quick Context

Neo4j I/O layer (Layer 4) for FP_core. Serializes domain graph patterns to Cypher, deserializes Neo4j records back to domain objects, and manages database connections. Only `connection.py` imports the `neo4j` driver — all other modules are pure functions testable without a database.

**Architecture Layer:** 4 (Persistence)
**Primary Responsibility:** Bidirectional mapping between domain GraphPattern objects and Neo4j

---

## Autonomy Boundaries

### Safe to Modify Independently
- Cypher query optimization (same semantics, better performance)
- Internal helper functions in serializers/deserializers
- Error messages and logging
- Connection pool tuning

### Requires Careful Review
- Serialize/deserialize parameter handling (must round-trip correctly)
- Cypher statement structure (MERGE patterns, parameter naming)
- Adding new operation functions in `operations.py`

### DO NOT Change Without Coordination
- `MERGE_KEYS` registry — must stay in sync with `domain.NodeLabel` (19 entries)
- Round-trip contract: `deserialize(serialize(pattern))` must reconstruct the original domain objects
- `_node_id` property convention — Node.id is stored/loaded via this Neo4j property
- Enum pass-through: enum values stored as strings in Neo4j, reconstituted on load

---

## Data Contracts

### Merge Keys (`merge_keys.py`)
- `MERGE_KEYS`: dict mapping every `NodeLabel` (19) to its MERGE identity properties
- `validate_merge_keys()`: confirms MERGE_KEYS covers all NodeLabel members

### Serializers (`serializers.py`) — Pure Functions
- `serialize_node(node) → (cypher, params)`: Node to MERGE statement
- `serialize_relationship(rel) → (cypher, params)`: Relationship to MERGE statement
- `serialize_pattern(pattern) → list[(cypher, params)]`: Full GraphPattern to statement list

### Deserializers (`deserializers.py`) — Pure Functions
- `deserialize_node(record) → Node`: Neo4j record to domain Node
- `deserialize_relationship(record) → Relationship`: Neo4j record to domain Relationship
- `deserialize_pattern(records) → GraphPattern`: Record set to domain GraphPattern

### Connection (`connection.py`)
- `Neo4jConnection`: Wrapper around the neo4j driver (only file with `import neo4j`)

### Operations (`operations.py`)
- `save_pattern(conn, pattern)`: Serialize + execute MERGE statements
- `load_pattern_by_recipe(conn, recipe_id) → GraphPattern`: Query + deserialize
- `delete_pattern_by_recipe(conn, recipe_id)`: Remove all nodes/relationships for a recipe
- `verify_pattern(conn, pattern) → bool`: Confirm pattern exists in Neo4j

### Key Conventions
- **MERGE for idempotent writes** — running save_pattern twice produces the same result
- **`_node_id` round-trip** — `Node.id` ↔ Neo4j `_node_id` property
- **Enum pass-through** — enum values stored as strings, reconstituted by deserializers

---

## Testing Contract

| Test File | Type | Tests |
|-----------|------|-------|
| `tests/persistence/test_merge_keys.py` | Pure | ~10 |
| `tests/persistence/test_serializers.py` | Pure | ~25 |
| `tests/persistence/test_deserializers.py` | Pure | ~20 |
| `tests/persistence/test_operations.py` | Integration | ~11 |

**Total: 66 tests (3 pure files + 1 integration)**

```bash
# Pure tests (no Neo4j needed)
pytest tests/persistence/test_merge_keys.py tests/persistence/test_serializers.py tests/persistence/test_deserializers.py

# Integration tests (requires NEO4J_URI, NEO4J_PASSWORD env vars)
pytest tests/persistence/test_operations.py
```

Integration tests are auto-skipped when `NEO4J_URI` is not set (see `tests/persistence/conftest.py`).

---

## Layer Integration Points

**Consumes from domain/:**
- Node, Relationship, GraphPattern, NodeLabel, RelationshipType (all Layer 1 types)
- Ontology merge functions (for merge key validation)
- ValidationResult (passed through from operations)

**Provides to mcp_server/:**
- `Neo4jConnection` (server holds a lazy connection)
- `save_pattern`, `load_pattern_by_recipe`, `delete_pattern_by_recipe`, `verify_pattern`
- `MERGE_KEYS` (used indirectly through serializers)

**Boundary Rules:**
- persistence/ imports from domain/ only — never from mcp_server/
- domain/ never imports from persistence/
- Only `connection.py` may import the `neo4j` driver

---

## Adding a New Node Type (Persistence Steps)

After completing the domain/ steps (see `domain/CLAUDE.md` Extension Patterns):

6. Add MERGE key entry in `merge_keys.py` → `MERGE_KEYS[NodeLabel.NEW_TYPE]`
7. Verify serializer handles the new node type (usually automatic if MERGE_KEYS is correct)
8. Update `test_merge_keys.py` count assertion (MERGE_KEYS count = NodeLabel count)
9. Run `pytest tests/persistence/` to confirm
