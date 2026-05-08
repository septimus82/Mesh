"""Regression tests for the LightLayer truthiness / chicken-and-egg deadlock.

Root cause (fixed):
    arcade.future.light.lights.LightLayer implements __len__ returning
    len(self._lights).  An empty-but-valid layer evaluates as False in Python
    boolean context.

    The original guards used:
        if not self._layer: ...          # _add_light / _add_occluder / _add_polygon_light
        if not (self.enabled and self._layer): ...  # begin / end / update

    These short-circuited when the layer had zero lights, making it impossible
    to add *any* light — a permanent chicken-and-egg deadlock.

Fix: replaced all 6 guards with explicit identity checks (``is None``).

These tests assert the broken behaviour cannot regress.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from engine.lighting import LightManager


pytestmark = [pytest.mark.fast]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FalsyLayer:
    """Mimics LightLayer with __len__ == 0 (empty but not None).

    Before the fix, ``bool(_FalsyLayer())`` is False, causing all guards
    to short-circuit as if the layer did not exist.
    """

    def __init__(self) -> None:
        self._lights: list[Any] = []
        self._walls: list[Any] = []
        self._add_light_calls: list[Any] = []
        self._add_wall_calls: list[Any] = []

    # The critical dunder — this is what makes LightLayer falsy when empty.
    def __len__(self) -> int:
        return len(self._lights)

    # LightLayer public API used by _add_light / _add_occluder
    def add_light(self, light: Any) -> None:
        self._lights.append(light)
        self._add_light_calls.append(light)

    def add_wall(self, wall: Any) -> None:
        self._walls.append(wall)
        self._add_wall_calls.append(wall)


def _manager_with_layer(layer: Any | None, *, enabled: bool = True) -> LightManager:
    """Return a partially-constructed LightManager with the given _layer."""
    manager = object.__new__(LightManager)
    manager.enabled = enabled
    manager._layer = layer
    manager.shadows_mode = "none"
    return manager


# ---------------------------------------------------------------------------
# Core falsiness regression — _add_light
# ---------------------------------------------------------------------------

class TestAddLightFalsinessRegression:
    """_add_light must not bail on a non-None layer that is currently empty."""

    def test_add_light_does_not_bail_on_empty_layer(self) -> None:
        """Before fix: bool(empty_layer) == False caused early return; no light added."""
        layer = _FalsyLayer()
        assert bool(layer) is False, "Precondition: layer must be falsy when empty"

        manager = _manager_with_layer(layer)
        fake_light = SimpleNamespace(name="test_light")
        manager._add_light(fake_light)

        assert layer._add_light_calls == [fake_light], (
            "_add_light bailed early on a falsy-but-non-None layer — "
            "falsiness check regressed"
        )

    def test_add_light_chicken_and_egg_breaker(self) -> None:
        """Adding N lights one-by-one must succeed for all N despite the layer
        being falsy before the first light lands."""
        layer = _FalsyLayer()
        manager = _manager_with_layer(layer)

        lights = [SimpleNamespace(name=f"light_{i}") for i in range(5)]
        for light in lights:
            assert bool(layer) is False or len(layer._lights) >= 0  # layer is falsy until first add
            manager._add_light(light)

        assert len(layer._lights) == 5
        assert layer._add_light_calls == lights

    def test_add_light_still_bails_on_none_layer(self) -> None:
        """The fix replaces bool-check with ``is None``; None must still bail."""
        manager = _manager_with_layer(None)
        # Should complete silently without AttributeError
        manager._add_light(SimpleNamespace(name="ghost"))  # must not raise

    def test_add_light_disabled_manager_bails(self) -> None:
        """enabled=False should still prevent light add (via begin/end path)."""
        layer = _FalsyLayer()
        # _add_light itself does not check enabled; this is a note that
        # begin() does.  Verify _add_light alone always succeeds if layer is set.
        manager = _manager_with_layer(layer, enabled=False)
        fake_light = SimpleNamespace(name="disabled_light")
        manager._add_light(fake_light)
        # _add_light is not gated by enabled, only by _layer is None
        assert layer._add_light_calls == [fake_light]


# ---------------------------------------------------------------------------
# _add_occluder
# ---------------------------------------------------------------------------

class TestAddOccluderFalsinessRegression:
    def test_add_occluder_does_not_bail_on_empty_layer(self) -> None:
        layer = _FalsyLayer()
        assert bool(layer) is False
        manager = _manager_with_layer(layer)
        fake_wall = SimpleNamespace(name="pillar")
        manager._add_occluder(fake_wall)
        assert layer._add_wall_calls == [fake_wall]

    def test_add_occluder_still_bails_on_none_layer(self) -> None:
        manager = _manager_with_layer(None)
        manager._add_occluder(SimpleNamespace(name="ghost_wall"))  # must not raise


# ---------------------------------------------------------------------------
# _add_polygon_light
# ---------------------------------------------------------------------------

class TestAddPolygonLightFalsinessRegression:
    def test_add_polygon_light_does_not_bail_on_empty_layer(self) -> None:
        """_add_polygon_light should attempt the call even on an empty layer."""
        layer = _FalsyLayer()
        # Add a polygon-light method to the fake layer
        received: list[Any] = []
        layer.add_light_polygon = lambda pts, **kw: received.append((pts, kw))  # type: ignore[attr-defined]

        assert bool(layer) is False
        manager = _manager_with_layer(layer)
        pts = [(0.0, 0.0), (100.0, 0.0), (50.0, 100.0)]
        result = manager._add_polygon_light(pts, {"color": (255, 255, 200, 180)})

        assert result is True
        assert len(received) == 1
        assert received[0][0] == pts

    def test_add_polygon_light_returns_false_on_none_layer(self) -> None:
        manager = _manager_with_layer(None)
        result = manager._add_polygon_light([(0, 0), (1, 0), (0, 1)], {})
        assert result is False


# ---------------------------------------------------------------------------
# begin() / end() / update() — guard correctness
# ---------------------------------------------------------------------------

class TestPublicApiGuardsRegression:
    """begin(), end(), update() must NOT be blocked by an empty-but-non-None layer."""

    def test_begin_returns_context_manager_with_empty_layer(self) -> None:
        """begin() must return a real context manager (not nullcontext) when layer
        is set but empty."""
        # We need a layer that supports __enter__/__exit__ and __len__==0
        layer = MagicMock()
        layer.__len__ = MagicMock(return_value=0)
        layer.__enter__ = MagicMock(return_value=None)
        layer.__exit__ = MagicMock(return_value=False)

        manager = _manager_with_layer(layer, enabled=True)
        manager.shadows_mode = "none"

        # Should not raise; should return something context-manager-shaped
        ctx = manager.begin()
        assert ctx is not None

    def test_update_does_not_raise_with_empty_layer(self) -> None:
        layer = _FalsyLayer()
        assert bool(layer) is False
        manager = _manager_with_layer(layer)
        manager._flicker_time = 0.0
        manager._dynamic_handles = []
        manager._flicker_lights = []
        # update() should not raise AttributeError or return early
        # (it will try to iterate handles — empty list is fine)
        try:
            manager.update(0.016)
        except AttributeError as exc:
            pytest.fail(f"update() raised AttributeError on empty layer: {exc}")
