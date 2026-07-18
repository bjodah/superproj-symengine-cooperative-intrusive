"""nbsymengine_compat._pickling -- __reduce_ex__ / _unpickle_basic support.

Pickling is defined directly on the ``Basic`` wrapper class (see
``_wrappers.py``) and ``DenseMatrixWrapper`` (see ``_matrices.py``).
No monkey-patching of ``_core`` types is performed.

This module provides the unpickling helper functions that are referenced
by those ``__reduce__`` methods.
"""
from __future__ import annotations

import sys as _sys

from nbsymengine import _core
from ._helpers import _sympify, HAS_SYMPY, _require_sympy
from ._constants import pi, E, EulerGamma, I, oo, zoo, nan, true, false, One


def _safe_sympify(s):
    """Parse a string to a SymPy expression without executing arbitrary code."""
    if not HAS_SYMPY:
        _require_sympy("_safe_sympify()")
    import sympy
    from sympy.parsing.sympy_parser import (
        parse_expr, standard_transformations, convert_xor,
    )
    safe_globals = {}
    for name in dir(sympy):
        if not name.startswith('_'):
            safe_globals[name] = getattr(sympy, name)
    safe_globals['S'] = sympy.S
    return parse_expr(s, global_dict=safe_globals,
                      transformations=(standard_transformations + (convert_xor,)))


def _unpickle_basic(s):
    """Unpickle a Basic expression from its string representation."""
    if not HAS_SYMPY:
        _require_sympy("unpickling Basic from string")
    from ._sympy_bridge import from_sympy
    from ._wrappers import wrap
    return wrap(from_sympy(_safe_sympify(s)))


_CONSTANT_MAP = None


def _get_constant_map():
    global _CONSTANT_MAP
    if _CONSTANT_MAP is None:
        mod = _sys.modules[__name__]
        _CONSTANT_MAP = {}
        for name in ("pi", "E", "EulerGamma", "I", "oo", "zoo", "nan",
                      "true", "false", "One"):
            obj = getattr(mod, name, None)
            if obj is not None:
                raw = getattr(obj, '_raw', obj)
                if isinstance(raw, _core.Basic):
                    _CONSTANT_MAP[str(raw)] = obj
    return _CONSTANT_MAP


def _unpickle_constant(name):
    """Unpickle a singleton constant by its str() representation."""
    cmap = _get_constant_map()
    obj = cmap.get(name)
    if obj is not None:
        return obj
    if not HAS_SYMPY:
        _require_sympy(f"unpickling constant '{name}'")
    from ._sympy_bridge import from_sympy
    from ._wrappers import wrap
    return wrap(from_sympy(_safe_sympify(name)))


def _unpickle_dummy(name, index):
    """Unpickle a Dummy with its original index."""
    from ._wrappers import wrap
    return wrap(_core.Dummy(name, index))


def _unpickle_via_sympy(sym_expr):
    """Unpickle via a SymPy expression object."""
    if not HAS_SYMPY:
        _require_sympy("unpickling via SymPy expression")
    from ._sympy_bridge import from_sympy
    from ._wrappers import wrap
    return wrap(from_sympy(sym_expr))


def _unpickle_dense_matrix(nrows, ncols, flat_vals):
    """Unpickle a DenseMatrix from its dimensions and flat value list."""
    from ._wrappers import wrap
    return wrap(_core.DenseMatrix(nrows, ncols, flat_vals))


def _unpickle_immutable_matrix(nrows, ncols, flat_vals):
    """Unpickle an ImmutableMatrix from its dimensions and flat value list."""
    from ._matrices import ImmutableMatrix
    return ImmutableMatrix(nrows, ncols, flat_vals)
