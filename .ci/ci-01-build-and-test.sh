#!/bin/bash
# The instrumented-libc++ roots (LIBCXX_ASAN_ROOT / LIBCXX_MSAN_ROOT) are
# resolved by the toolchain env scripts sourced via ci-common.sh; the asan and
# msan variants abort in ci_set_variant_flags if they are missing.
set -euxo pipefail

SCRIPT_DIR=$(dirname "$0")
source "${SCRIPT_DIR}/ci-common.sh"
# CI must not depend on globally installed pytest plugins. Some CTest entries
# execute pytest-backed checks.
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
ci_ensure_python_toolchain
ci_set_tsan_prefix
SYMENGINE_VARIANT="${SYMENGINE_VARIANT:-debug}"
export SYMENGINE_VARIANT

SYMENGINE_BUILD=$1
SYMENGINE_ROOT=$2
if [ ! -d "$(dirname "$SYMENGINE_ROOT")" ]; then
    >&2 echo "Non-existent parent of SYMENGINE_ROOT (second arg): $SYMENGINE_ROOT"
    exit 1
fi

SYMENGINE_SRC=${SUPERPROJECT_ROOT}/symengine

Boost_ROOT=$(compgen -G "${Boost_ROOT:-'/path-not-provided'}" || true)

if [ ! -d "${SYMENGINE_SRC}" ]; then
    >&2 echo "symengine source directory not found at: ${SYMENGINE_SRC}"
    exit 1
fi

# Set compiler/linker flags and default CMAKE_ARGS for the variant
ci_set_variant_flags "${SYMENGINE_VARIANT}"

# Apply SYMENGINE_RCP_CHOICE settings (e.g. for cooperative_intrusive, append backend and nanobind_DIR)
ci_apply_rcp_choice

if [[ "$CMAKE_ARGS" == *INTEGER_CLASS=boostmp* ]]; then
    if [[ ${Boost_ROOT:-""} != "" ]]; then
        export CMAKE_PREFIX_PATH="$Boost_ROOT:${CMAKE_PREFIX_PATH:-''}"
    fi
fi

cmake \
    -G Ninja \
    -DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
    -DCMAKE_C_COMPILER_LAUNCHER="${COMPILER_LAUNCHER:-ccache}" \
    -DCMAKE_CXX_COMPILER_LAUNCHER="${COMPILER_LAUNCHER:-ccache}" \
    -DBUILD_SHARED_LIBS=ON \
    -DBUILD_TESTS=ON \
    -DBUILD_BENCHMARKS=OFF \
    -DCMAKE_INSTALL_PREFIX=$SYMENGINE_ROOT \
    ${CMAKE_ARGS} \
    -S "$SYMENGINE_SRC" \
    -B "$SYMENGINE_BUILD"

cmake --build $SYMENGINE_BUILD --clean-first --verbose

pushd $SYMENGINE_BUILD
if [[ $SYMENGINE_VARIANT == asan ]]; then
    ${TSAN_PREFIX} ctest --output-on-failure -E "test_bipartite|test_hopcroft_karp|test_case004|test_case006|test_case007|test_parser"
elif [[ $SYMENGINE_VARIANT == msan ]]; then
    ${TSAN_PREFIX} ctest --output-on-failure -R "test_cse"  # more tests pass, but ~50% segfault....
elif [[ $SYMENGINE_VARIANT == release ]]; then
    valgrind ${TSAN_PREFIX} ctest --output-on-failure
else
    # For debug, glibcxxdbg, tsan:
    ${TSAN_PREFIX} ctest --output-on-failure -E "test_parser"
fi
popd

cmake --install $SYMENGINE_BUILD
if [[ "${SYMENGINE_SKIP_CLEAN:-no}" != "yes" ]]; then
    cmake --build $SYMENGINE_BUILD --target clean
fi
ln -sf $SYMENGINE_BUILD/compile_commands.json $SYMENGINE_ROOT
