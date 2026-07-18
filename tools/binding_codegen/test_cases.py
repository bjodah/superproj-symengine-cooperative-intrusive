"""Typed model and validation for the shared behavioral test cases."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import json

import yaml
from jsonschema import Draft202012Validator

from .model import BindingSpec, SpecValidationError, ROOT


TEST_CASES_PATH = ROOT / "binding-spec" / "test-cases.yaml"
TEST_CASES_SCHEMA_PATH = ROOT / "binding-spec" / "test-cases.schema.json"


@dataclass(frozen=True)
class ArrangeValue:
    kind: str  # "integer" or "symbol"
    value: object


@dataclass(frozen=True)
class Call:
    function: str
    arguments: tuple[str, ...]


@dataclass(frozen=True)
class Expect:
    string: str


@dataclass(frozen=True)
class TestCase:
    id: str
    arrange: Mapping[str, ArrangeValue]
    call: Call
    expect: Expect


@dataclass(frozen=True)
class TestCaseSuite:
    schema_version: int
    cases: tuple[TestCase, ...]
    source_path: Path


def _schema_errors(document: object, schema_path: Path) -> list[str]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    result: list[str] = []
    for error in sorted(validator.iter_errors(document), key=lambda item: list(item.absolute_path)):
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        entry = ""
        path = list(error.absolute_path)
        if (
            isinstance(document, Mapping)
            and len(path) >= 2
            and path[0] == "cases"
            and isinstance(path[1], int)
            and isinstance(document.get("cases"), list)
            and path[1] < len(document["cases"])
            and isinstance(document["cases"][path[1]], Mapping)
            and isinstance(document["cases"][path[1]].get("id"), str)
        ):
            entry = f"case '{document['cases'][path[1]]['id']}': "
        result.append(f"{entry}{location}: {error.message}")
    return result


def _to_model(document: Mapping[str, object], source_path: Path) -> TestCaseSuite:
    cases: list[TestCase] = []
    for raw in document["cases"]:  # type: ignore[union-attr]
        arrange_raw = raw.get("arrange", {})
        arrange = {
            name: ArrangeValue(kind=next(iter(spec)), value=next(iter(spec.values())))
            for name, spec in arrange_raw.items()
        }
        call_raw = raw["call"]
        call = Call(function=call_raw["function"], arguments=tuple(call_raw["arguments"]))
        expect_raw = raw["expect"]
        expect = Expect(string=expect_raw["string"])
        cases.append(TestCase(id=raw["id"], arrange=arrange, call=call, expect=expect))
    return TestCaseSuite(
        schema_version=document["schema_version"],  # type: ignore[arg-type]
        cases=tuple(cases),
        source_path=source_path,
    )


def load_test_cases(path: Path | str = TEST_CASES_PATH) -> TestCaseSuite:
    """Load and JSON-schema validate ``test-cases.yaml`` into typed data."""
    source_path = Path(path)
    try:
        document = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise SpecValidationError(f"cannot read {source_path}: {error}") from error
    except yaml.YAMLError as error:
        raise SpecValidationError(f"cannot parse {source_path}: {error}") from error
    if not isinstance(document, Mapping):
        raise SpecValidationError(f"{source_path} must contain a mapping at the top level")
    errors = _schema_errors(document, TEST_CASES_SCHEMA_PATH)
    if errors:
        raise SpecValidationError("test-cases schema validation failed:\n  " + "\n  ".join(errors))
    return _to_model(document, source_path)


def _validate_against_spec(suite: TestCaseSuite, spec: BindingSpec) -> None:
    functions_by_id = {function.id: function for function in spec.functions}
    ids: set[str] = set()
    for case in suite.cases:
        if case.id in ids:
            raise SpecValidationError(f"case '{case.id}': duplicate id")
        ids.add(case.id)

        function = functions_by_id.get(case.call.function)
        if function is None:
            raise SpecValidationError(
                f"case '{case.id}': call references unknown function '{case.call.function}'"
            )

        if len(case.call.arguments) != len(function.arguments):
            raise SpecValidationError(
                f"case '{case.id}': call to '{case.call.function}' passes "
                f"{len(case.call.arguments)} argument(s), expected {len(function.arguments)}"
            )

        for argument_name in case.call.arguments:
            if argument_name not in case.arrange:
                raise SpecValidationError(
                    f"case '{case.id}': call references unknown arrange variable '{argument_name}'"
                )


def validate_test_cases(
    path: Path | str = TEST_CASES_PATH, spec: BindingSpec | None = None
) -> TestCaseSuite:
    """Validate all declarative and cross-reference constraints and return the IR."""
    from .model import validate_spec

    suite = load_test_cases(path)
    if spec is None:
        spec = validate_spec()
    _validate_against_spec(suite, spec)
    return suite
