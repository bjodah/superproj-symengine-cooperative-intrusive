"""Render Swift's mechanical C call-through and public forwarding surface."""

from __future__ import annotations

from .model import BindingSpec, Function
from .render_common import functions_for_language, header


SUPPORTED_FAMILIES = frozenset(("singleton", "unary_basic", "binary_basic"))


def swift_functions(spec: BindingSpec) -> tuple[Function, ...]:
    """Return generated Swift entries in a stable order or name the gap."""
    return functions_for_language(spec, "swift", SUPPORTED_FAMILIES)


def _c_name(function: Function) -> str:
    return f"symengine_swift_{function.id}"


def render_swift_cpp(spec: BindingSpec) -> str:
    """Render C ABI call-throughs included by the manual runtime translation unit."""
    lines = header(spec, "//")
    lines.append("// Included inside extern \"C\" by CSymEngineSwift.cpp.")
    for function in swift_functions(spec):
        name = _c_name(function)
        parameters = ", ".join(
            f"symengine_swift_basic_ref {argument.name}" for argument in function.arguments
        )
        lines.extend(["", f"symengine_swift_basic_ref {name}({parameters})", "{"])
        if function.behavior == "singleton":
            expression = function.cpp.expression
            assert expression is not None
            lines.append(f"    return make_result([] {{ return {expression}; }});")
        else:
            cpp_name = function.cpp.name
            assert cpp_name is not None
            call_arguments = ", ".join(
                f"SymEngine::rcp(require_basic({argument.name}))"
                for argument in function.arguments
            )
            lines.extend([
                "    return make_result([&] {",
                f"        return {cpp_name}({call_arguments});",
                "    });",
            ])
        lines.append("}")
    return "\n".join(lines) + "\n"


def render_swift_api(spec: BindingSpec) -> str:
    """Render a Swift extension which relies only on manual adopt()/initialization."""
    lines = header(spec, "//")
    lines.extend([
        "import CSymEngineSwift",
        "",
        "// `_silgen_name` declarations avoid putting generated headers in source trees.",
    ])
    for function in swift_functions(spec):
        parameters = ", ".join(
            f"_ {argument.name}: symengine_swift_basic_ref" for argument in function.arguments
        )
        lines.extend([
            f'@_silgen_name("{_c_name(function)}")',
            f"private func _{_c_name(function)}({parameters}) -> symengine_swift_basic_ref?",
        ])
    lines.extend(["", "public extension SymEngine {"])
    for function in swift_functions(spec):
        result_type = "Integer" if function.id in {"zero", "one"} else "Basic"
        public_name = function.public_name("swift")
        parameters = ", ".join(
            f"_ {argument.name}: Basic" for argument in function.arguments
        )
        raw_arguments = ", ".join(f"{argument.name}.raw" for argument in function.arguments)
        lines.extend([
            f"    static func {public_name}({parameters}) throws -> {result_type} {{",
            "        try ensureInitialized()",
            f"        let value = try adopt(_{_c_name(function)}({raw_arguments}))",
        ])
        if result_type == "Integer":
            lines.append("        return try requireInteger(value)")
        else:
            lines.append("        return value")
        lines.append("    }")
    lines.append("}")
    return "\n".join(lines) + "\n"
