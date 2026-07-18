"""Tests for reporting utilities."""
import pytest
from nbsymengine_benchmarks.reporting import (
    BenchmarkRow,
    compute_speedups,
    format_text_table,
    format_json,
)


def test_format_text_table_empty():
    table = format_text_table([])
    assert isinstance(table, str)


def test_format_text_table_with_rows():
    rows = [
        BenchmarkRow(
            case_name="test_case",
            backend_name="sympy",
            status="ok",
            warmup=2,
            iterations=100,
            repeats=5,
            best_s=0.001,
            median_s=0.002,
            mean_s=0.003,
        ),
        BenchmarkRow(
            case_name="test_case",
            backend_name="nbsymengine",
            status="skipped",
            skip_reason="not installed",
        ),
    ]
    table = format_text_table(rows)
    assert "test_case" in table
    assert "sympy" in table
    assert "skipped" in table
    assert "not installed" in table
    assert "Warmup" in table


def test_format_json_empty():
    result = format_json([])
    assert result == "[]"


def test_format_json_with_rows():
    rows = [
        BenchmarkRow(
            case_name="test_case",
            backend_name="sympy",
            status="ok",
            warmup=2,
            iterations=100,
            repeats=5,
            best_s=0.001,
            median_s=0.002,
            mean_s=0.003,
        ),
    ]
    result = format_json(rows)
    assert '"case_name": "test_case"' in result
    assert '"best_s": 0.001' in result
    assert '"warmup": 2' in result


def test_format_json_skipped_includes_config():
    rows = [
        BenchmarkRow(
            case_name="test_case",
            backend_name="nbsymengine",
            status="skipped",
            skip_reason="not installed",
        ),
    ]
    result = format_json(rows)
    assert '"warmup": 0' in result
    assert '"iterations": 0' in result
    assert '"repeats": 0' in result
    assert '"skip_reason": "not installed"' in result


def test_compute_speedups():
    rows = [
        BenchmarkRow(
            case_name="c1", backend_name="sympy", status="ok",
            median_s=0.1, warmup=1, iterations=10, repeats=3,
        ),
        BenchmarkRow(
            case_name="c1", backend_name="nbsymengine", status="ok",
            median_s=0.01, warmup=1, iterations=10, repeats=3,
        ),
    ]
    compute_speedups(rows)
    assert rows[0].speedup_vs_sympy == 1.0
    assert rows[1].speedup_vs_sympy == pytest.approx(10.0)


def test_speedup_none_on_skipped():
    rows = [
        BenchmarkRow(case_name="c1", backend_name="sympy", status="skipped"),
        BenchmarkRow(case_name="c1", backend_name="other", status="skipped"),
    ]
    compute_speedups(rows)
    assert rows[0].speedup_vs_sympy is None
    assert rows[1].speedup_vs_sympy is None


def test_format_text_table_with_stdev():
    rows = [
        BenchmarkRow(
            case_name="test_case",
            backend_name="sympy",
            status="ok",
            warmup=2,
            iterations=100,
            repeats=5,
            best_s=0.001,
            median_s=0.002,
            mean_s=0.003,
            stdev_s=0.0005,
        ),
    ]
    table = format_text_table(rows)
    assert "StdDev" in table
    assert "0.0005" in table


def test_format_json_with_stdev():
    rows = [
        BenchmarkRow(
            case_name="test_case",
            backend_name="sympy",
            status="ok",
            warmup=2,
            iterations=100,
            repeats=5,
            best_s=0.001,
            median_s=0.002,
            mean_s=0.003,
            stdev_s=0.0005,
        ),
    ]
    result = format_json(rows)
    assert '"stdev_s": 0.0005' in result
