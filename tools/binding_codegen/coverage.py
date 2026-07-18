"""Coverage accounting for the deliberately small shared API surface."""

from __future__ import annotations

from .model import BindingSpec
from .render_perl import perl_functions
from .render_php import php_functions
from .render_nbsymengine import python_functions
from .render_swift import swift_functions
from .render_java import java_functions


_RENDERERS = {
    "python": python_functions,
    "perl": perl_functions,
    "php": php_functions,
    "swift": swift_functions,
    "java": java_functions,
}


def coverage_rows(spec: BindingSpec) -> tuple[tuple[str, str, str], ...]:
    """Classify every spec/language pair from the available renderers."""
    supported: dict[str, set[str]] = {}
    for language, renderer in _RENDERERS.items():
        # Calling the renderer turns an exposed unsupported adapter into the
        # precise error required by the roadmap rather than silently omitting it.
        supported[language] = {function.id for function in renderer(spec)}

    rows: list[tuple[str, str, str]] = []
    for function in sorted(spec.functions, key=lambda item: item.id):
        for language in ("python", "perl", "php", "swift", "java"):
            if language not in function.expose:
                status = "not exposed"
            elif function.implementation == "manual":
                status = "manual"
            elif language in supported and function.id in supported[language]:
                status = "generated"
            else:
                # A generated entry cannot be exposed without a renderer.
                raise ValueError(
                    f"entry '{function.id}': {language} is exposed but has no generated renderer"
                )
            rows.append((function.id, language, status))
    return tuple(rows)


def render_coverage_report(spec: BindingSpec) -> str:
    rows = coverage_rows(spec)
    lines = ["# Shared binding API coverage", "", "| entry | language | status |", "| --- | --- | --- |"]
    lines.extend(f"| `{entry}` | {language} | {status} |" for entry, language, status in rows)
    return "\n".join(lines) + "\n"


_MATRIX_LANGUAGES = ("python", "perl", "php", "swift", "java")
_MATRIX_CELL = {"generated": "generated", "manual": "manual", "not exposed": "—"}


def render_coverage_matrix(spec: BindingSpec) -> str:
    """Render a compact per-entry/per-language matrix for documentation.

    No digest or timestamp is embedded here (unlike generated code headers)
    so ``check``'s freshness diff against the committed file is stable across
    otherwise-unrelated spec whitespace changes.
    """
    status = {(entry, language): value for entry, language, value in coverage_rows(spec)}
    lines = [
        "# Shared binding API matrix",
        "",
        "<!-- AUTO-GENERATED — DO NOT EDIT. -->",
        "<!-- Regenerate with: python -m tools.binding_codegen coverage --matrix "
        "--output docs/binding-api-matrix.md -->",
        "",
        "| entry | " + " | ".join(_MATRIX_LANGUAGES) + " |",
        "| --- | " + " | ".join("---" for _ in _MATRIX_LANGUAGES) + " |",
    ]
    for function in sorted(spec.functions, key=lambda item: item.id):
        cells = [_MATRIX_CELL[status[(function.id, language)]] for language in _MATRIX_LANGUAGES]
        lines.append(f"| `{function.id}` | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"
