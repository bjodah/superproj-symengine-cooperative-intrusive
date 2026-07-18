"""Benchmark case base class and concrete Lambdify benchmark cases."""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class BenchmarkCase(ABC):
    """Base class for all benchmark cases."""
    name: str

    def build(self, adapter: Any) -> Callable[[], Any]:
        """Build a callable that performs one iteration of the benchmark."""
        if adapter.name in ("nbsymengine", "nbsymengine-lambda", "nbsymengine-llvm"):
            args, exprs = self.build_for_nbsymengine()
        else:
            args, exprs = self.build_for_sympy()

        lmb = adapter.build_lambdify(args, exprs)
        inp = self.input()

        def run():
            return lmb(inp)

        return run

    @abstractmethod
    def build_for_sympy(self) -> tuple[Any, Any]:
        """Return (args, exprs) in SymPy representation."""
        ...

    @abstractmethod
    def build_for_nbsymengine(self) -> tuple[Any, Any]:
        """Return (args, exprs) in native nbsymengine representation."""
        ...

    @abstractmethod
    def input(self) -> Any:
        """Return the input data for the benchmark."""
        ...

    @abstractmethod
    def expected(self) -> Any:
        """Return the expected output for validation."""
        ...

    @abstractmethod
    def validate(self, result: Any) -> None:
        """Validate *result* against expected output. Raise on mismatch."""
        ...


@dataclass
class IonSpeciationLambdifyCase(BenchmarkCase):
    """Port of external/symengine.py/benchmarks/Lambdify.py.

    14 x symbols, 14 p symbols, 28 scalar inputs, 15 scalar expressions.
    """
    name: str = "ion_speciation_lambdify"

    def __post_init__(self) -> None:
        import sympy as sp
        import numpy as np

        x = sp.symarray('x', 14)
        p = sp.symarray('p', 14)
        self._x = x
        self._p = p
        self._args = np.concatenate((x, p))
        exp = sp.exp
        self._exprs = [
            x[0] + x[1] - x[4] + 36.252574322669,
            x[0] - x[2] + x[3] + 21.3219379611249,
            x[3] + x[5] - x[6] + 9.9011158998744,
            2*x[3] + x[5] - x[7] + 18.190422234653,
            3*x[3] + x[5] - x[8] + 24.8679190043357,
            4*x[3] + x[5] - x[9] + 29.9336062089226,
            -x[10] + 5*x[3] + x[5] + 28.5520551531262,
            2*x[0] + x[11] - 2*x[4] - 2*x[5] + 32.4401680272417,
            3*x[1] - x[12] + x[5] + 34.9992934135095,
            4*x[1] - x[13] + x[5] + 37.0716199972041,
            p[0] - p[1] + 2*p[10] + 2*p[11] - p[12] - 2*p[13] + p[2] + 2*p[5] + 2*p[6] + 2*p[7] + 2*p[8] + 2*p[9] - exp(x[0]) + exp(x[1]) - 2*exp(x[10]) - 2*exp(x[11]) + exp(x[12]) + 2*exp(x[13]) - exp(x[2]) - 2*exp(x[5]) - 2*exp(x[6]) - 2*exp(x[7]) - 2*exp(x[8]) - 2*exp(x[9]),
            -p[0] - p[1] - 15*p[10] - 2*p[11] - 3*p[12] - 4*p[13] - 4*p[2] - 3*p[3] - 2*p[4] - 3*p[6] - 6*p[7] - 9*p[8] - 12*p[9] + exp(x[0]) + exp(x[1]) + 15*exp(x[10]) + 2*exp(x[11]) + 3*exp(x[12]) + 4*exp(x[13]) + 4*exp(x[2]) + 3*exp(x[3]) + 2*exp(x[4]) + 3*exp(x[6]) + 6*exp(x[7]) + 9*exp(x[8]) + 12*exp(x[9]),
            -5*p[10] - p[2] - p[3] - p[6] - 2*p[7] - 3*p[8] - 4*p[9] + 5*exp(x[10]) + exp(x[2]) + exp(x[3]) + exp(x[6]) + 2*exp(x[7]) + 3*exp(x[8]) + 4*exp(x[9]),
            -p[1] - 2*p[11] - 3*p[12] - 4*p[13] - p[4] + exp(x[1]) + 2*exp(x[11]) + 3*exp(x[12]) + 4*exp(x[13]) + exp(x[4]),
            -p[10] - 2*p[11] - p[12] - p[13] - p[5] - p[6] - p[7] - p[8] - p[9] + exp(x[10]) + 2*exp(x[11]) + exp(x[12]) + exp(x[13]) + exp(x[5]) + exp(x[6]) + exp(x[7]) + exp(x[8]) + exp(x[9]),
        ]

    def build_for_sympy(self) -> tuple[Any, Any]:
        return self._args, self._exprs

    def build_for_nbsymengine(self) -> tuple[Any, Any]:
        from ._sympy_to_nbsymengine import sympy_to_nbsymengine
        return (
            [sympy_to_nbsymengine(a) for a in self._args],
            [sympy_to_nbsymengine(e) for e in self._exprs]
        )

    def input(self) -> Any:
        import numpy as np
        return np.ones(28)

    def expected(self) -> Any:
        import sympy as sp
        import numpy as np
        lmb = sp.lambdify(self._args, self._exprs, modules='math')
        return np.array(lmb(*np.ones(28)), dtype=float)

    def validate(self, result: Any) -> None:
        import numpy as np
        expected = self.expected()
        result_arr = np.array(result, dtype=float).ravel()
        expected_arr = np.array(expected, dtype=float).ravel()
        np.testing.assert_allclose(result_arr, expected_arr, rtol=1e-10)


@dataclass
class HeterogeneousOutputLambdifyCase(BenchmarkCase):
    """Port of external/symengine.py/benchmarks/heterogeneous_output_Lambdify.py.

    Parses 6_links_rhs.txt, builds a 1x14 vector, computes Jacobian,
    and validates heterogeneous output (vector, matrix).
    """
    name: str = "heterogeneous_output_lambdify"

    def __post_init__(self) -> None:
        import sympy as sp
        from sympy.parsing.sympy_parser import parse_expr, standard_transformations

        data_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'data', '6_links_rhs.txt',
        )
        with open(data_path) as f:
            serial = f.read()
        parsed = parse_expr(serial, transformations=standard_transformations)
        vec = sp.Matrix(1, 14, parsed)
        self._sp_args = tuple(sorted(vec.free_symbols, key=lambda a: a.name))
        self._sp_exprs = (vec, vec.jacobian(self._sp_args[:-14]))
        self._sp_vec = vec

    def build_for_sympy(self) -> tuple[Any, Any]:
        return self._sp_args, self._sp_exprs

    def build_for_nbsymengine(self) -> tuple[Any, Any]:
        from ._sympy_to_nbsymengine import sympy_to_nbsymengine
        return (
            [sympy_to_nbsymengine(a) for a in self._sp_args],
            sympy_to_nbsymengine(self._sp_exprs)
        )

    def input(self) -> Any:
        import numpy as np
        return np.ones(len(self._sp_args))

    def expected(self) -> Any:
        import sympy as sp
        import numpy as np
        lmb = sp.lambdify(self._sp_args, self._sp_exprs, modules=['math', 'sympy'])
        inp = np.ones(len(self._sp_args))
        v, m = lmb(*inp)
        return np.array(v, dtype=float), np.array(m, dtype=float)

    def validate(self, result: Any) -> None:
        import numpy as np
        exp_v, exp_m = self.expected()
        res_v, res_m = result
        np.testing.assert_allclose(
            np.array(res_v, dtype=float).ravel(),
            np.array(exp_v, dtype=float).ravel(),
            rtol=1e-10,
        )
        np.testing.assert_allclose(
            np.array(res_m, dtype=float).ravel(),
            np.array(exp_m, dtype=float).ravel(),
            rtol=1e-10,
        )
