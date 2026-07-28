"""nbsymengine.lambdify -- Direct Lambdify API for nbsymengine.

Provides ``Lambdify``, ``LambdifyCSE``, and ``lambdify`` for converting
nbsymengine expressions into fast numeric callables.  Supports the
SymPy-based backend, the native ``lambda_double`` C++ evaluator,
and the LLVM-based JIT backend.
"""
from __future__ import annotations

from typing import Any, List, Optional, Tuple

from nbsymengine import _core

try:
    import numpy as np
except ImportError:  # pragma: no cover - NumPy is optional at import time
    np = None

have_llvm = getattr(_core, 'have_llvm', False)


# ---------------------------------------------------------------------------
# Helpers: to_sympy / from_sympy (local copies to avoid legacy shim import)
# ---------------------------------------------------------------------------

def _build_known_math_funcs():
    """Build the known-math-function dict (called once at import time)."""
    import sympy
    d = {
        'sin': sympy.sin, 'cos': sympy.cos, 'tan': sympy.tan,
        'asin': sympy.asin, 'acos': sympy.acos, 'atan': sympy.atan,
        'sinh': sympy.sinh, 'cosh': sympy.cosh, 'tanh': sympy.tanh,
        'log': sympy.log, 'sqrt': sympy.sqrt, 'exp': sympy.exp,
        'sign': sympy.sign, 'floor': sympy.floor, 'ceiling': sympy.ceiling,
        'abs': sympy.Abs, 'gamma': sympy.gamma,
        'erf': sympy.erf, 'erfc': sympy.erfc,
        'beta': sympy.beta, 'conjugate': sympy.conjugate,
        'loggamma': sympy.loggamma,
        'cot': sympy.cot, 'csc': sympy.csc, 'sec': sympy.sec,
        'acot': sympy.acot, 'acsc': sympy.acsc, 'asec': sympy.asec,
        'coth': sympy.coth, 'sech': sympy.sech, 'csch': sympy.csch,
        'asinh': sympy.asinh, 'acosh': sympy.acosh, 'atanh': sympy.atanh,
    }
    for name in ('atan2', 'lambertw', 'zeta', 'digamma', 'polygamma'):
        fn = getattr(sympy, name, None)
        if fn is not None:
            d[name] = fn
    return d


try:
    _KNOWN_MATH_FUNCS = _build_known_math_funcs()
except ImportError:
    _KNOWN_MATH_FUNCS = {}


def _to_sympy(expr):
    """Convert a ``_core.Basic`` expression to a SymPy expression."""
    import sympy
    from fractions import Fraction

    if not isinstance(expr, _core.Basic):
        return expr
    name = expr.__class__.__name__
    if name in ('Symbol', 'Dummy'):
        s = expr.name
        if s == 'Catalan':
            return sympy.Catalan
        elif s == 'GoldenRatio':
            return sympy.GoldenRatio
        return sympy.Symbol(s)
    elif name == 'Integer':
        return sympy.Integer(int(str(expr)))
    elif name == 'Rational':
        f = Fraction(str(expr))
        return sympy.Rational(f.numerator, f.denominator)
    elif name in ('RealDouble', 'RealMPFR'):
        return sympy.Float(float(str(expr)))
    elif name == 'Constant':
        s = str(expr)
        if s == 'pi':
            return sympy.pi
        elif s == 'E':
            return sympy.E
        elif s == 'EulerGamma':
            return sympy.EulerGamma
        elif s == 'I':
            return sympy.I
        return sympy.Symbol(s)
    elif name == 'Add':
        return sympy.Add(*(_to_sympy(a) for a in expr.get_args()))
    elif name == 'Mul':
        return sympy.Mul(*(_to_sympy(a) for a in expr.get_args()))
    elif name == 'Pow':
        args = expr.get_args()
        return sympy.Pow(_to_sympy(args[0]), _to_sympy(args[1]))
    elif name in ('Eq', 'Ne', 'Ge', 'Gt', 'Le', 'Lt'):
        args = expr.get_args()
        fn = getattr(sympy, name)
        return fn(_to_sympy(args[0]), _to_sympy(args[1]))
    elif name == 'FunctionSymbol':
        fn_name = expr.name
        args = [_to_sympy(a) for a in expr.get_args()]
        return sympy.Function(fn_name)(*args)
    elif name in ('_Derivative', 'Derivative'):
        args = expr.get_args()
        expr_sp = _to_sympy(args[0])
        variables = [_to_sympy(a) for a in args[1:]]
        return sympy.Derivative(expr_sp, *variables)
    else:
        core_fn = _KNOWN_MATH_FUNCS.get(name) or _KNOWN_MATH_FUNCS.get(name.lower())
        if core_fn is not None:
            return core_fn(*(_to_sympy(a) for a in expr.get_args()))
        raise NotImplementedError(
            f"lambdify cannot convert {name!r} to SymPy. "
            f"If this is a valid nbsymengine node, add it to _KNOWN_MATH_FUNCS."
        )


def _is_dense_matrix(obj: Any) -> bool:
    """Check if *obj* is a ``_core.DenseMatrix`` without importing legacy."""
    try:
        return isinstance(obj, _core.DenseMatrix)
    except (AttributeError, ImportError):
        return False


def _float_to_basic(val):
    """Convert a numeric value to ``_core.Basic`` for DenseMatrix.set()."""
    if isinstance(val, _core.Basic):
        return val
    return _core.real_double(float(val))


# ---------------------------------------------------------------------------
# Output layout recording / restoration
# ---------------------------------------------------------------------------

class _OutputLayout:
    """Records the structure of outputs so evaluation can restore it."""

    __slots__ = ('kind', 'shape', 'nested')

    def __init__(self, kind: str, shape: Optional[Tuple[int, ...]] = None,
                 nested: Optional[List['_OutputLayout']] = None):
        self.kind = kind  # 'scalar', 'vector', 'matrix', 'nested'
        self.shape = shape
        self.nested = nested

    def restore(self, flat_values, offset: int):
        """Restore structure from *flat_values* starting at *offset*.

        Returns ``(restored_value, new_offset)``.  Matrix outputs are
        returned as ``(nrows, ncols)`` NumPy arrays (matching the
        semantics of the legacy ``symengine.py`` Lambdify).
        """
        if self.kind == 'scalar':
            return flat_values[offset], offset + 1
        elif self.kind == 'vector':
            n = self.shape[0]
            return np.asarray(flat_values[offset:offset + n], dtype=np.float64), offset + n
        elif self.kind == 'matrix':
            rows, cols = self.shape
            n = rows * cols
            arr = np.asarray(flat_values[offset:offset + n], dtype=np.float64)
            return arr.reshape(rows, cols), offset + n
        elif self.kind == 'nested':
            parts = []
            off = offset
            for sub in self.nested:
                val, off = sub.restore(flat_values, off)
                parts.append(val)
            return tuple(parts), off
        else:
            raise ValueError(f"Unknown layout kind: {self.kind!r}")


def _record_output_layout(exprs) -> _OutputLayout:
    """Record the layout of the output expressions."""
    if len(exprs) == 1:
        return _record_single_layout(exprs[0])
    # Multiple expressions -> vector or nested
    has_matrix = False
    for e in exprs:
        if _is_dense_matrix(e):
            has_matrix = True
            break
    if has_matrix:
        # Nested: each element becomes its own layout
        nested = [_record_single_layout(e) for e in exprs]
        return _OutputLayout('nested', nested=nested)
    return _OutputLayout('vector', shape=(len(exprs),))


def _record_single_layout(expr) -> _OutputLayout:
    """Record layout for a single expression."""
    if _is_dense_matrix(expr):
        return _OutputLayout('matrix', shape=(expr.nrows(), expr.ncols()))
    return _OutputLayout('scalar')


def _layout_parts(layout: _OutputLayout) -> List[Tuple[int, int, Tuple[int, ...]]]:
    """Precompute ``(start, stop, shape)`` for every top-level output.

    ``shape`` is ``()`` for scalar outputs.  This mirrors the
    ``out_shapes``/``accum_out_sizes`` bookkeeping of legacy ``symengine.py``.
    """
    if layout.kind == 'nested':
        subs = layout.nested
    else:
        subs = [layout]
    parts = []
    offset = 0
    for sub in subs:
        if sub.kind == 'scalar':
            shape: Tuple[int, ...] = ()
            size = 1
        else:
            shape = tuple(sub.shape)
            size = 1
            for d in shape:
                size *= d
        parts.append((offset, offset + size, shape))
        offset += size
    return parts


def _flatten_exprs(exprs) -> List:
    """Flatten expressions into a list of scalar expressions."""
    flat = []
    for e in exprs:
        if _is_dense_matrix(e):
            for i in range(e.nrows()):
                for j in range(e.ncols()):
                    flat.append(e.get(i, j))
        else:
            flat.append(e)
    return flat


# ---------------------------------------------------------------------------
# Input normalization
# ---------------------------------------------------------------------------

def _normalize_args(args) -> List:
    """Normalize input arguments into a flat list of ``_core.Basic`` symbols.

    Accepted forms:
    - single symbol;
    - list/tuple of symbols;
    - ``DenseMatrix`` column vector;
    - NumPy object arrays containing symbols (when NumPy is installed).
    """
    if _is_dense_matrix(args):
        if args.ncols() != 1:
            raise TypeError(
                f"DenseMatrix argument must be a column vector (ncols=1), "
                f"got ncols={args.ncols()}."
            )
        result = []
        for i in range(args.nrows()):
            result.append(args.get(i, 0))
        return result

    if isinstance(args, (list, tuple)):
        # Check for nested structures -- reject unless it's a flat list
        for a in args:
            if isinstance(a, (list, tuple)):
                raise TypeError(
                    f"Ambiguous nested argument structure: {args!r}. "
                    "Expected a flat list/tuple of symbols, a single symbol, "
                    "or a DenseMatrix column vector."
                )
        return list(args)

    # Single symbol
    if isinstance(args, _core.Basic):
        return [args]

    # NumPy object array
    if np is not None and isinstance(args, np.ndarray):
        if args.dtype == object:
            return list(args.flat)
        raise TypeError(
            f"NumPy argument array has dtype {args.dtype!r}, expected object. "
            "Pass a list of symbols or a DenseMatrix."
        )

    raise TypeError(
        f"Cannot normalize arguments of type {type(args).__name__!r}. "
        "Expected a symbol, list/tuple of symbols, DenseMatrix, or "
        "NumPy object array."
    )


def _normalize_exprs(exprs) -> List:
    """Normalize output expressions into a flat list.

    Accepted forms:
    - scalar expression;
    - list/tuple of expressions;
    - ``DenseMatrix``;
    - nested tuple/list structures containing expressions and matrices;
    - NumPy object arrays (when NumPy is installed).
    """
    if isinstance(exprs, (list, tuple)):
        result = []
        for item in exprs:
            if isinstance(item, (list, tuple)):
                result.extend(_normalize_exprs(item))
            else:
                result.append(item)
        return result

    if _is_dense_matrix(exprs):
        return [exprs]

    if isinstance(exprs, _core.Basic):
        return [exprs]

    if np is not None and isinstance(exprs, np.ndarray) and exprs.dtype == object:
        return list(exprs.flat)

    raise TypeError(
        f"Cannot normalize expression of type {type(exprs).__name__!r}. "
        "Expected _core.Basic, DenseMatrix, or iterable thereof."
    )


# ---------------------------------------------------------------------------
# Lambdify
# ---------------------------------------------------------------------------

class Lambdify:
    """Direct ``nbsymengine.Lambdify`` -- numeric evaluation of symbolic expressions.

    Parameters
    ----------
    args : symbol, list/tuple of symbols, DenseMatrix, or NumPy object array
        The free variables.
    *exprs : expressions
        One or more symbolic expressions or DenseMatrix objects.
    backend : str
        ``"sympy"`` (default) for the SymPy-based backend.
        ``"lambda_double"`` for the native C++ evaluator.
        ``"llvm"`` for the LLVM JIT backend (real-valued only).
        ``"auto"`` resolves to ``"llvm"`` when LLVM is available and
        ``real=True``, otherwise ``"lambda_double"``.
    cse : bool
        If True, apply common subexpression elimination before lambdifying.
    dtype : type
        Output dtype. Default: ``float``.
    real : bool
        Assume real-valued inputs. Default: ``True``.
    order : str
        Array memory order. Default: ``"C"``.

    Notes
    -----
    Calling the object returns plain NumPy data (matching the semantics of
    legacy ``symengine.py``): a Python ``float`` for a single scalar
    expression, a 1-D ``float64`` array for a list of scalar expressions, an
    ``(nrows, ncols)`` array for a ``DenseMatrix`` output, and a tuple of
    such objects for heterogeneous outputs.  No ``DenseMatrix`` (and no
    per-element ``Basic``) is ever constructed during evaluation.

    The native backends (``lambda_double``/``llvm``) also accept a batched
    ``(m, n_args)`` C-order input array, in which case every output gains a
    leading ``m`` dimension.
    """

    def __init__(self, args, *exprs, backend='sympy', cse=False,
                 real=True, order='C', dtype=float, **kwargs):
        if backend not in ('sympy', 'lambda_double', 'llvm', 'auto'):
            raise ValueError(
                f"Unknown backend {backend!r}. Use 'sympy', 'lambda_double', 'llvm', or 'auto'."
            )

        self._backend = backend

        # Resolve 'auto' backend
        if self._backend == 'auto':
            self._backend = 'llvm' if (have_llvm and real) else 'lambda_double'

        self._cse = cse
        self._real = real
        self._order = order
        self._dtype = dtype
        self._native = None

        # Normalize args
        self._raw_args = args
        self._args = _normalize_args(args)

        # Normalize exprs
        if not exprs:
            raise ValueError("At least one expression is required.")
        raw_exprs = list(exprs)
        self._exprs_list = _normalize_exprs(raw_exprs[0]) if len(raw_exprs) == 1 else raw_exprs

        # Record output layout
        self._layout = _record_output_layout(self._exprs_list)

        # Native lambda_double backend
        if self._backend == 'lambda_double':
            flat_exprs = _flatten_exprs(self._exprs_list)
            self._native = _core._LambdaRealDouble(
                self._args, flat_exprs, cse=cse
            )
            self._n_flat = self._native.n_outputs()
            self._setup_dispatch()
            return  # Skip SymPy path entirely

        # Native LLVM JIT backend
        if self._backend == 'llvm':
            if not have_llvm:
                raise ValueError(
                    "LLVM backend requested but nbsymengine was built without LLVM support."
                )
            if not self._real:
                raise ValueError("LLVM backend only supports real-valued expressions.")
            flat_exprs = _flatten_exprs(self._exprs_list)
            opt_level = kwargs.get('opt_level', 3)
            self._native = _core._LLVMDouble(
                self._args, flat_exprs, cse=cse, opt_level=opt_level
            )
            self._n_flat = self._native.n_outputs()
            self._setup_dispatch()
            return

        # Convert to SymPy
        import sympy
        sp_args = [_to_sympy(a) for a in self._args]
        sp_exprs = []
        has_matrix_expr = False
        for expr in self._exprs_list:
            if _is_dense_matrix(expr):
                import sympy as sp
                has_matrix_expr = True
                rows, cols = expr.nrows(), expr.ncols()
                flat = [expr.get(i, j) for i in range(rows) for j in range(cols)]
                sp_flat = [_to_sympy(e) for e in flat]
                sp_exprs.append(sp.Matrix(rows, cols, sp_flat))
            else:
                sp_exprs.append(_to_sympy(expr))

        # Determine if we have a single expression or multiple
        self._single = len(sp_exprs) == 1 and not isinstance(sp_exprs[0], sympy.Matrix)

        # When there are multiple expressions and at least one is a matrix,
        # build separate lambdify functions to avoid inhomogeneous array issues
        self._multi_matrix = len(sp_exprs) > 1 and has_matrix_expr
        if self._multi_matrix:
            self._per_expr_funcs = []
            for sp_e in sp_exprs:
                if cse:
                    self._per_expr_funcs.append(
                        sympy.lambdify(sp_args, sp_e, modules='numpy', cse=True, **kwargs)
                    )
                else:
                    self._per_expr_funcs.append(
                        sympy.lambdify(sp_args, sp_e, modules='numpy', **kwargs)
                    )
        else:
            # Build a single SymPy lambdify function
            if cse:
                if self._single:
                    self._func = sympy.lambdify(
                        sp_args, sp_exprs[0], modules='numpy', cse=True, **kwargs
                    )
                else:
                    self._func = sympy.lambdify(
                        sp_args, sp_exprs, modules='numpy', cse=True, **kwargs
                    )
            else:
                if self._single:
                    self._func = sympy.lambdify(
                        sp_args, sp_exprs[0], modules='numpy', **kwargs
                    )
                else:
                    self._func = sympy.lambdify(
                        sp_args, sp_exprs, modules='numpy', **kwargs
                    )

        # Cache flat count for out= validation
        flat_exprs = _flatten_exprs(self._exprs_list)
        self._n_flat = len(flat_exprs)
        self._setup_dispatch()

    # -- fast-path setup ----------------------------------------------------

    def _setup_dispatch(self):
        """Precompute output bookkeeping and bind a per-instance fast call."""
        self._parts = _layout_parts(self._layout)
        self._out_shapes = [shape for _, _, shape in self._parts]
        self._accum_out_sizes = [start for start, _, _ in self._parts]
        self._accum_out_sizes.append(self._n_flat)
        self._fast = self._build_fast_call() if self._native is not None else None

    def _build_fast_call(self):
        """Build the closure used for ``f(inp)`` on the native backends.

        The closure keeps no per-element Python objects: the input is coerced
        once with ``np.ascontiguousarray`` (a no-op for float64 C-contiguous
        arrays) and the flat output buffer is filled in C++.
        """
        call_into = self._native.call_into
        n_flat = self._n_flat
        kind = self._layout.kind
        empty = np.empty
        ascontiguousarray = np.ascontiguousarray
        f64 = np.float64
        general = self._call_general

        if kind == 'vector':
            def fast(inp):
                try:
                    arr = ascontiguousarray(inp, dtype=f64)
                except TypeError:  # e.g. a generator -- use the slow path
                    return general((inp,), None)
                if arr.ndim != 1:
                    return general((inp,), None)
                buf = empty(n_flat, dtype=f64)
                call_into(arr, buf)
                return buf
        elif kind == 'scalar':
            def fast(inp):
                try:
                    arr = ascontiguousarray(inp, dtype=f64)
                except TypeError:  # e.g. a generator -- use the slow path
                    return general((inp,), None)
                if arr.ndim != 1:
                    return general((inp,), None)
                buf = empty(1, dtype=f64)
                call_into(arr, buf)
                return float(buf[0])
        else:  # 'matrix' / 'nested'
            restore = self._restore_flat

            def fast(inp):
                try:
                    arr = ascontiguousarray(inp, dtype=f64)
                except TypeError:  # e.g. a generator -- use the slow path
                    return general((inp,), None)
                if arr.ndim != 1:
                    return general((inp,), None)
                buf = empty(n_flat, dtype=f64)
                call_into(arr, buf)
                return restore(buf)
        return fast

    # -- output restoration (views into one flat buffer, no copies) ---------

    def _restore_flat(self, buf):
        """Reshape a flat ``(n_flat,)`` result buffer to the output layout."""
        kind = self._layout.kind
        if kind == 'vector':
            return buf
        if kind == 'scalar':
            return float(buf[0])
        if kind == 'matrix':
            return buf.reshape(self._layout.shape)
        return tuple(
            float(buf[start]) if not shape else buf[start:stop].reshape(shape)
            for start, stop, shape in self._parts
        )

    def _restore_batched(self, buf, m: int):
        """Reshape an ``(m, n_flat)`` result buffer to the output layout."""
        kind = self._layout.kind
        if kind == 'vector':
            return buf
        if kind == 'scalar':
            return buf.reshape(m)
        if kind == 'matrix':
            return buf.reshape((m,) + tuple(self._layout.shape))
        return tuple(
            buf[:, start:stop].reshape((m,) + shape)
            for start, stop, shape in self._parts
        )

    @property
    def n_args(self) -> int:
        return len(self._args)

    @property
    def n_exprs(self) -> int:
        return len(self._exprs_list)

    @property
    def n_flat(self) -> int:
        return self._n_flat

    def __call__(self, *args, out=None):
        """Evaluate the lambdified function.

        Accepted call signatures:
        - ``f([1.0, 2.0, 3.0])``
        - ``f(np.array([...]))``
        - ``f(np.array([[...], [...]]))`` (batched, native backends)
        - ``f(1.0, 2.0, 3.0)`` (scalar varargs)

        Returns a Python ``float`` for scalar outputs and NumPy arrays
        (or a tuple of them for heterogeneous outputs) otherwise.
        """
        fast = self._fast
        if fast is not None and out is None and len(args) == 1:
            return fast(args[0])
        return self._call_general(args, out)

    def _coerce_input(self, args):
        """Coerce call arguments into a contiguous float64 ndarray."""
        inp = args[0] if len(args) == 1 else args
        try:
            arr = np.ascontiguousarray(inp, dtype=np.float64)
        except TypeError:
            arr = np.fromiter(inp, dtype=np.float64)
        if arr.ndim == 0:
            arr = arr.reshape(1)
        return arr

    def _call_general(self, args, out):
        if len(args) == 0:
            raise ValueError("At least one argument is required.")

        # Native lambda_double / llvm evaluation
        if self._native is not None:
            return self._call_native(self._coerce_input(args), out)

        if len(args) == 1:
            inp = args[0]
            if np is not None and isinstance(inp, np.ndarray):
                if inp.ndim > 1:
                    raise NotImplementedError(
                        "Batched 2-D input arrays are not supported by the "
                        "'sympy' backend.  Use backend='llvm' or "
                        "backend='lambda_double'."
                    )
                inp_list = list(inp)
            elif hasattr(inp, '__iter__'):
                inp_list = list(inp)
            else:
                inp_list = [inp]
        else:
            inp_list = list(args)

        # Evaluate
        if self._multi_matrix:
            # Evaluate each expression separately
            per_results = []
            for func in self._per_expr_funcs:
                r = func(*inp_list)
                per_results.append(np.atleast_1d(np.asarray(r, dtype=float)))
            flat_values = list(np.concatenate([r.flat for r in per_results]))
        elif self._single:
            result = np.atleast_1d(self._func(*inp_list))
            flat_values = list(result.flat)
        else:
            result = np.array(self._func(*inp_list))
            flat_values = list(result.flat)

        # Restore output layout
        restored, _ = self._layout.restore(flat_values, 0)

        # Handle out=
        if out is not None:
            if self._layout.kind in ('scalar', 'vector'):
                out_arr = np.asarray(out)
                if out_arr.ndim == 1 and out_arr.size == self._n_flat:
                    np.copyto(out_arr, np.asarray(restored).flat[:out_arr.size].reshape(out_arr.shape))
                    return out
                else:
                    raise ValueError(
                        f"out= array shape {out_arr.shape} is incompatible "
                        f"with output flat size {self._n_flat}."
                    )
            else:
                raise NotImplementedError(
                    "out= is only supported for flat numeric outputs. "
                    f"Output layout is {self._layout.kind!r}."
                )

        return restored

    def _call_native(self, arr, out):
        """Evaluate a native backend from a contiguous float64 input array.

        ``arr`` is either ``(n_args,)`` or ``(m, n_args)`` (C order); in the
        latter case every output gains a leading ``m`` dimension.
        """
        nd = arr.ndim
        if nd == 1:
            m = 1
            batched = False
        elif nd == 2:
            m = arr.shape[0]
            batched = True
        else:
            raise NotImplementedError(
                "Only 1-D and 2-D (C order) input arrays are supported, "
                f"got ndim={nd}."
            )
        n_flat = self._n_flat

        if out is None:
            buf = np.empty((m, n_flat) if batched else n_flat, dtype=np.float64)
            self._native.call_into(arr, buf)
            if batched:
                return self._restore_batched(buf, m)
            return self._restore_flat(buf)

        if np is None or not isinstance(out, np.ndarray):
            raise TypeError("out= must be a NumPy ndarray.")
        if out.size != m * n_flat:
            raise ValueError(
                f"out= array shape {out.shape} is incompatible "
                f"with output flat size {m * n_flat}."
            )
        if out.dtype != np.float64:
            raise ValueError(
                f"out= array must have dtype float64, got {out.dtype!r}."
            )
        if not out.flags['C_CONTIGUOUS']:
            raise NotImplementedError("out= array must be C-contiguous.")
        if not out.flags['WRITEABLE']:
            raise ValueError("out= array must be writeable.")
        self._native.call_into(arr, out.reshape(-1))
        return out

    def unsafe_real(self, inp, out):
        """Evaluate with real input/output arrays (no type checks)."""
        if self._native is not None:
            inp_arr = np.ascontiguousarray(inp, dtype=np.float64).reshape(-1)
            out_arr = np.ascontiguousarray(out, dtype=np.float64).reshape(-1)
            if hasattr(self._native, 'call_ptr'):
                self._native.call_ptr(
                    inp_arr.ctypes.data, out_arr.ctypes.data)
            else:
                self._native.call(inp_arr, out_arr)
            if out_arr is not out:
                np.copyto(out, out_arr)
            return
        if self._multi_matrix:
            per_results = []
            for func in self._per_expr_funcs:
                r = func(*inp)
                per_results.append(np.atleast_1d(np.asarray(r, dtype=np.float64)))
            flat = np.concatenate([r.flat for r in per_results])
        else:
            result = self._func(*inp)
            if isinstance(result, (list, tuple)):
                result = np.array(result)
            flat = np.atleast_1d(np.asarray(result, dtype=np.float64)).flat
        np.copyto(out, np.asarray(list(flat)[:out.size]).reshape(out.shape))

    def unsafe_complex(self, inp, out):
        """Evaluate with complex input/output arrays (no type checks).

        Raises
        ------
        NotImplementedError
            If the ``lambda_double`` backend is active, since the native
            C++ evaluator only supports real-valued evaluation.
        """
        if self._native is not None:
            raise NotImplementedError(
                f"The {self._backend!r} backend does not support complex "
                "evaluation. Use backend='sympy' for complex inputs."
            )
        if self._multi_matrix:
            per_results = []
            for func in self._per_expr_funcs:
                r = func(*inp)
                per_results.append(np.atleast_1d(np.asarray(r, dtype=np.complex128)))
            flat = np.concatenate([r.flat for r in per_results])
        else:
            result = self._func(*inp)
            if isinstance(result, (list, tuple)):
                result = np.array(result)
            flat = np.atleast_1d(np.asarray(result, dtype=np.complex128)).flat
        np.copyto(out, np.asarray(list(flat)[:out.size]).reshape(out.shape))


# ---------------------------------------------------------------------------
# LambdifyCSE
# ---------------------------------------------------------------------------

class LambdifyCSE:
    """Thin wrapper for ``Lambdify(..., cse=True)``."""

    def __init__(self, args, *exprs, **kwargs):
        kwargs.setdefault('cse', True)
        self._inner = Lambdify(args, *exprs, **kwargs)

    def __call__(self, *args, out=None):
        return self._inner(*args, out=out)

    @property
    def n_args(self) -> int:
        return self._inner.n_args

    @property
    def n_exprs(self) -> int:
        return self._inner.n_exprs

    @property
    def n_flat(self) -> int:
        return self._inner.n_flat

    def unsafe_real(self, inp, out):
        return self._inner.unsafe_real(inp, out)

    def unsafe_complex(self, inp, out):
        return self._inner.unsafe_complex(inp, out)


# ---------------------------------------------------------------------------
# Module-level lambdify function
# ---------------------------------------------------------------------------

def lambdify(args, exprs, backend='sympy', cse=False, real=True, order='C',
             dtype=float, **kwargs):
    """Create a lambdified callable from nbsymengine expressions.

    This is a convenience wrapper around ``Lambdify``.

    Parameters
    ----------
    args : symbol, list/tuple of symbols, DenseMatrix, or NumPy object array
        The free variables.
    exprs : expression, list/tuple of expressions, DenseMatrix, or NumPy object array
        The output expressions.
    backend : str
        ``"sympy"`` (default), ``"lambda_double"`` for the native C++ evaluator,
        ``"llvm"`` for the LLVM JIT backend (real-valued only),
        or ``"auto"`` (resolves to ``"llvm"`` when available and ``real=True``).
    cse : bool
        Apply common subexpression elimination.
    real : bool
        Assume real-valued inputs.
    order : str
        Array memory order.
    dtype : type
        Output dtype.

    Returns
    -------
    Lambdify
        A callable that evaluates the expressions numerically.
    """
    return Lambdify(
        args, exprs, backend=backend, cse=cse, real=real, order=order,
        dtype=dtype, **kwargs
    )
