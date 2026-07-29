"""Pieces every renderer needs: the generated-file banner and entry selection.

Keeping these here means the DO-NOT-EDIT banner text, the "which entries does
this language generate?" rule and the C++ call shape of an adapter family have
exactly one definition, rather than one copy per target language.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
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
INTEGER_VECTOR = "std::vector<SymEngine::RCP<const SymEngine::Integer>>"
BASIC_VECTOR = "std::vector<SymEngine::RCP<const SymEngine::Basic>>"

# Spec types that arrive as a type-erased ``Basic`` handle but whose SymEngine
# overload wants a narrower expression class.  Each value is the SymEngine class
# the generated guard narrows to, the predicate that decides it, and the English
# article for the error message.  ``Number`` is abstract, so it has no
# ``type_code_id`` and needs ``is_a_sub`` rather than the exact ``is_a``.
DOWNCAST_TYPES = {
    "integer": ("Integer", "is_a", "an"),
    "number": ("Number", "is_a_sub", "a"),
}

# Spec types that are plain C++ scalars rather than expression handles.  Each
# wrapper receives them in its own numeric parameter type, so the generated call
# casts explicitly instead of relying on an implicit conversion.
SCALAR_TYPES = {"double": "double", "unsigned": "unsigned"}

# Every generated call site already sits inside a ``catch`` which reports a C++
# exception the language's own way (``croak``, ``zend_throw_exception``,
# ``last_error`` plus a thrown ``SymEngineError``, ``SymEngineException``), so
# throwing is the portable way to reject a wrong argument type.
CallPrologue = list[str]

# How a family's result reaches the caller.  ``handle`` is one expression,
# ``optional`` is an expression or "no result", ``list`` is zero or more
# expressions.  Only the last two need a language-specific container.
RESULT_SHAPES = {
    "singleton": "handle",
    "unary_basic": "handle",
    "binary_basic": "handle",
    "binary_boolean": "handle",
    "integer_unary": "handle",
    "integer_binary": "handle",
    "status_optional_unary": "optional",
    "list_integer_to_basic": "list",
}

# Locals the ``optional``/``list`` shapes introduce.  They are prefixed so they
# can never collide with a spec argument name (``[a-z][a-z0-9_]*``, but never
# ``symengine_``-prefixed in practice) or with the ``<name>_integer`` locals.
OUT_NAME = "symengine_out"
FOUND_NAME = "symengine_found"
VALUES_NAME = "symengine_values"


def _downcast_lines(
    function: Function, argument: Argument, unwrapped: str, indent: str, type_id: str
) -> CallPrologue:
    """Return the guarded ``Basic`` -> narrower-class conversion for one argument."""
    target, predicate, article = DOWNCAST_TYPES[type_id]
    handle = f"{argument.name}_basic"
    message = f"{function.id}(): argument '{argument.name}' must be {article} {target}"
    return [
        f"{indent}{BASIC_RCP} {handle} = {unwrapped};",
        f"{indent}if (!SymEngine::{predicate}<SymEngine::{target}>(*{handle})) {{",
        f'{indent}    throw SymEngine::SymEngineException("{message}");',
        f"{indent}}}",
        f"{indent}SymEngine::RCP<const SymEngine::{target}> {argument.name}_{target.lower()}",
        f"{indent}    = SymEngine::rcp_static_cast<const SymEngine::{target}>({handle});",
    ]


def cpp_call(
    function: Function,
    unwrap: Callable[[Argument], str],
    *,
    indent: str = "        ",
    prefix_arguments: tuple[str, ...] = (),
) -> tuple[CallPrologue, str]:
    """Return ``(prologue statements, call expression)`` for one generated entry.

    ``unwrap`` spells how the language turns its handle for ``argument`` into an
    ``RCP<const Basic>``.  A ``singleton`` yields no prologue and the spec's
    constant expression.  ``adapter.deref`` selects between SymEngine overloads
    taking ``const Integer &`` and ``const RCP<const Integer> &``.
    ``prefix_arguments`` are passed before the spec arguments; that is how the
    out-parameter families put ``outArg(...)``/the result vector first.
    """
    if function.behavior == "singleton":
        expression = function.cpp.expression
        assert expression is not None
        return [], expression
    name = function.cpp.name
    assert name is not None
    deref = bool(function.adapter.get("deref", True))
    prologue: CallPrologue = []
    spellings: list[str] = list(prefix_arguments)
    for argument in function.arguments:
        if argument.type_id in SCALAR_TYPES:
            spellings.append(f"static_cast<{SCALAR_TYPES[argument.type_id]}>({argument.name})")
            continue
        if argument.type_id not in DOWNCAST_TYPES:
            spellings.append(unwrap(argument))
            continue
        prologue.extend(
            _downcast_lines(function, argument, unwrap(argument), indent, argument.type_id)
        )
        local = f"{argument.name}_{DOWNCAST_TYPES[argument.type_id][0].lower()}"
        spellings.append(f"*{local}" if deref else local)
    return prologue, f"{name}({', '.join(spellings)})"


@dataclass(frozen=True)
class CppResult:
    """The C++ an entry's body needs, independent of the target language."""

    statements: CallPrologue
    value: str  # expression naming the result the wrapper must hand back
    found: str | None  # condition guarding ``value``; None when always present
    shape: str  # "handle", "optional" or "list"


def cpp_result(
    function: Function,
    unwrap: Callable[[Argument], str],
    *,
    indent: str = "        ",
) -> CppResult:
    """Return the whole C++ shape of one entry: locals, call, and result.

    ``handle`` families keep the single-expression form ``cpp_call`` already
    produced.  ``optional`` declares the ``Ptr`` out-parameter's target plus a
    ``found`` flag from the ``int``/``bool`` status; ``list`` declares the
    ``std::vector`` out-parameter and widens it to ``Basic`` once, so a wrapper
    only ever wraps ``RCP<const Basic>``.
    """
    shape = RESULT_SHAPES[function.behavior]
    if shape == "handle":
        prologue, call = cpp_call(function, unwrap, indent=indent)
        return CppResult(prologue, call, None, shape)
    if shape == "optional":
        prologue, call = cpp_call(
            function, unwrap, indent=indent,
            prefix_arguments=(f"SymEngine::outArg({OUT_NAME})",),
        )
        statements = [
            f"{indent}{INTEGER_RCP} {OUT_NAME};",
            *prologue,
            f"{indent}const bool {FOUND_NAME} = ({call}) != 0;",
        ]
        return CppResult(statements, OUT_NAME, FOUND_NAME, shape)
    prologue, call = cpp_call(function, unwrap, indent=indent, prefix_arguments=(OUT_NAME,))
    statements = [
        f"{indent}{INTEGER_VECTOR} {OUT_NAME};",
        *prologue,
        f"{indent}{call};",
        f"{indent}{BASIC_VECTOR} {VALUES_NAME}({OUT_NAME}.begin(), {OUT_NAME}.end());",
    ]
    return CppResult(statements, VALUES_NAME, None, shape)
