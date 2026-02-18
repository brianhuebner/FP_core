#!/bin/bash
# Run FP_core agent evals.
#
# Usage:
#   ./evals/run_eval.sh 1         # Run Eval 1 (Build Pipeline)
#   ./evals/run_eval.sh 2         # Run Eval 2 (Process Data)
#   ./evals/run_eval.sh 3         # Run Eval 3 (Build Output Format)
#   ./evals/run_eval.sh 4         # Run Eval 4 (Process with Format)
#   ./evals/run_eval.sh 5         # Run Eval 5 (Group-By / Split-By)
#   ./evals/run_eval.sh all       # Run all evals
#
# Requirements:
#   - NEO4J_URI and NEO4J_PASSWORD env vars set
#   - claude CLI available on PATH
#   - .mcp.json configured at project root

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="$SCRIPT_DIR/results/${TIMESTAMP}"
MCP_CONFIG="$PROJECT_ROOT/.mcp.json"

# Verify prerequisites
if [ -z "${NEO4J_URI:-}" ] || [ -z "${NEO4J_PASSWORD:-}" ]; then
    echo "ERROR: NEO4J_URI and NEO4J_PASSWORD env vars must be set."
    exit 1
fi

if ! command -v claude &> /dev/null; then
    echo "ERROR: claude CLI not found on PATH."
    exit 1
fi

# Activate virtualenv
PYTHON="$PROJECT_ROOT/.venv/bin/python"
if [ ! -f "$PYTHON" ]; then
    echo "ERROR: virtualenv not found at $PROJECT_ROOT/.venv"
    exit 1
fi

# Pre-authorize MCP tools and file operations for non-interactive agent runs
ALLOWED_TOOLS="mcp__fp_core__load_recipe mcp__fp_core__load_format mcp__fp_core__get_processing_instructions mcp__fp_core__build_and_save_pipeline mcp__fp_core__build_output mcp__fp_core__validate_entries Read Write Glob"

mkdir -p "$RESULTS_DIR"
echo "Results directory: $RESULTS_DIR"
echo ""

# ─────────────────────────────────────────────────────────────
# Eval 1: Build Pipeline
# ─────────────────────────────────────────────────────────────
run_eval_01() {
    echo "════════════════════════════════════════════════════════════"
    echo "  Eval 1: Build Pipeline"
    echo "════════════════════════════════════════════════════════════"

    RECIPE_ID="eval_build_pipeline_${TIMESTAMP}"
    echo "  Recipe ID: $RECIPE_ID"
    echo ""

    # Inject unique recipe_id into prompt
    PROMPT=$(sed "s/{{RECIPE_ID}}/$RECIPE_ID/" "$SCRIPT_DIR/scenarios/eval_01_build_pipeline.md")

    echo "  Invoking agent..."
    claude --print -p "$PROMPT" \
        --mcp-config "$MCP_CONFIG" \
        --allowedTools $ALLOWED_TOOLS \
        > "$RESULTS_DIR/eval_01_agent_output.txt" 2>&1 || true

    echo "  Agent output saved to: $RESULTS_DIR/eval_01_agent_output.txt"
    echo ""

    # Validate
    echo "  Running validator..."
    "$PYTHON" "$SCRIPT_DIR/validators/validate_eval_01.py" "$RECIPE_ID" "$RESULTS_DIR"
}

# ─────────────────────────────────────────────────────────────
# Eval 2: Process Data
# ─────────────────────────────────────────────────────────────
run_eval_02() {
    echo "════════════════════════════════════════════════════════════"
    echo "  Eval 2: Process Data"
    echo "════════════════════════════════════════════════════════════"

    RECIPE_ID="eval_payroll_v1"
    echo "  Recipe ID: $RECIPE_ID"
    echo ""

    # Setup: load recipe into Neo4j
    echo "  Loading recipe into Neo4j..."
    "$PYTHON" "$SCRIPT_DIR/setup_eval_02.py" "$RECIPE_ID"
    echo ""

    # Read prompt
    PROMPT=$(cat "$SCRIPT_DIR/scenarios/eval_02_process_data.md")

    echo "  Invoking agent..."
    claude --print -p "$PROMPT" \
        --mcp-config "$MCP_CONFIG" \
        --allowedTools $ALLOWED_TOOLS \
        > "$RESULTS_DIR/eval_02_agent_output.txt" 2>&1 || true

    echo "  Agent output saved to: $RESULTS_DIR/eval_02_agent_output.txt"
    echo ""

    # Copy output CSV to results dir if agent wrote it to default location
    if [ -f "$PROJECT_ROOT/evals/results/eval_02_output.csv" ]; then
        cp "$PROJECT_ROOT/evals/results/eval_02_output.csv" "$RESULTS_DIR/eval_02_output.csv"
    fi

    # Validate
    echo "  Running validator..."
    "$PYTHON" "$SCRIPT_DIR/validators/validate_eval_02.py" "$RESULTS_DIR"
}

# ─────────────────────────────────────────────────────────────
# Eval 3: Build Output Format
# ─────────────────────────────────────────────────────────────
run_eval_03() {
    echo "════════════════════════════════════════════════════════════"
    echo "  Eval 3: Build Output Format"
    echo "════════════════════════════════════════════════════════════"

    FORMAT_ID="eval_format_${TIMESTAMP}"
    echo "  Format ID: $FORMAT_ID"
    echo ""

    # Inject unique format_id into prompt
    PROMPT=$(sed "s/{{FORMAT_ID}}/$FORMAT_ID/" "$SCRIPT_DIR/scenarios/eval_03_build_format.md")

    echo "  Invoking agent..."
    claude --print -p "$PROMPT" \
        --mcp-config "$MCP_CONFIG" \
        --allowedTools $ALLOWED_TOOLS \
        > "$RESULTS_DIR/eval_03_agent_output.txt" 2>&1 || true

    echo "  Agent output saved to: $RESULTS_DIR/eval_03_agent_output.txt"
    echo ""

    # Validate
    echo "  Running validator..."
    "$PYTHON" "$SCRIPT_DIR/validators/validate_eval_03.py" "$FORMAT_ID" "$RESULTS_DIR"
}

# ─────────────────────────────────────────────────────────────
# Eval 4: Process Data with Independent Format
# ─────────────────────────────────────────────────────────────
run_eval_04() {
    echo "════════════════════════════════════════════════════════════"
    echo "  Eval 4: Process with Format"
    echo "════════════════════════════════════════════════════════════"

    RECIPE_ID="eval_payroll_v1"
    FORMAT_ID="eval_fmt_${TIMESTAMP}"
    echo "  Recipe ID: $RECIPE_ID"
    echo "  Format ID: $FORMAT_ID"
    echo ""

    # Setup: load recipe (without output format) into Neo4j
    echo "  Loading recipe (no format) into Neo4j..."
    "$PYTHON" "$SCRIPT_DIR/setup_eval_04.py" "$RECIPE_ID"
    echo ""

    # Inject both IDs into prompt
    PROMPT=$(sed -e "s/{{RECIPE_ID}}/$RECIPE_ID/g" -e "s/{{FORMAT_ID}}/$FORMAT_ID/g" \
        "$SCRIPT_DIR/scenarios/eval_04_process_with_format.md")

    echo "  Invoking agent..."
    claude --print -p "$PROMPT" \
        --mcp-config "$MCP_CONFIG" \
        --allowedTools $ALLOWED_TOOLS \
        > "$RESULTS_DIR/eval_04_agent_output.txt" 2>&1 || true

    echo "  Agent output saved to: $RESULTS_DIR/eval_04_agent_output.txt"
    echo ""

    # Copy output CSV to results dir if agent wrote it to default location
    if [ -f "$PROJECT_ROOT/evals/results/eval_04_output.csv" ]; then
        cp "$PROJECT_ROOT/evals/results/eval_04_output.csv" "$RESULTS_DIR/eval_04_output.csv"
    fi

    # Validate
    echo "  Running validator..."
    "$PYTHON" "$SCRIPT_DIR/validators/validate_eval_04.py" "$FORMAT_ID" "$RESULTS_DIR"
}

# ─────────────────────────────────────────────────────────────
# Eval 5: Build Pipeline with Group-By / Split-By
# ─────────────────────────────────────────────────────────────
run_eval_05() {
    echo "════════════════════════════════════════════════════════════"
    echo "  Eval 5: Group-By / Split-By"
    echo "════════════════════════════════════════════════════════════"

    RECIPE_ID="eval_group_by_${TIMESTAMP}"
    echo "  Recipe ID: $RECIPE_ID"
    echo ""

    # Inject unique recipe_id into prompt
    PROMPT=$(sed "s/{{RECIPE_ID}}/$RECIPE_ID/" "$SCRIPT_DIR/scenarios/eval_05_group_by_split_by.md")

    echo "  Invoking agent..."
    claude --print -p "$PROMPT" \
        --mcp-config "$MCP_CONFIG" \
        --allowedTools $ALLOWED_TOOLS \
        > "$RESULTS_DIR/eval_05_agent_output.txt" 2>&1 || true

    echo "  Agent output saved to: $RESULTS_DIR/eval_05_agent_output.txt"
    echo ""

    # Validate
    echo "  Running validator..."
    "$PYTHON" "$SCRIPT_DIR/validators/validate_eval_05.py" "$RECIPE_ID" "$RESULTS_DIR"
}

# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────
EVAL_NUM="${1:-all}"

case "$EVAL_NUM" in
    1)
        run_eval_01
        ;;
    2)
        run_eval_02
        ;;
    3)
        run_eval_03
        ;;
    4)
        run_eval_04
        ;;
    5)
        run_eval_05
        ;;
    all)
        run_eval_01
        echo ""
        run_eval_02
        echo ""
        run_eval_03
        echo ""
        run_eval_04
        echo ""
        run_eval_05
        ;;
    *)
        echo "Usage: $0 [1|2|3|4|all]"
        exit 1
        ;;
esac

echo ""
echo "Results saved to: $RESULTS_DIR"
