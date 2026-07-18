# Proposed upstream PR description (symengine/symengine)

**Status:** draft, 2026-07-10. This file is the *proposed text* of the PR body,
to be pasted into GitHub when `rcp-nanobind-2` is rebased and submitted.
Supplementary evidence (full scripts, measured outputs, diagrams) lives in
`PR-SUPPLEMENTARY.md` and would be published as a gist / `docs/` link so the
PR body stays short. Bracketed ✎-notes are instructions to ourselves and must
be removed before submitting.

---

## Title

**Add opt-in `cooperative_intrusive` RCP backend: one refcount that either
lives inline or delegates to a foreign runtime**

## Summary

This PR adds a third, **opt-in** reference-counting backend
(`-DSYMENGINE_RCP_BACKEND=cooperative_intrusive`) next to the existing
`WITH_SYMENGINE_RCP` and Teuchos backends. It changes nothing for existing
builds — the default backend, `Basic`'s layout under it, and the public API
are untouched.

The new backend stores, in the same pointer-sized field that today holds the
refcount, **either**:

* an inline reference count, left-shifted by one with the lowest bit set
  (`count << 1 | 1`) — the "C++-owned" mode every object starts in, **or**
* a pointer to a wrapper object in a foreign language runtime (lowest bit
  clear, guaranteed by alignment) — after ownership has been handed to that
  runtime, `inc_ref()`/`dec_ref()` forward to two process-global hooks
  (e.g. `Py_INCREF`/`Py_DECREF`).

This is the "intrusive counter with Python delegation" design that nanobind
ships as its reference sample (`nanobind/intrusive/counter.inl`, BSD-3,
© Wenzel Jakob); the implementation here is a direct port carrying all of its
correctness fixes (including the 2026-06 CAS hand-off race fix), made
runtime-agnostic: the hooks take `void *`, so the same backend serves CPython
(`Py_INCREF`), PHP (`GC_ADDREF`/`OBJ_RELEASE`), Perl (`SvREFCNT_inc/dec`) —
and prospectively Swift (`swift_retain/release`). We have working Python,
PHP, and Perl bindings exercising it. [✎ link the three binding repos]

## Why: the problem bindings cannot fix on their own

With the current backends, a language binding must keep the C++ object alive
with an `RCP` (count #1 inside `Basic`) while the language runtime
independently counts the wrapper (count #2). Any feature that requires the
C++ object to find its wrapper again — subclass identity preservation being
the canonical one — forces a strong back-pointer, and two counters + a
back-pointer is a reference cycle that no single garbage collector can see.

This is not hypothetical. symengine.py's `Symbol` docstring says today:

> *"Subclassing Symbol leads to a memory leak due to a cycle in reference
> counting."*

and `pywrapper.h`'s destructor carries:

> *"TODO: This is never called because of the cyclic reference."*

Measured on CPython 3.13 with the symengine.py 0.14.1 wheel: after creating
and dropping 1000 `Symbol`-subclass instances and running `gc.collect()`,
**1000/1000 are still alive**; 200k create/drop cycles grow RSS by **+36.5
MiB** (~190 bytes/instance, unbounded), versus **+0.0 MiB** for plain
`Symbol`. The documented workaround (`store_pickle=True`) trades the leak for
broken semantics: round-trip identity is lost (`arg is x` → `False`) and
attribute mutations after construction silently disappear. Full scripts and
outputs in the supplementary material. [✎ link]

With `cooperative_intrusive` there is only ever **one** count. When a value
is first returned to (say) Python, the binding calls `set_self_external(o)`,
which atomically transfers the inline count onto the wrapper's refcount and
stores the wrapper pointer in the same field. From then on the wrapper *is*
the count; C++-side `RCP` copies increment the wrapper's refcount through the
hook. No back edge, no cycle, nothing for the GC to miss. The same
nanobind-based bindings, same probes: **0/1000 alive, +0.0 MiB**, identity
preserved (`arg is x` → `True`), post-construction mutations visible. And
because the wrapper is found via `self_external()`, bindings get canonical
wrapper reuse (same Python object every time the same `Basic` crosses the
boundary) for free.

## What is in the diff

The core-library change is deliberately small; most of the patch is tests and
tooling. [✎ re-run `git diff --stat master...` after rebase and update]

* `symengine/symengine_rcp.h` — the `cooperative_intrusive` branch of
  `RCP<T>`/`EnableRCPFromThis<T>` (mirrors the existing `WITH_SYMENGINE_RCP`
  branch, but through `inc_ref()`/`dec_ref()` methods), plus the pointer-sized
  counter class (~230 lines touched).
* `symengine/symengine_rcp_cooperative.cpp` — the counter implementation:
  lock-free CAS loops, the `set_self_external` hand-off, `detach_external`
  for embedder shutdown reconciliation (~170 lines, new file).
* `symengine/add.cpp` — the two dict-steal sites now use
  `is_uniquely_owned()`, a predicate each backend defines correctly. This
  removes the pre-existing `#if !THREAD_SAFE && RCP` guard rather than adding
  backend-specific conditionals.
* `symengine_config.h.in`, `CMakeLists.txt`, `SymEngineConfig.cmake.in` —
  the backend switch and export of the hook-init symbol.
* Tests: `symengine/tests/rcp/test_cooperative_intrusive_rcp.cpp` (counting in
  both modes, hand-off, hook routing, `use_count()` semantics, detach/replay),
  a `use_count()==1` regression-guard script, and
  `bin/cooperative_intrusive_consume/` — a ~120-line raw CPython extension
  (no nanobind) proving the backend is binding-framework-agnostic.
* Benchmarks: `benchmarks/rcp_throughput.cpp` plus the new
  `benchmarks/add_steal.cpp`. On a Ryzen 9 7950X, the latter improves the
  exact eligible cooperative path by 1.33× (4 dictionary entries) to 1.48×
  (16/64 entries); broad workloads and Python-boundary cases remain within
  noise. Full setup and samples are in the supplementary report.

Explicitly **not** in this PR: any binding code. The Python/PHP/Perl bindings
live downstream; core only gains the counter, two function-pointer hooks
installed once via `cooperative_intrusive_init()`, and the handful of query
methods (`is_external_owned()`, `is_uniquely_owned()`,
`is_uniquely_owned_by_cpp()`,
`self_external()`, `detach_external()`).

## Semantics and caveats (reviewer checklist)

* **Opt-in only.** Default builds compile exactly the code they compile
  today. The new backend is ABI-incompatible with the others (the counter
  field is `uintptr_t` instead of `unsigned int`) — same situation as
  switching to/from Teuchos, and why it is a CMake-time choice.
* **Thread-safety of the counter itself** matches nanobind's sample: all
  transitions are CAS loops; the June-2026 upstream fix for the
  `set_self_py` hand-off race is included. Orderings are relaxed, exactly as
  in nanobind — we kept parity deliberately and documented it; strengthening
  should happen in both places or neither.
* **`use_count()` returns 0 in external-owned mode** (the foreign runtime
  holds the truth and we refuse to guess). Ownership-gated optimizations must
  use `is_uniquely_owned()`; a CI guard rejects new `use_count() == 1` sites.
  Externally-owned objects are never "unique" for stealing purposes — by
  design, since a foreign heap can still reach them.
* **Hooks before use:** using the backend without `cooperative_intrusive_init()`
  aborts with a clear message on first external-mode operation; pure-C++ use
  of a cooperative build (no foreign runtime at all) works fine and never
  touches the hooks.
* **Subclass/cycle caveat, honestly stated:** the backend removes the
  *structural* cycle that today's two-counter design forces on every
  subclass instance. A user can still hand-build a cross-language cycle
  (e.g. `x.attr = sin(x)`), which needs GC-traversal integration in the
  binding layer, same as any C-extension; that is out of scope for core.

## Relationship to nanobind

`counter.inl` is nanobind's *sample* implementation, intended to be adapted.
This PR vendors an adapted port (attribution header included) rather than
`#include`-ing it, because core symengine must not depend on Python headers —
the port replaces `PyObject *` with `void *` and the two `Py_*` calls with
installable hooks. We track upstream nanobind changes to the sample (last
audit: 2026-07-10, at parity with nanobind master `ff6a401`).

## Testing done

* Full C++ test suite under all three backends (Linux, gcc + clang).
* The rcp unit tests above plus a hooks-abort harness and detach/replay
  regression test.
* Downstream (not in this PR, evidence linked): nanobind-based Python
  bindings run a transcription of symengine.py's own pytest suite green,
  ASan/TSan/glibcxx-debug lanes, PHP `.phpt` and Perl TAP ownership/teardown
  suites, plus the leak probes quoted above. [✎ link CI runs]

---

[✎ PR footer: "Supplementary material with runnable reproductions:
<link to PR-SUPPLEMENTARY as gist or repo docs>"]
