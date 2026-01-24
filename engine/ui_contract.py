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
    "entity_paint_overlay",
    "interact_prompt_overlay",
    "objective_tracker_overlay",
    "demo_complete_overlay",
    "variant_picker_overlay",
    "dev_browser_overlay",
    "golden_slice_demo_hud",
    "settings_overlay",
    "main_menu_overlay",
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
