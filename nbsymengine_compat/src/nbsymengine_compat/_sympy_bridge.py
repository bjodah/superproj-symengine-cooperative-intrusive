"""nbsymengine_compat._sympy_bridge -- to_sympy / from_sympy / sympify glue.

Public ``sympify``
------------------
The ``sympify`` exported here is the **public** version that extends
``_expr.sympify`` with SymPy object handling (``sympy.Basic``, lists,
``MatrixBase``, objects with ``_sympy_()``).  It is re-exported by the
facade as the module-level ``sympify``.

This is distinct from:
* ``_expr.sympify`` -- Python scalars only, no SymPy, acyclic leaf.
* ``_helpers._sympify`` -- internal workhorse, adds ``PyNumber`` fallback.

All three are layered: ``_helpers._sympify`` calls ``_expr.sympify`` and
``_sympy_bridge.sympify`` calls ``_expr.sympify``.  The layering is acyclic.
"""
from __future__ import annotations

from fractions import Fraction

from nbsymengine import _core
from ._expr import SympifyError, sympify as _orig_sympify, _make_integer
from ._helpers import _sympify, HAS_SYMPY, _require_sympy


# ---------------------------------------------------------------------------
# Private trig/hyperbolic shim helpers (used inside from_sympy)
# ---------------------------------------------------------------------------

def _cot(x):
    x = _sympify(x)
    return _core.div(_core.one(), _core.tan(x))


def _csc(x):
    x = _sympify(x)
    return _core.div(_core.one(), _core.sin(x))


def _sec(x):
    x = _sympify(x)
    return _core.div(_core.one(), _core.cos(x))


def _coth(x):
    x = _sympify(x)
    return _core.div(_core.one(), _core.tanh(x))


try:
    _exp = _core.exp
except AttributeError:
    def _exp(x):
        return _core.pow(_core.e(), _sympify(x))


# ---------------------------------------------------------------------------
# Public sympify
# ---------------------------------------------------------------------------

def sympify(obj, raise_error=True):
    """Public sympify: convert Python/SymPy objects to SymEngine expressions.

    Extends ``_expr.sympify`` with:
    * SymPy ``Basic`` objects (via ``from_sympy``)
    * lists/tuples (element-wise)
    * ``sympy.MatrixBase``
    * Objects with a ``_sympy_()`` method

    Falls back to ``PyNumber`` wrapping for unknown types.
    Requires SymPy for SymPy-specific conversions.
    """
    from ._wrappers import wrap
    if isinstance(obj, (_core.Basic, _core.DenseMatrix)):
        return wrap(obj)
    if hasattr(obj, '_raw') and isinstance(obj._raw, (_core.Basic, _core.DenseMatrix)):
        return obj
    if HAS_SYMPY:
        import sympy
        if isinstance(obj, sympy.Basic):
            return wrap(from_sympy(obj))
        if isinstance(obj, (list, tuple)):
            result = [sympify(v, raise_error=raise_error) for v in obj]
            return type(obj)(result)
        if isinstance(obj, sympy.MatrixBase):
            return wrap(from_sympy(obj))
        if hasattr(obj, '_sympy_'):
            return sympify(obj._sympy_(), raise_error=raise_error)
    try:
        return wrap(_orig_sympify(obj))
    except (SympifyError, TypeError, ValueError):
        pass
    try:
        from ._helpers import PyNumber
        return wrap(PyNumber(obj))
    except Exception:
        pass
    if raise_error:
        raise SympifyError(f"Cannot sympify {obj!r}")
    return False


# ---------------------------------------------------------------------------
# to_sympy
# ---------------------------------------------------------------------------

def to_sympy(expr):
    """Convert a SymEngine expression to a SymPy expression.

    Requires SymPy to be installed.  Raises ``ImportError`` with a clear
    message if SymPy is not available.
    """
    # Unwrap delegation wrapper if present
    expr = getattr(expr, '_raw', expr)

    if not HAS_SYMPY:
        _require_sympy("to_sympy()")
    import sympy
    if isinstance(expr, _core.DenseMatrix):
        return sympy.Matrix([[to_sympy(expr.get(i, j)) for j in range(expr.ncols())] for i in range(expr.nrows())])
    if not isinstance(expr, _core.Basic):
        return expr
    name = expr.__class__.__name__
    if name == 'Dummy':
        return sympy.Dummy(expr.name, dummy_index=expr.dummy_index)
    elif name == 'Symbol':
        s = expr.name
        if s == 'Catalan':
            return sympy.Catalan
        elif s == 'GoldenRatio':
            return sympy.GoldenRatio
        return sympy.Symbol(s)
    elif name == 'Integer':
        import sys
        old_limit = sys.get_int_max_str_digits()
        try:
            sys.set_int_max_str_digits(0)
            return sympy.Integer(int(str(expr)))
        finally:
            sys.set_int_max_str_digits(old_limit)
    elif name == 'Rational':
        f = Fraction(str(expr))
        return sympy.Rational(f.numerator, f.denominator)
    elif name == 'Constant':
        s = str(expr)
        if s == 'pi':
            return sympy.pi
        elif s == 'E':
            return sympy.E
        elif s == 'EulerGamma':
            return sympy.EulerGamma
        elif s == 'I':
            return sympy.I
        elif s == 'Catalan':
            return sympy.Catalan
        elif s == 'GoldenRatio':
            return sympy.GoldenRatio
        return sympy.Symbol(s)
    elif name == 'Add':
        return sympy.Add(*(to_sympy(a) for a in expr.get_args()))
    elif name == 'Mul':
        return sympy.Mul(*(to_sympy(a) for a in expr.get_args()))
    elif name == 'Pow':
        base, exp = expr.get_args()
        if isinstance(exp, _core.Integer) and int(str(exp)) == -1:
            base_sp = to_sympy(base)
            if hasattr(base_sp, 'func') and hasattr(base_sp, 'args'):
                bfn = base_sp.func.__name__ if hasattr(base_sp.func, '__name__') else ''
                inv_map = {'tan': sympy.cot, 'cot': sympy.tan,
                           'sin': sympy.csc, 'csc': sympy.sin,
                           'cos': sympy.sec, 'sec': sympy.cos,
                           'tanh': sympy.coth, 'coth': sympy.tanh,
                           'sinh': sympy.csch, 'csch': sympy.sinh,
                           'cosh': sympy.sech, 'sech': sympy.cosh}
                inv_fn = inv_map.get(bfn)
                if inv_fn is not None:
                    return inv_fn(*base_sp.args)
            return sympy.Pow(base_sp, to_sympy(exp))
        return sympy.Pow(to_sympy(base), to_sympy(exp))
    elif name in ('Eq', 'Ne', 'Ge', 'Gt', 'Le', 'Lt',
                  'Equality', 'Unequality', 'LessThan', 'StrictLessThan'):
        args = expr.get_args()
        _REL_MAP = {'Equality': 'Eq', 'Unequality': 'Ne', 'LessThan': 'Le',
                    'StrictLessThan': 'Lt'}
        fn_name = _REL_MAP.get(name, name)
        fn = getattr(sympy, fn_name)
        return fn(to_sympy(args[0]), to_sympy(args[1]))
    elif name == 'FunctionSymbol':
        fn_name = expr.name
        args = [to_sympy(a) for a in expr.get_args()]
        import sympy as _sp
        sp_fn = getattr(_sp, fn_name, None)
        if sp_fn is not None and callable(sp_fn):
            return sp_fn(*args)
        return sympy.Function(fn_name)(*args)
    elif name == '_Derivative' or name == 'Derivative':
        args = expr.get_args()
        expr_sp = to_sympy(args[0])
        variables = [to_sympy(a) for a in args[1:]]
        return sympy.Derivative(expr_sp, *variables)
    elif name == 'UnevaluatedExpr':
        args = expr.get_args()
        return sympy.UnevaluatedExpr(*(to_sympy(a) for a in args))
    elif name == 'Interval':
        args = expr.get_args()
        if len(args) >= 2:
            start_sp = to_sympy(args[0])
            end_sp = to_sympy(args[1])
            left_open = (args[2] == _core.true_const()) if len(args) > 2 else False
            right_open = (args[3] == _core.true_const()) if len(args) > 3 else False
            return sympy.Interval(start_sp, end_sp, left_open, right_open)
        return sympy.sympify(str(expr))
    elif name == 'FiniteSet':
        args = expr.get_args()
        return sympy.FiniteSet(*(to_sympy(a) for a in args))
    elif name == 'Union':
        args = expr.get_args()
        return sympy.Union(*(to_sympy(a) for a in args))
    elif name == 'Intersection':
        args = expr.get_args()
        return sympy.Intersection(*(to_sympy(a) for a in args))
    elif name == 'Complement':
        args = expr.get_args()
        return sympy.Complement(to_sympy(args[0]), to_sympy(args[1]))
    elif name == 'RealDouble':
        try:
            val = expr.as_double
        except (ValueError, TypeError, AttributeError):
            try:
                val = float(repr(expr))
            except (ValueError, TypeError):
                val = float(str(expr))
        return sympy.Float(val)
    elif name == 'ComplexDouble':
        return sympy.sympify(str(expr))
    elif name in ('Number', 'Complex', 'BooleanAtom', 'Set',
                  'UniversalSet', 'EmptySet', 'ConditionSet', 'ImageSet',
                  'Complexes', 'Reals', 'Integers', 'Rationals',
                  'Naturals', 'Naturals0',
                  'ComplexDouble', 'RationalConstant',
                  'Constant', 'NumberWrapper'):
        return sympy.sympify(str(expr))
    else:
        if name != 'Basic':
            fn = getattr(sympy, name.lower(), None) or getattr(sympy, name, None)
            if fn is not None:
                return fn(*(to_sympy(a) for a in expr.get_args()))
        return sympy.sympify(str(expr))


# ---------------------------------------------------------------------------
# from_sympy
# ---------------------------------------------------------------------------

def from_sympy(expr):
    """Convert a SymPy expression to a SymEngine expression.

    Requires SymPy to be installed.  Raises ``ImportError`` with a clear
    message if SymPy is not available.
    """
    from ._wrappers import (Interval, FiniteSet, Union, Intersection,
                            Complement, ConditionSet, ImageSet)
    if not HAS_SYMPY:
        _require_sympy("from_sympy()")
    import sympy
    if isinstance(expr, sympy.Dummy):
        return _core.Dummy(expr.name, expr.dummy_index)
    elif isinstance(expr, sympy.Symbol):
        return _core.Symbol(expr.name)
    elif isinstance(expr, sympy.Integer):
        return _make_integer(int(expr))
    elif isinstance(expr, sympy.Rational):
        return _core.div(_make_integer(expr.p), _make_integer(expr.q))
    elif isinstance(expr, sympy.Float):
        return _sympify(float(expr))
    elif expr == sympy.pi:
        return _core.pi()
    elif expr == sympy.E:
        return _core.e()
    elif expr == sympy.EulerGamma:
        return _core.euler_gamma()
    elif expr == sympy.I:
        return _core.I()
    elif expr == sympy.Catalan:
        return _core.Symbol("Catalan")
    elif expr == sympy.GoldenRatio:
        return _core.Symbol("GoldenRatio")
    elif expr == sympy.oo:
        return _core.oo()
    elif expr == -sympy.oo:
        return _core.neg(_core.oo())
    elif expr == sympy.zoo:
        return _core.zoo()
    elif expr == sympy.nan:
        return _core.nan_const()
    elif expr is sympy.true:
        return _core.true_const()
    elif expr is sympy.false:
        return _core.false_const()
    elif isinstance(expr, sympy.Add):
        args = [from_sympy(a) for a in expr.args]
        result = args[0]
        for a in args[1:]:
            result = _core.add(result, a)
        return result
    elif isinstance(expr, sympy.Mul):
        args = [from_sympy(a) for a in expr.args]
        result = args[0]
        for a in args[1:]:
            result = _core.mul(result, a)
        return result
    elif isinstance(expr, sympy.Pow):
        return _core.pow(from_sympy(expr.base), from_sympy(expr.exp))
    elif isinstance(expr, sympy.Piecewise):
        return expr
    elif isinstance(expr, sympy.Matrix):
        rows, cols = expr.shape
        flat = [from_sympy(expr[i, j]) for i in range(rows) for j in range(cols)]
        return _core.DenseMatrix(rows, cols, flat)
    elif isinstance(expr, sympy.Derivative):
        args = [from_sympy(a) for a in expr.args]
        return _core._make_derivative(args[0], args[1:])
    elif isinstance(expr, sympy.KroneckerDelta):
        args = [from_sympy(a) for a in expr.args]
        return _core.function_symbol('KroneckerDelta', *args)
    elif isinstance(expr, sympy.LeviCivita):
        args = [from_sympy(a) for a in expr.args]
        return _core.LeviCivita(args)
    elif isinstance(expr, sympy.UnevaluatedExpr):
        return _core.unevaluated_expr(from_sympy(expr.args[0]))
    elif expr is getattr(sympy.S, 'EmptySet', None):
        return _core.emptyset()
    elif expr is getattr(sympy.S, 'UniversalSet', None):
        return _core.universalset()
    elif expr is getattr(sympy.S, 'Reals', None):
        return _core.reals()
    elif expr is getattr(sympy.S, 'Integers', None):
        return _core.integers()
    elif expr is getattr(sympy.S, 'Rationals', None):
        return _core.rationals()
    elif expr is getattr(sympy.S, 'Naturals', None):
        return _core.naturals()
    elif expr is getattr(sympy.S, 'Naturals0', None):
        return _core.naturals0()
    elif expr is getattr(sympy.S, 'Complexes', None):
        return _core.complexes()
    elif isinstance(expr, sympy.Eq):
        return _core.Eq(from_sympy(expr.lhs), from_sympy(expr.rhs))
    elif isinstance(expr, sympy.Ne):
        return _core.Ne(from_sympy(expr.lhs), from_sympy(expr.rhs))
    elif isinstance(expr, sympy.Lt):
        return _core.Lt(from_sympy(expr.lhs), from_sympy(expr.rhs))
    elif isinstance(expr, sympy.Le):
        return _core.Le(from_sympy(expr.lhs), from_sympy(expr.rhs))
    elif isinstance(expr, sympy.Gt):
        return _core.Gt(from_sympy(expr.lhs), from_sympy(expr.rhs))
    elif isinstance(expr, sympy.Ge):
        return _core.Ge(from_sympy(expr.lhs), from_sympy(expr.rhs))
    elif isinstance(expr, sympy.Union):
        return _core.set_union([from_sympy(a) for a in expr.args])
    elif isinstance(expr, sympy.Intersection):
        return _core.set_intersection([from_sympy(a) for a in expr.args])
    elif isinstance(expr, sympy.Complement):
        return _core.set_complement(from_sympy(expr.args[0]), from_sympy(expr.args[1]))
    elif isinstance(expr, sympy.FiniteSet):
        return _core.finiteset({from_sympy(a) for a in expr.args})
    elif isinstance(expr, sympy.Interval):
        left_open = bool(expr.left_open)
        right_open = bool(expr.right_open)
        return _core.interval(from_sympy(expr.start), from_sympy(expr.end), left_open, right_open)
    elif isinstance(expr, sympy.Subs):
        mapping = dict(zip(
            [from_sympy(v) for v in expr.variables],
            [from_sympy(p) for p in expr.point]
        ))
        return _core._make_subs(from_sympy(expr.expr), mapping)
    elif hasattr(expr, 'func') and hasattr(expr, 'args') and callable(expr.func):
        fn_name = str(expr.func)
        if fn_name.startswith("<class '") or fn_name.startswith("class '"):
            fn_name = expr.func.__name__
        if hasattr(expr, 'name'):
            fn_name = expr.name
        _KNOWN_FUNCTIONS = {
            'sin': _core.sin, 'cos': _core.cos, 'tan': _core.tan,
            'asin': _core.asin, 'acos': _core.acos, 'atan': _core.atan,
            'atan2': _core.atan2,
            'sinh': _core.sinh, 'cosh': _core.cosh, 'tanh': _core.tanh,
            'sech': _core.sech, 'csch': _core.csch,
            'log': _core.log, 'sqrt': _core.sqrt, 'exp': _exp,
            'sign': _core.sign, 'floor': _core.floor, 'ceiling': _core.ceiling,
            'abs': _core.abs, 'gamma': _core.gamma,
            'erf': _core.erf, 'erfc': _core.erfc,
            'lambertw': _core.lambertw, 'zeta': lambda *args: _core.zeta(args[0]) if len(args) == 1 else _core.function_symbol('zeta', *args),
            'dirichlet_eta': _core.dirichlet_eta,
            'beta': _core.beta, 'conjugate': _core.conjugate,
            'digamma': _core.digamma, 'loggamma': _core.loggamma,
            'polygamma': _core.polygamma, 'trigamma': _core.trigamma,
            'uppergamma': _core.uppergamma, 'lowergamma': _core.lowergamma,
            'cot': _cot, 'csc': _csc, 'sec': _sec,
            'coth': _coth,
            # Set types
            'finiteset': FiniteSet, 'interval': Interval,
            'union': Union, 'intersection': Intersection,
            'complement': Complement, 'conditionset': ConditionSet,
            'imageset': ImageSet,
            'contains': _core.contains,
        }
        core_fn = _KNOWN_FUNCTIONS.get(fn_name) or _KNOWN_FUNCTIONS.get(fn_name.lower())
        if core_fn is not None:
            args = [from_sympy(a) for a in expr.args]
            if fn_name.lower() == 'zeta' and len(args) == 2:
                return _core.function_symbol('zeta', *args)
            return core_fn(*args)
        args = [from_sympy(a) for a in expr.args]
        return _core.function_symbol(fn_name, *args)
    else:
        name = expr.__class__.__name__
        _SHIM_FUNCTIONS = {
            'cot': _cot, 'csc': _csc, 'sec': _sec,
            'coth': _coth,
        }
        shim_fn = _SHIM_FUNCTIONS.get(name.lower())
        if shim_fn is not None:
            return shim_fn(*(from_sympy(a) for a in expr.args))
        fn = getattr(_core, name.lower(), None) or getattr(_core, name, None)
        if fn is not None:
            return fn(*(from_sympy(a) for a in expr.args))
        try:
            from ._helpers import PyNumber
            return PyNumber(expr)
        except Exception:
            raise NotImplementedError(f"Conversion from SymPy {name} not implemented")
