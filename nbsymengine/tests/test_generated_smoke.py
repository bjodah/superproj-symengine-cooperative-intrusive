"""Smoke tests for the litgen-generated SymEngine nanobind extension.

Tests the Expression milestone: create symbols, build expressions,
perform arithmetic, check str/repr, verify equality, and test
hand-written function bindings (trig, hyperbolic, etc.).
"""
from __future__ import annotations

import ast
import os
import sys
import unittest


try:
    from nbsymengine import _core as sge
except ImportError:
    sge = None  # type: ignore[assignment]

# Phase 6 removed Expression in favor of direct RCP bindings.
# Skip all tests if Expression is not available.
_HAS_EXPRESSION = sge is not None and hasattr(sge, "Expression")


def _subprocess_python() -> str:
    return os.environ.get("NBSYMENGINE_SUBPROCESS_PYTHON", sys.executable)


@unittest.skipIf(not _HAS_EXPRESSION, "Expression not available (Phase 6 uses direct RCP)")
class TestExpressionSmoke(unittest.TestCase):
    """Phase 5 smoke tests for Expression-based bindings."""

    def test_expression_from_string(self) -> None:
        e = sge.Expression("x")
        self.assertIn("x", sge.str_expr(e))

    def test_symbol_factory(self) -> None:
        x = sge.symbol("x")
        self.assertEqual(sge.str_expr(x), "x")

    def test_integer_factory(self) -> None:
        i = sge.integer(42)
        self.assertEqual(sge.str_expr(i), "42")

    def test_add(self) -> None:
        x, y = sge.symbol("x"), sge.symbol("y")
        result = x + y
        self.assertEqual(sge.str_expr(result), "x + y")

    def test_sub(self) -> None:
        x, y = sge.symbol("x"), sge.symbol("y")
        result = x - y
        self.assertEqual(sge.str_expr(result), "x - y")

    def test_mul(self) -> None:
        x, y = sge.symbol("x"), sge.symbol("y")
        result = x * y
        self.assertEqual(sge.str_expr(result), "x*y")

    def test_div(self) -> None:
        x, y = sge.symbol("x"), sge.symbol("y")
        result = x / y
        self.assertEqual(sge.str_expr(result), "x/y")

    def test_pow(self) -> None:
        x = sge.symbol("x")
        result = x ** sge.integer(2)
        self.assertEqual(sge.str_expr(result), "x**2")

    def test_neg(self) -> None:
        x = sge.symbol("x")
        result = -x
        self.assertEqual(sge.str_expr(result), "-x")

    def test_expand(self) -> None:
        x, y = sge.symbol("x"), sge.symbol("y")
        result = sge.expand((x + y) ** sge.integer(2))
        expr_str = sge.str_expr(result)
        self.assertIn("x**2", expr_str)
        self.assertIn("y**2", expr_str)
        self.assertIn("x*y", expr_str)

    def test_equality(self) -> None:
        x1 = sge.symbol("x")
        x2 = sge.symbol("x")
        y = sge.symbol("y")
        self.assertEqual(x1, x2)
        self.assertNotEqual(x1, y)

    def test_str_repr(self) -> None:
        x, y = sge.symbol("x"), sge.symbol("y")
        self.assertEqual(str(x + y), "x + y")
        self.assertEqual(repr(x * y), "x*y")

    def test_int_interop(self) -> None:
        x = sge.symbol("x")
        self.assertEqual(sge.str_expr(x + 1), "1 + x")
        self.assertEqual(sge.str_expr(2 * x), "2*x")

    def test_chained_operations(self) -> None:
        x, y = sge.symbol("x"), sge.symbol("y")
        result = x + y + sge.integer(1)
        self.assertIn("1", sge.str_expr(result))


@unittest.skipIf(not _HAS_EXPRESSION, "Expression not available (Phase 6 uses direct RCP)")
class TestTrigFunctions(unittest.TestCase):
    """Test hand-written trigonometric and special function bindings."""

    def test_sin(self) -> None:
        x = sge.symbol("x")
        self.assertEqual(sge.str_expr(sge.sin(x)), "sin(x)")

    def test_cos(self) -> None:
        x = sge.symbol("x")
        self.assertEqual(sge.str_expr(sge.cos(x)), "cos(x)")

    def test_tan(self) -> None:
        x = sge.symbol("x")
        self.assertEqual(sge.str_expr(sge.tan(x)), "tan(x)")

    def test_asin(self) -> None:
        x = sge.symbol("x")
        self.assertEqual(sge.str_expr(sge.asin(x)), "asin(x)")

    def test_acos(self) -> None:
        x = sge.symbol("x")
        self.assertEqual(sge.str_expr(sge.acos(x)), "acos(x)")

    def test_atan(self) -> None:
        x = sge.symbol("x")
        self.assertEqual(sge.str_expr(sge.atan(x)), "atan(x)")

    def test_sinh(self) -> None:
        x = sge.symbol("x")
        self.assertEqual(sge.str_expr(sge.sinh(x)), "sinh(x)")

    def test_cosh(self) -> None:
        x = sge.symbol("x")
        self.assertEqual(sge.str_expr(sge.cosh(x)), "cosh(x)")

    def test_tanh(self) -> None:
        x = sge.symbol("x")
        self.assertEqual(sge.str_expr(sge.tanh(x)), "tanh(x)")

    def test_log(self) -> None:
        x = sge.symbol("x")
        self.assertEqual(sge.str_expr(sge.log(x)), "log(x)")

    def test_sqrt(self) -> None:
        x = sge.symbol("x")
        self.assertEqual(sge.str_expr(sge.sqrt(x)), "sqrt(x)")

    def test_abs(self) -> None:
        x = sge.symbol("x")
        self.assertEqual(sge.str_expr(sge.abs(x)), "abs(x)")

    def test_sign(self) -> None:
        x = sge.symbol("x")
        self.assertEqual(sge.str_expr(sge.sign(x)), "sign(x)")

    def test_floor(self) -> None:
        x = sge.symbol("x")
        self.assertEqual(sge.str_expr(sge.floor(x)), "floor(x)")

    def test_ceiling(self) -> None:
        x = sge.symbol("x")
        self.assertEqual(sge.str_expr(sge.ceiling(x)), "ceiling(x)")

    def test_gamma(self) -> None:
        x = sge.symbol("x")
        self.assertEqual(sge.str_expr(sge.gamma(x)), "gamma(x)")

    def test_erf(self) -> None:
        x = sge.symbol("x")
        self.assertEqual(sge.str_expr(sge.erf(x)), "erf(x)")

    def test_erfc(self) -> None:
        x = sge.symbol("x")
        self.assertEqual(sge.str_expr(sge.erfc(x)), "erfc(x)")

    def test_trig_identity_composition(self) -> None:
        x = sge.symbol("x")
        expr = sge.sin(x) ** sge.integer(2) + sge.cos(x) ** sge.integer(2)
        result_str = sge.str_expr(expr)
        self.assertIn("sin(x)**2", result_str)
        self.assertIn("cos(x)**2", result_str)


@unittest.skipIf(not _HAS_EXPRESSION, "Expression not available (Phase 6 uses direct RCP)")
class TestClassHierarchy(unittest.TestCase):
    """Verify nanobind class hierarchy reflects C++ inheritance."""

    def test_symbol_is_basic(self) -> None:
        s = sge.Symbol("x")
        self.assertIsInstance(s, sge.Basic)

    def test_integer_expression(self) -> None:
        i = sge.integer(42)
        self.assertIsInstance(i, sge.Expression)

    def test_add_expression(self) -> None:
        a = sge.add(sge.symbol("x"), sge.symbol("y"))
        self.assertIsInstance(a, sge.Expression)

    def test_dummy_is_symbol(self) -> None:
        d = sge.Dummy("d")
        self.assertIsInstance(d, sge.Symbol)
        self.assertIsInstance(d, sge.Basic)


@unittest.skipIf(not _HAS_EXPRESSION, "Expression not available (Phase 6 uses direct RCP)")
class TestStubFile(unittest.TestCase):
    """Verify the generated stub file is syntactically valid."""

    def test_stub_parseable(self) -> None:
        stub_path = os.path.join(
            os.path.dirname(__file__), "..", "generated", "symengine.pyi"
        )
        if not os.path.exists(stub_path):
            self.skipTest("stub file not found")
        with open(stub_path) as f:
            content = f.read()
        # Should be parseable as valid Python
        ast.parse(content)

    def test_stub_no_invalid_escape_sequences(self) -> None:
        """Verify no SyntaxWarning-causing escape sequences in stub."""
        stub_path = os.path.join(
            os.path.dirname(__file__), "..", "generated", "symengine.pyi"
        )
        if not os.path.exists(stub_path):
            self.skipTest("stub file not found")
        with open(stub_path) as f:
            content = f.read()
        import warnings
        with warnings.catch_warnings():
            warnings.filterwarnings("error", category=SyntaxWarning)
            try:
                ast.parse(content)
            except SyntaxWarning:
                self.fail("Stub file contains invalid escape sequences")

    def test_stub_class_hierarchy(self) -> None:
        """Verify stub declares correct base classes."""
        stub_path = os.path.join(
            os.path.dirname(__file__), "..", "generated", "symengine.pyi"
        )
        if not os.path.exists(stub_path):
            self.skipTest("stub file not found")
        with open(stub_path) as f:
            content = f.read()
        self.assertIn("class Symbol(Basic):", content)
        self.assertIn("class Integer(Number):", content)
        self.assertIn("class Add(Basic):", content)
        self.assertIn("class Mul(Basic):", content)
        self.assertIn("class Pow(Basic):", content)


@unittest.skipIf(
    os.environ.get("SYMENGINE_NANOBIND_REGEN_TESTS", "0") != "1",
    "Regeneration tests disabled (set SYMENGINE_NANOBIND_REGEN_TESTS=1 to enable)",
)
class TestReproducibility(unittest.TestCase):
    """Verify generate.py produces byte-identical output."""

    def test_regenerate_matches_committed(self) -> None:
        import subprocess
        import tempfile

        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        gen_script = os.path.join(repo_root, "generator", "generate.py")
        gen_config = os.path.join(repo_root, "generator", "generate.yaml")
        committed_pydef = os.path.join(repo_root, "generated", "symengine_pydef.cpp")
        committed_stub = os.path.join(repo_root, "generated", "symengine.pyi")

        if not os.path.exists(gen_script):
            self.skipTest("generate.py not found")
        if not os.path.exists(committed_pydef):
            self.skipTest("committed generated files not found")

        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [_subprocess_python(), gen_script, gen_config, "--output-dir", tmpdir],
                capture_output=True, text=True, cwd=repo_root,
            )
            self.assertEqual(result.returncode, 0, f"generate.py failed:\n{result.stderr}")

            tmp_pydef = os.path.join(tmpdir, "symengine_pydef.cpp")
            tmp_stub = os.path.join(tmpdir, "symengine.pyi")

            self.assertTrue(os.path.exists(tmp_pydef), "generate.py did not produce symengine_pydef.cpp")
            self.assertTrue(os.path.exists(tmp_stub), "generate.py did not produce symengine.pyi")

            with open(committed_pydef) as f:
                orig_pydef = f.read()
            with open(tmp_pydef) as f:
                new_pydef = f.read()
            with open(committed_stub) as f:
                orig_stub = f.read()
            with open(tmp_stub) as f:
                new_stub = f.read()

            self.assertEqual(orig_pydef, new_pydef, "symengine_pydef.cpp changed after re-generation")
            self.assertEqual(orig_stub, new_stub, "symengine.pyi changed after re-generation")


if __name__ == "__main__":
    unittest.main()
