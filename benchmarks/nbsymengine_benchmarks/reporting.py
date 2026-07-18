"""Reporting utilities for benchmark results."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class BenchmarkRow:
    """A single benchmark result row."""
    case_name: str
    backend_name: str
    status: str  # "ok", "failed", "skipped"
    skip_reason: Optional[str] = None
    failure_reason: Optional[str] = None
    warmup: int = 0
    iterations: int = 0
    repeats: int = 0
    best_s: Optional[float] = None
    median_s: Optional[float] = None
    mean_s: Optional[float] = None
    stdev_s: Optional[float] = None
    speedup_vs_sympy: Optional[float] = None


def compute_speedups(rows: List[BenchmarkRow]) -> None:
    """Compute speedup_vs_sympy for each row relative to the sympy backend."""
    sympy_times: Dict[str, float] = {}
    for r in rows:
        if r.backend_name == "sympy" and r.status == "ok" and r.median_s is not None:
            sympy_times[r.case_name] = r.median_s
    for r in rows:
        if r.status == "ok" and r.median_s is not None and r.case_name in sympy_times:
            r.speedup_vs_sympy = sympy_times[r.case_name] / r.median_s


def format_text_table(rows: List[BenchmarkRow]) -> str:
    """Format rows as an ASCII text table."""
    headers = [
        "Case", "Backend", "Status", "Warmup", "Iter", "Repeat",
        "Best(s)", "Median(s)", "Mean(s)", "StdDev(s)", "Speedup", "Reason",
    ]
    str_rows = []
    for r in rows:
        best = f"{r.best_s:.6g}" if r.best_s is not None else "-"
        med = f"{r.median_s:.6g}" if r.median_s is not None else "-"
        mean = f"{r.mean_s:.6g}" if r.mean_s is not None else "-"
        std = f"{r.stdev_s:.6g}" if r.stdev_s is not None else "-"
        spdup = f"{r.speedup_vs_sympy:.2f}x" if r.speedup_vs_sympy is not None else "-"
        reason = r.skip_reason or r.failure_reason or ""
        str_rows.append([
            r.case_name, r.backend_name, r.status,
            str(r.warmup),
            str(r.iterations), str(r.repeats),
            best, med, mean, std,
            spdup, reason,
        ])

    col_widths = [len(h) for h in headers]
    for row in str_rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(cell))

    def fmt_row(cells):
        return " | ".join(cell.ljust(col_widths[i]) for i, cell in enumerate(cells))

    lines = [fmt_row(headers), "-+-".join("-" * w for w in col_widths)]
    for row in str_rows:
        lines.append(fmt_row(row))
    return "\n".join(lines)


def format_json(rows: List[BenchmarkRow]) -> str:
    """Format rows as a JSON string."""
    data = []
    for r in rows:
        d = {
            "case_name": r.case_name,
            "backend_name": r.backend_name,
            "status": r.status,
        }
        if r.skip_reason:
            d["skip_reason"] = r.skip_reason
        if r.failure_reason:
            d["failure_reason"] = r.failure_reason
        d["warmup"] = r.warmup
        d["iterations"] = r.iterations
        d["repeats"] = r.repeats
        if r.status == "ok":
            d["best_s"] = r.best_s
            d["median_s"] = r.median_s
            d["mean_s"] = r.mean_s
            d["stdev_s"] = r.stdev_s
        if r.speedup_vs_sympy is not None:
            d["speedup_vs_sympy"] = r.speedup_vs_sympy
        data.append(d)
    return json.dumps(data, indent=2)
