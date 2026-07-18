# 24 — Remaining Work: Nanobind Parity Audit, the `Add` Steal-Path Investigation, and Upstream PR Packaging

**Date:** 2026-07-10
**Status:** Implementation in progress. The source changes in sections 1–3,
the upstream rebases, and the benchmark report are complete; TSAN and
hit-rate instrumentation remain.
**Audience:** Developer continuing the cooperative_intrusive work


---

## 3. Counter hardening (small, do alongside Phase 2)

1. **`detach_external()` should CAS, not load+store**
   (`symengine_rcp_cooperative.cpp:160–167`). Today it is only invoked from
   single-threaded shutdown reconciliation, so the plain
   `LOAD` → `STORE(1)` window is not observed in practice — but the rest of
   the counter is lock-free-correct, and this one function is the outlier.
   `while (!CMPXCHG(&m_state, &v, 1))` with the same external-check makes it
   self-consistent and costs nothing. Add a comment either way stating the
   shutdown-only contract.
2. **Document the memory-ordering decision.** Both nanobind's sample and our
   port use relaxed (`0`) orderings everywhere. This is deliberate upstream
   parity, and safe on x86-64/TSO; on weakly-ordered targets (AArch64) the
   textbook refcount discipline is release-decrement + acquire-fence before
   `delete`. nanobind ships it relaxed to this day; we should (a) note the
   parity decision in a comment block in `symengine_rcp_cooperative.cpp`,
   (b) keep TSAN lanes on AArch64 in mind if we ever get such a runner, and
   (c) if we strengthen, do it as an upstream nanobind conversation first so
   the two implementations do not diverge silently.
3. **`use_count()` doc-string tightening:** it returns 0 for external-owned;
   the header note exists (`symengine_rcp.h:49–52`, `:481–484`) but should
   also state that the value is *advisory under concurrency* except for the
   sole-owner == 1 case used by section 2.

---

## 4. Previously root-caused leak fixes (from report 16b)

Unchanged status; listed so this plan is the single "what's left" document:

1. **Completed:** `SymEngine::minus_one` and `SymEngine::NegInf` are present
   in `g_singletons` in `nbsymengine/support/nanobind_module_common.h`.
2. **Finalization-window decref policy remains open** (16b Shape 1): the
   current `s_python_is_dead` atexit guard avoids unsafe decrefs after teardown,
   but it still needs a phase-aware policy for the interval where the
   interpreter is finalizing but remains usable. Removing the guard naïvely
   segfaults (16b §7); distinguish the phases via `Py_IsFinalizing()` / atexit
   ordering rather than a binary guard.

---

## 6. Deferred / unowned items (carried forward)

* Apache-module and broad FPM lifecycle matrices (22d unknowns).
* PHP ASAN lane (currently only a clean debug lane).
* Swift (`swift_retain/release`) and raw-Perl (`SvREFCNT_*`) consumers of the
  cooperative hook pair — explicitly deferred; the hook signature was designed
  for them, no work scheduled.
* Follow-up from section 2 Phase 4(b) if the benchmark gap is not
  steal-dominated: profile `Mul::from_dict` and small-map allocation.
