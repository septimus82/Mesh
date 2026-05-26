from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import engine.optional_arcade as optional_arcade
from engine.editor.editor_inspector_input_controller import EditorInspectorInputController
from engine.editor.editor_item_editor_controller import EditorItemEditorController
from engine.editor.editor_shell_layout import DOCK_WIDTH, compute_editor_shell_layout
from engine.editor_runtime import editor_input_click_handlers
from engine.editor_runtime.editor_database_form_input import dispatch_database_form_click
from tests._dock_stub import make_dock_stub


pytestmark = [pytest.mark.fast]


class _SceneController:
    def __init__(self, scene: dict[str, Any] | None = None) -> None:
        self._loaded_scene_data = scene or {"settings": {"shadows_enabled": True}, "entities": []}
        self.all_sprites: list[Any] = []


class _Window:
    width = 1280
    height = 720

    def __init__(self, scene: dict[str, Any] | None = None) -> None:
        self.scene_controller = _SceneController(scene)
        self.editor_controller: Any | None = None
        self.world_clicks: list[tuple[float, float]] = []

    def screen_to_world(self, x: float, y: float) -> tuple[float, float]:
        self.world_clicks.append((x, y))
        return (x + 1000.0, y + 1000.0)


def _right_dock_point(row_offset: float = 40.0) -> tuple[float, float]:
    dock = compute_editor_shell_layout(1280, 720, DOCK_WIDTH, DOCK_WIDTH).right_dock
    return (dock.left + 24.0, dock.top - row_offset)


def _editor(*, right_tab: str = "Inspector", scene: dict[str, Any] | None = None) -> SimpleNamespace:
    window = _Window(scene)
    editor = SimpleNamespace(
        active=True,
        dock=make_dock_stub(right_tab=right_tab),
        window=window,
        _primary_selected_id=None,
        _selected_entity_ids=[],
        _hd2d_panel_sections_expanded={},
        _inspector_sections_expanded={},
        _inspector_cursor=("transform", 0),
        _mark_dirty=lambda: None,
        _push_command=lambda _cmd: None,
    )
    window.editor_controller = editor
    return editor


def test_click_inside_inspector_routes_to_inspector_input(monkeypatch: pytest.MonkeyPatch) -> None:
    editor = _editor()
    calls: list[tuple[float, float, int]] = []
    editor._inspector_handle_mouse_click = lambda x, y, button: calls.append((x, y, button)) or True
    for name in ("_handle_menu_bar_click", "_handle_top_bar_controls_click", "_handle_splitter_click", "_handle_dock_tab_click"):
        monkeypatch.setattr(editor_input_click_handlers, name, lambda *_args: None)

    x, y = _right_dock_point()

    assert editor_input_click_handlers.handle_mouse_click(editor, x, y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True
    assert calls == [(x, y, optional_arcade.arcade.MOUSE_BUTTON_LEFT)]


def test_hd2d_toggle_click_flips_scene_setting() -> None:
    editor = _editor(scene={"settings": {"shadows_enabled": True}, "entities": []})
    controller = EditorInspectorInputController(editor)
    x, y = _right_dock_point(92.0)

    assert controller.handle_mouse_click(x, y, optional_arcade.arcade.MOUSE_BUTTON_LEFT) is True
    assert editor.window.scene_controller._loaded_scene_data["settings"]["shadows_enabled"] is False


def test_hd2d_preset_button_click_applies_preset() -> None:
    editor = _editor(scene={"settings": {}, "entities": []})
    controller = EditorInspectorInputController(editor)
    x, y = _right_dock_point(388.0)

    assert controller.handle_mouse_click(x, y, optional_arcade.arcade.MOUSE_BUTTON_LEFT) is True
    settings = editor.window.scene_controller._loaded_scene_data["settings"]
    assert settings["depth_tint_enabled"] is True
    assert settings["shadows_enabled"] is True


def test_hd2d_header_click_toggles_section_expansion() -> None:
    editor = _editor()
    controller = EditorInspectorInputController(editor)
    x, y = _right_dock_point(66.0)

    assert controller.handle_mouse_click(x, y, optional_arcade.arcade.MOUSE_BUTTON_LEFT) is True
    assert editor._hd2d_panel_sections_expanded["shadows"] is False


def test_right_dock_content_guard_consumes_unhandled_click(monkeypatch: pytest.MonkeyPatch) -> None:
    editor = _editor()
    editor._inspector_handle_mouse_click = lambda *_args: False
    for name in ("_handle_menu_bar_click", "_handle_top_bar_controls_click", "_handle_splitter_click", "_handle_dock_tab_click"):
        monkeypatch.setattr(editor_input_click_handlers, name, lambda *_args: None)
    x, y = _right_dock_point()

    assert editor_input_click_handlers.handle_mouse_click(editor, x, y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True
    assert editor.window.world_clicks == []


def test_viewport_click_still_reaches_world_space(monkeypatch: pytest.MonkeyPatch) -> None:
    editor = _editor()
    editor._inspector_handle_mouse_click = lambda *_args: False
    editor.shape_edit_mode = False
    editor.tile_panel_active = False
    editor.asset_place_active = False
    editor.occluder_tool_active = False
    editor.lights_tool_active = False
    editor.palette_active = False
    editor.tool_mode = "SELECT"
    editor.selected_entity = None
    editor.begin_marquee = lambda *_args: None
    editor._find_everything_open = False
    editor.asset_browser_active = False
    for name in ("_handle_menu_bar_click", "_handle_top_bar_controls_click", "_handle_splitter_click", "_handle_dock_tab_click"):
        monkeypatch.setattr(editor_input_click_handlers, name, lambda *_args: None)

    assert editor_input_click_handlers.handle_mouse_click(editor, 640.0, 360.0, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True
    assert editor.window.world_clicks == [(640.0, 360.0)]


class _ItemOverlay:
    def selected_item_dict(self) -> dict[str, Any]:
        return {"id": "potion", "name": "Potion", "description": "", "icon": None, "max_stack": 1, "stackable": False}

    def all_item_dicts(self) -> list[dict[str, Any]]:
        return [self.selected_item_dict()]


def test_item_edit_button_click_routes_when_not_in_edit_mode() -> None:
    window = SimpleNamespace(item_editor_overlay=_ItemOverlay())
    editor = SimpleNamespace(
        dock=make_dock_stub(right_tab="Items"),
        window=window,
        feedback=SimpleNamespace(info=lambda *_args, **_kwargs: None, error=lambda *_args, **_kwargs: None),
        _get_repo_root=lambda: Path("."),
    )
    item_editor = EditorItemEditorController(editor)
    editor.item_editor = item_editor
    item_editor.set_button_rects({"edit": SimpleNamespace(contains=lambda _x, _y: True)})

    assert item_editor.is_edit_mode_active() is False
    assert dispatch_database_form_click(editor, 10.0, 10.0) is True
    assert item_editor.is_edit_mode_active() is True
