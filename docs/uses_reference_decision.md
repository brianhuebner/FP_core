# The Accounting Boundary

## Two Zones, One Graph

A user's knowledge graph contains two fundamentally different kinds of data, governed by different rules:

```
┌─────────────────────────────────────┐     ┌─────────────────────────────────────┐
│         ACCOUNTING ZONE             │     │         KNOWLEDGE ZONE              │
│                                     │     │                                     │
│  Strict. Validated. Typed.          │     │  Flexible. User-defined. Opaque.    │
│                                     │     │                                     │
│  - Account must have account_type   │     │  - Employee has... whatever the     │
│  - Transaction must balance         │     │    user puts on it                  │
│  - MappingRule must have DR + CR    │     │  - TimeclockEntry, Product, Role,   │
│  - Every edge is constrained        │     │    LeaseSchedule... anything        │
│  - FP_core enforces all of this     │     │  - No schema enforcement            │
│                                     │     │  - FP_core doesn't know or care     │
└─────────────────────────────────────┘     └─────────────────────────────────────┘
```

The accounting zone is FP_core's domain. Every node has a `NodeLabel`, a `PropertySchema`
with required fields, and relationships constrained to valid `(source, target)` pairs.
Validators enforce invariants: transactions balance, mapping rules have both debit and
credit sides, accounts have correct normal balance directions.

The knowledge zone is the user's domain. An accountant's graph may contain employee lists
for payroll allocation, product catalogs for revenue categorization, lease schedules for
accrual calculations, timeclock data for labor cost distribution. These structures have
meaning to the user's business but are not accounting concepts. FP_core has no business
dictating their schema.

Both zones live in the same Neo4j graph. The question is: how do they connect?

---

## The Boundary Edge: USES_REFERENCE

Every relationship in the system except one lives entirely within the accounting zone:

```
(MappingRule)──DEBITS──►(AccountSlot)          Both accounting. Both validated.
(AccountSlot)──MAPPED_TO──►(Account)           Both accounting. Both validated.
(TransactionLine)──POSTS_TO──►(Account)        Both accounting. Both validated.
(AccountingRecipe)──TRANSFORMS──►(SourceSchema) Both accounting. Both validated.
(OutputFormat)──HAS_VALIDATION──►(ValidationRule) Both accounting. Both validated.
```

`USES_REFERENCE` is the only edge that crosses the boundary:

```
┌─ ACCOUNTING ZONE ────────────────────────┐     ┌─ KNOWLEDGE ZONE ─────────────────┐
│                                          │     │                                  │
│  MappingRule ─────USES_REFERENCE────────────────►  Reference:Employee             │
│  Condition ───────USES_REFERENCE────────────────►  Reference:TimeclockEntry       │
│  AccountingRecipe ─USES_REFERENCE───────────────►  Reference:ProductCatalog       │
│                                          │     │                                  │
│  (source validated by FP_core)           │     │  (target opaque to FP_core)      │
└──────────────────────────────────────────┘     └──────────────────────────────────┘
```

One end is strict (FP_core validates the source node's label, properties, and schema).
The other end is open (FP_core doesn't validate the target node's structure at all).

---

## How the Boundary Is Enforced: The Reference Sentinel

### The problem

FP_core's constraint system requires concrete `NodeLabel` values on both sides of every
relationship. A reference data node like `Employee` has no `NodeLabel` — it's a
user-defined concept that lives in `Node.extra_labels` as a raw string.

Without a mechanism to bridge this, `validate_relationship()` would reject every
`USES_REFERENCE` edge as invalid, because the target node has no recognized label.

### The solution: NodeLabel.REFERENCE

`REFERENCE` is a sentinel label — a badge that reference data nodes carry in their
`labels` set to participate in the constraint system. Their actual type identity
lives in `extra_labels`.

```python
# A reference data node in FP_core
Node(
    id="emp1",
    labels={NodeLabel.REFERENCE},              # sentinel — lets constraints match
    extra_labels=frozenset({"Employee"}),       # actual type — user's domain
    properties={"employee_id": "E001", "name": "Jane", "role": "engineer"},
)
```

In Neo4j, this becomes a node with two labels:

```cypher
(:Reference:Employee {employee_id: "E001", name: "Jane", role: "engineer"})
```

The constraint entry uses the sentinel:

```python
RelationshipType.USES_REFERENCE: (
    (NodeLabel.MAPPING_RULE, NodeLabel.REFERENCE),
    (NodeLabel.CONDITION, NodeLabel.REFERENCE),
    (NodeLabel.ACCOUNTING_RECIPE, NodeLabel.REFERENCE),
),
```

### What this means in practice

The constraint system sees:

```
Source: MappingRule  → known NodeLabel ✓, has PropertySchema ✓, validated ✓
Target: Reference   → known NodeLabel ✓, has PropertySchema (empty) ✓, not validated ✓
Edge:   USES_REFERENCE → in constraints dict ✓, pair matches ✓
```

Validation passes. FP_core enforced the accounting side (MappingRule is valid, the edge
type is allowed from MappingRule) and let the reference side through (Reference has an
empty PropertySchema — no required fields, no type checks).

### The two-label contract

Reference nodes always carry two kinds of labels:

| Label type | Where it lives | Purpose | Who controls it |
|---|---|---|---|
| `NodeLabel.REFERENCE` | `Node.labels` | Constraint matching, boundary marker | FP_core (automatic) |
| `"Employee"`, `"Product"`, etc. | `Node.extra_labels` | Actual type identity | User (their domain) |

FP_core sees `REFERENCE`. Neo4j sees both `Reference` and `Employee`. The user's
queries use the specific label (`MATCH (e:Employee)`). FP_core's validators use the
sentinel (`NodeLabel.REFERENCE`).

---

## What Gets Validated at the Boundary

### Accounting side (strict)

The source of a USES_REFERENCE edge must be one of three node types:

```python
REFERENCE_RELATIONSHIP_SOURCES: FrozenSet[NodeLabel] = frozenset({
    NodeLabel.MAPPING_RULE,      # "I need external data to route this entry"
    NodeLabel.CONDITION,         # "I need external data to evaluate this filter"
    NodeLabel.ACCOUNTING_RECIPE, # "I depend on external data to produce output"
})
```

`validate_uses_reference()` checks:
- The source node exists in the pattern
- The source node has at least one label from `REFERENCE_RELATIONSHIP_SOURCES`
- If either check fails → hard error

### Knowledge side (opaque)

The target of a USES_REFERENCE edge is not validated by FP_core at all:
- No required properties
- No type checking
- No schema enforcement
- The `_REFERENCE_PROPS` PropertySchema is intentionally empty

This is by design. The ontology.md philosophy: "The foundation enforces understanding,
not uniformity." Reference data is the user's world — FP_core guards the gate where it
connects to accounting, not the data itself.

---

## Why Only Three Source Types?

Not every accounting node can reach into the knowledge zone. The source types are
specifically the recipe/pipeline nodes that need external data to do their work:

```
MappingRule:       "To split payroll by department, I need employee hours data."
                   The rule uses reference data to DECIDE how to route journal entries.

Condition:         "Only fire this rule when the product category is 'hardware'."
                   The condition uses reference data to EVALUATE a filter predicate.

AccountingRecipe:  "This recipe requires a location code lookup table."
                   The recipe uses reference data as a DEPENDENCY declaration.
```

Core accounting nodes (Account, Transaction, TransactionLine, Entity) do NOT get
USES_REFERENCE edges. They live entirely within the accounting zone. If a transaction
needs to reference an employee, it does so indirectly — through a MappingRule or
AllocationRule that has the USES_REFERENCE edge, not from the transaction itself.

This keeps the accounting zone's relationships clean and fully constrained:

```
TransactionLine ─POSTS_TO─► Account             ✓ both sides known
TransactionLine ─BELONGS_TO─► Transaction        ✓ both sides known
TransactionLine ─DIMENSIONED_BY─► Dimension      ✓ both sides known
TransactionLine ─ALLOCATED_BY─► AllocationRule    ✓ both sides known

MappingRule ─USES_REFERENCE─► Reference:Employee  ✓ source known, target opaque (by design)
```

---

## Examples

### Payroll allocation using employee hours

```
(recipe:AccountingRecipe {name: "Monthly Payroll Split"})
    ──TRANSFORMS──► (schema:SourceSchema {name: "ADP Payroll Export"})
    ──USES_REFERENCE──► (emp:Reference:Employee {employee_id: "E001"})
    ──USES_REFERENCE──► (tc:Reference:TimeclockEntry {employee_id: "E001", hours: 160})

(rule:MappingRule {rule_name: "split_salary_by_hours"})
    ──DEBITS──► (slot:AccountSlot {role: "salary_expense"})
    ──CREDITS──► (slot:AccountSlot {role: "payroll_clearing"})
    ──USES_REFERENCE──► (tc:Reference:TimeclockEntry)

(slot:AccountSlot {role: "salary_expense"})
    ──MAPPED_TO──► (acct:Account {code: "6100", name: "Salary Expense"})
```

FP_core validates: recipe has TRANSFORMS, rule has DEBITS + CREDITS, slot has MAPPED_TO,
account has valid type. It does NOT validate: employee has employee_id, timeclock entry
has hours, employee-timeclock relationship makes sense.

### Revenue split by product category

```
(rule:MappingRule {rule_name: "revenue_by_product"})
    ──DEBITS──► (slot:AccountSlot {role: "receivable"})
    ──CREDITS──► (slot:AccountSlot {role: "product_revenue"})
    ──USES_REFERENCE──► (cat:Reference:ProductCategory {code: "HW", name: "Hardware"})

(cond:Condition {column: "product_type", operator: "equals", value: "hardware"})
    ──USES_REFERENCE──► (cat:Reference:ProductCategory {code: "HW"})
```

The Condition node references the product category to evaluate whether the rule should
fire. The MappingRule references it to document the dependency. Both are validated on
the accounting side; the ProductCategory structure is the user's concern.

---

## The Complete Boundary Map

```
                    ACCOUNTING ZONE                          KNOWLEDGE ZONE
                    (FP_core validates)                      (user's domain)
                    ═══════════════════                      ══════════════

    ┌─ Core Accounting ──────────┐
    │  Account                   │
    │  Transaction               │
    │  TransactionLine           │
    │  Entity                    │    No USES_REFERENCE
    │  AnalyticalDimension       │    from these nodes.
    │  AllocationRule            │    They stay inside
    │  DataSource                │    the accounting zone.
    └────────────────────────────┘

    ┌─ Recipe Pipeline ──────────┐
    │  SourceSchema              │
    │  Column                    │
    │  Measure                   │
    │  Condition ────────────────────── USES_REFERENCE ──►  Reference:*
    │  AccountSlot               │
    │  MappingRule ──────────────────── USES_REFERENCE ──►  Reference:*
    │  AccountingRecipe ─────────────── USES_REFERENCE ──►  Reference:*
    │  OutputFormat              │
    │  OutputColumn              │
    │  ValidationRule            │
    │  BatchFormat               │
    └────────────────────────────┘

    ┌─ Boundary Sentinel ────────┐     ┌─ User-defined ──────────────┐
    │  Reference                 │     │  Employee, Product, Role,   │
    │  (NodeLabel.REFERENCE)     │     │  TimeclockEntry, Lease...   │
    │  (empty PropertySchema)    │◄───►│  (Node.extra_labels)        │
    │  (no validation)           │     │  (any properties)           │
    └────────────────────────────┘     └─────────────────────────────┘
```

---

## Design Decision Record

**Decision:** Option A — Sentinel Label

**Date:** 2026-02-15

**Context:** Three options were evaluated for representing the open-target USES_REFERENCE
relationship in FP_core's constraint system:
- Option A: Sentinel `NodeLabel.REFERENCE` as boundary marker
- Option B: Keep USES_REFERENCE out of constraints, validate separately
- Option C: Widen `RelationshipConstraint` to support wildcard targets

**Choice:** Option A, because:
1. The constraint dict stays uniform — every entry is `(NodeLabel, NodeLabel)` pairs
2. `validate_relationship()` works unchanged
3. EntitySchema wiring works — source types get USES_REFERENCE in outgoing_relationships
4. The boundary is explicit — reference nodes wear a badge to cross into accounting territory
5. `validate_uses_reference()` (already existed) handles source-side enforcement

**Trade-off accepted:** Every reference data node must carry `NodeLabel.REFERENCE` in its
`labels` set. This is a tagging obligation, but it makes the boundary visible and
machine-readable rather than implicit.
