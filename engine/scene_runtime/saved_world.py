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
- where play left each object (``PLAY_OWNED``: its place and the floor it stands on); its inner state (a door's, a
  chest's, a quest object's) is the save's ``saved_entities``, restored by id as before. Everything else about an
  object the room still has (its dialogue, its picture, its behaviours) is the room's, as authored now;
- the game state (flags, variables, quests; with them, room memory: the authored objects play removed).

The objects are reconciled with the room by ``id``:

- an object the room has and the save doesn't (added since) appears, unless play removed it (room memory);
- an object that came from the room when the game was saved (``meta.room_entity_ids``) and that the room no longer
  has (deleted since) is left out; saves made before #390 don't record it: theirs are all kept, as they were;
- an object spawned during play (not from the room) is kept;
- an object without an ``id`` is kept as saved.

A save whose room can't be read any more (renamed, deleted): a save from before #390 loads its own copy of the room,
as it always did; a newer save has no copy, so it is refused (``needs_its_room``), clearly and before anything is
applied: the game stays as it was, and the save file is kept unchanged for when the room is back.

**Saving** (``slim``): what play doesn't change isn't written: the room's settings (only the camera's zoom), its
map, lights, occluders and backgrounds; ``meta.room_entity_ids`` records the objects that came from the room. Saves
made before #390 still load (they are composed the same way, their own copy of the room ignored). Loading never
rewrites a save file.

The trade-off: an object the creator moves after a save stays, in that save, where the save found it (a save can't
tell a creator's move from play's).
"""

from __future__ import annotations

import copy
from typing import Any

from engine.log_utils import get_logger
from engine.scene_runtime.room_memory import is_player, room_key

logger = get_logger(__name__)

ROOM_IDS = "room_entity_ids"
MUSIC = "music"  # meta: the music playing when saved ({"path", "volume"}; path None: silence)
PLAY_OWNED = ("x", "y", "elevation")  # (what play changes on an object the room has; the rest is the room's)


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


def _idless_key(entity: dict[str, Any]) -> tuple[Any, Any]:
    # A prefab's object is told by its prefab alone: loading fills in the prefab's name, which the room file lacks.
    prefab = entity.get("prefab_id")
    return (None, prefab) if prefab else (entity.get("name"), None)


def room_idless(room_entities: Any) -> dict[tuple[Any, Any], int]:
    """How many id-less objects (by name and prefab) the room file has: what a loaded save's own id-less objects are
    told apart from by (never saved: the loader hands it to the controller)."""
    counts: dict[tuple[Any, Any], int] = {}
    for e in room_entities or []:
        if isinstance(e, dict) and not _id(e):
            counts[_idless_key(e)] = counts.get(_idless_key(e), 0) + 1
    return counts


def carried(entities: list[dict[str, Any]], from_room: dict[tuple[Any, Any], int]) -> set[int]:
    """B-09: the indexes of the id-less ``entities`` that are provably not the room's: the room file has no id-less
    object with their name and prefab, so they were spawned during play (a projectile) and only a save carries them.
    A snapshot drops one whose sprite is gone. Where the room has some of that name and prefab, a save's id-less
    objects can't be told from the room's (not by list order), so none is dropped (warned), as before B-09."""
    found: dict[tuple[Any, Any], int] = {}
    for e in entities:
        if not _id(e):
            found[_idless_key(e)] = found.get(_idless_key(e), 0) + 1
    for key, n in found.items():
        if 0 < from_room.get(key, 0) < n:
            logger.warning("saved world: %d id-less objects named %r (prefab %r), the room has %d; they can't be told "
                           "apart, so an expired one is kept", n, key[0], key[1], from_room[key])
    return {i for i, e in enumerate(entities) if not _id(e) and from_room.get(_idless_key(e), 0) == 0}


def needs_its_room(save: dict[str, Any]) -> bool:
    """True for a save made since #390: it has no copy of its room, so it can't be loaded without it."""
    meta = save.get("meta")
    return isinstance(meta, dict) and ROOM_IDS in meta


def _where_play_left(authored: dict[str, Any], saved: dict[str, Any]) -> dict[str, Any]:
    """The room's object as authored now, standing where the save left it."""
    out = copy.deepcopy(authored)
    for key in PLAY_OWNED:
        if key in saved:
            out[key] = copy.deepcopy(saved[key])
    return out


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
    authored: dict[str, list[dict[str, Any]]] = {}
    for room_entity in room.get("entities") or []:
        if i := _id(room_entity):
            authored.setdefault(i, []).append(room_entity)
    seen: dict[str, int] = {}  # the k-th saved entity with an id pairs with the k-th authored entry with it
    paired: list[dict[str, Any]] = []
    for e in kept:
        i = _id(e)
        k = seen.get(i, 0) if i else 0
        if i:
            seen[i] = k + 1
        paired.append(_where_play_left(authored[i][k], e) if i in authored and k < len(authored[i]) else e)
    kept = paired
    for i, n in seen.items():
        if i in authored and n != len(authored[i]):
            logger.warning("saved world: %d saved objects share id %r but the room now has %d; paired in order, "
                           "the extra saved ones keep their saved fields", n, i, len(authored[i]))
    have = {i for i in map(_id, kept) if i}
    removed = _removed(save, room_path)
    added = [copy.deepcopy(e) for e in room.get("entities") or []
             if _id(e) and _id(e) not in have and (_id(e) not in removed or is_player(e))]  # (#750)
    out["entities"] = kept + added
    if "state" in save:
        out["state"] = copy.deepcopy(save["state"])
    music = meta.get(MUSIC)
    settings = out.get("settings")
    if isinstance(music, dict) and isinstance(settings, dict) and "music" not in settings:
        # A room without its own music played whatever was playing when it was entered: the save recorded that.
        path = music.get("path")
        settings["music"] = path if isinstance(path, str) and path else None
        if isinstance(music.get("volume"), (int, float)) and not isinstance(music.get("volume"), bool):
            settings["music_volume"] = float(music["volume"])
    zoom = _zoom(save)
    if zoom is not None:
        settings = out.setdefault("settings", {})
        if isinstance(settings, dict):
            camera = settings.setdefault("camera", {})
            if isinstance(camera, dict):
                camera["zoom"] = copy.deepcopy(zoom)
    return out
