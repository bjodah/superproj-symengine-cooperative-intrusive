# nbsymengine_compat

Legacy `symengine.py` compatibility shim backed by `nbsymengine`
nanobind bindings.

## Overview

This package provides a drop-in replacement for the "legacy" `symengine.py` Python
API, implemented on top of the new `nbsymengine` C++ extension.  It is intended
for use by the converted legacy test suite and as a bridge for code that has not
yet migrated to the modern API.

## Layout

```
src/nbsymengine_compat/    # installable package
  __init__.py
  _expr.py                # sympify coercion helper
  symengine_py_compat.py  # full legacy API shim
  test_utilities.py       # raises() helper for tests
tools/                    # conversion tooling
  inventory_legacy_tests.py
  rewrite_legacy_tests.py
  regen_converted_tests.sh
  report_compat.py
tests/                    # test suite
  test_legacy_shim.py     # unit tests for the shim
  converted/              # generated converted legacy tests (git-ignored)
benchmarks/               # compat-owned benchmark adapter code
  compat_adapters.py      # legacy compat benchmark adapter
  README.md
external/
  symengine.py/           # nested submodule (source of legacy tests)
```

## Setup

```sh
git submodule update --init --recursive
python -m venv .venv && . .venv/bin/activate
# Install nbsymengine from the main symengine repo first
pip install -e .[test]
```

## Regenerating converted tests

```sh
bash tools/regen_converted_tests.sh
```

## Running tests

```sh
pytest tests/ -q
```

## Dependencies

- `nbsymengine` (the modern nanobind-based Python package, built from the main
  symengine repo with `-DBUILD_PYTHON_NANOBIND=ON -DSYMENGINE_RCP_BACKEND=cooperative_intrusive`)
- `sympy` (runtime dependency of the compatibility shim)
- `pytest`, `libcst`, `numpy`, `scipy` (test extras)
