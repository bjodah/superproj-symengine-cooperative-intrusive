#!/usr/bin/env python3
"""report_compat.py -- Metrics reporting for the legacy compatibility layer."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import defaultdict
from pathlib import Path


def _scan_body(body: list[ast.stmt], supported: set[str], missing: set[str]) -> None:
    """Scan a list of AST statements for assignments, functions, and classes."""
    for node in body:
        if isinstance(node, ast.ImportFrom):
            # Only count re-exports from internal modules (e.g. _core, _expr)
            # as API names.  Standard library imports (fractions, itertools, …)
            # are not part of the public shim API.
            module = node.module or ""
            if module.startswith("_core") or module.startswith("nbsymengine"):
                for alias in node.names:
                    name = alias.asname if alias.asname else alias.name
                    if not name.startswith('_'):
                        supported.add(name)
        elif isinstance(node, ast.Assign):
            if len(node.targets) != 1:
                continue
            target = node.targets[0]
            if not isinstance(target, ast.Name):
                continue
            name = target.id
            if name.startswith('_'):
                continue
            if _is_missing_call(node.value):
                missing.add(name)
            else:
                supported.add(name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = node.name
            if not name.startswith('_'):
                supported.add(name)
        elif isinstance(node, ast.ClassDef):
            name = node.name
            if not name.startswith('_'):
                supported.add(name)
        elif isinstance(node, ast.Try):
            # Scan both try body and except body for definitions
            _scan_body(node.body, supported, missing)
            for handler in node.handlers:
                _scan_body(handler.body, supported, missing)


def parse_shim_names(shim_path: Path) -> tuple[set[str], set[str]]:
    """Parse the shim file to get supported and missing names.

    Returns (supported_names, missing_names).

    Only top-level (module-scope) names are considered — names defined inside
    classes or nested functions are excluded since they cannot be imported.
    Private names (starting with ``_``) are also excluded.
    """
    source = shim_path.read_text()
    tree = ast.parse(source)

    supported: set[str] = set()
    missing: set[str] = set()

    _scan_body(tree.body, supported, missing)

    return supported, missing


def _is_missing_call(node: ast.expr) -> bool:
    """Check if an AST node is a call to _missing(...)."""
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id == '_missing':
            return True
    return False


def load_manifest(manifest_path: Path) -> dict:
    """Load and return the manifest JSON."""
    with open(manifest_path) as f:
        return json.load(f)


def compute_report(manifest: dict, supported: set[str], missing: set[str]) -> dict:
    """Compute all metrics from the manifest and shim analysis."""
    reachable_count = 0
    unreachable_count = 0
    all_referenced_names: set[str] = set()
    bucket_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"reachable": 0, "total": 0})

    for _test_file, entry in manifest.items():
        imports_se = set(entry.get("imports_symengine", []))
        imports_w = set(entry.get("imports_wrapper", []))
        all_referenced_names.update(imports_se | imports_w)

        bucket = entry.get("bucket", "other")
        bucket_stats[bucket]["total"] += 1

        if entry.get("reachable_now", False):
            reachable_count += 1
            bucket_stats[bucket]["reachable"] += 1
        else:
            unreachable_count += 1

    supported_referenced = all_referenced_names & supported
    shim_coverage = (
        len(supported_referenced) / len(all_referenced_names) * 100
        if all_referenced_names
        else 0.0
    )

    still_unsupported = sorted(
        name for name in all_referenced_names if name not in supported
    )

    return {
        "files_reachable": reachable_count,
        "files_unreachable": unreachable_count,
        "files_total": reachable_count + unreachable_count,
        "names_referenced": len(all_referenced_names),
        "names_supported": len(supported_referenced),
        "shim_coverage_pct": round(shim_coverage, 2),
        "buckets": {
            bucket: stats
            for bucket, stats in sorted(bucket_stats.items())
        },
        "unsupported_names": still_unsupported,
    }


def print_human(report: dict) -> None:
    """Print report in human-readable format to stdout."""
    print("=" * 60)
    print("  Legacy Compatibility Layer — Coverage Report")
    print("=" * 60)
    print()

    print("Test files")
    print(f"  Reachable now:  {report['files_reachable']}")
    print(f"  Unreachable:    {report['files_unreachable']}")
    print(f"  Total:          {report['files_total']}")
    print()

    print("Shim coverage")
    print(f"  Names referenced across all tests: {report['names_referenced']}")
    print(f"  Names supported (not stubbed):     {report['names_supported']}")
    print(f"  Coverage:                          {report['shim_coverage_pct']}%")
    print()

    print("Per-bucket breakdown")
    print(f"  {'Bucket':<30} {'Reachable':>9} / {'Total':>5}")
    print(f"  {'-' * 30} {'-' * 9}   {'-' * 5}")
    for bucket, stats in report["buckets"].items():
        print(f"  {bucket:<30} {stats['reachable']:>9} / {stats['total']:>5}")
    print()

    unsupported = report["unsupported_names"]
    if unsupported:
        print(f"Still-unsupported names ({len(unsupported)}):")
        for name in unsupported:
            print(f"  - {name}")
    else:
        print("All referenced names are supported!")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Metrics reporting for the legacy compatibility layer."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Path to manifest.json (default: tests/converted/manifest.json relative to repo root)",
    )
    parser.add_argument(
        "--shim-path",
        type=Path,
        default=None,
        help="Path to symengine_py_compat.py (default: src/nbsymengine_compat/symengine_py_compat.py relative to repo root)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output machine-readable JSON instead of human-readable text",
    )

    args = parser.parse_args()

    # Resolve default paths relative to the script's parent's parent
    repo_root = Path(__file__).resolve().parent.parent

    manifest_path = args.manifest or repo_root / "tests" / "converted" / "manifest.json"
    shim_path = args.shim_path or repo_root / "src" / "nbsymengine_compat" / "symengine_py_compat.py"

    if not manifest_path.is_file():
        print(f"ERROR: Manifest not found: {manifest_path}", file=sys.stderr)
        return 1
    if not shim_path.is_file():
        print(f"ERROR: Shim file not found: {shim_path}", file=sys.stderr)
        return 1

    manifest = load_manifest(manifest_path)
    supported, missing = parse_shim_names(shim_path)
    report = compute_report(manifest, supported, missing)

    if args.json_output:
        print(json.dumps(report, indent=2))
    else:
        print_human(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
