from __future__ import annotations

from types import SimpleNamespace

import pytest

import engine.optional_arcade as optional_arcade
from engine.editor.find_everything_model import FindResult, compute_find_counts
from engine.editor.editor_search_controller import EditorSearchController
from engine.editor_runtime import editor_input_key_handlers
from engine.ui_overlays.find_everything_overlay import FindEverythingOverlay
from engine.ui_overlays import find_everything_overlay as overlay_module
from engine.ui_overlays.widgets import Rect
from tests._typing import as_any

pytestmark = [pytest.mark.fast]


class _FindControllerStub:
    def __init__(self, results: list[FindResult]) -> None:
        self.active = True
        self._find_everything_open = True
        self._find_everything_query = ""
        self._find_everything_selection_index = 0
        self._find_everything_cached_results = list(results)
        self._find_everything_counts = compute_find_counts(results, include_zero=True)
        self.activate_calls: list[int] = []

    def set_find_query(self, text: str) -> None:
        self._find_everything_query = str(text or "")

    def move_find_selection(self, delta: int) -> None:
        count = len(self._find_everything_cached_results)
        if count <= 0:
            self._find_everything_selection_index = 0
            return
        current = int(self._find_everything_selection_index or 0)
        target = max(0, min(current + int(delta), count - 1))
        self._find_everything_selection_index = target

    def activate_find_selection(self) -> bool:
        self.activate_calls.append(int(self._find_everything_selection_index or 0))
        return True


def _make_overlay(result_count: int = 12) -> tuple[FindEverythingOverlay, _FindControllerStub]:
    results = [
        FindResult(kind="scene", item_id=f"scene.{i}", title=f"Scene: {i}", subtitle="pack/demo")
        for i in range(result_count)
    ]
    controller = _FindControllerStub(results)
    window = SimpleNamespace(
        width=1280,
        height=720,
        editor_controller=controller,
        input=SimpleNamespace(input_source="keyboard_mouse"),
    )
    overlay = FindEverythingOverlay(as_any(window))
    return overlay, controller


def _stub_draw(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine import arcade_fallback as arcade_stub

    monkeypatch.setattr(optional_arcade, "arcade", arcade_stub)
    monkeypatch.setattr(overlay_module, "draw_panel_bg", lambda *args, **kwargs: None)
    monkeypatch.setattr(overlay_module, "_draw_tb_rectangle_outline", lambda *args, **kwargs: None)
    monkeypatch.setattr(overlay_module, "_draw_rectangle_filled", lambda *args, **kwargs: None)
    monkeypatch.setattr(overlay_module, "draw_text_cached", lambda *args, **kwargs: None)


def _visible_signature(overlay: FindEverythingOverlay) -> list[tuple[int, str, float, float, bool]]:
    rows = overlay._results_scroll.visible_rows
    return [
        (idx, text, round(rect.y, 3), round(rect.height, 3), selected)
        for idx, text, rect, selected in rows
    ]


def test_find_everything_scrolllist_visible_rows_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_draw(monkeypatch)
    overlay, _controller = _make_overlay()
    overlay.draw()
    first = _visible_signature(overlay)
    overlay.draw()
    second = _visible_signature(overlay)
    assert first == second


def test_find_everything_up_down_selection_clamps(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_draw(monkeypatch)
    overlay, controller = _make_overlay(result_count=4)
    overlay.draw()

    assert overlay.move_selection(-1) is True
    assert controller._find_everything_selection_index == 0

    controller._find_everything_selection_index = 3
    overlay.draw()
    assert overlay.move_selection(1) is True
    assert controller._find_everything_selection_index == 3


def test_find_everything_wheel_scroll_clamps(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_draw(monkeypatch)
    overlay, _controller = _make_overlay(result_count=18)
    overlay.draw()
    bounds = overlay._results_rect
    assert isinstance(bounds, Rect)

    assert overlay.on_mouse_scroll(bounds.center_x, bounds.center_y, 0.0, -200.0) is True
    max_offset = overlay._results_scroll._max_scroll_offset(overlay._results_scroll.visible_capacity)
    assert overlay._results_scroll.scroll_offset == pytest.approx(max_offset)

    assert overlay.on_mouse_scroll(bounds.center_x, bounds.center_y, 0.0, 200.0) is True
    assert overlay._results_scroll.scroll_offset == pytest.approx(0.0)


def test_find_everything_enter_activates_selected(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_draw(monkeypatch)
    overlay, controller = _make_overlay(result_count=6)
    controller._find_everything_selection_index = 3
    overlay.draw()

    assert overlay.activate_selected() is True
    assert controller.activate_calls == [3]


def test_find_everything_click_selects_row_deterministically(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_draw(monkeypatch)
    overlay, controller = _make_overlay(result_count=8)
    overlay.draw()

    target_rect = None
    for display_idx, _text, rect, _selected in overlay._results_scroll.visible_rows:
        row = overlay._result_rows[display_idx]
        if str(getattr(row, "kind", "") or "") == "row" and int(getattr(row, "row_index", -1)) == 1:
            target_rect = rect
            break
    assert target_rect is not None
    handled = overlay.on_mouse_press(target_rect.center_x, target_rect.center_y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0)
    assert handled is True
    assert controller._find_everything_selection_index == 1


def test_find_everything_results_focus_up_down_uses_scrolllist_and_keeps_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_draw(monkeypatch)
    overlay, controller = _make_overlay(result_count=24)
    overlay.draw()
    overlay.toggle_focus()
    assert overlay._focus_target == "results"

    # Move down enough to force scrolling and ensure selection stays visible.
    for _ in range(9):
        assert overlay.move_selection(1) is True
    assert controller._find_everything_selection_index == 9

    visible_result_indexes: list[int] = []
    for display_idx, _text, _rect, _sel in overlay._results_scroll.visible_rows:
        row = overlay._result_rows[display_idx]
        row_index = getattr(row, "row_index", None)
        if isinstance(row_index, int):
            visible_result_indexes.append(row_index)
    assert 9 in visible_result_indexes


def test_search_controller_forwards_wheel_to_overlay() -> None:
    calls: list[tuple[float, float, float, float]] = []

    class _OverlayStub:
        def on_mouse_scroll(self, x: float, y: float, scroll_x: float, scroll_y: float) -> bool:
            calls.append((x, y, scroll_x, scroll_y))
            return True

    editor = SimpleNamespace(
        active=True,
        _find_everything_open=True,
        window=SimpleNamespace(find_everything_overlay=_OverlayStub()),
    )
    search = EditorSearchController(editor, SimpleNamespace())
    assert search.handle_find_everything_mouse_scroll(10.0, 20.0, 0.0, -1.0) is True
    assert calls == [(10.0, 20.0, 0.0, -1.0)]


def test_find_everything_tab_toggles_focus_deterministically(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_draw(monkeypatch)
    overlay, _controller = _make_overlay(result_count=6)
    overlay.draw()
    assert overlay._focus_target == "input"

    assert overlay.toggle_focus() is True
    assert overlay._focus_target == "results"
    assert overlay._text_input.focused is False

    assert overlay.toggle_focus() is True
    assert overlay._focus_target == "input"
    assert overlay._text_input.focused is True


def test_find_everything_enter_activates_only_when_results_focused(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_draw(monkeypatch)
    overlay, controller = _make_overlay(result_count=6)
    controller._find_everything_selection_index = 2
    overlay.draw()

    assert overlay._focus_target == "input"
    assert overlay.on_key_enter() is True
    assert controller.activate_calls == []

    overlay.toggle_focus()
    assert overlay._focus_target == "results"
    assert overlay.on_key_enter() is True
    assert controller.activate_calls == [2]


def test_find_everything_typing_updates_query_only_when_input_focused(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_draw(monkeypatch)
    overlay, controller = _make_overlay(result_count=5)
    overlay.draw()

    assert overlay.append_text("a") is True
    assert controller._find_everything_query == "a"

    overlay.toggle_focus()
    assert overlay._focus_target == "results"
    assert overlay.append_text("b") is False
    assert controller._find_everything_query == "a"


def test_search_controller_forwards_tab_to_overlay_toggle() -> None:
    calls: list[str] = []

    class _OverlayStub:
        def toggle_focus(self) -> bool:
            calls.append("toggle")
            return True

        def on_key_enter(self) -> bool:
            calls.append("enter")
            return True

    editor = SimpleNamespace(
        active=True,
        _find_everything_open=True,
        _find_everything_query="",
        window=SimpleNamespace(find_everything_overlay=_OverlayStub()),
    )
    search = EditorSearchController(editor, SimpleNamespace())
    assert search.handle_find_everything_input(optional_arcade.arcade.key.TAB, 0) is True
    assert search.handle_find_everything_input(optional_arcade.arcade.key.ENTER, 0) is True
    assert calls == ["toggle", "enter"]


def test_key_router_prioritizes_find_everything_tab_when_open(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[int, int]] = []

    def _handler(key: int, modifiers: int) -> bool:
        calls.append((key, modifiers))
        return True

    controller = SimpleNamespace(
        panels=SimpleNamespace(dispatch_input=lambda key, modifiers: False),
        _alt_dup_active=False,
        _marquee_active=False,
        _find_everything_open=True,
        _handle_find_everything_input=_handler,
        search=SimpleNamespace(is_search_focused=lambda: True),
    )
    monkeypatch.setattr(editor_input_key_handlers, "panels_is_open", lambda *_args, **_kwargs: False)
    handled = editor_input_key_handlers.handle_pre_routed_keys(controller, optional_arcade.arcade.key.TAB, 0)
    assert handled is True
    assert calls == [(optional_arcade.arcade.key.TAB, 0)]
