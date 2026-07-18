#!/usr/bin/env bash
set -euo pipefail

# Verify that no generated litgen artifacts are tracked in git.
# The only allowed tracked file under generated/ is .gitignore.

offending=()

while IFS= read -r f; do
    offending+=("$f")
done < <(git ls-files \
    generated \
    nbsymengine/_core.pyi \
    | grep -v '^generated/\.gitignore$' \
    || true)

if (( ${#offending[@]} > 0 )); then
    echo "ERROR: Generated artifacts are tracked in git:" >&2
    for f in "${offending[@]}"; do
        echo "  $f" >&2
    done
    exit 1
fi

echo "Policy check passed: no generated artifacts tracked."
