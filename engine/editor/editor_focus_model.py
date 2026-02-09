"""Pure focus model for editor focus, text input, and shortcut scopes."""
from __future__ import annotations

from typing import Any, Mapping

from engine.editor.editor_dock_focus_model import derive_focus_from_dock
from engine.editor.editor_dock_query import get_dock_snapshot
from engine.editor.editor_panels_query import panels_is_open
from engine.editor.editor_session_query import get_session_snapshot
from engine.editor.shortcut_resolver_model import (
    SHORTCUT_SCOPE_GLOBAL,
    SHORTCUT_SCOPE_INLINE_RENAME,
    SHORTCUT_SCOPE_PROJECT_EXPLORER,
    SHORTCUT_SCOPE_PROJECT_EXPLORER_CONTEXT_MENU,
)

FocusTarget = str

FOCUS_NONE: FocusTarget = "none"
FOCUS_PROJECT_EXPLORER: FocusTarget = "project_explorer"
FOCUS_PROJECT_EXPLORER_CONTEXT_MENU: FocusTarget = "project_explorer_context_menu"
FOCUS_PROBLEMS: FocusTarget = "problems"
FOCUS_COMMAND_PALETTE: FocusTarget = "command_palette"
FOCUS_INLINE_RENAME: FocusTarget = "inline_rename"
FOCUS_INSPECTOR: FocusTarget = "inspector"
FOCUS_OUTLINER: FocusTarget = "outliner"
FOCUS_ASSETS: FocusTarget = "assets"
FOCUS_HISTORY: FocusTarget = "history"
FOCUS_SCENE_BROWSER: FocusTarget = "scene_browser"
FOCUS_ASSET_BROWSER: FocusTarget = "asset_browser"
FOCUS_PALETTE: FocusTarget = "palette"
FOCUS_ENTITY_PANELS: FocusTarget = "entity_panels"
FOCUS_SCENE_SWITCHER: FocusTarget = "scene_switcher"
FOCUS_DEBUG: FocusTarget = "debug"

_SEARCH_FOCUS_MAP: dict[str, FocusTarget] = {
    "project": FOCUS_PROJECT_EXPLORER,
    "outliner": FOCUS_OUTLINER,
    "assets": FOCUS_ASSETS,
    "history": FOCUS_HISTORY,
    "problems": FOCUS_PROBLEMS,
    "debug": FOCUS_DEBUG,
}

_STATE_KEYS: tuple[str, ...] = (
    "palette_filter_active",
    "hierarchy_filter_active",
    "hierarchy_rename_active",
    "animation_edit_active",
    "inspector_edit_active",
    "entity_panels_filter_active",
    "entity_panels_text_edit_active",
    "scene_browser_filter_active",
    "asset_browser_filter_active",
    "scene_browser_active",
    "asset_browser_active",
    "scene_switcher_active",
    "search",
    "search_focus",
    "dock",
    "project_explorer",
    "panels",
    "ui_layers",
)


def collect_editor_state(source: Any) -> dict[str, Any]:
    """Legacy helper: avoid using outside this module."""
    if isinstance(source, Mapping):
        state = dict(source)
    else:
        state = {}
    for key in _STATE_KEYS:
        if key not in state:
            state[key] = getattr(source, key, None)
    return state


def derive_focus_target_for_controller(
    controller: Any, session_snapshot: Any | None = None
) -> FocusTarget:
    if session_snapshot is None:
        session_snapshot = get_session_snapshot(controller)
    if panels_is_open(controller, "project_context_menu"):
        return FOCUS_PROJECT_EXPLORER_CONTEXT_MENU
    project_ctrl = getattr(controller, "project_explorer", None)
    if project_ctrl is not None and getattr(project_ctrl, "inline_rename_active", False) is True:
        return FOCUS_INLINE_RENAME
    if panels_is_open(controller, "command_palette"):
        return FOCUS_COMMAND_PALETTE
    if getattr(controller, "scene_browser_active", False) is True:
        return FOCUS_SCENE_BROWSER
    if getattr(controller, "asset_browser_active", False) is True:
        return FOCUS_ASSET_BROWSER
    if getattr(controller, "scene_switcher_active", False) is True:
        return FOCUS_SCENE_SWITCHER
    if getattr(controller, "palette_filter_active", False) is True:
        return FOCUS_PALETTE
    if getattr(controller, "hierarchy_filter_active", False) is True:
        return FOCUS_OUTLINER
    if getattr(controller, "hierarchy_rename_active", False) is True:
        return FOCUS_OUTLINER
    if getattr(controller, "inspector_edit_active", False) is True:
        return FOCUS_INSPECTOR
    if getattr(controller, "entity_panels_filter_active", False) is True:
        return FOCUS_ENTITY_PANELS
    if getattr(controller, "entity_panels_text_edit_active", False) is True:
        return FOCUS_ENTITY_PANELS
    if getattr(controller, "scene_browser_filter_active", False) is True:
        return FOCUS_SCENE_BROWSER
    if getattr(controller, "asset_browser_filter_active", False) is True:
        return FOCUS_ASSET_BROWSER

    search = getattr(controller, "search", None)
    focus_value = ""
    if search is not None:
        getter = getattr(search, "get_search_focus", None)
        if callable(getter):
            focus_value = getter()
    if isinstance(focus_value, str) and focus_value:
        mapped = _SEARCH_FOCUS_MAP.get(focus_value)
        if mapped:
            return mapped

    dock_snapshot = get_dock_snapshot(controller)
    left_tab = getattr(dock_snapshot, "left_tab", "") if dock_snapshot is not None else ""
    right_tab = getattr(dock_snapshot, "right_tab", "") if dock_snapshot is not None else ""
    session_flags = {
        "project_explorer_focused": bool(getattr(session_snapshot, "project_explorer_focused", False)),
    }
    return derive_focus_from_dock(left_tab or "", right_tab or "", session_flags)


def derive_focus_target(editor_state_dict: Mapping[str, Any], session_snapshot: Any) -> FocusTarget:
    if panels_is_open(editor_state_dict, "project_context_menu"):
        return FOCUS_PROJECT_EXPLORER_CONTEXT_MENU
    project_ctrl = editor_state_dict.get("project_explorer")
    if project_ctrl is not None and getattr(project_ctrl, "inline_rename_active", False) is True:
        return FOCUS_INLINE_RENAME
    if panels_is_open(editor_state_dict, "command_palette"):
        return FOCUS_COMMAND_PALETTE
    if editor_state_dict.get("scene_browser_active", False) is True:
        return FOCUS_SCENE_BROWSER
    if editor_state_dict.get("asset_browser_active", False) is True:
        return FOCUS_ASSET_BROWSER
    if editor_state_dict.get("scene_switcher_active", False) is True:
        return FOCUS_SCENE_SWITCHER
    if editor_state_dict.get("palette_filter_active", False) is True:
        return FOCUS_PALETTE
    if editor_state_dict.get("hierarchy_filter_active", False) is True:
        return FOCUS_OUTLINER
    if editor_state_dict.get("hierarchy_rename_active", False) is True:
        return FOCUS_OUTLINER
    if editor_state_dict.get("inspector_edit_active", False) is True:
        return FOCUS_INSPECTOR
    if editor_state_dict.get("entity_panels_filter_active", False) is True:
        return FOCUS_ENTITY_PANELS
    if editor_state_dict.get("entity_panels_text_edit_active", False) is True:
        return FOCUS_ENTITY_PANELS
    if editor_state_dict.get("scene_browser_filter_active", False) is True:
        return FOCUS_SCENE_BROWSER
    if editor_state_dict.get("asset_browser_filter_active", False) is True:
        return FOCUS_ASSET_BROWSER

    search_obj = editor_state_dict.get("search")
    search_focus = ""
    if search_obj is not None:
        getter = getattr(search_obj, "get_search_focus", None)
        if callable(getter):
            search_focus = getter()
    if not search_focus:
        search_focus = editor_state_dict.get("search_focus", "")
    if isinstance(search_focus, str) and search_focus:
        mapped = _SEARCH_FOCUS_MAP.get(search_focus)
        if mapped:
            return mapped

    dock = editor_state_dict.get("dock")
    left_tab = ""
    right_tab = ""
    if dock is not None:
        snapshot = dock.get_snapshot()
        left_tab = getattr(snapshot, "left_tab", "") or ""
        right_tab = getattr(snapshot, "right_tab", "") or ""
    session_flags = {
        "project_explorer_focused": bool(getattr(session_snapshot, "project_explorer_focused", False)),
    }
    return derive_focus_from_dock(left_tab, right_tab, session_flags)


def is_text_input_active(focus_target: FocusTarget, editor_state_dict: Mapping[str, Any]) -> bool:
    if focus_target in (FOCUS_INLINE_RENAME, FOCUS_COMMAND_PALETTE):
        return True
    if editor_state_dict.get("palette_filter_active", False) is True:
        return True
    if editor_state_dict.get("hierarchy_filter_active", False) is True:
        return True
    if editor_state_dict.get("hierarchy_rename_active", False) is True:
        return True
    if editor_state_dict.get("animation_edit_active", False) is True:
        return True
    if editor_state_dict.get("inspector_edit_active", False) is True:
        return True
    if editor_state_dict.get("entity_panels_filter_active", False) is True:
        return True
    if editor_state_dict.get("entity_panels_text_edit_active", False) is True:
        return True
    if editor_state_dict.get("scene_browser_filter_active", False) is True:
        return True
    if editor_state_dict.get("asset_browser_filter_active", False) is True:
        return True

    search_obj = editor_state_dict.get("search")
    search_focus = ""
    if search_obj is not None:
        getter = getattr(search_obj, "get_search_focus", None)
        if callable(getter):
            search_focus = getter()
    if not search_focus:
        search_focus = editor_state_dict.get("search_focus", "")
    if isinstance(search_focus, str) and search_focus:
        return True

    project_ctrl = editor_state_dict.get("project_explorer")
    if project_ctrl is not None and getattr(project_ctrl, "inline_rename_active", False) is True:
        return True

    return False


def is_text_input_active_for_controller(focus_target: FocusTarget, controller: Any) -> bool:
    if focus_target in (FOCUS_INLINE_RENAME, FOCUS_COMMAND_PALETTE):
        return True
    if getattr(controller, "palette_filter_active", False) is True:
        return True
    if getattr(controller, "hierarchy_filter_active", False) is True:
        return True
    if getattr(controller, "hierarchy_rename_active", False) is True:
        return True
    if getattr(controller, "animation_edit_active", False) is True:
        return True
    if getattr(controller, "inspector_edit_active", False) is True:
        return True
    if getattr(controller, "entity_panels_filter_active", False) is True:
        return True
    if getattr(controller, "entity_panels_text_edit_active", False) is True:
        return True
    if getattr(controller, "scene_browser_filter_active", False) is True:
        return True
    if getattr(controller, "asset_browser_filter_active", False) is True:
        return True

    search = getattr(controller, "search", None)
    getter = getattr(search, "get_search_focus", None) if search is not None else None
    search_focus = getter() if callable(getter) else ""
    if isinstance(search_focus, str) and search_focus:
        return True

    project_ctrl = getattr(controller, "project_explorer", None)
    if project_ctrl is not None and getattr(project_ctrl, "inline_rename_active", False) is True:
        return True

    return False


def compute_active_shortcut_scopes(
    focus_target: FocusTarget, editor_state_dict: Mapping[str, Any]
) -> tuple[str, ...]:
    scopes: list[str] = []
    if focus_target == FOCUS_INLINE_RENAME:
        scopes.append(SHORTCUT_SCOPE_INLINE_RENAME)
    if focus_target == FOCUS_PROJECT_EXPLORER_CONTEXT_MENU:
        scopes.append(SHORTCUT_SCOPE_PROJECT_EXPLORER_CONTEXT_MENU)
    if focus_target == FOCUS_PROJECT_EXPLORER:
        scopes.append(SHORTCUT_SCOPE_PROJECT_EXPLORER)
    if focus_target != FOCUS_PROJECT_EXPLORER_CONTEXT_MENU:
        scopes.append(SHORTCUT_SCOPE_GLOBAL)
    return tuple(scopes)
