"""Tests that singleton access does not trigger nanobind leak reports."""

import os
import subprocess
import sys
import unittest


class TestSingletonLeaks(unittest.TestCase):
    """Verify no nanobind leak messages when accessing singletons."""

    def _run_with_singletons(self, code: str) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        executable = env.get("NBSYMENGINE_SUBPROCESS_PYTHON", sys.executable)
        return subprocess.run(
            [executable, "-c", code],
            capture_output=True,
            text=True,
            env=env,
        )

    def test_generated_ext_no_leak(self) -> None:
        code = (
            "from nbsymengine import _core as m\n"
            "m.zero(); m.one(); m.pi(); m.e(); m.euler_gamma()\n"
            "m.reals(); m.integers(); m.rationals(); m.complexes()\n"
            "m.naturals(); m.naturals0(); m.emptyset(); m.universalset()\n"
        )
        result = self._run_with_singletons(code)
        self.assertEqual(result.returncode, 0, f"Process failed:\n{result.stderr}")
        self.assertNotIn("nanobind: leaked", result.stderr,
                         "nanobind reported leaked singleton instances")
        self.assertNotIn("reference counting issue", result.stderr,
                         "nanobind reported a reference counting issue")

    def test_manual_ext_no_leak(self) -> None:
        code = (
            "import symengine_manual_ext as m\n"
            "m.zero(); m.one(); m.pi(); m.euler_gamma()\n"
            "m.reals(); m.integers(); m.rationals(); m.complexes()\n"
            "m.naturals(); m.naturals0(); m.emptyset(); m.universalset()\n"
        )
        result = self._run_with_singletons(code)
        self.assertEqual(result.returncode, 0, f"Process failed:\n{result.stderr}")
        self.assertNotIn("nanobind: leaked", result.stderr,
                         "nanobind reported leaked singleton instances")
        self.assertNotIn("reference counting issue", result.stderr,
                         "nanobind reported a reference counting issue")

    def test_repeated_singleton_access_no_leak(self) -> None:
        """Multiple calls to the same singleton should not accumulate leaks."""
        code = (
            "from nbsymengine import _core as m\n"
            "for _ in range(100):\n"
            "    m.zero(); m.one(); m.pi()\n"
            "for _ in range(100):\n"
            "    m.reals(); m.integers(); m.emptyset()\n"
        )
        result = self._run_with_singletons(code)
        self.assertEqual(result.returncode, 0, f"Process failed:\n{result.stderr}")
        self.assertNotIn("nanobind: leaked", result.stderr,
                         "nanobind reported leaked singleton instances")

    def test_generated_ext_identity(self) -> None:
        """Singleton accessors must return the same Python object (is check)."""
        code = (
            "from nbsymengine import _core as m\n"
            "assert m.pi() is m.pi(), 'pi identity failed'\n"
            "assert m.zero() is m.zero(), 'zero identity failed'\n"
            "assert m.one() is m.one(), 'one identity failed'\n"
            "assert m.e() is m.e(), 'e identity failed'\n"
            "assert m.euler_gamma() is m.euler_gamma(), 'euler_gamma identity failed'\n"
            "assert m.reals() is m.reals(), 'reals identity failed'\n"
            "assert m.integers() is m.integers(), 'integers identity failed'\n"
            "assert m.rationals() is m.rationals(), 'rationals identity failed'\n"
            "assert m.complexes() is m.complexes(), 'complexes identity failed'\n"
            "assert m.naturals() is m.naturals(), 'naturals identity failed'\n"
            "assert m.naturals0() is m.naturals0(), 'naturals0 identity failed'\n"
            "assert m.emptyset() is m.emptyset(), 'emptyset identity failed'\n"
            "assert m.universalset() is m.universalset(), 'universalset identity failed'\n"
        )
        result = self._run_with_singletons(code)
        self.assertEqual(result.returncode, 0, f"Identity test failed:\n{result.stderr}")
        self.assertNotIn("nanobind: leaked", result.stderr,
                         "nanobind reported leaked singleton instances")
        self.assertNotIn("reference counting issue", result.stderr,
                         "nanobind reported a reference counting issue")

    def test_manual_ext_identity(self) -> None:
        """Singleton accessors must return the same Python object (is check)."""
        code = (
            "import symengine_manual_ext as m\n"
            "assert m.pi() is m.pi(), 'pi identity failed'\n"
            "assert m.zero() is m.zero(), 'zero identity failed'\n"
            "assert m.one() is m.one(), 'one identity failed'\n"
            "assert m.euler_gamma() is m.euler_gamma(), 'euler_gamma identity failed'\n"
            "assert m.reals() is m.reals(), 'reals identity failed'\n"
            "assert m.integers() is m.integers(), 'integers identity failed'\n"
            "assert m.rationals() is m.rationals(), 'rationals identity failed'\n"
            "assert m.complexes() is m.complexes(), 'complexes identity failed'\n"
            "assert m.naturals() is m.naturals(), 'naturals identity failed'\n"
            "assert m.naturals0() is m.naturals0(), 'naturals0 identity failed'\n"
            "assert m.emptyset() is m.emptyset(), 'emptyset identity failed'\n"
            "assert m.universalset() is m.universalset(), 'universalset identity failed'\n"
        )
        result = self._run_with_singletons(code)
        self.assertEqual(result.returncode, 0, f"Identity test failed:\n{result.stderr}")
        self.assertNotIn("nanobind: leaked", result.stderr,
                         "nanobind reported leaked singleton instances")
        self.assertNotIn("reference counting issue", result.stderr,
                         "nanobind reported a reference counting issue")

    def test_identity_and_leak_combined(self) -> None:
        """Exercise identity + access + shutdown in a single subprocess."""
        code = (
            "from nbsymengine import _core as m\n"
            "# Exercise identity\n"
            "assert m.pi() is m.pi()\n"
            "assert m.zero() is m.zero()\n"
            "assert m.reals() is m.reals()\n"
            "# Exercise repeated access\n"
            "for _ in range(50):\n"
            "    m.pi(); m.zero(); m.reals(); m.emptyset()\n"
            "# Keep references alive until shutdown\n"
            "a = m.pi(); b = m.reals()\n"
        )
        result = self._run_with_singletons(code)
        self.assertEqual(result.returncode, 0, f"Combined test failed:\n{result.stderr}")
        self.assertNotIn("nanobind: leaked", result.stderr,
                         "nanobind reported leaked singleton instances")
        self.assertNotIn("reference counting issue", result.stderr,
                         "nanobind reported a reference counting issue")


if __name__ == "__main__":
    unittest.main()
