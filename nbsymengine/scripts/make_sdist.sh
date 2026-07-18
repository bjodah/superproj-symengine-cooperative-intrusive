#!/bin/bash
# Build a source-distribution tarball that ships pre-baked generated bindings.
#
# Requirements at sdist-CREATION time (only):
#   - litgen installed at $LITGEN_ROOT/src (default:
#     /opt-6/litgen-6085aaa/src), or set SYMENGINE_LITGEN_DIR directly
#   - Python 3.13+
#
# Requirements at sdist-INSTALL time (pip install <tarball>):
#   - No litgen, no PYTHONPATH, no PyPI nanobind — the sdist is fully self-contained.
#
# The sdist contains:
#   - SymEngine C++ source tree (symengine_src/)
#   - Pre-generated binding sources (generated/symengine_pydef.cpp, symengine.pyi)
#   - C++ extension sources (src/, support/)
#   - Python package (nbsymengine/)
#   - Modern pytest tests (tests/)
#   - Build configuration (CMakeLists.txt, pyproject.toml)
#
# Usage (run from the superproject root or nbsymengine/):
#   bash nbsymengine/scripts/make_sdist.sh [OUTPUT_DIR]
#
# OUTPUT_DIR defaults to /tmp/symengine-sdist.  The tarball is written to
# OUTPUT_DIR.tar.gz.

set -euo pipefail

SRC=$(realpath "$(dirname "$0")/..")
SUPERPROJECT_ROOT=$(realpath "$SRC/..")
SYMENGINE_SRC=${SUPERPROJECT_ROOT}/symengine
LITGEN_ROOT=${LITGEN_ROOT:-/opt-6/litgen-6085aaa}
LITGEN_SRC=${SYMENGINE_LITGEN_DIR:-${LITGEN_ROOT}/src}
OUT=${1:-/tmp/symengine-sdist}

rm -rf "$OUT"
mkdir -p "$OUT"

if ! git -C "$SRC" diff --quiet HEAD 2>/dev/null; then
    echo "WARNING: working tree has uncommitted changes; sdist will be based on HEAD only" >&2
fi

COMMIT=$(git -C "$SRC" rev-parse HEAD 2>/dev/null || echo "unknown")

echo "==> Exporting clean working tree …"
git -C "$SRC" archive --format=tar HEAD | tar -x -C "$OUT"

echo "==> Generating bindings from original checkout into staged tree …"
GENERATE_PY="$SRC/generator/generate.py"
GENERATE_YAML="$SRC/generator/generate.yaml"
if [ ! -f "$GENERATE_PY" ]; then
    echo "ERROR: generator script not found at $GENERATE_PY" >&2
    exit 1
fi
if [ ! -d "$LITGEN_SRC" ]; then
    echo "ERROR: litgen not found at $LITGEN_SRC." >&2
    echo "  litgen is required when *creating* an sdist (to generate bindings)," >&2
    echo "  but is NOT needed when *installing* from the sdist tarball." >&2
    exit 1
fi
GENERATED_OUT="$OUT/generated"
mkdir -p "$GENERATED_OUT"
(cd "$SYMENGINE_SRC" && PYTHONPATH="$LITGEN_SRC" python3 "$GENERATE_PY" \
    "$GENERATE_YAML" \
    --output-dir "$GENERATED_OUT")
(cd "$SUPERPROJECT_ROOT" && python3 -m tools.binding_codegen generate \
    --language python --output "$GENERATED_OUT")


echo "==> Verifying generated files …"
GENERATED_CPP="$OUT/generated/symengine_pydef.cpp"
GENERATED_PYI="$OUT/generated/symengine.pyi"

for f in "$GENERATED_CPP" "$GENERATED_PYI"; do
    if [ ! -f "$f" ]; then
        echo "ERROR: expected generated file not found: $f" >&2
        exit 1
    fi
done
echo "    symengine_pydef.cpp: $(wc -c < "$GENERATED_CPP") bytes"
echo "    symengine.pyi:       $(wc -c < "$GENERATED_PYI") bytes"

echo "==> Assembling sdist root from submodule layout …"
SDIST="$OUT/sdist_root"
mkdir -p "$SDIST"

# Copy package sources & build config files
cp "$OUT/pyproject.toml" "$SDIST/"
cp "$OUT/CMakeLists.txt" "$SDIST/"
cp -r "$OUT/nbsymengine" "$SDIST/"
mkdir -p "$SDIST/binding-spec"
cp "$SUPERPROJECT_ROOT/binding-spec/api.yaml" "$SDIST/binding-spec/"
cp "$SUPERPROJECT_ROOT/binding-spec/schema.json" "$SDIST/binding-spec/"
mkdir -p "$SDIST/external"
cp -r "$SRC/external/nanobind" "$SDIST/external/"
find "$SDIST/external/nanobind" -name .git -type f -delete

# C++ extension sources
mkdir -p "$SDIST/src" "$SDIST/support"
cp "$OUT/src/"*.cpp "$SDIST/src/"
# Also copy any headers that may exist in src/ (defensive: avoids silent breakage)
if ls "$OUT/src/"*.h &>/dev/null; then
    cp "$OUT/src/"*.h "$SDIST/src/"
fi
cp "$OUT/support/"*.h "$SDIST/support/"
# Also copy any .cpp files that may exist in support/ (defensive)
if ls "$OUT/support/"*.cpp &>/dev/null; then
    cp "$OUT/support/"*.cpp "$SDIST/support/"
fi

# Pre-generated binding sources (litgen output)
mkdir -p "$SDIST/generated"
cp "$GENERATED_CPP" "$SDIST/generated/"
cp "$GENERATED_PYI" "$SDIST/generated/"
cp "$GENERATED_OUT/symengine_simple_funcs.inc" "$SDIST/generated/"
cp "$GENERATED_OUT/symengine_simple_funcs.pyi" "$SDIST/generated/"

# SymEngine C++ source tree (for building from source during pip install)
echo "==> Copying SymEngine source tree into sdist …"
mkdir -p "$SDIST/symengine_src"
for d in symengine cmake; do
    if [ -d "$SYMENGINE_SRC/$d" ]; then
        cp -r "$SYMENGINE_SRC/$d" "$SDIST/symengine_src/$d"
    fi
done
cp "$SYMENGINE_SRC/CMakeLists.txt" "$SDIST/symengine_src/"

echo "==> Including modern tests in sdist …"
mkdir -p "$SDIST/tests"
cp "$SRC/tests/"test_*.py "$SDIST/tests/" 2>/dev/null || true
if ! ls "$SDIST/tests/"test_*.py &>/dev/null; then
    echo "WARNING: no test_*.py files found to include in sdist" >&2
fi
if [ -f "$SRC/tests/conftest.py" ]; then
    cp "$SRC/tests/conftest.py" "$SDIST/tests/"
fi

echo "==> Writing generation manifest …"
LITGEN_ROOT=$(realpath "$LITGEN_SRC/..")
LITGEN_DESCRIBE=$(git -C "$LITGEN_ROOT" describe --tags 2>/dev/null || echo "unknown")
LITGEN_SHA=$(git -C "$LITGEN_ROOT" rev-parse HEAD 2>/dev/null || echo "unknown")
BINDING_SPEC_SHA=$(sha256sum "$SUPERPROJECT_ROOT/binding-spec/api.yaml" | awk '{print $1}')
cat > "$SDIST/generated/GENERATION_MANIFEST.txt" <<EOF
# Generated by make_sdist.sh — do not edit.
# litgen is required only at sdist-creation time, NOT at install time.
commit=${COMMIT}
litgen_describe=${LITGEN_DESCRIBE}
litgen_sha=${LITGEN_SHA}
generate_py=generator/generate.py
generate_yaml=generator/generate.yaml
generated_cpp=symengine_pydef.cpp
generated_pyi=symengine.pyi
generated_simple_inc=symengine_simple_funcs.inc
generated_simple_pyi=symengine_simple_funcs.pyi
binding_spec_api=binding-spec/api.yaml
binding_spec_schema=binding-spec/schema.json
binding_spec_api_sha256=${BINDING_SPEC_SHA}
EOF

echo "==> Verifying required support headers present in sdist …"
SUPPORT_HEADERS=(
    "$SDIST/support/nanobind_symengine.h"
    "$SDIST/support/nanobind_module_common.h"
)
for hdr in "${SUPPORT_HEADERS[@]}"; do
    if [ ! -f "$hdr" ]; then
        echo "ERROR: required support header missing from staged sdist: $hdr" >&2
        exit 1
    fi
done
echo "    All required support headers present."

echo "==> Verifying no generated files leaked outside generated/ …"
# Check that the staged sdist does not contain generated artifacts in
# unexpected locations (only generated/ should have them).
LEAKED=$(find "$SDIST/src" "$SDIST/support" -name 'symengine_pydef.cpp' -o -name 'symengine.pyi' 2>/dev/null || true)
if [ -n "$LEAKED" ]; then
    echo "ERROR: generated files found outside generated/ directory:" >&2
    echo "$LEAKED" >&2
    exit 1
fi

echo "==> Creating tarball …"
tar -C "$(dirname "$SDIST")" -czf "$OUT.tar.gz" "$(basename "$SDIST")"
echo "wrote $OUT.tar.gz"
