"""Legacy compatibility backend adapter for benchmarks.

Exposed under nbsymengine_compat benchmarks and run during ci-03.
"""
from __future__ import annotations

from typing import Any, Callable, Optional
from nbsymengine_benchmarks.adapters import BackendAdapter


def _coerce_args(args):
    """Convert numpy arrays to lists for legacy shim compatibility."""
    import numpy as np
    if isinstance(args, np.ndarray):
        return list(args)
    return args


def _to_nbsymengine_args(args):
    """Convert sympy symbols to nbsymengine symbols."""
    from nbsymengine_compat import symengine_py_compat as se
    return [se.from_sympy(a) if hasattr(a, 'name') else a for a in args]


def _to_nbsymengine_exprs(exprs):
    """Convert sympy expressions/matrices to nbsymengine equivalents."""
    from nbsymengine_compat import symengine_py_compat as se
    from sympy import Matrix
    result = []
    for expr in exprs:
        if isinstance(expr, Matrix):
            sx_rows, sx_cols = expr.shape
            flat = [se.from_sympy(expr[i, j]) for i in range(sx_rows) for j in range(sx_cols)]
            result.append(se.DenseMatrix(sx_rows, sx_cols, flat))
        else:
            result.append(se.from_sympy(expr))
    return result


class NBSymEngineLegacyAdapter(BackendAdapter):
    """nbsymengine_compat legacy compatibility adapter.

    Uses the single-array calling convention ``lmb(inp)`` for every case,
    matching legacy ``symengine.py``: the compat ``Lambdify`` returns one
    shaped array for a single expression and a list of shaped arrays for
    heterogeneous output.
    """
    @property
    def name(self) -> str:
        return "nbsymengine-legacy"

    def is_available(self) -> bool:
        try:
            from nbsymengine_compat import symengine_py_compat  # noqa: F401
            return True
        except ImportError:
            return False

    def skip_reason(self) -> Optional[str]:
        if not self.is_available():
            return "nbsymengine_compat submodule not installed"
        return None

    def build_lambdify(self, args, exprs):
        from nbsymengine_compat import symengine_py_compat as se
        from sympy import Matrix

        args = _coerce_args(args)
        sx_args = _to_nbsymengine_args(args)
        is_heterogeneous = (
            isinstance(exprs, (tuple, list))
            and len(exprs) == 2
            and isinstance(exprs[0], Matrix)
            and isinstance(exprs[1], Matrix)
        )

        sx_exprs = _to_nbsymengine_exprs(exprs)
        if is_heterogeneous:
            # One Lambdify expression per output -> a list of shaped arrays.
            lmb = se.Lambdify(sx_args, *sx_exprs)
        else:
            # A single expression (the whole list) -> one 1-D array, which is
            # what the legacy-symengine adapter does as well.
            lmb = se.Lambdify(sx_args, sx_exprs)

        def call(inp):
            return lmb(inp)
        return call
