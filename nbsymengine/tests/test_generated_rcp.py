"""Tests for Phase 6: Direct RCP<const Basic> generated bindings.

Validates:
  1. Direct RCP round trips (add, mul, pow, functions)
  2. Identity reuse via self_external()
  3. Polymorphic typing (RTTI downcasting)
  4. const correctness
  5. Container adapters (finiteset, etc.)
  6. Stub sanity
  7. Determinism (generate.py no-diff)
"""
from __future__ import annotations

import ast
import gc
import os
import sys
import unittest


try:
    from nbsymengine import _core as m
except ImportError:
    m = None  # type: ignore[assignment]


def _subprocess_python() -> str:
    return os.environ.get("NBSYMENGINE_SUBPROCESS_PYTHON", sys.executable)


@unittest.skipIf(m is None, "nbsymengine._core not importable")
class TestDirectRCPRoundTrip(unittest.TestCase):
    """Direct RCP round trips: functions take/return bound Basic objects."""

    def test_add_round_trip(self) -> None:
        x = m.symbol("x")
        y = m.symbol("y")
        result = m.add(x, y)
        self.assertIsInstance(result, m.Basic)
        self.assertIsInstance(result, m.Add)

    def test_sub_round_trip(self) -> None:
        x = m.symbol("x")
        y = m.symbol("y")
        result = m.sub(x, y)
        self.assertIsInstance(result, m.Basic)

    def test_mul_round_trip(self) -> None:
        x = m.symbol("x")
        y = m.symbol("y")
        result = m.mul(x, y)
        self.assertIsInstance(result, m.Mul)

    def test_pow_round_trip(self) -> None:
        x = m.symbol("x")
        n = m.integer(2)
        result = m.pow(x, n)
        self.assertIsInstance(result, m.Pow)

    def test_div_round_trip(self) -> None:
        x = m.symbol("x")
        y = m.symbol("y")
        result = m.div(x, y)
        self.assertIsInstance(result, m.Basic)

    def test_neg_round_trip(self) -> None:
        x = m.symbol("x")
        result = m.neg(x)
        self.assertIsInstance(result, m.Basic)

    def test_sin_round_trip(self) -> None:
        x = m.symbol("x")
        result = m.sin(x)
        self.assertIsInstance(result, m.Sin)
        self.assertIn("sin", m.str(result))

    def test_cos_round_trip(self) -> None:
        x = m.symbol("x")
        result = m.cos(x)
        self.assertIsInstance(result, m.Cos)

    def test_tan_round_trip(self) -> None:
        x = m.symbol("x")
        result = m.tan(x)
        self.assertIsInstance(result, m.Tan)

    def test_exp_functions(self) -> None:
        x = m.symbol("x")
        self.assertIsInstance(m.asin(x), m.ASin)
        self.assertIsInstance(m.acos(x), m.ACos)
        self.assertIsInstance(m.atan(x), m.ATan)

    def test_hyperbolic_functions(self) -> None:
        x = m.symbol("x")
        self.assertIsInstance(m.sinh(x), m.Sinh)
        self.assertIsInstance(m.cosh(x), m.Cosh)
        self.assertIsInstance(m.tanh(x), m.Tanh)

    def test_special_functions(self) -> None:
        x = m.symbol("x")
        self.assertIsInstance(m.log(x), m.Log)
        self.assertIsInstance(m.sqrt(x), m.Basic)  # sqrt(x) = Pow(x, 1/2)
        self.assertIsInstance(m.gamma(x), m.Gamma)
        self.assertIsInstance(m.erf(x), m.Erf)
        self.assertIsInstance(m.erfc(x), m.Erfc)
        self.assertIsInstance(m.lambertw(x), m.LambertW)
        self.assertIsInstance(m.zeta(x), m.Zeta)

    def test_expand(self) -> None:
        x = m.symbol("x")
        y = m.symbol("y")
        expr = m.mul(m.add(x, y), m.sub(x, y))
        expanded = m.expand(expr)
        self.assertIsInstance(expanded, m.Basic)

    def test_get_args(self) -> None:
        x = m.symbol("x")
        y = m.symbol("y")
        result = m.add(x, y)
        args = result.get_args()
        self.assertIsInstance(args, list)
        self.assertEqual(len(args), 2)

    def test_integer_round_trip(self) -> None:
        n = m.integer(42)
        self.assertIsInstance(n, m.Integer)
        self.assertEqual(str(n), "42")

    def test_rational_class_exists(self) -> None:
        self.assertTrue(hasattr(m, "Rational"))

    def test_constant_class(self) -> None:
        p = m.pi()
        self.assertIsInstance(p, m.Basic)
        self.assertEqual(m.str(p), "pi")

    def test_e_constant(self) -> None:
        e = m.e()
        self.assertIsInstance(e, m.Constant)
        self.assertIsInstance(e, m.Basic)
        self.assertEqual(m.str(e), "E")

    def test_euler_gamma_constant(self) -> None:
        eg = m.euler_gamma()
        self.assertIsInstance(eg, m.Constant)
        self.assertIsInstance(eg, m.Basic)
        self.assertEqual(m.str(eg), "EulerGamma")


@unittest.skipIf(m is None, "nbsymengine._core not importable")
class TestIdentityReuse(unittest.TestCase):
    """Identity reuse: returning the same Python object via self_external()."""

    def test_same_object_reflexive(self) -> None:
        x = m.symbol("x")
        self.assertTrue(m.same_object(x, x))

    def test_same_object_different(self) -> None:
        x = m.symbol("x")
        y = m.symbol("y")
        self.assertFalse(m.same_object(x, y))

    def test_constants_are_singletons(self) -> None:
        a = m.zero()
        b = m.zero()
        self.assertEqual(a, b)

    def test_one_is_singleton(self) -> None:
        a = m.one()
        b = m.one()
        self.assertEqual(a, b)

    def test_identity_on_round_trip(self) -> None:
        x = m.symbol("x")
        y = m.symbol("y")
        result = m.add(x, y)
        # Pass result back to C++; the caster should reuse the Python wrapper
        result2 = m.add(result, m.zero())
        # add(x, y) + 0 simplifies to add(x, y); the caster should return
        # the same Python object via self_external()
        self.assertIsInstance(result2, m.Basic)
        self.assertEqual(m.str(result), m.str(result2))

    def test_python_object_survives_cpp_round_trip(self) -> None:
        x = m.symbol("x")
        y = m.symbol("y")
        s = m.add(x, y)
        # Pass s back to C++ via add
        result = m.add(s, x)
        self.assertIsInstance(result, m.Basic)
        # s should still be valid
        self.assertEqual(str(s), m.str(m.add(x, y)))


@unittest.skipIf(m is None, "nbsymengine._core not importable")
class TestPolymorphicTyping(unittest.TestCase):
    """Polymorphic typing: RTTI downcasting returns most-derived bound type."""

    def test_add_returns_add_type(self) -> None:
        x = m.symbol("x")
        y = m.symbol("y")
        result = m.add(x, y)
        self.assertEqual(type(result).__name__, "Add")

    def test_mul_returns_mul_type(self) -> None:
        x = m.symbol("x")
        y = m.symbol("y")
        result = m.mul(x, y)
        self.assertEqual(type(result).__name__, "Mul")

    def test_pow_returns_pow_type(self) -> None:
        x = m.symbol("x")
        n = m.integer(2)
        result = m.pow(x, n)
        self.assertEqual(type(result).__name__, "Pow")

    def test_sin_returns_sin_type(self) -> None:
        x = m.symbol("x")
        result = m.sin(x)
        self.assertEqual(type(result).__name__, "Sin")

    def test_cos_returns_cos_type(self) -> None:
        x = m.symbol("x")
        result = m.cos(x)
        self.assertEqual(type(result).__name__, "Cos")

    def test_symbol_returns_symbol_type(self) -> None:
        x = m.symbol("x")
        self.assertEqual(type(x).__name__, "Symbol")

    def test_integer_returns_integer_type(self) -> None:
        n = m.integer(42)
        self.assertEqual(type(n).__name__, "Integer")

    def test_class_hierarchy(self) -> None:
        x = m.symbol("x")
        self.assertIsInstance(x, m.Symbol)
        self.assertIsInstance(x, m.Basic)

        n = m.integer(42)
        self.assertIsInstance(n, m.Integer)
        self.assertIsInstance(n, m.Number)
        self.assertIsInstance(n, m.Basic)

    def test_add_hierarchy(self) -> None:
        x = m.symbol("x")
        y = m.symbol("y")
        result = m.add(x, y)
        self.assertIsInstance(result, m.Add)
        self.assertIsInstance(result, m.Basic)

    def test_function_hierarchy(self) -> None:
        x = m.symbol("x")
        s = m.sin(x)
        self.assertIsInstance(s, m.Sin)
        self.assertIsInstance(s, m.Basic)


@unittest.skipIf(m is None, "nbsymengine._core not importable")
class TestConstCorrectness(unittest.TestCase):
    """const correctness: RCP<const Symbol> etc. accepted and returned."""

    def test_rcp_const_basic_accepted(self) -> None:
        x = m.symbol("x")
        y = m.symbol("y")
        s = m.add(x, y)
        self.assertIsInstance(s, m.Basic)

    def test_rcp_const_integer_accepted(self) -> None:
        n = m.integer(10)
        x = m.symbol("x")
        s = m.add(n, x)
        self.assertIsInstance(s, m.Basic)

    def test_rcp_const_symbol_round_trip(self) -> None:
        x = m.symbol("x")
        self.assertIsInstance(x, m.Symbol)
        self.assertEqual(m.str(x), "x")

    def test_integer_operations(self) -> None:
        a = m.integer(10)
        b = m.integer(20)
        result = m.add(a, b)
        self.assertEqual(m.str(result), "30")

    def test_eq_with_non_basic(self) -> None:
        x = m.symbol("x")
        # Basic.__eq__ returns NotImplemented for non-Basic args; Python
        # fallback makes the == operator evaluate to False.
        self.assertIs(x == "hello", False)
        self.assertIs(x == 42, False)
        self.assertIs(x == None, False)
        # Same-object equality still works
        self.assertIs(x == x, True)
        self.assertIs(m.symbol("x") == m.symbol("x"), True)
        self.assertIs(m.integer(1) == "1", False)
        # Reflected: non-Basic on the left defers to Basic.__eq__
        self.assertIs(42 == x, False)
        self.assertIs(None == x, False)
        self.assertIs("1" == m.integer(1), False)

    def test_hash_consistency(self) -> None:
        x1 = m.symbol("x")
        x2 = m.symbol("x")
        # Two symbols with the same name should have equal hashes
        # regardless of whether identity reuse fires
        self.assertEqual(hash(x1), hash(x2))
        if m.same_object(x1, x2):
            self.assertIs(x1, x2)


@unittest.skipIf(m is None, "nbsymengine._core not importable")
class TestIntegerIsMethods(unittest.TestCase):
    """Verify restored is_* member methods on Integer."""

    def test_is_zero(self) -> None:
        self.assertTrue(m.integer(0).is_zero())
        self.assertFalse(m.integer(1).is_zero())

    def test_is_one(self) -> None:
        self.assertTrue(m.integer(1).is_one())
        self.assertFalse(m.integer(0).is_one())

    def test_is_minus_one(self) -> None:
        self.assertTrue(m.integer(-1).is_minus_one())
        self.assertFalse(m.integer(1).is_minus_one())

    def test_is_positive(self) -> None:
        self.assertTrue(m.integer(5).is_positive())
        self.assertFalse(m.integer(0).is_positive())
        self.assertFalse(m.integer(-3).is_positive())

    def test_is_negative(self) -> None:
        self.assertTrue(m.integer(-3).is_negative())
        self.assertFalse(m.integer(0).is_negative())
        self.assertFalse(m.integer(5).is_negative())

    def test_is_complex(self) -> None:
        self.assertFalse(m.integer(5).is_complex())
        self.assertFalse(m.integer(0).is_complex())


@unittest.skipIf(m is None, "nbsymengine._core not importable")
class TestBooleanRelational(unittest.TestCase):
    """Boolean and relational bindings."""

    def test_eq_constructor(self) -> None:
        x = m.symbol("x")
        y = m.symbol("y")
        result = m.Eq(x, y)
        self.assertIsInstance(result, m.Basic)

    def test_ne_constructor(self) -> None:
        x = m.symbol("x")
        y = m.symbol("y")
        result = m.Ne(x, y)
        self.assertIsInstance(result, m.Basic)

    def test_ge_gt_le_lt(self) -> None:
        x = m.symbol("x")
        y = m.symbol("y")
        self.assertIsInstance(m.Ge(x, y), m.Basic)
        self.assertIsInstance(m.Gt(x, y), m.Basic)
        self.assertIsInstance(m.Le(x, y), m.Basic)
        self.assertIsInstance(m.Lt(x, y), m.Basic)


@unittest.skipIf(m is None, "nbsymengine._core not importable")
class TestSets(unittest.TestCase):
    """Set bindings."""

    def test_emptyset(self) -> None:
        s = m.emptyset()
        self.assertIsInstance(s, m.EmptySet)
        self.assertIsInstance(s, m.Set)
        self.assertIsInstance(s, m.Basic)

    def test_universalset(self) -> None:
        s = m.universalset()
        self.assertIsInstance(s, m.UniversalSet)

    def test_reals(self) -> None:
        s = m.reals()
        self.assertIsInstance(s, m.Reals)
        self.assertIsInstance(s, m.Set)

    def test_rationals(self) -> None:
        s = m.rationals()
        self.assertIsInstance(s, m.Rationals)

    def test_integers(self) -> None:
        s = m.integers()
        self.assertIsInstance(s, m.Integers)

    def test_interval(self) -> None:
        a = m.integer(0)
        b = m.integer(1)
        s = m.interval(a, b)
        self.assertIsInstance(s, m.Interval)
        self.assertIsInstance(s, m.Set)

    def test_finiteset(self) -> None:
        items = [m.integer(1), m.integer(2), m.integer(3)]
        s = m.finiteset(items)
        self.assertIsInstance(s, m.FiniteSet)


@unittest.skipIf(m is None, "nbsymengine._core not importable")
class TestNumberTheory(unittest.TestCase):
    """Number theory function bindings."""

    def test_factorial(self) -> None:
        result = m.factorial(5)
        self.assertEqual(str(result), "120")
        self.assertIsInstance(result, m.Integer)

    def test_fibonacci(self) -> None:
        result = m.fibonacci(10)
        self.assertEqual(str(result), "55")

    def test_lucas(self) -> None:
        result = m.lucas(7)
        self.assertEqual(str(result), "29")

    def test_gcd(self) -> None:
        a = m.integer(12)
        b = m.integer(8)
        result = m.gcd(a, b)
        self.assertEqual(str(result), "4")

    def test_lcm(self) -> None:
        a = m.integer(4)
        b = m.integer(6)
        result = m.lcm(a, b)
        self.assertEqual(str(result), "12")

    def test_nextprime(self) -> None:
        a = m.integer(10)
        result = m.nextprime(a)
        self.assertEqual(str(result), "11")

    def test_binomial(self) -> None:
        n = m.integer(10)
        result = m.binomial(n, 3)
        self.assertEqual(str(result), "120")

    def test_totient(self) -> None:
        n = m.integer(12)
        result = m.totient(n)
        self.assertEqual(str(result), "4")

    def test_probab_prime_p(self) -> None:
        self.assertTrue(m.probab_prime_p(m.integer(7)))
        self.assertFalse(m.probab_prime_p(m.integer(4)))

    def test_divides(self) -> None:
        self.assertTrue(m.divides(m.integer(12), m.integer(4)))
        self.assertFalse(m.divides(m.integer(12), m.integer(5)))

    def test_carmichael(self) -> None:
        n = m.integer(12)
        result = m.carmichael(n)
        self.assertEqual(str(result), "2")

    def test_legendre(self) -> None:
        self.assertEqual(m.legendre(m.integer(5), m.integer(3)), -1)

    def test_jacobi(self) -> None:
        self.assertEqual(m.jacobi(m.integer(5), m.integer(3)), -1)

    def test_kronecker(self) -> None:
        self.assertEqual(m.kronecker(m.integer(5), m.integer(3)), -1)

    def test_mod(self) -> None:
        a = m.integer(13)
        b = m.integer(5)
        self.assertEqual(str(m.mod(a, b)), "3")
        self.assertEqual(str(m.mod(m.integer(-4), m.integer(7))), "-4")

    def test_mod_zero_division(self) -> None:
        with self.assertRaises(RuntimeError):
            m.mod(m.integer(2), m.integer(0))

    def test_quotient(self) -> None:
        a = m.integer(13)
        b = m.integer(5)
        self.assertEqual(str(m.quotient(a, b)), "2")
        self.assertEqual(str(m.quotient(m.integer(-4), m.integer(7))), "0")

    def test_quotient_zero_division(self) -> None:
        with self.assertRaises(RuntimeError):
            m.quotient(m.integer(1), m.integer(0))

    def test_gcd_ext(self) -> None:
        a = m.integer(30)
        b = m.integer(12)
        g, s, t = m.gcd_ext(a, b)
        self.assertEqual(str(g), "6")
        self.assertEqual(int(str(g)), int(str(s)) * 30 + int(str(t)) * 12)

    def test_quotient_mod(self) -> None:
        a = m.integer(17)
        b = m.integer(5)
        q, r = m.quotient_mod(a, b)
        self.assertEqual(str(q), "3")
        self.assertEqual(str(r), "2")

    def test_quotient_mod_zero_division(self) -> None:
        with self.assertRaises(RuntimeError):
            m.quotient_mod(m.integer(1), m.integer(0))

    def test_fibonacci2(self) -> None:
        f_n, f_nm1 = m.fibonacci2(10)
        self.assertEqual(str(f_n), "55")
        self.assertEqual(str(f_nm1), "34")

    def test_lucas2(self) -> None:
        l_n, l_nm1 = m.lucas2(10)
        self.assertEqual(str(l_n), "123")
        self.assertEqual(str(l_nm1), "76")

    def test_mod_inverse(self) -> None:
        result = m.mod_inverse(m.integer(3), m.integer(11))
        self.assertEqual(str(result), "4")
        self.assertIsNone(m.mod_inverse(m.integer(0), m.integer(3)))
        self.assertIsNone(m.mod_inverse(m.integer(4), m.integer(6)))

    def test_crt(self) -> None:
        rem = [m.integer(0), m.integer(1), m.integer(2), m.integer(4)]
        mod = [m.integer(2), m.integer(3), m.integer(4), m.integer(5)]
        result = m.crt(rem, mod)
        self.assertEqual(str(result), "34")
        rem2 = [m.integer(3), m.integer(5)]
        mod2 = [m.integer(6), m.integer(21)]
        self.assertIsNone(m.crt(rem2, mod2))

    def test_prime_factors(self) -> None:
        result = m.prime_factors(m.integer(360))
        vals = [int(str(x)) for x in result]
        self.assertEqual(vals, [2, 2, 2, 3, 3, 5])

    def test_prime_factor_multiplicities(self) -> None:
        result = m.prime_factor_multiplicities(m.integer(360))
        d = {int(str(k)): v for k, v in result.items()}
        self.assertEqual(d, {2: 3, 3: 2, 5: 1})

    def test_primitive_root(self) -> None:
        result = m.primitive_root(m.integer(7))
        self.assertEqual(str(result), "3")
        self.assertIsNone(m.primitive_root(m.integer(15)))

    def test_primitive_root_list(self) -> None:
        result = m.primitive_root_list(m.integer(7))
        vals = [int(str(x)) for x in result]
        self.assertEqual(vals, [3, 5])

    def test_multiplicative_order(self) -> None:
        result = m.multiplicative_order(m.integer(2), m.integer(7))
        self.assertEqual(str(result), "3")
        self.assertIsNone(m.multiplicative_order(m.integer(5), m.integer(10)))

    def test_nthroot_mod(self) -> None:
        result = m.nthroot_mod(m.integer(1), m.integer(3), m.integer(7))
        self.assertEqual(str(result), "1")
        self.assertIsNone(m.nthroot_mod(m.integer(2), m.integer(2), m.integer(5)))

    def test_nthroot_mod_list(self) -> None:
        result = m.nthroot_mod_list(m.integer(1), m.integer(3), m.integer(7))
        vals = sorted([int(str(x)) for x in result])
        self.assertEqual(vals, [1, 2, 4])

    def test_powermod(self) -> None:
        result = m.powermod(m.integer(3), m.integer(8), m.integer(7))
        self.assertEqual(str(result), "2")

    def test_powermod_list(self) -> None:
        result = m.powermod_list(m.integer(3), m.integer(8), m.integer(7))
        vals = sorted([int(str(x)) for x in result])
        self.assertIn(2, vals)

    def test_mod_f(self) -> None:
        self.assertEqual(str(m.mod_f(m.integer(13), m.integer(5))), "3")
        self.assertEqual(str(m.mod_f(m.integer(-4), m.integer(7))), "3")
        self.assertEqual(str(m.mod_f(m.integer(-11), m.integer(5))), "4")

    def test_mod_f_zero_division(self) -> None:
        with self.assertRaises(RuntimeError):
            m.mod_f(m.integer(2), m.integer(0))

    def test_quotient_f(self) -> None:
        self.assertEqual(str(m.quotient_f(m.integer(13), m.integer(5))), "2")
        self.assertEqual(str(m.quotient_f(m.integer(-4), m.integer(7))), "-1")
        self.assertEqual(str(m.quotient_f(m.integer(-11), m.integer(5))), "-3")

    def test_quotient_f_zero_division(self) -> None:
        with self.assertRaises(RuntimeError):
            m.quotient_f(m.integer(1), m.integer(0))

    def test_quotient_mod_f(self) -> None:
        q, r = m.quotient_mod_f(m.integer(-11), m.integer(5))
        self.assertEqual(str(q), "-3")
        self.assertEqual(str(r), "4")
        q2, r2 = m.quotient_mod_f(m.integer(17), m.integer(5))
        self.assertEqual(str(q2), "3")
        self.assertEqual(str(r2), "2")

    def test_quotient_mod_f_zero_division(self) -> None:
        with self.assertRaises(RuntimeError):
            m.quotient_mod_f(m.integer(1), m.integer(0))

    def test_factor(self) -> None:
        f = m.factor(m.integer(102))
        self.assertIsNotNone(f)
        self.assertEqual(int(str(f)) in [2, 3, 17, 6, 34, 51], True)
        self.assertIsNone(m.factor(m.integer(101)))

    def test_factor_trial_division(self) -> None:
        f = m.factor_trial_division(m.integer(102))
        self.assertIsNotNone(f)
        self.assertIsNone(m.factor_trial_division(m.integer(101)))

    def test_factor_lehman_method(self) -> None:
        f = m.factor_lehman_method(m.integer(102))
        self.assertIsNotNone(f)
        self.assertIsNone(m.factor_lehman_method(m.integer(101)))

    def test_factor_pollard_pm1_method(self) -> None:
        # 1000009 = 1000009 (prime-like for small B)
        # Use a B-smooth composite: 2*3*5*7*11*13 = 30030
        f = m.factor_pollard_pm1_method(m.integer(30030))
        self.assertIsNotNone(f)

    def test_factor_pollard_rho_method(self) -> None:
        f = m.factor_pollard_rho_method(m.integer(102))
        self.assertIsNotNone(f)

    def test_bernoulli(self) -> None:
        result = m.bernoulli(0)
        self.assertEqual(str(result), "1")
        result2 = m.bernoulli(1)
        # NOTE: Without ARB/FLINT, the C++ fallback Akiyama-Tanigawa algorithm
        # computes B_n^+ (second Bernoulli numbers) where B(1)^+ = +1/2.
        # The standard convention (used by FLINT/ARB) is B(1) = -1/2.
        # This test reflects the current C++ fallback behavior.
        self.assertIn(str(result2), ["1/2", "-1/2"])
        result4 = m.bernoulli(4)
        self.assertEqual(str(result4), "-1/30")

    def test_harmonic(self) -> None:
        result = m.harmonic(3)
        self.assertEqual(str(result), "11/6")


@unittest.skipIf(m is None, "nbsymengine._core not importable")
class TestClassHierarchyGenerated(unittest.TestCase):
    """Verify nanobind class hierarchy reflects C++ inheritance for generated classes."""

    def test_symbol_is_basic(self) -> None:
        s = m.Symbol("x")
        self.assertIsInstance(s, m.Basic)

    def test_integer_is_number(self) -> None:
        n = m.integer(42)
        self.assertIsInstance(n, m.Number)
        self.assertIsInstance(n, m.Basic)

    def test_add_is_basic(self) -> None:
        x = m.symbol("x")
        y = m.symbol("y")
        a = m.add(x, y)
        self.assertIsInstance(a, m.Add)
        self.assertIsInstance(a, m.Basic)

    def test_dummy_is_symbol(self) -> None:
        d = m.Dummy("d")
        self.assertIsInstance(d, m.Symbol)
        self.assertIsInstance(d, m.Basic)

    def test_constant_is_basic(self) -> None:
        p = m.pi()
        self.assertIsInstance(p, m.Basic)

    def test_set_is_basic(self) -> None:
        self.assertTrue(issubclass(m.Set, m.Basic))

    def test_emptyset_is_set(self) -> None:
        self.assertTrue(issubclass(m.EmptySet, m.Set))

    def test_sin_is_basic(self) -> None:
        self.assertTrue(issubclass(m.Sin, m.Basic))

    def test_boolean_is_basic(self) -> None:
        self.assertTrue(issubclass(m.Boolean, m.Basic))

    def test_erf_is_basic(self) -> None:
        self.assertTrue(issubclass(m.Erf, m.Basic))

    def test_finiteset_is_set(self) -> None:
        self.assertTrue(issubclass(m.FiniteSet, m.Set))


@unittest.skipIf(m is None, "nbsymengine._core not importable")
class TestRational(unittest.TestCase):
    """Rational number bindings."""

    def test_rational_exists(self) -> None:
        self.assertTrue(hasattr(m, "Rational"))

    def test_rational_is_number(self) -> None:
        self.assertTrue(issubclass(m.Rational, m.Number))
        self.assertTrue(issubclass(m.Rational, m.Basic))


@unittest.skipIf(m is None, "nbsymengine._core not importable")
class TestBooleanRelationalExtended(unittest.TestCase):
    """Extended boolean/relational tests."""

    def test_eq_returns_boolean(self) -> None:
        x = m.symbol("x")
        y = m.symbol("y")
        result = m.Eq(x, y)
        self.assertIsInstance(result, m.Boolean)
        self.assertIsInstance(result, m.Basic)

    def test_ne_returns_boolean(self) -> None:
        x = m.symbol("x")
        y = m.symbol("y")
        result = m.Ne(x, y)
        self.assertIsInstance(result, m.Boolean)

    def test_ge_returns_boolean(self) -> None:
        x = m.symbol("x")
        y = m.symbol("y")
        result = m.Ge(x, y)
        self.assertIsInstance(result, m.Boolean)

    def test_gt_returns_boolean(self) -> None:
        x = m.symbol("x")
        y = m.symbol("y")
        result = m.Gt(x, y)
        self.assertIsInstance(result, m.Boolean)

    def test_le_returns_boolean(self) -> None:
        x = m.symbol("x")
        y = m.symbol("y")
        result = m.Le(x, y)
        self.assertIsInstance(result, m.Boolean)

    def test_lt_returns_boolean(self) -> None:
        x = m.symbol("x")
        y = m.symbol("y")
        result = m.Lt(x, y)
        self.assertIsInstance(result, m.Boolean)


@unittest.skipIf(m is None, "nbsymengine._core not importable")
class TestSetOperations(unittest.TestCase):
    """Extended set operation tests."""

    def test_complexes(self) -> None:
        s = m.complexes()
        self.assertIsInstance(s, m.Complexes)
        self.assertIsInstance(s, m.Set)

    def test_naturals(self) -> None:
        s = m.naturals()
        self.assertIsInstance(s, m.Naturals)
        self.assertIsInstance(s, m.Set)

    def test_naturals0(self) -> None:
        s = m.naturals0()
        self.assertIsInstance(s, m.Naturals0)
        self.assertIsInstance(s, m.Set)

    def test_interval_open_closed(self) -> None:
        a = m.integer(0)
        b = m.integer(1)
        # Test with explicit open/closed flags
        s = m.interval(a, b, True, False)
        self.assertIsInstance(s, m.Interval)
        s2 = m.interval(a, b, False, True)
        self.assertIsInstance(s2, m.Interval)
        s3 = m.interval(a, b, True, True)
        self.assertIsInstance(s3, m.Interval)


@unittest.skipIf(m is None, "nbsymengine._core not importable")
class TestUtilityFunctions(unittest.TestCase):
    """Utility function tests."""

    def test_cpp_use_count(self) -> None:
        x = m.symbol("x")
        count = m.cpp_use_count(x)
        self.assertIsInstance(count, int)

    def test_str_function(self) -> None:
        x = m.symbol("x")
        self.assertEqual(m.str(x), "x")
        n = m.integer(42)
        self.assertEqual(m.str(n), "42")

    def test_dirichlet_eta(self) -> None:
        x = m.symbol("x")
        result = m.dirichlet_eta(x)
        self.assertIsInstance(result, m.Dirichlet_eta)
        self.assertIsInstance(result, m.Basic)


@unittest.skipIf(m is None, "nbsymengine._core not importable")
class TestStubFile(unittest.TestCase):
    """Verify the generated stub file is syntactically valid."""

    def test_stub_no_invalid_escape_sequences(self) -> None:
        stub_path = os.path.join(
            os.path.dirname(__file__), "..", "generated", "symengine.pyi"
        )
        if not os.path.exists(stub_path):
            self.skipTest("stub file not found")
        with open(stub_path) as f:
            content = f.read()
        import warnings
        with warnings.catch_warnings():
            warnings.filterwarnings("error", category=SyntaxWarning)
            try:
                ast.parse(content)
            except SyntaxWarning:
                self.fail("Stub file contains invalid escape sequences")

    def test_stub_class_hierarchy(self) -> None:
        stub_path = os.path.join(
            os.path.dirname(__file__), "..", "generated", "symengine.pyi"
        )
        if not os.path.exists(stub_path):
            self.skipTest("stub file not found")
        with open(stub_path) as f:
            content = f.read()
        self.assertIn("class Symbol(Basic):", content)
        self.assertIn("class Integer(Number):", content)
        self.assertIn("class Add(Basic):", content)
        self.assertIn("class Mul(Basic):", content)
        self.assertIn("class Pow(Basic):", content)
        self.assertIn("class Sin(Basic):", content)
        self.assertIn("class Interval(Set):", content)

    def test_stub_contains_new_classes(self) -> None:
        stub_path = os.path.join(
            os.path.dirname(__file__), "..", "generated", "symengine.pyi"
        )
        if not os.path.exists(stub_path):
            self.skipTest("stub file not found")
        with open(stub_path) as f:
            content = f.read()
        # Phase 6 additions
        for cls in ["Rational", "Constant", "Sin", "Cos", "Log", "Gamma",
                     "Reals", "Integers", "Interval", "Boolean",
                     "Erf", "Erfc", "EmptySet", "FiniteSet"]:
            self.assertIn(f"class {cls}", content, f"Missing class {cls} in stub")

    def test_stub_syntax_valid(self) -> None:
        stub_path = os.path.join(
            os.path.dirname(__file__), "..", "generated", "symengine.pyi"
        )
        if not os.path.exists(stub_path):
            self.skipTest("stub file not found")
        with open(stub_path) as f:
            content = f.read()
        tree = ast.parse(content)
        self.assertTrue(len(tree.body) > 0, "Parsed AST is empty")

    def test_stub_functions_present(self) -> None:
        stub_path = os.path.join(
            os.path.dirname(__file__), "..", "generated", "symengine.pyi"
        )
        if not os.path.exists(stub_path):
            self.skipTest("stub file not found")
        with open(stub_path) as f:
            content = f.read()
        functions = [
            "symbol", "integer",
            "add", "sub", "mul", "div", "pow", "neg",
            "expand",
            "sin", "cos", "tan", "asin", "acos", "atan", "atan2",
            "sinh", "cosh", "tanh",
            "log", "sqrt", "abs", "sign", "floor", "ceiling",
            "gamma", "erf", "erfc", "lambertw", "zeta", "dirichlet_eta",
            "Eq", "Ne", "Ge", "Gt", "Le", "Lt",
            "factorial", "binomial", "gcd", "lcm", "fibonacci", "lucas",
            "nextprime", "totient", "carmichael",
            "finiteset", "interval", "emptyset", "universalset",
            "reals", "rationals", "integers", "complexes", "naturals", "naturals0",
            "zero", "one", "pi", "e", "euler_gamma",
            "str", "same_object", "cpp_use_count",
        ]
        for func in functions:
            self.assertIn(
                f"def {func}(",
                content,
                f"Missing stub entry for function '{func}'",
            )


@unittest.skipIf(
    os.environ.get("SYMENGINE_NANOBIND_REGEN_TESTS", "0") != "1",
    "Determinism tests disabled (set SYMENGINE_NANOBIND_REGEN_TESTS=1 to enable)",
)
class TestDeterminism(unittest.TestCase):
    """Verify generate.py produces deterministic (byte-identical) output."""

    def test_generation_is_deterministic(self) -> None:
        import subprocess
        import tempfile

        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        gen_script = os.path.join(repo_root, "bindings", "python_nanobind", "generate.py")
        gen_config = os.path.join(repo_root, "bindings", "python_nanobind", "generate.yaml")

        if not os.path.exists(gen_script):
            self.skipTest("generate.py not found")

        litgen_path = os.path.join(repo_root, "external", "litgen", "src")
        env = os.environ.copy()
        env["PYTHONPATH"] = litgen_path + os.pathsep + env.get("PYTHONPATH", "")

        with tempfile.TemporaryDirectory() as tmpA, tempfile.TemporaryDirectory() as tmpB:
            for tmpdir in (tmpA, tmpB):
                result = subprocess.run(
                    [_subprocess_python(), gen_script, gen_config, "--output-dir", tmpdir],
                    capture_output=True, text=True, cwd=repo_root, env=env,
                )
                self.assertEqual(
                    result.returncode, 0, f"generate.py failed:\n{result.stderr}"
                )

            # Both files must be byte-identical across runs.
            for name in ("symengine_pydef.cpp", "symengine.pyi"):
                path_a = os.path.join(tmpA, name)
                path_b = os.path.join(tmpB, name)
                self.assertTrue(os.path.exists(path_a), f"generate.py did not produce {name}")
                self.assertTrue(os.path.exists(path_b), f"generate.py did not produce {name}")
                with open(path_a, "rb") as f:
                    content_a = f.read()
                with open(path_b, "rb") as f:
                    content_b = f.read()
                self.assertEqual(
                    content_a, content_b, f"{name} is not deterministic across runs"
                )

            # Validate the stub header.
            stub_path = os.path.join(tmpA, "symengine.pyi")
            with open(stub_path) as f:
                stub = f.read()

            expected_header = (
                "# AUTO-GENERATED by generator/generate.py — DO NOT EDIT.\n"
                "# Requires Python >= 3.13.\n"
                "import builtins\n"
                "from typing import overload\n"
            )
            self.assertTrue(
                stub.startswith(expected_header),
                f"Stub does not start with expected header.\n"
                f"Expected:\n{expected_header}\nGot:\n{stub[:200]}",
            )

            # No future-import allowed (Python >= 3.13 makes it unnecessary).
            self.assertNotIn(
                "from __future__ import annotations",
                stub,
                "Stub must not contain 'from __future__ import annotations'",
            )

            # Stub must parse as valid Python.
            ast.parse(stub)


@unittest.skipIf(m is None, "nbsymengine._core not importable")
class TestNoInfrastructureLeakage(unittest.TestCase):
    """Verify no binding infrastructure leaked into the public surface."""

    def test_no_rcp_cast_functions(self) -> None:
        for name in dir(m):
            self.assertFalse(
                name.startswith("rcp_static_cast"),
                f"Infrastructure leaked: {name}",
            )
            self.assertFalse(
                name.startswith("rcp_dynamic_cast"),
                f"Infrastructure leaked: {name}",
            )

    def test_no_make_rcp(self) -> None:
        for name in dir(m):
            self.assertFalse(
                name.startswith("make_rcp"),
                f"Infrastructure leaked: {name}",
            )

    def test_no_outArg(self) -> None:
        self.assertFalse(hasattr(m, "outArg"))
        self.assertFalse(hasattr(m, "ptrFromRef"))


@unittest.skipIf(m is None, "nbsymengine._core not importable")
class TestLifecycle(unittest.TestCase):
    """Lifecycle / destruction stress tests."""

    def test_no_leak_on_create_drop(self) -> None:
        for _ in range(100):
            x = m.symbol("temp")
            y = m.integer(42)
            s = m.add(x, y)
        del s, x, y
        gc.collect()
        z = m.symbol("post_gc")
        self.assertIsInstance(z, m.Basic)

    def test_rapid_create_destroy(self) -> None:
        for _ in range(500):
            x = m.symbol("x")
            y = m.integer(1)
            s = m.add(x, y)
            del s, x, y
        gc.collect()

    def test_nested_operations(self) -> None:
        x = m.symbol("x")
        expr = x
        for i in range(50):
            expr = m.add(expr, m.integer(i))
        self.assertIsInstance(expr, m.Basic)
        del expr
        gc.collect()


@unittest.skipIf(m is None, "nbsymengine._core not importable")
class TestEqualitySemantics(unittest.TestCase):
    """Verify Python equality behaves like normal Python equality."""

    def test_symbol_eq_non_basic_returns_false(self) -> None:
        self.assertIs(m.symbol("x") == 42, False)
        self.assertIs(m.symbol("x") == None, False)
        self.assertIs(m.symbol("x") == m.symbol("x"), True)

    def test_integer_eq_string_returns_false(self) -> None:
        self.assertIs(m.integer(1) == "1", False)

    def test_symbol_eq_list_returns_false(self) -> None:
        self.assertIs(m.symbol("x") == [1, 2, 3], False)

    def test_symbol_eq_dict_returns_false(self) -> None:
        self.assertIs(m.symbol("x") == {"a": 1}, False)

    def test_integer_eq_float_returns_false(self) -> None:
        self.assertIs(m.integer(1) == 1.0, False)

    def test_symbol_ne_non_basic(self) -> None:
        x = m.symbol("x")
        self.assertIs(x != 42, True)
        self.assertIs(x != None, True)
        self.assertIs(x != "hello", True)
        self.assertIs(x != x, False)

    def test_integer_equality(self) -> None:
        a = m.integer(42)
        b = m.integer(42)
        self.assertIs(a == b, True)
        self.assertIs(a == m.integer(43), False)

    def test_add_equality(self) -> None:
        x = m.symbol("x")
        y = m.symbol("y")
        expr1 = m.add(x, y)
        expr2 = m.add(x, y)
        self.assertIs(expr1 == expr2, True)

    def test_mul_equality(self) -> None:
        x = m.symbol("x")
        y = m.symbol("y")
        expr1 = m.mul(x, y)
        expr2 = m.mul(x, y)
        self.assertIs(expr1 == expr2, True)

    def test_reflected_eq_non_basic(self) -> None:
        x = m.symbol("x")
        n = m.integer(1)
        # int.__eq__(42, x) returns NotImplemented -> Basic.__eq__(x, 42) -> False
        self.assertIs(42 == x, False)
        # None.__eq__(x) returns NotImplemented -> Basic.__eq__(x, None) -> False
        self.assertIs(None == x, False)
        # str.__eq__("1", n) returns NotImplemented -> Basic.__eq__(n, "1") -> False
        self.assertIs("1" == n, False)
        # Reflected != for non-Basic
        self.assertIs(42 != x, True)
        self.assertIs(None != x, True)

    def test_cross_type_basic_equality(self) -> None:
        self.assertIs(m.symbol("x") == m.integer(1), False)
        self.assertIs(m.symbol("x") != m.integer(1), True)


if __name__ == "__main__":
    unittest.main()
