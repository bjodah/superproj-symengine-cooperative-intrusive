#!/bin/bash
# Build the Java JNI wrapper against the shared cooperative-intrusive
# SymEngine build (the same superproject build directory the nbsymengine lane
# produced) instead of compiling a second core with the ordinary RCP backend.
# This is safe because the cooperative-intrusive counter is unconditionally
# atomic (CAS) and the Java wrapper never registers incref/decref hooks, so
# every object stays in C++-owned integer-count mode; WITH_SYMENGINE_THREAD_SAFE
# is only needed for the ordinary backend's plain refcount.
set -euo pipefail

SCRIPT_DIR=$(dirname "$0")
source "${SCRIPT_DIR}/ci-common.sh"

BUILD_DIR=${1:-}
if [[ -z "${BUILD_DIR}" ]]; then
    >&2 echo "Usage: $0 <build-dir>"
    >&2 echo "Pass an already-configured cooperative superproject build dir"
    >&2 echo "(e.g. the nbsymengine lane's) to reuse its libsymengine, or a"
    >&2 echo "fresh directory to configure a standalone cooperative build."
    exit 1
fi

ci_ensure_python_toolchain
ci_use_java_toolchain

if [[ -f "${BUILD_DIR}/CMakeCache.txt" ]]; then
    # Reuse an existing cooperative superproject build: only switch the Java
    # targets on. All other cached settings (backend, flags, launcher) stay.
    cmake -DBUILD_JAVA_JNI=ON -S "${SUPERPROJECT_ROOT}" -B "${BUILD_DIR}"
else
    # Standalone invocation: configure a fresh cooperative build.
    # INTEGER_CLASS=boostmp is fine here, unlike the perl lane: the JNI build
    # has no Makefile.PL include-path constraint.
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
        -DSYMENGINE_RCP_BACKEND=cooperative_intrusive \
        -DBUILD_JAVA_JNI=ON \
        -S "${SUPERPROJECT_ROOT}" \
        -B "${BUILD_DIR}"
fi
# No --clean-first: the point of reusing the shared build dir is to keep its
# already-built libsymengine.
cmake --build "${BUILD_DIR}" --target symengine_jni symengine_java
ctest --test-dir "${BUILD_DIR}" --output-on-failure -R '^java_symengine(_shared_cases)?$'
