#!/bin/bash
# Build and test the Swift package against a cooperative SymEngine build.
set -euo pipefail

SCRIPT_DIR=$(dirname "$0")
source "${SCRIPT_DIR}/ci-common.sh"

SYMENGINE_BUILD=${1:-}
SWIFT_BUILD=${2:-}
if [[ -z "${SYMENGINE_BUILD}" || -z "${SWIFT_BUILD}" ]]; then
    >&2 echo "Usage: $0 <symengine-build-dir> <swift-build-dir>"
    exit 1
fi

if ! command -v swift >/dev/null 2>&1; then
    >&2 echo "Error: swift is required for the Swift binding CI lane."
    exit 1
fi

cmake \
    -G Ninja \
    -DCMAKE_BUILD_TYPE=Debug \
    -DCMAKE_C_COMPILER_LAUNCHER="${COMPILER_LAUNCHER:-ccache}" \
    -DCMAKE_CXX_COMPILER_LAUNCHER="${COMPILER_LAUNCHER:-ccache}" \
    -DBUILD_SHARED_LIBS=ON \
    -DBUILD_TESTS=OFF \
    -DBUILD_BENCHMARKS=OFF \
    -DWITH_LLVM=OFF \
    -DINTEGER_CLASS=gmp \
    -DWITH_SYMENGINE_THREAD_SAFE=ON \
    -DSYMENGINE_RCP_BACKEND=cooperative_intrusive \
    -S "${SUPERPROJECT_ROOT}/symengine" \
    -B "${SYMENGINE_BUILD}"
cmake --build "${SYMENGINE_BUILD}" --clean-first --target symengine --verbose

SYMENGINE_SOURCE_DIR="${SUPERPROJECT_ROOT}/symengine" \
SYMENGINE_BUILD_DIR="${SYMENGINE_BUILD}" \
SYMENGINE_LIBRARY_DIR="${SYMENGINE_BUILD}/symengine" \
BINDING_CODEGEN_ROOT="${SUPERPROJECT_ROOT}" \
"${SUPERPROJECT_ROOT}/symengine.swift/tools/generate-bindings.sh" "${SWIFT_BUILD}/binding-generated"

SYMENGINE_SOURCE_DIR="${SUPERPROJECT_ROOT}/symengine" \
SYMENGINE_BUILD_DIR="${SYMENGINE_BUILD}" \
SYMENGINE_LIBRARY_DIR="${SYMENGINE_BUILD}/symengine" \
SYMENGINE_BINDING_GENERATED_DIR="${SWIFT_BUILD}/binding-generated" \
BINDING_CODEGEN_ROOT="${SUPERPROJECT_ROOT}" \
swift test --build-path "${SWIFT_BUILD}" --package-path "${SUPERPROJECT_ROOT}/symengine.swift"
