"""Deterministic nanobind output for adapter families in the shared spec."""

from __future__ import annotations

import hashlib
import json
import re
from .model import BindingSpec, Function


GENERATOR_VERSION = "1"


def spec_digest(spec: BindingSpec) -> str:
    """Return the whitespace-insensitive digest required by the roadmap."""
    import yaml

    document = yaml.safe_load(spec.source_path.read_text(encoding="utf-8"))
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _header(spec: BindingSpec, comment: str) -> list[str]:
    return [
        f"{comment} AUTO-GENERATED — DO NOT EDIT.",
        f"{comment} schema_version: {spec.schema_version}; spec_sha256: {spec_digest(spec)}; generator_version: {GENERATOR_VERSION}",
    ]


def python_functions(spec: BindingSpec) -> tuple[Function, ...]:
    """Generated Python functions, sorted independently of YAML input order."""
    return tuple(sorted(
        (function for function in spec.functions
         if "python" in function.expose and function.implementation == "generated"),
        key=lambda function: function.id,
    ))


def python_excluded_names(spec: BindingSpec) -> tuple[str, ...]:
    """Exact litgen exclusion patterns for all Python-owned free functions."""
    names = {
        function.cpp.name.rsplit("::", 1)[-1]
        for function in spec.functions
        if "python" in function.expose and function.cpp.name is not None
    }
    return tuple(rf"^{re.escape(name)}$" for name in sorted(names))


def _cpp_type(type_id: str) -> str:
    return {
        "basic": "RCP<const Basic>",
        "boolean": "RCP<const Boolean>",
        "integer": "RCP<const Integer>",
        "number": "RCP<const Number>",
        "double": "double",
        "unsigned": "unsigned",
    }[type_id]


def _python_type(type_id: str) -> str:
    return {
        "basic": "Basic", "boolean": "Boolean", "integer": "Integer",
        "number": "Basic", "double": "float", "unsigned": "int",
    }[type_id]


def _param(argument: object) -> str:
    type_id = argument.type_id
    cpp_type = _cpp_type(type_id)
    if type_id in {"double", "unsigned"}:
        return f"{cpp_type} {argument.name}"
    return f"const {cpp_type} &{argument.name}"


def _call_argument(function: Function, argument: object) -> str:
    deref = bool(function.adapter.get("deref", True))
    return f"*{argument.name}" if deref and argument.type_id == "integer" else argument.name


def _nb_args(function: Function) -> str:
    result: list[str] = []
    for argument in function.arguments:
        item = f'nb::arg("{argument.name}")'
        if argument.has_default:
            value = argument.default
            if isinstance(value, str):
                item += f" = {value}"
            else:
                item += f" = {str(value).lower()}"
        result.append(item)
    return ", ".join(result)


def render_python_inc(spec: BindingSpec) -> str:
    """Render the include consumed by ``core_module.cpp``."""
    lines = _header(spec, "    //")
    previous_section: str | None = None
    for function in python_functions(spec):
        section = function.adapter.get("section")
        if isinstance(section, str) and section != previous_section:
            lines.extend(["", f"    // {section}"])
            previous_section = section
        args = function.arguments
        parameters = ", ".join(_param(argument) for argument in args)
        call_args = ", ".join(_call_argument(function, argument) for argument in args)
        public_name = function.public_name("python")
        behavior = function.behavior
        name = function.cpp.name
        if behavior in {"unary_basic", "binary_basic", "binary_boolean", "integer_unary", "integer_binary"}:
            assert name is not None
            return_type = _cpp_type(function.returns)
            lines.extend([
                f'    m.def("{public_name}", []({parameters}) -> {return_type} {{',
                f"        return {name}({call_args});",
                f"    }}, {_nb_args(function)});",
            ])
        elif behavior == "singleton":
            expression = function.cpp.expression
            assert expression is not None
            lines.extend([
                f'    m.def("{public_name}", []() -> {_cpp_type(function.returns)} {{',
                f"        return {expression};",
                "    });",
            ])
        elif behavior == "status_optional_unary":
            status_type = function.adapter.get("status_type", "int")
            lines.extend([
                f'    m.def("{public_name}", []({parameters}) -> nb::object {{',
                "        RCP<const Integer> r;",
                f"        {status_type} status = {name}(outArg(r), {call_args});",
                "        if (status) return nb::cast(r);",
                "        return nb::none();",
                f"    }}, {_nb_args(function)});",
            ])
        elif behavior == "list_integer_to_basic":
            lines.extend([
                f'    m.def("{public_name}", []({parameters}) -> std::vector<RCP<const Basic>> {{',
                "        std::vector<RCP<const Integer>> tmp;",
                f"        {name}(tmp, {call_args});",
                "        std::vector<RCP<const Basic>> result;",
                "        result.reserve(tmp.size());",
                "        for (auto &v : tmp) result.push_back(v);",
                "        return result;",
                f"    }}, {_nb_args(function)});",
            ])
        else:  # guarded by schema/model validation; retain a useful error if extended incorrectly
            raise ValueError(f"entry '{function.id}': Python renderer does not support {behavior!r}")
    return "\n".join(lines) + "\n"


def render_python_pyi(spec: BindingSpec) -> str:
    """Render the generated declaration fragment appended to litgen's stub."""
    lines = _header(spec, "#")
    lines.append("# Shared adapter-family declarations.")
    for function in python_functions(spec):
        parameters: list[str] = []
        for argument in function.arguments:
            value = f"{argument.name}: {_python_type(argument.type_id)}"
            if argument.has_default:
                default = argument.default
                value += f" = {str(default).rstrip('u')}"
            parameters.append(value)
        if function.behavior == "status_optional_unary":
            result = "Basic | None"
        elif function.behavior == "list_integer_to_basic":
            result = "list"
        else:
            result = _python_type(function.returns)
        lines.append(f"def {function.public_name('python')}({', '.join(parameters)}) -> {result}: ...")
    return "\n".join(lines) + "\n"
