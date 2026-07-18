#include "perl_symengine.h"

#include <symengine/add.h>
#include <symengine/constants.h>
#include <symengine/functions.h>
#include <symengine/integer.h>
#include <symengine/mul.h>
#include <symengine/pow.h>
#include <symengine/symbol.h>

#include <cstdio>
#include <cstdlib>
#include <stdexcept>
#include <string>
#include <vector>

#if !defined(WITH_SYMENGINE_COOPERATIVE_INTRUSIVE_RCP)
#error "The SymEngine Perl extension requires SymEngine built with " \
       "SYMENGINE_RCP_BACKEND=cooperative_intrusive (the raw-pointer holder " \
       "relies on cooperative externalization to retain ownership)."
#endif

using SymEngine::Basic;
using SymEngine::RCP;

namespace {
// Set true while the Perl interpreter is being torn down (registered via
// call_atexit).  While set, the cooperative hooks become no-ops and DESTROY
// stops deleting C++ objects, so that neither side touches the other across
// interpreter/static-destruction ordering.
bool g_perl_destructing = false;

// Raw pointers to the C++ static singletons.  These are the only objects that
// can remain external-owned (pinned by SymEngine statics) once every Perl
// reference is gone, so they need explicit teardown reconciliation.
std::vector<const Basic *> g_singletons;

bool debug_enabled()
{
    static int v = []{ const char *e = std::getenv("SYMENGINE_PERL_DEBUG");
                       return e && *e && *e != '0'; }();
    return v;
}
} // namespace

#if defined(WITH_SYMENGINE_COOPERATIVE_INTRUSIVE_RCP)
// Cooperative-ownership hooks: in external-owned mode the SymEngine counter
// routes every inc_ref()/dec_ref() into the Perl scalar that anchors the
// wrapper.  The object pointer handed to set_self_external() is the *inner*
// (blessed) SV, so the SymEngine reference count and the Perl SvREFCNT track
// the same lifetime.
//
// Once g_perl_destructing is set the hooks become inert: C++ static
// destructors of SymEngine singletons run *after* the Perl interpreter has
// been torn down, so they must not touch (freed) Perl scalars.  The flag is a
// plain C++ global, safe to read even after the interpreter is gone.
static void symengine_perl_inc_hook(void *object) noexcept
{
    if (g_perl_destructing)
        return;
    SvREFCNT_inc(reinterpret_cast<SV *>(object));
}

static void symengine_perl_dec_hook(void *object) noexcept
{
    if (g_perl_destructing)
        return;
    SvREFCNT_dec(reinterpret_cast<SV *>(object));
}

static void seed_singletons()
{
    if (!g_singletons.empty())
        return;
    const RCP<const Basic> seeds[] = {
        SymEngine::zero, SymEngine::one, SymEngine::minus_one, SymEngine::two,
        SymEngine::I, SymEngine::pi, SymEngine::E, SymEngine::EulerGamma,
        SymEngine::Catalan, SymEngine::GoldenRatio,
        SymEngine::Inf, SymEngine::NegInf, SymEngine::ComplexInf, SymEngine::Nan,
    };
    for (const auto &s : seeds)
        g_singletons.push_back(s.get());
}

// Reconcile the externally-owned SymEngine singletons back to plain C++-owned
// (inline) reference counting before the interpreter finishes tearing down.
//
// By the time this runs (Perl's call_atexit, see below) the program's
// lexicals are already gone, so the only references left to a singleton's
// wrapper are the C++ static RCPs that pinned it (SvREFCNT(inner) == that
// count).  detach_external() flips the counter back to inline mode (count 0)
// and inc_ref() replays that count, so the SymEngine static destructors
// (ConstantInitializer::~ConstantInitializer) delete the objects exactly as
// they would without any Perl involvement.  The wrapper SVs themselves are
// reclaimed by Perl's own global-destruction sweep.
static void reconcile_singletons(pTHX)
{
    for (const Basic *p : g_singletons) {
        void *ext = p->self_external();
        if (ext == nullptr)
            continue; // never wrapped from Perl -> still inline, nothing to do
        SV *inner = reinterpret_cast<SV *>(ext);
        long count = (long) SvREFCNT(inner);
        if (debug_enabled())
            std::fprintf(stderr, "[se-perl reconcile] p=%p inner=%p R=%ld\n",
                         (const void *) p, (void *) inner, count);
        p->detach_external();
        for (long i = 0; i < count; ++i)
            p->inc_ref();
    }
}

// Registered with Perl's call_atexit; runs during perl_destruct, after the
// main program's pad (and its lexicals) has been released.
static void symengine_perl_cleanup(pTHX_ void * /*ptr*/)
{
    reconcile_singletons(aTHX);
    g_perl_destructing = true;
}
#endif

namespace SymEnginePerl {

void initialize()
{
#if defined(WITH_SYMENGINE_COOPERATIVE_INTRUSIVE_RCP)
    SymEngine::cooperative_intrusive_init(symengine_perl_inc_hook,
                                          symengine_perl_dec_hook);
    seed_singletons();
    call_atexit(symengine_perl_cleanup, nullptr);
#endif
}

static BasicHolder *holder_from_sv(SV *sv)
{
    if (!sv_isobject(sv) || !sv_derived_from(sv, "SymEngine::Basic")) {
        throw std::invalid_argument("expected a SymEngine::Basic object");
    }
    SV *inner = SvRV(sv);
    auto *holder = INT2PTR(BasicHolder *, SvIV(inner));
    if (holder == nullptr) {
        throw std::runtime_error("SymEngine::Basic object has no holder");
    }
    return holder;
}

SV *wrap_basic(const RCP<const Basic> &value)
{
    if (value.is_null()) {
        return &PL_sv_undef;
    }

    const Basic *p = value.get();

#if defined(WITH_SYMENGINE_COOPERATIVE_INTRUSIVE_RCP)
    // Identity reuse: if this C++ object already owns a Perl wrapper, return a
    // fresh Perl reference to the *same* inner SV instead of minting a second
    // wrapper.  newRV_inc bumps SvREFCNT(inner), i.e. takes one cooperative
    // reference; the incoming `value` RCP releases its own reference when it
    // dies, so the net effect is one durable Perl reference.
    if (void *ext = p->self_external()) {
        SV *inner = reinterpret_cast<SV *>(ext);
        return newRV_inc(inner);
    }
#endif

    auto *holder = new BasicHolder{p};
    SV *inner = newSViv(0);
    SV *ref = newRV_noinc(inner);
    sv_setiv(inner, PTR2IV(holder));
    sv_bless(ref, gv_stashpv("SymEngine::Basic", GV_ADD));

#if defined(WITH_SYMENGINE_COOPERATIVE_INTRUSIVE_RCP)
    // Hand the object off to cooperative ownership.  This replays the current
    // C++ reference count as SvREFCNT increments on `inner`, so every live
    // RCP<const Basic> (including `value` and the caller's temporaries) now
    // pins the inner SV until it is dropped.
    p->set_self_external(inner);
#endif

    return ref;
}

SV *wrap_basic_perl_owned(const RCP<const Basic> &value)
{
    return wrap_basic(value);
}

RCP<const Basic> unwrap_basic(SV *sv)
{
    const Basic *p = holder_from_sv(sv)->ptr;
    // Rebuilding an RCP from the raw pointer takes one cooperative reference
    // (SvREFCNT_inc on the inner SV in external-owned mode), keeping the
    // wrapper alive for as long as the returned RCP lives.
    return SymEngine::rcp(p);
}

std::string stringify(SV *sv)
{
    return holder_from_sv(sv)->ptr->__str__();
}

bool equals(SV *left, SV *right)
{
    return SymEngine::eq(*holder_from_sv(left)->ptr, *holder_from_sv(right)->ptr);
}

bool same_object(SV *left, SV *right)
{
    return holder_from_sv(left)->ptr == holder_from_sv(right)->ptr;
}

unsigned int cpp_use_count(SV *sv)
{
    // Note: in external-owned mode use_count() is 0 by design (the foreign
    // runtime holds the live references); see perl_refcount for the Perl side.
    return holder_from_sv(sv)->ptr->use_count();
}

unsigned int perl_refcount(SV *sv)
{
    return static_cast<unsigned int>(SvREFCNT(SvRV(sv)));
}

bool is_external_owned(SV *sv)
{
    return holder_from_sv(sv)->ptr->is_external_owned();
}

void destroy_basic(SV *sv)
{
    SV *inner = SvRV(sv);
    auto *holder = INT2PTR(BasicHolder *, SvIV(inner));
    if (holder == nullptr) {
        return;
    }
    const Basic *p = holder->ptr;
    delete holder;
    sv_setiv(inner, 0);

#if defined(WITH_SYMENGINE_COOPERATIVE_INTRUSIVE_RCP)
    // During interpreter global destruction the cooperative hooks are inert and
    // the SymEngine C++ statics retain ownership of whatever survives, so we
    // must not delete here (doing so races the static-destruction of the
    // singletons and frees objects the statics still point at).  PL_phase flips
    // to PERL_PHASE_DESTRUCT at the very start of perl_destruct -- before any
    // pad teardown or DESTROY sweep -- so it reliably covers the whole teardown
    // window, including the gap before our call_atexit handler runs.
    if (g_perl_destructing || PL_phase == PERL_PHASE_DESTRUCT) {
        g_perl_destructing = true;
        return;
    }
    // Reaching DESTROY outside teardown means SvREFCNT(inner) just hit zero.
    // While the object is still external-owned that implies no C++ RCP and no
    // Perl reference survives, so this wrapper performs the final delete.  If
    // the object was previously detached back to C++-owned mode (singleton
    // reconciliation), is_external_owned() is false and the C++ side keeps it.
    if (p != nullptr && p->is_external_owned()) {
        delete p;
    }
#else
    (void) p;
#endif
}

} // namespace SymEnginePerl
