#!/usr/bin/env python3
"""Extract an API inventory from the legacy Cython wrapper.

A developer-only reporting tool.  Nothing in the build consumes its output:
``nbsymengine``'s exposed C++ API is defined by ``generator/generate.yaml`` and
``binding-spec/api.yaml``, never by the legacy inventory.  The inventory is
still useful when measuring how much of legacy ``symengine.py`` the
``nbsymengine_compat`` shim covers, so it is printed on demand rather than
committed as a snapshot that silently goes stale.

Parses symengine_wrapper.in.pyx and emits YAML with three lists:
  - classes_initial: Python-visible classes worth binding
  - functions_initial: module-level functions
  - excluded_infrastructure: rcp_static_cast_*, make_rcp_*, outArg, c2py, etc.

Usage (writes to stdout unless -o is given):
    python scripts/extract_inventory.py [WRAPPER_PATH] [-o OUTPUT]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

INFRASTRUCTURE_PATTERNS = [
    r"rcp_static_cast",
    r"make_rcp",
    r"outArg",
    r"c2py",
    r"vec_basic_to_",
    r"vec_pair_to_",
    r"iter_to_vec",
    r"capsule_to_basic",
    r"assign_to_capsule",
    r"sympy2symengine",
    r"_sympify",
    r"get_function_class",
    r"load_basic",
    r"get_dict",
    r"_DictBasic",
    r"DictBasicIter",
]


def is_infrastructure(name: str) -> bool:
    return any(re.search(pat, name) for pat in INFRASTRUCTURE_PATTERNS)


def extract_inventory(wrapper_path: str) -> dict:
    text = Path(wrapper_path).read_text()

    classes: list[str] = []
    functions: list[str] = []
    excluded: list[str] = []

    for m in re.finditer(r"^(?:cdef\s+)?class\s+(\w+)", text, re.MULTILINE):
        name = m.group(1)
        if is_infrastructure(name):
            excluded.append(name)
        else:
            classes.append(name)

    for m in re.finditer(r"^(?:cpdef\s+(?:\w+\s+)?|def\s+)(\w+)", text, re.MULTILINE):
        name = m.group(1)
        if is_infrastructure(name):
            excluded.append(name)
        else:
            functions.append(name)

    # Deduplicate while preserving order
    def dedup(xs: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for x in xs:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out

    return {
        "classes_initial": dedup(classes),
        "functions_initial": dedup(functions),
        "excluded_infrastructure": dedup(excluded),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    # scripts/ -> nbsymengine/ -> superproject root, which owns symengine.py.
    default_wrapper = str(
        Path(__file__).resolve().parents[2]
        / "symengine.py"
        / "symengine"
        / "lib"
        / "symengine_wrapper.in.pyx"
    )
    ap.add_argument(
        "wrapper_path",
        nargs="?",
        default=default_wrapper,
        help="Path to symengine_wrapper.in.pyx",
    )
    ap.add_argument(
        "-o",
        "--output",
        default="-",
        help="YAML destination; '-' (the default) writes to stdout",
    )
    args = ap.parse_args()

    inventory = extract_inventory(args.wrapper_path)

    import yaml

    document = yaml.dump(inventory, default_flow_style=False, sort_keys=False)
    if args.output == "-":
        sys.stdout.write(document)
    else:
        Path(args.output).write_text(document, encoding="utf-8")
        print(f"Wrote {args.output}")
    print(
        f"classes: {len(inventory['classes_initial'])}, "
        f"functions: {len(inventory['functions_initial'])}, "
        f"excluded: {len(inventory['excluded_infrastructure'])}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
