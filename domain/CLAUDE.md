# Agent Instructions: domain/

## Quick Context

Pure Python package implementing Layers 1-3 of FP_core. **Zero I/O imports** — everything here is testable without databases or networks. Transforms accounting concepts into a typed graph model and provides pure validation and recipe graph construction.

**Architecture Layers:** 1 (Types), 2 (Ontology & Validation), 3 (Logic)
**Primary Responsibility:** Define all domain types, enforce schema constraints, build recipe graph patterns

---

## Autonomy Boundaries

### Safe to Modify Independently
- Internal helper functions that don't change public signatures
- Docstrings, error messages, inline comments
- Algorithm improvements that maintain function signatures and return values

### Requires Careful Review
- Adding optional parameters with defaults to existing functions
- Changing default values (check all call sites)
- Adding new validation rules that don't break existing data

### DO NOT Change Without Coordination
- Frozen dataclass field names, types, or required status
- Canonical counts (NodeLabel=19, RelationshipType=26, ONTOLOGY=7, RECIPE_ONTOLOGY=12, etc.)
- Schema dictionaries (ONTOLOGY, RECIPE_ONTOLOGY, RELATIONSHIP_CONSTRAINTS, RECIPE_RELATIONSHIP_CONSTRAINTS)
- `__all__` exports in `domain/__init__.py` — persistence/ and mcp_server/ depend on these
- Function signatures consumed by persistence/ or mcp_server/

---

## Data Contracts

### Layer 1 — Types (`types.py`, `types_recipe.py`)

**Core Enums (7):** AccountType, BalanceDirection, SemanticType, EntityType, DimensionType, RuleType, SourceType

**Core Dataclasses (7):** Account, Transaction, TransactionLine, Entity, AnalyticalDimension, AllocationRule, DataSource

**Graph Primitives (5):** Node, Relationship, GraphPattern, QueryIntent, Knowledge

**Graph Schema Enums (2):** NodeLabel (19 members), RelationshipType (26 members)

**Recipe Enums (5):** ColumnDataType, SemanticRole, AggregationOp, ConditionOp, TransformOp

**Recipe Dataclasses (9+):** SourceSchema, Column, Measure, Condition, AccountSlot, MappingRule, AccountingRecipe, OutputFormat, OutputColumn, ValidationRule, BatchFormat

### Layer 2 — Ontology & Validation (`ontology.py`, `ontology_recipe.py`)

**Schema Types (3):** PropertySchema, RelationshipConstraint, EntitySchema

**Result Type (1):** ValidationResult

**Ontology Dicts:** ONTOLOGY (7 entries), RECIPE_ONTOLOGY (12 entries), RELATIONSHIP_CONSTRAINTS (11 entries), RECIPE_RELATIONSHIP_CONSTRAINTS (14 entries), ACCOUNT_TYPE_BALANCE_MAP (7 entries), REFERENCE_RELATIONSHIP_SOURCES

**Merge Functions (2):** `merged_ontology()` → 19 entries, `merged_relationship_constraints()` → 25 entries

**Core Validators (9):** validate_node_properties, validate_account_balance_direction, validate_relationship, validate_graph_pattern, validate_transaction_balance, validate_posting_allowed, validate_clearing_account_balance (soft), validate_temporal_ordering (soft), validate_dimension_hierarchy (soft)

**Recipe Validators (8):** validate_recipe_has_schema, validate_slot_has_mapping (soft), validate_mapping_rule_completeness, validate_measure_references_column, validate_output_format_has_columns, validate_output_column_positions_unique, validate_batch_format_references_column (soft), validate_uses_reference

**Composition (1):** compose_validators

### Layer 3 — Logic (`logic.py`)

**Builders (3):** build_source_schema_pattern, build_recipe_pattern, build_output_format_pattern

**Extractors (5):** extract_measures_for_schema, extract_debit_credit_slots, extract_output_columns, extract_validation_rules, extract_batch_format

**Orchestrating Validators (2):** validate_recipe, validate_output_format

**Composition Functions (2):** compose_pipeline_pattern, validate_pipeline_connectivity

---

## Key Design Constraints

- All domain types use `frozen=True` — never make them mutable
- All validators are pure functions returning `ValidationResult` — no side effects, no exceptions for validation
- Debits must equal credits — hard invariant in `validate_transaction_balance`
- Enum values in property maps are stored as strings (not enum instances) at the graph layer
- `recipe_id` is a template reference — NOT a multi-tenancy key
- Reference data nodes carry `NodeLabel.REFERENCE` (sentinel) in `Node.labels` and their actual type in `Node.extra_labels`; FP_core validates the accounting side of `USES_REFERENCE` edges but treats the reference side as opaque (empty PropertySchema, no required fields)
- Only `MappingRule`, `Condition`, and `AccountingRecipe` may source `USES_REFERENCE` edges (defined in `REFERENCE_RELATIONSHIP_SOURCES`); core accounting nodes cannot reach into the knowledge zone directly
- `ValidationResult.merge()` combines results — valid only if all have zero errors
- `compose_validators()` creates a single validator from multiple, using `merge` internally

---

## Extension Patterns

**Adding a new node type:**
1. Add member to `NodeLabel` in `types.py` (or `types_recipe.py` if recipe-layer)
2. Create frozen dataclass for the type in the same file
3. Add `PropertySchema` and `EntitySchema` entry in `ontology.py` (or `ontology_recipe.py`)
4. Export from `domain/__init__.py`
5. Update count tests (NodeLabel count, ONTOLOGY/RECIPE_ONTOLOGY count, merged count)
6. Then update persistence/ — see `persistence/CLAUDE.md` for those steps

**Adding a new relationship type:**
1. Add member to `RelationshipType` in `types.py`
2. Add `RelationshipConstraint` entry in the appropriate constraints dict
3. Update count tests (RelationshipType count, constraints count, merged count)
4. EntitySchema `allowed_relationships` auto-populates from constraints — no manual update needed

**Adding a new validator:**
1. Write pure function: `def validate_xxx(arg) -> ValidationResult:`
2. Hard blocks return `ValidationResult(is_valid=False, errors=[...])`, soft warnings return `ValidationResult(is_valid=True, warnings=[...])`
3. Export from `domain/__init__.py`
4. Add test class following existing patterns in the corresponding test file

---

## Testing Contract

| Test File | Layer | Tests |
|-----------|-------|-------|
| `tests/domain/test_types.py` | L1 core | ~30 |
| `tests/domain/test_types_recipe.py` | L1 recipe | ~40 |
| `tests/domain/test_ontology.py` | L2 core | ~60 |
| `tests/domain/test_ontology_recipe.py` | L2 recipe | ~40 |
| `tests/domain/test_logic.py` | L3 | ~27 |

**Total: 197 tests, all pure (no I/O, no fixtures)**

```bash
pytest tests/domain/
```

---

## Layer Integration Points

**Consumes:** Nothing — domain/ is the bottom layer

**Provides to persistence/:**
- All types (Node, Relationship, GraphPattern, NodeLabel, RelationshipType)
- Ontology dicts and merge functions (for merge key validation)
- ValidationResult

**Provides to mcp_server/:**
- All Layer 3 logic functions (builders, extractors, validators)
- All Layer 2 validators (Gate 1 validation)
- Ontology dicts and merge functions (for resources)

**Boundary Rule:** domain/ must never import from persistence/ or mcp_server/

---

## Ontology Reference

See `docs/old/ontology.md` for the full design document including node type definitions, relationship semantics, validation strategy (hard blocks vs soft warnings vs no validation), traceability patterns, and implementation phases.
