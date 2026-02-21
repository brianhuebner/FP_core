# Spec: [Feature / Workflow Name]

> **Status:** Draft | Ready | Implemented | Superseded
> **Created:** YYYY-MM-DD
> **Spec type:** Feature | Workflow

---

## Purpose

What problem does this solve in the accounting knowledge graph? Why does it matter for recipe pipelines, double-entry semantics, or agent workflows? (1-3 sentences)

---

## Layer Placement

**Primary layer:** L[1-5] — [Layer name]
**Layers touched:**

| Layer | Package | What changes |
|-------|---------|--------------|
| L1 Types | `domain/types.py` or `types_recipe.py` | [Enums, frozen dataclasses added/modified] |
| L2 Ontology | `domain/ontology.py` or `ontology_recipe.py` | [PropertySchema, EntitySchema, validators] |
| L3 Logic | `domain/logic.py` | [Builder/extractor/validator signatures] |
| L4 Persistence | `persistence/` | [Merge keys, serialization changes] |
| L5 MCP Server | `mcp_server/` | [Tool signatures, builder/summarizer changes] |

---

## Domain Types (L1)

Frozen dataclasses and enums affected. Show the relevant dataclass with fields highlighted:

```python
@dataclass(frozen=True)
class ExampleType:
    required_field: str
    new_field: Optional[str] = None  # <-- NEW
```

**Immutability check:** All new/modified dataclasses use `frozen=True`. Any new collections use `FrozenSet` or `tuple`, not `list`/`set`/`dict`.

If no L1 changes: state "No Layer 1 changes required" and explain why.

---

## Schema Definitions (L2)

Ontology entries and PropertySchema changes:

```python
_EXAMPLE_PROPS = PropertySchema(
    required=frozenset({"field_a", "field_b"}),
    optional=frozenset({"new_field"}),  # <-- ADDED
    types={
        "field_a": str,
        "field_b": int,
        "new_field": str,  # <-- ADDED
    },
)
```

**Declarative check:** All new validation logic is expressed as `PropertySchema`/`EntitySchema` data in the ontology dicts, not as scattered `if` statements. Any new validator function should operate *on* schema data, not duplicate it.

**Validators affected:** List any new or modified validators with signatures.

**Gate classification:**
- Gate 1 (template-time): [Which validations run during `build_and_save_pipeline`]
- Gate 2 (runtime): [Which validations run during `validate_entries`]

---

## Pure Functions (L3)

Builder, extractor, and validator signatures affected:

```python
def build_example_pattern(
    node: Node,
    new_param: List[Node],  # <-- NEW
) -> GraphPattern:
    """[What this builds]"""
    ...
```

---

## Persistence Contract (L4)

Merge keys, serialization, or deserialization changes:

- **Merge keys:** [Any additions to `MERGE_KEYS` registry]
- **Serialization:** [New properties that must survive Cypher round-trip]
- **Deserialization:** [New fields to extract from Neo4j records]

If no L4 changes: state "No Layer 4 changes required."

---

## MCP Interface (L5)

### Tool signatures affected

[Which of the 6 tools change, and how]

### JSON spec format

Show the relevant portion of the pipeline spec JSON with new/changed fields:

```json
{
  "field": "value",
  "new_field": "value"
}
```

### Summarizer output

Show the relevant portion of the summarizer output with new/changed fields:

```json
{
  "field": "value",
  "new_field": "value"
}
```

---

## Data Flow

ASCII diagram showing how data moves through the affected layers:

```
JSON spec (agent input)
    |
    v
builders.py — parse new_field from spec dict
    |
    v
Node(properties={"new_field": value})
    |
    v
Gate 1 validation (ontology checks)
    |
    v
Neo4j (MERGE with properties)
    |
    v
summarizers.py — emit new_field in instructions
    |
    v
JSON response (agent output)
```

---

## Examples

### Happy path

```json
// Input
{ "field": "valid_value" }

// Expected output
{ "result": "correct_output" }
```

### Error case

```json
// Input
{ "field": "invalid_value" }

// Expected error
{ "error": "Descriptive error message" }
```

### Edge case

Describe boundary conditions, empty values, missing optional fields, etc.

---

## Invariants

### Graph semantics
- [Constraints that must hold in the Neo4j graph]

### Functional constraints
- [Pure function guarantees, idempotency, etc.]

### Purity boundaries
- **New functions that are pure** (no I/O, no side effects): [list]
- **New functions that touch I/O**: [list — should only be in L4 connection.py or L5 tools.py]
- **Composition approach**: [How new pieces compose with existing validators/builders — via `.merge()`, via function composition, etc.]
- domain/ must never import from persistence/ or mcp_server/
- Pure functions (builders, summarizers) must not import from persistence/

---

## Integration

### Files modified

| File | Change |
|------|--------|
| `path/to/file.py` | [What changes] |

### Files created (justify each)

| File | Why an existing file can't absorb this |
|------|----------------------------------------|
| `path/to/new_file.py` | [Justification] |

### Canonical counts affected

| Constant | Before | After | Delta |
|----------|--------|-------|-------|
| `NodeLabel` | 19 | 19 | 0 |
| `Total tests` | 347 | [new] | +[n] |

**Count-assertion tests:** For each canonical count that changes, list the specific test assertion that will enforce the new count (e.g., `test_node_label_count` in `test_types.py`). If no existing test covers this count, one must be added.

If no canonical counts change, state "No canonical count changes."

---

## Test Strategy

### New tests

| Test file | Test class / method | What it verifies |
|-----------|-------------------|-----------------|
| `tests/path/test_file.py` | `TestClass::test_method` | [Assertion] |

### Existing tests

[Which existing tests must continue to pass, and why they won't break]

### Expected new test count

Current: 347 | Added: [n] | New total: [347 + n]

---

## Success Criteria

- [ ] [Concrete, verifiable criterion]
- [ ] [Another criterion]
- [ ] All existing tests pass (no regressions)
- [ ] Canonical counts updated in CLAUDE.md and count tests

---

## Out of Scope

- [What this spec deliberately does NOT address]
- [Deferred decisions, future work]

---

## Open Questions

- [ ] [Unresolved design decision] (Decide by: [date or milestone])
