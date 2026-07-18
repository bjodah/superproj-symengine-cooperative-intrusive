"""Tests for compat benchmark adapter calling conventions."""
import pytest
import numpy as np
import sys
import os

# Add nbsymengine_compat to sys.path so we can import from benchmarks
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from benchmarks.compat_adapters import NBSymEngineLegacyAdapter


def test_nbsymengine_legacy_adapter_call_convention():
    """NBSymEngineLegacy adapter uses lmb(inp) for non-heterogeneous."""
    import sympy as sp

    adapter = NBSymEngineLegacyAdapter()
    if not adapter.is_available():
        pytest.skip("nbsymengine_compat not available")

    x, y = sp.symbols('x y')
    lmb = adapter.build_lambdify([x, y], [x + y])
    result = lmb(np.array([1.0, 2.0]))
    assert np.allclose(result, [3.0])
