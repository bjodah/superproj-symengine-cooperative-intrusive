"""Render the mechanical PHP extension module functions and declarations."""

from __future__ import annotations

from .model import BindingSpec, Function
from .render_common import cpp_call, functions_for_language, header


SUPPORTED_FAMILIES = frozenset((
    "singleton", "unary_basic", "binary_basic", "binary_boolean",
    "integer_unary", "integer_binary",
))


def php_functions(spec: BindingSpec) -> tuple[Function, ...]:
    """Return generated PHP entries in a stable order or name the gap."""
    return functions_for_language(spec, "php", SUPPORTED_FAMILIES)


def _arginfo_name(function: Function) -> str:
    return f"arginfo_{function.public_name('php')}"


def render_php_inc(spec: BindingSpec) -> str:
    """Render arginfo plus handlers; Zend ownership remains in runtime helpers."""
    lines = header(spec, "//")
    lines.append("// Included by symengine_php.cpp.")
    for function in php_functions(spec):
        name = function.public_name("php")
        arginfo = _arginfo_name(function)
        count = len(function.arguments)
        lines.extend([
            "",
            f"ZEND_BEGIN_ARG_WITH_RETURN_OBJ_INFO_EX({arginfo}, 0, {count}, SymEngine\\\\Basic, 0)",
        ])
        for argument in function.arguments:
            lines.append(
                f"    ZEND_ARG_OBJ_INFO(0, {argument.name}, SymEngine\\\\Basic, 0)"
            )
        lines.append("ZEND_END_ARG_INFO()")
        lines.extend(["", f"PHP_FUNCTION({name})", "{"])
        prologue, call = cpp_call(
            function, lambda argument: f"symengine_unwrap_basic({argument.name})"
        )
        if function.behavior == "singleton":
            lines.extend([
                "    ZEND_PARSE_PARAMETERS_NONE();",
                f"    symengine_wrap_basic(return_value, {call});",
            ])
        else:
            for argument in function.arguments:
                lines.append(f"    zval *{argument.name};")
            parse = "".join("O" for _ in function.arguments)
            parse_arguments = ", ".join(
                item
                for argument in function.arguments
                for item in (f"&{argument.name}", "symengine_ce_basic")
            )
            lines.extend([
                "",
                f'    if (zend_parse_parameters(ZEND_NUM_ARGS(), "{parse}", {parse_arguments}) == FAILURE) {{',
                "        RETURN_THROWS();",
                "    }",
                "",
                "    try {",
            ])
            lines.extend(prologue)
            lines.extend([
                f"        symengine_wrap_basic(return_value, {call});",
                "    } catch (const std::exception &error) {",
                "        symengine_throw_cpp_exception(error);",
                "        RETURN_THROWS();",
                "    }",
            ])
        lines.append("}")
    return "\n".join(lines) + "\n"


def render_php_function_table_inc(spec: BindingSpec) -> str:
    lines = header(spec, "//")
    lines.append("// Included in symengine_functions.")
    lines.extend(
        f"    PHP_FE({function.public_name('php')}, {_arginfo_name(function)})"
        for function in php_functions(spec)
    )
    return "\n".join(lines) + "\n"


def render_php_stub(spec: BindingSpec) -> str:
    """Render an IDE-visible declaration source from the same signatures."""
    lines = header(spec, "//")
    lines.extend(["<?php", "", "// Generated declaration source; runtime arginfo is emitted in C++."])
    for function in php_functions(spec):
        parameters = ", ".join(
            f"SymEngine\\Basic ${argument.name}" for argument in function.arguments
        )
        lines.append(
            f"function {function.public_name('php')}({parameters}): SymEngine\\Basic {{}}"
        )
    return "\n".join(lines) + "\n"
