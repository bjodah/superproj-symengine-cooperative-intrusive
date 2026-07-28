# symengine.java

Small JNI bindings for SymEngine. The public arithmetic surface is generated
from `../binding-spec/api.yaml`; JNI handle lifetime and Java exception
translation remain deliberately hand-written in the runtime files.

This wrapper never hooks into the cooperative incref/decref facilities (the
JVM has no reference counts to cooperate with) and builds against either RCP
backend: the cooperative-intrusive backend used by the Python, Perl, PHP, and
Swift wrappers, or the ordinary `SYMENGINE_RCP_BACKEND=symengine` backend. A
Java `Basic` owns a native heap cell containing an `RCP<const Basic>`.
`Basic` registers that cell with `Cleaner` and also implements
`AutoCloseable`; call `close()` when deterministic release matters.
`close()` is idempotent.

Cleaner actions may run concurrently with application threads, so RCP updates
must be atomic. The cooperative-intrusive counter is unconditionally atomic
(CAS-based), and since `cooperative_intrusive_init()` is never called, every
object stays in C++-owned integer-count mode. The ordinary backend instead
requires `WITH_SYMENGINE_THREAD_SAFE=ON` to make its plain refcount atomic;
the build errors out otherwise. Do not load a cooperative and ordinary
SymEngine build into one JVM process.

`equals` and `hashCode` are structural (`SymEngine::eq` and `Basic::hash`).
Java object identity is not native identity: two Java objects can wrap the
same C++ expression. `sameInstance` exists only as a test/debug helper.

Build through the superproject:

```bash
cmake -S . -B build-java -G Ninja \
  -DBUILD_JAVA_JNI=ON -DSYMENGINE_RCP_BACKEND=cooperative_intrusive
cmake --build build-java
ctest --test-dir build-java --output-on-failure -R java_symengine
```

CI reuses the nbsymengine lane's cooperative superproject build directory and
just switches `BUILD_JAVA_JNI=ON` on there (see `.ci/ci-08-build-and-test-java.sh`),
so no second SymEngine core is compiled for Java. For the ordinary backend,
configure with `-DSYMENGINE_RCP_BACKEND=symengine -DWITH_SYMENGINE_THREAD_SAFE=ON`
instead.
