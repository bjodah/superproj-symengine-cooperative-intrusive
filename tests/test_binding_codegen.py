"""Regression tests for Phase 1 shared binding specification validation."""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path
import re

import pytest
import yaml

from tools.binding_codegen import inspect_cpp
from tools.binding_codegen.inspect_cpp import CppFunction
from tools.binding_codegen.model import SpecValidationError, validate_spec
from tools.binding_codegen.render_nbsymengine import (
    python_excluded_names,
    render_python_inc,
    render_python_pyi,
)
from tools.binding_codegen.coverage import coverage_rows, render_coverage_matrix, render_coverage_report
from tools.binding_codegen.render_perl import render_perl_xs_inc
from tools.binding_codegen.render_php import render_php_function_table_inc, render_php_inc, render_php_stub
from tools.binding_codegen.render_swift import render_swift_api, render_swift_cpp
from tools.binding_codegen.render_java import render_java_api, render_java_cpp, render_java_jni
from tools.binding_codegen.render_tests import (
    render_java_tests,
    render_perl_tests,
    render_php_tests,
    render_python_tests,
    render_swift_tests,
)
from tools.binding_codegen.test_cases import ArrangeValue, validate_test_cases
from tools import check_binding_api_fixtures as fixture_check
from tools.binding_codegen import __main__ as codegen_main
from tools.binding_codegen import render_common, render_tests
from tools.binding_codegen.model import BindingSpec
from tools.binding_codegen.render_java import SUPPORTED_FAMILIES as JAVA_FAMILIES, java_functions
from tools.binding_codegen.render_nbsymengine import python_functions
from tools.binding_codegen.render_perl import SUPPORTED_FAMILIES as PERL_FAMILIES, perl_functions
from tools.binding_codegen.render_php import SUPPORTED_FAMILIES as PHP_FAMILIES, php_functions
from tools.binding_codegen.render_swift import SUPPORTED_FAMILIES as SWIFT_FAMILIES, swift_functions


ROOT = Path(__file__).resolve().parents[1]
API_PATH = ROOT / "binding-spec" / "api.yaml"
TEST_CASES_PATH = ROOT / "binding-spec" / "test-cases.yaml"


def api_document() -> dict:
    return yaml.safe_load(API_PATH.read_text(encoding="utf-8"))


def entry(document: dict, id_: str) -> dict:
    return next(item for item in document["functions"] if item["id"] == id_)


def validate_document(tmp_path: Path, document: dict) -> None:
    path = tmp_path / "api.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    validate_spec(path)


def assert_invalid(tmp_path: Path, document: dict, message: str) -> None:
    with pytest.raises(SpecValidationError, match=message):
        validate_document(tmp_path, document)


def cases_document() -> dict:
    return yaml.safe_load(TEST_CASES_PATH.read_text(encoding="utf-8"))


def case_entry(document: dict, id_: str) -> dict:
    return next(item for item in document["cases"] if item["id"] == id_)


def validate_cases_document(tmp_path: Path, document: dict) -> None:
    path = tmp_path / "test-cases.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    validate_test_cases(path)


def assert_invalid_cases(tmp_path: Path, document: dict, message: str) -> None:
    with pytest.raises(SpecValidationError, match=message):
        validate_cases_document(tmp_path, document)


def test_committed_spec_validates_and_resolves_documented_names() -> None:
    spec = validate_spec(API_PATH)
    assert len(spec.functions) == 90
    sub = next(function for function in spec.functions if function.id == "sub")
    assert sub.public_name("php") == "symengine_sub"
    assert sub.public_name("swift") == "subtract"
    assert sub.public_name("perl") == "sub"


def test_schema_rejects_misspelled_required_field(tmp_path: Path) -> None:
    document = api_document()
    add = entry(document, "add")
    add["returnz"] = add.pop("returns")
    assert_invalid(tmp_path, document, r"entry 'add'.*returns")


def test_rejects_unknown_type(tmp_path: Path) -> None:
    document = api_document()
    entry(document, "add")["arguments"][0]["type"] = "does_not_exist"
    assert_invalid(tmp_path, document, r"entry 'add'.*unknown type 'does_not_exist'")


def test_rejects_missing_renderer(tmp_path: Path) -> None:
    document = api_document()
    entry(document, "add")["expose"].append("ruby")
    assert_invalid(tmp_path, document, r"entry 'add'.*no renderer.*ruby")


def test_rejects_duplicate_resolved_public_name(tmp_path: Path) -> None:
    document = api_document()
    entry(document, "div")["names"] = {"python": "add", "swift": "divide"}
    assert_invalid(tmp_path, document, r"duplicate resolved python name 'add'")


def test_rejects_reserved_default_name_without_override(tmp_path: Path) -> None:
    document = api_document()
    entry(document, "sub")["names"] = {"swift": "subtract"}
    assert_invalid(tmp_path, document, r"resolved perl name 'sub' is reserved")


def test_rejects_unsupported_default_value(tmp_path: Path) -> None:
    document = api_document()
    entry(document, "neg")["arguments"][0]["default"] = 0
    assert_invalid(tmp_path, document, r"entry 'neg'.*unsupported default value")


def test_rejects_missing_header(tmp_path: Path) -> None:
    document = api_document()
    entry(document, "add")["cpp"]["header"] = "symengine/no_such_header.h"
    assert_invalid(tmp_path, document, r"entry 'add'.*does not exist")


def test_rejects_nonexistent_function(tmp_path: Path) -> None:
    document = api_document()
    entry(document, "add")["cpp"]["name"] = "SymEngine::no_such_function"
    assert_invalid(tmp_path, document, r"entry 'add'.*no_such_function.*not found")


def test_rejects_ambiguous_overload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    document = api_document()
    two_basic = CppFunction(
        name="add",
        return_type="RCP<const Basic>",
        parameter_types=("const RCP<const Basic> &", "const RCP<const Basic> &"),
    )
    original = inspect_cpp._free_functions

    def duplicate_add(root: object) -> tuple[CppFunction, ...]:
        return (*original(root), two_basic)

    monkeypatch.setattr(inspect_cpp, "_free_functions", duplicate_add)
    assert_invalid(tmp_path, document, r"entry 'add'.*ambiguous")


def test_python_renderer_is_deterministic_and_uses_exact_exclusions() -> None:
    spec = validate_spec(API_PATH)
    assert render_python_inc(spec) == render_python_inc(spec)
    assert render_python_pyi(spec) == render_python_pyi(spec)
    exclusions = python_excluded_names(spec)
    assert "^sin$" in exclusions
    assert "^add$" in exclusions


def test_common_language_renderers_are_deterministic_and_keep_runtime_boundaries() -> None:
    spec = validate_spec(API_PATH)
    for renderer in (
        render_perl_xs_inc,
        render_php_inc,
        render_php_function_table_inc,
        render_php_stub,
        render_swift_cpp,
        render_swift_api,
        render_java_jni,
        render_java_api,
        render_java_cpp,
    ):
        assert renderer(spec) == renderer(spec)

    assert "SymEnginePerl::wrap_basic_perl_owned" in render_perl_xs_inc(spec)
    assert "symengine_throw_cpp_exception" in render_php_inc(spec)
    assert "make_result" in render_swift_cpp(spec)
    assert "adopt(" in render_swift_api(spec)
    assert "static native byte[] string(long handle);" in render_java_jni(spec)


def test_coverage_is_complete_and_java_generates_the_common_surface() -> None:
    spec = validate_spec(API_PATH)
    rows = coverage_rows(spec)
    assert len(rows) == len(spec.functions) * 5
    assert all(status in {"generated", "manual", "not exposed"}
               for _, _, status in rows)
    java_status = {entry: status for entry, language, status in rows if language == "java"}
    for common in ("add", "sub", "mul", "div", "pow", "neg", "sin", "zero", "one", "pi",
                   "eq", "lt", "gcd", "nextprime", "totient"):
        assert java_status[common] == "generated"
    # Families no renderer but Python supports yet.
    assert java_status["mod_inverse"] == "not exposed"
    assert java_status["prime_factors"] == "not exposed"
    assert "| `add` | perl | generated |" in render_coverage_report(spec)


def test_generated_python_keyword_arguments_match_phase0_fixture() -> None:
    """Generation may improve annotations/order, never accepted keyword names."""
    def signatures(source: str) -> dict[str, tuple[str, ...]]:
        return {
            node.name: tuple(argument.arg for argument in node.args.args)
            for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef)
        }

    fixture = ROOT / "tests" / "binding_api_fixtures" / "python-api.txt"
    expected = {
        match.group("name"): tuple(
            part.strip().split(":", 1)[0].split("=", 1)[0].strip()
            for part in match.group("arguments").split(",") if part.strip()
        )
        for match in re.finditer(
            r"^def (?P<name>\w+)\((?P<arguments>[^)]*)\)",
            fixture.read_text(encoding="utf-8"), re.MULTILINE,
        )
    }
    actual = signatures(render_python_pyi(validate_spec(API_PATH)))
    shared = set(expected) & set(actual)
    assert shared
    assert {name: actual[name] for name in shared} == {name: expected[name] for name in shared}


def test_fixture_checker_extracts_union_of_manual_and_generated_surface() -> None:
    """Phase 3 moved mechanical entries into generated sources; the checker
    must record manual and generated declarations together, matching the
    Phase 0 fixtures which are the baseline for the public surface."""
    for name, extractor in (
        ("perl-xsubs.txt", fixture_check.perl_xsubs),
        ("php-functions.txt", fixture_check.php_functions),
        ("swift-api.txt", fixture_check.swift_surface),
        ("java-api.txt", fixture_check.java_surface),
    ):
        assert fixture_check.compare(name, extractor())


def test_fixture_checker_generated_functions_appear_in_extracted_surface() -> None:
    assert "add(a, b) -> SV *" in fixture_check.perl_xsubs()
    assert "symengine_add -> arginfo_symengine_add" in fixture_check.php_functions()
    assert "symengine_swift_basic_ref symengine_swift_add(symengine_swift_basic_ref a, symengine_swift_basic_ref b)" in fixture_check.swift_surface()


def test_coverage_matrix_has_one_row_per_entry_and_no_digest() -> None:
    spec = validate_spec(API_PATH)
    matrix = render_coverage_matrix(spec)
    assert matrix == render_coverage_matrix(spec)
    assert "DO NOT EDIT" in matrix
    assert "spec_sha256" not in matrix
    assert "| `add` | generated | generated | generated | generated | generated |" in matrix
    assert matrix.count("\n| `") == len(spec.functions)


def test_find_nondeterministic_artifacts_reports_a_broken_renderer(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = validate_spec(API_PATH)
    suite = validate_test_cases(spec=spec)
    assert codegen_main.find_nondeterministic_artifacts(spec, suite) == ()

    calls = {"count": 0}
    stable = codegen_main.ARTIFACT_RENDERERS["perl:SymEngine.generated.xs.inc"]

    def flaky(spec: object) -> str:
        calls["count"] += 1
        return stable(spec) + ("" if calls["count"] % 2 else " ")

    monkeypatch.setitem(codegen_main.ARTIFACT_RENDERERS, "perl:SymEngine.generated.xs.inc", flaky)
    assert codegen_main.find_nondeterministic_artifacts(spec, suite) == ("perl:SymEngine.generated.xs.inc",)

    calls["count"] = 0
    stable_test_renderer = codegen_main.TEST_ARTIFACT_RENDERERS["python:test_shared_cases.py"]

    def flaky_test_renderer(spec: object, suite: object) -> str:
        calls["count"] += 1
        return stable_test_renderer(spec, suite) + ("" if calls["count"] % 2 else " ")

    monkeypatch.setitem(codegen_main.TEST_ARTIFACT_RENDERERS, "python:test_shared_cases.py", flaky_test_renderer)
    assert "python:test_shared_cases.py" in codegen_main.find_nondeterministic_artifacts(spec, suite)


def test_stale_matrix_message_detects_missing_and_stale_and_fresh_docs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = validate_spec(API_PATH)
    matrix_path = tmp_path / "binding-api-matrix.md"
    monkeypatch.setattr(codegen_main, "MATRIX_PATH", matrix_path)

    missing = codegen_main.stale_matrix_message(spec)
    assert missing is not None and "missing" in missing

    matrix_path.write_text(render_coverage_matrix(spec) + "stale trailer\n", encoding="utf-8")
    stale = codegen_main.stale_matrix_message(spec)
    assert stale is not None and "stale" in stale
    assert "python -m tools.binding_codegen coverage --matrix" in stale

    matrix_path.write_text(render_coverage_matrix(spec), encoding="utf-8")
    assert codegen_main.stale_matrix_message(spec) is None


def test_check_command_end_to_end(capsys: pytest.CaptureFixture[str]) -> None:
    assert codegen_main.main(["check"]) == 0
    output = capsys.readouterr()
    assert "artifacts render deterministically" in output.out
    assert "is up to date" in output.out


# --- Phase 5: shared behavioral test cases ----------------------------------


def test_committed_test_cases_validate_against_the_spec() -> None:
    spec = validate_spec(API_PATH)
    suite = validate_test_cases(TEST_CASES_PATH, spec=spec)
    assert len(suite.cases) == 46
    ids = {case.id for case in suite.cases}
    assert ids == {
        "add_integers", "sub_integers", "mul_integers", "div_integers",
        "pow_integers", "neg_integer", "sin_symbol",
        "add_symbol_integer", "sub_symbol_integer", "mul_symbol_integer",
        "div_symbol_integer", "pow_symbol_integer", "neg_symbol",
        "zero_constant", "one_constant", "pi_constant", "minus_one_constant",
        "two_constant", "i_constant", "e_constant", "euler_gamma_constant",
        "catalan_constant", "golden_ratio_constant", "inf_constant",
        "neg_inf_constant", "complex_inf_constant", "nan_constant",
        "sqrt_integer", "log_symbol", "abs_negative_integer", "cosh_symbol",
        "asin_symbol", "gamma_integer", "zeta_integer", "atan2_integers",
        "eq_equal_integers", "ne_distinct_integers", "lt_symbol_integer",
        "le_symbols", "ge_symbol_integer", "gt_integers",
        "gcd_integers", "lcm_integers", "nextprime_integer",
        "totient_integer", "carmichael_integer",
    }


def test_rejects_unknown_case_function(tmp_path: Path) -> None:
    document = cases_document()
    case_entry(document, "add_integers")["call"]["function"] = "does_not_exist"
    assert_invalid_cases(tmp_path, document, r"case 'add_integers'.*unknown function 'does_not_exist'")


def test_rejects_unknown_arrange_variable(tmp_path: Path) -> None:
    document = cases_document()
    case_entry(document, "add_integers")["call"]["arguments"] = ["x", "does_not_exist"]
    assert_invalid_cases(tmp_path, document, r"case 'add_integers'.*unknown arrange variable 'does_not_exist'")


def test_rejects_call_argument_count_mismatch(tmp_path: Path) -> None:
    document = cases_document()
    case_entry(document, "add_integers")["call"]["arguments"] = ["x"]
    assert_invalid_cases(tmp_path, document, r"case 'add_integers'.*1 argument.*expected 2")


def test_rejects_duplicate_case_id(tmp_path: Path) -> None:
    document = cases_document()
    duplicate = dict(case_entry(document, "add_integers"))
    document["cases"].append(duplicate)
    assert_invalid_cases(tmp_path, document, r"case 'add_integers': duplicate id")


def test_rejects_unknown_arrange_kind(tmp_path: Path) -> None:
    document = cases_document()
    case_entry(document, "add_integers")["arrange"]["x"] = {"float": 2}
    assert_invalid_cases(tmp_path, document, r"arrange.x")


def test_rejects_case_missing_required_field(tmp_path: Path) -> None:
    document = cases_document()
    entry_ = case_entry(document, "add_integers")
    entry_["expects"] = entry_.pop("expect")
    assert_invalid_cases(tmp_path, document, r"expect")


def test_rejects_unknown_top_level_property(tmp_path: Path) -> None:
    document = cases_document()
    document["extra"] = True
    assert_invalid_cases(tmp_path, document, r"<root>")


def test_test_renderers_are_deterministic() -> None:
    spec = validate_spec(API_PATH)
    suite = validate_test_cases(TEST_CASES_PATH, spec=spec)
    for renderer in (
        render_python_tests,
        render_perl_tests,
        render_php_tests,
        render_swift_tests,
        render_java_tests,
    ):
        assert renderer(spec, suite) == renderer(spec, suite)


def test_test_renderers_carry_the_standard_header() -> None:
    spec = validate_spec(API_PATH)
    suite = validate_test_cases(TEST_CASES_PATH, spec=spec)
    for renderer in (
        render_python_tests,
        render_perl_tests,
        render_php_tests,
        render_swift_tests,
        render_java_tests,
    ):
        assert "AUTO-GENERATED" in renderer(spec, suite)


def test_test_renderers_sort_cases_by_id_independent_of_yaml_order() -> None:
    spec = validate_spec(API_PATH)
    suite = validate_test_cases(TEST_CASES_PATH, spec=spec)
    rendered = render_python_tests(spec, suite)
    positions = [rendered.index(f"test_{case_id}") for case_id in (
        "add_integers", "div_integers", "mul_integers", "neg_integer",
        "one_constant", "pi_constant", "pow_integers", "sin_symbol",
        "sub_integers", "zero_constant",
    )]
    assert positions == sorted(positions)


def test_renderers_skip_a_case_whose_function_is_not_exposed_with_a_named_reason() -> None:
    """Every ``unary_basic``/``binary_basic`` entry is exposed everywhere, so the
    skip path is exercised against a spec with ``sin`` withdrawn instead."""
    spec = validate_spec(API_PATH)
    suite = validate_test_cases(TEST_CASES_PATH, spec=spec)
    withdrawn = dataclasses.replace(
        next(function for function in spec.functions if function.id == "sin"),
        expose=("python", "perl", "java"),
    )
    mutated = dataclasses.replace(
        spec,
        functions=tuple(withdrawn if function.id == "sin" else function
                        for function in spec.functions),
    )
    swift_output = render_swift_tests(mutated, suite)
    assert "SKIPPED case 'sin_symbol'" in swift_output
    assert "not exposed to swift" in swift_output
    assert "func test_sin_symbol" not in swift_output

    php_output = render_php_tests(mutated, suite)
    assert "SKIPPED case 'sin_symbol'" in php_output
    assert "not exposed to php" in php_output


def test_every_wrapper_but_python_includes_every_case() -> None:
    spec = validate_spec(API_PATH)
    suite = validate_test_cases(TEST_CASES_PATH, spec=spec)
    for renderer, needle in (
        (render_java_tests, "sin"),
        (render_perl_tests, "sin_symbol"),
        (render_php_tests, "symengine_sqrt"),
        (render_swift_tests, "test_atan2_integers"),
    ):
        assert "SKIPPED" not in renderer(spec, suite)
        assert needle in renderer(spec, suite)


def test_python_renderer_skips_only_the_constants_it_does_not_expose() -> None:
    """Python is the one language exposing `sin` but not every singleton."""
    spec = validate_spec(API_PATH)
    suite = validate_test_cases(TEST_CASES_PATH, spec=spec)
    rendered = render_python_tests(spec, suite)
    assert "def test_sin_symbol" in rendered
    skipped = set(re.findall(r"# SKIPPED case '(\w+)'", rendered))
    assert skipped == {
        "catalan_constant", "golden_ratio_constant", "minus_one_constant",
        "neg_inf_constant", "two_constant",
    }
    assert "is not exposed to python" in rendered


def test_generate_writes_a_test_file_for_every_language(tmp_path: Path) -> None:
    for language, name in (
        ("python", "test_shared_cases.py"),
        ("perl", "shared_cases.t"),
        ("php", "shared_cases.phpt"),
        ("swift", "SharedCasesTests.swift"),
        ("java", "SharedCasesTest.java"),
    ):
        output = tmp_path / language
        assert codegen_main.main(["generate", "--language", language, "--output", str(output)]) == 0
        assert (output / name).exists()


def test_php_generated_test_file_places_header_after_the_open_tag() -> None:
    spec = validate_spec(API_PATH)
    suite = validate_test_cases(TEST_CASES_PATH, spec=spec)
    rendered = render_php_tests(spec, suite)
    file_section = rendered.split("--FILE--\n", 1)[1].split("\n--EXPECT--", 1)[0]
    assert file_section.startswith("<?php")


def test_check_command_validates_test_cases(capsys: pytest.CaptureFixture[str]) -> None:
    assert codegen_main.main(["check"]) == 0
    output = capsys.readouterr()
    assert "shared behavioral test cases" in output.out


# --- Shared renderer helpers ------------------------------------------------


def test_functions_for_language_backs_every_per_language_selection() -> None:
    spec = validate_spec(API_PATH)
    for language, families, selector in (
        ("python", None, python_functions),
        ("perl", PERL_FAMILIES, perl_functions),
        ("php", PHP_FAMILIES, php_functions),
        ("swift", SWIFT_FAMILIES, swift_functions),
        ("java", JAVA_FAMILIES, java_functions),
    ):
        selected = render_common.functions_for_language(spec, language, families)
        assert selected == selector(spec)
        assert [function.id for function in selected] == sorted(function.id for function in selected)
        assert all(language in function.expose and function.implementation == "generated"
                   for function in selected)


def test_functions_for_language_names_the_language_of_an_unsupported_behavior() -> None:
    spec = validate_spec(API_PATH)
    unsupported = dataclasses.replace(
        next(function for function in spec.functions if function.id == "add"),
        behavior="list_integer_to_basic",
    )
    mutated = dataclasses.replace(
        spec,
        functions=tuple(unsupported if function.id == "add" else function
                        for function in spec.functions),
    )
    for language, families, label in (
        ("perl", PERL_FAMILIES, "Perl"),
        ("php", PHP_FAMILIES, "PHP"),
        ("swift", SWIFT_FAMILIES, "Swift"),
        ("java", JAVA_FAMILIES, "Java"),
    ):
        with pytest.raises(ValueError) as error:
            render_common.functions_for_language(mutated, language, families)
        assert str(error.value) == (
            f"entry 'add': {label} renderer does not support 'list_integer_to_basic'"
        )
    # Without a supported set nothing is rejected; Python reports at render time.
    assert unsupported in render_common.functions_for_language(mutated, "python")


def test_every_non_python_renderer_supports_the_same_families() -> None:
    """Nothing forces the four sets to agree, but a divergence should be a
    deliberate edit rather than a renderer someone forgot to widen."""
    for families in (PERL_FAMILIES, PHP_FAMILIES, SWIFT_FAMILIES, JAVA_FAMILIES):
        assert families == frozenset((
            "singleton", "unary_basic", "binary_basic", "binary_boolean",
            "integer_unary", "integer_binary",
        ))
        # Still Python-only; they need a documented adapter policy first.
        assert "status_optional_unary" not in families
        assert "list_integer_to_basic" not in families


def test_cpp_call_passes_basic_arguments_straight_through() -> None:
    """``binary_boolean`` is call-compatible with ``binary_basic``: the result
    is an ordinary expression handle, so no wrapper needs a special path."""
    spec = validate_spec(API_PATH)
    equality = next(function for function in spec.functions if function.id == "eq")
    prologue, call = render_common.cpp_call(equality, lambda argument: f"unwrap({argument.name})")
    assert prologue == []
    assert call == "SymEngine::Eq(unwrap(a), unwrap(b))"

    constant = next(function for function in spec.functions if function.id == "pi")
    assert render_common.cpp_call(constant, lambda argument: "unused") == ([], "SymEngine::pi")


def test_cpp_call_guards_every_integer_argument_and_honours_deref() -> None:
    spec = validate_spec(API_PATH)
    gcd = next(function for function in spec.functions if function.id == "gcd")
    prologue, call = render_common.cpp_call(
        gcd, lambda argument: f"unwrap({argument.name})", indent="  "
    )
    assert call == "SymEngine::gcd(*a_integer, *b_integer)"
    assert prologue == [
        "  SymEngine::RCP<const SymEngine::Basic> a_basic = unwrap(a);",
        "  if (!SymEngine::is_a<SymEngine::Integer>(*a_basic)) {",
        '      throw SymEngine::SymEngineException("gcd(): argument \'a\' must be an Integer");',
        "  }",
        "  SymEngine::RCP<const SymEngine::Integer> a_integer",
        "      = SymEngine::rcp_static_cast<const SymEngine::Integer>(a_basic);",
        "  SymEngine::RCP<const SymEngine::Basic> b_basic = unwrap(b);",
        "  if (!SymEngine::is_a<SymEngine::Integer>(*b_basic)) {",
        '      throw SymEngine::SymEngineException("gcd(): argument \'b\' must be an Integer");',
        "  }",
        "  SymEngine::RCP<const SymEngine::Integer> b_integer",
        "      = SymEngine::rcp_static_cast<const SymEngine::Integer>(b_basic);",
    ]

    # ``totient`` takes ``const RCP<const Integer> &``, so it must not deref.
    totient = next(function for function in spec.functions if function.id == "totient")
    assert render_common.cpp_call(totient, lambda argument: "unwrap")[1] == (
        "SymEngine::totient(a_integer)"
    )


def test_every_wrapper_guards_typed_arguments_and_reports_it_its_own_way() -> None:
    """One generated guard per language, each ending in that runtime's error
    channel: croak, zend_throw_exception, last_error, SymEngineException."""
    spec = validate_spec(API_PATH)
    guard = 'throw SymEngine::SymEngineException("nextprime(): argument \'a\' must be an Integer");'
    for renderer, unwrap, reporter in (
        (render_perl_xs_inc, "SymEnginePerl::unwrap_basic(a)", "croak_current_exception();"),
        (render_php_inc, "symengine_unwrap_basic(a)", "symengine_throw_cpp_exception(error);"),
        (render_swift_cpp, "SymEngine::rcp(require_basic(a))", "make_result"),
        (render_java_cpp, "symengine_java::require_handle(a)", "symengine_java::throw_exception"),
    ):
        rendered = renderer(spec)
        assert guard in rendered
        assert f"SymEngine::RCP<const SymEngine::Basic> a_basic = {unwrap};" in rendered
        assert "SymEngine::rcp_static_cast<const SymEngine::Integer>(a_basic);" in rendered
        assert reporter in rendered
        # Basic-only entries keep their previous single-expression shape.
        assert "SymEngine::Eq(" in rendered
        assert "Eq(a_basic" not in rendered


def test_relational_entries_reach_every_public_surface_under_documented_names() -> None:
    spec = validate_spec(API_PATH)
    relational = next(function for function in spec.functions if function.id == "eq")
    assert relational.public_name("python") == "Eq"
    assert relational.public_name("perl") == "eq"
    assert relational.public_name("swift") == "eq"
    assert relational.public_name("java") == "eq"
    # PHP already owns symengine_eq() as the structural predicate and its
    # function names are case-insensitive, so this one entry is renamed.
    assert relational.public_name("php") == "symengine_eq_relational"
    assert "PHP_FUNCTION(symengine_eq_relational)" in render_php_inc(spec)
    assert "function symengine_eq_relational(" in render_php_stub(spec)
    assert "static func lt(_ a: Basic, _ b: Basic) throws -> Basic {" in render_swift_api(spec)
    assert "static native long gcd(long a, long b);" in render_java_jni(spec)
    assert "public static Basic carmichael(Basic a) {" in render_java_api(spec)


def test_header_banner_is_shared_and_comment_marker_aware() -> None:
    spec = validate_spec(API_PATH)
    lines = render_common.header(spec, "//")
    assert lines == [
        "// AUTO-GENERATED — DO NOT EDIT.",
        f"// schema_version: {spec.schema_version}; spec_sha256: {render_common.spec_digest(spec)}; "
        f"generator_version: {render_common.GENERATOR_VERSION}",
    ]
    assert render_common.header(spec, "#")[0] == "# AUTO-GENERATED — DO NOT EDIT."


def test_spec_digest_is_cached_per_file_and_stays_whitespace_insensitive(tmp_path: Path) -> None:
    path = tmp_path / "api.yaml"
    path.write_text("schema_version: 1\nfunctions: []\n", encoding="utf-8")
    spec = BindingSpec(schema_version=1, types={}, functions=(), source_path=path)

    digest = render_common.spec_digest(spec)
    assert any(key[0] == str(path) for key in render_common._DIGEST_CACHE)
    assert render_common.spec_digest(spec) == digest

    path.write_text("schema_version:    1\nfunctions:    []\n", encoding="utf-8")
    assert render_common.spec_digest(spec) == digest

    path.write_text("schema_version: 1\nfunctions: [{id: add}]\n", encoding="utf-8")
    assert render_common.spec_digest(spec) != digest


def test_language_profiles_spell_arrange_values_per_language() -> None:
    integer = ArrangeValue(kind="integer", value=2)
    symbol = ArrangeValue(kind="symbol", value="x")
    for profile, expected_integer, expected_symbol in (
        (render_tests.PYTHON, "sx.integer(2)", "sx.symbol('x')"),
        (render_tests.PERL, "SymEngine::integer(2)", "SymEngine::symbol('x')"),
        (render_tests.PHP, "symengine_integer(2)", "symengine_symbol('x')"),
        (render_tests.SWIFT, "try SymEngine.integer(2)", 'try SymEngine.symbol("x")'),
        (render_tests.JAVA, "SymEngine.integer(2)", 'SymEngine.symbol("x")'),
    ):
        assert profile.arrange(integer) == expected_integer
        assert profile.arrange(symbol) == expected_symbol
        with pytest.raises(ValueError, match="unsupported arrange kind"):
            profile.arrange(ArrangeValue(kind="float", value=1.5))


def test_language_profile_string_literals_escape_their_own_delimiters() -> None:
    for profile in (render_tests.PERL, render_tests.PHP):
        assert profile.string_literal("a'b\\c") == "'a\\'b\\\\c'"
    for profile in (render_tests.SWIFT, render_tests.JAVA):
        assert profile.string_literal('a"b\\c') == '"a\\"b\\\\c"'
