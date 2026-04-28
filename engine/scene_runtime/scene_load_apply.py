from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, cast

from engine import optional_arcade
from engine.scene_runtime import authoring as _authoring_runtime
from engine.swallowed_exceptions import _log_swallow
from engine.tilemap import TilemapInstance


def get_loaded_scene_payload(controller: Any) -> Dict[str, Any]:
    return cast(Dict[str, Any], controller._loaded_scene_data)


def get_authored_scene_payload(controller: Any, *, authoring_runtime: Any = _authoring_runtime) -> Dict[str, Any]:
    return cast(Dict[str, Any], authoring_runtime.get_authored_scene_payload(controller))


def debug_apply_authored_scene_payload(
    controller: Any,
    authored_payload: Dict[str, Any],
    *,
    authoring_runtime: Any = _authoring_runtime,
) -> bool:
    return bool(authoring_runtime.debug_apply_authored_scene_payload(controller, authored_payload))


def load_tilemap_layers(
    controller: Any,
    scene: Dict[str, Any],
    scene_dir: Path,
    *,
    load_tilemap_func: Callable[..., TilemapInstance | None],
) -> None:
    tilemap_data = scene.get("tilemap")
    manager = getattr(controller.window, "tilemap_manager", None)
    if not isinstance(tilemap_data, dict) or manager is None:
        return

    def _expand_candidates(raw: Any) -> list[Path]:
        candidates: list[Path] = []
        if not isinstance(raw, str) or not raw.strip():
            return candidates
        value_path = Path(raw)
        if value_path.is_absolute():
            candidates.append(value_path)
        else:
            candidates.append((scene_dir / value_path).resolve())
            candidates.append((Path.cwd() / value_path).resolve())
        return candidates

    candidates: list[Path] = []
    candidates.extend(_expand_candidates(tilemap_data.get("resolved_path")))
    candidates.extend(_expand_candidates(tilemap_data.get("path")))

    if not candidates:
        print("[Mesh][Tilemap] WARNING: Scene defined a tilemap without a path")
        return

    tilemap_path = None
    for candidate in candidates:
        if candidate.exists():
            tilemap_path = candidate
            break
    if tilemap_path is None:
        tilemap_path = candidates[-1]

    raw_tile_layers = tilemap_data.get("tile_layers")
    raw_layer_configs = (
        raw_tile_layers
        if isinstance(raw_tile_layers, list) and raw_tile_layers
        else tilemap_data.get("layers", [])
    )
    if not isinstance(raw_layer_configs, list) or not raw_layer_configs:
        print(f"[Mesh][Tilemap] WARNING: Scene tilemap '{tilemap_path}' has no layers configured")
        return

    layer_configs: list[dict[str, Any]] = []
    for cfg in raw_layer_configs:
        if isinstance(cfg, dict):
            layer_configs.append(dict(cfg))

    collision_layer_id = tilemap_data.get("collision_layer_id")
    if isinstance(collision_layer_id, str) and collision_layer_id.strip():
        target = collision_layer_id.strip()
        for cfg in layer_configs:
            name = cfg.get("id") or cfg.get("name") or cfg.get("layer")
            if isinstance(name, str) and name.strip() == target:
                cfg["collision"] = True

    overrides_value = tilemap_data.get("overrides")
    overrides: dict[str, Any] | None = None
    if isinstance(overrides_value, dict):
        overrides = dict(overrides_value)

    tile_override_layers: dict[str, Any] = {}
    if overrides and isinstance(overrides.get("layers"), dict):
        tile_override_layers = dict(overrides.get("layers", {}))

    if isinstance(raw_tile_layers, list):
        for entry in raw_tile_layers:
            if not isinstance(entry, dict):
                continue
            layer_id = entry.get("id") or entry.get("name") or entry.get("layer")
            if not isinstance(layer_id, str) or not layer_id.strip():
                continue
            tiles = entry.get("tiles")
            if isinstance(tiles, list):
                tile_override_layers[layer_id.strip()] = tiles

    if tile_override_layers:
        if overrides is None:
            overrides = {}
        overrides["layers"] = tile_override_layers
    try:
        instance = load_tilemap_func(tilemap_path, layer_configs, overrides=overrides)
    except Exception:
        _log_swallow("scene_load_tilemap", f"Failed to load tilemap path={tilemap_path}")
        return

    if instance is None:
        return

    controller.tilemap_instance = instance
    controller.navigation.invalidate()
    controller._tilemap_background_layers = instance.background_layers
    controller._tilemap_foreground_layers = instance.foreground_layers
    controller._tilemap_draw_layers = list(getattr(instance, "draw_layers", []))
    if instance.collision_sprites:
        controller.solid_sprites.extend(instance.collision_sprites)
    controller._init_tilemap_batching(instance)
    controller._apply_tilemap_world_bounds(instance)

    layer_count = len(instance.background_layers) + len(instance.foreground_layers)
    print(
        f"[Mesh][Tilemap] Loaded '{tilemap_path.name}' with {layer_count} draw layer(s) and "
        f"{len(instance.collision_sprites)} collision sprite(s)",
    )


def apply_scene_settings(controller: Any, settings: Dict[str, Any]) -> None:
    try:
        arcade_window = optional_arcade.arcade.get_window()
    except RuntimeError:
        arcade_window = None
    if arcade_window is None:
        return

    color_name = settings.get("background_color")
    if isinstance(color_name, str):
        color_value = getattr(optional_arcade.arcade.color, color_name.upper(), None)
        if color_value:
            optional_arcade.arcade.set_background_color(color_value)
            return
    optional_arcade.arcade.set_background_color(optional_arcade.arcade.color.DARK_BLUE_GRAY)

    # Day/night overrides
    day_night = getattr(controller.window, "day_night", None)
    if day_night is not None:
        if "day_night_enabled" in settings:
            day_night.enabled = bool(settings.get("day_night_enabled"))
        if "time_of_day_hour" in settings:
            try:
                day_night.set_hour(float(settings["time_of_day_hour"]))
            except (TypeError, ValueError):
                pass
        if "day_night_cycle_length_seconds" in settings:
            try:
                day_night.set_cycle_length_seconds(float(settings["day_night_cycle_length_seconds"]))
            except (TypeError, ValueError):
                pass

    spawn_id = settings.get("initial_spawn")
    if spawn_id:
        # Queue a spawn move after entities are loaded
        controller.window.set_next_spawn_point(spawn_id)


def apply_scene_state(
    controller: Any,
    state_block: Any,
    *,
    apply_scene_state_runtime: Callable[[Any, Any], None],
) -> None:
    apply_scene_state_runtime(controller, state_block)
