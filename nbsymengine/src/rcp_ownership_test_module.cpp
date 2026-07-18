// Phase 4 hand-written nanobind module for SymEngine ownership validation.
//
// This module binds the root Basic as intrusive, plus a few concrete classes
// and factory functions, to prove that direct nanobind ownership of
// SymEngine::RCP<const Basic> works end-to-end.
//
// Must be built against a symengine library configured with
// -DSYMENGINE_RCP_BACKEND=cooperative_intrusive.

#include <nanobind/nanobind.h>
#include <nanobind/stl/string.h>
#include "nanobind_symengine.h"
#include "nanobind_module_common.h"

#include <symengine/symbol.h>
#include <symengine/integer.h>
#include <symengine/add.h>
#include <symengine/mul.h>
#include <symengine/pow.h>
#include <symengine/constants.h>
#include <symengine/sets.h>

#include <vector>

namespace nb = nanobind;
using namespace SymEngine;
namespace mcomm = SymEngine::python::module_common;

// Singleton registry: tracks every static singleton whose Python wrapper has
// been (or may be) created, so the atexit cleanup can detach them before
// interpreter finalization.  Design (A) from NextPhase04 — a single explicit
// list kept in one place.
static std::vector<RCP<const Basic>> g_singletons;

// Private test hook used by CI to prove that real leaks are still surfaced by
// nanobind after the shutdown-fix work.
static std::vector<RCP<const Basic>> g_intentional_leaks;

NB_MODULE(symengine_manual_ext, m) {
    // Install GIL-guarded intrusive hooks (shared scaffolding, see nanobind_module_common.h).
    mcomm::initialize_intrusive_hooks();

    // Root class — intrusive ownership for Basic hierarchy (shared scaffolding).
    auto basic = mcomm::bind_basic_common(m);

    // Concrete subclasses so RTTI downcasting has targets.
    nb::class_<Symbol, Basic>(m, "Symbol")
        .def("get_name", &Symbol::get_name);

    nb::class_<Number, Basic>(m, "Number");

    nb::class_<Integer, Number>(m, "Integer")
        .def("as_int", &Integer::as_int);

    nb::class_<Constant, Basic>(m, "Constant")
        .def("get_name", &Constant::get_name);

    nb::class_<Add, Basic>(m, "Add");
    nb::class_<Mul, Basic>(m, "Mul");
    nb::class_<Pow, Basic>(m, "Pow");

    // Factory functions returning RCP<const Basic> (caster: C++ -> Python).
    m.def("symbol", [](const std::string &n) -> RCP<const Basic> {
        return SymEngine::symbol(n);
    });
    m.def("integer", [](long long i) -> RCP<const Basic> {
        return SymEngine::integer(i);
    });
    m.def("integer", [](const std::string &s) -> RCP<const Basic> {
        return SymEngine::integer(integer_class(s));
    });

    // Arithmetic functions taking RCP<const Basic> (caster: Python -> C++).
    m.def("add", [](const RCP<const Basic> &a, const RCP<const Basic> &b)
                     -> RCP<const Basic> { return SymEngine::add(a, b); });
    m.def("sub", [](const RCP<const Basic> &a, const RCP<const Basic> &b)
                     -> RCP<const Basic> { return SymEngine::sub(a, b); });
    m.def("mul", [](const RCP<const Basic> &a, const RCP<const Basic> &b)
                     -> RCP<const Basic> { return SymEngine::mul(a, b); });
    m.def("div", [](const RCP<const Basic> &a, const RCP<const Basic> &b)
                     -> RCP<const Basic> { return SymEngine::div(a, b); });
    m.def("pow", [](const RCP<const Basic> &a, const RCP<const Basic> &b)
                     -> RCP<const Basic> { return SymEngine::pow(a, b); });
    m.def("neg", [](const RCP<const Basic> &a) -> RCP<const Basic> {
        return SymEngine::neg(a);
    });

    // Utility functions for testing identity, refcounts, etc.
    m.def("same_object", [](const RCP<const Basic> &a,
                            const RCP<const Basic> &b){ return a.get() == b.get(); });
    m.def("cpp_use_count", [](const RCP<const Basic> &a){ return a->use_count(); });
    m.def("_leak_symbol_for_test", []() -> RCP<const Basic> {
        auto leaked = SymEngine::symbol("__intentional_leak__");
        g_intentional_leaks.push_back(leaked);
        return leaked;
    });

    // Constants — return the genuine C++ static singletons.  The caster's
    // from_cpp already provides identity reuse: once a wrapper is attached via
    // set_self_py, every subsequent call returns the same Python object.
    m.def("zero", []() -> RCP<const Basic> { return SymEngine::zero; });
    m.def("one",  []() -> RCP<const Basic> { return SymEngine::one;  });
    m.def("pi",   []() -> RCP<const Basic> { return SymEngine::pi;   });
    m.def("euler_gamma", []() -> RCP<const Basic> {
        return SymEngine::EulerGamma;
    });

    // Set singletons — return the genuine C++ static singletons from sets.h.
    m.def("reals", []() -> RCP<const Basic> { return SymEngine::reals(); });
    m.def("integers", []() -> RCP<const Basic> { return SymEngine::integers(); });
    m.def("rationals", []() -> RCP<const Basic> { return SymEngine::rationals(); });
    m.def("complexes", []() -> RCP<const Basic> { return SymEngine::complexes(); });
    m.def("naturals", []() -> RCP<const Basic> { return SymEngine::naturals(); });
    m.def("naturals0", []() -> RCP<const Basic> { return SymEngine::naturals0(); });
    m.def("emptyset", []() -> RCP<const Basic> { return SymEngine::emptyset(); });
    m.def("universalset", []() -> RCP<const Basic> {
        return SymEngine::universalset();
    });

    // expand function
    m.def("expand", [](const RCP<const Basic> &x, bool deep) -> RCP<const Basic> {
        return SymEngine::expand(x, deep);
    }, nb::arg("expr"), nb::arg("deep") = true);

    // Singleton cleanup (shared scaffolding, see nanobind_module_common.h).
    mcomm::seed_common_singletons(g_singletons);
    mcomm::register_singleton_cleanup(&g_singletons);
}
