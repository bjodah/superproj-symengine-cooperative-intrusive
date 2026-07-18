#!/usr/bin/env python3
"""Measure Add-heavy SymEngine operations that cross the Python boundary."""

from __future__ import annotations

import argparse
import gc
import statistics
import time


def make_boundary_add(sx, factors: int, binding: str):
    if binding == "legacy":
        symbols = [sx.Symbol(f"x{i}") for i in range(factors)]
        zero = sx.Integer(0)

        def run():
            term = symbols[0]
            for factor in symbols[1:]:
                term = term * factor
            return term + zero

        return run

    symbols = [sx.symbol(f"x{i}") for i in range(factors)]
    zero = sx.integer(0)

    def run():
        term = symbols[0]
        for factor in symbols[1:]:
            term = sx.mul(term, factor)
        return sx.add(term, zero)

    return run


def make_expand(sx, exponent: int, binding: str):
    if binding == "legacy":
        x, y, z, w = (sx.Symbol(name) for name in ("x", "y", "z", "w"))
        expression = ((x + y) + (z + w)) ** exponent
        return lambda: sx.expand(expression)

    x, y, z, w = (sx.symbol(name) for name in ("x", "y", "z", "w"))
    base = sx.add(sx.add(x, y), sx.add(z, w))
    expression = sx.pow(base, sx.integer(exponent))
    return lambda: sx.expand(expression)


def measure(fn, iterations: int, repeats: int) -> tuple[float, list[float], int]:
    for _ in range(3):
        fn()

    samples: list[float] = []
    checksum = 0
    gc_was_enabled = gc.isenabled()
    gc.disable()
    try:
        for _ in range(repeats):
            start = time.perf_counter_ns()
            for _ in range(iterations):
                checksum ^= hash(fn())
            samples.append((time.perf_counter_ns() - start) / iterations)
    finally:
        if gc_was_enabled:
            gc.enable()
    return statistics.median(samples), samples, checksum


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("case", choices=("boundary-add", "expand"))
    parser.add_argument("--factors", type=int, default=16)
    parser.add_argument("--exponent", type=int, default=15)
    parser.add_argument("--iterations", type=int, default=None)
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--binding", choices=("nanobind", "legacy"),
                        default="nanobind")
    args = parser.parse_args()

    if args.binding == "legacy":
        import symengine as sx
    else:
        import nbsymengine as sx

    if args.case == "boundary-add":
        fn = make_boundary_add(sx, args.factors, args.binding)
        iterations = args.iterations or 1000
        parameter = f"factors={args.factors}"
    else:
        fn = make_expand(sx, args.exponent, args.binding)
        iterations = args.iterations or 10
        parameter = f"exponent={args.exponent}"

    median_ns, samples, checksum = measure(fn, iterations, args.repeats)
    print(f"case: {args.case}")
    print(f"binding: {args.binding}")
    print(f"{parameter}")
    print(f"iterations_per_sample: {iterations}")
    print(f"samples_ns_per_call: {','.join(f'{sample:.1f}' for sample in samples)}")
    print(f"median_ns_per_call: {median_ns:.1f}")
    print(f"checksum: {checksum}")


if __name__ == "__main__":
    main()
