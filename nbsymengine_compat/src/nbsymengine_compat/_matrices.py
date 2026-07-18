"""nbsymengine_compat._matrices -- DenseMatrix / ImmutableMatrix support.

All matrix classes are delegation wrappers around raw ``_core.DenseMatrix`` objects.
No monkey-patching of ``_core.DenseMatrix`` is performed.
"""
from __future__ import annotations

from nbsymengine import _core
from ._helpers import _sympify, _missing, nb_isinstance_DenseMatrix, HAS_SYMPY


class DenseMatrixWrapper:
    """Delegation wrapper around a ``_core.DenseMatrix`` C++ object.

    Instance attribute ``_raw`` holds the raw C++ matrix.
    """

    def __init__(self, *args, **kwargs):
        if not hasattr(self, '_raw'):
            self._raw = self._create_raw(*args, **kwargs)

    @staticmethod
    def _create_raw(*args, **kwargs):
        from ._wrappers import unwrap
        if len(args) == 3 and not kwargs:
            rows, cols, values = args
            new_values = [unwrap(_sympify(v)) for v in values]
            return _core.DenseMatrix(rows, cols, new_values)
        elif len(args) == 1 and not kwargs:
            arg = args[0]
            if HAS_SYMPY:
                import sympy
                if isinstance(arg, sympy.MatrixBase):
                    from ._sympy_bridge import from_sympy
                    se_matrix = from_sympy(arg)
                    flat = [se_matrix.get(i, j) for i in range(se_matrix.nrows())
                            for j in range(se_matrix.ncols())]
                    return _core.DenseMatrix(se_matrix.nrows(), se_matrix.ncols(), flat)
            if isinstance(arg, DenseMatrixWrapper):
                flat = [unwrap(arg.get(i, j)) for i in range(arg.nrows()) for j in range(arg.ncols())]
                return _core.DenseMatrix(arg.nrows(), arg.ncols(), flat)
            if isinstance(arg, _core.DenseMatrix):
                flat = [arg.get(i, j) for i in range(arg.nrows()) for j in range(arg.ncols())]
                return _core.DenseMatrix(arg.nrows(), arg.ncols(), flat)
            if hasattr(arg, '__iter__') and not isinstance(arg, (str, bytes)):
                def _sympify_recursive(x):
                    if hasattr(x, '__iter__') and not isinstance(x, (str, bytes, _core.Basic, _core.DenseMatrix)):
                        return [_sympify_recursive(v) for v in x]
                    return unwrap(_sympify(x))
                new_arg = _sympify_recursive(arg)
                return _core.DenseMatrix(new_arg)
            return _core.DenseMatrix(unwrap(arg))
        unwrapped_args = [unwrap(a) for a in args]
        unwrapped_kwargs = {k: unwrap(v) for k, v in kwargs.items()}
        return _core.DenseMatrix(*unwrapped_args, **unwrapped_kwargs)

    # -- delegation for native methods ---------------------------------------
    def nrows(self):
        return self._raw.nrows()

    def ncols(self):
        return self._raw.ncols()

    def __getattr__(self, name):
        if name == '_raw':
            raise AttributeError(name)
        try:
            raw = object.__getattribute__(self, '_raw')
        except AttributeError:
            raise AttributeError(name)
        if hasattr(raw, name):
            attr = getattr(raw, name)
            if callable(attr):
                def wrapper_method(*args, **kwargs):
                    from ._wrappers import _wrap_nested, unwrap, wrap
                    unwrapped_args = [unwrap(a) for a in args]
                    unwrapped_kwargs = {k: unwrap(v) for k, v in kwargs.items()}
                    res = attr(*unwrapped_args, **unwrapped_kwargs)
                    return _wrap_nested(res)
                return wrapper_method
            else:
                from ._wrappers import wrap
                return wrap(attr)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    @property
    def shape(self):
        return (self.nrows(), self.ncols())


    def get(self, i, j):
        from ._wrappers import wrap
        return wrap(self._raw.get(i, j))

    def set(self, i, j, value):
        from ._wrappers import unwrap
        return self._raw.set(i, j, unwrap(value))

    def det(self):
        from ._wrappers import wrap
        return wrap(self._raw.det())

    def __eq__(self, other):
        if hasattr(other, '_raw'):
            return self._raw == other._raw
        if isinstance(other, _core.DenseMatrix):
            return self._raw == other
        return False

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self._raw)

    def __repr__(self):
        return repr(self._raw)

    def __str__(self):
        return str(self._raw)

    # -- custom Python methods (formerly patched onto _core.DenseMatrix) -----

    def tolist(self):
        result = []
        for i in range(self.nrows()):
            row = []
            for j in range(self.ncols()):
                row.append(self.get(i, j))
            result.append(row)
        return result

    def reshape(self, new_rows, new_cols):
        if new_rows * new_cols != self.nrows() * self.ncols():
            raise ValueError("reshape: total size must remain the same")
        flat = []
        for i in range(self.nrows()):
            for j in range(self.ncols()):
                flat.append(self.get(i, j))
        return DenseMatrixWrapper(new_rows, new_cols, flat)

    def __getitem__(self, key):
        if isinstance(key, int):
            total = self.nrows() * self.ncols()
            idx = key
            if idx < 0:
                idx += total
            if idx < 0 or idx >= total:
                raise IndexError("matrix index out of range")
            r, c = divmod(idx, self.ncols())
            return self.get(r, c)
        if isinstance(key, tuple):
            r, c = key
            if isinstance(r, int) and isinstance(c, int):
                ri, ci = r, c
                if ri < 0: ri += self.nrows()
                if ci < 0: ci += self.ncols()
                if ri < 0 or ri >= self.nrows() or ci < 0 or ci >= self.ncols():
                    raise IndexError("matrix index out of range")
                return self.get(ri, ci)
            if isinstance(r, int):
                ri = r
                if ri < 0: ri += self.nrows()
                if ri < 0 or ri >= self.nrows():
                    raise IndexError("row index out of range")
                if isinstance(c, slice):
                    cols = range(*c.indices(self.ncols()))
                    vals = [self.get(ri, j) for j in cols]
                    return DenseMatrixWrapper(1, len(cols), vals)
            if isinstance(c, int):
                ci = c
                if ci < 0: ci += self.ncols()
                if ci < 0 or ci >= self.ncols():
                    raise IndexError("column index out of range")
                if isinstance(r, slice):
                    rows = range(*r.indices(self.nrows()))
                    vals = [self.get(i, ci) for i in rows]
                    return DenseMatrixWrapper(len(rows), 1, vals)
            if isinstance(r, slice) and isinstance(c, slice):
                rows = range(*r.indices(self.nrows()))
                cols = range(*c.indices(self.ncols()))
                vals = []
                for i in rows:
                    for j in cols:
                        vals.append(self.get(i, j))
                return DenseMatrixWrapper(len(rows), len(cols), vals)
            if isinstance(r, (list, tuple)):
                if isinstance(c, (list, tuple)):
                    vals = []
                    for ri in r:
                        for ci in c:
                            vals.append(self.get(ri, ci))
                    return DenseMatrixWrapper(len(r), len(c), vals)
                if isinstance(c, int):
                    ci = c
                    if ci < 0: ci += self.ncols()
                    vals = [self.get(ri, ci) for ri in r]
                    return DenseMatrixWrapper(len(r), 1, vals)
                if isinstance(c, slice):
                    cols = range(*c.indices(self.ncols()))
                    vals = []
                    for ri in r:
                        for j in cols:
                            vals.append(self.get(ri, j))
                    return DenseMatrixWrapper(len(r), len(cols), vals)
            if isinstance(c, (list, tuple)):
                if isinstance(r, int):
                    ri = r
                    if ri < 0: ri += self.nrows()
                    vals = [self.get(ri, ci) for ci in c]
                    return DenseMatrixWrapper(1, len(c), vals)
                if isinstance(r, slice):
                    rows = range(*r.indices(self.nrows()))
                    vals = []
                    for i in rows:
                        for ci in c:
                            vals.append(self.get(i, ci))
                    return DenseMatrixWrapper(len(rows), len(c), vals)
        if isinstance(key, slice):
            total = self.nrows() * self.ncols()
            indices = range(*key.indices(total))
            return [self.get(*divmod(idx, self.ncols())) for idx in indices]
        raise IndexError("invalid matrix index")

    def __setitem__(self, key, value):
        if isinstance(key, int):
            total = self.nrows() * self.ncols()
            idx = key
            if idx < 0:
                idx += total
            if idx < 0 or idx >= total:
                raise IndexError("matrix index out of range")
            r, c = divmod(idx, self.ncols())
            if isinstance(value, (int, float)):
                value = _sympify(value)
            self.set(r, c, value)
            return
        if isinstance(key, tuple):
            r, c = key
            if isinstance(r, int) and isinstance(c, int):
                ri, ci = r, c
                if ri < 0: ri += self.nrows()
                if ci < 0: ci += self.ncols()
                if ri < 0 or ri >= self.nrows() or ci < 0 or ci >= self.ncols():
                    raise IndexError("matrix index out of range")
                if isinstance(value, (int, float)):
                    value = _sympify(value)
                self.set(ri, ci, value)
                return
            if isinstance(r, int) and isinstance(c, slice):
                ri = r
                if ri < 0: ri += self.nrows()
                cols = list(range(*c.indices(self.ncols())))
                if isinstance(value, (list, tuple)):
                    for j, ci in enumerate(cols):
                        v = value[j]
                        if isinstance(v, (int, float)):
                            v = _sympify(v)
                        self.set(ri, ci, v)
                elif nb_isinstance_DenseMatrix(value):
                    for j, ci in enumerate(cols):
                        v = value.get(0, j) if value.nrows() == 1 else value.get(j, 0)
                        self.set(ri, ci, v)
                return
            if isinstance(r, slice) and isinstance(c, int):
                ci = c
                if ci < 0: ci += self.ncols()
                rows = list(range(*r.indices(self.nrows())))
                if isinstance(value, (list, tuple)):
                    for i, ri in enumerate(rows):
                        v = value[i]
                        if isinstance(v, (int, float)):
                            v = _sympify(v)
                        self.set(ri, ci, v)
                elif nb_isinstance_DenseMatrix(value):
                    for i, ri in enumerate(rows):
                        v = value.get(i, 0) if value.ncols() == 1 else value.get(0, i)
                        self.set(ri, ci, v)
                return
            if isinstance(r, slice) and isinstance(c, slice):
                rows = list(range(*r.indices(self.nrows())))
                cols = list(range(*c.indices(self.ncols())))
                if isinstance(value, (list, tuple)):
                    for i, ri in enumerate(rows):
                        row_vals = value[i]
                        for j, ci in enumerate(cols):
                            v = row_vals[j]
                            if isinstance(v, (int, float)):
                                v = _sympify(v)
                            self.set(ri, ci, v)
                return
            if isinstance(r, (list, tuple)) and isinstance(c, int):
                ci = c
                if ci < 0: ci += self.ncols()
                if isinstance(value, (int, float)):
                    value = _sympify(value)
                    for ri in r:
                        self.set(ri, ci, value)
                elif isinstance(value, (list, tuple)):
                    for i, ri in enumerate(r):
                        v = value[i]
                        if isinstance(v, (list, tuple)):
                            v = v[0]
                        if isinstance(v, (int, float)):
                            v = _sympify(v)
                        self.set(ri, ci, v)
                elif nb_isinstance_DenseMatrix(value):
                    for i, ri in enumerate(r):
                        v = value.get(i, 0)
                        self.set(ri, ci, v)
                return
            if isinstance(r, (list, tuple)) and isinstance(c, (list, tuple)):
                if isinstance(value, (int, float)):
                    value = _sympify(value)
                    for ri in r:
                        for ci in c:
                            self.set(ri, ci, value)
                elif isinstance(value, (list, tuple)):
                    for i, ri in enumerate(r):
                        for j, ci in enumerate(c):
                            v = value[i]
                            if isinstance(v, (list, tuple)):
                                v = v[j]
                            if isinstance(v, (int, float)):
                                v = _sympify(v)
                            self.set(ri, ci, v)
                return
            if isinstance(r, int) and isinstance(c, (list, tuple)):
                ri = r
                if ri < 0: ri += self.nrows()
                if isinstance(value, (int, float)):
                    value = _sympify(value)
                    for ci in c:
                        self.set(ri, ci, value)
                elif isinstance(value, (list, tuple)):
                    for j, ci in enumerate(c):
                        v = value[j]
                        if isinstance(v, (int, float)):
                            v = _sympify(v)
                        self.set(ri, ci, v)
                return
            if isinstance(r, slice) and isinstance(c, (list, tuple)):
                rows = list(range(*r.indices(self.nrows())))
                if isinstance(value, (int, float)):
                    value = _sympify(value)
                    for ri in rows:
                        for ci in c:
                            self.set(ri, ci, value)
                elif isinstance(value, (list, tuple)):
                    for i, ri in enumerate(rows):
                        for j, ci in enumerate(c):
                            v = value[i]
                            if isinstance(v, (list, tuple)):
                                v = v[j]
                            if isinstance(v, (int, float)):
                                v = _sympify(v)
                            self.set(ri, ci, v)
                return
            raise NotImplementedError("Advanced matrix setitem not yet implemented")
        raise IndexError("invalid matrix index")

    def abs(self):
        from ._wrappers import unwrap
        result_raw = _core.DenseMatrix(self.nrows(), self.ncols())
        for i in range(self.nrows()):
            for j in range(self.ncols()):
                result_raw.set(i, j, _core.abs(unwrap(self.get(i, j))))
        return DenseMatrixWrapper._from_raw(result_raw)

    def diff(self, sym):
        from ._wrappers import unwrap
        sym_raw = unwrap(sym)
        result_raw = _core.DenseMatrix(self.nrows(), self.ncols())
        for i in range(self.nrows()):
            for j in range(self.ncols()):
                result_raw.set(i, j, _core.diff(unwrap(self.get(i, j)), sym_raw))
        return DenseMatrixWrapper._from_raw(result_raw)

    def col_swap(self, c1, c2):
        for i in range(self.nrows()):
            tmp = self.get(i, c1)
            self.set(i, c1, self.get(i, c2))
            self.set(i, c2, tmp)

    def row_swap(self, r1, r2):
        for j in range(self.ncols()):
            tmp = self.get(r1, j)
            self.set(r1, j, self.get(r2, j))
            self.set(r2, j, tmp)

    def fill(self, val):
        if isinstance(val, (int, float)):
            val = _sympify(val)
        for i in range(self.nrows()):
            for j in range(self.ncols()):
                self.set(i, j, val)

    def row(self, n):
        vals = [self.get(n, j) for j in range(self.ncols())]
        return DenseMatrixWrapper(1, self.ncols(), vals)

    def col(self, n):
        vals = [self.get(i, n) for i in range(self.nrows())]
        return DenseMatrixWrapper(self.nrows(), 1, vals)

    def rowadd(self, r1, r2, k):
        if isinstance(k, (int, float)):
            k = _sympify(k)
        for j in range(self.ncols()):
            self.set(r1, j, _sympify(self.get(r1, j)) + k * _sympify(self.get(r2, j)))
        return self

    def rowmul(self, r, k):
        if isinstance(k, (int, float)):
            k = _sympify(k)
        for j in range(self.ncols()):
            self.set(r, j, k * _sympify(self.get(r, j)))
        return self

    def dot(self, other):
        from ._wrappers import wrap
        if isinstance(other, DenseMatrixWrapper):
            other_raw = other._raw
        elif isinstance(other, _core.DenseMatrix):
            other_raw = other
        else:
            other_raw = DenseMatrixWrapper._create_raw(other)
        if self.nrows() == 1 and self.ncols() == 1:
            s = self.get(0, 0)
            if other_raw.nrows() == 1 and other_raw.ncols() == 1:
                return wrap(s * other_raw.get(0, 0))
        self_len = self.nrows() * self.ncols()
        other_len = other_raw.nrows() * other_raw.ncols()
        if self.nrows() == 1 and other_raw.ncols() == 1 and self.ncols() == other_raw.nrows():
            s = _sympify(0)
            for i in range(self.ncols()):
                s = s + _sympify(self.get(0, i)) * _sympify(other_raw.get(i, 0))
            return wrap(s)
        if self.ncols() == 1 and other_raw.ncols() == 1 and self.nrows() == other_raw.nrows():
            s = _sympify(0)
            for i in range(self.nrows()):
                s = s + _sympify(self.get(i, 0)) * _sympify(other_raw.get(i, 0))
            return wrap(s)
        if self.nrows() == 1 and other_raw.nrows() == 1 and self.ncols() == other_raw.ncols():
            s = _sympify(0)
            for i in range(self.ncols()):
                s = s + _sympify(self.get(0, i)) * _sympify(other_raw.get(0, i))
            return wrap(s)
        if self.ncols() == 1 and other_raw.nrows() == 1 and self.nrows() == other_raw.ncols():
            s = _sympify(0)
            for i in range(self.nrows()):
                s = s + _sympify(self.get(i, 0)) * _sympify(other_raw.get(0, i))
            return wrap(s)
        if self.nrows() != other_raw.nrows():
            raise _core.ShapeError("Matrix dimensions mismatch for dot product")
        n = self.nrows()
        result_nrows = self.ncols()
        result_ncols = other_raw.ncols()
        vals = []
        for k in range(result_nrows):
            for j in range(result_ncols):
                s = _sympify(0)
                for i in range(n):
                    s = s + _sympify(self.get(i, k)) * _sympify(other_raw.get(i, j))
                vals.append(s)
        if result_ncols == 1 and result_nrows == 1:
            return wrap(vals[0])
        if result_ncols == 1:
            return DenseMatrixWrapper(1, result_nrows, vals)
        return DenseMatrixWrapper(result_nrows, result_ncols, vals)

    def cross(self, other):
        if isinstance(other, DenseMatrixWrapper):
            other_raw = other._raw
        else:
            other_raw = other
        if self.ncols() != 3 or other_raw.ncols() != 3 or self.nrows() != 1 or other_raw.nrows() != 1:
            raise _core.ShapeError("cross product requires 1x3 matrices")
        a = [self.get(0, i) for i in range(3)]
        b = [other_raw.get(0, i) for i in range(3)]
        vals = [
            _sympify(a[1]) * _sympify(b[2]) - _sympify(a[2]) * _sympify(b[1]),
            _sympify(a[2]) * _sympify(b[0]) - _sympify(a[0]) * _sympify(b[2]),
            _sympify(a[0]) * _sympify(b[1]) - _sympify(a[1]) * _sympify(b[0]),
        ]
        return DenseMatrixWrapper(1, 3, vals)

    def atoms(self, *types):
        s = set()
        for i in range(self.nrows()):
            for j in range(self.ncols()):
                elem = self.get(i, j)
                if types:
                    if isinstance(elem, types):
                        s.add(elem)
                else:
                    if isinstance(elem, _core.Basic):
                        s.add(elem)
        return s

    def __len__(self):
        return self.nrows() * self.ncols()

    def __iter__(self):
        for i in range(self.nrows()):
            for j in range(self.ncols()):
                yield self.get(i, j)

    # -- is_* matrix predicates ----------------------------------------------

    def _check_all_elements(self, pred):
        from ._wrappers import unwrap
        result = True
        for i in range(self.nrows()):
            for j in range(self.ncols()):
                v = unwrap(self.get(i, j))
                r = pred(v)
                if r is False:
                    return False
                if r is None:
                    result = None
        return result

    def _is_zero_pred(v):
        if isinstance(v, (_core.Integer, _core.Rational)):
            return v.is_zero()
        if isinstance(v, _core.Number):
            return None
        return None

    def _is_real_pred(v):
        if isinstance(v, (_core.Integer, _core.Rational)):
            return True
        if isinstance(v, _core.RealDouble):
            return True
        name = v.__class__.__name__
        if name in ('Symbol',):
            return None
        return None

    @property
    def is_zero_matrix(self):
        return self._check_all_elements(DenseMatrixWrapper._is_zero_pred)

    @property
    def is_real_matrix(self):
        return self._check_all_elements(DenseMatrixWrapper._is_real_pred)

    @property
    def is_diagonal(self):
        from ._wrappers import unwrap
        n = self.nrows()
        m = self.ncols()
        result = True
        for i in range(n):
            for j in range(m):
                if i != j:
                    v = unwrap(self.get(i, j))
                    if isinstance(v, _core.Integer):
                        if not v.is_zero():
                            return False
                    else:
                        result = None
        return result

    @property
    def is_symmetric(self):
        from ._wrappers import unwrap
        if self.nrows() != self.ncols():
            return False
        n = self.nrows()
        result = True
        for i in range(n):
            for j in range(i + 1, n):
                a = unwrap(self.get(i, j))
                b = unwrap(self.get(j, i))
                if isinstance(a, _core.Integer) and isinstance(b, _core.Integer):
                    if not (a == b):
                        return False
                else:
                    result = None
        return result

    @property
    def is_hermitian(self):
        from ._wrappers import unwrap
        if self.nrows() != self.ncols():
            return False
        n = self.nrows()
        result = True
        for i in range(n):
            for j in range(i, n):
                a = unwrap(self.get(i, j))
                b = _core.conjugate(unwrap(self.get(j, i)))
                if isinstance(a, _core.Integer) and isinstance(b, _core.Integer):
                    if not (a == b):
                        return False
                else:
                    result = None
        return result

    def _is_diag_dom_impl(self, strict=False):
        from ._wrappers import unwrap, wrap
        if self.nrows() != self.ncols():
            return False
        n = self.nrows()
        result = True
        for i in range(n):
            diag = self.get(i, i)
            diag_raw = unwrap(diag)
            if not isinstance(diag_raw, (_core.Integer, _core.Rational)):
                result = None
                continue
            off_sum = _sympify(0)
            all_numeric = True
            for j in range(n):
                if i != j:
                    v = self.get(i, j)
                    v_raw = unwrap(v)
                    if isinstance(v_raw, (_core.Integer, _core.Rational)):
                        off_sum = off_sum + _core.abs(v_raw)
                    else:
                        all_numeric = False
            if not all_numeric:
                result = None
                continue
            d = _core.abs(diag_raw)
            d_wrapped = wrap(d)
            off_sum_wrapped = wrap(off_sum)
            if strict:
                if not (d_wrapped > off_sum_wrapped):
                    return False
            else:
                if not (d_wrapped >= off_sum_wrapped):
                    return False
        return result

    @property
    def is_weakly_diagonally_dominant(self):
        return self._is_diag_dom_impl(strict=False)

    @property
    def is_strongly_diagonally_dominant(self):
        return self._is_diag_dom_impl(strict=True)

    @property
    def is_positive_definite(self):
        from ._wrappers import unwrap, wrap
        if self.nrows() != self.ncols():
            return False
        n = self.nrows()
        result = True
        for k in range(1, n + 1):
            minor = _core.DenseMatrix(k, k)
            for i in range(k):
                for j in range(k):
                    minor.set(i, j, unwrap(self.get(i, j)))
            d = minor.det()
            if isinstance(d, (_core.Integer, _core.Rational)):
                if not (wrap(d) > 0):
                    return False
            else:
                result = None
        return result

    @property
    def is_negative_definite(self):
        from ._wrappers import unwrap, wrap
        if self.nrows() != self.ncols():
            return False
        n = self.nrows()
        result = True
        for k in range(1, n + 1):
            minor = _core.DenseMatrix(k, k)
            for i in range(k):
                for j in range(k):
                    minor.set(i, j, unwrap(self.get(i, j)))
            d = minor.det()
            sign = (-1)**k
            if isinstance(d, (_core.Integer, _core.Rational)):
                if sign * wrap(d) <= 0:
                    return False
            else:
                result = None
        return result

    # -- matrix operations that return matrices ------------------------------

    def as_immutable(self):
        return ImmutableMatrix._from_raw(self._raw)

    def subs(self, *args):
        from ._wrappers import unwrap
        result_raw = _core.DenseMatrix(self.nrows(), self.ncols())
        if len(args) == 2:
            old, new = args
            for i in range(self.nrows()):
                for j in range(self.ncols()):
                    result_raw.set(i, j, _core.subs(unwrap(self.get(i, j)), {_sympify(old): _sympify(new)}))
        elif len(args) == 1 and isinstance(args[0], dict):
            d = {_sympify(k): _sympify(v) for k, v in args[0].items()}
            for i in range(self.nrows()):
                for j in range(self.ncols()):
                    result_raw.set(i, j, _core.subs(unwrap(self.get(i, j)), d))
        return DenseMatrixWrapper._from_raw(result_raw)

    def xreplace(self, *args):
        from ._wrappers import unwrap
        result_raw = _core.DenseMatrix(self.nrows(), self.ncols())
        if len(args) == 2:
            old, new = args
            mapping = {_sympify(old): _sympify(new)}
        elif len(args) == 1 and isinstance(args[0], dict):
            mapping = {_sympify(k): _sympify(v) for k, v in args[0].items()}
        else:
            return DenseMatrixWrapper._from_raw(result_raw)
        for i in range(self.nrows()):
            for j in range(self.ncols()):
                result_raw.set(i, j, _core.xreplace(unwrap(self.get(i, j)), mapping))
        return DenseMatrixWrapper._from_raw(result_raw)

    def simplify(self):
        return self

    def row_join(self, B):
        if isinstance(B, DenseMatrixWrapper):
            B_raw = B._raw
        else:
            B_raw = B
        self._raw.row_join(B_raw)
        return self

    def col_join(self, B):
        if isinstance(B, DenseMatrixWrapper):
            B_raw = B._raw
        else:
            B_raw = B
        self._raw.col_join(B_raw)
        return self

    def row_insert(self, pos, M):
        if isinstance(M, DenseMatrixWrapper):
            M_raw = M._raw
        else:
            M_raw = M
        if M_raw.ncols() != self.ncols():
            raise _core.ShapeError("Column dimensions don't match for row_insert")
        nrows = self.nrows()
        if pos < 0:
            pos += nrows
        if pos < 0:
            pos = 0
        if pos > nrows:
            pos = nrows
        new_rows = nrows + M_raw.nrows()
        new_cols = self.ncols()
        vals = []
        for i in range(nrows):
            if i == pos:
                for r in range(M_raw.nrows()):
                    for j in range(M_raw.ncols()):
                        vals.append(M_raw.get(r, j))
            for j in range(self.ncols()):
                vals.append(self.get(i, j))
        if pos >= nrows:
            for r in range(M_raw.nrows()):
                for j in range(M_raw.ncols()):
                    vals.append(M_raw.get(r, j))
        return DenseMatrixWrapper(new_rows, new_cols, vals)

    def col_insert(self, pos, M):
        if isinstance(M, DenseMatrixWrapper):
            M_raw = M._raw
        else:
            M_raw = M
        if M_raw.nrows() != self.nrows():
            raise _core.ShapeError("Row dimensions don't match for col_insert")
        ncols = self.ncols()
        if pos < 0:
            pos += ncols
        if pos < 0:
            pos = 0
        if pos > ncols:
            pos = ncols
        new_rows = self.nrows()
        new_cols = ncols + M_raw.ncols()
        vals = []
        for i in range(self.nrows()):
            for j in range(ncols):
                if j == pos:
                    for c in range(M_raw.ncols()):
                        vals.append(M_raw.get(i, c))
                vals.append(self.get(i, j))
            if pos >= ncols:
                for c in range(M_raw.ncols()):
                    vals.append(M_raw.get(i, c))
        return DenseMatrixWrapper(new_rows, new_cols, vals)

    def LUsolve(self, other):
        if isinstance(other, DenseMatrixWrapper):
            other_raw = other._raw
        else:
            other_raw = other
        result_raw = self._raw.LU_solve(other_raw)
        return DenseMatrixWrapper._from_raw(result_raw)

    def dump_real(self, out):
        from ._sympy_bridge import to_sympy
        nr = self.nrows()
        nc = self.ncols()
        if len(out) < nr * nc:
            raise ValueError("out parameter too short")
        for r in range(nr):
            for c in range(nc):
                out[r * nc + c] = float(to_sympy(self.get(r, c)))

    def dump_complex(self, out):
        from ._sympy_bridge import to_sympy
        nr = self.nrows()
        nc = self.ncols()
        if len(out) < nr * nc:
            raise ValueError("out parameter too short")
        for r in range(nr):
            for c in range(nc):
                out[r * nc + c] = complex(to_sympy(self.get(r, c)))

    def _sympy_(self):
        if not HAS_SYMPY:
            from ._helpers import _require_sympy
            _require_sympy("DenseMatrix._sympy_()")
        from ._sympy_bridge import to_sympy
        import sympy
        rows = self.nrows()
        cols = self.ncols()
        flat = []
        for i in range(rows):
            for j in range(cols):
                flat.append(to_sympy(self.get(i, j)))
        return sympy.Matrix(rows, cols, flat)

    def _repr_latex_(self):
        return str(self)

    # -- arithmetic ----------------------------------------------------------

    def __add__(self, other):
        if isinstance(other, DenseMatrixWrapper):
            other_raw = other._raw
        elif isinstance(other, _core.DenseMatrix):
            other_raw = other
        else:
            return NotImplemented
        result_raw = self._raw + other_raw
        return DenseMatrixWrapper._from_raw(result_raw)

    def __radd__(self, other):
        if isinstance(other, DenseMatrixWrapper):
            other_raw = other._raw
        elif isinstance(other, _core.DenseMatrix):
            other_raw = other
        else:
            return NotImplemented
        result_raw = other_raw + self._raw
        return DenseMatrixWrapper._from_raw(result_raw)

    def __sub__(self, other):
        if isinstance(other, DenseMatrixWrapper):
            other_raw = other._raw
        else:
            return NotImplemented
        result_raw = self._raw - other_raw
        return DenseMatrixWrapper._from_raw(result_raw)

    def __rsub__(self, other):
        if isinstance(other, DenseMatrixWrapper):
            other_raw = other._raw
        elif isinstance(other, _core.DenseMatrix):
            other_raw = other
        else:
            return NotImplemented
        result_raw = other_raw - self._raw
        return DenseMatrixWrapper._from_raw(result_raw)

    def __mul__(self, other):
        if isinstance(other, DenseMatrixWrapper):
            other_raw = other._raw
        elif isinstance(other, _core.DenseMatrix):
            other_raw = other
        elif isinstance(other, (int, float, _core.Basic)) or hasattr(other, '_raw'):
            if hasattr(other, '_raw'):
                other_raw = other._raw
            else:
                other_raw = _sympify(other)
            result_raw = self._raw.mul_scalar(other_raw)
            return DenseMatrixWrapper._from_raw(result_raw)
        else:
            return NotImplemented
        result_raw = self._raw.mul_matrix(other_raw)
        return DenseMatrixWrapper._from_raw(result_raw)

    def __rmul__(self, other):
        if isinstance(other, DenseMatrixWrapper):
            other_raw = other._raw
        elif isinstance(other, _core.DenseMatrix):
            other_raw = other
        elif isinstance(other, (int, float, _core.Basic)) or hasattr(other, '_raw'):
            if hasattr(other, '_raw'):
                other_raw = other._raw
            else:
                other_raw = _sympify(other)
            result_raw = self._raw.mul_scalar(other_raw)
            return DenseMatrixWrapper._from_raw(result_raw)
        else:
            return NotImplemented
        result_raw = other_raw.mul_matrix(self._raw)
        return DenseMatrixWrapper._from_raw(result_raw)

    def __truediv__(self, other):
        if isinstance(other, DenseMatrixWrapper):
            return self * other._raw.inv()
        if isinstance(other, _core.DenseMatrix):
            return self * other.inv()
        if isinstance(other, (int, float, _core.Basic)) or hasattr(other, '_raw'):
            if hasattr(other, '_raw'):
                other_raw = other._raw
            else:
                other_raw = _sympify(other)
            result_raw = self._raw.mul_scalar(_core.div(_core.one(), other_raw))
            return DenseMatrixWrapper._from_raw(result_raw)
        return NotImplemented

    def __matmul__(self, other):
        return self.__mul__(other)

    def __neg__(self):
        result_raw = -self._raw
        return DenseMatrixWrapper._from_raw(result_raw)

    def __pos__(self):
        return self

    def __abs__(self):
        return self.abs()

    # -- additional operations that return matrices --------------------------

    def transpose(self):
        result_raw = self._raw.transpose()
        return DenseMatrixWrapper._from_raw(result_raw)

    def conjugate(self):
        result_raw = self._raw.conjugate()
        return DenseMatrixWrapper._from_raw(result_raw)

    def conjugate_transpose(self):
        result_raw = self._raw.conjugate_transpose()
        return DenseMatrixWrapper._from_raw(result_raw)

    def inv(self, method=""):
        result_raw = self._raw.inv(method)
        return DenseMatrixWrapper._from_raw(result_raw)

    def add_matrix(self, other):
        if isinstance(other, DenseMatrixWrapper):
            other_raw = other._raw
        else:
            other_raw = other
        result_raw = self._raw.add_matrix(other_raw)
        return DenseMatrixWrapper._from_raw(result_raw)

    def mul_matrix(self, other):
        if isinstance(other, DenseMatrixWrapper):
            other_raw = other._raw
        else:
            other_raw = other
        result_raw = self._raw.mul_matrix(other_raw)
        return DenseMatrixWrapper._from_raw(result_raw)

    def mul_scalar(self, k):
        if hasattr(k, '_raw'):
            k_raw = k._raw
        else:
            k_raw = _sympify(k)
        result_raw = self._raw.mul_scalar(k_raw)
        return DenseMatrixWrapper._from_raw(result_raw)

    def add_scalar(self, k):
        if hasattr(k, '_raw'):
            k_raw = k._raw
        else:
            k_raw = _sympify(k)
        result_raw = self._raw.add_scalar(k_raw)
        return DenseMatrixWrapper._from_raw(result_raw)

    def solve(self, b, method='LU'):
        if isinstance(b, DenseMatrixWrapper):
            b_raw = b._raw
        else:
            b_raw = b
        result_raw = self._raw.solve(b_raw, method)
        return DenseMatrixWrapper._from_raw(result_raw)

    def LU_solve(self, other):
        if isinstance(other, DenseMatrixWrapper):
            other_raw = other._raw
        else:
            other_raw = other
        result_raw = self._raw.LU_solve(other_raw)
        return DenseMatrixWrapper._from_raw(result_raw)

    # -- pickling ------------------------------------------------------------

    def __reduce__(self):
        from ._pickling import _unpickle_dense_matrix
        flat = []
        for i in range(self.nrows()):
            for j in range(self.ncols()):
                flat.append(self.get(i, j))
        return (_unpickle_dense_matrix, (self.nrows(), self.ncols(), flat))

    # -- factory method for wrap() -------------------------------------------

    @classmethod
    def _from_raw(cls, raw):
        """Create a DenseMatrixWrapper from an existing _core.DenseMatrix."""
        obj = object.__new__(cls)
        obj._raw = raw
        return obj


# Public alias
DenseMatrix = DenseMatrixWrapper
MutableDenseMatrix = DenseMatrixWrapper
Matrix = DenseMatrixWrapper


class ImmutableMatrix(DenseMatrixWrapper):
    """Immutable delegation wrapper around a _core.DenseMatrix."""

    def __setitem__(self, *args):
        raise TypeError("ImmutableMatrix does not support item assignment")

    def set(self, *args):
        raise TypeError("ImmutableMatrix does not support item assignment")

    def fill(self, *args):
        raise TypeError("ImmutableMatrix does not support item assignment")

    def rowadd(self, *args):
        raise TypeError("ImmutableMatrix does not support mutation")

    def rowmul(self, *args):
        raise TypeError("ImmutableMatrix does not support mutation")

    def row_swap(self, *args):
        raise TypeError("ImmutableMatrix does not support mutation")

    def col_swap(self, *args):
        raise TypeError("ImmutableMatrix does not support mutation")

    def row_join(self, *args):
        result = super().row_join(*args)
        return self._as_immutable(result)

    def col_join(self, *args):
        result = super().col_join(*args)
        return self._as_immutable(result)

    def row_del(self, *args):
        raise TypeError("ImmutableMatrix does not support mutation")

    def col_del(self, *args):
        raise TypeError("ImmutableMatrix does not support mutation")

    def resize(self, *args):
        raise TypeError("ImmutableMatrix does not support mutation")

    def _as_immutable(self, m):
        if isinstance(m, ImmutableMatrix):
            return m
        if isinstance(m, DenseMatrixWrapper):
            return ImmutableMatrix._from_raw(m._raw)
        return ImmutableMatrix._from_raw(m)

    def solve(self, b, method='LU'):
        return self._as_immutable(super().solve(b, method))

    def LU_solve(self, other):
        return self._as_immutable(super().LU_solve(other))

    def LUsolve(self, other):
        return self._as_immutable(super().LUsolve(other))

    def __add__(self, other):
        return self._as_immutable(super().__add__(other))

    def __radd__(self, other):
        if isinstance(other, (DenseMatrixWrapper, _core.DenseMatrix)):
            return self._as_immutable(DenseMatrixWrapper.__radd__(self, other))
        return self.__add__(other)

    def __sub__(self, other):
        return self._as_immutable(super().__sub__(other))

    def __rsub__(self, other):
        if isinstance(other, (DenseMatrixWrapper, _core.DenseMatrix)):
            return self._as_immutable(DenseMatrixWrapper.__rsub__(self, other))
        return NotImplemented

    def __mul__(self, other):
        if isinstance(other, (int, float, _core.Basic)) or hasattr(other, '_raw'):
            return self._as_immutable(super().__mul__(other))
        return self._as_immutable(super().__mul__(other))

    def __rmul__(self, other):
        if isinstance(other, (DenseMatrixWrapper, _core.DenseMatrix)):
            return self._as_immutable(DenseMatrixWrapper.__rmul__(self, other))
        return self.__mul__(other)

    def __truediv__(self, other):
        return self._as_immutable(super().__truediv__(other))

    def __matmul__(self, other):
        return self._as_immutable(super().__matmul__(other))

    def __neg__(self):
        return self._as_immutable(super().__neg__())

    def __pos__(self):
        return self._as_immutable(super().__pos__())

    def __abs__(self):
        return self._as_immutable(super().__abs__())

    def transpose(self):
        return self._as_immutable(super().transpose())

    def conjugate(self):
        return self._as_immutable(super().conjugate())

    def conjugate_transpose(self):
        return self._as_immutable(super().conjugate_transpose())

    def subs(self, *args):
        return self._as_immutable(super().subs(*args))

    def xreplace(self, *args):
        return self._as_immutable(super().xreplace(*args))

    def diff(self, sym):
        return self._as_immutable(super().diff(sym))

    def inv(self, method=""):
        return self._as_immutable(super().inv(method))

    def add_matrix(self, other):
        return self._as_immutable(super().add_matrix(other))

    def mul_matrix(self, other):
        return self._as_immutable(super().mul_matrix(other))

    def mul_scalar(self, k):
        return self._as_immutable(super().mul_scalar(k))

    def add_scalar(self, k):
        return self._as_immutable(super().add_scalar(k))

    def row(self, n):
        return self._as_immutable(super().row(n))

    def col(self, n):
        return self._as_immutable(super().col(n))

    def row_insert(self, pos, M):
        return self._as_immutable(super().row_insert(pos, M))

    def col_insert(self, pos, M):
        return self._as_immutable(super().col_insert(pos, M))

    def __getitem__(self, key):
        result = super().__getitem__(key)
        if isinstance(result, DenseMatrixWrapper) and not isinstance(result, ImmutableMatrix):
            return self._as_immutable(result)
        return result

    def as_immutable(self):
        return self

    def __reduce__(self):
        from ._pickling import _unpickle_immutable_matrix
        flat = []
        for i in range(self.nrows()):
            for j in range(self.ncols()):
                flat.append(self.get(i, j))
        return (_unpickle_immutable_matrix, (self.nrows(), self.ncols(), flat))


ImmutableDenseMatrix = ImmutableMatrix

SparseMatrix = _missing("SparseMatrix")
MutableSparseMatrix = _missing("MutableSparseMatrix")
ImmutableSparseMatrix = _missing("ImmutableSparseMatrix")

NonSquareMatrixError = _core.NonSquareMatrixError
ShapeError = _core.ShapeError


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------

def zeros(rows, cols=None, **kwargs):
    c = kwargs.get('c')
    if c is not None:
        cols = c
    if cols is None:
        cols = rows
    return DenseMatrixWrapper._from_raw(_core.zeros(rows, cols))


def ones(rows, cols=None):
    if cols is None:
        cols = rows
    return DenseMatrixWrapper._from_raw(_core.ones(rows, cols))


def eye(n, m=None, k=0):
    if m is None:
        return DenseMatrixWrapper._from_raw(_core.eye(n, k))
    return DenseMatrixWrapper._from_raw(_core.eye(n, m, k))


def diag(*values, k=0):
    if len(values) == 1 and isinstance(values[0], (list, tuple)):
        values = values[0]
    vals = [_sympify(v) for v in values]
    return DenseMatrixWrapper._from_raw(_core.diag(vals, k))
