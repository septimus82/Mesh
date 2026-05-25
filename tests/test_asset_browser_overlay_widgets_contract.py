from __future__ import annotations

from types import SimpleNamespace

import pytest

import engine.optional_arcade as optional_arcade
from engine.asset_index import AssetRow
from engine.editor.editor_asset_browser_controller import EditorAssetBrowserController
from engine.ui_overlays import asset_browser_overlay as overlay_module
from engine.ui_overlays.asset_browser_overlay import AssetBrowserOverlay
from engine.ui_overlays.widgets import Rect
from tests._typing import as_any

pytestmark = [pytest.mark.fast]


class _DockStub:
    def get_snapshot(self) -> object:
        return SimpleNamespace(right_tab="Assets")


class _SearchStub:
    def __init__(self) -> None:
        self._assets_search = ""
        self._focused = False

    def get_assets_search(self) -> str:
        return self._assets_search

    def set_assets_search(self, text: str) -> None:
        self._assets_search = str(text or "")

    def is_panel_search_focused(self, panel: str) -> bool:
        return panel == "assets" and self._focused

    def backspace_search_text(self) -> None:
        self._assets_search = self._assets_search[:-1]


class _AssetControllerStub:
    def __init__(self, rows: list[AssetRow]) -> None:
        self.active = True
        self.asset_browser_active = True
        self.asset_browser_kind = "All"
        self.asset_browser_selection_index = 0
        self.asset_browser_filter = ""
        self._asset_browser_cached_rows = list(rows)
        self._asset_browser_filtered_rows = list(rows)
        self.dock = _DockStub()
        self.search = _SearchStub()
        self._activate_calls: list[int] = []

    def set_asset_browser_filter(self, text: str) -> None:
        self.asset_browser_filter = str(text or "")
        self.search.set_assets_search(self.asset_browser_filter)
        q = self.asset_browser_filter.lower().strip()
        if not q:
            self._asset_browser_filtered_rows = list(self._asset_browser_cached_rows)
        else:
            self._asset_browser_filtered_rows = [
                row for row in self._asset_browser_cached_rows if q in row.rel_path.lower() or q in row.display_name.lower()
            ]
        if self._asset_browser_filtered_rows:
            self.asset_browser_selection_index = max(
                0, min(int(self.asset_browser_selection_index), len(self._asset_browser_filtered_rows) - 1)
            )
        else:
            self.asset_browser_selection_index = 0

    def _activate_selected_asset(self) -> None:
        self._activate_calls.append(int(self.asset_browser_selection_index))


def _make_rows(count: int) -> list[AssetRow]:
    rows: list[AssetRow] = []
    for i in range(count):
        rows.append(
            AssetRow(
                rel_path=f"assets/props/item_{i}.png" if i % 2 == 0 else f"assets/audio/sfx_{i}.ogg",
                kind="image" if i % 2 == 0 else "audio",
                display_name=f"item_{i}.png" if i % 2 == 0 else f"sfx_{i}.ogg",
            )
        )
    return rows


def _stub_draw(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine import arcade_fallback as arcade_stub

    monkeypatch.setattr(optional_arcade, "arcade", arcade_stub)
    monkeypatch.setattr(overlay_module, "draw_panel_bg", lambda *args, **kwargs: None)
    monkeypatch.setattr(overlay_module, "_draw_tb_rectangle_outline", lambda *args, **kwargs: None)
    monkeypatch.setattr(overlay_module, "_draw_rectangle_filled", lambda *args, **kwargs: None)
    monkeypatch.setattr(overlay_module, "draw_text_cached", lambda *args, **kwargs: None)


def _visible_signature(overlay: AssetBrowserOverlay) -> list[tuple[int, str, float, float, bool]]:
    rows = overlay._results_scroll.visible_rows
    return [
        (idx, text, round(rect.y, 3), round(rect.height, 3), selected)
        for idx, text, rect, selected in rows
    ]


def _make_overlay(row_count: int = 20) -> tuple[AssetBrowserOverlay, _AssetControllerStub]:
    controller = _AssetControllerStub(_make_rows(row_count))
    window = SimpleNamespace(width=1280, height=720, editor_controller=controller)
    overlay = AssetBrowserOverlay(as_any(window))
    return overlay, controller


def test_asset_browser_filter_visible_window_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_draw(monkeypatch)
    overlay, controller = _make_overlay(24)
    controller.set_asset_browser_filter("item_")
    overlay.draw()
    first = _visible_signature(overlay)
    overlay.draw()
    second = _visible_signature(overlay)
    assert first == second
    assert len(controller._asset_browser_filtered_rows) > 0


def test_asset_browser_focus_toggle() -> None:
    overlay, _controller = _make_overlay(8)
    overlay.reset_for_open()
    assert overlay._focus_target == "input"
    assert overlay.toggle_focus() is True
    assert overlay._focus_target == "results"
    assert overlay.toggle_focus() is True
    assert overlay._focus_target == "input"


def test_asset_browser_nav_keeps_selection_visible(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_draw(monkeypatch)
    overlay, controller = _make_overlay(26)
    overlay.draw()
    overlay.toggle_focus()
    assert overlay._focus_target == "results"
    for _ in range(9):
        assert overlay.handle_navigation_key(optional_arcade.arcade.key.DOWN) is True
    assert controller.asset_browser_selection_index == 9
    visible_indexes = [idx for idx, _text, _rect, _sel in overlay._results_scroll.visible_rows]
    assert 9 in visible_indexes


def test_asset_browser_enter_activation_gated_by_focus(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_draw(monkeypatch)
    overlay, controller = _make_overlay(10)
    overlay.draw()
    assert overlay._focus_target == "input"
    assert overlay.on_key_enter() is True
    assert controller._activate_calls == []
    overlay.toggle_focus()
    controller.asset_browser_selection_index = 3
    assert overlay.on_key_enter() is True
    assert controller._activate_calls == [3]


def test_asset_browser_wheel_click_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_draw(monkeypatch)
    overlay, controller = _make_overlay(30)
    overlay.draw()
    bounds = overlay._list_rect
    assert isinstance(bounds, Rect)

    assert overlay.on_mouse_scroll(bounds.center_x, bounds.center_y, 0.0, -200.0) is True
    max_offset = overlay._results_scroll._max_scroll_offset(overlay._results_scroll.visible_capacity)
    assert overlay._results_scroll.scroll_offset == pytest.approx(max_offset)

    assert overlay.on_mouse_scroll(bounds.center_x, bounds.center_y, 0.0, 200.0) is True
    assert overlay._results_scroll.scroll_offset == pytest.approx(0.0)

    target_rect = None
    for idx, _text, rect, _selected in overlay._results_scroll.visible_rows:
        if idx == 2:
            target_rect = rect
            break
    assert target_rect is not None
    handled = overlay.on_mouse_press(target_rect.center_x, target_rect.center_y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0)
    assert handled is True
    assert controller.asset_browser_selection_index == 2


def test_asset_browser_controller_forwards_overlay_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class _OverlayStub:
        def reset_for_open(self) -> None:
            calls.append("open")

        def reset_for_close(self) -> None:
            calls.append("close")

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

    editor = SimpleNamespace(
        active=True,
        asset_browser_active=True,
        scene_switcher_active=False,
        scene_browser_active=False,
        _asset_browser_cached_rows=[],
        _asset_browser_filtered_rows=[],
        asset_browser_filter="",
        asset_browser_kind="All",
        asset_browser_selection_index=0,
        search=SimpleNamespace(
            is_panel_search_focused=lambda panel: False,
            clear_search_focus=lambda: None,
            get_assets_search=lambda: "",
            set_assets_search=lambda text: None,
            backspace_search_text=lambda: None,
        ),
        panels=SimpleNamespace(close_command_palette=lambda: None),
        window=SimpleNamespace(),
        _autosave_workspace=lambda: None,
    )
    ctrl = EditorAssetBrowserController(editor)
    editor.asset_browser_overlay = _OverlayStub()
    monkeypatch.setattr(ctrl, "refresh_asset_browser", lambda: None)

    assert ctrl.toggle_asset_browser() is False
    assert ctrl.toggle_asset_browser() is True
    assert ctrl.handle_asset_browser_input(optional_arcade.arcade.key.TAB, 0) is True
    assert ctrl.handle_asset_browser_input(optional_arcade.arcade.key.DOWN, 0) is True
    assert ctrl.handle_asset_browser_input(optional_arcade.arcade.key.ENTER, 0) is True
    assert ctrl.handle_asset_browser_input(optional_arcade.arcade.key.BACKSPACE, 0) is True
    assert ctrl.handle_asset_browser_text_input("x") is True
    assert ctrl.handle_asset_browser_mouse_click(10.0, 20.0, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True
    assert ctrl.handle_asset_browser_mouse_scroll(10.0, 20.0, 0.0, -1.0) is True

    assert calls == [
        "close",
        "open",
        "tab",
        f"nav:{int(optional_arcade.arcade.key.DOWN)}",
        "enter",
        "backspace",
        "text:x",
        "click",
        "wheel",
    ]
