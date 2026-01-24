from __future__ import annotations

import copy
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict
import engine.optional_arcade as optional_arcade

from .index_build import build_scene_index_from_sprites
from ..background_layers import parse_background_layers

if TYPE_CHECKING:
    from ..scene_controller import SceneController


def get_authored_scene_payload(controller: "SceneController") -> Dict[str, Any]:
    """Return a copy of the scene payload before runtime-only mutations (e.g., themed spawn resolution)."""
    return controller._loaded_scene_source_data


def debug_apply_authored_scene_payload(controller: "SceneController", authored_payload: Dict[str, Any]) -> bool:
    """
    Debug-only: replace the current authored scene payload in-memory (no disk I/O),
    rebuild runtime scene data, and refresh tile/entity visuals deterministically.
    """
    if not isinstance(authored_payload, dict):
        return False

    scene_path = str(controller.current_scene_path or "").strip()
    if not scene_path:
        return False

    controller._loaded_scene_source_data = copy.deepcopy(authored_payload)
    runtime_scene: Dict[str, Any] = copy.deepcopy(authored_payload)
    controller._background_layers = parse_background_layers(runtime_scene)
    controller._apply_theme_runtime(runtime_scene)
    controller._loaded_scene_data = runtime_scene
    controller.scene_settings = runtime_scene.get("settings", {}) if isinstance(runtime_scene.get("settings"), dict) else {}

    controller._scene_index = None

    window = getattr(controller, "window", None)
    if window is None or getattr(window, "assets", None) is None or getattr(window, "scene_loader", None) is None:
        return True

    controller._clear_scene_event_subscriptions()
    controller._ensure_layers(runtime_scene.get("layers", []))

    for sprite_list in controller.layers.values():
        sprite_list.clear()
    try:
        controller.solid_sprites.clear()
    except RuntimeError:
        controller.solid_sprites = optional_arcade.arcade.SpriteList()

    try:
        controller.refresh_tilemap_layers()
    except Exception:  # noqa: BLE001
        pass

    prev_suppress = bool(getattr(controller, "_suppress_spawn_toasts", False))
    controller._suppress_spawn_toasts = True
    try:
        from ..scene_entity_gating import filter_entities_by_flags  # noqa: PLC0415

        getter = getattr(window, "get_flag", None)
        entities_payload = filter_entities_by_flags(
            runtime_scene.get("entities", []),
            get_flag=getter if callable(getter) else None,
        )
        for entity in entities_payload:
            if not isinstance(entity, dict):
                continue
            sprite = controller._create_sprite(entity)
            if not sprite:
                continue
            layer_name = entity.get("layer", "entities")
            if layer_name not in controller.layers:
                controller.layers[layer_name] = optional_arcade.arcade.SpriteList()
            layer = controller.layers[layer_name]
            layer.append(sprite)
            is_solid = bool(entity.get("solid", False))
            sprite.mesh_is_solid = is_solid
            if is_solid:
                controller.solid_sprites.append(sprite)
    finally:
        controller._suppress_spawn_toasts = prev_suppress

    controller._scene_index = build_scene_index_from_sprites(controller.all_sprites)
    return True


def debug_find_sprite_by_entity_id(controller: "SceneController", entity_id: str) -> optional_arcade.arcade.Sprite | None:
    idx = controller._ensure_scene_index()
    sprite = idx.get_by_id(entity_id)
    return sprite if isinstance(sprite, optional_arcade.arcade.Sprite) else None


def _debug_iter_authoring_payloads(controller: "SceneController") -> list[Dict[str, Any]]:
    out: list[Dict[str, Any]] = []
    if isinstance(controller._loaded_scene_data, dict):
        out.append(controller._loaded_scene_data)
    if isinstance(controller._loaded_scene_source_data, dict):
        out.append(controller._loaded_scene_source_data)
    return out


def _debug_remove_sprite(controller: "SceneController", sprite: optional_arcade.arcade.Sprite) -> None:
    for layer in controller.layers.values():
        try:
            if sprite in layer:
                layer.remove(sprite)
        except Exception:  # noqa: BLE001
            continue
    try:
        if sprite in controller.solid_sprites:
            controller.solid_sprites.remove(sprite)
    except Exception:  # noqa: BLE001
        pass


def debug_add_entity_payload(controller: "SceneController", entity_payload: Dict[str, Any]) -> bool:
    """
    Debug-only: add a new entity payload (by id) to the authored + runtime payloads and spawn a sprite.
    """
    from ..entity_paint_mode import ensure_entities_list, find_entity_by_id  # noqa: PLC0415

    if not isinstance(entity_payload, dict):
        return False
    entity_id = str(entity_payload.get("id") or "").strip()
    if not entity_id:
        return False

    prefab_id = entity_payload.get("prefab_id")
    if not isinstance(prefab_id, str) or not prefab_id.strip():
        return False

    changed_any = False
    for payload in _debug_iter_authoring_payloads(controller):
        entities = ensure_entities_list(payload)
        if find_entity_by_id(entities, entity_id) is not None:
            continue
        entities.append(dict(entity_payload))
        changed_any = True

    if not changed_any:
        return False

    sprite = controller._create_sprite(dict(entity_payload))
    if sprite is None:
        return True

    layer_name = str(entity_payload.get("layer") or "entities")
    if layer_name not in controller.layers:
        controller.layers[layer_name] = optional_arcade.arcade.SpriteList()
    controller.layers[layer_name].append(sprite)
    controller._scene_index = build_scene_index_from_sprites(controller.all_sprites)
    return True


def debug_remove_entity_by_id(controller: "SceneController", entity_id: str) -> bool:
    """Debug-only: remove an entity by id from payload(s) and from live sprites."""
    from ..entity_paint_mode import apply_remove_entity  # noqa: PLC0415

    removed_any = False
    for payload in _debug_iter_authoring_payloads(controller):
        if apply_remove_entity(payload, entity_id=entity_id):
            removed_any = True

    sprite = debug_find_sprite_by_entity_id(controller, entity_id)
    if sprite is not None:
        _debug_remove_sprite(controller, sprite)
        removed_any = True

    if removed_any:
        controller._scene_index = build_scene_index_from_sprites(controller.all_sprites)
    return removed_any


def debug_move_entity_by_id(controller: "SceneController", entity_id: str, *, x: float, y: float) -> bool:
    """Debug-only: move an entity by id in payload(s) and update the live sprite if present."""
    from ..entity_paint_mode import apply_move_entity  # noqa: PLC0415

    moved_any = False
    for payload in _debug_iter_authoring_payloads(controller):
        if apply_move_entity(payload, entity_id=entity_id, x=x, y=y):
            moved_any = True

    sprite = debug_find_sprite_by_entity_id(controller, entity_id)
    if sprite is not None:
        sprite.center_x = float(x)
        sprite.center_y = float(y)
        data = getattr(sprite, "mesh_entity_data", None)
        if isinstance(data, dict):
            data["x"] = float(x)
            data["y"] = float(y)
        moved_any = True

    if moved_any:
        controller._scene_index = build_scene_index_from_sprites(controller.all_sprites)
    return moved_any


def debug_duplicate_entities_by_ids(controller: "SceneController", ids: list[str], *, dx: float, dy: float) -> dict[str, str]:
    """
    Debug-only: duplicate selected authored entities deterministically.

    - Operates on the authored payload copy so persist does not bake runtime-only mutations.
    - Attempts to spawn sprites for the duplicates best-effort (no hard failure if sprite creation fails).
    - Returns mapping of orig_id -> new_id for the successfully duplicated entities.
    """
    from ..entity_paint_mode import ensure_entities_list  # noqa: PLC0415

    if not isinstance(ids, list) or not ids:
        return {}

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return {}

    authored_entities = ensure_entities_list(authored)
    by_id: dict[str, Dict[str, Any]] = {}
    for entity in authored_entities:
        if not isinstance(entity, dict):
            continue
        entity_id = entity.get("id")
        if isinstance(entity_id, str) and entity_id.strip():
            by_id[entity_id.strip()] = entity

    used_ids: set[str] = set()
    for payload in _debug_iter_authoring_payloads(controller):
        for entity in ensure_entities_list(payload):
            if not isinstance(entity, dict):
                continue
            eid = entity.get("id")
            if isinstance(eid, str) and eid.strip():
                used_ids.add(eid.strip())

    mapping: dict[str, str] = {}
    created_any = False

    for orig_id in sorted({str(i).strip() for i in ids if isinstance(i, str) and str(i).strip()}):
        orig = by_id.get(orig_id)
        if orig is None:
            continue

        k = 1
        while True:
            candidate = f"{orig_id}__dup{k}"
            if candidate not in used_ids:
                new_id = candidate
                break
            k += 1
        used_ids.add(new_id)

        clone: Dict[str, Any] = dict(orig)
        clone["id"] = new_id
        try:
            clone["x"] = float(clone.get("x", 0.0)) + float(dx)
        except Exception:  # noqa: BLE001
            clone["x"] = float(dx)
        try:
            clone["y"] = float(clone.get("y", 0.0)) + float(dy)
        except Exception:  # noqa: BLE001
            clone["y"] = float(dy)

        authored_entities.append(clone)
        mapping[orig_id] = new_id
        created_any = True

        sprite = None
        try:
            sprite = controller._create_sprite(dict(clone))
        except Exception:  # noqa: BLE001
            sprite = None
        if sprite is not None:
            layer_name = str(clone.get("layer") or "entities")
            if layer_name not in controller.layers:
                controller.layers[layer_name] = optional_arcade.arcade.SpriteList()
            controller.layers[layer_name].append(sprite)

    if created_any:
        controller._scene_index = build_scene_index_from_sprites(controller.all_sprites)
    return mapping


def debug_copy_entities_by_ids(
    controller: "SceneController",
    ids: list[str],
    *,
    primary_id: str | None = None,
) -> Dict[str, Any] | None:
    """
    Debug-only: copy selected authored entities into a clipboard payload (no mutation).

    - Operates on the authored scene payload.
    - Skips player entities silently.
    - Deterministic: entities sorted by orig_id.
    """
    from ..entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

    if not isinstance(ids, list) or not ids:
        return None

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return None

    entities = ensure_entities_list(authored)
    by_id: dict[str, Dict[str, Any]] = {}
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        entity_id = entity.get("id")
        if isinstance(entity_id, str) and entity_id.strip():
            by_id[entity_id.strip()] = entity

    selected_ids = sorted({str(i).strip() for i in ids if isinstance(i, str) and str(i).strip()})
    if not selected_ids:
        return None

    chosen_primary = str(primary_id or "").strip()
    if chosen_primary not in selected_ids:
        chosen_primary = selected_ids[0]

    primary_entity = by_id.get(chosen_primary)
    if isinstance(primary_entity, dict) and is_player_entity(primary_entity):
        primary_entity = None

    if primary_entity is None:
        for candidate in selected_ids:
            ent = by_id.get(candidate)
            if isinstance(ent, dict) and not is_player_entity(ent):
                chosen_primary = candidate
                primary_entity = ent
                break

    if primary_entity is None:
        return None

    try:
        primary_x = float(primary_entity.get("x", 0.0))
    except Exception:  # noqa: BLE001
        primary_x = 0.0
    try:
        primary_y = float(primary_entity.get("y", 0.0))
    except Exception:  # noqa: BLE001
        primary_y = 0.0

    copied_entities: list[Dict[str, Any]] = []
    rel_offsets: Dict[str, Dict[str, float]] = {}

    for entity_id in selected_ids:
        ent = by_id.get(entity_id)
        if not isinstance(ent, dict):
            continue
        if is_player_entity(ent):
            continue
        clone = copy.deepcopy(ent)
        orig_id = str(clone.pop("id", "") or entity_id).strip()
        if not orig_id:
            continue
        clone["orig_id"] = orig_id
        copied_entities.append(clone)
        try:
            ex = float(ent.get("x", 0.0))
        except Exception:  # noqa: BLE001
            ex = 0.0
        try:
            ey = float(ent.get("y", 0.0))
        except Exception:  # noqa: BLE001
            ey = 0.0
        rel_offsets[orig_id] = {"dx": float(ex) - float(primary_x), "dy": float(ey) - float(primary_y)}

    copied_entities.sort(key=lambda e: str(e.get("orig_id") or ""))
    if not copied_entities:
        return None

    return {
        "scene_path": str(controller.current_scene_path or ""),
        "primary_id": str(chosen_primary),
        "entities": copied_entities,
        "rel_offsets": rel_offsets,
    }


def debug_paste_entities_from_clipboard(
    controller: "SceneController",
    clipboard: Dict[str, Any],
    *,
    anchor_x: float,
    anchor_y: float,
    snap_to_tile: bool = False,
) -> tuple[list[str], str]:
    """
    Debug-only: paste entities from a clipboard payload into the authored scene payload.

    - Deterministic id scheme: <orig_id>__paste<k>, with k starting at 0.
    - Deterministic ordering: paste in sorted orig_id order.
    - Returns (pasted_ids_sorted, pasted_primary_id).
    """
    from ..entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return ([], "")

    entities_payload = clipboard.get("entities")
    rel_offsets = clipboard.get("rel_offsets")
    primary_orig = clipboard.get("primary_id")
    if not isinstance(entities_payload, list) or not isinstance(rel_offsets, dict) or not isinstance(primary_orig, str):
        return ([], "")

    ax = float(anchor_x)
    ay = float(anchor_y)
    if bool(snap_to_tile):
        try:
            from engine.entity_select_mode import snap_world_to_tile_center  # noqa: PLC0415

            snapped = snap_world_to_tile_center(controller.window, world_x=float(ax), world_y=float(ay))
        except Exception:  # noqa: BLE001
            snapped = None
        if snapped is not None:
            ax, ay = float(snapped[0]), float(snapped[1])

    authored_entities = ensure_entities_list(authored)
    used_ids: set[str] = set()
    for entry in authored_entities:
        if not isinstance(entry, dict):
            continue
        eid = entry.get("id")
        if isinstance(eid, str) and eid.strip():
            used_ids.add(eid.strip())

    def _iter_entries_sorted() -> list[Dict[str, Any]]:
        out: list[Dict[str, Any]] = []
        for entry in entities_payload:
            if isinstance(entry, dict):
                out.append(entry)
        out.sort(key=lambda e: str(e.get("orig_id") or ""))
        return out

    pasted: dict[str, str] = {}
    created_any = False

    prev_suppress = bool(getattr(controller, "_suppress_spawn_toasts", False))
    controller._suppress_spawn_toasts = True
    try:
        for entry in _iter_entries_sorted():
            orig_id = entry.get("orig_id")
            if not isinstance(orig_id, str) or not orig_id.strip():
                continue
            orig_id = orig_id.strip()

            offset = rel_offsets.get(orig_id)
            if not isinstance(offset, dict):
                continue
            dx = offset.get("dx")
            dy = offset.get("dy")
            if not isinstance(dx, (int, float)) or not isinstance(dy, (int, float)):
                continue

            k = 0
            while True:
                candidate = f"{orig_id}__paste{k}"
                if candidate not in used_ids:
                    new_id = candidate
                    break
                k += 1
            used_ids.add(new_id)

            clone: Dict[str, Any] = copy.deepcopy(entry)
            clone.pop("orig_id", None)
            clone["id"] = new_id
            clone["x"] = float(ax) + float(dx)
            clone["y"] = float(ay) + float(dy)
            if is_player_entity(clone):
                continue

            authored_entities.append(clone)
            pasted[orig_id] = new_id
            created_any = True

            sprite = None
            try:
                sprite = controller._create_sprite(dict(clone))
            except Exception:  # noqa: BLE001
                sprite = None
            if sprite is not None:
                layer_name = str(clone.get("layer") or "entities")
                if layer_name not in controller.layers:
                    controller.layers[layer_name] = optional_arcade.arcade.SpriteList()
                controller.layers[layer_name].append(sprite)
    finally:
        controller._suppress_spawn_toasts = prev_suppress

    if created_any:
        controller._scene_index = build_scene_index_from_sprites(controller.all_sprites)

    pasted_ids = sorted({str(v).strip() for v in pasted.values() if isinstance(v, str) and str(v).strip()})
    pasted_primary = pasted.get(str(primary_orig).strip(), "")
    if not isinstance(pasted_primary, str) or not pasted_primary.strip():
        pasted_primary = pasted_ids[0] if pasted_ids else ""
    return pasted_ids, pasted_primary


def debug_transform_entities_by_ids(
    controller: "SceneController",
    ids: list[str],
    *,
    op: str,
    snap_to_tile: bool = False,
) -> int:
    """
    Debug-only: transform authored entities around the selection centroid.

    Supported ops:
    - "rotate_cw_90"
    - "flip_x"
    - "flip_y"

    Returns the number of entities transformed.
    """
    from ..entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

    if not isinstance(ids, list) or not ids:
        return 0

    op_text = str(op or "").strip().lower()
    if op_text not in ("rotate_cw_90", "flip_x", "flip_y"):
        return 0

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return 0

    authored_entities = ensure_entities_list(authored)
    by_id: dict[str, Dict[str, Any]] = {}
    for entity in authored_entities:
        if not isinstance(entity, dict):
            continue
        entity_id = entity.get("id")
        if isinstance(entity_id, str) and entity_id.strip():
            by_id[entity_id.strip()] = entity

    selected_ids = sorted({str(i).strip() for i in ids if isinstance(i, str) and str(i).strip()})
    points: dict[str, tuple[float, float]] = {}
    for entity_id in selected_ids:
        ent = by_id.get(entity_id)
        if not isinstance(ent, dict) or is_player_entity(ent):
            continue
        try:
            x = float(ent.get("x", 0.0))
        except Exception:  # noqa: BLE001
            x = 0.0
        try:
            y = float(ent.get("y", 0.0))
        except Exception:  # noqa: BLE001
            y = 0.0
        points[entity_id] = (float(x), float(y))

    if not points:
        return 0

    cx = sum(x for x, _y in points.values()) / float(len(points))
    cy = sum(y for _x, y in points.values()) / float(len(points))

    new_positions: dict[str, tuple[float, float]] = {}
    for entity_id, (x, y) in points.items():
        dx = float(x) - float(cx)
        dy = float(y) - float(cy)
        if op_text == "rotate_cw_90":
            ndx, ndy = float(dy), -float(dx)
            nx, ny = float(cx) + ndx, float(cy) + ndy
        elif op_text == "flip_x":
            nx, ny = float(cx) - dx, float(y)
        else:  # flip_y
            nx, ny = float(x), float(cy) - dy
        new_positions[entity_id] = (float(nx), float(ny))

    if bool(snap_to_tile):
        try:
            from engine.entity_select_mode import snap_world_to_tile_center  # noqa: PLC0415
        except Exception:  # noqa: BLE001
            snap_world_to_tile_center = None  # type: ignore[assignment]
        if snap_world_to_tile_center is not None:
            for entity_id, (nx, ny) in list(new_positions.items()):
                snapped = snap_world_to_tile_center(controller.window, world_x=float(nx), world_y=float(ny))
                if snapped is not None:
                    new_positions[entity_id] = (float(snapped[0]), float(snapped[1]))

    moved_any = False
    for entity_id in selected_ids:
        pos = new_positions.get(entity_id)
        if pos is None:
            continue
        x, y = pos
        for payload in _debug_iter_authoring_payloads(controller):
            try:
                from ..entity_paint_mode import apply_move_entity  # noqa: PLC0415

                moved_any = apply_move_entity(payload, entity_id=entity_id, x=float(x), y=float(y)) or moved_any
            except Exception:  # noqa: BLE001
                continue
        sprite = debug_find_sprite_by_entity_id(controller, entity_id)
        if sprite is not None:
            try:
                sprite.center_x = float(x)
                sprite.center_y = float(y)
                data = getattr(sprite, "mesh_entity_data", None)
                if isinstance(data, dict):
                    data["x"] = float(x)
                    data["y"] = float(y)
                moved_any = True
            except Exception:  # noqa: BLE001
                pass

    if moved_any:
        controller._scene_index = build_scene_index_from_sprites(controller.all_sprites)
    return len(new_positions) if moved_any else 0


def debug_set_prefab_id(controller: "SceneController", selected_ids: list[str], prefab_id: str) -> tuple[int, int]:
    """
    Debug-only: set prefab_id for all selected authored entities (skips player).

    Operates on the authored payload only and reapplies it (no disk I/O).
    Returns (changed_count, skipped_player_count).
    """
    from ..entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415

    wanted = str(prefab_id or "").strip()
    if not isinstance(selected_ids, list) or not selected_ids or not wanted:
        return (0, 0)

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return (0, 0)
    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)

    changed = 0
    skipped_player = 0
    for entity_id in sorted({str(i).strip() for i in selected_ids if isinstance(i, str) and str(i).strip()}):
        ent = find_entity_by_id(entities, entity_id)
        if not isinstance(ent, dict):
            continue
        if is_player_entity(ent):
            skipped_player += 1
            continue
        before = ent.get("prefab_id")
        if before != wanted:
            ent["prefab_id"] = wanted
            changed += 1

    if changed > 0:
        debug_apply_authored_scene_payload(controller, authored_copy)
    return (changed, skipped_player)


def debug_add_behaviour(controller: "SceneController", selected_ids: list[str], behaviour_name: str) -> tuple[int, int]:
    """
    Debug-only: add behaviour to all selected authored entities (idempotent, skips player).

    Operates on the authored payload only and reapplies it (no disk I/O).
    Returns (changed_count, skipped_player_count).
    """
    from ..entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415

    wanted = str(behaviour_name or "").strip()
    if not isinstance(selected_ids, list) or not selected_ids or not wanted:
        return (0, 0)

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return (0, 0)
    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)

    changed = 0
    skipped_player = 0
    for entity_id in sorted({str(i).strip() for i in selected_ids if isinstance(i, str) and str(i).strip()}):
        ent = find_entity_by_id(entities, entity_id)
        if not isinstance(ent, dict):
            continue
        if is_player_entity(ent):
            skipped_player += 1
            continue
        behaviours = ent.get("behaviours")
        if not isinstance(behaviours, list):
            behaviours = []
            ent["behaviours"] = behaviours
        existing: set[str] = set()
        for b in behaviours:
            if isinstance(b, str) and b.strip():
                existing.add(b.strip())
            elif isinstance(b, dict):
                bt = b.get("type")
                if isinstance(bt, str) and bt.strip():
                    existing.add(bt.strip())
        if wanted not in existing:
            behaviours.append(wanted)
            changed += 1

    if changed > 0:
        debug_apply_authored_scene_payload(controller, authored_copy)
    return (changed, skipped_player)


def debug_remove_behaviour(controller: "SceneController", selected_ids: list[str], behaviour_name: str) -> tuple[int, int]:
    """
    Debug-only: remove behaviour from all selected authored entities (idempotent, skips player).

    Operates on the authored payload only and reapplies it (no disk I/O).
    Returns (changed_count, skipped_player_count).
    """
    from ..entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415

    wanted = str(behaviour_name or "").strip()
    if not isinstance(selected_ids, list) or not selected_ids or not wanted:
        return (0, 0)

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return (0, 0)
    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)

    changed = 0
    skipped_player = 0
    for entity_id in sorted({str(i).strip() for i in selected_ids if isinstance(i, str) and str(i).strip()}):
        ent = find_entity_by_id(entities, entity_id)
        if not isinstance(ent, dict):
            continue
        if is_player_entity(ent):
            skipped_player += 1
            continue
        behaviours = ent.get("behaviours")
        if not isinstance(behaviours, list) or not behaviours:
            continue

        new_behaviours: list[Any] = []
        removed_any = False
        for b in behaviours:
            if isinstance(b, str):
                if b.strip() == wanted:
                    removed_any = True
                    continue
            elif isinstance(b, dict):
                bt = b.get("type")
                if isinstance(bt, str) and bt.strip() == wanted:
                    removed_any = True
                    continue
            new_behaviours.append(b)
        if removed_any:
            ent["behaviours"] = new_behaviours
            changed += 1

    if changed > 0:
        debug_apply_authored_scene_payload(controller, authored_copy)
    return (changed, skipped_player)


def debug_set_name(controller: "SceneController", primary_id: str, name: str) -> tuple[int, int]:
    """
    Debug-only: set name on the primary authored entity (skips player).

    Operates on the authored payload only and reapplies it (no disk I/O).
    Returns (changed_count, skipped_player_count).
    """
    from ..entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415

    entity_id = str(primary_id or "").strip()
    wanted = str(name or "").strip()
    if not entity_id or not wanted:
        return (0, 0)

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return (0, 0)
    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)
    ent = find_entity_by_id(entities, entity_id)
    if not isinstance(ent, dict):
        return (0, 0)
    if is_player_entity(ent):
        return (0, 1)

    before = ent.get("name")
    if before == wanted:
        return (0, 0)
    ent["name"] = wanted
    debug_apply_authored_scene_payload(controller, authored_copy)
    return (1, 0)


def debug_add_tag(controller: "SceneController", selected_ids: list[str], tag: str) -> tuple[int, int]:
    """
    Debug-only: add a tag to all selected authored entities (idempotent, skips player).

    Operates on the authored payload only and reapplies it (no disk I/O).
    Returns (changed_count, skipped_player_count).
    """
    from ..entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415

    wanted = str(tag or "").strip()
    if not isinstance(selected_ids, list) or not selected_ids or not wanted:
        return (0, 0)

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return (0, 0)
    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)

    changed = 0
    skipped_player = 0
    for entity_id in sorted({str(i).strip() for i in selected_ids if isinstance(i, str) and str(i).strip()}):
        ent = find_entity_by_id(entities, entity_id)
        if not isinstance(ent, dict):
            continue
        if is_player_entity(ent):
            skipped_player += 1
            continue
        tags = ent.get("tags")
        if not isinstance(tags, list):
            tags = []
            ent["tags"] = tags
        existing = {str(t).strip() for t in tags if isinstance(t, str) and str(t).strip()}
        if wanted not in existing:
            tags.append(wanted)
            changed += 1

    if changed > 0:
        debug_apply_authored_scene_payload(controller, authored_copy)
    return (changed, skipped_player)


def debug_config_triggerzone_set_zone_id(controller: "SceneController", selected_ids: list[str], zone_id: str) -> tuple[int, int, int]:
    """
    Debug-only: set behaviour_config.TriggerZone.zone_id for selected entities that have TriggerZone.

    Returns (changed_count, skipped_player_count, skipped_missing_behaviour_count).
    """
    return _debug_config_set_field_for_behaviour(
        controller,
        selected_ids,
        behaviour_name="TriggerZone",
        field_path=("zone_id",),
        value=str(zone_id or "").strip(),
    )


def debug_config_triggerzone_set_radius(
    controller: "SceneController",
    selected_ids: list[str],
    trigger_radius: float,
) -> tuple[int, int, int]:
    """
    Debug-only: set behaviour_config.TriggerZone.trigger_radius for selected entities that have TriggerZone.

    Returns (changed_count, skipped_player_count, skipped_missing_behaviour_count).
    """
    return _debug_config_set_field_for_behaviour(
        controller,
        selected_ids,
        behaviour_name="TriggerZone",
        field_path=("trigger_radius",),
        value=float(trigger_radius),
    )


def debug_config_set_game_state_set_toast(
    controller: "SceneController",
    selected_ids: list[str],
    *,
    toast: str,
    toast_seconds: float | None,
) -> tuple[int, int, int]:
    """
    Debug-only: set toast (+ optional toast_seconds) for selected entities with SetGameStateOnEvent.

    - If toast_seconds is None: keep existing toast_seconds if present, else use 3.0.
    Returns (changed_count, skipped_player_count, skipped_missing_behaviour_count).
    """
    wanted_toast = str(toast or "").strip()
    if not wanted_toast:
        return (0, 0, 0)

    def _mutate(cfg: dict[str, Any]) -> bool:
        changed_any = False
        before_toast = cfg.get("toast")
        if before_toast != wanted_toast:
            cfg["toast"] = wanted_toast
            changed_any = True
        if toast_seconds is None:
            existing = cfg.get("toast_seconds")
            if not isinstance(existing, (int, float)) or float(existing) <= 0.0:
                cfg["toast_seconds"] = 3.0
                changed_any = True
        else:
            before_s = cfg.get("toast_seconds")
            if not isinstance(before_s, (int, float)) or float(before_s) != float(toast_seconds):
                cfg["toast_seconds"] = float(toast_seconds)
                changed_any = True
        return changed_any

    return _debug_config_mutate_for_behaviour(controller, selected_ids, behaviour_name="SetGameStateOnEvent", mutate=_mutate)


def debug_config_set_game_state_add_require_flag(controller: "SceneController", selected_ids: list[str], flag: str) -> tuple[int, int, int]:
    """
    Debug-only: append a require_flags entry for SetGameStateOnEvent, idempotently.

    Returns (changed_count, skipped_player_count, skipped_missing_behaviour_count).
    """
    wanted = str(flag or "").strip()
    if not wanted:
        return (0, 0, 0)

    def _mutate(cfg: dict[str, Any]) -> bool:
        req = cfg.get("require_flags")
        if not isinstance(req, list):
            req = []
            cfg["require_flags"] = req
        existing = {str(v).strip() for v in req if isinstance(v, str) and str(v).strip()}
        if wanted in existing:
            return False
        req.append(wanted)
        return True

    return _debug_config_mutate_for_behaviour(controller, selected_ids, behaviour_name="SetGameStateOnEvent", mutate=_mutate)


def debug_config_set_game_state_add_forbid_flag(controller: "SceneController", selected_ids: list[str], flag: str) -> tuple[int, int, int]:
    """
    Debug-only: append a forbid_flags entry for SetGameStateOnEvent, idempotently.

    Returns (changed_count, skipped_player_count, skipped_missing_behaviour_count).
    """
    wanted = str(flag or "").strip()
    if not wanted:
        return (0, 0, 0)

    def _mutate(cfg: dict[str, Any]) -> bool:
        forbid = cfg.get("forbid_flags")
        if not isinstance(forbid, list):
            forbid = []
            cfg["forbid_flags"] = forbid
        existing = {str(v).strip() for v in forbid if isinstance(v, str) and str(v).strip()}
        if wanted in existing:
            return False
        forbid.append(wanted)
        return True

    return _debug_config_mutate_for_behaviour(controller, selected_ids, behaviour_name="SetGameStateOnEvent", mutate=_mutate)


def debug_config_set_game_state_set_flag_true(controller: "SceneController", selected_ids: list[str], flag_key: str) -> tuple[int, int, int]:
    """
    Debug-only: set set_flags[flag_key] = True for SetGameStateOnEvent, without removing other keys.

    Returns (changed_count, skipped_player_count, skipped_missing_behaviour_count).
    """
    key = str(flag_key or "").strip()
    if not key:
        return (0, 0, 0)

    def _mutate(cfg: dict[str, Any]) -> bool:
        flags = cfg.get("set_flags")
        if not isinstance(flags, dict):
            flags = {}
            cfg["set_flags"] = flags
        before = flags.get(key)
        if before is True:
            return False
        flags[key] = True
        return True

    return _debug_config_mutate_for_behaviour(controller, selected_ids, behaviour_name="SetGameStateOnEvent", mutate=_mutate)


def debug_config_scene_transition_set_target_scene(controller: "SceneController", selected_ids: list[str], target_scene: str) -> tuple[int, int, int]:
    """
    Debug-only: set behaviour_config.SceneTransition.target_scene for selected entities that have SceneTransition.

    Returns (changed_count, skipped_player_count, skipped_missing_behaviour_count).
    """
    wanted = str(target_scene or "").strip()
    if not wanted:
        return (0, 0, 0)
    return _debug_config_set_field_for_behaviour(
        controller,
        selected_ids,
        behaviour_name="SceneTransition",
        field_path=("target_scene",),
        value=wanted,
    )


def debug_config_scene_transition_set_spawn_id(controller: "SceneController", selected_ids: list[str], spawn_id: str) -> tuple[int, int, int]:
    """
    Debug-only: set behaviour_config.SceneTransition.spawn_id (and spawn_point alias) for selected entities.

    Returns (changed_count, skipped_player_count, skipped_missing_behaviour_count).
    """
    wanted = str(spawn_id or "").strip()
    if not wanted:
        return (0, 0, 0)

    def _mutate(cfg: dict[str, Any]) -> bool:
        changed_any = False
        if cfg.get("spawn_id") != wanted:
            cfg["spawn_id"] = wanted
            changed_any = True
        if cfg.get("spawn_point") != wanted:
            cfg["spawn_point"] = wanted
            changed_any = True
        return changed_any

    return _debug_config_mutate_for_behaviour(controller, selected_ids, behaviour_name="SceneTransition", mutate=_mutate)


def _debug_config_entity_has_behaviour(controller: "SceneController", entity_payload: dict[str, Any], behaviour_name: str) -> bool:
    behaviours = entity_payload.get("behaviours")
    if not isinstance(behaviours, list):
        return False
    wanted = str(behaviour_name or "").strip()
    if not wanted:
        return False
    for b in behaviours:
        if isinstance(b, str) and b.strip() == wanted:
            return True
        if isinstance(b, dict):
            bt = b.get("type")
            if isinstance(bt, str) and bt.strip() == wanted:
                return True
    return False


def _debug_config_mutate_for_behaviour(
    controller: "SceneController",
    selected_ids: list[str],
    *,
    behaviour_name: str,
    mutate: "Callable[[dict[str, Any]], bool]",
) -> tuple[int, int, int]:
    from ..entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415

    if not isinstance(selected_ids, list) or not selected_ids:
        return (0, 0, 0)
    wanted_behaviour = str(behaviour_name or "").strip()
    if not wanted_behaviour:
        return (0, 0, 0)

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return (0, 0, 0)

    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)

    changed = 0
    skipped_player = 0
    skipped_no_behaviour = 0

    for entity_id in sorted({str(i).strip() for i in selected_ids if isinstance(i, str) and str(i).strip()}):
        ent = find_entity_by_id(entities, entity_id)
        if not isinstance(ent, dict):
            continue
        if is_player_entity(ent):
            skipped_player += 1
            continue
        if not _debug_config_entity_has_behaviour(controller, ent, wanted_behaviour):
            skipped_no_behaviour += 1
            continue
        root = ent.get("behaviour_config")
        if not isinstance(root, dict):
            root = {}
            ent["behaviour_config"] = root
        cfg = root.get(wanted_behaviour)
        if not isinstance(cfg, dict):
            cfg = {}
            root[wanted_behaviour] = cfg
        try:
            did = bool(mutate(cfg))
        except Exception:  # noqa: BLE001
            did = False
        if did:
            changed += 1

    if changed > 0:
        debug_apply_authored_scene_payload(controller, authored_copy)
    return (changed, skipped_player, skipped_no_behaviour)


def _debug_config_set_field_for_behaviour(
    controller: "SceneController",
    selected_ids: list[str],
    *,
    behaviour_name: str,
    field_path: tuple[str, ...],
    value: Any,
) -> tuple[int, int, int]:
    wanted_path = tuple(str(p).strip() for p in (field_path or ()) if str(p).strip())
    if not wanted_path:
        return (0, 0, 0)

    def _mutate(cfg: dict[str, Any]) -> bool:
        key = wanted_path[0]
        before = cfg.get(key)
        if before == value:
            return False
        cfg[key] = value
        return True

    return _debug_config_mutate_for_behaviour(controller, selected_ids, behaviour_name=behaviour_name, mutate=_mutate)


def debug_build_macro_objective_zone_payload(
    controller: "SceneController",
    *,
    center_x: float,
    center_y: float,
    zone_id: str,
    set_flag: str,
    radius: float,
    toast: str | None,
    require_flags: list[str] | None = None,
    forbid_flags: list[str] | None = None,
    toast_seconds: float | None = None,
) -> tuple[Dict[str, Any], int, int]:
    """
    Debug-only: build a new authored scene payload with a TriggerZone + SetGameStateOnEvent pair.

    Returns (new_payload, created_count, updated_count). Does not mutate scene state by itself.
    """
    from ..entity_paint_mode import ensure_entities_list, find_entity_by_id  # noqa: PLC0415
    from ..entity_paint_mode import _format_id_number as _fmt  # noqa: PLC0415
    from ..entity_paint_mode import _sanitize_entity_id_token as _san  # noqa: PLC0415

    authored = get_authored_scene_payload(controller)
    authored_copy = copy.deepcopy(authored) if isinstance(authored, dict) else {"entities": []}
    entities = ensure_entities_list(authored_copy)

    scene_path = str(controller.current_scene_path or "").strip()
    stem = _san(Path(scene_path).stem if scene_path else "scene")
    zid = str(zone_id or "").strip()
    flag = str(set_flag or "").strip()
    zid_tok = _san(zid)
    flag_tok = _san(flag)

    x = float(center_x)
    y = float(center_y)
    x_tok = _fmt(x)
    y_tok = _fmt(y)

    trigger_id = f"{stem}_macro_triggerzone_{zid_tok}_{x_tok}_{y_tok}_0_0"
    hook_id = f"{stem}_macro_setflag_{flag_tok}_{zid_tok}_{x_tok}_{y_tok}_0_0"

    created = 0
    updated = 0

    def _has_behaviour(ent: dict[str, Any], behaviour: str) -> bool:
        raw = ent.get("behaviours")
        if not isinstance(raw, list):
            return False
        for b in raw:
            if isinstance(b, str) and b.strip() == behaviour:
                return True
            if isinstance(b, dict):
                bt = b.get("type")
                if isinstance(bt, str) and bt.strip() == behaviour:
                    return True
        return False

    def _ensure_behaviour(ent: dict[str, Any], behaviour: str) -> bool:
        behaviours = ent.get("behaviours")
        if not isinstance(behaviours, list):
            behaviours = []
            ent["behaviours"] = behaviours
        if _has_behaviour(ent, behaviour):
            return False
        behaviours.append(behaviour)
        return True

    def _ensure_cfg(ent: dict[str, Any], behaviour: str) -> dict[str, Any]:
        root = ent.get("behaviour_config")
        if not isinstance(root, dict):
            root = {}
            ent["behaviour_config"] = root
        cfg = root.get(behaviour)
        if not isinstance(cfg, dict):
            cfg = {}
            root[behaviour] = cfg
        return cfg

    def _set_field(ent: dict[str, Any], key: str, value: Any) -> bool:
        if ent.get(key) == value:
            return False
        ent[key] = value
        return True

    def _apply_triggerzone(ent: dict[str, Any]) -> bool:
        changed_any = False
        changed_any = _ensure_behaviour(ent, "TriggerZone") or changed_any
        changed_any = _set_field(ent, "x", x) or changed_any
        changed_any = _set_field(ent, "y", y) or changed_any
        if zid:
            changed_any = _set_field(ent, "name", zid) or changed_any
        changed_any = _set_field(ent, "layer", ent.get("layer") or "background") or changed_any
        changed_any = _set_field(ent, "tag", ent.get("tag") or "trigger") or changed_any
        changed_any = _set_field(ent, "scale", float(ent.get("scale", 0.0) or 0.0)) or changed_any
        if require_flags is not None:
            req_gate = sorted({str(v).strip() for v in require_flags if str(v).strip()})
            changed_any = _set_field(ent, "require_flags", req_gate) or changed_any
        if forbid_flags is not None:
            forb_gate = sorted({str(v).strip() for v in forbid_flags if str(v).strip()})
            changed_any = _set_field(ent, "forbid_flags", forb_gate) or changed_any
        cfg = _ensure_cfg(ent, "TriggerZone")
        if cfg.get("zone_id") != zid:
            cfg["zone_id"] = zid
            changed_any = True
        if cfg.get("trigger_target") != "Player":
            cfg["trigger_target"] = "Player"
            changed_any = True
        if cfg.get("trigger_radius") != float(radius):
            cfg["trigger_radius"] = float(radius)
            changed_any = True
        return changed_any

    def _apply_set_flag(ent: dict[str, Any]) -> bool:
        changed_any = False
        changed_any = _ensure_behaviour(ent, "SetGameStateOnEvent") or changed_any
        changed_any = _set_field(ent, "x", x) or changed_any
        changed_any = _set_field(ent, "y", y) or changed_any
        changed_any = _set_field(ent, "layer", ent.get("layer") or "background") or changed_any
        changed_any = _set_field(ent, "tag", ent.get("tag") or "trigger") or changed_any
        changed_any = _set_field(ent, "scale", float(ent.get("scale", 0.0) or 0.0)) or changed_any
        if flag:
            changed_any = _set_field(ent, "name", ent.get("name") or f"SetFlag:{flag}") or changed_any
        if require_flags is not None:
            req_gate = sorted({str(v).strip() for v in require_flags if str(v).strip()})
            changed_any = _set_field(ent, "require_flags", req_gate) or changed_any
        if forbid_flags is not None:
            forb_gate = sorted({str(v).strip() for v in forbid_flags if str(v).strip()})
            changed_any = _set_field(ent, "forbid_flags", forb_gate) or changed_any
        cfg = _ensure_cfg(ent, "SetGameStateOnEvent")
        if cfg.get("event_type") != "entered_zone":
            cfg["event_type"] = "entered_zone"
            changed_any = True
        if cfg.get("payload_field") != "zone":
            cfg["payload_field"] = "zone"
            changed_any = True
        if cfg.get("payload_value") != zid:
            cfg["payload_value"] = zid
            changed_any = True
        if cfg.get("once") is not True:
            cfg["once"] = True
            changed_any = True
        if require_flags is not None:
            req = sorted({str(v).strip() for v in require_flags if str(v).strip()})
            if cfg.get("require_flags") != req:
                cfg["require_flags"] = req
                changed_any = True
        if forbid_flags is not None:
            forb = sorted({str(v).strip() for v in forbid_flags if str(v).strip()})
            if cfg.get("forbid_flags") != forb:
                cfg["forbid_flags"] = forb
                changed_any = True
        set_flags = cfg.get("set_flags")
        if not isinstance(set_flags, dict):
            set_flags = {}
            cfg["set_flags"] = set_flags
            changed_any = True
        if flag and set_flags.get(flag) is not True:
            set_flags[flag] = True
            changed_any = True
        toast_text = str(toast or "").strip()
        if toast_text:
            if cfg.get("toast") != toast_text:
                cfg["toast"] = toast_text
                changed_any = True
            if isinstance(toast_seconds, (int, float)) and float(toast_seconds) > 0.0:
                if cfg.get("toast_seconds") != float(toast_seconds):
                    cfg["toast_seconds"] = float(toast_seconds)
                    changed_any = True
            else:
                if not isinstance(cfg.get("toast_seconds"), (int, float)) or float(cfg.get("toast_seconds") or 0.0) <= 0.0:
                    cfg["toast_seconds"] = 3.0
                    changed_any = True
        else:
            if cfg.get("toast") not in (None, ""):
                cfg["toast"] = ""
                changed_any = True
        return changed_any

    trigger_ent = find_entity_by_id(entities, trigger_id)
    if trigger_ent is None:
        entities.append({"id": trigger_id})
        trigger_ent = entities[-1]
        created += 1
        if _apply_triggerzone(trigger_ent):
            updated += 0
    else:
        if isinstance(trigger_ent, dict):
            pid = trigger_ent.get("prefab_id")
            if (
                isinstance(pid, str)
                and pid.strip()
                and pid.strip() not in {"TriggerZone"}
                and not _has_behaviour(trigger_ent, "TriggerZone")
            ):
                raise ValueError(f"prefab_mismatch id={trigger_id} prefab_id={pid.strip()!r}")
        if _apply_triggerzone(trigger_ent):
            updated += 1

    hook_ent = find_entity_by_id(entities, hook_id)
    if hook_ent is None:
        entities.append({"id": hook_id})
        hook_ent = entities[-1]
        created += 1
        if _apply_set_flag(hook_ent):
            updated += 0
    else:
        if isinstance(hook_ent, dict):
            pid = hook_ent.get("prefab_id")
            if (
                isinstance(pid, str)
                and pid.strip()
                and pid.strip() not in {"SetGameStateOnEvent"}
                and not _has_behaviour(hook_ent, "SetGameStateOnEvent")
            ):
                raise ValueError(f"prefab_mismatch id={hook_id} prefab_id={pid.strip()!r}")
        if _apply_set_flag(hook_ent):
            updated += 1

    return authored_copy, created, updated


def debug_build_macro_door_transition_payload(
    controller: "SceneController",
    *,
    center_x: float,
    center_y: float,
    target_scene: str,
    spawn_id: str,
    primary_id: str | None,
    require_flags: list[str] | None = None,
    forbid_flags: list[str] | None = None,
) -> tuple[Dict[str, Any], int, int]:
    """
    Debug-only: build a new authored scene payload that ensures a SceneTransition exists or is updated.

    Returns (new_payload, created_count, updated_count). Does not mutate scene state by itself.
    """
    from ..entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415
    from ..entity_paint_mode import _format_id_number as _fmt  # noqa: PLC0415
    from ..entity_paint_mode import _sanitize_entity_id_token as _san  # noqa: PLC0415

    authored = get_authored_scene_payload(controller)
    authored_copy = copy.deepcopy(authored) if isinstance(authored, dict) else {"entities": []}
    entities = ensure_entities_list(authored_copy)

    tgt = str(target_scene or "").strip()
    sp = str(spawn_id or "").strip()

    created = 0
    updated = 0

    def _has_behaviour(ent: dict[str, Any], behaviour: str) -> bool:
        raw = ent.get("behaviours")
        if not isinstance(raw, list):
            return False
        for b in raw:
            if isinstance(b, str) and b.strip() == behaviour:
                return True
            if isinstance(b, dict):
                bt = b.get("type")
                if isinstance(bt, str) and bt.strip() == behaviour:
                    return True
        return False

    def _ensure_behaviour(ent: dict[str, Any], behaviour: str) -> bool:
        behaviours = ent.get("behaviours")
        if not isinstance(behaviours, list):
            behaviours = []
            ent["behaviours"] = behaviours
        if _has_behaviour(ent, behaviour):
            return False
        behaviours.append(behaviour)
        return True

    def _ensure_cfg(ent: dict[str, Any], behaviour: str) -> dict[str, Any]:
        root = ent.get("behaviour_config")
        if not isinstance(root, dict):
            root = {}
            ent["behaviour_config"] = root
        cfg = root.get(behaviour)
        if not isinstance(cfg, dict):
            cfg = {}
            root[behaviour] = cfg
        return cfg

    def _set_field(ent: dict[str, Any], key: str, value: Any) -> bool:
        if ent.get(key) == value:
            return False
        ent[key] = value
        return True

    # If primary is a SceneTransition, patch it in-place.
    pid = str(primary_id or "").strip()
    if pid:
        ent = find_entity_by_id(entities, pid)
        if isinstance(ent, dict) and not is_player_entity(ent) and _has_behaviour(ent, "SceneTransition"):
            changed_any = False
            changed_any = _ensure_behaviour(ent, "SceneTransition") or changed_any
            cfg = _ensure_cfg(ent, "SceneTransition")
            if cfg.get("target_scene") != tgt:
                cfg["target_scene"] = tgt
                changed_any = True
            if cfg.get("spawn_id") != sp:
                cfg["spawn_id"] = sp
                changed_any = True
            if cfg.get("spawn_point") != sp:
                cfg["spawn_point"] = sp
                changed_any = True
            if require_flags is not None:
                req_gate = sorted({str(v).strip() for v in require_flags if str(v).strip()})
                changed_any = _set_field(ent, "require_flags", req_gate) or changed_any
            if forbid_flags is not None:
                forb_gate = sorted({str(v).strip() for v in forbid_flags if str(v).strip()})
                changed_any = _set_field(ent, "forbid_flags", forb_gate) or changed_any
            if changed_any:
                updated = 1
            return authored_copy, 0, updated

    scene_path = str(controller.current_scene_path or "").strip()
    stem = _san(Path(scene_path).stem if scene_path else "scene")
    target_stem = _san(Path(tgt).stem if tgt else "target")
    x = float(center_x)
    y = float(center_y)
    entity_id = f"{stem}_macro_transition_{target_stem}_{_fmt(x)}_{_fmt(y)}_0_0"

    ent = find_entity_by_id(entities, entity_id)
    if ent is None:
        entities.append({"id": entity_id})
        ent = entities[-1]
        created = 1
    else:
        if isinstance(ent, dict):
            existing_pid = ent.get("prefab_id")
            if (
                isinstance(existing_pid, str)
                and existing_pid.strip()
                and existing_pid.strip() not in {"SceneTransition"}
                and not _has_behaviour(ent, "SceneTransition")
            ):
                raise ValueError(f"prefab_mismatch id={entity_id} prefab_id={existing_pid.strip()!r}")

    changed_any = False
    changed_any = _ensure_behaviour(ent, "SceneTransition") or changed_any
    changed_any = _set_field(ent, "x", x) or changed_any
    changed_any = _set_field(ent, "y", y) or changed_any
    changed_any = _set_field(ent, "layer", ent.get("layer") or "background") or changed_any
    if require_flags is not None:
        req_gate = sorted({str(v).strip() for v in require_flags if str(v).strip()})
        changed_any = _set_field(ent, "require_flags", req_gate) or changed_any
    if forbid_flags is not None:
        forb_gate = sorted({str(v).strip() for v in forbid_flags if str(v).strip()})
        changed_any = _set_field(ent, "forbid_flags", forb_gate) or changed_any
    cfg = _ensure_cfg(ent, "SceneTransition")
    if cfg.get("target_scene") != tgt:
        cfg["target_scene"] = tgt
        changed_any = True
    if cfg.get("spawn_id") != sp:
        cfg["spawn_id"] = sp
        changed_any = True
    if cfg.get("spawn_point") != sp:
        cfg["spawn_point"] = sp
        changed_any = True
    if changed_any and created == 0:
        updated = 1
    return authored_copy, created, updated


def debug_build_macro_dialogue_choice_flag_payload(
    controller: "SceneController",
    *,
    speaker_id: str,
    choice_id: str,
    choice_text: str,
    set_flag: str,
    toast: str | None,
) -> tuple[Dict[str, Any], int, int]:
    """
    Debug-only: build a new authored payload that ensures a Dialogue choice and a SetGameStateOnEvent hook exist.

    Returns (new_payload, created_count, updated_count). Does not mutate scene state by itself.
    """
    from ..entity_paint_mode import ensure_entities_list, find_entity_by_id  # noqa: PLC0415
    from ..entity_paint_mode import _sanitize_entity_id_token as _san  # noqa: PLC0415

    authored = get_authored_scene_payload(controller)
    authored_copy = copy.deepcopy(authored) if isinstance(authored, dict) else {"entities": []}
    entities = ensure_entities_list(authored_copy)

    sid = str(speaker_id or "").strip()
    cid = str(choice_id or "").strip()
    ctext = str(choice_text or "").strip()
    flag = str(set_flag or "").strip()
    toast_text = str(toast or "").strip()

    created = 0
    updated = 0

    def _has_behaviour(ent: dict[str, Any], behaviour: str) -> bool:
        raw = ent.get("behaviours")
        if not isinstance(raw, list):
            return False
        for b in raw:
            if isinstance(b, str) and b.strip() == behaviour:
                return True
            if isinstance(b, dict):
                bt = b.get("type")
                if isinstance(bt, str) and bt.strip() == behaviour:
                    return True
        return False

    def _ensure_cfg(ent: dict[str, Any], behaviour: str) -> dict[str, Any]:
        root = ent.get("behaviour_config")
        if not isinstance(root, dict):
            root = {}
            ent["behaviour_config"] = root
        cfg = root.get(behaviour)
        if not isinstance(cfg, dict):
            cfg = {}
            root[behaviour] = cfg
        return cfg

    # Update speaker dialogue choice.
    speaker_ent = find_entity_by_id(entities, sid)
    if isinstance(speaker_ent, dict) and _has_behaviour(speaker_ent, "Dialogue"):
        changed_any = False
        cfg = _ensure_cfg(speaker_ent, "Dialogue")
        dialogue = cfg.get("dialogue")
        if not isinstance(dialogue, dict):
            dialogue = {"nodes": {"root": {"text": "", "choices": []}}, "start": "root", "speaker": ""}
            cfg["dialogue"] = dialogue
            changed_any = True
        nodes = dialogue.get("nodes")
        if not isinstance(nodes, dict):
            nodes = {}
            dialogue["nodes"] = nodes
            changed_any = True
        start_key = str(dialogue.get("start") or "root")
        start_node = nodes.get(start_key)
        if not isinstance(start_node, dict):
            start_node = {"text": "", "choices": []}
            nodes[start_key] = start_node
            changed_any = True
        choices = start_node.get("choices")
        if not isinstance(choices, list):
            choices = []
            start_node["choices"] = choices
            changed_any = True
        found = None
        for entry in choices:
            if isinstance(entry, dict) and str(entry.get("id") or "").strip() == cid:
                found = entry
                break
        if found is None:
            choices.append({"id": cid, "text": ctext, "next": None, "once": True})
            changed_any = True
        else:
            if found.get("text") != ctext:
                found["text"] = ctext
                changed_any = True
            if "id" not in found:
                found["id"] = cid
                changed_any = True
        if changed_any:
            updated += 1

    # Ensure hook entity exists.
    scene_path = str(controller.current_scene_path or "").strip()
    stem = _san(Path(scene_path).stem if scene_path else "scene")
    hook_id = f"{stem}_macro_choiceflag_{_san(flag)}_{_san(cid)}_0_0"
    hook_ent = find_entity_by_id(entities, hook_id)
    if hook_ent is None:
        entities.append({"id": hook_id})
        hook_ent = entities[-1]
        created += 1
    else:
        if isinstance(hook_ent, dict):
            pid = hook_ent.get("prefab_id")
            if (
                isinstance(pid, str)
                and pid.strip()
                and pid.strip() not in {"SetGameStateOnEvent"}
                and not _has_behaviour(hook_ent, "SetGameStateOnEvent")
            ):
                raise ValueError(f"prefab_mismatch id={hook_id} prefab_id={pid.strip()!r}")

    changed_any = False
    behaviours = hook_ent.get("behaviours")
    if not isinstance(behaviours, list):
        behaviours = []
        hook_ent["behaviours"] = behaviours
        changed_any = True
    if not any(
        (isinstance(b, str) and b.strip() == "SetGameStateOnEvent")
        or (isinstance(b, dict) and str(b.get("type") or "").strip() == "SetGameStateOnEvent")
        for b in behaviours
    ):
        behaviours.append("SetGameStateOnEvent")
        changed_any = True

    cfg = _ensure_cfg(hook_ent, "SetGameStateOnEvent")
    if cfg.get("event_type") != "dialogue_choice":
        cfg["event_type"] = "dialogue_choice"
        changed_any = True
    if cfg.get("payload_field") != "choice_id":
        cfg["payload_field"] = "choice_id"
        changed_any = True
    if cfg.get("payload_value") != cid:
        cfg["payload_value"] = cid
        changed_any = True
    if cfg.get("once") is not True:
        cfg["once"] = True
        changed_any = True
    set_flags = cfg.get("set_flags")
    if not isinstance(set_flags, dict):
        set_flags = {}
        cfg["set_flags"] = set_flags
        changed_any = True
    if flag and set_flags.get(flag) is not True:
        set_flags[flag] = True
        changed_any = True
    if toast_text:
        if cfg.get("toast") != toast_text:
            cfg["toast"] = toast_text
            changed_any = True
        if not isinstance(cfg.get("toast_seconds"), (int, float)) or float(cfg.get("toast_seconds") or 0.0) <= 0.0:
            cfg["toast_seconds"] = 3.0
            changed_any = True
    else:
        if cfg.get("toast") not in (None, ""):
            cfg["toast"] = ""
            changed_any = True

    if changed_any and created == 0:
        updated += 1

    return authored_copy, created, updated


def _debug_preview_diff(controller: "SceneController", before_payload: Dict[str, Any], after_payload: Dict[str, Any]) -> Dict[str, Any]:
    from ..entity_paint_mode import ensure_entities_list  # noqa: PLC0415

    before_entities = ensure_entities_list(before_payload)
    after_entities = ensure_entities_list(after_payload)

    before_by_id: dict[str, dict[str, Any]] = {}
    for ent in before_entities:
        if not isinstance(ent, dict):
            continue
        entity_id = ent.get("id")
        if isinstance(entity_id, str) and entity_id.strip():
            before_by_id[entity_id.strip()] = ent
    after_by_id: dict[str, dict[str, Any]] = {}
    for ent in after_entities:
        if not isinstance(ent, dict):
            continue
        entity_id = ent.get("id")
        if isinstance(entity_id, str) and entity_id.strip():
            after_by_id[entity_id.strip()] = ent

    before_ids = set(before_by_id.keys())
    after_ids = set(after_by_id.keys())
    create_ids = sorted(after_ids - before_ids)
    update_ids = sorted([eid for eid in (after_ids & before_ids) if before_by_id.get(eid) != after_by_id.get(eid)])

    return {
        "will_create": int(len(create_ids)),
        "will_update": int(len(update_ids)),
        "create_ids": create_ids,
        "update_ids": update_ids,
    }


def debug_preview_macro_objective_zone(
    controller: "SceneController",
    *,
    center_x: float,
    center_y: float,
    zone_id: str,
    set_flag: str,
    radius: float,
    toast: str | None,
    require_flags: list[str] | None = None,
    forbid_flags: list[str] | None = None,
    toast_seconds: float | None = None,
) -> Dict[str, Any]:
    before = get_authored_scene_payload(controller)
    after, _created, _updated = debug_build_macro_objective_zone_payload(
        controller,
        center_x=float(center_x),
        center_y=float(center_y),
        zone_id=zone_id,
        set_flag=set_flag,
        radius=float(radius),
        toast=toast,
        require_flags=require_flags,
        forbid_flags=forbid_flags,
        toast_seconds=toast_seconds,
    )
    return _debug_preview_diff(controller, before, after)


def debug_preview_macro_door_transition(
    controller: "SceneController",
    *,
    center_x: float,
    center_y: float,
    target_scene: str,
    spawn_id: str,
    primary_id: str | None,
) -> Dict[str, Any]:
    before = get_authored_scene_payload(controller)
    after, _created, _updated = debug_build_macro_door_transition_payload(
        controller,
        center_x=float(center_x),
        center_y=float(center_y),
        target_scene=target_scene,
        spawn_id=spawn_id,
        primary_id=primary_id,
    )
    return _debug_preview_diff(controller, before, after)


def debug_preview_macro_dialogue_choice_flag(
    controller: "SceneController",
    *,
    speaker_id: str,
    choice_id: str,
    choice_text: str,
    set_flag: str,
    toast: str | None,
) -> Dict[str, Any]:
    before = get_authored_scene_payload(controller)
    after, _created, _updated = debug_build_macro_dialogue_choice_flag_payload(
        controller,
        speaker_id=speaker_id,
        choice_id=choice_id,
        choice_text=choice_text,
        set_flag=set_flag,
        toast=toast,
    )
    return _debug_preview_diff(controller, before, after)
