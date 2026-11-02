"""What the game running in Mesh Studio is doing right now, for an AI debugging it (D1, #422).

Mesh Studio's play-test runs the real game in Studio's window. ``snapshot`` reads that game as it is, on Studio's
main thread (the live-session bridge queues every request there): the room running, where the player is, flags,
counters and other game values, quests, the events the play-test has made, and errors the engine caught and carried
on from. It only reads: no frame is advanced, no event is taken off a queue, nothing is created on the way (a
quest the game hasn't touched yet is reported "inactive", as the quest manager would make it, without making it),
nothing is saved and Studio's selection is left alone. While Studio is editing there is no game to read:
``status: "not_playing"``.

The running game is never mixed up with what the person is writing: everything read from the game is under
``scene``, ``player``, ``game_state``, ``quests``, ``events`` and ``diagnostics``; ``studio`` says what Studio has
open (the room being edited, unsaved changes), which play-testing never changes. A system the game doesn't have
reads ``{"available": false, "reason": ...}``, never an empty success.

Every value is made plain JSON (``plain``): numbers, text, lists and objects, bounded in depth, length and count;
anything else (a sprite in an event, say) is named by its entity or type, never written out. The bridge's token, the
project's absolute folder and files' contents are never part of a snapshot.

The other half, at the bottom, is what the MCP tools call: ``request_snapshot``, ``request_play`` and
``request_stop`` find the Mesh Studio that has the project open (the same verified session proposals use, and the
same refusals when there isn't one) and ask it.
"""

from __future__ import annotations

import json
import math
import numbers
import time
from pathlib import Path
from typing import Any

Doc = dict[str, Any]

EVENTS_DEFAULT = 20
EVENTS_MAX = 50  # the game's event bus keeps its last 50
DIAGNOSTICS_MAX = 20
TEXT_MAX = 200  # characters of any one text
ITEMS_MAX = 100  # entries of any one list or object (flags and counters: FLAGS_MAX)
FLAGS_MAX = 200
DEPTH_MAX = 4
BYTES_MAX = 200_000  # a whole snapshot, as JSON


def plain(value: Any, depth: int = 0, items: int = ITEMS_MAX) -> Any:
    """``value`` as bounded plain JSON: deterministic (object keys sorted), never raising, never repr-ing objects."""
    if value is None or isinstance(value, (bool, str)):
        return value if not isinstance(value, str) or len(value) <= TEXT_MAX else value[:TEXT_MAX] + "..."
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        number = float(value)
        return number if math.isfinite(number) else str(number)
    if isinstance(value, dict):
        if depth >= DEPTH_MAX:
            return {"...": f"{len(value)} entries"}
        keys = sorted(value, key=str)
        out = {str(key)[:TEXT_MAX]: plain(value[key], depth + 1) for key in keys[:items]}
        if len(keys) > items:
            out["..."] = f"{len(keys) - items} more"
        return out
    if isinstance(value, (list, tuple, set, frozenset)):
        seq = sorted(value, key=str) if isinstance(value, (set, frozenset)) else list(value)
        if depth >= DEPTH_MAX:
            return [f"... {len(seq)} items"]
        out_list = [plain(item, depth + 1) for item in seq[:items]]
        if len(seq) > items:
            out_list.append(f"... {len(seq) - items} more")
        return out_list
    name = getattr(value, "mesh_name", None) or getattr(value, "mesh_id", None)
    if isinstance(name, str) and name:
        return {"entity": name[:TEXT_MAX]}
    return f"<{type(value).__name__}>"


def _unavailable(reason: str) -> Doc:
    return {"available": False, "reason": reason}


def _relative(path: Any, root: Path | None) -> str | None:
    """A scene's path as the project names it (relative to the project folder); never another folder's full path."""
    if not path:
        return None
    candidate = Path(str(path))
    if root is not None and candidate.is_absolute():
        try:
            return candidate.resolve().relative_to(root.resolve()).as_posix()
        except (OSError, ValueError):
            return candidate.name
    return candidate.as_posix()


# --------------------------------------------------------------------- reading the running game

def _scene(window: Any, project: Any) -> Doc:
    controller = getattr(window, "scene_controller", None)
    if controller is None:
        return _unavailable("the game has no scene controller")
    root = Path(project.root) if getattr(project, "root", None) else None
    path = _relative(getattr(controller, "current_scene_path", None), root)
    if path is None:
        return _unavailable("no room is loaded")
    room = None
    for key, label, room_path in project.rooms() if hasattr(project, "rooms") else ():
        if _relative(room_path, root) == path:
            room = {"key": key, "label": label}
            break
    return {"available": True, "path": path, "room": room}


def _player(window: Any) -> Doc:
    controller = getattr(window, "scene_controller", None)
    finder = getattr(controller, "_find_player_sprite", None)
    if not callable(finder):
        return _unavailable("the game has no scene controller")
    sprite = finder()
    if sprite is None:
        return _unavailable("the running room has no player")
    x, y = getattr(sprite, "center_x", None), getattr(sprite, "center_y", None)
    return {"available": True, "id": plain(getattr(sprite, "mesh_id", None)),
            "name": plain(getattr(sprite, "mesh_name", None)), "tag": plain(getattr(sprite, "mesh_tag", None)),
            "x": plain(x), "y": plain(y), "units": "pixels"}


def _game_state(window: Any) -> Doc:
    controller = getattr(window, "game_state_controller", None)
    state = getattr(controller, "state", None)
    if state is None:
        return _unavailable("the game has no game state")
    values = getattr(state, "values", None) or {}
    return {"available": True,
            "flags": plain(dict(getattr(state, "flags", None) or {}), items=FLAGS_MAX),
            "counters": plain(dict(getattr(state, "counters", None) or {}), items=FLAGS_MAX),
            # (the game's variables: GameState keeps ``values`` and ``variables`` as one mapping; its quests' records
            # are under "quests")
            "values": plain({k: v for k, v in values.items() if k != "quests"} if isinstance(values, dict) else {}),
            "chapter": plain(getattr(state, "chapter", None)),
            "playtime_seconds": plain(round(float(getattr(state, "playtime_seconds", 0.0) or 0.0), 3))}


def _quests(window: Any) -> Doc:
    manager = getattr(window, "quest_manager", None)
    definitions = getattr(manager, "_definitions", None)
    if not isinstance(definitions, dict):
        return _unavailable("the game has no quest manager")
    state = getattr(getattr(window, "game_state_controller", None), "state", None)
    values = getattr(state, "values", None)
    records = values.get("quests") if isinstance(values, dict) else None
    records = records if isinstance(records, dict) else {}  # (read as it is: never created here)
    quests = []
    for quest_id, quest in list(definitions.items())[:ITEMS_MAX]:
        record = records.get(quest_id)
        record = record if isinstance(record, dict) else {}
        stages = quest.get("stages") if isinstance(quest, dict) else None
        quests.append({"id": plain(quest_id), "title": plain(quest.get("title") if isinstance(quest, dict) else None),
                       "auto_start": bool(quest.get("auto_start")) if isinstance(quest, dict) else False,
                       "status": plain(record.get("status", "inactive")),
                       "current_stage": plain(record.get("current_stage")),
                       "awaiting_stage": plain(record.get("awaiting_stage")),
                       "completed_stages": plain(list(record.get("completed_stages") or [])),
                       "total_stages": len(stages) if isinstance(stages, list) else None})
    return {"available": True, "quests": quests, "defined": len(definitions)}


def _events(window: Any, since: int | None, limit: int) -> Doc:
    """The play-test's events, oldest first, numbered in the order the game emitted them (``seq``)."""
    bus = getattr(window, "event_bus", None)
    history = getattr(bus, "_history", None)
    emitted = getattr(bus, "emitted", None)
    if not isinstance(history, list) or not isinstance(emitted, int):
        return _unavailable("the game has no event history")
    first = emitted - len(history) + 1  # the history's oldest event's number
    since = 0 if since is None else since
    numbered = [(first + i, event) for i, event in enumerate(list(history)) if first + i > since]
    made = emitted - since
    items = []
    for seq, event in numbered[-limit:] if limit else []:
        payload = event.get("payload") if isinstance(event, dict) else None
        payload = payload if isinstance(payload, dict) else {}
        entity = event.get("entity_name") or payload.get("entity") or payload.get("owner")
        items.append({"seq": seq, "type": plain(event.get("name")), "entity": plain(entity),
                      "scene": plain(event.get("scene_id")), "time": _rounded(event.get("timestamp")),
                      "payload": plain(payload)})
    return {"available": True, "items": items, "made_this_playtest": made,
            "no_longer_kept": max(0, made - len(numbered)), "last_seq": emitted, "limit": limit}


def _rounded(value: Any) -> Any:
    return round(float(value), 3) if isinstance(value, numbers.Real) and math.isfinite(value) else plain(value)


def _diagnostics(playtest: Doc) -> Doc:
    """Errors the engine caught and carried on from during this play-test (``engine.swallowed_exceptions``: each
    place that catches one counts it), newest first."""
    from engine import swallowed_exceptions  # noqa: PLC0415

    before = playtest.get("caught_before") or {}
    started = float(playtest.get("started_at") or 0.0)
    rows = []
    for site, stats in swallowed_exceptions.read_sites().items():
        count = stats.count - int(before.get(site, 0))
        if count > 0 and stats.last_seen_ts >= started:
            rows.append({"kind": "caught_exception", "site": plain(site), "count": count,
                         "last_seen": round(stats.last_seen_ts, 3)})
    rows.sort(key=lambda row: (-row["last_seen"], row["site"]))
    return {"available": True, "items": rows[:DIAGNOSTICS_MAX], "sites": len(rows),
            "note": "Errors the engine caught and carried on from (each place that catches one counts it), since the "
                    "play-test started; the log has their details."}


def snapshot(studio: Any, *, sequence: int, events: int = EVENTS_DEFAULT) -> Doc:
    """The running game in ``studio``, read on Studio's main thread (``StudioAIHost.debug_snapshot``)."""
    project = studio.project
    limit = max(0, min(int(events), EVENTS_MAX))
    out: Doc = {"ok": True, "mode": "live_studio", "sequence": sequence, "time": round(time.time(), 3),
                "studio": {"mode": "playing" if studio.mode == "play" else "editing",
                           "edited_room": project.current, "unsaved_changes": bool(project.is_dirty),
                           "revision": project.revision,
                           "ai_playtest_control": bool(getattr(studio.ai, "playtest_control", False))}}
    playtest = getattr(studio, "playtest", None)
    if studio.mode != "play" or not isinstance(playtest, dict):
        last = getattr(studio, "last_playtest", None)
        out.update(status="not_playing", last_playtest=_playtest_view(last) if isinstance(last, dict) else None,
                   message="Mesh Studio is editing, not play-testing: no game is running to inspect. "
                           "debug_start_playtest starts one (if the person allowed it), or ask the person to press "
                           "Play (F4).")
        return out
    window = studio.window
    out.update(status="playing", playtest=_playtest_view(playtest), scene=_scene(window, project),
               player=_player(window), game_state=_game_state(window), quests=_quests(window),
               events=_events(window, playtest.get("events_before"), limit), diagnostics=_diagnostics(playtest))
    if len(json.dumps(out)) > BYTES_MAX:  # (each part is bounded; together they still may not be)
        for item in out["events"].get("items", []):
            item["payload"] = "..."
        if out["game_state"].get("available"):
            out["game_state"]["values"] = "..."
        out["truncated"] = True
    return out


def _playtest_view(playtest: Doc) -> Doc:
    return {key: playtest.get(key) for key in ("id", "number", "started_at", "started_by", "stopped_at")}


# --------------------------------------------------------------------- from outside (the MCP tools)

def _ask(root: str | Path, method: str, path: str) -> Doc:
    from engine import authoring_session  # noqa: PLC0415  # (it imports the project model: only when asked)

    info, failure = authoring_session._studio(root)
    return failure or authoring_session._call(info, method, path)


def request_snapshot(root: str | Path = ".", events: int = EVENTS_DEFAULT) -> Doc:
    try:
        count = max(0, min(int(events), EVENTS_MAX))
    except (TypeError, ValueError):
        count = EVENTS_DEFAULT
    return _ask(root, "GET", f"/live/debug/snapshot?events={count}")


def request_play(root: str | Path = ".") -> Doc:
    return _ask(root, "POST", "/live/debug/play")


def request_stop(root: str | Path = ".") -> Doc:
    return _ask(root, "POST", "/live/debug/stop")
