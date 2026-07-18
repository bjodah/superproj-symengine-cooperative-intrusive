#pragma once
#include <nanobind/nanobind.h>
#include <symengine/basic.h>
#include <symengine/symengine_rcp.h>

#include <type_traits>

// Free helpers so call sites read uniformly (and a future ref-like usage works).
namespace SymEngine {
inline void inc_ref(const Basic *o) noexcept { if (o) o->inc_ref(); }
inline void dec_ref(const Basic *o) noexcept { if (o && o->dec_ref()) delete o; }
}

namespace nanobind::detail {

// Caster for RCP<T> (and, via const, RCP<const T>).
// nanobind's make_caster<const T> provides operator T*() (const is stripped),
// so we cast through std::remove_const_t<T>* to match.
template <typename T> struct type_caster<SymEngine::RCP<T>> {
    using U = std::remove_const_t<T>;
    using Caster = make_caster<T>;
    NB_TYPE_CASTER(SymEngine::RCP<T>, Caster::Name)

    bool from_python(handle src, uint8_t flags, cleanup_list *cl) noexcept {
        Caster caster;
        if (!caster.from_python(src, flags, cl)) return false;
        // Building an RCP<T> from the T* increments the intrusive count.
        value = SymEngine::RCP<T>(caster.operator U *());
        return true;
    }

    static handle from_cpp(const SymEngine::RCP<T> &v, rv_policy policy,
                           cleanup_list *cl) noexcept {
        if (!v.get()) return none().release();
        // Identity reuse: if this object already has a Python wrapper, return it.
        if constexpr (std::is_base_of_v<SymEngine::Basic, U>) {
            if (void *o = v->self_external())
                return handle(reinterpret_cast<PyObject *>(o)).inc_ref();
        }
        return Caster::from_cpp(v.get(), policy, cl);
    }
};

} // namespace nanobind::detail
