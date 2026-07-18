"""Smoke test: import nbsymengine and exercise basic operations."""

def test_import_and_basic():
    import nbsymengine as sx

    x = sx.symbol("x")
    assert isinstance(x, sx.Basic)
    two = sx.integer(2)
    assert sx.str(sx.add(x, two)) in ("x + 2", "2 + x")


def test_module_has_version():
    import nbsymengine as sx

    assert isinstance(sx.__version__, str)


def test_core_is_private_submodule():
    import nbsymengine

    assert hasattr(nbsymengine, "_core")


def test_all_exports_nonprivate():
    import nbsymengine as sx

    for name in sx.__all__:
        assert not name.startswith("_"), f"Private name in __all__: {name}"
        assert hasattr(sx, name)
