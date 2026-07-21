#!/bin/bash
# .ci/run-ci-steps.sh - Main CI orchestrator
set -euo pipefail

SCRIPT_DIR=$(dirname "$0")
source "${SCRIPT_DIR}/ci-common.sh"

# LIBCXX_ASAN_ROOT comes from ci-common.sh sourcing the image's
# env-python-asan.sh; LIBCXX_MSAN_ROOT is resolved by env-msan.sh when the
# msan variant is selected.
export SYMENGINE_RCP_CHOICE=cooperative_intrusive

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

# The package lists live with the image definition
# (bjodah-containers/triceratops/env-N/pip-requirements-ci-*.txt) and are
# pre-installed into the image, so these installs are no-op verifications on a
# current image (and keep working offline). Keep symengine.py's build backend
# (hatchling) in the default lane because the later editable install uses
# --no-build-isolation.
echo "=== Preparing Default Python Lane ==="
ci_use_python_toolchain default
ci_pip install -r "${CI_TOOLCHAIN_ENV_DIR}/pip-requirements-ci-default.txt"

echo "=== Preparing ASAN Python Lane ==="
if [[ "${RUN_ASAN}" == "yes" ]]; then
    ci_use_python_toolchain asan
    ci_pip install -r "${CI_TOOLCHAIN_ENV_DIR}/pip-requirements-ci-sanitizer.txt"
else
    echo "ASAN lane is disabled or skipped."
fi

echo "=== Preparing TSAN Python Lane ==="
ci_use_python_toolchain tsan
ci_pip install -r "${CI_TOOLCHAIN_ENV_DIR}/pip-requirements-ci-sanitizer.txt"

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

if [[ "${CI_CXX14_COOPERATIVE_INTRUSIVE:-yes}" == "yes" ]]; then
    echo "=== 3. Core C++14 thread-safe cooperative-intrusive build ==="
    env SYMENGINE_VARIANT=cxx14 CMAKE_ARGS="-DWITH_SYMENGINE_THREAD_SAFE=yes" \
        "${SCRIPT_DIR}/ci-01-build-and-test.sh" /tmp/bld-se-cxx14 /tmp/symen-cxx14
fi

echo "=== 4. nbsymengine debug build ==="
env SYMENGINE_VARIANT=debug "${SCRIPT_DIR}/ci-02-build-and-test-nbsymengine.sh" /tmp/bld-nbse-debug

echo "=== 5. nbsymengine_compat debug tests ==="
"${SCRIPT_DIR}/ci-03-build-and-test-nbsymengine_compat.sh" /tmp/bld-nbse-debug

echo "=== 6. nbsymengine glibcxxdbg build ==="
env SYMENGINE_VARIANT=glibcxxdbg "${SCRIPT_DIR}/ci-02-build-and-test-nbsymengine.sh" /tmp/bld-nbse-glibcxxdbg

echo "=== 7. Leak tests ==="
"${SCRIPT_DIR}/ci-04-leak-test.sh" /tmp/bld-nbse-debug

echo "=== 8. Perl XS extension build and tests ==="
ci_use_perl_toolchain
env SYMENGINE_VARIANT=debug "${SCRIPT_DIR}/ci-05-build-and-test-perl.sh" /tmp/bld-perl-debug

echo "=== 9. PHP extension build and tests ==="
ci_use_php_toolchain
# Reuse the debug SymEngine build installed by lane 1. The PHP extension is
# built out of tree and links against that install tree; no second core build
# is needed here.
env SYMENGINE_VARIANT=debug "${SCRIPT_DIR}/ci-06-build-and-test-php.sh" /tmp/bld-se-debug /tmp/symen-debug /tmp/bld-php-ext

echo "=== 10. Swift package build and tests ==="
env SYMENGINE_VARIANT=debug "${SCRIPT_DIR}/ci-07-build-and-test-swift.sh" /tmp/bld-se-swift /tmp/bld-swift-package

echo "=== 11. Java JNI build and tests (ordinary RCP) ==="
ci_use_java_toolchain
env SYMENGINE_VARIANT=debug "${SCRIPT_DIR}/ci-08-build-and-test-java.sh" /tmp/bld-java-debug

# --- ASAN Python Lane Execution ---
if [[ "${RUN_ASAN}" == "yes" ]]; then
    ci_use_python_toolchain asan

    echo "=== 12. Core C++ ASAN build ==="
    env SYMENGINE_VARIANT=asan "${SCRIPT_DIR}/ci-01-build-and-test.sh" /tmp/bld-se-asan /tmp/symen-asan

    echo "=== 13. nbsymengine ASAN build ==="
    env SYMENGINE_VARIANT=asan "${SCRIPT_DIR}/ci-02-build-and-test-nbsymengine.sh" /tmp/bld-nbse-asan
fi

# --- TSAN Python Lane Execution ---
ci_use_python_toolchain tsan

echo "=== 14. Core C++ TSAN build ==="
env SYMENGINE_VARIANT=tsan "${SCRIPT_DIR}/ci-01-build-and-test.sh" /tmp/bld-se-tsan /tmp/symen-tsan

echo "=== 15. nbsymengine TSAN build ==="
env SYMENGINE_VARIANT=tsan "${SCRIPT_DIR}/ci-02-build-and-test-nbsymengine.sh" /tmp/bld-nbse-tsan

echo "=== CI steps completed successfully ==="
