"""Phase 0 ownership/identity baseline, intentionally separate from smoke."""

import nbsymengine as se


def test_singletons_and_canonical_results_reuse_python_identity() -> None:
    assert se.zero() is se.zero()
    assert se.one() is se.one()
    assert se.pi() is se.pi()

    x = se.symbol("phase0_identity_x")
    assert se.add(x, se.zero()) is x
