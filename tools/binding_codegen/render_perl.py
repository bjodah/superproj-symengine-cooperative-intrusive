"""Render the ownership-neutral, mechanical part of the Perl XS surface."""

from __future__ import annotations

from .model import BindingSpec, Function
from .render_common import functions_for_language, header


SUPPORTED_FAMILIES = frozenset(("singleton", "unary_basic", "binary_basic"))


def perl_functions(spec: BindingSpec) -> tuple[Function, ...]:
    """Return generated Perl entries in a stable order or name the gap."""
    return functions_for_language(spec, "perl", SUPPORTED_FAMILIES)


def render_perl_xs_inc(spec: BindingSpec) -> str:
    """Render XSUB bodies; wrapping, unwrapping and exception policy stay manual."""
    lines = header(spec, "#")
    lines.append("# Included by SymEngine.xs after the manual runtime setup.")
    for function in perl_functions(spec):
        parameters = ", ".join(argument.name for argument in function.arguments)
        lines.extend(["", "SV *", f"{function.public_name('perl')}({parameters})"])
        for argument in function.arguments:
            lines.append(f"    SV *{argument.name}")
        lines.append("  CODE:")
        lines.append("    try {")
        if function.behavior == "singleton":
            call = function.cpp.expression
            assert call is not None
        else:
            name = function.cpp.name
            assert name is not None
            arguments = ", ".join(
                f"SymEnginePerl::unwrap_basic({argument.name})"
                for argument in function.arguments
            )
            call = f"{name}({arguments})"
        lines.extend([
            f"        RETVAL = SymEnginePerl::wrap_basic_perl_owned({call});",
            "    } catch (...) {",
            "        croak_current_exception();",
            "    }",
            "  OUTPUT:",
            "    RETVAL",
        ])
    return "\n".join(lines) + "\n"


def render_perl_exports(spec: BindingSpec) -> str:
    """Render a small machine-readable public-name list for API fixtures."""
    lines = header(spec, "#")
    lines.extend(function.public_name("perl") for function in perl_functions(spec))
    return "\n".join(lines) + "\n"
