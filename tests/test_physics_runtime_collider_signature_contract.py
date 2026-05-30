from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.physics_runtime import _collider_signature

pytestmark = [pytest.mark.fast]


def test_collider_signature_same_bounds_is_deterministic() -> None:
    s = SimpleNamespace(left=0.0, right=2.0, bottom=-1.0, top=1.0)
    assert _collider_signature(s) == _collider_signature(s)


def test_collider_signature_distinct_right_bound_differs() -> None:
    s1 = SimpleNamespace(left=0.0, right=2.0, bottom=-1.0, top=1.0)
    s2 = SimpleNamespace(left=0.0, right=2.25, bottom=-1.0, top=1.0)  # shifted by one quantum (0.25 px)
    assert _collider_signature(s1) != _collider_signature(s2)


def test_collider_signature_fallback_to_center_wh_matches_explicit_bounds() -> None:
    explicit = SimpleNamespace(left=-1.0, right=1.0, bottom=-1.0, top=1.0)
    implicit = SimpleNamespace(
        left=None, right=None, bottom=None, top=None,
        center_x=0.0, center_y=0.0, width=2.0, height=2.0,
    )
    assert _collider_signature(explicit) == _collider_signature(implicit)


def test_collider_signature_missing_all_geometry_returns_zero() -> None:
    s = SimpleNamespace()
    assert _collider_signature(s) == 0
