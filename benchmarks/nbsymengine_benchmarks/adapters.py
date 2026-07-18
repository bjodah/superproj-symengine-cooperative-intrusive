"""Backend adapters for Lambdify benchmarks.

Calling conventions per adapter
================================

Each adapter's ``build_lambdify`` returns a callable with signature
``call(inp) -> result`` where *inp* is a numpy array.  The internal
calling convention to the underlying lambdify object differs:

+-----------------------+---------------------+-----------------------------+
| Adapter               | Non-heterogeneous   | Heterogeneous               |
+=======================+=====================+=============================+
| SymPy                 | ``lmb(*inp)``       | ``lmb(*inp)``               |
+-----------------------+---------------------+-----------------------------+
| NBSymEngine           | ``lmb(inp)``        | ``lmb(*inp)``               |
+-----------------------+---------------------+-----------------------------+
| LegacySymEngine       | ``lmb(inp)``        | ``lmb(inp)``                |
+-----------------------+---------------------+-----------------------------+

Notes:
- SymPy's ``lambdify`` always unpacks positional arguments.
- NBSymEngine's ``Lambdify`` accepts a single array for non-heterogeneous
  cases but requires unpacked args for heterogeneous output.
- LegacySymEngine's ``Lambdify`` always accepts a single array/callable.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, List, Optional


def _coerce_args(args):
    """Convert numpy arrays to lists for legacy shim compatibility."""
    import numpy as np
    if isinstance(args, np.ndarray):
        return list(args)
    return args


def _to_numpy(obj):
    """Recursively convert nbsymengine.DenseMatrix to numpy array."""
    import numpy as np
    import nbsymengine as sx
    if isinstance(obj, sx.DenseMatrix):
        rows, cols = obj.nrows(), obj.ncols()
        flat = [float(str(obj.get(i, j))) for i in range(rows) for j in range(cols)]
        return np.array(flat, dtype=float).reshape(rows, cols)
    if isinstance(obj, (list, tuple)):
        return type(obj)(_to_numpy(x) for x in obj)
    return obj


class BackendAdapter(ABC):
    """Base class for backend adapters."""
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def build_lambdify(self, args: Any, exprs: Any) -> Callable[[Any], Any]:
        """Build a lambdify callable that takes a numpy array and returns result."""
        ...

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def skip_reason(self) -> Optional[str]: ...


class SymPyAdapter(BackendAdapter):
    """Baseline using sympy.lambdify."""
    @property
    def name(self) -> str:
        return "sympy"

    def is_available(self) -> bool:
        try:
            import sympy  # noqa: F401
            return True
        except ImportError:
            return False

    def skip_reason(self) -> Optional[str]:
        if not self.is_available():
            return "sympy not installed"
        return None

    def build_lambdify(self, args, exprs):
        import sympy
        import numpy as np

        # Detect heterogeneous output (tuple of (vector, matrix))
        is_heterogeneous = (
            isinstance(exprs, (tuple, list))
            and len(exprs) == 2
            and isinstance(exprs[0], sympy.Matrix)
            and isinstance(exprs[1], sympy.Matrix)
        )

        if is_heterogeneous:
            lmb = sympy.lambdify(args, exprs, modules=['math', 'sympy'])
            def call(inp):
                v, m = lmb(*inp)
                return (np.array(v, dtype=float), np.array(m, dtype=float))
            return call
        else:
            lmb = sympy.lambdify(args, exprs, modules='math')
            def call(inp):
                return np.array(lmb(*inp), dtype=float)
            return call


class NBSymEngineAdapter(BackendAdapter):
    """Direct nbsymengine Lambdify API adapter.

    Uses ``nbsymengine.Lambdify`` with the default ``sympy`` backend for
    numeric evaluation.  Falls back to skipped status if the
    nbsymengine package is not installed or does not expose ``Lambdify``.
    """

    @property
    def name(self) -> str:
        return "nbsymengine"

    def is_available(self) -> bool:
        try:
            import nbsymengine
            return hasattr(nbsymengine, 'Lambdify')
        except ImportError:
            return False

    def skip_reason(self) -> Optional[str]:
        if not self.is_available():
            return "nbsymengine not installed or Lambdify unavailable"
        return None

    def build_lambdify(self, args, exprs):
        import nbsymengine as sx

        is_heterogeneous = (
            isinstance(exprs, (tuple, list))
            and len(exprs) == 2
            and isinstance(exprs[0], sx.DenseMatrix)
            and isinstance(exprs[1], sx.DenseMatrix)
        )

        if is_heterogeneous:
            lmb = sx.Lambdify(args, *exprs)
            def call(inp):
                raw = lmb(*inp)
                return _to_numpy(raw)
            return call
        else:
            lmb = sx.Lambdify(args, exprs)
            def call(inp):
                return _to_numpy(lmb(inp))
            return call


class NBSymEngineLLVMAdapter(BackendAdapter):
    """nbsymengine Lambdify with LLVM JIT backend.

    Uses ``nbsymengine.Lambdify`` with ``backend='llvm'`` for JIT-compiled
    numeric evaluation.  Requires LLVM support compiled into nbsymengine.
    """

    @property
    def name(self) -> str:
        return "nbsymengine-llvm"

    def is_available(self) -> bool:
        try:
            from nbsymengine._core import have_llvm
            return have_llvm
        except (ImportError, AttributeError):
            return False

    def skip_reason(self) -> Optional[str]:
        if not self.is_available():
            return "nbsymengine built without LLVM support"
        return None

    def build_lambdify(self, args, exprs):
        import nbsymengine as sx

        is_heterogeneous = (
            isinstance(exprs, (tuple, list))
            and len(exprs) == 2
            and isinstance(exprs[0], sx.DenseMatrix)
            and isinstance(exprs[1], sx.DenseMatrix)
        )

        if is_heterogeneous:
            lmb = sx.Lambdify(args, *exprs, backend='llvm')
            def call(inp):
                raw = lmb(*inp)
                return _to_numpy(raw)
            return call
        elif isinstance(exprs, sx.DenseMatrix):
            lmb = sx.Lambdify(args, exprs, backend='llvm')
            def call(inp):
                return _to_numpy(lmb(inp))
            return call
        else:
            lmb = sx.Lambdify(args, exprs, backend='llvm')
            def call(inp):
                return _to_numpy(lmb(inp))
            return call


class NBSymEngineLambdaAdapter(BackendAdapter):
    """nbsymengine Lambdify with lambda_double (interpreter) backend.

    Uses ``nbsymengine.Lambdify`` with ``backend='lambda_double'`` for
    C++ interpreter-based numeric evaluation (no JIT).
    """

    @property
    def name(self) -> str:
        return "nbsymengine-lambda"

    def is_available(self) -> bool:
        try:
            import nbsymengine
            return hasattr(nbsymengine, 'Lambdify')
        except ImportError:
            return False

    def skip_reason(self) -> Optional[str]:
        if not self.is_available():
            return "nbsymengine not installed"
        return None

    def build_lambdify(self, args, exprs):
        import nbsymengine as sx

        is_heterogeneous = (
            isinstance(exprs, (tuple, list))
            and len(exprs) == 2
            and isinstance(exprs[0], sx.DenseMatrix)
            and isinstance(exprs[1], sx.DenseMatrix)
        )

        if is_heterogeneous:
            lmb = sx.Lambdify(args, *exprs, backend='lambda_double')
            def call(inp):
                raw = lmb(*inp)
                return _to_numpy(raw)
            return call
        elif isinstance(exprs, sx.DenseMatrix):
            lmb = sx.Lambdify(args, exprs, backend='lambda_double')
            def call(inp):
                return _to_numpy(lmb(inp))
            return call
        else:
            lmb = sx.Lambdify(args, exprs, backend='lambda_double')
            def call(inp):
                return _to_numpy(lmb(inp))
            return call


class LegacySymEngineAdapter(BackendAdapter):
    """Old symengine package (must be installed, never imported from tree)."""
    @property
    def name(self) -> str:
        return "legacy-symengine"

    def is_available(self) -> bool:
        try:
            import symengine
            return hasattr(symengine, "Lambdify")   # only there if NumPy installed
        except (ImportError, Exception):
            return False

    def skip_reason(self) -> Optional[str]:
        if not self.is_available():
            return "legacy symengine package not installed"
        return None

    def build_lambdify(self, args, exprs):
        import symengine as se
        from sympy import Matrix

        args = _coerce_args(args)
        is_heterogeneous = (
            isinstance(exprs, (tuple, list))
            and len(exprs) == 2
            and isinstance(exprs[0], Matrix)
            and isinstance(exprs[1], Matrix)
        )

        if is_heterogeneous:
            lmb = se.Lambdify(args, *exprs)
            def call(inp):
                return lmb(inp)
            return call
        else:
            lmb = se.Lambdify(args, exprs)
            def call(inp):
                return lmb(inp)
            return call


# Registry of all adapters
ALL_ADAPTERS: List[BackendAdapter] = [
    SymPyAdapter(),
    NBSymEngineAdapter(),
    NBSymEngineLambdaAdapter(),
    NBSymEngineLLVMAdapter(),
    LegacySymEngineAdapter(),
]


def get_adapter(name: str) -> BackendAdapter:
    for a in ALL_ADAPTERS:
        if a.name == name:
            return a
    raise ValueError(f"Unknown adapter: {name!r}. Available: {[a.name for a in ALL_ADAPTERS]}")


def get_available_adapters(names: Optional[List[str]] = None) -> List[BackendAdapter]:
    if names is None:
        return [a for a in ALL_ADAPTERS if a.is_available()]
    return [get_adapter(n) for n in names]
