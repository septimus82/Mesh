from __future__ import annotations

import types
from pathlib import Path

import pytest

from engine.ui import SettingsOverlay
from engine.ui_overlays.widgets import Rect
from tests._typing import as_any

pytestmark = [pytest.mark.fast]


def _make_overlay(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SettingsOverlay:
    settings_path = tmp_path / "settings_slider_label_no_overlap_contract.json"
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


def _slider_bounds(overlay: SettingsOverlay, section: str, label: str) -> tuple[float, list[Rect]]:
    layout = overlay._layout_audio_section() if section == "audio" else overlay._layout_input_section()
    label_bottom: float | None = None
    rects: list[Rect] = []
    collecting = False
    for instruction in layout.instructions:
        payload = instruction.payload if isinstance(instruction.payload, dict) else {}
        kind = str(instruction.kind or "")
        if kind == "slider_label_text":
            if collecting:
                break
            collecting = str(payload.get("text", "")) == label
            if collecting:
                label_bottom = float(payload.get("y", 0.0)) - overlay._SLIDER_LABEL_FONT_SIZE
        elif collecting and kind in ("slider_track", "slider_fill", "slider_knob"):
            rect = payload.get("rect")
            assert isinstance(rect, Rect)
            rects.append(rect)
    assert label_bottom is not None
    assert rects
    return label_bottom, rects


@pytest.mark.parametrize(
    ("section", "label"),
    [
        ("audio", "Master Volume"),
        ("audio", "Music Volume"),
        ("audio", "SFX Volume"),
        ("input", "Rumble Strength"),
    ],
)
def test_settings_overlay_slider_label_sits_above_bar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, section: str, label: str
) -> None:
    overlay = _make_overlay(monkeypatch, tmp_path)

    label_bottom, rects = _slider_bounds(overlay, section, label)

    for rect in rects:
        assert rect.top <= label_bottom - overlay._SLIDER_LABEL_BAR_GAP
