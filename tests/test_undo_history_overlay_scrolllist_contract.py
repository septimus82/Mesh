from __future__ import annotations

from types import SimpleNamespace

import pytest

import engine.optional_arcade as optional_arcade
from engine.ui_overlays.undo_history_overlay import UndoHistoryOverlay
from engine.ui_overlays.widgets import Rect, ScrollList
from tests._typing import as_any

pytestmark = [pytest.mark.fast]


class _HistoryStub:
    def __init__(self) -> None:
        self.jump_calls: list[int] = []

    def jump_to(self, cursor_index: int) -> bool:
        self.jump_calls.append(int(cursor_index))
        return True


def _make_overlay() -> UndoHistoryOverlay:
    history = _HistoryStub()
    controller = SimpleNamespace(
        active=True,
        dock=SimpleNamespace(right_tab="History", get_snapshot=lambda: SimpleNamespace(right_tab="History")),
        history=history,
    )
    window = SimpleNamespace(editor_controller=controller)
    overlay = UndoHistoryOverlay(as_any(window))
    entries = [
        SimpleNamespace(index=i + 1, real_index=i, label=f"Entry {i}", is_current=(i == 0))
        for i in range(12)
    ]
    rect = Rect(x=10.0, y=10.0, width=300.0, height=90.0)
    overlay._last_history_entries = entries
    overlay._history_list_rect = rect
    overlay._scroll_list = ScrollList(
        items=[f"{entry.index:02d} {entry.label}" for entry in entries],
        row_height=18,
        selected_index=0,
        scroll_offset=0.0,
    )
    overlay._scroll_list.layout(rect)
    return overlay


def test_undo_history_overlay_scrolllist_wheel_updates_selection_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from engine import arcade_fallback as arcade_stub

    monkeypatch.setattr(optional_arcade, "arcade", arcade_stub)
    overlay = _make_overlay()
    changed = overlay.on_mouse_scroll(20.0, 20.0, 0.0, -2.0)
    assert changed is True
    assert overlay._scroll_list.scroll_offset == pytest.approx(2.0)
    visible = [row[0] for row in overlay._scroll_list.visible_rows]
    assert visible == [2, 3, 4, 5, 6]


def test_undo_history_overlay_scrolllist_click_selects_and_jumps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from engine import arcade_fallback as arcade_stub

    monkeypatch.setattr(optional_arcade, "arcade", arcade_stub)
    overlay = _make_overlay()
    # Third visible row -> index 2
    handled = overlay.on_mouse_press(20.0, 55.0, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0)
    assert handled is True
    assert overlay._scroll_list.selected_index == 2
    history = overlay.window.editor_controller.history
    assert history.jump_calls == [2]
