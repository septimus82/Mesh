from __future__ import annotations

import pytest

import engine.scene_runtime.authoring.entity_ops as entity_ops


pytestmark = [pytest.mark.fast]


def test_entity_ops_geometry_helper_symbols_exist() -> None:
    for name in ("_entity_bounds", "_anchor_value", "_snap_value"):
        assert hasattr(entity_ops, name)
        assert callable(getattr(entity_ops, name))


def test_entity_bounds_defaults_and_custom_sizes() -> None:
    cx, cy, hw, hh = entity_ops._entity_bounds({"x": 10, "y": -5}) or (0.0, 0.0, 0.0, 0.0)
    assert (cx, cy, hw, hh) == (10.0, -5.0, 16.0, 16.0)

    bounds = entity_ops._entity_bounds({"x": 1, "y": 2, "width": 40, "height": 20})
    assert bounds == (1.0, 2.0, 20.0, 10.0)

    bounds_alt = entity_ops._entity_bounds({"x": 1, "y": 2, "w": 18, "h": 14})
    assert bounds_alt == (1.0, 2.0, 9.0, 7.0)


def test_entity_bounds_invalid_cases() -> None:
    assert entity_ops._entity_bounds({"y": 5}) is None
    assert entity_ops._entity_bounds({"x": "bad", "y": 5}) is None
    assert entity_ops._entity_bounds({"x": 0, "y": 0, "width": "bad", "height": []}) == (0.0, 0.0, 16.0, 16.0)


def test_anchor_value_modes() -> None:
    assert entity_ops._anchor_value(10.0, 20.0, 3.0, 4.0, "x", "left") == pytest.approx(7.0)
    assert entity_ops._anchor_value(10.0, 20.0, 3.0, 4.0, "x", "right") == pytest.approx(13.0)
    assert entity_ops._anchor_value(10.0, 20.0, 3.0, 4.0, "x", "center") == pytest.approx(10.0)
    assert entity_ops._anchor_value(10.0, 20.0, 3.0, 4.0, "y", "top") == pytest.approx(24.0)
    assert entity_ops._anchor_value(10.0, 20.0, 3.0, 4.0, "y", "bottom") == pytest.approx(16.0)
    assert entity_ops._anchor_value(10.0, 20.0, 3.0, 4.0, "y", "middle") == pytest.approx(20.0)


def test_snap_value_modes_and_ties() -> None:
    assert entity_ops._snap_value(7.1, 4, "nearest") == pytest.approx(8.0)
    assert entity_ops._snap_value(6.0, 4, "nearest") == pytest.approx(8.0)
    assert entity_ops._snap_value(-6.0, 4, "nearest") == pytest.approx(-8.0)
    assert entity_ops._snap_value(7.9, 4, "floor") == pytest.approx(4.0)
    assert entity_ops._snap_value(-7.9, 4, "floor") == pytest.approx(-8.0)
    assert entity_ops._snap_value(7.1, 4, "ceil") == pytest.approx(8.0)
    assert entity_ops._snap_value(-7.1, 4, "ceil") == pytest.approx(-4.0)
