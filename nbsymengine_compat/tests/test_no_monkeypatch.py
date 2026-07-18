"""Verify that importing nbsymengine_compat does NOT modify nbsymengine._core.

See docs/plans/11-NO-MORE-MONKEYPATCHING.md -- Section 5A.
"""
from __future__ import annotations


def _snapshot_core_types():
    """Take a snapshot of all public attributes on _core types before import."""
    import nbsymengine._core as core
    snap = {}
    for name in dir(core):
        obj = getattr(core, name)
        if isinstance(obj, type) and issubclass(obj, core.Basic):
            attrs = {a: getattr(obj, a, None) for a in dir(obj) if not a.startswith('__')}
            snap[name] = sorted(attrs.keys())
    return snap


def test_no_monkeypatch():
    """Ensure importing nbsymengine_compat does not modify _core types.

    Approach:
    1. Snapshot _core type attributes before compat import.
    2. Import nbsymengine_compat.
    3. Assert no new attributes appeared on any _core type.
    """
    # Step 1: Snapshot before import
    snap_before = _snapshot_core_types()

    # Step 2: Import the compat layer
    from nbsymengine_compat import symengine_py_compat  # noqa: F401

    # Step 3: Snapshot after import
    snap_after = _snapshot_core_types()

    # Step 4: Compare
    for cls_name, attrs_before in snap_before.items():
        attrs_after = snap_after.get(cls_name, [])
        new_attrs = set(attrs_after) - set(attrs_before)
        assert not new_attrs, (
            f"_core.{cls_name} gained new attributes after compat import: "
            f"{sorted(new_attrs)}"
        )

    # Ensure all original classes still exist
    missing = set(snap_before.keys()) - set(snap_after.keys())
    assert not missing, f"_core types lost: {sorted(missing)}"


def test_no_direct_patching_of_core_methods():
    """Ensure specific critical methods are not patched on _core.Basic."""
    import nbsymengine._core as core

    from nbsymengine_compat import symengine_py_compat  # noqa: F401

    # __reduce_ex__ must NOT be set on _core.Basic
    assert '__reduce_ex__' not in core.Basic.__dict__, (
        "__reduce_ex__ must not be set on _core.Basic"
    )

    # __reduce__ must NOT be set on _core.DenseMatrix (unless native)
    assert '__reduce__' not in core.DenseMatrix.__dict__, (
        "__reduce__ must not be set on _core.DenseMatrix"
    )

    # Arithmetic dunders should be native (from C++), not Python overrides
    for dunder in ('__add__', '__mul__', '__sub__', '__truediv__', '__pow__',
                   '__eq__', '__ne__', '__lt__', '__le__', '__gt__', '__ge__',
                   '__floordiv__', '__mod__'):
        attr = getattr(core.Basic, dunder, None)
        # Native nanobind methods are not plain Python functions.
        # We check that the attribute is NOT a Python function from our compat layer.
        if attr is not None and callable(attr):
            mod = getattr(attr, '__module__', '')
            assert 'nbsymengine_compat' not in str(mod), (
                f"_core.Basic.{dunder} was patched by nbsymengine_compat ({mod})"
            )
