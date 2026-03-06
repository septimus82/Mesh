from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import engine.optional_arcade as optional_arcade
from engine.editor import (
    editor_asset_browser_controller as asset_module,
    editor_keybinds_controller as keybinds_module,
    editor_scene_browse_controller as scene_module,
    editor_search_controller as search_module,
)
from engine.editor.keybinds_ui_model import KeybindRow, KeybindsState

pytestmark = [pytest.mark.fast]


_HELPER_NAMES: tuple[str, ...] = (
    "apply_text_input",
    "apply_backspace",
    "apply_nav_key",
    "apply_enter",
    "apply_mouse_scroll",
    "apply_mouse_press",
)

_CONTROLLER_PATHS: tuple[Path, ...] = (
    Path("engine/editor/editor_search_controller.py"),
    Path("engine/editor/editor_scene_browse_controller.py"),
    Path("engine/editor/editor_keybinds_controller.py"),
    Path("engine/editor/editor_asset_browser_controller.py"),
)


def _stub_arcade(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine import arcade_fallback as arcade_stub

    monkeypatch.setattr(optional_arcade, "arcade", arcade_stub)


def test_widgetized_controllers_source_ratchet_uses_helper_forwarding_calls() -> None:
    for path in _CONTROLLER_PATHS:
        source = path.read_text(encoding="utf-8")
        assert "widget_overlay_helpers" in source, f"{path}: missing helper module reference"
        for helper_name in _HELPER_NAMES:
            assert helper_name in source, f"{path}: missing helper reference {helper_name}"


def test_editor_search_controller_helper_parity_fallbacks_and_tab(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_arcade(monkeypatch)
    toggle_calls: list[str] = []

    class _Overlay:
        def toggle_focus(self) -> bool:
            toggle_calls.append("tab")
            return True

    class _UiFlow:
        def __init__(self) -> None:
            self.query = ""
            self.is_open = True
            self.move_calls: list[int] = []
            self.commit_calls = 0

        def update_query(self, text: str) -> None:
            self.query = str(text or "")

        def move_selection(self, delta: int) -> None:
            self.move_calls.append(int(delta))

        def commit_selection(self) -> bool:
            self.commit_calls += 1
            return True

    ui_flow = _UiFlow()
    editor = SimpleNamespace(
        active=True,
        _find_everything_open=True,
        window=SimpleNamespace(find_everything_overlay=_Overlay()),
    )
    controller = search_module.EditorSearchController(editor, ui_flow)
    controller.set_find_query("ab")

    monkeypatch.setattr(search_module, "apply_backspace", lambda _overlay: False)
    monkeypatch.setattr(search_module, "apply_nav_key", lambda _overlay, _key: False)
    monkeypatch.setattr(search_module, "apply_enter", lambda _overlay: False)
    monkeypatch.setattr(search_module, "apply_text_input", lambda _overlay, _text: False)
    monkeypatch.setattr(search_module, "apply_mouse_press", lambda _overlay, _x, _y, **_kw: True)
    monkeypatch.setattr(search_module, "apply_mouse_scroll", lambda _overlay, _scroll_y, **_kw: False)
    ctrl_n_key = getattr(optional_arcade.arcade.key, "N", None)
    ctrl_p_key = getattr(optional_arcade.arcade.key, "P", None)
    if ctrl_n_key is None or ctrl_p_key is None:
        pytest.skip("arcade key constants N/P unavailable in current test runtime")

    assert controller.handle_find_everything_input(optional_arcade.arcade.key.TAB, 0) is True
    assert toggle_calls == ["tab"]

    assert controller.handle_find_everything_input(optional_arcade.arcade.key.BACKSPACE, 0) is True
    assert ui_flow.query == "a"

    assert controller.handle_find_everything_input(optional_arcade.arcade.key.DOWN, 0) is True
    assert ui_flow.move_calls == [1]
    assert controller.handle_find_everything_input(ctrl_n_key, optional_arcade.arcade.key.MOD_CTRL) is True
    assert ui_flow.move_calls == [1, 1]
    assert controller.handle_find_everything_input(ctrl_p_key, optional_arcade.arcade.key.MOD_CTRL) is True
    assert ui_flow.move_calls == [1, 1, -1]

    assert controller.handle_find_everything_input(optional_arcade.arcade.key.ENTER, 0) is True
    assert ui_flow.commit_calls == 1

    assert controller.append_find_query_text("x") is True
    assert ui_flow.query == "ax"

    assert controller.handle_find_everything_mouse_press(1.0, 2.0, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True
    assert controller.handle_find_everything_mouse_scroll(1.0, 2.0, 0.0, -1.0) is False

    editor._find_everything_open = False
    before = list(ui_flow.move_calls)
    assert controller.handle_find_everything_input(ctrl_n_key, optional_arcade.arcade.key.MOD_CTRL) is False
    assert ui_flow.move_calls == before


def test_editor_scene_browse_controller_helper_parity_fallbacks_and_tab(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_arcade(monkeypatch)
    toggle_calls: list[str] = []
    calls: list[str] = []

    class _Overlay:
        def toggle_focus(self) -> bool:
            toggle_calls.append("tab")
            return True

    editor = SimpleNamespace(
        active=True,
        scene_browser_active=True,
        scene_browser_query="ab",
        scene_browser_index=0,
        scene_switcher_active=False,
        scene_switcher_query="",
        scene_switcher_index=0,
        scene_switcher_recent=[],
        window=SimpleNamespace(scene_browser_overlay=_Overlay(), width=1280, height=720),
    )
    controller = scene_module.EditorSceneBrowseController(editor)

    monkeypatch.setattr(scene_module, "apply_backspace", lambda _overlay: False)
    nav_keys: list[int] = []

    def _apply_nav_key(_overlay: object, key: int) -> bool:
        nav_keys.append(int(key))
        return False

    monkeypatch.setattr(scene_module, "apply_nav_key", _apply_nav_key)
    monkeypatch.setattr(scene_module, "apply_enter", lambda _overlay: False)
    monkeypatch.setattr(scene_module, "apply_text_input", lambda _overlay, _text: False)
    monkeypatch.setattr(scene_module, "apply_mouse_scroll", lambda _overlay, _scroll_y, **_kw: True)
    monkeypatch.setattr(scene_module, "apply_mouse_press", lambda _overlay, _x, _y, **_kw: False)
    monkeypatch.setattr(scene_module, "compute_scene_browser_hit_index", lambda *_a, **_kw: None)

    monkeypatch.setattr(controller, "refresh_scene_browser_rows", lambda: calls.append("refresh"))
    monkeypatch.setattr(controller, "scene_browser_rows", lambda: [1, 2, 3])
    monkeypatch.setattr(controller, "scene_browser_clamp_index", lambda count: calls.append(f"clamp:{int(count)}"))
    monkeypatch.setattr(controller, "scene_browser_open_selected", lambda: (calls.append("open"), True)[1])
    monkeypatch.setattr(controller, "scene_browser_layout", lambda _count: {"left": 0.0, "right": 100.0, "top": 100.0, "bottom": 0.0, "row_start_y": 90.0})
    monkeypatch.setattr(controller, "scene_browser_window", lambda _count: (0, 0))
    ctrl_n_key = getattr(optional_arcade.arcade.key, "N", None)
    ctrl_p_key = getattr(optional_arcade.arcade.key, "P", None)
    if ctrl_n_key is None or ctrl_p_key is None:
        pytest.skip("arcade key constants N/P unavailable in current test runtime")

    assert controller.handle_scene_browser_input(optional_arcade.arcade.key.TAB, 0) is True
    assert toggle_calls == ["tab"]

    assert controller.handle_scene_browser_input(optional_arcade.arcade.key.BACKSPACE, 0) is True
    assert editor.scene_browser_query == "a"
    assert "refresh" in calls
    assert "clamp:3" in calls

    assert controller.handle_scene_browser_input(optional_arcade.arcade.key.DOWN, 0) is True
    assert controller.handle_scene_browser_input(ctrl_n_key, optional_arcade.arcade.key.MOD_CTRL) is True
    assert controller.handle_scene_browser_input(ctrl_p_key, optional_arcade.arcade.key.MOD_CTRL) is True
    assert nav_keys == [
        int(optional_arcade.arcade.key.DOWN),
        int(optional_arcade.arcade.key.DOWN),
        int(optional_arcade.arcade.key.UP),
    ]

    assert controller.handle_scene_browser_input(optional_arcade.arcade.key.ENTER, 0) is True
    assert "open" in calls

    assert controller.handle_scene_browser_text_input("x") is True
    assert editor.scene_browser_query.endswith("x")

    assert controller.handle_scene_browser_mouse_scroll(1.0, 2.0, 0.0, -1.0) is True
    assert controller.scene_browser_handle_mouse_click(1.0, 2.0, optional_arcade.arcade.MOUSE_BUTTON_LEFT) is True

    editor.scene_browser_active = False
    before = list(nav_keys)
    assert controller.handle_scene_browser_input(ctrl_n_key, optional_arcade.arcade.key.MOD_CTRL) is False
    assert nav_keys == before


def test_editor_keybinds_controller_helper_parity_fallbacks_and_tab(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_arcade(monkeypatch)
    calls: list[str] = []

    class _Overlay:
        def toggle_focus(self) -> bool:
            calls.append("tab")
            return True

    editor = SimpleNamespace(window=SimpleNamespace(), _keymap_overrides={}, keybinds_overlay=_Overlay())
    controller = keybinds_module.EditorKeybindsController(editor)
    controller._cached_rows = (
        KeybindRow(
            scope="global",
            action_id="editor.action_a",
            title="Action A",
            shortcut_effective="Ctrl+A",
            shortcut_default="Ctrl+A",
            has_override=False,
            conflict_ids=(),
        ),
        KeybindRow(
            scope="global",
            action_id="editor.action_b",
            title="Action B",
            shortcut_effective="Ctrl+B",
            shortcut_default="Ctrl+B",
            has_override=False,
            conflict_ids=(),
        ),
    )
    controller._rows_dirty = False
    controller.state = KeybindsState(visible=True, query="", selected_index=0, staged_overrides={})

    monkeypatch.setattr(keybinds_module, "apply_nav_key", lambda _overlay, _key: False)
    monkeypatch.setattr(keybinds_module, "apply_enter", lambda _overlay: False)
    monkeypatch.setattr(keybinds_module, "apply_backspace", lambda _overlay: False)
    monkeypatch.setattr(keybinds_module, "apply_text_input", lambda _overlay, _text: False)
    monkeypatch.setattr(keybinds_module, "apply_mouse_press", lambda _overlay, _x, _y, **_kw: True)
    monkeypatch.setattr(keybinds_module, "apply_mouse_scroll", lambda _overlay, _scroll_y, **_kw: False)
    ctrl_n_key = getattr(optional_arcade.arcade.key, "N", None)
    ctrl_p_key = getattr(optional_arcade.arcade.key, "P", None)
    if ctrl_n_key is None or ctrl_p_key is None:
        pytest.skip("arcade key constants N/P unavailable in current test runtime")

    assert controller.handle_input(optional_arcade.arcade.key.TAB, 0) is True
    assert calls == ["tab"]

    assert controller.handle_input(ctrl_n_key, optional_arcade.arcade.key.MOD_CTRL) is True
    assert controller.state.selected_index == 1
    assert controller.handle_input(ctrl_p_key, optional_arcade.arcade.key.MOD_CTRL) is True
    assert controller.state.selected_index == 0

    assert controller.handle_input(optional_arcade.arcade.key.DOWN, 0) is True
    assert controller.state.selected_index == 1

    assert controller.handle_input(optional_arcade.arcade.key.ENTER, 0) is True
    assert controller.state.recording is True
    controller.state = replace(controller.state, recording=False)

    assert controller.handle_input(optional_arcade.arcade.key.BACKSPACE, 0) is True
    assert controller.state.staged_overrides[("global", "editor.action_b")] == ""

    assert controller.on_text("x") is True
    assert controller.state.query == "x"

    assert controller.handle_mouse_press(1.0, 2.0, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True
    assert controller.handle_mouse_scroll(1.0, 2.0, 0.0, -1.0) is False


def test_editor_asset_browser_controller_helper_parity_fallbacks_and_tab(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_arcade(monkeypatch)
    calls: list[str] = []

    class _Overlay:
        def toggle_focus(self) -> bool:
            calls.append("tab")
            return True

    search_state = {"value": "ab"}

    def _get_assets_search() -> str:
        return str(search_state["value"])

    editor = SimpleNamespace(
        active=True,
        asset_browser_active=True,
        scene_switcher_active=False,
        scene_browser_active=False,
        _asset_browser_filtered_rows=[SimpleNamespace(), SimpleNamespace(), SimpleNamespace()],
        _asset_browser_cached_rows=[SimpleNamespace()],
        asset_browser_filter="",
        asset_browser_kind="All",
        asset_browser_selection_index=0,
        search=SimpleNamespace(
            is_panel_search_focused=lambda _panel: False,
            clear_search_focus=lambda: None,
            get_assets_search=_get_assets_search,
            set_assets_search=lambda text: search_state.__setitem__("value", str(text)),
            backspace_search_text=lambda: None,
        ),
        panels=SimpleNamespace(close_command_palette=lambda: None),
        window=SimpleNamespace(asset_browser_overlay=_Overlay()),
        asset_browser_overlay=_Overlay(),
        _autosave_workspace=lambda: None,
    )
    controller = asset_module.EditorAssetBrowserController(editor)

    monkeypatch.setattr(asset_module, "apply_nav_key", lambda _overlay, _key: False)
    monkeypatch.setattr(asset_module, "apply_enter", lambda _overlay: False)
    monkeypatch.setattr(asset_module, "apply_backspace", lambda _overlay: False)
    monkeypatch.setattr(asset_module, "apply_text_input", lambda _overlay, _text: False)
    monkeypatch.setattr(asset_module, "apply_mouse_press", lambda _overlay, _x, _y, **_kw: True)
    monkeypatch.setattr(asset_module, "apply_mouse_scroll", lambda _overlay, _scroll_y, **_kw: False)
    ctrl_n_key = getattr(optional_arcade.arcade.key, "N", None)
    ctrl_p_key = getattr(optional_arcade.arcade.key, "P", None)
    if ctrl_n_key is None or ctrl_p_key is None:
        pytest.skip("arcade key constants N/P unavailable in current test runtime")

    monkeypatch.setattr(controller, "_activate_selected_asset", lambda: calls.append("activate"))
    monkeypatch.setattr(controller, "set_asset_browser_filter", lambda text: calls.append(f"filter:{text}"))

    assert controller.handle_asset_browser_input(optional_arcade.arcade.key.TAB, 0) is True
    assert calls == ["tab"]

    assert controller.handle_asset_browser_input(ctrl_n_key, optional_arcade.arcade.key.MOD_CTRL) is True
    assert editor.asset_browser_selection_index == 1
    assert controller.handle_asset_browser_input(ctrl_p_key, optional_arcade.arcade.key.MOD_CTRL) is True
    assert editor.asset_browser_selection_index == 0

    assert controller.handle_asset_browser_input(optional_arcade.arcade.key.DOWN, 0) is True
    assert editor.asset_browser_selection_index == 1

    editor.asset_browser_active = False
    selected_before = int(editor.asset_browser_selection_index)
    assert controller.handle_asset_browser_input(ctrl_n_key, optional_arcade.arcade.key.MOD_CTRL) is True
    assert editor.asset_browser_selection_index == selected_before
    editor.asset_browser_active = True

    assert controller.handle_asset_browser_input(optional_arcade.arcade.key.ENTER, 0) is True
    assert "activate" in calls

    assert controller.handle_asset_browser_input(optional_arcade.arcade.key.BACKSPACE, 0) is True

    assert controller.handle_asset_browser_text_input("x") is True
    assert "filter:abx" in calls

    assert controller.handle_asset_browser_mouse_click(1.0, 2.0, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True
    assert controller.handle_asset_browser_mouse_scroll(1.0, 2.0, 0.0, -1.0) is False
