# Accounting Knowledge Graph - Design Decisions

## Project Vision

Building a **knowledge graph that understands accounting semantics** to help accountants use different structured data sources while supporting transaction granularity and healthy, easy-to-audit ledgers.

## Core Philosophy

### The Foundation Principle
- The ontology provides the **semantic framework** without enforcing uniformity
- Individual implementations can be sparse, extended, or restructured as needed
- The foundation enforces *understanding*, not *uniformity*
- **Assumption: Professional accountants know what they're doing** - the system guides but doesn't block

### Traceability as a First-Class Citizen
The graph must support all professional accounting traceability patterns natively:
- **Trace**: Follow complete path backwards from current point to origin
- **Track**: Follow emerging path forward from starting point
- **Walk**: Step-by-step manual navigation through the system
- **Drilldown**: Vertical movement from aggregation to underlying details
- **Drill across**: Horizontal movement between related information sets at same granularity
- **Provenance**: Chronology from origin to current location
- **Audit trail**: Comprehensive record of who did what when

## Minimum Viable Ontology (MVP)

### Core Node Types (7 foundational concepts)

#### 1. Account
```
Properties:
  - code: string (account number)
  - name: string
  - account_type: enum [asset, liability, equity, revenue, expense, contra_revenue, contra_expense]
  - normal_balance: enum [debit, credit]
  - semantic_type: optional enum [clearing, bank, receivable, payable, etc.]
  - is_active: boolean
  - expected_behavior: optional string (e.g., "should_net_to_zero" for clearing)
```

**Semantic Understanding:**
- Knows its role in the accounting equation
- Understands normal balance for validation
- Special types (clearing accounts) have expected behaviors
- Can flag anomalies without preventing them

#### 2. Transaction
```
Properties:
  - transaction_id: string (unique identifier)
  - transaction_date: datetime
  - posting_date: datetime
  - period: string (fiscal period)
  - description: string
  - is_posted: boolean
  - created_by: string (user)
  - created_at: datetime
  - source_system_id: string (reference to source)

Invariants:
  - Must satisfy double-entry (sum of debits = sum of credits)
  - Immutable once posted (edits create reversals/adjustments)
```

**Semantic Understanding:**
- Represents atomic accounting events
- Enforces accounting equation balance
- Maintains immutability for audit compliance

#### 3. TransactionLine
```
Properties:
  - line_id: string
  - amount: decimal
  - direction: enum [debit, credit]
  - memo: optional string

Relationships:
  - BELONGS_TO → Transaction
  - POSTS_TO → Account
  - ALLOCATED_BY → AllocationRule (optional)
  - DIMENSIONED_BY → AnalyticalDimension (optional, multiple)
```

**Semantic Understanding:**
- Individual debit/credit entries
- Links to account and dimensions
- Preserves allocation provenance

#### 4. Entity
```
Properties:
  - entity_id: string
  - legal_name: string
  - entity_type: enum [legal_entity, division, consolidation_group]
  - tax_id: optional string
  - base_currency: string

Relationships:
  - OWNS → Account
  - PARENT_OF → Entity (for hierarchies)
```

**Semantic Understanding:**
- Represents reporting and legal boundaries
- Supports consolidation hierarchies
- Enables inter-entity transaction tracking

#### 5. AnalyticalDimension
```
Properties:
  - dimension_id: string
  - dimension_type: enum [location, department, cost_center, product, customer, project, custom]
  - name: string
  - code: optional string
  - is_hierarchical: boolean
  - is_required: boolean
  - parent_id: optional string (for hierarchies)

Relationships:
  - CHILD_OF → AnalyticalDimension (for hierarchies)
  - BELONGS_TO → Entity
```

**Semantic Understanding:**
- Provides ways to slice transactions beyond account structure
- Supports unlimited custom dimensions
- Enables drill-across between different analytical views
- Maps to system-specific implementations (QBO Classes, Xero Tracking Categories, etc.)

#### 6. AllocationRule
```
Properties:
  - rule_id: string
  - rule_name: string
  - rule_type: enum [split_by_dimension, percentage, formula, custom]
  - is_active: boolean
  - created_by: string
  - created_at: datetime
  - version: integer

Relationships:
  - CREATED_FROM → Recipe (optional)
  - USES_DIMENSION → AnalyticalDimension (optional)
  - APPLIED_TO → Transaction (historical applications)
```

**Semantic Understanding:**
- Encodes transformation logic
- Maintains provenance of how splits were calculated
- Versioned for audit trail
- Can be shared via recipes or custom per client

#### 7. DataSource
```
Properties:
  - source_id: string
  - source_type: enum [stripe, quickbooks, xero, bank_feed, manual, api, csv_import]
  - connection_config: json (system-specific configuration)
  - last_sync: datetime

Relationships:
  - PROVIDES → Transaction
  - SYNCED_BY → SyncJob
```

**Semantic Understanding:**
- Origin point for traceability
- Enables drill-across between source system and canonical view
- Supports "show me the original Stripe data for this GL entry"

### Optional/Extended Node Types

#### TransactionSet (Composable Unit)
```
Properties:
  - set_id: string
  - set_type: enum [payout_processing, period_close, allocation_batch]
  - created_at: datetime

Relationships:
  - CONTAINS → Transaction (multiple)
  - CREATED_BY → AllocationRule (optional)

Semantic Understanding:
  - Groups related transactions
  - Enables batch operations and validations
  - Example: "All transactions from today's Stripe payout"
```

#### Recipe (Community Template)
```
Properties:
  - recipe_id: string
  - name: string
  - description: string
  - industry: optional string
  - complexity: enum [simple, intermediate, advanced]
  - version: string
  - created_by: string
  - uses_count: integer

Semantic Understanding:
  - Template for transformation patterns
  - Can be instantiated with client-specific parameters
  - Lives in community graph, not private client graph
```

#### RecipeInstance (Bound Recipe)
```
Properties:
  - instance_id: string
  - parameter_bindings: json
  - instantiated_at: datetime
  - instantiated_by: string

Relationships:
  - INSTANCE_OF → Recipe
  - CREATED → AllocationRule

Semantic Understanding:
  - Private implementation of community template
  - Preserves link back to source recipe
  - Allows customization while maintaining shareability
```

## Design Decisions

### 1. Composability Model

**User Freedom:**
- Users can leave nodes/properties empty/null
- Users can delete or restructure as needed
- Users can extend with custom dimensions and properties
- Foundation guides but doesn't block

**Recipe Composability:**
```
Recipe declares dependencies:
  Requires:
    - AnalyticalDimension: Location
    - Account: Revenue (type: income)
  Recommends:
    - Account: ClearingAccount (type: clearing)
    - TransactionSet: PayoutProcessing
```

Users can:
- Adopt full recipe as-is
- Map recommended components to null (skip clearing accounts)
- Extend with their own custom components
- Modify and save as private variant

### 2. Validation Strategy

**Hard Blocks (Accounting Equation):**
- Transaction debits must equal credits
- Cannot post to inactive accounts
- Cannot delete posted transactions (must reverse)

**Soft Warnings (Best Practices):**
- Clearing accounts don't net to zero
- Revenue posted as negative (might be contra-revenue)
- Missing recommended analytical dimensions
- Deviating from recipe standard pattern

**No Validation (Professional Discretion):**
- Custom dimension structures
- Non-standard account hierarchies
- Unique allocation formulas
- System-specific workarounds

### 3. Transformation Layer Strategy

**Inbound Transforms:**
```
Source System Data → Canonical Ontology

Examples:
- "QBO Class 'Location-SF'" → AnalyticalDimension(type=location, code=SF)
- "Xero TrackingCategory 'Department:Engineering'" → AnalyticalDimension(type=department, code=ENG)
- "Stripe payout.line_item" → Transaction with proper double-entry structure
```

**Outbound Transforms:**
```
Canonical Ontology → Target System Format

Examples:
- Allocation result → QBO Journal Entry with Class assignments
- Canonical transaction → Xero Invoice with TrackingCategories
- Multi-entity consolidation → System-specific reporting format
```

**Key Principle:** The canonical model is system-agnostic. System connectors handle the impedance mismatch.

### 4. Traceability Implementation

**Every transformation creates edges:**
```
Transaction A
  → ALLOCATED_BY → AllocationRule R
  → CREATES → Transaction B
  → POSTS_TO → Account X

AllocationRule R
  → USES_DIMENSION → AnalyticalDimension (Location)
  → CREATED_FROM → Recipe Template
  → APPLIED_AT → timestamp T
  → APPLIED_BY → user U
```

**Questions answered by graph traversal:**
- "Trace this GL entry to original Stripe payout" → traverse CREATED_FROM edges backward
- "Track this refund to see what it affected" → traverse CREATES edges forward
- "Show allocation rule history" → traverse APPLIED_AT with temporal filter
- "Drill from revenue summary to individual transactions" → traverse CONTAINS edges in TransactionSet
- "Drill across from Stripe view to QBO view" → traverse through DataSource mappings

### 5. Clearing Account Pattern (Example)

**Foundation understands the pattern:**
```
ClearingAccount (semantic_type: "clearing")
  expected_behavior: "should_net_to_zero"
  validation: flag_imbalance (warning, not blocking)

Healthy Pattern:
  Transaction 1: Payout Received
    DR: Bank $970
    DR: Processing Fees $30
    CR: Stripe_Clearing $1000
  
  Transaction 2+: Individual Sales (repeated)
    DR: Stripe_Clearing $50
    CR: Revenue_LocationA $50
    
  Validation: Stripe_Clearing nets to $0 ✓
```

**User variations allowed:**
```
Direct Posting (simpler, less traceable):
  Transaction 1: Daily Summary
    DR: Bank $970
    DR: Processing Fees $30
    CR: Revenue $1000
    
  System warns: "⚠️ Pattern reduces traceability to individual transactions"

Custom Hybrid:
  Transaction 1: Payout → Clearing
  Transaction 2: Periodic sweep with subledger detail
    
  System recognizes as valid variant
```

### 6. Extensibility Model

**The Accounting Boundary**

The graph has two zones: an **accounting zone** (strict, validated, typed) and a **knowledge zone** (flexible, user-defined, opaque). FP_core enforces invariants within the accounting zone and guards the boundary where reference data connects to accounting nodes, but does not validate the reference data itself.

Reference data nodes carry `NodeLabel.REFERENCE` as a sentinel label (for constraint matching) and their actual type identity in `Node.extra_labels` (e.g., `"Employee"`, `"Product"`). Only three recipe-layer node types (`MappingRule`, `Condition`, `AccountingRecipe`) may source `USES_REFERENCE` edges into the knowledge zone. Core accounting nodes stay inside the boundary.

See `docs/uses_reference_decision.md` for the full boundary architecture.

**Four paths to extend the graph:**

**A. Analytical Dimensions (Preferred for categorization):**
```
User creates: ProjectPhase (subtype of AnalyticalDimension)
System recognizes: It's a dimension, all dimension-aware recipes work
Benefit: Maximum reusability, stays inside the accounting zone
```

**B. Reference Data (For non-accounting structures):**
```
User creates: (:Reference:Employee {employee_id: "E001", name: "Jane"})
System treats: As opaque data connected via USES_REFERENCE
Benefit: Full graph-native structure, no schema constraints
Limitation: FP_core doesn't validate reference data internals
```

**C. Custom Properties:**
```
User adds: transaction.custom_fields.project_phase
System treats: As metadata, not semantic concept
Benefit: Quick customization
Limitation: Recipes won't understand it without explicit teaching
```

**D. Contribute to Community:**
```
User proposes: ProjectPhase as standard dimension type
Community approves: Becomes part of foundation ontology
Benefit: All future recipes can leverage it
```

## Implementation Phases

### Phase 1: Foundation (Current Focus)
- 7 core node types
- Basic relationship types
- Transaction balance validation
- Simple traceability (CREATED_FROM, POSTS_TO edges)

### Phase 2: Transformation Layer
- AllocationRule execution
- Recipe templates
- Parameter binding
- Inbound/outbound system connectors

### Phase 3: Community Features
- Recipe sharing
- Template registry
- Usage analytics
- Community contributions

### Phase 4: Advanced Semantics
- Inference rules
- Pattern detection
- Automated suggestions
- Anomaly flagging

## Critical Success Factors

### 1. Ontology Consistency
**The private client graph schema must be consistent across all clients from day one.**

If Client A represents locations differently than Client B, nothing is shareable. The community layer only works with a common ontology.

### 2. Semantic Types Over Implementation Details
Recipes operate on **concepts** (AnalyticalDimension: Location), not **implementations** (QBO Class field).

The transformation layer handles system-specific bindings.

### 3. Provenance is Non-Negotiable
Every transformation, allocation, and posting must preserve full audit trail. This is not a feature—it's a compliance requirement.

### 4. Balance Professional Guidance with Freedom
- Guide toward best practices
- Warn about risks
- Don't block professional judgment
- Make the "right way" the easy way

### 5. Start Small, Design for Growth
The MVP (7 node types) must be:
- Complete enough to prove value
- Flexible enough to extend
- Rigorous enough to trust
- Simple enough to understand

## Next Steps for Skill Development

To create a `.skill` for building Cypher queries in this domain, include:

1. **Ontology reference**: Full node and relationship type definitions
2. **Semantic rules**: What each concept means, not just what it's called
3. **Common patterns**: Standard Cypher queries for traceability operations
4. **Validation queries**: How to check accounting equation, clearing account balance, etc.
5. **Example recipes**: Working implementations of allocation patterns
6. **Anti-patterns**: Common mistakes to avoid in graph modeling

The skill should enable an agent to:
- Understand the accounting semantics
- Write ontology-compliant Cypher
- Create transformation logic
- Validate accounting principles
- Preserve full traceability