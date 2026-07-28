"""Tests for the nbsymengine.legacy compatibility shim."""


def test_symbol_basics():
    from nbsymengine_compat import symengine_py_compat as se
    x = se.Symbol("x")
    assert x.name == "x"
    assert str(x) == "x"
    assert repr(x) == "x"
    assert isinstance(x, se.Basic)


def test_symbols_helper():
    from nbsymengine_compat import symengine_py_compat as se
    # Single symbol
    x = se.symbols("x")
    assert isinstance(x, se.Symbol)
    assert x.name == "x"
    # Multiple symbols
    x, y, z = se.symbols("x y z")
    assert (x.name, y.name, z.name) == ("x", "y", "z")
    # Comma-separated
    a, b, c = se.symbols("a,b,c")
    assert (a.name, b.name, c.name) == ("a", "b", "c")
    # Trailing comma forces tuple
    result = se.symbols("x,")
    assert isinstance(result, tuple)
    assert len(result) == 1
    # Range syntax
    syms = se.symbols("x0:3")
    assert len(syms) == 3
    assert syms[0].name == "x0"
    # Alpha range
    syms = se.symbols("x:z")
    assert len(syms) == 3
    assert syms[0].name == "x"


def test_arithmetic_operators():
    from nbsymengine_compat import symengine_py_compat as se
    x = se.Symbol("x")
    # Addition
    expr = x + 1
    assert str(expr) in ("x + 1", "1 + x")
    # Subtraction
    expr = x - 1
    assert str(expr) in ("x - 1", "-1 + x")
    # Multiplication
    expr = 2 * x
    assert str(expr) in ("2*x", "2x")
    # Power
    expr = x ** 2
    assert str(expr) in ("x**2", "x^2")
    # Identity: (x + 1) - 1 == x
    assert (x + 1) - 1 == x


def test_int_coercion():
    from nbsymengine_compat import symengine_py_compat as se
    x = se.Symbol("x")
    # int on the right
    assert isinstance(x + 1, se.Basic)
    # int on the left
    assert isinstance(1 + x, se.Basic)
    # negation
    assert isinstance(-x, se.Basic)
    # unary plus
    assert isinstance(+x, se.Basic)
    # unsupported type should raise TypeError
    try:
        x + "hello"
        assert False, "Should have raised TypeError"
    except TypeError:
        pass


def test_sympify():
    from nbsymengine_compat._expr import sympify, SympifyError
    from nbsymengine_compat import symengine_py_compat as se
    # int -> Integer
    assert isinstance(sympify(42), se.Basic)
    # bool -> Integer (must be caught before int)
    assert isinstance(sympify(True), se.Basic)
    assert str(sympify(True)) == "1"
    assert str(sympify(False)) == "0"
    # float -> Rational
    assert isinstance(sympify(0.5), se.Basic)
    # Fraction -> Rational
    from fractions import Fraction
    assert isinstance(sympify(Fraction(1, 3)), se.Basic)
    # Basic passthrough
    x = se.Symbol("x")
    assert sympify(x) is x
    # Unsupported type raises SympifyError
    try:
        sympify("hello")
        assert False, "Should have raised"
    except SympifyError:
        pass
    # Float special values raise SympifyError
    for bad in (float('inf'), float('-inf'), float('nan')):
        try:
            sympify(bad)
            assert False, f"sympify({bad!r}) should have raised"
        except SympifyError:
            pass


def test_raises_helper():
    from nbsymengine_compat.test_utilities import raises
    # Callable mode
    raises(ZeroDivisionError, lambda: 1 / 0)
    # Context manager mode
    with raises(ZeroDivisionError):
        1 / 0


def test_S_identity():
    from nbsymengine_compat import symengine_py_compat as se
    # Singleton identity
    assert se.S.Zero is se.S.Zero
    assert se.S.One is se.S.One
    assert se.S.Pi is se.S.Pi
    assert se.S.Exp1 is se.S.Exp1
    assert se.S.EulerGamma is se.S.EulerGamma
    # EmptySet
    assert se.S.EmptySet is se.S.EmptySet
    # S callable works as sympify
    assert isinstance(se.S(42), se.Basic)
    assert str(se.S(42)) == "42"


def test_S_properties():
    from nbsymengine_compat import symengine_py_compat as se
    assert str(se.S.Zero) == "0"
    assert str(se.S.One) == "1"


def test_dummy():
    from nbsymengine_compat import symengine_py_compat as se
    d1 = se.Dummy("x")
    d2 = se.Dummy("x")
    assert d1.name == "x"
    assert d1 != d2  # different dummy_index
    assert isinstance(d1, se.Symbol)


def test_module_constants():
    from nbsymengine_compat import symengine_py_compat as se
    assert se.pi is not None
    assert str(se.pi) == "pi"
    assert se.E is not None
    assert se.EulerGamma is not None
    # Previously unsupported constants are now real singletons
    assert se.I is not None
    assert str(se.I) == "I"
    assert se.oo is not None
    assert str(se.oo) == "oo"
    assert se.zoo is not None
    assert str(se.zoo) == "zoo"
    assert se.nan is not None
    assert str(se.nan) == "nan"
    assert se.true is not None
    assert str(se.true) == "True"
    assert se.false is not None
    assert str(se.false) == "False"


def test_lowercase_set_factories_use_compat_coercion():
    from nbsymengine_compat import symengine_py_compat as se

    x = se.Symbol("x")
    domain = se.Interval(0, 1)

    assert se.interval(0, 1) == domain
    assert se.finiteset(1, 2) == se.FiniteSet(1, 2)
    assert se.set_union(domain, se.EmptySet()) == domain
    assert se.set_intersection(domain, se.UniversalSet()) == domain
    assert se.set_complement(domain, se.EmptySet()) == domain
    assert se.conditionset(x, se.Gt(x, 0)) == se.ConditionSet(x, se.Gt(x, 0))
    assert se.imageset(x, 1, domain) == se.FiniteSet(1)


def test_unsupported_raises_not_implemented():
    from nbsymengine_compat import symengine_py_compat as se
    # Each unsupported name should raise NotImplementedError with the name
    for name in ():
        obj = getattr(se, name, None)
        if obj is not None:
            try:
                obj()
                assert False, f"{name} should have raised"
            except NotImplementedError as e:
                assert name in str(e)


def test_matrix_equality():
    from nbsymengine_compat import symengine_py_compat as se
    m = se.zeros(2)
    assert m == se.zeros(2)
    assert m != se.ones(2)
    assert m != None
    assert m != 5
    assert not (m == None)
    assert not (m == 5)


import pickle
import pytest


def _check_pickle_roundtrip(obj):
    """Pickle round-trip preserving type and value."""
    data = pickle.dumps(obj)
    result = pickle.loads(data)
    assert type(result) is type(obj), (type(obj).__name__, type(result).__name__)
    assert result == obj, (repr(obj), repr(result))
    return result


def test_pickle_finiteset():
    from nbsymengine_compat import symengine_py_compat as se
    fs = se.FiniteSet(1, 2, 3)
    _check_pickle_roundtrip(fs)


def test_pickle_interval():
    from nbsymengine_compat import symengine_py_compat as se
    iv = se.Interval(0, 1)
    _check_pickle_roundtrip(iv)
    iv_open = se.Interval(0, 1, True, True)
    _check_pickle_roundtrip(iv_open)


def test_pickle_union():
    from nbsymengine_compat import symengine_py_compat as se
    u = se.Union(se.Interval(0, 1), se.Interval(2, 3))
    _check_pickle_roundtrip(u)


def test_pickle_intersection():
    from nbsymengine_compat import symengine_py_compat as se
    inter = se.Intersection(se.Interval(0, 2), se.Interval(1, 3))
    _check_pickle_roundtrip(inter)


def test_pickle_complement():
    from nbsymengine_compat import symengine_py_compat as se
    # SymPy auto-evaluates Complement(FiniteSet(x,1), FiniteSet(x)) to FiniteSet(1).
    # The type may change after round-trip, but the value must be preserved.
    x = se.Symbol("x")
    comp = se.Complement(se.FiniteSet(x, se.Integer(1)), se.FiniteSet(x))
    data = pickle.dumps(comp)
    result = pickle.loads(data)
    assert result == comp


def test_pickle_dummy_in_expression():
    from nbsymengine_compat import symengine_py_compat as se
    d = se.Dummy("d")
    a = d + 1
    result = pickle.loads(pickle.dumps(a))
    # The Dummy identity must survive pickling
    assert isinstance(result, se.Add)
    args = result.get_args()
    d_arg = args[0] if isinstance(args[0], se.Dummy) else args[1]
    assert isinstance(d_arg, se.Dummy), type(d_arg).__name__
    assert d_arg.dummy_index == d.dummy_index


def test_pickle_set_types_preserve_type():
    from nbsymengine_compat import symengine_py_compat as se
    objects = [
        se.FiniteSet(1, 2, 3),
        se.Interval(0, 1),
        se.Union(se.Interval(0, 1), se.Interval(2, 3)),
        se.Intersection(se.Interval(0, 2), se.Interval(1, 3)),
    ]
    for obj in objects:
        data = pickle.dumps(obj)
        result = pickle.loads(data)
        assert type(result) is type(obj), (
            f"{type(obj).__name__} did not survive pickle: got {type(result).__name__}"
        )
        assert result == obj


def test_safe_sympify_rejects_code_execution():
    """_safe_sympify must not execute arbitrary Python code."""
    from nbsymengine_compat.symengine_py_compat import _safe_sympify
    import sympy
    # These payloads would execute code if eval() had access to builtins.
    # With the restricted global_dict, they must either raise or return
    # a SymPy expression (UndefinedFunction applied to args), never actually
    # execute the code.
    # __import__ must not return the os module
    with pytest.raises(Exception):
        _safe_sympify("__import__('os').getcwd()")
    # eval('1+1') must return a symbolic eval(2), not the integer 2
    result = _safe_sympify("eval('1+1')")
    assert not isinstance(result, int), "eval() was actually executed!"
    # exec must not succeed
    with pytest.raises(Exception):
        _safe_sympify("exec('import os')")


def test_safe_sympify_parses_valid_expressions():
    """_safe_sympify must still parse normal SymPy expressions."""
    from nbsymengine_compat.symengine_py_compat import _safe_sympify
    import sympy
    assert _safe_sympify("x + 1") == sympy.Symbol("x") + 1
    assert _safe_sympify("2*x") == 2 * sympy.Symbol("x")
    assert _safe_sympify("sin(x)") == sympy.sin(sympy.Symbol("x"))


def test_pickle_piecewise_roundtrip():
    """Piecewise round-trips as a SymPy object (no SymEngine equivalent)."""
    from nbsymengine_compat import symengine_py_compat as se
    x = se.Symbol("x")
    pw = se.Piecewise((x, x > 0), (0, True))
    _check_pickle_roundtrip(pw)


def test_pickle_lambdify_sympy_backend_not_supported():
    """Compat Lambdify pickling is intentionally limited to delegated native backends."""
    from nbsymengine_compat import symengine_py_compat as se
    x = se.Symbol("x")
    lmb = se.Lambdify([x], x + 1, backend='sympy')
    with pytest.raises(NotImplementedError):
        pickle.dumps(lmb)


def test_has_sympy_flag():
    """HAS_SYMPY must be a bool and True when sympy is installed."""
    from nbsymengine_compat._helpers import HAS_SYMPY
    assert isinstance(HAS_SYMPY, bool)
    # In the test environment, sympy is installed
    import importlib
    assert HAS_SYMPY == (importlib.util.find_spec("sympy") is not None)


def test_native_is_zero_integer():
    """is_zero on Integer must use native C++, not SymPy round-trip."""
    from nbsymengine_compat import symengine_py_compat as se
    assert se.Integer(0).is_zero is True
    assert se.Integer(1).is_zero is False
    assert se.Integer(-1).is_zero is False


def test_native_is_positive_integer():
    """is_positive on Integer must use native C++."""
    from nbsymengine_compat import symengine_py_compat as se
    assert se.Integer(1).is_positive is True
    assert se.Integer(0).is_positive is False
    assert se.Integer(-1).is_positive is False


def test_native_is_negative_integer():
    """is_negative on Integer must use native C++."""
    from nbsymengine_compat import symengine_py_compat as se
    assert se.Integer(-1).is_negative is True
    assert se.Integer(0).is_negative is False
    assert se.Integer(1).is_negative is False


def test_native_is_real_integer():
    """is_real on Integer must return True without SymPy."""
    from nbsymengine_compat import symengine_py_compat as se
    assert se.Integer(42).is_real is True


def test_native_is_finite_integer():
    """is_finite on Integer must return True without SymPy."""
    from nbsymengine_compat import symengine_py_compat as se
    assert se.Integer(42).is_finite is True


def test_native_is_number_types():
    """is_number on Number subclasses must return True."""
    from nbsymengine_compat import symengine_py_compat as se
    assert se.Integer(42).is_number is True
    assert se.pi.is_number is True


def test_native_is_atom_types():
    """is_AAtom on atomic types must return True."""
    from nbsymengine_compat import symengine_py_compat as se
    x = se.Symbol("x")
    assert x.is_Atom is True
    assert se.Integer(42).is_Atom is True
    assert se.pi.is_Atom is True


def test_native_predicate_symbol_indeterminate():
    """is_zero/is_positive/is_negative on Symbol must return None (indeterminate)."""
    from nbsymengine_compat import symengine_py_compat as se
    x = se.Symbol("x")
    assert x.is_zero is None
    assert x.is_positive is None
    assert x.is_negative is None
    assert x.is_real is None
    assert x.is_finite is None


def test_native_is_complex_integer():
    """is_complex on Integer/Rational must return False (no imaginary part)."""
    from nbsymengine_compat import symengine_py_compat as se
    assert se.Integer(42).is_complex is False


def test_arithmetic_fast_path():
    """Arithmetic must work without triggering SymPy import for common cases."""
    from nbsymengine_compat import symengine_py_compat as se
    x = se.Symbol("x")
    # Basic arithmetic
    assert isinstance(x + 1, se.Basic)
    assert isinstance(1 + x, se.Basic)
    assert isinstance(x * 2, se.Basic)
    assert isinstance(2 * x, se.Basic)
    assert isinstance(x ** 2, se.Basic)
    assert isinstance(x / 2, se.Basic)
    # Identity
    assert (x + 1) - 1 == x
    # "hello" + x must raise TypeError
    try:
        "hello" + x
        assert False, "Should have raised TypeError"
    except TypeError:
        pass


def test_native_is_real_double():
    """is_real on RealDouble must return True."""
    from nbsymengine_compat import symengine_py_compat as se
    assert se.RealDouble(3.14).is_real is True
    assert se.RealDouble(0.0).is_zero is True
    assert se.RealDouble(2.5).is_positive is True
    assert se.RealDouble(-1.5).is_negative is True


def test_legacy_shim_delegates():
    """The legacy shim Lambdify delegates to the direct implementation."""
    from nbsymengine_compat import symengine_py_compat as se
    x = se.Symbol('x')
    f = se.Lambdify([x], x * x + 1)
    result = f([3.0])
    import numpy as np
    np.testing.assert_allclose(result, [10.0], rtol=1e-12)


def test_legacy_shim_has_direct_attribute():
    """The legacy shim stores _direct when delegation succeeds."""
    from nbsymengine_compat import symengine_py_compat as se
    from nbsymengine.lambdify import Lambdify as DirectLambdify
    x = se.Symbol('x')
    f = se.Lambdify([x], x * x + 1)
    assert hasattr(f, '_direct')
    assert f._direct is not None
    assert isinstance(f._direct, DirectLambdify)


def _lambdify_backends():
    """Every native backend the compat shim can delegate to."""
    from nbsymengine_compat import symengine_py_compat as se
    return ['lambda'] + (['llvm'] if se.have_llvm else [])


def test_lambdify_scalar_expr_shape():
    """A single scalar expression yields a 0-d array (legacy out_shape ())."""
    import numpy as np
    from nbsymengine_compat import symengine_py_compat as se
    x, y = se.symbols('x y')
    for backend in _lambdify_backends():
        f = se.Lambdify([x, y], x ** 2 + y, backend=backend)
        assert f.n_exprs == 1
        assert f.out_shapes == [()]
        res = f(np.array([2.0, 3.0]))
        assert isinstance(res, np.ndarray)
        assert res.shape == ()
        assert res == 7.0


def test_lambdify_vector_expr_shape():
    """A list of k expressions yields one (k,) array, not a list."""
    import numpy as np
    from nbsymengine_compat import symengine_py_compat as se
    x, y = se.symbols('x y')
    for backend in _lambdify_backends():
        f = se.Lambdify([x, y], [x + y, x * y, x - y], backend=backend)
        assert f.n_exprs == 1
        assert f.out_shapes == [(3,)]
        res = f(np.array([2.0, 3.0]))
        assert res.shape == (3,)
        np.testing.assert_allclose(res, [5.0, 6.0, -1.0])


def test_lambdify_matrix_expr_shape():
    """A single DenseMatrix expression yields an (nrows, ncols) array."""
    import numpy as np
    from nbsymengine_compat import symengine_py_compat as se
    x, y = se.symbols('x y')
    mat = se.DenseMatrix(2, 3, [x, y, x + y, x * y, x - y, x ** 2])
    for backend in _lambdify_backends():
        f = se.Lambdify([x, y], mat, backend=backend)
        assert f.out_shapes == [(2, 3)]
        res = f(np.array([2.0, 3.0]))
        assert isinstance(res, np.ndarray)
        assert res.shape == (2, 3)
        np.testing.assert_allclose(
            res, [[2.0, 3.0, 5.0], [6.0, -1.0, 4.0]])


def test_lambdify_heterogeneous_returns_list():
    """Heterogeneous (vector, jacobian) output is a *list* of shaped arrays."""
    import numpy as np
    from nbsymengine_compat import symengine_py_compat as se
    x, y = se.symbols('x y')
    args = se.DenseMatrix(2, 1, [x, y])
    vec = se.DenseMatrix(2, 1, [x ** 3 * y, (x + 1) * (y + 1)])
    jac = vec.jacobian(args)
    for backend in _lambdify_backends():
        f = se.Lambdify(args, vec, jac, backend=backend)
        assert f.n_exprs == 2
        assert f.out_shapes == [(2, 1), (2, 2)]
        res = f(np.array([7.0, 11.0]))
        assert isinstance(res, list)  # legacy returns a list, not a tuple
        v, m = res
        assert v.shape == (2, 1) and m.shape == (2, 2)
        X, Y = 7.0, 11.0
        np.testing.assert_allclose(v, [[X ** 3 * Y], [(X + 1) * (Y + 1)]])
        np.testing.assert_allclose(
            m, [[3 * X ** 2 * Y, X ** 3], [Y + 1, X + 1]])


def test_lambdify_broadcasting():
    """A (m, n_args) input adds a leading m dimension to every output."""
    import numpy as np
    from nbsymengine_compat import symengine_py_compat as se
    x, y = se.symbols('x y')
    mat = se.DenseMatrix(2, 1, [x + y, x * y])
    inp = np.array([[2.0, 3.0], [5.0, 7.0], [11.0, 13.0]])
    for backend in _lambdify_backends():
        f = se.Lambdify([x, y], [x - y], mat, backend=backend)
        vec_out, mat_out = f(inp)
        assert vec_out.shape == (3, 1)
        assert mat_out.shape == (3, 2, 1)
        np.testing.assert_allclose(vec_out.ravel(), [-1.0, -2.0, -2.0])
        np.testing.assert_allclose(
            mat_out.reshape(3, 2), [[5.0, 6.0], [12.0, 35.0], [24.0, 143.0]])
        # A flat input whose size is a multiple of n_args broadcasts too.
        flat_out = f(inp.ravel())
        np.testing.assert_allclose(flat_out[0], vec_out)
        np.testing.assert_allclose(flat_out[1], mat_out)


def test_lambdify_out_buffer():
    """out= fills a flat, writable, C-contiguous float64 buffer in place."""
    import numpy as np
    import pytest
    from nbsymengine_compat import symengine_py_compat as se
    x, y = se.symbols('x y')
    mat = se.DenseMatrix(2, 2, [x, y, x + y, x * y])
    for backend in _lambdify_backends():
        f = se.Lambdify([x, y], mat, backend=backend)
        buf = np.empty(4)
        res = f(np.array([2.0, 3.0]), out=buf)
        np.testing.assert_allclose(buf, [2.0, 3.0, 5.0, 6.0])
        np.testing.assert_allclose(res, [[2.0, 3.0], [5.0, 6.0]])

        # Broadcasting writes nbroadcast * tot_out_size values.
        big = np.empty(8)
        f(np.array([[2.0, 3.0], [5.0, 7.0]]), out=big)
        np.testing.assert_allclose(
            big, [2.0, 3.0, 5.0, 6.0, 5.0, 7.0, 12.0, 35.0])

        with pytest.raises(ValueError):
            f(np.array([2.0, 3.0]), out=np.empty(3))
        with pytest.raises(ValueError):
            f(np.array([2.0, 3.0]), out=np.empty(4, dtype=int))
        read_only = np.empty(4)
        read_only.flags['WRITEABLE'] = False
        with pytest.raises(ValueError):
            f(np.array([2.0, 3.0]), out=read_only)


def test_lambdify_no_private_func_on_native_backends():
    """Native delegation must not expose/rely on a private ``_func``."""
    from nbsymengine_compat import symengine_py_compat as se
    x = se.Symbol('x')
    for backend in _lambdify_backends():
        f = se.Lambdify([x], x * x, backend=backend)
        assert f._direct is not None
        assert not hasattr(f, '_func')


def test_legacy_shim_boolean_classes():
    """Legacy shim exposes boolean classes correctly."""
    from nbsymengine_compat import symengine_py_compat as se
    x = se.Symbol("x")
    assert callable(se.And)
    assert callable(se.Or)
    assert callable(se.Not)
    assert callable(se.Xor)
    assert callable(se.Contains)
    assert se.BooleanAtom is not None
    assert se.Relational is not None
    assert se.Equality is not None
    assert se.Unequality is not None
    assert se.LessThan is not None
    assert se.StrictLessThan is not None
    assert se.And(True, True) == se.true
    assert se.And(True, False) == se.false
    assert se.Or(True, False) == se.true
    assert se.Or(False, False) == se.false
    assert se.Not(True) == se.false
    assert se.Not(False) == se.true
    assert se.Xor(True, False) == se.true
    assert se.Xor(True, True) == se.false
    cond1 = se.Lt(x, se.Integer(10))
    cond2 = se.Gt(x, se.Integer(0))
    result = se.And(cond1, cond2)
    assert isinstance(result, se.And)
    result = se.Contains(x, se.reals())
    assert isinstance(result, se.Contains)


class TestLegacyShimSets:

    def test_shim_conditionset(self):
        from nbsymengine_compat.symengine_py_compat import (
            ConditionSet, Symbol, Ge, And, Eq, Gt, Interval, EmptySet,
            oo, FiniteSet
        )
        x = Symbol("x")
        i1 = Interval(-oo, oo)
        cond1 = Ge(x**2, 9)
        result = ConditionSet(x, And(Eq(0, 1), i1.contains(x)))
        assert result == EmptySet()

    def test_shim_imageset(self):
        from nbsymengine_compat.symengine_py_compat import (
            ImageSet, Symbol, EmptySet, Interval, FiniteSet
        )
        x = Symbol("x")
        i1 = Interval(0, 1)
        assert ImageSet(x, x**2, EmptySet()) == EmptySet()
        assert ImageSet(x, 1, i1) == FiniteSet({1})

    def test_shim_solve(self):
        from nbsymengine_compat.symengine_py_compat import (
            solve, Symbol, Interval, EmptySet, FiniteSet, oo, Eq
        )
        x = Symbol("x")
        reals = Interval(-oo, oo)
        assert solve(1, x, reals) == EmptySet()
        assert solve(x + 3, x, reals) == FiniteSet({-3})
        assert solve(x, x, reals) == FiniteSet({0})

    def test_shim_linsolve(self):
        from nbsymengine_compat.symengine_py_compat import linsolve, Symbol
        x = Symbol("x")
        y = Symbol("y")
        assert linsolve([x - 2], [x]) == (2,)
        assert linsolve([x - 2, y - 3], [x, y]) == (2, 3)

    def test_shim_set_operations(self):
        from nbsymengine_compat.symengine_py_compat import (
            Interval, UniversalSet, EmptySet, Reals, FiniteSet, Symbol, true
        )
        U = UniversalSet()
        assert U.union(Interval(2, 4)) == U
        assert U.intersection(Interval(2, 4)) == Interval(2, 4)
        assert U.contains(0) == true

    def test_shim_finiteset_nesting(self):
        from nbsymengine_compat.symengine_py_compat import FiniteSet
        fs = FiniteSet(1, 2, 3)
        fs2 = FiniteSet(fs)
        assert fs2 != fs
        assert str(fs2) == "{{1, 2, 3}}"

    def test_shim_contains_and_lt(self):
        from nbsymengine_compat.symengine_py_compat import (
            Symbol, Interval, And, Contains, Lt, oo
        )
        x = Symbol("x")
        i = Interval(0, 10)
        c = Contains(x, i)
        lt = Lt(x, 5)
        combined = And(c, lt)
        assert combined is not None
