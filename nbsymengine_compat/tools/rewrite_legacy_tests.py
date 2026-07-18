#!/usr/bin/env python3
"""rewrite_legacy_tests.py -- Rewrite imports in legacy symengine Python test files.

Uses LibCST to parse and transform import statements from the legacy
``symengine`` package to a configurable shim module (default: ``nbsymengine_compat``).
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union

import libcst as cst
from libcst import matchers as m


# ---------------------------------------------------------------------------
# Shim analysis: extract supported vs missing names
# ---------------------------------------------------------------------------

def _scan_body(body: list, supported: Set[str], missing: Set[str], shim_path: Path) -> None:
    for node in body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    name = target.id
                    if name.startswith('_'):
                        continue
                    if _is_missing_call(node.value):
                        missing.add(name)
                    else:
                        supported.add(name)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
            if name.startswith('_'):
                continue
            if node.value is not None and _is_missing_call(node.value):
                missing.add(name)
            elif node.value is not None:
                supported.add(name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith('_'):
                supported.add(node.name)
        elif isinstance(node, ast.ClassDef):
            if not node.name.startswith('_'):
                supported.add(node.name)
        elif isinstance(node, ast.Try):
            _scan_body(node.body, supported, missing, shim_path)
            for handler in node.handlers:
                _scan_body(handler.body, supported, missing, shim_path)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mod_name = node.module.lstrip('.')
                sub_path = shim_path.parent / f"{mod_name}.py"
                if sub_path.exists():
                    for alias in node.names:
                        if alias.name == '*':
                            sub_supported, sub_missing = _parse_shim(str(sub_path))
                            supported.update(sub_supported)
                            missing.update(sub_missing)
                        elif not alias.name.startswith('_'):
                            supported.add(alias.asname or alias.name)


def _parse_shim(shim_path: str) -> Tuple[Set[str], Set[str]]:
    """Parse the shim source and return (supported_names, missing_names).

    A name is *missing* if it is assigned via ``_missing(...)``.
    A name is *supported* if it is assigned from ``_core.*`` or defined as a
    real function/class (not a ``_missing`` stub).

    Only top-level (module-scope) names are considered — names defined inside
    classes or nested functions are excluded since they cannot be imported.
    Private names (starting with ``_``) are also excluded.
    """
    path = Path(shim_path)
    source = path.read_text()
    tree = ast.parse(source, filename=shim_path)

    missing: Set[str] = set()
    supported: Set[str] = set()

    _scan_body(tree.body, supported, missing, path)

    # Check if we should dynamically load nbsymengine._core names
    # to account for dynamic loop re-exports in symengine_py_compat.py
    if "symengine_py_compat.py" in path.name:
        try:
            from nbsymengine import _core as _c
            for name in dir(_c):
                if not name.startswith('_'):
                    supported.add(name)
        except ImportError as e:
            import sys
            print(f"WARNING: could not import nbsymengine._core during rewrite shim parse: {e}", file=sys.stderr)

    return supported, missing


def _is_missing_call(node: ast.expr) -> bool:
    """Return True if *node* is a ``_missing(...)`` call."""
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id == "_missing":
            return True
    return False


# ---------------------------------------------------------------------------
# LibCST helpers
# ---------------------------------------------------------------------------

def _make_import_from(
    module_parts: List[str], names: List[cst.ImportAlias]
) -> cst.ImportFrom:
    """Build ``from a.b.c import X, Y`` from a list of module parts."""
    mod_node: cst.BaseExpression = cst.Name(module_parts[0])
    for part in module_parts[1:]:
        mod_node = cst.Attribute(value=mod_node, attr=cst.Name(part))
    # Use parentheses for multi-name imports to allow trailing commas
    if len(names) > 1:
        return cst.ImportFrom(
            module=mod_node,
            names=names,
            lpar=cst.LeftParen(),
            rpar=cst.RightParen(),
        )
    # Single name: ensure no trailing comma (would be invalid without parens)
    single = names[0]
    if not isinstance(single.comma, cst.MaybeSentinel):
        single = single.with_changes(comma=cst.MaybeSentinel.DEFAULT)
    return cst.ImportFrom(module=mod_node, names=[single])


def _build_module_node(module_parts: List[str]) -> cst.BaseExpression:
    """Build a module expression node from a list of parts (e.g. ``["a", "b"]`` → ``a.b``)."""
    node: cst.BaseExpression = cst.Name(module_parts[0])
    for part in module_parts[1:]:
        node = cst.Attribute(value=node, attr=cst.Name(part))
    return node


def _alias_name(alias: cst.ImportAlias) -> str:
    """Return the evaluated name of an ImportAlias."""
    return alias.evaluated_name


def _module_string(node: cst.ImportFrom) -> str:
    """Return the full dotted module name of an ImportFrom as a string."""
    parts: List[str] = []
    n = node.module
    while isinstance(n, cst.Attribute):
        parts.append(n.attr.value)
        n = n.value
    if isinstance(n, cst.Name):
        parts.append(n.value)
    return ".".join(reversed(parts))


def _is_symengine_import(node: cst.ImportFrom) -> bool:
    """Check if the ImportFrom targets ``symengine`` (top-level)."""
    return m.matches(node.module, m.Name("symengine"))


def _is_symengine_submodule(node: cst.ImportFrom, sub: str) -> bool:
    """Check if the ImportFrom targets ``symengine.<sub>``."""
    return m.matches(
        node.module,
        m.Attribute(value=m.Name("symengine"), attr=m.Name(sub)),
    )


def _is_symengine_wrapper(node: cst.ImportFrom) -> bool:
    """Check if ``from symengine.lib.symengine_wrapper import ...``."""
    return m.matches(
        node.module,
        m.Attribute(
            value=m.Attribute(
                value=m.Name("symengine"),
                attr=m.Name("lib"),
            ),
            attr=m.Name("symengine_wrapper"),
        ),
    )


def _split_supported(
    names: List[cst.ImportAlias], supported_names: Set[str]
) -> Tuple[List[cst.ImportAlias], List[cst.ImportAlias]]:
    """Partition *names* into (supported, unsupported) lists."""
    good: List[cst.ImportAlias] = []
    bad: List[cst.ImportAlias] = []
    for alias in names:
        real_name = alias.evaluated_name
        if real_name in supported_names:
            good.append(alias)
        else:
            bad.append(alias)
    return good, bad


# ---------------------------------------------------------------------------
# LibCST transformer
# ---------------------------------------------------------------------------

class SymengineImportRewriter(cst.CSTTransformer):
    """Rewrite ``import symengine`` / ``from symengine import ...`` nodes.

    Uses ``leave_SimpleStatementLine`` to handle wrapper import splitting
    and to attach ``# UNSUPPORTED`` comments.
    """

    def __init__(
        self,
        supported_names: Set[str],
        missing_names: Set[str],
        shim_module_parts: Optional[List[str]] = None,
    ):
        self.supported_names = supported_names
        self.missing_names = missing_names
        self.shim_module_parts = shim_module_parts or ["nbsymengine", "legacy"]
        self.changes: List[Dict[str, object]] = []

    @property
    def _shim_module_str(self) -> str:
        return ".".join(self.shim_module_parts)

    # ---- helpers ----------------------------------------------------------

    def _record(self, rule: str, original: str, rewritten: str, **extra):
        entry: Dict[str, object] = {
            "rule": rule,
            "original": original,
            "rewritten": rewritten,
        }
        entry.update(extra)
        self.changes.append(entry)

    # ---- main entry -------------------------------------------------------

    def leave_ImportFrom(
        self, original_node: cst.ImportFrom, updated_node: cst.ImportFrom
    ) -> cst.ImportFrom | cst.RemovalSentinel:
        if updated_node.names is None or isinstance(updated_node.names, cst.MaybeSentinel):
            return updated_node

        names_list = list(updated_node.names)

        # Rule 1 / Rule 7 / Rule 8: from symengine import X, Y
        #   or from symengine.sympy_compat / symengine.printing import X, Y
        # If mixed support, defer to leave_SimpleStatementLine for splitting
        if _is_symengine_import(updated_node):
            good, bad = _split_supported(names_list, self.supported_names)
            if not bad:
                # All supported -- rewrite directly
                return self._rewrite_from_symengine(updated_node, names_list)
            # Mixed or all unsupported -- defer to leave_SimpleStatementLine
            return updated_node

        if _is_symengine_submodule(updated_node, "sympy_compat"):
            return self._rewrite_from_symengine_submod(
                updated_node, names_list, "sympy_compat"
            )

        if _is_symengine_submodule(updated_node, "printing"):
            return self._rewrite_from_symengine_submod(
                updated_node, names_list, "printing"
            )

        # Rule 4: from symengine.test_utilities import raises
        if _is_symengine_submodule(updated_node, "test_utilities"):
            return self._rewrite_test_utilities(updated_node, names_list)

        # Rule 5: from symengine.utilities import ...
        if _is_symengine_submodule(updated_node, "utilities"):
            return self._rewrite_utilities(updated_node, names_list)

        # Rule 6: from symengine.lib.symengine_wrapper import X
        # Handled in leave_SimpleStatementLine for proper splitting
        if _is_symengine_wrapper(updated_node):
            return updated_node

        # Rule 9: other symengine.* submodule imports
        mod_str = _module_string(updated_node)
        if mod_str.startswith("symengine."):
            return self._rewrite_generic_submodule(updated_node, names_list, mod_str)

        return updated_node

    def leave_SimpleStatementLine(
        self,
        original_node: cst.SimpleStatementLine,
        updated_node: cst.SimpleStatementLine,
    ) -> Union[cst.SimpleStatementLine, cst.FlattenSentinel[cst.BaseStatement]]:
        """Handle import splitting and UNSUPPORTED comments for mixed-support imports."""
        # Find the first ImportFrom in the statement
        orig_import: Optional[cst.ImportFrom] = None
        for stmt in original_node.body:
            if isinstance(stmt, cst.ImportFrom):
                orig_import = stmt
                break

        if orig_import is None:
            return updated_node

        # Rule 6: handle wrapper imports (split if mixed support)
        if _is_symengine_wrapper(orig_import):
            return self._handle_wrapper_statement(original_node, updated_node, orig_import)

        # Rule 1: handle top-level symengine imports with mixed support
        if _is_symengine_import(orig_import):
            return self._handle_symengine_statement(original_node, updated_node, orig_import)

        return updated_node

    def _handle_wrapper_statement(
        self,
        original_ssl: cst.SimpleStatementLine,
        updated_ssl: cst.SimpleStatementLine,
        orig_import: cst.ImportFrom,
    ) -> Union[cst.SimpleStatementLine, cst.FlattenSentinel[cst.BaseStatement]]:
        """Handle ``from symengine.lib.symengine_wrapper import ...``.

        If all names are supported, rewrite to compat shim.
        If all are unsupported, keep original with UNSUPPORTED comment.
        If mixed, split into two statement lines.
        """
        if orig_import.names is None or isinstance(orig_import.names, cst.MaybeSentinel):
            return updated_ssl

        names_list = list(orig_import.names)
        original = f"from symengine.lib.symengine_wrapper import {', '.join(_alias_name(a) for a in names_list)}"
        good, bad = _split_supported(names_list, self.supported_names)

        if not bad:
            # All supported -- rewrite
            self._record("Rule 6", original, f"→ {self._shim_module_str}.symengine_py_compat (all supported)")
            new_import = _make_import_from(
                [*self.shim_module_parts, "symengine_py_compat"], good
            )
            return updated_ssl.with_changes(body=[new_import])

        if not good:
            # All unsupported -- keep original with comment
            self._record(
                "Rule 6", original, "kept original (all unsupported)",
                unsupported=[_alias_name(a) for a in bad],
            )
            comment = "# UNSUPPORTED: " + ", ".join(_alias_name(a) for a in bad)
            return updated_ssl.with_changes(
                trailing_whitespace=cst.TrailingWhitespace(
                    whitespace=cst.SimpleWhitespace(" "),
                    comment=cst.Comment(comment),
                )
            )

        # Mixed: split into two statement lines
        self._record(
            "Rule 6", original,
            f"split: supported={len(good)}, unsupported={len(bad)}",
            unsupported=[_alias_name(a) for a in bad],
        )

        # Line 1: rewritten import for good names
        good_import = _make_import_from(
            [*self.shim_module_parts, "symengine_py_compat"], good
        )
        good_ssl = cst.SimpleStatementLine(body=[good_import])

        # Line 2: kept original for bad names with UNSUPPORTED comment
        bad_import = _make_import_from(
            ["symengine", "lib", "symengine_wrapper"], bad
        )
        comment = "# UNSUPPORTED: " + ", ".join(_alias_name(a) for a in bad)
        bad_ssl = cst.SimpleStatementLine(
            body=[bad_import],
            trailing_whitespace=cst.TrailingWhitespace(
                whitespace=cst.SimpleWhitespace(" "),
                comment=cst.Comment(comment),
            ),
        )

        return cst.FlattenSentinel([good_ssl, bad_ssl])

    def _handle_symengine_statement(
        self,
        original_ssl: cst.SimpleStatementLine,
        updated_ssl: cst.SimpleStatementLine,
        orig_import: cst.ImportFrom,
    ) -> Union[cst.SimpleStatementLine, cst.FlattenSentinel[cst.BaseStatement]]:
        """Handle ``from symengine import ...`` with mixed support.

        If all names are supported, rewrite to compat shim.
        If all are unsupported, keep original with UNSUPPORTED comment.
        If mixed, split into two statement lines.
        """
        if orig_import.names is None or isinstance(orig_import.names, cst.MaybeSentinel):
            return updated_ssl

        names_list = list(orig_import.names)
        original = f"from symengine import {', '.join(_alias_name(a) for a in names_list)}"
        good, bad = _split_supported(names_list, self.supported_names)

        if not bad:
            # All supported -- rewrite (shouldn't reach here due to leave_ImportFrom, but handle anyway)
            self._record("Rule 1", original, f"→ {self._shim_module_str}.symengine_py_compat (all supported)")
            new_import = _make_import_from(
                [*self.shim_module_parts, "symengine_py_compat"], good
            )
            return updated_ssl.with_changes(body=[new_import])

        if not good:
            # All unsupported -- keep original with comment
            self._record(
                "Rule 1", original, "kept original (all unsupported)",
                unsupported=[_alias_name(a) for a in bad],
            )
            comment = "# UNSUPPORTED: " + ", ".join(_alias_name(a) for a in bad)
            return updated_ssl.with_changes(
                trailing_whitespace=cst.TrailingWhitespace(
                    whitespace=cst.SimpleWhitespace(" "),
                    comment=cst.Comment(comment),
                )
            )

        # Mixed: split into two statement lines
        self._record(
            "Rule 1", original,
            f"split: supported={len(good)}, unsupported={len(bad)}",
            unsupported=[_alias_name(a) for a in bad],
        )

        # Line 1: rewritten import for good names
        good_import = _make_import_from(
            [*self.shim_module_parts, "symengine_py_compat"], good
        )
        good_ssl = cst.SimpleStatementLine(body=[good_import])

        # Line 2: kept original for bad names with UNSUPPORTED comment
        bad_import = _make_import_from(
            ["symengine"], bad
        )
        comment = "# UNSUPPORTED: " + ", ".join(_alias_name(a) for a in bad)
        bad_ssl = cst.SimpleStatementLine(
            body=[bad_import],
            trailing_whitespace=cst.TrailingWhitespace(
                whitespace=cst.SimpleWhitespace(" "),
                comment=cst.Comment(comment),
            ),
        )

        return cst.FlattenSentinel([good_ssl, bad_ssl])

    def leave_Import(
        self, original_node: cst.Import, updated_node: cst.Import
    ) -> cst.Import | cst.ImportFrom:
        """Handle ``import symengine`` and ``import symengine as se``."""
        names_list = list(updated_node.names)
        for alias in names_list:
            real = alias.evaluated_name
            if real == "symengine":
                asname = alias.asname
                if asname is not None:
                    # Rule 2: import symengine as se
                    alias_name = asname.name
                    if isinstance(alias_name, cst.Name):
                        target = alias_name.value
                    else:
                        target = "se"
                    self._record(
                        "Rule 2",
                        f"import symengine as {target}",
                        f"from {self._shim_module_str} import symengine_py_compat as {target}",
                    )
                    return cst.ImportFrom(
                        module=_build_module_node(self.shim_module_parts),
                        names=[
                            cst.ImportAlias(
                                name=cst.Name("symengine_py_compat"),
                                asname=cst.AsName(name=cst.Name(target)),
                            )
                        ],
                    )
                else:
                    # Rule 3: import symengine (bare)
                    self._record(
                        "Rule 3",
                        "import symengine",
                        f"from {self._shim_module_str} import symengine_py_compat as symengine",
                    )
                    return cst.ImportFrom(
                        module=_build_module_node(self.shim_module_parts),
                        names=[
                            cst.ImportAlias(
                                name=cst.Name("symengine_py_compat"),
                                asname=cst.AsName(name=cst.Name("symengine")),
                            )
                        ],
                    )
        return updated_node

    # ---- rule implementations ---------------------------------------------

    def _rewrite_from_symengine(
        self, node: cst.ImportFrom, names_list: List[cst.ImportAlias]
    ) -> cst.ImportFrom:
        """Rule 1: from symengine import X, Y."""
        original = f"from symengine import {', '.join(_alias_name(a) for a in names_list)}"
        self._record("Rule 1", original, f"→ {self._shim_module_str}.symengine_py_compat")
        return _make_import_from(
            [*self.shim_module_parts, "symengine_py_compat"], names_list
        )

    def _rewrite_from_symengine_submod(
        self,
        node: cst.ImportFrom,
        names_list: List[cst.ImportAlias],
        submod: str,
    ) -> cst.ImportFrom:
        """Rule 7/8: from symengine.sympy_compat/printing import X."""
        original = f"from symengine.{submod} import {', '.join(_alias_name(a) for a in names_list)}"
        rule = "Rule 7" if submod == "sympy_compat" else "Rule 8"
        self._record(rule, original, f"→ {self._shim_module_str}.symengine_py_compat")
        return _make_import_from(
            [*self.shim_module_parts, "symengine_py_compat"], names_list
        )

    def _rewrite_test_utilities(
        self, node: cst.ImportFrom, names_list: List[cst.ImportAlias]
    ) -> cst.ImportFrom:
        """Rule 4: from symengine.test_utilities import raises."""
        original = f"from symengine.test_utilities import {', '.join(_alias_name(a) for a in names_list)}"
        self._record("Rule 4", original, f"→ {self._shim_module_str}.test_utilities")
        return _make_import_from(
            [*self.shim_module_parts, "test_utilities"], names_list
        )

    def _rewrite_utilities(
        self, node: cst.ImportFrom, names_list: List[cst.ImportAlias]
    ) -> cst.ImportFrom:
        """Rule 5: from symengine.utilities import ..."""
        original = f"from symengine.utilities import {', '.join(_alias_name(a) for a in names_list)}"
        self._record("Rule 5", original, f"→ {self._shim_module_str}.test_utilities")
        return _make_import_from(
            [*self.shim_module_parts, "test_utilities"], names_list
        )

    def _rewrite_generic_submodule(
        self,
        node: cst.ImportFrom,
        names_list: List[cst.ImportAlias],
        mod_str: str,
    ) -> cst.ImportFrom:
        """Rule 9: other symengine.* submodule imports."""
        suffix = mod_str[len("symengine."):]
        original = f"from {mod_str} import {', '.join(_alias_name(a) for a in names_list)}"

        # Check if any names are available in the compat shim
        good, bad = _split_supported(names_list, self.supported_names)

        if good and not bad:
            self._record("Rule 9", original, f"→ {self._shim_module_str}.symengine_py_compat")
            return _make_import_from(
                [*self.shim_module_parts, "symengine_py_compat"], good
            )

        # Try rewriting to <shim_module>.<suffix>
        self._record("Rule 9", original, f"→ {self._shim_module_str}.{suffix}")
        return _make_import_from(
            [*self.shim_module_parts, *suffix.split(".")], names_list
        )


# ---------------------------------------------------------------------------
# File processing
# ---------------------------------------------------------------------------

def _process_file(
    src_path: Path,
    out_path: Path,
    supported_names: Set[str],
    missing_names: Set[str],
    shim_module_parts: Optional[List[str]] = None,
) -> Dict[str, object]:
    """Process a single test file and return a report dict."""
    source = src_path.read_text()
    try:
        tree = cst.parse_module(source)
    except cst.ParserSyntaxError as exc:
        return {
            "file": str(src_path),
            "error": f"Parse error: {exc}",
            "changes": [],
        }

    rewriter = SymengineImportRewriter(
        supported_names, missing_names, shim_module_parts=shim_module_parts
    )
    new_tree = tree.visit(rewriter)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(new_tree.code)

    return {
        "file": str(src_path),
        "output": str(out_path),
        "changes": rewriter.changes,
        "error": None,
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _generate_report(
    reports: List[Dict[str, object]], out_dir: Path
) -> None:
    """Generate CONVERSION_REPORT.md in the output directory.

    If ``manifest.json`` exists in *out_dir* (produced by the inventory tool),
    the report includes bucket assignment and ``reachable_now`` per file.
    """
    # Try to load manifest for enrichment
    manifest: Dict[str, Dict] = {}
    manifest_path = out_dir / "manifest.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    lines: List[str] = []
    lines.append("# Conversion Report")
    lines.append("")
    lines.append(f"Processed **{len(reports)}** test files.")
    lines.append("")

    total_changes = sum(len(r["changes"]) for r in reports)  # type: ignore[arg-type]
    total_errors = sum(1 for r in reports if r["error"])
    lines.append(f"- Total import rewrites: **{total_changes}**")
    lines.append(f"- Files with parse errors: **{total_errors}**")
    if manifest:
        reachable = sum(1 for v in manifest.values() if v.get("reachable_now"))
        lines.append(f"- Reachable now: **{reachable}/{len(manifest)}**")
    lines.append("")

    # Bucket summary from manifest
    if manifest:
        buckets: Dict[str, List[str]] = {}
        for fname, entry in sorted(manifest.items()):
            bucket = entry.get("bucket", "other")
            buckets.setdefault(bucket, []).append(fname)
        lines.append("## Buckets")
        lines.append("")
        lines.append("| Bucket | Files | Reachable |")
        lines.append("|--------|-------|-----------|")
        for bucket in sorted(buckets):
            files = buckets[bucket]
            reachable_in_bucket = sum(
                1 for f in files if manifest[f].get("reachable_now")
            )
            lines.append(
                f"| {bucket} | {len(files)} | {reachable_in_bucket}/{len(files)} |"
            )
        lines.append("")

    for report in reports:
        fname = Path(report["file"]).name  # type: ignore[arg-type]
        lines.append(f"## `{fname}`")
        lines.append("")

        # Enrich with manifest data
        entry = manifest.get(fname, {})
        if entry:
            bucket = entry.get("bucket", "other")
            reachable = "Yes" if entry.get("reachable_now") else "No"
            missing = entry.get("missing_names", [])
            ext = entry.get("external", [])
            lines.append(f"- **Bucket**: {bucket}")
            lines.append(f"- **Reachable now**: {reachable}")
            if missing:
                lines.append(
                    f"- **Missing names** ({len(missing)}): "
                    + ", ".join(f"`{n}`" for n in missing)
                )
            if ext:
                lines.append(f"- **External deps**: {', '.join(ext)}")
            lines.append("")

        if report["error"]:
            lines.append(f"> **ERROR**: {report['error']}")
            lines.append("")
            continue

        changes = report["changes"]  # type: ignore[assignment]
        if not changes:
            lines.append("No symengine imports found -- file copied as-is.")
            lines.append("")
            continue

        lines.append("| Rule | Original | Rewritten |")
        lines.append("|------|----------|-----------|")
        for ch in changes:
            rule = ch["rule"]
            orig = ch["original"].replace("|", "\\|")
            rew = ch["rewritten"].replace("|", "\\|")
            lines.append(f"| {rule} | `{orig}` | `{rew}` |")
        lines.append("")

        unsupported = []
        for ch in changes:
            if "unsupported" in ch:
                unsupported.extend(ch["unsupported"])  # type: ignore[arg-type]
        if unsupported:
            lines.append(
                f"**Unsupported names** ({len(unsupported)}): "
                + ", ".join(f"`{u}`" for u in unsupported)
            )
            lines.append("")

    report_path = out_dir / "CONVERSION_REPORT.md"
    report_path.write_text("\n".join(lines))
    print(f"Report written to {report_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rewrite imports in legacy symengine Python test files."
    )
    parser.add_argument(
        "--tests-dir",
        required=True,
        help="Directory containing legacy test files",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Output directory for rewritten test files",
    )
    parser.add_argument(
        "--shim-path",
        default="src/nbsymengine_compat/symengine_py_compat.py",
        help="Path to the symengine_py_compat shim source",
    )
    parser.add_argument(
        "--shim-module",
        default="nbsymengine_compat",
        help="Dotted module path for the shim package (default: nbsymengine_compat)",
    )
    args = parser.parse_args()

    tests_dir = Path(args.tests_dir)
    out_dir = Path(args.out)
    shim_path = Path(args.shim_path)
    shim_module_parts = args.shim_module.split(".")

    if not tests_dir.is_dir():
        print(f"Error: tests-dir {tests_dir} is not a directory", file=sys.stderr)
        sys.exit(1)
    if not shim_path.is_file():
        print(f"Error: shim-path {shim_path} is not a file", file=sys.stderr)
        sys.exit(1)

    supported, missing = _parse_shim(str(shim_path))
    print(f"Parsed shim: {len(supported)} supported names, {len(missing)} missing names")

    out_dir.mkdir(parents=True, exist_ok=True)

    test_files = sorted(tests_dir.glob("test_*.py"))
    if not test_files:
        print(f"No test_*.py files found in {tests_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Processing {len(test_files)} test files...")

    reports: List[Dict[str, object]] = []
    for src in test_files:
        out_path = out_dir / src.name
        report = _process_file(src, out_path, supported, missing, shim_module_parts)
        reports.append(report)
        n_changes = len(report["changes"])  # type: ignore[arg-type]
        status = "OK" if not report["error"] else "ERROR"
        print(f"  {src.name}: {n_changes} changes [{status}]")

    _generate_report(reports, out_dir)
    print("Done.")


if __name__ == "__main__":
    main()
