"""Tests for adapter calling conventions."""
import pytest
import numpy as np


def test_sympy_adapter_call_convention():
    """SymPy adapter unpacks input via lmb(*inp)."""
    from nbsymengine_benchmarks.adapters import SymPyAdapter
    import sympy as sp

    adapter = SymPyAdapter()
    if not adapter.is_available():
        pytest.skip("sympy not available")

    x, y = sp.symbols('x y')
    lmb = adapter.build_lambdify([x, y], [x + y])
    result = lmb(np.array([1.0, 2.0]))
    assert np.allclose(result, [3.0])


def test_nbsymengine_adapter_call_convention():
    """NBSymEngine adapter uses lmb(inp) for non-heterogeneous."""
    from nbsymengine_benchmarks.adapters import NBSymEngineAdapter
    import nbsymengine as sx

    adapter = NBSymEngineAdapter()
    if not adapter.is_available():
        pytest.skip("nbsymengine not available")

    x, y = sx.symbol('x'), sx.symbol('y')
    lmb = adapter.build_lambdify([x, y], [x + y])
    result = lmb(np.array([1.0, 2.0]))
    assert np.allclose(result, [3.0])


def test_legacy_symengine_adapter_call_convention():
    """LegacySymEngine adapter uses lmb(inp) for non-heterogeneous."""
    from nbsymengine_benchmarks.adapters import LegacySymEngineAdapter
    import sympy as sp

    adapter = LegacySymEngineAdapter()
    if not adapter.is_available():
        pytest.skip("legacy symengine not available")

    x, y = sp.symbols('x y')
    lmb = adapter.build_lambdify([x, y], [x + y])
    result = lmb(np.array([1.0, 2.0]))
    assert np.allclose(result, [3.0])


def test_adapter_build_lambdify_returns_callable():
    """All available adapters return a callable from build_lambdify."""
    from nbsymengine_benchmarks.adapters import ALL_ADAPTERS
    import sympy as sp
    import nbsymengine as sx

    for adapter in ALL_ADAPTERS:
        if not adapter.is_available():
            continue
        if adapter.name in ("nbsymengine", "nbsymengine-lambda", "nbsymengine-llvm"):
            x = sx.symbol('x')
            lmb = adapter.build_lambdify([x], [x + 1])
        else:
            x = sp.Symbol('x')
            lmb = adapter.build_lambdify([x], [x + 1])
        assert callable(lmb), f"{adapter.name}.build_lambdify did not return a callable"
