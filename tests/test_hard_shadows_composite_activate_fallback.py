from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from engine.lighting import LightManager

pytestmark = [pytest.mark.fast]


def test_hard_shadows_composite_uses_activate_fallback_for_fbos() -> None:
    sentinel_mask = object()
    events: list[str] = []

    class _Activation:
        def __init__(self, name: str) -> None:
            self._name = name

        def __enter__(self):  # noqa: ANN204
            events.append(f"{self._name}.enter")
            return self

        def __exit__(self, *_args: object) -> bool:
            events.append(f"{self._name}.exit")
            return False

    class _FboActivate:
        def __init__(self, name: str) -> None:
            self._name = name

        def activate(self):  # noqa: ANN201
            events.append(f"{self._name}.activate")
            return _Activation(self._name)

        def clear(self, *_args: object) -> None:
            events.append(f"{self._name}.clear")

    class _Layer:
        diffuse_texture = object()

        def draw(self, **_kwargs):  # noqa: ANN003
            return None

    targets = SimpleNamespace(
        light_fbo=_FboActivate("light"),
        mask_fbo=_FboActivate("mask"),
        mask_tex=sentinel_mask,
        light_tex=object(),
    )

    manager = object.__new__(LightManager)
    manager.window = SimpleNamespace(width=800, height=600, camera=None, ctx=None, scene_controller=None)
    manager._layer = _Layer()
    manager.enabled = True
    manager.ambient_color = (10, 10, 10, 255)
    manager._static_occluders = [{"id": "o1", "type": "rect", "x": 0, "y": 0, "width": 10, "height": 10}]
    manager._dynamic_handles = []
    manager._static_lights = []
    manager._static_configs = []
    manager.shadows_mode = "hard"

    with patch("engine.lighting.hard_shadows_backend.ensure_render_targets", return_value=targets), patch(
        "engine.lighting.shadows.render_shadow_mask", return_value=None
    ), patch(
        "engine.lighting.hard_shadows_backend.composite_to_window",
        side_effect=lambda _window, *, diffuse_tex, light_tex, mask_tex, ambient_color: mask_tex is sentinel_mask,
    ), patch.object(
        LightManager,
        "_select_shadow_light",
        return_value=("dynamic", (0.0, 0.0), 100.0, object()),
    ):
        ok = LightManager._end_hard_shadows_composite(manager)

    assert ok is True
    assert "light.activate" in events
    assert "light.enter" in events
    assert "light.exit" in events
    assert "mask.activate" in events
    assert "mask.enter" in events
    assert "mask.exit" in events
