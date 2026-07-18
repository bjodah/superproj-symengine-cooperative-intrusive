# symengine.swift

Experimental Swift bindings for SymEngine using the
`cooperative_intrusive` reference-counting backend.

The initial API deliberately stays small while validating the ownership model:
symbols, integers, selected constants, arithmetic, stringification, equality,
dynamic wrapper types, and canonical Swift object identity.

## Status

This is a validation wrapper, not yet a production-ready package. It currently
targets Swift 5.9 or newer and has been exercised with Swift 6 on Linux. macOS,
framework packaging, and dynamic library unloading still need dedicated tests.

## Why the shim is local

The Swift package contains a small C ABI shim in
`Sources/CSymEngineSwift`. It is intentionally not part of SymEngine's generic
`symengine/cwrapper.{h,cpp}`.

The existing C wrapper uses an explicit ownership model: a caller allocates a
`basic` value containing an `RCP<const Basic>` and later calls
`basic_free_stack()` or `basic_free_heap()`. That is a good general C API, but
it does not model a foreign runtime object whose own reference count becomes
the intrusive counter.

The local shim has binding-specific responsibilities:

- registering Swift ARC retain and release callbacks;
- adapting ordinary C callbacks to SymEngine's required C++ `noexcept` hooks;
- storing a Swift object identity in `self_external()`;
- returning temporary owned native references for Swift to adopt;
- deleting an externalized C++ object from Swift `deinit`; and
- serializing first-wrapper creation so concurrent canonical results cannot
  externalize the same object twice.

These are runtime-binding policies rather than general symbolic C operations.
Keeping them here also keeps the intended patch to the core SymEngine repository
unchanged.

## Building

Build a shared SymEngine library with the cooperative backend first:

```bash
cd /work
cmake -S symengine -B build-swift/symengine -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_SHARED_LIBS=ON \
  -DSYMENGINE_RCP_BACKEND=cooperative_intrusive \
  -DWITH_SYMENGINE_THREAD_SAFE=ON \
  -DBUILD_TESTS=OFF
cmake --build build-swift/symengine --target symengine
```

The package defaults match those paths:

```bash
cd /work/symengine.swift
swift test
swift test -c release
```

Custom checkouts and build directories can be supplied when SwiftPM evaluates
`Package.swift`:

```bash
SYMENGINE_SOURCE_DIR=/path/to/symengine \
SYMENGINE_BUILD_DIR=/path/to/symengine-build \
SYMENGINE_LIBRARY_DIR=/path/to/symengine-build/symengine \
swift test
```

`SYMENGINE_BUILD_DIR` is the CMake build root containing the generated
`symengine/symengine_config.h`. `SYMENGINE_LIBRARY_DIR` contains
`libsymengine`; by default it is `$SYMENGINE_BUILD_DIR/symengine`.

## Example

```swift
import SymEngine

let x = try SymEngine.symbol("x")
let two = try SymEngine.integer(2)
let expression = try SymEngine.add(
    try SymEngine.power(x, two),
    try SymEngine.multiply(two, x)
)

print(try expression.string())
```

`Basic` conforms to `CustomStringConvertible` and `Equatable`. The throwing
`string()` and `isEqual(to:)` methods should be preferred when error details
matter; protocol requirements cannot propagate errors.

## Ownership implementation

### Tagged counter states

Before a value crosses into Swift, its cooperative counter is an inline C++
count: the count is shifted left one bit and tagged with a low bit of one.
After externalization, the counter stores the aligned opaque pointer returned
by `Unmanaged.passUnretained(swiftObject).toOpaque()`. Swift heap object
pointers are stable for the object's lifetime and satisfy the low-bit alignment
requirement, which the shim checks before externalization.

The registered hooks implement the foreign counter operations with Swift's
public `Unmanaged` API:

- C++ `inc_ref()` calls `Unmanaged.retain()` on the Swift wrapper.
- C++ `dec_ref()` calls `Unmanaged.release()` on the Swift wrapper.

The Swift callbacks themselves do not throw. A C function-pointer type cannot
express C++ `noexcept`, so the C++ shim registers two small `noexcept`
trampolines with `cooperative_intrusive_init()`.

### Owned result contract

Every result-producing shim function returns a raw `Basic` pointer carrying
one temporary C++ reference. Swift adopts it while holding the wrapper-creation
mutex:

1. If `self_external()` is already set, Swift recovers that exact `Basic`
   wrapper with `Unmanaged.fromOpaque()`. It then consumes the temporary native
   reference.
2. Otherwise Swift creates the appropriate `Basic`, `Integer`, or `Symbol`
   wrapper and calls `set_self_external()` with its opaque object pointer.
3. `set_self_external()` replays all current C++ references as ARC retains.
   Swift then consumes the temporary result reference, leaving the ordinary
   returned Swift strong reference.

`withExtendedLifetime` protects the wrapper across the balancing native
release, including optimized ARC builds.

This identity path means canonical operations reuse Swift identity as well as
C++ identity. For example, `add(x, 0)` returns the same Swift object (`=== x`)
rather than creating a second wrapper around the same `Basic`.

### Final release

A Swift wrapper stores only a borrowed raw native pointer; it does not contain
a second `RCP`. When its ARC strong count reaches zero, `deinit` verifies that
the native object's external owner still points to that wrapper and deletes the
C++ object directly.

Reaching `deinit` during normal execution implies that no C++ `RCP` remains:
each such `RCP` would have retained the Swift wrapper through the cooperative
hook. Deleting from `deinit` is therefore the equivalent of the final-wrapper
deletion performed by the PHP and Perl validation bindings.

### Expression-held references

If a C++ expression stores an `RCP` to one of its operands, the `RCP` retains
that operand's Swift wrapper. The operand remains alive even if the user's last
direct Swift reference leaves scope. Destroying the expression releases the
native `RCP`, which releases the operand wrapper. The test suite checks both
sides of this transition with a Swift `weak` reference.

## Lifecycle considerations

### Normal executables

Swift ARC remains available while ordinary C++ static destructors execute.
Externalized SymEngine constants such as `pi` can therefore remain pinned by
SymEngine's static `RCP`s after user references disappear. At process exit, the
static `RCP` releases the Swift wrapper; its `deinit` deletes the native object.
The current debug and optimized test executables exit cleanly with an
externalized singleton.

This differs from embedded PHP or Perl, where the interpreter may cease to be
usable before C++ static destruction and singleton ownership must first be
reconciled with `detach_external()`.

### Dynamic unloading

Unloading `libsymengine` or the Swift binding while wrappers or externalized
singletons remain alive is not supported. Swift has no supported API for
reading an object's total ARC retain count, so the PHP/Perl shutdown technique
of detaching an external owner and replaying its runtime count cannot be
implemented directly.

Applications must keep both libraries loaded until process termination. A
future unloadable framework design will need a different explicit lifecycle
contract, likely requiring all user wrappers to be released before shutdown
and separately accounting for singleton/native pins.

### Global hook registration

SymEngine currently stores one process-global pair of cooperative hooks. A
single `libsymengine` instance can therefore cooperate with only one foreign
runtime at a time. The Swift shim initializes its callbacks once and rejects a
different second initialization. It must not share the same library instance
with a Python, PHP, or Perl cooperative binding in one process.

Initialization occurs lazily before the first public operation and before any
object can be externalized.

### Concurrency

ARC retain/release operations are safe across threads, and the cooperative
counter is atomic. First-wrapper lookup and externalization are serialized by a
shim mutex because `self_external()` followed by `set_self_external()` is a
compound operation.

That does not make every SymEngine operation automatically thread-safe. Build
with `WITH_SYMENGINE_THREAD_SAFE=ON` before sharing expressions between threads.
The Swift classes are not currently declared `Sendable`; a reviewed Swift 6
concurrency contract is deferred.

### Errors and exceptions

No C++ exception crosses the C ABI. Result-producing functions catch
`SymEngineException`, standard exceptions, allocation failures, and unknown
exceptions. The message is stored in thread-local storage and immediately
converted to `SymEngineError` by Swift.

ARC hooks and finalization functions are non-throwing. A failure in these paths
cannot be safely recovered as a normal Swift error and would indicate a binding
invariant violation.

## Initial test coverage

The SwiftPM tests cover:

- integer and symbol dynamic wrapper types;
- arithmetic and stable string output;
- mathematical equality;
- external ownership after wrapping;
- canonical Swift identity reuse;
- expression-held `RCP` retention and release of an operand wrapper;
- singleton identity reuse; and
- process teardown with an externalized singleton.

The next lifecycle work should add macOS debug/release CI, sanitizer builds,
concurrent adoption stress, global Swift variable teardown, and an explicit
dynamic-unload rejection test where the platform supports unloading.
