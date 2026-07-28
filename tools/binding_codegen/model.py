"""Typed model and validation for the shared binding specification."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import json

import yaml
from jsonschema import Draft202012Validator

from .inspect_cpp import validate_cpp_targets


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "binding-spec" / "schema.json"

LANGUAGES = ("python", "perl", "php", "swift", "java")

# These are deliberately small, language-level lists.  They protect generated
# entry points; renderers may add their own private identifiers without changing
# the public API contract.
RESERVED_WORDS: dict[str, frozenset[str]] = {
    "python": frozenset(
        "False None True and as assert async await break class continue def del "
        "elif else except finally for from global if import in is lambda nonlocal "
        "not or pass raise return try while with yield".split()
    ),
    "perl": frozenset("sub package use my our state if else elsif while for foreach return".split()),
    "php": frozenset("class function namespace use trait interface match readonly".split()),
    "swift": frozenset(
        "associatedtype class deinit enum extension fileprivate func import init inout "
        "internal let open operator private protocol public rethrows static struct "
        "subscript typealias var break case catch continue default defer do else fallthrough "
        "for guard if repeat return switch throw where while as Any false is nil self "
        "Self super true try".split()
    ),
    "java": frozenset(
        "abstract assert boolean break byte case catch char class const continue default "
        "do double else enum extends final finally float for goto if implements import "
        "instanceof int interface long native new package private protected public return "
        "short static strictfp super switch synchronized this throw throws transient try "
        "void volatile while true false null".split()
    ),
}


class SpecValidationError(ValueError):
    """A clear user-facing failure in ``api.yaml``."""


@dataclass(frozen=True)
class TypeDefinition:
    id: str
    cpp: str
    category: str
    extends: str | None = None


@dataclass(frozen=True)
class Argument:
    name: str
    type_id: str
    default: object = None
    has_default: bool = False


@dataclass(frozen=True)
class CppTarget:
    header: str
    name: str | None = None
    expression: str | None = None


@dataclass(frozen=True)
class Function:
    id: str
    cpp: CppTarget
    arguments: tuple[Argument, ...]
    returns: str
    behavior: str
    expose: tuple[str, ...]
    names: Mapping[str, str]
    implementation: str
    adapter: Mapping[str, object]

    def public_name(self, language: str) -> str:
        """Return the public name after the documented language convention."""
        if language in self.names:
            return self.names[language]
        if language == "php":
            return f"symengine_{self.id}"
        if language in {"swift", "java"}:
            head, *tail = self.id.split("_")
            return head + "".join(part.capitalize() for part in tail)
        return self.id


@dataclass(frozen=True)
class BindingSpec:
    schema_version: int
    types: Mapping[str, TypeDefinition]
    functions: tuple[Function, ...]
    source_path: Path


def schema_errors(document: object, schema_path: Path, collection: str, label: str) -> list[str]:
    """Return readable JSON-schema errors, sorted and located.

    Errors inside ``document[collection][i]`` are prefixed with
    ``<label> '<id>': `` so a failure names the offending entry rather than a
    bare array index.  Shared by ``api.yaml`` and ``test-cases.yaml``.
    """
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    items = document.get(collection) if isinstance(document, Mapping) else None
    result: list[str] = []
    for error in sorted(validator.iter_errors(document), key=lambda item: list(item.absolute_path)):
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        entry = ""
        path = list(error.absolute_path)
        if (
            len(path) >= 2
            and path[0] == collection
            and isinstance(path[1], int)
            and isinstance(items, list)
            and path[1] < len(items)
            and isinstance(items[path[1]], Mapping)
            and isinstance(items[path[1]].get("id"), str)
        ):
            entry = f"{label} '{items[path[1]]['id']}': "
        result.append(f"{entry}{location}: {error.message}")
    return result


def _as_mapping(value: object, location: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SpecValidationError(f"{location} must be an object")
    return value


def _to_model(document: Mapping[str, Any], source_path: Path) -> BindingSpec:
    types = {
        type_id: TypeDefinition(
            id=type_id,
            cpp=definition["cpp"],
            category=definition["category"],
            extends=definition.get("extends"),
        )
        for type_id, definition in _as_mapping(document["types"], "types").items()
    }
    functions: list[Function] = []
    for raw in document["functions"]:
        cpp = _as_mapping(raw["cpp"], f"function {raw['id']}.cpp")
        functions.append(
            Function(
                id=raw["id"],
                cpp=CppTarget(header=cpp["header"], name=cpp.get("name"), expression=cpp.get("expression")),
                arguments=tuple(
                    Argument(item["name"], item["type"], item.get("default"), "default" in item)
                    for item in raw["arguments"]
                ),
                returns=raw["returns"],
                behavior=raw["behavior"],
                expose=tuple(raw["expose"]),
                names=dict(raw.get("names", {})),
                implementation=raw.get("implementation", "manual"),
                adapter=dict(raw.get("adapter", {})),
            )
        )
    return BindingSpec(
        schema_version=document["schema_version"],
        types=types,
        functions=tuple(functions),
        source_path=source_path,
    )


def _validate_model(spec: BindingSpec) -> None:
    ids: set[str] = set()
    for function in spec.functions:
        if function.id in ids:
            raise SpecValidationError(f"entry '{function.id}': duplicate id")
        ids.add(function.id)
        for argument in function.arguments:
            if argument.type_id not in spec.types:
                raise SpecValidationError(
                    f"entry '{function.id}': argument '{argument.name}' uses unknown type '{argument.type_id}'"
                )
            if argument.has_default and function.behavior not in {
                "status_optional_unary",
            }:
                raise SpecValidationError(
                    f"entry '{function.id}': argument '{argument.name}' has an unsupported default value"
                )
        if function.returns not in spec.types:
            raise SpecValidationError(
                f"entry '{function.id}': returns unknown type '{function.returns}'"
            )
        for language in function.expose:
            if language not in LANGUAGES:
                raise SpecValidationError(
                    f"entry '{function.id}': no renderer is registered for language '{language}'"
                )
    for type_definition in spec.types.values():
        if type_definition.extends is not None and type_definition.extends not in spec.types:
            raise SpecValidationError(
                f"type '{type_definition.id}': extends unknown type '{type_definition.extends}'"
            )

    resolved: dict[str, dict[str, str]] = {language: {} for language in LANGUAGES}
    for function in spec.functions:
        for language in function.expose:
            name = function.public_name(language)
            if name in RESERVED_WORDS[language] and language not in function.names:
                raise SpecValidationError(
                    f"entry '{function.id}': resolved {language} name '{name}' is reserved; add names.{language}"
                )
            previous = resolved[language].get(name)
            if previous is not None:
                raise SpecValidationError(
                    f"entries '{previous}' and '{function.id}': duplicate resolved {language} name '{name}'"
                )
            resolved[language][name] = function.id


def load_spec(path: Path | str = ROOT / "binding-spec" / "api.yaml") -> BindingSpec:
    """Load, JSON-schema validate, and convert an API YAML file to typed data."""
    source_path = Path(path)
    try:
        document = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise SpecValidationError(f"cannot read {source_path}: {error}") from error
    except yaml.YAMLError as error:
        raise SpecValidationError(f"cannot parse {source_path}: {error}") from error
    errors = schema_errors(document, SCHEMA_PATH, "functions", "entry")
    if errors:
        raise SpecValidationError("schema validation failed:\n  " + "\n  ".join(errors))
    return _to_model(_as_mapping(document, "<root>"), source_path)


def validate_spec(path: Path | str = ROOT / "binding-spec" / "api.yaml") -> BindingSpec:
    """Validate all declarative and C++-header constraints and return the IR."""
    spec = load_spec(path)
    _validate_model(spec)
    validate_cpp_targets(spec, ROOT)
    return spec
