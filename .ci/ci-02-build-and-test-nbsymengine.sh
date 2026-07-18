#!/bin/bash
# .ci/ci-02-build-and-test-nbsymengine.sh - Build and test nbsymengine Python bindings
set -euo pipefail

SCRIPT_DIR=$(dirname "$0")
source "${SCRIPT_DIR}/ci-common.sh"
# Keep CTest's pytest-backed entries independent of plugins installed on the
# worker image (notably pytest-black's incompatible hookspec on some images).
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
SYMENGINE_VARIANT="${SYMENGINE_VARIANT:-debug}"
export SYMENGINE_VARIANT
ci_ensure_python_toolchain
ci_set_tsan_prefix

SYMENGINE_BUILD=$1
if [[ -z "${SYMENGINE_BUILD}" ]]; then
    >&2 echo "Usage: $0 <build-dir>"
    exit 1
fi

if [[ "${SYMENGINE_RCP_CHOICE:-}" != "cooperative_intrusive" ]]; then
    >&2 echo "Error: SYMENGINE_RCP_CHOICE must be set to cooperative_intrusive for nbsymengine builds."
    exit 1
fi

# Set compiler/linker flags for the variant
ci_set_variant_flags "${SYMENGINE_VARIANT}"

# Apply RCP choice backend settings (adds cooperative_intrusive and nanobind_DIR to CMAKE_ARGS)
ci_apply_rcp_choice

# Add Python arguments for nanobind and python selection
CMAKE_ARGS="${CMAKE_ARGS} -DBUILD_PYTHON_NANOBIND=ON -DPython_EXECUTABLE=${CI_PYTHON} -DPython_ROOT_DIR=${CI_PYTHON_ROOT}"

# Configure
cmake \
    -G Ninja \
    -DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
    -DCMAKE_C_COMPILER_LAUNCHER="${COMPILER_LAUNCHER:-ccache}" \
    -DCMAKE_CXX_COMPILER_LAUNCHER="${COMPILER_LAUNCHER:-ccache}" \
    -DBUILD_SHARED_LIBS=ON \
    -DBUILD_TESTS=ON \
    -DBUILD_BENCHMARKS=OFF \
    ${CMAKE_ARGS} \
    -S "$SUPERPROJECT_ROOT" \
    -B "$SYMENGINE_BUILD"

# Build
cmake --build "$SYMENGINE_BUILD" --clean-first --verbose

# Check the shared binding API fixtures against the .pyi this build just
# generated, now that a real stub exists.
NBSYMENGINE_GENERATED_PYI="$SYMENGINE_BUILD/nbsymengine/generated/symengine.pyi"
if [[ -f "${NBSYMENGINE_GENERATED_PYI}" ]]; then
    "$CI_PYTHON" "${SUPERPROJECT_ROOT}/tools/check_binding_api_fixtures.py" --python-stub "${NBSYMENGINE_GENERATED_PYI}"
else
    echo "SKIPPED: check_binding_api_fixtures.py (no generated .pyi at ${NBSYMENGINE_GENERATED_PYI})"
fi

# Subprocess-based tests need an explicit interpreter override when the
# active lane uses a non-default Python toolchain.
export NBSYMENGINE_SUBPROCESS_PYTHON="${CI_PYTHON}"

# Render the shared behavioral test cases (binding-spec/test-cases.yaml) into a
# scratch directory and run them against this build's nbsymengine, mirroring
# every other wrapper lane's shared_cases coverage. Generation stays out of
# the nbsymengine submodule; only .ci/ owns this wiring.
SHARED_CASES_DIR="${SYMENGINE_BUILD}/binding-generated/python"
(cd "${SUPERPROJECT_ROOT}" && "$CI_PYTHON" -m tools.binding_codegen generate \
    --language python --output "${SHARED_CASES_DIR}")
PYTHONPATH="${SYMENGINE_BUILD}:${PYTHONPATH:-}" ${TSAN_PREFIX} "$CI_PYTHON" -m pytest -x \
    "${SHARED_CASES_DIR}/test_shared_cases.py" --tb=short -q

# Run tests
pushd "$SYMENGINE_BUILD"
if [[ "${SYMENGINE_VARIANT}" == "tsan" ]]; then
    # Keep the TSAN lane minimal as requested in the plan
    # Run only a small explicit subset:
    ${TSAN_PREFIX} ctest --output-on-failure -R '^nanobind_(nbsymengine_import|ownership|generated_smoke|generated_rcp|threading_stress)$'
else
    # Run only the nanobind-related CTest entries (do not rerun core SymEngine C++ tests here)
    ${TSAN_PREFIX} ctest --output-on-failure -R '^nanobind_'
fi
popd

# Extra pytest-only coverage for non-TSAN variants
if [[ "${SYMENGINE_VARIANT}" == "asan" ]]; then
    echo "=== Running minimal pytest-only coverage for ASAN ==="
    PYTHONPATH="${SYMENGINE_BUILD}:${PYTHONPATH:-}" ${TSAN_PREFIX} "$CI_PYTHON" -m pytest -x "${SUPERPROJECT_ROOT}/nbsymengine/tests/test_lambdify_direct.py" --tb=short -q
elif [[ "${SYMENGINE_VARIANT}" != "tsan" ]]; then
    echo "=== Running extra pytest-only coverage ==="
    ci_pip install --no-build-isolation -e "$SCRIPT_DIR/../symengine.py" -Ccmake.define.SymEngine_DIR="$SYMENGINE_BUILD"
    PYTHONPATH="${SYMENGINE_BUILD}:${PYTHONPATH:-}" ${TSAN_PREFIX} "$CI_PYTHON" -m pytest -x "${SUPERPROJECT_ROOT}/nbsymengine/tests/test_lambdify_direct.py" --tb=short -q
    
    if [[ -d "${SUPERPROJECT_ROOT}/benchmarks/tests" ]]; then
        PYTHONPATH="${SYMENGINE_BUILD}:${PYTHONPATH:-}" ${TSAN_PREFIX} "$CI_PYTHON" -m pytest -x "${SUPERPROJECT_ROOT}/benchmarks/tests/" --tb=short -q
    fi
fi
