"""nbsymengine_compat._wrappers -- Delegation wrapper classes and free function re-exports.

All compatibility API classes are delegation wrappers around raw ``_core`` C++
objects.  The ``Basic`` wrapper class (and its subclasses) holds a ``_raw``
reference to the C++ object and delegates operations through ``wrap()`` /
``unwrap()`` at every API boundary.

**No side effects on ``_core`` types.**  Importing this module does NOT
modify any ``nbsymengine._core`` class.
"""
from __future__ import annotations

import collections
import re
import string
import sys as _sys
import weakref as _weakref
from fractions import Fraction
from itertools import product as cartes

from nbsymengine import _core
from ._expr import SympifyError, sympify as _orig_sympify, _make_integer
from ._helpers import (
    _sympify, _missing, _missing_class, _wrap_fn, _to_bool_arg,
    _raise_zerodiv, nb_isinstance_DenseMatrix, HAS_SYMPY, _require_sympy
)

_WRAPPER_MAP = {}
_CORE_TYPE_FOR_WRAPPER = {}
_SINGLETON_CLASSES = []


# ---------------------------------------------------------------------------
# wrap / unwrap -- boundary helpers
# ---------------------------------------------------------------------------

def unwrap(obj):
    """Extract the raw ``_core`` object from a wrapper, or passthrough."""
    if any(obj is x for x in _SINGLETON_CLASSES):
        return obj()._raw
    if hasattr(obj, '_raw'):
        return obj._raw
    return obj


_WRAP_CACHE = _weakref.WeakValueDictionary()

def wrap(obj):
    """Wrap a raw ``_core`` object into the appropriate delegating wrapper class."""
    if hasattr(obj, '_raw'):
        return obj
    if isinstance(obj, _core.DenseMatrix):
        from ._matrices import DenseMatrixWrapper
        cache_key = id(obj)
        if cache_key in _WRAP_CACHE:
            return _WRAP_CACHE[cache_key]
        w = object.__new__(DenseMatrixWrapper)
        w._raw = obj
        _WRAP_CACHE[cache_key] = w
        return w
    if isinstance(obj, _core.Basic):
        cache_key = id(obj)
        if cache_key in _WRAP_CACHE:
            return _WRAP_CACHE[cache_key]
        core_type = type(obj)
        cls = _WRAPPER_MAP.get(core_type, Basic)
        w = object.__new__(cls)
        w._raw = obj
        _WRAP_CACHE[cache_key] = w
        return w
    return obj


def _wrap_nested(value):
    if isinstance(value, (list, tuple)):
        return type(value)(_wrap_nested(v) for v in value)
    if isinstance(value, (set, frozenset)):
        return type(value)(_wrap_nested(v) for v in value)
    if isinstance(value, dict):
        return {_wrap_nested(k): _wrap_nested(v) for k, v in value.items()}
    return wrap(value)


def _sympify_then_unwrap(obj):
    return unwrap(_sympify(obj))


def _get_wrapper_class(core_obj):
    """Get the matching wrapper class for a raw _core object."""
    core_type = type(core_obj)
    cls = _WRAPPER_MAP.get(core_type)
    if cls is not None:
        return cls
    return Basic


# ---------------------------------------------------------------------------
# Register all custom wrapper classes in the wrapper map.
# Called once at module load time.  After this, _register_wrappers() fills
# in remaining _core types not explicitly handled.
# ---------------------------------------------------------------------------

def _init_wrapper_map():
    """Populate _WRAPPER_MAP with all custom and dynamically-created wrapper classes."""
    global _WRAPPER_MAP, _CORE_TYPE_FOR_WRAPPER

    def _register(wrapper_cls, core_cls):
        if core_cls is None:
            return
        try:
            _WRAPPER_MAP[core_cls] = wrapper_cls
            _CORE_TYPE_FOR_WRAPPER[wrapper_cls] = core_cls
        except Exception:
            pass

    # Register custom wrapper subclasses (in order of definition)
    _custom_registrations = (
        (Symbol, _core.Symbol),
        (Dummy, _core.Dummy),
        (Number, _core.Number),
        (Add, _core.Add),
        (Mul, _core.Mul),
        (Pow, _core.Pow),
        (Integer, _core.Integer),
        (Rational, _core.Rational),
        (Boolean, _core.Boolean),
        (Abs, _core.Abs),
        (LambertW, _core.LambertW),
        (Zeta, _core.Zeta),
        (Set, _core.Set),
        (Interval, _core.Interval),
        (EmptySet, _core.EmptySet),
        (UniversalSet, _core.UniversalSet),
        (FiniteSet, _core.FiniteSet),
        (Union, _core.Union),
        (Intersection, _core.Intersection),
        (Complement, _core.Complement),
        (ConditionSet, _core.ConditionSet),
        (ImageSet, _core.ImageSet),
        (BooleanAtom, _core.BooleanAtom),
        (Derivative, _core._Derivative),
        (Subs, _core._Subs),
        (UnevaluatedExpr, _core.UnevaluatedExpr),
        (Max, _core.Max),
        (Min, _core.Min),
        (LeviCivita, _core.LeviCivita),
        (KroneckerDelta, _core.KroneckerDelta),
        (Eq, _core.Eq),
        (Ne, _core.Ne),
        (Ge, _core.Ge),
        (Gt, _core.Gt),
        (Le, _core.Le),
        (Lt, _core.Lt),
        (And, _core.And),
        (Or, _core.Or),
        (Not, _core.Not),
        (Xor, _core.Xor),
        (Contains, _core.Contains),
        (Equality, _core.Equality),
        (Unequality, _core.Unequality),
        (LessThan, _core.LessThan),
        (StrictLessThan, _core.StrictLessThan),
    )
    for wrapper_cls, core_cls in _custom_registrations:
        _register(wrapper_cls, core_cls)

    # Register function wrapper classes
    for _fn_name in _FUNC_CLASS_NAMES:
        wrapper_cls = globals().get(_fn_name)
        core_cls = getattr(_core, _fn_name, None)
        _register(wrapper_cls, core_cls)

    # Set class registrations
    _set_registrations = (
        (Reals, _core.Reals),
        (Integers, _core.Integers),
        (Rationals, _core.Rationals),
        (Complexes, _core.Complexes),
        (Naturals, _core.Naturals),
        (Naturals0, _core.Naturals0),
    )
    for wrapper_cls, core_cls in _set_registrations:
        _register(wrapper_cls, core_cls)

    # Special wrapper registrations for less-common types
    _special_registrations = (
        (Float, _core.RealDouble),
        (RealDouble, _core.RealDouble),
        (ComplexDouble, getattr(_core, "ComplexDouble", None)),
    )
    for wrapper_cls, core_cls in _special_registrations:
        _register(wrapper_cls, core_cls)

    # Now fill in remaining _core.Basic subclasses
    for name in dir(_core):
        obj = getattr(_core, name)
        if not isinstance(obj, type) or not issubclass(obj, _core.Basic):
            continue
        if obj is _core.Basic:
            continue
        if obj in _WRAPPER_MAP:
            continue
        # Create a dynamic subclass for this _core type, with custom isinstance
        class _DynMeta(_BasicMeta):
            _core_type = obj
        wrapper_cls = _DynMeta(name, (Basic,), {"__module__": __name__})
        _WRAPPER_MAP[obj] = wrapper_cls
        _CORE_TYPE_FOR_WRAPPER[wrapper_cls] = obj
        globals()[name] = wrapper_cls



# ---------------------------------------------------------------------------
# Coercion helpers (moved from _monkeypatch.py)
# ---------------------------------------------------------------------------

def _coerce_operand(other):
    """Fast coercion helper for arithmetic operands."""
    if isinstance(other, Basic):
        return unwrap(other)
    if isinstance(other, _core.Basic):
        return other
    if isinstance(other, (int, float, bool, complex, Fraction)):
        return _orig_sympify(other)
    if HAS_SYMPY:
        import sympy
        if isinstance(other, sympy.Basic):
            from ._sympy_bridge import from_sympy
            return from_sympy(other)
    from ._helpers import PyNumber
    try:
        return _orig_sympify(other)
    except Exception:
        pass
    return PyNumber(other)


def _get_p_q(val):
    if isinstance(val, _core.Rational):
        f = Fraction(str(val))
        return f.numerator, f.denominator
    elif isinstance(val, _core.Integer):
        return int(str(val)), 1
    return None


# ---------------------------------------------------------------------------
# Predicate helpers (moved from _monkeypatch.py)
# ---------------------------------------------------------------------------

_int_is_zero = _core.Integer.is_zero
_int_is_positive = _core.Integer.is_positive
_int_is_negative = _core.Integer.is_negative
_int_is_complex = _core.Integer.is_complex

_rat_is_zero = _core.Rational.is_zero
_rat_is_positive = _core.Rational.is_positive
_rat_is_negative = _core.Rational.is_negative
_rat_is_complex = _core.Rational.is_complex


def _native_is_zero(self):
    if isinstance(self, (_core.Integer,)):
        return _int_is_zero(self)
    if isinstance(self, (_core.Rational,)):
        return _rat_is_zero(self)
    if isinstance(self, _core.RealDouble):
        return float(str(self)) == 0.0
    if isinstance(self, _core.Number):
        s = str(self)
        if s == 'nan':
            return None
        if s in ('oo', 'zoo'):
            return False
    if isinstance(self, _core.Symbol):
        return None
    if isinstance(self, (_core.BooleanAtom,)):
        return None
    if HAS_SYMPY:
        from ._sympy_bridge import to_sympy
        return to_sympy(self).is_zero
    return None


def _native_is_positive(self):
    if isinstance(self, (_core.Integer,)):
        return _int_is_positive(self)
    if isinstance(self, (_core.Rational,)):
        return _rat_is_positive(self)
    if isinstance(self, _core.RealDouble):
        return float(str(self)) > 0.0
    if isinstance(self, _core.Number):
        s = str(self)
        if s == 'nan':
            return None
        if s in ('oo', 'zoo'):
            return False
    if isinstance(self, _core.Symbol):
        return None
    if isinstance(self, (_core.BooleanAtom,)):
        return None
    if HAS_SYMPY:
        from ._sympy_bridge import to_sympy
        return to_sympy(self).is_positive
    return None


def _native_is_negative(self):
    if isinstance(self, (_core.Integer,)):
        return _int_is_negative(self)
    if isinstance(self, (_core.Rational,)):
        return _rat_is_negative(self)
    if isinstance(self, _core.RealDouble):
        return float(str(self)) < 0.0
    if isinstance(self, _core.Number):
        s = str(self)
        if s == 'nan':
            return None
        if s in ('oo', 'zoo'):
            return False
    if isinstance(self, _core.Symbol):
        return None
    if isinstance(self, (_core.BooleanAtom,)):
        return None
    if HAS_SYMPY:
        from ._sympy_bridge import to_sympy
        return to_sympy(self).is_negative
    return None


def _native_is_real(self):
    if isinstance(self, (_core.Integer, _core.Rational)):
        return True
    if isinstance(self, _core.RealDouble):
        return True
    if isinstance(self, _core.Number):
        s = str(self)
        if s == 'nan':
            return None
        if s in ('oo', 'zoo'):
            return False
    if isinstance(self, _core.Symbol):
        return None
    if isinstance(self, (_core.BooleanAtom,)):
        return None
    if HAS_SYMPY:
        from ._sympy_bridge import to_sympy
        return to_sympy(self).is_real
    return None


def _native_is_nonzero(self):
    r = _native_is_real(self)
    if r is False:
        return False
    z = _native_is_zero(self)
    if z is True:
        return False
    if z is False and r is True:
        return True
    return None


def _native_is_nonpositive(self):
    r = _native_is_real(self)
    if r is False:
        return False
    pos = _native_is_positive(self)
    if pos is True:
        return False
    if pos is False and r is True:
        return True
    return None


def _native_is_nonnegative(self):
    r = _native_is_real(self)
    if r is False:
        return False
    neg = _native_is_negative(self)
    if neg is True:
        return False
    if neg is False and r is True:
        return True
    return None


def _native_is_number(self):
    if isinstance(self, _core.Number):
        return True
    if isinstance(self, _core.Constant):
        return True
    if isinstance(self, _core.Symbol):
        return False
    if isinstance(self, _core.BooleanAtom):
        return False
    if HAS_SYMPY:
        from ._sympy_bridge import to_sympy
        return to_sympy(self).is_number
    return None


def _native_is_Atom(self):
    if isinstance(self, (_core.Symbol, _core.Number, _core.Constant, _core.BooleanAtom)):
        return True
    return False


def _native_is_finite(self):
    if isinstance(self, (_core.Integer, _core.Rational)):
        return True
    if isinstance(self, _core.RealDouble):
        return True
    if isinstance(self, _core.Number):
        s = str(self)
        if s == 'nan':
            return None
        if s in ('oo', 'zoo'):
            return False
    if isinstance(self, _core.Symbol):
        return None
    if isinstance(self, (_core.BooleanAtom,)):
        return None
    if HAS_SYMPY:
        from ._sympy_bridge import to_sympy
        return to_sympy(self).is_finite
    return None


def _native_is_complex(self):
    if isinstance(self, (_core.Integer,)):
        return _int_is_complex(self)
    if isinstance(self, (_core.Rational,)):
        return _rat_is_complex(self)
    if isinstance(self, _core.RealDouble):
        return False
    if isinstance(self, _core.Number):
        s = str(self)
        if s in ('nan', 'oo', 'zoo'):
            return False
    if isinstance(self, _core.Symbol):
        return None
    if isinstance(self, (_core.BooleanAtom,)):
        return None
    if HAS_SYMPY:
        from ._sympy_bridge import to_sympy
        return bool(to_sympy(self).as_real_imag()[1] != 0)
    return None


# ---------------------------------------------------------------------------
# Arithmetic operator builders
# ---------------------------------------------------------------------------

def _wrap_binary_op(op_name, swap=False):
    old_op = getattr(_core.Basic, op_name)

    def new_op(self, other):
        from ._helpers import PyNumber
        coerced = _coerce_operand(other)

        if isinstance(coerced, PyNumber):
            if not HAS_SYMPY:
                return NotImplemented
            import sympy
            from ._sympy_bridge import to_sympy, from_sympy
            sp_self = to_sympy(self._raw)
            sp_result = getattr(sp_self, op_name)(coerced._val)
            if isinstance(sp_result, sympy.Basic):
                return wrap(from_sympy(sp_result))
            if sp_result is NotImplemented:
                return NotImplemented
            try:
                return PyNumber(sp_result)
            except Exception:
                return NotImplemented
        if swap:
            return wrap(old_op(coerced, self._raw))
        return wrap(old_op(self._raw, coerced))

    return new_op


# ---------------------------------------------------------------------------
# has / free_symbols / atoms helpers
# ---------------------------------------------------------------------------

def _has_basic(expr, looking_for):
    expr = _sympify(expr)
    looking_for = _sympify(looking_for)
    if isinstance(looking_for, (_core.Add, _core.Mul)):
        raise NotImplementedError(
            "Associative classes not yet handled in HasBasicVisitor"
        )
    if expr == looking_for:
        return True
    for arg in expr.get_args():
        if _has_basic(arg, looking_for):
            return True
    return False


def _free_symbols_walk(expr):
    syms = set()
    def walk(e):
        if e.__class__.__name__ in ('Symbol', 'Dummy'):
            syms.add(e)
        else:
            for arg in e.get_args():
                walk(arg)
    walk(expr)
    return syms


# ---------------------------------------------------------------------------
# Pickling helpers (moved from _pickling.py)
# ---------------------------------------------------------------------------

_CORE_TYPES = set()
for _name in dir(_core):
    _obj = getattr(_core, _name)
    if isinstance(_obj, type):
        _CORE_TYPES.add(_obj)

_SET_TYPE_NAMES = frozenset({
    'FiniteSet', 'Interval', 'Union', 'Intersection', 'Complement',
    'ConditionSet', 'ImageSet', 'EmptySet', 'UniversalSet',
    'Reals', 'Integers', 'Rationals', 'Complexes', 'Naturals', 'Naturals0',
})


def _safe_sympify(s):
    if not HAS_SYMPY:
        _require_sympy("_safe_sympify()")
    import sympy
    from sympy.parsing.sympy_parser import (
        parse_expr, standard_transformations, convert_xor,
    )
    safe_globals = {}
    for name in dir(sympy):
        if not name.startswith('_'):
            safe_globals[name] = getattr(sympy, name)
    safe_globals['S'] = sympy.S
    return parse_expr(s, global_dict=safe_globals,
                      transformations=(standard_transformations + (convert_xor,)))


def _unpickle_basic(s):
    if not HAS_SYMPY:
        _require_sympy("unpickling Basic from string")
    from ._sympy_bridge import from_sympy
    return wrap(from_sympy(_safe_sympify(s)))


_CONSTANT_MAP = None


def _get_constant_map():
    global _CONSTANT_MAP
    if _CONSTANT_MAP is None:
        _CONSTANT_MAP = {}
    return _CONSTANT_MAP


def _unpickle_constant(name):
    cmap = _get_constant_map()
    obj = cmap.get(name)
    if obj is not None:
        return obj
    if not HAS_SYMPY:
        _require_sympy(f"unpickling constant '{name}'")
    from ._sympy_bridge import from_sympy
    return wrap(from_sympy(_safe_sympify(name)))


def _unpickle_dummy(name, index):
    return wrap(_core.Dummy(name, index))


def _unpickle_via_sympy(sym_expr):
    if not HAS_SYMPY:
        _require_sympy("unpickling via SymPy expression")
    from ._sympy_bridge import from_sympy
    return wrap(from_sympy(sym_expr))


# ---------------------------------------------------------------------------
# Basic -- the base delegation wrapper
# ---------------------------------------------------------------------------

class _BasicMeta(type):
    """Metaclass for Basic delegation wrappers.

    Provides ``__instancecheck__`` so that ``isinstance(obj, SomeWrapper)``
    returns True for both:
    * Wrapped Python instances of the wrapper class (normal Python isinstance).
    * Raw ``_core`` C++ objects of the corresponding C++ type.
    """

    def __new__(mcs, name, bases, namespace, **kwargs):
        if '__slots__' not in namespace:
            mod = namespace.get('__module__', '')
            if mod.startswith('nbsymengine_compat') or 'nbsymengine_compat' in mod:
                if name == 'Basic':
                    namespace['__slots__'] = ('_raw', '__weakref__')
                else:
                    namespace['__slots__'] = ()
        return super().__new__(mcs, name, bases, namespace, **kwargs)

    def __instancecheck__(cls, inst):
        raw_inst = getattr(inst, '_raw', inst)
        if type.__instancecheck__(cls, inst):
            return True
        # Look up the _core type for this wrapper class
        core_type = _CORE_TYPE_FOR_WRAPPER.get(cls)
        if core_type is None:
            core_type = getattr(cls, '_core_type', None)
        if core_type is not None:
            if core_type is _core.Rational:
                return isinstance(raw_inst, (_core.Rational, _core.Integer))
            return isinstance(raw_inst, core_type)
        # Fallback: Basic wrapper accepts any _core.Basic
        if cls is Basic:
            return isinstance(raw_inst, _core.Basic)
        return False

    def __eq__(cls, other):
        if any(cls is x for x in _SINGLETON_CLASSES):
            return cls() == other
        return super().__eq__(other)

    def __ne__(cls, other):
        if any(cls is x for x in _SINGLETON_CLASSES):
            return cls() != other
        return super().__ne__(other)

    def __hash__(cls):
        if any(cls is x for x in _SINGLETON_CLASSES):
            return hash(cls())
        return super().__hash__()


# Map from wrapper class -> _core type (populated during _init_wrapper_map)
_CORE_TYPE_FOR_WRAPPER = {}


class Basic(metaclass=_BasicMeta):
    """Delegation wrapper around a ``_core.Basic`` C++ object.

    All compat-layer methods and properties live on this class (and its
    subclasses).  No monkey-patching of ``_core.Basic`` is performed.
    """

    def __getattribute__(self, name):
        if name == '__weakref__':
            raise AttributeError("__weakref__")
        return object.__getattribute__(self, name)

    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        if name == '_raw' and value is not None:
            _WRAP_CACHE[id(value)] = self

    def __init__(self, *args, **kwargs):
        if not hasattr(self, '_raw'):
            if args and isinstance(args[0], Basic):
                self._raw = args[0]._raw
            elif args and isinstance(args[0], _core.Basic):
                self._raw = args[0]

    def __hash__(self):
        return hash(self._raw)

    def __repr__(self):
        return repr(self._raw)

    def __str__(self):
        return str(self._raw)

    @property
    def name(self):
        return getattr(self._raw, 'name', None)

    # -- arithmetic dunders --------------------------------------------------
    __add__ = _wrap_binary_op('__add__')
    __radd__ = _wrap_binary_op('__add__', swap=True)
    __sub__ = _wrap_binary_op('__sub__')
    __rsub__ = _wrap_binary_op('__sub__', swap=True)
    __mul__ = _wrap_binary_op('__mul__')
    __rmul__ = _wrap_binary_op('__mul__', swap=True)
    __truediv__ = _wrap_binary_op('__truediv__')
    __rtruediv__ = _wrap_binary_op('__truediv__', swap=True)
    __pow__ = _wrap_binary_op('__pow__')
    __rpow__ = _wrap_binary_op('__pow__', swap=True)
    __neg__ = lambda self: wrap(-self._raw)
    __pos__ = lambda self: wrap(self._raw)
    __abs__ = lambda self: wrap(_core.abs(self._raw))

    # -- floor division / modulo ---------------------------------------------
    __floordiv__ = lambda self, other: wrap(_core.floor(self._raw / _sympify(other)))
    __rfloordiv__ = lambda self, other: wrap(_core.floor(_sympify(other) / self._raw))
    __mod__ = lambda self, other: wrap(self._raw - _sympify(other) * _core.floor(self._raw / _sympify(other)))
    __rmod__ = lambda self, other: wrap(_sympify(other) - self._raw * _core.floor(_sympify(other) / self._raw))

    # -- comparisons ---------------------------------------------------------
    def __eq__(self, other):
        if isinstance(other, (int, float, Fraction, bool)):
            try:
                other = _sympify(other)
            except Exception:
                return False
        return self._raw == unwrap(other)

    def __ne__(self, other):
        if isinstance(other, (int, float, Fraction, bool)):
            try:
                other = _sympify(other)
            except Exception:
                return True
        return self._raw != unwrap(other)

    __lt__ = lambda self, other: wrap(_core.Lt(self._raw, unwrap(_sympify(other))))
    __le__ = lambda self, other: wrap(_core.Le(self._raw, unwrap(_sympify(other))))
    __gt__ = lambda self, other: wrap(_core.Gt(self._raw, unwrap(_sympify(other))))
    __ge__ = lambda self, other: wrap(_core.Ge(self._raw, unwrap(_sympify(other))))

    # -- type coercion -------------------------------------------------------
    def __int__(self):
        if isinstance(self._raw, _core.Integer):
            old_limit = _sys.get_int_max_str_digits()
            try:
                _sys.set_int_max_str_digits(0)
                return int(str(self._raw))
            finally:
                _sys.set_int_max_str_digits(old_limit)
        from ._sympy_bridge import to_sympy
        return int(float(to_sympy(self._raw)))

    def __float__(self):
        from ._sympy_bridge import to_sympy
        return float(to_sympy(self._raw))

    def __complex__(self):
        from ._sympy_bridge import to_sympy
        return complex(to_sympy(self._raw))

    def __bool__(self):
        if isinstance(self._raw, _core.Boolean):
            if not HAS_SYMPY:
                _require_sympy("Boolean.__bool__()")
            from ._sympy_bridge import to_sympy
            return bool(to_sympy(self._raw))
        return True

    # -- properties (args, free_symbols, atoms) ------------------------------
    @property
    def args(self):
        return tuple(wrap(a) for a in self._raw.get_args())

    @property
    def func(self):
        return self.__class__

    def copy(self):
        return self

    def get_args(self):
        return self._raw.get_args()

    def has(self, *args):
        for arg in args:
            if _has_basic(self._raw, arg):
                return True
        return False

    @property
    def free_symbols(self):
        return _free_symbols_walk(self._raw)

    def atoms(self, *types):
        if not types:
            return self.free_symbols
        s = set()
        if isinstance(self._raw, types):
            s.add(self)
        for arg in self._raw.get_args():
            s.update(wrap(arg).atoms(*types))
        return s

    # -- as_powers_dict -----------------------------------------------------
    def as_powers_dict(self):
        d = collections.defaultdict(int)
        if str(self._raw) == '-oo':
            d[wrap(_core.integer(-1))] = 1
            d[wrap(_core.oo())] = 1
            return d
        d[self] = 1
        return d

    # -- as_coefficients_dict -----------------------------------------------
    def as_coefficients_dict(self):
        d = collections.defaultdict(int)
        d[self] = 1
        return d

    # -- as_numer_denom / as_real_imag --------------------------------------
    def as_numer_denom(self):
        if isinstance(self._raw, _core.Rational):
            f = Fraction(str(self._raw))
            return wrap(_make_integer(f.numerator)), wrap(_make_integer(f.denominator))
        elif isinstance(self._raw, _core.Integer):
            return self, wrap(_core.integer(1))
        elif isinstance(self._raw, _core.Pow):
            base, exp = self._raw.get_args()
            if isinstance(exp, _core.Integer) and int(str(exp)) < 0:
                return wrap(_core.integer(1)), wrap(base) ** wrap(-exp)
            return self, wrap(_core.integer(1))
        elif isinstance(self._raw, _core.Mul):
            num = []
            den = []
            for arg in self._raw.get_args():
                n, d = wrap(arg).as_numer_denom()
                if n != wrap(_core.integer(1)):
                    num.append(n._raw)
                if d != wrap(_core.integer(1)):
                    den.append(d._raw)
            if not num:
                num_expr = _core.integer(1)
            elif len(num) == 1:
                num_expr = num[0]
            else:
                num_expr = _core.mul(*num)
            if not den:
                den_expr = _core.integer(1)
            elif len(den) == 1:
                den_expr = den[0]
            else:
                den_expr = _core.mul(*den)
            return wrap(num_expr), wrap(den_expr)
        return self, wrap(_core.integer(1))

    def as_real_imag(self):
        conj = _core.conjugate(self._raw)
        real_part = _core.div(_core.add(self._raw, conj), _core.integer(2))
        imag_part = _core.div(_core.sub(self._raw, conj), _core.mul(_core.integer(2), _core.I()))
        return wrap(real_part), wrap(imag_part)

    # -- properties real / imag ---------------------------------------------
    @property
    def real(self):
        try:
            from ._sympy_bridge import to_sympy, from_sympy
            sp = to_sympy(self._raw)
            re = sp.as_real_imag()[0]
            return wrap(from_sympy(re))
        except Exception:
            return self

    @property
    def imag(self):
        try:
            from ._sympy_bridge import to_sympy, from_sympy
            sp = to_sympy(self._raw)
            im = sp.as_real_imag()[1]
            return wrap(from_sympy(im))
        except Exception:
            return wrap(_core.zero())

    # -- n / evalf / _sympy_ / subs / xreplace / msubs / diff / expand ------
    def _evalf_numbers(self, raw_expr):
        if isinstance(raw_expr, (_core.Integer, _core.Rational)):
            return _core.real_double(float(str(raw_expr)))
        args = raw_expr.get_args()
        if not args:
            return raw_expr
        new_args = [self._evalf_numbers(a) for a in args]
        if new_args == list(args):
            return raw_expr
        name = raw_expr.__class__.__name__
        if name == 'Add':
            return _core.add(*new_args)
        elif name == 'Mul':
            return _core.mul(*new_args)
        elif name == 'Pow':
            return _core.pow(new_args[0], new_args[1])
        elif name == 'FunctionSymbol':
            return _core.function_symbol(raw_expr.name, *new_args)
        else:
            fn = getattr(_core, name.lower(), None) or getattr(_core, name, None)
            if fn is not None:
                try:
                    return fn(*new_args)
                except Exception:
                    pass
            return raw_expr

    def n(self, prec=53, real=None):
        from ._helpers import have_mpfr, have_mpc
        if prec != 53:
            if real is True and not have_mpfr:
                raise ValueError("MPFR is not supported")
            if real is False and not have_mpc:
                raise ValueError("MPC is not supported")
            if real is None and (not have_mpfr or not have_mpc):
                raise ValueError("MPFR/MPC is not supported")
        if not HAS_SYMPY:
            _require_sympy("evalf()/n()")
        from ._sympy_bridge import to_sympy, from_sympy
        sp_expr = to_sympy(self._raw)
        if real is not None:
            if self.free_symbols:
                raise RuntimeError("Expression has free symbols")
        dec_prec = int(prec * 0.30103)
        if dec_prec < 1:
            dec_prec = 1
        res = sp_expr.evalf(n=dec_prec)
        if real is True:
            from ._wrappers import RealDouble
            try:
                val = float(res)
            except TypeError:
                raise RuntimeError("Expression cannot be evaluated to a float")
            return RealDouble(val)
        elif real is False:
            from ._wrappers import ComplexDouble
            try:
                val = complex(res)
            except TypeError:
                raise RuntimeError("Expression cannot be evaluated to a complex number")
            return ComplexDouble(val.real, val.imag)
        ret = from_sympy(res)
        return wrap(self._evalf_numbers(unwrap(ret)))

    def evalf(self, *args, **kwargs):
        return self.n(*args, **kwargs)

    def _sympy_(self):
        if not HAS_SYMPY:
            _require_sympy("_sympy_()")
        from ._sympy_bridge import to_sympy
        return to_sympy(self._raw)

    def subs(self, *args, **kwargs):
        from ._wrappers import subs
        return subs(self, *args, **kwargs)

    def xreplace(self, mapping):
        coerced = {_sympify(k): _sympify(v) for k, v in mapping.items()}
        return wrap(_core.xreplace(self._raw, coerced))

    def msubs(self, mapping):
        coerced = {_sympify(k): _sympify(v) for k, v in mapping.items()}
        return wrap(_core.msubs(self._raw, coerced))

    def diff(self, *symbols):
        from ._wrappers import diff
        return diff(self, *symbols)

    def expand(self, *args, **kwargs):
        return wrap(_core.expand(self._raw, *args, **kwargs))

    # -- predicates ----------------------------------------------------------
    @property
    def is_zero(self):
        return _native_is_zero(self._raw)

    @property
    def is_positive(self):
        return _native_is_positive(self._raw)

    @property
    def is_negative(self):
        return _native_is_negative(self._raw)

    @property
    def is_nonpositive(self):
        return _native_is_nonpositive(self._raw)

    @property
    def is_nonnegative(self):
        return _native_is_nonnegative(self._raw)

    @property
    def is_real(self):
        return _native_is_real(self._raw)

    @property
    def is_nonzero(self):
        return _native_is_nonzero(self._raw)

    @property
    def is_number(self):
        return _native_is_number(self._raw)

    @property
    def is_Atom(self):
        return _native_is_Atom(self._raw)

    @property
    def is_finite(self):
        return _native_is_finite(self._raw)

    @property
    def is_complex(self):
        return _native_is_complex(self._raw)

    # -- pickling -----------------------------------------------------------
    def __reduce__(self):
        from ._sympy_bridge import to_sympy
        raw = self._raw
        if isinstance(raw, _core.Dummy):
            return (_unpickle_dummy, (raw.name, raw.dummy_index))
        if type(raw) not in _CORE_TYPES:
            raise NotImplementedError(
                f"Pickling {type(raw).__name__} requires explicit __reduce__"
            )
        if any(isinstance(s, _core.Dummy) for s in _free_symbols_walk(raw)):
            return (_unpickle_via_sympy, (to_sympy(raw),))
        cname = type(raw).__name__
        if cname in _SET_TYPE_NAMES:
            return (_unpickle_via_sympy, (to_sympy(raw),))
        s = str(raw)
        cmap = _get_constant_map()
        if s in cmap:
            return (_unpickle_constant, (s,))
        return (_unpickle_basic, (s,))

    def __reduce_ex__(self, protocol):
        return self.__reduce__()

    def _unsafe_reset(self):
        pass

    def _repr_latex_(self):
        from ._printing import _latex_printing_enabled
        if _latex_printing_enabled[0]:
            from ._printing import latex
            return f'${latex(self)}$'
        return None

    def compare(self, other):
        if hasattr(other, '_raw'):
            return self._raw.compare(other._raw)
        return self._raw.compare(unwrap(other))

    def coeff(self, x, n=1):
        from ._sympy_bridge import to_sympy, from_sympy
        sp_self = to_sympy(self._raw)
        sp_x = to_sympy(unwrap(_sympify(x)))
        result = sp_self.coeff(sp_x, n)
        if HAS_SYMPY:
            import sympy
            if isinstance(result, sympy.Basic):
                return wrap(from_sympy(result))
        return result


# ---------------------------------------------------------------------------
# Concrete wrapper subclasses with custom constructors
# ---------------------------------------------------------------------------

class Symbol(Basic):
    def __new__(cls, name, **kwargs):
        obj = object.__new__(cls)
        obj._raw = _core.Symbol(name, **kwargs) if kwargs else _core.Symbol(name)
        return obj


class Dummy(Symbol):
    def __new__(cls, name=None, index=None):
        obj = object.__new__(cls)
        if name is None:
            if index is None:
                obj._raw = _core.Dummy()
            else:
                obj._raw = _core.Dummy('_Dummy', index)
        else:
            if index is None:
                obj._raw = _core.Dummy(name)
            else:
                obj._raw = _core.Dummy(name, index)
        return obj

    @property
    def name(self):
        return self._raw.name

    @property
    def dummy_index(self):
        return self._raw.dummy_index


class Number(Basic):
    pass


class Add(Basic):
    def __new__(cls, *args):
        obj = object.__new__(cls)
        if not args:
            obj._raw = _make_integer(0)
        else:
            res = _sympify(args[0])
            for a in args[1:]:
                res = _core.add(res, _sympify(a))
            obj._raw = res
        return obj

    @classmethod
    def _from_args(cls, args):
        if not args:
            return wrap(_core.zero())
        if len(args) == 1:
            return wrap(args[0])
        res = unwrap(_sympify(args[0]))
        for a in args[1:]:
            res = _core.add(res, unwrap(_sympify(a)))
        return wrap(res)

    @staticmethod
    def make_args(expr):
        if isinstance(expr, Basic):
            raw = expr._raw
        else:
            raw = expr
        if isinstance(raw, _core.Add):
            return tuple(wrap(a) for a in raw.get_args())
        return (expr,)

    @property
    def func(self):
        @staticmethod
        def _f(*args):
            return Add(*args)
        return _f

    def as_coefficients_dict(self):
        d = collections.defaultdict(int)
        d[wrap(_core.integer(1))] = wrap(_core.zero())
        for arg in self._raw.get_args():
            if isinstance(arg, _core.Mul):
                mul_args = arg.get_args()
                if isinstance(mul_args[0], (_core.Integer, _core.Rational, _core.RealDouble)):
                    coeff = wrap(mul_args[0])
                    base = Mul._from_args(mul_args[1:])
                else:
                    coeff = wrap(_core.integer(1))
                    base = wrap(arg)
                d[base] = coeff
            elif isinstance(arg, (_core.Integer, _core.Rational, _core.RealDouble)):
                d[wrap(_core.integer(1))] = wrap(arg)
            else:
                d[wrap(arg)] = wrap(_core.integer(1))
        return d


class Mul(Basic):
    def __new__(cls, *args):
        obj = object.__new__(cls)
        if not args:
            obj._raw = _make_integer(1)
        else:
            res = _sympify(args[0])
            for a in args[1:]:
                res = _core.mul(res, _sympify(a))
            obj._raw = res
        return obj

    @classmethod
    def _from_args(cls, args):
        if not args:
            return wrap(_core.one())
        if len(args) == 1:
            return wrap(args[0])
        res = unwrap(_sympify(args[0]))
        for a in args[1:]:
            res = _core.mul(res, unwrap(_sympify(a)))
        return wrap(res)

    @staticmethod
    def make_args(expr):
        if isinstance(expr, Basic):
            raw = expr._raw
        else:
            raw = expr
        if isinstance(raw, _core.Mul):
            return tuple(wrap(a) for a in raw.get_args())
        return (expr,)

    @property
    def func(self):
        @staticmethod
        def _f(*args):
            return Mul(*args)
        return _f

    def as_coefficients_dict(self):
        d = collections.defaultdict(int)
        args = self._raw.get_args()
        if isinstance(args[0], (_core.Integer, _core.Rational, _core.RealDouble)):
            coef = wrap(args[0])
            base = Mul._from_args(args[1:])
        else:
            coef = wrap(_core.integer(1))
            base = self
        d[base] = coef
        return d

    def as_powers_dict(self):
        d = collections.defaultdict(int)
        for arg in self._raw.get_args():
            if isinstance(arg, (_core.Integer, _core.Rational)):
                d.update(wrap(arg).as_powers_dict())
            elif isinstance(arg, _core.Pow):
                base, exp = arg.get_args()
                pq = _get_p_q(base)
                if pq is not None:
                    p, q = pq
                    if 0 < p < q:
                        d[wrap(_core.div(_core.one(), base))] -= wrap(exp)
                        continue
                d[wrap(base)] += wrap(exp)
            else:
                pq = _get_p_q(arg)
                if pq is not None:
                    p, q = pq
                    if 0 < p < q:
                        d[wrap(_core.div(_core.one(), arg))] -= 1
                        continue
                d[wrap(arg)] += 1
        return d


class Pow(Basic):
    def __new__(cls, a, b):
        obj = object.__new__(cls)
        obj._raw = _core.pow(_sympify(a), _sympify(b))
        return obj

    @property
    def base(self):
        return wrap(self._raw.get_args()[0])

    @property
    def exp(self):
        return wrap(self._raw.get_args()[1])

    def as_base_exp(self):
        return (self.base, self.exp)

    @property
    def func(self):
        @staticmethod
        def _f(a, b):
            return Pow(a, b)
        return _f

    def as_powers_dict(self):
        d = collections.defaultdict(int)
        base, exp = self._raw.get_args()
        pq = _get_p_q(base)
        if pq is not None:
            p, q = pq
            if 0 < p < q:
                d[wrap(_core.div(_core.one(), base))] = -wrap(exp)
                return d
        d[wrap(base)] = wrap(exp)
        return d


class Integer(Basic):
    def __new__(cls, i):
        obj = object.__new__(cls)
        if isinstance(i, _core.Integer):
            obj._raw = i
        elif isinstance(i, Basic) and isinstance(i._raw, _core.Integer):
            obj._raw = i._raw
        else:
            obj._raw = _make_integer(int(i))
        return obj

    @property
    def p(self):
        return int(str(self._raw))

    @property
    def q(self):
        return 1


class Rational(Basic):
    def __new__(cls, p, q=1):
        obj = object.__new__(cls)
        if isinstance(p, Fraction):
            q = p.denominator * q
            p = p.numerator
        if isinstance(p, (_core.Integer,)):
            p_val = p
        elif isinstance(p, Basic) and isinstance(p._raw, _core.Integer):
            p_val = p._raw
        elif isinstance(p, Basic) and isinstance(p._raw, _core.Rational):
            f = Fraction(str(p._raw))
            p_val = _make_integer(f.numerator)
            q = f.denominator * q
        else:
            p_val = _make_integer(int(p))
        q_val = _make_integer(int(q))
        obj._raw = _core.div(p_val, q_val)
        return obj

    @property
    def p(self):
        return Fraction(str(self._raw)).numerator

    @property
    def q(self):
        return Fraction(str(self._raw)).denominator


# Boolean / relational classes
class Boolean(Basic):
    def __bool__(self):
        if not HAS_SYMPY:
            _require_sympy("Boolean.__bool__()")
        from ._sympy_bridge import to_sympy
        return bool(to_sympy(self._raw))


class Eq(Basic):
    def __new__(cls, *args, **kwargs):
        if len(args) == 1:
            return wrap(_core.Eq(_sympify(args[0]), _make_integer(0)))
        return wrap(_core.Eq(*(_sympify(a) for a in args), **kwargs))


class Ne(Basic):
    def __new__(cls, *args, **kwargs):
        return wrap(_core.Ne(*(_sympify(a) for a in args), **kwargs))


class Ge(Basic):
    def __new__(cls, *args, **kwargs):
        return wrap(_core.Ge(*(_sympify(a) for a in args), **kwargs))


class Gt(Basic):
    def __new__(cls, *args, **kwargs):
        return wrap(_core.Gt(*(_sympify(a) for a in args), **kwargs))


class Le(Basic):
    def __new__(cls, *args, **kwargs):
        return wrap(_core.Le(*(_sympify(a) for a in args), **kwargs))


class Lt(Basic):
    def __new__(cls, *args, **kwargs):
        return wrap(_core.Lt(*(_sympify(a) for a in args), **kwargs))

class Equality(Basic):
    def __new__(cls, *args, **kwargs):
        return Eq(*args, **kwargs)


class Unequality(Basic):
    def __new__(cls, *args, **kwargs):
        return Ne(*args, **kwargs)


class LessThan(Basic):
    def __new__(cls, *args, **kwargs):
        return Le(*args, **kwargs)


class StrictLessThan(Basic):
    def __new__(cls, *args, **kwargs):
        return Lt(*args, **kwargs)


Relational = Basic

# Function classes (distinct per type for isinstance/type equality checks)
_FUNC_CLASS_MAP = {
    # Trig
    'Sin': 'sin', 'Cos': 'cos', 'Tan': 'tan',
    'ASin': 'asin', 'ACos': 'acos', 'ATan': 'atan', 'ATan2': 'atan2',
    # Reciprocal Trig
    'Cot': 'cot', 'Csc': 'csc', 'Sec': 'sec',
    'ACot': 'acot', 'ACsc': 'acsc', 'ASec': 'asec',
    # Hyperbolic
    'Sinh': 'sinh', 'Cosh': 'cosh', 'Tanh': 'tanh',
    'Sech': 'sech', 'Csch': 'csch', 'Coth': 'coth',
    'ASinh': 'asinh', 'ACosh': 'acosh', 'ATanh': 'atanh',
    'ACoth': 'acoth', 'ASech': 'asech', 'ACsch': 'acsch',
    # Other math
    'Log': 'log', 'Gamma': 'gamma', 'Erf': 'erf', 'Erfc': 'erfc',
    'Sign': 'sign', 'Floor': 'floor', 'Ceiling': 'ceiling',
    'Dirichlet_eta': 'dirichlet_eta', 'Conjugate': 'conjugate',
    'Abs': 'abs',
    'Beta': 'beta',
    'PolyGamma': 'polygamma',
    'LogGamma': 'loggamma',
    'LowerGamma': 'lowergamma',
    'UpperGamma': 'uppergamma',
}

_FUNC_CLASS_NAMES = tuple(_FUNC_CLASS_MAP.keys())

def _make_func_class(uc_name, lc_name):
    class _FuncClass(Basic):
        __slots__ = ()
        def __new__(cls, *args, **kwargs):
            if lc_name == 'cot':
                x_sym = _sympify(args[0])
                return wrap(_core.div(_core.one(), _core.tan(unwrap(x_sym))))
            elif lc_name == 'csc':
                x_sym = _sympify(args[0])
                return wrap(_core.div(_core.one(), _core.sin(unwrap(x_sym))))
            elif lc_name == 'sec':
                x_sym = _sympify(args[0])
                return wrap(_core.div(_core.one(), _core.cos(unwrap(x_sym))))
            elif lc_name == 'coth':
                x_sym = _sympify(args[0])
                return wrap(_core.div(_core.one(), _core.tanh(unwrap(x_sym))))
            elif lc_name in ('acot', 'acsc', 'asec', 'asinh', 'acosh', 'atanh', 'acoth', 'asech', 'acsch'):
                import sympy
                from ._sympy_bridge import to_sympy, from_sympy
                sym_func = getattr(sympy, lc_name)
                sympy_args = [to_sympy(_sympify(a)) for a in args]
                return wrap(from_sympy(sym_func(*sympy_args, **kwargs)))
            elif lc_name == 'log':
                if len(args) == 2:
                    return wrap(_core.div(_core.log(unwrap(_sympify(args[0]))),
                                          _core.log(unwrap(_sympify(args[1])))))
                coerced = [unwrap(_sympify(a)) for a in args]
                return wrap(_core.log(*coerced, **kwargs))
            
            core_fn = getattr(_core, lc_name, None)
            if core_fn is None:
                core_fn = getattr(_core, uc_name, None)
            if core_fn is None:
                raise AttributeError(f"No C++ or Python implementation found for {lc_name}")
            return wrap(core_fn(*[unwrap(_sympify(a)) for a in args], **kwargs))

    _FuncClass.__name__ = lc_name
    _FuncClass.__qualname__ = lc_name
    return _FuncClass

for _uc, _lc in _FUNC_CLASS_MAP.items():
    _cls = _make_func_class(_uc, _lc)
    globals()[_lc] = _cls
    globals()[_uc] = _cls

abs = Abs


class Abs(Basic):
    def __new__(cls, *args):
        if not args:
            raise TypeError("Abs() missing required argument")
        obj = object.__new__(cls)
        obj._raw = _core.abs(_sympify(args[0]))
        return obj


class LambertW(Basic):
    def __new__(cls, x):
        obj = object.__new__(cls)
        obj._raw = _core.lambertw(_sympify(x))
        return obj


class Zeta(Basic):
    def __new__(cls, s, a=None):
        obj = object.__new__(cls)
        s_raw = _sympify(s)
        if a is not None:
            a_sym = _sympify(a)
            s_raw = unwrap(s_raw)
            a_raw = unwrap(a_sym)
            try:
                s_val = int(str(s_raw))
                is_s_int = isinstance(s_raw, _core.Integer) or (hasattr(s_raw, 'is_integer') and s_raw.is_integer)
            except (ValueError, TypeError, AttributeError):
                is_s_int = False
            try:
                a_val = int(str(a_raw))
                is_a_int = isinstance(a_raw, _core.Integer) or (hasattr(a_raw, 'is_integer') and a_raw.is_integer)
            except (ValueError, TypeError, AttributeError):
                is_a_int = False
            if is_s_int:
                if s_val == 0:
                    obj._raw = _core.sub(_core.div(_core.integer(1), _core.integer(2)), a_raw)
                    return obj
                elif s_val == 1:
                    obj._raw = _core.zoo()
                    return obj
            if is_s_int and is_a_int:
                if s_val < 0:
                    res = _core.integer(1) if s_val % 2 == 0 else _core.integer(-1)
                    b = _core.bernoulli(-s_val + 1)
                    denom = _core.integer(-s_val + 1)
                    zeta_val = _core.mul(res, _core.div(b, denom))
                elif s_val % 2 == 0:
                    zeta_val = _core.zeta(s_raw)
                else:
                    obj._raw = _core.function_symbol('zeta', s_raw, a_raw)
                    return obj
                if a_val < 0:
                    obj._raw = _core.add(zeta_val, _core.harmonic(-a_val, s_val))
                else:
                    obj._raw = _core.sub(zeta_val, _core.harmonic(a_val - 1, s_val))
                return obj
            obj._raw = _core.function_symbol('zeta', s_raw, a_raw)
            return obj
        obj._raw = _core.zeta(unwrap(s_raw))
        return obj


# Set classes
class Set(Basic):
    def union(self, other):
        return wrap(self._raw.set_union(unwrap(other)))

    def intersection(self, other):
        return wrap(self._raw.set_intersection(unwrap(other)))

    def complement(self, other):
        return wrap(self._raw.set_complement(unwrap(other)))

    def contains(self, expr):
        return wrap(self._raw.contains(_sympify(expr)))


class EmptySet(Set):
    def __new__(cls):
        return wrap(_core.emptyset())


class UniversalSet(Set):
    def __new__(cls):
        return wrap(_core.universalset())


class Interval(Set):
    def __new__(cls, start, end, left_open=False, right_open=False):
        s = _sympify(start)
        e = _sympify(end)
        if e == _core.oo() or e == _core.zoo():
            right_open = True
        if s == _core.neg(_core.oo()):
            left_open = True
        return wrap(_core.interval(s, e, bool(left_open), bool(right_open)))

    @property
    def start(self):
        return wrap(self._raw.get_args()[0])

    @property
    def end(self):
        return wrap(self._raw.get_args()[1])


class FiniteSet(Set):
    def __new__(cls, *args):
        if len(args) == 1 and isinstance(args[0], _core.FiniteSet):
            raw = _core.finiteset({args[0]})
        elif len(args) == 1 and isinstance(args[0], (set, frozenset)):
            raw = _core.finiteset({_sympify(x) for x in args[0]})
        elif len(args) == 1 and hasattr(args[0], '__iter__') and not isinstance(args[0], (str, _core.Basic)):
            raw = _core.finiteset({_sympify(x) for x in args[0]})
        else:
            raw = _core.finiteset({_sympify(x) for x in args})
        return wrap(raw)


class Union(Set):
    def __new__(cls, *args):
        if len(args) == 1 and isinstance(args[0], (list, tuple, set, frozenset)):
            raw = _core.set_union([_sympify(a) for a in args[0]])
        else:
            raw = _core.set_union([_sympify(a) for a in args])
        return wrap(raw)


class Intersection(Set):
    def __new__(cls, *args):
        if len(args) == 1 and isinstance(args[0], (list, tuple, set, frozenset)):
            raw = _core.set_intersection([_sympify(a) for a in args[0]])
        else:
            raw = _core.set_intersection([_sympify(a) for a in args])
        return wrap(raw)


class Complement(Set):
    def __new__(cls, universe, container):
        return wrap(_core.set_complement(_sympify(universe), _sympify(container)))


class ConditionSet(Set):
    def __new__(cls, sym, condition, base_set=None):
        return wrap(_core.conditionset(unwrap(_sympify(sym)), unwrap(_sympify(condition))))


class ImageSet(Set):
    def __new__(cls, sym_or_expr, expr_or_base, base=None):
        if base is not None:
            raw = _core.imageset(unwrap(_sympify(sym_or_expr)), unwrap(_sympify(expr_or_base)), unwrap(_sympify(base)))
        else:
            raw = _core.imageset(unwrap(_sympify(sym_or_expr)), unwrap(_sympify(expr_or_base)), _core.emptyset())
        return wrap(raw)


class Reals(Set):
    def __new__(cls):
        return wrap(_core.reals())


class Integers(Set):
    def __new__(cls):
        return wrap(_core.integers())


class Rationals(Set):
    def __new__(cls):
        return wrap(_core.rationals())


class Complexes(Set):
    def __new__(cls):
        return wrap(_core.complexes())


class Naturals(Set):
    def __new__(cls):
        return wrap(_core.naturals())


class Naturals0(Set):
    def __new__(cls):
        return wrap(_core.naturals0())


# Boolean classes
class BooleanAtom(Basic):
    pass


class And(Basic):
    def __new__(cls, *args):
        if not args:
            return wrap(_core.true_const())
        return wrap(_core.logical_and(*[_to_bool_arg(a) for a in args]))


class Or(Basic):
    def __new__(cls, *args):
        if not args:
            return wrap(_core.false_const())
        return wrap(_core.logical_or(*[_to_bool_arg(a) for a in args]))


class Not(Basic):
    def __new__(cls, arg):
        return wrap(_core.logical_not(_to_bool_arg(arg)))


class Xor(Basic):
    def __new__(cls, *args):
        if not args:
            return wrap(_core.false_const())
        return wrap(_core.logical_xor(*[_to_bool_arg(a) for a in args]))


class Nand(Basic):
    def __new__(cls, *args):
        return Not(And(*args))


class Nor(Basic):
    def __new__(cls, *args):
        return Not(Or(*args))


class Xnor(Basic):
    def __new__(cls, *args):
        return Not(Xor(*args))


class Contains(Basic):
    def __new__(cls, expr, set_expr):
        return wrap(_core.contains(_sympify(expr), _sympify(set_expr)))


# ---------------------------------------------------------------------------
# Free function re-exports (all auto-wrapping)
# ---------------------------------------------------------------------------

def _auto_wrap(fn):
    def wrapper(*args, **kwargs):
        coerced = [unwrap(_sympify(a)) for a in args]
        return wrap(fn(*coerced, **kwargs))
    return wrapper


# Factory functions
_symbol_raw = _core.symbol  # Internal use only

def symbol(name):
    return Symbol(name)

def integer(i):
    return wrap(_core.integer(i))


# Arithmetic
add = _auto_wrap(_core.add)
sub = _auto_wrap(_core.sub)
mul = _auto_wrap(_core.mul)
div = _auto_wrap(_core.div)
pow = _auto_wrap(_core.pow)
neg = _auto_wrap(_core.neg)
expand = _auto_wrap(_core.expand)

# Trigonometric, hyperbolic, and other math functions are defined dynamically
# in the _FUNC_CLASS_MAP loop above.
sqrt = _auto_wrap(_core.sqrt)
digamma = _auto_wrap(_core.digamma)
trigamma = _auto_wrap(_core.trigamma)
lambertw = LambertW
zeta = Zeta

# exp
try:
    exp = _auto_wrap(_core.exp)
except AttributeError:
    def exp(x):
        return Pow(_core.e(), _sympify(x))


# Number theory
def factorial(n):
    n = int(n)
    if n < 0:
        raise ArithmeticError("factorial: n must be >= 0")
    return wrap(_core.factorial(n))


def binomial(n, k):
    k = int(k)
    if k < 0:
        raise ArithmeticError("binomial: k must be >= 0")
    return wrap(_core.binomial(unwrap(_sympify(n)), k))


def fibonacci(n):
    n = int(n)
    if n < 0:
        raise NotImplementedError("fibonacci: n must be >= 0")
    return wrap(_core.fibonacci(n))


def lucas(n):
    n = int(n)
    if n < 0:
        raise NotImplementedError("lucas: n must be >= 0")
    return wrap(_core.lucas(n))


nextprime = _auto_wrap(_core.nextprime)
totient = lambda n: wrap(_core.totient(unwrap(_sympify(n))))
carmichael = lambda n: wrap(_core.carmichael(unwrap(_sympify(n))))
legendre = lambda a, n: wrap(_core.legendre(unwrap(_sympify(a)), unwrap(_sympify(n))))
jacobi = lambda a, n: wrap(_core.jacobi(unwrap(_sympify(a)), unwrap(_sympify(n))))
kronecker = lambda a, n: wrap(_core.kronecker(unwrap(_sympify(a)), unwrap(_sympify(n))))
divides = lambda a, b: wrap(_core.divides(unwrap(_sympify(a)), unwrap(_sympify(b))))
gcd = _auto_wrap(_core.gcd)
lcm = _auto_wrap(_core.lcm)


def bernoulli(n):
    n = int(n)
    if n < 0:
        raise ArithmeticError("bernoulli: n must be >= 0")
    return wrap(_core.bernoulli(n))


def harmonic(n, m=1):
    return wrap(_core.harmonic(int(n), int(m)))


def isprime(n, reps=25):
    return bool(_core.probab_prime_p(unwrap(_sympify(n)), reps))


def gcd_ext(a, b):
    g, s, t = _core.gcd_ext(unwrap(_sympify(a)), unwrap(_sympify(b)))
    return _wrap_nested((s, t, g))


mod = _raise_zerodiv(_auto_wrap(_core.mod_f))
quotient = _raise_zerodiv(_auto_wrap(_core.quotient_f))


def quotient_mod(a, b):
    try:
        q, r = _core.quotient_mod_f(unwrap(_sympify(a)), unwrap(_sympify(b)))
        return _wrap_nested((q, r))
    except RuntimeError as e:
        if "ZeroDivisionError" in str(e):
            raise ZeroDivisionError(str(e))
        raise


def fibonacci2(n):
    n = int(n)
    if n < 0:
        raise NotImplementedError("fibonacci2: n must be >= 0")
    return _wrap_nested(list(_core.fibonacci2(n)))


def lucas2(n):
    n = int(n)
    if n < 0:
        raise NotImplementedError("lucas2: n must be >= 0")
    return _wrap_nested(list(_core.lucas2(n)))


def mod_inverse(a, m):
    return wrap(_core.mod_inverse(unwrap(_sympify(a)), unwrap(_sympify(m))))


def crt(rem, mod):
    rem_i = [unwrap(_sympify(r)) for r in rem]
    mod_i = [unwrap(_sympify(m)) for m in mod]
    return wrap(_core.crt(rem_i, mod_i))


def prime_factors(n):
    return _wrap_nested(_core.prime_factors(unwrap(_sympify(n))))


def prime_factor_multiplicities(n):
    return _wrap_nested(_core.prime_factor_multiplicities(unwrap(_sympify(n))))


def primitive_root(n):
    return wrap(_core.primitive_root(unwrap(_sympify(n))))


def primitive_root_list(n):
    return _wrap_nested(_core.primitive_root_list(unwrap(_sympify(n))))


def multiplicative_order(a, n):
    return wrap(_core.multiplicative_order(unwrap(_sympify(a)), unwrap(_sympify(n))))


def nthroot_mod(a, n, m):
    return wrap(_core.nthroot_mod(unwrap(_sympify(a)), unwrap(_sympify(n)), unwrap(_sympify(m))))


def nthroot_mod_list(a, n, m):
    return _wrap_nested(_core.nthroot_mod_list(unwrap(_sympify(a)), unwrap(_sympify(n)), unwrap(_sympify(m))))


def powermod(a, b, m):
    return wrap(_core.powermod(unwrap(_sympify(a)), unwrap(_sympify(b)), unwrap(_sympify(m))))


def powermod_list(a, b, m):
    return _wrap_nested(_core.powermod_list(unwrap(_sympify(a)), unwrap(_sympify(b)), unwrap(_sympify(m))))


def factor(n, B1=1.0):
    result = _core.factor(unwrap(_sympify(n)), B1)
    if result is None:
        return None
    return wrap(result)


def factor_lehman_method(n):
    result = _core.factor_lehman_method(unwrap(_sympify(n)))
    if result is None:
        return None
    return wrap(result)


def factor_pollard_pm1_method(n, B=10, retries=5):
    result = _core.factor_pollard_pm1_method(unwrap(_sympify(n)), B, retries)
    if result is None:
        return None
    return wrap(result)


def factor_pollard_rho_method(n, retries=5):
    result = _core.factor_pollard_rho_method(unwrap(_sympify(n)), retries)
    if result is None:
        return None
    return wrap(result)


def sqrt_mod(a, p, all_roots=False):
    if all_roots:
        return nthroot_mod_list(a, _core.integer(2), p)
    return nthroot_mod(a, _core.integer(2), p)


def integer_nthroot(a, n):
    a = int(a)
    n = int(n)
    if a < 0:
        if n % 2 == 0:
            raise ValueError("even root of a negative is non-real")
        root, exact = integer_nthroot(-a, n)
        return -root, exact
    if a == 0:
        return wrap(_make_integer(0)), True
    if a == 1:
        return wrap(_make_integer(1)), True
    if n == 1:
        return wrap(_make_integer(a)), True
    bit_len = a.bit_length()
    guess_bits = (bit_len + n - 1) // n
    x = 1 << guess_bits
    while True:
        y = ((n - 1) * x + a // (x ** (n - 1))) // n
        if y >= x:
            break
        x = y
    return wrap(_make_integer(x)), x ** n == a


def is_square(n):
    return bool(_core.is_square(unwrap(_sympify(n))))


def perfect_power(n):
    return bool(_core.perfect_power(unwrap(_sympify(n))))


# Set factories
def finiteset(*args):
    return FiniteSet(*args)


def interval(start, end, left_open=False, right_open=False):
    return Interval(start, end, left_open, right_open)


def emptyset():
    return EmptySet()


def universalset():
    return UniversalSet()


def reals():
    return Reals()


def rationals():
    return Rationals()


def integers():
    return Integers()


def complexes():
    return Complexes()


def naturals():
    return Naturals()


def naturals0():
    return Naturals0()


def set_union(*args):
    return Union(*args)


def set_intersection(*args):
    return Intersection(*args)


def set_complement(universe, container):
    return Complement(universe, container)


def conditionset(sym, condition):
    return ConditionSet(sym, condition)


def imageset(sym, expr, base):
    return ImageSet(sym, expr, base)


# Additional function classes generated by litgen
class KroneckerDelta(Basic):
    def __new__(cls, x, y):
        import sympy
        from ._sympy_bridge import to_sympy, from_sympy
        return wrap(from_sympy(sympy.KroneckerDelta(to_sympy(x), to_sympy(y))))


class LeviCivita(Basic):
    def __new__(cls, *args):
        obj = object.__new__(cls)
        coerced = [_sympify(a) for a in args]
        for i_idx in range(len(coerced)):
            for j_idx in range(i_idx + 1, len(coerced)):
                if coerced[i_idx] == coerced[j_idx]:
                    obj._raw = _make_integer(0)
                    return obj
        all_int = all(isinstance(a, _core.Integer) for a in coerced)
        if all_int:
            vals = [int(str(a)) for a in coerced]
            if len(set(vals)) != len(vals):
                obj._raw = _make_integer(0)
                return obj
            inversions = 0
            n = len(vals)
            for i in range(n):
                for j in range(i + 1, n):
                    if vals[i] > vals[j]:
                        inversions += 1
            obj._raw = _make_integer(1 if inversions % 2 == 0 else -1)
            return obj
        obj._raw = _core.LeviCivita(coerced)
        return obj


import functools


def _compare_basics_rcp(a, b):
    ha = hash(a)
    hb = hash(b)
    if ha != hb:
        return -1 if ha < hb else 1
    if a == b:
        return 0
    type_a = a.__class__.__name__
    type_b = b.__class__.__name__
    if type_a != type_b:
        return -1 if type_a < type_b else 1
    raw_a = unwrap(a)
    raw_b = unwrap(b)
    return raw_a.compare(raw_b)


def _to_py_num(a):
    a = unwrap(a)
    name = a.__class__.__name__
    if name == 'Integer':
        return int(str(a))
    elif name == 'Rational':
        return Fraction(str(a))
    return float(str(a))


def _canonicalize_max_min(args, is_max=True):
    flat = []
    target_class_name = 'Max' if is_max else 'Min'
    for a in args:
        raw_a = unwrap(a)
        if raw_a.__class__.__name__ == target_class_name:
            flat.extend(_canonicalize_max_min(raw_a.get_args(), is_max))
        else:
            flat.append(a)
    unique = []
    for a in flat:
        raw_a = unwrap(a)
        if not any(raw_a == unwrap(x) for x in unique):
            unique.append(a)
    numbers = []
    non_numbers = []
    for a in unique:
        raw_a = unwrap(a)
        if isinstance(raw_a, (_core.Integer, _core.Rational, _core.RealDouble)):
            numbers.append(a)
        else:
            non_numbers.append(a)
    if numbers:
        numbers.sort(key=_to_py_num)
        extreme = numbers[-1] if is_max else numbers[0]
        if not non_numbers:
            return [extreme]
        unique = non_numbers + [extreme]
    unique.sort(key=functools.cmp_to_key(_compare_basics_rcp))
    return unique


class Max(Basic):
    def __new__(cls, *args):
        obj = object.__new__(cls)
        if len(args) == 1 and isinstance(args[0], (list, tuple)):
            coerced = [_sympify(a) for a in args[0]]
        else:
            coerced = [_sympify(a) for a in args]
        if coerced and all(a == coerced[0] for a in coerced):
            obj._raw = unwrap(coerced[0])
            return obj
        canonical = _canonicalize_max_min(coerced, is_max=True)
        if len(canonical) == 1:
            obj._raw = unwrap(canonical[0])
            return obj
        obj._raw = _core.Max([unwrap(c) for c in canonical])
        return obj


class Min(Basic):
    def __new__(cls, *args):
        obj = object.__new__(cls)
        if len(args) == 1 and isinstance(args[0], (list, tuple)):
            coerced = [_sympify(a) for a in args[0]]
        else:
            coerced = [_sympify(a) for a in args]
        if coerced and all(a == coerced[0] for a in coerced):
            obj._raw = unwrap(coerced[0])
            return obj
        canonical = _canonicalize_max_min(coerced, is_max=False)
        if len(canonical) == 1:
            obj._raw = unwrap(canonical[0])
            return obj
        obj._raw = _core.Min([unwrap(c) for c in canonical])
        return obj


# ---------------------------------------------------------------------------
# Stubs for not-yet-implemented names
# ---------------------------------------------------------------------------

class Sieve:
    @staticmethod
    def generate_primes(limit):
        if limit < 2:
            return []
        sieve = [True] * (limit + 1)
        sieve[0] = sieve[1] = False
        for i in range(2, int(limit**0.5) + 1):
            if sieve[i]:
                for j in range(i*i, limit + 1, i):
                    sieve[j] = False
        return [i for i in range(2, limit + 1) if sieve[i]]


class Sieve_iterator:
    def __init__(self, limit):
        self._primes = Sieve.generate_primes(limit)
        self._index = 0
    def __iter__(self):
        return self
    def __next__(self):
        if self._index >= len(self._primes):
            raise StopIteration
        val = self._primes[self._index]
        self._index += 1
        return val


class Float(Basic):
    def __new__(cls, val, precision=None, dps=None):
        from ._constants import have_mpfr
        if precision is not None and dps is not None:
            raise ValueError("Cannot specify both precision and dps")
        if precision is not None and precision > 53 and not have_mpfr:
            raise ValueError("MPFR precision not available")
        if dps is not None:
            import math
            prec = int(math.ceil(dps * 3.3219280948873626))
            if prec > 53 and not have_mpfr:
                raise ValueError("MPFR precision not available")
            return RealDouble(float(val))
        return RealDouble(float(val))


class RealDouble(Basic):
    def __new__(cls, val):
        obj = object.__new__(cls)
        obj._raw = _sympify(float(val))
        return obj

    @property
    def real(self):
        return self

    @property
    def imag(self):
        return wrap(_core.real_double(0.0))


class ComplexDouble(Basic):
    def __new__(cls, real, imag=0):
        obj = object.__new__(cls)
        real_raw = unwrap(_sympify(real))
        imag_raw = unwrap(_sympify(imag))
        obj._raw = _core.add(real_raw, _core.mul(imag_raw, _core.I()))
        return obj


RealMPFR = _missing_class("RealMPFR", ImportError)
ComplexMPC = _missing_class("ComplexMPC", ImportError)

Rational_type = _missing("Rational_type")


def series(expr, x, n=6):
    expr_raw = unwrap(_sympify(expr))
    x_raw = unwrap(_sympify(x))
    if not isinstance(x_raw, _core.Symbol):
        raise TypeError("series expansion variable must be a Symbol")
    return wrap(_core.series(expr_raw, x_raw, int(n)))


def diff(expr, *symbols):
    expr_raw = unwrap(_sympify(expr))
    if not symbols:
        return wrap(expr_raw)
    result = expr_raw
    i = 0
    while i < len(symbols):
        sym = unwrap(_sympify(symbols[i]))
        i += 1
        if not isinstance(sym, (_core.Symbol, _core.Dummy)):
            raise ValueError(
                f"diff: expected a Symbol, got {type(sym).__name__}"
            )
        count = 1
        if i < len(symbols) and isinstance(symbols[i], int):
            count = symbols[i]
            i += 1
        for _ in range(count):
            result = _core.diff(result, sym)
    return wrap(result)


limit = _missing("limit")


def solve(f, sym, domain=None):
    f_raw = unwrap(_sympify(f))
    if domain is None:
        domain_raw = _core.universalset()
    else:
        domain_raw = unwrap(domain)
    if isinstance(sym, (list, tuple)):
        if len(sym) == 1:
            return wrap(_core.solve(f_raw, unwrap(sym[0]), domain_raw))
        raise NotImplementedError("solve with multiple symbols not supported yet")
    return wrap(_core.solve(f_raw, unwrap(sym), domain_raw))


def linsolve(system, syms):
    coerced_eqns = [unwrap(_sympify(eq)) for eq in system]
    coerced_syms = [unwrap(_sympify(s)) for s in syms]
    result = _core.linsolve(coerced_eqns, coerced_syms)
    return tuple(wrap(r) for r in result)


class Function:
    def __new__(cls, name, *args):
        if args:
            raise TypeError(
                f"Function() takes only one argument (the function name); "
                f"call the result with arguments, e.g. Function('f')(x)"
            )
        if not isinstance(name, str):
            raise TypeError("Function() argument must be a string")
        class _Func:
            _name = name
            def __call__(self, *fargs):
                coerced = [unwrap(_sympify(a)) for a in fargs]
                return wrap(_core.function_symbol(self._name, *coerced))
            def __repr__(self):
                return f"Function('{self._name}')"
        return _Func()


def function_symbol(name, *args):
    coerced = [unwrap(_sympify(a)) for a in args]
    return wrap(_core.function_symbol(name, *coerced))


Symbol_function = _missing("Symbol_function")
Lambda = _missing("Lambda")


def Piecewise(*pieces):
    import sympy
    from ._sympy_bridge import to_sympy, from_sympy
    sp_pieces = []
    for expr, cond in pieces:
        sp_expr = to_sympy(unwrap(_sympify(expr)))
        if cond is True:
            sp_cond = sympy.true
        elif cond is False:
            sp_cond = sympy.false
        else:
            sp_cond = to_sympy(unwrap(_sympify(cond)))
        sp_pieces.append((sp_expr, sp_cond))
    result = sympy.Piecewise(*sp_pieces)
    if not hasattr(result, '_sympy_'):
        result._sympy_ = lambda self=result: self
    return result


Sum = _missing("Sum")
Product = _missing("Product")
Integral = _missing("Integral")


class Derivative(Basic):
    def __new__(cls, expr, *args):
        obj = object.__new__(cls)
        expr_raw = unwrap(_sympify(expr))
        symbols = []
        i = 0
        while i < len(args):
            sym = unwrap(_sympify(args[i]))
            i += 1
            if not isinstance(sym, (_core.Symbol, _core.Dummy)):
                raise ValueError(
                    f"Derivative: expected a Symbol, got {type(sym).__name__}"
                )
            count = 1
            if i < len(args) and isinstance(args[i], int):
                count = args[i]
                i += 1
            if count == 0:
                continue
            if count < 0:
                raise ValueError("Derivative count must be non-negative")
            for _ in range(count):
                symbols.append(sym)
        if not symbols:
            obj._raw = expr_raw
            return obj
        obj._raw = _core._make_derivative(expr_raw, symbols)
        return obj

    @property
    def expr(self):
        return wrap(self._raw.get_arg())

    @property
    def variables(self):
        return tuple(wrap(s) for s in self._raw.get_symbols())


class Subs(Basic):
    def __new__(cls, expr, variables, points):
        obj = object.__new__(cls)
        expr_raw = unwrap(_sympify(expr))
        if isinstance(variables, (list, tuple)):
            vars_list = [unwrap(_sympify(v)) for v in variables]
        else:
            vars_list = [unwrap(_sympify(variables))]
        if isinstance(points, (list, tuple)):
            pts_list = [unwrap(_sympify(p)) for p in points]
        else:
            pts_list = [unwrap(_sympify(points))]
        if len(vars_list) != len(pts_list):
            raise ValueError("Subs: variables and points must have the same length")
        mapping = dict(zip(vars_list, pts_list))
        obj._raw = _core._make_subs(expr_raw, mapping)
        return obj

    @property
    def expr(self):
        return wrap(self._raw.get_arg())

    @property
    def variables(self):
        return tuple(wrap(v) for v in self._raw.get_variables())

    @property
    def point(self):
        return tuple(wrap(p) for p in self._raw.get_point())


class UnevaluatedExpr(Basic):
    def __new__(cls, expr):
        obj = object.__new__(cls)
        obj._raw = _core.unevaluated_expr(unwrap(_sympify(expr)))
        return obj

    @property
    def is_number(self):
        args = self._raw.get_args()
        if args:
            return isinstance(args[0], (_core.Number, _core.Constant))
        return False

    @property
    def is_integer(self):
        args = self._raw.get_args()
        if args:
            return isinstance(args[0], _core.Integer)
        return False

    @property
    def is_finite(self):
        args = self._raw.get_args()
        if not args:
            return None
        arg0 = args[0]
        if isinstance(arg0, _core.Number):
            return True
        if arg0 in (_core.oo(), _core.zoo(), _core.nan_const()):
            return False
        return None


def subs(expr, *args, **kwargs):
    expr_w = expr if isinstance(expr, Basic) else wrap(unwrap(_sympify(expr)))
    raw = expr_w._raw
    if len(args) == 1 and isinstance(args[0], (dict, DictBasic)):
        mapping = {unwrap(_sympify(k)): unwrap(_sympify(v)) for k, v in args[0].items()}
    elif len(args) == 2:
        mapping = {unwrap(_sympify(args[0])): unwrap(_sympify(args[1]))}
    elif len(args) == 0:
        mapping = {unwrap(_sympify(k)): unwrap(_sympify(v)) for k, v in kwargs.items()}
    else:
        raise TypeError(
            f"subs() takes 1 positional argument (a dict) or 2 positional arguments "
            f"(old, new); got {len(args) + 1}"
        )
    if not mapping:
        return expr_w

    def has_function_symbol(e):
        if not isinstance(e, _core.Basic):
            return False
        if e.__class__.__name__ == 'FunctionSymbol':
            return True
        try:
            return any(has_function_symbol(arg) for arg in e.get_args())
        except Exception:
            return False

    has_fs = has_function_symbol(raw) or any(has_function_symbol(v) for v in mapping.values())
    if not has_fs:
        res = _core.subs(raw, mapping)
        if not has_function_symbol(res):
            return wrap(res)

    from ._sympy_bridge import to_sympy, from_sympy
    try:
        expr_sp = to_sympy(raw)
        mapping_sp = {to_sympy(k): to_sympy(v) for k, v in mapping.items()}
        res_sp = expr_sp.subs(mapping_sp)
        return wrap(from_sympy(res_sp))
    except Exception:
        return wrap(_core.subs(raw, mapping))


class DictBasic(collections.abc.MutableMapping):
    def __init__(self, *args, **kwargs):
        self._dict = {}
        if args:
            if isinstance(args[0], (dict, collections.abc.Mapping)):
                for k, v in args[0].items():
                    self[unwrap(_sympify(k))] = unwrap(_sympify(v))
            elif isinstance(args[0], DictBasic):
                for k, v in args[0].items():
                    self[unwrap(_sympify(k))] = unwrap(_sympify(v))
        for k, v in kwargs.items():
            self[unwrap(_sympify(k))] = unwrap(_sympify(v))

    def __getitem__(self, key):
        return wrap(self._dict[unwrap(_sympify(key))])

    def __setitem__(self, key, value):
        self._dict[unwrap(_sympify(key))] = unwrap(_sympify(value))

    def __delitem__(self, key):
        del self._dict[unwrap(_sympify(key))]

    def __iter__(self):
        return (wrap(k) for k in self._dict)

    def __len__(self):
        return len(self._dict)

    def __repr__(self):
        items = ', '.join(f'{wrap(k)}: {wrap(v)}' for k, v in self._dict.items())
        return '{' + items + '}'

    def __str__(self):
        return self.__repr__()

    def __eq__(self, other):
        if isinstance(other, DictBasic):
            return self._dict == other._dict
        return NotImplemented

    def __hash__(self):
        return hash(tuple(sorted(self._dict.items(), key=lambda kv: hash(kv[0]))))


def symarray(prefix, shape, **kwargs):
    import numpy as np
    if isinstance(shape, (int,)):
        shape = (shape,)
    elif not isinstance(shape, tuple):
        shape = tuple(shape)
    arr = np.empty(shape, dtype=object)
    for index in np.ndindex(shape):
        arr[index] = Symbol('%s_%s' % (prefix, '_'.join(map(str, index))), **kwargs)
    return arr


def cse(exprs):
    coerced = [unwrap(_sympify(e)) for e in exprs]
    replacements, reduced = _core.cse(coerced)
    return ([(sym, wrap(expr)) for sym, expr in replacements], [wrap(r) for r in reduced])


# ---------------------------------------------------------------------------
# Pure-Python helper functions -- ported from legacy symengine
# ---------------------------------------------------------------------------

def has_symbol(expr, sym):
    if isinstance(expr, Basic):
        raw = expr._raw
    elif isinstance(expr, _core.Basic):
        raw = expr
    else:
        return False
    if isinstance(sym, str):
        sym_raw = _symbol_raw(sym)
    elif isinstance(sym, Basic):
        sym_raw = sym._raw
    else:
        sym_raw = sym
    if raw == sym_raw:
        return True
    for arg in raw.get_args():
        if has_symbol(wrap(arg), sym):
            return True
    return False


def count_ops(*args, visual=None):
    if len(args) == 0:
        return 0
    if len(args) == 1:
        result = args[0]
    else:
        result = args

    def _count(expr):
        if isinstance(expr, Basic):
            raw = expr._raw
        elif isinstance(expr, _core.Basic):
            raw = expr
        else:
            return 0
        name = raw.__class__.__name__
        if name in ('Symbol', 'Integer', 'Rational', 'Complex', 'Constant', 'Dummy'):
            return 0
        elif name in ('Add', 'Mul'):
            args_list = raw.get_args()
            if not args_list:
                return 0
            c = 0
            for a in args_list:
                if isinstance(a, (_core.Integer, _core.Rational)):
                    c += 1
                else:
                    c += _count(wrap(a)) + 1
            return c - 1
        elif name == 'Pow':
            args_list = raw.get_args()
            if len(args_list) == 2:
                return 1 + _count(wrap(args_list[0])) + _count(wrap(args_list[1]))
            return 1
        else:
            args_list = raw.get_args()
            return 1 + sum(_count(wrap(a)) for a in args_list)

    if isinstance(result, Basic):
        return _count(result)
    if isinstance(result, (list, tuple)):
        total = 0
        for item in result:
            total += count_ops(item)
        return total
    return 0


# ---------------------------------------------------------------------------
# symbols() helper -- ported from legacy symengine
# ---------------------------------------------------------------------------

_range = re.compile(r'([0-9]*:[0-9]+|[a-zA-Z]?:[a-zA-Z])')


def symbols(names, **args):
    result = []

    if isinstance(names, str):
        marker = 0
        literals = [r'\,', r'\:', r'\ ']
        for i in range(len(literals)):
            lit = literals.pop(0)
            if lit in names:
                while chr(marker) in names:
                    marker += 1
                lit_char = chr(marker)
                marker += 1
                names = names.replace(lit, lit_char)
                literals.append((lit_char, lit[1:]))

        def literal(s):
            if literals:
                for c, l in literals:
                    s = s.replace(c, l)
            return s

        names = names.strip()
        as_seq = names.endswith(',')
        if as_seq:
            names = names[:-1].rstrip()
        if not names:
            raise ValueError('no symbols given')

        names = [n.strip() for n in names.split(',')]
        if not all(n for n in names):
            raise ValueError('missing symbol between commas')
        for i in range(len(names) - 1, -1, -1):
            names[i: i + 1] = names[i].split()

        cls = args.pop('cls', Symbol)
        seq = args.pop('seq', as_seq)

        for name in names:
            if not name:
                raise ValueError('missing symbol')
            if ':' not in name:
                symbol = cls(literal(name), **args)
                result.append(symbol)
                continue

            split = _range.split(name)
            for i in range(len(split) - 1):
                if i and ':' in split[i] and split[i] != ':' and \
                        split[i - 1].endswith('(') and \
                        split[i + 1].startswith(')'):
                    split[i - 1] = split[i - 1][:-1]
                    split[i + 1] = split[i + 1][1:]
            for i, s in enumerate(split):
                if ':' in s:
                    if s[-1].endswith(':'):
                        raise ValueError('missing end range')
                    a, b = s.split(':')
                    if b[-1] in string.digits:
                        a = 0 if not a else int(a)
                        b = int(b)
                        split[i] = [str(c) for c in range(a, b)]
                    else:
                        a = a or 'a'
                        split[i] = [string.ascii_letters[c] for c in range(
                            string.ascii_letters.index(a),
                            string.ascii_letters.index(b) + 1)]
                    if not split[i]:
                        break
                else:
                    split[i] = [s]
            else:
                seq = True
                if len(split) == 1:
                    names = split[0]
                else:
                    names = [''.join(s) for s in cartes(*split)]
                if literals:
                    result.extend([cls(literal(s), **args) for s in names])
                else:
                    result.extend([cls(s, **args) for s in names])

        if not seq and len(result) <= 1:
            if not result:
                return ()
            return result[0]
        return tuple(result)
    else:
        for name in names:
            result.append(symbols(name, **args))
        return type(names)(result)


# ---------------------------------------------------------------------------
# var() -- inject symbols into caller's globals
# ---------------------------------------------------------------------------

def var(names, **args):
    def traverse(symbols, frame):
        for symbol in symbols:
            if isinstance(symbol, Basic):
                frame.f_globals[symbol.__str__()] = symbol
            else:
                traverse(symbol, frame)

    from inspect import currentframe
    frame = currentframe().f_back
    try:
        syms = symbols(names, **args)
        if syms is not None:
            if isinstance(syms, Basic):
                frame.f_globals[syms.__str__()] = syms
            else:
                traverse(syms, frame)
    finally:
        del frame
    return syms


# Populate the map at module load time
_init_wrapper_map()
del _init_wrapper_map

_SINGLETON_CLASSES.extend([
    EmptySet,
    UniversalSet,
    Reals,
    Integers,
    Rationals,
])
