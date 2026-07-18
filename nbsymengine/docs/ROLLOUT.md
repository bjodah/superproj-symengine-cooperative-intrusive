# Rollout and Packaging Policy — SymEngine nanobind Bindings

**Status:** normative
**Phase:** 7.6

---

## 1. Core Library Independence from Python

The SymEngine core library remains Python-independent under all default
configurations. A plain `find_package(symengine)` consumer that does not select
the `cooperative_intrusive` backend is completely unaffected by this work.

When `cooperative_intrusive` is selected, the only Python-adjacent header entering the
core is `<nanobind/intrusive/counter.h>`, which forward-declares `PyObject`
without including `<Python.h>`. No translation unit in `symengine/` ever
includes `<Python.h>`. This property is enforced by the design and verified by
source-level grep in CI.

Decision references: D7, D10.

---

## 2. Backend Selection

Three RCP backends are available, selected at CMake configure time via
`-DSYMENGINE_RCP_BACKEND=<value>`:

| Backend | Macro | Default | Description |
|---------|-------|---------|-------------|
| `symengine` | `WITH_SYMENGINE_RCP` | Release builds | Original internal intrusive counter. Non-atomic when `WITH_SYMENGINE_THREAD_SAFE=OFF`. |
| `teuchos` | `WITH_SYMENGINE_TEUCHOS` | Debug builds | Teuchos RCP with full safety checks and weak-pointer support. |
| `cooperative_intrusive` | `WITH_SYMENGINE_COOPERATIVE_INTRUSIVE_RCP` | Opt-in only | nanobind-compatible intrusive counter. Always atomic. Enables Python object identity sharing. |

The deprecated boolean `-DWITH_SYMENGINE_RCP=ON/OFF` continues to work as an
alias (`ON` maps to `symengine`, `OFF` maps to `teuchos`).

---

## 3. When to Choose Which Backend

**`symengine` (default Release)** -- Use when:
- Building a pure C++ application or library.
- Single-threaded performance is critical and `WITH_SYMENGINE_THREAD_SAFE=OFF`.
- No Python interoperability is needed.

**`teuchos` (default Debug)** -- Use when:
- Debugging memory or ownership issues (Teuchos provides debug-mode reference
  tracking and weak pointer support).
- Building against Trilinos or other Teuchos-based ecosystems.

**`cooperative_intrusive` (opt-in)** -- Use when:
- Building the Python nanobind extension module.
- C++ objects must share identity and reference count with Python wrappers via
  `nb::intrusive_ptr<Basic>`.
- You accept the always-atomic counter overhead (measured in Phase 7
  benchmarks; see the benchmark table in the Phase 7 report).

---

## 4. Python Package Requirements

The Python binding package at the repository root requires:

- **nanobind** -- both as a build-time CMake dependency
  (`find_package(nanobind CONFIG)`) and as a runtime dependency for the
  compiled extension module. Source checkouts use the vendored checkout at
  `external/nanobind/`; standalone configure can point at
  `external/nanobind/cmake`.
- **cooperative_intrusive backend** -- the core SymEngine library must be built with
  `-DSYMENGINE_RCP_BACKEND=cooperative_intrusive`. The Python module will not link
  against a library built with a different backend.
- **CMake option** -- `-DBUILD_PYTHON_NANOBIND=ON` (off by default; decision
  D10).
- **litgen** (generator only, not at runtime) -- required only when
  regenerating the binding code from headers. Use the pinned local checkout at
  `external/litgen/`. srcML must be available.

Build sequence:

```bash
# 1. Build core library with cooperative_intrusive backend
cmake -S . -B build-nb -DCMAKE_BUILD_TYPE=Release \
      -DSYMENGINE_RCP_BACKEND=cooperative_intrusive \
      -DBUILD_PYTHON_NANOBIND=ON -DBUILD_TESTS=ON
cmake --build build-nb -j

# 2. Run Python tests
ctest --test-dir build-nb --output-on-failure
```

---

## 5. Generated File Strategy

### Decision

Generated litgen output is **never tracked in git**:

- `symengine_pydef.cpp` -- litgen output (class and function bindings), git-ignored
- `symengine.pyi` -- Python type stub file, git-ignored

The hand-written `_core` module scaffold **is** tracked:

- `src/core_module.cpp` -- hand-written NB_MODULE wrapper with manual bindings;
  includes generated code via `#include "symengine_pydef.cpp"` but is not itself generated
- `support/nanobind_module_common.h` -- shared helper header (intrusive hooks,
  Basic binding, singleton cleanup) used by both `_core` and
  `symengine_manual_ext`
- `src/rcp_ownership_test_module.cpp` -- minimal test-only ownership validation
  module backing `symengine_manual_ext`

### Build-time generation

- **Source checkouts** regenerate bindings at build time into the build tree
  (`${CMAKE_CURRENT_BINARY_DIR}/generated/`).
- **sdist tarballs** ship pre-generated copies in `generated/` so that
  downstream builds do not require litgen.
- `SYMENGINE_NB_FORCE_REGENERATE=ON` forces regeneration even when
  pre-generated sdist files are present (developer reproducibility checks).

### Verification

CI re-runs `generate.py` via the `BUILD_PYTHON_NANOBIND_REGEN_TESTS` option
and asserts byte-identical output. The `nanobind_generated_policy` test
verifies that no generated artifacts are tracked in git.

### Rationale

- Generated outputs are non-trivial to review and inflate the diff surface.
- The generator is byte-for-byte reproducible (verified by the
  `test_generated_smoke.py` reproducibility test).
- Source-tree builds regenerate automatically; no manual commit step needed.
- sdists include generated files so downstream builds work without litgen.

### Regeneration

To regenerate after modifying headers or the generator:

```bash
export PYTHONPATH="$PWD/external/litgen/src:${PYTHONPATH:-}"
python generator/generate.py generator/generate.yaml
```

Generated files land in `generated/` (git-ignored).
For sdist builds, `make_sdist.sh` generates them into the staged tarball.

---

## 6. Thread Safety and GIL Interactions

### Counter Atomicity

The `cooperative_intrusive` counter is **always atomic**, regardless of the
`WITH_SYMENGINE_THREAD_SAFE` setting. This is a property of nanobind's
`intrusive_counter` implementation, which uses compiler atomic intrinsics
(`__atomic_*` / `_Interlocked*`) rather than `std::atomic`. SymEngine's original
`symengine` backend uses a plain `unsigned int` when thread safety is off.

### GIL Acquisition on Destruction

Once a SymEngine object transitions to Python-owned mode (via `set_self_py`),
any C++ `dec_ref` call routes through the Python `Py_DECREF` hook, which
acquires the GIL. This means:

- Dropping the last C++ reference to a Python-owned object from a thread that
  does not hold the GIL will trigger a `gil_scoped_acquire` inside the
  destructor.
- If a SymEngine internal lock is held at that point, and another thread holds
  the GIL while waiting on that same lock, a **deadlock** occurs.

### Rules for Downstream Users

1. **Single-threaded use is safe.** No special handling is needed.
2. **Multi-threaded use with Python-owned objects:** Do not drop the last
   reference to a Python-owned `Basic` object from a C++ thread while holding
   a SymEngine internal lock. Transfer ownership back to C++ or ensure the GIL
   is not contended.
3. **Static/global objects:** SymEngine global constants (`zero`, `one`, `pi`,
   etc.) that are wrapped in Python become Python-owned. The registered atexit
   cleanup detaches their wrappers before finalization and restores the C++
   references needed by the static registry.
4. **The `use_count()` contract:** For Python-owned objects, `use_count()`
   returns 0 (not the total reference count). Use the backend-neutral
   `is_uniquely_owned()` for ownership-gated optimizations. The dictionary
   stealing optimization in `add.cpp` is enabled for C++-owned cooperative
   objects and remains disabled for foreign-owned objects.

---

## 7. CI Coverage Summary

| CI Job | Backend | Thread Mode | What It Covers |
|--------|---------|-------------|----------------|
| Default Release | `symengine` | OFF | Full C++ test suite, original backend regression |
| Default Debug | `teuchos` | OFF | Full C++ test suite, Teuchos debug checks |
| cooperative_intrusive Release | `cooperative_intrusive` | OFF | Full C++ test suite + RCP tests + counter query tests |
| cooperative_intrusive Thread-Safe | `cooperative_intrusive` | ON | Same as above, validates atomic counter under contention |
| Python nanobind tests | `cooperative_intrusive` | OFF | Manual ownership tests (35), generated smoke (41), generated RCP (108), threading stress (8) |
| Sanitizer (ASAN/UBSAN) | `cooperative_intrusive` | OFF | Memory safety, pointer punning, ownership boundary |
| `use_count() == 1` guard | All | All | Regression script banning new `use_count() == 1` sites |
| Generator no-diff | N/A | N/A | Re-runs `generate.py`, asserts byte-identical output |

---

## 8. Decision D8: Non-Atomic Counter Variant

Decision D8 (a SymEngine-owned non-atomic counter variant, modeled on
`refcount-py-cxx`) is **deferred** until benchmarks demonstrate that the
always-atomic overhead of `cooperative_intrusive` is unacceptable for single-threaded
workloads. The Phase 7 benchmark results determine whether this work proceeds.

If implemented, the variant must:
- Use the same bit-0 ownership encoding as nanobind's `intrusive_counter`.
- Be non-atomic when `WITH_SYMENGINE_THREAD_SAFE=OFF`, `std::atomic` when ON.
- Pass the entire Phase 2/3 C++ suite and Phase 4 Python lifecycle suite as a
  drop-in replacement.
