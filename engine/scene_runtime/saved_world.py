"""The saved world (#390): a save restores the player's progress; the game's authored world stays authoritative.

A save slot is a room snapshot plus the game's state. Until #390 the snapshot carried a deep copy of the room as it
was authored when it loaded: its settings (an HD-2D room's sculpted ground and scattered decoration, its lights,
weather, wind, animation), its map and its layers. Loading the save replayed that copy, so a room re-sculpted,
re-scattered or re-lit after the save never reached it, and each slot of a decorated room weighed hundreds of KB.
None of that copy is changed by play: only the camera's zoom (in ``settings.camera``), the objects and the game
state are (``engine.scene_runtime.persistence.build_scene_snapshot``).

**Loading a save** (``compose``): the room the save was made in (``meta.scene_path``) is read as it is now, and
everything authored comes from it: settings, map, layers, lights, backgrounds. From the save come what play changes:

- the camera's zoom;
- the objects, each as play left it (its place, its behaviours; their inner states, a door's or a chest's, are the
  save's ``saved_entities``, restored by id as before);
- the game state (flags, variables, quests; with them, room memory: the authored objects play removed).

The objects are reconciled with the room by ``id``:

- an object the room has and the save doesn't (added since) appears, unless play removed it (room memory);
- an object that came from the room when the game was saved (``meta.room_entity_ids``) and that the room no longer
  has (deleted since) is left out; saves made before #390 don't record it: theirs are all kept, as they were;
- an object spawned during play (not from the room) is kept;
- an object without an ``id`` is kept as saved.

A save whose room can't be read any more (renamed, deleted) loads from what it has, with a warning.

**Saving** (``slim``): what play doesn't change isn't written: the room's settings (only the camera's zoom), its
map, lights, occluders and backgrounds; ``meta.room_entity_ids`` records the objects that came from the room. Saves
made before #390 still load (they are composed the same way, their own copy of the room ignored). The trade-off: a
new save whose room can't be read any more loads its objects and progress without the room's look (an older save
still has its own copy to fall back on).

Not yet (a later step): an object's authored fields (its dialogue, its picture) edited after a save. The object's
saved data mixes them with what play changed (behaviour settings), so they stay as saved; a per-field split is the
next step.
"""

from __future__ import annotations

import copy
from typing import Any

from engine.scene_runtime.room_memory import room_key

ROOM_IDS = "room_entity_ids"


def _zoom(scene: dict[str, Any]) -> Any:
    settings = scene.get("settings")
    camera = settings.get("camera") if isinstance(settings, dict) else None
    return camera.get("zoom") if isinstance(camera, dict) else None


AUTHORED = ("tilemap", "lights", "occluders", "background_layers", "foreground_layers")  # (and settings: below)


def slim(snapshot: dict[str, Any]) -> None:
    """A new save's room part: what play doesn't change left out: the room's settings (only the camera's zoom kept),
    its map, lights, occluders and backgrounds."""
    zoom = _zoom(snapshot)
    snapshot["settings"] = {"camera": {"zoom": copy.deepcopy(zoom)}} if zoom is not None else {}
    for key in AUTHORED:
        snapshot.pop(key, None)


def room_ids(controller: Any) -> list[str]:
    """The ids of the objects that came from the room when it loaded (``meta.room_entity_ids`` of a new save)."""
    return sorted(str(i) for i in (getattr(controller, "_room_spawned_ids", None) or ()) if isinstance(i, str) and i)


def _removed(save: dict[str, Any], room: str) -> set[str]:
    state = save.get("state")
    values = (state.get("variables") or state.get("values")) if isinstance(state, dict) else None
    memory = values.get("room_memory") if isinstance(values, dict) else None
    entry = memory.get(room_key(room)) if isinstance(memory, dict) else None
    removed = entry.get("removed") if isinstance(entry, dict) else None
    return {str(x) for x in removed} if isinstance(removed, list) else set()


def _id(entity: Any) -> str | None:
    value = entity.get("id") if isinstance(entity, dict) else None
    return value if isinstance(value, str) and value else None


def compose(save: dict[str, Any], room: dict[str, Any], room_path: str) -> dict[str, Any]:
    """The scene to load for ``save`` (a whole save slot), its room ``room`` (that room's file, as it is now)."""
    out = copy.deepcopy(room)
    raw_meta = save.get("meta")
    meta: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
    at_save = meta.get(ROOM_IDS)
    from_room_then = {str(i) for i in at_save} if isinstance(at_save, list) else None
    in_room_now = {i for i in map(_id, room.get("entities") or []) if i}
    saved = [e for e in (save.get("entities") or []) if isinstance(e, dict)]
    kept = [copy.deepcopy(e) for e in saved
            if not (from_room_then is not None and _id(e) in from_room_then and _id(e) not in in_room_now)]
    have = {i for i in map(_id, kept) if i}
    removed = _removed(save, room_path)
    added = [copy.deepcopy(e) for e in room.get("entities") or []
             if _id(e) and _id(e) not in have and _id(e) not in removed]
    out["entities"] = kept + added
    if "state" in save:
        out["state"] = copy.deepcopy(save["state"])
    zoom = _zoom(save)
    if zoom is not None:
        settings = out.setdefault("settings", {})
        if isinstance(settings, dict):
            camera = settings.setdefault("camera", {})
            if isinstance(camera, dict):
                camera["zoom"] = copy.deepcopy(zoom)
    return out
