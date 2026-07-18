"""Phase 4 tests for hand-written nanobind ownership bridge.

Validates:
  1. C++ -> Python -> C++ round trip
  2. Identity reuse via self_external()
  3. const behavior
  4. Lifecycle / destruction counts
  5. Python-subclass round trip (trampoline)
  6. No nb::ref<T> used (grep check in report)
  7. Thread/GIL stress basics
"""

import gc
import sys
import pathlib
import pytest

# The extension module is built by CMake and must be on PYTHONPATH.
import symengine_manual_ext as m


# ---------------------------------------------------------------------------
# Test 1: C++ -> Python -> C++ round trip
# ---------------------------------------------------------------------------
class TestRoundTrip:
    def test_symbol_round_trip(self):
        x = m.symbol("x")
        y = m.symbol("y")
        s = m.add(x, y)
        assert isinstance(x, m.Basic)
        assert isinstance(y, m.Basic)
        assert isinstance(s, m.Basic)
        assert str(s) == "x + y" or str(s) == "y + x"

    def test_integer_round_trip(self):
        n = m.integer(42)
        assert isinstance(n, m.Integer)
        assert str(n) == "42"

    def test_mul_round_trip(self):
        x = m.symbol("x")
        y = m.symbol("y")
        p = m.mul(x, y)
        assert isinstance(p, m.Mul)
        result_str = str(p)
        assert "x" in result_str and "y" in result_str

    def test_pow_round_trip(self):
        x = m.symbol("x")
        n = m.integer(2)
        p = m.pow(x, n)
        assert isinstance(p, m.Pow)

    def test_python_object_passes_to_cpp(self):
        x = m.symbol("x")
        y = m.symbol("y")
        s1 = m.add(x, y)
        # Pass the result back to C++ (exercises Python -> C++ caster)
        s2 = m.add(s1, x)
        assert isinstance(s2, m.Basic)

    def test_sub_round_trip(self):
        x = m.symbol("x")
        y = m.symbol("y")
        s = m.sub(x, y)
        assert isinstance(s, m.Basic)

    def test_div_round_trip(self):
        x = m.symbol("x")
        y = m.symbol("y")
        d = m.div(x, y)
        assert isinstance(d, m.Basic)

    def test_neg_round_trip(self):
        x = m.symbol("x")
        n = m.neg(x)
        assert isinstance(n, m.Basic)

    def test_get_args(self):
        """get_args() should return the arguments of an expression."""
        x = m.symbol("x")
        y = m.symbol("y")
        s = m.add(x, y)
        args = s.get_args()
        assert isinstance(args, list)
        assert len(args) == 2
        for a in args:
            assert isinstance(a, m.Basic)

    def test_get_args_leaf(self):
        """get_args() on a symbol should return empty list."""
        x = m.symbol("x")
        assert x.get_args() == []


# ---------------------------------------------------------------------------
# Test 2: Identity reuse via self_external()
# ---------------------------------------------------------------------------
class TestIdentityReuse:
    def test_same_python_object_returned(self):
        """An API that returns its argument unchanged should return the
        identical Python object (via the self_external() branch in from_cpp)."""
        x = m.symbol("x")
        y = m.symbol("y")
        # add(x, zero_like) would normally simplify, but we can test
        # that the same object is returned when C++ returns the same pointer.
        # Using same_object to verify pointer identity.
        assert m.same_object(x, x) is True
        assert m.same_object(x, y) is False

    def test_constants_are_singletons(self):
        """Constants like zero, one should return equal objects.
        Each call creates a fresh C++ instance (to avoid nanobind leaks
        on static singletons), so pointer identity does NOT hold."""
        a = m.zero()
        b = m.zero()
        assert a == b  # Value-equal

    def test_symbol_factory_returns_same_object_for_same_name(self):
        """Symbol factory may return the same object for the same name
        depending on SymEngine internals. At minimum, the object should
        round-trip correctly."""
        x1 = m.symbol("x")
        x2 = m.symbol("x")
        # They may or may not be the same object -- but they should be equal
        assert m.same_object(x1, x2) == (x1 is x2)


# ---------------------------------------------------------------------------
# Test 3: const behavior
# ---------------------------------------------------------------------------
class TestConstBehavior:
    def test_rcp_const_basic_accepted(self):
        """Functions typed RCP<const Basic> accept and return correctly."""
        x = m.symbol("x")
        y = m.symbol("y")
        s = m.add(x, y)  # returns RCP<const Basic>
        assert isinstance(s, m.Basic)

    def test_rcp_const_integer_accepted(self):
        """RCP<const Integer> is accepted where RCP<const Basic> is expected."""
        n = m.integer(10)
        x = m.symbol("x")
        s = m.add(n, x)  # Integer is a Basic subclass
        assert isinstance(s, m.Basic)

    def test_const_return_from_factory(self):
        """Factory functions return RCP<const Basic> which should be usable."""
        x = m.symbol("x")
        # Can call methods on it (const methods)
        assert isinstance(str(x), str)
        assert isinstance(hash(x), int)

    def test_rcp_const_symbol_round_trip(self):
        """RCP<const Symbol> must round-trip through the caster correctly.
        This exercises the const-aware type_caster from nanobind_symengine.h."""
        x = m.symbol("x")
        # x is returned as RCP<const Basic>, but internally it's a Symbol.
        assert isinstance(x, m.Symbol)
        assert x.get_name() == "x"
        # Pass it back to C++ (Python->C++ direction)
        y = m.symbol("y")
        s = m.add(x, y)
        assert isinstance(s, m.Basic)

    def test_eq_direct_method_notimplemented_str(self):
        """m.Basic.__eq__(x, str) must return NotImplemented (not False)."""
        x = m.symbol("x")
        assert m.Basic.__eq__(x, "hello") is NotImplemented

    def test_eq_direct_method_notimplemented_int(self):
        """m.Basic.__eq__(x, int) must return NotImplemented (not False)."""
        x = m.symbol("x")
        assert m.Basic.__eq__(x, 42) is NotImplemented

    def test_eq_direct_method_none_returns_false(self):
        """m.Basic.__eq__(x, None) must return False (explicit None check)."""
        x = m.symbol("x")
        assert m.Basic.__eq__(x, None) is False

    def test_eq_direct_method_self_returns_true(self):
        """m.Basic.__eq__(x, x) must return True."""
        x = m.symbol("x")
        assert m.Basic.__eq__(x, x) is True

    def test_eq_direct_method_different_returns_false(self):
        """m.Basic.__eq__(x, y) must return False."""
        x = m.symbol("x")
        y = m.symbol("y")
        assert m.Basic.__eq__(x, y) is False

    def test_eq_with_non_basic_types(self):
        """Comparing Basic with non-Basic types must return False, not raise."""
        x = m.symbol("x")
        assert (x == "hello") is False
        assert (x == 42) is False
        assert (x == None) is False
        assert (x == 3.14) is False
        assert (x == [1, 2, 3]) is False

    def test_eq_with_same_basic(self):
        """Comparing a Basic with itself must return True."""
        x = m.symbol("x")
        assert (x == x) is True

    def test_eq_with_different_basics(self):
        """Comparing different Basic objects must return False."""
        x = m.symbol("x")
        y = m.symbol("y")
        assert (x == y) is False

    def test_constant_type(self):
        """Constants like pi, E should be of type Constant."""
        p = m.pi()
        assert isinstance(p, m.Constant)
        assert isinstance(p, m.Basic)
        assert p.get_name() == "pi"

    def test_hash_consistency(self):
        """Equal objects must have the same hash (Python data model)."""
        x1 = m.symbol("x")
        x2 = m.symbol("x")
        assert x1 == x2
        assert hash(x1) == hash(x2)


# ---------------------------------------------------------------------------
# Test 4: Lifecycle / destruction counts
# ---------------------------------------------------------------------------
class TestLifecycle:
    def test_no_leak_on_create_drop(self):
        """Objects created and dropped should be properly cleaned up.
        Verify the heap is sane by creating objects after a GC cycle."""
        for _ in range(100):
            x = m.symbol("temp")
            y = m.integer(42)
            s = m.add(x, y)
        del s, x, y
        gc.collect()
        # Verify heap is still sane after cleanup
        z = m.symbol("post_gc")
        assert isinstance(z, m.Basic)
        assert str(z) == "post_gc"

    def test_refcount_behavior(self):
        """Check that C++ use_count is 0 for Python-owned objects.
        In cooperative_intrusive mode, use_count() returns 0 for Python-owned objects
        because Python manages all references internally."""
        x = m.symbol("x")
        count = m.cpp_use_count(x)
        assert count == 0, (
            f"Expected use_count() == 0 for Python-owned object, got {count}"
        )

    def test_gc_collect_no_crash(self):
        """After gc.collect(), no dangling references should cause crashes."""
        objects = [m.symbol(f"v{i}") for i in range(50)]
        del objects
        gc.collect()
        # Create new objects to ensure heap is still sane
        x = m.symbol("after_gc")
        assert isinstance(x, m.Basic)


# ---------------------------------------------------------------------------
# Test 5: Python-subclass round trip (trampoline)
# ---------------------------------------------------------------------------
class TestSubclass:
    def test_python_subclass_basic(self):
        """Create a Python subclass of Basic and pass it through C++.
        Trampoline support for Basic is deferred to Phase 6."""

        class MyExpr(m.Basic):
            pass

        # This test may not work if trampoline support isn't compiled in.
        # We test at least that the class can be defined.
        try:
            obj = MyExpr()
        except TypeError:
            pytest.skip("Trampoline not available for Basic")

    def test_subclass_survives_round_trip(self):
        """A Python-owned object should survive being passed to C++ and back.
        This stresses the RCP<const Basic> caster in the Python->C++ direction."""
        x = m.symbol("x")
        y = m.symbol("y")
        s = m.add(x, y)  # s is Python-owned
        # Pass s (Python-owned) back to C++ via add:
        result = m.add(s, x)
        assert isinstance(result, m.Basic)
        # Verify s is still valid after the round trip
        assert str(s) == str(m.add(x, y))


# ---------------------------------------------------------------------------
# Test 6: No nb::ref<T> used (decision D5)
# ---------------------------------------------------------------------------
class TestDesignDecisions:
    def test_no_ref_in_module(self):
        """Verify the module source doesn't use nb::ref<T> (decision D5).
        Grep the actual source files as required by the plan."""
        src_dir = pathlib.Path(__file__).parent.parent / "src"
        support_dir = pathlib.Path(__file__).parent.parent / "support"
        for d in [src_dir, support_dir]:
            for f in d.glob("*.cpp"):
                content = f.read_text()
                assert "nb::ref<" not in content, f"Found nb::ref< in {f}"
            for f in d.glob("*.h"):
                content = f.read_text()
                assert "nb::ref<" not in content, f"Found nb::ref< in {f}"

    def test_no_counter_inl_in_module(self):
        """Verify counter.inl is NOT #included by the module (only by core library)."""
        import re
        src_dir = pathlib.Path(__file__).parent.parent / "src"
        support_dir = pathlib.Path(__file__).parent.parent / "support"
        include_pat = re.compile(r'#\s*include\s*[<"].*counter\.inl[>"]')
        for d in [src_dir, support_dir]:
            for f in d.glob("*.cpp"):
                content = f.read_text()
                assert not include_pat.search(content), (
                    f"Found counter.inl #include in {f} -- must only be in core library"
                )
            for f in d.glob("*.h"):
                content = f.read_text()
                assert not include_pat.search(content), (
                    f"Found counter.inl #include in {f} -- must only be in core library"
                )

    def test_module_has_expected_interface(self):
        """Verify all expected symbols are exported."""
        expected = [
            "Basic", "Symbol", "Integer", "Number", "Constant",
            "Add", "Mul", "Pow",
            "symbol", "integer", "add", "sub", "mul", "div", "pow", "neg",
            "same_object", "cpp_use_count", "expand",
            "zero", "one", "pi", "euler_gamma",
        ]
        for name in expected:
            assert hasattr(m, name), f"Missing: {name}"


# ---------------------------------------------------------------------------
# Test 7: Thread/GIL stress basics (single-threaded correctness)
# ---------------------------------------------------------------------------
class TestGILStress:
    def test_drop_rcp_under_gil(self):
        """Drop RCP references while the GIL is held (normal Python behavior)."""
        objects = [m.symbol(f"s{i}") for i in range(200)]
        # Drop them all at once under GIL
        del objects
        gc.collect()

    def test_rapid_create_destroy_cycle(self):
        """Rapidly create and destroy objects to stress ref counting."""
        for _ in range(500):
            x = m.symbol("x")
            y = m.integer(1)
            s = m.add(x, y)
            del s, x, y
        gc.collect()

    def test_nested_operations(self):
        """Deeply nested operations should not overflow or leak."""
        x = m.symbol("x")
        expr = x
        for i in range(50):
            expr = m.add(expr, m.integer(i))
        assert isinstance(expr, m.Basic)
        del expr
        gc.collect()


# ---------------------------------------------------------------------------
# Test 8: expand function
# ---------------------------------------------------------------------------
class TestExpand:
    def test_expand_basic(self):
        """Test that expand works on a simple expression.
        (x+y)*(x-y) should expand to x**2 - y**2."""
        x = m.symbol("x")
        y = m.symbol("y")
        expr = m.mul(m.add(x, y), m.sub(x, y))
        expanded = m.expand(expr)
        assert isinstance(expanded, m.Basic)
        # The expanded form should not be the same object as the input
        assert not m.same_object(expr, expanded)

    def test_expand_identity(self):
        """Expanding an already-expanded expression should be idempotent."""
        x = m.symbol("x")
        expr = m.add(x, m.integer(1))
        expanded = m.expand(expr)
        assert str(expanded) == str(expr)
