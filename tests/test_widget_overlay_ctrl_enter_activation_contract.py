from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

import engine.optional_arcade as optional_arcade
from engine.editor import (
    editor_asset_browser_controller as asset_module,
)
from engine.editor import (
    editor_keybinds_controller as keybinds_module,
)
from engine.editor import (
    editor_scene_browse_controller as scene_module,
)
from engine.editor import (
    editor_search_controller as search_module,
)
from engine.editor.keybinds_ui_model import KeybindRow, KeybindsState

pytestmark = [pytest.mark.fast]


def _stub_arcade(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine import arcade_fallback as arcade_stub

    monkeypatch.setattr(optional_arcade, "arcade", arcade_stub)


def test_ctrl_enter_find_everything_activates_regardless_of_focus(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_arcade(monkeypatch)

    class _Overlay:
        def __init__(self) -> None:
            self.calls = 0

        def on_key_enter(self) -> bool:
            return True

        def activate_selected(self) -> bool:
            self.calls += 1
            return True

    class _UiFlow:
        def __init__(self) -> None:
            self.query = ""
            self.is_open = True

        def update_query(self, text: str) -> None:
            self.query = str(text or "")

        def move_selection(self, delta: int) -> None:  # noqa: ARG002
            return None

        def commit_selection(self) -> bool:
            return True

    overlay = _Overlay()
    editor = SimpleNamespace(
        active=True,
        _find_everything_open=True,
        _find_everything_query="",
        window=SimpleNamespace(find_everything_overlay=overlay),
    )
    controller = search_module.EditorSearchController(editor, _UiFlow())
    monkeypatch.setattr(search_module, "apply_enter", lambda _overlay: True)

    assert controller.handle_find_everything_input(optional_arcade.arcade.key.ENTER, 0) is True
    assert overlay.calls == 0
    assert controller.handle_find_everything_input(optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.MOD_CTRL) is True
    assert overlay.calls == 1

    editor._find_everything_open = False
    assert controller.handle_find_everything_input(optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.MOD_CTRL) is False
    assert overlay.calls == 1


def test_ctrl_enter_scene_browser_activates_regardless_of_focus(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_arcade(monkeypatch)

    class _Overlay:
        def __init__(self) -> None:
            self.calls = 0

        def on_key_enter(self) -> bool:
            return True

        def activate_selected(self) -> bool:
            self.calls += 1
            return True

    overlay = _Overlay()
    editor = SimpleNamespace(
        scene_browser_active=True,
        scene_browser_query="",
        scene_browser_index=0,
        scene_switcher_active=False,
        scene_switcher_query="",
        scene_switcher_index=0,
        scene_switcher_recent=[],
        window=SimpleNamespace(scene_browser_overlay=overlay),
    )
    controller = scene_module.EditorSceneBrowseController(editor)
    monkeypatch.setattr(scene_module, "apply_enter", lambda _overlay: True)

    assert controller.handle_scene_browser_input(optional_arcade.arcade.key.ENTER, 0) is True
    assert overlay.calls == 0
    assert controller.handle_scene_browser_input(optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.MOD_CTRL) is True
    assert overlay.calls == 1

    editor.scene_browser_active = False
    assert controller.handle_scene_browser_input(optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.MOD_CTRL) is False
    assert overlay.calls == 1


def test_ctrl_enter_keybinds_activates_regardless_of_focus(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_arcade(monkeypatch)

    class _Overlay:
        def __init__(self) -> None:
            self.calls = 0

        def on_key_enter(self) -> bool:
            return True

        def activate_selected(self) -> bool:
            self.calls += 1
            return True

    overlay = _Overlay()
    editor = SimpleNamespace(window=SimpleNamespace(), _keymap_overrides={}, keybinds_overlay=overlay)
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
    )
    controller._rows_dirty = False
    controller.state = KeybindsState(visible=True, query="", selected_index=0, staged_overrides={})

    monkeypatch.setattr(keybinds_module, "apply_enter", lambda _overlay: True)

    assert controller.handle_input(optional_arcade.arcade.key.ENTER, 0) is True
    assert overlay.calls == 0
    assert controller.handle_input(optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.MOD_CTRL) is True
    assert overlay.calls == 1

    controller.state = replace(controller.state, visible=False)
    assert controller.handle_input(optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.MOD_CTRL) is True
    assert overlay.calls == 1


def test_ctrl_enter_asset_browser_activates_regardless_of_focus(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_arcade(monkeypatch)

    class _Overlay:
        def __init__(self) -> None:
            self.calls = 0

        def on_key_enter(self) -> bool:
            return True

        def activate_selected(self) -> bool:
            self.calls += 1
            return True

    overlay = _Overlay()
    editor = SimpleNamespace(
        active=True,
        asset_browser_active=True,
        scene_switcher_active=False,
        scene_browser_active=False,
        _asset_browser_filtered_rows=[SimpleNamespace()],
        _asset_browser_cached_rows=[SimpleNamespace()],
        asset_browser_filter="",
        asset_browser_kind="All",
        asset_browser_selection_index=0,
        search=SimpleNamespace(
            is_panel_search_focused=lambda _panel: False,
            clear_search_focus=lambda: None,
            get_assets_search=lambda: "",
            set_assets_search=lambda _text: None,
            backspace_search_text=lambda: None,
        ),
        panels=SimpleNamespace(close_command_palette=lambda: None),
        window=SimpleNamespace(asset_browser_overlay=overlay),
        asset_browser_overlay=overlay,
        _autosave_workspace=lambda: None,
    )
    controller = asset_module.EditorAssetBrowserController(editor)
    monkeypatch.setattr(asset_module, "apply_enter", lambda _overlay: True)

    assert controller.handle_asset_browser_input(optional_arcade.arcade.key.ENTER, 0) is True
    assert overlay.calls == 0
    assert controller.handle_asset_browser_input(optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.MOD_CTRL) is True
    assert overlay.calls == 1

    editor.asset_browser_active = False
    assert controller.handle_asset_browser_input(optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.MOD_CTRL) is True
    assert overlay.calls == 1
