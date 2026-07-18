"""Tests for benchmark cases: import and correctness."""
import pytest
import numpy as np


def test_ion_speciation_build_with_sympy():
    from nbsymengine_benchmarks.cases import IonSpeciationLambdifyCase
    from nbsymengine_benchmarks.adapters import SymPyAdapter

    case = IonSpeciationLambdifyCase()
    adapter = SymPyAdapter()
    if not adapter.is_available():
        pytest.skip("sympy not available")

    fn = case.build(adapter)
    result = fn()
    assert result is not None
    case.validate(result)


def test_ion_speciation_expected():
    from nbsymengine_benchmarks.cases import IonSpeciationLambdifyCase

    case = IonSpeciationLambdifyCase()
    expected = case.expected()
    assert len(expected) == 15
    assert all(np.isfinite(v) for v in expected)


def test_heterogeneous_output_build_with_sympy():
    from nbsymengine_benchmarks.cases import HeterogeneousOutputLambdifyCase
    from nbsymengine_benchmarks.adapters import SymPyAdapter

    case = HeterogeneousOutputLambdifyCase()
    adapter = SymPyAdapter()
    if not adapter.is_available():
        pytest.skip("sympy not available")

    fn = case.build(adapter)
    result = fn()
    assert isinstance(result, tuple)
    assert len(result) == 2
    v, m = result
    assert np.array(v).shape == (1, 14) or np.array(v).shape == (14,)
    case.validate(result)


def test_heterogeneous_input_size():
    from nbsymengine_benchmarks.cases import HeterogeneousOutputLambdifyCase

    case = HeterogeneousOutputLambdifyCase()
    inp = case.input()
    assert inp.size == 26


def test_adapters_available():
    from nbsymengine_benchmarks.adapters import ALL_ADAPTERS

    available = []
    for adapter in ALL_ADAPTERS:
        assert isinstance(adapter.name, str)
        assert adapter.is_available() == (adapter.skip_reason() is None)
        if adapter.is_available():
            available.append(adapter)
    assert len(available) >= 1, "At least one backend adapter must be available"


def test_timing_run_benchmark():
    from nbsymengine_benchmarks.timing import run_benchmark, BenchmarkConfig

    call_count = 0
    def fn():
        nonlocal call_count
        call_count += 1

    config = BenchmarkConfig(warmup=1, iterations=3, repeats=2)
    result = run_benchmark(fn, config)
    assert len(result.times) == 2
    assert result.best >= 0
    # warmup(1) + repeats(2) * iterations(3) = 7
    assert call_count == 7


def test_cli_repeats_zero_rejected():
    """--repeats 0 must be rejected by the CLI."""
    from nbsymengine_benchmarks.cli import parse_args
    with pytest.raises(SystemExit):
        parse_args(["lambdify", "--repeats", "0"])


def test_cli_repeats_negative_rejected():
    """--repeats -1 must be rejected by the CLI."""
    from nbsymengine_benchmarks.cli import parse_args
    with pytest.raises(SystemExit):
        parse_args(["lambdify", "--repeats", "-1"])
