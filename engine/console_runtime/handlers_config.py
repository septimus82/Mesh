"""Config, bindings, and settings console command handlers."""

from __future__ import annotations

from typing import Any

from engine.console_runtime.utils import parse_float
from engine.input_bindings import (
    key_code_to_name,
    key_name_to_code,
    known_actions,
    snapshot_bindings,
)


# ---------------------------------------------------------------------------
# Dispatch-compatible handlers  (controller, args) -> bool
# ---------------------------------------------------------------------------

def handle_set(controller: Any, args: list[str]) -> bool:
    """``set <key> <value>``"""
    if len(args) < 2:
        controller.log("Usage: set <key> <value>")
        return True
    key = args[0].lower()
    value = args[1].lower()

    if key in {"volume", "master"}:
        vol = parse_float(controller, value, "volume")
        if vol is not None:
            controller.window.audio.set_master_volume(vol)
            controller.window.engine_config.master_volume = vol
            controller.log(f"Master volume set to {vol:.2f}")
        return True

    if key == "sfx":
        vol = parse_float(controller, value, "sfx")
        if vol is not None:
            controller.window.audio.set_sfx_volume(vol)
            controller.window.engine_config.sfx_volume = vol
            controller.log(f"SFX volume set to {vol:.2f}")
        return True

    if key == "music":
        vol = parse_float(controller, value, "music")
        if vol is not None:
            controller.window.audio.set_music_volume(vol)
            controller.window.engine_config.music_volume = vol
            controller.log(f"Music volume set to {vol:.2f}")
        return True

    if key == "fullscreen":
        is_fs = value in ("1", "true", "yes", "on")
        controller.window.set_fullscreen(is_fs)
        controller.window.engine_config.fullscreen = is_fs
        controller.log(f"Fullscreen set to {is_fs}")
        return True

    if key == "vsync":
        is_vsync = value in ("1", "true", "yes", "on")
        controller.window.set_vsync(is_vsync)
        controller.window.engine_config.vsync = is_vsync
        controller.log(f"VSync set to {is_vsync}")
        return True

    if key == "show_fps":
        controller.log("show_fps not implemented")
        return True

    if key == "debug_on_start":
        is_debug = value in ("1", "true", "yes", "on")
        controller.window.engine_config.debug_on_start = is_debug
        controller.log(f"debug_on_start set to {is_debug}")
        return True

    controller.log(f"Unknown setting: {key}")
    return True


def handle_config(controller: Any, _args: list[str]) -> bool:
    """``config`` — print config summary."""
    cfg = getattr(controller.window, "engine_config", None)
    if cfg is None:
        controller.log("No config loaded.")
    else:
        controller.log(f"Config: {cfg.width}x{cfg.height}, scene={cfg.start_scene}, vol={cfg.master_volume:.2f}")
        controller.log(f"  Title: {cfg.title}")
        controller.log(f"  Fullscreen: {cfg.fullscreen}")
        controller.log(f"  VSync: {cfg.vsync}")
        controller.log(f"  Debug: {cfg.debug_on_start}")
    return True


def handle_bindings(controller: Any, _args: list[str]) -> bool:
    """``bindings`` — list current input bindings."""
    manager = _get_input_manager(controller)
    if manager is None:
        controller.log("Input manager not available")
        return True
    cfg_bindings = getattr(getattr(controller.window, "engine_config", None), "input_bindings", None)
    actions = sorted(known_actions(manager, cfg_bindings))
    bindings = snapshot_bindings(manager)
    controller.log("Input Bindings:")
    for action in actions:
        keys = bindings.get(action, [])
        label = ", ".join(keys) if keys else "<unbound>"
        controller.log(f"  {action}: {label}")
    return True


def handle_bind(controller: Any, args: list[str]) -> bool:
    """``bind <action> <key_name>``"""
    if len(args) < 2:
        controller.log("Usage: bind <action> <key_name>")
        return True
    manager = _get_input_manager(controller)
    if manager is None:
        controller.log("Input manager not available")
        return True

    action, key_name = args[0], args[1]
    if not _is_known_action(controller, action, manager):
        controller.log(f"Unknown action '{action}'")
        return True

    code = key_name_to_code(key_name)
    if code is None:
        controller.log(f"Unknown key name '{key_name}'")
        return True

    manager.bind(action, code)
    _persist_bindings(controller, manager)
    controller.log(f"Bound {action} -> {key_code_to_name(code)}")
    return True


def handle_unbind(controller: Any, args: list[str]) -> bool:
    """``unbind <action> [<key_name>]``"""
    if not args:
        controller.log("Usage: unbind <action> [<key_name>]")
        return True

    manager = _get_input_manager(controller)
    if manager is None:
        controller.log("Input manager not available")
        return True

    action = args[0]
    if not _is_known_action(controller, action, manager):
        controller.log(f"Unknown action '{action}'")
        return True

    if len(args) > 1:
        key_name = args[1]
        code = key_name_to_code(key_name)
        if code is None:
            controller.log(f"Unknown key name '{key_name}'")
            return True
        manager.unbind(action, code)
        _persist_bindings(controller, manager)
        controller.log(f"Unbound {key_code_to_name(code)} from {action}")
        return True

    current = manager.get_bindings().get(action, [])
    if not current:
        controller.log(f"No bindings to clear for '{action}'")
        return True

    for code in list(current):
        manager.unbind(action, code)
    _persist_bindings(controller, manager)
    controller.log(f"Cleared bindings for '{action}'")
    return True


def handle_saveconfig(controller: Any, _args: list[str]) -> bool:
    """``saveconfig``"""
    controller.log("Saving configuration to disk")
    from engine.config import save_config

    try:
        save_config(controller.window.engine_config, controller.window.config_path)
        controller.log(f"Config saved to {controller.window.config_path}")
    except Exception as e:  # noqa: BLE001
        controller.log(f"Error saving config: {e}")
    return True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_input_manager(controller: Any) -> Any:
    manager = getattr(controller.window, "input", None)
    if manager is not None:
        return manager
    ctrl = getattr(controller.window, "input_controller", None)
    return getattr(ctrl, "manager", None)


def _is_known_action(controller: Any, action: str, manager: Any) -> bool:
    cfg_bindings = getattr(getattr(controller.window, "engine_config", None), "input_bindings", None)
    return action in known_actions(manager, cfg_bindings)


def _persist_bindings(controller: Any, manager: Any) -> None:
    ctrl = getattr(controller.window, "input_controller", None)
    if ctrl is not None and hasattr(ctrl, "persist_bindings"):
        ctrl.persist_bindings(save=True)
        return

    cfg = getattr(controller.window, "engine_config", None)
    if cfg is None:
        controller.log("Config not available; bindings not saved")
        return

    cfg.input_bindings = snapshot_bindings(manager)
    try:
        from engine.config import save_config

        save_config(cfg, getattr(controller.window, "config_path", "config.json"))
    except Exception as exc:  # noqa: BLE001
        controller.log(f"Failed to save bindings: {exc}")
