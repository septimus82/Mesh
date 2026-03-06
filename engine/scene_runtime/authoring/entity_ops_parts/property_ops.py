# ruff: noqa
# mypy: ignore-errors
from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

from ._shared import _build_entity_index, _sorted_dedup_ids, debug_apply_authored_scene_payload, get_authored_scene_payload

if TYPE_CHECKING:
    from ....scene_controller import SceneController
def debug_set_prefab_id(controller: "SceneController", selected_ids: list[str], prefab_id: str) -> tuple[int, int]:
    """
    Debug-only: set prefab_id for all selected authored entities (skips player).

    Operates on the authored payload only and reapplies it (no disk I/O).
    Returns (changed_count, skipped_player_count).
    """
    from ....entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

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
    from ....entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

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
    from ....entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

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
    from ....entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

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
    from ....entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

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
    from ....entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

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
    from ....entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

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
    from ....entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

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
    from ....entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

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
