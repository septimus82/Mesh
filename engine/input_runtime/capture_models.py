from __future__ import annotations

ACTIONS_ALLOWED_WHEN_BLOCKED = {
    "show_quests",
    "show_inventory",
    "show_character",
    "toggle_editor",
    "toggle_help",
    "toggle_inspector",
    "toggle_dev_browser",
    "toggle_variant_picker",
    "pause_menu",
    "save_game",
    "quickload_last_save",
    "editor_dialogue",
    "editor_animation",
    "editor_tile",
    "editor_lights",
}

GAMEPLAY_ACTIONS = {
    "move_up",
    "move_down",
    "move_left",
    "move_right",
    "interact",
    "attack",
}


def should_dispatch_action_when_blocked(action_name: str) -> bool:
    return str(action_name) in ACTIONS_ALLOWED_WHEN_BLOCKED
