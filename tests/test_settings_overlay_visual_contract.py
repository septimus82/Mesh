from __future__ import annotations

import types
from pathlib import Path

import pytest

from engine.ui import SettingsOverlay
from engine.ui_overlays import settings_overlay as overlay_module
from tests._typing import as_any

pytestmark = [pytest.mark.fast]


def _make_overlay(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SettingsOverlay:
    settings_path = tmp_path / "settings_visual_contract.json"
    monkeypatch.setenv("MESH_SETTINGS_PATH", str(settings_path))
    window = types.SimpleNamespace(
        width=1024,
        height=768,
        paused=False,
        engine_config=types.SimpleNamespace(
            input_bindings={},
            master_volume=0.61,
            input={"rumble_enabled": True, "rumble_strength": 0.37},
        ),
        input_controller=types.SimpleNamespace(manager=None),
    )
    overlay = SettingsOverlay(as_any(window))
    overlay.open()
    return overlay


def _capture_draw(
    monkeypatch: pytest.MonkeyPatch,
    overlay: SettingsOverlay,
) -> tuple[list[tuple[str, tuple[object, ...]]], list[str]]:
    events: list[tuple[str, tuple[object, ...]]] = []
    texts: list[str] = []
    monkeypatch.setattr(
        overlay_module,
        "_draw_settings_cover",
        lambda width, height: events.append(("cover", (float(width), float(height), (8, 10, 14, 255)))),
    )
    monkeypatch.setattr(
        overlay_module,
        "_draw_rectangle_filled",
        lambda center_x, center_y, width, height, color: events.append(
            ("fill", (float(center_x), float(center_y), float(width), float(height), color))
        ),
    )
    monkeypatch.setattr(overlay_module, "_draw_tb_rectangle_outline", lambda *args, **kwargs: None)
    monkeypatch.setattr(overlay_module, "draw_text_cached", lambda text, *args, **kwargs: texts.append(str(text)))

    overlay.draw()
    return events, texts


def test_settings_overlay_draws_opaque_cover_before_panel(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    overlay = _make_overlay(monkeypatch, tmp_path)
    panel = overlay._panel_rect()

    events, _texts = _capture_draw(monkeypatch, overlay)

    assert events[0] == ("cover", (1024.0, 768.0, (8, 10, 14, 255)))
    assert events[1][0] == "fill"
    assert events[1][1][:4] == pytest.approx((panel.center_x, panel.center_y, panel.width, panel.height))
    assert events[1][1][4] == (0, 0, 0, 210)


def test_settings_overlay_draws_mesh_settings_title(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    overlay = _make_overlay(monkeypatch, tmp_path)

    _fills, texts = _capture_draw(monkeypatch, overlay)

    assert "MESH" in texts
    assert "Settings" in texts


def test_settings_overlay_visual_title_does_not_render_diagnostic_rows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    overlay = _make_overlay(monkeypatch, tmp_path)

    _fills, texts = _capture_draw(monkeypatch, overlay)

    assert all(not text.startswith("Settings (") for text in texts)
    assert all(not text.startswith("path: ") for text in texts)
