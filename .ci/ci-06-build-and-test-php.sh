#!/bin/bash
# .ci/ci-06-build-and-test-php.sh - Build and test the symengine.php PHP extension.
#
# This script builds SymEngine with cooperative_intrusive backend, then builds
# the PHP extension via phpize/configure/make, and runs the PHPT test suite.
#
# Usage: ci-06-build-and-test-php.sh <build-dir> <install-prefix> <php-ext-build-dir>
#
# The PHP extension is built out-of-tree to avoid polluting the source directory.
# The SymEngine library must be built and installed first (typically by ci-01).

set -euo pipefail

SCRIPT_DIR=$(dirname "$0")
source "${SCRIPT_DIR}/ci-common.sh"

SYMENGINE_BUILD=$1
SYMENGINE_INSTALL=$2
PHP_EXT_SRC="${SUPERPROJECT_ROOT}/symengine.php"
PHP_EXT_BUILD=$3
SYMENGINE_VARIANT="${SYMENGINE_VARIANT:-debug}"
export SYMENGINE_VARIANT

if [[ -z "${SYMENGINE_BUILD:-}" || -z "${SYMENGINE_INSTALL:-}" || -z "${PHP_EXT_BUILD:-}" ]]; then
    >&2 echo "Usage: $0 <symengine-build-dir> <symengine-install-dir> <php-ext-build-dir>"
    exit 1
fi

# Ensure PHP development tools are available
if ! command -v phpize >/dev/null 2>&1; then
    >&2 echo "Error: phpize not found. Install php-dev/php-devel package."
    exit 1
fi

if ! command -v php-config >/dev/null 2>&1; then
    >&2 echo "Error: php-config not found."
    exit 1
fi

PHP_CONFIG=$(command -v php-config)
PHP_VERSION=$("${PHP_CONFIG}" --version)
PHP_EXTENSION_DIR=$("${PHP_CONFIG}" --extension-dir)

echo "=== PHP Extension Build ==="
echo "PHP version: ${PHP_VERSION}"
echo "PHP config: ${PHP_CONFIG}"
echo "Extension dir: ${PHP_EXTENSION_DIR}"
echo "SymEngine build: ${SYMENGINE_BUILD}"
echo "SymEngine install: ${SYMENGINE_INSTALL}"
echo "SymEngine variant: ${SYMENGINE_VARIANT}"
echo "PHP ext source: ${PHP_EXT_SRC}"
echo "PHP ext build: ${PHP_EXT_BUILD}"

# Verify SymEngine was built with cooperative_intrusive
if [[ ! -f "${SYMENGINE_INSTALL}/include/symengine/symengine_rcp.h" ]]; then
    >&2 echo "Error: SymEngine headers not found at ${SYMENGINE_INSTALL}/include/symengine/"
    exit 1
fi

# Check for cooperative_intrusive backend
if ! grep -q "WITH_SYMENGINE_COOPERATIVE_INTRUSIVE_RCP" "${SYMENGINE_INSTALL}/include/symengine/symengine_rcp.h" 2>/dev/null; then
    >&2 echo "Error: SymEngine not built with cooperative_intrusive backend"
    exit 1
fi

# Create build directory
mkdir -p "${PHP_EXT_BUILD}"
cd "${PHP_EXT_BUILD}"

# Copy source files (out-of-tree build to keep source clean)
rsync -a --exclude='.git' --exclude='build' --exclude='modules' --exclude='.libs' \
    --exclude='autom4te.cache' --exclude='configure' \
    --exclude='Makefile*' --exclude='*.log' \
    --exclude='*.la' --exclude='*.lo' --exclude='*.o' \
    "${PHP_EXT_SRC}/" .

# Run phpize
# The extension is copied out of tree before configure. Point its shared-codegen
# lookup back to the superproject rather than relying on a parent directory.
export BINDING_CODEGEN_ROOT="${SUPERPROJECT_ROOT}"
phpize

# Configure against the freshly installed SymEngine tree.
export SYMENGINE_PREFIX="${SYMENGINE_INSTALL}"
./configure --with-php-config="${PHP_CONFIG}"

# Build
make -j"$(nproc)" clean
make -j"$(nproc)"

# Run tests
export TEST_PHP_EXECUTABLE=$(command -v php)
export EXTENSION_DIR="${PHP_EXT_BUILD}/modules"
export LD_LIBRARY_PATH="${SYMENGINE_INSTALL}/lib64:${SYMENGINE_INSTALL}/lib:${LD_LIBRARY_PATH:-}"
# PHP's debug allocator reports process-shutdown allocations after the PHPT
# output. These bindings intentionally retain wrapper bookkeeping until module
# shutdown, so suppress those allocator diagnostics while retaining the
# functional PHPT assertions.
export ZEND_ALLOC_PRINT_LEAKS=0
php run-tests.php -d extension=modules/symengine.so tests/*.phpt

echo "=== PHP extension build and test completed successfully ==="
