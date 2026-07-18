#!/bin/bash
set -euo pipefail

SYMENGINE_BUILD=${1:-}
if [[ -z "${SYMENGINE_BUILD}" ]]; then
    >&2 echo "Usage: $0 <symengine-build-dir>"
    exit 1
fi

if [[ ! -d "${SYMENGINE_BUILD}" ]]; then
    >&2 echo "Build directory does not exist: ${SYMENGINE_BUILD}"
    exit 1
fi

TMP_STDOUT=$(mktemp)
TMP_STDERR=$(mktemp)
cleanup() {
    rm -f "${TMP_STDOUT}" "${TMP_STDERR}"
}
trap cleanup EXIT

PYTHONPATH="${SYMENGINE_BUILD}:${PYTHONPATH:-}" python -c \
    'import symengine_manual_ext as m; m._leak_symbol_for_test()' \
    >"${TMP_STDOUT}" 2>"${TMP_STDERR}"

if ! grep -q 'nanobind: leaked' "${TMP_STDERR}"; then
    >&2 echo "Expected the intentional leak probe to trigger nanobind leak warnings."
    >&2 echo "--- stdout ---"
    cat "${TMP_STDOUT}" >&2
    >&2 echo "--- stderr ---"
    cat "${TMP_STDERR}" >&2
    exit 1
fi

if ! grep -q 'symengine_manual_ext.Symbol' "${TMP_STDERR}"; then
    >&2 echo "Expected the intentional leak probe to report a leaked Symbol instance."
    >&2 echo "--- stderr ---"
    cat "${TMP_STDERR}" >&2
    exit 1
fi
echo "ci-04-leak-test OK (nanobind reported on our intentional leak)"
