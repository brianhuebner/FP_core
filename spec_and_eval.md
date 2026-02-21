# Spec-Driven Development & Agent Evals Guide

A practical guide for driving your functional programming project forward using specs and measuring agent performance.

---

## Table of Contents
1. [Spec-Driven Development Workflow](#spec-driven-development-workflow)
2. [Writing Effective Specs](#writing-effective-specs)
3. [Spec → Test → Code Cycle](#spec--test--code-cycle)
4. [Agent Eval Framework](#agent-eval-framework)
5. [Running and Analyzing Evals](#running-and-analyzing-evals)
6. [Practical Examples](#practical-examples)

---

## Spec-Driven Development Workflow

### The Core Loop

```
1. Write Spec (what should happen)
   ↓
2. Write Tests (prove the spec)
   ↓
3. Write Code (make tests pass)
   ↓
4. Run Evals (validate agent can work with it)
   ↓
5. Refine Spec (based on learnings)
```

### Why This Order Matters

**Spec First** - Forces you to think through edge cases before code exists
**Tests Second** - Makes the spec concrete and executable
**Code Last** - You know exactly when you're done (tests pass)
**Evals After** - Validates that agents can actually work with your design

---

## Writing Effective Specs

### Spec Template for Functional Modules

```markdown
# Spec: [Module Name]

## Purpose
[1-2 sentences: What problem does this solve?]

## Layer
[Which of your 5 layers does this belong to?]

## Core Concepts

### Data Structures
```python
@dataclass(frozen=True)
class InputData:
    """[What this represents]"""
    field: str
    count: int
    
@dataclass(frozen=True)
class OutputData:
    """[What this represents]"""
    result: str
    metadata: dict
```

### Primary Functions

#### `transform_data(input: InputData) -> Result[OutputData, Error]`

**Purpose:** [What this function does]

**Preconditions:**
- Input must have valid field (non-empty string)
- Count must be positive integer

**Postconditions:**
- Returns Success[OutputData] when valid
- Returns Failure[Error] when invalid
- Pure function - no side effects

**Examples:**
```python
# Happy path
input = InputData(field="test", count=5)
result = transform_data(input)
assert result == Success(OutputData(result="test-5", metadata={}))

# Error case
input = InputData(field="", count=5)
result = transform_data(input)
assert result == Failure(Error("field cannot be empty"))
```

**Edge Cases:**
- Empty field → Error
- Zero count → Error
- Negative count → Error
- Very large count (>10000) → Error
- Unicode in field → Success (handled)
- None values → Type system prevents

## Data Flow

```
Input DataClass
    ↓
validate_input() → Result[ValidInput, ValidationError]
    ↓
transform_logic() → Result[TransformedData, TransformError]
    ↓
format_output() → Result[OutputData, FormatError]
    ↓
Output DataClass
```

## Invariants

**Must Always Be True:**
1. All functions are pure (same input → same output)
2. No mutations of frozen dataclasses
3. Errors are values, not exceptions (use Result type)
4. Type hints on all public functions
5. All validation happens in __post_init__ or dedicated validators

## Dependencies

**Imports From:**
- `layer_1.data_models` - DataClass definitions
- `shared.result_types` - Result, Success, Failure

**Exports To:**
- `layer_3.business_logic` - Transformation functions

**Must Not Import:**
- Anything from layers above this one
- External I/O libraries (keep pure)

## Performance Requirements

- Transform 10k records per second on single core
- Memory: O(1) per record (no accumulation)
- No blocking operations

## Error Handling Strategy

```python
# All errors as values
@dataclass(frozen=True)
class ValidationError:
    field: str
    message: str

@dataclass(frozen=True)
class TransformError:
    reason: str
    
# Functions return Result types
def process(data: Input) -> Result[Output, ValidationError | TransformError]:
    ...
```

## Open Questions

- [ ] Should we support batch operations? (Decide by: [date])
- [ ] Unicode normalization strategy? (Decide by: [date])
- [ ] Max field length? (Decide by: [date])

## Out of Scope (For This Version)

- Async operations
- Database persistence
- Network calls
- File I/O

## Success Criteria

This spec is complete when:
- [ ] All data structures defined with validation
- [ ] All function signatures documented
- [ ] All edge cases identified
- [ ] Example inputs/outputs provided
- [ ] Error cases enumerated
- [ ] Performance requirements stated
```

### Spec Checklist

Before calling a spec "done", verify:

- [ ] **Concrete examples** - At least 3 examples showing happy path, error case, edge case
- [ ] **Explicit edge cases** - Empty, None, boundary values, invalid combinations
- [ ] **Clear success criteria** - What does "correct" output look like?
- [ ] **Error enumeration** - All possible error states listed
- [ ] **Performance bounds** - Speed, memory, latency requirements
- [ ] **Data structure contracts** - All DataClasses fully specified
- [ ] **Dependencies mapped** - What this imports and exports
- [ ] **Invariants stated** - What must always be true
- [ ] **Out of scope** - What this deliberately doesn't do

---

## Spec → Test → Code Cycle

### Step 1: Write Tests From Spec

```python
# tests/unit/test_transform_data.py
import pytest
from dataclasses import dataclass
from module.transform import transform_data, InputData, OutputData
from shared.result_types import Success, Failure

class TestTransformDataHappyPath:
    """Tests from spec examples - happy path"""
    
    def test_basic_transformation(self):
        """Spec example 1: Basic valid input"""
        input_data = InputData(field="test", count=5)
        result = transform_data(input_data)
        
        assert isinstance(result, Success)
        assert result.value.result == "test-5"
        assert result.value.metadata == {}
    
    def test_unicode_handling(self):
        """Spec edge case: Unicode characters"""
        input_data = InputData(field="café", count=3)
        result = transform_data(input_data)
        
        assert isinstance(result, Success)
        assert "café" in result.value.result

class TestTransformDataErrorCases:
    """Tests from spec - error cases"""
    
    def test_empty_field_returns_error(self):
        """Spec error case: Empty field"""
        input_data = InputData(field="", count=5)
        result = transform_data(input_data)
        
        assert isinstance(result, Failure)
        assert "field cannot be empty" in result.error.message
    
    def test_zero_count_returns_error(self):
        """Spec error case: Zero count"""
        input_data = InputData(field="test", count=0)
        result = transform_data(input_data)
        
        assert isinstance(result, Failure)
        assert "count must be positive" in result.error.message
    
    def test_negative_count_returns_error(self):
        """Spec edge case: Negative count"""
        input_data = InputData(field="test", count=-1)
        result = transform_data(input_data)
        
        assert isinstance(result, Failure)

class TestTransformDataBoundaries:
    """Tests from spec - boundary conditions"""
    
    def test_max_count_boundary(self):
        """Spec edge case: Very large count"""
        input_data = InputData(field="test", count=10001)
        result = transform_data(input_data)
        
        assert isinstance(result, Failure)
        assert "count exceeds maximum" in result.error.message

class TestTransformDataProperties:
    """Property-based tests for functional guarantees"""
    
    def test_transform_is_pure(self):
        """Calling twice with same input gives same output"""
        input_data = InputData(field="test", count=5)
        
        result1 = transform_data(input_data)
        result2 = transform_data(input_data)
        
        assert result1 == result2
    
    def test_no_side_effects(self):
        """Input dataclass is not mutated"""
        input_data = InputData(field="test", count=5)
        original_field = input_data.field
        
        transform_data(input_data)
        
        assert input_data.field == original_field

# Run with: pytest tests/unit/test_transform_data.py -v
```

### Step 2: Watch Tests Fail

```bash
$ pytest tests/unit/test_transform_data.py -v

# You should see all tests fail because transform_data doesn't exist yet
# This proves your tests are actually testing something
```

### Step 3: Write Minimal Code to Pass Tests

```python
# src/module/transform.py
from dataclasses import dataclass
from typing import Union
from shared.result_types import Result, Success, Failure

@dataclass(frozen=True)
class ValidationError:
    field: str
    message: str

@dataclass(frozen=True)
class InputData:
    field: str
    count: int
    
    def __post_init__(self):
        """Validation from spec"""
        if not self.field:
            raise ValueError("field cannot be empty")
        if self.count <= 0:
            raise ValueError("count must be positive")
        if self.count > 10000:
            raise ValueError("count exceeds maximum")

@dataclass(frozen=True)
class OutputData:
    result: str
    metadata: dict

def transform_data(input_data: InputData) -> Result[OutputData, ValidationError]:
    """
    Transform input according to spec.
    
    Pure function - no side effects.
    """
    try:
        # Validation happened in __post_init__
        result = f"{input_data.field}-{input_data.count}"
        return Success(OutputData(result=result, metadata={}))
    except ValueError as e:
        return Failure(ValidationError(field="input_data", message=str(e)))

# Now tests should pass
```

### Step 4: Verify

```bash
$ pytest tests/unit/test_transform_data.py -v
# All tests pass ✓

$ mypy src/module/transform.py --strict
# Type checking passes ✓

$ pytest tests/unit/test_transform_data.py --cov=src/module --cov-report=term-missing
# Coverage report shows 100% ✓
```

---

## Agent Eval Framework

### What Are Agent Evals?

Agent evals test whether an AI agent can successfully complete tasks with your codebase. They answer:
- Can an agent understand my specs and write correct code?
- Can an agent fix bugs without breaking things?
- Can an agent work within the autonomy boundaries?
- Can an agent write tests that validate the spec?

### Eval Types for Your Project

#### 1. **Code Generation Evals**
Task: "Given this spec, implement the function"
Success: Code passes all tests, follows functional principles

#### 2. **Test Writing Evals**
Task: "Given this spec and code, write comprehensive tests"
Success: Tests cover all edge cases, achieve >90% coverage

#### 3. **Bug Fix Evals**
Task: "This function has a bug, fix it"
Success: Bug fixed, tests pass, no new bugs introduced

#### 4. **Refactoring Evals**
Task: "Improve this code while maintaining behavior"
Success: Tests still pass, code is cleaner, performance maintained

#### 5. **Boundary Respect Evals**
Task: "Add feature X to this module"
Success: Agent only modifies files in autonomy boundaries, doesn't break contracts

### Eval Structure

```python
# evals/eval_schema.py
from dataclasses import dataclass
from typing import Literal, Callable
from enum import Enum

class EvalType(Enum):
    CODE_GEN = "code_generation"
    TEST_WRITE = "test_writing"
    BUG_FIX = "bug_fix"
    REFACTOR = "refactor"
    BOUNDARY = "boundary_respect"

@dataclass(frozen=True)
class EvalTask:
    """Single eval task definition"""
    task_id: str
    eval_type: EvalType
    description: str
    
    # Context provided to agent
    spec_file: str | None
    code_file: str | None
    test_file: str | None
    claude_md_file: str | None
    
    # What agent should do
    prompt: str
    
    # How to score
    success_criteria: list[str]
    scoring_function: Callable
    
    # Expected behavior
    expected_files_modified: list[str]
    expected_files_created: list[str]
    must_not_modify: list[str]
    
    # Validation
    required_tests_pass: list[str]  # Test commands that must pass
    required_coverage: float  # e.g., 0.90 for 90%
    required_type_check: bool  # Must pass mypy

@dataclass(frozen=True)
class EvalResult:
    """Result of running an eval"""
    task_id: str
    passed: bool
    score: float  # 0.0 to 1.0
    
    agent_output: str
    files_modified: list[str]
    files_created: list[str]
    
    test_results: dict[str, bool]  # test_name -> passed
    coverage: float
    type_check_passed: bool
    
    boundary_violations: list[str]  # Files modified that shouldn't be
    errors: list[str]
    
    execution_time_seconds: float
```

### Creating Eval Tasks

```python
# evals/tasks/code_generation.py
from evals.eval_schema import EvalTask, EvalType

def create_transform_data_eval() -> EvalTask:
    """Eval: Can agent implement transform_data from spec?"""
    return EvalTask(
        task_id="code_gen_001_transform_data",
        eval_type=EvalType.CODE_GEN,
        description="Implement transform_data function from specification",
        
        # Context files
        spec_file="specs/features/data_transformation.md",
        code_file=None,  # Agent creates this
        test_file="tests/unit/test_transform_data.py",  # Pre-written
        claude_md_file="src/module/CLAUDE.md",
        
        # Task
        prompt="""
        Read the spec at specs/features/data_transformation.md
        Read the CLAUDE.md to understand autonomy boundaries
        Implement the transform_data function in src/module/transform.py
        The tests are already written - make them pass
        Follow functional programming principles (pure functions, immutable data)
        """,
        
        # Success criteria
        success_criteria=[
            "All tests pass",
            "Type checking passes with mypy --strict",
            "Coverage >= 90%",
            "Function is pure (no side effects)",
            "Uses frozen dataclasses",
            "Returns Result type, not exceptions"
        ],
        
        scoring_function=score_code_generation,
        
        # Expected changes
        expected_files_modified=[],
        expected_files_created=["src/module/transform.py"],
        must_not_modify=["tests/unit/test_transform_data.py", "specs/"],
        
        # Validation
        required_tests_pass=["pytest tests/unit/test_transform_data.py -v"],
        required_coverage=0.90,
        required_type_check=True
    )

def score_code_generation(result: EvalResult) -> float:
    """
    Scoring function for code generation evals.
    Returns 0.0 to 1.0
    """
    score = 0.0
    
    # Tests passing is 50% of score
    if all(result.test_results.values()):
        score += 0.5
    
    # Type checking is 20%
    if result.type_check_passed:
        score += 0.2
    
    # Coverage is 20%
    if result.coverage >= 0.90:
        score += 0.2
    elif result.coverage >= 0.75:
        score += 0.1
    
    # No boundary violations is 10%
    if not result.boundary_violations:
        score += 0.1
    
    return score
```

### Running Evals

```python
# evals/runner.py
import subprocess
import time
from pathlib import Path
from typing import List
from evals.eval_schema import EvalTask, EvalResult

class EvalRunner:
    """Runs eval tasks against an agent"""
    
    def __init__(self, workspace_dir: Path):
        self.workspace_dir = workspace_dir
    
    def run_eval(self, task: EvalTask, agent_function: Callable) -> EvalResult:
        """
        Run a single eval task.
        
        Args:
            task: The eval task to run
            agent_function: Function that takes (task, workspace) and performs work
        
        Returns:
            EvalResult with scores and metrics
        """
        start_time = time.time()
        
        # Setup clean workspace
        workspace = self._setup_workspace(task)
        
        # Track files before agent runs
        files_before = self._get_file_tree(workspace)
        
        # Run agent
        try:
            agent_output = agent_function(task, workspace)
        except Exception as e:
            return self._create_error_result(task, str(e), time.time() - start_time)
        
        # Track files after agent runs
        files_after = self._get_file_tree(workspace)
        files_modified = files_after - files_before
        
        # Run validation
        test_results = self._run_tests(task, workspace)
        coverage = self._measure_coverage(task, workspace)
        type_check_passed = self._run_type_check(task, workspace)
        boundary_violations = self._check_boundaries(task, files_modified)
        
        # Calculate score
        result = EvalResult(
            task_id=task.task_id,
            passed=self._determine_passed(task, test_results, coverage, type_check_passed, boundary_violations),
            score=task.scoring_function(
                # Pass preliminary result for scoring
                EvalResult(
                    task_id=task.task_id,
                    passed=False,  # Will be set after
                    score=0.0,
                    agent_output=agent_output,
                    files_modified=list(files_modified),
                    files_created=[],
                    test_results=test_results,
                    coverage=coverage,
                    type_check_passed=type_check_passed,
                    boundary_violations=boundary_violations,
                    errors=[],
                    execution_time_seconds=0
                )
            ),
            agent_output=agent_output,
            files_modified=list(files_modified),
            files_created=[],  # Could track separately
            test_results=test_results,
            coverage=coverage,
            type_check_passed=type_check_passed,
            boundary_violations=boundary_violations,
            errors=[],
            execution_time_seconds=time.time() - start_time
        )
        
        return result
    
    def _run_tests(self, task: EvalTask, workspace: Path) -> dict[str, bool]:
        """Run all required tests"""
        results = {}
        
        for test_cmd in task.required_tests_pass:
            try:
                result = subprocess.run(
                    test_cmd,
                    shell=True,
                    cwd=workspace,
                    capture_output=True,
                    timeout=60
                )
                results[test_cmd] = result.returncode == 0
            except subprocess.TimeoutExpired:
                results[test_cmd] = False
        
        return results
    
    def _measure_coverage(self, task: EvalTask, workspace: Path) -> float:
        """Measure test coverage"""
        if not task.required_coverage:
            return 1.0
        
        try:
            # Run pytest with coverage
            result = subprocess.run(
                ["pytest", "--cov=src", "--cov-report=json"],
                cwd=workspace,
                capture_output=True,
                timeout=60
            )
            
            # Parse coverage from json report
            import json
            coverage_file = workspace / "coverage.json"
            if coverage_file.exists():
                data = json.loads(coverage_file.read_text())
                return data["totals"]["percent_covered"] / 100.0
            
            return 0.0
        except Exception:
            return 0.0
    
    def _run_type_check(self, task: EvalTask, workspace: Path) -> bool:
        """Run mypy type checking"""
        if not task.required_type_check:
            return True
        
        try:
            result = subprocess.run(
                ["mypy", "src/", "--strict"],
                cwd=workspace,
                capture_output=True,
                timeout=30
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def _check_boundaries(self, task: EvalTask, files_modified: set[str]) -> list[str]:
        """Check if agent respected autonomy boundaries"""
        violations = []
        
        for file in files_modified:
            if file in task.must_not_modify:
                violations.append(f"Modified protected file: {file}")
        
        return violations
    
    def _determine_passed(
        self, 
        task: EvalTask, 
        test_results: dict[str, bool],
        coverage: float,
        type_check_passed: bool,
        boundary_violations: list[str]
    ) -> bool:
        """Determine if eval passed"""
        return (
            all(test_results.values()) and
            coverage >= task.required_coverage and
            (type_check_passed if task.required_type_check else True) and
            len(boundary_violations) == 0
        )

# Usage
def run_code_gen_evals():
    """Run all code generation evals"""
    from evals.tasks.code_generation import create_transform_data_eval
    
    runner = EvalRunner(workspace_dir=Path("./eval_workspace"))
    task = create_transform_data_eval()
    
    # Your agent function
    def my_agent(task: EvalTask, workspace: Path) -> str:
        """
        Your agent implementation.
        Could call Claude API, use local model, etc.
        """
        # Read spec
        spec = (workspace / task.spec_file).read_text()
        
        # Call agent with prompt
        response = call_claude_api(
            prompt=task.prompt,
            context={"spec": spec}
        )
        
        # Agent writes files
        # ...
        
        return response
    
    result = runner.run_eval(task, my_agent)
    
    print(f"Task: {result.task_id}")
    print(f"Passed: {result.passed}")
    print(f"Score: {result.score:.2f}")
    print(f"Coverage: {result.coverage:.1%}")
    print(f"Type Check: {result.type_check_passed}")
    
    if result.boundary_violations:
        print(f"Violations: {result.boundary_violations}")
```

### Eval Suite Organization

```
evals/
├── eval_schema.py         # EvalTask, EvalResult definitions
├── runner.py              # EvalRunner class
├── tasks/
│   ├── code_generation/
│   │   ├── transform_data_eval.py
│   │   ├── validation_eval.py
│   │   └── formatting_eval.py
│   ├── test_writing/
│   │   ├── edge_case_coverage_eval.py
│   │   └── property_test_eval.py
│   ├── bug_fixes/
│   │   ├── off_by_one_eval.py
│   │   └── type_error_eval.py
│   └── boundaries/
│       ├── respect_autonomy_eval.py
│       └── contract_preservation_eval.py
├── scoring/
│   ├── code_quality.py    # Scoring functions
│   ├── test_quality.py
│   └── boundary_adherence.py
└── results/
    ├── 2024-02-16_run_001.json
    └── 2024-02-16_run_002.json
```

---

## Running and Analyzing Evals

### Command Line Interface

```python
# evals/cli.py
import click
from pathlib import Path
from evals.runner import EvalRunner
from evals.tasks import load_all_tasks

@click.group()
def cli():
    """Agent eval CLI"""
    pass

@cli.command()
@click.option('--task-id', help='Run specific task')
@click.option('--type', help='Run all tasks of type (code_gen, test_write, etc)')
@click.option('--output', default='results/', help='Output directory')
def run(task_id, type, output):
    """Run evals"""
    runner = EvalRunner(workspace_dir=Path("./eval_workspace"))
    
    if task_id:
        tasks = [load_task(task_id)]
    elif type:
        tasks = load_tasks_by_type(type)
    else:
        tasks = load_all_tasks()
    
    results = []
    for task in tasks:
        print(f"Running {task.task_id}...")
        result = runner.run_eval(task, your_agent_function)
        results.append(result)
        print(f"  Score: {result.score:.2f} - {'PASS' if result.passed else 'FAIL'}")
    
    # Save results
    save_results(results, output)
    
    # Print summary
    print_summary(results)

@cli.command()
@click.argument('results_file')
def analyze(results_file):
    """Analyze eval results"""
    results = load_results(results_file)
    
    print(f"\n{'='*60}")
    print(f"Eval Run Analysis: {results_file}")
    print(f"{'='*60}\n")
    
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    avg_score = sum(r.score for r in results) / total
    
    print(f"Total Tasks: {total}")
    print(f"Passed: {passed} ({passed/total:.1%})")
    print(f"Failed: {total - passed}")
    print(f"Average Score: {avg_score:.2f}")
    
    print(f"\nBy Type:")
    by_type = group_by_type(results)
    for eval_type, type_results in by_type.items():
        type_passed = sum(1 for r in type_results if r.passed)
        type_avg = sum(r.score for r in type_results) / len(type_results)
        print(f"  {eval_type}: {type_passed}/{len(type_results)} ({type_avg:.2f})")
    
    print(f"\nFailed Tasks:")
    for r in results:
        if not r.passed:
            print(f"  - {r.task_id} (score: {r.score:.2f})")
            if r.errors:
                for error in r.errors:
                    print(f"    Error: {error}")
            if r.boundary_violations:
                for violation in r.boundary_violations:
                    print(f"    Violation: {violation}")

@cli.command()
@click.argument('task_id')
def debug(task_id):
    """Debug a specific failed task"""
    task = load_task(task_id)
    latest_result = load_latest_result(task_id)
    
    print(f"\nTask: {task.task_id}")
    print(f"Description: {task.description}")
    print(f"\nPrompt:")
    print(task.prompt)
    print(f"\nAgent Output:")
    print(latest_result.agent_output)
    print(f"\nTest Results:")
    for test, passed in latest_result.test_results.items():
        status = "✓" if passed else "✗"
        print(f"  {status} {test}")
    print(f"\nCoverage: {latest_result.coverage:.1%}")
    print(f"Type Check: {'✓' if latest_result.type_check_passed else '✗'}")
    
    if latest_result.boundary_violations:
        print(f"\nBoundary Violations:")
        for violation in latest_result.boundary_violations:
            print(f"  - {violation}")

if __name__ == '__main__':
    cli()
```

### Usage Examples

```bash
# Run all evals
python -m evals.cli run

# Run specific eval
python -m evals.cli run --task-id code_gen_001_transform_data

# Run all code generation evals
python -m evals.cli run --type code_gen

# Analyze results
python -m evals.cli analyze results/2024-02-16_run_001.json

# Debug failed task
python -m evals.cli debug code_gen_001_transform_data
```

### Continuous Evaluation

```python
# evals/continuous.py
"""Run evals on every commit"""

def run_on_commit():
    """
    Git hook to run evals.
    
    Put this in .git/hooks/pre-push:
    #!/bin/bash
    python -m evals.continuous
    """
    import sys
    from evals.cli import run
    
    # Run fast evals only (< 30 seconds)
    results = run(type="fast")
    
    # Block push if critical evals fail
    critical_failed = [r for r in results if r.task_id.startswith("critical_") and not r.passed]
    
    if critical_failed:
        print("❌ Critical evals failed - push blocked")
        for r in critical_failed:
            print(f"  - {r.task_id}")
        sys.exit(1)
    
    print("✓ All critical evals passed")
    sys.exit(0)
```

### Eval Result Visualization

```python
# evals/visualize.py
import matplotlib.pyplot as plt
from pathlib import Path
import json

def plot_eval_trends(results_dir: Path):
    """Plot eval performance over time"""
    results_files = sorted(results_dir.glob("*.json"))
    
    dates = []
    pass_rates = []
    avg_scores = []
    
    for file in results_files:
        results = json.loads(file.read_text())
        date = file.stem.split("_")[0]
        
        dates.append(date)
        pass_rates.append(
            sum(1 for r in results if r["passed"]) / len(results)
        )
        avg_scores.append(
            sum(r["score"] for r in results) / len(results)
        )
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
    
    # Pass rate over time
    ax1.plot(dates, pass_rates, marker='o')
    ax1.set_title("Eval Pass Rate Over Time")
    ax1.set_ylabel("Pass Rate")
    ax1.set_ylim(0, 1)
    ax1.grid(True)
    
    # Average score over time
    ax2.plot(dates, avg_scores, marker='o', color='green')
    ax2.set_title("Average Eval Score Over Time")
    ax2.set_ylabel("Score")
    ax2.set_ylim(0, 1)
    ax2.grid(True)
    
    plt.tight_layout()
    plt.savefig("eval_trends.png")
    print("Saved eval_trends.png")
```

---

## Practical Examples

### Example 1: Full Workflow for New Feature

```bash
# 1. Write spec
vim specs/features/email_validation.md

# 2. Write tests from spec
vim tests/unit/test_email_validation.py

# 3. Create eval task
vim evals/tasks/code_generation/email_validation_eval.py

# 4. Run eval to see baseline (should fail - no code yet)
python -m evals.cli run --task-id code_gen_email_validation

# 5. Implement feature
vim src/validation/email.py

# 6. Run tests
pytest tests/unit/test_email_validation.py -v

# 7. Run eval again (should pass now)
python -m evals.cli run --task-id code_gen_email_validation

# 8. Commit
git add .
git commit -m "feat: add email validation per spec"
```

### Example 2: Agent Eval Task

```python
# evals/tasks/code_generation/email_validation_eval.py

from evals.eval_schema import EvalTask, EvalType
from evals.scoring.code_quality import score_functional_code

def create_email_validation_eval() -> EvalTask:
    return EvalTask(
        task_id="code_gen_002_email_validation",
        eval_type=EvalType.CODE_GEN,
        description="Implement email validation from spec",
        
        spec_file="specs/features/email_validation.md",
        code_file=None,
        test_file="tests/unit/test_email_validation.py",
        claude_md_file="src/validation/CLAUDE.md",
        
        prompt="""
        Implement email validation according to the spec.
        
        Read:
        - specs/features/email_validation.md for requirements
        - src/validation/CLAUDE.md for autonomy boundaries
        - tests/unit/test_email_validation.py to see what tests expect
        
        Create:
        - src/validation/email.py with validate_email function
        
        Requirements:
        - Pure function (no side effects)
        - Use frozen dataclasses for errors
        - Return Result[ValidEmail, ValidationError]
        - Handle all edge cases from spec
        - Follow functional programming principles
        
        The tests are already written. Make them pass.
        """,
        
        success_criteria=[
            "All tests pass",
            "Type hints on all functions",
            "Coverage >= 95%",
            "Pure functions only",
            "Returns Result types"
        ],
        
        scoring_function=score_functional_code,
        
        expected_files_created=["src/validation/email.py"],
        must_not_modify=[
            "tests/unit/test_email_validation.py",
            "specs/",
            "src/validation/phone.py"  # Other module
        ],
        
        required_tests_pass=[
            "pytest tests/unit/test_email_validation.py -v"
        ],
        required_coverage=0.95,
        required_type_check=True
    )
```

### Example 3: Measuring Agent Improvement

```python
# Track how agent improves over time

from datetime import datetime
from evals.runner import EvalRunner
from evals.tasks import load_all_tasks

def benchmark_agent_versions():
    """Compare different agent versions"""
    
    runner = EvalRunner(workspace_dir=Path("./eval_workspace"))
    tasks = load_all_tasks()
    
    agents = {
        "baseline": baseline_agent,
        "with_examples": agent_with_examples,
        "with_cot": agent_with_chain_of_thought,
    }
    
    results = {}
    
    for agent_name, agent_func in agents.items():
        print(f"\nTesting {agent_name}...")
        agent_results = []
        
        for task in tasks:
            result = runner.run_eval(task, agent_func)
            agent_results.append(result)
            print(f"  {task.task_id}: {result.score:.2f}")
        
        results[agent_name] = {
            "pass_rate": sum(1 for r in agent_results if r.passed) / len(agent_results),
            "avg_score": sum(r.score for r in agent_results) / len(agent_results),
            "results": agent_results
        }
    
    # Print comparison
    print(f"\n{'='*60}")
    print("Agent Comparison")
    print(f"{'='*60}")
    
    for agent_name, metrics in results.items():
        print(f"\n{agent_name}:")
        print(f"  Pass Rate: {metrics['pass_rate']:.1%}")
        print(f"  Avg Score: {metrics['avg_score']:.2f}")
    
    # Find best agent
    best = max(results.items(), key=lambda x: x[1]['avg_score'])
    print(f"\nBest Agent: {best[0]} ({best[1]['avg_score']:.2f})")
```

---

## Quick Start Checklist

### Setting Up Spec-Driven Development

- [ ] Create `/specs` directory structure
- [ ] Write first feature spec using template
- [ ] Write tests that validate the spec
- [ ] Implement minimal code to pass tests
- [ ] Verify with: pytest, mypy, coverage

### Setting Up Agent Evals

- [ ] Create `/evals` directory structure  
- [ ] Define `EvalTask` and `EvalResult` schemas
- [ ] Create `EvalRunner` class
- [ ] Write 1-2 simple eval tasks
- [ ] Run evals and iterate
- [ ] Add CLI for running evals
- [ ] Set up continuous eval on commits

### Daily Workflow

**Morning:**
1. Review yesterday's eval results
2. Identify patterns in failures
3. Update specs based on learnings

**Development:**
1. Write/update spec for feature
2. Write tests from spec
3. Implement code
4. Run local tests
5. Run evals

**Before Commit:**
1. All tests pass
2. Type check passes
3. Coverage meets threshold
4. Critical evals pass
5. Commit with clear message

**Weekly:**
1. Review eval trends
2. Add new eval tasks for common failures
3. Update CLAUDE.md files based on agent confusion
4. Refine specs based on implementation learnings

---

## Key Principles to Remember

1. **Specs are executable** - If you can't write a test for it, your spec is too vague
2. **Tests document intent** - They're the most honest form of specification
3. **Evals measure reality** - They show you if agents can actually work with your design
4. **Iterate quickly** - Spec → Test → Code → Eval → Refine should be fast
5. **Boundaries enable autonomy** - Clear contracts let agents work independently
6. **Failures teach** - Every eval failure reveals unclear specs or poor abstractions

---

## Advanced Topics

### Property-Based Testing with Specs

```python
from hypothesis import given, strategies as st

@given(st.text(), st.integers(min_value=1))
def test_transform_properties(field, count):
    """Property: output always contains input field"""
    input_data = InputData(field=field, count=count)
    result = transform_data(input_data)
    
    if isinstance(result, Success):
        assert field in result.value.result
```

### Spec Versioning

```markdown
# Spec: Email Validation v2.0

## Changelog
- v2.0 (2024-02-16): Added international email support
- v1.1 (2024-01-15): Clarified error messages
- v1.0 (2024-01-01): Initial spec

## Breaking Changes from v1.x
- Now accepts emails with unicode characters
- Error messages have new structure
```

### Multi-Agent Evals

```python
def test_agents_cooperate():
    """Two agents working on different modules"""
    
    # Agent A implements validation
    result_a = run_eval(validation_task, agent_a)
    
    # Agent B implements transformation, depends on A
    result_b = run_eval(transform_task, agent_b)
    
    # Integration test
    assert result_a.passed
    assert result_b.passed
    assert integration_tests_pass()
```

---

This guide gives you everything you need to drive your project forward with specs and measure agent performance. Start small, iterate quickly, and let the evals guide your improvements.