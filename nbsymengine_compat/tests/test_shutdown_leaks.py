"""Subprocess-based leak/shutdown regression tests for nbsymengine_compat.

Uses subprocess to detect nanobind reference-counting issues at exit.
"""
from __future__ import annotations

import subprocess
import sys

import pytest


_IMPORT_AND_EXERCISE = """
import gc
from nbsymengine_compat.symengine_py_compat import (
    Symbol, Integer, Rational, DenseMatrix, ImmutableMatrix,
    FiniteSet, Interval, EmptySet, UniversalSet, true_const, false_const,
    sin, cos, exp, Pow, I, E, pi,
    gcd, lcm, nextprime, fibonacci, lucas, factorial, binomial,
    series, diff, subs,
)

def main():
    x = Symbol("x")
    y = Symbol("y")
    n = Integer(5)
    r = Rational(1, 2)
    e = sin(x) + cos(y)
    e_expanded = e.expand()
    e_subbed = e.subs(x, n)
    e_diff = e.diff(x)
    e_series = series(sin(x), x, n=10)

    A = DenseMatrix([[1, 2], [3, 4]])
    B = ImmutableMatrix([[x, y], [1, 0]])
    C = A * B
    D = A + A
    det_A = A.det()
    inv_A = A.inv()

    fs = FiniteSet(1, 2, 3)
    iv = Interval(0, 1)
    es = EmptySet()
    us = UniversalSet()
    u = fs.union(iv)

    t = true_const()
    f = false_const()

    p = Pow(x, 2)

    g = gcd(12, 18)
    l = lcm(12, 18)
    fib = fibonacci(10)
    luc = lucas(10)
    fac = factorial(10)
    bin_coeff = binomial(10, 3)
    np = nextprime(100)

main()
gc.collect()
"""

_SUBPROCESS_TIMEOUT = 30


def _run_code(code: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=_SUBPROCESS_TIMEOUT,
    )


def test_no_leak_warnings_on_exit():
    proc = subprocess.run(
        [sys.executable, "-c", _IMPORT_AND_EXERCISE],
        capture_output=True,
        text=True,
    )
    stderr = proc.stderr
    assert proc.returncode == 0, f"Subprocess failed with code {proc.returncode}: {stderr}"
    assert "nanobind: leaked" not in stderr, f"Leak detected in stderr:\n{stderr}"
    assert "reference counting issue" not in stderr, f"Reference counting issue:\n{stderr}"


def test_repeated_import_drop_legacy():
    """Import the legacy shim, access symbols, then exit repeatedly."""
    code = (
        "from nbsymengine_compat import symengine_py_compat as se\n"
        "x = se.Symbol('x')\n"
        "p = se.pi\n"
        "z = se.S.Zero\n"
        "assert se.S.Pi is se.S.Pi\n"
        "assert se.S.Zero is se.S.Zero\n"
    )
    for i in range(10):
        result = _run_code(code)
        assert result.returncode == 0, (
            f"iteration {i} failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )


def test_singleton_wrappers_before_shutdown_legacy():
    """Create major compat singletons and let the interpreter exit."""
    code = (
        "from nbsymengine_compat import symengine_py_compat as se\n"
        "singletons = {\n"
        "    'pi': se.pi,\n"
        "    'E': se.E,\n"
        "    'EulerGamma': se.EulerGamma,\n"
        "    'I': se.I,\n"
        "    'oo': se.oo,\n"
        "    'zoo': se.zoo,\n"
        "    'nan': se.nan,\n"
        "    'true': se.true,\n"
        "    'false': se.false,\n"
        "    'Zero': se.S.Zero,\n"
        "    'One': se.S.One,\n"
        "    'Pi': se.S.Pi,\n"
        "    'Exp1': se.S.Exp1,\n"
        "    'EmptySet': se.S.EmptySet,\n"
        "}\n"
        "for name, obj in singletons.items():\n"
        "    assert isinstance(obj, se.Basic), f'{name} is not Basic'\n"
    )
    result = _run_code(code)
    assert result.returncode == 0, (
        f"Failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_subprocess_singleton_identity_legacy():
    """Verify singleton identity through the legacy S namespace."""
    code = (
        "from nbsymengine_compat import symengine_py_compat as se\n"
        "assert se.S.Zero is se.S.Zero, 'S.Zero identity'\n"
        "assert se.S.One is se.S.One, 'S.One identity'\n"
        "assert se.S.Pi is se.S.Pi, 'S.Pi identity'\n"
        "assert se.S.Exp1 is se.S.Exp1, 'S.Exp1 identity'\n"
        "assert se.S.EulerGamma is se.S.EulerGamma, 'S.EulerGamma identity'\n"
        "assert se.S.EmptySet is se.S.EmptySet, 'S.EmptySet identity'\n"
        "assert se.true is se.true, 'true identity'\n"
        "assert se.false is se.false, 'false identity'\n"
        "assert se.pi is se.pi, 'pi identity'\n"
        "assert se.E is se.E, 'E identity'\n"
        "assert se.I is se.I, 'I identity'\n"
        "assert se.oo is se.oo, 'oo identity'\n"
    )
    result = _run_code(code)
    assert result.returncode == 0, (
        f"Legacy identity test failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
