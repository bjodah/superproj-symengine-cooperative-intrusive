"""nbsymengine_compat._monkeypatch -- No-op placeholder.

All compat-layer functionality has been moved to the delegation wrapper
classes in ``_wrappers.py``.  No monkey-patching of ``_core`` types is
performed.  This module exists for backward compatibility — it exports
the public function names that the legacy facade re-exports.
"""
from __future__ import annotations

import collections as _collections
import logging as _logging

from nbsymengine import _core

_log = _logging.getLogger(__name__)

# Re-export compatibility names that the public surface test expects.
# These are thin wrappers around the Basic wrapper methods or raw _core calls.

def apply_compat_patches():
    """No-op: all compat functionality is on the delegation wrapper classes."""
    _log.debug("Compat monkey-patches skipped (delegation wrappers in use)")


# ---------------------------------------------------------------------------
# Stub exports for public surface compatibility
# ---------------------------------------------------------------------------

def basic_as_powers_dict(self):
    d = _collections.defaultdict(int)
    d[self] = 1
    return d


def pow_as_powers_dict(self):
    d = _collections.defaultdict(int)
    base, exp = self.get_args()
    d[base] = exp
    return d


def mul_as_powers_dict(self):
    d = _collections.defaultdict(int)
    for arg in self.get_args():
        if isinstance(arg, (_core.Integer, _core.Rational)):
            from ._monkeypatch import basic_as_powers_dict
            d.update(basic_as_powers_dict(arg))
        elif isinstance(arg, _core.Pow):
            from ._monkeypatch import pow_as_powers_dict
            pwr = type('Pow', (), {'get_args': lambda s=arg: arg.get_args()})()
            d.update(pow_as_powers_dict(pwr))
        else:
            d[arg] += 1
    return d


def basic_as_coefficients_dict(self):
    d = _collections.defaultdict(int)
    d[self] = 1
    return d


def add_as_coefficients_dict(self):
    d = _collections.defaultdict(int)
    d[_core.integer(1)] = _core.zero()
    for arg in self.get_args():
        if isinstance(arg, _core.Mul):
            mul_args = arg.get_args()
            if isinstance(mul_args[0], (_core.Integer, _core.Rational, _core.RealDouble)):
                coeff = mul_args[0]
                base = _core.mul(*mul_args[1:]) if len(mul_args) > 1 else _core.integer(1)
            else:
                coeff = _core.integer(1)
                base = arg
            d[base] = coeff
        elif isinstance(arg, (_core.Integer, _core.Rational, _core.RealDouble)):
            d[_core.integer(1)] = arg
        else:
            d[arg] = _core.integer(1)
    return d


def mul_as_coefficients_dict(self):
    d = _collections.defaultdict(int)
    args = self.get_args()
    if isinstance(args[0], (_core.Integer, _core.Rational, _core.RealDouble)):
        coef = args[0]
        base = _core.mul(*args[1:]) if len(args) > 1 else _core.integer(1)
    else:
        coef = _core.integer(1)
        base = self
    d[base] = coef
    return d


def basic_as_numer_denom(self):
    return self, _core.integer(1)


def basic_as_real_imag(self):
    conj = _core.conjugate(self)
    real_part = _core.div(_core.add(self, conj), _core.integer(2))
    imag_part = _core.div(_core.sub(self, conj), _core.mul(_core.integer(2), _core.I()))
    return real_part, imag_part


def basic_atoms(self, *types):
    if not types:
        return set()
    s = set()
    if isinstance(self, types):
        s.add(self)
    for arg in self.get_args():
        s.update(basic_atoms(arg, *types))
    return s


def basic_diff(self, *symbols):
    from ._wrappers import diff
    return diff(self, *symbols)


def basic_eq(self, other):
    from ._expr import sympify as _s
    try:
        other = _s(other)
    except Exception:
        pass
    return self == other


def basic_free_symbols(self):
    syms = set()
    def walk(expr):
        if expr.__class__.__name__ in ('Symbol', 'Dummy'):
            syms.add(expr)
        else:
            for arg in expr.get_args():
                walk(arg)
    walk(self)
    return syms


def basic_has(self, *args):
    for arg in args:
        if has_basic(self, arg):
            return True
    return False


def basic_msubs(self, mapping):
    from ._helpers import _sympify
    coerced = {_sympify(k): _sympify(v) for k, v in mapping.items()}
    return _core.msubs(self, coerced)


def basic_n(self, prec=53, real=None):
    from ._wrappers import Basic
    w = Basic.__new__(Basic)
    w._raw = self
    return w.n(prec=prec, real=real)


def basic_ne(self, other):
    from ._expr import sympify as _s
    try:
        other = _s(other)
    except Exception:
        pass
    return self != other


def basic_subs(self, *args, **kwargs):
    from ._wrappers import subs
    return subs(self, *args, **kwargs)


def basic_xreplace(self, mapping):
    from ._helpers import _sympify
    coerced = {_sympify(k): _sympify(v) for k, v in mapping.items()}
    return _core.xreplace(self, coerced)


def has_basic(expr, looking_for):
    from ._helpers import _sympify
    expr = _sympify(expr)
    looking_for = _sympify(looking_for)
    if isinstance(looking_for, (_core.Add, _core.Mul)):
        raise NotImplementedError(
            "Associative classes not yet handled in HasBasicVisitor"
        )
    if expr == looking_for:
        return True
    for arg in expr.get_args():
        if has_basic(arg, looking_for):
            return True
    return False
