from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from engine.lighting import LightManager


def test_hard_shadows_composite_never_passes_none_mask() -> None:
    sentinel_mask = object()

    class _Layer:
        diffuse_texture = object()
        light_texture = object()

        def draw(self, **_kwargs):  # noqa: ANN003
            return None

    class _Fbo:
        def use(self) -> None:
            return None

        def clear(self) -> None:
            return None

    targets = SimpleNamespace(light_fbo=_Fbo(), mask_fbo=_Fbo(), mask_tex=sentinel_mask)
    targets.light_tex = object()

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
        stats = manager.get_lighting_stats()
        # render_shadow_mask returned None, but we must still run composite using the preallocated mask.
        assert stats.get("composite_ok") is True
        assert stats.get("mask_fallback_used") is True
