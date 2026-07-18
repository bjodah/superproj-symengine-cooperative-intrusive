"""Command line interface for shared binding specification validation."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .model import BindingSpec, ROOT, SpecValidationError, load_spec, validate_spec
from .render_nbsymengine import render_python_inc, render_python_pyi
from .render_perl import render_perl_exports, render_perl_xs_inc
from .render_php import render_php_function_table_inc, render_php_inc, render_php_stub
from .render_swift import render_swift_api, render_swift_cpp
from .render_java import render_java_api, render_java_cpp, render_java_jni
from .render_tests import (
    render_java_tests,
    render_perl_tests,
    render_php_tests,
    render_python_tests,
    render_swift_tests,
)
from .coverage import render_coverage_matrix, render_coverage_report
from .test_cases import TestCaseSuite, validate_test_cases


# name -> renderer, covering every artifact `generate` can write for every
# language. Determinism means calling one of these twice yields identical text.
ARTIFACT_RENDERERS = {
    "python:symengine_simple_funcs.inc": render_python_inc,
    "python:symengine_simple_funcs.pyi": render_python_pyi,
    "perl:SymEngine.generated.xs.inc": render_perl_xs_inc,
    "perl:SymEngine.generated.exports": render_perl_exports,
    "php:symengine_php_generated.inc": render_php_inc,
    "php:symengine_php_generated_functions.inc": render_php_function_table_inc,
    "php:symengine.stub.php": render_php_stub,
    "swift:SymEngineSwiftGenerated.inc": render_swift_cpp,
    "swift:SymEngineGenerated.swift": render_swift_api,
    "java:SymEngineJNI.java": render_java_jni,
    "java:SymEngine.java": render_java_api,
    "java:symengine_jni_generated.cpp": render_java_cpp,
}

# name -> renderer, covering the shared behavioral test file `generate` can
# write for every language. Kept separate from ARTIFACT_RENDERERS because
# these renderers take the parsed test-case suite as well as the spec.
TEST_ARTIFACT_RENDERERS = {
    "python:test_shared_cases.py": render_python_tests,
    "perl:shared_cases.t": render_perl_tests,
    "php:shared_cases.phpt": render_php_tests,
    "swift:SharedCasesTests.swift": render_swift_tests,
    "java:SharedCasesTest.java": render_java_tests,
}

MATRIX_PATH = ROOT / "docs" / "binding-api-matrix.md"


def find_nondeterministic_artifacts(spec: BindingSpec, suite: TestCaseSuite) -> tuple[str, ...]:
    """Return the names of artifacts whose renderer is not byte-stable.

    Rendering happens purely in memory; nothing is written to the working
    tree.
    """
    unstable = [
        name for name, renderer in ARTIFACT_RENDERERS.items()
        if renderer(spec) != renderer(spec)
    ]
    unstable.extend(
        name for name, renderer in TEST_ARTIFACT_RENDERERS.items()
        if renderer(spec, suite) != renderer(spec, suite)
    )
    return tuple(unstable)


def stale_matrix_message(spec: BindingSpec) -> str | None:
    """Return a failure message if the committed API matrix is out of date."""
    current = render_coverage_matrix(spec)
    try:
        display_path = MATRIX_PATH.relative_to(ROOT)
    except ValueError:
        display_path = MATRIX_PATH
    command = f"python -m tools.binding_codegen coverage --matrix --output {display_path}"
    if not MATRIX_PATH.exists():
        return f"{MATRIX_PATH} is missing; regenerate with: {command}"
    committed = MATRIX_PATH.read_text(encoding="utf-8")
    if committed == current:
        return None
    return f"{MATRIX_PATH} is stale; regenerate with: {command}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.binding_codegen")
    subcommands = parser.add_subparsers(dest="command", required=True)
    validate = subcommands.add_parser("validate", help="validate binding-spec/api.yaml")
    validate.add_argument("--spec", type=Path, default=ROOT / "binding-spec" / "api.yaml")
    generate = subcommands.add_parser("generate", help="render shared binding outputs")
    generate.add_argument("--spec", type=Path, default=ROOT / "binding-spec" / "api.yaml")
    generate.add_argument("--language", choices=("python", "perl", "php", "swift", "java"), required=True)
    generate.add_argument("--output", type=Path, required=True)
    generate.add_argument("--artifact", choices=("all", "cpp", "api", "tests"), default="all",
                          help="Swift-only: select C++ glue, Swift API, or XCTest output")
    coverage = subcommands.add_parser("coverage", help="report generated/manual/not-exposed API coverage")
    coverage.add_argument("--spec", type=Path, default=ROOT / "binding-spec" / "api.yaml")
    coverage.add_argument("--output", type=Path)
    coverage.add_argument("--matrix", action="store_true", help="render the per-entry/per-language matrix")
    check = subcommands.add_parser("check", help="validate, check determinism, and check doc freshness")
    check.add_argument("--spec", type=Path, default=ROOT / "binding-spec" / "api.yaml")
    arguments = parser.parse_args(argv)
    if arguments.command == "validate":
        try:
            spec = validate_spec(arguments.spec)
        except SpecValidationError as error:
            print(f"binding spec validation failed: {error}", file=sys.stderr)
            return 1
        print(f"validated {len(spec.functions)} binding entries from {arguments.spec}")
        return 0
    if arguments.command == "generate":
        try:
            spec = validate_spec(arguments.spec)
            suite = validate_test_cases(spec=spec)
            arguments.output.mkdir(parents=True, exist_ok=True)
            if arguments.language == "python":
                (arguments.output / "symengine_simple_funcs.inc").write_text(
                    render_python_inc(spec), encoding="utf-8", newline="\n")
                (arguments.output / "symengine_simple_funcs.pyi").write_text(
                    render_python_pyi(spec), encoding="utf-8", newline="\n")
                (arguments.output / "test_shared_cases.py").write_text(
                    render_python_tests(spec, suite), encoding="utf-8", newline="\n")
            elif arguments.language == "perl":
                (arguments.output / "SymEngine.generated.xs.inc").write_text(
                    render_perl_xs_inc(spec), encoding="utf-8", newline="\n")
                (arguments.output / "SymEngine.generated.exports").write_text(
                    render_perl_exports(spec), encoding="utf-8", newline="\n")
                (arguments.output / "shared_cases.t").write_text(
                    render_perl_tests(spec, suite), encoding="utf-8", newline="\n")
            elif arguments.language == "php":
                (arguments.output / "symengine_php_generated.inc").write_text(
                    render_php_inc(spec), encoding="utf-8", newline="\n")
                (arguments.output / "symengine_php_generated_functions.inc").write_text(
                    render_php_function_table_inc(spec), encoding="utf-8", newline="\n")
                (arguments.output / "symengine.stub.php").write_text(
                    render_php_stub(spec), encoding="utf-8", newline="\n")
                (arguments.output / "shared_cases.phpt").write_text(
                    render_php_tests(spec, suite), encoding="utf-8", newline="\n")
            elif arguments.language == "swift":
                if arguments.artifact in {"all", "cpp"}:
                    (arguments.output / "SymEngineSwiftGenerated.inc").write_text(
                        render_swift_cpp(spec), encoding="utf-8", newline="\n")
                if arguments.artifact in {"all", "api"}:
                    (arguments.output / "SymEngineGenerated.swift").write_text(
                        render_swift_api(spec), encoding="utf-8", newline="\n")
                if arguments.artifact in {"all", "tests"}:
                    (arguments.output / "SharedCasesTests.swift").write_text(
                        render_swift_tests(spec, suite), encoding="utf-8", newline="\n")
            elif arguments.language == "java":
                (arguments.output / "SymEngineJNI.java").write_text(
                    render_java_jni(spec), encoding="utf-8", newline="\n")
                (arguments.output / "SymEngine.java").write_text(
                    render_java_api(spec), encoding="utf-8", newline="\n")
                (arguments.output / "symengine_jni_generated.cpp").write_text(
                    render_java_cpp(spec), encoding="utf-8", newline="\n")
                (arguments.output / "SharedCasesTest.java").write_text(
                    render_java_tests(spec, suite), encoding="utf-8", newline="\n")
        except (SpecValidationError, ValueError) as error:
            print(f"binding generation failed: {error}", file=sys.stderr)
            return 1
        return 0
    if arguments.command == "coverage":
        try:
            spec = validate_spec(arguments.spec)
            report = render_coverage_matrix(spec) if arguments.matrix else render_coverage_report(spec)
            if arguments.output is None:
                print(report, end="")
            else:
                arguments.output.parent.mkdir(parents=True, exist_ok=True)
                arguments.output.write_text(report, encoding="utf-8", newline="\n")
        except (SpecValidationError, ValueError) as error:
            print(f"binding coverage failed: {error}", file=sys.stderr)
            return 1
        return 0
    if arguments.command == "check":
        try:
            spec = validate_spec(arguments.spec)
            suite = validate_test_cases(spec=spec)
        except SpecValidationError as error:
            print(f"binding spec validation failed: {error}", file=sys.stderr)
            return 1
        print(f"validated {len(spec.functions)} binding entries from {arguments.spec}")
        print(f"validated {len(suite.cases)} shared behavioral test cases")
        nondeterministic = find_nondeterministic_artifacts(spec, suite)
        if nondeterministic:
            print("non-deterministic renderer output: " + ", ".join(sorted(nondeterministic)), file=sys.stderr)
            return 1
        total_artifacts = len(ARTIFACT_RENDERERS) + len(TEST_ARTIFACT_RENDERERS)
        print(f"all {total_artifacts} artifacts render deterministically")
        stale = stale_matrix_message(spec)
        if stale is not None:
            print(stale, file=sys.stderr)
            return 1
        print(f"{MATRIX_PATH.relative_to(ROOT)} is up to date")
        return 0
    parser.error(f"unsupported command: {arguments.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
