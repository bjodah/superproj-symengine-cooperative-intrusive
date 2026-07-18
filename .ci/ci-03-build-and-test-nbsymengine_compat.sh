#!/bin/bash
# .ci/ci-03-build-and-test-nbsymengine_compat.sh - Build and test nbsymengine_compat shim
set -euo pipefail

SCRIPT_DIR=$(dirname "$0")
source "${SCRIPT_DIR}/ci-common.sh"
# The converted suite is pytest-based as well, so use the same hermetic plugin
# policy as the CTest lanes.
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
ci_ensure_python_toolchain

SYMENGINE_BUILD=$1
if [[ -z "${SYMENGINE_BUILD}" ]]; then
    >&2 echo "Usage: $0 <nbsymengine-build-dir>"
    exit 1
fi

if [[ ! -d "${SYMENGINE_BUILD}" ]]; then
    >&2 echo "Build directory does not exist: ${SYMENGINE_BUILD}"
    exit 1
fi

COMPAT_DIR="${SUPERPROJECT_ROOT}/nbsymengine_compat"

# 1. Export PYTHONPATH so the built nbsymengine package and benchmarks are importable
export PYTHONPATH="${SYMENGINE_BUILD}:${SUPERPROJECT_ROOT}/benchmarks:${PYTHONPATH:-}"

# 2. Install compat package and test extras
ci_pip install -e "${COMPAT_DIR}[test]"

# 3. Regenerate converted tests from the top-level symengine.py checkout
export TESTS_DIR="${SUPERPROJECT_ROOT}/symengine.py/symengine/tests"
export OUT_DIR="${COMPAT_DIR}/tests/converted"
export SHIM_PATH="${COMPAT_DIR}/src/nbsymengine_compat/symengine_py_compat.py"
export PYTHON="${CI_PYTHON}"

echo "=== Regenerating converted tests ==="
bash "${COMPAT_DIR}/tools/regen_converted_tests.sh"

# 4. Run the compat test suite
echo "=== Running compat test suite ==="
"$CI_PYTHON" -m pytest -x "${COMPAT_DIR}/tests/" --tb=short -q
