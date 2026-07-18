# Lambdify Benchmark Results

This document records benchmark results for the nbsymengine Lambdify API.

## How to reproduce

Run the full benchmark suite:

```sh
PYTHONPATH=build-dir/python-bindings:/path/to/benchmarks \
  python -m nbsymengine_benchmarks lambdify
```

Run with JSON output:

```sh
PYTHONPATH=build-dir/python-bindings:/path/to/benchmarks \
  python -m nbsymengine_benchmarks lambdify --json /tmp/lambdify.json
```

Quick smoke test:

```sh
PYTHONPATH=build-dir/python-bindings:/path/to/benchmarks \
  python -m nbsymengine_benchmarks lambdify --quick
```

Run specific backends:

```sh
PYTHONPATH=build-dir/python-bindings:/path/to/benchmarks \
  python -m nbsymengine_benchmarks lambdify --backends sympy,nbsymengine-llvm
```

## Build requirements

The SymEngine C++ library must be built with LLVM support for the `nbsymengine-llvm` backend:

```
cmake -S . -B build -G Ninja \
  -DBUILD_PYTHON_NANOBIND=ON \
  -DSYMENGINE_RCP_BACKEND=cooperative_intrusive \
  -DINTEGER_CLASS=boostmp \
  -DWITH_LLVM=ON \
  -Dnanobind_DIR=$(python -m nanobind --cmake_dir)
```

## Latest results

See [BENCHMARKS_RESULTS.md](../../BENCHMARKS_RESULTS.md) for the latest full benchmark
results including all backends (SymPy, nbsymengine, lambda_double, LLVM JIT, legacy).

## Interpretation notes

- The `lambda_double` backend uses C++ interpreter (std::function closures) — no JIT.
- The `llvm` backend JIT-compiles expression trees to native x86_64 machine code via LLVM.
- LLVM provides ~4x speedup over `lambda_double` for scalar expression evaluation.
- For heterogeneous output (vector + matrix), Python-level output construction dominates.
- The `nbsymengine-legacy` adapter adds shim overhead on top of the direct API.
- The `legacy-symengine` adapter is optional and only available when the old `symengine.py` package is installed.
- Results vary by machine. Always report the environment when sharing numbers.
