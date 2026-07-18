#!/bin/bash
# .ci/ci-05-build-and-test-perl.sh - Build and test the symengine.pl Perl XS extension.
#
# The Perl XS extension is built through the super-project CMake
# (-DBUILD_PERL_XS=ON): it compiles the symengine C++ library and the XS
# wrapper, then registers the `perl_symengine` ctest entry (which runs the
# t/*.t suite via `make test`).
#
# Design notes:
#   * Uses the pinned debug Perl toolchain configured by CI. Override with
#     SYMENGINE_PERL_EXECUTABLE if needed.
#   * Uses INTEGER_CLASS=gmp (symengine's default). symengine.pl/Makefile.PL only
#     adds the symengine source/build and cereal include dirs to the XS compile,
#     so building the extension against a boostmp symengine would fail to find
#     the Boost headers. gmp keeps the lane self-contained (gmpxx.h lives in the
#     system include path and Makefile.PL links -lgmp by default).
#   * Does not depend on the Python/nanobind toolchain: the cooperative_intrusive
#     backend no longer needs nanobind headers, and the Perl XS build needs only
#     perl + make + a C++ compiler.
set -euo pipefail

SCRIPT_DIR=$(dirname "$0")
source "${SCRIPT_DIR}/ci-common.sh"

SYMENGINE_BUILD=$1
if [[ -z "${SYMENGINE_BUILD:-}" ]]; then
    >&2 echo "Usage: $0 <build-dir>"
    exit 1
fi

# Pick the configured Perl interpreter, falling back to PATH for local use.
PERL_EXECUTABLE="${SYMENGINE_PERL_EXECUTABLE:-${CI_PERL_EXECUTABLE:-$(command -v perl || true)}}"
if [[ -z "${PERL_EXECUTABLE}" ]]; then
    >&2 echo "Error: no perl interpreter found on PATH."
    exit 1
fi
echo "Using Perl: ${PERL_EXECUTABLE} ($(${PERL_EXECUTABLE} -e 'print $^V'))"

# Configure the super-project for a self-contained Perl XS build.
cmake \
    -G Ninja \
    -DCMAKE_BUILD_TYPE=Debug \
    -DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
    -DCMAKE_C_COMPILER_LAUNCHER=ccache \
    -DCMAKE_CXX_COMPILER_LAUNCHER=ccache \
    -DBUILD_SHARED_LIBS=ON \
    -DBUILD_TESTS=OFF \
    -DBUILD_BENCHMARKS=OFF \
    -DWITH_LLVM=OFF \
    -DINTEGER_CLASS=gmp \
    -DSYMENGINE_RCP_BACKEND=cooperative_intrusive \
    -DBUILD_PERL_XS=ON \
    -DPERL_EXECUTABLE="${PERL_EXECUTABLE}" \
    -S "$SUPERPROJECT_ROOT" \
    -B "$SYMENGINE_BUILD"

# Build the symengine C++ library + perl_xs target
cmake --build "$SYMENGINE_BUILD" --clean-first --verbose

# Run the Perl extension test suite
pushd "$SYMENGINE_BUILD"
ctest --output-on-failure -R '^perl_symengine$'
popd
