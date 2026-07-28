"""Pieces every renderer needs: the generated-file banner and entry selection.

Keeping these here means the DO-NOT-EDIT banner text and the "which entries
does this language generate?" rule have exactly one definition, rather than one
copy per target language.
"""

from __future__ import annotations

import hashlib
import json

import yaml

from .model import BindingSpec, Function


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
