from threading import Lock
from time import perf_counter
from typing import Any, Sequence, Dict, List, Tuple, cast
import engine.optional_arcade as optional_arcade
from engine.asset_hot_reload_watcher import is_hot_reload_enabled
from engine.logging_tools import get_logger

_OVERLAY_PERF_LOCK = Lock()
_OVERLAY_PERF_REQUIRED_KEYS = ("providers_total", "command_palette_provider")
_OVERLAY_PERF: dict[str, dict[str, float]] = {}

logger = get_logger(__name__)
_SWALLOW_ONCE_TAGS: set[str] = set()
_PROVIDER_FALLBACK_EXCEPTIONS: tuple[type[Exception], ...] = (
    AttributeError,
    ImportError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    logger.debug("SWALLOW[%s] %s", tag, context, exc_info=True)



def _record_overlay_perf(metric: str, elapsed_ms: float) -> None:
    if elapsed_ms < 0.0:
        elapsed_ms = 0.0
    with _OVERLAY_PERF_LOCK:
        bucket = _OVERLAY_PERF.get(metric)
        if bucket is None:
            bucket = {"count": 0.0, "total_ms": 0.0, "max_ms": 0.0}
            _OVERLAY_PERF[metric] = bucket
        bucket["count"] = float(bucket.get("count", 0.0) + 1.0)
        bucket["total_ms"] = float(bucket.get("total_ms", 0.0) + elapsed_ms)
        if elapsed_ms > float(bucket.get("max_ms", 0.0)):
            bucket["max_ms"] = float(elapsed_ms)


def read_overlay_perf_telemetry(*, reset: bool = False) -> dict[str, dict[str, float | int]]:
    with _OVERLAY_PERF_LOCK:
        snapshot = {
            str(name): {
                "count": int(float(bucket.get("count", 0.0))),
                "total_ms": float(bucket.get("total_ms", 0.0)),
                "max_ms": float(bucket.get("max_ms", 0.0)),
            }
            for name, bucket in _OVERLAY_PERF.items()
        }
        if reset:
            _OVERLAY_PERF.clear()

    for key in _OVERLAY_PERF_REQUIRED_KEYS:
        snapshot.setdefault(key, {"count": 0, "total_ms": 0.0, "max_ms": 0.0})
    return {
        name: {
            "count": int(data["count"]),
            "total_ms": round(float(data["total_ms"]), 3),
            "max_ms": round(float(data["max_ms"]), 3),
        }
        for name, data in sorted(snapshot.items())
    }


def reset_overlay_perf_telemetry() -> None:
    with _OVERLAY_PERF_LOCK:
        _OVERLAY_PERF.clear()


def _selected_plane_id_for_suggestions(window: Any) -> str:
    state = getattr(window, "background_plane_editor_state", None) if window is not None else None
    selected = getattr(state, "selected_plane_id", "") if state is not None else ""
    return str(selected or "").strip()

def encounter_debug_provider(window: Any) -> Any:
    from engine.encounter_report import compute_current_scene_encounter_report
    scene = getattr(window, "scene_controller", None)
    if scene is None:
        return None
    return compute_current_scene_encounter_report(scene)

def scene_dirty_provider(window: Any) -> dict[str, Any]:
    return {
        "enabled": bool(getattr(window, "show_debug", False)),
        "dirty": bool(getattr(window, "scene_dirty", False)),
        "reason": str(getattr(window, "scene_dirty_reason", "") or ""),
        "counter": int(getattr(window, "scene_dirty_counter", 0) or 0),
        "undo": int(len(getattr(window, "undo_stack", []) or [])),
        "redo": int(len(getattr(window, "redo_stack", []) or [])),
    }

def entity_select_provider(window: Any) -> dict[str, Any]:
    enabled = bool(getattr(window, "show_debug", False))
    state = getattr(window, "entity_select_state", None)
    ids = getattr(state, "selected_ids", None) if state is not None else None
    if not isinstance(ids, list):
        ids = []
    selected_ids = sorted({str(i).strip() for i in ids if isinstance(i, str) and str(i).strip()})
    primary_id = getattr(state, "primary_id", None) if state is not None else None
    primary_id = str(primary_id).strip() if isinstance(primary_id, str) and str(primary_id).strip() else (selected_ids[0] if selected_ids else "")

    clipboard = getattr(window, "entity_clipboard", None)
    clipboard_primary = ""
    clipboard_count = 0
    if isinstance(clipboard, dict):
        entities = clipboard.get("entities")
        if isinstance(entities, list) and entities:
            clipboard_count = len(entities)
            cp = clipboard.get("primary_id")
            if isinstance(cp, str) and cp.strip():
                clipboard_primary = cp.strip()

    transform_action = str(getattr(window, "last_transform_action", "") or "").strip()
    transform_count = int(getattr(window, "last_transform_count", 0) or 0)
    show_transform = (
        bool(transform_action)
        and transform_count > 0
        and int(getattr(window, "last_transform_counter", 0) or 0)
        == int(getattr(window, "scene_dirty_counter", 0) or 0)
    )

    props_action = str(getattr(window, "last_props_action", "") or "").strip()
    props_changed = int(getattr(window, "last_props_changed", 0) or 0)
    show_props = (
        bool(props_action)
        and props_changed > 0
        and int(getattr(window, "last_props_counter", 0) or 0)
        == int(getattr(window, "scene_dirty_counter", 0) or 0)
    )

    config_action = str(getattr(window, "last_config_action", "") or "").strip()
    config_changed = int(getattr(window, "last_config_changed", 0) or 0)
    show_config = (
        bool(config_action)
        and config_changed > 0
        and int(getattr(window, "last_config_counter", 0) or 0)
        == int(getattr(window, "scene_dirty_counter", 0) or 0)
    )

    if not (enabled and selected_ids):
        return {
            "enabled": enabled,
            "selected_ids": [],
            "primary_id": "",
            "primary": None,
            "clipboard_count": clipboard_count,
            "clipboard_primary": clipboard_primary,
            "transform_action": transform_action if show_transform else "",
            "transform_count": transform_count if show_transform else 0,
            "props_action": props_action if show_props else "",
            "props_changed": props_changed if show_props else 0,
            "config_action": config_action if show_config else "",
            "config_changed": config_changed if show_config else 0,
        }

    sc = getattr(window, "scene_controller", None)
    sprite = getattr(sc, "debug_find_sprite_by_entity_id", lambda _eid: None)(primary_id) if sc is not None else None

    prefab_id = getattr(state, "selected_prefab_id", "")
    if isinstance(sprite, optional_arcade.arcade.Sprite):
        entity_data = getattr(sprite, "mesh_entity_data", None)
        if isinstance(entity_data, dict):
            pid = entity_data.get("prefab_id")
            if isinstance(pid, str) and pid.strip():
                prefab_id = pid

    x = float(getattr(sprite, "center_x", 0.0)) if isinstance(sprite, optional_arcade.arcade.Sprite) else None
    y = float(getattr(sprite, "center_y", 0.0)) if isinstance(sprite, optional_arcade.arcade.Sprite) else None
    return {
        "enabled": enabled,
        "selected_ids": selected_ids,
        "primary_id": primary_id,
        "primary": {
            "id": str(primary_id),
            "prefab_id": str(prefab_id or ""),
            "pos": {"x": x, "y": y} if isinstance(x, float) and isinstance(y, float) else {},
        },
        "dup_count": int(getattr(window, "last_duplicate_count", 0) or 0)
        if int(getattr(window, "last_duplicate_counter", 0) or 0) == int(getattr(window, "scene_dirty_counter", 0) or 0)
        else 0,
        "dup_primary": str(getattr(window, "last_duplicate_primary", "") or "")
        if int(getattr(window, "last_duplicate_counter", 0) or 0) == int(getattr(window, "scene_dirty_counter", 0) or 0)
        else "",
        "clipboard_count": clipboard_count,
        "clipboard_primary": clipboard_primary,
        "transform_action": transform_action if show_transform else "",
        "transform_count": transform_count if show_transform else 0,
        "props_action": props_action if show_props else "",
        "props_changed": props_changed if show_props else 0,
        "config_action": config_action if show_config else "",
        "config_changed": config_changed if show_config else 0,
    }

def scene_inspector_provider(window: Any) -> dict[str, Any]:
    scene = getattr(window, "scene_controller", None)
    scene_path = getattr(scene, "current_scene_path", None)

    player_sprite = scene._find_player_sprite() if scene is not None else None
    player_payload: dict[str, Any] = {}
    if player_sprite is not None:
        player_payload = {"x": float(player_sprite.center_x), "y": float(player_sprite.center_y)}

    hover_payload: dict[str, Any] = {}
    if scene is not None:
        mx = getattr(window, "_mouse_x", None)
        my = getattr(window, "_mouse_y", None)
        if isinstance(mx, (int, float)) and isinstance(my, (int, float)) and hasattr(window, "screen_to_world"):
            try:
                world_x, world_y = window.screen_to_world(float(mx), float(my))
            except _PROVIDER_FALLBACK_EXCEPTIONS:
                _log_swallow("UOVP-001", "engine.ui_overlays.providers blanket exception fallback")
                world_x, world_y = None, None
            if isinstance(world_x, (int, float)) and isinstance(world_y, (int, float)):
                candidates: list[Any] = []
                layers = getattr(scene, "layers", {}) or {}
                for layer in layers.values():
                    try:
                        hits = optional_arcade.arcade.get_sprites_at_point((float(world_x), float(world_y)), layer)
                    except _PROVIDER_FALLBACK_EXCEPTIONS:
                        _log_swallow("UOVP-002", "engine.ui_overlays.providers blanket exception fallback")
                        hits = []
                    if hits:
                        candidates.extend(hits)
                sprite = candidates[-1] if candidates else None
                if sprite is not None:
                    entity_data = getattr(sprite, "mesh_entity_data", None)
                    if not isinstance(entity_data, dict):
                        entity_data = {}
                    hover_payload = {
                        "id": entity_data.get("id") or entity_data.get("entity_id"),
                        "prefab_id": entity_data.get("prefab_id"),
                        "mesh_name": entity_data.get("mesh_name") or getattr(sprite, "mesh_name", None),
                        "pos": {"x": float(sprite.center_x), "y": float(sprite.center_y)},
                    }
                    prefab_id = hover_payload.get("prefab_id")
                    if isinstance(prefab_id, str) and prefab_id.strip():
                        try:
                            from engine.prefabs import get_prefab_manager

                            manager = get_prefab_manager()
                            manager.load()
                            source = manager.prefab_sources.get(prefab_id)
                        except _PROVIDER_FALLBACK_EXCEPTIONS:
                            _log_swallow("UOVP-003", "engine.ui_overlays.providers blanket exception fallback")
                            source = None
                        if isinstance(source, str) and source.strip():
                            hover_payload["prefab_source"] = source

    flags_state = getattr(getattr(window, "game_state_controller", None), "state", None)
    flags_dict = getattr(flags_state, "flags", {}) if flags_state is not None else {}
    if not isinstance(flags_dict, dict):
        flags_dict = {}
    flags_total = len(flags_dict)
    true_keys = sorted(str(k) for k, v in flags_dict.items() if bool(v))
    flags_payload = {
        "total": flags_total,
        "on": len(true_keys),
        "keys": true_keys[:5],
    }

    # HD-2D info
    render_sort_mode = getattr(scene, "_render_sort_mode", "y_sort") if scene is not None else "y_sort"
    background_planes = getattr(scene, "_background_planes", []) if scene is not None else []
    background_planes_count = len(background_planes) if isinstance(background_planes, list) else 0

    return {
        "scene_path": str(scene_path or "-"),
        "player": player_payload,
        "hover": hover_payload,
        "flags": flags_payload,
        "render_sort_mode": str(render_sort_mode),
        "background_planes_count": background_planes_count,
    }


def hd2d_depth_debug_provider(window: Any) -> dict[str, Any]:
    """Provider for HD-2D depth debug overlay.

    Collects sprite render key info for debug display.
    """
    from engine.hd2d_debug_model import compute_hd2d_debug_payload

    scene = getattr(window, "scene_controller", None)
    if scene is None:
        return {
            "sort_mode": "y_sort",
            "sprite_count": 0,
            "plane_count": 0,
            "sprite_infos": [],
        }

    sort_mode = getattr(scene, "_render_sort_mode", "y_sort")
    background_planes = getattr(scene, "_background_planes", [])
    plane_count = len(background_planes) if isinstance(background_planes, list) else 0

    # Collect sprites from all layers
    all_sprites: list[Any] = []
    layers = getattr(scene, "layers", {}) or {}
    for layer in layers.values():
        try:
            all_sprites.extend(layer)
        except _PROVIDER_FALLBACK_EXCEPTIONS:
            _log_swallow("UOVP-004", "engine.ui_overlays.providers blanket exception fallback")
            pass

    return compute_hd2d_debug_payload(
        sort_mode=str(sort_mode),
        sprites=all_sprites,
        plane_count=plane_count,
    )


def background_planes_editor_provider(window: Any) -> dict[str, Any]:
    """Provider for background planes editor panel.

    Returns list of planes with editable fields for inspector UI.
    """
    from engine.editor.background_planes_edit_model import (
        compute_tiling_mode,
        list_background_planes,
    )

    scene = getattr(window, "scene_controller", None)
    scene_payload = getattr(scene, "_loaded_scene_data", None) if scene is not None else None
    if not isinstance(scene_payload, dict):
        return {
            "enabled": True,
            "planes": [],
            "selected_plane_id": "",
        }

    planes = list_background_planes(scene_payload)

    plane_entries = []
    for plane in planes:
        plane_entries.append({
            "id": plane.id,
            "asset_path": plane.asset_path,
            "parallax": plane.parallax,
            "render_layer": plane.render_layer,
            "alpha": plane.alpha,
            "offset_x": plane.offset_x,
            "offset_y": plane.offset_y,
            "tiling_mode": compute_tiling_mode(plane.repeat_x, plane.repeat_y),
        })

    # Get selected plane id from editor state if available
    editor_state = getattr(window, "background_plane_editor_state", None)
    selected_id = getattr(editor_state, "selected_plane_id", "") if editor_state is not None else ""

    return {
        "enabled": True,
        "planes": plane_entries,
        "selected_plane_id": str(selected_id),
    }


def tile_paint_provider(window: Any) -> dict[str, Any]:
    from engine.tile_paint_mode import compute_tile_paint_tool, world_to_tile

    state = getattr(window, "tile_paint_state", None)
    enabled = bool(getattr(window, "show_debug", False)) and bool(getattr(state, "enabled", False))
    layer_id = str(getattr(state, "layer_id", "") or "-")
    tile_id = int(getattr(state, "tile_id", 0)) if state is not None else 0

    world_x = None
    world_y = None
    tx = None
    ty = None
    try:
        world_x, world_y = window.screen_to_world(float(window.mouse_x), float(window.mouse_y))
    except _PROVIDER_FALLBACK_EXCEPTIONS:
        _log_swallow("UOVP-005", "engine.ui_overlays.providers blanket exception fallback")
        world_x, world_y = None, None

    sc = getattr(window, "scene_controller", None)
    instance = getattr(sc, "tilemap_instance", None) if sc is not None else None
    if instance is not None and isinstance(world_x, (int, float)) and isinstance(world_y, (int, float)):
        map_w, map_h = getattr(instance, "map_size", (0, 0))
        tile_w, tile_h = getattr(instance, "tile_size", (0, 0))
        hit = world_to_tile(
            map_width=int(map_w),
            map_height=int(map_h),
            tile_width=int(tile_w),
            tile_height=int(tile_h),
            world_x=float(world_x),
            world_y=float(world_y),
        )
        if hit is not None:
            tx, ty = hit

    mods = int(getattr(window, "_debug_last_modifiers", 0) or 0)
    tool = compute_tile_paint_tool(
        shift=bool(mods & optional_arcade.arcade.key.MOD_SHIFT),
        ctrl=bool(mods & optional_arcade.arcade.key.MOD_CTRL),
        alt=bool(mods & optional_arcade.arcade.key.MOD_ALT),
    )

    slots_raw = getattr(window, "tile_quick_slots", None)
    slots: dict[int, int] = {}
    if isinstance(slots_raw, dict):
        for k, v in slots_raw.items():
            if isinstance(k, int) and 1 <= int(k) <= 9 and isinstance(v, int):
                slots[int(k)] = int(v)

    recent_raw = getattr(window, "tile_recent", None)
    recent: list[int] = []
    if isinstance(recent_raw, list):
        recent = [int(v) for v in recent_raw if isinstance(v, int)]

    return {
        "enabled": enabled,
        "layer_id": layer_id,
        "tile_id": int(tile_id),
        "tool": tool,
        "slots": slots,
        "recent": recent,
        "hover": {"tx": tx, "ty": ty, "world_x": world_x, "world_y": world_y},
    }

def entity_paint_provider(window: Any) -> dict[str, Any]:
    from engine.entity_paint_mode import get_filtered_prefab_ids, get_selected_prefab_id, load_prefab_infos
    from engine.tile_paint_mode import world_to_tile

    state = getattr(window, "entity_paint_state", None)
    enabled = bool(getattr(window, "show_debug", False)) and bool(getattr(state, "enabled", False))
    if state is None:
        return {"enabled": False}

    if enabled and not getattr(state, "prefabs", ()):
        state.prefabs = load_prefab_infos()
        state.selected_index = 0

    prefab_ids = get_filtered_prefab_ids(state) if enabled else []
    selected = get_selected_prefab_id(state) if enabled else None
    if selected is None and prefab_ids:
        selected = prefab_ids[0]

    idx = 0
    if selected is not None and prefab_ids:
        try:
            idx = prefab_ids.index(selected)
        except ValueError:
            idx = int(getattr(state, "selected_index", 0) or 0) % len(prefab_ids)
    prefab_index = (idx + 1) if prefab_ids else 0

    world_x = None
    world_y = None
    mx = getattr(window, "_mouse_x", None)
    my = getattr(window, "_mouse_y", None)
    if isinstance(mx, (int, float)) and isinstance(my, (int, float)) and hasattr(window, "screen_to_world"):
        try:
            world_x, world_y = window.screen_to_world(float(mx), float(my))
        except _PROVIDER_FALLBACK_EXCEPTIONS:
            _log_swallow("UOVP-006", "engine.ui_overlays.providers blanket exception fallback")
            world_x, world_y = None, None

    tx = None
    ty = None
    scene = getattr(window, "scene_controller", None)
    instance = getattr(scene, "tilemap_instance", None) if scene is not None else None
    if isinstance(world_x, (int, float)) and isinstance(world_y, (int, float)):
        map_w = map_h = tile_w = tile_h = None
        if instance is not None:
            mw, mh = getattr(instance, "map_size", (None, None))
            tw, th = getattr(instance, "tile_size", (None, None))
            if all(isinstance(v, int) and v > 0 for v in (mw, mh, tw, th)):
                map_w, map_h, tile_w, tile_h = int(mw or 0), int(mh or 0), int(tw or 0), int(th or 0)
        if map_w is None:
            payload: Dict[str, Any] = getattr(scene, "get_authored_scene_payload", lambda: {})()
            tilemap = payload.get("tilemap") if isinstance(payload, dict) and isinstance(payload.get("tilemap"), dict) else None
            mw = tilemap.get("width") if isinstance(tilemap, dict) else None
            mh = tilemap.get("height") if isinstance(tilemap, dict) else None
            tw = tilemap.get("tilewidth") if isinstance(tilemap, dict) else None
            th = tilemap.get("tileheight") if isinstance(tilemap, dict) else None
            if all(isinstance(v, int) and v > 0 for v in (mw, mh, tw, th)):
                map_w, map_h, tile_w, tile_h = int(mw or 0), int(mh or 0), int(tw or 0), int(th or 0)
        if map_w is not None and map_h is not None and tile_w is not None and tile_h is not None:
            hit = world_to_tile(
                map_width=int(map_w),
                map_height=int(map_h),
                tile_width=int(tile_w),
                tile_height=int(tile_h),
                world_x=float(world_x),
                world_y=float(world_y),
            )
            if hit is not None:
                tx, ty = int(hit[0]), int(hit[1])

    hover_entity: dict[str, Any] = {}
    if enabled:
        try:
            from engine.tooling_runtime.authoring_snippets import (
                get_effective_hover_payload,
                get_scene_inspector_payload,
            )

            inspector = get_scene_inspector_payload(window)
            inspector = get_effective_hover_payload(window, inspector)
            hover = inspector.get("hover") if isinstance(inspector, dict) and isinstance(inspector.get("hover"), dict) else None
            if isinstance(hover, dict):
                hover_entity = {
                    "id": hover.get("id"),
                    "prefab_id": hover.get("prefab_id"),
                    "name": hover.get("mesh_name"),
                }
        except _PROVIDER_FALLBACK_EXCEPTIONS:
            _log_swallow("UOVP-007", "engine.ui_overlays.providers blanket exception fallback")
            hover_entity = {}

    return {
        "enabled": enabled,
        "prefab_id": str(selected) if isinstance(selected, str) else None,
        "prefab_index": int(prefab_index) if prefab_ids else 0,
        "prefab_count": int(len(prefab_ids)),
        "filter_mode": str(getattr(state, "filter_mode", "all")),
        "persist_armed": bool(getattr(state, "persist_armed", False)),
        "hover": {"world_x": world_x, "world_y": world_y, "tx": tx, "ty": ty},
        "hover_entity": hover_entity,
        "slots": {
            int(k): str(v).strip()
            for k, v in (getattr(window, "prefab_quick_slots", {}) or {}).items()
            if isinstance(k, int) and 1 <= int(k) <= 9 and isinstance(v, str) and str(v).strip()
        },
        "recent": [
            str(v).strip()
            for v in (getattr(window, "prefab_recent", []) or [])
            if isinstance(v, str) and str(v).strip()
        ],
    }

def capture_provider(window: Any) -> dict[str, Any]:
    from engine.capture_mode import iter_layer_ids_sorted_by_z_id
    from engine.tile_paint_mode import world_to_tile

    state = getattr(window, "capture_state", None)
    if state is None:
        return {"enabled": False}
    enabled = bool(getattr(window, "show_debug", False)) and bool(getattr(state, "enabled", False))

    sc = getattr(window, "scene_controller", None)
    payload = getattr(sc, "_loaded_scene_data", None) if sc is not None else None

    layer_ids = iter_layer_ids_sorted_by_z_id(payload) if isinstance(payload, dict) else []

    rect_obj = getattr(state, "rect", None)
    rect_payload = None
    if rect_obj is not None:
        rect_payload = {
            "x0": int(rect_obj.x0),
            "y0": int(rect_obj.y0),
            "x1": int(rect_obj.x1),
            "y1": int(rect_obj.y1),
            "w": int(rect_obj.w),
            "h": int(rect_obj.h),
        }

    hover: Dict[str, Any] = {"tx": None, "ty": None, "tile_id": None, "layer_id": str(getattr(state, "layer_id", "") or "-")}
    instance = getattr(sc, "tilemap_instance", None) if sc is not None else None
    if instance is not None:
        map_w, map_h = getattr(instance, "map_size", (0, 0))
        tile_w, tile_h = getattr(instance, "tile_size", (0, 0))
        try:
            wx, wy = window.screen_to_world(float(window.mouse_x), float(window.mouse_y))
        except _PROVIDER_FALLBACK_EXCEPTIONS:
            _log_swallow("UOVP-008", "engine.ui_overlays.providers blanket exception fallback")
            wx, wy = None, None
        if isinstance(wx, (int, float)) and isinstance(wy, (int, float)):
            hit = world_to_tile(
                map_width=int(map_w),
                map_height=int(map_h),
                tile_width=int(tile_w),
                tile_height=int(tile_h),
                world_x=float(wx),
                world_y=float(wy),
            )
            if hit is not None:
                tx, ty = hit
                hover["tx"] = int(tx)
                hover["ty"] = int(ty)
                if isinstance(payload, dict) and str(getattr(state, "layer_id", "") or "").strip():
                    entry = None
                    tilemap = payload.get("tilemap") if isinstance(payload.get("tilemap"), dict) else None
                    raw_layers = tilemap.get("tile_layers") if isinstance(tilemap, dict) else None
                    if isinstance(raw_layers, list):
                        for e in raw_layers:
                            if isinstance(e, dict) and e.get("id") == str(getattr(state, "layer_id", "")).strip():
                                entry = e
                                break
                    tiles = entry.get("tiles") if isinstance(entry, dict) else None
                    if (
                        isinstance(tiles, list)
                        and len(tiles) == int(map_w) * int(map_h)
                        and all(isinstance(v, int) for v in tiles)
                    ):
                        idx = int(ty) * int(map_w) + int(tx)
                        hover["tile_id"] = int(tiles[idx])

    return {
        "enabled": enabled,
        "mode": str(getattr(state, "mode", "stamp")),
        "rect": rect_payload,
        "layers": len(layer_ids),
        "include_entities": bool(getattr(state, "include_entities", True)),
        "persist_armed": bool(getattr(window, "capture_persist_armed", False)),
        "persist_status": str(getattr(window, "capture_persist_status", "") or ""),
        "hover": hover,
    }


def profiler_provider(window: Any) -> dict[str, Any]:
    overlay = getattr(window, "profiler_overlay", None)
    enabled = bool(getattr(overlay, "visible", False))
    if not enabled:
        return {
            "profiler_enabled": False,
            "profiler_rows": [],
        }

    perf_stats = getattr(window, "perf_stats", None)
    snapshotter = getattr(perf_stats, "snapshot", None)
    if not callable(snapshotter):
        return {
            "profiler_enabled": True,
            "profiler_rows": ["PROFILER (Shift+F6)", "perf_stats: unavailable"],
        }
    try:
        perf_snapshot = snapshotter()
    except _PROVIDER_FALLBACK_EXCEPTIONS:
        _log_swallow("UOVP-009", "engine.ui_overlays.providers blanket exception fallback")
        return {
            "profiler_enabled": True,
            "profiler_rows": ["PROFILER (Shift+F6)", "perf_stats: unavailable"],
        }
    counters: dict[str, Any] = {}
    raw_meta = getattr(perf_snapshot, "meta", None)
    if isinstance(raw_meta, dict):
        raw_counters = raw_meta.get("counters")
        if isinstance(raw_counters, dict):
            counters = raw_counters

    def _counter_int(*keys: str) -> int | None:
        for key in keys:
            if key not in counters:
                continue
            value = counters.get(key)
            if value is None:
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        return None

    scene_controller = getattr(window, "scene_controller", None)
    get_all_entities = getattr(scene_controller, "get_all_entities", None) if scene_controller is not None else None
    entity_count = _counter_int("world.entities.count")
    if entity_count is None and callable(get_all_entities):
        try:
            entity_count = len(get_all_entities())
        except _PROVIDER_FALLBACK_EXCEPTIONS:
            _log_swallow("UOVP-010", "engine.ui_overlays.providers blanket exception fallback")
            entity_count = 0

    watcher = getattr(window, "asset_hot_reload_watcher", None)
    hot_reload_enabled = bool(is_hot_reload_enabled())
    hot_reload_running = bool(getattr(watcher, "running", False))
    input_controller = getattr(window, "input_controller", None)
    input_manager = getattr(input_controller, "manager", None) if input_controller is not None else None
    rumble_enabled = False
    rumble_strength = 1.0
    rumble_backend_connected = False
    if input_manager is not None:
        enabled_getter = getattr(input_manager, "is_rumble_enabled", None)
        if callable(enabled_getter):
            try:
                rumble_enabled = bool(enabled_getter())
            except _PROVIDER_FALLBACK_EXCEPTIONS:
                _log_swallow("UOVP-011", "engine.ui_overlays.providers blanket exception fallback")
                rumble_enabled = False
        strength_getter = getattr(input_manager, "get_rumble_strength", None)
        if callable(strength_getter):
            try:
                rumble_strength = float(strength_getter())
            except (TypeError, ValueError):
                rumble_strength = 1.0
        backend_getter = getattr(input_manager, "has_rumble_backend", None)
        if callable(backend_getter):
            try:
                rumble_backend_connected = bool(backend_getter())
            except _PROVIDER_FALLBACK_EXCEPTIONS:
                _log_swallow("UOVP-012", "engine.ui_overlays.providers blanket exception fallback")
                rumble_backend_connected = False
    runtime_summary = {
        "entity_count": int(entity_count or 0),
        "hot_reload_enabled": hot_reload_enabled,
        "hot_reload_running": hot_reload_running,
        "rumble_enabled": rumble_enabled,
        "rumble_strength": max(0.0, min(rumble_strength, 1.0)),
        "rumble_backend_connected": rumble_backend_connected,
    }
    if hot_reload_enabled or hot_reload_running:
        last_stats = getattr(window, "_last_hot_reload_stats", None)
        if isinstance(last_stats, dict):
            shader_reloaded = last_stats.get("shader_reloaded")
            shader_failed = last_stats.get("shader_failed")
            textures_reloaded = last_stats.get("textures_reloaded")
            textures_failed = last_stats.get("textures_failed")
            audio_reloaded = last_stats.get("audio_reloaded")
            audio_failed = last_stats.get("audio_failed")
            try:
                runtime_summary["shader_reloaded"] = int(shader_reloaded) if shader_reloaded is not None else 0
            except (TypeError, ValueError):
                runtime_summary["shader_reloaded"] = 0
            try:
                runtime_summary["shader_failed"] = int(shader_failed) if shader_failed is not None else 0
            except (TypeError, ValueError):
                runtime_summary["shader_failed"] = 0
            try:
                runtime_summary["textures_reloaded"] = int(textures_reloaded) if textures_reloaded is not None else 0
            except (TypeError, ValueError):
                runtime_summary["textures_reloaded"] = 0
            try:
                runtime_summary["textures_failed"] = int(textures_failed) if textures_failed is not None else 0
            except (TypeError, ValueError):
                runtime_summary["textures_failed"] = 0
            try:
                runtime_summary["audio_reloaded"] = int(audio_reloaded) if audio_reloaded is not None else 0
            except (TypeError, ValueError):
                runtime_summary["audio_reloaded"] = 0
            try:
                runtime_summary["audio_failed"] = int(audio_failed) if audio_failed is not None else 0
            except (TypeError, ValueError):
                runtime_summary["audio_failed"] = 0
    draw_calls = _counter_int("render.draw_calls", "render_draw_calls")
    if draw_calls is not None:
        runtime_summary["draw_calls"] = int(draw_calls)

    from engine.ui_overlays.profiler_overlay import render_rows  # noqa: PLC0415

    rows = render_rows(
        perf_snapshot,
        overlay_perf_snapshot=read_overlay_perf_telemetry(reset=False),
        runtime_summary=runtime_summary,
    )
    return {
        "profiler_enabled": True,
        "profiler_rows": rows,
    }

def command_palette_provider(window: Any) -> dict[str, Any]:
    _perf_start = perf_counter()

    def _ret(payload: dict[str, Any]) -> dict[str, Any]:
        elapsed_ms = (perf_counter() - _perf_start) * 1000.0
        _record_overlay_perf("providers_total", elapsed_ms)
        _record_overlay_perf("command_palette_provider", elapsed_ms)
        return payload

    import json
    from engine.command_palette import build_default_commands, filter_commands, filter_options
    from engine.command_palette_controller import get_command_palette_recent_command_ids
    from engine.command_palette_preview import build_arg_preview, build_arg_suggestions
    from engine.palette_mode import get_state

    enabled = bool(getattr(window, "show_debug", False)) and bool(getattr(window, "command_palette_enabled", False))
    if not enabled:
        return _ret({"enabled": False})
    query = str(getattr(window, "command_palette_query", "") or "")
    idx = int(getattr(window, "command_palette_index", 0) or 0)

    commands = build_default_commands(window)
    filtered = filter_commands(commands, query)
    if not filtered:
        help_enabled = bool(getattr(window, "command_palette_help_enabled", False))
        help_rows_empty: list[str] = []
        if help_enabled:
            from engine.command_palette_help import build_command_help_rows  # noqa: PLC0415

            help_rows_empty = build_command_help_rows("", command_title="", command_section="")
        return _ret({
            "enabled": True,
            "query": query,
            "rows": [],
            "selected_row": 0,
            "help_enabled": help_enabled,
            "help_rows": help_rows_empty,
            "prompt_active": bool(getattr(window, "command_palette_prompt_active", False)),
            "prompt_text": str(getattr(window, "command_palette_prompt_text", "") or ""),
            "prompt_kind": str(getattr(window, "command_palette_prompt_kind", "text") or "text"),
            "prompt_query": str(getattr(window, "command_palette_prompt_query", "") or ""),
            "prompt_selected_row": int(getattr(window, "command_palette_prompt_index", 0) or 0),
            "prompt_placeholder": str(getattr(window, "command_palette_prompt_placeholder", "") or ""),
            "prompt_title": str(getattr(window, "command_palette_prompt_title", "") or ""),
        })

    idx = max(0, min(int(idx), len(filtered) - 1))

    page_start = 0 if idx < 10 else (idx - 9)
    if page_start > max(0, len(filtered) - 10):
        page_start = max(0, len(filtered) - 10)
    page = filtered[page_start : page_start + 10]
    page_index = idx - page_start
    selected_cmd = filtered[idx]

    active_mode = "none"
    try:
        if bool(get_state().enabled):
            active_mode = "palette"
    except Exception:  # noqa: BLE001  # REASON: provider isolation fallback
        _log_swallow("UOVP-013", "engine.ui_overlays.providers blanket exception fallback")
        active_mode = "none"
    if bool(getattr(getattr(window, "capture_state", None), "enabled", False)):
        active_mode = "capture"
    if bool(getattr(getattr(window, "entity_paint_state", None), "enabled", False)):
        active_mode = "entity_paint"
    if bool(getattr(getattr(window, "tile_paint_state", None), "enabled", False)):
        active_mode = "tile_paint"

    commands_by_id = {str(getattr(c, "id", "") or ""): c for c in commands}
    recent_command_ids = tuple(get_command_palette_recent_command_ids(window))
    recent_commands = [commands_by_id[cid] for cid in recent_command_ids if cid in commands_by_id]

    rows: list[dict[str, Any]] = []
    if recent_commands:
        rows.append({"kind": "section", "title": "Recent"})
        for c in recent_commands:
            enabled_cmd = True
            disabled_reason = ""
            try:
                enabled_cmd, disabled_reason = c.is_enabled(window)
            except Exception:  # noqa: BLE001  # REASON: provider isolation fallback
                _log_swallow("UOVP-014", "engine.ui_overlays.providers blanket exception fallback")
                enabled_cmd, disabled_reason = True, ""
            rows.append(
                {
                    "kind": "command",
                    "id": c.id,
                    "title": c.title,
                    "hotkey_hint": c.hotkey_hint,
                    "enabled": bool(enabled_cmd),
                    "disabled_reason": str(disabled_reason or "").strip(),
                }
            )

    last_section = None
    for c in page:
        section = str(getattr(c, "section", "") or "").strip() or "Other"
        if section != last_section:
            rows.append({"kind": "section", "title": section})
            last_section = section
        enabled_cmd = True
        disabled_reason = ""
        try:
            enabled_cmd, disabled_reason = c.is_enabled(window)
        except Exception:  # noqa: BLE001  # REASON: provider isolation fallback
            _log_swallow("UOVP-015", "engine.ui_overlays.providers blanket exception fallback")
            enabled_cmd, disabled_reason = True, ""
        rows.append(
            {
                "kind": "command",
                "id": c.id,
                "title": c.title,
                "hotkey_hint": c.hotkey_hint,
                "enabled": bool(enabled_cmd),
                "disabled_reason": str(disabled_reason or "").strip(),
            }
        )

    # selected_row is within the command rows (not headers)
    selected_row = int(len(recent_commands) + page_index)

    prompt_active = bool(getattr(window, "command_palette_prompt_active", False))
    prompt_text = str(getattr(window, "command_palette_prompt_text", "") or "")
    prompt_kind = str(getattr(window, "command_palette_prompt_kind", "text") or "text")
    prompt_query = str(getattr(window, "command_palette_prompt_query", "") or "")
    prompt_index = int(getattr(window, "command_palette_prompt_index", 0) or 0)
    prompt_placeholder = str(getattr(window, "command_palette_prompt_placeholder", "") or "")
    prompt_title = str(getattr(window, "command_palette_prompt_title", "") or "")
    prompt_command_id = str(getattr(window, "command_palette_prompt_command_id", "") or "")
    help_enabled = bool(getattr(window, "command_palette_help_enabled", False))
    prompt_preview = ""
    prompt_error = ""

    prompt_rows: list[dict[str, Any]] = []
    prompt_selected_row = 0
    prompt_no_matches = False
    prompt_match_count = 0
    if prompt_active and prompt_kind.strip().lower() == "pick":
        by_id = {c.id: c for c in commands}
        cmd = by_id.get(prompt_command_id)
        provider = None
        steps = getattr(window, "command_palette_prompt_steps", ())
        step_index = int(getattr(window, "command_palette_prompt_step_index", 0) or 0)
        if isinstance(steps, tuple) and steps:
            current = steps[step_index] if 0 <= step_index < len(steps) else None
            provider = getattr(current, "options_provider", None)
        if provider is None:
            provider = getattr(getattr(cmd, "prompt", None), "options_provider", None) if cmd is not None else None
        options = provider(window) if callable(provider) else []
        filtered_opts = filter_options(options, prompt_query)
        prompt_match_count = len(filtered_opts)
        if not filtered_opts:
            prompt_no_matches = True
            prompt_rows = []
            prompt_selected_row = 0
        else:
            idx2 = max(0, min(int(prompt_index), len(filtered_opts) - 1))
            page_start = 0 if idx2 < 8 else (idx2 - 7)
            if page_start > max(0, len(filtered_opts) - 8):
                page_start = max(0, len(filtered_opts) - 8)
            prompt_page = filtered_opts[page_start : page_start + 8]
            prompt_selected_row = idx2 - page_start
            prompt_rows = [{"value": value, "label": label} for (value, label) in prompt_page]
    elif prompt_active and prompt_kind.strip().lower() == "text":
        preview_payload = build_arg_preview(prompt_command_id, prompt_text)
        suggestions_context: dict[str, Any] | None = None
        if str(prompt_command_id).strip().startswith("planes."):
            sc = getattr(window, "scene_controller", None)
            scene = getattr(sc, "_loaded_scene_data", None) if sc is not None else None
            if isinstance(scene, dict):
                raw_planes = scene.get("background_planes")
                plane_ids_seen: dict[str, None] = {}
                if isinstance(raw_planes, list):
                    for entry in raw_planes:
                        if not isinstance(entry, dict):
                            continue
                        raw_id = entry.get("id")
                        if isinstance(raw_id, str):
                            plane_id = raw_id.strip()
                            if plane_id:
                                plane_ids_seen.setdefault(plane_id, None)
                plane_ids = sorted(plane_ids_seen)
                selected_plane_id = _selected_plane_id_for_suggestions(window)
                suggestions_context = {
                    "plane_count": len(plane_ids),
                    "plane_ids": plane_ids,
                    "selected_plane_id": selected_plane_id,
                }
        suggestions = build_arg_suggestions(prompt_command_id, prompt_text, context=suggestions_context)
        prompt_match_count = len(suggestions)
        if suggestions:
            idx3 = max(0, min(int(prompt_index), len(suggestions) - 1))
            page_start = 0 if idx3 < 8 else (idx3 - 7)
            if page_start > max(0, len(suggestions) - 8):
                page_start = max(0, len(suggestions) - 8)
            prompt_suggestions_page = suggestions[page_start : page_start + 8]
            prompt_selected_row = idx3 - page_start
            prompt_rows = [{"value": s, "label": s} for s in prompt_suggestions_page]
        else:
            prompt_rows = []
            prompt_selected_row = 0
        if bool(preview_payload.get("ok")):
            prompt_preview = str(preview_payload.get("preview") or "").strip()
        else:
            prompt_error = str(preview_payload.get("error") or "").strip()

    preview_line = ""
    preview_line2 = ""
    macro_id = str(getattr(selected_cmd, "macro_id", "") or "").strip()
    if not prompt_active and macro_id:
        sc = getattr(window, "scene_controller", None)
        if sc is not None:
            last_args = getattr(window, "last_macro_args", None)
            last_args = last_args if isinstance(last_args, dict) else {}
            defaults = getattr(selected_cmd, "macro_defaults", None)
            defaults = defaults if isinstance(defaults, dict) else None
            args = defaults if defaults is not None else last_args.get(macro_id)
            if isinstance(args, dict):
                # Anchor resolution.
                anchor = str(args.get("anchor") or "cursor").strip().lower() or "cursor"
                primary_id = ""
                selected_ids: list[str] = []
                state = getattr(window, "entity_select_state", None)
                ids = getattr(state, "selected_ids", None) if state is not None else None
                if isinstance(ids, list):
                    selected_ids = [str(v).strip() for v in ids if isinstance(v, str) and str(v).strip()]
                pid = getattr(state, "primary_id", None) if state is not None else None
                primary_id = (
                    str(pid).strip()
                    if isinstance(pid, str) and str(pid).strip()
                    else (sorted(selected_ids)[0] if selected_ids else "")
                )

                pos = None
                if anchor == "primary":
                    if selected_ids and primary_id:
                        authored: Any = getattr(sc, "get_authored_scene_payload", lambda: {})()
                        if isinstance(authored, dict):
                            ents = authored.get("entities")
                            if isinstance(ents, list):
                                for e in ents:
                                    if isinstance(e, dict) and str(e.get("id") or "") == primary_id:
                                        try:
                                            pos = (float(e.get("x", 0.0)), float(e.get("y", 0.0)))
                                        except _PROVIDER_FALLBACK_EXCEPTIONS:
                                            _log_swallow("UOVP-016", "engine.ui_overlays.providers blanket exception fallback")
                                            pos = (0.0, 0.0)
                                        break
                    if pos is None:
                        preview_line = "PREVIEW unavailable reason=no_selection"
                elif anchor == "cursor":
                    input_ctrl = getattr(window, "input_controller", None)
                    mx = getattr(input_ctrl, "mouse_x", None) if input_ctrl is not None else None
                    my = getattr(input_ctrl, "mouse_y", None) if input_ctrl is not None else None
                    to_world = getattr(window, "screen_to_world", None)
                    if callable(to_world) and isinstance(mx, (int, float)) and isinstance(my, (int, float)):
                        try:
                            cx, cy = to_world(float(mx), float(my))
                            pos = (float(cx), float(cy))
                        except _PROVIDER_FALLBACK_EXCEPTIONS:
                            _log_swallow("UOVP-017", "engine.ui_overlays.providers blanket exception fallback")
                            pos = None

                if pos is None and not preview_line:
                    authored = getattr(sc, "get_authored_scene_payload", lambda: {})()
                    player_pos = None
                    if isinstance(authored, dict):
                        ents = authored.get("entities")
                        if isinstance(ents, list):
                            for e in ents:
                                if isinstance(e, dict) and str(e.get("prefab_id") or "") == "player":
                                    try:
                                        player_pos = (float(e.get("x", 0.0)), float(e.get("y", 0.0)))
                                    except _PROVIDER_FALLBACK_EXCEPTIONS:
                                        _log_swallow("UOVP-018", "engine.ui_overlays.providers blanket exception fallback")
                                        player_pos = (0.0, 0.0)
                                    break
                    pos = player_pos or (0.0, 0.0)

                if not preview_line:
                    preview = None
                    if macro_id == "macro.objective_zone":
                        zone_id = str(args.get("zone_id") or "").strip()
                        set_flag = str(args.get("set_flag") or "").strip()
                        radius = args.get("radius")
                        if not zone_id or not set_flag or radius in (None, ""):
                            preview_line = "PREVIEW unavailable reason=missing_args"
                        elif pos:
                            previewer = getattr(sc, "debug_preview_macro_objective_zone", None)
                            if callable(previewer):
                                preview = previewer(
                                    center_x=float(pos[0]),
                                    center_y=float(pos[1]),
                                    zone_id=zone_id,
                                    set_flag=set_flag,
                                    radius=float(radius or 0),
                                    toast=str(args.get("toast") or "").strip() or None,
                                )
                    elif macro_id == "macro.door_transition":
                        target_scene = str(args.get("target_scene") or "").strip()
                        spawn_id = str(args.get("spawn_id") or "").strip()
                        if not target_scene or not spawn_id:
                            preview_line = "PREVIEW unavailable reason=missing_args"
                        elif pos:
                            previewer = getattr(sc, "debug_preview_macro_door_transition", None)
                            if callable(previewer):
                                cx = float(pos[0])
                                cy = float(pos[1])
                                preview = previewer(
                                    center_x=cx,
                                    center_y=cy,
                                    target_scene=target_scene,
                                    spawn_id=spawn_id,
                                    primary_id=primary_id or None,
                                )
                    elif macro_id == "macro.dialogue_choice_flag":
                        speaker_id = str(args.get("speaker_id") or "").strip()
                        choice_id = str(args.get("choice_id") or "").strip()
                        choice_text = str(args.get("choice_text") or "").strip()
                        set_flag = str(args.get("set_flag") or "").strip()
                        if not speaker_id or not choice_id or not choice_text or not set_flag:
                            preview_line = "PREVIEW unavailable reason=missing_args"
                        else:
                            previewer = getattr(sc, "debug_preview_macro_dialogue_choice_flag", None)
                            if callable(previewer):
                                preview = previewer(
                                    speaker_id=speaker_id,
                                    choice_id=choice_id,
                                    choice_text=choice_text,
                                    set_flag=set_flag,
                                    toast=str(args.get("toast") or "").strip() or None,
                                )

                    if isinstance(preview, dict):
                        create_n = int(preview.get("will_create", 0) or 0)
                        update_n = int(preview.get("will_update", 0) or 0)
                        create_ids_raw = preview.get("create_ids")
                        create_ids: list[Any] = create_ids_raw if isinstance(create_ids_raw, list) else []
                        update_ids_raw = preview.get("update_ids")
                        update_ids: list[Any] = update_ids_raw if isinstance(update_ids_raw, list) else []
                        ids_combined = []
                        for v in create_ids + update_ids:
                            if isinstance(v, str) and v.strip():
                                ids_combined.append(v.strip())
                        first_ids = ",".join(sorted(ids_combined)[:3])
                        preview_line = f"PREVIEW create={create_n} update={update_n} (first ids: {first_ids})"

                if defaults is not None:
                    last = last_args.get(macro_id)
                    if isinstance(last, dict) and last:
                        preview_line2 = "LAST " + json.dumps(last, sort_keys=True)

    help_rows: list[str] = []
    if help_enabled:
        from engine.command_palette_help import build_command_help_rows  # noqa: PLC0415

        help_command = selected_cmd
        if prompt_active and prompt_command_id:
            by_id = {c.id: c for c in commands}
            prompt_cmd = by_id.get(prompt_command_id)
            if prompt_cmd is not None:
                help_command = prompt_cmd
        help_rows = build_command_help_rows(
            str(getattr(help_command, "id", "") or ""),
            command_title=str(getattr(help_command, "title", "") or ""),
            command_section=str(getattr(help_command, "section", "") or ""),
        )

    return _ret({
        "enabled": True,
        "query": query,
        "rows": rows,
        "selected_row": selected_row,
        "help_enabled": help_enabled,
        "help_rows": help_rows,
        "preview_line": preview_line,
        "preview_line2": preview_line2,
        "dirty": bool(getattr(window, "scene_dirty", False)),
        "rev": int(getattr(window, "scene_dirty_counter", 0) or 0),
        "armed": bool(getattr(window, "scene_persist_armed", False)),
        "undo": len(getattr(window, "undo_stack", []) or []),
        "redo": len(getattr(window, "redo_stack", []) or []),
        "active_mode": active_mode,
        "prompt_active": prompt_active,
        "prompt_text": prompt_text,
        "prompt_kind": prompt_kind,
        "prompt_query": prompt_query,
        "prompt_rows": prompt_rows,
        "prompt_selected_row": prompt_selected_row,
        "prompt_no_matches": prompt_no_matches,
        "prompt_match_count": prompt_match_count,
        "prompt_placeholder": prompt_placeholder,
        "prompt_title": prompt_title,
        "prompt_preview": prompt_preview,
        "prompt_error": prompt_error,
    })


def editor_command_palette_provider(window: Any) -> dict[str, Any]:
    from engine.editor_commands import (
        filter_commands,
        get_all_commands,
        get_palette_focus_target,
    )

    editor = getattr(window, "editor_controller", None)
    from engine.editor.editor_panels_query import panels_is_open  # noqa: PLC0415

    enabled = bool(
        editor
        and getattr(editor, "active", False)
        and panels_is_open(editor, "command_palette")
    )
    if not enabled:
        return {"enabled": False}

    search = getattr(editor, "search", None)
    query = ""
    idx = 0
    if search is not None:
        getter = getattr(search, "get_command_palette_state", None)
        if callable(getter):
            query, idx = getter()

    focus_target = get_palette_focus_target(window)
    commands = filter_commands(get_all_commands(window), query, focus_target=focus_target)
    if not commands:
        return {"enabled": True, "query": query, "rows": [], "selected_row": 0}

    page = commands[:8]
    selected = max(0, min(idx, len(page) - 1))
    rows = [
        {
            "kind": "command",
            "id": c.id,
            "title": c.title,
            "hotkey_hint": "",
            "enabled": True,
            "disabled_reason": "",
        }
        for c in page
    ]
    return {
        "enabled": True,
        "query": query,
        "rows": rows,
        "selected_row": int(selected),
    }

def interact_prompt_provider(window: Any) -> Any:
    from engine.interaction import DEFAULT_INTERACT_MAX_DIST, pick_interactable

    scene = getattr(window, "scene_controller", None)
    if scene is None:
        return None
    finder = getattr(scene, "_find_player_sprite", None)
    if not callable(finder):
        return None
    try:
        player_sprite = finder()
    except _PROVIDER_FALLBACK_EXCEPTIONS:
        _log_swallow("UOVP-019", "engine.ui_overlays.providers blanket exception fallback")
        player_sprite = None
    if player_sprite is None:
        return None

    try:
        entities = list(window.all_sprites)
    except _PROVIDER_FALLBACK_EXCEPTIONS:
        _log_swallow("UOVP-020", "engine.ui_overlays.providers blanket exception fallback")
        return None
    getter = getattr(window, "get_flag", None)
    return pick_interactable(
        entities,
        player_pos=(float(player_sprite.center_x), float(player_sprite.center_y)),
        max_dist=DEFAULT_INTERACT_MAX_DIST,
        exclude_entity=player_sprite,
        get_flag=getter if callable(getter) else None,
    )

def objective_tracker_provider(window: Any) -> Sequence[str]:
    from engine.ui import compute_objective_tracker_lines
    demo_complete_visible = bool(getattr(getattr(window, "demo_complete_overlay", None), "visible", False))
    getter = getattr(window, "get_flag", None)
    if not callable(getter):
        return []
    return compute_objective_tracker_lines(getter, demo_complete_visible=demo_complete_visible)


def hd2d_preview_indicator_provider(window: Any) -> dict[str, Any]:
    """Provider for HD-2D preset preview indicator overlay.

    Returns:
        Dict with:
            visible: True if HD-2D preview is active
            preset_id: The preset ID being previewed (or None)
    """
    editor = getattr(window, "editor_controller", None)
    if editor is None:
        return {"visible": False, "preset_id": None}

    active = bool(getattr(editor, "_hd2d_preview_active", False))
    preset_id = getattr(editor, "_hd2d_preview_preset_id", None)
    if not active or not preset_id:
        return {"visible": False, "preset_id": None}

    return {"visible": True, "preset_id": str(preset_id)}


def hd2d_settings_panel_provider(window: Any) -> dict[str, Any]:
    """Provider for HD-2D settings panel in inspector.

    Returns:
        Dict with:
            visible: True if no entity selected (show scene settings)
            settings: Dict of current HD-2D settings values
            active_preset: Preset ID if current settings match a preset (or None)
            presets: List of {id, name} for preset buttons
    """
    from engine.editor.hd2d_look_presets_model import list_hd2d_presets  # noqa: PLC0415
    from engine.editor.hd2d_settings_panel_model import (  # noqa: PLC0415
        detect_active_preset,
        parse_hd2d_scene_settings,
        parse_hd2d_scene_settings_dict,
    )

    editor = getattr(window, "editor_controller", None)
    if editor is None or not getattr(editor, "active", False):
        return {"visible": False, "settings": {}, "active_preset": None, "presets": []}

    # Only show when no entity is selected
    primary_id = getattr(editor, "_primary_selected_id", None)
    selected_ids = getattr(editor, "_selected_entity_ids", [])
    has_selection = bool(primary_id) or (isinstance(selected_ids, list) and len(selected_ids) > 0)

    # Get scene payload
    scene_controller = getattr(window, "scene_controller", None)
    scene_payload = getattr(scene_controller, "_loaded_scene_data", {}) if scene_controller else {}
    if not isinstance(scene_payload, dict):
        scene_payload = {}

    # Parse settings
    parsed = parse_hd2d_scene_settings(scene_payload)
    settings_dict = parse_hd2d_scene_settings_dict(scene_payload)
    active_preset = detect_active_preset(parsed)

    # Build preset list
    presets = [{"id": p.id, "name": p.name} for p in list_hd2d_presets()]

    return {
        "visible": not has_selection,
        "settings": settings_dict,
        "active_preset": active_preset,
        "presets": presets,
    }


def hd2d_entity_overrides_provider(window: Any) -> dict[str, Any]:
    """Provider for HD-2D entity overrides panel in inspector.

    Returns:
        Dict with:
            visible: True if an entity is selected
            entity_id: The selected entity ID (or None)
            overrides: Dict of current override values (None = inherit)
            has_overrides: True if entity has any overrides set
            override_count: Number of overrides set
    """
    from engine.editor.hd2d_entity_overrides_model import (  # noqa: PLC0415
        count_overrides,
        has_any_override,
        parse_hd2d_entity_overrides_dict,
    )

    editor = getattr(window, "editor_controller", None)
    if editor is None or not getattr(editor, "active", False):
        return {
            "visible": False,
            "entity_id": None,
            "overrides": {},
            "has_overrides": False,
            "override_count": 0,
        }

    # Get selected entity
    primary_id = getattr(editor, "_primary_selected_id", None)
    if not primary_id:
        return {
            "visible": False,
            "entity_id": None,
            "overrides": {},
            "has_overrides": False,
            "override_count": 0,
        }

    # Get scene payload and find entity
    scene_controller = getattr(window, "scene_controller", None)
    scene_payload = getattr(scene_controller, "_loaded_scene_data", {}) if scene_controller else {}
    if not isinstance(scene_payload, dict):
        scene_payload = {}

    entities = scene_payload.get("entities", [])
    if not isinstance(entities, list):
        entities = []

    entity_dict: dict[str, Any] = {}
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        eid = ent.get("id") or ent.get("mesh_name") or ent.get("name")
        if str(eid or "").strip() == str(primary_id or "").strip():
            entity_dict = ent
            break

    # Parse overrides
    overrides = parse_hd2d_entity_overrides_dict(entity_dict)

    return {
        "visible": True,
        "entity_id": str(primary_id),
        "overrides": overrides,
        "has_overrides": has_any_override(entity_dict),
        "override_count": count_overrides(entity_dict),
    }


def project_explorer_provider(window: Any, viewport_h: int, row_h: float, overscan: int = 5) -> dict[str, Any]:
    """Provider for the project explorer."""
    editor = getattr(window, "editor_controller", None)
    if not editor:
        return {}

    providers = getattr(editor, "providers", None)
    if providers and hasattr(providers, "get_project_explorer_payload"):
        return cast(Dict[str, Any], providers.get_project_explorer_payload(viewport_h, row_h, overscan))

    explorer = getattr(editor, "project_explorer", None)
    if not explorer:
        return {}
    
    # We call get_provider_payload
    # Note: If the method doesn't exist on the stub during partial refactor, this might fail, 
    # but we added it to the class in Step 1.
    if hasattr(explorer, "get_provider_payload"):
        return cast(Dict[str, Any], explorer.get_provider_payload(viewport_h, row_h, overscan))
    return {}


def project_explorer_context_menu_provider(window: Any) -> dict[str, Any]:
    """Provider for Project Explorer context menu."""
    editor = getattr(window, "editor_controller", None)
    if not editor:
        return {}

    providers = getattr(editor, "providers", None)
    if providers and hasattr(providers, "get_project_explorer_context_menu_payload"):
        return cast(Dict[str, Any], providers.get_project_explorer_context_menu_payload())

    explorer = getattr(editor, "project_explorer", None)
    if not explorer or not hasattr(explorer, "get_context_menu_payload"):
        return {}
    return cast(Dict[str, Any], explorer.get_context_menu_payload())

def physics_broadphase_provider(window: Any) -> dict[str, Any]:
    from engine import physics_runtime

    stats = physics_runtime.get_broadphase_stats()
    return {
        "enabled": bool(stats.get("enabled", False)),
        "build_count": int(stats.get("build_count", 0)),
        "candidate_count": int(stats.get("candidate_count", 0)),
        "exact_checks_count": int(stats.get("exact_checks_count", 0)),
    }


def problems_panel_provider(window: Any, viewport_h: int, row_h: float, overscan: int = 5) -> dict[str, Any]:
    """Provider for the problems panel."""
    editor = getattr(window, "editor_controller", None)
    if not editor:
        return {}

    providers = getattr(editor, "providers", None)
    if providers and hasattr(providers, "get_problems_panel_payload"):
        return cast(Dict[str, Any], providers.get_problems_panel_payload(viewport_h, row_h, overscan))

    problems = getattr(editor, "problems", None)
    if not problems:
        return {}

    if hasattr(problems, "get_provider_payload"):
        return cast(Dict[str, Any], problems.get_provider_payload(viewport_height=viewport_h, row_height=row_h, overscan=overscan))
    return {}

