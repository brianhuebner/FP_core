The 3 Categories                                                                                                                                                                                                                                                                                                                                                                                                                                                         
                                                                                                                                                                                                                                                                                                                                                                                                                                                                         
  Layer 3 functions fall into three patterns based on what they do:                                                                                                                                                                                                                                                                                                                                                                                                        
                                                                                                                                                                                                                                                                                                                                                                                                                                                                           
  Builders take disaggregated pieces (nodes, relationships) and assemble them into a GraphPattern. They're construction functions — hand them the parts, get back the assembled subgraph. No validation.                                                                                                                                                                                                                                                                   

  Validators/Orchestrators take a GraphPattern and run multiple Layer 2 validators against it, merging results into a single ValidationResult. They answer: "is this subgraph structurally sound?"

  Extractors take a GraphPattern and a node ID, then traverse relationships to pull out specific connected nodes. They answer: "give me the X nodes connected to Y."

  How They Map to the Pipeline

  The project's core mechanism is a three-layer pipeline. Each layer is a subgraph in the user's Neo4j graph:

  Layer 1: SourceSchema         "What data do I have?"
           + Columns              (CSV structure, column types, measures)
           + Measures
           + Conditions

  Layer 2: AccountingRecipe     "What journal entries do I create from it?"
           + MappingRules         (DR/CR routing, account slots, conditions)
           + AccountSlots
           + Accounts

  Layer 3: OutputFormat         "What does the output file look like?"
           + OutputColumns        (column order, sign conventions, formatting)
           + ValidationRules
           + BatchFormat

  Each layer needs all three categories of function:
  ┌───────────────┬─────────────────────────────┬──────────────────┬─────────────────────────────┐
  │               │           Builder           │    Validator     │         Extractors          │
  ├───────────────┼─────────────────────────────┼──────────────────┼─────────────────────────────┤
  │ Source Schema │ build_source_schema_pattern │ validate_recipe* │ extract_measures_for_schema │
  ├───────────────┼─────────────────────────────┼──────────────────┼─────────────────────────────┤
  │ Recipe        │ build_recipe_pattern        │ validate_recipe  │ extract_debit_credit_slots  │
  ├───────────────┼─────────────────────────────┼──────────────────┼─────────────────────────────┤
  │ Output Format │ missing                     │ missing          │ missing                     │
  └───────────────┴─────────────────────────────┴──────────────────┴─────────────────────────────┘
  *validate_recipe covers both schema and recipe because it validates the full recipe pattern which includes the TRANSFORMS link to the schema.

  So the output format functions (builder + validator + 3 extractors) are the obvious gap — they complete the trifecta. Without them, you can build and validate source schemas and recipes but not output formats.

  What Pipeline Composition Does

  Right now each subgraph is built and validated independently. But the three layers are connected in the graph:

  (AccountingRecipe) ──TRANSFORMS──► (SourceSchema)

  The recipe references the source schema. If you build them as separate GraphPatterns, you can validate each in isolation, but you can't check the cross-layer wiring: "does this recipe's TRANSFORMS actually point to the schema that's in the pipeline?"

  compose_pipeline_pattern() merges the three subgraphs into one GraphPattern so that validate_pipeline_connectivity() can verify the connections between them. It's the difference between validating three isolated islands and validating the whole archipelago.

  Before composition:  [Schema pattern]  [Recipe pattern]  [Output pattern]
                       Each valid alone, but are they connected?

  After composition:   [Single merged pattern]
                       Now you can check: does the TRANSFORMS edge land on a real schema?

  Where Transaction Patterns Fit

  Transaction patterns are a different concern entirely. They're about core accounting (the things the pipeline produces), not about the pipeline itself:

  Pipeline builds these:
    Transaction
      + TransactionLine ──BELONGS_TO──► Transaction
      + TransactionLine ──POSTS_TO──► Account
      + TransactionLine ──DIMENSIONED_BY──► Dimension (optional)

  The pipeline (source → recipe → output) is the template. Transactions are the result of executing that template against real data. A build_transaction_pattern() function would be useful when Layer 4/5 actually creates journal entries, but it's not part of the pipeline machinery.
