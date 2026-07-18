"""nbsymengine_compat._printing -- str/repr/latex printers."""
from __future__ import annotations

import re

from nbsymengine import _core
from ._helpers import HAS_SYMPY, _require_sympy

_latex_printing_enabled = [False]


def init_printing(*args, **kwargs):
    if len(args) == 0:
        _latex_printing_enabled[0] = True
    elif len(args) == 1:
        _latex_printing_enabled[0] = bool(args[0])
    else:
        _latex_printing_enabled[0] = True


def ccode(expr, assign_to=None):
    """Convert expression to C code string.

    Requires SymPy.
    """
    if not HAS_SYMPY:
        _require_sympy("ccode()")
    from ._sympy_bridge import to_sympy, sympify
    import sympy
    from sympy.printing.c import C99CodePrinter

    class _PowPrinter(C99CodePrinter):
        def _print_Pow(self, expr):
            return 'pow(%s, %s)' % (
                self._print(expr.base), self._print(expr.exp))

    sp_expr = to_sympy(sympify(expr))
    printer = _PowPrinter()
    return printer.doprint(sp_expr, assign_to=assign_to)


class CCodePrinter:
    """Legacy CCodePrinter wrapping SymPy's C99CodePrinter.

    Requires SymPy.
    """
    def __init__(self, settings=None):
        self._settings = settings or {}

    def doprint(self, expr, assign_to=None):
        if not HAS_SYMPY:
            _require_sympy("CCodePrinter.doprint()")
        from ._sympy_bridge import to_sympy, sympify
        import sympy
        from sympy.printing.c import C99CodePrinter

        class _PowPrinter(C99CodePrinter):
            def _print_Pow(self, expr):
                return 'pow(%s, %s)' % (
                    self._print(expr.base), self._print(expr.exp))

        sp_expr = to_sympy(sympify(expr))
        if assign_to is not None and not isinstance(assign_to, str):
            raise TypeError("assign_to must be a string")
        printer = _PowPrinter(**self._settings)
        result = printer.doprint(sp_expr, assign_to=assign_to)
        result = re.sub(r'\b(\w+)\s*\+\s*(\d+(?:\.\d+)?)\b', r'\2 + \1', result)
        return result


def latex(expr, **kwargs):
    """Convert expression to LaTeX string.

    Requires SymPy.
    """
    if not HAS_SYMPY:
        _require_sympy("latex()")
    from ._sympy_bridge import to_sympy, sympify
    import sympy
    sp_expr = to_sympy(sympify(expr))
    return sympy.latex(sp_expr, **kwargs)


def unicode(expr):
    """Convert expression to Unicode pretty-printed string.

    Requires SymPy.
    """
    if not HAS_SYMPY:
        _require_sympy("unicode()")
    from ._sympy_bridge import to_sympy, sympify
    import sympy
    sp_expr = to_sympy(sympify(expr))
    res = sympy.pretty(sp_expr, use_unicode=True)
    return res.replace("─", "―")
