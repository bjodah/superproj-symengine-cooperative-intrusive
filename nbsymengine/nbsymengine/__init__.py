"""nbsymengine -- nanobind/litgen-generated bindings for SymEngine.

Requires Python >= 3.13.
"""

from . import _core

# Explicit imports for names our tests rely on -- if _core drops any of
# these the import will fail loudly rather than producing a silent
# AttributeError at use-time.
from ._core import (
    Basic,
    Boolean,
    Integer,
    Number,
    Rational,
    Set,
    Symbol,
    add,
    div,
    expand,
    integer,
    mul,
    neg,
    pow,
    str,
    sub,
    symbol,
    zero,
    one,
    pi,
    e,
    euler_gamma,
    Eq,
    Ne,
    Ge,
    Gt,
    Le,
    Lt,
)

# Re-export every public name from the extension so that
# ``import nbsymengine as sx; sx.sin(...)`` works without manual
# maintenance of the full name list.
globals().update({name: getattr(_core, name) for name in dir(_core) if not name.startswith("_")})

# Import the lambdify submodule, then extract the callable names.
# We use ``import ... as _lambdify_mod`` to avoid the submodule
# overwriting the ``lambdify`` function name at package level.
from . import lambdify as _lambdify_mod
Lambdify = _lambdify_mod.Lambdify
LambdifyCSE = _lambdify_mod.LambdifyCSE
lambdify = _lambdify_mod.lambdify

__all__ = [name for name in dir(_core) if not name.startswith("_")]
__all__.extend(["Lambdify", "LambdifyCSE", "lambdify"])
__version__ = _core.__version__ if hasattr(_core, "__version__") else "0.0.0"
