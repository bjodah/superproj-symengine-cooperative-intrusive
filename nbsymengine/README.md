# nbsymengine

## Nanobind source of truth

Normal source builds use the vendored nanobind submodule at
`external/nanobind` unless `nanobind_DIR` is explicitly supplied. The
cooperative-intrusive CI lane deliberately supplies `nanobind_DIR` from the
active Python environment (`python -m nanobind --cmake_dir`), so the
pip-installed nanobind copy wins there. CI enforces a minimum version of
2.13.0, which includes the intrusive-counter race fixes mirrored by
SymEngine.

When changing either copy, inspect changes under
`include/nanobind/intrusive/` and `src/nb_type.cpp` and compare any counter
changes with `symengine/symengine_rcp_cooperative.cpp` before updating the
minimum version or submodule pin.

## Litgen source

In-tree binding generation uses `$LITGEN_ROOT/src`; CI sets `LITGEN_ROOT` to
`/opt-6/litgen-6085aaa`. Override it with
`-DSYMENGINE_LITGEN_DIR=<litgen-checkout>/src` (or
`SYMENGINE_LITGEN_DIR` in the CI/sdist scripts). Litgen is not a submodule.
