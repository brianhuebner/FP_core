# Accounting Knowledge Graph - Neo4j Cypher Skill

## Purpose
This skill enables you to write Neo4j Cypher queries for an accounting knowledge graph that understands accounting semantics. Use this skill when users need to:
- Build queries for transaction tracking and traceability
- Create accounting data models in Neo4j
- Validate accounting principles through graph patterns
- Implement allocation rules and recipes
- Query financial data across multiple dimensions

## Core Ontology Reference

### Node Labels

#### Account
```cypher
(:Account {
  code: String,              // Account number (e.g., "1000", "4000")
  name: String,              // Account name (e.g., "Cash", "Revenue")
  account_type: String,      // asset|liability|equity|revenue|expense|contra_revenue|contra_expense
  normal_balance: String,    // debit|credit
  semantic_type: String?,    // clearing|bank|receivable|payable (optional)
  is_active: Boolean,
  expected_behavior: String? // e.g., "should_net_to_zero" for clearing accounts
})
```

#### Transaction
```cypher
(:Transaction {
  transaction_id: String,
  transaction_date: DateTime,
  posting_date: DateTime,
  period: String,            // e.g., "2024-01"
  description: String,
  is_posted: Boolean,
  created_by: String,
  created_at: DateTime,
  source_system_id: String
})
```

#### TransactionLine
```cypher
(:TransactionLine {
  line_id: String,
  amount: Float,
  direction: String,         // debit|credit
  memo: String?
})
```

#### Entity
```cypher
(:Entity {
  entity_id: String,
  legal_name: String,
  entity_type: String,       // legal_entity|division|consolidation_group
  tax_id: String?,
  base_currency: String      // e.g., "USD"
})
```

#### AnalyticalDimension
```cypher
(:AnalyticalDimension {
  dimension_id: String,
  dimension_type: String,    // location|department|cost_center|product|customer|project|custom
  name: String,
  code: String?,
  is_hierarchical: Boolean,
  is_required: Boolean,
  parent_id: String?
})
```

#### AllocationRule
```cypher
(:AllocationRule {
  rule_id: String,
  rule_name: String,
  rule_type: String,         // split_by_dimension|percentage|formula|custom
  is_active: Boolean,
  created_by: String,
  created_at: DateTime,
  version: Integer
})
```

#### DataSource
```cypher
(:DataSource {
  source_id: String,
  source_type: String,       // stripe|quickbooks|xero|bank_feed|manual|api|csv_import
  connection_config: String, // JSON string
  last_sync: DateTime
})
```

### Relationship Types

```cypher
// Transaction structure
(:TransactionLine)-[:BELONGS_TO]->(:Transaction)
(:TransactionLine)-[:POSTS_TO]->(:Account)

// Analytical dimensions
(:TransactionLine)-[:DIMENSIONED_BY]->(:AnalyticalDimension)
(:AnalyticalDimension)-[:CHILD_OF]->(:AnalyticalDimension)
(:AnalyticalDimension)-[:BELONGS_TO]->(:Entity)

// Allocation and transformation
(:TransactionLine)-[:ALLOCATED_BY]->(:AllocationRule)
(:AllocationRule)-[:USES_DIMENSION]->(:AnalyticalDimension)
(:AllocationRule)-[:CREATED_FROM]->(:Recipe)
(:AllocationRule)-[:APPLIED_TO]->(:Transaction)

// Provenance and traceability
(:Transaction)-[:CREATED_FROM]->(:Transaction)        // Tracks source transaction
(:Transaction)-[:REVERSES]->(:Transaction)            // Adjustment/reversal relationship
(:DataSource)-[:PROVIDES]->(:Transaction)
(:Entity)-[:OWNS]->(:Account)
(:Entity)-[:PARENT_OF]->(:Entity)

// Transaction grouping
(:TransactionSet)-[:CONTAINS]->(:Transaction)
(:TransactionSet)-[:CREATED_BY]->(:AllocationRule)
```

## Semantic Rules & Validation Queries

### 1. Accounting Equation Balance

**Rule**: For every transaction, sum(debits) must equal sum(credits)

```cypher
// Check if a transaction balances
MATCH (t:Transaction {transaction_id: $txn_id})<-[:BELONGS_TO]-(line:TransactionLine)
WITH t,
     sum(CASE WHEN line.direction = 'debit' THEN line.amount ELSE 0 END) AS total_debits,
     sum(CASE WHEN line.direction = 'credit' THEN line.amount ELSE 0 END) AS total_credits
WHERE abs(total_debits - total_credits) > 0.01  // Allow for floating point rounding
RETURN t.transaction_id, total_debits, total_credits,
       abs(total_debits - total_credits) AS imbalance
```

**Validation query for all unbalanced transactions:**
```cypher
MATCH (t:Transaction)<-[:BELONGS_TO]-(line:TransactionLine)
WITH t,
     sum(CASE WHEN line.direction = 'debit' THEN line.amount ELSE 0 END) AS debits,
     sum(CASE WHEN line.direction = 'credit' THEN line.amount ELSE 0 END) AS credits
WHERE abs(debits - credits) > 0.01
RETURN t.transaction_id, t.description, debits, credits, (debits - credits) AS imbalance
ORDER BY abs(debits - credits) DESC
```

### 2. Clearing Account Validation

**Rule**: Clearing accounts should net to zero (or close to it)

```cypher
// Check clearing account balance
MATCH (a:Account {semantic_type: 'clearing'})<-[:POSTS_TO]-(line:TransactionLine)
WITH a,
     sum(CASE WHEN line.direction = 'debit' THEN line.amount ELSE 0 END) AS total_debits,
     sum(CASE WHEN line.direction = 'credit' THEN line.amount ELSE 0 END) AS total_credits
WITH a, total_debits, total_credits, (total_debits - total_credits) AS net_balance
WHERE abs(net_balance) > 0.01
RETURN a.code, a.name, total_debits, total_credits, net_balance
ORDER BY abs(net_balance) DESC
```

### 3. Account Normal Balance Check

**Rule**: Accounts should typically have balances consistent with their normal balance

```cypher
// Find accounts with unusual balances (e.g., asset with credit balance)
MATCH (a:Account)<-[:POSTS_TO]-(line:TransactionLine)
WITH a,
     sum(CASE WHEN line.direction = 'debit' THEN line.amount ELSE 0 END) AS debits,
     sum(CASE WHEN line.direction = 'credit' THEN line.amount ELSE 0 END) AS credits
WITH a, debits, credits,
     CASE 
       WHEN a.normal_balance = 'debit' THEN (debits - credits)
       ELSE (credits - debits)
     END AS net_balance
WHERE net_balance < 0
RETURN a.code, a.name, a.account_type, a.normal_balance, 
       debits, credits, net_balance
```

## Traceability Pattern Queries

### TRACE: Follow path backwards to origin

```cypher
// Trace a transaction back to its original source
MATCH path = (t:Transaction {transaction_id: $txn_id})-[:CREATED_FROM*0..10]->(source:Transaction)
WHERE NOT (source)-[:CREATED_FROM]->()  // Find the root
RETURN path, source
```

```cypher
// Trace a GL entry back to source system data
MATCH (t:Transaction {transaction_id: $txn_id})
OPTIONAL MATCH (t)<-[:PROVIDES]-(ds:DataSource)
OPTIONAL MATCH path = (t)-[:CREATED_FROM*1..5]->(source:Transaction)<-[:PROVIDES]-(source_ds:DataSource)
RETURN t, ds, path, source, source_ds
```

### TRACK: Follow path forward from origin

```cypher
// Track what transactions were created from this source transaction
MATCH path = (source:Transaction {transaction_id: $source_id})<-[:CREATED_FROM*0..10]-(derived:Transaction)
RETURN path
ORDER BY length(path)
```

### DRILLDOWN: Vertical movement from summary to detail

```cypher
// Drill down from a period summary to individual transactions
MATCH (t:Transaction {period: $period})
WHERE (t)-[:POSTS_TO]->(:Account {code: $account_code})
RETURN t
ORDER BY t.transaction_date
```

```cypher
// Drill down from allocation rule to specific applications
MATCH (rule:AllocationRule {rule_id: $rule_id})-[:APPLIED_TO]->(t:Transaction)
MATCH (t)<-[:BELONGS_TO]-(line:TransactionLine)
RETURN t, collect(line) as lines
ORDER BY t.transaction_date DESC
```

### DRILL ACROSS: Horizontal movement between related sets

```cypher
// Show same logical transaction in different systems
MATCH (canonical:Transaction {transaction_id: $txn_id})
OPTIONAL MATCH (canonical)-[:CREATED_FROM]->(stripe:Transaction)<-[:PROVIDES]-(stripe_ds:DataSource {source_type: 'stripe'})
OPTIONAL MATCH (canonical)<-[:CREATED_FROM]-(qbo:Transaction)<-[:PROVIDES]-(qbo_ds:DataSource {source_type: 'quickbooks'})
RETURN canonical, stripe, qbo, stripe_ds, qbo_ds
```

### PROVENANCE: Show chronology of changes

```cypher
// Show the lineage of an allocation rule
MATCH (rule:AllocationRule {rule_id: $rule_id})
OPTIONAL MATCH (rule)-[:CREATED_FROM]->(recipe:Recipe)
OPTIONAL MATCH (rule)-[:APPLIED_TO]->(t:Transaction)
WITH rule, recipe, collect(DISTINCT t.transaction_date) as application_dates
RETURN rule.rule_name, rule.created_at, rule.created_by, rule.version,
       recipe.name as source_recipe,
       application_dates
```

### AUDIT TRAIL: Comprehensive change record

```cypher
// Show all modifications to a transaction (if versioning is implemented)
MATCH (current:Transaction {transaction_id: $txn_id})
OPTIONAL MATCH path = (current)-[:REVERSES|CREATED_FROM*]-(related:Transaction)
RETURN current, path, related
ORDER BY related.created_at
```

## Common Query Patterns

### Creating a Basic Transaction

```cypher
// Create a simple journal entry
CREATE (t:Transaction {
  transaction_id: randomUUID(),
  transaction_date: datetime(),
  posting_date: datetime(),
  period: '2024-02',
  description: 'Sample journal entry',
  is_posted: true,
  created_by: 'system',
  created_at: datetime(),
  source_system_id: 'manual'
})

WITH t
CREATE (debit:TransactionLine {
  line_id: randomUUID(),
  amount: 1000.00,
  direction: 'debit',
  memo: 'Debit to asset'
})-[:BELONGS_TO]->(t)

CREATE (credit:TransactionLine {
  line_id: randomUUID(),
  amount: 1000.00,
  direction: 'credit',
  memo: 'Credit to revenue'
})-[:BELONGS_TO]->(t)

WITH t, debit, credit
MATCH (asset:Account {code: '1000'})
MATCH (revenue:Account {code: '4000'})

CREATE (debit)-[:POSTS_TO]->(asset)
CREATE (credit)-[:POSTS_TO]->(revenue)

RETURN t, debit, credit
```

### Creating a Transaction with Dimensions

```cypher
// Create transaction with location dimension
MATCH (bank:Account {code: '1000'})
MATCH (revenue:Account {code: '4000'})
MATCH (location:AnalyticalDimension {code: 'SF', dimension_type: 'location'})

CREATE (t:Transaction {
  transaction_id: randomUUID(),
  transaction_date: datetime(),
  posting_date: datetime(),
  period: '2024-02',
  description: 'Sale at SF location',
  is_posted: true,
  created_by: 'system',
  created_at: datetime(),
  source_system_id: 'stripe_123'
})

CREATE (debit:TransactionLine {
  line_id: randomUUID(),
  amount: 500.00,
  direction: 'debit'
})-[:BELONGS_TO]->(t),
(debit)-[:POSTS_TO]->(bank)

CREATE (credit:TransactionLine {
  line_id: randomUUID(),
  amount: 500.00,
  direction: 'credit'
})-[:BELONGS_TO]->(t),
(credit)-[:POSTS_TO]->(revenue),
(credit)-[:DIMENSIONED_BY]->(location)

RETURN t
```

### Implementing Clearing Account Pattern

```cypher
// Step 1: Record payout to clearing account
MATCH (bank:Account {code: '1000'})
MATCH (fees:Account {code: '5000'})
MATCH (clearing:Account {code: '1200', semantic_type: 'clearing'})

CREATE (payout:Transaction {
  transaction_id: randomUUID(),
  transaction_date: datetime(),
  posting_date: datetime(),
  period: '2024-02',
  description: 'Stripe payout received',
  is_posted: true,
  created_by: 'system',
  created_at: datetime(),
  source_system_id: 'stripe_payout_xyz'
})

CREATE (line1:TransactionLine {
  line_id: randomUUID(),
  amount: 970.00,
  direction: 'debit',
  memo: 'Net payout to bank'
})-[:BELONGS_TO]->(payout),
(line1)-[:POSTS_TO]->(bank)

CREATE (line2:TransactionLine {
  line_id: randomUUID(),
  amount: 30.00,
  direction: 'debit',
  memo: 'Processing fees'
})-[:BELONGS_TO]->(payout),
(line2)-[:POSTS_TO]->(fees)

CREATE (line3:TransactionLine {
  line_id: randomUUID(),
  amount: 1000.00,
  direction: 'credit',
  memo: 'Gross payout to clearing'
})-[:BELONGS_TO]->(payout),
(line3)-[:POSTS_TO]->(clearing)

RETURN payout

// Step 2: Clear individual sales (repeat for each sale)
MATCH (clearing:Account {code: '1200', semantic_type: 'clearing'})
MATCH (revenue:Account {code: '4000'})
MATCH (location:AnalyticalDimension {code: 'SF', dimension_type: 'location'})
MATCH (source_payout:Transaction {source_system_id: 'stripe_payout_xyz'})

CREATE (sale:Transaction {
  transaction_id: randomUUID(),
  transaction_date: datetime(),
  posting_date: datetime(),
  period: '2024-02',
  description: 'Individual sale recognition',
  is_posted: true,
  created_by: 'system',
  created_at: datetime(),
  source_system_id: 'stripe_charge_abc'
})-[:CREATED_FROM]->(source_payout)

CREATE (debit:TransactionLine {
  line_id: randomUUID(),
  amount: 50.00,
  direction: 'debit'
})-[:BELONGS_TO]->(sale),
(debit)-[:POSTS_TO]->(clearing)

CREATE (credit:TransactionLine {
  line_id: randomUUID(),
  amount: 50.00,
  direction: 'credit'
})-[:BELONGS_TO]->(sale),
(credit)-[:POSTS_TO]->(revenue),
(credit)-[:DIMENSIONED_BY]->(location)

RETURN sale
```

### Revenue by Dimension Query

```cypher
// Revenue by location for a period
MATCH (revenue:Account {account_type: 'revenue'})<-[:POSTS_TO]-(line:TransactionLine)-[:DIMENSIONED_BY]->(dim:AnalyticalDimension {dimension_type: 'location'})
WHERE (line)-[:BELONGS_TO]->(:Transaction {period: $period})
  AND line.direction = 'credit'
WITH dim.name as location, sum(line.amount) as total_revenue
RETURN location, total_revenue
ORDER BY total_revenue DESC
```

### Multi-dimensional Analysis

```cypher
// Revenue by location and product
MATCH (revenue:Account {account_type: 'revenue'})<-[:POSTS_TO]-(line:TransactionLine)-[:BELONGS_TO]->(t:Transaction {period: $period})
WHERE line.direction = 'credit'
OPTIONAL MATCH (line)-[:DIMENSIONED_BY]->(loc:AnalyticalDimension {dimension_type: 'location'})
OPTIONAL MATCH (line)-[:DIMENSIONED_BY]->(prod:AnalyticalDimension {dimension_type: 'product'})
WITH coalesce(loc.name, 'Unallocated') as location,
     coalesce(prod.name, 'Unallocated') as product,
     sum(line.amount) as revenue
RETURN location, product, revenue
ORDER BY location, revenue DESC
```

## Recipe Pattern Examples

### Creating an Allocation Rule

```cypher
// Create a location-based revenue split rule
MATCH (location_dim:AnalyticalDimension {dimension_type: 'location'})

CREATE (rule:AllocationRule {
  rule_id: randomUUID(),
  rule_name: 'Split revenue by terminal location',
  rule_type: 'split_by_dimension',
  is_active: true,
  created_by: 'user@company.com',
  created_at: datetime(),
  version: 1
})

CREATE (rule)-[:USES_DIMENSION]->(location_dim)

RETURN rule
```

### Applying an Allocation Rule

```cypher
// Apply rule to split a transaction by location
MATCH (rule:AllocationRule {rule_id: $rule_id})-[:USES_DIMENSION]->(dim:AnalyticalDimension)
MATCH (source_txn:Transaction {transaction_id: $source_id})
MATCH (source_txn)<-[:BELONGS_TO]-(source_line:TransactionLine)-[:POSTS_TO]->(revenue:Account {account_type: 'revenue'})

// Get all locations
MATCH (location:AnalyticalDimension {dimension_type: 'location'})
WITH rule, source_txn, source_line, revenue, collect(location) as locations

// Create allocated transactions (simplified - assumes even split)
UNWIND locations as loc
CREATE (allocated:Transaction {
  transaction_id: randomUUID(),
  transaction_date: source_txn.transaction_date,
  posting_date: datetime(),
  period: source_txn.period,
  description: 'Allocated: ' + source_txn.description + ' - ' + loc.name,
  is_posted: true,
  created_by: 'allocation_engine',
  created_at: datetime(),
  source_system_id: source_txn.source_system_id
})-[:CREATED_FROM]->(source_txn)

CREATE (allocated_line:TransactionLine {
  line_id: randomUUID(),
  amount: source_line.amount / size(locations),
  direction: source_line.direction,
  memo: 'Allocated to ' + loc.name
})-[:BELONGS_TO]->(allocated),
(allocated_line)-[:POSTS_TO]->(revenue),
(allocated_line)-[:DIMENSIONED_BY]->(loc),
(allocated_line)-[:ALLOCATED_BY]->(rule)

CREATE (rule)-[:APPLIED_TO]->(allocated)

RETURN allocated, allocated_line, loc
```

## Anti-Patterns to Avoid

### ❌ Don't: Create transactions without balancing

```cypher
// BAD: Unbalanced transaction
CREATE (t:Transaction {...})
CREATE (:TransactionLine {amount: 100, direction: 'debit'})-[:BELONGS_TO]->(t)
// Missing credit side!
```

### ✅ Do: Always validate balance

```cypher
// GOOD: Check balance before committing
MATCH (t:Transaction {transaction_id: $txn_id})<-[:BELONGS_TO]-(line:TransactionLine)
WITH t,
     sum(CASE WHEN line.direction = 'debit' THEN line.amount ELSE 0 END) AS debits,
     sum(CASE WHEN line.direction = 'credit' THEN line.amount ELSE 0 END) AS credits
WHERE abs(debits - credits) > 0.01
RETURN CASE WHEN count(t) > 0 THEN 'UNBALANCED' ELSE 'BALANCED' END as status
```

### ❌ Don't: Lose traceability

```cypher
// BAD: No link to source
CREATE (derived:Transaction {...})
// No relationship showing where this came from
```

### ✅ Do: Preserve provenance

```cypher
// GOOD: Maintain lineage
MATCH (source:Transaction {transaction_id: $source_id})
CREATE (derived:Transaction {...})-[:CREATED_FROM]->(source)
```

### ❌ Don't: Modify posted transactions

```cypher
// BAD: Editing history
MATCH (t:Transaction {is_posted: true})
SET t.amount = 500  // Breaks audit trail
```

### ✅ Do: Create reversals/adjustments

```cypher
// GOOD: Create reversal transaction
MATCH (original:Transaction {transaction_id: $original_id, is_posted: true})
CREATE (reversal:Transaction {
  ...
  description: 'Reversal of ' + original.transaction_id
})-[:REVERSES]->(original)
```

### ❌ Don't: Use string matching for semantic concepts

```cypher
// BAD: String matching
MATCH (a:Account)
WHERE a.name CONTAINS 'Revenue'
```

### ✅ Do: Use semantic properties

```cypher
// GOOD: Semantic type
MATCH (a:Account {account_type: 'revenue'})
```

## Working with the Agent

When building queries with this ontology:

1. **Always validate accounting principles**: Check that transactions balance, clearing accounts net to zero, etc.

2. **Preserve traceability**: Every derived transaction should have a CREATED_FROM relationship

3. **Use semantic types**: Query by `account_type` not by name patterns

4. **Think in terms of accounting concepts**: Debits/credits, chart of accounts, periods, dimensions

5. **Support composability**: Allow for null/missing dimensions, custom extensions

6. **Enable all traceability operations**: Your queries should support trace, track, walk, drilldown, drill across, provenance, and audit trail

7. **Respect immutability**: Never modify posted transactions, create reversals instead

8. **Document transformations**: When creating allocation rules or recipes, include clear metadata about what they do

## Example Usage Scenarios

### Scenario 1: "Show me all revenue by location for last month"

```cypher
MATCH (t:Transaction {period: '2024-01'})<-[:BELONGS_TO]-(line:TransactionLine)-[:POSTS_TO]->(a:Account {account_type: 'revenue'})
WHERE line.direction = 'credit'
OPTIONAL MATCH (line)-[:DIMENSIONED_BY]->(dim:AnalyticalDimension {dimension_type: 'location'})
WITH coalesce(dim.name, 'Unallocated') as location, sum(line.amount) as revenue
RETURN location, revenue
ORDER BY revenue DESC
```

### Scenario 2: "Check if my clearing accounts are balanced"

```cypher
MATCH (a:Account {semantic_type: 'clearing'})<-[:POSTS_TO]-(line:TransactionLine)
WITH a,
     sum(CASE WHEN line.direction = 'debit' THEN line.amount ELSE 0 END) AS debits,
     sum(CASE WHEN line.direction = 'credit' THEN line.amount ELSE 0 END) AS credits
WITH a, debits, credits, abs(debits - credits) as imbalance
WHERE imbalance > 0.01
RETURN a.code, a.name, debits, credits, imbalance
ORDER BY imbalance DESC
```

### Scenario 3: "Trace this transaction back to the original Stripe charge"

```cypher
MATCH path = (current:Transaction {transaction_id: $txn_id})-[:CREATED_FROM*0..10]->(source:Transaction)<-[:PROVIDES]-(ds:DataSource {source_type: 'stripe'})
RETURN path, source, ds
ORDER BY length(path)
LIMIT 1
```

### Scenario 4: "Create a recipe for splitting Stripe revenue by location"

```cypher
// First create the allocation rule
CREATE (rule:AllocationRule {
  rule_id: randomUUID(),
  rule_name: 'Stripe Multi-Location Revenue Split',
  rule_type: 'split_by_dimension',
  is_active: true,
  created_by: 'user@company.com',
  created_at: datetime(),
  version: 1
})

WITH rule
MATCH (location_dim:AnalyticalDimension {dimension_type: 'location'})
CREATE (rule)-[:USES_DIMENSION]->(location_dim)

RETURN rule

// Then apply it to Stripe transactions
// (Implementation would follow the allocation pattern shown above)
```

## Summary

This skill provides the foundation for building a knowledge graph that:
- Understands accounting semantics (not just stores data)
- Maintains full traceability (trace, track, walk, drilldown, drill across, provenance, audit trail)
- Enforces accounting principles (balanced transactions, proper clearing accounts)
- Supports composability (recipes, templates, custom dimensions)
- Enables professional accountants to work effectively across systems

Always prioritize semantic understanding over implementation details, preserve complete audit trails, and enable users to work with their data in accountant-friendly ways.