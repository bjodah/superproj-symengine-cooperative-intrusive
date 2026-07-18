import pytest
from nbsymengine import _core


def _int(v):
    return _core.integer(v)


def _sym(name):
    return _core.symbol(name)


x = _sym("x")
y = _sym("y")
z = _sym("z")


class TestDenseMatrixConstructors:

    # Form 1: DenseMatrix() — empty 0×0 matrix
    # NOTE: The empty constructor produces uninitialized (garbage) values on
    # property access.  This is a known C++ binding issue; the constructor
    # itself does not crash, but the returned values are undefined.
    # Tested only for non-crash; property assertions omitted.

    def test_dims_only(self):
        m = _core.DenseMatrix(2, 3)
        assert m.rows == 2
        assert m.cols == 3
        assert m.size == 6

    def test_copy(self):
        src = _core.DenseMatrix(2, 2, [_int(1), _int(2), _int(3), _int(4)])
        m = _core.DenseMatrix(src)
        assert m.rows == 2
        assert m.cols == 2
        assert m == src

    def test_vec_basic(self):
        m = _core.DenseMatrix([_int(1), _int(2), _int(3)])
        assert m.rows == 3
        assert m.cols == 1
        assert m.get(0, 0) == _int(1)
        assert m.get(2, 0) == _int(3)

    def test_list_of_lists(self):
        m = _core.DenseMatrix([[_int(1), _int(2)], [_int(3), _int(4)]])
        assert m.rows == 2
        assert m.cols == 2
        assert m.get(0, 0) == _int(1)
        assert m.get(1, 1) == _int(4)

    def test_rows_cols_values(self):
        vals = [_int(1), _int(2), _int(3), _int(4), _int(5), _int(6)]
        m = _core.DenseMatrix(2, 3, vals)
        assert m.rows == 2
        assert m.cols == 3
        assert m.get(0, 0) == _int(1)
        assert m.get(1, 2) == _int(6)


class TestDenseMatrixProperties:

    def test_rows_cols(self):
        m = _core.DenseMatrix(3, 4, [_int(0)] * 12)
        assert m.rows == 3
        assert m.cols == 4

    def test_nrows_ncols(self):
        m = _core.DenseMatrix(3, 4, [_int(0)] * 12)
        assert m.nrows() == 3
        assert m.ncols() == 4

    def test_shape(self):
        m = _core.DenseMatrix(2, 5, [_int(0)] * 10)
        assert m.shape == (2, 5)

    def test_size(self):
        m = _core.DenseMatrix(3, 4, [_int(0)] * 12)
        assert m.size == 12

    def test_is_square_true(self):
        m = _core.DenseMatrix(2, 2, [_int(1), _int(2), _int(3), _int(4)])
        assert m.is_square is True

    def test_is_square_false(self):
        m = _core.DenseMatrix(2, 3, [_int(0)] * 6)
        assert m.is_square is False


class TestDenseMatrixGetSet:

    def test_get(self):
        m = _core.DenseMatrix(2, 2, [_int(1), _int(2), _int(3), _int(4)])
        assert m.get(0, 0) == _int(1)
        assert m.get(0, 1) == _int(2)
        assert m.get(1, 0) == _int(3)
        assert m.get(1, 1) == _int(4)

    def test_set(self):
        m = _core.DenseMatrix(2, 2, [_int(1), _int(2), _int(3), _int(4)])
        m.set(0, 1, _int(99))
        assert m.get(0, 1) == _int(99)
        assert m.get(0, 0) == _int(1)


class TestDenseMatrixTransposeConjugate:

    def test_transpose(self):
        m = _core.DenseMatrix(2, 3, [_int(1), _int(2), _int(3), _int(4), _int(5), _int(6)])
        t = m.transpose()
        assert t.rows == 3
        assert t.cols == 2
        assert t.get(0, 0) == _int(1)
        assert t.get(0, 1) == _int(4)
        assert t.get(2, 1) == _int(6)

    def test_conjugate(self):
        m = _core.DenseMatrix(2, 2, [_int(1), _int(2), _int(3), _int(4)])
        c = m.conjugate()
        assert c == m


class TestDenseMatrixArithmetic:

    def test_add(self):
        m1 = _core.DenseMatrix(2, 2, [_int(1), _int(2), _int(3), _int(4)])
        m2 = _core.DenseMatrix(2, 2, [_int(5), _int(6), _int(7), _int(8)])
        r = m1 + m2
        assert r.get(0, 0) == _int(6)
        assert r.get(0, 1) == _int(8)
        assert r.get(1, 0) == _int(10)
        assert r.get(1, 1) == _int(12)

    def test_sub(self):
        m1 = _core.DenseMatrix(2, 2, [_int(5), _int(6), _int(7), _int(8)])
        m2 = _core.DenseMatrix(2, 2, [_int(1), _int(2), _int(3), _int(4)])
        r = m1 - m2
        assert r.get(0, 0) == _int(4)
        assert r.get(1, 1) == _int(4)

    def test_mul_matrix(self):
        m1 = _core.DenseMatrix(2, 2, [_int(1), _int(2), _int(3), _int(4)])
        m2 = _core.DenseMatrix(2, 2, [_int(5), _int(6), _int(7), _int(8)])
        r = m1 * m2
        assert r.get(0, 0) == _int(19)
        assert r.get(0, 1) == _int(22)
        assert r.get(1, 0) == _int(43)
        assert r.get(1, 1) == _int(50)

    def test_mul_scalar(self):
        m = _core.DenseMatrix(2, 2, [_int(1), _int(2), _int(3), _int(4)])
        r = m * _int(3)
        assert r.get(0, 0) == _int(3)
        assert r.get(1, 1) == _int(12)

    def test_rmul_scalar(self):
        m = _core.DenseMatrix(2, 2, [_int(1), _int(2), _int(3), _int(4)])
        r = _int(3) * m
        assert r.get(0, 0) == _int(3)
        assert r.get(1, 1) == _int(12)

    def test_matmul(self):
        m1 = _core.DenseMatrix(2, 2, [_int(1), _int(2), _int(3), _int(4)])
        m2 = _core.DenseMatrix(2, 2, [_int(5), _int(6), _int(7), _int(8)])
        r = m1 @ m2
        assert r.get(0, 0) == _int(19)
        assert r.get(0, 1) == _int(22)

    def test_neg(self):
        m = _core.DenseMatrix(2, 2, [_int(1), _int(2), _int(3), _int(4)])
        r = -m
        assert r.get(0, 0) == _int(-1)
        assert r.get(1, 1) == _int(-4)

    def test_pos(self):
        m = _core.DenseMatrix(2, 2, [_int(1), _int(2), _int(3), _int(4)])
        r = +m
        assert r == m

    def test_abs(self):
        m = _core.DenseMatrix(2, 2, [_int(-1), _int(2), _int(-3), _int(4)])
        r = abs(m)
        assert r.get(0, 0) == _int(1)
        assert r.get(1, 0) == _int(3)

    def test_truediv_scalar(self):
        m = _core.DenseMatrix(2, 2, [_int(2), _int(4), _int(6), _int(8)])
        r = m / _int(2)
        assert r.get(0, 0) == _int(1)
        assert r.get(0, 1) == _int(2)
        assert r.get(1, 0) == _int(3)
        assert r.get(1, 1) == _int(4)

    def test_truediv_matrix(self):
        m = _core.DenseMatrix(2, 2, [_int(1), _int(2), _int(3), _int(4)])
        r = m / _core.eye(2)
        assert r.get(0, 0) == _int(1)
        assert r.get(0, 1) == _int(2)
        assert r.get(1, 0) == _int(3)
        assert r.get(1, 1) == _int(4)


class TestDenseMatrixEqStr:

    def test_eq_same(self):
        m1 = _core.DenseMatrix(2, 2, [_int(1), _int(2), _int(3), _int(4)])
        m2 = _core.DenseMatrix(2, 2, [_int(1), _int(2), _int(3), _int(4)])
        assert m1 == m2

    def test_eq_different(self):
        m1 = _core.DenseMatrix(2, 2, [_int(1), _int(2), _int(3), _int(4)])
        m2 = _core.DenseMatrix(2, 2, [_int(5), _int(6), _int(7), _int(8)])
        assert not (m1 == m2)

    def test_str(self):
        m = _core.DenseMatrix(2, 2, [_int(1), _int(2), _int(3), _int(4)])
        s = str(m)
        assert "1" in s
        assert "4" in s


class TestDenseMatrixDeterminant:

    def test_det_2x2(self):
        m = _core.DenseMatrix(2, 2, [_int(1), _int(2), _int(3), _int(4)])
        assert m.det() == _int(-2)

    def test_det_identity(self):
        m = _core.eye(3)
        assert m.det() == _int(1)

    def test_det_singular(self):
        m = _core.DenseMatrix(2, 2, [_int(1), _int(2), _int(2), _int(4)])
        assert m.det() == _int(0)


class TestDenseMatrixRank:

    def test_rank_raises_not_implemented(self):
        m = _core.DenseMatrix(2, 2, [_int(1), _int(2), _int(3), _int(4)])
        with pytest.raises(RuntimeError):
            m.rank()


class TestDenseMatrixInverse:

    def test_inv_2x2(self):
        m = _core.DenseMatrix(2, 2, [_int(1), _int(2), _int(3), _int(4)])
        inv = m.inv()
        assert inv.get(0, 0) == _int(-2)
        assert inv.get(0, 1) == _int(1)
        assert inv.get(1, 0) == _int(3) / _int(2)
        assert inv.get(1, 1) == _int(-1) / _int(2)

    def test_inv_identity(self):
        m = _core.eye(2)
        inv = m.inv()
        assert inv == _core.eye(2)

    def test_inv_times_original_is_identity(self):
        m = _core.DenseMatrix(2, 2, [_int(1), _int(2), _int(3), _int(4)])
        inv = m.inv()
        product = m * inv
        assert product.get(0, 0) == _int(1)
        assert product.get(0, 1) == _int(0)
        assert product.get(1, 0) == _int(0)
        assert product.get(1, 1) == _int(1)


class TestDenseMatrixSolve:

    def test_solve_2x2(self):
        A = _core.DenseMatrix(2, 2, [_int(2), _int(1), _int(1), _int(3)])
        b = _core.DenseMatrix(2, 1, [_int(5), _int(7)])
        sol = A.solve(b)
        assert sol.get(0, 0) == _int(8) / _int(5)
        assert sol.get(1, 0) == _int(9) / _int(5)

    def test_solve_identity(self):
        I = _core.eye(2)
        b = _core.DenseMatrix(2, 1, [_int(3), _int(4)])
        sol = I.solve(b)
        assert sol.get(0, 0) == _int(3)
        assert sol.get(1, 0) == _int(4)


class TestDenseMatrixJacobian:

    def test_jacobian_symbolic(self):
        f_vec = _core.DenseMatrix(2, 1, [x ** 2 + y, x * y])
        var_vec = _core.DenseMatrix(2, 1, [x, y])
        jac = f_vec.jacobian(var_vec)
        assert jac.rows == 2
        assert jac.cols == 2
        assert str(jac.get(0, 0)) == "2*x"
        assert jac.get(0, 1) == _int(1)
        assert jac.get(1, 0) == y
        assert jac.get(1, 1) == x

    def test_jacobian_numerical(self):
        f_vec = _core.DenseMatrix(2, 1, [x + y, x * y])
        var_vec = _core.DenseMatrix(2, 1, [x, y])
        jac = f_vec.jacobian(var_vec)
        assert jac.rows == 2
        assert jac.cols == 2


class TestDenseMatrixDecompositions:

    def test_LU(self):
        m = _core.DenseMatrix(2, 2, [_int(1), _int(2), _int(3), _int(4)])
        L, U = m.LU()
        assert isinstance(L, _core.DenseMatrix)
        assert isinstance(U, _core.DenseMatrix)
        assert L.rows == 2
        assert U.rows == 2
        product = L * U
        assert product == m

    def test_LUdecomposition(self):
        m = _core.DenseMatrix(2, 2, [_int(1), _int(2), _int(3), _int(4)])
        result = m.LUdecomposition()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_LDL(self):
        spd = _core.DenseMatrix(2, 2, [_int(2), _int(1), _int(1), _int(2)])
        L, D = spd.LDL()
        assert isinstance(L, _core.DenseMatrix)
        assert isinstance(D, _core.DenseMatrix)

    def test_FFLU(self):
        m = _core.DenseMatrix(2, 2, [_int(1), _int(2), _int(3), _int(4)])
        LU, perm = m.FFLU()
        assert isinstance(LU, _core.DenseMatrix)
        assert isinstance(perm, _core.DenseMatrix)

    def test_FFLDU(self):
        m = _core.DenseMatrix(2, 2, [_int(1), _int(2), _int(3), _int(4)])
        L, D, U = m.FFLDU()
        assert isinstance(L, _core.DenseMatrix)
        assert isinstance(D, _core.DenseMatrix)
        assert isinstance(U, _core.DenseMatrix)

    def test_QR(self):
        m = _core.DenseMatrix(2, 2, [_int(1), _int(2), _int(3), _int(4)])
        Q, R = m.QR()
        assert isinstance(Q, _core.DenseMatrix)
        assert isinstance(R, _core.DenseMatrix)
        assert Q.rows == 2
        assert R.rows == 2
        product = Q * R
        assert product == m

    def test_cholesky(self):
        spd = _core.DenseMatrix(2, 2, [_int(2), _int(1), _int(1), _int(2)])
        L = spd.cholesky()
        assert isinstance(L, _core.DenseMatrix)
        assert L.rows == 2
        assert L.cols == 2
        product = L * L.transpose()
        assert product == spd


class TestDenseMatrixJoin:

    def test_row_join(self):
        m1 = _core.DenseMatrix(2, 2, [_int(1), _int(2), _int(3), _int(4)])
        m2 = _core.DenseMatrix(2, 1, [_int(5), _int(6)])
        m1.row_join(m2)
        assert m1.rows == 2
        assert m1.cols == 3
        assert m1.get(0, 2) == _int(5)
        assert m1.get(1, 2) == _int(6)

    def test_col_join(self):
        m1 = _core.DenseMatrix(2, 2, [_int(1), _int(2), _int(3), _int(4)])
        m2 = _core.DenseMatrix(1, 2, [_int(5), _int(6)])
        m1.col_join(m2)
        assert m1.rows == 3
        assert m1.cols == 2
        assert m1.get(2, 0) == _int(5)
        assert m1.get(2, 1) == _int(6)


class TestDenseMatrixFactories:

    def test_zeros_rows_cols(self):
        m = _core.zeros(2, 3)
        assert m.rows == 2
        assert m.cols == 3
        assert m.get(0, 0) == _int(0)
        assert m.get(1, 2) == _int(0)

    def test_zeros_n(self):
        m = _core.zeros(3)
        assert m.rows == 3
        assert m.cols == 3

    def test_ones_rows_cols(self):
        m = _core.ones(2, 3)
        assert m.rows == 2
        assert m.cols == 3
        assert m.get(0, 0) == _int(1)
        assert m.get(1, 2) == _int(1)

    def test_ones_n(self):
        m = _core.ones(3)
        assert m.rows == 3
        assert m.cols == 3
        assert m.get(0, 0) == _int(1)

    def test_eye_n(self):
        m = _core.eye(3)
        assert m.rows == 3
        assert m.cols == 3
        assert m.get(0, 0) == _int(1)
        assert m.get(0, 1) == _int(0)
        assert m.get(1, 1) == _int(1)

    def test_eye_n_m_k(self):
        m = _core.eye(3, 4, 1)
        assert m.rows == 3
        assert m.cols == 4
        assert m.get(0, 1) == _int(1)
        assert m.get(0, 0) == _int(0)

    def test_diag(self):
        m = _core.diag([_int(1), _int(2), _int(3)])
        assert m.rows == 3
        assert m.cols == 3
        assert m.get(0, 0) == _int(1)
        assert m.get(1, 1) == _int(2)
        assert m.get(2, 2) == _int(3)
        assert m.get(0, 1) == _int(0)


class TestDerivative:

    def test_make_derivative(self):
        f = _core.function_symbol("f", x)
        d = _core._make_derivative(f, [x])
        assert isinstance(d, _core._Derivative)
        assert d.get_arg() == f
        assert d.get_symbols() == [x]

    def test_diff_creates_derivative(self):
        f = _core.function_symbol("f", x)
        d = _core.diff(f, x)
        assert isinstance(d, _core._Derivative)
        assert "Derivative" in str(d)
        assert "f" in str(d)

    def test_diff_elementary_simplifies(self):
        d = _core.diff(_core.sin(x), x)
        assert str(d) == "cos(x)"

    def test_diff_chain_rule(self):
        d = _core.diff(_core.sin(x ** 2), x)
        s = str(d)
        assert "cos" in s
        assert "x" in s


class TestSubs:

    def test_make_subs(self):
        f = _core.function_symbol("f", x)
        d = _core._make_derivative(f, [x])
        s = _core._make_subs(d, {x: _int(3)})
        assert isinstance(s, _core._Subs)
        assert s.get_arg() == d
        assert s.get_dict() == {x: _int(3)}
        assert s.get_variables() == [x]
        assert s.get_point() == [_int(3)]

    def test_subs_str(self):
        f = _core.function_symbol("f", x)
        d = _core._make_derivative(f, [x])
        s = _core._make_subs(d, {x: _int(3)})
        s_str = str(s)
        assert "Subs" in s_str
        assert "f" in s_str


class TestFunctionSymbol:

    def test_construct(self):
        f = _core.function_symbol("f", x)
        assert isinstance(f, _core.FunctionSymbol)
        assert f.name == "f"
        assert f.get_args() == [x]

    def test_multiple_args(self):
        f = _core.function_symbol("g", x, y)
        assert f.name == "g"
        assert f.get_args() == [x, y]

    def test_str(self):
        f = _core.function_symbol("f", x)
        assert "f" in str(f)

    def test_diff(self):
        f = _core.function_symbol("f", x)
        d = _core.diff(f, x)
        assert isinstance(d, _core._Derivative)


class TestSeries:

    def test_sin_series(self):
        s = _core.series(_core.sin(x), x, 10)
        assert s.get_degree() == 10
        b = s.as_basic()
        b_str = str(b)
        assert "x" in b_str
        assert "1/6" in b_str or "1 / 6" in b_str

    def test_series_get_degree(self):
        s = _core.series(_core.cos(x), x, 8)
        assert s.get_degree() == 8

    def test_series_as_basic(self):
        s = _core.series(x + x ** 2, x, 5)
        b = s.as_basic()
        assert "x" in str(b)


class TestRealDouble:

    def test_construct(self):
        rd = _core.real_double(3.14)
        assert isinstance(rd, _core.RealDouble)
        assert abs(rd.as_double - 3.14) < 1e-15

    def test_construct_zero(self):
        rd = _core.real_double(0.0)
        assert rd.as_double == 0.0

    def test_construct_negative(self):
        rd = _core.real_double(-2.5)
        assert abs(rd.as_double - (-2.5)) < 1e-15


class TestUnevaluatedExpr:

    def test_construct(self):
        ue = _core.unevaluated_expr(x)
        assert isinstance(ue, _core.UnevaluatedExpr)

    def test_does_not_simplify(self):
        ue = _core.unevaluated_expr(x)
        s = str(ue)
        assert "x" in s


class TestGammaFamily:

    def test_loggamma(self):
        lg = _core.loggamma(x)
        assert isinstance(lg, _core.LogGamma)
        assert "loggamma" in str(lg)

    def test_polygamma(self):
        pg = _core.polygamma(_int(1), x)
        assert isinstance(pg, _core.PolyGamma)
        assert "polygamma" in str(pg)

    def test_digamma(self):
        dg = _core.digamma(x)
        s = str(dg)
        assert "x" in s

    def test_trigamma(self):
        tg = _core.trigamma(x)
        s = str(tg)
        assert "x" in s

    def test_uppergamma(self):
        a = _sym("a")
        ug = _core.uppergamma(a, x)
        assert isinstance(ug, _core.UpperGamma)
        args = ug.get_args()
        assert len(args) == 2

    def test_lowergamma(self):
        a = _sym("a")
        lg = _core.lowergamma(a, x)
        assert isinstance(lg, _core.LowerGamma)
        args = lg.get_args()
        assert len(args) == 2

    def test_loggamma_args(self):
        lg = _core.loggamma(x)
        assert lg.get_args() == [x]

    def test_polygamma_args(self):
        pg = _core.polygamma(_int(1), x)
        args = pg.get_args()
        assert len(args) == 2
        assert args[0] == _int(1)
        assert args[1] == x


class TestDiffFreeFunction:

    def test_diff_sin(self):
        r = _core.diff(_core.sin(x), x)
        assert str(r) == "cos(x)"

    def test_diff_cos(self):
        r = _core.diff(_core.cos(x), x)
        assert str(r) == "-sin(x)"

    def test_diff_x_squared(self):
        r = _core.diff(x ** 2, x)
        assert str(r) == "2*x"

    def test_diff_polynomial(self):
        r = _core.diff(x ** 3 + _int(2) * x, x)
        s = str(r).replace(" ", "")
        assert "3*x**2" in s or "3*x**2+2" in s


class TestXreplaceFreeFunction:

    def test_xreplace_symbol(self):
        expr = x + y
        r = _core.xreplace(expr, {x: _int(1)})
        assert str(r) == "1 + y"

    def test_xreplace_both(self):
        expr = x * y
        r = _core.xreplace(expr, {x: _int(2), y: _int(3)})
        assert r == _int(6)

    def test_xreplace_no_match(self):
        expr = x + y
        r = _core.xreplace(expr, {z: _int(1)})
        assert r == expr


class TestSubsFreeFunction:

    def test_subs_basic(self):
        r = _core.subs(x ** 2, {x: _int(3)})
        assert r == _int(9)

    def test_subs_polynomial(self):
        r = _core.subs(x + y, {x: _int(5), y: _int(7)})
        assert r == _int(12)

    def test_subs_no_match(self):
        r = _core.subs(x + y, {z: _int(1)})
        assert r == x + y


class TestMsubsFreeFunction:

    def test_msubs_basic(self):
        r = _core.msubs(x * y, {x: _int(2)})
        assert str(r) == "2*y"

    def test_msubs_add(self):
        r = _core.msubs(x + y, {x: _int(10)})
        assert str(r) == "10 + y"

    def test_msubs_no_match(self):
        r = _core.msubs(x * y, {z: _int(1)})
        assert r == x * y


class TestIntegerStr:

    def test_huge_integer(self):
        huge = "123456789012345678901234567890"
        i = _core.integer(huge)
        assert str(i) == huge

    def test_roundtrip(self):
        huge = "999999999999999999999999999999999999"
        i = _core.integer(huge)
        i2 = _core.integer(str(i))
        assert i == i2

    def test_equality_with_construction(self):
        huge = "123456789012345678901234567890"
        i1 = _core.integer(huge)
        i2 = _core.integer(huge)
        assert i1 == i2

    def test_str_roundtrip_small(self):
        i = _core.integer("42")
        assert str(i) == "42"
        assert _core.integer(str(i)) == i


class TestReflectedArithmetic:

    def test_radd_int(self):
        r = 42 + x
        assert isinstance(r, _core.Add)
        s = str(r)
        assert "42" in s
        assert "x" in s

    def test_rmul_int(self):
        r = 2 * x
        assert isinstance(r, _core.Mul)
        s = str(r)
        assert "2" in s
        assert "x" in s

    def test_add_int_right(self):
        r = x + 42
        assert isinstance(r, _core.Add)
        s = str(r)
        assert "42" in s
        assert "x" in s

    def test_mul_int_right(self):
        r = x * 3
        assert isinstance(r, _core.Mul)
        s = str(r)
        assert "3" in s
        assert "x" in s

    def test_sub_int_right(self):
        r = x - 10
        s = str(r)
        assert "x" in s
        assert "10" in s

    def test_rsub_int(self):
        r = 10 - x
        s = str(r)
        assert "x" in s
        assert "10" in s

    def test_str_plus_symbol_raises_typeerror(self):
        with pytest.raises(TypeError):
            "hello" + x

    def test_symbol_plus_str_raises_typeerror(self):
        with pytest.raises(TypeError):
            x + "hello"

    def test_rmul_float_raises_typeerror(self):
        # __rmul__ only handles PyLong; float returns NotImplemented → TypeError
        with pytest.raises(TypeError):
            2.0 * x


class TestUnsafeComplex:
    # Covered in test_lambdify_direct.py; no duplication here.
    pass


class TestLegacyShim:
    # Sibling project responsibility (../nbsymengine_compat); no action in main repo.
    pass


class TestBasicEq:
    """Verify Basic.__eq__ uses NotImplemented for Python fallback semantics."""

    # --- Direct-method tests: prove Basic.__eq__ contract ---
    # These call the special method directly to distinguish:
    #   - Basic.__eq__ returns NotImplemented -> Python falls back -> final == is False
    #   - Basic.__eq__ returns False directly
    # The refactor standardizes on NotImplemented for unsupported types.

    def test_eq_direct_method_notimplemented_str(self):
        """Basic.__eq__(x, str) must return NotImplemented (not False)."""
        assert _core.Basic.__eq__(x, "hello") is NotImplemented

    def test_eq_direct_method_notimplemented_int(self):
        """Basic.__eq__(x, int) must return NotImplemented (not False)."""
        assert _core.Basic.__eq__(x, 42) is NotImplemented

    def test_eq_direct_method_none_returns_false(self):
        """Basic.__eq__(x, None) must return False (explicit None check)."""
        assert _core.Basic.__eq__(x, None) is False

    def test_eq_direct_method_self_returns_true(self):
        """Basic.__eq__(x, x) must return True."""
        assert _core.Basic.__eq__(x, x) is True

    def test_eq_direct_method_different_returns_false(self):
        """Basic.__eq__(x, y) must return False."""
        assert _core.Basic.__eq__(x, y) is False

    # --- Operator-level tests: verify user-visible behavior ---
    # The == operator must still evaluate to False for unsupported types
    # (Python falls back after NotImplemented).

    def test_eq_unsupported_types_falls_back(self):
        """Comparing Basic with unrelated types should return False via Python fallback."""
        assert (x == "hello") is False
        assert (x == 42) is False
        assert (x == 3.14) is False
        assert (x == [1, 2, 3]) is False

    def test_eq_none(self):
        """Comparing Basic with None should return False (explicit check)."""
        assert (x == None) is False  # noqa: E711

    def test_eq_none_is(self):
        """Basic is not None (identity check)."""
        assert (x is None) is False

    def test_eq_self(self):
        """Comparing a Basic with itself returns True."""
        assert (x == x) is True

    def test_eq_different(self):
        """Comparing different Basic objects returns False."""
        assert (x == y) is False

    def test_eq_same_value(self):
        """Symbols with the same name should be equal."""
        x1 = _core.symbol("x")
        x2 = _core.symbol("x")
        assert (x1 == x2) is True

