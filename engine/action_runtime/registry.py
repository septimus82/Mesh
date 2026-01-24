from __future__ import annotations

from typing import Callable

from engine.action_runtime.constants import ActionHandler
from engine.constants import (
    EVENT_INVENTORY_OVERLAY_CLOSED,
    EVENT_INVENTORY_OVERLAY_OPENED,
    EVENT_QUEST_LOG_CLOSED,
    EVENT_QUEST_LOG_OPENED,
)
from engine.ui import maybe_enqueue_lighting_toggle_tip
from engine import savegame


def _noop(_window: object) -> None:
    return


def _toggle_editor(window: object) -> None:
    editor = getattr(window, "editor_controller", None)
    toggle = getattr(editor, "toggle", None) if editor is not None else None
    if callable(toggle):
        toggle()


def _toggle_help(window: object) -> None:
    pause_menu = getattr(window, "pause_menu", None)
    if pause_menu is not None and bool(getattr(pause_menu, "visible", False)):
        return
    ui = getattr(window, "ui_controller", None)
    if ui is not None:
        is_quest_log_visible = getattr(ui, "is_quest_log_visible", None)
        if callable(is_quest_log_visible) and is_quest_log_visible():
            return
    overlay = getattr(window, "help_overlay", None)
    toggle = getattr(overlay, "toggle", None) if overlay is not None else None
    if callable(toggle):
        toggle()


def _toggle_variant_picker(window: object) -> None:
    overlay = getattr(window, "variant_picker_overlay", None)
    toggle = getattr(overlay, "toggle", None) if overlay is not None else None
    if callable(toggle):
        toggle()


def _toggle_inspector(window: object) -> None:
    overlay = getattr(window, "inspector_overlay", None)
    toggle = getattr(overlay, "toggle", None) if overlay is not None else None
    if callable(toggle):
        toggle()


def _toggle_dev_browser(window: object) -> None:
    overlay = getattr(window, "dev_browser_overlay", None)
    toggle = getattr(overlay, "toggle", None) if overlay is not None else None
    if callable(toggle):
        toggle()


def _toggle_quest_log(window: object) -> None:
    toggle = getattr(window, "toggle_quest_log", None)
    emitter = getattr(window, "emit_signal", None)
    if callable(toggle):
        visible = bool(toggle())
        if callable(emitter):
            event_type = EVENT_QUEST_LOG_OPENED if visible else EVENT_QUEST_LOG_CLOSED
            emitter(event_type, visible=visible)


def _toggle_inventory(window: object) -> None:
    toggle = getattr(window, "toggle_inventory_overlay", None)
    emitter = getattr(window, "emit_signal", None)
    if callable(toggle):
        visible = bool(toggle())
        if callable(emitter):
            event_type = EVENT_INVENTORY_OVERLAY_OPENED if visible else EVENT_INVENTORY_OVERLAY_CLOSED
            emitter(event_type, visible=visible)


def _toggle_character(window: object) -> None:
    toggle = getattr(window, "toggle_character_panel", None)
    if callable(toggle):
        toggle()


def _toggle_shadowmask(window: object) -> None:
    lighting = getattr(window, "lighting", None)
    toggle = getattr(lighting, "toggle_shadowmask", None)
    if callable(toggle):
        enabled = toggle()
        state = "ON" if enabled else "OFF"

        hud = getattr(window, "player_hud", None)
        enqueue = getattr(hud, "enqueue_toast", None)
        if callable(enqueue):
            enqueue(f"Lighting: Shadow mask {state}")
            maybe_enqueue_lighting_toggle_tip(window)


def _toggle_shadowcast_debug(window: object) -> None:
    lighting = getattr(window, "lighting", None)
    toggle = getattr(lighting, "toggle_shadowcast_debug", None)
    if callable(toggle):
        enabled = toggle()
        state = "ON" if enabled else "OFF"

        hud = getattr(window, "player_hud", None)
        enqueue = getattr(hud, "enqueue_toast", None)
        if callable(enqueue):
            enqueue(f"Lighting: Debug rays {state}")
            maybe_enqueue_lighting_toggle_tip(window)


def _toggle_pause_menu(window: object) -> None:
    paused = not bool(getattr(window, "paused", False))
    setattr(window, "paused", paused)
    pause_menu = getattr(window, "pause_menu", None)
    toggle = getattr(pause_menu, "toggle", None) if pause_menu is not None else None
    if callable(toggle):
        toggle()
    if pause_menu is not None:
        try:
            pause_menu.visible = paused
        except Exception:  # noqa: BLE001
            pass
    logger = getattr(window, "console_log", None)
    if callable(logger):
        logger("Game Paused" if paused else "Game Resumed")


def _editor_if_active(window: object, method_name: str) -> None:
    editor = getattr(window, "editor_controller", None)
    if editor is None or not getattr(editor, "active", False):
        return
    method = getattr(editor, method_name, None)
    if callable(method):
        method()


def _save_game_action(window: object) -> None:
    manager = getattr(window, "save_manager", None)
    hud = getattr(window, "player_hud", None)

    if manager is None:
        return

    # Use a fixed slot for quick actions
    slot = "quicksave"
    if not manager.save_game(slot):
        if hud and hasattr(hud, "enqueue_toast"):
            hud.enqueue_toast("Save Failed")


def _quickload_action(window: object) -> None:
    manager = getattr(window, "save_manager", None)
    hud = getattr(window, "player_hud", None)

    if manager is None:
        return

    slot = "quicksave"
    # load_game returns True on success, False on failure (e.g. file not found)
    if not manager.load_game(slot):
        if hud and hasattr(hud, "enqueue_toast"):
            hud.enqueue_toast("No Save Found")


def _quick_save_snapshot_action(window: object) -> None:
    hud = getattr(window, "player_hud", None)

    ok = savegame.save_quick_snapshot(window)
    if not ok and hud and hasattr(hud, "enqueue_toast"):
        hud.enqueue_toast("Snapshot Save Failed")


def _quick_load_snapshot_action(window: object) -> None:
    hud = getattr(window, "player_hud", None)

    ok = savegame.load_quick_snapshot(window)
    if not ok:
        if hud and hasattr(hud, "enqueue_toast"):
            hud.enqueue_toast("No Snapshot Found")
        return

    if hud and hasattr(hud, "enqueue_toast"):
        hud.enqueue_toast("Loaded snapshot")


def build_actions() -> dict[str, ActionHandler]:
    return {
        # Movement/combat actions are queried continuously by gameplay code; keep as no-ops here.
        "move_up": _noop,
        "move_down": _noop,
        "move_left": _noop,
        "move_right": _noop,
        "interact": _noop,
        "attack": _noop,
        # UI toggles.
        "show_quests": _toggle_quest_log,
        "show_inventory": _toggle_inventory,
        "show_character": _toggle_character,
        "toggle_editor": _toggle_editor,
        "toggle_help": _toggle_help,
        "toggle_dev_browser": _toggle_dev_browser,
        "toggle_inspector": _toggle_inspector,
        "toggle_variant_picker": _toggle_variant_picker,
        "toggle_shadowmask": _toggle_shadowmask,
        "toggle_shadowcast_debug": _toggle_shadowcast_debug,
        "pause_menu": _toggle_pause_menu,
        # Editor sub-panels.
        "editor_dialogue": lambda w: _editor_if_active(w, "toggle_dialogue_panel"),
        "editor_animation": lambda w: _editor_if_active(w, "toggle_animation_panel"),
        "editor_tile": lambda w: _editor_if_active(w, "toggle_tile_panel"),
        "editor_lights": lambda w: _editor_if_active(w, "toggle_lights_tool"),
        # Save/Load
        "save_game": lambda w: _save_game_action(w),
        "quickload_last_save": lambda w: _quickload_action(w),
        "quick_save": lambda w: _quick_save_snapshot_action(w),
        "quick_load": lambda w: _quick_load_snapshot_action(w),
    }


def build_required_actions() -> set[str]:
    return {
        "move_up",
        "move_down",
        "move_left",
        "move_right",
        "interact",
        "attack",
        "show_quests",
        "show_inventory",
        "show_character",
        "toggle_editor",
        "toggle_help",
        "save_game",
        "quickload_last_save",
    }


_ACTIONS: dict[str, ActionHandler] | None = None
_REQUIRED: set[str] | None = None


def get_actions() -> dict[str, ActionHandler]:
    global _ACTIONS
    if _ACTIONS is None:
        _ACTIONS = build_actions()
    return _ACTIONS


def get_required_actions() -> set[str]:
    global _REQUIRED
    if _REQUIRED is None:
        _REQUIRED = build_required_actions()
    return _REQUIRED


def validate_bound_actions(bound_actions: object) -> tuple[list[str], list[str]]:
    """
    Validate action wiring for a binding map (e.g., EngineConfig.input_bindings).

    Returns (unknown_actions, missing_required_actions).
    """
    actions = get_actions()
    required = get_required_actions()

    if isinstance(bound_actions, dict):
        names = [str(key) for key in bound_actions.keys()]
    elif isinstance(bound_actions, (list, set, tuple)):
        names = [str(key) for key in bound_actions]
    else:
        names = []

    bound = set(names)
    unknown = sorted(bound.difference(actions.keys()))
    missing = sorted(required.difference(bound))
    return unknown, missing


def list_actions() -> list[str]:
    return sorted(get_actions().keys())


def dispatch_action(window: object, action_name: str) -> bool:
    handler = get_actions().get(str(action_name))
    if handler is None:
        return False
    handler(window)
    return True
