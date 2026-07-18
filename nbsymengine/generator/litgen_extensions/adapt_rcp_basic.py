"""Custom litgen adapter: RCP<const Basic> handling.

Phase 6: The default strategy is pass-through -- the type_caster<RCP<T>>
from nanobind_symengine.h handles RCP<const Basic> parameters and returns
directly, preserving object identity and polymorphic typing.

The Expression adapter remains available for specific functions where a
value type is genuinely nicer (controlled by _EXPRESSION_ALLOW_LIST).
"""
from __future__ import annotations

import copy
from typing import Optional

from litgen.internal.adapt_function_params._lambda_adapter import LambdaAdapter
from srcmlcpp.cpp_types import CppType


def _is_rcp_basic_type(type_str: str) -> bool:
    """Check if a type string contains RCP<const Basic> or variants."""
    t = type_str.replace(" ", "")
    targets = [
        "RCP<constBasic>",
        "RCP<constSymEngine::Basic>",
        "RCP<Basic>",
        "RCP<constNumber>",
        "RCP<constSymEngine::Number>",
        "RCP<constSymbol>",
        "RCP<constSymEngine::Symbol>",
        "RCP<constInteger>",
        "RCP<constSymEngine::Integer>",
    ]
    return any(tok in t for tok in targets)


# Functions that should still use Expression wrapping for ergonomics.
# Add function names here if a value-type boundary is genuinely nicer.
_EXPRESSION_ALLOW_LIST: set[str] = set()


def adapt_rcp_basic(adapted_function) -> Optional[LambdaAdapter]:
    """Default adapter: pass-through for RCP<const Basic>.

    Returns None for all functions, letting the type_caster<RCP<T>> handle
    RCP<const Basic> parameters and returns directly. This preserves object
    identity (self_external()) and polymorphic RTTI downcasting.
    """
    return None


def adapt_rcp_basic_to_expression(adapted_function) -> Optional[LambdaAdapter]:
    """Rewrite RCP<const Basic> returns to Expression.

    Only applies to functions in _EXPRESSION_ALLOW_LIST. Returns None
    (pass-through) for all other functions.
    """
    cpp_fn = adapted_function.cpp_adapted_function
    if cpp_fn is None:
        return None

    # Only adapt functions in the allow-list
    if cpp_fn.function_name not in _EXPRESSION_ALLOW_LIST:
        return None

    # Only adapt free functions (not constructors, not methods for now)
    if cpp_fn.is_constructor():
        return None

    # Check return type
    if not cpp_fn.has_return_type():
        return None

    ret_str = cpp_fn.return_type.str_code()
    if not _is_rcp_basic_type(ret_str):
        return None

    adapter = LambdaAdapter()
    adapter.lambda_name = cpp_fn.function_name + "_expression_adapter"

    new_infos = copy.deepcopy(cpp_fn)

    # Rewrite return type to Expression
    new_infos.return_type = CppType(new_infos.return_type)
    new_infos.return_type.typenames = ["SymEngine::Expression"]

    # The lambda_result is RCP<const Basic>, wrap it
    adapter.lambda_output_code = "return SymEngine::Expression(lambda_result);"

    # Pass through all parameters unchanged
    adapted_params = []
    for p in cpp_fn.parameter_list.parameters:
        adapted_params.append(p.decl.decl_name)

    adapter.new_function_infos = new_infos
    adapter.adapted_cpp_parameter_list = adapted_params

    return adapter
