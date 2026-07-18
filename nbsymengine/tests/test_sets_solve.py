"""Direct tests for set operations, solve, and linsolve bindings."""
import pytest
from nbsymengine import _core


class TestSetInstanceMethods:

    def test_interval_union(self):
        i1 = _core.interval(_core.integer(1), _core.integer(3))
        i2 = _core.interval(_core.integer(2), _core.integer(4))
        result = i1.set_union(i2)
        assert result == _core.interval(_core.integer(1), _core.integer(4))

    def test_interval_intersection(self):
        i1 = _core.interval(_core.integer(1), _core.integer(3))
        i2 = _core.interval(_core.integer(2), _core.integer(4))
        result = i1.set_intersection(i2)
        assert result == _core.interval(_core.integer(2), _core.integer(3))

    def test_interval_complement(self):
        i1 = _core.interval(_core.integer(1), _core.integer(5))
        i2 = _core.interval(_core.integer(2), _core.integer(4))
        result = _core.set_complement(i1, i2)
        # set_complement(universe, container) = universe - container
        # [1,5] - [2,4] = [1,2) U (4,5]
        assert result != _core.emptyset()

    def test_contains_in_interval(self):
        i = _core.interval(_core.integer(0), _core.integer(10))
        result = i.contains(_core.integer(5))
        assert result == _core.true_const()

    def test_contains_not_in_interval(self):
        i = _core.interval(_core.integer(0), _core.integer(10))
        result = i.contains(_core.integer(15))
        assert result == _core.false_const()

    def test_emptyset_contains(self):
        e = _core.emptyset()
        result = e.contains(_core.integer(0))
        assert result == _core.false_const()

    def test_universalset_contains(self):
        u = _core.universalset()
        result = u.contains(_core.integer(42))
        assert result == _core.true_const()


class TestSetFreeFunctions:

    def test_set_union_of_list(self):
        i1 = _core.interval(_core.integer(1), _core.integer(2))
        i2 = _core.interval(_core.integer(3), _core.integer(4))
        result = _core.set_union([i1, i2])
        expected = _core.Union({i1, i2})
        assert result == expected

    def test_set_intersection_of_list(self):
        i1 = _core.interval(_core.integer(1), _core.integer(3))
        i2 = _core.interval(_core.integer(2), _core.integer(4))
        result = _core.set_intersection([i1, i2])
        assert result == _core.interval(_core.integer(2), _core.integer(3))

    def test_set_complement_free(self):
        u = _core.reals()
        i = _core.interval(_core.integer(0), _core.integer(1))
        result = _core.set_complement(u, i)
        assert result != _core.emptyset()


class TestConditionSet:

    def test_conditionset_basic(self):
        x = _core.symbol("x")
        cond = _core.Ge(x, _core.integer(0))
        cs = _core.conditionset(x, cond)
        assert isinstance(cs, _core.ConditionSet)

    def test_conditionset_str(self):
        x = _core.symbol("x")
        cond = _core.Gt(x, _core.integer(0))
        cs = _core.conditionset(x, cond)
        s = _core.str(cs)
        assert "x" in s


class TestImageSet:

    def test_imageset_basic(self):
        n = _core.symbol("n")
        expr = _core.mul(_core.integer(2), n)
        base = _core.integers()
        ims = _core.imageset(n, expr, base)
        assert isinstance(ims, _core.ImageSet)

    def test_imageset_empty_base(self):
        n = _core.symbol("n")
        expr = n
        base = _core.emptyset()
        result = _core.imageset(n, expr, base)
        assert result == _core.emptyset()


class TestContains:

    def test_contains_expression(self):
        x = _core.symbol("x")
        i = _core.interval(_core.integer(0), _core.integer(1))
        c = _core.contains(x, i)
        assert isinstance(c, _core.Contains)

    def test_contains_with_and(self):
        x = _core.symbol("x")
        i = _core.interval(_core.integer(0), _core.integer(10))
        c1 = _core.contains(x, i)
        c2 = _core.Gt(x, _core.integer(3))
        combined = _core.logical_and(c1, c2)
        assert isinstance(combined, _core.And)


class TestSolve:

    def test_solve_linear(self):
        x = _core.symbol("x")
        expr = _core.add(x, _core.integer(3))
        result = _core.solve(expr, x)
        assert result == _core.finiteset({_core.integer(-3)})

    def test_solve_constant_nonzero(self):
        x = _core.symbol("x")
        result = _core.solve(_core.integer(1), x)
        assert result == _core.emptyset()

    def test_solve_constant_zero(self):
        x = _core.symbol("x")
        result = _core.solve(_core.integer(0), x)
        assert result == _core.universalset()

    def test_solve_quadratic(self):
        x = _core.symbol("x")
        expr = _core.sub(_core.pow(x, _core.integer(2)), _core.integer(1))
        result = _core.solve(expr, x)
        expected = _core.finiteset({_core.integer(-1), _core.integer(1)})
        assert result == expected

    def test_solve_with_domain(self):
        x = _core.symbol("x")
        expr = _core.add(x, _core.integer(3))
        domain = _core.interval(_core.integer(0), _core.integer(100))
        result = _core.solve(expr, x, domain)
        assert result == _core.emptyset()


class TestLinsolve:

    def test_linsolve_single(self):
        x = _core.symbol("x")
        eq = _core.sub(x, _core.integer(2))
        result = _core.linsolve([eq], [x])
        assert len(result) == 1
        assert result[0] == _core.integer(2)

    def test_linsolve_two_vars(self):
        x = _core.symbol("x")
        y = _core.symbol("y")
        eq1 = _core.sub(_core.add(x, y), _core.integer(3))
        eq2 = _core.sub(_core.add(x, _core.mul(_core.integer(2), y)), _core.integer(4))
        result = _core.linsolve([eq1, eq2], [x, y])
        assert len(result) == 2
        assert result[0] == _core.integer(2)
        assert result[1] == _core.integer(1)


class TestCastToNumber:

    def test_cast_integer(self):
        x = _core.integer(42)
        result = _core.cast_to_number(x)
        assert isinstance(result, _core.Number)

    def test_cast_non_number_raises(self):
        x = _core.symbol("x")
        with pytest.raises(RuntimeError, match="Not a Number"):
            _core.cast_to_number(x)


class TestIntervalBasicOverload:

    def test_interval_with_number_args(self):
        i = _core.interval(_core.integer(0), _core.integer(1))
        assert isinstance(i, _core.Interval)

    def test_interval_with_oo(self):
        oo = _core.oo()
        i = _core.interval(_core.integer(0), oo, False, True)
        assert isinstance(i, _core.Interval)

    def test_interval_non_number_raises(self):
        x = _core.symbol("x")
        with pytest.raises(RuntimeError, match="interval arguments must be Numbers"):
            _core.interval(x, _core.integer(1))


# Legacy shim tests removed
