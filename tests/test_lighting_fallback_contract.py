from unittest.mock import patch

import pytest

import engine.lighting as lighting
from engine.lighting import LightManager


pytestmark = [pytest.mark.fast]


class _Window:
    show_debug = False


def test_draw_debug_geometry_bad_shape_uses_lgin012_once() -> None:
    manager = object.__new__(LightManager)
    manager.window = _Window()
    manager._static_occluders = []
    manager._select_shadow_light_params = lambda: ("bad", {}, object())

    lighting._SWALLOW_ONCE_TAGS.clear()
    try:
        with patch("engine.lighting.debug.draw_occluder_rects", lambda *_a, **_k: None), patch(
            "engine.lighting.debug.draw_shadow_polygons", lambda *_a, **_k: None
        ), patch("engine.lighting._occluder_utils.build_rect_occluders", return_value=[]):
            manager._draw_debug_geometry()
            manager._draw_debug_geometry()
        assert lighting._SWALLOW_ONCE_TAGS == {"LGIN-012"}
    finally:
        lighting._SWALLOW_ONCE_TAGS.clear()


def test_create_light_bad_radius_uses_lgin019_once_and_returns_none() -> None:
    manager = object.__new__(LightManager)

    lighting._SWALLOW_ONCE_TAGS.clear()
    try:
        assert manager._create_light(0.0, 0.0, "bad", (255, 255, 255, 255), "none") is None
        assert manager._create_light(0.0, 0.0, "bad", (255, 255, 255, 255), "none") is None
        assert lighting._SWALLOW_ONCE_TAGS == {"LGIN-019"}
    finally:
        lighting._SWALLOW_ONCE_TAGS.clear()


def test_normalize_color_invalid_hex_logs_lgin020_and_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = object.__new__(LightManager)
    seen: list[tuple[str, str, str, bool]] = []

    def _capture(tag: str, where: str, purpose: str, *, once: bool = False) -> None:
        seen.append((tag, where, purpose, once))

    monkeypatch.setattr(lighting, "_log_swallow", _capture)

    assert manager._normalize_color("#zzzzzz") == (255, 255, 255, 255)
    assert seen == [
        (
            "LGIN-020",
            "engine.lighting.__init__.LightManager._normalize_color",
            "normalize_hex_color",
            False,
        )
    ]
