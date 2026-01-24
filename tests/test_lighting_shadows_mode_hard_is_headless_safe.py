from __future__ import annotations

from unittest.mock import MagicMock, patch

from engine.lighting import LightManager


def test_lighting_shadows_mode_hard_is_headless_safe(mock_arcade_lighting) -> None:
    window = MagicMock()
    window.width = 800
    window.height = 600

    lm = LightManager(window, enabled=True)
    lm.available = True
    lm.enabled = True
    lm._layer = MagicMock()
    lm.shadows_mode = "hard"
    lm._static_configs = [{"x": 100, "y": 100, "radius": 50, "enabled": True}]
    lm._static_occluders = [{"id": "r", "type": "rect", "x": 10, "y": 10, "width": 10, "height": 10}]

    with patch("arcade.get_window", side_effect=RuntimeError("no window")):
        lm.end()

