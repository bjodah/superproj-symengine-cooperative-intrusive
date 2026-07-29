"""Typed model and validation for the shared behavioral test cases."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import yaml

from .model import BindingSpec, SpecValidationError, ROOT, schema_errors


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
    """One of the three result expectations the shared schema can state.

    ``string`` is the printed form of a single expression, ``none`` is "the
    entry reported that no result exists" (Python's ``None``), and ``strings``
    is the ordered printed forms of a list result.  ``kind`` names which one is
    set so renderers branch on data rather than on ``is None`` checks.
    """

    kind: str  # "string", "none" or "strings"
    string: str | None = None
    strings: tuple[str, ...] = ()


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
        if "none" in expect_raw:
            expect = Expect(kind="none")
        elif "strings" in expect_raw:
            expect = Expect(kind="strings", strings=tuple(expect_raw["strings"]))
        else:
            expect = Expect(kind="string", string=expect_raw["string"])
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
    errors = schema_errors(document, TEST_CASES_SCHEMA_PATH, "cases", "case")
    if errors:
        raise SpecValidationError("test-cases schema validation failed:\n  " + "\n  ".join(errors))
    return _to_model(document, source_path)


# Which expectations an adapter family can produce.  A family whose result is
# always one expression can only be checked with ``string``; only the optional
# family can report "no result", and only the list family yields ``strings``.
EXPECTATIONS_BY_BEHAVIOR: Mapping[str, frozenset[str]] = {
    "status_optional_unary": frozenset({"string", "none"}),
    "list_integer_to_basic": frozenset({"strings"}),
}
_DEFAULT_EXPECTATIONS = frozenset({"string"})


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

        allowed = EXPECTATIONS_BY_BEHAVIOR.get(function.behavior, _DEFAULT_EXPECTATIONS)
        if case.expect.kind not in allowed:
            raise SpecValidationError(
                f"case '{case.id}': expectation '{case.expect.kind}' does not fit "
                f"'{function.id}' ({function.behavior}); expected one of "
                + ", ".join(sorted(allowed))
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
