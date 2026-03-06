from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

import engine.optional_arcade as optional_arcade
from engine.editor.editor_keybinds_controller import EditorKeybindsController
from engine.editor.keybinds_ui_model import KeybindRow, KeybindsState
from engine.ui_overlays import keybinds_overlay as overlay_module
from engine.ui_overlays.keybinds_overlay import KeybindsOverlay
from engine.ui_overlays.widgets import Rect

pytestmark = [pytest.mark.fast]


class _KeybindsControllerStub:
    def __init__(self, rows: list[KeybindRow]) -> None:
        self._all_rows = tuple(rows)
        self.state = KeybindsState(visible=True, query="", selected_index=0)
        self.start_recording_calls: list[int] = []

    @property
    def visible_rows(self) -> tuple[KeybindRow, ...]:
        q = str(self.state.query or "").strip().lower()
        if not q:
            return self._all_rows
        return tuple(
            row
            for row in self._all_rows
            if q in row.title.lower() or q in row.action_id.lower() or q in row.shortcut_effective.lower()
        )

    def set_query(self, text: str) -> None:
        self.state = replace(self.state, query=str(text or ""), selected_index=0)

    def set_selected_index(self, index: int) -> None:
        rows = self.visible_rows
        if not rows:
            self.state = replace(self.state, selected_index=-1)
            return
        target = max(0, min(int(index), len(rows) - 1))
        self.state = replace(self.state, selected_index=target)

    def start_recording_selected(self) -> None:
        self.start_recording_calls.append(int(self.state.selected_index))


def _make_rows(count: int) -> list[KeybindRow]:
    rows: list[KeybindRow] = []
    for i in range(count):
        rows.append(
            KeybindRow(
                scope="global" if i % 2 == 0 else "mesh",
                action_id=f"editor.action_{i}",
                title=f"Move Action {i}" if i % 3 == 0 else f"Action {i}",
                shortcut_effective=f"Ctrl+{i % 10}",
                shortcut_default=f"Ctrl+{i % 10}",
                has_override=(i % 4 == 0),
                conflict_ids=(f"editor.conflict_{i}",) if i % 7 == 0 else (),
            )
        )
    return rows


def _stub_draw(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine import arcade_fallback as arcade_stub

    monkeypatch.setattr(optional_arcade, "arcade", arcade_stub)
    monkeypatch.setattr(overlay_module, "draw_text", lambda *args, **kwargs: None)
    monkeypatch.setattr(overlay_module, "_draw_lrtb_rectangle_filled", lambda *args, **kwargs: None)
    monkeypatch.setattr(overlay_module, "_draw_lrtb_rectangle_outline", lambda *args, **kwargs: None)
    monkeypatch.setattr(overlay_module, "_draw_rectangle_outline", lambda *args, **kwargs: None)


def _visible_signature(overlay: KeybindsOverlay) -> list[tuple[int, str, float, float, bool]]:
    rows = overlay._results_scroll.visible_rows
    return [
        (idx, text, round(rect.y, 3), round(rect.height, 3), selected)
        for idx, text, rect, selected in rows
    ]


def _make_overlay(row_count: int = 20) -> tuple[KeybindsOverlay, _KeybindsControllerStub]:
    keybinds = _KeybindsControllerStub(_make_rows(row_count))
    editor = SimpleNamespace(active=True, keybinds=keybinds)
    window = SimpleNamespace(width=1280, height=720, editor_controller=editor, text_cache=None)
    overlay = KeybindsOverlay(window)  # type: ignore[arg-type]
    overlay.visible = True
    return overlay, keybinds


def test_keybinds_overlay_filtering_is_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_draw(monkeypatch)
    overlay, keybinds = _make_overlay(24)
    keybinds.set_query("move")

    overlay.draw()
    first = _visible_signature(overlay)
    overlay.draw()
    second = _visible_signature(overlay)
    assert first == second
    assert len(keybinds.visible_rows) > 0


def test_keybinds_overlay_tab_focus_toggle() -> None:
    overlay, _keybinds = _make_overlay(10)
    overlay.visible = True
    overlay.reset_for_open()
    assert overlay._focus_target == "input"
    assert overlay.toggle_focus() is True
    assert overlay._focus_target == "results"
    assert overlay.toggle_focus() is True
    assert overlay._focus_target == "input"


def test_keybinds_overlay_navigation_keeps_selection_visible(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_draw(monkeypatch)
    overlay, keybinds = _make_overlay(30)
    overlay.draw()
    overlay.toggle_focus()
    assert overlay._focus_target == "results"

    for _ in range(9):
        assert overlay.handle_navigation_key(optional_arcade.arcade.key.DOWN) is True
    assert keybinds.state.selected_index == 9
    visible_indexes = [idx for idx, _text, _rect, _sel in overlay._results_scroll.visible_rows]
    assert 9 in visible_indexes


def test_keybinds_overlay_enter_activation_gated_by_focus(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_draw(monkeypatch)
    overlay, keybinds = _make_overlay(8)
    overlay.draw()

    assert overlay._focus_target == "input"
    assert overlay.on_key_enter() is True
    assert keybinds.start_recording_calls == []

    overlay.toggle_focus()
    keybinds.set_selected_index(3)
    assert overlay.on_key_enter() is True
    assert keybinds.start_recording_calls == [3]


def test_keybinds_overlay_wheel_and_click_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_draw(monkeypatch)
    overlay, keybinds = _make_overlay(28)
    overlay.draw()
    bounds = overlay._list_rect
    assert isinstance(bounds, Rect)

    assert overlay.on_mouse_scroll(bounds.center_x, bounds.center_y, 0.0, -200.0) is True
    max_offset = overlay._results_scroll._max_scroll_offset(overlay._results_scroll.visible_capacity)
    assert overlay._results_scroll.scroll_offset == pytest.approx(max_offset)
    assert overlay.on_mouse_scroll(bounds.center_x, bounds.center_y, 0.0, 200.0) is True
    assert overlay._results_scroll.scroll_offset == pytest.approx(0.0)

    target_rect = None
    for row_idx, _text, rect, _sel in overlay._results_scroll.visible_rows:
        if row_idx == 2:
            target_rect = rect
            break
    assert target_rect is not None
    handled = overlay.on_mouse_press(
        target_rect.center_x,
        target_rect.center_y,
        optional_arcade.arcade.MOUSE_BUTTON_LEFT,
        0,
    )
    assert handled is True
    assert keybinds.state.selected_index == 2


def test_keybinds_controller_forwards_input_to_overlay_first(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_draw(monkeypatch)
    calls: list[str] = []

    class _OverlayStub:
        def reset_for_open(self) -> None:
            calls.append("open")

        def toggle_focus(self) -> bool:
            calls.append("tab")
            return True

        def handle_navigation_key(self, key: int) -> bool:
            calls.append(f"nav:{int(key)}")
            return True

        def on_key_enter(self) -> bool:
            calls.append("enter")
            return True

        def backspace(self) -> bool:
            calls.append("backspace")
            return True

        def append_text(self, text: str) -> bool:
            calls.append(f"text:{text}")
            return True

        def on_mouse_press(self, x: float, y: float, button: int, modifiers: int) -> bool:
            calls.append("click")
            return True

        def on_mouse_scroll(self, x: float, y: float, scroll_x: float, scroll_y: float) -> bool:
            calls.append("wheel")
            return True

    editor = SimpleNamespace(window=SimpleNamespace(), _keymap_overrides={}, keybinds_overlay=_OverlayStub())
    controller = EditorKeybindsController(editor)
    controller.open()
    assert controller.handle_input(optional_arcade.arcade.key.TAB, 0) is True
    assert controller.handle_input(optional_arcade.arcade.key.DOWN, 0) is True
    assert controller.handle_input(optional_arcade.arcade.key.ENTER, 0) is True
    assert controller.handle_input(optional_arcade.arcade.key.BACKSPACE, 0) is True
    assert controller.on_text("x") is True
    assert controller.handle_mouse_press(1.0, 2.0, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True
    assert controller.handle_mouse_scroll(1.0, 2.0, 0.0, -1.0) is True
    assert calls == [
        "open",
        "tab",
        f"nav:{int(optional_arcade.arcade.key.DOWN)}",
        "enter",
        "backspace",
        "text:x",
        "click",
        "wheel",
    ]
