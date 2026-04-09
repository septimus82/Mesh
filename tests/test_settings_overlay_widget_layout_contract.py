from __future__ import annotations

import types
from pathlib import Path

import pytest

from engine.ui import SettingsOverlay
from engine.ui_overlays import settings_overlay as overlay_module
from engine.ui_overlays.widgets import DrawInstruction, LayoutResult, Rect
from tests._typing import as_any

pytestmark = [pytest.mark.fast]


class _Audio:
    def __init__(self) -> None:
        self.master_volume = 1.0
        self.sfx_volume = 1.0
        self.music_volume = 1.0

    def set_master_volume(self, volume: float) -> None:
        self.master_volume = float(volume)

    def set_sfx_volume(self, volume: float) -> None:
        self.sfx_volume = float(volume)

    def set_music_volume(self, volume: float) -> None:
        self.music_volume = float(volume)


def _make_overlay(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SettingsOverlay:
    settings_path = tmp_path / "settings_widget_layout_contract.json"
    monkeypatch.setenv("MESH_SETTINGS_PATH", str(settings_path))
    window = types.SimpleNamespace(
        width=1024,
        height=768,
        paused=False,
        audio=_Audio(),
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


def _instruction_signature(layout: LayoutResult) -> list[tuple[str, str, str, tuple[str, ...]]]:
    signature: list[tuple[str, str, str, tuple[str, ...]]] = []
    for instruction in layout.instructions:
        payload = instruction.payload if isinstance(instruction.payload, dict) else {}
        signature.append(
            (
                str(instruction.kind or ""),
                str(payload.get("style_token", "")),
                str(payload.get("text", "")),
                tuple(sorted(str(key) for key in payload.keys())),
            )
        )
    return signature


def test_settings_overlay_section_layout_contract_deterministic(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    overlay = _make_overlay(monkeypatch, tmp_path)
    lines = overlay.get_lines()
    overview_lines = lines[:3]
    options_lines = lines[3 + len(overlay._ACTIONS) :]

    overview_first = _instruction_signature(overlay._layout_overview_section(overview_lines))
    options_first = _instruction_signature(overlay._layout_options_section(options_lines))
    audio_first = _instruction_signature(overlay._layout_audio_section())
    input_first = _instruction_signature(overlay._layout_input_section())

    overview_second = _instruction_signature(overlay._layout_overview_section(overview_lines))
    options_second = _instruction_signature(overlay._layout_options_section(options_lines))
    audio_second = _instruction_signature(overlay._layout_audio_section())
    input_second = _instruction_signature(overlay._layout_input_section())

    assert overview_first == overview_second
    assert options_first == options_second
    assert audio_first == audio_second
    assert input_first == input_second

    audio_kinds = {kind for kind, _style, _text, _keys in audio_first}
    assert {"slider_track", "slider_fill", "slider_knob"}.issubset(audio_kinds)

    input_kinds = {kind for kind, _style, _text, _keys in input_first}
    assert "toggle_text" in input_kinds
    assert {"slider_track", "slider_fill", "slider_knob"}.issubset(input_kinds)


def test_settings_overlay_overview_options_panel_bg_suppressed_in_draw(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    overlay = _make_overlay(monkeypatch, tmp_path)
    filled_calls: list[tuple[float, float, float, float, object]] = []

    monkeypatch.setattr(overlay_module, "draw_text_cached", lambda *args, **kwargs: None)
    monkeypatch.setattr(overlay_module, "_draw_lrtb_rectangle_outline", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        overlay_module,
        "_draw_rectangle_filled",
        lambda center_x, center_y, width, height, color: filled_calls.append(
            (float(center_x), float(center_y), float(width), float(height), color)
        ),
    )

    panel_rect = overlay._panel_rect()
    bg_rect = Rect(x=panel_rect.left, y=panel_rect.bottom, width=panel_rect.width, height=panel_rect.height)
    overview_layout = LayoutResult(
        rect=bg_rect,
        instructions=[DrawInstruction(kind="panel_bg", payload={"rect": bg_rect, "style_token": "settings_overview"})],
    )
    options_layout = LayoutResult(
        rect=bg_rect,
        instructions=[DrawInstruction(kind="panel_bg", payload={"rect": bg_rect, "style_token": "settings_options"})],
    )
    empty_layout = LayoutResult(rect=bg_rect, instructions=[])

    monkeypatch.setattr(overlay, "_layout_overview_section", lambda _rows: overview_layout)
    monkeypatch.setattr(overlay, "_layout_options_section", lambda _rows: options_layout)
    monkeypatch.setattr(overlay, "_layout_keybinds_section", lambda: empty_layout)
    monkeypatch.setattr(overlay, "_layout_audio_section", lambda: empty_layout)
    monkeypatch.setattr(overlay, "_layout_input_section", lambda: empty_layout)

    overlay.draw()
    assert len(filled_calls) == 1
