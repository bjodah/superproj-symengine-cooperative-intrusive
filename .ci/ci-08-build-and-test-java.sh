#!/bin/bash
# Build the Java JNI wrapper in its own ordinary-RCP SymEngine process.
set -euo pipefail

SCRIPT_DIR=$(dirname "$0")
source "${SCRIPT_DIR}/ci-common.sh"

BUILD_DIR=${1:-}
if [[ -z "${BUILD_DIR}" ]]; then
    >&2 echo "Usage: $0 <build-dir>"
    exit 1
fi

ci_ensure_python_toolchain
ci_use_java_toolchain

# INTEGER_CLASS=boostmp is fine here, unlike the perl lane: the JNI build has no Makefile.PL include-path constraint.
cmake \
    -G Ninja \
    -DCMAKE_BUILD_TYPE=Debug \
    -DCMAKE_C_COMPILER_LAUNCHER="${COMPILER_LAUNCHER:-ccache}" \
    -DCMAKE_CXX_COMPILER_LAUNCHER="${COMPILER_LAUNCHER:-ccache}" \
    -DBUILD_SHARED_LIBS=ON \
    -DBUILD_TESTS=OFF \
    -DBUILD_BENCHMARKS=OFF \
    -DWITH_LLVM=OFF \
    -DINTEGER_CLASS=boostmp \
    -DSYMENGINE_RCP_BACKEND=symengine \
    -DWITH_SYMENGINE_THREAD_SAFE=ON \
    -DBUILD_JAVA_JNI=ON \
    -S "${SUPERPROJECT_ROOT}" \
    -B "${BUILD_DIR}"
cmake --build "${BUILD_DIR}" --clean-first --target symengine_jni symengine_java
ctest --test-dir "${BUILD_DIR}" --output-on-failure -R '^java_symengine(_shared_cases)?$'
