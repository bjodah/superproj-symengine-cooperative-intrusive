# 25 — Shared binding generation roadmap

**Date:** 2026-07-11 (revised)
**Status:** Implemented. Phase 0: 51c11cf, toolchains ea59e75, Phase 1: 59fb1e3,
Phase 2: cbb816b, Phase 3: 9aa0bbc, Phase 4: e5a5542, fixture/check/matrix:
a74a6dd+72b31ef, Phase 5: bf548ce+b1614dc. The sdist `GENERATION_MANIFEST` item
under "Build and CI integration" remains deferred.

**Status note (2026-07-28), generator invocation unified:** every CMake caller
now goes through `cmake/BindingCodegen.cmake`'s `symengine_binding_codegen()`,
which owns the single canonical DEPENDS list (spec, schema, test cases, and all
`tools/binding_codegen/*.py` sources). Call sites: the Perl block in
`CMakeLists.txt`, `symengine.java/CMakeLists.txt`, and the two shared-spec
commands in `nbsymengine/CMakeLists.txt` (adapter glue plus the shared
behavioral pytest file, now rendered by the build into
`<build>/binding-generated/python/` instead of by `.ci/ci-02-*`). The litgen
command in `nbsymengine/CMakeLists.txt` is a different generator and is
untouched. `symengine.php/config.m4` no longer writes into the tracked source
tree: it renders into `$abs_builddir/generated` and adds that directory to
`INCLUDES`, so a configure+build leaves `git status` clean.
**Audience:** Developer implementing shared codegen across the language wrappers.

## Purpose

This document proposes a practical way to make `nbsymengine` more mechanically
generated and to share API descriptions across the Python, Perl, PHP, Swift,
and (new) Java wrappers. It is an implementation plan, not a request to put
binding-specific code into upstream SymEngine.

The main design rule is:

> SymEngine headers define what the C++ API is; a small declarative file defines
> which parts are exposed and how language-specific edges are adapted.

Do not copy complete C++ signatures into YAML. That would create a second C++
API which inevitably becomes stale.

A second design rule falls out of adding Java (see below):

> The shared spec describes the API surface only. It must be equally usable by
> a wrapper that participates in cooperative_intrusive ownership (Python, Perl,
> PHP, Swift) and by one that holds ordinary `RCP<const Basic>` handles (Java).
> Any field that would only make sense for one ownership model does not belong
> in the spec.

## What exists today

The current Python generator is a useful foundation, but its configuration is
spread across several places:

- `nbsymengine/generator/generate.yaml` selects headers and carries exclusion
  lists.
- `nbsymengine/generator/generate.py` contains the class hierarchy
  (`_SYMENTITY_HIERARCHY`, ~100 entries), type-name repairs (`_sanitize_stub`),
  manual `.pyi` declarations (`_MANUAL_FUNCTION_STUBS`), and litgen
  customization.
- `nbsymengine/generator/simple_functions.json` describes 70 relatively simple
  free functions across 7 adapter kinds (`unary_basic`: 40, `binary_boolean`: 6,
  `binary_basic`: 5, `integer_unary`: 3, `integer_binary`: 2,
  `status_optional_unary`: 10, `list_integer_to_basic`: 4), rendered by
  `gen_simple_functions.py` into a `.inc` plus stub lines.
- `nbsymengine/src/core_module.cpp` is still about 1,485 lines (123
  `m.def`/`nb::class_` statements) and binds arithmetic operators, matrices,
  lambdify/LLVM visitors, number theory, sets, constants, and ownership/debug
  helpers by hand.
- `nbsymengine/generator/api_inventory.yaml` is a snapshot derived from the
  legacy Cython wrapper, but it is not currently consumed by the generator.
- Perl, PHP, and Swift each repeat a small common surface. Concretely: 12 of
  the 19 Perl XSUBs, roughly 22 of the 24 `PHP_FUNCTION`s, and all of the
  Swift C-bridge value functions are mechanical
  factory/constant/arithmetic/`sin`-style call-throughs that differ only in
  naming convention and error surface.
- CI (`.ci/run-ci-steps.sh`) builds and tests the C++ core, nbsymengine,
  nbsymengine_compat, Perl (`ci-05`), and PHP (`ci-06`). **There is no Swift CI
  lane** even though `symengine.swift` builds and passes its XCTests locally,
  and there is no Java wrapper at all yet.
- Upstream SymEngine ships `symengine/cwrapper.h`, a C API whose
  `basic_struct` embeds an `RCP<const Basic>` and which translates C++
  exceptions into status codes. It compiles under all three RCP backends
  (there is a cooperative-aware `static_assert` at `cwrapper.cpp:149`). It is
  prior art for the Java handle design, though not the recommended call target
  (see the Java section).

There are three important kinds of code here, and they should not be conflated:

1. **API surface:** names, arguments, result categories, documentation, and
   availability. This is safe to share.
2. **Mechanical language glue:** repetitive argument conversion, calls, error
   translation, and return wrapping. This can be generated per language.
3. **Runtime ownership:** nanobind intrusive hooks, Perl `SV` handling, Zend
   object storage, Swift ARC adoption, and Java handle lifecycle. This is
   language-specific and should remain small, reviewed, hand-written code.

Generating category 3 would hide the most safety-sensitive part of each
wrapper. The initial effort should generate categories 1 and 2 only.

## Target layout

Start with a super-project-owned specification because all wrappers are
assembled and tested here:

```text
binding-spec/
  api.yaml                 shared exposure and adaptation intent
  schema.json              machine-readable schema for api.yaml
  README.md                field definitions and contributor workflow
  test-cases.yaml          optional language-neutral smoke cases
tools/binding_codegen/
  __main__.py              validate/generate/check CLI
  model.py                 typed intermediate representation
  inspect_cpp.py           header/signature validation
  render_nbsymengine.py
  render_perl.py
  render_php.py
  render_swift.py
  render_java.py
  templates/
```

Generated files should go to build directories, not source directories. The
one exception is a published wrapper repository that cannot access the shared
spec at build time: it may commit a generated snapshot, but CI must reproduce
that snapshot with `python -m tools.binding_codegen check`.

Build systems that have no separate build tree of their own still honour this:
`symengine.php/config.m4` renders into `$abs_builddir/generated` (ignored by
`symengine.php/.gitignore` for the usual in-tree `phpize` build), and the Swift
plugin renders into SwiftPM's plugin work directory.

If these wrappers later move to separate repositories, move `binding-spec/` and
the generator into a small versioned repository or Python package. Each wrapper
can pin a commit and publish the pin in its generation manifest. Do not put the
shared spec in upstream SymEngine merely to make it reachable; keeping the
upstream patch generic and small is more valuable.

## Proposed YAML model

Use YAML for readability and JSON Schema for strict validation. Parse it once
into a typed intermediate representation; renderers must not read arbitrary
YAML dictionaries directly.

```yaml
schema_version: 1

types:
  basic:
    cpp: SymEngine::RCP<const SymEngine::Basic>
    category: expression
  integer:
    cpp: SymEngine::RCP<const SymEngine::Integer>
    category: expression
    extends: basic
  string:
    cpp: std::string
    category: value

functions:
  - id: add
    cpp:
      name: SymEngine::add
      header: symengine/add.h
    arguments:
      - {name: left, type: basic}
      - {name: right, type: basic}
    returns: basic
    behavior: pure
    expose: [python, perl, php, swift, java]
    names:
      php: symengine_add     # php default would also be symengine_add; shown for clarity

  - id: pi
    cpp:
      expression: SymEngine::pi
      header: symengine/constants.h
    arguments: []
    returns: basic
    behavior: singleton
    expose: [python, perl, php, swift, java]

  - id: sin
    cpp:
      name: SymEngine::sin
      header: symengine/functions.h
    arguments:
      - {name: value, type: basic}
    returns: basic
    behavior: pure
    expose: [python, perl, java]
```

Required fields should be `id`, `cpp`, `arguments`, `returns`, and `expose`.

Language names must default predictably from `id` and be overridden only where
the language convention differs. Concretely:

| language | default derivation from `id` | example (`logical_and`) |
|---|---|---|
| python | unchanged | `logical_and` |
| perl | unchanged | `logical_and` |
| php | `symengine_` prefix | `symengine_logical_and` |
| swift | lowerCamelCase | `logicalAnd` |
| java | lowerCamelCase | `logicalAnd` |

The validator must check the *resolved* name of every entry against a
per-language reserved-word list and reject collisions unless an explicit
override is present. Precedent: Perl exposes `sub` today, which works only
because callers use the fully qualified `SymEngine::sub(...)`; Swift already
renames `sub`/`mul`/`div`/`pow`/`neg` to
`subtract`/`multiply`/`divide`/`power`/`negate`. Such intentional divergences
belong in `names:`, not in renderer code.

Adapter families should be seeded from the seven kinds that
`simple_functions.json` already proves out (`unary_basic`,
`binary_basic`, `binary_boolean`, `integer_unary`, `integer_binary`,
`status_optional_unary`, `list_integer_to_basic`), plus `singleton` for
constants. They are the `behavior`/adapter vocabulary of schema version 1;
new families are added by need, never speculatively.

Keep these fields out of the first schema version:

- raw template text;
- arbitrary C++ snippets;
- reference-count increments or decrements;
- language runtime pointers;
- exception-handling code;
- anything specific to one ownership model (cooperative hooks, externalization,
  Java handle allocation).

If an entry needs one of those, mark it `manual` with a reason and bind it in
the relevant runtime file. This keeps the spec declarative.

### Determinism requirements

"Byte-for-byte reproducible" needs a definition, or it will be discovered the
hard way on the first cross-machine `check` failure:

- render entries sorted by `id` (input order in `api.yaml` is not significant);
- emit LF newlines and UTF-8 unconditionally, independent of platform;
- no timestamps, hostnames, usernames, or absolute paths in output;
- the spec digest is SHA-256 over the canonicalized (parsed and re-serialized
  with sorted keys) spec, so whitespace-only YAML edits do not churn digests;
- every generated file carries a header with: schema version, spec digest,
  generator version, and a `DO NOT EDIT` banner.

## Outputs from one intermediate representation

| Consumer | Generated output | Hand-written boundary |
|---|---|---|
| `nbsymengine` | free-function `.inc`, matching `.pyi` declarations, exact litgen exclusions | intrusive hooks, complex matrix/lambdify adapters |
| Perl | an XS include containing repetitive functions and an export-name list | `SV` ownership, wrapper identity, `DESTROY` |
| PHP | function handlers plus a PHP stub/arginfo source | Zend object lifecycle and module hooks |
| Swift C bridge | declarations and simple C++ call-through functions | ARC hooks, externalization, lock/adoption protocol |
| Swift API | public factory/operation methods | `Basic` class lifecycle and typed downcasts |
| Java JNI glue | `Java_org_symengine_SymEngineJNI_*` call-through implementations | handle allocation/free, exception translation, `JNI_OnLoad` |
| Java API | `SymEngineJNI.java` native declarations, `SymEngine.java` factory/operation methods | `Basic.java` (Cleaner lifecycle), `SymEngineException.java`, kind→class downcast map |

Every generated file must contain the header described under "Determinism
requirements".

### Error-translation policy (fixed per language, never per entry)

The renderer wraps every generated call in the language's one blessed
error-translation idiom. The spec never describes exception handling:

| language | translation |
|---|---|
| python | nanobind's built-in C++→Python exception translation |
| perl | `try { ... } catch (...) { croak_current_exception(); }` (existing helper) |
| php | catch → `zend_throw_exception` (existing `symengine_throw_cpp_exception`) |
| swift | catch → status code + `symengine_swift_last_error` (existing bridge protocol) |
| java | catch → throw `org.symengine.SymEngineException` (unchecked), then return a dummy value |

## `symengine.java`: a JNI wrapper on ordinary RCP

A new wrapper, `symengine.java/`, is added to the roadmap with a deliberately
different ownership design from the other four:

- It does **not** use `symengine_cooperative_intrusive_counter`. It links a
  symengine build with the ordinary intrusive backend
  (`SYMENGINE_RCP_BACKEND=symengine`) and holds plain
  `RCP<const Basic>` handles.
- No hook initialization, no `externalize`/`adopt`/wrapper-lock protocol, no
  identity reuse. Two Java objects may wrap the same C++ object.

This is not just "one more wrapper": it is the control experiment for the
shared spec. If `binding-spec/api.yaml` can drive both a cooperative wrapper
(Swift) and a plain-handle wrapper (Java) from the same entries, the spec has
stayed at the right altitude (category 1 only). Any spec field that the Java
renderer must ignore "because Java doesn't do cooperative ownership" is a
design smell to fix in the spec, not in the renderer. It also gives CI a lane
that exercises the upstream-default RCP backend, which today no wrapper lane
covers (all export `SYMENGINE_RCP_CHOICE=cooperative_intrusive`).

### Ownership and lifecycle

- A Java `Basic` holds a `long` handle that is a pointer to a heap-allocated
  `SymEngine::RCP<const SymEngine::Basic>` cell (the same shape as upstream
  `cwrapper.h`'s `basic_struct`, minus the placement-new gymnastics).
- The handle is released by a `java.lang.ref.Cleaner` registered at
  construction. Do **not** use `Object.finalize()` (deprecated for removal,
  resurrects objects, unbounded latency). `Basic` may additionally implement
  `AutoCloseable` for deterministic release in benchmarks; `close()` must be
  idempotent and make the Cleaner action a no-op.
- Because the JVM has real threads and Cleaner actions run on their own
  thread, the Java lane must build symengine with
  `WITH_SYMENGINE_THREAD_SAFE=ON` so refcount updates are atomic. Without it,
  a Cleaner decref racing an application-thread incref corrupts counts. State
  this in `symengine.java/README.md`.
- Structural equality (`equals`/`hashCode` via `SymEngine::eq`/`hash`) is the
  public contract. A `sameInstance(Basic)` test helper may compare raw
  pointers, but the README must document that wrapper identity (`==`) means
  nothing — the deliberate opposite of the cooperative wrappers' canonical
  identity-reuse guarantee.

### Why generated JNI glue rather than binding `cwrapper.h`

Upstream `cwrapper.h` was considered as the Java call target and rejected as
the *generated* path, because its `basic_add`-style names would introduce a
third naming layer into the spec, its coverage lags the C++ API, and its
out-parameter convention differs from every other renderer's return-value
convention. Instead, the Java renderer emits JNI functions that call
`SymEngine::add(...)` etc. directly — the same adapter families and the same
`cpp.name` spec field as the Swift C-bridge renderer. `cwrapper.h` remains
useful as prior art for the handle cell and the status-code discipline, and as
a hand-written fallback for anything the renderer does not support yet.

### Layout

```text
symengine.java/
  CMakeLists.txt              FindJNI + UseJava (add_jar); no Gradle/Maven
  README.md                   ownership contract, thread-safety note
  src/main/java/org/symengine/
    Basic.java                handle + Cleaner + equals/hashCode/toString   (manual)
    SymEngineException.java   unchecked exception                           (manual)
    SymEngineJNI.java         native method declarations                    (generated in Phase 4)
    SymEngine.java            public factory/operation methods              (generated in Phase 4)
  src/main/native/
    symengine_jni.cpp         JNI_OnLoad, handle helpers, throw helper      (manual)
    symengine_jni_generated.cpp                                             (generated in Phase 4)
  src/test/java/org/symengine/
    SmokeTest.java            assert-based main(), run via ctest
```

Build notes: plain JDK toolchain (`javac`/`jar` via CMake's `UseJava`), JDK 21
is available in the CI image and locally. No Gradle/Maven and no JUnit
download — the "no network during generation/build" rule applies to wrapper
builds too; an assert-based `main()` runner matches the simplicity of the
`.t`/`.phpt` suites. `JNI_OnLoad` caches `jclass` (as global refs) and
`jmethodID`s once; the CI lane runs tests with `-Xcheck:jni`.

## Implementation phases

### Phase 0: protect the current behavior

1. Add a fast API smoke test for each wrapper covering `symbol`, `integer`,
   `zero`, `one`, `pi`, `add`, `sub`, `mul`, `div`, `pow`, `neg`, equality, and
   string conversion where currently supported.
2. Add identity/ownership tests separately. Generation work must not change
   those tests.
3. Record the current public Python names and stub declarations in a normalized
   text fixture. Do the equivalent for exported Perl, PHP, and Swift names
   (XSUB list, `PHP_FUNCTION`/arginfo table, C-bridge header + public Swift
   API).
4. **Add the missing Swift CI lane** (`ci-07-build-and-test-swift.sh`, modeled
   on the Perl lane; `swift` is present in the CI image). Rewiring Swift
   sources onto a generator without CI coverage would be flying blind.
5. Run these tests before introducing the spec. Their purpose is to detect an
   accidental API change while code moves from hand-written to generated.

Acceptance criterion: all tests pass without generated code changes, and every
wrapper that will be rewired has a CI lane.

### Phase 1: create and validate the shared spec

1. Create `binding-spec/schema.json` with `additionalProperties: false` at
   every object level. Typos must fail validation.
2. Add only the common functions already implemented in at least two wrappers.
   Do not begin by describing all of SymEngine.
3. Implement `python -m tools.binding_codegen validate`.
4. During validation, confirm that every named header exists and use srcML,
   libclang, or litgen's parsed model to confirm that the selected function and
   overload exist. Prefer the parser already available through litgen/srcML
   unless it cannot reliably identify overloads.
5. Reject duplicate resolved public names within one language, unknown type
   IDs, missing renderers, ambiguous overloads, unsupported default values,
   and reserved-word collisions (see the name-defaulting table).
6. Add unit tests with intentionally invalid fixtures for each rejection path.

Acceptance criterion: changing `SymEngine::add` to a nonexistent function or
misspelling `returns` causes a clear validation failure naming the YAML entry.

### Phase 2: reduce hand-written `nbsymengine`

Do this incrementally, one adapter family at a time:

1. Move `simple_functions.json` entries into `binding-spec/api.yaml`. Preserve
   their current `kind` information as the adapter-family name.
2. Generate both `symengine_simple_funcs.inc` and its `.pyi` declarations from
   the same model. Delete the corresponding declarations from
   `_MANUAL_FUNCTION_STUBS`. (Note: the stubs currently listed under the
   "Logic" comment in `_MANUAL_FUNCTION_STUBS` are *hand-bound* variadic and
   container functions from `core_module.cpp`, not `simple_functions.json`
   output; they migrate only when a variadic adapter family exists.)
3. Generate exact-name litgen exclusions from entries owned by a manual or
   generated adapter. Keep only regex/infrastructure exclusions in
   `generate.yaml`.
4. Add renderers in this order: constants, unary expression functions, binary
   expression functions, integer unary/binary functions, optional-status
   results, and list results.
5. Move the hard-coded `_SYMENTITY_HIERARCHY` into generated parser metadata or
   derive it from the C++ headers. Keep a small override table only for binding
   names that intentionally differ.
6. Replace `_sanitize_stub()` string substitutions with litgen type adapters.
   A textual repair such as replacing `"-> unsigned int int:"` is fragile and
   should become a regression test before it is removed. The same applies to
   the two `.replace()`-anchored `is_*` stub injections in `generate.py`,
   which already fail hard when litgen's layout shifts — fold them into the
   generated model.
7. Split the remaining `core_module.cpp` into focused files even when they stay
   manual: `ownership_runtime.cpp`, `matrix_bindings.cpp`,
   `lambdify_bindings.cpp`, and `special_adapters.cpp`. The module initializer
   should call one registration function per file.
8. Make `api_inventory.yaml` either an enforced coverage report or delete it.
   A generated-but-unused inventory is misleading. The legacy Cython inventory
   is useful for `nbsymengine_compat` coverage, but it should not define the thin
   wrapper's C++ API.

After each adapter family, run generation twice and compare hashes, build the
extension, run `nbsymengine/tests`, and run `nbsymengine_compat/tests`.

Acceptance criterion: adding a supported free function requires one YAML entry
and tests, with no edits to C++, `.pyi`, or exclusion lists.

### Phase 3: generate the common Perl, PHP, and Swift surface

1. Implement the Perl renderer first because the current XS functions are
   repetitive and the surface is small (12 of 19 XSUBs). Generate an included
   `.xs.inc`; leave initialization, unwrapping, wrapping, diagnostics, and
   destruction manual.
2. Implement the PHP renderer. Generate function handlers and declarations from
   the same entries. Prefer a generated PHP stub as the source of arginfo so
   PHP-visible signatures are not separately hand-maintained. Keep Zend object
   creation/free handlers and module lifecycle manual.
3. Implement the Swift renderer in two layers: C ABI declarations/call-through
   implementations, then public Swift forwarding methods. Keep hook
   initialization, ARC retain/release, `adopt`, externalization, and locking
   manual.
4. Add per-language overrides only for names, error surface, and return
   refinement.
5. Generate a coverage report listing `generated`, `manual`, and `not exposed`
   for every spec entry and language (including `java`, all `not exposed`
   until Phase 4). Fail CI on an unclassified entry.

Acceptance criterion: adding a simple binary expression function for the four
existing languages is one YAML change plus behavior tests; all renderers either
emit code or report a precise unsupported-adapter error.

### Phase 4: bootstrap `symengine.java` and its renderer

Deliberately after Phase 3: the Java wrapper starts life generated, so the
renderer contract should already be proven on the existing wrappers. Split it
in two PR-sized steps:

1. **Hand-written bootstrap.** Create the layout above with a hand-written
   surface matching the other wrappers (`symbol`, `integer`, constants,
   arithmetic, `neg`, equality, `toString`), plus the manual runtime files.
   Build via super-project CMake behind `-DBUILD_JAVA_JNI=ON`; add
   `ci-08-build-and-test-java.sh` configuring a **separate build tree** with
   `SYMENGINE_RCP_BACKEND=symengine` and `WITH_SYMENGINE_THREAD_SAFE=ON`
   (`-DBUILD_JAVA_JNI=ON` must fail configuration under
   `cooperative_intrusive`; one process must never mix RCP backends, so the
   Java lane cannot share the cooperative build trees). Tests: smoke test per
   Phase 0, plus Java-specific lifecycle tests (Cleaner actually frees —
   observable via a native live-handle counter; `close()` idempotent;
   multi-threaded create/drop stress under `-Xcheck:jni`).
2. **Java renderer.** Add `render_java.py` emitting the three generated files.
   Replace the bootstrap's mechanical functions; the manual files shrink to
   runtime-only code. Update the coverage report so `java` rows flip from
   `manual`/`not exposed` to `generated`.

Acceptance criterion: the acceptance criterion of Phase 3 now covers five
languages, and the Java smoke tests pass against generated glue with
`-Xcheck:jni` enabled.

### Phase 5: share behavioral tests and documentation

Add conservative language-neutral cases to `binding-spec/test-cases.yaml`:

```yaml
cases:
  - id: add_integers
    arrange:
      x: {integer: 2}
      y: {integer: 3}
    call: {function: add, arguments: [x, y]}
    expect: {string: "5"}
```

Render native pytest, Perl `.t`, PHP `.phpt`, XCTest, and Java assert-runner
cases. Do not encode ownership or identity assertions here; those remain
native tests because their runtime semantics differ — Java's lack of
canonical wrapper identity is the standing example of why.

Generate a small API matrix for documentation from the coverage report. This
prevents READMEs from claiming a function that its wrapper does not expose.

## Build and CI integration

Expose the following commands before wiring generation into every build:

```bash
python -m tools.binding_codegen validate
python -m tools.binding_codegen generate --language python --output build/generated/python
python -m tools.binding_codegen generate --language perl --output build/generated/perl
python -m tools.binding_codegen check
```

`check` should generate into a temporary directory and compare committed
snapshots where snapshots are necessary. It should never rewrite the working
tree. Every build-system caller must list the spec, schema, test cases, and all
generator sources in `DEPENDS` so edits trigger regeneration. That list is
maintained once, in `cmake/BindingCodegen.cmake`; CMake callers invoke

```cmake
symengine_binding_codegen(
    LANGUAGE <python|perl|php|swift|java>
    OUTPUT_DIR <build-tree dir>
    OUTPUTS <generated files>
    [ARTIFACT <all|cpp|api|tests>] [TARGET <name>] [ALL]
    [PYTHON <interpreter>] [ENVIRONMENT <VAR=value>...] [DEPENDS ...] [COMMENT ...])
```

rather than repeating the command and its dependency list. The non-CMake
callers (`symengine.php/config.m4`,
`symengine.swift/Plugins/BindingCodegenPlugin`) run the same CLI keyed on
`BINDING_CODEGEN_ROOT`/`BINDING_CODEGEN_PYTHON`.

Add a CI job that runs validation and every renderer without compiling — it is
cheap and keeps renderers honest even for languages whose toolchain lane is
temporarily disabled. Keep the existing compile/test lanes as the
authoritative end-to-end check, extended by:

- `ci-07-build-and-test-swift.sh` (Phase 0) — cooperative backend, like Perl/PHP;
- `ci-08-build-and-test-java.sh` (Phase 4) — **ordinary backend**
  (`SYMENGINE_RCP_BACKEND=symengine`, `WITH_SYMENGINE_THREAD_SAFE=ON`), its own
  build tree, tests run with `-Xcheck:jni`.

For the `nbsymengine` sdist, copy the spec, schema version, and generated files
into the staged archive. Extend `GENERATION_MANIFEST.txt` with the spec digest
and generator commit.

## Suggested first pull requests

1. **Phase 0 fixtures and Swift CI lane:** smoke tests, name fixtures,
   `ci-07`; generate nothing.
2. **Validation only:** add the schema, model, validator, and ten shared
   entries; generate nothing.
3. **Python constants and arithmetic:** emit the simplest `nbsymengine`
   fragment and matching stubs; prove byte-for-byte reproducibility.
4. **Migrate `simple_functions.json`:** preserve behavior, then remove the old
   JSON and manual stub duplication.
5. **Perl renderer:** replace only `symbol` through `sin` in `SymEngine.xs`.
6. **PHP renderer:** replace only module-level constant/arithmetic handlers.
7. **Swift renderer:** replace only C call-throughs and `SymEngine` forwarding
   methods.
8. **`symengine.java` bootstrap:** hand-written wrapper, `ci-08`, lifecycle
   tests; no renderer.
9. **Java renderer:** replace the bootstrap's mechanical surface.
10. **Generated smoke tests and API matrix.**

Each pull request should be independently revertible and should avoid changes
to cooperative ownership code.

## Pitfalls to avoid

- Do not make YAML a full interface-definition language. Let C++ headers own
  types and signatures.
- Do not generate ownership transitions until the API generator has been stable
  for several releases; these transitions deserve direct review.
- Do not infer that identically named functions have identical language
  semantics. Variadic arguments, optionals, exceptions, matrices, and numeric
  conversion need explicit adapter families.
- Do not silently skip unsupported entries. A renderer must emit code or fail
  with the entry ID and reason.
- Do not mix legacy `symengine.py` compatibility policy into `nbsymengine`.
  Use the legacy inventory to measure the compatibility shim, not to bloat the
  thin binding.
- Do not require network access during generation or wrapper builds. Pin tools
  and consume local headers and specs; this is also why `symengine.java` uses
  CMake+`javac` rather than Gradle/Maven.
- JNI-specific traps for the Java renderer's fixed preamble/epilogue (they are
  runtime-file concerns, never spec concerns):
  - `GetStringUTFChars`/`NewStringUTF` speak *Modified* UTF-8; convert via
    `String.getBytes(StandardCharsets.UTF_8)` on the Java side for anything
    beyond ASCII symbol names.
  - After throwing a Java exception from native code, return immediately; do
    not call further JNI functions.
  - `DeleteLocalRef` inside loops that create local references (list/dict
    adapters).
  - Never load two symengine builds with different RCP backends into one
    process; the Java lane owns its build tree.
- Do not let the cooperative wrappers' identity-reuse guarantee leak into
  shared tests or docs as if it were universal — Java intentionally does not
  provide it.

## Definition of done

The shared-generation effort is successful when:

- the public surface for each language is reported automatically;
- one declarative entry produces implementation glue, declarations/stubs, and
  smoke tests for supported adapter families;
- generated output is deterministic (per the determinism requirements) and
  checked in CI;
- `nbsymengine` no longer duplicates generated free-function declarations in
  Python strings, C++ code, and exclusion lists;
- language-specific ownership code remains easy to locate and review;
- `symengine.java` exposes the common surface from the same spec entries as
  the cooperative wrappers while linking the ordinary RCP backend — proving
  the spec carries no ownership-model assumptions;
- every wrapper, including Swift and Java, has a CI lane; and
- no binding metadata or language runtime dependency is added to upstream
  SymEngine.
