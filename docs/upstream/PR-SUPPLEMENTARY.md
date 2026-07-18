# Supplementary material for the cooperative_intrusive upstream PR

**Status:** draft, 2026-07-10. All outputs below are real, captured on this
date. Re-capture on a clean checkout before publishing (as a gist or a
`docs/` page linked from the PR body — the PR body itself only quotes the
headline numbers).

**Environment for every run below:**

* CPython 3.13 (`/opt-3/cpython-v3.13-apt-deb`), Linux x86-64
* symengine.py **0.14.1** (release wheel from PyPI) — the Cython bindings
* nbsymengine built from source, Release, `SYMENGINE_RCP_BACKEND=cooperative_intrusive`,
  nanobind 2.13.0

---

## 1. The failure mode in today's Cython bindings (symengine.py)

### 1.1 Why it happens

To make a Python subclass of `Symbol` survive a round trip through C++
(`sin(x).free_symbols` must return *your* object, with *your* attributes),
symengine.py wraps it in a C++ `PySymbol` that holds a strong `PyObject*`
back-reference:

```
   Python wrapper (MySymbol instance)
        │  .thisptr        RCP<const Basic>          count #1 (inside Basic)
        ▼
   C++ PySymbol
        │  .obj            PyObject* + Py_INCREF     count #2 (CPython)
        ▼
   Python wrapper  ←──────────── the same object: a cycle
```

CPython's cycle collector can only traverse edges that `tp_traverse`
declares; the edge through `.thisptr` into C++ and back is invisible to it.
Neither count can reach zero, so **every subclass instance is immortal**.
Upstream knows — the `Symbol` docstring says:

> Subclassing Symbol leads to a memory leak due to a cycle in reference
> counting.

and `symengine/lib/pywrapper.h` (`PySymbol::~PySymbol`):

> // TODO: This is never called because of the cyclic reference.

The root cause is *structural*: with the current RCP backends the C++ count
lives inside `Basic` and the Python count lives in the wrapper — two counters
that must each pin the other side. No binding-side change can merge them.

### 1.2 Reproduction A — instances are never collected

```python
# leak_repro.py
import gc, weakref
import symengine

class MySymbol(symengine.Symbol):
    def __init__(self, name, extra=None):
        super().__init__(name)
        self.extra = extra

refs = []
for i in range(1000):
    s = MySymbol(f"s{i}", extra=list(range(100)))
    refs.append(weakref.ref(s))
    del s
for _ in range(3):
    gc.collect()
alive = sum(1 for r in refs if r() is not None)
print(f"subclass instances still alive after del + gc.collect(): {alive}/1000")
```

Output (symengine.py 0.14.1, CPython 3.13):

```
subclass instances still alive after del + gc.collect(): 1000/1000
```

### 1.3 Reproduction B — unbounded memory growth

```python
# leak_repro2.py
import gc, resource
import symengine

def rss_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024

class MySymbol(symengine.Symbol):
    pass

N = 200_000
base = rss_mb()
for i in range(N):
    s = symengine.Symbol(f"plain_{i}"); del s
gc.collect()
print(f"plain Symbol:    RSS delta {rss_mb() - base:+7.1f} MiB")

base = rss_mb()
for i in range(N):
    s = MySymbol(f"sub_{i}"); del s
gc.collect()
print(f"Symbol subclass: RSS delta {rss_mb() - base:+7.1f} MiB")

x = MySymbol("x")
fs, = symengine.sin(x).free_symbols
print("round-trip identity preserved:", fs is x, "| type:", type(fs).__name__)
```

Output:

```
plain Symbol:    RSS delta    +0.0 MiB
Symbol subclass: RSS delta   +36.5 MiB
round-trip identity preserved: True | type: MySymbol
```

~190 bytes leak per instance, forever, in any long-running process that
churns subclass symbols (a very common pattern: domain packages subclass
`Symbol` to attach units, indices, metadata…). Note the last line: the
*feature* works — that is exactly why the back-reference, and therefore the
cycle, exists.

### 1.4 Reproduction C — the documented workaround breaks the feature

symengine.py's escape hatch is `store_pickle=True` (pickle the wrapper at
construction instead of holding a reference; unpickle on every round trip):

```python
# store_pickle_repro.py
import symengine

class PickleSymbol(symengine.Symbol):
    def __init__(self, name, tag=None):
        self.tag = tag
        super().__init__(name, store_pickle=True)
    def __reduce__(self):
        return (self.__class__, (str(self), self.tag))

x = PickleSymbol("x", tag="original")
expr = symengine.sin(x)
fs, = expr.free_symbols
print("identity preserved with store_pickle:", fs is x)
x.tag = "mutated-after-creation"
fs2, = expr.free_symbols
print("round-tripped object's .tag:", fs2.tag)
```

Output:

```
identity preserved with store_pickle: False
round-tripped object's .tag: original
```

So the user must choose: leak every instance, or lose object identity and
any state change made after construction (plus implement `__reduce__`, plus
pay pickle round-trips on every boundary crossing).

---

## 2. How cooperative_intrusive eliminates the failure mode

### 2.1 One count instead of two

The counter is a single `uintptr_t` (`m_state`) inside `Basic`:

| `m_state` value | meaning |
|---|---|
| `(count << 1) \| 1` | **C++-owned**: inline refcount, CAS inc/dec |
| wrapper pointer (bit 0 clear, by alignment) | **external-owned**: `inc_ref()`/`dec_ref()` forward to the runtime's incref/decref hooks |

When a `Basic` first crosses into Python, the binding calls
`set_self_external(wrapper)`: the inline count is transferred onto the
wrapper's refcount and the pointer is stored — atomically, with the CAS
retry loop from nanobind's June-2026 race fix (references are transferred
*before* publication, surplus transfers are rolled back after).

```
   Python wrapper (MySymbol instance)
        │  holds C++ pointer (nanobind instance slot)
        ▼
   C++ Symbol ── m_state = wrapper ptr ──► the wrapper's OWN refcount
                                           IS the count.  No second
                                           counter, no back edge, no cycle.
```

A C++ expression that keeps the symbol alive (`sin(x)` holding `x`) simply
holds +1 on the wrapper — a normal, GC-visible-as-refcount relationship.
When the last reference (Python or C++) goes away, the wrapper deallocates
and destroys the C++ object with it. Identity comes for free:
`self_external()` returns the canonical wrapper whenever the same `Basic`
crosses the boundary again.

### 2.2 Demonstration — same probes, cooperative backend

Run against nbsymengine (nanobind bindings over the cooperative backend);
`get_args()` is the thin-wrapper spelling of the round trip:

```python
# no_leak_demo.py — probes 1:1 with reproductions A and B
import gc, weakref, resource
from nbsymengine import _core as se

def rss_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024

class MySymbol(se.Symbol):
    def __init__(self, name, extra=None):
        super().__init__(name)
        self.extra = extra

refs = []
for i in range(1000):
    s = MySymbol(f"s{i}", extra=list(range(100)))
    refs.append(weakref.ref(s))
    del s
for _ in range(3):
    gc.collect()
print(f"subclass instances still alive after del + gc.collect(): "
      f"{sum(1 for r in refs if r() is not None)}/1000")

N = 200_000
base = rss_mb()
for i in range(N):
    s = se.Symbol(f"plain_{i}"); del s
gc.collect()
print(f"plain Symbol:    RSS delta {rss_mb() - base:+7.1f} MiB")

base = rss_mb()
for i in range(N):
    s = MySymbol(f"sub_{i}"); del s
gc.collect()
print(f"Symbol subclass: RSS delta {rss_mb() - base:+7.1f} MiB")

x = MySymbol("x", extra="user-data")
expr = se.sin(x)
arg, = expr.get_args()
print("round-trip identity preserved:", arg is x,
      "| type:", type(arg).__name__, "| .extra:", arg.extra)
x.extra = "mutated-after-creation"
arg2, = expr.get_args()
print("mutation visible after round-trip:", arg2.extra)
```

Output (Release build, cooperative_intrusive, CPython 3.13):

```
subclass instances still alive after del + gc.collect(): 0/1000
plain Symbol:    RSS delta    +0.0 MiB
Symbol subclass: RSS delta    +0.0 MiB
round-trip identity preserved: True | type: MySymbol | .extra: user-data
mutation visible after round-trip: mutated-after-creation
```

### 2.3 Side-by-side

| | symengine.py (leak mode) | symengine.py (`store_pickle`) | cooperative_intrusive |
|---|---|---|---|
| subclass instances collected | **never** (1000/1000 alive) | yes | yes (0/1000 alive) |
| RSS, 200k subclass churn | **+36.5 MiB** | ~flat | +0.0 MiB |
| round-trip identity (`arg is x`) | yes | **no** | yes |
| mutations after construction survive | yes | **no** | yes |
| user burden | none | `__reduce__` + pickle cost | none |

The cooperative backend is the only column with no bold entry: it keeps the
feature *and* the memory.

### 2.4 Honest caveat

The backend removes the structural cycle that today makes every subclass
instance leak unconditionally. A user can still build a genuine
cross-language cycle by hand (e.g. `x.loop = se.sin(x)` — wrapper → attribute
→ expression → C++ edge → wrapper). Collecting those requires GC-traversal
integration in the binding layer, as with any C extension; it is orthogonal
to this PR and does not affect the reproductions above.

---

## 3. Reproducing the builds

* symengine.py numbers: `pip install symengine==0.14.1`, run the scripts in
  §1 as-is.
* cooperative backend: build symengine with
  `-DSYMENGINE_RCP_BACKEND=cooperative_intrusive` and any binding that
  installs the hooks. Minimal, framework-free proof: the ~120-line raw
  CPython extension in `bin/cooperative_intrusive_consume/` (part of the PR)
  plus its `smoke.py`. Full-featured: the nbsymengine bindings
  [✎ link repo + exact commit] — in the superproject,
  `SYMENGINE_RCP_CHOICE=cooperative_intrusive .ci/ci-02-build-and-test-nbsymengine.sh <builddir>`.
* Cross-runtime evidence that the hook design is not Python-specific:
  PHP (`GC_ADDREF`/`OBJ_RELEASE`, `.phpt` ownership + teardown suites) and
  Perl (`SvREFCNT_inc/dec`, TAP suites) bindings run the same backend
  [✎ link `symengine.php`, `symengine.pl` + CI runs].

## 4. Related core tests and benchmarks (in the PR itself)

* `symengine/tests/rcp/test_cooperative_intrusive_rcp.cpp` — inline counting,
  hand-off transfer semantics, hook routing in external mode,
  `use_count()==0-when-external`, detach/replay for embedder shutdown.
* `symengine/tests/rcp/check_use_count_eq1.sh` — CI guard: no
  `use_count() == 1` ownership gates may appear (they are wrong under this
  backend); use `is_uniquely_owned()`.
* `benchmarks/rcp_throughput.cpp` + `benchmarks/bench_rcp_backends.sh` —
  three-backend counter throughput comparison.
* `benchmarks/add_steal.cpp` — direct, allocation-sensitive measurement of
  the one-entry `Add::from_dict` path. The rebased benchmark report records
  a 1.33×–1.48× gain for C++-unique `Mul`s and no measurable change for
  broad or Python-boundary workloads; see
  [plan 24 benchmark report](../reports/24-ADD-STEAL-BENCHMARKS.md).
