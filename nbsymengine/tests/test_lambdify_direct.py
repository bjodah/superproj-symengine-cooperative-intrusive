"""Tests for the direct nbsymengine.Lambdify API.

These tests verify the direct ``nbsymengine.lambdify`` module without
going through the legacy compatibility shim.
"""
from __future__ import annotations

import numpy as np
import pytest
import sys

# Legacy shim imports removed from direct tests


# ---------------------------------------------------------------------------
# Ensure the direct module does NOT import the legacy shim
# ---------------------------------------------------------------------------

def test_direct_module_no_legacy_import():
    """The direct lambdify module must not import the legacy shim."""
    import importlib
    import nbsymengine as sx
    mod_name = 'nbsymengine.lambdify'
    if mod_name in sys.modules:
        saved = sys.modules.pop(mod_name)
    else:
        saved = None
    # Also clear legacy modules
    legacy_mods = [k for k in sys.modules if 'legacy' in k]
    legacy_saved = {k: sys.modules.pop(k) for k in legacy_mods}
    # Save the package-level lambdify attribute (function, not module)
    saved_fn = getattr(sx, 'lambdify', None)
    try:
        mod = importlib.import_module(mod_name)
        # Verify no legacy module was imported as a side effect
        for k in sys.modules:
            if 'legacy' in k and k not in legacy_saved:
                pytest.fail(
                    f"Direct lambdify module imported legacy module: {k}"
                )
    finally:
        # Restore cached modules
        if saved is not None:
            sys.modules[mod_name] = saved
        sys.modules.update(legacy_saved)
        # Restore the package-level lambdify function
        if saved_fn is not None:
            sx.lambdify = saved_fn


# ---------------------------------------------------------------------------
# Scalar output
# ---------------------------------------------------------------------------

def test_scalar_output():
    """Lambdify with a single scalar expression."""
    import nbsymengine as sx
    x = sx.symbol('x')
    f = sx.Lambdify([x], x * x + 1)
    result = f([3.0])
    assert abs(float(result) - 10.0) < 1e-12


def test_scalar_output_varargs():
    """Lambdify with scalar varargs call signature."""
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    f = sx.Lambdify([x, y], x + y)
    result = f(2.0, 3.0)
    assert abs(float(result) - 5.0) < 1e-12


# ---------------------------------------------------------------------------
# Vector output
# ---------------------------------------------------------------------------

def test_vector_output():
    """Lambdify with a list of expressions returns a numpy array."""
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    f = sx.Lambdify([x, y], [x + y, x * y])
    result = f([2.0, 3.0])
    assert isinstance(result, np.ndarray)
    assert len(result) == 2
    assert abs(result[0] - 5.0) < 1e-12
    assert abs(result[1] - 6.0) < 1e-12


def test_vector_output_tuple():
    """Lambdify with a tuple of expressions."""
    import nbsymengine as sx
    x = sx.symbol('x')
    f = sx.Lambdify([x], (x, x * x, x * x * x))
    result = f([2.0])
    assert len(result) == 3
    assert abs(result[0] - 2.0) < 1e-12
    assert abs(result[1] - 4.0) < 1e-12
    assert abs(result[2] - 8.0) < 1e-12


# ---------------------------------------------------------------------------
# Matrix output
# ---------------------------------------------------------------------------

def _basic_to_float(val):
    """Convert a _core.Basic value to float."""
    try:
        return float(str(val))
    except (ValueError, TypeError):
        return float(val)


def test_matrix_output():
    """Lambdify with a DenseMatrix expression returns a shaped NumPy array."""
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    mat = sx.DenseMatrix(2, 1, [x + y, x * y])
    f = sx.Lambdify([x, y], mat)
    result = f([2.0, 3.0])
    assert isinstance(result, np.ndarray)
    assert result.dtype == np.float64
    assert result.shape == (2, 1)
    assert abs(result[0, 0] - 5.0) < 1e-12
    assert abs(result[1, 0] - 6.0) < 1e-12


# ---------------------------------------------------------------------------
# Heterogeneous output
# ---------------------------------------------------------------------------

def test_heterogeneous_output():
    """Lambdify with heterogeneous (matrix, matrix) output."""
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    vec = sx.DenseMatrix(2, 1, [x + y, x * y])
    mat = sx.DenseMatrix(2, 2, [x, y, y, x])
    f = sx.Lambdify([x, y], vec, mat)
    result = f([2.0, 3.0])
    assert isinstance(result, tuple)
    assert len(result) == 2
    r_vec, r_mat = result
    assert isinstance(r_vec, np.ndarray)
    assert isinstance(r_mat, np.ndarray)
    assert r_vec.shape == (2, 1)
    assert r_mat.shape == (2, 2)
    assert np.allclose(r_vec, [[5.0], [6.0]])
    assert np.allclose(r_mat, [[2.0, 3.0], [3.0, 2.0]])


# ---------------------------------------------------------------------------
# out= support
# ---------------------------------------------------------------------------

def test_out_parameter_flat_vector():
    """out= with a flat compatible array."""
    import numpy as np
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    f = sx.Lambdify([x, y], [x + y, x * y])
    out = np.zeros(2)
    result = f([2.0, 3.0], out=out)
    assert result is out
    assert abs(out[0] - 5.0) < 1e-12
    assert abs(out[1] - 6.0) < 1e-12


def test_out_parameter_scalar():
    """out= with scalar output."""
    import numpy as np
    import nbsymengine as sx
    x = sx.symbol('x')
    f = sx.Lambdify([x], x * x)
    out = np.zeros(1)
    result = f([3.0], out=out)
    assert result is out
    assert abs(out[0] - 9.0) < 1e-12


# ---------------------------------------------------------------------------
# CSE equivalence
# ---------------------------------------------------------------------------

def test_cse_equivalence():
    """LambdifyCSE produces the same results as Lambdify(..., cse=True)."""
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    exprs = [x + y, x * y, (x + y) * (x - y)]
    f_no_cse = sx.Lambdify([x, y], exprs)
    f_cse = sx.Lambdify([x, y], exprs, cse=True)
    f_cse_class = sx.LambdifyCSE([x, y], exprs)
    inp = [2.0, 3.0]
    r1 = f_no_cse(inp)
    r2 = f_cse(inp)
    r3 = f_cse_class(inp)
    assert len(r1) == len(r2) == len(r3) == 3
    for a, b, c in zip(r1, r2, r3):
        assert abs(a - b) < 1e-12
        assert abs(a - c) < 1e-12


# ---------------------------------------------------------------------------
# Module-level lambdify function
# ---------------------------------------------------------------------------

def test_module_level_lambdify():
    """The module-level lambdify() function works."""
    import nbsymengine as sx
    x = sx.symbol('x')
    f = sx.lambdify([x], x * x + 1)
    result = f([3.0])
    assert abs(float(result) - 10.0) < 1e-12


# ---------------------------------------------------------------------------
# NumPy input
# ---------------------------------------------------------------------------

def test_numpy_input():
    """Lambdify accepts NumPy arrays as input."""
    np = pytest.importorskip('numpy')
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    f = sx.Lambdify([x, y], x + y)
    inp = np.array([2.0, 3.0])
    result = f(inp)
    assert abs(float(result) - 5.0) < 1e-12


# ---------------------------------------------------------------------------
# DenseMatrix input args
# ---------------------------------------------------------------------------

def test_dense_matrix_args():
    """Lambdify accepts DenseMatrix as args."""
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    args_mat = sx.DenseMatrix(2, 1, [x, y])
    f = sx.Lambdify(args_mat, x + y)
    result = f([2.0, 3.0])
    assert abs(float(result) - 5.0) < 1e-12


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_reject_ambiguous_nested_args():
    """Nested list args should raise TypeError."""
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    with pytest.raises(TypeError, match="Ambiguous nested"):
        sx.Lambdify([[x, y]], x + y)


def test_batched_2d_input_raises():
    """2-D input arrays are unsupported by the 'sympy' backend."""
    np = pytest.importorskip('numpy')
    import nbsymengine as sx
    x = sx.symbol('x')
    f = sx.Lambdify([x], x)
    with pytest.raises(NotImplementedError, match="Batched 2-D"):
        f(np.array([[1.0], [2.0]]))


def test_out_incompatible_shape_raises():
    """out= with wrong shape should raise ValueError."""
    np = pytest.importorskip('numpy')
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    f = sx.Lambdify([x, y], [x + y, x * y])
    out = np.zeros(5)
    with pytest.raises(ValueError, match="incompatible"):
        f([2.0, 3.0], out=out)


def test_lambda_double_scalar():
    """backend='lambda_double' with a single scalar expression."""
    import nbsymengine as sx
    x = sx.symbol('x')
    f = sx.Lambdify([x], x * x + 1, backend='lambda_double')
    result = f([3.0])
    assert abs(float(result) - 10.0) < 1e-12


def test_unknown_backend():
    """Unknown backend should raise ValueError."""
    import nbsymengine as sx
    x = sx.symbol('x')
    with pytest.raises(ValueError, match="Unknown backend"):
        sx.Lambdify([x], x, backend='nonexistent')


# Legacy shim tests removed


# ---------------------------------------------------------------------------
# Phase 21: Native lambda_double backend tests
# ---------------------------------------------------------------------------

def test_lambda_double_vector():
    """lambda_double backend with vector output."""
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    f = sx.Lambdify([x, y], [x + y, x * y], backend='lambda_double')
    result = f([2.0, 3.0])
    assert isinstance(result, np.ndarray)
    assert len(result) == 2
    assert abs(result[0] - 5.0) < 1e-12
    assert abs(result[1] - 6.0) < 1e-12


def test_lambda_double_cse():
    """lambda_double backend with CSE enabled."""
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    exprs = [x + y, x * y, (x + y) * (x - y)]
    f = sx.Lambdify([x, y], exprs, backend='lambda_double', cse=True)
    result = f([2.0, 3.0])
    assert len(result) == 3
    assert abs(result[0] - 5.0) < 1e-12
    assert abs(result[1] - 6.0) < 1e-12
    assert abs(result[2] - (-5.0)) < 1e-12


def test_lambda_double_unknown_symbol():
    """lambda_double backend raises on unknown symbol."""
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    z = sx.symbol('z')
    with pytest.raises(RuntimeError):
        sx.Lambdify([x, y], x + z, backend='lambda_double')


def test_lambda_double_wrong_input_length():
    """lambda_double backend raises on wrong input length."""
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    f = sx.Lambdify([x, y], x + y, backend='lambda_double')
    with pytest.raises((ValueError, RuntimeError)):
        f([1.0])  # Need 2 inputs


def test_lambda_double_wrong_output_length():
    """lambda_double backend raises on wrong output array length."""
    import numpy as np
    import nbsymengine as sx
    x = sx.symbol('x')
    f = sx.Lambdify([x], [x, x * x], backend='lambda_double')
    # call_vector with wrong output is internal; test via ndarray call
    native = f._native
    inp = np.array([2.0], dtype=np.float64)
    out = np.array([0.0], dtype=np.float64)  # Need 2 slots
    with pytest.raises(ValueError):
        native.call(inp, out)


def test_lambda_double_repeated_calls():
    """lambda_double backend does not mutate state on repeated calls."""
    import nbsymengine as sx
    x = sx.symbol('x')
    f = sx.Lambdify([x], x * x, backend='lambda_double')
    for i in range(100):
        result = f([float(i)])
        assert abs(float(result) - float(i * i)) < 1e-12


def test_lambda_double_auto_backend():
    """backend='auto' resolves to lambda_double (or llvm when available)."""
    import nbsymengine as sx
    x = sx.symbol('x')
    f = sx.Lambdify([x], x * x + 1, backend='auto')
    if _llvm_available:
        assert f._backend == 'llvm'
    else:
        assert f._backend == 'lambda_double'
    result = f([3.0])
    assert abs(float(result) - 10.0) < 1e-12


def test_lambda_double_numpy_input():
    """lambda_double backend accepts NumPy arrays."""
    np = pytest.importorskip('numpy')
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    f = sx.Lambdify([x, y], x + y, backend='lambda_double')
    inp = np.array([2.0, 3.0])
    result = f(inp)
    assert abs(float(result) - 5.0) < 1e-12


def test_lambda_double_out_parameter():
    """lambda_double backend supports out= parameter."""
    np = pytest.importorskip('numpy')
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    f = sx.Lambdify([x, y], [x + y, x * y], backend='lambda_double')
    out = np.zeros(2)
    result = f([2.0, 3.0], out=out)
    assert result is out
    assert abs(out[0] - 5.0) < 1e-12
    assert abs(out[1] - 6.0) < 1e-12


def test_lambda_double_matrix_output():
    """lambda_double backend with DenseMatrix output."""
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    mat = sx.DenseMatrix(2, 1, [x + y, x * y])
    f = sx.Lambdify([x, y], mat, backend='lambda_double')
    result = f([2.0, 3.0])
    assert isinstance(result, np.ndarray)
    assert result.shape == (2, 1)
    assert np.allclose(result, [[5.0], [6.0]])


def test_lambda_double_functions():
    """lambda_double backend with various math functions."""
    import nbsymengine as sx
    import math
    x = sx.symbol('x')
    exprs = [sx.sin(x), sx.cos(x), sx.e() ** x, sx.log(x), sx.sqrt(x)]
    f = sx.Lambdify([x], exprs, backend='lambda_double')
    result = f([1.0])
    assert abs(result[0] - math.sin(1.0)) < 1e-12
    assert abs(result[1] - math.cos(1.0)) < 1e-12
    assert abs(result[2] - math.exp(1.0)) < 1e-12
    assert abs(result[3] - math.log(1.0)) < 1e-12
    assert abs(result[4] - math.sqrt(1.0)) < 1e-12


def test_lambda_double_matches_sympy():
    """lambda_double and sympy backends produce matching results."""
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    exprs = [x + y, x * y, sx.sin(x), sx.cos(y), x / (y + 1)]
    f_sympy = sx.Lambdify([x, y], exprs, backend='sympy')
    f_native = sx.Lambdify([x, y], exprs, backend='lambda_double')
    inp = [2.5, 3.7]
    r_sympy = f_sympy(inp)
    r_native = f_native(inp)
    for a, b in zip(r_sympy, r_native):
        assert abs(a - b) < 1e-12


def test_lambda_double_scalar_varargs():
    """lambda_double backend with scalar varargs call signature."""
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    f = sx.Lambdify([x, y], x + y, backend='lambda_double')
    result = f(2.0, 3.0)
    assert abs(float(result) - 5.0) < 1e-12


def test_lambda_double_unsafe_real():
    """lambda_double backend unsafe_real method."""
    np = pytest.importorskip('numpy')
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    f = sx.Lambdify([x, y], [x + y, x * y], backend='lambda_double')
    inp = np.array([2.0, 3.0], dtype=np.float64)
    out = np.zeros(2, dtype=np.float64)
    f.unsafe_real(inp, out)
    assert abs(out[0] - 5.0) < 1e-12
    assert abs(out[1] - 6.0) < 1e-12


# ---------------------------------------------------------------------------
# unsafe_complex tests
# ---------------------------------------------------------------------------

def test_unsafe_complex_sympy_backend():
    """unsafe_complex on the sympy backend returns correct complex results."""
    np = pytest.importorskip('numpy')
    import nbsymengine as sx
    x = sx.symbol('x')
    f = sx.Lambdify([x], x * x + 1, backend='sympy')
    inp = np.array([1.0 + 2.0j], dtype=np.complex128)
    out = np.zeros(1, dtype=np.complex128)
    f.unsafe_complex(inp, out)
    expected = (1.0 + 2.0j) ** 2 + 1
    assert abs(out[0] - expected) < 1e-12


def test_unsafe_complex_lambda_double_raises():
    """unsafe_complex on lambda_double raises NotImplementedError (no AttributeError)."""
    np = pytest.importorskip('numpy')
    import nbsymengine as sx
    x = sx.symbol('x')
    f = sx.Lambdify([x], x * x + 1, backend='lambda_double')
    inp = np.array([1.0 + 2.0j], dtype=np.complex128)
    out = np.zeros(1, dtype=np.complex128)
    with pytest.raises(NotImplementedError, match="does not support complex"):
        f.unsafe_complex(inp, out)


def test_unsafe_complex_lambda_double_no_attribute_error():
    """Regression: unsafe_complex on lambda_double must not raise AttributeError."""
    np = pytest.importorskip('numpy')
    import nbsymengine as sx
    x = sx.symbol('x')
    f = sx.Lambdify([x], x * x + 1, backend='lambda_double')
    inp = np.array([3.0], dtype=np.float64)
    out = np.zeros(1, dtype=np.float64)
    try:
        f.unsafe_complex(inp, out)
    except NotImplementedError:
        pass  # expected
    except AttributeError:
        pytest.fail("unsafe_complex raised AttributeError instead of NotImplementedError")


def test_unsafe_complex_cse_lambda_double_raises():
    """LambdifyCSE.unsafe_complex on lambda_double raises NotImplementedError."""
    np = pytest.importorskip('numpy')
    import nbsymengine as sx
    x = sx.symbol('x')
    f = sx.LambdifyCSE([x], x * x + 1, backend='lambda_double')
    inp = np.array([1.0 + 2.0j], dtype=np.complex128)
    out = np.zeros(1, dtype=np.complex128)
    with pytest.raises(NotImplementedError, match="does not support complex"):
        f.unsafe_complex(inp, out)


# ---------------------------------------------------------------------------
# Input validation tests (Phase 28)
# ---------------------------------------------------------------------------

def test_reject_invalid_expr_input():
    """Lambdify rejects non-expression inputs with a clear message."""
    import nbsymengine as sx
    x = sx.symbol('x')
    with pytest.raises(TypeError, match="Cannot normalize expression"):
        sx.Lambdify([x], 42)
    with pytest.raises(TypeError, match="Cannot normalize expression"):
        sx.Lambdify([x], "hello")


def test_lambda_double_noncontiguous_ndarray():
    """lambda_double backend handles non-contiguous ndarray input correctly."""
    np = pytest.importorskip('numpy')
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    f = sx.Lambdify([x, y], x + y, backend='lambda_double')
    # Column slice of a 2D array is non-contiguous in C order
    big = np.array([[1.0, 2.0], [3.0, 4.0]])
    col = big[:, 0]  # [1.0, 3.0] -- non-contiguous
    assert not col.flags['C_CONTIGUOUS']
    result = f(col)
    assert abs(float(result) - 4.0) < 1e-12


def test_lambda_double_wrong_dtype_ndarray():
    """lambda_double backend accepts float32 by converting to float64."""
    np = pytest.importorskip('numpy')
    import nbsymengine as sx
    x = sx.symbol('x')
    f = sx.Lambdify([x], x * x, backend='lambda_double')
    inp = np.array([3.0], dtype=np.float32)
    result = f(inp)
    assert abs(float(result) - 9.0) < 1e-12


def test_lambda_double_call_vector():
    """lambda_double native call_vector method works."""
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    f = sx.Lambdify([x, y], [x + y, x * y], backend='lambda_double')
    native = f._native
    result = native.call_vector([2.0, 3.0])
    assert isinstance(result, list)
    assert len(result) == 2
    assert abs(result[0] - 5.0) < 1e-12
    assert abs(result[1] - 6.0) < 1e-12


def test_lambda_double_call_vector_wrong_input():
    """lambda_double native call_vector raises on wrong input length."""
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    f = sx.Lambdify([x, y], x + y, backend='lambda_double')
    native = f._native
    with pytest.raises(ValueError):
        native.call_vector([1.0])  # Need 2 inputs


# ---------------------------------------------------------------------------
# LLVM backend tests
# ---------------------------------------------------------------------------

_llvm_available = False
try:
    from nbsymengine._core import have_llvm as _llvm_available
except (ImportError, AttributeError):
    pass


@pytest.mark.skipif(not _llvm_available, reason="LLVM not available")
def test_Lambdify_LLVM_basic():
    """LLVM backend with a single scalar expression."""
    import nbsymengine as sx
    x = sx.symbol('x')
    f = sx.Lambdify([x], x * x + 1, backend='llvm')
    result = f([3.0])
    assert abs(float(result) - 10.0) < 1e-12


@pytest.mark.skipif(not _llvm_available, reason="LLVM not available")
def test_Lambdify_LLVM_vector():
    """LLVM backend with vector output."""
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    f = sx.Lambdify([x, y], [x + y, x * y], backend='llvm')
    result = f([2.0, 3.0])
    assert isinstance(result, np.ndarray)
    assert len(result) == 2
    assert abs(result[0] - 5.0) < 1e-12
    assert abs(result[1] - 6.0) < 1e-12


@pytest.mark.skipif(not _llvm_available, reason="LLVM not available")
def test_Lambdify_LLVM_cse():
    """LLVM backend with CSE enabled."""
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    exprs = [x + y, x * y, (x + y) * (x - y)]
    f = sx.Lambdify([x, y], exprs, backend='llvm', cse=True)
    result = f([2.0, 3.0])
    assert len(result) == 3
    assert abs(result[0] - 5.0) < 1e-12
    assert abs(result[1] - 6.0) < 1e-12
    assert abs(result[2] - (-5.0)) < 1e-12


@pytest.mark.skipif(not _llvm_available, reason="LLVM not available")
def test_Lambdify_LLVM_opt_level():
    """LLVM backend with different optimization levels."""
    import nbsymengine as sx
    x = sx.symbol('x')
    expr = x * x + sx.sin(x)
    for level in range(4):
        f = sx.Lambdify([x], expr, backend='llvm', opt_level=level)
        result = f([2.5])
        expected = 2.5 * 2.5 + __import__('math').sin(2.5)
        assert abs(float(result) - expected) < 1e-12, f"Failed at opt_level={level}"


@pytest.mark.skipif(not _llvm_available, reason="LLVM not available")
def test_Lambdify_LLVM_matrix_output():
    """LLVM backend with DenseMatrix output."""
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    mat = sx.DenseMatrix(2, 1, [x + y, x * y])
    f = sx.Lambdify([x, y], mat, backend='llvm')
    result = f([2.0, 3.0])
    assert isinstance(result, np.ndarray)
    assert result.shape == (2, 1)
    assert np.allclose(result, [[5.0], [6.0]])


@pytest.mark.skipif(not _llvm_available, reason="LLVM not available")
def test_Lambdify_LLVM_heterogeneous():
    """LLVM backend with heterogeneous (matrix, matrix) output."""
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    vec = sx.DenseMatrix(2, 1, [x + y, x * y])
    mat = sx.DenseMatrix(2, 2, [x, y, y, x])
    f = sx.Lambdify([x, y], vec, mat, backend='llvm')
    result = f([2.0, 3.0])
    assert isinstance(result, tuple)
    assert len(result) == 2
    r_vec, r_mat = result
    assert isinstance(r_vec, np.ndarray)
    assert isinstance(r_mat, np.ndarray)
    assert r_vec.shape == (2, 1)
    assert r_mat.shape == (2, 2)
    assert np.allclose(r_vec, [[5.0], [6.0]])
    assert np.allclose(r_mat, [[2.0, 3.0], [3.0, 2.0]])


@pytest.mark.skipif(not _llvm_available, reason="LLVM not available")
def test_Lambdify_LLVM_serialization():
    """LLVM backend serialization via dumps()."""
    import nbsymengine as sx
    x = sx.symbol('x')
    f = sx.Lambdify([x], x * x + 1, backend='llvm')
    native = f._native
    blob = native.dumps()
    assert isinstance(blob, bytes)
    assert len(blob) > 0


@pytest.mark.skipif(not _llvm_available, reason="LLVM not available")
def test_Lambdify_LLVM_default_backend():
    """Verify 'auto' resolves to 'llvm' when available."""
    import nbsymengine as sx
    x = sx.symbol('x')
    f = sx.Lambdify([x], x * x + 1, backend='auto')
    assert f._backend == 'llvm'
    result = f([3.0])
    assert abs(float(result) - 10.0) < 1e-12


@pytest.mark.skipif(not _llvm_available, reason="LLVM not available")
def test_Lambdify_LLVM_unsafe_real():
    """LLVM backend unsafe_real method."""
    np = pytest.importorskip('numpy')
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    f = sx.Lambdify([x, y], [x + y, x * y], backend='llvm')
    inp = np.array([2.0, 3.0], dtype=np.float64)
    out = np.zeros(2, dtype=np.float64)
    f.unsafe_real(inp, out)
    assert abs(out[0] - 5.0) < 1e-12
    assert abs(out[1] - 6.0) < 1e-12


@pytest.mark.skipif(not _llvm_available, reason="LLVM not available")
def test_Lambdify_LLVM_unsafe_complex_raises():
    """LLVM backend unsafe_complex raises NotImplementedError."""
    np = pytest.importorskip('numpy')
    import nbsymengine as sx
    x = sx.symbol('x')
    f = sx.Lambdify([x], x * x + 1, backend='llvm')
    inp = np.array([1.0 + 2.0j], dtype=np.complex128)
    out = np.zeros(1, dtype=np.complex128)
    with pytest.raises(NotImplementedError):
        f.unsafe_complex(inp, out)


@pytest.mark.skipif(not _llvm_available, reason="LLVM not available")
def test_Lambdify_LLVM_matches_lambda_double():
    """LLVM and lambda_double backends produce matching results."""
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    exprs = [x + y, x * y, sx.sin(x), sx.cos(y), x / (y + 1)]
    f_lambda = sx.Lambdify([x, y], exprs, backend='lambda_double')
    f_llvm = sx.Lambdify([x, y], exprs, backend='llvm')
    inp = [2.5, 3.7]
    r_lambda = f_lambda(inp)
    r_llvm = f_llvm(inp)
    for a, b in zip(r_lambda, r_llvm):
        assert abs(a - b) < 1e-12


def test_Lambdify_LLVM_unavailable():
    """Graceful error when LLVM not compiled in."""
    import nbsymengine as sx
    x = sx.symbol('x')
    if not _llvm_available:
        with pytest.raises(ValueError, match="LLVM backend requested"):
            sx.Lambdify([x], x, backend='llvm')


@pytest.mark.skipif(not _llvm_available, reason="LLVM not available")
def test_Lambdify_LLVM_math_functions():
    """LLVM backend with various math functions."""
    import nbsymengine as sx
    import math
    x = sx.symbol('x')
    exprs = [sx.sin(x), sx.cos(x), sx.e() ** x, sx.log(x), sx.sqrt(x)]
    f = sx.Lambdify([x], exprs, backend='llvm')
    result = f([1.5])
    assert abs(result[0] - math.sin(1.5)) < 1e-12
    assert abs(result[1] - math.cos(1.5)) < 1e-12
    assert abs(result[2] - math.exp(1.5)) < 1e-12
    assert abs(result[3] - math.log(1.5)) < 1e-12
    assert abs(result[4] - math.sqrt(1.5)) < 1e-12


@pytest.mark.skipif(not _llvm_available, reason="LLVM not available")
def test_Lambdify_LLVM_repeated_calls():
    """LLVM backend does not mutate state on repeated calls."""
    import nbsymengine as sx
    x = sx.symbol('x')
    f = sx.Lambdify([x], x * x, backend='llvm')
    for i in range(100):
        result = f([float(i)])
        assert abs(float(result) - float(i * i)) < 1e-12


@pytest.mark.skipif(not _llvm_available, reason="LLVM not available")
def test_Lambdify_LLVM_varargs():
    """LLVM backend with scalar varargs call signature."""
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    f = sx.Lambdify([x, y], x + y, backend='llvm')
    result = f(2.0, 3.0)
    assert abs(float(result) - 5.0) < 1e-12


@pytest.mark.skipif(not _llvm_available, reason="LLVM not available")
def test_Lambdify_LLVM_wrong_input_length():
    """LLVM backend raises on wrong input length."""
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    f = sx.Lambdify([x, y], x + y, backend='llvm')
    with pytest.raises((ValueError, RuntimeError)):
        f([1.0])  # Need 2 inputs


@pytest.mark.skipif(not _llvm_available, reason="LLVM not available")
def test_Lambdify_LLVM_call_vector():
    """LLVM native call_vector method works."""
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    f = sx.Lambdify([x, y], [x + y, x * y], backend='llvm')
    native = f._native
    result = native.call_vector([2.0, 3.0])
    assert isinstance(result, list)
    assert len(result) == 2
    assert abs(result[0] - 5.0) < 1e-12
    assert abs(result[1] - 6.0) < 1e-12


@pytest.mark.skipif(not _llvm_available, reason="LLVM not available")
def test_Lambdify_LLVM_cse_lambda_double():
    """LambdifyCSE with LLVM backend."""
    import nbsymengine as sx
    x = sx.symbol('x')
    f = sx.LambdifyCSE([x], x * x + 1, backend='llvm')
    result = f([3.0])
    assert abs(float(result) - 10.0) < 1e-12


# ---------------------------------------------------------------------------
# Broadcasting (2-D input) on the native backends
# ---------------------------------------------------------------------------

_native_backends = ['lambda_double'] + (['llvm'] if _llvm_available else [])


@pytest.mark.parametrize('backend', _native_backends)
def test_broadcast_vector_1d_vs_2d(backend):
    """A 2-D input broadcasts row-wise and matches the 1-D results."""
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    f = sx.Lambdify([x, y], [x + y, x * y, sx.sin(x)], backend=backend)
    rows = np.array([[2.0, 3.0], [1.5, -0.5], [0.0, 4.0]])
    batched = f(rows)
    assert batched.shape == (3, 3)
    for i, row in enumerate(rows):
        assert np.allclose(batched[i], f(row))


@pytest.mark.parametrize('backend', _native_backends)
def test_broadcast_scalar_and_matrix_layouts(backend):
    """Batched input adds a leading dimension for every output layout."""
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    rows = np.array([[2.0, 3.0], [4.0, 5.0]])

    f_scalar = sx.Lambdify([x, y], x + y, backend=backend)
    r_scalar = f_scalar(rows)
    assert r_scalar.shape == (2,)
    assert np.allclose(r_scalar, [5.0, 9.0])

    mat = sx.DenseMatrix(2, 2, [x, y, y, x])
    f_mat = sx.Lambdify([x, y], mat, backend=backend)
    r_mat = f_mat(rows)
    assert r_mat.shape == (2, 2, 2)
    assert np.allclose(r_mat[0], [[2.0, 3.0], [3.0, 2.0]])
    assert np.allclose(r_mat[1], [[4.0, 5.0], [5.0, 4.0]])

    vec = sx.DenseMatrix(2, 1, [x + y, x * y])
    f_nested = sx.Lambdify([x, y], vec, mat, backend=backend)
    r_vec_b, r_mat_b = f_nested(rows)
    assert r_vec_b.shape == (2, 2, 1)
    assert r_mat_b.shape == (2, 2, 2)
    assert np.allclose(r_vec_b[1], [[9.0], [20.0]])
    assert np.allclose(r_mat_b[1], [[4.0, 5.0], [5.0, 4.0]])


@pytest.mark.parametrize('backend', _native_backends)
def test_mixed_scalar_matrix_output(backend):
    """A (scalar, matrix) output keeps scalars as floats, matrices as arrays."""
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    mat = sx.DenseMatrix(2, 2, [x, y, y, x])
    f = sx.Lambdify([x, y], x + y, mat, backend=backend)
    r_scalar, r_mat = f([2.0, 3.0])
    assert isinstance(r_scalar, float)
    assert abs(r_scalar - 5.0) < 1e-12
    assert r_mat.shape == (2, 2)
    assert np.allclose(r_mat, [[2.0, 3.0], [3.0, 2.0]])
    b_scalar, b_mat = f(np.array([[2.0, 3.0], [4.0, 5.0]]))
    assert b_scalar.shape == (2,)
    assert np.allclose(b_scalar, [5.0, 9.0])
    assert b_mat.shape == (2, 2, 2)


@pytest.mark.parametrize('backend', _native_backends)
def test_broadcast_out_flat_buffer(backend):
    """out= accepts an (m, n_flat) buffer for batched evaluation."""
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    f = sx.Lambdify([x, y], [x + y, x * y], backend=backend)
    rows = np.array([[2.0, 3.0], [4.0, 5.0]])
    out = np.zeros((2, 2))
    result = f(rows, out=out)
    assert result is out
    assert np.allclose(out, [[5.0, 6.0], [9.0, 20.0]])


@pytest.mark.parametrize('backend', _native_backends)
def test_call_alloc_2d(backend):
    """The native call_alloc returns (m, n_outputs) for 2-D input."""
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    f = sx.Lambdify([x, y], [x + y, x * y], backend=backend)
    native = f._native
    flat = native.call_alloc(np.array([2.0, 3.0]))
    assert flat.shape == (2,)
    assert np.allclose(flat, [5.0, 6.0])
    batched = native.call_alloc(np.array([[2.0, 3.0], [4.0, 5.0]]))
    assert batched.dtype == np.float64
    assert batched.shape == (2, 2)
    assert np.allclose(batched, [[5.0, 6.0], [9.0, 20.0]])
    with pytest.raises(ValueError):
        native.call_alloc(np.zeros((2, 3)))


@pytest.mark.parametrize('backend', _native_backends)
def test_out_matrix_layout_flat_buffer(backend):
    """out= with a matrix layout fills a flat float64 buffer."""
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    mat = sx.DenseMatrix(2, 2, [x, y, y, x])
    f = sx.Lambdify([x, y], mat, backend=backend)
    out = np.zeros(4)
    result = f([2.0, 3.0], out=out)
    assert result is out
    assert np.allclose(out, [2.0, 3.0, 3.0, 2.0])


@pytest.mark.parametrize('backend', _native_backends)
def test_call_does_not_mutate_input(backend):
    """Regression: evaluation must not write into the input array."""
    import nbsymengine as sx
    x, y = sx.symbol('x'), sx.symbol('y')
    f = sx.Lambdify([x, y], [x + y, x * y], backend=backend)
    inp = np.array([2.0, 3.0], dtype=np.float64)
    original = inp.copy()
    for _ in range(3):
        f(inp)
    assert np.array_equal(inp, original)


# ---------------------------------------------------------------------------
# DenseMatrix.to_numpy
# ---------------------------------------------------------------------------

def test_dense_matrix_to_numpy():
    """DenseMatrix.to_numpy() returns a float64 (nrows, ncols) array."""
    import nbsymengine as sx
    mat = sx.DenseMatrix(2, 3, [sx.integer(1), sx.integer(2), sx.integer(3),
                                sx.integer(4), sx.integer(5), sx.integer(6)])
    arr = mat.to_numpy()
    assert isinstance(arr, np.ndarray)
    assert arr.dtype == np.float64
    assert arr.shape == (2, 3)
    assert np.allclose(arr, [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
    # __array__ hook
    assert np.allclose(np.asarray(mat), arr)


def test_dense_matrix_to_numpy_non_numeric_raises():
    """DenseMatrix.to_numpy() propagates the SymEngine error for symbols."""
    import nbsymengine as sx
    x = sx.symbol('x')
    mat = sx.DenseMatrix(1, 2, [x, sx.integer(1)])
    with pytest.raises(RuntimeError):
        mat.to_numpy()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _is_dense_matrix(obj):
    try:
        from nbsymengine import _core
        return isinstance(obj, _core.DenseMatrix)
    except (AttributeError, ImportError):
        return False
