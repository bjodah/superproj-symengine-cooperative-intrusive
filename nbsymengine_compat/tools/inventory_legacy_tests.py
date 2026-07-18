#!/usr/bin/env python3
"""inventory_legacy_tests.py -- Scan legacy symengine Python test files and produce a JSON manifest."""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from pathlib import Path
from typing import Dict, Set, Tuple


# ---------------------------------------------------------------------------
# Shim introspection
# ---------------------------------------------------------------------------

def _scan_body(body: list, supported: Set[str], missing: Set[str], shim_path: Path) -> None:
    """Recursively scan a list of AST statements for definitions.

    Handles try/except blocks so that names defined inside them (e.g. exp)
    are detected. Also traverses relative star imports.
    """
    for node in body:
        if isinstance(node, ast.Assign):
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
                            sub_supported, sub_missing = parse_shim_names(sub_path)
                            supported.update(sub_supported)
                            missing.update(sub_missing)
                        elif not alias.name.startswith('_'):
                            supported.add(alias.asname or alias.name)


def parse_shim_names(shim_path: Path) -> Tuple[Set[str], Set[str]]:
    """Parse the shim file to get supported and missing names.

    Returns (supported_names, missing_names).

    Only top-level (module-scope) names are considered — names defined inside
    classes or nested functions are excluded since they cannot be imported.
    Private names (starting with ``_``) are also excluded.
    Names defined inside try/except blocks ARE included (e.g. exp).
    """
    source = shim_path.read_text()
    tree = ast.parse(source)

    supported: Set[str] = set()
    missing: Set[str] = set()

    _scan_body(tree.body, supported, missing, shim_path)

    # Check if we should dynamically load nbsymengine._core names
    # to account for dynamic loop re-exports in symengine_py_compat.py
    if "symengine_py_compat.py" in shim_path.name:
        try:
            from nbsymengine import _core as _c
            for name in dir(_c):
                if not name.startswith('_'):
                    supported.add(name)
        except ImportError as e:
            print(f"WARNING: could not import nbsymengine._core during inventory: {e}", file=sys.stderr)

    return supported, missing


def _is_missing_call(node: ast.expr) -> bool:
    """Check if an AST node is a call to _missing(...)."""
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id == '_missing':
            return True
    return False


# ---------------------------------------------------------------------------
# Known symbolic properties (best-effort detection)
# ---------------------------------------------------------------------------

SYMBOLIC_PROPERTIES = {
    'args', 'free_symbols', 'name', 'is_zero', 'is_number', 'is_integer',
    'is_real', 'is_positive', 'is_negative', 'is_nonpositive', 'is_nonnegative',
    'is_nonzero', 'is_finite', 'is_infinite', 'is_complex', 'is_rational',
    'is_algebraic', 'is_transcendental', 'is_irrational', 'is_commutative',
    'is_even', 'is_odd', 'is_prime', 'is_composite', 'dummy_index',
    'is_symbol', 'is_Add', 'is_Mul', 'is_Pow', 'is_Function', 'is_Number',
    'is_Symbol', 'is_Dummy', 'is_Matrix', 'is_set', 'is_Boolean',
    'base', 'exp', 'expr', 'variables', 'point', 'function',
}

# Operators to detect in BinOp/UnaryOp nodes
OPERATOR_MAP = {
    ast.Add: '+',
    ast.Sub: '-',
    ast.Mult: '*',
    ast.Div: '/',
    ast.Pow: '**',
    ast.Mod: '%',
    ast.FloorDiv: '//',
    ast.USub: '-',
    ast.UAdd: '+',
    ast.Eq: '==',
    ast.NotEq: '!=',
    ast.Lt: '<',
    ast.LtE: '<=',
    ast.Gt: '>',
    ast.GtE: '>=',
}

# External dependencies to detect
EXTERNAL_DEPS = {'sympy', 'sage', 'numpy', 'scipy'}

# Bucket classification by filename
BUCKET_BY_NAME = {
    'test_symbol': 'core',
    'test_arit': 'core',
    'test_number': 'core',
    'test_expr': 'core',
    'test_dict_basic': 'core',
    'test_var': 'core',
    'test_cse': 'core',
    'test_functions': 'functions',
    'test_series_expansion': 'functions',
    'test_logic': 'assumptions',
    'test_subs': 'subs_sympify',
    'test_sympify': 'subs_sympify',
    'test_sympy_compat': 'subs_sympify',
    'test_sets': 'sets',
    'test_solve': 'sets',
    'test_ntheory': 'ntheory',
    'test_matrices': 'matrices',
    'test_sympy_conv': 'conversion',
    'test_sage': 'conversion',
    'test_lambdify': 'lambdify_eval_print_pickle',
    'test_eval': 'lambdify_eval_print_pickle',
    'test_printing': 'lambdify_eval_print_pickle',
    'test_pickling': 'lambdify_eval_print_pickle',
}


# ---------------------------------------------------------------------------
# Test file analyzer
# ---------------------------------------------------------------------------

class TestFileAnalyzer(ast.NodeVisitor):
    """Analyze a single test file."""

    def __init__(self, supported_names: Set[str], missing_names: Set[str]):
        self.supported = supported_names
        self.missing = missing_names
        self.all_shim_names = supported_names | missing_names

        # Results
        self.imports_symengine: Set[str] = set()
        self.imports_wrapper: Set[str] = set()
        self.external: Set[str] = set()
        self.imports_test_utilities: bool = False
        self.imports_other_symengine: Set[str] = set()
        self.imports_other_symengine_names: Set[str] = set()
        self.attributes: Set[str] = set()
        self.operators: Set[str] = set()
        self.markers: Dict[str, int] = {'raises_count': 0, 'skip_count': 0}

        # Track symengine names in scope for operator detection
        self._symengine_names_in_scope: Set[str] = set()
        # Track all imported names for operator context
        self._all_imported_names: Set[str] = set()

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            module = alias.name
            if module == 'symengine':
                # import symengine -- we track attribute access separately
                pass
            elif module.startswith('symengine.'):
                self.imports_other_symengine.add(module)
            elif module in EXTERNAL_DEPS:
                self.external.add(module)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module is None:
            self.generic_visit(node)
            return

        module = node.module

        if module == 'symengine':
            for alias in node.names:
                name = alias.asname or alias.name
                self.imports_symengine.add(alias.name)
                self._symengine_names_in_scope.add(name)
                self._all_imported_names.add(name)
        elif module == 'symengine.lib.symengine_wrapper':
            for alias in node.names:
                name = alias.asname or alias.name
                self.imports_wrapper.add(alias.name)
                self._symengine_names_in_scope.add(name)
                self._all_imported_names.add(name)
        elif module in ('symengine.test_utilities', 'symengine.utilities'):
            self.imports_test_utilities = True
            for alias in node.names:
                self._all_imported_names.add(alias.asname or alias.name)
        elif module.startswith('symengine.'):
            self.imports_other_symengine.add(module)
            for alias in node.names:
                name = alias.name
                self.imports_other_symengine_names.add(name)
                self._all_imported_names.add(alias.asname or alias.name)
        elif module in EXTERNAL_DEPS or any(module.startswith(d + '.') for d in EXTERNAL_DEPS):
            ext = module.split('.')[0]
            self.external.add(ext)
            for alias in node.names:
                self._all_imported_names.add(alias.asname or alias.name)
        else:
            # stdlib or other
            for alias in node.names:
                self._all_imported_names.add(alias.asname or alias.name)

        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        if node.attr in SYMBOLIC_PROPERTIES:
            self.attributes.add(node.attr)
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp):
        op_type = type(node.op)
        if op_type in OPERATOR_MAP:
            self.operators.add(OPERATOR_MAP[op_type])
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare):
        for op in node.ops:
            op_type = type(op)
            if op_type in OPERATOR_MAP:
                self.operators.add(OPERATOR_MAP[op_type])
        self.generic_visit(node)

    def visit_UnaryOp(self, node: ast.UnaryOp):
        op_type = type(node.op)
        if op_type in OPERATOR_MAP:
            self.operators.add(OPERATOR_MAP[op_type])
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        # Detect raises(...) usage
        func_name = _get_call_name(node)
        if func_name == 'raises':
            self.markers['raises_count'] += 1

        # Detect attribute calls like symengine.Symbol(...)
        if isinstance(node.func, ast.Attribute):
            if node.func.attr in SYMBOLIC_PROPERTIES:
                self.attributes.add(node.func.attr)

        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        # Check for skip/xfail decorators
        for decorator in node.decorator_list:
            dec_name = _get_decorator_name(decorator)
            if dec_name and ('skip' in dec_name.lower() or 'xfail' in dec_name.lower()):
                self.markers['skip_count'] += 1
        self.generic_visit(node)

    def visit_Assert(self, node: ast.Assert):
        # Some tests use assert with raises context managers
        self.generic_visit(node)

    def visit_With(self, node: ast.With):
        # Detect `with raises(...):` context manager pattern
        for item in node.items:
            if isinstance(item.context_expr, ast.Call):
                func_name = _get_call_name(item.context_expr)
                if func_name == 'raises':
                    self.markers['raises_count'] += 1
        self.generic_visit(node)


def _get_call_name(node: ast.Call) -> str | None:
    """Get the function name from a Call node."""
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _get_decorator_name(node: ast.expr) -> str | None:
    """Get decorator name from a decorator node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return _get_call_name(node)
    return None


# ---------------------------------------------------------------------------
# Bucket assignment
# ---------------------------------------------------------------------------

def assign_bucket(filename: str, source: str) -> str:
    """Assign a test file to a bucket based on filename and content."""
    stem = Path(filename).stem
    if stem in BUCKET_BY_NAME:
        return BUCKET_BY_NAME[stem]

    # Content-based fallback heuristics
    if 'matrices' in stem or 'Matrix' in source[:2000]:
        return 'matrices'
    if 'ntheory' in stem or 'isprime' in source[:2000]:
        return 'ntheory'
    if 'sets' in stem or 'FiniteSet' in source[:2000]:
        return 'sets'

    return 'other'


# ---------------------------------------------------------------------------
# Analysis pipeline
# ---------------------------------------------------------------------------

def analyze_test_file(
    filepath: Path,
    supported: Set[str],
    missing: Set[str],
) -> Dict:
    """Analyze a single test file and return its manifest entry."""
    source = filepath.read_text()
    tree = ast.parse(source)

    analyzer = TestFileAnalyzer(supported, missing)
    analyzer.visit(tree)

    # Determine reachable_now: all imported symengine/wrapper names are supported
    all_imported = (
        analyzer.imports_symengine
        | analyzer.imports_wrapper
        | analyzer.imports_other_symengine_names
    )
    all_shim_names = supported | missing
    # Names that are either missing stubs or not in the shim at all
    not_supported = all_imported - supported
    reachable = len(not_supported) == 0

    bucket = assign_bucket(filepath.name, source)

    return {
        'imports_symengine': sorted(analyzer.imports_symengine),
        'imports_wrapper': sorted(analyzer.imports_wrapper),
        'external': sorted(analyzer.external),
        'imports_test_utilities': analyzer.imports_test_utilities,
        'imports_other_symengine': sorted(analyzer.imports_other_symengine),
        'imports_other_symengine_names': sorted(analyzer.imports_other_symengine_names),
        'attributes': sorted(analyzer.attributes),
        'operators': sorted(analyzer.operators),
        'markers': analyzer.markers,
        'bucket': bucket,
        'reachable_now': reachable,
        'missing_names': sorted(not_supported),
    }


def scan_tests_dir(
    tests_dir: Path,
    supported: Set[str],
    missing: Set[str],
) -> Dict[str, Dict]:
    """Scan all test_*.py files in the tests directory."""
    manifest = {}
    for filepath in sorted(tests_dir.glob('test_*.py')):
        rel_name = filepath.name
        try:
            entry = analyze_test_file(filepath, supported, missing)
            manifest[rel_name] = entry
        except Exception as e:
            print(f"WARNING: Failed to analyze {filepath}: {e}", file=sys.stderr)
            manifest[rel_name] = {
                'error': str(e),
                'imports_symengine': [],
                'imports_wrapper': [],
                'external': [],
                'imports_test_utilities': False,
                'imports_other_symengine': [],
                'imports_other_symengine_names': [],
                'attributes': [],
                'operators': [],
                'markers': {'raises_count': 0, 'skip_count': 0},
                'bucket': 'other',
                'reachable_now': False,
                'missing_names': [],
            }
    return manifest


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Scan legacy symengine Python test files and produce a JSON manifest.'
    )
    parser.add_argument(
        '--tests-dir',
        type=Path,
        required=True,
        help='Path to the directory containing test_*.py files',
    )
    parser.add_argument(
        '--out',
        type=Path,
        required=True,
        help='Output path for manifest.json',
    )
    parser.add_argument(
        '--shim-path',
        type=Path,
        default=Path('src/nbsymengine_compat/symengine_py_compat.py'),
        help='Path to the shim file (default: src/nbsymengine_compat/symengine_py_compat.py)',
    )

    args = parser.parse_args()

    # Resolve paths relative to cwd
    tests_dir = args.tests_dir.resolve()
    shim_path = args.shim_path.resolve()
    out_path = args.out.resolve()

    if not tests_dir.is_dir():
        print(f"ERROR: Tests directory not found: {tests_dir}", file=sys.stderr)
        sys.exit(1)
    if not shim_path.is_file():
        print(f"ERROR: Shim file not found: {shim_path}", file=sys.stderr)
        sys.exit(1)

    # Parse shim
    print(f"Parsing shim: {shim_path}")
    supported, missing = parse_shim_names(shim_path)
    print(f"  Supported names: {len(supported)}")
    print(f"  Missing (stub) names: {len(missing)}")

    # Scan tests
    print(f"Scanning tests: {tests_dir}")
    manifest = scan_tests_dir(tests_dir, supported, missing)
    print(f"  Files analyzed: {len(manifest)}")

    # Write manifest
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    print(f"Manifest written to: {out_path}")

    # Summary
    reachable = sum(1 for v in manifest.values() if v.get('reachable_now'))
    print(f"\nSummary: {reachable}/{len(manifest)} files reachable now")


if __name__ == '__main__':
    main()
