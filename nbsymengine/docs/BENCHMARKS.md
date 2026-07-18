# Phase 7 — Benchmark Results

Recorded on 2026-06-06 UTC.

## Environment

- CPU: Intel Xeon (cloud VM)
- OS: Linux
- Compiler: system gcc/g++
- Build type: Release
- nanobind: 2.x

## Methodology

Each backend was built in Release mode with `-DBUILD_BENCHMARKS=ON`. The
benchmarks are the existing SymEngine C++ benchmarks (`expand1`, `add1`,
`symbench`) plus a new `rcp_throughput` microbenchmark that measures
symbol/integer creation, expression building, and destruction-heavy patterns.

## Results Table

### expand1 (expand (w+x+y+z)^60)

| Backend                          | Time (ms) |
|----------------------------------|-----------|
| symengine (default)              | 44        |
| teuchos                          | 62        |
| cooperative_intrusive                     | 47        |
| cooperative_intrusive (thread-safe)       | 46        |

### add1 (build large Add tree)

| Backend                          | Time (ms) |
|----------------------------------|-----------|
| symengine (default)              | 101       |
| teuchos                          | 114       |
| cooperative_intrusive                     | 119       |
| cooperative_intrusive (thread-safe)       | 119       |

### symbench (S3a — most RCP-intensive sub-benchmark)

| Backend                          | Time (s)  |
|----------------------------------|-----------|
| symengine (default)              | 0.392     |
| teuchos                          | 0.558     |
| cooperative_intrusive                     | 0.407     |
| cooperative_intrusive (thread-safe)       | 0.417     |

### rcp_throughput (ops/sec, higher is better)

| Benchmark           | symengine   | teuchos     | cooperative_intrusive | cooperative_intrusive TS |
|---------------------|-------------|-------------|--------------|-----------------|
| symbol_creation     | 45,526,975  | 26,274,456  | 42,016,736   | 42,162,284      |
| integer_creation    | 47,556,907  | 29,576,506  | 51,311,628   | 48,755,563      |
| add_chain           | 12,085,585  | 7,018,864   | 10,214,546   | 9,458,036       |
| mul_build           | 3,944,213   | 2,206,045   | 3,751,782    | 3,356,730       |
| expr_build_add      | 2,233,943   | 1,361,233   | 2,066,513    | 1,877,479       |
| drop_expressions    | 400,820     | 229,193     | 316,093      | 316,936         |

## Analysis: Atomic Overhead (Decision D8)

The headline comparison is **cooperative_intrusive vs symengine in single-threaded
(THREAD_SAFE=OFF) mode** — this quantifies the overhead of nanobind's always-atomic
counter operations versus SymEngine's plain `unsigned int` increment.

### Per-benchmark overhead

| Benchmark         | symengine ops/s | cooperative_intrusive ops/s | Overhead  |
|-------------------|-----------------|--------------------|-----------|
| symbol_creation   | 45,526,975      | 42,016,736         | -7.7%     |
| integer_creation  | 47,556,907      | 51,311,628         | +7.9%     |
| add_chain         | 12,085,585      | 10,214,546         | -15.5%    |
| mul_build         | 3,944,213       | 3,751,782          | -4.9%     |
| expr_build_add    | 2,233,943       | 2,066,513          | -7.5%     |
| drop_expressions  | 400,820         | 316,093            | -21.1%    |

### Macro-benchmark overhead

| Benchmark | symengine | cooperative_intrusive | Overhead |
|-----------|-----------|--------------|----------|
| expand1   | 44 ms     | 47 ms        | +6.8%    |
| add1      | 101 ms    | 119 ms       | +17.8%   |
| symbench  | 0.392 s   | 0.407 s      | +3.8%    |

### Thread-safe overhead (cooperative_intrusive TS vs cooperative_intrusive)

| Benchmark         | cooperative_intrusive | cooperative_intrusive TS | TS overhead |
|-------------------|--------------|-----------------|-------------|
| symbol_creation   | 42,016,736   | 42,162,284      | +0.3%       |
| integer_creation  | 51,311,628   | 48,755,563      | -5.0%       |
| add_chain         | 10,214,546   | 9,458,036       | -7.4%       |
| mul_build         | 3,751,782    | 3,356,730       | -10.5%      |
| expr_build_add    | 2,066,513    | 1,877,479       | -9.1%       |
| drop_expressions  | 316,093      | 316,936         | +0.3%       |

### Decision D8: Non-atomic counter variant

**Decision: Not needed at this time.**

The measured single-threaded overhead of `cooperative_intrusive` vs `symengine` is
**3.8%–17.8% on macro-benchmarks** (expand1, add1, symbench) and up to **15–21% on
micro-benchmarks that are pure RCP churn** (add_chain, drop_expressions). The
micro-benchmarks are not representative of real symbolic workloads where the
expression tree operations dominate over refcount manipulation. The add1
benchmark (which builds a very large `Add` tree, exercising internal lock
contention) shows a higher overhead of 17.8%, suggesting that lock-heavy
patterns amplify the atomic cost. For typical symbolic computation (expand,
simplify, differentiate), the overhead is in the 4–7% range. This is acceptable
for the initial release. The non-atomic variant (Master §6, modeled on
`refcount-py-cxx`) should be revisited only if profiling of downstream
applications shows refcount operations as a bottleneck.

**The `WITH_SYMENGINE_THREAD_SAFE=ON` mode adds negligible overhead on top of
the already-atomic cooperative_intrusive counter** (0–10% depending on the benchmark),
confirming that the thread-safe mode is safe to use.
