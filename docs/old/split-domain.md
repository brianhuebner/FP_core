# Agent Instructions: [MODULE_NAME]

## Quick Context
[2-3 sentence description: What problem does this module solve? What data does it transform?]

**Architecture Layer:** [Specify which of the 5 layers this belongs to]
**Primary Responsibility:** [Single clear purpose]

---

## Functional Programming Principles for This Module

### Pure Functions Only
- All functions must be pure: same input → same output, no side effects
- State transformations return new data structures (no mutation)
- Side effects (I/O, logging, external calls) isolated to specific boundary functions

### Data Flow
```
Input DataClass → Transformation Functions → Output DataClass
```

### Type Safety
- All functions must have type hints
- All DataClasses must use frozen=True where possible
- Use Pattern matching for control flow where appropriate

---

## Autonomy Boundaries

### ✅ Safe to Modify Independently

**Pure Functions:**
- Internal transformation logic in `[filename].py`
- Helper functions that don't change interfaces
- Algorithm improvements that maintain function signatures
- Performance optimizations

**Tests:**
- Unit tests in `tests/unit/test_[module].py`
- Property-based tests (if using hypothesis/quickcheck)
- Test data fixtures

**Data Validation:**
- Validation rules in DataClass `__post_init__`
- Custom validators for fields
- Error messages (keep them clear and actionable)

**Documentation:**
- Docstrings
- Type annotations
- Inline comments
- This CLAUDE.md file

### ⚠️ Requires Careful Review

**DataClass Definitions:**
- Adding new optional fields (backward compatible)
- Adding new validation rules that don't break existing data
- Changing default values (check all call sites)

**Function Signatures:**
- Adding optional parameters (with defaults)
- Extending return types (e.g., Result[T] → Result[T, E])

### ⛔ DO NOT CHANGE Without Coordination

**Public Interfaces:**
- DataClass field names, types, or required status
- Function signatures (name, required parameters, return type)
- Module exports in `__init__.py`
- Exception types raised

**Cross-Layer Contracts:**
- Data structures passed between layers
- Interface functions that other layers depend on
- Validation schemas used by multiple modules

**Dependencies:**
- Imports from other modules
- External library versions
- Shared utility functions

---

## Data Class Contracts

### Current DataClasses Exported by This Module
```python
# Example - Replace with actual DataClasses
@dataclass(frozen=True)
class ExampleData:
    """
    [Description of what this represents]
    
    Contract:
    - field_name: [constraints, validation rules]
    - other_field: [constraints, validation rules]
    """
    field_name: str
    other_field: int
    
    def __post_init__(self):
        # Validation rules that must be maintained
        pass
```

**Breaking Changes:**
- Removing fields
- Changing field types
- Making optional fields required
- Changing validation rules to be more strict

**Safe Changes:**
- Adding optional fields (with defaults)
- Making validation rules more permissive
- Adding computed properties
- Improving error messages

---

## Testing Contract

### Required Test Commands
```bash
# All tests must pass
pytest tests/unit/test_[module].py -v

# Type checking must pass
mypy src/[module].py --strict

# Coverage must stay above threshold
pytest tests/unit/test_[module].py --cov=src/[module] --cov-report=term-missing
# Current coverage: [X%]
# Minimum required: [Y%]
```

### Test Structure for Functional Code
```python
# Property-based tests for pure functions
@given(st.text())
def test_function_properties(input_data):
    result = pure_function(input_data)
    assert verify_property(result)

# Example-based tests for edge cases
def test_edge_case_empty_input():
    result = pure_function("")
    assert result == expected_value

# Composition tests
def test_function_composition():
    result = compose(fn_a, fn_b, fn_c)(input_data)
    assert result == expected_output
```

### What Tests Must Cover
- All exported functions
- All DataClass validation rules
- Edge cases: empty, None, boundary values
- Error cases: invalid inputs, constraint violations
- Composition: functions used together
- Idempotency: f(f(x)) == f(x) where applicable
- Associativity: (a • b) • c == a • (b • c) where applicable

---

## Layer Integration Points

**Current Layer:** [Layer X of 5]

**Consumes From (Layer Below):**
- Module: `[module_name]`
- DataClasses: `[ClassName, ...]`
- Functions: `[function_name, ...]`

**Provides To (Layer Above):**
- Module: `[module_name]`
- DataClasses: `[ClassName, ...]`
- Functions: `[function_name, ...]`

**Sibling Modules (Same Layer):**
- Coordination required for: [shared data structures, contracts]
- Independent from: [list modules with no dependencies]

### Layer Boundaries Must Maintain
1. **Data flows unidirectionally** (typically bottom-up or top-down)
2. **Lower layers don't import from higher layers**
3. **Layers communicate through defined DataClass contracts**
4. **No circular dependencies between layers**

---

## Context Budget & Code Organization

**Target Complexity:**
- Total lines of code: ~[X] lines (current: [Y])
- Functions per file: [recommended max]
- Lines per function: [recommended max]

**If This Module Grows Beyond Target:**
- Split by: [criteria - e.g., separate read/write operations]
- Extract: [what functionality could be extracted]
- Consider: [alternative organization strategies]

**Code Organization Philosophy:**
```
[module]/
├── types.py          # DataClass definitions
├── validators.py     # Validation logic
├── core.py          # Main transformation functions
├── helpers.py       # Internal utilities
└── __init__.py      # Public API exports only
```

---

## Functional Patterns Used Here

### Current Patterns
- [ ] Composition: `compose(f, g, h)`
- [ ] Pipe: `pipe(data, fn1, fn2, fn3)`
- [ ] Map/Filter/Reduce over collections
- [ ] Result/Option types for error handling
- [ ] Currying/Partial application
- [ ] Higher-order functions
- [ ] Pattern matching (Python 3.10+)

### Error Handling Approach
```python
# Example - adapt to your actual approach
from typing import Union, Literal
from dataclasses import dataclass

@dataclass(frozen=True)
class Success:
    value: T

@dataclass(frozen=True)
class Failure:
    error: str
    
Result = Union[Success[T], Failure]

# All functions return Result types, no exceptions in business logic
```

---

## Change Protocols

### For Internal Changes (✅ Autonomous)
1. Make the change
2. Update or add tests
3. Run test suite: `pytest tests/unit/test_[module].py`
4. Run type checker: `mypy src/[module].py --strict`
5. Verify coverage threshold
6. Commit with clear message

### For Interface Changes (⛔ Requires Coordination)
1. **STOP** - Flag this for human review
2. Document the proposed change in a comment
3. Identify all modules that depend on this interface
4. Propose a migration strategy:
   - Adapter pattern to maintain compatibility?
   - Version bump required?
   - Deprecation period needed?
5. Update integration tests
6. Update all dependent modules
7. Run full test suite: `pytest tests/`

### For DataClass Schema Changes
1. Check if change is backward compatible:
   - Adding optional field? → Safe
   - Removing field? → Breaking, needs coordination
   - Changing type? → Breaking, needs coordination
2. Update validation tests
3. Update any serialization/deserialization logic
4. Search codebase for all usages: `grep -r "ClassName" .`
5. Update or create migration script if needed

---

## Performance Considerations

**Current Performance Requirements:**
- Throughput: [e.g., "10k operations/second"]
- Latency: [e.g., "p95 < 100ms"]
- Memory: [e.g., "< 1GB for 1M records"]

**Optimization Opportunities:**
- [ ] Memoization for expensive pure functions
- [ ] Lazy evaluation where appropriate
- [ ] Generator expressions over list comprehensions
- [ ] Structural sharing in immutable data structures

**Do Not Optimize Without:**
- Benchmark showing actual bottleneck
- Test proving correctness is maintained
- Documentation of optimization trade-offs

---

## Related Documentation

**Feature Specs:** `/specs/features/[feature_name].md`
- [Brief description of what feature specs are relevant]

**API Contracts:** `/specs/api/[api_name].md`
- [List relevant API specifications]

**Architecture Decisions:** `/specs/architecture/[decision_name].md`
- [Link to ADRs that explain why this module exists as it does]

**Layer Documentation:** `/docs/architecture/layer_[X].md`
- [Link to documentation about this layer's responsibilities]

---

## Common Patterns & Idioms

### How to Add a New Function
```python
def new_function(input_data: InputType) -> OutputType:
    """
    [Clear docstring explaining purpose, inputs, outputs]
    
    Args:
        input_data: [description with constraints]
    
    Returns:
        [description of return value and possible states]
        
    Examples:
        >>> new_function(example_input)
        expected_output
    """
    # Implementation (pure function only)
    pass
```

### How to Add a New DataClass
```python
@dataclass(frozen=True)
class NewData:
    """
    [What this represents in the domain]
    
    Invariants:
    - [List constraints that always hold]
    """
    field: Type
    
    def __post_init__(self):
        """Validate invariants"""
        if not self._is_valid():
            raise ValueError("Clear error message")
    
    def _is_valid(self) -> bool:
        """Private validation logic"""
        return True  # validation rules
```

### How to Compose Functions
```python
# Prefer explicit composition over nested calls
result = pipe(
    input_data,
    validate_input,
    transform_step_1,
    transform_step_2,
    format_output
)

# Or using composition
process = compose(
    format_output,
    transform_step_2,
    transform_step_1,
    validate_input
)
result = process(input_data)
```

---

## Debugging & Troubleshooting

### Common Issues in This Module
1. **[Common Issue 1]**
   - Symptoms: [what you'll see]
   - Likely cause: [explanation]
   - Fix: [solution]

2. **[Common Issue 2]**
   - Symptoms: [what you'll see]
   - Likely cause: [explanation]
   - Fix: [solution]

### Debug Checklist for Pure Functions
- [ ] Check input types match signature
- [ ] Verify input satisfies DataClass invariants
- [ ] Confirm no global state is being accessed
- [ ] Test function in isolation (REPL)
- [ ] Check for None/empty/boundary values
- [ ] Verify return type matches annotation

### When Tests Fail
1. Read the test name - it describes what should happen
2. Look at the test input - is it valid?
3. Check expected output - does it match the spec?
4. Run just that test: `pytest tests/unit/test_[module].py::test_name -v`
5. Add print statements to understand data flow
6. Check if DataClass validation is the issue

---

## Version History

**Current Version:** [X.Y.Z]

**Versioning Scheme:**
- Major (X): Breaking changes to public interfaces
- Minor (Y): New features, backward compatible
- Patch (Z): Bug fixes, internal improvements

**Recent Changes:**
- [Version] - [Date] - [Brief description]
- [Version] - [Date] - [Brief description]

---

## Notes for Future Refactoring

**Technical Debt:**
- [Item 1: Description and why it exists]
- [Item 2: Description and why it exists]

**Potential Improvements:**
- [Improvement 1: What and why it would help]
- [Improvement 2: What and why it would help]

**Waiting On:**
- [Dependency 1: What you need before making certain changes]
- [Dependency 2: What you need before making certain changes]

---

## Questions to Ask Before Modifying This Module

1. Does this change affect the public interface?
2. Will existing data still be valid after this change?
3. Do any other layers depend on the current behavior?
4. Are there tests covering the behavior I'm about to change?
5. Is this change purely internal, or does it affect contracts?
6. Can I make this change without breaking backward compatibility?
7. Do I need to update documentation beyond code comments?

---

## Human Escalation Triggers

**Immediately flag for human review if:**
- You need to change a DataClass field that other modules use
- You need to modify a function signature in the public API
- Tests fail after your changes and you can't determine why
- You need to add a new dependency
- You discover a bug in the existing logic that affects correctness
- You need to make a breaking change to meet requirements
- You find a security concern
- Performance requirements can't be met without architectural changes

**How to escalate:**
1. Stop making changes
2. Document what you were trying to do
3. Document what the issue is
4. Propose 2-3 alternative approaches
5. Flag with clear description in PR/commit message

---

## AI Agent Self-Check

Before committing changes, verify:
- [ ] All tests pass (`pytest tests/unit/test_[module].py`)
- [ ] Type checking passes (`mypy src/[module].py --strict`)
- [ ] Coverage meets threshold
- [ ] No changes to files in "DO NOT CHANGE" section
- [ ] All new functions have docstrings with examples
- [ ] All new DataClasses have validation logic
- [ ] No mutations of immutable data structures
- [ ] No side effects in pure functions
- [ ] Changes are focused on stated autonomy boundaries
- [ ] Related specs still accurately describe behavior

---

## Getting Started Checklist for New Agents

**First time working on this module?**
1. [ ] Read this entire CLAUDE.md file
2. [ ] Read the feature spec at `/specs/features/[name].md`
3. [ ] Look at the DataClass definitions in `types.py`
4. [ ] Run the tests to see them pass: `pytest tests/unit/test_[module].py -v`
5. [ ] Read 2-3 test files to understand expected behavior
6. [ ] Identify the layer this module belongs to
7. [ ] Understand what modules depend on this one
8. [ ] Check the "DO NOT CHANGE" section carefully
9. [ ] Review the function signatures in the public API
10. [ ] Now you're ready to make changes within boundaries!