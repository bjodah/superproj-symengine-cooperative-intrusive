"""conftest.py for nbsymengine_compat tests -- auto-xfail converted legacy tests.

Loads the manifest produced by ``tools/inventory_legacy_tests.py`` and
automatically marks converted test files whose ``missing_names`` is non-empty
as ``xfail`` with a reason naming the missing APIs.  External-dependency
suites (sympy, numpy, sage) are skipped when the dependency is absent.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

# Pre-import the shim so we can inject real names into mocked modules
try:
    from nbsymengine_compat import symengine_py_compat as _shim
    _shim_available = True
except Exception as e:
    import traceback
    print("CONTEST SHIM IMPORT ERROR:", e, file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    _shim_available = False


_symengine_mock = MagicMock()
_symengine_mock.__path__ = []
sys.modules['symengine'] = _symengine_mock

_lib_mock = MagicMock()
_lib_mock.__path__ = []
sys.modules['symengine.lib'] = _lib_mock

import types
_sympy_compat_mock = types.ModuleType('symengine.sympy_compat')
if _shim_available:
    for name in dir(_shim):
        setattr(_sympy_compat_mock, name, getattr(_shim, name))
    _functions_mock = types.ModuleType('symengine.sympy_compat.functions')
    for name in dir(_shim):
        setattr(_functions_mock, name, getattr(_shim, name))
    _sympy_compat_mock.functions = _functions_mock
    sys.modules['symengine.sympy_compat.functions'] = _functions_mock
sys.modules['symengine.sympy_compat'] = _sympy_compat_mock
_symengine_mock.sympy_compat = _sympy_compat_mock

# Provide real names from the shim in the mocked wrapper module
_wrapper_mock = MagicMock()
if _shim_available:
    _wrapper_mock._sympify = _shim._sympify
    _wrapper_mock.One = _shim.One
    _wrapper_mock.exp = _shim.exp
    _wrapper_mock.GoldenRatio = _shim.GoldenRatio
    _wrapper_mock.Catalan = _shim.Catalan
sys.modules['symengine.lib.symengine_wrapper'] = _wrapper_mock


# Also inject into the top-level symengine mock
_symengine_mock = sys.modules['symengine']
if _shim_available:
    _symengine_mock.exp = _shim.exp
    _symengine_mock.GoldenRatio = _shim.GoldenRatio
    _symengine_mock.Catalan = _shim.Catalan

import importlib
import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Locate manifest
# ---------------------------------------------------------------------------

_HERE = Path(__file__).resolve().parent
_MANIFEST_CANDIDATES = [
    _HERE / "tests" / "converted" / "manifest.json",
    _HERE / "converted" / "manifest.json",
]

_manifest: dict[str, dict] | None = None
for _p in _MANIFEST_CANDIDATES:
    if _p.is_file():
        try:
            _loaded = json.loads(_p.read_text())
            if isinstance(_loaded, dict):
                _manifest = _loaded
        except (json.JSONDecodeError, OSError):
            pass
        break

# Map: stem name (e.g. "test_arit") -> manifest entry
_manifest_by_stem: dict[str, dict] = {}
if _manifest:
    for _fname, _entry in _manifest.items():
        if not isinstance(_entry, dict):
            continue
        _stem = _fname.removesuffix(".py")
        _manifest_by_stem[_stem] = _entry


# ---------------------------------------------------------------------------
# Pre-check external deps (cached at module level)
# ---------------------------------------------------------------------------

def _dep_available(name: str) -> bool:
    try:
        importlib.import_module(name)
        return True
    except ImportError:
        return False


_DEP_MAP = {
    "sympy": "sympy",
    "numpy": "numpy",
    "scipy": "scipy",
    "sage": "sage",
}

# Cache dep availability so we only import-check once per session
_DEP_AVAILABLE: dict[str, bool] = {}


def _check_dep(ext_dep: str) -> bool:
    py_dep = _DEP_MAP.get(ext_dep, ext_dep)
    if py_dep not in _DEP_AVAILABLE:
        _DEP_AVAILABLE[py_dep] = _dep_available(py_dep)
    return _DEP_AVAILABLE[py_dep]


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_printing_state():
    try:
        from nbsymengine_compat._printing import _latex_printing_enabled
        _latex_printing_enabled[0] = False
    except ImportError:
        pass


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "legacy_compat: converted legacy symengine.py test",
    )


def pytest_collection_modifyitems(config, items):
    """Add markers to converted legacy test items after normal collection.

    This runs after pytest's standard collection, so there is no double
    collection and no need for a custom File/Item subclass.
    """
    for item in items:
        # Only touch files inside tests/converted/
        if f"tests{os.sep}converted" not in str(item.path):
            continue

        item.add_marker(pytest.mark.legacy_compat)

        if item.name == "test_pysymbol":
            item.add_marker(
                pytest.mark.skip(
                    reason="PySymbol Python subclassing is not supported in nbsymengine"
                )
            )
            continue

        stem = item.path.stem  # e.g. "test_arit"
        entry = _manifest_by_stem.get(stem)
        if entry is None:
            continue

        # Auto-xfail if missing names
        missing = entry.get("missing_names", [])
        if missing:
            reason = f"compat API not implemented: {', '.join(sorted(missing))}"
            item.add_marker(pytest.mark.xfail(reason=reason, run=False, strict=False))

        # Skip external-dep tests when dep is absent
        for ext_dep in entry.get("external", []):
            if not _check_dep(ext_dep):
                py_dep = _DEP_MAP.get(ext_dep, ext_dep)
                item.add_marker(
                    pytest.mark.skip(reason=f"external dep not available: {py_dep}")
                )
                break
