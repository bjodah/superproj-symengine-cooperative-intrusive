"""Render the ownership-neutral, mechanical part of the Perl XS surface."""

from __future__ import annotations

from .model import Argument, BindingSpec, Function
from .render_common import SCALAR_TYPES, cpp_result, functions_for_language, header


SUPPORTED_FAMILIES = frozenset((
    "singleton", "unary_basic", "binary_basic", "binary_boolean",
    "integer_unary", "integer_binary", "status_optional_unary",
    "list_integer_to_basic",
))

# XS input typemap spellings for the spec's non-handle argument types.  The
# standard typemap knows ``double`` and ``unsigned int``; ``unsigned`` alone is
# not a typemap key, hence the explicit ``int``.
XS_SCALAR_TYPES = {"double": "double", "unsigned": "unsigned int"}


def perl_functions(spec: BindingSpec) -> tuple[Function, ...]:
    """Return generated Perl entries in a stable order or name the gap."""
    return functions_for_language(spec, "perl", SUPPORTED_FAMILIES)


def _declaration(argument: Argument) -> str:
    if argument.type_id in SCALAR_TYPES:
        return f"    {XS_SCALAR_TYPES[argument.type_id]} {argument.name}"
    return f"    SV *{argument.name}"


def render_perl_xs_inc(spec: BindingSpec) -> str:
    """Render XSUB bodies; wrapping, unwrapping and exception policy stay manual."""
    lines = header(spec, "#")
    lines.append("# Included by SymEngine.xs after the manual runtime setup.")
    for function in perl_functions(spec):
        parameters = ", ".join(argument.name for argument in function.arguments)
        lines.extend(["", "SV *", f"{function.public_name('perl')}({parameters})"])
        lines.extend(_declaration(argument) for argument in function.arguments)
        lines.append("  CODE:")
        lines.append("    try {")
        result = cpp_result(
            function, lambda argument: f"SymEnginePerl::unwrap_basic({argument.name})"
        )
        lines.extend(result.statements)
        if result.shape == "handle":
            lines.append(f"        RETVAL = SymEnginePerl::wrap_basic_perl_owned({result.value});")
        elif result.shape == "optional":
            # No result is Perl's undef, matching Python's None.
            lines.extend([
                f"        RETVAL = {result.found}",
                f"            ? SymEnginePerl::wrap_basic_perl_owned({result.value})",
                "            : SymEnginePerl::undefined();",
            ])
        else:
            # A list result is one reference to an array of wrapped handles.
            lines.append(f"        RETVAL = SymEnginePerl::wrap_basic_list({result.value});")
        lines.extend([
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
