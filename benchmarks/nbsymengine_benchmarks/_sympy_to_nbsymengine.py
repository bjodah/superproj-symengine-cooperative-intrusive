"""Helper to convert SymPy expressions to native nbsymengine expressions.

This is a benchmark-local helper module and must not import nbsymengine_compat.
"""
from __future__ import annotations


def sympy_to_nbsymengine(expr):
    import sympy
    import nbsymengine as sx

    if isinstance(expr, (list, tuple)):
        return type(expr)(sympy_to_nbsymengine(x) for x in expr)

    if isinstance(expr, sympy.Matrix):
        rows, cols = expr.shape
        flat = [sympy_to_nbsymengine(expr[i, j]) for i in range(rows) for j in range(cols)]
        return sx.DenseMatrix(rows, cols, flat)

    if isinstance(expr, sympy.Symbol):
        if isinstance(expr, sympy.Dummy):
            return sx.Dummy(expr.name)
        return sx.Symbol(expr.name)

    if isinstance(expr, sympy.Integer):
        return sx.integer(int(expr))

    if isinstance(expr, sympy.Rational):
        return sx.div(sx.integer(expr.p), sx.integer(expr.q))

    if isinstance(expr, sympy.Float):
        return sx.real_double(float(expr))

    if isinstance(expr, sympy.Add):
        from functools import reduce
        return reduce(lambda x, y: x + y, (sympy_to_nbsymengine(a) for a in expr.args))

    if isinstance(expr, sympy.Mul):
        from functools import reduce
        return reduce(lambda x, y: x * y, (sympy_to_nbsymengine(a) for a in expr.args))

    if isinstance(expr, sympy.Pow):
        return sympy_to_nbsymengine(expr.base) ** sympy_to_nbsymengine(expr.exp)

    if isinstance(expr, sympy.Function):
        name = expr.func.__name__
        if name == 'exp':
            return sx.e() ** sympy_to_nbsymengine(expr.args[0])
        fn = getattr(sx, name.lower(), None) or getattr(sx, name, None)
        if fn is not None:
            return fn(*(sympy_to_nbsymengine(a) for a in expr.args))
        raise NotImplementedError(f"Function {name} not supported in direct nbsymengine converter")

    if expr == sympy.pi:
        return sx.pi()
    if expr == sympy.E:
        return sx.e()

    if isinstance(expr, (int, float)):
        return sx.integer(expr) if isinstance(expr, int) else sx.real_double(expr)

    return expr
