"""Render shared behavioral test cases into each wrapper's native test format.

Every renderer here consumes the same parsed ``TestCaseSuite`` plus the
``BindingSpec`` it was validated against. A case whose function is not
exposed to a language is skipped with an explicit comment naming the case and
the reason (never silently, per the roadmap). A case whose function is
exposed but ``implementation: manual`` is still rendered: it tests runtime
behavior, not codegen.
"""

from __future__ import annotations

from .model import BindingSpec, Function
from .render_nbsymengine import _header
from .test_cases import ArrangeValue, TestCase, TestCaseSuite


def _sorted_cases(suite: TestCaseSuite) -> tuple[TestCase, ...]:
    return tuple(sorted(suite.cases, key=lambda case: case.id))


def _functions_by_id(spec: BindingSpec) -> dict[str, Function]:
    return {function.id: function for function in spec.functions}


def _skip_reason(case: TestCase, function: Function, language: str) -> str | None:
    if language not in function.expose:
        return f"'{function.id}' is not exposed to {language}"
    return None


# --- Python -----------------------------------------------------------------


def render_python_tests(spec: BindingSpec, suite: TestCaseSuite) -> str:
    """Render a pytest file exercising the shared behavioral cases."""
    functions = _functions_by_id(spec)
    lines = _header(spec, "#")
    lines.extend([
        "import nbsymengine as sx",
        "",
        "",
    ])
    for case in _sorted_cases(suite):
        function = functions[case.call.function]
        reason = _skip_reason(case, function, "python")
        if reason is not None:
            lines.append(f"# SKIPPED case '{case.id}': {reason}")
            continue
        lines.append(f"def test_{case.id}():")
        for name, argument in sorted(case.arrange.items()):
            lines.append(f"    {name} = {_python_arrange(argument)}")
        arguments = ", ".join(case.call.arguments)
        public_name = function.public_name("python")
        lines.append(f"    result = sx.{public_name}({arguments})")
        lines.append(f"    assert sx.str(result) == {case.expect.string!r}")
        lines.append("")
    return "\n".join(lines) + "\n"


def _python_arrange(argument: ArrangeValue) -> str:
    if argument.kind == "integer":
        return f"sx.integer({argument.value!r})"
    if argument.kind == "symbol":
        return f"sx.symbol({argument.value!r})"
    raise ValueError(f"unsupported arrange kind {argument.kind!r}")  # pragma: no cover - schema-guarded


# --- Perl ---------------------------------------------------------------


def render_perl_tests(spec: BindingSpec, suite: TestCaseSuite) -> str:
    """Render a Test::More ``.t`` file exercising the shared behavioral cases."""
    functions = _functions_by_id(spec)
    lines = _header(spec, "#")
    lines.extend([
        "use strict;",
        "use warnings;",
        "use Test::More;",
        "",
        "use SymEngine;",
        "",
    ])
    emitted = 0
    for case in _sorted_cases(suite):
        function = functions[case.call.function]
        reason = _skip_reason(case, function, "perl")
        if reason is not None:
            lines.append(f"# SKIPPED case '{case.id}': {reason}")
            continue
        lines.append("{")
        for name, argument in sorted(case.arrange.items()):
            lines.append(f"    my ${name} = {_perl_arrange(argument)};")
        arguments = ", ".join(f"${name}" for name in case.call.arguments)
        public_name = function.public_name("perl")
        lines.append(
            f'    is("" . SymEngine::{public_name}({arguments}), '
            f'{_perl_string(case.expect.string)}, {_perl_string(case.id)});'
        )
        lines.append("}")
        emitted += 1
    lines.append(f"done_testing({emitted});" if emitted else "done_testing();")
    return "\n".join(lines) + "\n"


def _perl_arrange(argument: ArrangeValue) -> str:
    if argument.kind == "integer":
        return f"SymEngine::integer({int(argument.value)})"
    if argument.kind == "symbol":
        return f"SymEngine::symbol({_perl_string(str(argument.value))})"
    raise ValueError(f"unsupported arrange kind {argument.kind!r}")  # pragma: no cover - schema-guarded


def _perl_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


# --- PHP ------------------------------------------------------------------


def render_php_tests(spec: BindingSpec, suite: TestCaseSuite) -> str:
    """Render a ``.phpt`` file exercising the shared behavioral cases."""
    functions = _functions_by_id(spec)
    header = _header(spec, "#")
    body: list[str] = []
    expect: list[str] = []
    for case in _sorted_cases(suite):
        function = functions[case.call.function]
        reason = _skip_reason(case, function, "php")
        if reason is not None:
            body.append(f"// SKIPPED case '{case.id}': {reason}")
            continue
        for name, argument in sorted(case.arrange.items()):
            body.append(f"${name} = {_php_arrange(argument)};")
        arguments = ", ".join(f"${name}" for name in case.call.arguments)
        public_name = function.public_name("php")
        body.append(f'echo symengine_str({public_name}({arguments})), "\\n";')
        expect.append(case.expect.string)
    lines = [
        "--TEST--",
        "Shared behavioral test cases (generated)",
        "--SKIPIF--",
        "<?php if (!extension_loaded('symengine')) die('skip symengine extension not loaded'); ?>",
        "--FILE--",
        "<?php",
        *header,
        *body,
        "?>",
        "--EXPECT--",
        *expect,
    ]
    return "\n".join(lines) + "\n"


def _php_arrange(argument: ArrangeValue) -> str:
    if argument.kind == "integer":
        return f"symengine_integer({int(argument.value)})"
    if argument.kind == "symbol":
        return f"symengine_symbol({_php_string(str(argument.value))})"
    raise ValueError(f"unsupported arrange kind {argument.kind!r}")  # pragma: no cover - schema-guarded


def _php_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


# --- Swift ------------------------------------------------------------------


def render_swift_tests(spec: BindingSpec, suite: TestCaseSuite) -> str:
    """Render an XCTest file exercising the shared behavioral cases."""
    functions = _functions_by_id(spec)
    lines = _header(spec, "//")
    lines.extend([
        "import XCTest",
        "@testable import SymEngine",
        "",
        "final class SharedCasesTests: XCTestCase {",
    ])
    for case in _sorted_cases(suite):
        function = functions[case.call.function]
        reason = _skip_reason(case, function, "swift")
        if reason is not None:
            lines.append(f"    // SKIPPED case '{case.id}': {reason}")
            continue
        lines.append(f"    func test_{case.id}() throws {{")
        for name, argument in sorted(case.arrange.items()):
            lines.append(f"        let {name} = {_swift_arrange(argument)}")
        arguments = ", ".join(case.call.arguments)
        public_name = function.public_name("swift")
        lines.append(f"        let result = try SymEngine.{public_name}({arguments})")
        lines.append(f'        XCTAssertEqual(try result.string(), {_swift_string(case.expect.string)})')
        lines.append("    }")
        lines.append("")
    lines.append("}")
    return "\n".join(lines) + "\n"


def _swift_arrange(argument: ArrangeValue) -> str:
    if argument.kind == "integer":
        return f"try SymEngine.integer({int(argument.value)})"
    if argument.kind == "symbol":
        return f"try SymEngine.symbol({_swift_string(str(argument.value))})"
    raise ValueError(f"unsupported arrange kind {argument.kind!r}")  # pragma: no cover - schema-guarded


def _swift_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


# --- Java -------------------------------------------------------------------


def render_java_tests(spec: BindingSpec, suite: TestCaseSuite) -> str:
    """Render a Java assert-runner class exercising the shared behavioral cases."""
    functions = _functions_by_id(spec)
    lines = _header(spec, "//")
    lines.extend([
        "package org.symengine;",
        "",
        "/** Generated shared behavioral test cases; run via ctest like SmokeTest. */",
        "public final class SharedCasesTest {",
        "    public static void main(String[] arguments) throws Exception {",
    ])
    for case in _sorted_cases(suite):
        function = functions[case.call.function]
        reason = _skip_reason(case, function, "java")
        if reason is not None:
            lines.append(f"        // SKIPPED case '{case.id}': {reason}")
            continue
        lines.append("        try (" + _java_try_with_resources(case, function) + ") {")
        lines.append(
            f'            assert result_{case.id}.toString().equals({_java_string(case.expect.string)}) '
            f': "case \'{case.id}\' failed";'
        )
        lines.append("        }")
    lines.extend([
        "    }",
        "}",
    ])
    return "\n".join(lines) + "\n"


def _java_try_with_resources(case: TestCase, function: Function) -> str:
    declarations = []
    for name, argument in sorted(case.arrange.items()):
        declarations.append(f"Basic {name} = {_java_arrange(argument)}")
    arguments = ", ".join(case.call.arguments)
    public_name = function.public_name("java")
    declarations.append(f"Basic result_{case.id} = SymEngine.{public_name}({arguments})")
    return "; ".join(declarations)


def _java_arrange(argument: ArrangeValue) -> str:
    if argument.kind == "integer":
        return f"SymEngine.integer({int(argument.value)})"
    if argument.kind == "symbol":
        return f"SymEngine.symbol({_java_string(str(argument.value))})"
    raise ValueError(f"unsupported arrange kind {argument.kind!r}")  # pragma: no cover - schema-guarded


def _java_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
