"""Test utilities for the legacy symengine compatibility shim.

Provides ``raises()`` as both a callable and a context manager, matching
the signature expected by the legacy test suite.
"""
from contextlib import contextmanager


@contextmanager
def _raises_cm(expected):
    try:
        yield
    except expected:
        return
    raise AssertionError("DID NOT RAISE")


def raises(expected, code=None):
    """Assert that *code* raises *expected*.

    Can be used as a callable::

        raises(ValueError, lambda: int("abc"))

    Or as a context manager::

        with raises(ValueError):
            int("abc")
    """
    if code is None:
        return _raises_cm(expected)
    try:
        code()
    except expected:
        return
    raise AssertionError("DID NOT RAISE")
