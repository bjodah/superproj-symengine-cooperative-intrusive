"""Entry point for python -m nbsymengine_benchmarks."""
from __future__ import annotations

import sys
from dataclasses import replace

from .cli import parse_args
from .cases import IonSpeciationLambdifyCase, HeterogeneousOutputLambdifyCase
from .adapters import get_available_adapters, get_adapter
from .timing import run_benchmark, BenchmarkConfig, QUICK_CONFIG, DEFAULT_CONFIG
from .reporting import BenchmarkRow, compute_speedups, format_text_table, format_json


def run_lambdify(args) -> int:
    """Run the Lambdify benchmark suite."""
    if args.quick:
        config = QUICK_CONFIG
    else:
        config = DEFAULT_CONFIG

    overrides = {}
    if args.warmup is not None:
        overrides["warmup"] = args.warmup
    if args.iterations is not None:
        overrides["iterations"] = args.iterations
    if args.repeats is not None:
        overrides["repeats"] = args.repeats
    if overrides:
        config = replace(config, **overrides)

    if args.backends:
        adapters = [get_adapter(n) for n in args.backends]
    else:
        adapters = get_available_adapters()

    cases = [
        IonSpeciationLambdifyCase(),
        HeterogeneousOutputLambdifyCase(),
    ]

    rows = []
    for case in cases:
        for adapter in adapters:
            if not adapter.is_available():
                rows.append(BenchmarkRow(
                    case_name=case.name,
                    backend_name=adapter.name,
                    status="skipped",
                    skip_reason=adapter.skip_reason(),
                ))
                continue

            try:
                fn = case.build(adapter)
                case.validate(fn())
                result = run_benchmark(fn, config)
                rows.append(BenchmarkRow(
                    case_name=case.name,
                    backend_name=adapter.name,
                    status="ok",
                    warmup=config.warmup,
                    iterations=config.iterations,
                    repeats=config.repeats,
                    best_s=result.best,
                    median_s=result.median,
                    mean_s=result.mean,
                    stdev_s=result.stdev,
                ))
            except Exception as e:
                rows.append(BenchmarkRow(
                    case_name=case.name,
                    backend_name=adapter.name,
                    status="failed",
                    failure_reason=str(e),
                ))

    compute_speedups(rows)
    print(format_text_table(rows))

    if args.json_output:
        with open(args.json_output, "w") as f:
            f.write(format_json(rows))
        print(f"\nJSON written to {args.json_output}")

    return 0


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.command == "lambdify":
        return run_lambdify(args)
    print(f"Unknown command: {args.command}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
