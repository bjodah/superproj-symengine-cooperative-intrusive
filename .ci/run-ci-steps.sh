#!/bin/bash
# .ci/run-ci-steps.sh - Main CI orchestrator
set -euo pipefail

SCRIPT_DIR=$(dirname "$0")
source "${SCRIPT_DIR}/ci-common.sh"

export SYMENGINE_RCP_CHOICE=cooperative_intrusive
export LIBCXX_ASAN_ROOT="$(compgen -G "/opt*/libcxx*-asan/" | sort -rV | head -1 || true)"
export LIBCXX_ASAN_ROOT="${LIBCXX_ASAN_ROOT%/}"
export LIBCXX_MSAN_ROOT="$(compgen -G "/opt*/libcxx*-msan/" | sort -rV | head -1 || true)"
export LIBCXX_MSAN_ROOT="${LIBCXX_MSAN_ROOT%/}"

# Check for ASAN toolchain and determine if we should run the ASAN lane
RUN_ASAN=yes
if [[ "${CI_ENABLE_ASAN:-}" == "no" ]]; then
    RUN_ASAN=no
fi

if [[ -n "${CI:-}" ]]; then
    if [[ -z "${LIBCXX_ASAN_ROOT:-}" ]]; then
        echo "Error: LIBCXX_ASAN_ROOT is missing in CI environment!" >&2
        exit 1
    fi
    if [[ -z "${CI_ASAN_PYTHON_ROOT:-}" ]]; then
        echo "Error: CI_ASAN_PYTHON_ROOT is missing in CI environment!" >&2
        exit 1
    fi
    if [[ ! -x "${CI_ASAN_PYTHON:-}" || ! -x "${CI_ASAN_PIP:-}" ]]; then
        echo "Error: ASAN Python executables are missing in CI environment!" >&2
        exit 1
    fi
else
    if [[ -z "${LIBCXX_ASAN_ROOT:-}" || -z "${CI_ASAN_PYTHON_ROOT:-}" || ! -x "${CI_ASAN_PYTHON:-}" || ! -x "${CI_ASAN_PIP:-}" ]]; then
        echo "Warning: ASAN toolchain components not found. Skipping ASAN lane."
        RUN_ASAN=no
    fi
fi

echo "=== Preparing Default Python Lane ==="
ci_use_python_toolchain default
# Install baseline Python tooling needed by CI.
# Keep symengine.py's build backend in the environment because the later
# editable install uses --no-build-isolation.
ci_pip install munch srcml_caller libcst nanobind hatchling pytest numpy scipy sympy scikit-build-core setuptools-scm cython cython-cmake pyyaml jsonschema

echo "=== Preparing ASAN Python Lane ==="
if [[ "${RUN_ASAN}" == "yes" ]]; then
    ci_use_python_toolchain asan
    ci_pip install munch srcml_caller libcst nanobind pytest sympy
else
    echo "ASAN lane is disabled or skipped."
fi

echo "=== Preparing TSAN Python Lane ==="
ci_use_python_toolchain tsan
# Install nanobind for TSAN lane (do not install numpy, scipy, sympy yet)
ci_pip install nanobind

# --- Default Python Lane Execution ---
ci_use_python_toolchain default

echo "=== 0. Shared binding spec validation and renderers ==="
(cd "${SUPERPROJECT_ROOT}" && python3 -m tools.binding_codegen check)
(cd "${SUPERPROJECT_ROOT}" && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/test_binding_codegen.py -q)
# No --python-stub here: the nbsymengine build tree that produces the .pyi
# does not exist yet at this point. Step 3 below runs the Python check once
# it does.
(cd "${SUPERPROJECT_ROOT}" && python3 tools/check_binding_api_fixtures.py)

echo "=== 1. Core C++ debug build ==="
env SYMENGINE_VARIANT=debug "${SCRIPT_DIR}/ci-01-build-and-test.sh" /tmp/bld-se-debug /tmp/symen-debug

echo "=== 2. Core C++ glibcxxdbg build ==="
env SYMENGINE_VARIANT=glibcxxdbg "${SCRIPT_DIR}/ci-01-build-and-test.sh" /tmp/bld-se-glibcxxdbg /tmp/symen-glibcxxdbg

echo "=== 3. nbsymengine debug build ==="
env SYMENGINE_VARIANT=debug "${SCRIPT_DIR}/ci-02-build-and-test-nbsymengine.sh" /tmp/bld-nbse-debug

echo "=== 4. nbsymengine_compat debug tests ==="
"${SCRIPT_DIR}/ci-03-build-and-test-nbsymengine_compat.sh" /tmp/bld-nbse-debug

echo "=== 5. nbsymengine glibcxxdbg build ==="
env SYMENGINE_VARIANT=glibcxxdbg "${SCRIPT_DIR}/ci-02-build-and-test-nbsymengine.sh" /tmp/bld-nbse-glibcxxdbg

echo "=== 6. Leak tests ==="
"${SCRIPT_DIR}/ci-04-leak-test.sh" /tmp/bld-nbse-debug

echo "=== 7. Perl XS extension build and tests ==="
ci_use_perl_toolchain
env SYMENGINE_VARIANT=debug "${SCRIPT_DIR}/ci-05-build-and-test-perl.sh" /tmp/bld-perl-debug

echo "=== 8. PHP extension build and tests ==="
ci_use_php_toolchain
env SYMENGINE_VARIANT=debug "${SCRIPT_DIR}/ci-06-build-and-test-php.sh" /tmp/bld-se-php /tmp/inst-se-php /tmp/bld-php-ext

echo "=== 9. Swift package build and tests ==="
env SYMENGINE_VARIANT=debug "${SCRIPT_DIR}/ci-07-build-and-test-swift.sh" /tmp/bld-se-swift /tmp/bld-swift-package

echo "=== 10. Java JNI build and tests (ordinary RCP) ==="
ci_use_java_toolchain
env SYMENGINE_VARIANT=debug "${SCRIPT_DIR}/ci-08-build-and-test-java.sh" /tmp/bld-java-debug

# --- ASAN Python Lane Execution ---
if [[ "${RUN_ASAN}" == "yes" ]]; then
    ci_use_python_toolchain asan

    echo "=== 11. Core C++ ASAN build ==="
    env SYMENGINE_VARIANT=asan "${SCRIPT_DIR}/ci-01-build-and-test.sh" /tmp/bld-se-asan /tmp/symen-asan

    echo "=== 12. nbsymengine ASAN build ==="
    env SYMENGINE_VARIANT=asan "${SCRIPT_DIR}/ci-02-build-and-test-nbsymengine.sh" /tmp/bld-nbse-asan
fi

# --- TSAN Python Lane Execution ---
ci_use_python_toolchain tsan

echo "=== 13. Core C++ TSAN build ==="
env SYMENGINE_VARIANT=tsan "${SCRIPT_DIR}/ci-01-build-and-test.sh" /tmp/bld-se-tsan /tmp/symen-tsan

echo "=== 14. nbsymengine TSAN build ==="
env SYMENGINE_VARIANT=tsan "${SCRIPT_DIR}/ci-02-build-and-test-nbsymengine.sh" /tmp/bld-nbse-tsan

echo "=== CI steps completed successfully ==="
