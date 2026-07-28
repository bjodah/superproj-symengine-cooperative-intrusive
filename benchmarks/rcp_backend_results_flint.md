# RCP backend benchmarks with FLINT

Run on 2026-07-28 against SymEngine commit
`15fa4cb3853089c34d1a8107b1a8614c5f9a009f`, including the new
`add_steal` and `rcp_throughput` benchmark sources in the working tree.

## Configuration and method

- Release build (`-O3 -funroll-loops`) with GCC 14.2.0.
- `INTEGER_CLASS=flint` for every build, using FLINT 3.4.0-dev from
  `/opt-3/flint-b00e994-release`.
- AMD Ryzen 9 7950X (16 cores/32 threads), Linux 7.0.14-5-pve.
- Each single-threaded benchmark was pinned to logical CPU 8.
- One warm-up run was followed by seven measured runs. Backend order was
  rotated between samples; all tables report the median. Lower is better.
- `add_steal` used its defaults of 200,000 iterations and 16 factors.
  `rcp_throughput` used its compiled-in default operation counts.
- The `symbench` and `lwbench` columns are sums of the timed sections reported
  by those executables, not process wall time.

## Results

| RCP backend | `expand1` (ms) | `add1` (ms) | `add_steal` (ns/iteration) | `symbench` timed sum (ms) | `lwbench` timed sum (ms) |
|---|---:|---:|---:|---:|---:|
| SymEngine intrusive | **37** | **90** | **483.5** | **435.0** | **4.115** |
| Teuchos | 51 | 110 | 725.1 | 593.4 | 4.193 |
| Cooperative intrusive | 39 | 112 | 551.3 | 481.8 | 4.118 |
| Cooperative intrusive, thread-safe | 39 | 110 | 574.6 | 478.4 | 4.116 |

The targeted RCP throughput results, normalized to nanoseconds per operation:

| Operation | SymEngine intrusive | Teuchos | Cooperative intrusive | Cooperative intrusive, thread-safe |
|---|---:|---:|---:|---:|
| Symbol creation | **20.34** | 35.34 | 22.14 | 22.34 |
| Integer creation | **7.36** | 21.30 | 9.14 | 9.16 |
| Add chain | **61.0** | 119.4 | 75.6 | 75.0 |
| Multiply expression build | **162** | 340 | 187 | 187 |
| Add expression build | **384** | 666 | 443 | 444 |
| Create and drop expression batches | **2,260** | 3,810 | 2,897 | 2,862 |

All configurations produced the same `add_steal` checksum
(`5125865154610734112`) and the same `expand1`/`add1` term counts.

## Conclusions

- Cooperative intrusive is substantially closer to the original SymEngine
  RCP than Teuchos on reference-count-heavy work. It is 14% slower than the
  original backend in `add_steal`, versus 50% for Teuchos.
- Across the detailed throughput cases, non-thread-safe cooperative intrusive
  is 9–28% slower than the original backend. Teuchos is 69–189% slower.
- On broader symbolic work, cooperative intrusive is 5% slower in `expand1`,
  24% slower in `add1`, and 11% slower in the aggregate `symbench` timing.
  `lwbench`, which is dominated more by arithmetic than pointer traffic, is
  effectively unchanged.
- Thread-safe cooperative intrusive adds about 4% over non-thread-safe
  cooperative intrusive in `add_steal`; elsewhere their results are close
  enough that this run does not show a consistent additional penalty.
- These are single-threaded latency measurements. The thread-safe build was
  tested for uncontended reference-count overhead, not multi-threaded scaling
  or contention.
