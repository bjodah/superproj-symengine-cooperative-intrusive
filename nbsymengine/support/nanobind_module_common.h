#pragma once

#include <nanobind/nanobind.h>
#include <nanobind/stl/string.h>
#include "nanobind_symengine.h"

#include <symengine/basic.h>
#include <symengine/constants.h>
#include <symengine/sets.h>
#include <symengine/logic.h>

namespace SymEngine {
    extern RCP<const Basic> &i2;
    extern RCP<const Basic> &i3;
    extern RCP<const Basic> &i5;
    extern RCP<const Basic> &im2;
    extern RCP<const Basic> &im3;
    extern RCP<const Basic> &im5;
    extern RCP<const Basic> &sq2;
    extern RCP<const Basic> &sq3;
    extern RCP<const Basic> &sq5;
    extern RCP<const Basic> &C0;
    extern RCP<const Basic> &C1;
    extern RCP<const Basic> &C2;
    extern RCP<const Basic> &C3;
    extern RCP<const Basic> &C4;
    extern RCP<const Basic> &C5;
    extern RCP<const Basic> &C6;
    extern RCP<const Basic> &mC0;
    extern RCP<const Basic> &mC1;
    extern RCP<const Basic> &mC2;
    extern RCP<const Basic> &mC3;
    extern RCP<const Basic> &mC4;
    extern RCP<const Basic> &mC5;
    extern RCP<const Basic> &mC6;
    extern RCP<const BooleanAtom> &boolTrue;
    extern RCP<const BooleanAtom> &boolFalse;
}

#include <cstring>
#include <atomic>
#include <vector>

namespace nb = nanobind;
using namespace SymEngine;

namespace SymEngine::python::module_common {

inline void initialize_intrusive_hooks() {
    static std::atomic<bool> s_python_is_dead{false};
    s_python_is_dead.store(false, std::memory_order_relaxed);
    Py_AtExit([]() noexcept {
        s_python_is_dead.store(true, std::memory_order_relaxed);
    });
    SymEngine::cooperative_intrusive_init(
        [](void *o) noexcept {
            if (s_python_is_dead.load(std::memory_order_relaxed)) return;
            nb::gil_scoped_acquire g;
            Py_INCREF(reinterpret_cast<PyObject *>(o));
        },
        [](void *o) noexcept {
            if (s_python_is_dead.load(std::memory_order_relaxed)) return;
            nb::gil_scoped_acquire g;
            Py_DECREF(reinterpret_cast<PyObject *>(o));
        });
}

inline nb::class_<Basic> bind_basic_common(nb::module_ &m) {
    nb::class_<Basic> cls(m, "Basic",
        nb::intrusive_ptr<Basic>(
            [](Basic *o, PyObject *po) noexcept { o->set_self_external(po); }));

    cls.def("__str__", [](const Basic &b){ return b.__str__(); })
       .def("__hash__", [](const Basic &b){ return b.hash(); })
       .def("__eq__", [](const Basic &a, nb::object b) -> nb::object {
            if (b.is_none()) return nb::cast(false);
            if (!nb::isinstance<Basic>(b)) return nb::not_implemented();
            return nb::cast(eq(a, nb::cast<const Basic &>(b)));
        }, nb::arg("b").none())
       .def("get_args", [](const Basic &b) {
            auto args = b.get_args();
            nb::list result;
            for (auto &a : args) result.append(a);
            return result;
        });

    return cls;
}

inline void seed_common_singletons(std::vector<RCP<const Basic>> &out) {
    if (!out.empty()) return;
    out = {
        SymEngine::zero, SymEngine::one, SymEngine::minus_one, SymEngine::two,
        SymEngine::pi, SymEngine::E, SymEngine::EulerGamma,
        SymEngine::Catalan, SymEngine::GoldenRatio,
        SymEngine::reals(), SymEngine::integers(),
        SymEngine::rationals(), SymEngine::complexes(),
        SymEngine::naturals(), SymEngine::naturals0(),
        SymEngine::emptyset(), SymEngine::universalset(),

        SymEngine::I, SymEngine::Inf, SymEngine::NegInf, SymEngine::ComplexInf, SymEngine::Nan,
        SymEngine::boolTrue, SymEngine::boolFalse,
        SymEngine::i2, SymEngine::i3, SymEngine::i5, SymEngine::im2, SymEngine::im3, SymEngine::im5,
        SymEngine::sq2, SymEngine::sq3, SymEngine::sq5,
        SymEngine::C0, SymEngine::C1, SymEngine::C2, SymEngine::C3, SymEngine::C4, SymEngine::C5, SymEngine::C6,
        SymEngine::mC0, SymEngine::mC1, SymEngine::mC2, SymEngine::mC3, SymEngine::mC4, SymEngine::mC5, SymEngine::mC6,
    };
}

// ---------------------------------------------------------------------------
// Singleton cleanup at interpreter shutdown
// ---------------------------------------------------------------------------
//
// Register a Python atexit callback that detaches Python wrappers from
// the C++ static singletons before the interpreter finalizes.  This
// prevents nanobind's leak checker from seeing live wrappers attached to
// C++ statics at shutdown.
//
// Background: when set_self_external(po) is called on a singleton, it transfers
// ALL existing C++ references to Python references (Py_INCREF per ref).
// This includes the singleton registry RCP ref and any internal SymEngine
// refs (e.g. SymEngine::one may have many internal C++ refs).  The
// wrapper's Python refcount is therefore 1 (creation) + N (transferred
// C++ refs).
//
// The cleanup for each singleton:
//   1. detach_external() atomically resets m_state to C++-owned (refcount 0)
//      and returns the PyObject* wrapper.
//   2. Read Py_REFCNT(o) = R (total Python references to the wrapper).
//   3. inc_ref() × (R + 2) sets the C++ refcount to R + 2, accounting for:
//      R dec_refs from the Py_DECREF loop below,
//      +1 from tp_dealloc (triggered when the wrapper's Python refcount
//      reaches 0 during the Py_DECREF loop),
//      +1 from this entry's g_singletons RCP destructor during C++
//      static destruction.
//   4. Py_DECREF in a loop (R times) releases ALL Python refs, freeing
//      the wrapper when the refcount reaches 0.
//
// If g_singletons contains multiple entries sharing the same raw pointer
// (n_holders > 1), the Python-owned entry accounts for its own RCP
// destructor via the +1 above.  Any additional entries sharing the same
// pointer will hit the else branch (detach_python returns nullptr after
// the first detach), where each does one inc_ref for its own RCP
// destructor.  Total inc_refs = (R+2) + (n_holders-1) = R+1+n_holders,
// which is exactly right: after tp_dealloc (-1) and n_holders RCP
// destructors (-n_holders), the final C++ refcount is R.
//
// After this runs, the C++ singletons are back to C++-owned mode with
// refcount R (a harmless static "leak"), and no Python objects are
// reachable from C++ statics.
inline void register_singleton_cleanup(std::vector<RCP<const Basic>> *singletons) {
    nb::module_::import_("atexit").attr("register")(nb::cpp_function([singletons]() noexcept {
        nb::gil_scoped_acquire g;

        // Clear modules first to deallocate all function objects and defaults
        if (PyObject *sys_modules = PyImport_GetModuleDict()) {
            const char *mod_names[] = { "nbsymengine", "nbsymengine._core", "symengine_manual_ext", "__main__" };
            for (const char *name : mod_names) {
                if (PyObject *mod = PyDict_GetItemString(sys_modules, name)) {
                    if (PyObject *dict = PyModule_GetDict(mod)) {
                        if (PyObject *keys = PyDict_Keys(dict)) {
                            Py_ssize_t len = PyList_Size(keys);
                            for (Py_ssize_t i = 0; i < len; ++i) {
                                PyObject *key = PyList_GetItem(keys, i);
                                if (key) {
                                    const char *key_str = PyUnicode_AsUTF8(key);
                                    if (key_str && std::strcmp(key_str, "__name__") != 0 && std::strcmp(key_str, "__doc__") != 0) {
                                        PyDict_DelItem(dict, key);
                                    }
                                }
                            }
                            Py_DECREF(keys);
                        }
                    }
                }
            }
        }

        for (auto &s : *singletons) {
            if (void *o_void = s->detach_external()) {
                PyObject *o = reinterpret_cast<PyObject *>(o_void);
                nanobind::detail::nb_inst_set_state(o, true, false);
                Py_ssize_t cnt = Py_REFCNT(o);
                for (Py_ssize_t i = 0; i < cnt + 2; i++) {
                    s->inc_ref();
                }
                for (Py_ssize_t i = 0; i < cnt; i++) {
                    Py_DECREF(o);
                }
            } else {
                s->inc_ref();
            }
        }
    }));
}

} // namespace SymEngine::python::module_common
