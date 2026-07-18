"""CLI argument parsing for nbsymengine_benchmarks."""
from __future__ import annotations

import argparse
from typing import List, Optional


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="nbsymengine_benchmarks",
        description="Benchmark suite for nbsymengine Lambdify",
    )
    sub = parser.add_subparsers(dest="command")

    lambdify_parser = sub.add_parser("lambdify", help="Run Lambdify benchmarks")
    lambdify_parser.add_argument(
        "--quick", action="store_true",
        help="Use low iteration counts for CI smoke tests",
    )
    lambdify_parser.add_argument(
        "--backends", type=str, default=None,
        help="Comma-separated list of backends (default: all available)",
    )
    lambdify_parser.add_argument(
        "--json", type=str, default=None, dest="json_output",
        help="Path to write JSON output",
    )
    lambdify_parser.add_argument(
        "--warmup", type=int, default=None,
        help="Override warmup count",
    )
    lambdify_parser.add_argument(
        "--iterations", type=int, default=None,
        help="Override iteration count",
    )
    lambdify_parser.add_argument(
        "--repeats", type=int, default=None,
        help="Override repeat count",
    )

    args = parser.parse_args(argv)

    if args.repeats is not None and args.repeats < 1:
        parser.error("--repeats must be >= 1")

    if args.command is None:
        parser.print_help()
        raise SystemExit(1)

    if args.backends is not None:
        args.backends = [b.strip() for b in args.backends.split(",")]

    return args
