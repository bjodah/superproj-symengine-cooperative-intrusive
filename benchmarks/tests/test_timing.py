"""Tests for timing utilities."""
import pytest
import math
from nbsymengine_benchmarks.timing import TimingResult


def test_timing_result_empty_times():
    """TimingResult properties return nan on empty times list."""
    result = TimingResult(times=[])
    assert math.isnan(result.best)
    assert math.isnan(result.median)
    assert math.isnan(result.mean)
    assert math.isnan(result.stdev)


def test_timing_result_single_time():
    result = TimingResult(times=[0.5])
    assert result.best == 0.5
    assert result.median == 0.5
    assert result.mean == 0.5


def test_timing_result_even_count():
    result = TimingResult(times=[0.1, 0.3, 0.2, 0.4])
    assert result.best == 0.1
    assert result.median == pytest.approx(0.25)
    assert result.mean == pytest.approx(0.25)


def test_timing_result_odd_count():
    result = TimingResult(times=[0.3, 0.1, 0.2])
    assert result.best == 0.1
    assert result.median == pytest.approx(0.2)
    assert result.mean == pytest.approx(0.2)


def test_timing_result_stdev_empty():
    """stdev returns nan on empty times list."""
    result = TimingResult(times=[])
    assert math.isnan(result.stdev)


def test_timing_result_stdev_single():
    """stdev returns 0.0 for a single measurement."""
    result = TimingResult(times=[0.5])
    assert result.stdev == 0.0


def test_timing_result_stdev_multi():
    """stdev computes population standard deviation."""
    result = TimingResult(times=[0.1, 0.3, 0.2, 0.4])
    # mean=0.25, pop var=((0.15^2+0.05^2+0.05^2+0.15^2)/4)=0.0125
    # pop stdev=sqrt(0.0125)≈0.111803
    assert result.stdev == pytest.approx(0.11180339887498948)
