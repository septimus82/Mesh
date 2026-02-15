from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any, Callable, Dict

import engine.optional_arcade as optional_arcade

from ...background_layers import parse_background_layers
from ..index_build import build_scene_index_from_sprites

if TYPE_CHECKING:
    from ...scene_controller import SceneController


# ---------------------------------------------------------------------------
# Private helpers – shared scaffolding for debug_* authoring ops
# ---------------------------------------------------------------------------

def _sorted_dedup_ids(raw_ids: list[str] | None) -> list[str]:
    """Return sorted, deduplicated, stripped, non-empty entity IDs."""
    return sorted(
        {str(i).strip() for i in (raw_ids or []) if isinstance(i, str) and str(i).strip()}
    )


def _build_entity_index(entities: list[Dict[str, Any]]) -> dict[str, Dict[str, Any]]:
    """Build an ``{id: entity_dict}`` index in O(N) for fast lookup."""
    idx: dict[str, Dict[str, Any]] = {}
    for ent in entities:
        if isinstance(ent, dict):
            eid = ent.get("id")
            if isinstance(eid, str) and eid.strip():
                idx[eid.strip()] = ent
    return idx


def _collect_participants(
    sorted_ids: list[str],
    index: dict[str, Dict[str, Any]],
    is_player_entity: Callable[[dict[str, Any]], bool],
    *,
    require_position: bool = False,
    skip_group_entity: bool = False,
) -> tuple[list[tuple[str, dict]], int]:
    """Gather participant entities from *sorted_ids* using an index.

    Returns ``(participants, skipped_count)``.  *participants* is a list of
    ``(id, entity_dict)`` pairs in the same order as *sorted_ids*.
    """
    participants: list[tuple[str, dict]] = []
    skipped = 0
    for eid in sorted_ids:
        ent = index.get(eid)
        if not isinstance(ent, dict):
            skipped += 1
            continue
        if is_player_entity(ent):
            skipped += 1
            continue
        if require_position and ("x" not in ent or "y" not in ent):
            skipped += 1
            continue
        if skip_group_entity and _is_group_entity(ent):
            skipped += 1
            continue
        participants.append((eid, ent))
    return participants, skipped


def _build_used_id_set(entities: list[Dict[str, Any]]) -> set[str]:
    """Collect all entity IDs currently in the scene for collision avoidance."""
    used: set[str] = set()
    for ent in entities:
        if isinstance(ent, dict):
            eid = ent.get("id")
            if isinstance(eid, str) and eid.strip():
                used.add(eid.strip())
    return used


def _next_unique_dup_id(orig_id: str, used_ids: set[str]) -> str:
    """Allocate the next ``{orig_id}__dup{k}`` that isn't in *used_ids*, and add it."""
    k = 1
    while True:
        candidate = f"{orig_id}__dup{k}"
        if candidate not in used_ids:
            used_ids.add(candidate)
            return candidate
        k += 1


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
        from ...scene_entity_gating import filter_entities_by_flags  # noqa: PLC0415

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
    from ...entity_paint_mode import ensure_entities_list, find_entity_by_id  # noqa: PLC0415

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
    from ...entity_paint_mode import apply_remove_entity  # noqa: PLC0415

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
    from ...entity_paint_mode import apply_move_entity  # noqa: PLC0415

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
    from ...entity_paint_mode import ensure_entities_list  # noqa: PLC0415

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

def debug_set_prefab_id(controller: "SceneController", selected_ids: list[str], prefab_id: str) -> tuple[int, int]:
    """
    Debug-only: set prefab_id for all selected authored entities (skips player).

    Operates on the authored payload only and reapplies it (no disk I/O).
    Returns (changed_count, skipped_player_count).
    """
    from ...entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

    wanted = str(prefab_id or "").strip()
    if not isinstance(selected_ids, list) or not selected_ids or not wanted:
        return (0, 0)

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return (0, 0)
    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)
    index = _build_entity_index(entities)

    changed = 0
    skipped_player = 0
    for entity_id in _sorted_dedup_ids(selected_ids):
        ent = index.get(entity_id)
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
    from ...entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

    wanted = str(behaviour_name or "").strip()
    if not isinstance(selected_ids, list) or not selected_ids or not wanted:
        return (0, 0)

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return (0, 0)
    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)
    index = _build_entity_index(entities)

    changed = 0
    skipped_player = 0
    for entity_id in _sorted_dedup_ids(selected_ids):
        ent = index.get(entity_id)
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
    from ...entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

    wanted = str(behaviour_name or "").strip()
    if not isinstance(selected_ids, list) or not selected_ids or not wanted:
        return (0, 0)

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return (0, 0)
    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)
    index = _build_entity_index(entities)

    changed = 0
    skipped_player = 0
    for entity_id in _sorted_dedup_ids(selected_ids):
        ent = index.get(entity_id)
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
    from ...entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

    entity_id = str(primary_id or "").strip()
    wanted = str(name or "").strip()
    if not entity_id or not wanted:
        return (0, 0)

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return (0, 0)
    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)
    index = _build_entity_index(entities)
    ent = index.get(entity_id)
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
    from ...entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

    wanted = str(tag or "").strip()
    if not isinstance(selected_ids, list) or not selected_ids or not wanted:
        return (0, 0)

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return (0, 0)
    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)
    index = _build_entity_index(entities)

    changed = 0
    skipped_player = 0
    for entity_id in _sorted_dedup_ids(selected_ids):
        ent = index.get(entity_id)
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

def debug_remove_tag(controller: "SceneController", selected_ids: list[str], tag: str) -> tuple[int, int]:
    """
    Debug-only: remove a tag from all selected authored entities (idempotent, skips player).

    Operates on the authored payload only and reapplies it (no disk I/O).
    Returns (changed_count, skipped_player_count).
    """
    from ...entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

    wanted = str(tag or "").strip()
    if not isinstance(selected_ids, list) or not selected_ids or not wanted:
        return (0, 0)

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return (0, 0)
    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)
    index = _build_entity_index(entities)

    changed = 0
    skipped_player = 0
    for entity_id in _sorted_dedup_ids(selected_ids):
        ent = index.get(entity_id)
        if not isinstance(ent, dict):
            continue
        if is_player_entity(ent):
            skipped_player += 1
            continue
        tags = ent.get("tags")
        if not isinstance(tags, list):
            continue
        existing = [str(t).strip() for t in tags if isinstance(t, str) and str(t).strip()]
        if wanted in existing:
            ent["tags"] = [t for t in existing if t != wanted]
            changed += 1

    if changed > 0:
        debug_apply_authored_scene_payload(controller, authored_copy)
    return (changed, skipped_player)

def debug_toggle_tag(controller: "SceneController", selected_ids: list[str], tag: str) -> tuple[int, int, int]:
    """
    Debug-only: toggle a tag on all selected authored entities (skips player).

    For each entity: if the tag is present it is removed, otherwise it is added.
    Operates on the authored payload only and reapplies it (no disk I/O).
    Returns (added_count, removed_count, skipped_player_count).
    """
    from ...entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

    wanted = str(tag or "").strip()
    if not isinstance(selected_ids, list) or not selected_ids or not wanted:
        return (0, 0, 0)

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return (0, 0, 0)
    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)
    index = _build_entity_index(entities)

    added = 0
    removed = 0
    skipped_player = 0
    for entity_id in _sorted_dedup_ids(selected_ids):
        ent = index.get(entity_id)
        if not isinstance(ent, dict):
            continue
        if is_player_entity(ent):
            skipped_player += 1
            continue
        tags = ent.get("tags")
        if not isinstance(tags, list):
            tags = []
            ent["tags"] = tags
        existing = [str(t).strip() for t in tags if isinstance(t, str) and str(t).strip()]
        if wanted in existing:
            ent["tags"] = [t for t in existing if t != wanted]
            removed += 1
        else:
            tags.clear()
            tags.extend(existing)
            tags.append(wanted)
            added += 1

    if added > 0 or removed > 0:
        debug_apply_authored_scene_payload(controller, authored_copy)
    return (added, removed, skipped_player)

def debug_batch_rename(controller: "SceneController", selected_ids: list[str], prefix: str = "", suffix: str = "") -> tuple[int, int]:
    """
    Debug-only: batch rename selected authored entities by prepending *prefix* and appending *suffix* (skips player).

    Entities without an existing ``name`` field are skipped.
    Operates on the authored payload only and reapplies it (no disk I/O).
    Returns (changed_count, skipped_player_count).
    """
    from ...entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

    pfx = str(prefix or "")
    sfx = str(suffix or "")
    if not isinstance(selected_ids, list) or not selected_ids or (not pfx and not sfx):
        return (0, 0)

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return (0, 0)
    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)
    index = _build_entity_index(entities)

    changed = 0
    skipped_player = 0
    for entity_id in _sorted_dedup_ids(selected_ids):
        ent = index.get(entity_id)
        if not isinstance(ent, dict):
            continue
        if is_player_entity(ent):
            skipped_player += 1
            continue
        old_name = ent.get("name")
        if not isinstance(old_name, str):
            continue
        new_name = pfx + old_name + sfx
        if new_name != old_name:
            ent["name"] = new_name
            changed += 1

    if changed > 0:
        debug_apply_authored_scene_payload(controller, authored_copy)
    return (changed, skipped_player)

def debug_set_names(
    controller: "SceneController",
    entity_ids: list[str],
    base: str,
    start: int = 1,
    width: int = 3,
) -> dict[str, Any]:
    """
    Debug-only: rename selected authored entities to ``base_NNN`` with deterministic numbering.

    Entities are processed in sorted-ID order.  Those without a ``name`` field are
    skipped.  Player entities are skipped.

    Returns a dict with keys: ok, renamed, skipped, base, start, width.
    """
    from ...entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

    cleaned_base = str(base or "").strip()
    if not cleaned_base:
        return {"ok": False, "renamed": 0, "skipped": 0, "base": "", "start": start, "width": width}

    if not isinstance(start, int) or start < 0:
        return {"ok": False, "renamed": 0, "skipped": 0, "base": cleaned_base, "start": start, "width": width}
    if not isinstance(width, int) or width < 1 or width > 6:
        return {"ok": False, "renamed": 0, "skipped": 0, "base": cleaned_base, "start": start, "width": width}

    if not isinstance(entity_ids, list) or not entity_ids:
        return {"ok": True, "renamed": 0, "skipped": 0, "base": cleaned_base, "start": start, "width": width}

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return {"ok": True, "renamed": 0, "skipped": 0, "base": cleaned_base, "start": start, "width": width}
    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)
    index = _build_entity_index(entities)

    renamed = 0
    skipped = 0
    idx = 0
    for entity_id in _sorted_dedup_ids(entity_ids):
        ent = index.get(entity_id)
        if not isinstance(ent, dict):
            continue
        if is_player_entity(ent):
            skipped += 1
            continue
        if "name" not in ent:
            skipped += 1
            continue
        new_name = f"{cleaned_base}_{start + idx:0{width}d}"
        ent["name"] = new_name
        renamed += 1
        idx += 1

    if renamed > 0:
        debug_apply_authored_scene_payload(controller, authored_copy)
    return {"ok": True, "renamed": renamed, "skipped": skipped, "base": cleaned_base, "start": start, "width": width}


# ---------------------------------------------------------------------------
# Alignment helpers
# ---------------------------------------------------------------------------

_ALIGN_X_MODES = frozenset({"left", "center", "right"})
_ALIGN_Y_MODES = frozenset({"top", "middle", "bottom"})
_ALIGN_VALID_AXES = frozenset({"x", "y"})
_ALIGN_VALID_REFS = frozenset({"primary", "group"})


def _entity_bounds(ent: dict[str, Any]) -> tuple[float, float, float, float] | None:
    """Return (cx, cy, half_w, half_h) from authored entity data, or *None* if no position."""
    raw_x = ent.get("x")
    raw_y = ent.get("y")
    if raw_x is None or raw_y is None:
        return None
    try:
        cx = float(raw_x)
        cy = float(raw_y)
    except (TypeError, ValueError):
        return None
    w_val = ent.get("width", ent.get("w"))
    h_val = ent.get("height", ent.get("h"))
    try:
        hw = float(w_val) / 2.0 if w_val is not None else 16.0
    except (TypeError, ValueError):
        hw = 16.0
    try:
        hh = float(h_val) / 2.0 if h_val is not None else 16.0
    except (TypeError, ValueError):
        hh = 16.0
    return (cx, cy, hw, hh)


def _anchor_value(cx: float, cy: float, hw: float, hh: float, axis: str, mode: str) -> float:
    if axis == "x":
        if mode == "left":
            return cx - hw
        if mode == "right":
            return cx + hw
        return cx  # center
    # axis == "y"
    if mode == "top":
        return cy + hh
    if mode == "bottom":
        return cy - hh
    return cy  # middle


def debug_align_selection(
    controller: "SceneController",
    entity_ids: list[str],
    axis: str,
    mode: str,
    reference: str = "primary",
    primary_id: str = "",
) -> dict[str, Any]:
    """
    Debug-only: align selected authored entities along *axis* to the anchor
    determined by *mode* and *reference*.

    *reference* = ``"primary"`` uses the entity identified by *primary_id* as
    the alignment target.  ``"group"`` computes the anchor from the
    min/max/center of the entire selection.

    Returns ``{ok, moved, skipped, axis, mode, reference}``.
    """
    from ...entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

    ax = str(axis or "").strip().lower()
    md = str(mode or "").strip().lower()
    ref = str(reference or "primary").strip().lower()

    fail = {"ok": False, "moved": 0, "skipped": 0, "axis": ax, "mode": md, "reference": ref}

    if ax not in _ALIGN_VALID_AXES:
        return fail
    valid_modes = _ALIGN_X_MODES if ax == "x" else _ALIGN_Y_MODES
    if md not in valid_modes:
        return fail
    if ref not in _ALIGN_VALID_REFS:
        return fail

    sorted_ids = _sorted_dedup_ids(entity_ids)
    if len(sorted_ids) < 2:
        return fail

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return fail
    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)
    index = _build_entity_index(entities)

    # Gather bounds for all selected non-player entities.
    bounds_map: dict[str, tuple[float, float, float, float]] = {}
    skipped = 0
    for eid in sorted_ids:
        ent = index.get(eid)
        if not isinstance(ent, dict):
            skipped += 1
            continue
        if is_player_entity(ent):
            skipped += 1
            continue
        b = _entity_bounds(ent)
        if b is None:
            skipped += 1
            continue
        bounds_map[eid] = b

    if len(bounds_map) < 2:
        return fail

    # Determine target anchor value.
    pid = str(primary_id or "").strip()
    if ref == "primary" and pid and pid in bounds_map:
        pcx, pcy, phw, phh = bounds_map[pid]
        target = _anchor_value(pcx, pcy, phw, phh, ax, md)
    else:
        # Fall back to group anchor.
        anchors = [_anchor_value(cx, cy, hw, hh, ax, md) for cx, cy, hw, hh in bounds_map.values()]
        if md in ("left", "bottom"):
            target = min(anchors)
        elif md in ("right", "top"):
            target = max(anchors)
        else:
            target = sum(anchors) / len(anchors)  # center / middle

    # Apply moves.
    moved = 0
    for eid in sorted_ids:
        if eid not in bounds_map:
            continue
        cx, cy, hw, hh = bounds_map[eid]
        current_anchor = _anchor_value(cx, cy, hw, hh, ax, md)
        delta = target - current_anchor
        if abs(delta) < 1e-6:
            continue
        ent = index.get(eid)
        if not isinstance(ent, dict):
            continue
        if ax == "x":
            ent["x"] = cx + delta
        else:
            ent["y"] = cy + delta
        moved += 1

    if moved > 0:
        debug_apply_authored_scene_payload(controller, authored_copy)
    return {"ok": True, "moved": moved, "skipped": skipped, "axis": ax, "mode": md, "reference": ref}


_DISTRIBUTE_VALID_MODES = frozenset({"gap", "center"})


def debug_distribute_selection(
    controller: "SceneController",
    entity_ids: list[str],
    axis: str,
    mode: str = "gap",
    reference: str = "group",
    primary_id: str = "",
) -> dict[str, Any]:
    """
    Debug-only: distribute selected authored entities evenly along *axis*.

    *mode* = ``"gap"``  – equal spacing between bounding-box edges.
    *mode* = ``"center"`` – equal spacing between entity centres.

    *reference* = ``"group"`` uses the overall min/max of the selection as
    the fixed endpoints.  ``"primary"`` uses the primary entity as one
    endpoint and the furthest entity as the other.

    Entities are sorted by their current position on *axis* before spacing
    is computed.  The two endpoint entities are kept in place; interior
    entities are redistributed.

    Returns ``{ok, moved, skipped, axis, mode, reference}``.
    """
    from ...entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

    ax = str(axis or "").strip().lower()
    md = str(mode or "gap").strip().lower()
    ref = str(reference or "group").strip().lower()

    fail = {"ok": False, "moved": 0, "skipped": 0, "axis": ax, "mode": md, "reference": ref}

    if ax not in _ALIGN_VALID_AXES:
        return fail
    if md not in _DISTRIBUTE_VALID_MODES:
        return fail
    if ref not in _ALIGN_VALID_REFS:
        return fail

    sorted_ids = _sorted_dedup_ids(entity_ids)
    if len(sorted_ids) < 3:
        return fail

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return fail
    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)
    index = _build_entity_index(entities)

    # Gather bounds.
    bounds_map: dict[str, tuple[float, float, float, float]] = {}
    skipped = 0
    for eid in sorted_ids:
        ent = index.get(eid)
        if not isinstance(ent, dict):
            skipped += 1
            continue
        if is_player_entity(ent):
            skipped += 1
            continue
        b = _entity_bounds(ent)
        if b is None:
            skipped += 1
            continue
        bounds_map[eid] = b

    if len(bounds_map) < 3:
        return fail

    # Sort participating entities by current center on the chosen axis.
    ax_idx = 0 if ax == "x" else 1  # index into (cx, cy, hw, hh)
    ordered = sorted(bounds_map.keys(), key=lambda e: bounds_map[e][ax_idx])

    first_eid = ordered[0]
    last_eid = ordered[-1]

    if md == "center":
        # Equal spacing between centres.
        first_center = bounds_map[first_eid][ax_idx]
        last_center = bounds_map[last_eid][ax_idx]
        n = len(ordered)
        step = (last_center - first_center) / (n - 1) if n > 1 else 0.0

        moved = 0
        for i, eid in enumerate(ordered):
            target_center = first_center + step * i
            cx, cy, hw, hh = bounds_map[eid]
            current_center = bounds_map[eid][ax_idx]
            delta = target_center - current_center
            if abs(delta) < 1e-6:
                continue
            ent = index.get(eid)
            if not isinstance(ent, dict):
                continue
            if ax == "x":
                ent["x"] = cx + delta
            else:
                ent["y"] = cy + delta
            moved += 1
    else:
        # mode == "gap": equal spacing between bounding-box edges.
        hw_idx = 2 if ax == "x" else 3  # half-width or half-height index
        # Total extent from first left-edge to last right-edge.
        first_left = bounds_map[first_eid][ax_idx] - bounds_map[first_eid][hw_idx]
        last_right = bounds_map[last_eid][ax_idx] + bounds_map[last_eid][hw_idx]
        total_span = last_right - first_left
        total_entity_size = sum(bounds_map[e][hw_idx] * 2.0 for e in ordered)
        total_gap = total_span - total_entity_size
        n_gaps = len(ordered) - 1
        gap = total_gap / n_gaps if n_gaps > 0 else 0.0

        moved = 0
        cursor = first_left
        for eid in ordered:
            cx, cy, hw_val, hh_val = bounds_map[eid]
            entity_half = bounds_map[eid][hw_idx]
            target_center = cursor + entity_half
            current_center = bounds_map[eid][ax_idx]
            delta = target_center - current_center
            cursor = target_center + entity_half + gap
            if abs(delta) < 1e-6:
                continue
            ent = index.get(eid)
            if not isinstance(ent, dict):
                continue
            if ax == "x":
                ent["x"] = cx + delta
            else:
                ent["y"] = cy + delta
            moved += 1

    if moved > 0:
        debug_apply_authored_scene_payload(controller, authored_copy)
    return {"ok": True, "moved": moved, "skipped": skipped, "axis": ax, "mode": md, "reference": ref}


# ---------------------------------------------------------------------------
# Snap to grid
# ---------------------------------------------------------------------------

_SNAP_VALID_AXES = frozenset({"x", "y", "xy"})
_SNAP_VALID_MODES = frozenset({"nearest", "floor", "ceil"})


def _snap_value(v: float, step: int, mode: str) -> float:
    """Snap *v* to the grid defined by *step* using *mode*.

    ``nearest`` – deterministic half-up rounding (ties round away from zero).
    ``floor`` – always round toward negative infinity.
    ``ceil``  – always round toward positive infinity.
    """
    import math  # noqa: PLC0415
    s = float(step)
    if mode == "floor":
        return s * math.floor(v / s)
    if mode == "ceil":
        return s * math.ceil(v / s)
    # nearest – half-up (ties away from zero)
    return s * math.copysign(math.floor(abs(v) / s + 0.5), v)


def debug_snap_to_grid(
    controller: "SceneController",
    entity_ids: list[str],
    step: int,
    axes: str = "xy",
    mode: str = "nearest",
) -> dict:
    """Debug-only: snap selected entities to a grid.

    *step* – positive integer grid spacing.
    *axes* – ``"x"``, ``"y"``, or ``"xy"``.
    *mode* – ``"nearest"`` (half-up), ``"floor"``, or ``"ceil"``.

    Returns ``{ok, moved, skipped, step, axes, mode}``.
    """
    from ...entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

    ax = str(axes or "xy").strip().lower()
    md = str(mode or "nearest").strip().lower()
    st = int(step) if isinstance(step, (int, float)) else 0

    fail: dict = {"ok": False, "moved": 0, "skipped": 0, "step": st, "axes": ax, "mode": md}

    if ax not in _SNAP_VALID_AXES:
        return fail
    if md not in _SNAP_VALID_MODES:
        return fail
    if st <= 0:
        return fail

    sorted_ids = _sorted_dedup_ids(entity_ids)
    if not sorted_ids:
        return fail

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return fail
    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)
    index = _build_entity_index(entities)

    moved = 0
    skipped = 0
    snap_x = "x" in ax
    snap_y = "y" in ax

    for eid in sorted_ids:
        ent = index.get(eid)
        if not isinstance(ent, dict):
            skipped += 1
            continue
        if is_player_entity(ent):
            skipped += 1
            continue
        if "x" not in ent and "y" not in ent:
            skipped += 1
            continue

        changed = False
        if snap_x and "x" in ent:
            new_x = _snap_value(float(ent["x"]), st, md)
            if abs(new_x - float(ent["x"])) > 1e-9:
                ent["x"] = new_x
                changed = True
        if snap_y and "y" in ent:
            new_y = _snap_value(float(ent["y"]), st, md)
            if abs(new_y - float(ent["y"])) > 1e-9:
                ent["y"] = new_y
                changed = True
        if changed:
            moved += 1

    if moved > 0:
        debug_apply_authored_scene_payload(controller, authored_copy)
    return {"ok": moved > 0, "moved": moved, "skipped": skipped, "step": st, "axes": ax, "mode": md}


# ---------------------------------------------------------------------------
# Nudge selection
# ---------------------------------------------------------------------------

def debug_nudge_selection(
    controller: "SceneController",
    entity_ids: list[str],
    dx: float,
    dy: float,
    count: int = 1,
    step: float | None = None,
) -> dict:
    """Debug-only: nudge selected entities by a deterministic delta.

    *dx*, *dy* – direction / raw delta.
    *count* – repeat multiplier (must be >= 1).
    *step* – if provided (> 0), scales dx/dy as direction multipliers.

    Effective delta:
        If *step* is not None:  eff_dx = dx * step * count
        Else:                   eff_dx = dx * count
    (same for dy.)

    Returns ``{ok, moved, skipped, dx, dy, count, step}``.
    """
    from ...entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

    cnt = int(count) if isinstance(count, (int, float)) else 0
    raw_dx = float(dx)
    raw_dy = float(dy)
    st: float | None = None
    if step is not None:
        st = float(step)

    fail: dict = {"ok": False, "moved": 0, "skipped": 0, "dx": 0.0, "dy": 0.0, "count": cnt, "step": st}

    if cnt < 1:
        return fail
    if st is not None and st <= 0:
        return fail

    if st is not None:
        eff_dx = raw_dx * st * cnt
        eff_dy = raw_dy * st * cnt
    else:
        eff_dx = raw_dx * cnt
        eff_dy = raw_dy * cnt

    result_base: dict = {"ok": True, "moved": 0, "skipped": 0, "dx": eff_dx, "dy": eff_dy, "count": cnt, "step": st}

    if abs(eff_dx) < 1e-9 and abs(eff_dy) < 1e-9:
        return result_base  # no-op, ok=true

    sorted_ids = _sorted_dedup_ids(entity_ids)
    if not sorted_ids:
        fail["dx"] = eff_dx
        fail["dy"] = eff_dy
        return fail

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        fail["dx"] = eff_dx
        fail["dy"] = eff_dy
        return fail
    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)
    index = _build_entity_index(entities)

    moved = 0
    skipped = 0

    for eid in sorted_ids:
        ent = index.get(eid)
        if not isinstance(ent, dict):
            skipped += 1
            continue
        if is_player_entity(ent):
            skipped += 1
            continue
        if "x" not in ent and "y" not in ent:
            skipped += 1
            continue

        if "x" in ent:
            ent["x"] = float(ent["x"]) + eff_dx
        if "y" in ent:
            ent["y"] = float(ent["y"]) + eff_dy
        moved += 1

    if moved > 0:
        debug_apply_authored_scene_payload(controller, authored_copy)
    return {"ok": moved > 0, "moved": moved, "skipped": skipped, "dx": eff_dx, "dy": eff_dy, "count": cnt, "step": st}


# ---------------------------------------------------------------------------
# Rotate selection
# ---------------------------------------------------------------------------

_ROTATE_VALID_ABOUT = frozenset({"self", "primary", "group"})


def debug_rotate_selection(
    controller: "SceneController",
    entity_ids: list[str],
    deg: float,
    about: str = "self",
    primary_id: str = "",
) -> dict:
    """Debug-only: rotate selected entities by *deg* degrees.

    *about* controls pivot behaviour:
    - ``"self"``    – rotate each entity's own ``rotation`` field only.
    - ``"primary"`` – also rotate positions around the primary entity's centre.
    - ``"group"``   – also rotate positions around the group centroid.

    Rotation is clockwise-positive (matching engine coordinate conventions).
    The ``rotation`` field is normalised to [0, 360).

    Returns ``{ok, rotated, moved, skipped, deg, about}``.
    """
    import math  # noqa: PLC0415
    from ...entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

    ab = str(about or "self").strip().lower()
    d = float(deg)

    fail: dict = {"ok": False, "rotated": 0, "moved": 0, "skipped": 0, "deg": d, "about": ab}

    if ab not in _ROTATE_VALID_ABOUT:
        return fail

    if abs(d) < 1e-9:
        return {"ok": True, "rotated": 0, "moved": 0, "skipped": 0, "deg": d, "about": ab}

    sorted_ids = _sorted_dedup_ids(entity_ids)
    if not sorted_ids:
        return {"ok": True, "rotated": 0, "moved": 0, "skipped": 0, "deg": d, "about": ab}

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return fail
    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)
    index = _build_entity_index(entities)

    # Collect participating entities (skip player / missing position).
    participants: list[tuple[str, dict]] = []
    skipped = 0
    for eid in sorted_ids:
        ent = index.get(eid)
        if not isinstance(ent, dict):
            skipped += 1
            continue
        if is_player_entity(ent):
            skipped += 1
            continue
        participants.append((eid, ent))

    if not participants:
        return {"ok": True, "rotated": 0, "moved": 0, "skipped": skipped, "deg": d, "about": ab}

    # Determine pivot for position rotation.
    pivot: tuple[float, float] | None = None
    if ab == "primary":
        pid = str(primary_id or "").strip()
        if pid:
            pent = index.get(pid)
            if isinstance(pent, dict) and "x" in pent and "y" in pent:
                pivot = (float(pent["x"]), float(pent["y"]))
        if pivot is None:
            return fail
    elif ab == "group":
        xs: list[float] = []
        ys: list[float] = []
        for _eid, ent in participants:
            if "x" in ent and "y" in ent:
                xs.append(float(ent["x"]))
                ys.append(float(ent["y"]))
        if not xs:
            return fail
        pivot = (sum(xs) / len(xs), sum(ys) / len(ys))

    rad = math.radians(d)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)

    rotated = 0
    moved = 0
    for _eid, ent in participants:
        # Rotate the entity's own rotation field.
        old_rot = float(ent.get("rotation", 0.0))
        new_rot = (old_rot + d) % 360.0
        ent["rotation"] = new_rot
        rotated += 1

        # Rotate position around pivot if requested.
        if pivot is not None and "x" in ent and "y" in ent:
            ox = float(ent["x"]) - pivot[0]
            oy = float(ent["y"]) - pivot[1]
            nx = ox * cos_a - oy * sin_a + pivot[0]
            ny = ox * sin_a + oy * cos_a + pivot[1]
            if abs(nx - float(ent["x"])) > 1e-9 or abs(ny - float(ent["y"])) > 1e-9:
                ent["x"] = nx
                ent["y"] = ny
                moved += 1

    if rotated > 0 or moved > 0:
        debug_apply_authored_scene_payload(controller, authored_copy)
    return {"ok": True, "rotated": rotated, "moved": moved, "skipped": skipped, "deg": d, "about": ab}


# ---------------------------------------------------------------------------
# Mirror / flip selection
# ---------------------------------------------------------------------------

_MIRROR_VALID_AXES = frozenset({"x", "y"})
_MIRROR_VALID_ABOUT = frozenset({"group", "primary"})


def debug_mirror_selection(
    controller: "SceneController",
    entity_ids: list[str],
    axis: str,
    about: str = "group",
    primary_id: str = "",
    include_rotation: bool = True,
) -> dict:
    """Debug-only: mirror / flip selected entities across an axis.

    *axis* = ``"x"`` mirrors across a vertical line (flips left/right):
        ``x' = 2*px - x``
    *axis* = ``"y"`` mirrors across a horizontal line (flips up/down):
        ``y' = 2*py - y``

    *about* = ``"group"`` uses the centroid of participating positions as
    pivot.  ``"primary"`` uses the primary entity's position.

    If *include_rotation* is True, entity ``rotation`` fields are mirrored too:
        axis="x": ``new_rot = (360 - rot) % 360``
        axis="y": ``new_rot = (180 - rot) % 360``

    Returns ``{ok, moved, rotated, skipped, axis, about, include_rotation}``.
    """
    from ...entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

    ax = str(axis or "").strip().lower()
    ab = str(about or "group").strip().lower()
    inc_rot = bool(include_rotation)

    fail: dict = {
        "ok": False, "moved": 0, "rotated": 0, "skipped": 0,
        "axis": ax, "about": ab, "include_rotation": inc_rot,
    }

    if ax not in _MIRROR_VALID_AXES:
        return fail
    if ab not in _MIRROR_VALID_ABOUT:
        return fail

    sorted_ids = _sorted_dedup_ids(entity_ids)
    if not sorted_ids:
        return {"ok": True, "moved": 0, "rotated": 0, "skipped": 0, "axis": ax, "about": ab, "include_rotation": inc_rot}

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return fail
    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)
    index = _build_entity_index(entities)

    # Collect participating entities (have position, not player).
    participants: list[tuple[str, dict]] = []
    skipped = 0
    for eid in sorted_ids:
        ent = index.get(eid)
        if not isinstance(ent, dict):
            skipped += 1
            continue
        if is_player_entity(ent):
            skipped += 1
            continue
        if "x" not in ent or "y" not in ent:
            skipped += 1
            continue
        participants.append((eid, ent))

    if not participants:
        return {"ok": True, "moved": 0, "rotated": 0, "skipped": skipped, "axis": ax, "about": ab, "include_rotation": inc_rot}

    # Determine pivot.
    if ab == "primary":
        pid = str(primary_id or "").strip()
        if not pid:
            return fail
        pent = index.get(pid)
        if not isinstance(pent, dict) or "x" not in pent or "y" not in pent:
            return fail
        pivot = (float(pent["x"]), float(pent["y"]))
    else:
        # group centroid
        xs = [float(ent["x"]) for _eid, ent in participants]
        ys = [float(ent["y"]) for _eid, ent in participants]
        pivot = (sum(xs) / len(xs), sum(ys) / len(ys))

    moved = 0
    rotated = 0

    for _eid, ent in participants:
        ex = float(ent["x"])
        ey = float(ent["y"])

        if ax == "x":
            new_x = 2.0 * pivot[0] - ex
            if abs(new_x - ex) > 1e-9:
                ent["x"] = new_x
                moved += 1
        else:
            new_y = 2.0 * pivot[1] - ey
            if abs(new_y - ey) > 1e-9:
                ent["y"] = new_y
                moved += 1

        if inc_rot:
            old_rot = float(ent.get("rotation", 0.0))
            if ax == "x":
                new_rot = (360.0 - old_rot) % 360.0
            else:
                new_rot = (180.0 - old_rot) % 360.0
            if abs(new_rot - old_rot) > 1e-9:
                ent["rotation"] = new_rot
                rotated += 1

    if moved > 0 or rotated > 0:
        debug_apply_authored_scene_payload(controller, authored_copy)
    return {
        "ok": moved > 0 or rotated > 0 or True,
        "moved": moved, "rotated": rotated, "skipped": skipped,
        "axis": ax, "about": ab, "include_rotation": inc_rot,
    }


# ---------------------------------------------------------------------------
# Selection: Group / Ungroup
# ---------------------------------------------------------------------------

_GROUP_VALID_ABOUT = frozenset({"group", "primary"})


def _is_group_entity(ent: Dict[str, Any]) -> bool:
    """Return True if *ent* is a logical group container."""
    if ent.get("is_group") is True:
        return True
    tags = ent.get("tags")
    if isinstance(tags, list) and any(isinstance(t, str) and t.strip().lower() == "group" for t in tags):
        return True
    return False


def _next_group_id(used_ids: set[str]) -> str:
    """Return the next deterministic ``group_NNN`` id not in *used_ids*."""
    k = 1
    while True:
        candidate = f"group_{k}"
        if candidate not in used_ids:
            return candidate
        k += 1


def _next_group_name(entities: list[Dict[str, Any]], base: str) -> str:
    """Return ``{base}_NNN`` with the next available number (width=3)."""
    import re  # noqa: PLC0415

    pattern = re.compile(rf"^{re.escape(base)}_(\d+)$", re.IGNORECASE)
    max_n = 0
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        name = ent.get("name")
        if not isinstance(name, str):
            continue
        m = pattern.match(name.strip())
        if m:
            n = int(m.group(1))
            if n > max_n:
                max_n = n
    return f"{base}_{max_n + 1:03d}"


def debug_group_selection(
    controller: "SceneController",
    entity_ids: list[str],
    name_base: str = "Group",
    about: str = "group",
    primary_id: str = "",
) -> dict:
    """Debug-only: create a logical group container for selected entities.

    A new **group entity** is inserted into the scene with ``is_group=True``
    and ``tags=["group"]``.  Each participating member gets a ``group_id``
    field pointing at the new group entity's id.

    *about* controls the group entity's position:
        ``"group"``  → centroid of participating entity positions.
        ``"primary"`` → primary entity's position (fail if missing).

    Returns ``{ok, group_id, group_name, members, linked, skipped}``.
    """
    from ...entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

    ab = str(about or "group").strip().lower()
    base = str(name_base or "Group").strip() or "Group"

    fail: dict = {
        "ok": False, "group_id": "", "group_name": "",
        "members": [], "linked": 0, "skipped": 0,
    }

    if ab not in _GROUP_VALID_ABOUT:
        return fail

    sorted_ids = _sorted_dedup_ids(entity_ids)
    if not sorted_ids:
        return fail

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return fail
    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)
    index = _build_entity_index(entities)

    # Collect participants (have position, not player, not already grouped).
    participants: list[tuple[str, dict]] = []
    skipped = 0
    for eid in sorted_ids:
        ent = index.get(eid)
        if not isinstance(ent, dict):
            skipped += 1
            continue
        if is_player_entity(ent):
            skipped += 1
            continue
        if "x" not in ent or "y" not in ent:
            skipped += 1
            continue
        if _is_group_entity(ent):
            skipped += 1
            continue
        existing_gid = ent.get("group_id")
        if isinstance(existing_gid, str) and existing_gid.strip():
            # Already belongs to a group — refuse nested grouping.
            return fail
        participants.append((eid, ent))

    if len(participants) < 2:
        return fail

    # Determine pivot.
    if ab == "primary":
        pid = str(primary_id or "").strip()
        if not pid:
            return fail
        pent = index.get(pid)
        if not isinstance(pent, dict) or "x" not in pent or "y" not in pent:
            return fail
        pivot = (float(pent["x"]), float(pent["y"]))
    else:
        xs = [float(ent["x"]) for _eid, ent in participants]
        ys = [float(ent["y"]) for _eid, ent in participants]
        pivot = (sum(xs) / len(xs), sum(ys) / len(ys))

    # Build used-id set for collision avoidance.
    used_ids = _build_used_id_set(entities)

    group_id = _next_group_id(used_ids)
    group_name = _next_group_name(entities, base)

    # Create group entity.
    group_entity: Dict[str, Any] = {
        "id": group_id,
        "name": group_name,
        "x": pivot[0],
        "y": pivot[1],
        "tags": ["group"],
        "is_group": True,
    }
    entities.append(group_entity)

    # Link members.
    linked = 0
    member_ids: list[str] = []
    for eid, ent in participants:
        ent["group_id"] = group_id
        linked += 1
        member_ids.append(eid)

    debug_apply_authored_scene_payload(controller, authored_copy)
    return {
        "ok": True,
        "group_id": group_id,
        "group_name": group_name,
        "members": member_ids,
        "linked": linked,
        "skipped": skipped,
    }


def debug_ungroup_selection(
    controller: "SceneController",
    entity_ids: list[str],
    mode: str = "auto",
) -> dict:
    """Debug-only: dissolve a logical group, removing membership links.

    Target-group resolution:
    1. If any selected entity **is** a group entity, use that group.
    2. Otherwise pick the lexicographically lowest ``group_id`` among
       selected members.

    All entities whose ``group_id`` matches the target are unlinked, and the
    group entity itself is deleted from the scene.

    Returns ``{ok, group_id, unlinked, deleted_group, skipped}``.
    """
    from ...entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

    fail: dict = {
        "ok": False, "group_id": "", "unlinked": 0,
        "deleted_group": False, "skipped": 0,
    }

    sorted_ids = _sorted_dedup_ids(entity_ids)
    if not sorted_ids:
        return fail

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return fail
    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)
    index = _build_entity_index(entities)

    # --- Determine target group_id ---
    target_group_id = ""
    skipped = 0

    # Pass 1: check if any selected entity *is* a group entity.
    for eid in sorted_ids:
        ent = index.get(eid)
        if not isinstance(ent, dict):
            skipped += 1
            continue
        if is_player_entity(ent):
            skipped += 1
            continue
        if _is_group_entity(ent):
            target_group_id = str(ent.get("id", "")).strip()
            break

    # Pass 2: fallback to lowest group_id among selected members.
    if not target_group_id:
        candidate_gids: list[str] = []
        for eid in sorted_ids:
            ent = index.get(eid)
            if not isinstance(ent, dict):
                continue
            gid = ent.get("group_id")
            if isinstance(gid, str) and gid.strip():
                candidate_gids.append(gid.strip())
        if candidate_gids:
            target_group_id = sorted(set(candidate_gids))[0]

    if not target_group_id:
        return fail

    # --- Unlink all members with this group_id ---
    unlinked = 0
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        gid = ent.get("group_id")
        if isinstance(gid, str) and gid.strip() == target_group_id:
            del ent["group_id"]
            unlinked += 1

    # --- Delete the group entity ---
    deleted_group = False
    before_len = len(entities)
    entities[:] = [
        e for e in entities
        if not (isinstance(e, dict) and str(e.get("id", "")).strip() == target_group_id)
    ]
    if len(entities) < before_len:
        deleted_group = True

    if unlinked > 0 or deleted_group:
        debug_apply_authored_scene_payload(controller, authored_copy)

    return {
        "ok": unlinked > 0 or deleted_group,
        "group_id": target_group_id,
        "unlinked": unlinked,
        "deleted_group": deleted_group,
        "skipped": skipped,
    }


# ---------------------------------------------------------------------------
# Selection: Duplicate to Grid
# ---------------------------------------------------------------------------

_DUPLICATE_GRID_VALID_ORIGINS = frozenset({"selection", "group"})
_DUPLICATE_GRID_VALID_NAME_MODES = frozenset({"none", "numbered"})


def debug_duplicate_to_grid(
    controller: "SceneController",
    entity_ids: list[str],
    rows: int = 1,
    cols: int = 1,
    dx: float = 0.0,
    dy: float = 0.0,
    origin: str = "selection",
    include_original: bool = True,
    name_mode: str = "none",
) -> dict:
    """Debug-only: duplicate selected entities into an NxM grid.

    For each grid cell ``(r, c)`` in row-major order the offset is
    ``(c * dx, r * dy)``.  If *include_original* is True the ``(0, 0)``
    cell is skipped (the originals already occupy that position).

    *origin* controls base positions:
        ``"selection"`` — each entity's own position.
        ``"group"``     — group centroid (preserves relative offsets).

    *name_mode*:
        ``"none"``      — duplicates keep the cloned name.
        ``"numbered"``  — duplicates get ``_r{row}_c{col}`` suffix.

    Returns ``{ok, created, skipped, rows, cols, dx, dy,
    include_original, name_mode}``.
    """
    from ...entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

    ori = str(origin or "selection").strip().lower()
    nm = str(name_mode or "none").strip().lower()

    fail: dict = {
        "ok": False, "created": 0, "skipped": 0,
        "rows": int(rows), "cols": int(cols),
        "dx": float(dx), "dy": float(dy),
        "include_original": bool(include_original),
        "name_mode": nm,
    }

    try:
        r_count = int(rows)
        c_count = int(cols)
    except (TypeError, ValueError):
        return fail
    if r_count < 1 or c_count < 1:
        return fail
    if ori not in _DUPLICATE_GRID_VALID_ORIGINS:
        return fail
    if nm not in _DUPLICATE_GRID_VALID_NAME_MODES:
        return fail

    sorted_ids = _sorted_dedup_ids(entity_ids)
    if not sorted_ids:
        return fail

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return fail
    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)
    index = _build_entity_index(entities)

    # Collect participants (have position, not player).
    participants: list[tuple[str, dict]] = []
    skipped = 0
    for eid in sorted_ids:
        ent = index.get(eid)
        if not isinstance(ent, dict):
            skipped += 1
            continue
        if is_player_entity(ent):
            skipped += 1
            continue
        if "x" not in ent or "y" not in ent:
            skipped += 1
            continue
        participants.append((eid, ent))

    if not participants:
        return {
            "ok": True, "created": 0, "skipped": skipped,
            "rows": r_count, "cols": c_count,
            "dx": float(dx), "dy": float(dy),
            "include_original": bool(include_original),
            "name_mode": nm,
        }

    # If rows==1 cols==1 and include_original -> nothing to create.
    if r_count == 1 and c_count == 1 and include_original:
        return {
            "ok": True, "created": 0, "skipped": skipped,
            "rows": r_count, "cols": c_count,
            "dx": float(dx), "dy": float(dy),
            "include_original": bool(include_original),
            "name_mode": nm,
        }

    # Build used-id set.
    used_ids = _build_used_id_set(entities)

    created = 0

    # Row-major iteration.
    for r in range(r_count):
        for c in range(c_count):
            if include_original and r == 0 and c == 0:
                continue

            cell_dx = float(c) * float(dx)
            cell_dy = float(r) * float(dy)

            for orig_id, orig_ent in participants:
                candidate = _next_unique_dup_id(orig_id, used_ids)

                clone: Dict[str, Any] = copy.deepcopy(orig_ent)
                clone["id"] = candidate

                try:
                    clone["x"] = float(orig_ent["x"]) + cell_dx
                except (TypeError, ValueError):
                    clone["x"] = cell_dx
                try:
                    clone["y"] = float(orig_ent["y"]) + cell_dy
                except (TypeError, ValueError):
                    clone["y"] = cell_dy

                if nm == "numbered":
                    orig_name = orig_ent.get("name")
                    if isinstance(orig_name, str) and orig_name.strip():
                        clone["name"] = f"{orig_name.strip()}_r{r}_c{c}"

                entities.append(clone)
                created += 1

    if created > 0:
        debug_apply_authored_scene_payload(controller, authored_copy)

    return {
        "ok": True,
        "created": created,
        "skipped": skipped,
        "rows": r_count,
        "cols": c_count,
        "dx": float(dx),
        "dy": float(dy),
        "include_original": bool(include_original),
        "name_mode": nm,
    }


# ---------------------------------------------------------------------------
# Selection: Duplicate Along Path
# ---------------------------------------------------------------------------

_DUP_PATH_VALID_NAME_MODES = frozenset({"none", "numbered"})


def debug_duplicate_along_path(
    controller: "SceneController",
    entity_ids: list[str],
    from_x: float,
    from_y: float,
    to_x: float,
    to_y: float,
    count: int,
    include_original: bool = True,
    origin: str = "selection",
    name_mode: str = "none",
    orient: bool = False,
) -> dict:
    """Debug-only: duplicate selected entities along a line segment.

    Computes *count* points along ``(from_x, from_y)`` → ``(to_x, to_y)``
    using linear interpolation.  For each point, each selected entity is
    duplicated at ``base_position + (point_i - from)``.

    If *include_original* the ``i=0`` point is skipped (originals stay).

    *name_mode* ``"numbered"`` appends ``_p{idx:03d}`` to duplicate names.

    *orient* if True sets duplicate ``rotation`` to the segment angle
    (degrees, clockwise-positive from +X).

    Returns ``{ok, created, skipped, count, from, to,
    include_original, name_mode, orient}``.
    """
    import math  # noqa: PLC0415

    from ...entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

    nm = str(name_mode or "none").strip().lower()

    fail: dict = {
        "ok": False, "created": 0, "skipped": 0,
        "count": 0, "from": [float(from_x), float(from_y)],
        "to": [float(to_x), float(to_y)],
        "include_original": bool(include_original),
        "name_mode": nm, "orient": bool(orient),
    }

    try:
        n = int(count)
    except (TypeError, ValueError):
        return fail
    if n < 1:
        return fail
    if nm not in _DUP_PATH_VALID_NAME_MODES:
        return fail

    fx, fy = float(from_x), float(from_y)
    tx, ty = float(to_x), float(to_y)

    sorted_ids = _sorted_dedup_ids(entity_ids)
    if not sorted_ids:
        return fail

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return fail
    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)
    index = _build_entity_index(entities)

    # Collect participants.
    participants: list[tuple[str, dict]] = []
    skipped = 0
    for eid in sorted_ids:
        ent = index.get(eid)
        if not isinstance(ent, dict):
            skipped += 1
            continue
        if is_player_entity(ent):
            skipped += 1
            continue
        if "x" not in ent or "y" not in ent:
            skipped += 1
            continue
        participants.append((eid, ent))

    if not participants:
        return {
            "ok": True, "created": 0, "skipped": skipped,
            "count": n, "from": [fx, fy], "to": [tx, ty],
            "include_original": bool(include_original),
            "name_mode": nm, "orient": bool(orient),
        }

    # Compute segment angle for orient.
    seg_angle = 0.0
    if orient:
        seg_angle = math.degrees(math.atan2(ty - fy, tx - fx)) % 360.0

    # Build used-id set.
    used_ids = _build_used_id_set(entities)

    created = 0

    for i in range(n):
        if include_original and i == 0:
            continue

        if n == 1:
            t = 0.0
        else:
            t = float(i) / float(n - 1)

        pt_x = fx + t * (tx - fx)
        pt_y = fy + t * (ty - fy)
        offset_x = pt_x - fx
        offset_y = pt_y - fy

        for orig_id, orig_ent in participants:
            candidate = _next_unique_dup_id(orig_id, used_ids)

            clone: Dict[str, Any] = copy.deepcopy(orig_ent)
            clone["id"] = candidate

            try:
                clone["x"] = float(orig_ent["x"]) + offset_x
            except (TypeError, ValueError):
                clone["x"] = offset_x
            try:
                clone["y"] = float(orig_ent["y"]) + offset_y
            except (TypeError, ValueError):
                clone["y"] = offset_y

            if orient:
                clone["rotation"] = seg_angle

            if nm == "numbered":
                orig_name = orig_ent.get("name")
                if isinstance(orig_name, str) and orig_name.strip():
                    clone["name"] = f"{orig_name.strip()}_p{i:03d}"

            entities.append(clone)
            created += 1

    if created > 0:
        debug_apply_authored_scene_payload(controller, authored_copy)

    return {
        "ok": True,
        "created": created,
        "skipped": skipped,
        "count": n,
        "from": [fx, fy],
        "to": [tx, ty],
        "include_original": bool(include_original),
        "name_mode": nm,
        "orient": bool(orient),
    }


# ---------------------------------------------------------------------------
# Selection: Scatter
# ---------------------------------------------------------------------------

_SCATTER_VALID_NAME_MODES = frozenset({"none", "numbered"})
_SCATTER_VALID_SHAPES = frozenset({"circle", "rect"})
_SCATTER_VALID_CENTERS = frozenset({"group", "primary", "origin"})


def debug_scatter_selection(
    controller: "SceneController",
    entity_ids: list[str],
    n: int,
    shape: str = "circle",
    radius: float = 64.0,
    width: float = 128.0,
    height: float = 128.0,
    center: str = "group",
    seed: int = 0,
    jitter_rot_deg: float = 0.0,
    snap_step: int | None = None,
    include_original: bool = True,
    name_mode: str = "none",
) -> dict:
    """Debug-only: scatter-duplicate selected entities inside a shape.

    Generates *n* scatter points using a deterministic RNG seeded with *seed*.
    Each selected entity is duplicated at each point, preserving the
    selection's internal shape (relative offsets to centroid).

    Returns ``{ok, created, skipped, n, shape, seed, include_original}``.
    """
    import math   # noqa: PLC0415
    import random  # noqa: PLC0415

    from ...entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

    nm = str(name_mode or "none").strip().lower()
    sh = str(shape or "circle").strip().lower()
    ctr = str(center or "group").strip().lower()

    fail: dict = {
        "ok": False, "created": 0, "skipped": 0,
        "n": 0, "shape": sh, "seed": int(seed),
        "include_original": bool(include_original),
    }

    # Validate n.
    try:
        n_val = int(n)
    except (TypeError, ValueError):
        return fail
    if n_val < 1:
        return fail

    # Validate enums.
    if nm not in _SCATTER_VALID_NAME_MODES:
        return fail
    if sh not in _SCATTER_VALID_SHAPES:
        return fail
    if ctr not in _SCATTER_VALID_CENTERS:
        return fail

    # Validate shape dimensions.
    try:
        f_radius = float(radius)
        f_width = float(width)
        f_height = float(height)
    except (TypeError, ValueError):
        return fail
    if sh == "circle" and f_radius <= 0:
        return fail
    if sh == "rect" and (f_width <= 0 or f_height <= 0):
        return fail

    # Collect sorted, deduplicated ids.
    sorted_ids = _sorted_dedup_ids(entity_ids)
    if not sorted_ids:
        return fail

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return fail
    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)
    index = _build_entity_index(entities)

    # Collect participants.
    participants: list[tuple[str, dict]] = []
    skipped = 0
    for eid in sorted_ids:
        ent = index.get(eid)
        if not isinstance(ent, dict):
            skipped += 1
            continue
        if is_player_entity(ent):
            skipped += 1
            continue
        if "x" not in ent or "y" not in ent:
            skipped += 1
            continue
        participants.append((eid, ent))

    if not participants:
        return {
            "ok": True, "created": 0, "skipped": skipped,
            "n": n_val, "shape": sh, "seed": int(seed),
            "include_original": bool(include_original),
        }

    # Compute pivot.
    if ctr == "origin":
        pivot_x, pivot_y = 0.0, 0.0
    elif ctr == "primary":
        # Need primary id — use first from sorted_ids that is a participant.
        # Caller should ensure primary is in the list; we use the first participant.
        # Actually, use entity_ids[0] if present, or fail.
        primary_id: str | None = None
        for eid in (entity_ids or []):
            if isinstance(eid, str) and eid.strip():
                primary_id = eid.strip()
                break
        if primary_id is None:
            return fail
        pent = index.get(primary_id)
        if not isinstance(pent, dict) or "x" not in pent or "y" not in pent:
            return fail
        try:
            pivot_x = float(pent["x"])
            pivot_y = float(pent["y"])
        except (TypeError, ValueError):
            return fail
    else:
        # group centroid
        sum_x = 0.0
        sum_y = 0.0
        for _eid, ent in participants:
            try:
                sum_x += float(ent["x"])
                sum_y += float(ent["y"])
            except (TypeError, ValueError):
                pass
        pivot_x = sum_x / len(participants)
        pivot_y = sum_y / len(participants)

    # Build used-id set.
    used_ids = _build_used_id_set(entities)

    # Deterministic RNG.
    rng = random.Random(seed)

    # Pre-generate all scatter offsets so ordering is deterministic.
    offsets: list[tuple[float, float]] = []
    for _i in range(n_val):
        if sh == "circle":
            a = rng.uniform(0.0, 2.0 * math.pi)
            u = rng.uniform(0.0, 1.0)
            r = f_radius * math.sqrt(u)
            offsets.append((r * math.cos(a), r * math.sin(a)))
        else:
            ox = rng.uniform(-f_width / 2.0, f_width / 2.0)
            oy = rng.uniform(-f_height / 2.0, f_height / 2.0)
            offsets.append((ox, oy))

    # Pre-generate rotation jitter.
    rot_jitters: list[float] = []
    for _i in range(n_val):
        if jitter_rot_deg > 0:
            rot_jitters.append(rng.uniform(-jitter_rot_deg, jitter_rot_deg))
        else:
            rot_jitters.append(0.0)

    created = 0

    for i in range(n_val):
        if include_original and i == 0:
            continue

        scatter_x = pivot_x + offsets[i][0]
        scatter_y = pivot_y + offsets[i][1]

        for orig_id, orig_ent in participants:
            # Relative offset from centroid.
            try:
                rel_x = float(orig_ent["x"]) - pivot_x
                rel_y = float(orig_ent["y"]) - pivot_y
            except (TypeError, ValueError):
                rel_x, rel_y = 0.0, 0.0

            target_x = scatter_x + rel_x
            target_y = scatter_y + rel_y

            # Snap.
            if snap_step is not None:
                try:
                    ss = int(snap_step)
                    if ss > 0:
                        target_x = _snap_value(target_x, ss, "nearest")
                        target_y = _snap_value(target_y, ss, "nearest")
                except (TypeError, ValueError):
                    pass

            # Unique ID.
            candidate = _next_unique_dup_id(orig_id, used_ids)

            clone: Dict[str, Any] = copy.deepcopy(orig_ent)
            clone["id"] = candidate
            clone["x"] = target_x
            clone["y"] = target_y

            # Rotation jitter.
            jitter_val = rot_jitters[i]
            if jitter_rot_deg > 0:
                try:
                    cur_rot = float(orig_ent.get("rotation", 0.0))
                except (TypeError, ValueError):
                    cur_rot = 0.0
                clone["rotation"] = (cur_rot + jitter_val) % 360.0

            # Naming.
            if nm == "numbered":
                orig_name = orig_ent.get("name")
                if isinstance(orig_name, str) and orig_name.strip():
                    clone["name"] = f"{orig_name.strip()}_s{i:03d}"

            entities.append(clone)
            created += 1

    if created > 0:
        debug_apply_authored_scene_payload(controller, authored_copy)

    return {
        "ok": True,
        "created": created,
        "skipped": skipped,
        "n": n_val,
        "shape": sh,
        "seed": int(seed),
        "include_original": bool(include_original),
    }


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
    from ...entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

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
    index = _build_entity_index(entities)

    changed = 0
    skipped_player = 0
    skipped_no_behaviour = 0

    for entity_id in _sorted_dedup_ids(selected_ids):
        ent = index.get(entity_id)
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

