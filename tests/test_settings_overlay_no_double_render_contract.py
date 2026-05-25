from __future__ import annotations

import types
from pathlib import Path

import pytest

from engine.ui import SettingsOverlay
from engine.ui_overlays import settings_overlay as overlay_module
from tests._typing import as_any

pytestmark = [pytest.mark.fast]


def _make_overlay(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SettingsOverlay:
    settings_path = tmp_path / "settings_no_double_render_contract.json"
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


def _drawn_texts(monkeypatch: pytest.MonkeyPatch, overlay: SettingsOverlay) -> list[str]:
    captured: list[str] = []
    monkeypatch.setattr(overlay_module, "draw_text_cached", lambda text, *args, **kwargs: captured.append(str(text)))
    monkeypatch.setattr(overlay_module, "_draw_tb_rectangle_outline", lambda *args, **kwargs: None)
    monkeypatch.setattr(overlay_module, "_draw_rectangle_filled", lambda *args, **kwargs: None)

    overlay.draw()
    return captured


def test_draw_does_not_render_diagnostic_overview_text(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    overlay = _make_overlay(monkeypatch, tmp_path)

    drawn_texts = _drawn_texts(monkeypatch, overlay)

    assert all(not text.startswith("Settings (") for text in drawn_texts)


def test_draw_does_not_render_diagnostic_path_text(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    overlay = _make_overlay(monkeypatch, tmp_path)

    drawn_texts = _drawn_texts(monkeypatch, overlay)

    assert all(not text.startswith("path: ") for text in drawn_texts)


def test_draw_renders_interactive_keybinds_section(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    overlay = _make_overlay(monkeypatch, tmp_path)

    drawn_texts = _drawn_texts(monkeypatch, overlay)

    assert any("Keybind:" in text or "Keybinds" in text for text in drawn_texts)


def test_get_lines_still_callable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    overlay = _make_overlay(monkeypatch, tmp_path)

    assert overlay.get_lines()
