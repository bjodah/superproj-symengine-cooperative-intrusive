"""Cross-check that math function classes from type_codes.inc are either bound or waived."""
from __future__ import annotations

import os
import re
import sys
import unittest

# Paths relative to this test file
_SUBMODULE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
# symengine/ is a sibling submodule at the super-project root (/work)
_SUPER_ROOT = os.path.abspath(os.path.join(_SUBMODULE_ROOT, ".."))
_TYPE_CODES_INC = os.path.join(_SUPER_ROOT, "symengine", "symengine", "type_codes.inc")
sys.path.insert(0, _SUPER_ROOT)
from tools.binding_codegen.model import validate_spec

_API_YAML = os.path.join(_SUPER_ROOT, "binding-spec", "api.yaml")

# Curated set of math function class names (from type_codes.inc) that should
# be checked for Python binding coverage.  Infrastructure / non-math types
# (Integer, Symbol, Mul, Add, Pow, polynomial types, matrix types, set types,
# boolean types, FunctionSymbol, Derivative, Subs, Piecewise, Tuple, etc.)
# are intentionally excluded.
MATH_FUNCTION_CLASSES: dict[str, str] = {
    # Trig
    "Sin": "sin",
    "Cos": "cos",
    "Tan": "tan",
    "Cot": "cot",
    "Csc": "csc",
    "Sec": "sec",
    # Inverse trig
    "ASin": "asin",
    "ACos": "acos",
    "ASec": "asec",
    "ACsc": "acsc",
    "ATan": "atan",
    "ACot": "acot",
    # Binary trig
    "ATan2": "atan2",
    # Hyperbolic
    "Sinh": "sinh",
    "Csch": "csch",
    "Cosh": "cosh",
    "Sech": "sech",
    "Tanh": "tanh",
    "Coth": "coth",
    # Inverse hyperbolic
    "ASinh": "asinh",
    "ACsch": "acsch",
    "ACosh": "acosh",
    "ATanh": "atanh",
    "ACoth": "acoth",
    "ASech": "asech",
    # Special
    "LambertW": "lambertw",
    "Zeta": "zeta",
    "Dirichlet_eta": "dirichlet_eta",
    "Erf": "erf",
    "Erfc": "erfc",
    "Gamma": "gamma",
    "PolyGamma": "polygamma",
    "LowerGamma": "lowergamma",
    "UpperGamma": "uppergamma",
    "LogGamma": "loggamma",
    "Beta": "beta",
    # Other
    "Log": "log",
    "Conjugate": "conjugate",
    "Sign": "sign",
    "Floor": "floor",
    "Ceiling": "ceiling",
    "Abs": "abs",
    # Number theory
    "KroneckerDelta": "kronecker_delta",
    "LeviCivita": "levi_civita",
    "PrimePi": "primepi",
    "Primorial": "primorial",
}

# Functions that exist in type_codes.inc but are intentionally not yet bound
# in the Python bindings.  Each entry maps the expected Python function name
# to a human-readable reason.
WAIVED: dict[str, str] = {
    "kronecker_delta": "Not yet bound (special handling needed)",
    "levi_civita": "Not yet bound (container adapter needed)",
    "primepi": "Not yet bound (ntheory_funcs.h)",
    "primorial": "Not yet bound (ntheory_funcs.h)",
}


def _extract_class_names_from_type_codes(path: str) -> set[str]:
    """Parse type_codes.inc and return all ClassName values from SYMENGINE_ENUM lines.

    Skips lines inside conditional blocks (MPFR, MPC, Piranha, Flint) since
    those features may not be compiled in.
    """
    class_names: set[str] = set()
    skip = False
    with open(path) as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("#if "):
                skip = True
                continue
            if stripped == "#endif" and skip:
                skip = False
                continue
            if skip:
                continue
            m = re.match(r"SYMENGINE_ENUM\(\s*\w+\s*,\s*(\w+)\s*\)", stripped)
            if m:
                class_names.add(m.group(1))
    return class_names


def _load_generated_python_functions() -> set[str]:
    """Return Python names owned by a generated shared-spec adapter."""
    return {function.public_name("python") for function in validate_spec(_API_YAML).functions
            if function.implementation == "generated" and "python" in function.expose}


class TestFunctionCoverage(unittest.TestCase):
    """Every math function class in type_codes.inc must be either bound in
    binding-spec/api.yaml or explicitly listed in WAIVED."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.type_code_classes = _extract_class_names_from_type_codes(_TYPE_CODES_INC)
        cls.json_py_names = _load_generated_python_functions()

    def test_type_codes_parsed(self) -> None:
        """Sanity check: type_codes.inc should yield a reasonable number of classes."""
        self.assertGreater(len(self.type_code_classes), 30)

    def test_all_math_functions_covered(self) -> None:
        """Every math function class must be bound or waived."""
        missing: list[str] = []
        for class_name, py_name in sorted(MATH_FUNCTION_CLASSES.items()):
            if class_name not in self.type_code_classes:
                # Class not in type_codes.inc — skip (conditional build)
                continue
            if py_name in self.json_py_names:
                continue
            if py_name in WAIVED:
                continue
            missing.append(f"  {class_name} -> {py_name}")
        if missing:
            self.fail(
                "The following math function classes are not bound in "
                "binding-spec/api.yaml and not in the WAIVED set:\n"
                + "\n".join(missing)
            )

    def test_waived_entries_have_reasons(self) -> None:
        """Every waived entry must have a non-empty reason string."""
        for name, reason in WAIVED.items():
            self.assertIsInstance(reason, str)
            self.assertGreater(len(reason), 0, f"WAIVED[{name!r}] has empty reason")

    def test_no_waived_for_bound_functions(self) -> None:
        """A function should not appear in both JSON and WAIVED."""
        overlap = self.json_py_names & set(WAIVED.keys())
        if overlap:
            self.fail(
                f"These functions are in both binding-spec/api.yaml and WAIVED: "
                f"{sorted(overlap)} — remove them from WAIVED"
            )


if __name__ == "__main__":
    unittest.main()
