#!/usr/bin/env python3
"""Compare hand-written wrapper API surfaces with Phase 0 text fixtures.

The fixtures are deliberately source-level snapshots.  They give later code
generation work a small, reviewable alarm when it accidentally drops or
renames a public entry point, without requiring every foreign runtime to be
installed just to inspect its declarations.
"""

from __future__ import annotations

import argparse
import ast
import difflib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.binding_codegen.model import validate_spec
from tools.binding_codegen.render_java import render_java_api
from tools.binding_codegen.render_perl import render_perl_xs_inc
from tools.binding_codegen.render_php import render_php_function_table_inc
from tools.binding_codegen.render_swift import render_swift_api, render_swift_cpp


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "binding_api_fixtures"


def _annotation(node: ast.expr | None) -> str:
    return "" if node is None else ast.unparse(node)


def _arguments(arguments: ast.arguments) -> str:
    parts: list[str] = []
    positional = [*arguments.posonlyargs, *arguments.args]
    defaults = [None] * (len(positional) - len(arguments.defaults)) + list(arguments.defaults)
    for index, (argument, default) in enumerate(zip(positional, defaults)):
        prefix = "/, " if arguments.posonlyargs and index == len(arguments.posonlyargs) else ""
        text = prefix + argument.arg
        if annotation := _annotation(argument.annotation):
            text += f": {annotation}"
        if default is not None:
            text += f" = {ast.unparse(default)}"
        parts.append(text)
    if arguments.vararg is not None:
        text = f"*{arguments.vararg.arg}"
        if annotation := _annotation(arguments.vararg.annotation):
            text += f": {annotation}"
        parts.append(text)
    elif arguments.kwonlyargs:
        parts.append("*")
    for argument, default in zip(arguments.kwonlyargs, arguments.kw_defaults):
        text = argument.arg
        if annotation := _annotation(argument.annotation):
            text += f": {annotation}"
        if default is not None:
            text += f" = {ast.unparse(default)}"
        parts.append(text)
    if arguments.kwarg is not None:
        text = f"**{arguments.kwarg.arg}"
        if annotation := _annotation(arguments.kwarg.annotation):
            text += f": {annotation}"
        parts.append(text)
    return ", ".join(parts)


def _function_signature(prefix: str, function: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    result = f"{prefix}({ _arguments(function.args) })"
    if annotation := _annotation(function.returns):
        result += f" -> {annotation}"
    return result


def python_stub(stub: Path) -> str:
    tree = ast.parse(stub.read_text(encoding="utf-8"), filename=str(stub))
    lines = ["# Public Python names and normalized .pyi declarations."]
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            bases = ", ".join(ast.unparse(base) for base in node.bases)
            lines.append(f"class {node.name}({bases})")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            lines.append(_function_signature(f"def {node.name}", node))
    return "\n".join(lines) + "\n"


def python_api_compatibility(stub: Path) -> bool:
    """Check Phase-0 Python symbols/call syntax while allowing generated ordering/types.

    The shared renderer deliberately sorts declarations and can refine a stub
    annotation when a typed adapter becomes available.  Neither is a runtime
    API break. Public class/function names and accepted keyword arguments are,
    so keep those baseline declarations as a subset of the generated
    stub.  The other language fixtures remain exact source snapshots.
    """
    expected_text = (FIXTURES / "python-api.txt").read_text(encoding="utf-8")
    expected = re.findall(r"(?m)^def (\w+)\(([^)]*)\)", expected_text)
    expected_classes = set(re.findall(r"(?m)^class (\w+)\(", expected_text))
    tree = ast.parse(stub.read_text(encoding="utf-8"), filename=str(stub))
    actual_classes = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}

    def arguments(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, ...]:
        return tuple(argument.arg for argument in (*node.args.posonlyargs, *node.args.args)) + (
            (f"*{node.args.vararg.arg}",) if node.args.vararg is not None else ()
        )

    actual: dict[str, set[tuple[str, ...]]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            actual.setdefault(node.name, set()).add(arguments(node))
    failures: list[str] = []
    failures.extend(f"class {name}" for name in sorted(expected_classes - actual_classes))
    for name, raw_arguments in expected:
        expected_arguments = tuple(
            part.strip().split(":", 1)[0].split("=", 1)[0].strip()
            for part in raw_arguments.split(",") if part.strip()
        )
        if expected_arguments not in actual.get(name, set()):
            failures.append(f"def {name}({raw_arguments})")
    if failures:
        print("missing or incompatible Python declarations:\n  " + "\n  ".join(failures), file=sys.stderr)
        return False
    return True


_PERL_XSUB_PATTERN = re.compile(r"(?m)^(SV \*|bool|unsigned int|void)\n([A-Za-z_]\w*)\(([^)]*)\)")


def perl_xsubs() -> str:
    manual = (ROOT / "symengine.pl" / "xs" / "SymEngine.xs").read_text(encoding="utf-8")
    spec = validate_spec(ROOT / "binding-spec" / "api.yaml")
    generated = render_perl_xs_inc(spec)
    entries = [
        f"{name}({arguments}) -> {returns}"
        for returns, name, arguments in (
            _PERL_XSUB_PATTERN.findall(manual) + _PERL_XSUB_PATTERN.findall(generated)
        )
    ]
    return "# Perl XSUBs\n" + "\n".join(entries) + "\n"


_PHP_FE_PATTERN = re.compile(r"(?m)^    PHP_FE\((symengine_\w+), ([A-Za-z0-9_]+)\)$")


def php_functions() -> str:
    header = (ROOT / "symengine.php" / "src" / "symengine_php.h").read_text(encoding="utf-8")
    source = (ROOT / "symengine.php" / "src" / "symengine_php.cpp").read_text(encoding="utf-8")
    spec = validate_spec(ROOT / "binding-spec" / "api.yaml")
    generated = render_php_function_table_inc(spec)
    declarations = re.findall(r"(?m)^PHP_FUNCTION\((symengine_\w+)\);$", header)
    table = _PHP_FE_PATTERN.findall(source) + _PHP_FE_PATTERN.findall(generated)
    lines = ["# PHP_FUNCTION declarations", *declarations, "# PHP function table / arginfo"]
    lines.extend(f"{name} -> {arginfo}" for name, arginfo in table)
    return "\n".join(lines) + "\n"


_SWIFT_C_DECLARATION_PATTERN = re.compile(
    r"(?ms)^([A-Za-z_][\w\s\*]*?(symengine_swift_\w+)\s*\([^;{]*?\))\s*\n\{"
)


def swift_surface() -> str:
    header = (ROOT / "symengine.swift" / "Sources" / "CSymEngineSwift" / "include" / "CSymEngineSwift.h").read_text(encoding="utf-8")
    swift = (ROOT / "symengine.swift" / "Sources" / "SymEngine" / "SymEngine.swift").read_text(encoding="utf-8")
    spec = validate_spec(ROOT / "binding-spec" / "api.yaml")
    generated_cpp = render_swift_cpp(spec)
    generated_api = render_swift_api(spec)
    c_declarations = re.findall(r"(?ms)^([A-Za-z_][\w\s\*]*?(symengine_swift_\w+)\s*\([^;]*?\));$", header)
    generated_c_declarations = _SWIFT_C_DECLARATION_PATTERN.findall(generated_cpp)
    lines = ["# Swift C bridge declarations"]
    lines.extend(re.sub(r"\s+", " ", declaration).strip() for declaration, _ in c_declarations)
    lines.extend(re.sub(r"\s+", " ", declaration).strip() for declaration, _ in generated_c_declarations)
    lines.append("# Public Swift API declarations")
    lines.extend(
        line.strip()
        for line in swift.splitlines()
        if line.strip().startswith("public ")
    )
    lines.extend(
        f"public {line.strip()}"
        for line in generated_api.splitlines()
        if line.strip().startswith("static func ")
    )
    return "\n".join(lines) + "\n"


def java_surface() -> str:
    spec = validate_spec(ROOT / "binding-spec" / "api.yaml")
    # ``Basic``, a primitive, or an array of them (list-returning entries).
    generated = re.findall(
        r"(?m)^    public static \w+(?:\[\])? (\w+)\([^)]*\) \{$", render_java_api(spec)
    )
    manual = (ROOT / "symengine.java" / "src" / "main" / "java" / "org" / "symengine" / "Basic.java").read_text(
        encoding="utf-8"
    )
    manual_methods = re.findall(r"(?m)^    (?:@Override )?public (?:\w+(?:<\w+>)?|\w+\[\]) (\w+)\(", manual)
    lines = ["# Generated SymEngine.java public methods"]
    lines.extend(sorted(generated))
    lines.append("# Manual Basic.java public methods")
    lines.extend(sorted(manual_methods))
    return "\n".join(lines) + "\n"


def compare(name: str, actual: str) -> bool:
    expected_path = FIXTURES / name
    expected = expected_path.read_text(encoding="utf-8")
    if actual == expected:
        return True
    sys.stderr.writelines(
        difflib.unified_diff(
            expected.splitlines(keepends=True),
            actual.splitlines(keepends=True),
            fromfile=str(expected_path),
            tofile=f"current {name}",
        )
    )
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--python-stub", type=Path,
        help="generated .pyi to check; omit to skip the Python check (e.g. no build tree available)",
    )
    args = parser.parse_args()
    results = [
        compare("perl-xsubs.txt", perl_xsubs()),
        compare("php-functions.txt", php_functions()),
        compare("swift-api.txt", swift_surface()),
        compare("java-api.txt", java_surface()),
    ]
    if args.python_stub is None:
        print("SKIPPED: Python check (no --python-stub given)", file=sys.stderr)
    else:
        results.append(python_api_compatibility(args.python_stub))
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
