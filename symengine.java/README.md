# symengine.java

Small JNI bindings for SymEngine. The public arithmetic surface is generated
from `../binding-spec/api.yaml`; JNI handle lifetime and Java exception
translation remain deliberately hand-written in the runtime files.

This wrapper uses the ordinary `SYMENGINE_RCP_BACKEND=symengine` backend, not
the cooperative intrusive backend used by the Python, Perl, PHP, and Swift
wrappers. A Java `Basic` owns a native heap cell containing an
`RCP<const Basic>`. `Basic` registers that cell with `Cleaner` and also
implements `AutoCloseable`; call `close()` when deterministic release matters.
`close()` is idempotent.

The Java build must enable `WITH_SYMENGINE_THREAD_SAFE=ON`: Cleaner actions may
run concurrently with application threads, so ordinary RCP updates must be
atomic. Do not load a cooperative and ordinary SymEngine build into one JVM
process.

`equals` and `hashCode` are structural (`SymEngine::eq` and `Basic::hash`).
Java object identity is not native identity: two Java objects can wrap the
same C++ expression. `sameInstance` exists only as a test/debug helper.

Build through the superproject:

```bash
cmake -S . -B build-java -G Ninja \
  -DBUILD_JAVA_JNI=ON -DSYMENGINE_RCP_BACKEND=symengine \
  -DWITH_SYMENGINE_THREAD_SAFE=ON
cmake --build build-java
ctest --test-dir build-java --output-on-failure -R java_symengine
```
