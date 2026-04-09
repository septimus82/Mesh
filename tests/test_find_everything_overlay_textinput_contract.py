from __future__ import annotations

from types import SimpleNamespace

import pytest

import engine.optional_arcade as optional_arcade
from engine.ui_overlays.find_everything_overlay import FindEverythingOverlay
from engine.ui_overlays import find_everything_overlay as overlay_module
from tests._typing import as_any

pytestmark = [pytest.mark.fast]


class _FindControllerStub:
    def __init__(self) -> None:
        self.active = True
        self._find_everything_open = True
        self._find_everything_query = ""
        self._find_everything_selection_index = 0
        self._find_everything_cached_results = []
        self._find_everything_counts = {"total": 0, "by_group": {}}
        self.set_query_calls: list[str] = []
        self.refresh_count = 0

    def set_find_query(self, text: str) -> None:
        value = str(text or "")
        self._find_everything_query = value
        self.set_query_calls.append(value)
        self.refresh_count += 1


def _make_overlay() -> tuple[FindEverythingOverlay, _FindControllerStub]:
    controller = _FindControllerStub()
    window = SimpleNamespace(
        width=1280,
        height=720,
        editor_controller=controller,
        input=SimpleNamespace(input_source="keyboard_mouse"),
    )
    overlay = FindEverythingOverlay(as_any(window))
    return overlay, controller


def test_find_everything_overlay_textinput_updates_query(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine import arcade_fallback as arcade_stub

    monkeypatch.setattr(optional_arcade, "arcade", arcade_stub)
    monkeypatch.setattr(overlay_module, "draw_panel_bg", lambda *args, **kwargs: None)
    monkeypatch.setattr(overlay_module, "_draw_lrtb_rectangle_outline", lambda *args, **kwargs: None)
    monkeypatch.setattr(overlay_module, "_draw_rectangle_filled", lambda *args, **kwargs: None)
    monkeypatch.setattr(overlay_module, "draw_text_cached", lambda *args, **kwargs: None)
    overlay, controller = _make_overlay()
    overlay.draw()

    rect = overlay._text_input.last_rect
    assert rect is not None
    assert overlay.on_mouse_press(rect.center_x, rect.center_y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True

    assert overlay.append_text("r") is True
    assert overlay.append_text("x") is True
    assert overlay.backspace() is True
    assert controller._find_everything_query == "r"
    assert controller.set_query_calls == ["r", "rx", "r"]
    assert controller.refresh_count == 3


def test_find_everything_overlay_textinput_focus_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine import arcade_fallback as arcade_stub

    monkeypatch.setattr(optional_arcade, "arcade", arcade_stub)
    monkeypatch.setattr(overlay_module, "draw_panel_bg", lambda *args, **kwargs: None)
    monkeypatch.setattr(overlay_module, "_draw_lrtb_rectangle_outline", lambda *args, **kwargs: None)
    monkeypatch.setattr(overlay_module, "_draw_rectangle_filled", lambda *args, **kwargs: None)
    monkeypatch.setattr(overlay_module, "draw_text_cached", lambda *args, **kwargs: None)
    overlay, controller = _make_overlay()
    overlay.draw()

    assert overlay.on_mouse_press(2.0, 2.0, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True
    assert overlay._text_input.focused is False
    assert overlay.append_text("a") is False
    assert controller._find_everything_query == ""
    assert overlay.submit() is False

    rect = overlay._text_input.last_rect
    assert rect is not None
    assert overlay.on_mouse_press(rect.center_x, rect.center_y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True
    assert overlay.append_text("a") is True
    assert controller._find_everything_query == "a"
    assert overlay.submit() is True
