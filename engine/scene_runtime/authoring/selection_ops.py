from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any, Dict

import engine.optional_arcade as optional_arcade
from engine.swallowed_exceptions import _log_swallow

from ..index_build import build_scene_index_from_sprites
from .entity_ops import _debug_iter_authoring_payloads, debug_find_sprite_by_entity_id, get_authored_scene_payload

if TYPE_CHECKING:
    from ...scene_controller import SceneController


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
    from ...entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

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
    except Exception:  # noqa: BLE001  # REASON: selection ops fallback isolation
        _log_swallow("SELE-002", "primary entity x parse", once=True)
        primary_x = 0.0
    try:
        primary_y = float(primary_entity.get("y", 0.0))
    except Exception:  # noqa: BLE001  # REASON: selection ops fallback isolation
        _log_swallow("SELE-003", "primary entity y parse", once=True)
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
        except Exception:  # noqa: BLE001  # REASON: selection ops fallback isolation
            _log_swallow("SELE-004", "entity x parse", once=True)
            ex = 0.0
        try:
            ey = float(ent.get("y", 0.0))
        except Exception:  # noqa: BLE001  # REASON: selection ops fallback isolation
            _log_swallow("SELE-005", "entity y parse", once=True)
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
    from ...entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

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
        except Exception:  # noqa: BLE001  # REASON: selection ops fallback isolation
            _log_swallow("SELE-006", "snap_world_to_tile_center import/call", once=True)
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
            except Exception:  # noqa: BLE001  # REASON: selection ops fallback isolation
                _log_swallow("SELE-007", "_create_sprite call", once=True)
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
    from ...entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

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
        except Exception:  # noqa: BLE001  # REASON: selection ops fallback isolation
            _log_swallow("SELE-008", "transform entity x parse", once=True)
            x = 0.0
        try:
            y = float(ent.get("y", 0.0))
        except Exception:  # noqa: BLE001  # REASON: selection ops fallback isolation
            _log_swallow("SELE-009", "transform entity y parse", once=True)
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
        snap_world_to_tile_center: Any = None
        try:
            from engine.entity_select_mode import snap_world_to_tile_center as _snap_world_to_tile_center  # noqa: PLC0415
            snap_world_to_tile_center = _snap_world_to_tile_center
        except Exception:  # noqa: BLE001  # REASON: selection ops fallback isolation
            _log_swallow("SELE-010", "snap_world_to_tile_center import", once=True)
            snap_world_to_tile_center = None
        if callable(snap_world_to_tile_center):
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
                from ...entity_paint_mode import apply_move_entity  # noqa: PLC0415

                moved_any = apply_move_entity(payload, entity_id=entity_id, x=float(x), y=float(y)) or moved_any
            except Exception:  # noqa: BLE001  # REASON: selection ops fallback isolation
                _log_swallow("SELE-011", "apply_move_entity call", once=True)
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
            except Exception:  # noqa: BLE001  # REASON: selection ops fallback isolation
                _log_swallow("SELE-001", "engine/scene_runtime/authoring/selection_ops.py pass-only blanket swallow")
                pass

    if moved_any:
        controller._scene_index = build_scene_index_from_sprites(controller.all_sprites)
    return len(new_positions) if moved_any else 0

