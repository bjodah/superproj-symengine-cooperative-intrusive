"""Phase 7.4: Threading / GIL stress tests for nanobind intrusive bindings.

Concurrency model
=================
The cooperative_intrusive backend uses nanobind's intrusive reference counter with GIL
hooks.  When a C++ ``RCP<const Basic>`` is handed to Python the counter is
"owned" by Python; subsequent C++-side ``dec_ref`` calls **acquire the GIL**
before decrementing.  This means:

* Dropping the last Python reference to a Python-owned RCP from a **non-GIL
  C++ worker thread** triggers a GIL acquire inside ``dec_ref``.  If that
  worker thread also holds an internal SymEngine lock, the acquire can
  deadlock against the main thread which may be waiting on that same lock.

* These tests exercise that scenario from pure Python by spawning many
  threads that concurrently create, manipulate, and destroy bound objects.
  A deadlock will manifest as a test timeout (the thread pool will never
  return).

What is tested
==============
1. Dropping Python-owned RCPs from multiple C++ worker threads concurrently.
2. Rapid create/destroy cycles from multiple threads.
3. No deadlock when destroying Python-owned objects while operations happen
   on other threads.
4. Concurrent expression building and destruction.
5. Mixed read/write contention on shared expressions.

All tests use ``concurrent.futures.ThreadPoolExecutor`` and are marked
``@pytest.mark.slow`` because they run for several seconds each.
"""

from __future__ import annotations

import gc
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

# ---------------------------------------------------------------------------
# Import the generated extension (same pattern as test_generated_rcp.py)
# ---------------------------------------------------------------------------

try:
    from nbsymengine import _core as m
except ImportError:
    m = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Timeout in seconds for each test.  If a deadlock occurs the thread pool
# future will never complete and the test will hang; we bound that with a
# generous timeout so CI doesn't stall forever.
DEADLOCK_TIMEOUT = 30  # seconds


def _create_symbol(idx: int) -> object:
    """Create a symbol with a unique name."""
    return m.symbol(f"t{idx}")


def _build_expression(depth: int) -> object:
    """Build a nested add expression of the given depth."""
    x = m.symbol("x")
    expr = x
    for i in range(depth):
        expr = m.add(expr, m.integer(i))
    return expr


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------
@pytest.mark.skipif(m is None, reason="nbsymengine._core not importable")
class TestThreadingStress:
    """Threading / GIL stress tests for the intrusive reference counter.

    These tests exercise concurrent creation and destruction of Python-owned
    ``RCP<const Basic>`` objects from multiple threads.  The intrusive counter
    acquires the GIL on ``dec_ref``; if the GIL acquisition deadlocks against
    an internal SymEngine lock held by a worker thread, the test will time out.
    """

    # ------------------------------------------------------------------
    # Test 1: Drop Python-owned RCPs from multiple worker threads
    # ------------------------------------------------------------------
    @pytest.mark.slow
    def test_drop_rcps_from_multiple_threads(self) -> None:
        """Create objects on the main thread, hand them to worker threads,
        and drop all references concurrently.

        Each worker receives a list of Python-owned RCPs and deletes them.
        Because the objects were created on the main thread but destroyed on
        a worker, the worker's ``dec_ref`` must acquire the GIL -- this is
        the core deadlock scenario we are stress-testing.
        """
        num_workers = 8
        objects_per_worker = 100

        # Create all objects on the main thread (Python-owned).
        batches: list[list[object]] = []
        for _ in range(num_workers):
            batch = [m.symbol(f"s{i}") for i in range(objects_per_worker)]
            # Also create some compound expressions.
            x = m.symbol("x")
            batch.extend(m.add(x, m.integer(i)) for i in range(50))
            batches.append(batch)

        errors: list[BaseException] = []

        def drop_batch(batch: list[object]) -> None:
            try:
                batch.clear()
                gc.collect()
            except BaseException as exc:
                errors.append(exc)

        with ThreadPoolExecutor(max_workers=num_workers) as pool:
            futures = [pool.submit(drop_batch, b) for b in batches]
            # Wait with timeout to detect deadlocks.
            for fut in as_completed(futures, timeout=DEADLOCK_TIMEOUT):
                fut.result()  # re-raise any exception

        assert not errors, f"Worker errors: {errors}"

    # ------------------------------------------------------------------
    # Test 2: Rapid create/destroy cycles from multiple threads
    # ------------------------------------------------------------------
    @pytest.mark.slow
    def test_rapid_create_destroy_cycles(self) -> None:
        """Each worker thread rapidly creates and destroys objects.

        This exercises the full allocate -> inc_ref -> dec_ref -> free
        cycle concurrently, including the GIL acquisition in dec_ref when
        the refcount drops to zero on a non-main thread.
        """
        num_workers = 8
        iterations = 200

        def worker(tid: int) -> None:
            for i in range(iterations):
                x = m.symbol(f"w{tid}_{i}")
                y = m.integer(i)
                s = m.add(x, y)
                # Trigger destruction on the worker thread.
                del s, x, y
            gc.collect()

        with ThreadPoolExecutor(max_workers=num_workers) as pool:
            futures = [pool.submit(worker, tid) for tid in range(num_workers)]
            for fut in as_completed(futures, timeout=DEADLOCK_TIMEOUT):
                fut.result()

    # ------------------------------------------------------------------
    # Test 3: No deadlock when destroying while operations happen elsewhere
    # ------------------------------------------------------------------
    @pytest.mark.slow
    def test_concurrent_destroy_and_operate(self) -> None:
        """One set of threads builds expressions while another set destroys
        shared objects.

        This mimics the scenario where a background computation holds a
        reference to a shared expression while the owner drops its copy.
        """
        num_builders = 4
        num_destroyers = 4
        shared_count = 200

        # Pre-create shared objects on the main thread.
        shared = [m.symbol(f"shared{i}") for i in range(shared_count)]

        def builder() -> None:
            """Build new expressions using the shared symbols."""
            for s in shared:
                expr = m.add(s, m.integer(1))
                expr = m.mul(expr, m.integer(2))
                # expr goes out of scope here -> dec_ref on worker thread.
                del expr

        def destroyer() -> None:
            """Delete local copies of shared symbols."""
            local = list(shared)  # shallow copy -- inc_ref for each
            del local  # drop all refs at once -- dec_ref on worker thread
            gc.collect()

        with ThreadPoolExecutor(max_workers=num_builders + num_destroyers) as pool:
            futures = []
            futures.extend(pool.submit(builder) for _ in range(num_builders))
            futures.extend(pool.submit(destroyer) for _ in range(num_destroyers))
            for fut in as_completed(futures, timeout=DEADLOCK_TIMEOUT):
                fut.result()

        # Clean up the original shared list on the main thread.
        del shared
        gc.collect()

    # ------------------------------------------------------------------
    # Test 4: Concurrent expression building and destruction
    # ------------------------------------------------------------------
    @pytest.mark.slow
    def test_concurrent_expression_building_and_destruction(self) -> None:
        """Multiple threads build deep expression trees and then destroy them.

        Deep nesting means many intermediate RCP objects are created and
        destroyed in rapid succession, maximizing the chance of lock
        contention between the GIL and SymEngine internal locks.
        """
        num_workers = 6
        tree_depth = 80

        errors: list[BaseException] = []

        def build_and_destroy(tid: int) -> None:
            try:
                for _ in range(5):
                    expr = _build_expression(tree_depth)
                    assert isinstance(expr, m.Basic)
                    del expr
                gc.collect()
            except BaseException as exc:
                errors.append(exc)

        with ThreadPoolExecutor(max_workers=num_workers) as pool:
            futures = [pool.submit(build_and_destroy, i) for i in range(num_workers)]
            for fut in as_completed(futures, timeout=DEADLOCK_TIMEOUT):
                fut.result()

        assert not errors, f"Worker errors: {errors}"

    # ------------------------------------------------------------------
    # Test 5: Mixed read/write contention on shared expressions
    # ------------------------------------------------------------------
    @pytest.mark.slow
    def test_mixed_read_write_contention(self) -> None:
        """Readers call ``str()`` / ``hash()`` on shared expressions while
        writers create and destroy new expressions.

        ``str()`` and ``hash()`` are const methods that do not modify the
        refcount, but they may be called concurrently with ``dec_ref`` on
        the same object from another thread.
        """
        num_readers = 4
        num_writers = 4
        shared_count = 100

        shared = [m.add(m.symbol(f"r{i}"), m.integer(i)) for i in range(shared_count)]

        def reader() -> None:
            for expr in shared:
                _ = str(expr)
                _ = hash(expr)

        def writer() -> None:
            for i in range(shared_count):
                x = m.symbol(f"w{i}")
                y = m.integer(i)
                expr = m.add(x, y)
                _ = str(expr)
                del expr, x, y
            gc.collect()

        with ThreadPoolExecutor(max_workers=num_readers + num_writers) as pool:
            futures = []
            futures.extend(pool.submit(reader) for _ in range(num_readers))
            futures.extend(pool.submit(writer) for _ in range(num_writers))
            for fut in as_completed(futures, timeout=DEADLOCK_TIMEOUT):
                fut.result()

        del shared
        gc.collect()

    # ------------------------------------------------------------------
    # Test 6: Fan-out / fan-in with shared root expression
    # ------------------------------------------------------------------
    @pytest.mark.slow
    def test_fan_out_fan_in_shared_root(self) -> None:
        """A single root expression is shared across many threads that each
        derive new expressions from it, then all threads finish and drop
        their references.

        This exercises the pattern where a "root" object is ref'd by many
        workers; the last worker to drop triggers the actual deallocation.
        """
        num_workers = 8
        derivations_per_worker = 50

        root = m.add(m.symbol("root"), m.integer(0))

        def derive_and_drop(tid: int, _root=root) -> None:
            results = []
            for i in range(derivations_per_worker):
                leaf = m.symbol(f"leaf_{tid}_{i}")
                derived = m.add(_root, leaf)
                results.append(derived)
            # Drop all derived expressions and the local ref to root.
            del results
            del _root
            gc.collect()

        with ThreadPoolExecutor(max_workers=num_workers) as pool:
            futures = [pool.submit(derive_and_drop, i) for i in range(num_workers)]
            for fut in as_completed(futures, timeout=DEADLOCK_TIMEOUT):
                fut.result()

        # root is still alive on the main thread.
        assert isinstance(root, m.Basic)
        del root
        gc.collect()

    # ------------------------------------------------------------------
    # Test 7: Thread-safety of same_object / identity reuse
    # ------------------------------------------------------------------
    @pytest.mark.slow
    def test_concurrent_same_object_checks(self) -> None:
        """Multiple threads call ``same_object`` concurrently while other
        threads create and destroy objects.

        ``same_object`` compares C++ pointers; it should be safe to call
        concurrently as long as the objects are alive.  This test verifies
        no crash or data race occurs.
        """
        num_workers = 6
        checks_per_worker = 200

        x = m.symbol("x")
        y = m.symbol("y")

        def checker() -> None:
            for _ in range(checks_per_worker):
                assert m.same_object(x, x) is True
                assert m.same_object(x, y) is False

        def creator() -> None:
            for i in range(checks_per_worker):
                z = m.symbol(f"z{i}")
                _ = m.add(x, z)
                del z
            gc.collect()

        with ThreadPoolExecutor(max_workers=num_workers) as pool:
            futures = []
            # Half checkers, half creators.
            for i in range(num_workers):
                if i % 2 == 0:
                    futures.append(pool.submit(checker))
                else:
                    futures.append(pool.submit(creator))
            for fut in as_completed(futures, timeout=DEADLOCK_TIMEOUT):
                fut.result()

        del x, y
        gc.collect()

    # ------------------------------------------------------------------
    # Test 8: Stress test with barriers for maximum contention
    # ------------------------------------------------------------------
    @pytest.mark.slow
    def test_barrier_synchronized_destruction(self) -> None:
        """All threads wait on a barrier, then simultaneously destroy their
        objects.

        The barrier ensures maximum contention: every thread hits ``dec_ref``
        at the exact same instant, maximizing the chance of triggering any
        GIL-vs-lock ordering bug.
        """
        num_threads = 8
        objects_per_thread = 150
        barrier = threading.Barrier(num_threads)

        # Each slot holds a list of objects owned by one thread.
        per_thread_objects: list[list[object]] = [[] for _ in range(num_threads)]

        def synchronized_destroy(tid: int) -> None:
            # Create objects.
            objs = [m.symbol(f"barrier_{tid}_{i}") for i in range(objects_per_thread)]
            x = m.symbol(f"bx_{tid}")
            objs.extend(m.add(x, m.integer(i)) for i in range(50))
            per_thread_objects[tid] = objs

            # Wait for all threads to be ready.
            barrier.wait(timeout=DEADLOCK_TIMEOUT)

            # Simultaneously destroy everything.  Use None assignment rather
            # than ``del`` to avoid shrinking the shared list (which would
            # cause IndexError for other threads racing on their own index).
            del objs
            per_thread_objects[tid] = None
            gc.collect()

        with ThreadPoolExecutor(max_workers=num_threads) as pool:
            futures = [pool.submit(synchronized_destroy, i) for i in range(num_threads)]
            for fut in as_completed(futures, timeout=DEADLOCK_TIMEOUT):
                fut.result()


    # ------------------------------------------------------------------
    # Test 9: Drop RCPs from real C++ worker threads
    # ------------------------------------------------------------------
    @pytest.mark.slow
    def test_drop_rcps_on_cpp_threads(self) -> None:
        """Exercise the real deadlock scenario: C++ worker threads destroy
        Python-owned RCPs while the GIL is released.

        Unlike the Python ThreadPoolExecutor tests above, this calls into a
        C++ helper that spawns ``std::thread`` workers.  Each worker clears
        its batch of ``RCP<const Basic>`` objects, triggering ``dec_ref``
        (and thus GIL acquisition) from a true C++ thread with no GIL held.
        """
        num_cpp_workers = 4
        objects_per_batch = 150
        rounds = 10

        for _ in range(rounds):
            # Create objects on the main Python thread (Python-owned).
            objs = [m.symbol(f"cpp_d{i}") for i in range(objects_per_batch)]
            x = m.symbol("x")
            objs.extend(m.add(x, m.integer(i)) for i in range(50))

            # Hand them to C++ threads that will drop them.
            m.drop_rcps_on_cpp_threads(objs, num_cpp_workers)

            # The helper returned -- no deadlock.  The vector was moved into
            # C++ so Python's list is now empty; verify.
            assert len(objs) == 0


class TestThreadingDocumentation:
    """Verify that the concurrency model documentation is present."""

    def test_module_docstring_describes_concurrency_model(self) -> None:
        """The module docstring must explain the GIL-hooks mechanism."""
        this_module = sys.modules[__name__]

        doc = this_module.__doc__
        assert "GIL" in doc
        assert "intrusive" in doc.lower()
        assert "dec_ref" in doc
        assert "deadlock" in doc.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--timeout=60"])
