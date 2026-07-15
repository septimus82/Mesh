from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any, Dict

from engine.swallowed_exceptions import _log_swallow

if TYPE_CHECKING:
    from ..scene_controller import SceneController


def build_scene_snapshot(controller: SceneController, compact: bool = False) -> Dict[str, Any]:
    """Build a JSON-serializable snapshot of the current scene state."""
    from ..scene_serializer import compact_scene_payload

    authored_payload = getattr(controller, "_loaded_scene_source_data", None)
    if not isinstance(authored_payload, dict):
        authored_payload = getattr(controller, "_loaded_scene_data", {})

    # Start from the authored scene, not the runtime scene. Runtime scene data can
    # contain resolved encounter placeholders, injected lighting state, and other
    # transient values that are not valid authored scene JSON.
    snapshot = copy.deepcopy(authored_payload) if isinstance(authored_payload, dict) else {}

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

    def _coerce_scene_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except Exception:
            _log_swallow("scene_snapshot_float", "Error coercing scene float")
            return float(default)

    authored_entities = snapshot.get("entities")
    entities: list[dict[str, Any]] = []
    authored_entity_by_key: dict[tuple[str, str], int] = {}
    if isinstance(authored_entities, list):
        for entity in authored_entities:
            if not isinstance(entity, dict):
                continue
            entity_index = len(entities)
            entities.append(copy.deepcopy(entity))
            for key_name in ("id", "name", "mesh_name", "prefab_id"):
                value = entity.get(key_name)
                if isinstance(value, str) and value.strip():
                    authored_entity_by_key[(key_name, value.strip())] = entity_index

    updated_entity_indexes: set[int] = set()

    for sprite in controller.all_sprites:
        # Start with the original entity data if available
        entity_data = getattr(sprite, "mesh_entity_data", {})
        if not isinstance(entity_data, dict):
            entity_data = {}

        authored_entity_index = _find_authored_entity_index_for_sprite(entity_data, authored_entity_by_key)
        current_data = copy.deepcopy(entities[authored_entity_index]) if authored_entity_index is not None else {}
        _merge_authored_entity_fields(current_data, entity_data)

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

        _remove_runtime_only_entity_fields(current_data)

        if authored_entity_index is None:
            entities.append(current_data)
        else:
            entities[authored_entity_index] = current_data
            updated_entity_indexes.add(authored_entity_index)

    for index, entity in enumerate(entities):
        if index not in updated_entity_indexes:
            _remove_runtime_only_entity_fields(entity)

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
    _remove_runtime_tilemap_fields(snapshot)

    # Normalize using SceneLoader to ensure valid schema
    # We use a temporary loader instance or the existing one
    snapshot = controller.window.scene_loader.apply_scene_defaults(snapshot)

    if compact:
        snapshot = compact_scene_payload(snapshot)

    return snapshot


_AUTHORED_ENTITY_FIELDS = {
    "alpha",
    "animation_blend",
    "animation_frame_rate",
    "animation_root_motion",
    "animation_state",
    "animations",
    "behaviour_config",
    "behaviours",
    "collision_poly",
    "depth_z",
    "dialogue",
    "dialogue_lines",
    "encounter_cost",
    "encounter_group",
    "follow_speed",
    "follow_target",
    "forbid_flags",
    "id",
    "layer",
    "mesh_name",
    "name",
    "occluder_poly",
    "on_trigger",
    "patrol_points",
    "patrol_speed",
    "prefab_id",
    "prefab_overrides",
    "render_layer",
    "require_flags",
    "rotation",
    "scale",
    "solid",
    "spawn_id",
    "sprite",
    "sprite_sheet",
    "tag",
    "tags",
    "tint",
    "trigger_radius",
    "trigger_target",
    "type",
    "variant_id",
    "x",
    "y",
}


_SPRITE_SYNC_ENTITY_FIELDS = {
    "alpha",
    "behaviour_config",
    "behaviours",
    "collision_poly",
    "depth_z",
    "layer",
    "mesh_name",
    "occluder_poly",
    "prefab_overrides",
    "render_layer",
    "rotation",
    "scale",
    "solid",
    "tag",
    "tags",
    "tint",
    "x",
    "y",
}

_PREFAB_OWNED_ENTITY_FIELDS = {"name", "sprite"}


def _find_authored_entity_index_for_sprite(
    entity_data: dict[str, Any],
    authored_entity_by_key: dict[tuple[str, str], int],
) -> int | None:
    for key_name in ("id", "name", "mesh_name", "prefab_id"):
        value = entity_data.get(key_name)
        if not isinstance(value, str) or not value.strip():
            continue
        authored_index = authored_entity_by_key.get((key_name, value.strip()))
        if authored_index is not None:
            return authored_index
    return None


def _merge_authored_entity_fields(target: dict[str, Any], source: dict[str, Any]) -> None:
    is_existing_authored_entity = bool(target)
    has_prefab = isinstance(target.get("prefab_id"), str) and bool(str(target.get("prefab_id")).strip())
    for key, value in source.items():
        if key.startswith("x_"):
            target[key] = copy.deepcopy(value)
            continue
        if key not in _AUTHORED_ENTITY_FIELDS:
            continue
        if is_existing_authored_entity:
            if key not in _SPRITE_SYNC_ENTITY_FIELDS:
                continue
            if has_prefab and key in _PREFAB_OWNED_ENTITY_FIELDS:
                continue
        if key in _AUTHORED_ENTITY_FIELDS:
            target[key] = copy.deepcopy(value)


def _remove_runtime_only_entity_fields(entity: dict[str, Any]) -> None:
    for key in list(entity.keys()):
        if key.startswith("_"):
            entity.pop(key, None)
            continue
        if key not in _AUTHORED_ENTITY_FIELDS and not key.startswith("x_"):
            entity.pop(key, None)
    if isinstance(entity.get("prefab_id"), str) and str(entity.get("prefab_id")).strip():
        for key in _PREFAB_OWNED_ENTITY_FIELDS:
            entity.pop(key, None)


def _remove_runtime_tilemap_fields(snapshot: dict[str, Any]) -> None:
    tilemap = snapshot.get("tilemap")
    if not isinstance(tilemap, dict):
        return
    tilemap.pop("resolved_path", None)


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
