"""srcML-backed C++ declaration checks for shared binding entries."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import TYPE_CHECKING
import xml.etree.ElementTree as ElementTree

from srcml_caller import cpp_to_srcml

if TYPE_CHECKING:
    from .model import BindingSpec, Function


class CppInspectionError(ValueError):
    """Raised when a spec target cannot be proved against its selected header."""


@dataclass(frozen=True)
class CppFunction:
    name: str
    return_type: str
    parameter_types: tuple[str, ...]
    namespace: str = "SymEngine"


def _text(element: ElementTree.Element | None) -> str:
    return "" if element is None else "".join(element.itertext())


def _parse_header(path: Path) -> ElementTree.Element:
    try:
        xml = cpp_to_srcml(path.read_text(encoding="utf-8"), include_positions=False)
    except Exception as error:  # pragma: no cover - depends on srcML installation failures
        raise CppInspectionError(f"could not parse header '{path}': {error}") from error
    if not xml:
        raise CppInspectionError(f"could not parse header '{path}': srcML returned no document")
    # Keep preprocessor nodes namespaced but make ordinary srcML nodes easy to
    # query.  Recent srcml_caller versions already declare ``cpp`` themselves.
    xml = xml.replace('xmlns="http://www.srcML.org/srcML/src" ', "", 1)
    try:
        return ElementTree.fromstring(xml)
    except ElementTree.ParseError as error:  # pragma: no cover - defensive
        raise CppInspectionError(f"could not read srcML for '{path}': {error}") from error


def _free_functions(root: ElementTree.Element) -> tuple[CppFunction, ...]:
    found: list[CppFunction] = []

    def visit(node: ElementTree.Element, in_class: bool = False, namespace: str = "") -> None:
        nested_in_class = in_class or node.tag in {"class", "struct"}
        nested_namespace = namespace
        if node.tag == "namespace":
            name = _text(node.find("name"))
            nested_namespace = "::".join(part for part in (namespace, name) if part)
        if node.tag in {"function", "function_decl"} and not in_class:
            name = _text(node.find("name"))
            parameter_list = node.find("parameter_list")
            if name and parameter_list is not None:
                parameters: list[str] = []
                for parameter in parameter_list.findall("parameter"):
                    declaration = parameter.find("decl")
                    parameters.append(_text(None if declaration is None else declaration.find("type")))
                found.append(CppFunction(name, _text(node.find("type")), tuple(parameters), namespace))
        for child in node:
            visit(child, nested_in_class, nested_namespace)

    visit(root)
    return tuple(found)


def _canonical(cpp_type: str) -> str:
    value = re.sub(r"\b(const|volatile|class|struct)\b", "", cpp_type)
    value = value.replace("SymEngine::", "")
    value = re.sub(r"\s+", "", value)
    return value.replace("&", "").replace("*", "")


def _compatible(actual: str, expected: str, type_id: str) -> bool:
    actual_value, expected_value = _canonical(actual), _canonical(expected)
    if actual_value == expected_value:
        return True
    # A spec type describes the public category, so an RCP to a derived Basic
    # (Integer, Symbol, Constant) is a valid producer of ``basic``.
    if type_id == "basic":
        return actual_value.startswith("RCP<") and actual_value.endswith(">")
    # Adapter families intentionally describe the public Python category,
    # rather than duplicating every C++ spelling.  Number theory accepts a
    # mixture of ``Integer`` references and RCP handles for ``integer``.
    if type_id in {"integer", "number", "boolean"}:
        leaf = type_id.capitalize()
        return actual_value in {leaf, f"RCP<{leaf}>"}
    return False


def _header_path(root: Path, header: str) -> Path:
    if Path(header).is_absolute() or ".." in Path(header).parts:
        raise CppInspectionError(f"header '{header}' must be a relative symengine include path")
    return root / "symengine" / header


def _expression_exists(source: str, expression: str) -> bool:
    leaf = expression.rsplit("::", 1)[-1]
    # Constants in SymEngine are declarations such as ``RCP<...> &pi;``.  This
    # deliberately does not accept arbitrary expressions or calls in the spec.
    return bool(re.search(rf"\b{re.escape(leaf)}\s*;", source))


def _validate_function(function: Function, types: object, root: Path) -> None:
    path = _header_path(root, function.cpp.header)
    if not path.is_file():
        raise CppInspectionError(f"entry '{function.id}': header '{function.cpp.header}' does not exist")
    source = path.read_text(encoding="utf-8")
    if function.cpp.expression is not None:
        if not _expression_exists(source, function.cpp.expression):
            raise CppInspectionError(
                f"entry '{function.id}': expression '{function.cpp.expression}' was not found in '{function.cpp.header}'"
            )
        return

    root_xml = _parse_header(path)
    cpp_name = function.cpp.name.rsplit("::", 1)[-1]
    candidates = [
        item
        for item in _free_functions(root_xml)
        if item.name == cpp_name and item.namespace == "SymEngine"
    ]
    if not candidates:
        raise CppInspectionError(
            f"entry '{function.id}': function '{function.cpp.name}' was not found in '{function.cpp.header}'"
        )
    hidden_output = function.behavior in {"status_optional_unary", "list_integer_to_basic"}
    expected_arity = len(function.arguments) + int(hidden_output)
    arity_candidates = [item for item in candidates if len(item.parameter_types) == expected_arity]
    if not arity_candidates:
        available = ", ".join(str(len(item.parameter_types)) for item in candidates)
        raise CppInspectionError(
            f"entry '{function.id}': function '{function.cpp.name}' has no {expected_arity}-argument overload "
            f"in '{function.cpp.header}' (available arities: {available})"
        )
    matched = []
    for candidate in arity_candidates:
        parameters = candidate.parameter_types[1:] if hidden_output else candidate.parameter_types
        if not all(
            _compatible(actual, types[argument.type_id].cpp, argument.type_id)
            for actual, argument in zip(parameters, function.arguments)
        ):
            continue
        if hidden_output:
            if _canonical(candidate.return_type) not in {"int", "bool", "void"}:
                continue
        elif not _compatible(candidate.return_type, types[function.returns].cpp, function.returns):
            continue
        matched.append(candidate)
    if not matched:
        raise CppInspectionError(
            f"entry '{function.id}': no overload of '{function.cpp.name}' matches the declared argument and return types"
        )
    if len(matched) > 1:
        raise CppInspectionError(
            f"entry '{function.id}': overload of '{function.cpp.name}' is ambiguous; refine the shared type model"
        )


def validate_cpp_targets(spec: BindingSpec, root: Path) -> None:
    """Confirm every spec function/expression exists in its named header."""
    try:
        for function in spec.functions:
            _validate_function(function, spec.types, root)
    except CppInspectionError as error:
        from .model import SpecValidationError

        raise SpecValidationError(str(error)) from error
