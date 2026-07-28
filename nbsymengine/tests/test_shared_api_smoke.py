"""Bootstrap baseline for nbsymengine.

The arithmetic, constant and string expectations that used to be repeated here
now live in ``binding-spec/test-cases.yaml`` and are rendered into
``test_shared_cases.py`` for every wrapper.  What remains is what that shared
schema cannot express: the module imports, the hand-written factory functions
work, and structural (in)equality holds.
"""

import nbsymengine as se


def test_manual_factories_and_equality() -> None:
    x = se.symbol("phase0_x")
    two = se.integer(2)

    assert str(x) == "phase0_x"
    assert str(two) == "2"
    assert x == se.symbol("phase0_x")
    assert x != se.symbol("phase0_y")
