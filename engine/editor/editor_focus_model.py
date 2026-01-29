"""Pure focus model for editor focus, text input, and shortcut scopes."""
from __future__ import annotations

from typing import Any, Mapping

from engine.editor.shortcut_resolver_model import (
    SHORTCUT_SCOPE_GLOBAL,
    SHORTCUT_SCOPE_INLINE_RENAME,
)

FocusTarget = str

FOCUS_NONE: FocusTarget = "none"
FOCUS_PROJECT_EXPLORER: FocusTarget = "project_explorer"
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

_SEARCH_FOCUS_MAP: dict[str, FocusTarget] = {
    "project": FOCUS_PROJECT_EXPLORER,
    "outliner": FOCUS_OUTLINER,
    "assets": FOCUS_ASSETS,
    "history": FOCUS_HISTORY,
    "problems": FOCUS_PROBLEMS,
}

_STATE_KEYS: tuple[str, ...] = (
    "palette_filter_active",
    "hierarchy_filter_active",
    "hierarchy_rename_active",
    "animation_edit_active",
    "inspector_edit_active",
    "command_palette_active",
    "entity_panels_filter_active",
    "entity_panels_text_edit_active",
    "scene_browser_filter_active",
    "asset_browser_filter_active",
    "scene_browser_active",
    "asset_browser_active",
    "scene_switcher_active",
    "_search_focus",
    "_left_dock_tab",
    "_right_dock_tab",
    "project_explorer",
)


def _get_state(state: Mapping[str, Any], key: str, default: Any = None) -> Any:
    try:
        return state.get(key, default)
    except Exception:
        return default


def collect_editor_state(source: Any) -> dict[str, Any]:
    if isinstance(source, Mapping):
        state = dict(source)
    else:
        state = {}
    for key in _STATE_KEYS:
        if key not in state:
            state[key] = getattr(source, key, None)
    return state


def derive_focus_target(editor_state_dict: Mapping[str, Any]) -> FocusTarget:
    project_ctrl = _get_state(editor_state_dict, "project_explorer")
    if project_ctrl is not None and getattr(project_ctrl, "inline_rename_active", False) is True:
        return FOCUS_INLINE_RENAME
    if _get_state(editor_state_dict, "command_palette_active", False) is True:
        return FOCUS_COMMAND_PALETTE
    if _get_state(editor_state_dict, "scene_browser_active", False) is True:
        return FOCUS_SCENE_BROWSER
    if _get_state(editor_state_dict, "asset_browser_active", False) is True:
        return FOCUS_ASSET_BROWSER
    if _get_state(editor_state_dict, "scene_switcher_active", False) is True:
        return FOCUS_SCENE_SWITCHER
    if _get_state(editor_state_dict, "palette_filter_active", False) is True:
        return FOCUS_PALETTE
    if _get_state(editor_state_dict, "hierarchy_filter_active", False) is True:
        return FOCUS_OUTLINER
    if _get_state(editor_state_dict, "hierarchy_rename_active", False) is True:
        return FOCUS_OUTLINER
    if _get_state(editor_state_dict, "inspector_edit_active", False) is True:
        return FOCUS_INSPECTOR
    if _get_state(editor_state_dict, "entity_panels_filter_active", False) is True:
        return FOCUS_ENTITY_PANELS
    if _get_state(editor_state_dict, "entity_panels_text_edit_active", False) is True:
        return FOCUS_ENTITY_PANELS
    if _get_state(editor_state_dict, "scene_browser_filter_active", False) is True:
        return FOCUS_SCENE_BROWSER
    if _get_state(editor_state_dict, "asset_browser_filter_active", False) is True:
        return FOCUS_ASSET_BROWSER

    search_focus = _get_state(editor_state_dict, "_search_focus", "")
    if isinstance(search_focus, str) and search_focus:
        mapped = _SEARCH_FOCUS_MAP.get(search_focus)
        if mapped:
            return mapped

    left_tab = _get_state(editor_state_dict, "_left_dock_tab", "")
    if left_tab == "Project":
        return FOCUS_PROJECT_EXPLORER
    if left_tab == "Outliner":
        return FOCUS_OUTLINER
    if left_tab == "Assets":
        return FOCUS_ASSETS
    if left_tab == "History":
        return FOCUS_HISTORY
    if left_tab == "Problems":
        return FOCUS_PROBLEMS

    right_tab = _get_state(editor_state_dict, "_right_dock_tab", "")
    if right_tab == "Inspector":
        return FOCUS_INSPECTOR
    if right_tab == "History":
        return FOCUS_HISTORY
    if right_tab == "Problems":
        return FOCUS_PROBLEMS

    return FOCUS_NONE


def is_text_input_active(focus_target: FocusTarget, editor_state_dict: Mapping[str, Any]) -> bool:
    if focus_target in (FOCUS_INLINE_RENAME, FOCUS_COMMAND_PALETTE):
        return True
    if _get_state(editor_state_dict, "palette_filter_active", False) is True:
        return True
    if _get_state(editor_state_dict, "hierarchy_filter_active", False) is True:
        return True
    if _get_state(editor_state_dict, "hierarchy_rename_active", False) is True:
        return True
    if _get_state(editor_state_dict, "animation_edit_active", False) is True:
        return True
    if _get_state(editor_state_dict, "inspector_edit_active", False) is True:
        return True
    if _get_state(editor_state_dict, "entity_panels_filter_active", False) is True:
        return True
    if _get_state(editor_state_dict, "entity_panels_text_edit_active", False) is True:
        return True
    if _get_state(editor_state_dict, "scene_browser_filter_active", False) is True:
        return True
    if _get_state(editor_state_dict, "asset_browser_filter_active", False) is True:
        return True

    search_focus = _get_state(editor_state_dict, "_search_focus", "")
    if isinstance(search_focus, str) and search_focus:
        return True

    project_ctrl = _get_state(editor_state_dict, "project_explorer")
    if project_ctrl is not None and getattr(project_ctrl, "inline_rename_active", False) is True:
        return True

    return False


def compute_active_shortcut_scopes(
    focus_target: FocusTarget, editor_state_dict: Mapping[str, Any]
) -> tuple[str, ...]:
    scopes: list[str] = []
    if focus_target == FOCUS_INLINE_RENAME:
        scopes.append(SHORTCUT_SCOPE_INLINE_RENAME)
    scopes.append(SHORTCUT_SCOPE_GLOBAL)
    return tuple(scopes)