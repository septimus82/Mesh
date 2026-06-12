from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from engine.lighting import LightManager

pytestmark = [pytest.mark.fast]


def test_hard_shadows_composite_draw_signature_fallback_succeeds() -> None:
    class _Fbo:
        def use(self) -> None:
            return None

        def clear(self, *_args: object) -> None:
            return None

    class _Layer:
        diffuse_texture = object()

        def __init__(self) -> None:
            self.calls = 0

        # Intentionally narrow signature: rejects target= and position= kwargs.
        def draw(self, ambient_color=None):  # noqa: ANN001
            self.calls += 1
            return None

    targets = SimpleNamespace(
        light_fbo=_Fbo(),
        mask_fbo=_Fbo(),
        mask_tex=object(),
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
    manager._last_lighting_stats = {}

    with patch("engine.lighting.hard_shadows_backend.ensure_render_targets", return_value=targets), patch(
        "engine.lighting.shadows.render_shadow_mask", return_value=targets.mask_tex
    ), patch(
        "engine.lighting.hard_shadows_backend.composite_to_window", return_value=True
    ), patch.object(
        LightManager,
        "_select_shadow_light",
        return_value=("dynamic", (0.0, 0.0), 100.0, object()),
    ):
        ok = LightManager._end_hard_shadows_composite(manager)

    assert ok is True
    assert manager._layer.calls >= 1
    stats = manager.get_lighting_stats()
    assert stats.get("composite_ok") is True
