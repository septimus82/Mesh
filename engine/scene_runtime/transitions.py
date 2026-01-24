from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..scene_controller import SceneController

logger = logging.getLogger(__name__)


def request_scene_reload(controller: Any, *, clear_assets: bool = False) -> None:
    """Request that the currently loaded scene reload on the next frame."""
    if controller.current_scene_path:
        controller._pending_scene_path = controller.current_scene_path
        controller._clear_assets_on_next_load = clear_assets

        # Capture camera state for hot reload
        if hasattr(controller.window, "camera"):
            cx, cy = controller.window.get_camera_center()
            controller._preserved_camera_state = {
                "x": cx,
                "y": cy,
                "zoom": controller.window.camera_controller.zoom_state.current,
                "target_zoom": controller.window.camera_controller.zoom_state.target,
            }

        print(f"[Mesh][Scene] Queued reload for '{controller.current_scene_path}' (clear_assets={clear_assets})")


def request_scene_change(controller: Any, scene_path: str) -> None:
    """Request that a different scene load on the next frame."""
    if _try_fade_scene_change(controller, scene_path, spawn_id=None):
        return
    controller._pending_scene_path = scene_path
    controller._clear_assets_on_next_load = False
    print(f"[Mesh][Scene] Queued scene change to '{scene_path}'")


def queue_scene_change(controller: Any, scene_path: str, *, spawn_id: str | None = None) -> None:
    """Request that the game switches to another scene at the end of the frame."""
    scene_path = str(scene_path or "").strip()
    if not scene_path:
        return
    if _try_fade_scene_change(controller, scene_path, spawn_id=spawn_id):
        return
    controller._pending_scene_change = {
        "scene_path": scene_path,
        "spawn_id": spawn_id,
    }
    print(f"[Mesh][Scene] Queued scene change to '{scene_path}' (spawn={spawn_id})")


def _try_fade_scene_change(controller: Any, scene_path: str, spawn_id: str | None) -> bool:
    window = getattr(controller, "window", None)
    overlay = getattr(window, "transition_fade_overlay", None) if window is not None else None
    if overlay is None:
        return False
    if not _fade_enabled(controller):
        return False
    fade_out_s, fade_in_s = _fade_durations(controller)

    def _complete() -> None:
        perform_scene_change(controller, scene_path, spawn_id=spawn_id)
        overlay.start_fade_in(fade_in_s)

    overlay.start_fade_out(fade_out_s, on_complete=_complete)
    return True


def _fade_enabled(controller: Any) -> bool:
    window = getattr(controller, "window", None)
    if window is None:
        return False
    cfg = getattr(window, "engine_config", None)
    enabled = bool(getattr(cfg, "scene_fade_enabled", False))
    settings = getattr(controller, "scene_settings", None)
    if isinstance(settings, dict) and "scene_fade_enabled" in settings:
        enabled = bool(settings.get("scene_fade_enabled"))
    return enabled


def _fade_durations(controller: Any) -> tuple[float, float]:
    window = getattr(controller, "window", None)
    cfg = getattr(window, "engine_config", None) if window is not None else None
    fade_out = float(getattr(cfg, "scene_fade_out_s", 0.2))
    fade_in = float(getattr(cfg, "scene_fade_in_s", 0.2))
    settings = getattr(controller, "scene_settings", None)
    if isinstance(settings, dict):
        if "scene_fade_out_s" in settings:
            fade_out = float(settings.get("scene_fade_out_s", fade_out))
        if "scene_fade_in_s" in settings:
            fade_in = float(settings.get("scene_fade_in_s", fade_in))
    return (max(0.0, fade_out), max(0.0, fade_in))


def perform_scene_change(controller: SceneController, scene_path: str, spawn_id: str | None = None) -> None:
    """Load a new scene immediately and apply the requested spawn."""
    if not str(scene_path or "").strip():
        return

    controller.load_scene(scene_path)

    wc = getattr(controller.window, "world_controller", None)
    gs = getattr(controller.window, "game_state_controller", None)

    if wc is not None and gs is not None:
        key = wc.find_scene_key_by_path(scene_path)
        if key:
            try:
                gs.set_var("world_id", wc.id)
                gs.set_var("world_scene_key", key)
            except Exception as exc:
                logger.warning("Failed to persist world vars on scene change: %s", exc, exc_info=True)

    controller.apply_spawn(spawn_id)

    gs = getattr(controller.window, "game_state_controller", None)
    if gs is not None:
        try:
            gs.set_var("last_scene_path", scene_path)
            gs.set_var("last_spawn_id", spawn_id)
        except Exception as exc:
            logger.warning("Failed to persist last scene vars: %s", exc, exc_info=True)


def reload_scene(controller: SceneController, new_path: str | None = None) -> bool:
    """Hot reload the current (or provided) scene immediately."""
    from .persistence import (
        snapshot_player_state,
        snapshot_camera_state,
        restore_player_state,
        restore_camera_state,
    )

    scene_path = str(new_path or controller.current_scene_path or "").strip()

    def _log(msg: str) -> None:
        controller.window.console_log(f"[HotReload] {msg}")

    def _set_error(msg: str) -> None:
        controller._last_hot_reload_error_message = str(msg or "").strip()
        controller._last_hot_reload_error_scene = scene_path
        setter = getattr(controller.window, "set_hot_reload_error", None)
        if callable(setter):
            setter(controller._last_hot_reload_error_message, scene_path)

    def _clear_error() -> None:
        controller._last_hot_reload_error_message = ""
        controller._last_hot_reload_error_scene = ""
        clearer = getattr(controller.window, "clear_hot_reload_error", None)
        if callable(clearer):
            clearer()

    if not scene_path:
        _log("No active scene to reload")
        _set_error("No active scene to reload")
        return False

    controller._pending_scene_path = None

    gs_controller = getattr(controller.window, "game_state_controller", None)
    state_snapshot = gs_controller.export_state() if gs_controller is not None else None

    player_snapshot = snapshot_player_state(controller)
    camera_snapshot = snapshot_camera_state(controller)
    entity_count = sum(1 for _ in controller.all_sprites)

    _log(f"Reloading scene: {scene_path}")
    _log(f"Clearing {entity_count} entities...")

    controller._clear_layers()
    controller._clear_scene_event_subscriptions()
    if hasattr(controller.window, "_mesh_event_queue"):
        controller.window._mesh_event_queue = []

    _log("Rebuilding layers...")
    try:
        controller.load_scene(scene_path)
    except Exception as exc:
        _log(f"Scene reload failed: {exc}")
        logger.exception("Scene reload failed for path: %s", scene_path)
        _set_error(f"{type(exc).__name__}: {exc}")
        return False

    if gs_controller is not None and state_snapshot is not None:
        gs_controller.import_state(state_snapshot)

    restore_player_state(controller, player_snapshot)
    restore_camera_state(controller, camera_snapshot)

    _log("Instantiating behaviours:")
    behaviour_lines = controller._build_behaviour_instantiation_lines()
    if behaviour_lines:
        for line in behaviour_lines:
            _log(f"  - {line}")
    else:
        _log("  <no behaviours>")

    _log("Scene reload complete.")
    _clear_error()
    return True
