# Overview
This is a super-project around SymEngine.

## List of submodules

- `./symengine/`: SymEngine library C++ repo, now with "cooperative_intrusive" reference counted pointer (RCP) suitable for external reference counting in a foreign language runtime. We want our patch to this main repository of symengine to be as small and generic as possible. The reference counting technique employed here, which relies on storing the count as a union represented by *either* a left-shifted-by-1bit-unsigned-integer-count&lowest-bit-set-to-one-as-tag/flag *or* as an `uintptr_t` with lowest-bit-equal-to-zero-due-to-alignment-which-points-to-externally-reference-counted-object-in-third-party-language-with-incref-and-decref-callable, should usable by C++ bindings for Python via nanobind, and other reference counted languages (swift, perl, php).
- `./symengine.py/`: The current official Python bindings project of SymEngine (hand-written in Cython). We will not be modifying this repo, we simply use it as a source of (mechanically) auto-transcribed tests for `nbsymengine_compat`.

## Projects not (yet) in dedicated submodules

- `./nbsymengine/`: A proposed "Next generation" Python bindings for SymEngine using nanobind (tries to maximize code-generation, currently via "litgen"). Aims to be a *thin* wrapper around SymEngine, users are expected to write more ergonomic wrappers based on this package. Entry point for the Python bindings documentation: `./nbsymengine/README.md`.
- `./nbsymengine_compat/`: A "shim library" that uses `nbsymengine`, but exposes an API-compatible with legacy `symengine.py` (pytest based unit tests from symengine.py are mechanically exported/generated). Acts as an example of what an ergonomic package based on nbsymengine might looke like, also serves as a downstream testbed for nbsymengine (a cheap way to get test coverage thanks to allowing mechanically transcribed tests from symengine.py to be run against the nbsymengine wrapper). Note that nbsymengine_compat **may not** monkey-patch `nbsymengine` (or it would interfere with 3rd party packages).
- `./symengine.pl/`: A wrapper for Perl using `symengine_cooperative_intrusive_counter`.
- `./symengine.php/`: A wrapper for PHP using `symengine_cooperative_intrusive_counter`.
- `./symengine.swift/`: A wrapper for swift using `symengine_cooperative_intrusive_counter`.
- `./symengine.java/`: A wrapper for Java that is **not using** `symengine_cooperative_intrusive_counter`. This package should still benefit from the "codegen first" principle to bindings generation taken in this repo.

## Misc

- `./benchmarks/`: Contrast performance between legacy `symengine.py` and `nbsymengine`.
- `./.ci/`: CI scripts (build-and-test workflows), moved here from `symengine/.ci/`.
- `./docs/`: (meta-)docs for super project (tracking current progress).
- `./binding-spec/`: input for codegen of binding wrappers (both SymEngine API and test cases)
- `./tests/`: tests for the codegen tools
- `./tools/`: binding_codegen tool

## Prerequisites

#CI config in (see .woopecker.yaml): `pip install munch srcml_caller libcst`
Note that litgen (github.com/pthom/litgen.git) is available at: /opt-6/litgen-6085aaa/

FYI:
```console
$ ls -d /opt-6/php-8.5.7-*
/opt-6/php-8.5.7-asan  /opt-6/php-8.5.7-debug  /opt-6/php-8.5.7-release
$ ls -d /opt-6/perl-*
/opt-6/perl-v5.43.11-asan  /opt-6/perl-v5.43.11-debug
$ java --version
openjdk 21.0.11 2026-04-21
OpenJDK Runtime Environment (build 21.0.11+10-1-deb13u2-Debian)
OpenJDK 64-Bit Server VM (build 21.0.11+10-1-deb13u2-Debian, mixed mode, sharing)
$ swiftc --version
Swift version 6.0.3 (swift-6.0.3-RELEASE)
Target: x86_64-pc-linux-gnu
```
