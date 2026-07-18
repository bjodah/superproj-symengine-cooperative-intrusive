"""nbsymengine_compat._constants -- Singletons, constants, and feature flags."""
from __future__ import annotations

from nbsymengine import _core
from ._helpers import _sympify, HAS_SYMPY
from ._wrappers import wrap


# Constants (singleton factories)
zero = _core.zero
one = _core.one
pi_fn = _core.pi
e_fn = _core.e
euler_gamma_fn = _core.euler_gamma


# ---------------------------------------------------------------------------
# Module-level constants (singleton objects)
# ---------------------------------------------------------------------------

pi = wrap(_core.pi())
E = wrap(_core.e())
EulerGamma = wrap(_core.euler_gamma())
I = wrap(_core.I())
oo = wrap(_core.oo())
zoo = wrap(_core.zoo())
nan = _core.nan_const()

# Backward compat: type(nan)() should return nan
# Create a wrapper that behaves like nan but has a constructible type
class _NaNImpl(object):
    def __new__(cls):
        return nan
    def __eq__(self, other):
        if other is nan or other == _core.nan_const():
            return True
        return False
    def __ne__(self, other):
        return not self.__eq__(other)
    def __hash__(self):
        return hash(_core.nan_const())
    def __str__(self):
        return str(_core.nan_const())
    def __getattr__(self, name):
        return getattr(wrap(_core.nan_const()), name)

nan = object.__new__(_NaNImpl)
true = wrap(_core.true_const())
false = wrap(_core.false_const())

One = wrap(_core.one())


# Compile-time feature flags (not available as runtime C++ functions)
try:
    from nbsymengine._core import have_llvm as _have_llvm
    have_llvm = _have_llvm
except (ImportError, AttributeError):
    have_llvm = False
have_flint = False
have_piranha = False
have_llvm_long_double = False
have_mpfr = False
have_mpc = False

# Runtime dependency checks
try:
    import numpy as _numpy_mod
    have_numpy = True
except ImportError:
    have_numpy = False


# ---------------------------------------------------------------------------
# S singleton -- callable for sympify, properties for constants
# ---------------------------------------------------------------------------

class _Singleton:
    """Legacy S singleton -- callable for sympify, properties for constants."""
    def __call__(self, obj, raise_error=True):
        from ._sympy_bridge import sympify
        return sympify(obj, raise_error=raise_error)

    @property
    def Zero(self):
        return wrap(_core.zero())

    @property
    def One(self):
        return wrap(_core.one())

    @property
    def NegativeOne(self):
        return wrap(_core.integer(-1))

    @property
    def Half(self):
        return wrap(_core.div(_core.one(), _core.integer(2)))

    @property
    def Pi(self):
        return wrap(_core.pi())

    @property
    def NaN(self):
        return nan

    @property
    def Infinity(self):
        return wrap(_core.oo())

    @property
    def NegativeInfinity(self):
        return wrap(_core.neg(_core.oo()))

    @property
    def ComplexInfinity(self):
        return wrap(_core.zoo())

    @property
    def Exp1(self):
        return wrap(_core.e())

    @property
    def GoldenRatio(self):
        return GoldenRatio

    @property
    def Catalan(self):
        return Catalan

    @property
    def EulerGamma(self):
        return wrap(_core.euler_gamma())

    @property
    def ImaginaryUnit(self):
        return wrap(_core.I())

    @property
    def true(self):
        return wrap(_core.true_const())

    @property
    def false(self):
        return wrap(_core.false_const())

    @property
    def EmptySet(self):
        return wrap(_core.emptyset())

    @property
    def UniversalSet(self):
        return wrap(_core.universalset())

    @property
    def Integers(self):
        return wrap(_core.integers())

    @property
    def Rationals(self):
        return wrap(_core.rationals())

    @property
    def Reals(self):
        return wrap(_core.reals())


S = _Singleton()


# ---------------------------------------------------------------------------
# Catalan and GoldenRatio constants (require SymPy for proper creation)
# ---------------------------------------------------------------------------

if HAS_SYMPY:
    try:
        import sympy as _sympy_mod
        from ._sympy_bridge import from_sympy
        Catalan = wrap(from_sympy(_sympy_mod.Catalan))
        GoldenRatio = wrap(from_sympy(_sympy_mod.GoldenRatio))
    except (ImportError, AttributeError):
        Catalan = wrap(_core.Symbol("Catalan"))
        GoldenRatio = wrap(_core.Symbol("GoldenRatio"))
else:
    Catalan = wrap(_core.Symbol("Catalan"))
    GoldenRatio = wrap(_core.Symbol("GoldenRatio"))
