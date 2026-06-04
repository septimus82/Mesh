from __future__ import annotations

import types
from pathlib import Path

import pytest

from engine.ui import SettingsOverlay
from engine.ui_overlays import settings_overlay as overlay_module
from engine.ui_overlays.widgets import DrawInstruction, LayoutResult, Rect
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
    monkeypatch.setattr(
        overlay_module,
        "_draw_tb_rectangle_outline",
        lambda left, right, top, bottom, color, border_width=1.0: events.append(
            ("outline", (float(left), float(right), float(top), float(bottom), color, float(border_width)))
        ),
    )
    monkeypatch.setattr(
        overlay_module,
        "draw_text_cached",
        lambda text, *args, **kwargs: (
            texts.append(str(text)),
            events.append(("text", (str(text), kwargs.get("color")))),
        ),
    )

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


def test_settings_overlay_widget_panel_tokens_use_menu_palette(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    overlay = _make_overlay(monkeypatch, tmp_path)
    panel = overlay._panel_rect()
    themed_rects = {
        (
            overlay._audio_panel_bounds(panel).center_x,
            overlay._audio_panel_bounds(panel).center_y,
            overlay._audio_panel_bounds(panel).width,
            overlay._audio_panel_bounds(panel).height,
        ),
        (
            overlay._input_panel_bounds(panel).center_x,
            overlay._input_panel_bounds(panel).center_y,
            overlay._input_panel_bounds(panel).width,
            overlay._input_panel_bounds(panel).height,
        ),
        (
            overlay._keybinds_panel_bounds(panel).center_x,
            overlay._keybinds_panel_bounds(panel).center_y,
            overlay._keybinds_panel_bounds(panel).width,
            overlay._keybinds_panel_bounds(panel).height,
        ),
    }

    events, _texts = _capture_draw(monkeypatch, overlay)
    panel_fill_colors = [
        payload[4]
        for kind, payload in events
        if kind == "fill" and payload[:4] in themed_rects
    ]
    panel_outline_colors = [
        payload[4]
        for kind, payload in events
        if kind == "outline" and payload[4] == (72, 180, 205, 190)
    ]

    assert panel_fill_colors == [(24, 32, 42, 230), (24, 32, 42, 230), (24, 32, 42, 230)]
    assert (22, 24, 30, 180) not in panel_fill_colors
    assert len(panel_outline_colors) >= 3


def test_settings_overlay_sliders_use_menu_accent_colors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    overlay = _make_overlay(monkeypatch, tmp_path)

    events, _texts = _capture_draw(monkeypatch, overlay)
    fill_colors = [payload[4] for kind, payload in events if kind == "fill"]

    assert (42, 56, 66, 230) in fill_colors
    assert (116, 241, 218, 230) in fill_colors
    assert (232, 248, 246, 255) in fill_colors
    assert (70, 70, 80, 220) not in fill_colors
    assert (120, 180, 255, 230) not in fill_colors
    assert (220, 220, 230, 230) not in fill_colors


def test_settings_overlay_capture_accent_is_visual_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    overlay = _make_overlay(monkeypatch, tmp_path)
    overlay.on_key_press(overlay_module.optional_arcade.arcade.key.ENTER, 0)
    selected_before = overlay._selection_index
    capture_before = overlay._capture_action

    events, _texts = _capture_draw(monkeypatch, overlay)
    text_events = [payload for kind, payload in events if kind == "text"]

    assert any("[press a key...]" in payload[0] and payload[1] == (255, 220, 120, 255) for payload in text_events)
    assert overlay._selection_index == selected_before
    assert overlay._capture_action == capture_before


def test_settings_overlay_overview_options_suppression_survives_retheme(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    overlay = _make_overlay(monkeypatch, tmp_path)
    panel = overlay._panel_rect()
    bg_rect = Rect(x=panel.left, y=panel.bottom, width=panel.width, height=panel.height)
    empty_layout = LayoutResult(rect=bg_rect, instructions=[])
    monkeypatch.setattr(
        overlay,
        "_layout_overview_section",
        lambda _rows: LayoutResult(
            rect=bg_rect,
            instructions=[DrawInstruction(kind="panel_bg", payload={"rect": bg_rect, "style_token": "settings_overview"})],
        ),
    )
    monkeypatch.setattr(
        overlay,
        "_layout_options_section",
        lambda _rows: LayoutResult(
            rect=bg_rect,
            instructions=[DrawInstruction(kind="panel_bg", payload={"rect": bg_rect, "style_token": "settings_options"})],
        ),
    )
    monkeypatch.setattr(overlay, "_layout_keybinds_section", lambda: empty_layout)
    monkeypatch.setattr(overlay, "_layout_audio_section", lambda: empty_layout)
    monkeypatch.setattr(overlay, "_layout_input_section", lambda: empty_layout)

    events, _texts = _capture_draw(monkeypatch, overlay)
    panel_fills = [payload for kind, payload in events if kind == "fill"]

    assert panel_fills == [(panel.center_x, panel.center_y, panel.width, panel.height, (0, 0, 0, 210))]
