# INVESTIGATION: the `Add::from_dict` "steal" fast path under cooperative_intrusive

### 1 Background and current state

`Add::from_dict` collapses a one-entry dict into a `Mul`. Upstream has a
fast path that, when the inner `Mul` is uniquely owned, **steals** its
`dict_` (const_cast + move) instead of copying it — historically gated as:

```c++
#if !defined(WITH_SYMENGINE_THREAD_SAFE) && defined(WITH_SYMENGINE_RCP)
    if (down_cast<const Mul &>(*(p->first)).use_count() == 1) { /* steal */ }
#endif
```

There are two such sites. Before this implementation, the
cooperative_intrusive backend **compiled the steal path out entirely**
(decision D11), because `use_count() == 1` would be wrong there:
an external-owned object reports `use_count() == 0`, and more importantly the
inline count only exists in C++-owned mode. That made the cooperative backend
**always copy** the inner `Mul` dict — a per-call `map_basic_basic` copy
(O(n) node allocations) on one of the hottest paths in the library
(`x*y + 0` shaped canonicalizations inside `expand`, `mul`, polynomial code).

The regression guard `symengine/tests/rcp/check_use_count_eq1.sh` now bans
all non-test `use_count() == 1` ownership gates and directs callers to
`is_uniquely_owned()`.

### 2 The key insight: we do NOT need to call into Python

The concern that prompted this investigation — *"calling out to Python via
use_count would be prohibitively expensive"* — is well-founded but moot,
because the right predicate never leaves the C++ side:

```c++
bool is_uniquely_owned_by_cpp() const noexcept {
    uintptr_t v = SYMENGINE_ATOMIC_LOAD(&m_state);   // one relaxed load
    return (v & 1) && (v >> 1) == 1;                 // tag + count check
}
```

That is **one relaxed atomic load plus two ALU ops** — on x86-64 a plain
`mov`. No hook call, no GIL, no foreign runtime. It already exists on the
counter and on `EnableRCPFromThis`.

Why this loses (essentially) nothing versus interrogating Python:

1. **The objects stealing targets are C++-owned by construction.** The steal
   candidates are intermediates freshly built inside the expression kernel
   (e.g. the `Mul` produced while evaluating `2*x*y + 0`). Ownership only
   migrates to a foreign runtime when a value is *returned* through a binding
   and wrapped (`set_self_external`). Mid-expression temporaries never were.
   So `is_uniquely_owned_by_cpp()` fires for exactly the same population of
   objects that legacy `use_count() == 1` fired for.
2. **A foreign-owned object with wrapper-refcount 1 is *still not stealable*.**
   Even if we paid for the call: `Py_REFCNT == 1` means the *wrapper* has one
   reference — but the wrapper itself is a live, canonical Python object whose
   payload is this `Mul`. Gutting its `dict_` would corrupt an object the
   foreign heap can still reach (identity-reuse via `self_external()` hands it
   back out). The count answers "may the wrapper die?", not "may I mutate the
   payload?". So the *correct* answer for external-owned is unconditionally
   "copy", which is what the tag check gives us for free.
3. **The call would indeed be expensive and unreliable anyway** (for the
   record): a function-pointer hook call, `PyGILState_Ensure` from
   non-Python threads, `Py_REFCNT` being semantically fuzzy under
   free-threaded CPython (deferred/biased counts, immortality), and no
   uniform "current count" hook exists for PHP/Perl — we deliberately only
   installed incref/decref hooks. We should never add a `usage_count` hook.

So the investigation is not "how do we ask Python" — it is "confirm the
predicate swap recovers legacy's throughput, and prove it safe".

### 3 Hypotheses

* **H-pop:** ≥ 99% of steal-site hits during representative workloads
  (`expand2b`, nbsymengine test suite, nbsymengine_compat suite) are
  C++-owned with inline count 1, i.e. the predicate swap recovers virtually
  all legacy steals. (Measure, don't assume.)
* **H-perf:** enabling the steal under `is_uniquely_owned_by_cpp()` closes a
  measurable fraction of the cooperative-vs-legacy gap on `Add`-heavy
  benchmarks, and the added atomic load is not measurable on the copy path.
* **H-safe:** the steal is sound even with `WITH_SYMENGINE_THREAD_SAFE`-style
  concurrent use of *other* objects, because count==1 read by the sole owner
  is stable: no other thread can legally mint a new reference except through
  the one reference we hold (raw `Ptr`/`rcp_from_this` escapes would violate
  the same invariant legacy already assumes).

### 4 Plan of attack

**Phase 0 — instrument (no behavior change).**
Add a temporary counter (or `SYMENGINE_COOP_STEAL_STATS` env-gated atexit
print) at both steal sites recording: hits, would-steal-under-legacy
(`use_count()==1` in a legacy build), would-steal-under-cooperative
(`is_uniquely_owned_by_cpp()`), external-owned hits. Run: `expand2b`,
`symengine` C++ test suite, nbsymengine pytest suite, benchmarks/. This
directly tests H-pop and quantifies the addressable win before writing any
fix. Revert instrumentation afterwards (16b precedent).

**Phase 1 — baselines.**
Record before-numbers with the existing tooling:
`symengine/benchmarks/bench_rcp_backends.sh` (added by our patch) and
`benchmarks/` in the superproject (legacy symengine.py vs nbsymengine),
plus upstream's `expand2b`. Pin CPU frequency / use `taskset`; 5 repeats,
report median ± spread.

**Phase 2 — implement via a backend-neutral predicate seam.**
Rather than re-instantiating `#if` soup, give `EnableRCPFromThis` a single
spelling with per-backend definitions, and use it at both sites:

```c++
// symengine_rcp.h
bool is_uniquely_owned() const noexcept;
//  cooperative_intrusive: (m_state & 1) && (m_state >> 1) == 1
//  WITH_SYMENGINE_RCP (non-thread-safe): refcount_ == 1
//  WITH_SYMENGINE_RCP + THREAD_SAFE:     refcount_.load(relaxed) == 1   [see 2.5]
//  Teuchos:                              strong_count() == 1
```

then in `add.cpp` both sites become an unconditional:

```c++
if (down_cast<const Mul &>(*(p->first)).is_uniquely_owned()) { /* steal */ }
```

This *shrinks* the upstream diff in `add.cpp` (removes the `#if/#else` brace
gymnastics we added) and removes decision D11's compile-out entirely — a
strictly better story for the upstream PR (see `docs/upstream/`).
`check_use_count_eq1.sh` gets updated to ban `use_count() == 1` outright.

**Phase 3 — tests.**
* Unit (in `test_cooperative_intrusive_rcp.cpp` + a new `add`-level test):
  a C++-owned single-ref `Mul` **is** stolen (observable via dict identity
  or a probe on allocation counts); an external-owned `Mul` (fake aligned
  owner pointer, as the existing tests do) is **copied** and its dict is
  intact afterwards; the steal path never invokes the foreign hooks
  (hooks-abort harness already exists).
* TSAN lane: a stress test where threads build independent `x*y + 0`
  expressions concurrently while sharing leaf symbols (leaves get counts > 1,
  the `Mul` temporaries stay unique) — validates H-safe mechanically.
* Keep the smoke test in `bin/cooperative_intrusive_consume/` green.

**Phase 4 — measure and decide.**
Re-run Phase 1. Accept if: no test regressions, TSAN clean, and either
(a) ≥ half the legacy-vs-cooperative gap on the `Add`-dominated benchmark
closes, or (b) the gap turns out to be dominated by something else — in which
case the instrumentation data from Phase 0 tells us where to look next
(likely `Mul::from_dict` or the `map_basic_basic` allocator; file follow-up).

**Phase 4 result (2026-07-10).** The dedicated eligible-path benchmark is
1.33×–1.48× faster, while existing `add`/`expand` and Python-boundary
workloads are within noise. This proves the move has the expected local
payoff but does not establish the fraction of the legacy/cooperative gap it
closes; the Phase 0 hit-rate instrumentation and TSAN run remain before that
broader decision. See `docs/reports/24-ADD-STEAL-BENCHMARKS.md`.

### 5 Resolved during Phase 2

The legacy `WITH_SYMENGINE_THREAD_SAFE` backend keeps returning `false` from
`is_uniquely_owned()`. Although a relaxed `refcount_.load() == 1` is a
plausible later optimization, enabling it changes an existing thread-safe
path. Keeping the historical no-steal behavior gives the upstream PR a
smaller, lower-risk review surface.


# Benchmark results

**Date:** 2026-07-10

## Conclusion

The new `is_uniquely_owned()` gate recovers a material win when a one-entry
`Add::from_dict` owns the inner `Mul`: **1.33× to 1.48× faster** in the
dedicated native workload, with the gain increasing with the number of moved
dictionary entries. Existing broad `add`/`expand` programs and Python-boundary
operations show no statistically meaningful regression or improvement.

That is the expected split. Python-visible objects are external-owned and must
copy their dictionaries; the fast path is intentionally only for private C++
temporaries. The dedicated benchmark proves the predicate has the intended
payoff when that condition occurs. It does not measure the rate at which that
condition occurs in a whole workload; the optional hit-rate instrumentation
from plan 24 remains the next step if a broad-workload speedup is required.

## Revision and environment

Both requested rebases were performed before the measurements:

| Checkout | Revision after rebase |
|---|---|
| `symengine` | `rcp-nanobind-2` at `c13bed695`, 105 commits atop upstream `master` `7877e6bf0` |
| `symengine.py` | `support-glibcxx-debug` at upstream `master` `88ad323` |

The baseline is that rebased `symengine` revision without the uncommitted plan
24 changes. The comparison build has the same revision plus the
`is_uniquely_owned()`/steal-path implementation.

* AMD Ryzen 9 7950X, GCC 14.2.0, Boost 1.91.0, CPython 3.13.5, nanobind 2.13.0
* Release, `INTEGER_CLASS=boostmp`, `WITH_BFD=OFF`, `WITH_LLVM=OFF`
* `SYMENGINE_RCP_BACKEND=cooperative_intrusive`, non-thread-safe
* `taskset -c 0`; seven alternating baseline/post process runs per native
  result. CPU frequency could not be fixed, so ranges are reported rather
  than over-interpreting sub-percent changes.

## Native results

`benchmarks/add_steal.cpp` constructs the precise eligible shape: a
multi-factor `Mul`, then moves its only `RCP` into a one-entry
`Add::from_dict` dictionary. The old cooperative build copies the `Mul`
dictionary; the new build moves it. Each sample runs 200,000 iterations.

| `Mul` dictionary entries | Baseline median ns/op (range) | Steal median ns/op (range) | Speedup |
|---:|---:|---:|---:|
| 4 | 226.7 (223.2–230.3) | 169.9 (169.2–172.7) | **1.33×** |
| 16 | 783.5 (774.3–822.1) | 530.5 (525.4–533.1) | **1.48×** |
| 64 | 3275.6 (3167.1–3327.1) | 2208.7 (2170.8–2263.9) | **1.48×** |

The existing programs below exercise larger expression workloads. Their
medians have overlapping ranges, so the result is "no measurable change", not
evidence of a universal speedup.

| Program | Workload | Baseline median | Steal median | Result |
|---|---|---:|---:|---|
| `add1` | 3,000 Add terms | 108 ms (107–117) | 109 ms (107–116) | noise |
| `expand1` | `(w+x+y+z)^60`, 39,711 terms | 35 ms (33–37) | 35 ms (34–39) | noise |
| `expand2` | expanded product, 6,272 terms | 215 ms (212–218) | 216 ms (213–231) | noise |

## Python-boundary results

`benchmarks/python_boundary_add.py` was run against separately built baseline
and steal-path `nbsymengine` extensions. Each reported outer sample is itself
the median of seven timing batches; the table reports the median and range of
seven independent Python processes.

| Program | Workload | Baseline median | Steal median | Result |
|---|---|---:|---:|---|
| `boundary-add` | 16-factor `Mul` followed by `+ 0` | 7.679 µs (7.573–7.719) | 7.607 µs (7.521–7.734) | noise, 1.0% faster |
| `expand` | Python-visible `(w+x+y+z)^15`, 816 terms | 557.367 µs (555.685–558.858) | 554.129 µs (551.120–564.206) | noise, 0.6% faster |

The `boundary-add` case crosses the extension boundary for every constructed
intermediate. The `Mul` is consequently external-owned before the next Python
operation, so preserving the copy path is both required for correctness and
explains why there is no expected direct speedup. The expand case also returns
and hashes a Python wrapper on every timed call.

### Legacy-binding context (not a patch comparison)

For an end-to-end control, the same runner was also executed with the rebased
`symengine.py` Cython binding and a locally built legacy-RCP SymEngine core.
These are **not** baseline numbers for the table above and must not be used to
rank bindings: this run changes the RCP backend, wrapper implementation, and
the spelling of the Python operations (operators rather than generated
`nbsymengine` functions). It is included to record that the requested
`symengine.py` rebase was exercised with the same Add-heavy targets.

| Binding | Workload | Median (range), seven processes |
|---|---|---:|
| rebased `symengine.py` | 16-factor `Mul` followed by `+ 0` | 4.569 µs (4.489–4.847) |
| rebased `symengine.py` | `(w+x+y+z)^15`, 816 terms | 361.022 µs (357.930–369.332) |

The only causal pre/post measurements for the change remain the cooperative
native and `nbsymengine` baseline/steal comparisons above.

## Reproduction

Build a baseline worktree at the rebased `HEAD`, and a second build from the
same checkout with the plan 24 changes applied. Configure both with the
environment above, then run:

```sh
taskset -c 0 build-baseline/benchmarks/add_steal 200000 16
taskset -c 0 build-steal/benchmarks/add_steal 200000 16

PYTHONPATH=build-python-baseline taskset -c 0 \
  python benchmarks/python_boundary_add.py boundary-add --factors 16
PYTHONPATH=build-python-steal taskset -c 0 \
  python benchmarks/python_boundary_add.py boundary-add --factors 16

PYTHONPATH=legacy-python-install LD_LIBRARY_PATH=legacy-core-install/lib \
  taskset -c 0 python benchmarks/python_boundary_add.py expand --binding legacy
```

The report's Python builds pass `-DBOOST_INCLUDE_DIR` for the non-system Boost
prefix so the manually bound nanobind module can include `boostmp` headers.
