"""Stress tests for singleton behaviour around interpreter shutdown."""

import os
import subprocess
import sys
import threading

_SUBPROCESS_TIMEOUT = 30


def _subprocess_python() -> str:
    return os.environ.get("NBSYMENGINE_SUBPROCESS_PYTHON", sys.executable)


def _run_code(code: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [_subprocess_python(), "-c", code],
        capture_output=True,
        text=True,
        timeout=_SUBPROCESS_TIMEOUT,
    )


# ---------------------------------------------------------------------------
# Test 1: repeated import / drop in subprocesses
# ---------------------------------------------------------------------------

def test_repeated_import_drop():
    """Import nbsymengine, access symbols, then exit -- 10 times."""
    code = (
        "from nbsymengine import _core\n"
        "x = _core.symbol('x')\n"
        "p = _core.pi()\n"
        "z = _core.zero()\n"
        "assert _core.same_object(p, _core.pi())\n"
        "assert _core.same_object(z, _core.zero())\n"
    )
    for i in range(10):
        result = _run_code(code)
        assert result.returncode == 0, (
            f"iteration {i} failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )


# ---------------------------------------------------------------------------
# Test 2: wrappers for all major singletons alive at shutdown
# ---------------------------------------------------------------------------

def test_singleton_wrappers_before_shutdown():
    """Create wrappers for every major singleton and let the interpreter die."""
    code = (
        "from nbsymengine import _core\n"
        "singletons = {\n"
        "    'pi': _core.pi(),\n"
        "    'e': _core.e(),\n"
        "    'euler_gamma': _core.euler_gamma(),\n"
        "    'I': _core.I(),\n"
        "    'oo': _core.oo(),\n"
        "    'zoo': _core.zoo(),\n"
        "    'nan': _core.nan_const(),\n"
        "    'true': _core.true_const(),\n"
        "    'false': _core.false_const(),\n"
        "    'zero': _core.zero(),\n"
        "    'one': _core.one(),\n"
        "    'reals': _core.reals(),\n"
        "    'integers': _core.integers(),\n"
        "    'emptyset': _core.emptyset(),\n"
        "    'universalset': _core.universalset(),\n"
        "}\n"
        "# Verify they are all valid Basic objects\n"
        "for name, obj in singletons.items():\n"
        "    assert isinstance(obj, _core.Basic), f'{name} is not Basic'\n"
        "# Hold references until shutdown\n"
    )
    result = _run_code(code)
    assert result.returncode == 0, (
        f"Failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


# ---------------------------------------------------------------------------
# Test 3: booleans, relationals, and sets alive at shutdown
# ---------------------------------------------------------------------------

def test_boolean_relational_before_shutdown():
    """Create booleans, relationals, and sets, then shut down."""
    code = (
        "from nbsymengine import _core\n"
        "t = _core.true_const()\n"
        "f = _core.false_const()\n"
        "assert isinstance(t, _core.BooleanAtom)\n"
        "assert isinstance(f, _core.BooleanAtom)\n"
        "\n"
        "x = _core.symbol('x')\n"
        "\n"
        "rels = [\n"
        "    _core.Eq(x, _core.integer(1)),\n"
        "    _core.Ne(x, _core.integer(2)),\n"
        "    _core.Lt(x, _core.integer(3)),\n"
        "    _core.Gt(x, _core.integer(4)),\n"
        "    _core.Le(x, _core.integer(5)),\n"
        "    _core.Ge(x, _core.integer(6)),\n"
        "]\n"
        "for r in rels:\n"
        "    assert isinstance(r, _core.Relational)\n"
        "\n"
        "sets = [\n"
        "    _core.emptyset(),\n"
        "    _core.universalset(),\n"
        "    _core.finiteset({_core.integer(1), _core.integer(2)}),\n"
        "    _core.interval(_core.integer(0), _core.integer(1)),\n"
        "    _core.reals(),\n"
        "    _core.integers(),\n"
        "]\n"
        "for s in sets:\n"
        "    assert isinstance(s, _core.Set)\n"
        "\n"
        "# Boolean combinators\n"
        "cond1 = _core.Lt(x, _core.integer(10))\n"
        "cond2 = _core.Gt(x, _core.integer(0))\n"
        "and_expr = _core.logical_and(cond1, cond2)\n"
        "or_expr = _core.logical_or(cond1, cond2)\n"
        "not_expr = _core.logical_not(cond1)\n"
        "assert isinstance(and_expr, _core.Boolean)\n"
        "assert isinstance(or_expr, _core.Boolean)\n"
        "assert isinstance(not_expr, _core.Boolean)\n"
    )
    result = _run_code(code)
    assert result.returncode == 0, (
        f"Failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


# ---------------------------------------------------------------------------
# Test 4: worker-thread RCP drops
# ---------------------------------------------------------------------------

def test_worker_thread_rcp_drops():
    """Worker threads create symbolic objects; main thread waits, then shutdown."""
    code = (
        "import threading\n"
        "from nbsymengine import _core\n"
        "\n"
        "errors = []\n"
        "\n"
        "def worker(n):\n"
        "    try:\n"
        "        x = _core.symbol(f'x{n}')\n"
        "        expr = x\n"
        "        for i in range(20):\n"
        "            expr = _core.add(expr, _core.integer(i))\n"
        "        # Create singletons from the worker thread\n"
        "        p = _core.pi()\n"
        "        z = _core.zero()\n"
        "        r = _core.reals()\n"
        "        t = _core.true_const()\n"
        "        # Verify identity still holds across threads\n"
        "        assert _core.same_object(p, _core.pi())\n"
        "        assert _core.same_object(z, _core.zero())\n"
        "        assert _core.same_object(r, _core.reals())\n"
        "        assert _core.same_object(t, _core.true_const())\n"
        "    except Exception as e:\n"
        "        errors.append(e)\n"
        "\n"
        "threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]\n"
        "for t in threads:\n"
        "    t.start()\n"
        "for t in threads:\n"
        "    t.join(timeout=15)\n"
        "assert not errors, f'Worker errors: {errors}'\n"
        "# Main thread still holds a reference\n"
        "main_x = _core.symbol('main_x')\n"
        "assert isinstance(main_x, _core.Basic)\n"
    )
    result = _run_code(code)
    assert result.returncode == 0, (
        f"Failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


# ---------------------------------------------------------------------------
# Test 5: subprocess singleton identity
# ---------------------------------------------------------------------------

def test_subprocess_singleton_identity():
    """Verify singleton identity (is) holds in a subprocess."""
    code = (
        "from nbsymengine import _core\n"
        "assert _core.same_object(_core.pi(), _core.pi()), 'pi identity'\n"
        "assert _core.same_object(_core.e(), _core.e()), 'e identity'\n"
        "assert _core.same_object(_core.euler_gamma(), _core.euler_gamma()), 'euler_gamma identity'\n"
        "assert _core.same_object(_core.zero(), _core.zero()), 'zero identity'\n"
        "assert _core.same_object(_core.one(), _core.one()), 'one identity'\n"
        "assert _core.same_object(_core.I(), _core.I()), 'I identity'\n"
        "assert _core.same_object(_core.oo(), _core.oo()), 'oo identity'\n"
        "assert _core.same_object(_core.true_const(), _core.true_const()), 'true identity'\n"
        "assert _core.same_object(_core.false_const(), _core.false_const()), 'false identity'\n"
        "assert _core.same_object(_core.reals(), _core.reals()), 'reals identity'\n"
        "assert _core.same_object(_core.integers(), _core.integers()), 'integers identity'\n"
        "assert _core.same_object(_core.emptyset(), _core.emptyset()), 'emptyset identity'\n"
        "assert _core.same_object(_core.universalset(), _core.universalset()), 'universalset identity'\n"
    )
    result = _run_code(code)
    assert result.returncode == 0, (
        f"Identity test failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_manual_ext_singleton_wrappers_before_shutdown():
    """Import symengine_manual_ext, materialize singletons, exit cleanly."""
    code = (
        "import symengine_manual_ext as m\n"
        "singletons = {\n"
        "    'zero': m.zero(),\n"
        "    'one': m.one(),\n"
        "    'pi': m.pi(),\n"
        "    'euler_gamma': m.euler_gamma(),\n"
        "    'reals': m.reals(),\n"
        "    'integers': m.integers(),\n"
        "    'emptyset': m.emptyset(),\n"
        "    'universalset': m.universalset(),\n"
        "}\n"
        "for name, obj in singletons.items():\n"
        "    assert isinstance(obj, m.Basic), f'{name} is not Basic'\n"
    )
    result = _run_code(code)
    assert result.returncode == 0, (
        f"Failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_sign_integer_minus_seven_no_leak():
    """Verify sign(integer(-7)) doesn't leak or crash at shutdown."""
    code = (
        "from nbsymengine import _core\n"
        "s = _core.sign(_core.integer(-7))\n"
        "del s\n"
    )
    result = _run_code(code)
    assert result.returncode == 0, f"Failed: {result.stderr}"
    assert "nanobind: leaked" not in result.stderr, f"Leak detected: {result.stderr}"


def test_floor_neg_oo_no_leak():
    """Verify floor(neg(oo)) doesn't leak or crash at shutdown."""
    code = (
        "from nbsymengine import _core\n"
        "v = _core.floor(_core.neg(_core.oo()))\n"
        "del v\n"
    )
    result = _run_code(code)
    assert result.returncode == 0, f"Failed: {result.stderr}"
    assert "nanobind: leaked" not in result.stderr, f"Leak detected: {result.stderr}"


def test_ceiling_neg_oo_no_leak():
    """Verify ceiling(neg(oo)) doesn't leak or crash at shutdown."""
    code = (
        "from nbsymengine import _core\n"
        "v = _core.ceiling(_core.neg(_core.oo()))\n"
        "del v\n"
    )
    result = _run_code(code)
    assert result.returncode == 0, f"Failed: {result.stderr}"
    assert "nanobind: leaked" not in result.stderr, f"Leak detected: {result.stderr}"


def test_sin_symbol_names_bound_no_leak():
    """Verify sin(symbol) with names left bound doesn't leak at shutdown."""
    code = (
        "from nbsymengine import _core\n"
        "x = _core.symbol('x')\n"
        "s = _core.sin(x)\n"
    )
    result = _run_code(code)
    assert result.returncode == 0, f"Failed: {result.stderr}"
    assert "nanobind: leaked" not in result.stderr, f"Leak detected: {result.stderr}"


def test_gc_get_objects_held_at_exit_no_leak_or_crash():
    """Verify holding gc.get_objects() at exit doesn't crash or leak."""
    code = (
        "import gc\n"
        "from nbsymengine import _core\n"
        "x = _core.symbol('x')\n"
        "s = _core.sin(x)\n"
        "b = gc.get_objects()\n"
    )
    result = _run_code(code)
    assert result.returncode == 0, f"Failed: {result.stderr}"
    assert "nanobind: leaked" not in result.stderr, f"Leak detected: {result.stderr}"
