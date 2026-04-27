from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from engine.swallowed_exceptions import _log_swallow

if TYPE_CHECKING:
    from ..scene_controller import SceneController


def build_scene_snapshot(controller: SceneController, compact: bool = False) -> Dict[str, Any]:
    """Build a JSON-serializable snapshot of the current scene state."""
    from ..scene_serializer import compact_scene_payload

    # Start with the original loaded data to preserve metadata (tilemaps, etc)
    snapshot = dict(controller._loaded_scene_data)

    # Update settings
    if "settings" not in snapshot:
        snapshot["settings"] = {}

    # Update camera state in settings
    camera_settings = snapshot["settings"].get("camera", {})
    if not isinstance(camera_settings, dict):
        camera_settings = {}
        snapshot["settings"]["camera"] = camera_settings

    camera_settings["zoom"] = {
        "initial": controller.window.camera_controller.zoom_state.current,
        "target": controller.window.camera_controller.zoom_state.target,
        "speed": controller.window.camera_controller.zoom_state.speed,
        "min": controller.window.camera_controller.zoom_state.min_zoom,
        "max": controller.window.camera_controller.zoom_state.max_zoom,
    }

    # Update global state
    game_state_controller = getattr(controller.window, "game_state_controller", None)
    if game_state_controller is not None:
        snapshot["state"] = game_state_controller.export_state()
    else:
        snapshot["state"] = controller.window.game_state.snapshot()

    # Rebuild entities list from current sprites
    entities = []

    def _coerce_scene_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except Exception:
            _log_swallow("scene_snapshot_float", "Error coercing scene float")
            return float(default)

    for sprite in controller.all_sprites:
        # Start with the original entity data if available
        entity_data = getattr(sprite, "mesh_entity_data", {})
        if not isinstance(entity_data, dict):
            entity_data = {}

        # Create a copy to modify
        current_data = dict(entity_data)

        # Update core transform properties
        current_data["x"] = _coerce_scene_float(getattr(sprite, "center_x", 0.0))
        current_data["y"] = _coerce_scene_float(getattr(sprite, "center_y", 0.0))
        current_data["scale"] = _coerce_scene_float(getattr(sprite, "scale", 1.0), 1.0)
        current_data["rotation"] = _coerce_scene_float(getattr(sprite, "angle", 0.0))

        # Update layer if changed
        # We need to find which layer this sprite is currently in
        found_layer = None
        for layer_name, layer in controller.layers.items():
            if sprite in layer:
                found_layer = layer_name
                break
        if found_layer:
            current_data["layer"] = found_layer

        # Update behaviour config
        # The sprite.mesh_behaviour_configs list holds the runtime config
        # We should sync this back to the entity data
        behaviour_configs = getattr(sprite, "mesh_behaviour_configs", [])
        if behaviour_configs:
            normalized_behaviours: list[dict[str, Any]] = []
            for cfg in behaviour_configs:
                if not isinstance(cfg, dict):
                    continue
                behaviour_type = cfg.get("type")
                if not behaviour_type:
                    continue
                params_raw = cfg.get("params")
                params: dict[str, Any] = dict(params_raw) if isinstance(params_raw, dict) else {}
                normalized_behaviours.append(
                    {
                        "type": behaviour_type,
                        "params": params,
                    }
                )
            if normalized_behaviours:
                current_data["behaviours"] = normalized_behaviours

        # Clean up runtime-only fields
        keys_to_remove = [k for k in current_data.keys() if k.startswith("_")]
        for k in keys_to_remove:
            current_data.pop(k, None)

        entities.append(current_data)

    # Sort entities for determinism
    def _entity_sort_key(e: Dict[str, Any]) -> tuple:
        return (
            str(e.get("id", "")),
            str(e.get("prefab_id", "")),
            float(e.get("x", 0.0)),
            float(e.get("y", 0.0)),
        )
    entities.sort(key=_entity_sort_key)

    snapshot["entities"] = entities

    # Tilemap overrides (inline painted tiles)
    if controller.tilemap_instance and controller.tilemap_instance.layer_data:
        tilemap = snapshot.get("tilemap") or {}
        if not isinstance(tilemap, dict):
            tilemap = {}
        overrides = tilemap.get("overrides") or {}
        if not isinstance(overrides, dict):
            overrides = {}
        overrides["layers"] = dict(controller.tilemap_instance.layer_data)
        tilemap["overrides"] = overrides
        snapshot["tilemap"] = tilemap

    # Normalize using SceneLoader to ensure valid schema
    # We use a temporary loader instance or the existing one
    snapshot = controller.window.scene_loader.apply_scene_defaults(snapshot)

    if compact:
        snapshot = compact_scene_payload(snapshot)

    return snapshot


def apply_scene_state(controller: SceneController, state_block: Any) -> None:
    if not isinstance(state_block, dict):
        return
    game_state_controller = getattr(controller.window, "game_state_controller", None)
    if game_state_controller is None:
        return
    game_state_controller.import_state(state_block)


def snapshot_player_state(controller: SceneController) -> dict[str, Any] | None:
    player = controller._find_player_sprite()
    if player is None:
        return None
    return {
        "position": (float(player.center_x), float(player.center_y)),
    }


def restore_player_state(controller: SceneController, snapshot: dict[str, Any] | None) -> None:
    if not snapshot:
        return
    player = controller._find_player_sprite()
    if player is None:
        return
    position = snapshot.get("position")
    if isinstance(position, (tuple, list)) and len(position) == 2:
        controller._apply_entity_mutation(player, x=float(position[0]), y=float(position[1]))


def snapshot_camera_state(controller: SceneController) -> dict[str, Any] | None:
    camera = getattr(controller.window, "camera", None)
    if camera is None:
        return None
    return {
        "position": controller.window.get_camera_center(),
        "zoom": controller.window.camera_controller.zoom_state.current,
        "target": controller.window.camera_controller.zoom_state.target,
    }


def restore_camera_state(controller: SceneController, snapshot: dict[str, Any] | None) -> None:
    if not snapshot:
        return
    camera = getattr(controller.window, "camera", None)
    if camera is None:
        return

    pos = snapshot.get("position")
    if pos:
        move_to = getattr(camera, "move_to", None)
        if callable(move_to):
            move_to(pos, speed=1.0)
        else:
            setattr(camera, "position", pos)

    zoom = snapshot.get("zoom")
    target_zoom = snapshot.get("target")
    if zoom is not None:
        controller.window.camera_controller.zoom_state.current = float(zoom)
    if target_zoom is not None:
        controller.window.camera_controller.zoom_state.target = float(target_zoom)
