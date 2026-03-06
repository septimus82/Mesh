"""Scene save / dump / load / validate console command handlers."""

from __future__ import annotations

import json
from typing import Any

from engine import json_io
from engine.logging_tools import get_logger
_SWALLOW_ONCE_TAGS: set[str] = set()

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    get_logger(__name__).debug("SWALLOW[%s] %s", tag, context, exc_info=True)


logger = get_logger(__name__)


def handle_save_scene(controller: Any, args: list[str]) -> bool:
    """``scene save [path] [--compact]``"""
    compact = "--compact" in args
    clean_args = [a for a in args if a != "--compact"]

    if not clean_args:
        if not controller.window.scene_controller.current_scene_path:
            controller.log("Error: No scene loaded to save. Provide a path.")
            return True
        target_path = controller.window.scene_controller.current_scene_path
    else:
        target_path = clean_args[0]

    try:
        snapshot = controller.window.build_scene_snapshot(compact=compact)
        json_io.write_json_atomic(target_path, snapshot)
        controller.log(f"Scene saved to '{target_path}'")
    except Exception as e:  # noqa: BLE001  # REASON: runtime fallback isolation
        _log_swallow("CHSC-001", "engine/console_runtime/handlers_scene.py blanket swallow", once=True)
        controller.log(f"Error saving scene: {e}")
        logger.error("[Mesh][Save] Error: %s", e)
    return True


def handle_dump_scene(controller: Any, args: list[str]) -> bool:
    """``dump_scene [path]``"""
    target_path = args[0] if args else "mesh_scene.json"
    try:
        snapshot = controller.window.build_scene_snapshot()
        json_io.write_json_atomic(target_path, snapshot)
        controller.log(f"Dumped scene to '{target_path}'")
    except Exception as e:  # noqa: BLE001  # REASON: runtime fallback isolation
        _log_swallow("CHSC-002", "engine/console_runtime/handlers_scene.py blanket swallow", once=True)
        controller.log(f"Error dumping scene: {e}")
        logger.error("[Mesh][Dump] Error: %s", e)
    return True


def handle_dump_state(controller: Any, args: list[str]) -> bool:
    """``dumpstate [path]``"""
    path = args[0] if args else "mesh_dump.json"
    state = controller.window.game_state.snapshot()
    try:
        json_io.write_json_atomic(path, state)
        controller.log(f"State dumped to {path}")
    except Exception as e:  # noqa: BLE001  # REASON: runtime fallback isolation
        _log_swallow("CHSC-003", "engine/console_runtime/handlers_scene.py blanket swallow", once=True)
        controller.log(f"Error dumping state: {e}")
    return True


def handle_load_state(controller: Any, args: list[str]) -> bool:
    """``loadstate <path>``"""
    if not args:
        controller.log("Usage: loadstate <path>")
        return True
    path = args[0]
    try:
        with open(path) as f:
            state = json.load(f)
        controller.window.scene_controller._apply_scene_state(state)
        controller.log(f"State loaded from {path}")
    except Exception as e:  # noqa: BLE001  # REASON: runtime fallback isolation
        _log_swallow("CHSC-004", "engine/console_runtime/handlers_scene.py blanket swallow", once=True)
        controller.log(f"Error loading state: {e}")
    return True


def handle_validate_scene(controller: Any, args: list[str]) -> bool:
    """``validate_scene [path]``"""
    target = args[0] if args else (controller.window.scene_controller.current_scene_path or "scenes/test_scene.json")
    from engine.tooling_runtime.scene_validate import validate_scene_file

    try:
        errors = validate_scene_file(target)
        if not errors:
            controller.log(f"Scene '{target}' is valid.")
        else:
            controller.log(f"Scene '{target}' has errors:")
            for err in errors:
                controller.log(f"  - {err}")
    except Exception as e:  # noqa: BLE001  # REASON: runtime fallback isolation
        _log_swallow("CHSC-005", "engine/console_runtime/handlers_scene.py blanket swallow", once=True)
        controller.log(f"Error validating scene: {e}")
    return True
