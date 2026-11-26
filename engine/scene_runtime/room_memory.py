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

Facts (S1 4.1, D6): what already happened to an authored object (a door unlocked, a chest looted), which its
behaviours would otherwise forget on re-entry. A behaviour declares them (``Behaviour.FACT_FIELDS``) and writes one
when it changes (``Behaviour.record_fact``): straight into this room's entry, so a save made at any time carries it::

    room_memory[room]["facts"][entity_id][behaviour class name][field] = value

The factory applies an object's facts as its behaviours are built (``bind_facts``: room entry, re-entry, a loaded
save's room), before their first update. No record means "as authored", so saves made before facts load unchanged.
Facts are keyed by the object's authored ``id``: renaming the id (or the behaviour class, or the field) orphans them,
and the object is as authored again. An object without an id in its room's file (spawned at runtime), and objects
sharing one id in a room (their facts would cross-apply; warned), get none. Like removed objects, facts belong to the
game session that loaded the room.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from engine.log_utils import get_logger

logger = get_logger(__name__)

VAR = "room_memory"
FACTS = "facts"


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


def session(window: Any) -> Any:
    """The game session now: its ``GameState``, which ``GameStateController.replace_state`` replaces for a new game
    (New Game, Studio's Play and Stop)."""
    return getattr(_state(window), "state", None)


def remember_removed(controller: Any) -> None:
    """Record which of this room's authored objects are gone (call before leaving the room or saving).

    Only into the game session that loaded the room: after a new game began (New Game, Studio's Play or Stop), what
    was collected in the room the old game was in isn't the new game's."""
    room = room_key(getattr(controller, "room_path", None))
    spawned = getattr(controller, "_room_spawned_ids", None)
    state = _state(getattr(controller, "window", None))
    if not room or not spawned or state is None:
        return
    loaded_in = getattr(controller, "_room_session", None)
    if loaded_in is not None and loaded_in is not session(controller.window):
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
    entry = memory.get(room)
    memory[room] = {**(entry if isinstance(entry, dict) else {}), "removed": sorted(gone)}  # (its facts kept)
    state.set_var(VAR, memory)


# ----------------------------------------------------------------------------------------------------------- facts


def fact_ids(entities: list[Any]) -> set[str]:
    """The ids in a room's file that may carry facts: those exactly one object has (warned for the others)."""
    counts: dict[str, int] = {}
    for e in entities:
        if isinstance(e, dict) and isinstance(e.get("id"), str) and e["id"]:
            counts[e["id"]] = counts.get(e["id"], 0) + 1
    shared = sorted(i for i, n in counts.items() if n > 1)
    if shared:
        logger.warning("room memory: objects share the id(s) %s in one room; they get no facts (fix the ids)",
                       ", ".join(shared))
    return {i for i, n in counts.items() if n == 1}


def bind_facts(controller: Any, sprite: Any, behaviour: Any) -> None:
    """Bind a newly built behaviour to its object's facts in this room and apply those recorded (the factory calls
    this before the behaviour's first update). Unbound (no facts written or applied): no declared facts, no room, or
    an object without a unique authored id in the room's file."""
    fields = tuple(getattr(behaviour, "FACT_FIELDS", ()) or ())
    if not fields:
        return
    room = room_key(getattr(controller, "room_path", None))
    entity_id = getattr(sprite, "mesh_id", None)
    if not room or not isinstance(entity_id, str) or entity_id not in (getattr(controller, "_room_fact_ids", None) or ()):
        behaviour._mesh_fact_key = None
        return
    behaviour._mesh_fact_key = (room, entity_id, getattr(controller, "_room_session", None))
    entry = _memory(getattr(controller, "window", None)).get(room)
    facts = entry.get(FACTS) if isinstance(entry, dict) else None
    own = facts.get(entity_id) if isinstance(facts, dict) else None
    recorded = own.get(type(behaviour).__name__) if isinstance(own, dict) else None
    if isinstance(recorded, dict):
        known = {k: v for k, v in recorded.items() if k in fields}  # (a renamed field's old record: orphaned)
        if known:
            behaviour.apply_facts(known)


def record_fact(behaviour: Any, field: str, value: Any) -> bool:
    """Write one fact of ``behaviour`` into room memory now. False (nothing written) for an unbound behaviour (said
    once, at debug level) or a room loaded by an earlier game session."""
    try:
        json.dumps(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"fact {field!r} must be JSON data (saves carry it): {exc}") from None
    at = getattr(behaviour, "_mesh_fact_key", None)
    window = getattr(behaviour, "window", None)
    state = _state(window)
    if at is None or state is None:
        if not getattr(behaviour, "_mesh_fact_unbound_said", False):
            behaviour._mesh_fact_unbound_said = True
            logger.debug("room memory: %s on %r has no authored id of its own in this room; its facts are not kept",
                         type(behaviour).__name__, getattr(getattr(behaviour, "entity", None), "mesh_name", None))
        return False
    room, entity_id, loaded_in = at
    if loaded_in is not None and loaded_in is not session(window):
        return False
    memory = dict(_memory(window))
    entry = memory.get(room)
    entry = dict(entry) if isinstance(entry, dict) else {}
    facts = entry.get(FACTS)
    facts = dict(facts) if isinstance(facts, dict) else {}
    own = facts.get(entity_id)
    own = dict(own) if isinstance(own, dict) else {}
    kind = own.get(type(behaviour).__name__)
    kind = dict(kind) if isinstance(kind, dict) else {}
    kind[field] = value
    own[type(behaviour).__name__] = kind
    facts[entity_id] = own
    entry[FACTS] = facts
    memory[room] = entry
    state.set_var(VAR, memory)
    return True

