"""nbsymengine_compat.symengine_py_compat -- Legacy ``import symengine`` shim.

Re-exports the full set of names that the legacy ``symengine`` Python package
provided, backed by the new nanobind ``_core`` extension.

This module is a thin façade that re-exports from focused submodules:
  _helpers      -- small utility functions and classes
  _constants    -- singletons, constants, and feature flags
  _wrappers     -- wrapper classes and free function re-exports
  _sympy_bridge -- to_sympy / from_sympy / sympify glue
  _matrices     -- DenseMatrix / ImmutableMatrix support
  _printing     -- str/repr/latex printers
  _lambdify     -- the compat Lambdify class
  _pickling     -- __reduce_ex__ / _unpickle_basic support
  _monkeypatch  -- no-op placeholder (delegation wrappers eliminate patching)
"""
from __future__ import annotations

# Re-export all public names from submodules.
# Import order matters: _wrappers must come after _constants/_sympy_bridge
# so that the wrapper Basic class can handle isinstance checks on raw objects.

from ._helpers import *  # noqa: F401,F403
from ._constants import *  # noqa: F401,F403
from ._sympy_bridge import *  # noqa: F401,F403
from ._wrappers import *  # noqa: F401,F403
from ._matrices import *  # noqa: F401,F403
from ._printing import *  # noqa: F401,F403
from ._lambdify import *  # noqa: F401,F403
from ._pickling import *  # noqa: F401,F403
from ._monkeypatch import *  # noqa: F401,F403

# Private names used by conftest.py and test infrastructure
from ._helpers import _sympify, HAS_SYMPY  # noqa: F401
from ._pickling import _safe_sympify  # noqa: F401

# Preserve any _core names NOT already covered by wrapper/compat modules.
# The wrapper classes intentionally shadow raw _core types, so we must
# not overwrite them.  Only import names that are truly new.
from nbsymengine import _core as _c
_existing_names = set(globals().keys()) | {'_c', '_existing_names'}
for name in dir(_c):
    if name not in _existing_names and not name.startswith('_'):
        obj = getattr(_c, name)
        if not isinstance(obj, type) or not issubclass(obj, _c.Basic):
            globals()[name] = obj
del _c, _existing_names

# Infty and NaN classes are not part of the legacy public API
if 'Infty' in globals():
    del Infty
if 'NaN' in globals():
    del NaN
