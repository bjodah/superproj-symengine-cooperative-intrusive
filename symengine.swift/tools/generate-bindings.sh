#!/bin/sh
set -eu

# Generate only build-tree artefacts. A standalone checkout must set
# BINDING_CODEGEN_ROOT; in the super-project the wrapper's parent is enough.
ROOT=${BINDING_CODEGEN_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)}
OUTPUT=${1:?usage: generate-bindings.sh <build-generated-dir>}
PYTHON=${BINDING_CODEGEN_PYTHON:-python3}

test -f "$ROOT/binding-spec/api.yaml" || {
    echo "binding-spec/api.yaml not found; set BINDING_CODEGEN_ROOT" >&2
    exit 1
}
PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" \
    "$PYTHON" -m tools.binding_codegen generate --language swift --artifact cpp --output "$OUTPUT"
