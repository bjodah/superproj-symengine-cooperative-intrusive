"""nbsymengine_compat._lambdify -- The compat Lambdify class."""
from __future__ import annotations

from nbsymengine import _core
from ._helpers import _sympify, HAS_SYMPY, _require_sympy


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


class Lambdify:
    """Legacy Lambdify class wrapping SymPy's lambdify for numeric evaluation.

    Delegates to the direct ``nbsymengine.lambdify.Lambdify`` when semantics
    match (backend='lambda'/'sympy', no opt_level, no as_scipy).  Falls back
    to the original implementation for legacy-only features.
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

        # Determine if we can delegate to the direct implementation
        _direct_backend = backend in ('lambda', 'sympy', 'llvm')
        _use_direct = _direct_backend and not as_scipy and not kwargs

        if _use_direct:
            try:
                from nbsymengine.lambdify import Lambdify as _DirectLambdify
                if backend == 'lambda':
                    _be = 'lambda_double'
                elif backend == 'llvm':
                    _be = 'llvm'
                else:
                    _be = backend
                _direct_kwargs = dict(backend=_be, cse=cse, real=real, order=order, dtype=dtype or float)
                if opt_level is not None and backend == 'llvm':
                    _direct_kwargs['opt_level'] = opt_level
                if _is_matrix(args):
                    raw_args = _unwrap_matrix(args)
                elif isinstance(args, (list, tuple)):
                    raw_args = [_sympify(a) for a in args]
                else:
                    raw_args = _sympify(args)

                raw_exprs = []
                for e in exprs:
                    if _is_matrix(e):
                        raw_exprs.append(_unwrap_matrix(e))
                    else:
                        raw_exprs.append(_sympify(e))

                self._direct = _DirectLambdify(raw_args, *raw_exprs, **_direct_kwargs)
                if hasattr(self._direct, '_func'):
                    self._func = self._direct._func
                    self._single = self._direct._single
                self._args = self._direct._args
                self._exprs_list = self._direct._exprs_list
                self.n_exprs = self._direct.n_exprs
                self.real = real
                self.order = order
                self._raw_args = args
                return
            except Exception:
                pass  # Fall back to original implementation

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

    def __call__(self, *args, out=None, **kwargs):
        # Delegate to direct implementation when available
        if self._direct is not None:
            return self._direct(*args, out=out)
        import numpy as np
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
        import numpy as np
        result = self._func(*inp)
        if isinstance(result, (list, tuple)):
            result = np.array(result)
        result = np.atleast_1d(np.asarray(result, dtype=np.float64))
        np.copyto(out, result.flat[:out.size].reshape(out.shape))

    def unsafe_complex(self, inp, out):
        """Evaluate with complex input/output arrays (no type checks)."""
        if self._direct is not None:
            return self._direct.unsafe_complex(inp, out)
        import numpy as np
        result = self._func(*inp)
        if isinstance(result, (list, tuple)):
            result = np.array(result)
        result = np.atleast_1d(np.asarray(result, dtype=np.complex128))
        np.copyto(out, result.flat[:out.size].reshape(out.shape))

    def as_ctypes(self):
        """Return (function_pointer, user_data) for ctypes interop."""
        import ctypes
        import numpy as np
        nargs = len(self._args)
        nout = self.n_exprs

        def _c_func(out_p, inp_p, user_data):
            inp = np.ctypeslib.as_array(inp_p, shape=(nargs,))
            out = np.ctypeslib.as_array(out_p, shape=(nout,))
            result = self(inp)
            np.copyto(out, result.flat[:nout])

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
