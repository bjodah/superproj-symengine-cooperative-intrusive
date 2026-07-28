# Python wrapper benchmark results

This report compares the current Python wrappers and Lambdify backends using
local Release builds of SymEngine. It also tests whether the unmodified legacy
`symengine.py` Cython wrapper can use the cooperative-intrusive RCP backend.

## Result summary

Yes: the clean `symengine.py` checkout built a wheel against
`SYMENGINE_RCP_BACKEND=cooperative_intrusive` without any source changes. The
wheel imported successfully, its LLVM-backed `Lambdify` worked, and its
performance was within the run-to-run range of the same wrapper built against
the native SymEngine RCP backend.

The cooperative build passed 363 legacy-wrapper tests with 3 skipped and 1
failure. The same failing test (`test_pynumber`) also fails with the native-RCP
build because the installed development SymPy returns a python-flint `nmod`
that `symengine.py` cannot convert; it is not specific to cooperative RCP.

## Builds and method

| Component | Revision/configuration |
|---|---|
| Super-project | `fc9945355ca3dcd7878c49e43629954f2f4983dc` |
| SymEngine | `3d7ba4c74a8b42809ab73c9fea4893f4d4850ab2` |
| Legacy `symengine.py` | clean `88ad3236502ddafc771e823c5c4a2645a69c344a` |
| Cooperative core | Release, shared, cooperative-intrusive RCP, GMP, LLVM 21.1.8 |
| Native control core | Release, shared, native SymEngine RCP, GMP, LLVM 21.1.8 |
| Toolchain | GCC 14.2.0, CPython 3.13.5, NumPy 2.4.6, SymPy 1.15.0.dev, nanobind 2.13.0 |
| Host | AMD Ryzen 9 7950X, Linux 7.0.14-5-pve |

The standard benchmark configuration was used: 2 warm-ups, 100 calls per
batch, and 5 timed batches. Each complete benchmark was run in five fresh
Python processes pinned to logical CPU 8. Values below are the median of the
five process medians, with the process-median range in parentheses. Lower
latency is better.

The native and cooperative shared-library ABIs were kept in separate Python
processes. The nbsymengine extension and cooperative `symengine.py` wheel used
the same cooperative `libsymengine` build.

## Lambdify results

### Ion speciation

This case evaluates 15 scalar expressions from 28 scalar inputs.

| Wrapper/backend | Core RCP | Median latency, µs (range) | Speedup vs paired SymPy |
|---|---|---:|---:|
| SymPy | n/a | 6.716 (6.693–7.385) | 1.00× |
| nbsymengine, default SymPy evaluator | cooperative | 12.641 (12.604–13.888) | 0.53× |
| nbsymengine, `lambda_double` | cooperative | 4.050 (3.993–4.377) | 1.66× |
| nbsymengine, LLVM | cooperative | 2.162 (2.121–2.317) | 3.11× |
| nbsymengine compatibility shim | cooperative | 4.026 (3.981–4.288) | 1.67× |
| legacy `symengine.py`, default LLVM | cooperative | 1.462 (1.424–1.582) | 4.60× |
| legacy `symengine.py`, default LLVM | native | 1.439 (1.428–1.448) | 4.68× |

The native-control speedup uses its separately measured paired SymPy median of
6.734 µs.

### Heterogeneous vector and Jacobian output

| Wrapper/backend | Core RCP | Median latency, µs (range) | Speedup vs paired SymPy |
|---|---|---:|---:|
| SymPy | n/a | 778.588 (768.010–782.193) | 1.00× |
| nbsymengine, default SymPy evaluator | cooperative | 275.160 (274.023–280.292) | 2.83× |
| nbsymengine, `lambda_double` | cooperative | 158.162 (157.715–159.435) | 4.92× |
| nbsymengine, LLVM | cooperative | 102.905 (101.850–103.860) | 7.57× |
| nbsymengine compatibility shim | cooperative | failed: stale `_func` fallback | n/a |
| legacy `symengine.py`, default LLVM | cooperative | 1.924 (1.910–1.935) | 404.67× |
| legacy `symengine.py`, default LLVM | native | 1.913 (1.893–1.926) | 405.91× |

The native-control speedup uses its separately measured paired SymPy median of
776.426 µs.

The very large legacy-wrapper advantage in the heterogeneous case is primarily
a wrapper/output-conversion result, not a 400× evaluator advantage.
`symengine.py` fills NumPy outputs in its compiled Cython path, while the
current nbsymengine benchmark adapter converts matrix elements through Python,
including per-element string-to-float conversion.

## Conclusions

- Unmodified `symengine.py` is source- and runtime-compatible with the
  cooperative-intrusive core for this Release configuration.
- Switching that wrapper from native to cooperative RCP changed median latency
  by only 1.5% for ion speciation and 0.6% for heterogeneous output. The sample
  ranges overlap, so there is no measurable wrapper-level regression here.
- For direct nbsymengine, LLVM was 1.87× faster than `lambda_double` in ion
  speciation and 1.54× faster in the heterogeneous case. The earlier blanket
  “about 4×” statement does not hold for these current workloads.
- The default nbsymengine SymPy evaluator is slower than direct SymPy for the
  small ion-speciation call, but all native evaluator paths beat SymPy.
- The compatibility shim's heterogeneous benchmark failed in this run because
  its fallback expected a removed private `Lambdify._func` attribute. This was
  an adapter maintenance issue, not a cooperative-RCP failure; the fallback has
  since been removed and the shim evaluates the heterogeneous case through the
  public `lmb(inp)` interface. The table above is left as the record of this
  run and has not been re-measured.

## Post-optimization update (2026-07-28)

After the native-Lambdify fast path landed (flat float64 output buffers
filled in C++, shaped NumPy views returned, no per-call `Basic`/`DenseMatrix`
construction, batched 2-D input), a quick re-measurement on the same host
(single process pinned to logical CPU 8, 200 calls x 5 repeats, cooperative
core) gives:

| Case | nbsymengine `lambda_double` | nbsymengine LLVM | compat shim (default `lambda`) |
|---|---:|---:|---:|
| Ion speciation | 2.68 µs | 0.78 µs | 2.30 µs |
| Heterogeneous vector+Jacobian | 54.6 µs | 2.09 µs | 53.3 µs |

Referenced against the legacy `symengine.py` medians recorded above
(1.46 µs ion speciation, 1.92 µs heterogeneous, both LLVM), the direct
nbsymengine LLVM path is now faster than the legacy wrapper on both cases,
and the compatibility shim's heterogeneous case succeeds through the public
interface. Batched `(m, n_args)` input evaluates at roughly 6 ns per row for
the ion-speciation expressions. These are informal single-process numbers;
the multi-process methodology of the tables above was not repeated.

## Reproduction outline

Configure the cooperative super-project build with:

```sh
cmake -S . -B build-cooperative -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_SHARED_LIBS=ON \
  -DBUILD_PYTHON_NANOBIND=ON \
  -DSYMENGINE_RCP_BACKEND=cooperative_intrusive \
  -DINTEGER_CLASS=gmp -DWITH_LLVM=ON -DWITH_BFD=OFF
```

Build the untouched legacy wrapper against that build:

```sh
python -m pip wheel ./symengine.py --no-build-isolation --no-deps \
  -Ccmake.build-type=Release \
  -Ccmake.define.SymEngine_DIR=/path/to/build-cooperative/symengine
```

Then run the benchmark suite as documented in
[`benchmarks/LAMBDIFY_RESULTS.md`](benchmarks/LAMBDIFY_RESULTS.md).
