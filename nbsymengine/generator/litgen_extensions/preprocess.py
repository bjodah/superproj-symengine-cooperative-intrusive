"""Header preprocessing transforms for litgen/srcML.

Each function takes a string of C++ code and returns a cleaned version
that srcML can parse without choking on SymEngine-specific macros.
"""
from __future__ import annotations

import re


def strip_symengine_export(code: str) -> str:
    return code.replace("SYMENGINE_EXPORT", "")


def normalize_noexcept(code: str) -> str:
    return code.replace("SYMENGINE_NOEXCEPT", "noexcept")


def strip_symengine_assert(code: str) -> str:
    """SYMENGINE_ASSERT expands to a do{}while(0) that confuses srcML."""
    return re.sub(
        r"SYMENGINE_ASSERT\([^)]*\)\s*;?",
        "",
        code,
    )


def strip_implement_typeid(code: str) -> str:
    """IMPLEMENT_TYPEID / SYMENGINE_ASSIGN_TYPEID define __type_code; drop for litgen."""
    code = re.sub(r"IMPLEMENT_TYPEID\([^)]*\)\s*;?", "", code)
    code = re.sub(r"SYMENGINE_ASSIGN_TYPEID\(\)\s*;?", "", code)
    return code


def preprocess_header(code: str) -> str:
    code = strip_symengine_export(code)
    code = normalize_noexcept(code)
    code = strip_symengine_assert(code)
    code = strip_implement_typeid(code)
    return code
