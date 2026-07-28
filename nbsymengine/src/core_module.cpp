// SymEngine nanobind _core module — hand-written scaffold.
//
// This file is HAND-WRITTEN.  It owns:
//   - _core module initialization (NB_MODULE)
//   - intrusive ownership hooks (set_self_py, ref-count guards)
//   - singleton detach cleanup (atexit handler)
//   - manual bindings (arithmetic dunders, constants, sets, etc.)
//
// The generated litgen body is included below via:
//   #include "symengine_pydef.cpp"
// That included file comes from the build tree (generated at build time) or
// from the sdist extracted tarball (pre-generated).  It is NOT tracked in git.
//
// Re-generate with:
//   python generator/generate.py generator/generate.yaml

#include <nanobind/nanobind.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/vector.h>
#include <nanobind/stl/set.h>
#include <nanobind/stl/map.h>
#include <nanobind/stl/tuple.h>
#include "nanobind_symengine.h"
#include "nanobind_module_common.h"

#include <symengine/number.h>
#include <symengine/rational.h>
#include <symengine/constants.h>
#include <symengine/symbol.h>
#include <symengine/integer.h>
#include <symengine/add.h>
#include <symengine/mul.h>
#include <symengine/pow.h>
#include <symengine/functions.h>
#include <symengine/logic.h>
#include <symengine/sets.h>
#include <symengine/ntheory.h>
#include <symengine/solve.h>
#include <symengine/derivative.h>
#include <symengine/subs.h>
#include <symengine/series.h>
#include <symengine/real_double.h>
#include <symengine/matrix.h>
#include <symengine/eval_double.h>
#include <sstream>
#include <thread>
#include <vector>
#include <symengine/lambda_double.h>
#include <nanobind/ndarray.h>

namespace nb = nanobind;
using namespace SymEngine;
namespace mcomm = SymEngine::python::module_common;

// Helper: create an RCP<const Basic> that shares ownership with an existing
// object (increments intrusive refcount).  Used by arithmetic dunders to
// wrap `const Basic &` arguments before passing to SymEngine free functions.
static inline RCP<const Basic> rcp_from_ref(const Basic &b) {
    return RCP<const Basic>(&b);
}

// Singleton registry: tracks every static singleton whose Python wrapper has
// been (or may be) created, so the atexit cleanup can detach them before
// interpreter finalization.  Design (A) from NextPhase04.
static std::vector<RCP<const Basic>> g_singletons;

// Custom exception types for matrix operations
struct NonSquareMatrixError_ : std::runtime_error {
    using std::runtime_error::runtime_error;
};
struct ShapeError_ : std::runtime_error {
    using std::runtime_error::runtime_error;
};

// Helper: hand a freshly allocated double buffer over to NumPy.  The capsule
// deleter releases the buffer once the ndarray (and any view of it) dies.
static nb::ndarray<nb::numpy, double> own_double_buffer(double *data, size_t ndim,
                                                        const size_t *shape) {
    nb::capsule owner(data, [](void *p) noexcept {
        delete[] static_cast<double *>(p);
    });
    return nb::ndarray<nb::numpy, double>(data, ndim, shape, owner);
}

// Helper: numeric (float64) copy of a DenseMatrix, shape (nrows, ncols).
// Non-numeric entries make SymEngine::eval_double throw, which the registered
// exception translator turns into a Python error.
static nb::ndarray<nb::numpy, double> dense_matrix_to_numpy(const DenseMatrix &mat) {
    const unsigned rows = mat.nrows();
    const unsigned cols = mat.ncols();
    const size_t n = (size_t)rows * (size_t)cols;
    std::unique_ptr<double[]> buf(new double[n ? n : 1]);
    for (unsigned i = 0; i < rows; ++i) {
        for (unsigned j = 0; j < cols; ++j) {
            auto elem = mat.get(i, j);
            buf[(size_t)i * cols + j] =
                elem.is_null() ? 0.0 : SymEngine::eval_double(*elem);
        }
    }
    const size_t shape[2] = { (size_t)rows, (size_t)cols };
    return own_double_buffer(buf.release(), 2, shape);
}

class PyLambdaRealDouble {
    LambdaRealDoubleVisitor visitor_;
    vec_basic inputs_;
    size_t n_inputs_;
    size_t n_outputs_;

public:
    PyLambdaRealDouble(const vec_basic &inputs,
                       const vec_basic &flat_outputs,
                       bool cse)
        : inputs_(inputs),
          n_inputs_(inputs.size()),
          n_outputs_(flat_outputs.size())
    {
        visitor_.init(inputs_, flat_outputs, cse);
    }

    size_t n_inputs() const { return n_inputs_; }
    size_t n_outputs() const { return n_outputs_; }

    void call(double *out, const double *inp) {
        visitor_.call(out, inp);
    }
};

#ifdef HAVE_SYMENGINE_LLVM
#include <symengine/llvm_double.h>

class PyLLVMDouble {
    std::unique_ptr<LLVMDoubleVisitor> visitor_;
    vec_basic inputs_;
    size_t n_inputs_;
    size_t n_outputs_;

public:
    PyLLVMDouble(const vec_basic &inputs,
                 const vec_basic &flat_outputs,
                 bool cse,
                 unsigned opt_level)
        : inputs_(inputs),
          n_inputs_(inputs.size()),
          n_outputs_(flat_outputs.size())
    {
        visitor_ = std::make_unique<LLVMDoubleVisitor>();
        visitor_->init(inputs_, flat_outputs, cse, opt_level);
    }

    PyLLVMDouble(const std::string &blob,
                 size_t n_inputs,
                 size_t n_outputs)
        : n_inputs_(n_inputs),
          n_outputs_(n_outputs)
    {
        visitor_ = std::make_unique<LLVMDoubleVisitor>();
        visitor_->loads(blob);
    }

    size_t n_inputs() const { return n_inputs_; }
    size_t n_outputs() const { return n_outputs_; }

    void call(double *out, const double *inp) {
        visitor_->call(out, inp);
    }

    std::string dumps() const {
        return visitor_->dumps();
    }
};
#endif

// --- Shared ndarray API for the native lambdify visitors -------------------
//
// Both PyLambdaRealDouble and PyLLVMDouble expose n_inputs()/n_outputs() and
// call(out, inp), so the broadcasting ndarray entry points are bound once via
// these templates.

// Number of broadcast rows implied by *inp* (1-D => 1, 2-D => shape[0]).
template <typename Cls>
static size_t lambdify_nbroadcast(const Cls &self,
                                  const nb::ndarray<const double, nb::c_contig> &inp) {
    const size_t n_in = self.n_inputs();
    if (inp.ndim() == 1) {
        if ((size_t)inp.shape(0) != n_in)
            throw nb::value_error(
                ("Expected " + std::to_string(n_in) + " input values, got " +
                 std::to_string(inp.shape(0))).c_str());
        return 1;
    }
    if (inp.ndim() == 2) {
        if ((size_t)inp.shape(1) != n_in)
            throw nb::value_error(
                ("C order implies last dim == " + std::to_string(n_in) +
                 " (number of inputs), got " + std::to_string(inp.shape(1))).c_str());
        return (size_t)inp.shape(0);
    }
    throw nb::value_error("Input array must be 1-D or 2-D");
}

// Evaluate *m* consecutive input rows into *out*; GIL released when m > 1.
template <typename Cls>
static void lambdify_eval_rows(Cls &self, double *out, const double *inp, size_t m) {
    const size_t n_in = self.n_inputs();
    const size_t n_out = self.n_outputs();
    try {
        if (m == 1) {
            self.call(out, inp);
        } else {
            nb::gil_scoped_release release;
            for (size_t i = 0; i < m; ++i)
                self.call(out + i * n_out, inp + i * n_in);
        }
    } catch (const std::exception &e) {
        PyErr_SetString(PyExc_RuntimeError, e.what());
        throw nb::python_error();
    }
}

template <typename Cls>
static void bind_lambdify_ndarray_api(nb::class_<Cls> &cls) {
    cls.def("call_alloc", [](Cls &self,
                             nb::ndarray<const double, nb::c_contig> inp) {
        const size_t m = lambdify_nbroadcast(self, inp);
        const size_t n_out = self.n_outputs();
        const size_t n = m * n_out;
        std::unique_ptr<double[]> buf(new double[n ? n : 1]);
        lambdify_eval_rows(self, buf.get(), inp.data(), m);
        size_t shape[2];
        size_t ndim;
        if (inp.ndim() == 1) {
            ndim = 1;
            shape[0] = n_out;
        } else {
            ndim = 2;
            shape[0] = m;
            shape[1] = n_out;
        }
        return own_double_buffer(buf.release(), ndim, shape);
    }, nb::arg("inp"));

    cls.def("call_into", [](Cls &self,
                            nb::ndarray<const double, nb::c_contig> inp,
                            nb::ndarray<double, nb::c_contig> out) {
        const size_t m = lambdify_nbroadcast(self, inp);
        const size_t n_out = self.n_outputs();
        size_t out_size = 1;
        for (size_t i = 0; i < out.ndim(); ++i)
            out_size *= (size_t)out.shape(i);
        if (out_size != m * n_out)
            throw nb::value_error(
                ("Expected " + std::to_string(m * n_out) +
                 " output slots, got " + std::to_string(out_size)).c_str());
        lambdify_eval_rows(self, out.data(), inp.data(), m);
        // .noconvert(): never let nanobind silently fill a temporary copy.
    }, nb::arg("inp"), nb::arg("out").noconvert());
}

static void register_singletons() {
    mcomm::seed_common_singletons(g_singletons);
}

NB_MODULE(_core, m) {
    mcomm::initialize_intrusive_hooks();

    // Root class — intrusive ownership for Basic hierarchy (shared scaffolding).
    auto basic = mcomm::bind_basic_common(m);
    // _core-specific extensions: repr, compare, arithmetic dunders.
    basic.def("__repr__", [](const Basic &b){ return b.__str__(); })
        .def("compare", [](const Basic &self, const Basic &other) {
            return self.compare(other);
        }, nb::arg("other"))
        // Arithmetic dunders -- coerce Python int/bool to Integer, delegate
        // to SymEngine free functions.  Return NotImplemented on type error
        // so Python can try the reflected method.
        .def("__add__", [](const Basic &a, nb::object b) -> nb::object {
            if (nb::isinstance<Basic>(b))
                return nb::cast(add(rcp_from_ref(a), rcp_from_ref(nb::cast<const Basic &>(b))));
            if (PyLong_Check(b.ptr()))
                return nb::cast(add(rcp_from_ref(a), SymEngine::integer(nb::cast<long>(b))));
            return nb::not_implemented();
        })
        .def("__radd__", [](const Basic &a, nb::object b) -> nb::object {
            if (PyLong_Check(b.ptr()))
                return nb::cast(add(SymEngine::integer(nb::cast<long>(b)), rcp_from_ref(a)));
            return nb::not_implemented();
        })
        .def("__sub__", [](const Basic &a, nb::object b) -> nb::object {
            if (nb::isinstance<Basic>(b))
                return nb::cast(sub(rcp_from_ref(a), rcp_from_ref(nb::cast<const Basic &>(b))));
            if (PyLong_Check(b.ptr()))
                return nb::cast(sub(rcp_from_ref(a), SymEngine::integer(nb::cast<long>(b))));
            return nb::not_implemented();
        })
        .def("__rsub__", [](const Basic &a, nb::object b) -> nb::object {
            if (PyLong_Check(b.ptr()))
                return nb::cast(sub(SymEngine::integer(nb::cast<long>(b)), rcp_from_ref(a)));
            return nb::not_implemented();
        })
        .def("__mul__", [](const Basic &a, nb::object b) -> nb::object {
            if (nb::isinstance<Basic>(b))
                return nb::cast(mul(rcp_from_ref(a), rcp_from_ref(nb::cast<const Basic &>(b))));
            if (PyLong_Check(b.ptr()))
                return nb::cast(mul(rcp_from_ref(a), SymEngine::integer(nb::cast<long>(b))));
            return nb::not_implemented();
        })
        .def("__rmul__", [](const Basic &a, nb::object b) -> nb::object {
            if (PyLong_Check(b.ptr()))
                return nb::cast(mul(SymEngine::integer(nb::cast<long>(b)), rcp_from_ref(a)));
            return nb::not_implemented();
        })
        .def("__truediv__", [](const Basic &a, nb::object b) -> nb::object {
            if (nb::isinstance<Basic>(b))
                return nb::cast(div(rcp_from_ref(a), rcp_from_ref(nb::cast<const Basic &>(b))));
            if (PyLong_Check(b.ptr()))
                return nb::cast(div(rcp_from_ref(a), SymEngine::integer(nb::cast<long>(b))));
            return nb::not_implemented();
        })
        .def("__rtruediv__", [](const Basic &a, nb::object b) -> nb::object {
            if (PyLong_Check(b.ptr()))
                return nb::cast(div(SymEngine::integer(nb::cast<long>(b)), rcp_from_ref(a)));
            return nb::not_implemented();
        })
        .def("__pow__", [](const Basic &a, nb::object b) -> nb::object {
            if (nb::isinstance<Basic>(b))
                return nb::cast(pow(rcp_from_ref(a), rcp_from_ref(nb::cast<const Basic &>(b))));
            if (PyLong_Check(b.ptr()))
                return nb::cast(pow(rcp_from_ref(a), SymEngine::integer(nb::cast<long>(b))));
            return nb::not_implemented();
        })
        .def("__rpow__", [](const Basic &a, nb::object b) -> nb::object {
            if (PyLong_Check(b.ptr()))
                return nb::cast(pow(SymEngine::integer(nb::cast<long>(b)), rcp_from_ref(a)));
            return nb::not_implemented();
        })
        .def("__neg__", [](const Basic &a) {
            return nb::cast(neg(rcp_from_ref(a)));
        })
        .def("__pos__", [](const Basic &a) {
            return nb::cast(rcp_from_ref(a));
        });

    // Abstract base classes hand-bound here (do not duplicate in pydef)
    nb::class_<Number, Basic>(m, "Number");
    nb::class_<Set, Basic>(m, "Set")
        .def("set_union", [](const Set &self, const RCP<const Set> &other) -> RCP<const Set> {
            return self.set_union(other);
        }, nb::arg("other"))
        .def("set_intersection", [](const Set &self, const RCP<const Set> &other) -> RCP<const Set> {
            return self.set_intersection(other);
        }, nb::arg("other"))
        .def("set_complement", [](const Set &self, const RCP<const Set> &other) -> RCP<const Set> {
            return self.set_complement(other);
        }, nb::arg("other"))
        .def("contains", [](const Set &self, const RCP<const Basic> &expr) -> RCP<const Boolean> {
            return self.contains(expr);
        }, nb::arg("expr"));
    nb::class_<Boolean, Basic>(m, "Boolean");
    nb::class_<BooleanAtom, Boolean>(m, "BooleanAtom");
    nb::class_<And, Boolean>(m, "And");
    nb::class_<Or, Boolean>(m, "Or");
    nb::class_<Not, Boolean>(m, "Not");
    nb::class_<Xor, Boolean>(m, "Xor");
    nb::class_<Contains, Boolean>(m, "Contains");
    nb::class_<Relational, Boolean>(m, "Relational");
    nb::class_<Equality, Relational>(m, "Equality");
    nb::class_<Unequality, Relational>(m, "Unequality");
    nb::class_<LessThan, Relational>(m, "LessThan");
    nb::class_<StrictLessThan, Relational>(m, "StrictLessThan");

    // Classes skipped by litgen (bound manually)
    nb::class_<Erf, Basic>(m, "Erf");
    nb::class_<Erfc, Basic>(m, "Erfc");
    nb::class_<LogGamma, Basic>(m, "LogGamma");
    nb::class_<Beta, Basic>(m, "Beta");
    nb::class_<PolyGamma, Basic>(m, "PolyGamma");
    nb::class_<Infty, Number>(m, "Infty");
    nb::class_<NaN, Number>(m, "NaN");
    nb::class_<EmptySet, Set>(m, "EmptySet");
    nb::class_<UniversalSet, Set>(m, "UniversalSet");
    nb::class_<FiniteSet, Set>(m, "FiniteSet");
    nb::class_<ConditionSet, Set>(m, "ConditionSet");
    nb::class_<ImageSet, Set>(m, "ImageSet");

    // FunctionSymbol (for symbolic functions like f(x))
    nb::class_<FunctionSymbol, Basic>(m, "FunctionSymbol")
        .def_prop_ro("name", [](const FunctionSymbol &f) -> std::string {
            return f.get_name();
        });

    // Derivative (unevaluated derivative expression)
    nb::class_<Derivative, Basic>(m, "_Derivative")
        .def("get_arg", &Derivative::get_arg)
        .def("get_symbols", [](const Derivative &d) -> std::vector<RCP<const Basic>> {
            auto &ms = d.get_symbols();
            return std::vector<RCP<const Basic>>(ms.begin(), ms.end());
        });

    // Subs (unevaluated substitution expression)
    nb::class_<Subs, Basic>(m, "_Subs")
        .def("get_arg", &Subs::get_arg)
        .def("get_dict", [](const Subs &s) -> nb::dict {
            nb::dict d;
            for (const auto &p : s.get_dict()) {
                d[nb::cast(p.first)] = nb::cast(p.second);
            }
            return d;
        })
        .def("get_variables", &Subs::get_variables)
        .def("get_point", &Subs::get_point);

    // UnevaluatedExpr (prevents automatic evaluation)
    nb::class_<UnevaluatedExpr, Basic>(m, "UnevaluatedExpr");

    // SeriesCoeffInterface (abstract base for series results)
    nb::class_<SeriesCoeffInterface, Number>(m, "SeriesCoeffInterface")
        .def("as_basic", &SeriesCoeffInterface::as_basic)
        .def("get_coeff", &SeriesCoeffInterface::get_coeff, nb::arg("n"))
        .def("get_degree", &SeriesCoeffInterface::get_degree)
        .def("get_var", &SeriesCoeffInterface::get_var);

    // RealDouble (double-precision floating point)
    nb::class_<RealDouble, Number>(m, "RealDouble")
        .def_prop_ro("as_double", [](const RealDouble &r) -> double {
            return r.as_double();
        });

    // --- Matrix bindings (value-like, non-intrusive) ---
    // NOTE: DenseMatrix methods that return new DenseMatrix objects use
    // heap allocation to avoid segfaults with value-type method returns.
    //
    // DenseMatrix.__init__ overload resolution:
    //
    // The six construction forms are disambiguated by argument count and type:
    //   1. DenseMatrix()                           → empty 0×0 matrix
    //   2. DenseMatrix(rows, cols)                 → zero-filled r×c matrix
    //   3. DenseMatrix(other_matrix)               → copy constructor
    //   4. DenseMatrix(flat_list)                  → 1×n or n×1 from vec_basic
    //   5. DenseMatrix(list_of_lists)              → r×c from nested sequences
    //   6. DenseMatrix(rows, cols, values)         → explicit r×c from flat values
    //
    // Forms 1-2 use nb::init<> (argument count dispatch).
    // Form 3-5 use a single __init__ lambda with nb::handle arg (manual type dispatch).
    // Form 6 uses a __init__ lambda with (rows, cols, values) signature.
    //
    // Overlap: DenseMatrix([1,2,3]) could match form 4 (flat) or form 5
    // (single row).  The current code correctly handles this: if the first
    // element is a sequence, it's treated as form 5; otherwise form 4.
    // This behavior is locked by test_core_bindings.py test_dense_matrix_init_*.
    nb::class_<DenseMatrix>(m, "DenseMatrix")
        .def(nb::init<>())
        .def(nb::init<unsigned, unsigned>(), nb::arg("rows"), nb::arg("cols"))
        .def("__init__", [](DenseMatrix *self, nb::handle arg) {
            // Single-argument init: handles DenseMatrix copy, vec_basic, and list-of-lists
            if (nb::isinstance<DenseMatrix>(arg)) {
                const DenseMatrix &other = nb::cast<const DenseMatrix &>(arg);
                new (self) DenseMatrix(other);
                return;
            }
            if (nb::isinstance<vec_basic>(arg)) {
                vec_basic v = nb::cast<vec_basic>(arg);
                new (self) DenseMatrix(v);
                return;
            }
            // Handle as sequence
            nb::sequence seq = nb::cast<nb::sequence>(arg);
            Py_ssize_t len = nb::len(seq);
            if (len == 0) {
                new (self) DenseMatrix(0, 0);
                return;
            }
            auto first = seq[0];
            if (nb::isinstance<nb::sequence>(first)) {
                unsigned nrows = (unsigned)len;
                unsigned ncols = 0;
                vec_basic v;
                for (unsigned i = 0; i < nrows; ++i) {
                    nb::sequence row = nb::cast<nb::sequence>(arg[i]);
                    unsigned row_len = (unsigned)nb::len(row);
                    if (i == 0) ncols = row_len;
                    else if (row_len != ncols)
                        throw nb::value_error("DenseMatrix: all rows must have the same length");
                    for (unsigned j = 0; j < row_len; ++j) {
                        auto item = row[j];
                        if (nb::isinstance<Basic>(item)) {
                            v.push_back(nb::cast<RCP<const Basic>>(item));
                        } else if (PyLong_Check(item.ptr())) {
                            v.push_back(SymEngine::integer(nb::cast<long>(item)));
                        } else if (PyFloat_Check(item.ptr())) {
                            v.push_back(SymEngine::real_double(nb::cast<double>(item)));
                        } else {
                            throw nb::type_error("DenseMatrix values must be Basic, int, or float");
                        }
                    }
                }
                new (self) DenseMatrix(nrows, ncols, v);
            } else {
                vec_basic v;
                for (auto item : arg) {
                    if (nb::isinstance<Basic>(item)) {
                        v.push_back(nb::cast<RCP<const Basic>>(item));
                    } else if (PyLong_Check(item.ptr())) {
                        v.push_back(SymEngine::integer(nb::cast<long>(item)));
                    } else if (PyFloat_Check(item.ptr())) {
                        v.push_back(SymEngine::real_double(nb::cast<double>(item)));
                    } else {
                        throw nb::type_error("DenseMatrix values must be Basic, int, or float");
                    }
                }
                new (self) DenseMatrix(v);
            }
        }, nb::arg("arg"))
        .def("__init__", [](DenseMatrix *self, unsigned rows, unsigned cols,
                            nb::sequence values) {
            vec_basic v;
            for (auto item : values) {
                if (nb::isinstance<Basic>(item)) {
                    v.push_back(nb::cast<RCP<const Basic>>(item));
                } else if (PyLong_Check(item.ptr())) {
                    v.push_back(SymEngine::integer(nb::cast<long>(item)));
                } else if (PyFloat_Check(item.ptr())) {
                    v.push_back(SymEngine::real_double(nb::cast<double>(item)));
                } else {
                    throw nb::type_error("DenseMatrix values must be Basic, int, or float");
                }
            }
            if (v.size() != (size_t)(rows * cols))
                throw nb::value_error("DenseMatrix: values length does not match rows*cols");
            new (self) DenseMatrix(rows, cols, v);
        }, nb::arg("rows"), nb::arg("cols"), nb::arg("values"))
        .def_prop_ro("rows", [](const DenseMatrix &m) { return m.nrows(); })
        .def_prop_ro("cols", [](const DenseMatrix &m) { return m.ncols(); })
        .def_prop_ro("shape", [](const DenseMatrix &m) {
            return nb::make_tuple(m.nrows(), m.ncols());
        })
        .def_prop_ro("size", [](const DenseMatrix &m) { return m.nrows() * m.ncols(); })
        .def("nrows", &DenseMatrix::nrows)
        .def("ncols", &DenseMatrix::ncols)
        .def_prop_ro("is_square", &DenseMatrix::is_square)
        .def("__str__", [](const DenseMatrix &mat) -> std::string {
            std::ostringstream os;
            for (unsigned i = 0; i < mat.nrows(); ++i) {
                os << "[";
                for (unsigned j = 0; j < mat.ncols(); ++j) {
                    auto elem = mat.get(i, j);
                    if (elem.is_null()) {
                        os << "0";
                    } else {
                        os << *elem;
                    }
                    if (j + 1 < mat.ncols()) os << ", ";
                }
                os << "]\n";
            }
            return os.str();
        })
        .def("__repr__", [](const DenseMatrix &mat) -> std::string {
            std::ostringstream os;
            for (unsigned i = 0; i < mat.nrows(); ++i) {
                os << "[";
                for (unsigned j = 0; j < mat.ncols(); ++j) {
                    auto elem = mat.get(i, j);
                    if (elem.is_null()) {
                        os << "0";
                    } else {
                        os << *elem;
                    }
                    if (j + 1 < mat.ncols()) os << ", ";
                }
                os << "]\n";
            }
            return os.str();
        })
        .def("__eq__", [](const DenseMatrix &a, nb::object b) -> nb::object {
            if (b.is_none()) return nb::cast(false);
            if (!nb::isinstance<DenseMatrix>(b)) return nb::not_implemented();
            return nb::cast(a.eq(nb::cast<const DenseMatrix &>(b)));
        }, nb::arg("b").none())
        .def("get", [](const DenseMatrix &mat, int i, int j) -> RCP<const Basic> {
            unsigned nrows = mat.nrows();
            unsigned ncols = mat.ncols();
            if (i < 0) i += nrows;
            if (j < 0) j += ncols;
            if (i < 0 || (unsigned)i >= nrows || j < 0 || (unsigned)j >= ncols)
                throw nb::index_error("matrix index out of range");
            return mat.get((unsigned)i, (unsigned)j);
        }, nb::arg("i"), nb::arg("j"))
        .def("set", [](DenseMatrix &mat, int i, int j, const RCP<const Basic> &e) {
            unsigned nrows = mat.nrows();
            unsigned ncols = mat.ncols();
            if (i < 0) i += nrows;
            if (j < 0) j += ncols;
            if (i < 0 || (unsigned)i >= nrows || j < 0 || (unsigned)j >= ncols)
                throw nb::index_error("matrix index out of range");
            mat.set((unsigned)i, (unsigned)j, e);
        }, nb::arg("i"), nb::arg("j"), nb::arg("e"))
        .def("set_from_array", [](DenseMatrix &mat,
                                  nb::ndarray<double, nb::ndim<1>, nb::c_contig> arr) {
            unsigned rows = mat.nrows();
            unsigned cols = mat.ncols();
            if ((size_t)arr.shape(0) != (size_t)(rows * cols))
                throw nb::value_error("Array size must match matrix dimensions");
            const double *data = arr.data();
            for (unsigned i = 0; i < rows; ++i)
                for (unsigned j = 0; j < cols; ++j)
                    mat.set(i, j, SymEngine::real_double(data[i * cols + j]));
        }, nb::arg("arr"))
        .def("to_numpy", [](const DenseMatrix &mat) {
            return dense_matrix_to_numpy(mat);
        })
        .def("__array__", [](const DenseMatrix &mat, nb::handle dtype, nb::handle copy) {
            (void)dtype;
            (void)copy;
            return dense_matrix_to_numpy(mat);
        }, nb::arg("dtype") = nb::none(), nb::arg("copy") = nb::none())
        .def("resize", &DenseMatrix::resize, nb::arg("i"), nb::arg("j"))
        .def("as_vec_basic", &DenseMatrix::as_vec_basic)
        .def("is_lower", &DenseMatrix::is_lower)
        .def("is_upper", &DenseMatrix::is_upper)
        .def("det", [](const DenseMatrix &self) {
            if (self.nrows() != self.ncols())
                throw NonSquareMatrixError_("Matrix must be square to compute determinant.");
            return self.det();
        })
        .def("rank", &DenseMatrix::rank)
        .def("trace", [](const DenseMatrix &self) {
            if (self.nrows() != self.ncols())
                throw NonSquareMatrixError_("Matrix must be square to compute trace");
            return self.trace();
        })
        .def("inv", [](const DenseMatrix &self, const std::string &method) {
            if (self.nrows() != self.ncols())
                throw NonSquareMatrixError_("Matrix must be square to compute inverse");
            DenseMatrix result(self.ncols(), self.nrows());
            if (method == "LU") {
                inverse_LU(self, result);
            } else if (method == "FFLU") {
                inverse_fraction_free_LU(self, result);
            } else if (method == "GJ") {
                inverse_gauss_jordan(self, result);
            } else {
                self.inv(result);
            }
            return result;
        }, nb::arg("method") = std::string(""))
        .def("transpose", [](const DenseMatrix &self) {
            DenseMatrix result(self.ncols(), self.nrows());
            self.transpose(result);
            return result;
        })
        .def("conjugate", [](const DenseMatrix &self) {
            DenseMatrix result(self.nrows(), self.ncols());
            self.conjugate(result);
            return result;
        })
        .def("conjugate_transpose", [](const DenseMatrix &self) {
            DenseMatrix result(self.ncols(), self.nrows());
            self.conjugate_transpose(result);
            return result;
        })
        .def("add_matrix", [](const DenseMatrix &a, const DenseMatrix &b) {
            if (a.nrows() != b.nrows() || a.ncols() != b.ncols())
                throw ShapeError_("Matrix dimensions don't match for addition");
            DenseMatrix result(a.nrows(), a.ncols());
            a.add_matrix(b, result);
            return result;
        }, nb::arg("other"))
        .def("mul_matrix", [](const DenseMatrix &a, const DenseMatrix &b) {
            if (a.ncols() != b.nrows())
                throw ShapeError_("Matrix dimensions incompatible for multiplication");
            DenseMatrix result(a.nrows(), b.ncols());
            a.mul_matrix(b, result);
            return result;
        }, nb::arg("other"))
        .def("multiply_elementwise", [](const DenseMatrix &a, const DenseMatrix &b) {
            if (a.nrows() != b.nrows() || a.ncols() != b.ncols())
                throw ShapeError_("Matrix dimensions don't match for element-wise multiplication");
            DenseMatrix result(a.nrows(), a.ncols());
            a.elementwise_mul_matrix(b, result);
            return result;
        }, nb::arg("other"))
        .def("add_scalar", [](const DenseMatrix &self, const RCP<const Basic> &k) {
            DenseMatrix result(self.nrows(), self.ncols());
            self.add_scalar(k, result);
            return result;
        }, nb::arg("k"))
        .def("mul_scalar", [](const DenseMatrix &self, const RCP<const Basic> &k) {
            DenseMatrix result(self.nrows(), self.ncols());
            self.mul_scalar(k, result);
            return result;
        }, nb::arg("k"))
        .def("LU", [](const DenseMatrix &self) {
            if (self.nrows() != self.ncols())
                throw NonSquareMatrixError_("Matrix must be square for LU decomposition");
            DenseMatrix L(self.nrows(), self.nrows());
            DenseMatrix U(self.nrows(), self.ncols());
            self.LU(L, U);
            return nb::make_tuple(L, U);
        })
        .def("LUdecomposition", [](const DenseMatrix &self) {
            if (self.nrows() != self.ncols())
                throw NonSquareMatrixError_("Matrix must be square for LU decomposition");
            unsigned n = self.nrows();
            DenseMatrix L(n, n);
            DenseMatrix U(n, n);
            permutelist pl;
            pivoted_LU(self, L, U, pl);
            nb::list plist;
            for (auto &p : pl) {
                plist.append(nb::make_tuple(p.first, p.second));
            }
            return nb::make_tuple(L, U, plist);
        })
        .def("LDL", [](const DenseMatrix &self) {
            if (self.nrows() != self.ncols())
                throw NonSquareMatrixError_("Matrix must be square for LDL decomposition");
            DenseMatrix L(self.nrows(), self.nrows());
            DenseMatrix D(self.nrows(), self.nrows());
            self.LDL(L, D);
            return nb::make_tuple(L, D);
        })
        .def("FFLU", [](const DenseMatrix &self) {
            if (self.nrows() != self.ncols())
                throw NonSquareMatrixError_("Matrix must be square for FFLU decomposition");
            DenseMatrix LU(self.nrows(), self.ncols());
            self.FFLU(LU);
            // FFLU stores combined L/U: L below+on diagonal, U on+above diagonal
            // Both L and U share the diagonal values (pivots)
            unsigned n = self.nrows();
            DenseMatrix L(n, n);
            DenseMatrix U(n, n);
            SymEngine::zeros(L);
            SymEngine::zeros(U);
            for (unsigned i = 0; i < n; ++i) {
                for (unsigned j = 0; j < n; ++j) {
                    if (i > j) {
                        L.set(i, j, LU.get(i, j));
                    } else if (i == j) {
                        L.set(i, j, LU.get(i, j));
                        U.set(i, j, LU.get(i, j));
                    } else {
                        U.set(i, j, LU.get(i, j));
                    }
                }
            }
            return nb::make_tuple(L, U);
        })
        .def("FFLDU", [](const DenseMatrix &self) {
            if (self.nrows() != self.ncols())
                throw NonSquareMatrixError_("Matrix must be square for FFLDU decomposition");
            DenseMatrix L(self.nrows(), self.nrows());
            DenseMatrix D(self.nrows(), self.nrows());
            DenseMatrix U(self.nrows(), self.nrows());
            self.FFLDU(L, D, U);
            return nb::make_tuple(L, D, U);
        })
        .def("QR", [](const DenseMatrix &self) {
            if (self.nrows() != self.ncols())
                throw NonSquareMatrixError_("Matrix must be square for QR decomposition");
            DenseMatrix Q(self.nrows(), self.nrows());
            DenseMatrix R(self.nrows(), self.ncols());
            self.QR(Q, R);
            return nb::make_tuple(Q, R);
        })
        .def("cholesky", [](const DenseMatrix &self) {
            if (self.nrows() != self.ncols())
                throw NonSquareMatrixError_("Matrix must be square for Cholesky decomposition");
            DenseMatrix L(self.nrows(), self.ncols());
            self.cholesky(L);
            return L;
        })
        .def("solve", [](const DenseMatrix &A, const DenseMatrix &b,
                          const std::string &method) {
            DenseMatrix x(A.ncols(), 1);
            if (method == "LU") {
                LU_solve(A, b, x);
            } else if (method == "FFLU") {
                fraction_free_LU_solve(A, b, x);
            } else if (method == "FFGJ") {
                fraction_free_gauss_jordan_solve(A, b, x);
            } else {
                A.LU_solve(b, x);
            }
            return x;
        }, nb::arg("b"), nb::arg("method") = std::string("LU"))
        .def("LU_solve", [](const DenseMatrix &A, const DenseMatrix &b) {
            DenseMatrix x(A.ncols(), 1);
            A.LU_solve(b, x);
            return x;
        }, nb::arg("b"))
        .def("row_join", [](DenseMatrix &self, const DenseMatrix &B) {
            self.row_join(B);
        }, nb::arg("B"))
        .def("col_join", [](DenseMatrix &self, const DenseMatrix &B) {
            self.col_join(B);
        }, nb::arg("B"))
        .def("row_del", [](DenseMatrix &self, int k) {
            unsigned n = self.nrows();
            if (k < 0) k += n;
            if (k < 0 || (unsigned)k >= n)
                throw nb::index_error("row index out of range");
            self.row_del((unsigned)k);
            return self;
        }, nb::arg("k"))
        .def("col_del", [](DenseMatrix &self, int k) {
            unsigned n = self.ncols();
            if (k < 0) k += n;
            if (k < 0 || (unsigned)k >= n)
                throw nb::index_error("column index out of range");
            self.col_del((unsigned)k);
            return self;
        }, nb::arg("k"))
        .def("jacobian", [](const DenseMatrix &A, const DenseMatrix &x) {
            DenseMatrix result(A.nrows(), x.nrows());
            jacobian(A, x, result);
            return result;
        }, nb::arg("x"))
        .def("__add__", [](const DenseMatrix &a, const DenseMatrix &b) {
            if (a.nrows() != b.nrows() || a.ncols() != b.ncols())
                throw ShapeError_("Matrix dimensions don't match for addition");
            DenseMatrix result(a.nrows(), a.ncols());
            a.add_matrix(b, result);
            return result;
        })
        .def("__sub__", [](const DenseMatrix &a, const DenseMatrix &b) {
            if (a.nrows() != b.nrows() || a.ncols() != b.ncols())
                throw ShapeError_("Matrix dimensions don't match for subtraction");
            DenseMatrix neg_b(b.nrows(), b.ncols());
            b.mul_scalar(SymEngine::integer(-1), neg_b);
            DenseMatrix result(a.nrows(), a.ncols());
            a.add_matrix(neg_b, result);
            return result;
        })
        .def("__mul__", [](const DenseMatrix &a, const DenseMatrix &b) {
            if (a.ncols() != b.nrows())
                throw ShapeError_("Matrix dimensions incompatible for multiplication");
            DenseMatrix result(a.nrows(), b.ncols());
            a.mul_matrix(b, result);
            return result;
        })
        .def("__matmul__", [](const DenseMatrix &a, const DenseMatrix &b) {
            if (a.ncols() != b.nrows())
                throw ShapeError_("Matrix dimensions incompatible for multiplication");
            DenseMatrix result(a.nrows(), b.ncols());
            a.mul_matrix(b, result);
            return result;
        })
        .def("__mul__", [](const DenseMatrix &a, nb::object k) -> nb::object {
            if (nb::isinstance<Basic>(k)) {
                DenseMatrix result(a.nrows(), a.ncols());
                a.mul_scalar(nb::cast<RCP<const Basic>>(k), result);
                return nb::cast(result);
            }
            if (PyLong_Check(k.ptr())) {
                DenseMatrix result(a.nrows(), a.ncols());
                a.mul_scalar(SymEngine::integer(nb::cast<long>(k)), result);
                return nb::cast(result);
            }
            if (PyFloat_Check(k.ptr())) {
                DenseMatrix result(a.nrows(), a.ncols());
                a.mul_scalar(SymEngine::real_double(nb::cast<double>(k)), result);
                return nb::cast(result);
            }
            return nb::not_implemented();
        })
        .def("__rmul__", [](const DenseMatrix &a, nb::object k) -> nb::object {
            if (nb::isinstance<Basic>(k)) {
                DenseMatrix result(a.nrows(), a.ncols());
                a.mul_scalar(nb::cast<RCP<const Basic>>(k), result);
                return nb::cast(result);
            }
            if (PyLong_Check(k.ptr())) {
                DenseMatrix result(a.nrows(), a.ncols());
                a.mul_scalar(SymEngine::integer(nb::cast<long>(k)), result);
                return nb::cast(result);
            }
            if (PyFloat_Check(k.ptr())) {
                DenseMatrix result(a.nrows(), a.ncols());
                a.mul_scalar(SymEngine::real_double(nb::cast<double>(k)), result);
                return nb::cast(result);
            }
            return nb::not_implemented();
        })
        .def("__truediv__", [](const DenseMatrix &a, nb::object k) -> nb::object {
            if (nb::isinstance<DenseMatrix>(k)) {
                // Matrix right division: A / B = A * B^{-1}
                const DenseMatrix &b = nb::cast<const DenseMatrix &>(k);
                if (b.nrows() != b.ncols())
                    throw NonSquareMatrixError_("Matrix must be square for division");
                DenseMatrix b_inv(b.ncols(), b.nrows());
                inverse_LU(b, b_inv);
                DenseMatrix result(a.nrows(), b_inv.ncols());
                a.mul_matrix(b_inv, result);
                return nb::cast(result);
            }
            if (nb::isinstance<Basic>(k)) {
                DenseMatrix result(a.nrows(), a.ncols());
                a.mul_scalar(div(one, nb::cast<RCP<const Basic>>(k)), result);
                return nb::cast(result);
            }
            if (PyLong_Check(k.ptr())) {
                DenseMatrix result(a.nrows(), a.ncols());
                a.mul_scalar(div(one, SymEngine::integer(nb::cast<long>(k))), result);
                return nb::cast(result);
            }
            if (PyFloat_Check(k.ptr())) {
                DenseMatrix result(a.nrows(), a.ncols());
                a.mul_scalar(div(one, SymEngine::real_double(nb::cast<double>(k))), result);
                return nb::cast(result);
            }
            return nb::not_implemented();
        })
        .def("__neg__", [](const DenseMatrix &a) {
            DenseMatrix result(a.nrows(), a.ncols());
            a.mul_scalar(SymEngine::integer(-1), result);
            return result;
        })
        .def("__pos__", [](const DenseMatrix &a) {
            return DenseMatrix(a);
        })
        .def("__abs__", [](const DenseMatrix &a) {
            DenseMatrix result(a.nrows(), a.ncols());
            for (unsigned i = 0; i < a.nrows(); ++i)
                for (unsigned j = 0; j < a.ncols(); ++j)
                    result.set(i, j, SymEngine::abs(a.get(i, j)));
            return result;
        });

    m.def("zeros", [](unsigned rows, unsigned cols) -> DenseMatrix {
        DenseMatrix A(rows, cols);
        SymEngine::zeros(A);
        return A;
    }, nb::arg("rows"), nb::arg("cols"));

    m.def("zeros", [](unsigned n) -> DenseMatrix {
        DenseMatrix A(n, n);
        SymEngine::zeros(A);
        return A;
    }, nb::arg("n"));

    m.def("ones", [](unsigned rows, unsigned cols) -> DenseMatrix {
        DenseMatrix A(rows, cols);
        SymEngine::ones(A);
        return A;
    }, nb::arg("rows"), nb::arg("cols"));

    m.def("ones", [](unsigned n) -> DenseMatrix {
        DenseMatrix A(n, n);
        SymEngine::ones(A);
        return A;
    }, nb::arg("n"));

    m.def("eye", [](unsigned n, int k) -> DenseMatrix {
        DenseMatrix A(n, n);
        SymEngine::eye(A, k);
        return A;
    }, nb::arg("n"), nb::arg("k") = 0);

    m.def("eye", [](unsigned n, unsigned m_val, int k) -> DenseMatrix {
        DenseMatrix A(n, m_val);
        SymEngine::zeros(A);
        unsigned max_ones;
        if (k >= 0) {
            max_ones = std::min(n, m_val > (unsigned)k ? m_val - (unsigned)k : 0u);
        } else {
            unsigned ak = (unsigned)(-k);
            max_ones = std::min(n > ak ? n - ak : 0u, m_val);
        }
        for (unsigned i = 0; i < max_ones; ++i) {
            unsigned row = k >= 0 ? i : i + (unsigned)(-k);
            unsigned col = k >= 0 ? i + (unsigned)k : i;
            A.set(row, col, one);
        }
        return A;
    }, nb::arg("n"), nb::arg("m"), nb::arg("k") = 0);

    m.def("diag", [](const vec_basic &v, int k) -> DenseMatrix {
        unsigned n = (unsigned)v.size() + (unsigned)std::abs(k);
        DenseMatrix A(n, n);
        SymEngine::zeros(A);
        for (unsigned i = 0; i < (unsigned)v.size(); ++i) {
            unsigned row = k >= 0 ? i : i + (unsigned)(-k);
            unsigned col = k >= 0 ? i + (unsigned)k : i;
            A.set(row, col, v[i]);
        }
        return A;
    }, nb::arg("values"), nb::arg("k") = 0);

    m.def("diag", [](nb::args args) -> DenseMatrix {
        vec_basic v;
        for (size_t i = 0; i < nb::len(args); ++i) {
            v.push_back(nb::cast<RCP<const Basic>>(args[i]));
        }
        unsigned n = (unsigned)v.size();
        DenseMatrix A(n, n);
        SymEngine::zeros(A);
        for (unsigned i = 0; i < n; ++i) {
            A.set(i, i, v[i]);
        }
        return A;
    });

    // Register custom Python exception types
    nb::exception<NonSquareMatrixError_>(m, "NonSquareMatrixError", PyExc_ValueError);
    nb::exception<ShapeError_>(m, "ShapeError", PyExc_ValueError);

    nb::register_exception_translator(
        [](const std::exception_ptr &p, void *) {
            try {
                if (p) std::rethrow_exception(p);
            } catch (const NonSquareMatrixError_ &) {
                throw;  // Let nanobind handle via nb::exception registration
            } catch (const ShapeError_ &) {
                throw;  // Let nanobind handle via nb::exception registration
            } catch (const std::runtime_error &e) {
                PyErr_SetString(PyExc_RuntimeError, e.what());
            } catch (const std::invalid_argument &e) {
                PyErr_SetString(PyExc_ValueError, e.what());
            }
        }, nullptr);

    // --- Phase 21: Native lambda-double evaluator ---
    auto pyClassLambdaRealDouble = nb::class_<PyLambdaRealDouble>(m, "_LambdaRealDouble")
        .def("__init__", [](PyLambdaRealDouble *self,
                            const std::vector<RCP<const Basic>> &inputs,
                            const std::vector<RCP<const Basic>> &outputs,
                            bool cse) {
            new (self) PyLambdaRealDouble(inputs, outputs, cse);
        }, nb::arg("inputs"), nb::arg("outputs"), nb::arg("cse") = false)
        .def("n_inputs", &PyLambdaRealDouble::n_inputs)
        .def("n_outputs", &PyLambdaRealDouble::n_outputs)
        .def("call", [](PyLambdaRealDouble &self,
                        nb::ndarray<double, nb::ndim<1>, nb::c_contig> inp,
                        nb::ndarray<double, nb::ndim<1>, nb::c_contig> out) {
            if ((size_t)inp.shape(0) != self.n_inputs())
                throw nb::value_error(
                    ("Expected " + std::to_string(self.n_inputs()) +
                     " input values, got " + std::to_string(inp.shape(0))).c_str());
            if ((size_t)out.shape(0) != self.n_outputs())
                throw nb::value_error(
                    ("Expected " + std::to_string(self.n_outputs()) +
                     " output slots, got " + std::to_string(out.shape(0))).c_str());
            try {
                self.call(out.data(), inp.data());
            } catch (const std::exception &e) {
                PyErr_SetString(PyExc_RuntimeError, e.what());
                throw nb::python_error();
            }
        }, nb::arg("inp"), nb::arg("out"))
        .def("call_ptr", [](PyLambdaRealDouble &self, uint64_t inp_ptr, uint64_t out_ptr) {
            self.call(reinterpret_cast<double *>(out_ptr),
                      reinterpret_cast<double *>(inp_ptr));
        }, nb::arg("inp_ptr"), nb::arg("out_ptr"))
        .def("call_vector", [](PyLambdaRealDouble &self,
                               const std::vector<double> &inp) -> std::vector<double> {
            if (inp.size() != self.n_inputs())
                throw nb::value_error(
                    ("Expected " + std::to_string(self.n_inputs()) +
                     " input values, got " + std::to_string(inp.size())).c_str());
            std::vector<double> out(self.n_outputs());
            try {
                self.call(out.data(), inp.data());
            } catch (const std::exception &e) {
                PyErr_SetString(PyExc_RuntimeError, e.what());
                throw nb::python_error();
            }
            return out;
        }, nb::arg("inp"));
    bind_lambdify_ndarray_api(pyClassLambdaRealDouble);

#ifdef HAVE_SYMENGINE_LLVM
    auto pyClassLLVMDouble = nb::class_<PyLLVMDouble>(m, "_LLVMDouble")
        .def("__init__", [](PyLLVMDouble *self,
                            const std::vector<RCP<const Basic>> &inputs,
                            const std::vector<RCP<const Basic>> &outputs,
                            bool cse,
                            unsigned opt_level) {
            new (self) PyLLVMDouble(inputs, outputs, cse, opt_level);
        }, nb::arg("inputs"), nb::arg("outputs"),
           nb::arg("cse") = false, nb::arg("opt_level") = 3)
        .def("__init__", [](PyLLVMDouble *self,
                            nb::bytes blob,
                            size_t n_inputs,
                            size_t n_outputs) {
            std::string s(reinterpret_cast<const char*>(blob.data()), blob.size());
            new (self) PyLLVMDouble(s, n_inputs, n_outputs);
        }, nb::arg("blob"), nb::arg("n_inputs"), nb::arg("n_outputs"))
        .def("n_inputs", &PyLLVMDouble::n_inputs)
        .def("n_outputs", &PyLLVMDouble::n_outputs)
        .def("call", [](PyLLVMDouble &self,
                        nb::ndarray<double, nb::ndim<1>, nb::c_contig> inp,
                        nb::ndarray<double, nb::ndim<1>, nb::c_contig> out) {
            if ((size_t)inp.shape(0) != self.n_inputs())
                throw nb::value_error(
                    ("Expected " + std::to_string(self.n_inputs()) +
                     " input values, got " + std::to_string(inp.shape(0))).c_str());
            if ((size_t)out.shape(0) != self.n_outputs())
                throw nb::value_error(
                    ("Expected " + std::to_string(self.n_outputs()) +
                     " output slots, got " + std::to_string(out.shape(0))).c_str());
            try {
                self.call(out.data(), inp.data());
            } catch (const std::exception &e) {
                PyErr_SetString(PyExc_RuntimeError, e.what());
                throw nb::python_error();
            }
        }, nb::arg("inp"), nb::arg("out"))
        .def("call_ptr", [](PyLLVMDouble &self, uint64_t inp_ptr, uint64_t out_ptr) {
            self.call(reinterpret_cast<double *>(out_ptr),
                      reinterpret_cast<double *>(inp_ptr));
        }, nb::arg("inp_ptr"), nb::arg("out_ptr"))
        .def("call_vector", [](PyLLVMDouble &self,
                               const std::vector<double> &inp) -> std::vector<double> {
            if (inp.size() != self.n_inputs())
                throw nb::value_error(
                    ("Expected " + std::to_string(self.n_inputs()) +
                     " input values, got " + std::to_string(inp.size())).c_str());
            std::vector<double> out(self.n_outputs());
            try {
                self.call(out.data(), inp.data());
            } catch (const std::exception &e) {
                PyErr_SetString(PyExc_RuntimeError, e.what());
                throw nb::python_error();
            }
            return out;
        }, nb::arg("inp"))
        .def("dumps", [](PyLLVMDouble &self) -> nb::bytes {
            const std::string &s = self.dumps();
            return nb::bytes(s.data(), s.size());
        });
    bind_lambdify_ndarray_api(pyClassLLVMDouble);
#endif

    // --- Generated binding code (from litgen) ---
#include "symengine_pydef.cpp"

    // Restore is_* member methods excluded by fn_exclude (which was needed
    // to suppress the free is_* functions from number.h that return tribool).
    pyClassInteger
        .def("is_zero", &Integer::is_zero)
        .def("is_minus_one", &Integer::is_minus_one)
        .def("is_positive", &Integer::is_positive)
        .def("is_negative", &Integer::is_negative)
        .def("is_complex", &Integer::is_complex);
    pyClassRational
        .def("is_zero", &Rational::is_zero)
        .def("is_minus_one", &Rational::is_minus_one)
        .def("is_positive", &Rational::is_positive)
        .def("is_negative", &Rational::is_negative)
        .def("is_complex", &Rational::is_complex);
    pyClassSymbol
        .def_prop_ro("name", [](const Symbol &s) -> std::string {
            return s.get_name();
        });
    pyClassDummy
        .def_prop_ro("dummy_index", [](const Dummy &d) -> size_t {
            return d.get_index();
        });

    // --- Hand-written direct RCP API ---
    // These functions take/return RCP<const Basic> directly.
    // The type_caster<RCP<T>> from nanobind_symengine.h handles conversion.

    // Factory functions
    m.def("symbol", [](const std::string &n) -> RCP<const Basic> {
        return SymEngine::symbol(n);
    }, nb::arg("name"));

    m.def("integer", [](long long i) -> RCP<const Basic> {
        return SymEngine::integer(i);
    }, nb::arg("i"));
    m.def("integer", [](const std::string &s) -> RCP<const Basic> {
        return SymEngine::integer(integer_class(s));
    }, nb::arg("s"));

    // expand
    m.def("expand", [](const RCP<const Basic> &x, bool deep) -> RCP<const Basic> {
        return SymEngine::expand(x, deep);
    }, nb::arg("expr"), nb::arg("deep") = true);

    // Simple direct-RCP functions (trig, hyperbolic, special, relational).
    // Generated from binding-spec/api.yaml by tools.binding_codegen.
    #include "symengine_simple_funcs.inc"

    m.def("logical_and", [](nb::args args) -> RCP<const Boolean> {
        set_boolean s;
        for (auto a : args) {
            if (!nb::isinstance<Boolean>(a))
                throw nb::type_error("logical_and: all arguments must be Boolean");
            s.insert(nb::cast<RCP<const Boolean>>(a));
        }
        return SymEngine::logical_and(s);
    }, "Create a logical AND of conditions");

    m.def("logical_or", [](nb::args args) -> RCP<const Boolean> {
        set_boolean s;
        for (auto a : args) {
            if (!nb::isinstance<Boolean>(a))
                throw nb::type_error("logical_or: all arguments must be Boolean");
            s.insert(nb::cast<RCP<const Boolean>>(a));
        }
        return SymEngine::logical_or(s);
    }, "Create a logical OR of conditions");

    m.def("logical_not", [](const RCP<const Boolean> &condition) -> RCP<const Boolean> {
        return SymEngine::logical_not(condition);
    }, nb::arg("condition"), "Create a logical NOT of a condition");

    m.def("logical_xor", [](nb::args args) -> RCP<const Boolean> {
        vec_boolean v;
        for (auto a : args) {
            if (!nb::isinstance<Boolean>(a))
                throw nb::type_error("logical_xor: all arguments must be Boolean");
            v.push_back(nb::cast<RCP<const Boolean>>(a));
        }
        return SymEngine::logical_xor(v);
    }, "Create a logical XOR of conditions");

    m.def("contains", [](const RCP<const Basic> &expr, const RCP<const Set> &set) -> RCP<const Boolean> {
        return SymEngine::contains(expr, set);
    }, nb::arg("expr"), nb::arg("set"), "Check if expr is contained in set");

    // Number theory functions (direct RCP, taking Integer references)
    m.def("factorial", [](unsigned long n) -> RCP<const Basic> {
        return SymEngine::factorial(n);
    }, nb::arg("n"));
    m.def("binomial", [](const RCP<const Integer> &n, unsigned long k)
                        -> RCP<const Basic> {
        return SymEngine::binomial(*n, k);
    }, nb::arg("n"), nb::arg("k"));
    m.def("fibonacci", [](unsigned long n) -> RCP<const Basic> {
        return SymEngine::fibonacci(n);
    }, nb::arg("n"));
    m.def("lucas", [](unsigned long n) -> RCP<const Basic> {
        return SymEngine::lucas(n);
    }, nb::arg("n"));

    m.def("mod", [](const RCP<const Integer> &n, const RCP<const Integer> &d)
                    -> RCP<const Basic> {
        if (d->is_zero()) throw std::runtime_error("ZeroDivisionError: modulo by zero");
        return SymEngine::mod(*n, *d);
    }, nb::arg("n"), nb::arg("d"));
    m.def("quotient", [](const RCP<const Integer> &n, const RCP<const Integer> &d)
                       -> RCP<const Basic> {
        if (d->is_zero()) throw std::runtime_error("ZeroDivisionError: integer division by zero");
        return SymEngine::quotient(*n, *d);
    }, nb::arg("n"), nb::arg("d"));
    m.def("mod_f", [](const RCP<const Integer> &n, const RCP<const Integer> &d)
                    -> RCP<const Basic> {
        if (d->is_zero()) throw std::runtime_error("ZeroDivisionError: modulo by zero");
        return SymEngine::mod_f(*n, *d);
    }, nb::arg("n"), nb::arg("d"));
    m.def("quotient_f", [](const RCP<const Integer> &n, const RCP<const Integer> &d)
                       -> RCP<const Basic> {
        if (d->is_zero()) throw std::runtime_error("ZeroDivisionError: integer division by zero");
        return SymEngine::quotient_f(*n, *d);
    }, nb::arg("n"), nb::arg("d"));
    m.def("bernoulli", [](unsigned long n) -> RCP<const Number> {
        return SymEngine::bernoulli(n);
    }, nb::arg("n"));
    m.def("harmonic", [](unsigned long n, long m_val) -> RCP<const Number> {
        return SymEngine::harmonic(n, m_val);
    }, nb::arg("n"), nb::arg("m") = 1L);

    // Extended GCD: returns (g, s, t) where g = s*a + t*b
    m.def("gcd_ext", [](const RCP<const Integer> &a, const RCP<const Integer> &b)
                      -> std::tuple<RCP<const Basic>, RCP<const Basic>, RCP<const Basic>> {
        RCP<const Integer> g, s, t;
        SymEngine::gcd_ext(outArg(g), outArg(s), outArg(t), *a, *b);
        return {g, s, t};
    }, nb::arg("a"), nb::arg("b"));

    // Quotient and modulo (round toward zero): returns (q, r)
    m.def("quotient_mod", [](const RCP<const Integer> &a, const RCP<const Integer> &b)
                            -> std::tuple<RCP<const Basic>, RCP<const Basic>> {
        if (b->is_zero()) throw std::runtime_error("ZeroDivisionError: integer division by zero");
        RCP<const Integer> q, r;
        SymEngine::quotient_mod(outArg(q), outArg(r), *a, *b);
        return {q, r};
    }, nb::arg("a"), nb::arg("b"));

    // Quotient and modulo (floor division): returns (q, r)
    m.def("quotient_mod_f", [](const RCP<const Integer> &a, const RCP<const Integer> &b)
                              -> std::tuple<RCP<const Basic>, RCP<const Basic>> {
        if (b->is_zero()) throw std::runtime_error("ZeroDivisionError: integer division by zero");
        RCP<const Integer> q, r;
        SymEngine::quotient_mod_f(outArg(q), outArg(r), *a, *b);
        return {q, r};
    }, nb::arg("a"), nb::arg("b"));

    // Fibonacci n and n-1: returns (F_n, F_{n-1})
    m.def("fibonacci2", [](unsigned long n) -> std::tuple<RCP<const Basic>, RCP<const Basic>> {
        RCP<const Integer> g, s;
        SymEngine::fibonacci2(outArg(g), outArg(s), n);
        return {g, s};
    }, nb::arg("n"));

    // Lucas n and n-1: returns (L_n, L_{n-1})
    m.def("lucas2", [](unsigned long n) -> std::tuple<RCP<const Basic>, RCP<const Basic>> {
        RCP<const Integer> g, s;
        SymEngine::lucas2(outArg(g), outArg(s), n);
        return {g, s};
    }, nb::arg("n"));

    // Chinese Remainder Theorem: returns result or None
    m.def("crt", [](const std::vector<RCP<const Integer>> &rem,
                    const std::vector<RCP<const Integer>> &mod) -> nb::object {
        RCP<const Integer> r;
        bool status = SymEngine::crt(outArg(r), rem, mod);
        if (status) return nb::cast(r);
        return nb::none();
    }, nb::arg("rem"), nb::arg("mod"));

    // Prime factor multiplicities: returns dict[Integer, int]
    m.def("prime_factor_multiplicities", [](const RCP<const Integer> &n)
          -> nb::dict {
        map_integer_uint primes;
        SymEngine::prime_factor_multiplicities(primes, *n);
        nb::dict result;
        for (auto &[k, v] : primes) {
            result[nb::cast(k)] = v;
        }
        return result;
    }, nb::arg("n"));

    // integer_nthroot: returns (root, is_exact)
    m.def("integer_nthroot", [](const RCP<const Integer> &a, unsigned long n)
                              -> std::tuple<RCP<const Basic>, bool> {
        RCP<const Integer> r;
        int exact = SymEngine::i_nth_root(outArg(r), *a, n);
        return {r, exact == 1};
    }, nb::arg("a"), nb::arg("n"));

    m.def("is_square", [](const RCP<const Integer> &n) -> bool {
        return SymEngine::perfect_square(*n);
    }, nb::arg("n"));

    m.def("perfect_power", [](const RCP<const Integer> &n) -> bool {
        return SymEngine::perfect_power(*n);
    }, nb::arg("n"));

    m.def("cse", [](const std::vector<RCP<const Basic>> &exprs)
                 -> std::tuple<nb::list, nb::list> {
        vec_pair replacements;
        vec_basic reduced_exprs;
        SymEngine::cse(replacements, reduced_exprs, exprs);
        nb::list repl;
        for (auto &p : replacements) {
            repl.append(nb::make_tuple(p.first, p.second));
        }
        nb::list reduced;
        for (auto &e : reduced_exprs) {
            reduced.append(e);
        }
        return {repl, reduced};
    }, nb::arg("exprs"));

    // Set factory functions
    m.def("finiteset", [](const set_basic &container) -> RCP<const Basic> {
        return SymEngine::finiteset(container);
    }, nb::arg("container"));
    m.def("interval", [](const RCP<const Number> &l, const RCP<const Number> &r,
                          bool left_open, bool right_open) -> RCP<const Basic> {
        return SymEngine::interval(l, r, left_open, right_open);
    }, nb::arg("l"), nb::arg("r"),
       nb::arg("left_open") = false, nb::arg("right_open") = false);
    m.def("interval", [](const RCP<const Basic> &l, const RCP<const Basic> &r,
                          bool left_open, bool right_open) -> RCP<const Basic> {
        if (!is_a_Number(*l) || !is_a_Number(*r))
            throw std::runtime_error("interval arguments must be Numbers");
        auto ln = rcp_static_cast<const Number>(l);
        auto rn = rcp_static_cast<const Number>(r);
        return SymEngine::interval(ln, rn, left_open, right_open);
    }, nb::arg("l"), nb::arg("r"),
       nb::arg("left_open") = false, nb::arg("right_open") = false);
    // Singleton set factories: return the genuine C++ static singletons.
    // The caster's from_cpp provides identity reuse — once a wrapper is
    // attached via set_self_py, every subsequent call returns the same object.
    m.def("emptyset", []() -> RCP<const Basic> {
        return SymEngine::emptyset();
    });
    m.def("universalset", []() -> RCP<const Basic> {
        return SymEngine::universalset();
    });
    m.def("reals", []() -> RCP<const Basic> {
        return SymEngine::reals();
    });
    m.def("rationals", []() -> RCP<const Basic> {
        return SymEngine::rationals();
    });
    m.def("integers", []() -> RCP<const Basic> {
        return SymEngine::integers();
    });
    m.def("complexes", []() -> RCP<const Basic> {
        return SymEngine::complexes();
    });
    m.def("naturals", []() -> RCP<const Basic> {
        return SymEngine::naturals();
    });
    m.def("naturals0", []() -> RCP<const Basic> {
        return SymEngine::naturals0();
    });

    m.def("set_union", [](const std::vector<RCP<const Set>> &sets) -> RCP<const Set> {
        set_set s(sets.begin(), sets.end());
        return SymEngine::set_union(s);
    }, nb::arg("sets"), "Compute the union of a collection of sets");

    m.def("set_intersection", [](const std::vector<RCP<const Set>> &sets) -> RCP<const Set> {
        set_set s(sets.begin(), sets.end());
        return SymEngine::set_intersection(s);
    }, nb::arg("sets"), "Compute the intersection of a collection of sets");

    m.def("set_complement", [](const RCP<const Set> &universe, const RCP<const Set> &container) -> RCP<const Set> {
        return SymEngine::set_complement(universe, container);
    }, nb::arg("universe"), nb::arg("container"), "Compute the complement of container within universe");

    m.def("conditionset", [](const RCP<const Basic> &sym, const RCP<const Boolean> &condition) -> RCP<const Set> {
        return SymEngine::conditionset(sym, condition);
    }, nb::arg("sym"), nb::arg("condition"), "Create a ConditionSet");

    m.def("imageset", [](const RCP<const Basic> &sym, const RCP<const Basic> &expr, const RCP<const Set> &base) -> RCP<const Set> {
        return SymEngine::imageset(sym, expr, base);
    }, nb::arg("sym"), nb::arg("expr"), nb::arg("base"), "Create an ImageSet");

    m.def("solve", [](const RCP<const Basic> &f, const RCP<const Symbol> &sym,
                       const RCP<const Set> &domain) -> RCP<const Set> {
        return SymEngine::solve(f, sym, domain);
    }, nb::arg("f"), nb::arg("sym"), nb::arg("domain") = SymEngine::universalset(),
       "Solve equation f=0 for sym within domain");

    m.def("linsolve", [](const std::vector<RCP<const Basic>> &system,
                          const std::vector<RCP<const Symbol>> &syms) -> std::vector<RCP<const Basic>> {
        return SymEngine::linsolve(system, syms);
    }, nb::arg("system"), nb::arg("syms"),
       "Solve a system of linear equations");

    // Utility functions
    m.def("same_object", [](const RCP<const Basic> &a,
                            const RCP<const Basic> &b){ return a.get() == b.get(); },
        nb::arg("a"), nb::arg("b"));
    m.def("cpp_use_count", [](const RCP<const Basic> &a){ return a->use_count(); },
        nb::arg("a"));

    // Threading stress helper: drop RCPs from C++ worker threads.
    // This forces the intrusive dec_ref (and potential GIL acquire) to happen
    // on non-main threads, exercising the deadlock scenario described in
    // test_threading_stress.py.
    m.def("drop_rcps_on_cpp_threads",
          [](nb::list objects, unsigned int thread_count) {
              if (thread_count == 0) {
                  throw std::invalid_argument("thread_count must be > 0");
              }
              // Copy RCPs from Python list into per-thread C++ vectors.
              // Each copy inc_ref's, so we can clear the Python list first.
              size_t n = nb::len(objects);
              std::vector<std::vector<RCP<const Basic>>> per_thread(thread_count);
              for (size_t i = 0; i < n; ++i) {
                  per_thread[i % thread_count].push_back(
                      nb::cast<RCP<const Basic>>(objects[i]));
              }
              // Drop Python-side references while GIL is still held.
              // Now the only references are in the C++ vectors.
              objects.attr("clear")();
              // Release GIL and spawn C++ worker threads.
              {
                  nb::gil_scoped_release release;
                  std::vector<std::thread> threads;
                  threads.reserve(thread_count);
                  for (unsigned int i = 0; i < thread_count; ++i) {
                      threads.emplace_back([batch = std::move(per_thread[i])]() mutable {
                          batch.clear();  // dec_ref on non-main thread
                      });
                  }
                  for (auto &t : threads) t.join();
              }
          },
          nb::arg("objects"), nb::arg("thread_count") = 4);

    // Constants — return the genuine C++ static singletons.
    m.def("e",    []() -> RCP<const Basic> { return SymEngine::E;    });
    m.def("euler_gamma", []() -> RCP<const Basic> {
        return SymEngine::EulerGamma;
    });
    m.def("I", []() -> RCP<const Basic> { return SymEngine::I; });
    m.def("oo", []() -> RCP<const Number> { return SymEngine::Inf; });
    m.def("cast_to_number", [](const RCP<const Basic> &x) -> RCP<const Number> {
        if (is_a_Number(*x)) return rcp_static_cast<const Number>(x);
        throw std::runtime_error("Not a Number");
    }, nb::arg("x"));
    m.def("zoo", []() -> RCP<const Number> { return SymEngine::ComplexInf; });
    m.def("nan_const", []() -> RCP<const Number> { return SymEngine::Nan; });
    m.def("true_const", []() -> RCP<const Boolean> { return SymEngine::boolTrue; });
    m.def("false_const", []() -> RCP<const Boolean> { return SymEngine::boolFalse; });

    // str: convert Basic to string
    m.def("str", [](const RCP<const Basic> &x) -> std::string {
        std::ostringstream os;
        os << *x;
        return os.str();
    }, nb::arg("expr"));

    // FunctionSymbol factory
    m.def("function_symbol", [](const std::string &name, nb::args args) -> RCP<const Basic> {
        vec_basic v;
        v.reserve(nb::len(args));
        for (size_t i = 0; i < nb::len(args); ++i) {
            v.push_back(nb::cast<RCP<const Basic>>(args[i]));
        }
        return SymEngine::function_symbol(name, v);
    }, "Create a symbolic function with the given name and arguments");

    // diff: symbolic differentiation
    m.def("diff", [](const RCP<const Basic> &expr, const RCP<const Symbol> &sym) -> RCP<const Basic> {
        return SymEngine::diff(expr, sym);
    }, nb::arg("expr"), nb::arg("sym"));

    // xreplace: structural substitution
    m.def("xreplace", [](const RCP<const Basic> &expr, const nb::dict &d) -> RCP<const Basic> {
        map_basic_basic m;
        for (auto item : d) {
            insert(m, nb::cast<RCP<const Basic>>(item.first), nb::cast<RCP<const Basic>>(item.second));
        }
        return SymEngine::xreplace(expr, m);
    }, nb::arg("expr"), nb::arg("subs_dict"));

    // subs: mathematical substitution
    m.def("subs", [](const RCP<const Basic> &expr, const nb::dict &d) -> RCP<const Basic> {
        map_basic_basic m;
        for (auto item : d) {
            insert(m, nb::cast<RCP<const Basic>>(item.first), nb::cast<RCP<const Basic>>(item.second));
        }
        return SymEngine::subs(expr, m);
    }, nb::arg("expr"), nb::arg("subs_dict"));

    // msubs: mathematical substitution (port of sympy.physics.mechanics.msubs)
    m.def("msubs", [](const RCP<const Basic> &expr, const nb::dict &d) -> RCP<const Basic> {
        map_basic_basic m;
        for (auto item : d) {
            insert(m, nb::cast<RCP<const Basic>>(item.first), nb::cast<RCP<const Basic>>(item.second));
        }
        return SymEngine::msubs(expr, m);
    }, nb::arg("expr"), nb::arg("subs_dict"));

    // _make_derivative: factory for Derivative from a list of symbols
    m.def("_make_derivative", [](const RCP<const Basic> &expr,
                                   const std::vector<RCP<const Basic>> &symbols) -> RCP<const Basic> {
        multiset_basic ms(symbols.begin(), symbols.end());
        return Derivative::create(expr, ms);
    }, nb::arg("expr"), nb::arg("symbols"));

    // _make_subs: factory for Subs from expr + dict
    m.def("_make_subs", [](const RCP<const Basic> &expr, const nb::dict &d) -> RCP<const Basic> {
        map_basic_basic m;
        for (auto item : d) {
            insert(m, nb::cast<RCP<const Basic>>(item.first), nb::cast<RCP<const Basic>>(item.second));
        }
        return Subs::create(expr, m);
    }, nb::arg("expr"), nb::arg("subs_dict"));

    // unevaluated_expr factory
    m.def("unevaluated_expr", [](const RCP<const Basic> &arg) -> RCP<const Basic> {
        return SymEngine::unevaluated_expr(arg);
    }, nb::arg("arg"));

    // series: Taylor series expansion
    m.def("series", [](const RCP<const Basic> &ex, const RCP<const Symbol> &var,
                        unsigned int prec) -> RCP<const SeriesCoeffInterface> {
        return SymEngine::series(ex, var, prec);
    }, nb::arg("expr"), nb::arg("var"), nb::arg("prec"));

    // real_double factory
    m.def("real_double", [](double x) -> RCP<const Number> {
        return SymEngine::real_double(x);
    }, nb::arg("x"));

    // Singleton cleanup (shared scaffolding, see nanobind_module_common.h).
    register_singletons();
    mcomm::register_singleton_cleanup(&g_singletons);

    m.attr("have_llvm") =
#ifdef HAVE_SYMENGINE_LLVM
        true;
#else
        false;
#endif
}
