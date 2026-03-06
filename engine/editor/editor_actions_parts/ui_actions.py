"""UI panel toggle, dock tab, browser, lighting preset, fog, shadow action handlers."""

from __future__ import annotations

from typing import Any

from engine.editor import editor_actions_camera as _camera_actions
from engine.editor import editor_actions_entities as _entity_actions
from engine.editor.editor_actions_parts._shared import _get_editor, _is_web_runtime
from engine.editor.editor_dock_query import get_dock_snapshot
from engine.runtime_settings import ensure_runtime_settings

__all__ = [
    "_toggle_lights_tool",
    "_toggle_occluder_tool",
    "_toggle_entity_panels",
    "_set_dock_tab",
    "_toggle_dock_tab",
    "_toggle_inspector_panel",
    "_toggle_outliner_panel",
    "_toggle_history_panel",
    "_toggle_problems_panel",
    "_toggle_debug_panel",
    "_action_problems_jump",
    "_action_problems_copy_location",
    "_toggle_project_explorer_panel",
    "_toggle_prefab_variant_editor",
    "_toggle_scene_switcher",
    "_toggle_find_everything",
    "_toggle_left_dock",
    "_toggle_right_dock",
    "_toggle_viewport_maximized",
    "_open_scene_browser",
    "_apply_lighting_preset",
    "_action_apply_lighting_preset_0",
    "_action_apply_lighting_preset_1",
    "_action_apply_lighting_preset_2",
    "_action_apply_lighting_preset_3",
    "_toggle_fog",
    "_toggle_soft_shadows",
    "_toggle_asset_browser",
    "_toggle_command_palette",
    "_open_keybinds",
    "_toggle_ghost_originals",
    "_toggle_prefab_palette",
]


def _toggle_lights_tool(window: Any) -> None:
    editor = _get_editor(window)
    toggler = getattr(editor, "toggle_lights_tool", None) if editor is not None else None
    if callable(toggler):
        toggler()


def _toggle_occluder_tool(window: Any) -> None:
    editor = _get_editor(window)
    toggler = getattr(editor, "toggle_occluder_tool", None) if editor is not None else None
    if callable(toggler):
        toggler()


def _toggle_entity_panels(window: Any) -> None:
    _entity_actions._toggle_entity_panels(window, _get_editor)


def _set_dock_tab(window: Any, dock: str, tab: str) -> None:
    _camera_actions._set_dock_tab(window, dock, tab, _get_editor)


def _toggle_dock_tab(window: Any, dock: str, tab: str) -> None:
    _camera_actions._toggle_dock_tab(window, dock, tab, _get_editor, get_dock_snapshot, _set_dock_tab)


def _toggle_inspector_panel(window: Any) -> None:
    _camera_actions._toggle_inspector_panel(window, _toggle_dock_tab)


def _toggle_outliner_panel(window: Any) -> None:
    _camera_actions._toggle_outliner_panel(window, _toggle_dock_tab)


def _toggle_history_panel(window: Any) -> None:
    _camera_actions._toggle_history_panel(window, _toggle_dock_tab)


def _toggle_problems_panel(window: Any) -> None:
    _camera_actions._toggle_problems_panel(window, _toggle_dock_tab)


def _toggle_debug_panel(window: Any) -> None:
    _camera_actions._toggle_debug_panel(window, _toggle_dock_tab)


def _action_problems_jump(window: Any) -> None:
    """Jump to the currently selected problem (EditorAction handler)."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    jumper = getattr(editor, "problems_jump_to_selected", None)
    if callable(jumper):
        jumper()


def _action_problems_copy_location(window: Any) -> None:
    """Copy the selected problem's location to clipboard (EditorAction handler)."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    copier = getattr(editor, "problems_copy_location", None)
    if callable(copier):
        copier()


def _toggle_project_explorer_panel(window: Any) -> None:
    _camera_actions._toggle_project_explorer_panel(window, _toggle_dock_tab)


def _toggle_prefab_variant_editor(window: Any) -> None:
    _toggle_dock_tab(window, "right", "Inspector")


def _toggle_scene_switcher(window: Any) -> None:
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    toggler = getattr(editor, "toggle_scene_switcher", None)
    if callable(toggler):
        toggler()


def _toggle_find_everything(window: Any) -> None:
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    toggler = getattr(editor, "toggle_find_everything", None)
    if callable(toggler):
        toggler()


def _toggle_left_dock(window: Any) -> None:
    _camera_actions._toggle_left_dock(window, _get_editor)


def _toggle_right_dock(window: Any) -> None:
    _camera_actions._toggle_right_dock(window, _get_editor)


def _toggle_viewport_maximized(window: Any) -> None:
    _camera_actions._toggle_viewport_maximized(window, _get_editor)


def _open_scene_browser(window: Any) -> None:
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    toggler = getattr(editor, "toggle_scene_browser", None)
    if callable(toggler):
        toggler()


def _apply_lighting_preset(window: Any, index: int) -> None:
    editor = _get_editor(window)
    apply_fn = getattr(editor, "apply_lighting_preset_hotkey", None) if editor is not None else None
    if callable(apply_fn):
        apply_fn(int(index))


def _action_apply_lighting_preset_0(window: Any) -> None:
    _apply_lighting_preset(window, 0)


def _action_apply_lighting_preset_1(window: Any) -> None:
    _apply_lighting_preset(window, 1)


def _action_apply_lighting_preset_2(window: Any) -> None:
    _apply_lighting_preset(window, 2)


def _action_apply_lighting_preset_3(window: Any) -> None:
    _apply_lighting_preset(window, 3)


def _toggle_fog(window: Any) -> None:
    settings = ensure_runtime_settings(window)
    settings.fog_enabled = not bool(settings.fog_enabled)
    settings.apply(window)


def _toggle_soft_shadows(window: Any) -> None:
    settings = ensure_runtime_settings(window)
    settings.soft_shadows_enabled = not bool(settings.soft_shadows_enabled)
    settings.apply(window)


def _toggle_asset_browser(window: Any) -> None:
    editor = _get_editor(window)
    toggler = getattr(editor, "toggle_asset_browser", None) if editor is not None else None
    if callable(toggler):
        toggler()


def _toggle_command_palette(window: Any) -> None:
    editor = _get_editor(window)
    toggler = getattr(editor, "toggle_command_palette", None) if editor is not None else None
    if callable(toggler):
        toggler()
        return
    if editor is None:
        return
    panels = getattr(editor, "panels", None)
    if panels and hasattr(panels, "toggle_command_palette"):
        if panels.toggle_command_palette():
            search = getattr(editor, "search", None)
            if search is not None:
                clear = getattr(search, "clear_command_palette_state", None)
                if callable(clear):
                    clear()
        return


def _open_keybinds(window: Any) -> None:
    editor = _get_editor(window)
    if editor:
        panels = getattr(editor, "panels", None)
        if panels and hasattr(panels, "open_keybinds"):
            panels.open_keybinds()
            return


def _toggle_ghost_originals(window: Any) -> None:
    editor = _get_editor(window)
    toggler = getattr(editor, "toggle_ghost_originals", None) if editor is not None else None
    if callable(toggler):
        toggler()


def _toggle_prefab_palette(window: Any) -> None:
    _entity_actions._toggle_prefab_palette(window, _get_editor)
