#!/usr/bin/env bash
# regen_converted_tests.sh -- Regenerate the legacy test conversion.
#
# Runs inventory_legacy_tests.py (stdlib ast) and rewrite_legacy_tests.py
# (libcst) in sequence, producing:
#   tests/converted/manifest.json
#   tests/converted/CONVERSION_REPORT.md
#   tests/converted/test_*.py
#
# Requirements: python3, pip-installable libcst (pip install libcst)
#
# Usage:
#   ./external/nbsymengine_compat/tools/regen_converted_tests.sh
#   # or with custom paths:
#   TESTS_DIR=external/symengine.py/symengine/tests \
#   OUT_DIR=tests/converted \
#   ./external/nbsymengine_compat/tools/regen_converted_tests.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPAT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON:-python3}"

if [ -z "${TESTS_DIR:-}" ]; then
    if [ -d "${COMPAT_ROOT}/external/symengine.py/symengine/tests" ]; then
        TESTS_DIR="${COMPAT_ROOT}/external/symengine.py/symengine/tests"
    elif [ -d "${COMPAT_ROOT}/../symengine.py/symengine/tests" ]; then
        TESTS_DIR="${COMPAT_ROOT}/../symengine.py/symengine/tests"
    else
        >&2 echo "ERROR: Could not find symengine.py/symengine/tests directory automatically."
        >&2 echo "Please set TESTS_DIR environment variable."
        exit 1
    fi
fi

OUT_DIR="${OUT_DIR:-$COMPAT_ROOT/tests/converted}"
SHIM_PATH="${SHIM_PATH:-$COMPAT_ROOT/src/nbsymengine_compat/symengine_py_compat.py}"

echo "=== Checking dependencies ==="
"${PYTHON_BIN}" -c "import libcst" 2>/dev/null || {
    echo "ERROR: libcst not installed. Run: pip install libcst"
    exit 1
}

echo "=== Step 1: Inventory ==="
"${PYTHON_BIN}" "$SCRIPT_DIR/inventory_legacy_tests.py" \
    --tests-dir "$TESTS_DIR" \
    --out "$OUT_DIR/manifest.json" \
    --shim-path "$SHIM_PATH"

echo ""
echo "=== Step 2: Rewrite ==="
"${PYTHON_BIN}" "$SCRIPT_DIR/rewrite_legacy_tests.py" \
    --tests-dir "$TESTS_DIR" \
    --out "$OUT_DIR" \
    --shim-path "$SHIM_PATH" \
    --shim-module nbsymengine_compat

echo ""
echo "=== Done ==="
echo "Output: $OUT_DIR"
echo "  manifest.json      -- machine-readable classification"
echo "  CONVERSION_REPORT.md -- human-readable summary"
echo "  test_*.py          -- rewritten test files"
