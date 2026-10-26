from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any, cast

from engine import optional_arcade
from engine.background_layers import parse_background_layers, parse_foreground_layers
from engine.depth_tint_model import parse_depth_tint_settings
from engine.hd2d.runtime import configure_scene as configure_hd2d_scene
from engine.parallax_model import parse_background_planes
from engine.scene_lifecycle_model import SceneLoadInputs, build_scene_load_plan
from engine.scene_particles import configure as configure_scene_particles
from engine.scene_runtime import room_memory
from engine.scene_runtime.index_build import build_scene_index_from_sprites
from engine.sprite_outline_model import parse_outline_settings
from engine.swallowed_exceptions import _log_swallow
from engine.ui import (
    maybe_enqueue_controls_hint_toast,
    maybe_enqueue_preset_mode_toast,
    maybe_enqueue_shadowmask_enabled_toast,
)
from engine.water import reset as reset_water


def _restore_camera(window: Any, pos: tuple[float, float], zoom: float | None) -> None:
    camera = getattr(window, "camera", None)
    if camera:
        move_to = getattr(camera, "move_to", None)
        if callable(move_to):
            move_to(pos, 1.0)
        else:
            setattr(camera, "position", pos)
    if zoom is not None:
        window.set_camera_zoom_target(zoom, speed=999.0)



def configure_scene_lighting(window: Any, scene: dict[str, Any], settings: Any, scene_path: str) -> None:
    """Set the lighting up for a scene that is loading (before its objects spawn).

    Lights carried by the previous scene's objects are dropped (this scene's objects register their own),
    and a room that doesn't set its own ambient gets the project's, not whatever the last room had.
    """
    lighting = getattr(window, "lighting", None)
    if lighting is None:
        return
    clear_dynamic = getattr(lighting, "clear_dynamic_lights", None)
    if callable(clear_dynamic):
        clear_dynamic()
    # A room may switch lighting on or off; one that doesn't say gets the project's setting. (Before this the
    # scene key was documented and used by demo scenes but never read.) Set before objects spawn: their lights
    # only register while lighting is on.
    project_default = getattr(getattr(window, "engine_config", None), "lighting_enabled", None)
    wanted = settings.get("lighting_enabled", project_default) if isinstance(settings, dict) else project_default
    if wanted is not None:
        lighting.enabled = bool(wanted) and bool(getattr(lighting, "available", True))
    lights_cfg = scene.get("lights")
    if isinstance(lights_cfg, list):
        lighting.configure_scene_lights(lights_cfg)
    else:
        lighting.configure_scene_lights(None)
    ambient_tint = settings.get("ambient_light_rgba") if isinstance(settings, dict) else None
    if ambient_tint is None:  # a room without its own ambient goes back to the project's, not the last room's
        ambient_tint = getattr(getattr(window, "engine_config", None), "ambient_light_rgba", None) or (255, 255, 255, 255)
    try:
        lighting.set_ambient_tint(ambient_tint)
    except Exception:  # noqa: BLE001  # REASON: scene lifecycle controller fallback isolation
        _log_swallow("SCEN-003", "engine/scene_lifecycle_controller.py pass-only blanket swallow")
    # How light the room is away from its lamps: its own ambient colour, else the project's (never the last
    # room's). While the day/night clock runs in this room, the clock sets the ambient light instead.
    if not getattr(getattr(window, "day_night", None), "enabled", False):
        base_ambient = getattr(lighting, "base_ambient_color", None)
        room_ambient: Any = settings.get("lighting_ambient_color") if isinstance(settings, dict) else None
        try:
            r, g, b = (max(0, min(255, int(c))) for c in room_ambient[:3])
            lighting.ambient_color = (r, g, b, 255)
        except (TypeError, ValueError):  # not set (or unreadable): the project's
            if base_ambient is not None:
                lighting.ambient_color = base_ambient

    occluders_cfg = scene.get("occluders")
    try:
        from engine.lighting.occluders import (  # noqa: PLC0415
            build_entity_occluders_from_scene_payload,
            build_occluders_from_scene_payload,
        )

        entity_occluders = build_entity_occluders_from_scene_payload(scene)
    except Exception:  # noqa: BLE001  # REASON: scene lifecycle controller fallback isolation
        entity_occluders = []

    if "occluders" in scene and isinstance(occluders_cfg, list):
        merged = list(occluders_cfg)
        if entity_occluders:
            merged.extend(entity_occluders)
        lighting.configure_scene_occluders(merged)
    else:
        try:
            revision = int(getattr(window, "scene_dirty_counter", 0) or 0)
            auto_occluders = build_occluders_from_scene_payload(scene, scene_path=scene_path, revision=revision)
            if entity_occluders:
                auto_occluders.extend(entity_occluders)
            lighting.configure_scene_occluders(auto_occluders)
        except Exception:  # noqa: BLE001  # REASON: scene lifecycle controller fallback isolation
            lighting.configure_scene_occluders(None)

    try:
        settings_block = scene.get("settings", {})
        settings_block = settings_block if isinstance(settings_block, dict) else {}
        cfg = getattr(window, "engine_config", None)
        # A room without its own setting follows the project's: the previous room's must not carry over.
        mode = settings_block.get("lighting_shadows_mode")
        if mode is None and not os.environ.get("MESH_SHADOWS_MODE"):  # a developer's override stays
            mode = getattr(cfg, "lighting_shadows_mode", None)
        if mode is not None:
            setter = getattr(lighting, "set_shadows_mode", None)
            if callable(setter):
                setter(str(mode))
            else:
                lighting.shadows_mode = str(mode or "none").strip().lower()
        apply_shadow_look(lighting, settings_block, getattr(cfg, "lighting_shadow_softness", "sharp"))
    except Exception:  # noqa: BLE001  # REASON: scene lifecycle controller fallback isolation
        _log_swallow("SCEN-004", "engine/scene_lifecycle_controller.py pass-only blanket swallow")
        pass


def handle_pending_scene_load(controller: Any) -> bool:
    if controller._pending_scene_path is None:
        return False

    path = controller._pending_scene_path
    controller._pending_scene_path = None

    if hasattr(controller.window, "_mesh_event_queue"):
        controller.window._mesh_event_queue = []

    inputs = SceneLoadInputs(
        scene_path=path,
        current_scene_path=controller.current_scene_path,
        preserved_camera_state=controller._preserved_camera_state,
        clear_assets_on_next_load=controller._clear_assets_on_next_load,
        has_assets=getattr(controller.window, "assets", None) is not None,
        has_audio=getattr(controller.window, "audio", None) is not None,
        camera_center=controller.window.get_camera_center() if hasattr(controller.window, "get_camera_center") else None,
        camera_zoom=(
            float(controller.window.camera_controller.zoom_state.current)
            if hasattr(controller.window, "camera_controller")
            else None
        ),
    )

    plan = build_scene_load_plan(inputs)

    # Prefer explicitly preserved state (from request_scene_reload), fallback to current
    controller._preserved_camera_state = None

    if plan.should_clear_assets:
        print("[Mesh][Assets] Clearing texture cache before reload")
        controller.window.assets.clear()
        if getattr(controller.window, "audio", None) is not None:
            controller.window.audio.clear_cache()
    controller._clear_assets_on_next_load = False

    print(f"[Mesh][Scene] Loading pending scene '{path}'")
    controller.load_scene(path)

    if plan.is_reload and plan.saved_camera_pos is not None:
        print(f"[Mesh][Scene] Restoring camera to {plan.saved_camera_pos}")
        _restore_camera(controller.window, plan.saved_camera_pos, plan.saved_zoom)

    return True


def handle_pending_scene_change(controller: Any) -> bool:
    if not controller._pending_scene_change:
        return False
    info = controller._pending_scene_change
    controller._pending_scene_change = None
    controller._perform_scene_change(info["scene_path"], info.get("spawn_id"))
    return True


def load_scene(controller: Any, scene_path: str) -> dict[str, Any]:
    """Load entities from a JSON scene file and build sprites for them."""
    print(f"[Mesh][Scene] Loading scene '{scene_path}'")
    # Every room change comes through here: note what was collected or defeated in the room being left.
    # Not when loading a save: its game state, room memory included, has just replaced this one.
    if not room_memory.is_save_slot(controller.window, scene_path):
        room_memory.remember_removed(controller)
    controller._clear_scene_event_subscriptions()
    try:
        from engine.lighting.occluders import reset_entity_occluder_cache  # noqa: PLC0415

        reset_entity_occluder_cache()
    except Exception:  # noqa: BLE001  # REASON: scene lifecycle controller fallback isolation
        _log_swallow("SCEN-001", "engine/scene_lifecycle_controller.py pass-only blanket swallow")
        pass
    scene = controller.window.scene_loader.load_scene(scene_path)
    controller.current_scene_path = scene_path
    # The room this is, also when it comes from a save slot (which records the room it was made in).
    controller.room_path = room_memory.room_key(getattr(controller.window.scene_loader, "last_saved_from", None) or scene_path)
    controller._loaded_scene_data = scene
    controller.sensors_runtime.reset()
    # Keep a stable authored copy for debug authoring tools (avoid persisting runtime-only mutations).
    controller._loaded_scene_source_data = copy.deepcopy(scene) if isinstance(scene, dict) else {}
    controller._background_layers = parse_background_layers(scene)
    controller._foreground_layers = parse_foreground_layers(scene)
    controller._background_planes = parse_background_planes(scene)
    controller._background_plane_texture_cache.clear()  # Clear texture cache on scene load

    try:
        recorder = getattr(controller.window, "record_recent_scene", None)
        if callable(recorder):
            recorder(scene_path)
    except Exception:  # noqa: BLE001  # REASON: scene lifecycle controller fallback isolation
        _log_swallow("SCEN-002", "engine/scene_lifecycle_controller.py pass-only blanket swallow")
        pass

    controller._apply_theme_runtime(scene)

    controller.scene_settings = scene.get("settings", {})
    # Load render sort mode from scene settings
    raw_sort_mode = controller.scene_settings.get("render_sort_mode", "y_sort")
    controller._render_sort_mode = str(raw_sort_mode) if raw_sort_mode in ("y_sort", "explicit_z") else "y_sort"
    # Load shadows enabled setting (default True)
    controller._shadows_enabled = bool(controller.scene_settings.get("shadows_enabled", True))
    # Load contact shadows setting (default True when shadows enabled)
    controller._shadows_contact_enabled = bool(controller.scene_settings.get("shadows_contact_enabled", True))
    # Load AO shadows setting (default False - subtle, opt-in)
    controller._shadows_ao_enabled = bool(controller.scene_settings.get("shadows_ao_enabled", False))
    # Load depth tint settings (default disabled)
    controller._depth_tint_settings = parse_depth_tint_settings(controller.scene_settings)
    # Load outline settings (default disabled)
    controller._outline_settings = parse_outline_settings(controller.scene_settings)
    controller._apply_scene_settings(controller.scene_settings)
    controller._apply_scene_state(scene.get("state"))
    controller._configure_camera_from_scene(controller.scene_settings)

    # Reset collision rules to default
    controller.collision_rules = dict(controller._default_collision_rules)
    scene_rules = scene.get("collision_rules")
    if isinstance(scene_rules, dict):
        controller._apply_collision_rules_overrides(scene_rules)

    controller.window.world_width = controller.scene_settings.get("world_width")
    controller.window.world_height = controller.scene_settings.get("world_height")
    configure_scene_lighting(controller.window, scene, controller.scene_settings, scene_path)
    configure_hd2d_scene(controller.window, controller.scene_settings, scene)
    configure_scene_particles(controller.window, controller.scene_settings, scene)  # after the renderer: HD-2D's own them
    reset_water(controller.window)  # its water surfaces register as their objects are made (engine.water)

    # Handle music
    music_path = controller.scene_settings.get("music")
    audio = getattr(controller.window, "audio", None)
    if audio is not None:
        cfg = getattr(controller.window, "engine_config", None)
        crossfade_enabled = bool(getattr(cfg, "music_crossfade_enabled", False))
        if isinstance(controller.scene_settings, dict) and "music_crossfade_enabled" in controller.scene_settings:
            crossfade_enabled = bool(controller.scene_settings.get("music_crossfade_enabled"))
        fade_out_s = float(getattr(cfg, "music_crossfade_out_s", 0.25))
        fade_in_s = float(getattr(cfg, "music_crossfade_in_s", 0.25))
        if isinstance(controller.scene_settings, dict):
            if "music_crossfade_out_s" in controller.scene_settings:
                fade_out_s = float(controller.scene_settings.get("music_crossfade_out_s", fade_out_s))
            if "music_crossfade_in_s" in controller.scene_settings:
                fade_in_s = float(controller.scene_settings.get("music_crossfade_in_s", fade_in_s))

        if music_path:
            volume = float(controller.scene_settings.get("music_volume", 1.0))
            if crossfade_enabled and hasattr(audio, "transition_music"):
                audio.transition_music(
                    music_path,
                    fade_out_s=fade_out_s,
                    fade_in_s=fade_in_s,
                    volume=volume,
                )
            else:
                audio.play_music(music_path, volume=volume)
        else:
            # Stop music if scene has none? Or keep playing previous?
            # Usually we want to stop if explicitly None, but maybe keep if missing?
            # Let's assume if "music" key is missing, we keep playing.
            # If "music" is explicitly null/empty, we stop.
            if "music" in controller.scene_settings and not music_path:
                if crossfade_enabled and hasattr(audio, "transition_music"):
                    audio.transition_music("", fade_out_s=fade_out_s, fade_in_s=fade_in_s, volume=0.0)
                else:
                    audio.stop_music()

    controller._ensure_layers(scene.get("layers", []))
    controller._clear_layers()
    scene_dir = Path(scene_path).resolve().parent
    controller._load_tilemap_layers(scene, scene_dir)

    total_spawned = 0
    from engine.scene_entity_gating import filter_entities_by_flags  # noqa: PLC0415

    getter = getattr(controller.window, "get_flag", None)
    entities_payload = filter_entities_by_flags(scene.get("entities", []), get_flag=getter if callable(getter) else None)
    gone = room_memory.removed_ids(controller.window, controller.room_path)  # collected or defeated earlier
    entities_payload = [e for e in entities_payload if not (isinstance(e, dict) and e.get("id") in gone)]
    controller._room_spawned_ids = room_memory.spawned_ids(entities_payload)
    for entity in entities_payload:
        sprite = controller._create_sprite(entity)
        if not sprite:
            continue
        layer_name = entity.get("layer", "entities")
        if layer_name not in controller.layers:
            print(f"[Mesh][Scene] WARNING: Layer '{layer_name}' missing, creating on the fly")
            controller.layers[layer_name] = optional_arcade.arcade.SpriteList()
        is_solid = bool(entity.get("solid", False))
        sprite.mesh_is_solid = is_solid
        controller.entities.enqueue_spawn(sprite, layer_name=layer_name, is_solid=is_solid)
        total_spawned += 1

    # Build deterministic per-scene entity index once per load.
    # Use the same iteration order as legacy lookup paths (layer order).
    controller.entities.apply_pending_ops(controller, stage="load")
    pending = getattr(controller, "_pending_saved_entities", None)
    if pending is not None:  # a loaded save's object states belong to this room, now that it exists
        controller._pending_saved_entities = None
        from engine.save_runtime.entity_state import apply_entities  # noqa: PLC0415

        apply_entities(controller, pending)
    controller._scene_index = build_scene_index_from_sprites(controller.all_sprites)
    controller.entities.invalidate("scene_load")

    print(f"[Mesh][Scene] Scene ready with {total_spawned} sprite(s)")
    editor = getattr(controller.window, "editor_controller", None)
    record_recent = getattr(editor, "record_recent_scene", None) if editor is not None else None
    if callable(record_recent):
        record_recent(controller.current_scene_path)
    refresh_live_bridge = getattr(editor, "refresh_live_bridge_scene", None) if editor is not None else None
    if callable(refresh_live_bridge):
        refresh_live_bridge()
    # Auto-apply HD2D defaults if configured and scene lacks HD2D keys
    auto_apply_hd2d = getattr(editor, "maybe_auto_apply_hd2d_defaults", None) if editor is not None else None
    if callable(auto_apply_hd2d):
        try:
            auto_apply_hd2d()
        except Exception:  # noqa: BLE001  # REASON: scene lifecycle controller fallback isolation
            _log_swallow("SCEN-005", "engine/scene_lifecycle_controller.py pass-only blanket swallow")
            pass
    controller._rebuild_ui_for_scene()
    maybe_enqueue_controls_hint_toast(controller.window, scene_id=controller.current_scene_path, seconds=4.0)
    maybe_enqueue_preset_mode_toast(controller.window, scene_id=controller.current_scene_path, seconds=4.0)
    maybe_enqueue_shadowmask_enabled_toast(controller.window, seconds=4.0)
    controller._apply_pending_spawn_point()
    try:
        from engine.savegame import _apply_pending_savegame_player_pos  # noqa: PLC0415

        _apply_pending_savegame_player_pos(controller.window)
    except Exception:  # noqa: BLE001  # REASON: scene lifecycle controller fallback isolation
        _log_swallow("SCEN-006", "engine/scene_lifecycle_controller.py pass-only blanket swallow")
        pass
    # CameraFollow is paused in the editor; keep a newly opened scene on the canvas.
    frame_scene = getattr(editor, "frame_scene_on_canvas", None) if editor is not None else None
    if callable(frame_scene) and getattr(editor, "active", False):
        frame_scene()
    controller.window.clear_input_locks()
    return cast(dict[str, Any], scene)


def apply_shadow_look(lighting: Any, settings_block: dict[str, Any], default_softness: str = "sharp") -> None:
    """A room's shadow edges and their fine-tuning. Each falls back to its default, so one room's never carries
    into the next."""
    softness = settings_block.get("lighting_shadow_softness", default_softness)
    lighting.shadow_softness = softness if softness in ("sharp", "soft", "softer") else "sharp"
    edge = settings_block.get("lighting_shadow_edge")
    lighting.shadow_edge_px = float(edge) if isinstance(edge, (int, float)) else None
    strength = settings_block.get("lighting_shadow_strength")
    lighting.shadow_strength = float(strength) if isinstance(strength, (int, float)) else 1.0
    quality = settings_block.get("lighting_shadow_quality")
    lighting.shadow_quality = quality if quality in ("low", "normal", "high") else "normal"
    lighting.character_shadows = settings_block.get("lighting_character_shadows") is not False
