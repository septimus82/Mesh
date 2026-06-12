"""Runtime-safe UI contract helpers.

This module intentionally avoids importing `arcade` so CLI tooling can run in
headless environments.
"""

from __future__ import annotations

PERSISTENT_UI_ATTRS: tuple[str, ...] = (
    "player_hud",
    "game_over_screen",
    "pause_menu",
    "help_overlay",
    "inspector_overlay",
    "encounter_debug_overlay",
    "scene_inspector_overlay",
    "scene_dirty_overlay",
    "hot_reload_overlay",
    "entity_select_overlay",
    "tile_paint_overlay",
    "entity_paint_overlay",
    "capture_overlay",
    "command_palette_overlay",
    "editor_command_palette_overlay",
    "editor_shell_overlay",
    "menu_bar_overlay",
    "context_menu_overlay",
    "entity_panels_overlay",
    "component_inspector_overlay",
    "hd2d_settings_panel_overlay",
    "editor_status_bar_overlay",
    "scene_switcher_overlay",
    "scene_browser_overlay",
    "project_explorer_overlay",
    "asset_browser_overlay",
    "item_editor_overlay",
    "prefab_editor_overlay",
    "quest_editor_overlay",
    "undo_history_overlay",
    "problems_panel_overlay",
    "debug_panels_overlay",
    "find_everything_overlay",
    "interact_prompt_overlay",
    "objective_tracker_overlay",
    "demo_complete_overlay",
    "variant_picker_overlay",
    "dev_browser_overlay",
    "golden_slice_demo_hud",
    "settings_overlay",
    "main_menu_overlay",
    "light_occluder_overlay",
    "selection_outline_overlay",
    "editor_hover_highlight_overlay",
    "marquee_select_overlay",
    "editor_gizmo_overlay",
    "editor_tooltip_overlay",
    "editor_cursor_hint_overlay",
    "fog_overlay",
    "transition_fade_overlay",
)

REQUIRED_PERSISTENT_UI_ATTRS: set[str] = {
    "player_hud",
    "game_over_screen",
    "pause_menu",
    "help_overlay",
}


def missing_persistent_ui_attrs(
    attrs: tuple[str, ...] | list[str] | set[str] | None = None,
) -> tuple[list[str], bool]:
    """
    Return (missing_required, has_duplicates) for the persistent UI contract.
    """
    source = PERSISTENT_UI_ATTRS if attrs is None else attrs
    keys = [str(key) for key in source]
    missing = sorted(REQUIRED_PERSISTENT_UI_ATTRS.difference(keys))
    has_duplicates = len(keys) != len(set(keys))
    return missing, has_duplicates
