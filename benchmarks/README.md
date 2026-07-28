# nbsymengine Benchmarks

Benchmark suite comparing nbsymengine Lambdify performance against SymPy and the legacy `symengine` package.

## Architecture

Top-level benchmarks are direct-only and must not import `nbsymengine_compat`.
- `nbsymengine/` and the direct benchmark suite have no compat imports.
- `ci-02` owns direct tests and benchmarks and must not import compat.
- `nbsymengine_compat/` owns the legacy compat layer. Compat-owned benchmark code lives under `nbsymengine_compat/benchmarks/`.
- `ci-03` owns the compat benchmark layer and tests.

## Layout

```
benchmarks/
├── README.md
├── data/
│   └── 6_links_rhs.txt
├── python_boundary_add.py
├── nbsymengine_benchmarks/
│   ├── __init__.py
│   ├── __main__.py
│   ├── adapters.py
│   ├── cases.py
│   ├── cli.py
│   ├── reporting.py
│   └── timing.py
└── tests/
    ├── test_lambdify_cases.py
    └── test_reporting.py
```

## Usage

### Run all benchmarks (default config)

```sh
PYTHONPATH=build-cooperative_intrusive/python-bindings:python-bindings/benchmarks \
  python -m nbsymengine_benchmarks lambdify
```

### Quick smoke test (low iterations)

```sh
PYTHONPATH=build-cooperative_intrusive/python-bindings:python-bindings/benchmarks \
  python -m nbsymengine_benchmarks lambdify --quick
```

### Select specific backends

```sh
PYTHONPATH=build-cooperative_intrusive/python-bindings:python-bindings/benchmarks \
  python -m nbsymengine_benchmarks lambdify --backends sympy,nbsymengine
```

### JSON output

```sh
PYTHONPATH=build-cooperative_intrusive/python-bindings:python-bindings/benchmarks \
  python -m nbsymengine_benchmarks lambdify --json /tmp/lambdify.json
```

### Run tests

```sh
python -m pytest python-bindings/benchmarks/tests
```

## Backends

| Adapter | Name | Description |
|---|---|---|
| SymPy | `sympy` | Baseline using `sympy.lambdify` |
| nbsymengine | `nbsymengine` | Direct nbsymengine.Lambdify API |
| legacy-symengine | `legacy-symengine` | Installed old `symengine` package (optional) |

## Adapter Calling Conventions

Each adapter's `build_lambdify` returns a callable `call(inp)` where `inp` is a numpy array. The internal convention to the underlying library differs:

| Adapter | Non-heterogeneous | Heterogeneous |
|---|---|---|
| SymPy | `lmb(*inp)` | `lmb(*inp)` |
| NBSymEngine | `lmb(inp)` | `lmb(inp)` |
| LegacySymEngine | `lmb(inp)` | `lmb(inp)` |

## Benchmark Cases

- **ion_speciation_lambdify**: 14 x symbols, 14 p symbols, 28 inputs, 15 expressions with exp() terms.
- **heterogeneous_output_lambdify**: Parses a 6-link robot kinematic expression, builds a 1x14 vector and its Jacobian, producing heterogeneous (vector, matrix) output.

## Timing Parameters

| Parameter | Default | Meaning |
|-----------|---------|---------|
| warmup | 2 | Iterations discarded before measurement begins |
| iterations | 100 | Number of calls per repeat batch |
| repeats | 5 | Number of measurement batches |

Results report best, median, mean, and standard deviation per-call time. Speedups are computed relative to the `sympy` backend median.

## Cooperative Add ownership benchmark

`python_boundary_add.py` measures Add-heavy operations through the nanobind
boundary. Use it with separately built baseline and candidate extension trees
when validating a cooperative-intrusive ownership change:

```sh
PYTHONPATH=build-python taskset -c 0 \
  python benchmarks/python_boundary_add.py boundary-add --factors 16
PYTHONPATH=build-python taskset -c 0 \
  python benchmarks/python_boundary_add.py expand --exponent 15
```

The corresponding native eligible-path benchmark is
`symengine/benchmarks/add_steal.cpp`; `bench_rcp_backends.sh` runs it with the
other RCP backend benchmarks. See
[`docs/reports/24-ADD-STEAL-BENCHMARKS.md`](../docs/reports/24-ADD-STEAL-BENCHMARKS.md)
for the initial paired result.

`python_boundary_add.py` defaults to `nbsymengine`; pass `--binding legacy` to
exercise an installed `symengine.py` binding as a contextual control. Its
absolute timings are not comparable across bindings.

## Data Files

`data/6_links_rhs.txt` contains a 6-link robot kinematic expression used by the `heterogeneous_output_lambdify` benchmark case.
