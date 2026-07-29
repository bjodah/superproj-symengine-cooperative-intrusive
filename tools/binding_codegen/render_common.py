"""Pieces every renderer needs: the generated-file banner and entry selection.

Keeping these here means the DO-NOT-EDIT banner text, the "which entries does
this language generate?" rule and the C++ call shape of an adapter family have
exactly one definition, rather than one copy per target language.
"""

from __future__ import annotations

import hashlib
import json
from typing import Callable

import yaml

from .model import Argument, BindingSpec, Function


GENERATOR_VERSION = "1"

# Human-readable names used in "<Label> renderer does not support ..." errors.
LANGUAGE_LABELS = {
    "python": "Python",
    "perl": "Perl",
    "php": "PHP",
    "swift": "Swift",
    "java": "Java",
}

# Digests are stable for an unmodified spec file, so a single invocation which
# renders several artifacts only reads and hashes the YAML once.
_DIGEST_CACHE: dict[tuple[str, int, int], str] = {}


def spec_digest(spec: BindingSpec) -> str:
    """Return the whitespace-insensitive digest required by the roadmap."""
    try:
        status = spec.source_path.stat()
    except OSError:
        key = None
    else:
        key = (str(spec.source_path), status.st_mtime_ns, status.st_size)
    if key is not None and key in _DIGEST_CACHE:
        return _DIGEST_CACHE[key]
    document = yaml.safe_load(spec.source_path.read_text(encoding="utf-8"))
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if key is not None:
        _DIGEST_CACHE[key] = digest
    return digest


def header(spec: BindingSpec, comment: str) -> list[str]:
    """Return the two-line banner every generated artifact starts with."""
    return [
        f"{comment} AUTO-GENERATED — DO NOT EDIT.",
        f"{comment} schema_version: {spec.schema_version}; spec_sha256: {spec_digest(spec)}; generator_version: {GENERATOR_VERSION}",
    ]


def functions_for_language(
    spec: BindingSpec,
    language: str,
    supported: frozenset[str] | None = None,
) -> tuple[Function, ...]:
    """Return generated entries for ``language``, sorted independently of YAML order.

    When ``supported`` is given, an exposed generated entry whose behavior is
    outside that set names the gap instead of being silently omitted.
    """
    result: list[Function] = []
    for function in spec.functions:
        if language not in function.expose or function.implementation != "generated":
            continue
        if supported is not None and function.behavior not in supported:
            raise ValueError(
                f"entry '{function.id}': {LANGUAGE_LABELS[language]} renderer does not support "
                f"{function.behavior!r}"
            )
        result.append(function)
    return tuple(sorted(result, key=lambda function: function.id))


# --- Shared C++ call shape --------------------------------------------------
#
# Perl, PHP, Swift and Java all hand the generated call a *type-erased* handle:
# their wrapper object is always a ``Basic``, with no per-subclass wrapper type
# the way nanobind gives Python.  So an argument the spec types as ``integer``
# needs an explicit, guarded downcast before SymEngine's overload can be
# called, and that downcast is the same C++ in every one of them -- only the
# handle-to-``RCP<const Basic>`` spelling differs.  ``cpp_call`` owns the shape;
# the four renderers keep owning their own surrounding function bodies.

BASIC_RCP = "SymEngine::RCP<const SymEngine::Basic>"
INTEGER_RCP = "SymEngine::RCP<const SymEngine::Integer>"

# Every generated call site already sits inside a ``catch`` which reports a C++
# exception the language's own way (``croak``, ``zend_throw_exception``,
# ``last_error`` plus a thrown ``SymEngineError``, ``SymEngineException``), so
# throwing is the portable way to reject a wrong argument type.
CallPrologue = list[str]


def _downcast_lines(function: Function, argument: Argument, unwrapped: str, indent: str) -> CallPrologue:
    """Return the guarded ``Basic`` -> ``Integer`` narrowing for one argument."""
    handle = f"{argument.name}_basic"
    message = f"{function.id}(): argument '{argument.name}' must be an Integer"
    return [
        f"{indent}{BASIC_RCP} {handle} = {unwrapped};",
        f"{indent}if (!SymEngine::is_a<SymEngine::Integer>(*{handle})) {{",
        f'{indent}    throw SymEngine::SymEngineException("{message}");',
        f"{indent}}}",
        f"{indent}{INTEGER_RCP} {argument.name}_integer",
        f"{indent}    = SymEngine::rcp_static_cast<const SymEngine::Integer>({handle});",
    ]


def cpp_call(
    function: Function,
    unwrap: Callable[[Argument], str],
    *,
    indent: str = "        ",
) -> tuple[CallPrologue, str]:
    """Return ``(prologue statements, call expression)`` for one generated entry.

    ``unwrap`` spells how the language turns its handle for ``argument`` into an
    ``RCP<const Basic>``.  A ``singleton`` yields no prologue and the spec's
    constant expression.  ``adapter.deref`` selects between SymEngine overloads
    taking ``const Integer &`` and ``const RCP<const Integer> &``.
    """
    if function.behavior == "singleton":
        expression = function.cpp.expression
        assert expression is not None
        return [], expression
    name = function.cpp.name
    assert name is not None
    deref = bool(function.adapter.get("deref", True))
    prologue: CallPrologue = []
    spellings: list[str] = []
    for argument in function.arguments:
        if argument.type_id != "integer":
            spellings.append(unwrap(argument))
            continue
        prologue.extend(_downcast_lines(function, argument, unwrap(argument), indent))
        local = f"{argument.name}_integer"
        spellings.append(f"*{local}" if deref else local)
    return prologue, f"{name}({', '.join(spellings)})"
