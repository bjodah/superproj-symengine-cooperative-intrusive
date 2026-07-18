"""nbsymengine_compat._helpers -- Small utility functions and classes."""
from __future__ import annotations

from nbsymengine import _core
from ._expr import SympifyError, sympify as _orig_sympify, _make_integer


# ---------------------------------------------------------------------------
# HAS_SYMPY flag -- True when SymPy is importable at runtime.
# Guard SymPy-only paths behind this to give clear errors instead of opaque
# ModuleNotFoundError deep in a property access.
# ---------------------------------------------------------------------------

try:
    import sympy as _sympy_mod
    HAS_SYMPY = True
    del _sympy_mod
except ImportError:
    HAS_SYMPY = False


def _require_sympy(feature):
    """Raise a clear error when *feature* requires SymPy but it is absent."""
    raise ImportError(
        f"the legacy compat layer requires SymPy for {feature}; "
        f"install sympy or use native nbsymengine APIs"
    )


def _sympify(obj, raise_error=True):
    """Main coercion function used throughout the compat layer.

    Coerces *obj* into a ``_core.Basic`` instance.  Accepts:
    * ``_core.Basic`` passthrough
    * Delegation wrapper (``Basic``) passthrough via hasattr(_raw)
    * SymPy objects (via ``from_sympy``) -- requires SymPy
    * Python scalars (int, float, bool, complex, Fraction) via ``_expr.sympify``
    * Anything else is wrapped in ``PyNumber``

    This is the workhorse ``_sympify`` used by all monkey-patch code and
    wrappers.  It must NOT re-import the public ``sympify`` from
    ``_sympy_bridge`` (that would create a circular import).
    """
    if isinstance(obj, _core.Basic):
        return obj
    if hasattr(obj, '_raw') and isinstance(obj._raw, _core.Basic):
        return obj._raw

    if HAS_SYMPY:
        import sympy
        if isinstance(obj, sympy.Basic):
            from ._sympy_bridge import from_sympy
            return from_sympy(obj)
    try:
        return _orig_sympify(obj)
    except (SympifyError, TypeError, ValueError):
        pass
    try:
        return PyNumber(obj)
    except Exception:
        pass
    if raise_error:
        raise SympifyError(f"Cannot sympify {obj!r}")
    return False


# ---------------------------------------------------------------------------
# Stub helper for not-yet-implemented names
# ---------------------------------------------------------------------------

def _missing(name):
    def _stub(*a, **k):
        raise NotImplementedError(
            f"nbsymengine_compat: {name} not implemented yet"
        )
    _stub.__name__ = name
    _stub.__qualname__ = name
    return _stub


def _missing_class(name, exc_type=NotImplementedError):
    """Create a placeholder class for names used in isinstance() checks."""
    return type(name, (), {
        "__init__": lambda self, *a, **k: (_ for _ in ()).throw(
            exc_type(f"nbsymengine_compat: {name} not implemented yet")
        ),
    })


def _wrap_fn(fn):
    def wrapper(*args, **kwargs):
        coerced = [_sympify(a) for a in args]
        return fn(*coerced, **kwargs)
    return wrapper


def _to_bool_arg(a):
    raw_a = getattr(a, '_raw', a)
    if raw_a is True:
        return _core.true_const()
    if raw_a is False:
        return _core.false_const()
    if isinstance(raw_a, _core.Boolean):
        return raw_a
    if HAS_SYMPY:
        import sympy
        if raw_a is sympy.true:
            return _core.true_const()
        if raw_a is sympy.false:
            return _core.false_const()
        if isinstance(raw_a, sympy.Basic):
            from ._sympy_bridge import from_sympy
            return from_sympy(raw_a)
    raise TypeError(f"expected Boolean, got {type(a).__name__}")


def _raise_zerodiv(fn):
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except RuntimeError as e:
            if "ZeroDivisionError" in str(e):
                raise ZeroDivisionError(str(e))
            raise
    return wrapper


same_object = _core.same_object
cpp_use_count = _core.cpp_use_count

have_mpfr = False
have_mpc = False


def nb_isinstance_DenseMatrix(obj):
    try:
        if isinstance(obj, _core.DenseMatrix):
            return True
        if hasattr(obj, '_raw') and isinstance(obj._raw, _core.DenseMatrix):
            return True
        return False
    except Exception:
        return False


class PyNumber:
    """Wrapper for Python number types not directly supported by SymEngine."""
    def __init__(self, val, module=None):
        self._val = val
        self._module = module

    def __eq__(self, other):
        if isinstance(other, PyNumber):
            return self._val == other._val
        return self._val == other

    def __hash__(self):
        return hash(self._val)

    def __str__(self):
        return str(self._val)

    def __repr__(self):
        return f"PyNumber({self._val!r})"

    def __add__(self, other):
        if isinstance(other, PyNumber):
            return PyNumber(self._val + other._val, self._module)
        return PyNumber(self._val + other, self._module)

    def __radd__(self, other):
        return PyNumber(other + self._val, self._module)

    def __sub__(self, other):
        if isinstance(other, PyNumber):
            return PyNumber(self._val - other._val, self._module)
        return PyNumber(self._val - other, self._module)

    def __rsub__(self, other):
        return PyNumber(other - self._val, self._module)

    def __mul__(self, other):
        if isinstance(other, PyNumber):
            return PyNumber(self._val * other._val, self._module)
        return PyNumber(self._val * other, self._module)

    def __rmul__(self, other):
        return PyNumber(other * self._val, self._module)

    def __truediv__(self, other):
        if isinstance(other, PyNumber):
            return PyNumber(self._val / other._val, self._module)
        return PyNumber(self._val / other, self._module)

    def __rtruediv__(self, other):
        return PyNumber(other / self._val, self._module)

    def _sympy_(self):
        return self._val


class PyFunction:
    """Wrapper for Python function objects not directly supported by SymEngine."""
    def __init__(self, func, module=None):
        self._func = func
        self._module = module

    def __call__(self, *args):
        return self._func(*args)


sage_module = None


def wrap_sage_function(expr):
    """Wrap a Sage expression as a SymEngine-compatible object."""
    from ._sympy_bridge import sympify
    return sympify(expr)
