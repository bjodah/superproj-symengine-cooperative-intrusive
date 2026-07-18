"""Timing utilities for benchmarks."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, List


@dataclass
class TimingResult:
    """Raw timing measurements for a single benchmark run."""
    times: List[float] = field(default_factory=list)

    @property
    def best(self) -> float:
        if not self.times:
            return float('nan')
        return min(self.times)

    @property
    def median(self) -> float:
        if not self.times:
            return float('nan')
        s = sorted(self.times)
        n = len(s)
        if n % 2 == 1:
            return s[n // 2]
        return (s[n // 2 - 1] + s[n // 2]) / 2.0

    @property
    def mean(self) -> float:
        if not self.times:
            return float('nan')
        return sum(self.times) / len(self.times)

    @property
    def stdev(self) -> float:
        if not self.times:
            return float('nan')
        n = len(self.times)
        if n < 2:
            return 0.0
        mu = sum(self.times) / n
        return (sum((t - mu) ** 2 for t in self.times) / n) ** 0.5


@dataclass
class BenchmarkConfig:
    """Configuration for benchmark execution."""
    warmup: int = 2
    iterations: int = 100
    repeats: int = 5


QUICK_CONFIG = BenchmarkConfig(warmup=1, iterations=5, repeats=2)
DEFAULT_CONFIG = BenchmarkConfig(warmup=2, iterations=100, repeats=5)


def run_benchmark(
    fn: Callable[[], Any],
    config: BenchmarkConfig | None = None,
) -> TimingResult:
    """Run *fn* under the given config and return timing measurements.

    Uses ``time.perf_counter()`` for all measurements.
    """
    if config is None:
        config = DEFAULT_CONFIG

    for _ in range(config.warmup):
        fn()

    times: list[float] = []
    for _ in range(config.repeats):
        start = time.perf_counter()
        for _ in range(config.iterations):
            fn()
        elapsed = time.perf_counter() - start
        times.append(elapsed / config.iterations)

    return TimingResult(times=times)
