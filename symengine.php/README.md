# SymEngine PHP Extension

PHP extension for SymEngine (computer algebra system) using the `cooperative_intrusive` RCP backend.

## Purpose

This extension serves as a validation project for the SymEngine `cooperative_intrusive` reference-counting backend. It demonstrates that a PHP extension can correctly participate in shared reference counting with SymEngine's C++ objects.

**This is not yet a production-ready user-facing package.** The API is minimal and intentionally kept small to focus on lifetime/ownership correctness.

## Prerequisites

- PHP 8.1+ development headers (`php-dev` / `php-devel`)
- SymEngine built with `-DSYMENGINE_RCP_BACKEND=cooperative_intrusive`
- C++17 compatible compiler
- GNU Autotools (`phpize`, `autoconf`, `automake`, `libtool`)

## Source of Truth

The following files are the **source of truth** (committed to version control):

- `config.m4` — Extension configuration
- `configure.ac` — Autoconf input
- `src/*.cpp`, `src/*.h` — C++ extension source
- `tests/*.phpt` — PHPT test files
- `README.md` — This file

**Generated build artifacts are ignored** (see `.gitignore`). Do not commit:
- `configure`, `Makefile`, `config.h`, `libtool`
- `.libs/`, `modules/*.so`, `*.lo`, `*.la`
- `autom4te.cache/`, `config.log`, `config.status`

## Building

```bash
# 1. Build and install SymEngine with cooperative_intrusive backend
cd /path/to/symengine
mkdir build && cd build
cmake -DSYMENGINE_RCP_BACKEND=cooperative_intrusive -DCMAKE_BUILD_TYPE=Release ..
make -j$(nproc)
sudo make install
sudo ldconfig

# 2. Build the PHP extension
cd /path/to/symengine.php
phpize
./configure --with-php-config=/path/to/php-config
make -j$(nproc)

# 3. Install the extension (system-wide or for current user)
sudo make install
# OR for development:
# cp modules/symengine.so $(php-config --extension-dir)/
# echo "extension=symengine.so" > /etc/php/8.x/mods-available/symengine.ini
# phpenmod symengine
```

## Running Tests

The extension uses standard PHPT tests located in `tests/`.

```bash
# Run all tests
cd /path/to/symengine.php
php run-tests.php -d extension=modules/symengine.so tests/

# Run specific test
php run-tests.php -d extension=modules/symengine.so tests/001-load.phpt

# Verbose output
php run-tests.php -v -d extension=modules/symengine.so tests/
```

### Test Suite

| Test | Purpose |
|------|---------|
| `001-load.phpt` | Extension loads, version/info smoke test |
| `010-basic-ops.phpt` | Integer, symbol, add, sub, div, mul, neg, pow, str, eq with stable outputs |
| `015-constructor-ban.phpt` | Direct `new SymEngine\Basic`/`Integer`/`Symbol` fails clearly |
| `020-identity-reuse.phpt` | Singleton identity reuse; `sameObject()` returns true |
| `025-canonical-identity-reuse.phpt` | Canonical `add(x, 0)` reuses the existing wrapper |
| `030-external-ownership.phpt` | `isExternalOwned()` true after wrapping; `phpRefCount()` predictable |
| `035-debug-helpers.phpt` | Extension-specific debug helpers expose ownership state when enabled |
| `040-temporary-cpp-handles.phpt` | Temporary C++ handles don't break ownership |
| `045-expression-pins-operand.phpt` | Expression-held C++ `RCP` pins an operand wrapper |
| `050-singleton-teardown.phpt` | Subprocess holding live singleton wrappers until exit |
| `060-expression-teardown.phpt` | Subprocess holding non-singleton expressions until exit |
| `065-loop-teardown.phpt` | Looped child-process lifetime smoke with canonical reuse |

## Architecture Overview

### Cooperative Intrusive RCP

SymEngine's `cooperative_intrusive` backend allows foreign runtimes (PHP, Perl, Python, etc.) to participate in reference counting:

- C++ objects store either an inline refcount (LSB=1) or a pointer to an external owner (LSB=0, aligned)
- PHP registers `inc_hook`/`dec_hook` callbacks that manipulate `zend_object` refcounts
- When a C++ object is "externalized" to PHP, its refcount becomes the PHP object's refcount
- Singleton reconciliation at shutdown detaches external ownership and replays inline refcounts

### Key Invariants

1. **Single externalization**: `set_self_external()` called exactly once per object
2. **Identity reuse**: Wrapping the same C++ singleton returns the same PHP object
3. **Hook safety**: Cooperative hooks become inert only during the narrow shutdown window that can no longer safely touch Zend objects
4. **Singleton teardown**: Wrapped singletons are external-owned during runtime, then reconciled back to inline mode during request shutdown

## Runtime Lifecycle Note

The currently verified shutdown strategy covers CLI and a local FPM smoke
harness.

- During normal runtime, both singleton and non-singleton `Basic` wrappers are external-owned once wrapped.
- `RSHUTDOWN` reconciles any externalized SymEngine singletons back to inline mode with `detach_external()` plus `inc_ref()` replay while the Zend wrapper and its refcount are still available.
- Wrapper destruction after that point no longer deletes those detached singletons, but still deletes ordinary external-owned objects when their final PHP/C++ reference disappears.
- `MSHUTDOWN` marks the cooperative hooks inert so any later SymEngine static destruction cannot touch Zend objects after PHP teardown.

FPM has been smoke-tested with one persistent worker across repeated requests.
Apache module mode remains unverified. The current code intentionally keeps the
inert-hook window as narrow as possible.

### PHP API Surface (Minimal)

| Function / Method | Description |
|-------------------|-------------|
| `symengine_zero()` .. `symengine_nan()` | Singleton constants |
| `symengine_integer(int $val)` | Create integer |
| `symengine_symbol(string $name)` | Create symbol |
| `symengine_add(a, b)`, `symengine_sub(a, b)`, `symengine_div(a, b)`, `symengine_mul(a, b)`, `symengine_neg(value)`, `symengine_pow(base, exp)` | Arithmetic |
| `symengine_str(obj)`, `symengine_eq(a, b)` | String/equality |
| `Basic::isExternalOwned()` | True if PHP owns the C++ object |
| `Basic::phpRefCount()` | PHP object refcount |
| `Basic::sameObject(other)` | True if same C++ object |
| `Basic::cppUseCount()`, `Basic::externalOwnerAddress()`, `Basic::isSingletonSeeded()` | Debug ownership helpers when `SYMENGINE_PHP_DEBUG_HELPERS` is enabled |

Classes: `SymEngine\Basic`, `SymEngine\Integer`, `SymEngine\Symbol`

## PHP vs Perl Extension Comparison

### Shared Ownership Story

Both extensions use SymEngine's `cooperative_intrusive` backend:

- **C++ objects** store either an inline refcount (LSB=1) or a pointer to an external owner (LSB=0)
- **Foreign runtime** registers `inc_hook`/`dec_hook` that manipulate its own refcount (PHP: `zend_object` GC; Perl: `SvREFCNT`)
- **Externalization** transfers ownership: the foreign wrapper becomes the refcount anchor
- **Identity reuse** via `self_external()`: wrapping the same C++ singleton returns the same foreign wrapper
- **Singleton reconciliation** at shutdown: `detach_external()` + `inc_ref()` replay

### Key Lifecycle Similarity

| Aspect | PHP Extension | Perl Extension |
|--------|---------------|----------------|
| Runtime refcount anchor | `zend_object` (GC_ADDREF/GC_DELREF) | SV (`SvREFCNT_inc`/`SvREFCNT_dec`) |
| Cooperative hooks | `cooperative_intrusive_init(php_inc, php_dec)` | `cooperative_intrusive_init(perl_inc, perl_dec)` |
| Singleton externalization | `self_external()` on first wrap | `self_external()` on first wrap |
| Identity reuse | `sameObject()` compares C++ pointer | `same_object()` compares C++ pointer |
| Shutdown reconciliation | `RSHUTDOWN`: `detach_external()` + `inc_ref()` replay | `call_atexit` during `perl_destruct`: `detach_external()` + `inc_ref()` replay |
| Hook inert transition | `MSHUTDOWN` marks hooks inert | Process exit (no module shutdown) |

### Current Difference in Shutdown Handling

- **PHP (CLI)**: Split shutdown — `RSHUTDOWN` reconciles singletons while Zend objects are alive; `MSHUTDOWN` marks hooks inert for static C++ destruction.
- **Perl**: Single process-exit phase — child interpreter under `PERL_DESTRUCT_LEVEL=2` exercises global destruction with live singletons.

### Confidence Assessment

- **Perl**: Higher teardown confidence. Test suite runs child interpreter with `PERL_DESTRUCT_LEVEL=2` holding live singletons and expressions, asserting clean exit.
- **PHP**: Core ownership tests pass. Subprocess teardown tests pass under CLI.
  The local FPM smoke harness passed with a single persistent worker. Apache
  module mode remains unverified.

### Upstreaming Implications

Both extensions validate the same `cooperative_intrusive` backend. Perl has more comprehensive teardown testing. PHP adds validation of the request/module shutdown split relevant to PHP's SAPI architecture. Together they demonstrate the backend works across two very different runtimes (request-scoped interpreter vs process-scoped interpreter).

## License

MIT (same as SymEngine)
