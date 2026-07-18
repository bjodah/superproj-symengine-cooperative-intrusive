"""Phase 0 behavior baseline for the common nbsymengine surface."""

import nbsymengine as se


def test_shared_api_smoke() -> None:
    x = se.symbol("phase0_x")
    two = se.integer(2)

    assert str(x) == "phase0_x"
    assert str(two) == "2"
    assert str(se.zero()) == "0"
    assert str(se.one()) == "1"
    assert str(se.pi()) == "pi"
    assert str(se.add(x, two)) == "2 + phase0_x"
    assert str(se.sub(x, two)) == "-2 + phase0_x"
    assert str(se.mul(x, two)) == "2*phase0_x"
    assert str(se.div(x, two)) == "(1/2)*phase0_x"
    assert str(se.pow(x, two)) == "phase0_x**2"
    assert str(se.neg(x)) == "-phase0_x"
    assert x == se.symbol("phase0_x")
    assert x != se.symbol("phase0_y")
