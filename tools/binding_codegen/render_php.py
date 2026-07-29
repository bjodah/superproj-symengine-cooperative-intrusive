"""Render the mechanical PHP extension module functions and declarations."""

from __future__ import annotations

from .model import Argument, BindingSpec, Function
from .render_common import (
    RESULT_SHAPES,
    SCALAR_TYPES,
    cpp_result,
    functions_for_language,
    header,
)


SUPPORTED_FAMILIES = frozenset((
    "singleton", "unary_basic", "binary_basic", "binary_boolean",
    "integer_unary", "integer_binary", "status_optional_unary",
    "list_integer_to_basic",
))

# Zend spellings of the spec's non-handle argument types: the declared arginfo
# type, the zend_parse_parameters format letter, and the C local it fills.
PHP_SCALARS = {
    "double": ("IS_DOUBLE", "d", "double"),
    "unsigned": ("IS_LONG", "l", "zend_long"),
}


def php_functions(spec: BindingSpec) -> tuple[Function, ...]:
    """Return generated PHP entries in a stable order or name the gap."""
    return functions_for_language(spec, "php", SUPPORTED_FAMILIES)


def _arginfo_name(function: Function) -> str:
    return f"arginfo_{function.public_name('php')}"


def _argument_info(argument: Argument) -> str:
    if argument.type_id in SCALAR_TYPES:
        return f"    ZEND_ARG_TYPE_INFO(0, {argument.name}, {PHP_SCALARS[argument.type_id][0]}, 0)"
    return f"    ZEND_ARG_OBJ_INFO(0, {argument.name}, SymEngine\\\\Basic, 0)"


def _local(argument: Argument) -> str:
    if argument.type_id in SCALAR_TYPES:
        return f"    {PHP_SCALARS[argument.type_id][2]} {argument.name};"
    return f"    zval *{argument.name};"


def _parse_spec(function: Function) -> str:
    return "".join(
        PHP_SCALARS[argument.type_id][1] if argument.type_id in SCALAR_TYPES else "O"
        for argument in function.arguments
    )


def _parse_arguments(function: Function) -> str:
    items: list[str] = []
    for argument in function.arguments:
        items.append(f"&{argument.name}")
        if argument.type_id not in SCALAR_TYPES:
            items.append("symengine_ce_basic")
    return ", ".join(items)


def render_php_inc(spec: BindingSpec) -> str:
    """Render arginfo plus handlers; Zend ownership remains in runtime helpers."""
    lines = header(spec, "//")
    lines.append("// Included by symengine_php.cpp.")
    for function in php_functions(spec):
        name = function.public_name("php")
        arginfo = _arginfo_name(function)
        count = len(function.arguments)
        result = cpp_result(
            function, lambda argument: f"symengine_unwrap_basic({argument.name})"
        )
        lines.append("")
        if result.shape == "list":
            lines.append(
                f"ZEND_BEGIN_ARG_WITH_RETURN_TYPE_INFO_EX({arginfo}, 0, {count}, IS_ARRAY, 0)"
            )
        else:
            # The trailing flag is Zend's "may return null"; only the optional
            # family can, and it is how Python's None is spelled here.
            nullable = 1 if result.shape == "optional" else 0
            lines.append(
                f"ZEND_BEGIN_ARG_WITH_RETURN_OBJ_INFO_EX({arginfo}, 0, {count}, "
                f"SymEngine\\\\Basic, {nullable})"
            )
        lines.extend(_argument_info(argument) for argument in function.arguments)
        lines.append("ZEND_END_ARG_INFO()")
        lines.extend(["", f"PHP_FUNCTION({name})", "{"])
        if function.behavior == "singleton":
            lines.extend([
                "    ZEND_PARSE_PARAMETERS_NONE();",
                f"    symengine_wrap_basic(return_value, {result.value});",
            ])
        else:
            lines.extend(_local(argument) for argument in function.arguments)
            lines.extend([
                "",
                f'    if (zend_parse_parameters(ZEND_NUM_ARGS(), "{_parse_spec(function)}", '
                f"{_parse_arguments(function)}) == FAILURE) {{",
                "        RETURN_THROWS();",
                "    }",
                "",
                "    try {",
            ])
            lines.extend(result.statements)
            if result.shape == "optional":
                lines.extend([
                    f"        if (!{result.found}) {{",
                    "            RETURN_NULL();",
                    "        }",
                    f"        symengine_wrap_basic(return_value, {result.value});",
                ])
            elif result.shape == "list":
                lines.append(f"        symengine_wrap_basic_list(return_value, {result.value});")
            else:
                lines.append(f"        symengine_wrap_basic(return_value, {result.value});")
            lines.extend([
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


_PHP_STUB_TYPES = {"double": "float", "unsigned": "int"}
_PHP_STUB_RETURNS = {
    "handle": "SymEngine\\Basic",
    "optional": "?SymEngine\\Basic",
    "list": "array",
}


def _stub_parameter(argument: Argument) -> str:
    if argument.type_id in SCALAR_TYPES:
        return f"{_PHP_STUB_TYPES[argument.type_id]} ${argument.name}"
    return f"SymEngine\\Basic ${argument.name}"


def render_php_stub(spec: BindingSpec) -> str:
    """Render an IDE-visible declaration source from the same signatures."""
    lines = header(spec, "//")
    lines.extend(["<?php", "", "// Generated declaration source; runtime arginfo is emitted in C++."])
    for function in php_functions(spec):
        parameters = ", ".join(_stub_parameter(argument) for argument in function.arguments)
        result = _PHP_STUB_RETURNS[RESULT_SHAPES[function.behavior]]
        lines.append(
            f"function {function.public_name('php')}({parameters}): {result} {{}}"
        )
    return "\n".join(lines) + "\n"
