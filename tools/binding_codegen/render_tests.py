"""Render shared behavioral test cases into each wrapper's native test format.

Every renderer here consumes the same parsed ``TestCaseSuite`` plus the
``BindingSpec`` it was validated against. A case whose function is not
exposed to a language is skipped with an explicit comment naming the case and
the reason (never silently, per the roadmap). A case whose function is
exposed but ``implementation: manual`` is still rendered: it tests runtime
behavior, not codegen.

The languages differ only in spelling, so each one is a ``LanguageProfile``
describing its factory calls, string literals, file scaffolding, and the lines
one case expands to; ``_render`` is the single shared emission loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .model import BindingSpec, Function
from .render_common import RESULT_SHAPES, header
from .test_cases import ArrangeValue, TestCase, TestCaseSuite


def _sorted_cases(suite: TestCaseSuite) -> tuple[TestCase, ...]:
    return tuple(sorted(suite.cases, key=lambda case: case.id))


def _functions_by_id(spec: BindingSpec) -> dict[str, Function]:
    return {function.id: function for function in spec.functions}


def _skip_reason(function: Function, language: str) -> str | None:
    if language not in function.expose:
        return f"'{function.id}' is not exposed to {language}"
    return None


# --- String literals --------------------------------------------------------


def _single_quoted(value: str) -> str:
    """Perl/PHP single-quoted literal: only ``\\`` and ``'`` are special."""
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def _double_quoted(value: str) -> str:
    """Swift/Java double-quoted literal: only ``\\`` and ``"`` are special."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


# --- Language profiles ------------------------------------------------------


def _no_footer(emitted: tuple[TestCase, ...]) -> list[str]:
    """Default footer for formats whose case blocks are self-contained."""
    return []


@dataclass(frozen=True)
class LanguageProfile:
    """Everything that differs between the per-language test renderers."""

    language: str
    comment: str  # banner comment marker
    skip_prefix: str  # comment marker plus indentation for a skipped case
    integer_call: str  # ``{}``-templated integer factory spelling
    symbol_call: str  # ``{}``-templated symbol factory spelling
    string_literal: Callable[[str], str]
    emit_case: Callable[["LanguageProfile", TestCase, Function], list[str]]
    prologue: tuple[str, ...] = ()  # lines before the generated-file banner
    preamble: tuple[str, ...] = ()  # lines after the banner
    footer: Callable[[tuple[TestCase, ...]], list[str]] = _no_footer

    def arrange(self, argument: ArrangeValue) -> str:
        """Render one ``arrange`` entry as a factory call in this language."""
        if argument.kind == "integer":
            return self.integer_call.format(int(argument.value))
        if argument.kind == "symbol":
            return self.symbol_call.format(self.string_literal(str(argument.value)))
        raise ValueError(f"unsupported arrange kind {argument.kind!r}")  # schema-guarded


def _render(spec: BindingSpec, suite: TestCaseSuite, profile: LanguageProfile) -> str:
    """Emit a whole test file: scaffolding, one block per case, footer."""
    functions = _functions_by_id(spec)
    lines = [*profile.prologue, *header(spec, profile.comment), *profile.preamble]
    emitted: list[TestCase] = []
    for case in _sorted_cases(suite):
        function = functions[case.call.function]
        reason = _skip_reason(function, profile.language)
        if reason is not None:
            lines.append(f"{profile.skip_prefix}SKIPPED case '{case.id}': {reason}")
            continue
        lines.extend(profile.emit_case(profile, case, function))
        emitted.append(case)
    lines.extend(profile.footer(tuple(emitted)))
    return "\n".join(lines) + "\n"


# --- Python -----------------------------------------------------------------


def _python_case(profile: LanguageProfile, case: TestCase, function: Function) -> list[str]:
    lines = [f"def test_{case.id}():"]
    for name, argument in sorted(case.arrange.items()):
        lines.append(f"    {name} = {profile.arrange(argument)}")
    arguments = ", ".join(case.call.arguments)
    lines.append(f"    result = sx.{function.public_name('python')}({arguments})")
    if case.expect.kind == "string":
        lines.append(f"    assert sx.str(result) == {profile.string_literal(case.expect.string)}")
    elif case.expect.kind == "none":
        lines.append("    assert result is None")
    else:
        expected = ", ".join(profile.string_literal(item) for item in case.expect.strings)
        lines.append(f"    assert [sx.str(value) for value in result] == [{expected}]")
    lines.append("")
    return lines


PYTHON = LanguageProfile(
    language="python",
    comment="#",
    skip_prefix="# ",
    integer_call="sx.integer({})",
    symbol_call="sx.symbol({})",
    string_literal=repr,
    emit_case=_python_case,
    preamble=("import nbsymengine as sx", "", ""),
)


def render_python_tests(spec: BindingSpec, suite: TestCaseSuite) -> str:
    """Render a pytest file exercising the shared behavioral cases."""
    return _render(spec, suite, PYTHON)


# --- Perl ---------------------------------------------------------------


def _perl_case(profile: LanguageProfile, case: TestCase, function: Function) -> list[str]:
    lines = ["{"]
    for name, argument in sorted(case.arrange.items()):
        lines.append(f"    my ${name} = {profile.arrange(argument)};")
    arguments = ", ".join(f"${name}" for name in case.call.arguments)
    call = f"SymEngine::{function.public_name('perl')}({arguments})"
    label = profile.string_literal(case.id)
    if case.expect.kind == "string":
        lines.append(
            f'    is("" . {call}, {profile.string_literal(case.expect.string)}, {label});'
        )
    elif case.expect.kind == "none":
        lines.append(f"    is({call}, undef, {label});")
    else:
        # A list entry returns one reference to an array of wrapped handles.
        expected = ", ".join(profile.string_literal(item) for item in case.expect.strings)
        lines.append(
            f'    is_deeply([map {{ "" . $_ }} @{{ {call} }}], [{expected}], {label});'
        )
    lines.append("}")
    return lines


def _perl_footer(emitted: tuple[TestCase, ...]) -> list[str]:
    return [f"done_testing({len(emitted)});" if emitted else "done_testing();"]


PERL = LanguageProfile(
    language="perl",
    comment="#",
    skip_prefix="# ",
    integer_call="SymEngine::integer({})",
    symbol_call="SymEngine::symbol({})",
    string_literal=_single_quoted,
    emit_case=_perl_case,
    preamble=("use strict;", "use warnings;", "use Test::More;", "", "use SymEngine;", ""),
    footer=_perl_footer,
)


def render_perl_tests(spec: BindingSpec, suite: TestCaseSuite) -> str:
    """Render a Test::More ``.t`` file exercising the shared behavioral cases."""
    return _render(spec, suite, PERL)


# --- PHP ------------------------------------------------------------------


def _php_case(profile: LanguageProfile, case: TestCase, function: Function) -> list[str]:
    lines = []
    for name, argument in sorted(case.arrange.items()):
        lines.append(f"${name} = {profile.arrange(argument)};")
    arguments = ", ".join(f"${name}" for name in case.call.arguments)
    call = f'{function.public_name("php")}({arguments})'
    if case.expect.kind == "string":
        lines.append(f'echo symengine_str({call}), "\\n";')
    elif case.expect.kind == "none":
        lines.append(f"echo ({call} === null ? 'NULL' : 'NOT NULL'), \"\\n\";")
    else:
        lines.append(f"echo implode(',', array_map('symengine_str', {call})), \"\\n\";")
    return lines


def _php_expected(case: TestCase) -> str:
    """The single stdout line ``_php_case`` prints for this expectation."""
    if case.expect.kind == "string":
        return case.expect.string
    if case.expect.kind == "none":
        return "NULL"
    return ",".join(case.expect.strings)


def _php_footer(emitted: tuple[TestCase, ...]) -> list[str]:
    # phpt compares stdout against --EXPECT--, one line per emitted case.
    return ["?>", "--EXPECT--", *(_php_expected(case) for case in emitted)]


PHP = LanguageProfile(
    language="php",
    comment="#",
    skip_prefix="// ",
    integer_call="symengine_integer({})",
    symbol_call="symengine_symbol({})",
    string_literal=_single_quoted,
    emit_case=_php_case,
    prologue=(
        "--TEST--",
        "Shared behavioral test cases (generated)",
        "--SKIPIF--",
        "<?php if (!extension_loaded('symengine')) die('skip symengine extension not loaded'); ?>",
        "--FILE--",
        "<?php",
    ),
    footer=_php_footer,
)


def render_php_tests(spec: BindingSpec, suite: TestCaseSuite) -> str:
    """Render a ``.phpt`` file exercising the shared behavioral cases."""
    return _render(spec, suite, PHP)


# --- Swift ------------------------------------------------------------------


def _swift_case(profile: LanguageProfile, case: TestCase, function: Function) -> list[str]:
    lines = [f"    func test_{case.id}() throws {{"]
    for name, argument in sorted(case.arrange.items()):
        lines.append(f"        let {name} = {profile.arrange(argument)}")
    arguments = ", ".join(case.call.arguments)
    call = f"SymEngine.{function.public_name('swift')}({arguments})"
    if case.expect.kind == "string" and RESULT_SHAPES[function.behavior] == "optional":
        # Swift is the one language where "a value" and "no value" are distinct
        # static types, so a string expectation on an optional entry unwraps.
        call = f"XCTUnwrap({call})"
    lines.append(f"        let result = try {call}")
    if case.expect.kind == "string":
        lines.append(
            f'        XCTAssertEqual(try result.string(), {profile.string_literal(case.expect.string)})'
        )
    elif case.expect.kind == "none":
        lines.append("        XCTAssertNil(result)")
    else:
        expected = ", ".join(profile.string_literal(item) for item in case.expect.strings)
        lines.append(
            f"        XCTAssertEqual(try result.map {{ try $0.string() }}, [{expected}])"
        )
    lines.append("    }")
    lines.append("")
    return lines


SWIFT = LanguageProfile(
    language="swift",
    comment="//",
    skip_prefix="    // ",
    integer_call="try SymEngine.integer({})",
    symbol_call="try SymEngine.symbol({})",
    string_literal=_double_quoted,
    emit_case=_swift_case,
    preamble=(
        "import XCTest",
        "@testable import SymEngine",
        "",
        "final class SharedCasesTests: XCTestCase {",
    ),
    footer=lambda emitted: ["}"],
)


def render_swift_tests(spec: BindingSpec, suite: TestCaseSuite) -> str:
    """Render an XCTest file exercising the shared behavioral cases."""
    return _render(spec, suite, SWIFT)


# --- Java -------------------------------------------------------------------


def _java_case(profile: LanguageProfile, case: TestCase, function: Function) -> list[str]:
    # try-with-resources so every intermediate handle is released.
    declarations = [
        f"Basic {name} = {profile.arrange(argument)}"
        for name, argument in sorted(case.arrange.items())
    ]
    arguments = ", ".join(case.call.arguments)
    call = f"SymEngine.{function.public_name('java')}({arguments})"
    failure = f': "case \'{case.id}\' failed";'
    if case.expect.kind == "string":
        declarations.append(f"Basic result_{case.id} = {call}")
        return [
            "        try (" + "; ".join(declarations) + ") {",
            f'            assert result_{case.id}.toString().equals({profile.string_literal(case.expect.string)}) '
            f'{failure}',
            "        }",
        ]
    # A null or an array is not AutoCloseable, so only the arranged arguments
    # go in the resource list and the call itself moves into the body.
    opening = "        try (" + "; ".join(declarations) + ") {"
    if case.expect.kind == "none":
        return [
            opening,
            f"            Basic result_{case.id} = {call};",
            f"            assert result_{case.id} == null{failure}",
            "        }",
        ]
    joined = profile.string_literal(",".join(case.expect.strings))
    return [
        opening,
        f"            Basic[] result_{case.id} = {call};",
        f"            StringBuilder text_{case.id} = new StringBuilder();",
        f"            for (Basic item : result_{case.id}) {{",
        f'                if (text_{case.id}.length() > 0) text_{case.id}.append(",");',
        f"                text_{case.id}.append(item.toString());",
        "            }",
        f"            assert text_{case.id}.toString().equals({joined}){failure}",
        "        }",
    ]


JAVA = LanguageProfile(
    language="java",
    comment="//",
    skip_prefix="        // ",
    integer_call="SymEngine.integer({})",
    symbol_call="SymEngine.symbol({})",
    string_literal=_double_quoted,
    emit_case=_java_case,
    preamble=(
        "package org.symengine;",
        "",
        "/** Generated shared behavioral test cases; run via ctest like SmokeTest. */",
        "public final class SharedCasesTest {",
        "    public static void main(String[] arguments) throws Exception {",
    ),
    footer=lambda emitted: ["    }", "}"],
)


def render_java_tests(spec: BindingSpec, suite: TestCaseSuite) -> str:
    """Render a Java assert-runner class exercising the shared behavioral cases."""
    return _render(spec, suite, JAVA)
