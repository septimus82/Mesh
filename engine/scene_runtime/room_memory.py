"""Room memory: what stays changed in a room after the player leaves it.

A room is rebuilt from its authored file every time it loads. Without this, a coin picked up, a chest
emptied or an enemy defeated was back as soon as the player left and returned, or loaded a save made
in that room.

What persists: the authored objects (those with an ``id``) that were in the room when it loaded and
were removed during play (collected, destroyed, defeated). They are recorded per room in the game
state's variables (``room_memory``), so saves carry them with everything else, and they are left out
when the room loads again. A new game (a new game state) starts with every room as authored.

What does not: objects spawned at runtime (projectiles, effects), positions of things that move, and
anything a flag already controls (flags persist on their own).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

VAR = "room_memory"


def _state(window: Any) -> Any:
    return getattr(window, "game_state_controller", None)


def _memory(window: Any) -> dict[str, Any]:
    state = _state(window)
    value = state.get_var(VAR, None) if state is not None else None
    return value if isinstance(value, dict) else {}


def room_key(path: str | None) -> str:
    return str(path or "").replace("\\", "/").strip()


def removed_ids(window: Any, room: str) -> set[str]:
    entry = _memory(window).get(room_key(room))
    removed = entry.get("removed") if isinstance(entry, dict) else None
    return {str(x) for x in removed} if isinstance(removed, list) else set()


def spawned_ids(entities: list[Any]) -> set[str]:
    return {str(e["id"]) for e in entities if isinstance(e, dict) and isinstance(e.get("id"), str) and e["id"]}


def is_save_slot(window: Any, path: str) -> bool:
    """Whether ``path`` is a save file (loading one replaces the game state, room memory included)."""
    manager = getattr(window, "save_manager", None)
    folders = [getattr(manager, "save_dir", None), getattr(manager, "legacy_dir", None)]  # (H9: an older export's too)
    parent = Path(path).resolve().parent
    return any(folder is not None and parent == Path(folder).resolve() for folder in folders)


def remember_removed(controller: Any) -> None:
    """Record which of this room's authored objects are gone (call before leaving the room or saving)."""
    room = room_key(getattr(controller, "room_path", None))
    spawned = getattr(controller, "_room_spawned_ids", None)
    state = _state(getattr(controller, "window", None))
    if not room or not spawned or state is None:
        return
    alive = set()
    for sprite in controller.all_sprites:
        data = getattr(sprite, "mesh_entity_data", None)
        if isinstance(data, dict) and isinstance(data.get("id"), str):
            alive.add(data["id"])
    gone = (set(spawned) - alive) | removed_ids(controller.window, room)
    if not gone:
        return
    memory = dict(_memory(controller.window))
    memory[room] = {"removed": sorted(gone)}
    state.set_var(VAR, memory)

