"""Render Swift's mechanical C call-through and public forwarding surface."""

from __future__ import annotations

from .model import Argument, BindingSpec, Function
from .render_common import (
    BASIC_VECTOR,
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

# C ABI and Swift spellings of the spec's non-handle argument types.
SWIFT_SCALARS = {"double": ("double", "Double"), "unsigned": ("unsigned", "UInt32")}

# The C bridge signals "no result" and "here is a list" through out-parameters
# rather than the plain owned-reference return, because a null return already
# means "an exception was recorded in last_error".
OPTIONAL_OUT = "symengine_swift_basic_ref *result"
LIST_OUT = "symengine_swift_basic_ref **values, size_t *count"
SWIFT_OPTIONAL_OUT = "_ result: UnsafeMutablePointer<symengine_swift_basic_ref?>"
SWIFT_LIST_OUT = (
    "_ values: UnsafeMutablePointer<UnsafeMutablePointer<symengine_swift_basic_ref?>?>, "
    "_ count: UnsafeMutablePointer<Int>"
)


def swift_functions(spec: BindingSpec) -> tuple[Function, ...]:
    """Return generated Swift entries in a stable order or name the gap."""
    return functions_for_language(spec, "swift", SUPPORTED_FAMILIES)


def _c_name(function: Function) -> str:
    return f"symengine_swift_{function.id}"


def _c_parameter(argument: Argument) -> str:
    if argument.type_id in SCALAR_TYPES:
        return f"{SWIFT_SCALARS[argument.type_id][0]} {argument.name}"
    return f"symengine_swift_basic_ref {argument.name}"


def _c_parameters(function: Function, trailing: str = "") -> str:
    items = [_c_parameter(argument) for argument in function.arguments]
    if trailing:
        items.append(trailing)
    return ", ".join(items)


def render_swift_cpp(spec: BindingSpec) -> str:
    """Render C ABI call-throughs included by the manual runtime translation unit."""
    lines = header(spec, "//")
    lines.append("// Included inside extern \"C\" by CSymEngineSwift.cpp.")
    for function in swift_functions(spec):
        name = _c_name(function)
        result = cpp_result(
            function, lambda argument: f"SymEngine::rcp(require_basic({argument.name}))"
        )
        if result.shape == "handle":
            lines.extend([
                "",
                f"symengine_swift_basic_ref {name}({_c_parameters(function)})",
                "{",
            ])
            if function.behavior == "singleton":
                lines.append(f"    return make_result([] {{ return {result.value}; }});")
            else:
                lines.append("    return make_result([&] {")
                lines.extend(result.statements)
                lines.extend([f"        return {result.value};", "    });"])
        elif result.shape == "optional":
            lines.extend([
                "",
                f"symengine_swift_status {name}({_c_parameters(function, OPTIONAL_OUT)})",
                "{",
                "    return make_optional_result(result, [&]() -> SymEngine::RCP<const SymEngine::Basic> {",
            ])
            lines.extend(result.statements)
            lines.extend([
                f"        if (!{result.found})",
                "            return SymEngine::RCP<const SymEngine::Basic>();",
                f"        return {result.value};",
                "    });",
            ])
        else:
            lines.extend([
                "",
                f"symengine_swift_status {name}({_c_parameters(function, LIST_OUT)})",
                "{",
                f"    return make_list_result(values, count, [&]() -> {BASIC_VECTOR} {{",
            ])
            lines.extend(result.statements)
            lines.extend([f"        return {result.value};", "    });"])
        lines.append("}")
    return "\n".join(lines) + "\n"


def _swift_parameter(argument: Argument) -> str:
    if argument.type_id in SCALAR_TYPES:
        return f"_ {argument.name}: {SWIFT_SCALARS[argument.type_id][1]}"
    return f"_ {argument.name}: Basic"


def _silgen_parameter(argument: Argument) -> str:
    if argument.type_id in SCALAR_TYPES:
        return f"_ {argument.name}: {SWIFT_SCALARS[argument.type_id][1]}"
    return f"_ {argument.name}: symengine_swift_basic_ref"


def _forwarded(argument: Argument) -> str:
    return argument.name if argument.type_id in SCALAR_TYPES else f"{argument.name}.raw"


def render_swift_api(spec: BindingSpec) -> str:
    """Render a Swift extension which relies only on manual adopt()/initialization."""
    lines = header(spec, "//")
    lines.extend([
        "import CSymEngineSwift",
        "",
        "// `_silgen_name` declarations avoid putting generated headers in source trees.",
    ])
    for function in swift_functions(spec):
        shape = RESULT_SHAPES[function.behavior]
        parameters = [_silgen_parameter(argument) for argument in function.arguments]
        if shape == "optional":
            parameters.append(SWIFT_OPTIONAL_OUT)
            returns = "symengine_swift_status"
        elif shape == "list":
            parameters.append(SWIFT_LIST_OUT)
            returns = "symengine_swift_status"
        else:
            returns = "symengine_swift_basic_ref?"
        lines.extend([
            f'@_silgen_name("{_c_name(function)}")',
            f"private func _{_c_name(function)}({', '.join(parameters)}) -> {returns}",
        ])
    lines.extend(["", "public extension SymEngine {"])
    for function in swift_functions(spec):
        shape = RESULT_SHAPES[function.behavior]
        public_name = function.public_name("swift")
        parameters = ", ".join(_swift_parameter(argument) for argument in function.arguments)
        forwarded = [_forwarded(argument) for argument in function.arguments]
        if shape == "handle":
            result_type = "Integer" if function.id in {"zero", "one"} else "Basic"
            lines.extend([
                f"    static func {public_name}({parameters}) throws -> {result_type} {{",
                "        try ensureInitialized()",
                f"        let value = try adopt(_{_c_name(function)}({', '.join(forwarded)}))",
            ])
            if result_type == "Integer":
                lines.append("        return try requireInteger(value)")
            else:
                lines.append("        return value")
        elif shape == "optional":
            lines.extend([
                f"    static func {public_name}({parameters}) throws -> Basic? {{",
                "        try ensureInitialized()",
                "        var value: symengine_swift_basic_ref?",
                f"        try check(_{_c_name(function)}({', '.join([*forwarded, '&value'])}))",
                "        guard let value else { return nil }",
                "        return try adopt(value)",
            ])
        else:
            lines.extend([
                f"    static func {public_name}({parameters}) throws -> [Basic] {{",
                "        try ensureInitialized()",
                "        var values: UnsafeMutablePointer<symengine_swift_basic_ref?>?",
                "        var count = 0",
                f"        try check(_{_c_name(function)}({', '.join([*forwarded, '&values', '&count'])}))",
                "        return try adoptList(values, count)",
            ])
        lines.append("    }")
    lines.append("}")
    return "\n".join(lines) + "\n"
