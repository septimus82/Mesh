from __future__ import annotations

from types import SimpleNamespace

import pytest

import engine.optional_arcade as optional_arcade
from engine.editor.editor_scene_browse_controller import EditorSceneBrowseController
from engine.editor.scene_opening import compute_scene_browser_layout
from engine.scene_index import SceneRow
from engine.ui_overlays import scene_browser_overlay as overlay_module
from engine.ui_overlays.scene_browser_overlay import SceneBrowserOverlay
from engine.ui_overlays.widgets import Rect
from tests._typing import as_any

pytestmark = [pytest.mark.fast]


class _DockStub:
    def get_snapshot(self) -> object:
        return SimpleNamespace(left_tab="Scene")


class _SceneBrowserControllerStub:
    def __init__(self, rows: list[SceneRow], width: int = 1280, height: int = 720) -> None:
        self.active = True
        self.scene_browser_active = True
        self.scene_browser_query = ""
        self.scene_browser_index = 0
        self._all_rows = list(rows)
        self._rows = list(rows)
        self._open_calls: list[int] = []
        self.dock = _DockStub()
        self.window = SimpleNamespace(width=width, height=height)

    def _refresh_scene_browser_rows(self) -> None:
        query = str(self.scene_browser_query or "").strip().lower()
        if not query:
            self._rows = list(self._all_rows)
            return
        self._rows = [row for row in self._all_rows if query in row.display_name.lower()]

    def _scene_browser_rows(self) -> list[SceneRow]:
        return list(self._rows)

    def _scene_browser_clamp_index(self, count: int) -> None:
        if count <= 0:
            self.scene_browser_index = -1
            return
        self.scene_browser_index = max(0, min(int(self.scene_browser_index), count - 1))

    def _scene_browser_layout(self, count: int) -> dict[str, float]:
        return compute_scene_browser_layout(float(self.window.width), float(self.window.height), int(count))

    def _scene_browser_open_selected(self) -> bool:
        self._open_calls.append(int(self.scene_browser_index))
        return True


def _make_rows(count: int) -> list[SceneRow]:
    rows: list[SceneRow] = []
    for i in range(count):
        rows.append(
            SceneRow(
                scene_id=f"packs/core/scenes/scene_{i}.json",
                display_name=f"Scene {i}",
                pack_name="core",
                is_recent=(i % 3 == 0),
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


def _visible_signature(overlay: SceneBrowserOverlay) -> list[tuple[int, str, float, float, bool]]:
    rows = overlay._results_scroll.visible_rows
    return [
        (idx, text, round(rect.y, 3), round(rect.height, 3), selected)
        for idx, text, rect, selected in rows
    ]


def test_scene_browser_overlay_visible_rows_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_draw(monkeypatch)
    controller = _SceneBrowserControllerStub(_make_rows(20))
    window = SimpleNamespace(width=1280, height=720, editor_controller=controller)
    overlay = SceneBrowserOverlay(as_any(window))

    overlay.draw()
    first = _visible_signature(overlay)
    overlay.draw()
    second = _visible_signature(overlay)
    assert first == second


def test_scene_browser_overlay_tab_toggles_focus() -> None:
    controller = _SceneBrowserControllerStub(_make_rows(10))
    window = SimpleNamespace(width=1280, height=720, editor_controller=controller)
    overlay = SceneBrowserOverlay(as_any(window))
    overlay._was_open = True
    overlay._text_input.focused = True

    assert overlay._focus_target == "input"
    assert overlay.toggle_focus() is True
    assert overlay._focus_target == "results"
    assert overlay._text_input.focused is False
    assert overlay.toggle_focus() is True
    assert overlay._focus_target == "input"
    assert overlay._text_input.focused is True


def test_scene_browser_overlay_up_down_keeps_selection_visible(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_draw(monkeypatch)
    controller = _SceneBrowserControllerStub(_make_rows(24))
    window = SimpleNamespace(width=1280, height=720, editor_controller=controller)
    overlay = SceneBrowserOverlay(as_any(window))
    overlay.draw()
    overlay.toggle_focus()
    assert overlay._focus_target == "results"

    for _ in range(9):
        assert overlay.handle_navigation_key(optional_arcade.arcade.key.DOWN) is True
    assert controller.scene_browser_index == 9
    visible_indexes = [idx for idx, _text, _rect, _sel in overlay._results_scroll.visible_rows]
    assert 9 in visible_indexes


def test_scene_browser_overlay_enter_activates_only_in_results_focus(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_draw(monkeypatch)
    controller = _SceneBrowserControllerStub(_make_rows(8))
    window = SimpleNamespace(width=1280, height=720, editor_controller=controller)
    overlay = SceneBrowserOverlay(as_any(window))
    overlay.draw()

    assert overlay._focus_target == "input"
    assert overlay.on_key_enter() is True
    assert controller._open_calls == []

    overlay.toggle_focus()
    controller.scene_browser_index = 3
    assert overlay.on_key_enter() is True
    assert controller._open_calls == [3]


def test_scene_browser_overlay_wheel_scroll_clamps(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_draw(monkeypatch)
    controller = _SceneBrowserControllerStub(_make_rows(30))
    window = SimpleNamespace(width=1280, height=720, editor_controller=controller)
    overlay = SceneBrowserOverlay(as_any(window))
    overlay.draw()
    bounds = overlay._results_rect
    assert isinstance(bounds, Rect)

    assert overlay.on_mouse_scroll(bounds.center_x, bounds.center_y, 0.0, -300.0) is True
    max_offset = overlay._results_scroll._max_scroll_offset(overlay._results_scroll.visible_capacity)
    assert overlay._results_scroll.scroll_offset == pytest.approx(max_offset)
    assert overlay.on_mouse_scroll(bounds.center_x, bounds.center_y, 0.0, 300.0) is True
    assert overlay._results_scroll.scroll_offset == pytest.approx(0.0)


def test_scene_browse_controller_forwards_to_overlay_paths() -> None:
    calls: list[str] = []

    class _OverlayStub:
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

        def on_mouse_scroll(self, x: float, y: float, scroll_x: float, scroll_y: float) -> bool:
            calls.append("scroll")
            return True

    editor = SimpleNamespace(
        scene_browser_active=True,
        scene_browser_query="abc",
        scene_browser_index=0,
        window=SimpleNamespace(scene_browser_overlay=_OverlayStub()),
    )
    controller = EditorSceneBrowseController(editor)
    assert controller.handle_scene_browser_input(optional_arcade.arcade.key.TAB, 0) is True
    assert controller.handle_scene_browser_input(optional_arcade.arcade.key.DOWN, 0) is True
    assert controller.handle_scene_browser_input(optional_arcade.arcade.key.ENTER, 0) is True
    assert controller.handle_scene_browser_input(optional_arcade.arcade.key.BACKSPACE, 0) is True
    assert controller.handle_scene_browser_text_input("x") is True
    assert controller.handle_scene_browser_mouse_scroll(10.0, 20.0, 0.0, -1.0) is True
    assert calls == ["tab", f"nav:{int(optional_arcade.arcade.key.DOWN)}", "enter", "backspace", "text:x", "scroll"]
