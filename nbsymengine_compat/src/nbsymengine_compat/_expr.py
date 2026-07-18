"""nbsymengine_compat._expr -- Low-level sympify coercion helper.

Provides ``sympify`` to convert Python scalars into ``_core.Basic`` objects.
Arithmetic dunders live on ``Basic`` in C++, so no wrapper ``Expr`` class is
needed -- ``Basic`` *is* the expression type.

Layering contract
-----------------
This module is the **leaf** of the sympify hierarchy.  It must NOT import from
``_helpers``, ``_sympy_bridge``, or any other compat submodule, to avoid
circular dependencies.  It handles only native Python types (and numpy
generics) and raises ``SympifyError`` for anything it cannot convert.

The public ``sympify`` in ``_sympy_bridge`` extends this with SymPy object
handling.  The ``_sympify`` helper in ``_helpers`` extends it further with
``PyNumber`` wrapping.  See each function's docstring for its exact contract.
"""
from __future__ import annotations

from fractions import Fraction

from nbsymengine import _core


class SympifyError(Exception):
    """Raised when an object cannot be converted to a SymEngine expression."""


def _make_integer(i):
    """Create a ``_core.Integer`` from a Python *int*.

    Handles arbitrary-precision integers outside the 64-bit range by
    temporarily lifting ``sys.get_int_max_str_digits``.
    """
    if -9223372036854775808 <= i <= 9223372036854775807:
        return _core.integer(i)
    else:
        import sys
        old_limit = sys.get_int_max_str_digits()
        try:
            sys.set_int_max_str_digits(0)
            return _core.integer(str(i))
        finally:
            sys.set_int_max_str_digits(old_limit)


def sympify(obj):
    """Coerce *obj* into a ``_core.Basic`` instance (Python scalars only).

    Contract:
    * ``Basic`` instances pass through unchanged.
    * ``int`` (and ``bool``) become ``_core.Integer``.
    * ``float`` becomes ``_core.RealDouble`` (rejects NaN/inf).
    * ``complex`` becomes a complex expression (real + imag * I).
    * ``Fraction`` becomes ``_core.Rational``.
    * numpy generics are unwrapped via ``.item()``.
    * Anything else raises ``SympifyError``.

    This function does **not** handle SymPy objects.  Use
    ``_sympy_bridge.sympify`` (public) or ``_helpers._sympify`` (internal)
    for that.  This function must not import from those modules.
    """
    if isinstance(obj, _core.Basic):
        return obj

    if hasattr(obj, '_raw') and isinstance(obj._raw, _core.Basic):
        return obj

    if isinstance(obj, bool):
        return _make_integer(int(obj))

    if isinstance(obj, int):
        return _make_integer(obj)

    if isinstance(obj, float):
        if obj != obj:  # NaN
            raise SympifyError(f"Cannot sympify {obj!r}")
        if obj == float('inf') or obj == float('-inf'):
            raise SympifyError(f"Cannot sympify {obj!r}")
        return _core.real_double(obj)

    if isinstance(obj, complex):
        real_part = sympify(obj.real)
        imag_part = sympify(obj.imag)
        return _core.add(real_part, _core.mul(imag_part, _core.I()))

    if isinstance(obj, Fraction):
        return _core.div(_make_integer(obj.numerator),
                         _make_integer(obj.denominator))

    import sys
    np = sys.modules.get('numpy')
    if np is not None and isinstance(obj, np.generic):
        return sympify(obj.item())

    raise SympifyError(f"Cannot sympify {obj!r}")
