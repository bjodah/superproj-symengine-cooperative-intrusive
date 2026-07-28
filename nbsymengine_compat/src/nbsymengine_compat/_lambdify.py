"""nbsymengine_compat._lambdify -- The compat Lambdify class."""
from __future__ import annotations

from nbsymengine import _core
from ._helpers import _sympify, HAS_SYMPY, _require_sympy

try:
    import numpy as np
except ImportError:  # pragma: no cover - NumPy is optional at import time
    np = None

# ``symengine_py_compat`` star-imports this module; keep ``np`` out of the
# legacy public surface.
__all__ = ['Lambdify', 'lambdify']


def _is_matrix(obj):
    """Check if obj is a DenseMatrix (raw or wrapper)."""
    if isinstance(obj, _core.DenseMatrix):
        return True
    if hasattr(obj, '_raw') and isinstance(obj._raw, _core.DenseMatrix):
        return True
    return False


def _unwrap_matrix(obj):
    """Unwrap a matrix to raw _core.DenseMatrix."""
    if hasattr(obj, '_raw') and isinstance(obj._raw, _core.DenseMatrix):
        return obj._raw
    return obj


# ---------------------------------------------------------------------------
# Legacy output bookkeeping
#
# ``symengine.py``'s ``_Lambdify`` records ``out_shapes`` as
# ``[np.asanyarray(expr).shape for expr in exprs]`` and flattens every
# expression in C order into a single output buffer.  The two helpers below
# reproduce that without ever building an object ndarray (which would require
# ``Basic`` to be non-iterable and a ``DenseMatrix`` to have a symbolic
# ``__array__``).
# ---------------------------------------------------------------------------

def _expr_shape(expr):
    """NumPy-style shape recorded by legacy ``symengine.py`` for *expr*."""
    if _is_matrix(expr):
        raw = _unwrap_matrix(expr)
        return (raw.nrows(), raw.ncols())
    if isinstance(expr, _core.Basic):
        return ()
    if hasattr(expr, '_raw') and isinstance(expr._raw, _core.Basic):
        return ()
    if np is not None and isinstance(expr, np.ndarray):
        return expr.shape
    if isinstance(expr, (list, tuple)):
        if not expr:
            return (0,)
        return (len(expr),) + _expr_shape(expr[0])
    shape = getattr(expr, 'shape', None)  # e.g. a SymPy Matrix
    if (isinstance(shape, tuple) and len(shape) == 2
            and all(isinstance(d, int) for d in shape)):
        return shape
    return ()


def _flatten_expr(expr, out):
    """Append the C-order flattening of *expr* (as raw ``Basic``) to *out*."""
    if _is_matrix(expr):
        raw = _unwrap_matrix(expr)
        for i in range(raw.nrows()):
            for j in range(raw.ncols()):
                out.append(raw.get(i, j))
        return
    if isinstance(expr, _core.Basic):
        out.append(expr)
        return
    if hasattr(expr, '_raw') and isinstance(expr._raw, _core.Basic):
        out.append(expr._raw)
        return
    if np is not None and isinstance(expr, np.ndarray):
        for e in expr.ravel(order='C'):
            _flatten_expr(e, out)
        return
    if isinstance(expr, (list, tuple)):
        for e in expr:
            _flatten_expr(e, out)
        return
    shape = getattr(expr, 'shape', None)  # e.g. a SymPy Matrix
    if (isinstance(shape, tuple) and len(shape) == 2
            and all(isinstance(d, int) for d in shape)):
        for i in range(shape[0]):
            for j in range(shape[1]):
                out.append(_sympify(expr[i, j]))
        return
    out.append(_sympify(expr))


def _shape_size(shape):
    n = 1
    for d in shape:
        n *= d
    return n


def _to_pickle_tree(obj):
    """Convert compat/raw objects into a pickle-safe tree."""
    from ._sympy_bridge import to_sympy

    if _is_matrix(obj):
        return to_sympy(_unwrap_matrix(obj))
    if isinstance(obj, (list, tuple)):
        return type(obj)(_to_pickle_tree(x) for x in obj)
    if hasattr(obj, '_raw') and isinstance(obj._raw, _core.Basic):
        return to_sympy(obj._raw)
    if isinstance(obj, _core.Basic):
        return to_sympy(obj)
    return obj


def _from_pickle_tree(obj):
    """Rebuild compat constructor inputs from a pickle-safe tree."""
    import sympy
    from ._sympy_bridge import from_sympy

    if isinstance(obj, (list, tuple)):
        return type(obj)(_from_pickle_tree(x) for x in obj)
    if isinstance(obj, sympy.MatrixBase):
        return from_sympy(obj)
    if isinstance(obj, sympy.Basic):
        return from_sympy(obj)
    return obj


def _unpickle_lambdify(args_data, exprs_data, config):
    """Rebuild a compat Lambdify instance from pickle state."""
    args = _from_pickle_tree(args_data)
    exprs = _from_pickle_tree(exprs_data)
    exprs_list = list(exprs) if isinstance(exprs, (list, tuple)) else [exprs]
    kwargs = dict(config.get("extra_kwargs", {}))
    return Lambdify(
        args,
        *exprs_list,
        backend=config["backend"],
        cse=config["cse"],
        real=config["real"],
        order=config["order"],
        dtype=config["dtype"],
        opt_level=config["opt_level"],
        as_scipy=config["as_scipy"],
        **kwargs,
    )


_FLOAT64_DTYPES = (None, float)


def _is_float64_dtype(dtype):
    if dtype in _FLOAT64_DTYPES:
        return True
    if np is None:
        return False
    try:
        return np.dtype(dtype) == np.float64
    except TypeError:
        return False


class Lambdify:
    """Legacy Lambdify class wrapping SymPy's lambdify for numeric evaluation.

    Delegates to the direct ``nbsymengine.lambdify.Lambdify`` when semantics
    match (backend='lambda'/'sympy'/'llvm', real C-order float64 output, no
    ``as_scipy``).  In that mode the direct object is used purely as a flat
    ``float64`` evaluator -- output shapes, broadcasting and the
    single-array-vs-list return convention follow legacy ``symengine.py``.
    Falls back to the original SymPy implementation for legacy-only features
    (complex evaluation, Fortran order, ``as_scipy``, extra kwargs).
    """
    def __init__(self, args, *exprs, backend='lambda', cse=False,
                 real=True, order='C', dtype=None, opt_level=None,
                 as_scipy=False, **kwargs):
        from ._constants import have_llvm
        if opt_level is not None and backend == 'lambda':
            raise TypeError("opt_level not supported for lambda backend")
        if backend == 'llvm' and not have_llvm:
            raise ValueError("LLVM backend not available")
        self.as_scipy = as_scipy
        self._backend = backend
        self._cse = cse
        self._real = real
        self._order = order
        self._dtype = dtype
        self._opt_level = opt_level
        self._extra_kwargs = dict(kwargs)
        self._native = None
        self._fast = None

        # Determine if we can delegate to the direct implementation.  The
        # direct native backends are real-valued, C order and float64 only;
        # anything else keeps using the SymPy-based fallback below.
        _direct_backend = backend in ('lambda', 'sympy', 'llvm')
        _use_direct = (
            _direct_backend and not as_scipy and not kwargs and np is not None
            and real and order == 'C' and _is_float64_dtype(dtype)
        )

        if _use_direct:
            try:
                from nbsymengine.lambdify import Lambdify as _DirectLambdify
                if backend == 'lambda':
                    _be = 'lambda_double'
                elif backend == 'llvm':
                    _be = 'llvm'
                else:
                    _be = backend
                _direct_kwargs = dict(backend=_be, cse=cse, real=real,
                                      order=order, dtype=float)
                if opt_level is not None and backend == 'llvm':
                    _direct_kwargs['opt_level'] = opt_level

                raw_args = []
                _flatten_expr(args, raw_args)
                if not raw_args:
                    raise NotImplementedError(
                        "Support for zero arguments not yet supported")

                # Legacy bookkeeping straight off the constructor arguments.
                out_shapes = [_expr_shape(e) for e in exprs]
                flat_exprs = []
                for e in exprs:
                    _flatten_expr(e, flat_exprs)
                if sum(_shape_size(s) for s in out_shapes) != len(flat_exprs):
                    raise ValueError("inconsistent expression shapes")

                # The direct object only ever sees one flat list of scalar
                # expressions, so its own flat buffer order is ours.
                self._direct = _DirectLambdify(raw_args, flat_exprs,
                                               **_direct_kwargs)
                self._native = getattr(self._direct, '_native', None)
                self._args = raw_args
                self._exprs_list = list(exprs)
                self._raw_args = args
                self.real = real
                self.order = order
                self._setup_legacy_layout(out_shapes)
                return
            except Exception:
                # Fall back to original implementation
                self._direct = None
                self._native = None
                self._fast = None

        # Original implementation for legacy-only features
        self._direct = None
        if not HAS_SYMPY:
            _require_sympy("Lambdify with legacy fallback")
        import sympy
        from ._sympy_bridge import to_sympy
        self._raw_args = args
        self._args = []
        if _is_matrix(args):
            raw_args = _unwrap_matrix(args)
            for i in range(raw_args.nrows()):
                self._args.append(_sympify(raw_args.get(i, 0)))
        elif isinstance(args, (list, tuple)):
            for a in args:
                self._args.append(_sympify(a))
        else:
            self._args.append(_sympify(args))

        self._exprs_list = []
        for expr in exprs:
            if _is_matrix(expr):
                self._exprs_list.append(expr)
            else:
                self._exprs_list.append(_sympify(expr))

        self.real = real
        self.order = order
        self.n_exprs = len(self._exprs_list)
        self.args_size = len(self._args)

        sp_args = [to_sympy(a) for a in self._args]
        sp_exprs = []
        for expr in self._exprs_list:
            if _is_matrix(expr):
                raw_expr = _unwrap_matrix(expr)
                sp_exprs.append(sympy.Matrix(raw_expr.tolist()))
            else:
                sp_exprs.append(to_sympy(expr))

        if len(sp_exprs) == 1:
            single = sp_exprs[0]
            self._func = sympy.lambdify(sp_args, single, modules='numpy', **kwargs)
            self._single = True
        else:
            self._func = sympy.lambdify(sp_args, sp_exprs, modules='numpy', **kwargs)
            self._single = False

    # -- legacy output bookkeeping / evaluation ----------------------------

    def _setup_legacy_layout(self, out_shapes):
        """Record legacy ``out_shapes``/``accum_out_sizes`` and bind a fast call."""
        self.out_shapes = [tuple(s) for s in out_shapes]
        self.n_exprs = len(self.out_shapes)
        self.args_size = len(self._args)
        out_sizes = [_shape_size(s) for s in self.out_shapes]
        self.tot_out_size = sum(out_sizes)
        accum = [0]
        for size in out_sizes:
            accum.append(accum[-1] + size)
        self.accum_out_sizes = accum
        self._parts = [
            (accum[i], accum[i + 1], self.out_shapes[i])
            for i in range(self.n_exprs)
        ]
        self._fast = self._build_fast_call()

    def _build_fast_call(self):
        """Closure for the common ``f(inp_1d_float64_array)`` native call.

        Mirrors the legacy return convention: one array when a single
        expression was passed, a list of arrays otherwise.
        """
        native = self._native
        if native is None:
            return None
        call_into = native.call_into
        empty = np.empty
        f64 = np.float64
        tot = self.tot_out_size
        parts = self._parts

        if self.n_exprs == 1:
            shape = self.out_shapes[0]
            if shape == (tot,):
                def fast(inp):
                    buf = empty(tot, dtype=f64)
                    call_into(inp, buf)
                    return buf
            else:
                def fast(inp):
                    buf = empty(tot, dtype=f64)
                    call_into(inp, buf)
                    return buf.reshape(shape)
        else:
            def fast(inp):
                buf = empty(tot, dtype=f64)
                call_into(inp, buf)
                return [buf[start:stop].reshape(shape)
                        for start, stop, shape in parts]
        return fast

    def _eval_flat(self, inp, out_flat, nbroadcast):
        """Fill *out_flat* (size ``nbroadcast * tot_out_size``) from *inp*."""
        native = self._native
        if native is not None:
            native.call_into(inp, out_flat)
            return
        # SymPy-backed direct object: no flat C++ evaluator, go row by row.
        tot = self.tot_out_size
        if nbroadcast == 1:
            self._direct.unsafe_real(inp, out_flat)
        else:
            for i in range(nbroadcast):
                self._direct.unsafe_real(
                    inp[i], out_flat[i * tot:(i + 1) * tot])

    def _call_legacy(self, args, out):
        """Legacy ``symengine.py`` ``__call__`` semantics on the direct object."""
        if len(args) == 1:
            args = args[0]
        try:
            inp = np.ascontiguousarray(args, dtype=np.float64)
        except (TypeError, ValueError):
            inp = np.fromiter(args, dtype=np.float64)

        args_size = self.args_size
        if inp.size < args_size or inp.size % args_size != 0:
            raise ValueError("Broadcasting failed (input/arg size mismatch)")
        nbroadcast = inp.size // args_size

        if inp.ndim > 1:
            if args_size > 1:
                if inp.shape[inp.ndim - 1] != args_size:
                    raise ValueError(
                        "C order implies last dim (%d) == len(args) (%d)"
                        % (inp.shape[inp.ndim - 1], args_size))
                extra_dim = inp.shape[:inp.ndim - 1]
            else:
                extra_dim = inp.shape
        elif nbroadcast > 1:
            extra_dim = (nbroadcast,)  # special case: flat, broadcast input
        else:
            extra_dim = ()
        new_out_shapes = [extra_dim + shape for shape in self.out_shapes]

        tot = self.tot_out_size
        new_tot_out_size = nbroadcast * tot
        if out is None:
            buf = np.empty(new_tot_out_size, dtype=np.float64)
        else:
            buf = self._prepare_out(out, new_tot_out_size)[:new_tot_out_size]

        if nbroadcast > 1:
            inp = inp.reshape((nbroadcast, args_size))
        else:
            inp = inp.reshape(args_size)
        self._eval_flat(inp, buf, nbroadcast)

        res = buf.reshape((nbroadcast, tot))
        accum = self.accum_out_sizes
        result = [
            res[:, accum[idx]:accum[idx + 1]].reshape(new_out_shapes[idx])
            for idx in range(self.n_exprs)
        ]
        return result[0] if self.n_exprs == 1 else result

    def _prepare_out(self, out, new_tot_out_size):
        """Validate a legacy ``out=`` buffer and return a flat writable view."""
        if not isinstance(out, np.ndarray):
            raise TypeError("out= must be a NumPy ndarray")
        if out.size < new_tot_out_size:
            raise ValueError("Incompatible size of output argument")
        if out.dtype != np.float64:
            raise ValueError("Output argument must have dtype float64")
        if not out.flags['C_CONTIGUOUS']:
            raise ValueError("Output argument needs to be C-contiguous")
        if not out.flags['WRITEABLE']:
            raise ValueError("Output argument needs to be writeable")
        if out.ndim > 1:
            if self.n_exprs > 1:
                raise ValueError("output array with ndim > 1 assumes one output")
            out_shape, = self.out_shapes
            if out_shape and out.shape[-len(out_shape):] != tuple(out_shape):
                raise ValueError("shape mismatch for output array")
        return out.reshape(-1)

    def __call__(self, *args, out=None, **kwargs):
        # Delegate to direct implementation when available
        if self._direct is not None:
            fast = self._fast
            if fast is not None and out is None and len(args) == 1:
                inp = args[0]
                if (inp.__class__ is np.ndarray and inp.ndim == 1
                        and inp.shape[0] == self.args_size):
                    try:
                        return fast(inp)
                    except TypeError:  # e.g. an object dtype -- go general
                        pass
            return self._call_legacy(args, out)
        # as_scipy mode: called with individual float arguments
        if self.as_scipy and len(args) > 1:
            result = self._func(*args)
            if isinstance(result, np.ndarray):
                return float(result.flat[0])
            return float(result)
        # Normal mode: first arg is the input array
        inp = args[0] if args else []
        if isinstance(inp, np.ndarray):
            if inp.ndim == 1:
                if self._single:
                    result = np.atleast_1d(self._func(*inp))
                else:
                    result = np.array(self._func(*inp))
            else:
                results = [self._func(*row) for row in inp]
                result = np.array(results)
        elif hasattr(inp, '__iter__'):
            inp_list = list(inp)
            if self._single:
                result = np.atleast_1d(self._func(*inp_list))
            else:
                result = np.array(self._func(*inp_list))
        else:
            if self._single:
                result = np.atleast_1d(self._func(inp))
            else:
                result = np.array(self._func(inp))

        if out is not None:
            np.copyto(out, result)
            return out
        return result

    def unsafe_real(self, inp, out):
        """Evaluate with real input/output arrays (no type checks)."""
        if self._direct is not None:
            return self._direct.unsafe_real(inp, out)
        result = self._func(*inp)
        if isinstance(result, (list, tuple)):
            result = np.array(result)
        result = np.atleast_1d(np.asarray(result, dtype=np.float64))
        np.copyto(out, result.flat[:out.size].reshape(out.shape))

    def unsafe_complex(self, inp, out):
        """Evaluate with complex input/output arrays (no type checks)."""
        if self._direct is not None:
            return self._direct.unsafe_complex(inp, out)
        result = self._func(*inp)
        if isinstance(result, (list, tuple)):
            result = np.array(result)
        result = np.atleast_1d(np.asarray(result, dtype=np.complex128))
        np.copyto(out, result.flat[:out.size].reshape(out.shape))

    def as_ctypes(self):
        """Return (function_pointer, user_data) for ctypes interop."""
        import ctypes
        nargs = self.args_size
        # SymPy fallback path has no flat-buffer bookkeeping.
        nout = self.tot_out_size if self._direct is not None else self.n_exprs

        def _c_func(out_p, inp_p, user_data):
            inp = np.ctypeslib.as_array(inp_p, shape=(nargs,))
            out = np.ctypeslib.as_array(out_p, shape=(nout,))
            self.unsafe_real(inp, out)

        c_func_type = ctypes.CFUNCTYPE(None,
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double),
            ctypes.c_void_p)
        c_func = c_func_type(_c_func)
        return c_func, None

    def __reduce_ex__(self, protocol):
        if self._backend == 'sympy' or self._direct is None:
            raise NotImplementedError(
                "pickling compat Lambdify is only supported for delegated "
                "native backends"
            )
        config = {
            "backend": self._backend,
            "cse": self._cse,
            "real": self._real,
            "order": self._order,
            "dtype": self._dtype,
            "opt_level": self._opt_level,
            "as_scipy": self.as_scipy,
            "extra_kwargs": self._extra_kwargs,
        }
        return (
            _unpickle_lambdify,
            (_to_pickle_tree(self._raw_args), _to_pickle_tree(self._exprs_list), config),
        )


def lambdify(args, exprs, modules=None, **kwargs):
    """Module-level lambdify wrapping SymPy's lambdify.

    When ``modules`` is the default ``'numpy'`` and only direct-API kwargs are
    passed, delegates to the direct ``nbsymengine.lambdify.lambdify``.
    """
    if modules is None:
        modules = 'numpy'
    _direct_known = {'cse', 'real', 'order', 'dtype', 'backend'}
    if modules == 'numpy' and all(k in _direct_known for k in kwargs):
        try:
            from nbsymengine.lambdify import lambdify as _direct_lambdify
            return _direct_lambdify(args, exprs, **kwargs)
        except Exception:
            pass
    # Fallback: original implementation
    if not HAS_SYMPY:
        _require_sympy("lambdify() fallback")
    from ._sympy_bridge import to_sympy
    import sympy
    if _is_matrix(args):
        raw_args = _unwrap_matrix(args)
        sp_args = [to_sympy(raw_args.get(i, 0)) for i in range(raw_args.nrows())]
    elif isinstance(args, (list, tuple)):
        sp_args = [to_sympy(a) for a in args]
    else:
        sp_args = [to_sympy(args)]
    if _is_matrix(exprs):
        raw_exprs = _unwrap_matrix(exprs)
        sp_exprs = sympy.Matrix(raw_exprs.tolist())
    elif isinstance(exprs, (list, tuple)):
        sp_exprs = [to_sympy(e) for e in exprs]
    else:
        sp_exprs = to_sympy(exprs)
    return sympy.lambdify(sp_args, sp_exprs, modules=modules, **kwargs)
