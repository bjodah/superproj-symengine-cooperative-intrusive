"""Tests for boolean and relational classes in nbsymengine."""
import pytest

# Compat imports removed


def test_concrete_relational_isinstance():
    """Concrete relational functions return the correct subclass."""
    from nbsymengine import _core
    x = _core.symbol("x")
    # Lt returns StrictLessThan
    result = _core.Lt(x, _core.integer(1))
    assert isinstance(result, _core.StrictLessThan)
    assert isinstance(result, _core.Relational)
    assert isinstance(result, _core.Boolean)
    assert isinstance(result, _core.Basic)
    # Le returns LessThan
    result = _core.Le(x, _core.integer(1))
    assert isinstance(result, _core.LessThan)
    assert isinstance(result, _core.Relational)
    # Gt returns StrictLessThan (canonicalized)
    result = _core.Gt(x, _core.integer(1))
    assert isinstance(result, _core.StrictLessThan)
    # Ge returns LessThan (canonicalized)
    result = _core.Ge(x, _core.integer(1))
    assert isinstance(result, _core.LessThan)
    # Eq returns Equality
    result = _core.Eq(x, _core.integer(1))
    assert isinstance(result, _core.Equality)
    assert isinstance(result, _core.Relational)
    # Ne returns Unequality
    result = _core.Ne(x, _core.integer(1))
    assert isinstance(result, _core.Unequality)
    assert isinstance(result, _core.Relational)


def test_relational_construction():
    """Relational constructors work correctly."""
    from nbsymengine import _core
    x = _core.symbol("x")
    y = _core.symbol("y")
    # Lt(x, 1)
    r = _core.Lt(x, _core.integer(1))
    assert isinstance(r, _core.StrictLessThan)
    # Ge(x, y)
    r = _core.Ge(x, y)
    assert isinstance(r, _core.LessThan)


def test_no_direct_ordering_dunders():
    """Basic does not have ordering dunders for symbolic construction."""
    from nbsymengine import _core
    x = _core.symbol("x")
    # Direct comparison should return NotImplemented or bool, not a Relational
    result = x.__lt__(_core.integer(1))
    # Should return NotImplemented (no __lt__ on Basic in direct mode)
    assert result is NotImplemented


def test_logical_and():
    """And canonicalizes correctly."""
    from nbsymengine import _core
    x = _core.symbol("x")
    cond1 = _core.Lt(x, _core.integer(10))
    cond2 = _core.Gt(x, _core.integer(0))
    result = _core.logical_and(cond1, cond2)
    assert isinstance(result, _core.And)
    assert isinstance(result, _core.Boolean)
    s = str(result)
    # Should contain both conditions
    assert "x" in s


def test_logical_or():
    """Or canonicalizes correctly."""
    from nbsymengine import _core
    x = _core.symbol("x")
    cond1 = _core.Lt(x, _core.integer(1))
    cond2 = _core.Gt(x, _core.integer(10))
    result = _core.logical_or(cond1, cond2)
    assert isinstance(result, _core.Or)
    assert isinstance(result, _core.Boolean)


def test_logical_not():
    """Not canonicalizes correctly."""
    from nbsymengine import _core
    x = _core.symbol("x")
    cond = _core.Lt(x, _core.integer(1))
    result = _core.logical_not(cond)
    # SymEngine canonicalizes Not(Lt(x,1)) to Le(1,x), so result is a LessThan
    assert isinstance(result, _core.Boolean)
    # Also test with a condition that doesn't simplify away
    cond2 = _core.contains(x, _core.reals())
    result2 = _core.logical_not(cond2)
    assert isinstance(result2, _core.Not)
    assert isinstance(result2, _core.Boolean)


def test_logical_xor():
    """Xor canonicalizes correctly."""
    from nbsymengine import _core
    x = _core.symbol("x")
    cond1 = _core.Lt(x, _core.integer(1))
    cond2 = _core.Gt(x, _core.integer(10))
    result = _core.logical_xor(cond1, cond2)
    assert isinstance(result, _core.Xor)
    assert isinstance(result, _core.Boolean)


def test_contains():
    """Contains works correctly."""
    from nbsymengine import _core
    x = _core.symbol("x")
    s = _core.reals()
    result = _core.contains(x, s)
    assert isinstance(result, _core.Contains)
    assert isinstance(result, _core.Boolean)


def test_boolean_singletons():
    """Boolean singletons have correct identity."""
    from nbsymengine import _core
    t = _core.true_const()
    f = _core.false_const()
    assert isinstance(t, _core.BooleanAtom)
    assert isinstance(f, _core.BooleanAtom)
    assert isinstance(t, _core.Boolean)
    assert isinstance(f, _core.Boolean)
    # Identity
    assert _core.same_object(t, _core.true_const())
    assert _core.same_object(f, _core.false_const())
    # Values
    assert str(t) == "True"
    assert str(f) == "False"


def test_boolean_atom_values():
    """BooleanAtom has correct values."""
    from nbsymengine import _core
    t = _core.true_const()
    f = _core.false_const()
    # True and False are different
    assert not _core.same_object(t, f)


# Legacy shim tests removed
