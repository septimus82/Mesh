"""Mesh's one authoring API: named, validated changes to a project.

Mesh Studio, AI clients (over MCP) and the command line all edit projects through this module,
which runs the operations in ``engine.project_ops`` on a ``engine.studio_project.Project``.
There is no separate catalogue to keep in step: the list of operations, their settings and
their descriptions come from ``project_ops`` itself (``describe``).

A change is a dict: ``{"op": "place_prefab", "room": "start", "prefab": "person", "x": 320, "y": 200}``.

- ``room`` is a room key (``read_project`` lists them); it defaults to the project's current room.
- Settings named ``entity_id`` take an object's id or its unique name.
- ``prefab`` takes a prefab id (or display name); ``entity`` (to duplicate) takes an id or name.
- ``model`` (an HD-2D structure) takes a model from ``models`` (``read_project`` lists them): its catalogue id or
  its project-relative .glb path. Models are imported by a person in Mesh Studio; changes can't add files.
- ``"@2"`` stands for the id of the object (or the index of the light) created by change number 2
  (counting from 0) of the same batch, so one batch can add a person and give them a conversation.

``apply`` runs a batch as one transaction: all of it, or (if any change is refused) none of it,
with a message saying which change and why. ``changes_between`` and ``summarize`` describe what
a batch did, for people to review before accepting it.
"""

from __future__ import annotations

import copy
import inspect
import json
from typing import Any, Callable

from engine import project_ops as ops
from engine.studio_project import Project

Doc = dict[str, Any]

# Edits of a whole project rather than one room (they create rooms and write map files).
_PROJECT_OPS: dict[str, Callable[..., Any]] = {
    "add_room": Project.add_room,
    "add_map": Project.add_map,
    "link_rooms": Project.link_rooms,
}
# Settings the API fills in itself, never the caller.
_IMPLICIT = {"scene", "scene_key", "self"}
# ``project_ops`` functions that look like edits but only read or prepare.
_NOT_EDITS = {"ensure_entity_ids", "find_entity", "expand_players", "casts_shadow", "flicker_name"}


class ChangeError(ValueError):
    """A change was refused; ``str(err)`` names the change and the reason, for people and AIs."""

    def __init__(self, index: int, op: str, message: str) -> None:
        super().__init__(f"Change {index} ({op}): {message}")
        self.index, self.op, self.reason = index, op, message


def _room_ops() -> dict[str, Callable[..., Any]]:
    """Every ``project_ops`` function that edits one room: ``(scene, ...) -> scene``, ``(scene, id)`` or
    ``(scene, index)`` (a light)."""
    found: dict[str, Callable[..., Any]] = {}
    for name, func in vars(ops).items():
        if name.startswith("_") or name in _NOT_EDITS or not inspect.isfunction(func) or func.__module__ != ops.__name__:
            continue
        params = list(inspect.signature(func).parameters)
        returns = str(inspect.signature(func).return_annotation)
        if params and params[0] == "scene" and returns in ("Doc", "tuple[Doc, str]", "tuple[Doc, int]"):
            found[name] = func
    return found


def operations() -> dict[str, Callable[..., Any]]:
    return {**_room_ops(), **_PROJECT_OPS}


def describe() -> list[Doc]:
    """Every operation with its settings and what it does: what an AI or a person can ask for."""
    out = []
    for name, func in sorted(operations().items()):
        signature = inspect.signature(func)
        params = []
        if name not in _PROJECT_OPS:
            params.append({"name": "room", "type": "str", "required": False,
                           "note": "room key (default: the current room)"})
        for param in signature.parameters.values():
            if param.name in _IMPLICIT:
                continue
            entry: Doc = {"name": param.name, "type": str(param.annotation).replace("Doc", "object"),
                          "required": param.default is inspect.Parameter.empty}
            if param.default is not inspect.Parameter.empty and param.default is not ops._UNSET:
                entry["default"] = param.default if isinstance(param.default, (str, int, float, bool, type(None))) else repr(param.default)
            if param.name == "entity_id":
                entry["note"] = "an object's id or its unique name, or @N for one made earlier in the batch"
            params.append(entry)
        doc = inspect.getdoc(func) or ""
        out.append({"op": name, "summary": doc.split("\n\n")[0].replace("\n", " "), "params": params,
                    "scope": "project" if name in _PROJECT_OPS else "room"})
    return out


# --------------------------------------------------------------------------------------- apply
def apply(project: Project, changes: list[Doc]) -> Doc:
    """Run ``changes`` on ``project`` as one transaction (one undo step).

    Returns ``{"ok": True, "applied": n, "created": {index: id}}``; raises ChangeError (and
    changes nothing) if any change is refused.
    """
    if not isinstance(changes, list) or not all(isinstance(c, dict) for c in changes):
        raise ChangeError(0, "?", "changes must be a list of objects like {\"op\": ..., ...}.")
    created: dict[int, str | int] = {}
    with project.transaction():
        for index, change in enumerate(changes):
            made = _apply_one(project, index, change, created)
            if made is not None:
                created[index] = made
    return {"ok": True, "applied": len(changes), "created": created}


def _apply_one(project: Project, index: int, change: Doc, created: dict[int, str | int]) -> str | int | None:
    name = str(change.get("op") or change.get("type") or "")  # "type": how older Mesh tools spell it
    func = operations().get(name)
    if func is None:
        raise ChangeError(index, name or "?", f"there is no operation '{name}'. describe() lists them.")
    args = {k: _deref(v, created, index, name) for k, v in change.items() if k not in ("op", "type", "room")}
    try:
        if name in _PROJECT_OPS:
            return _call_project_op(project, func, args, index, name)
        room = str(change.get("room") or project.current)
        if room not in {key for key, _label, _path in project.rooms()}:
            raise ChangeError(index, name, f"there is no room '{room}'. Rooms: {', '.join(k for k, _, _ in project.rooms())}.")
        scene = project.scene(room)
        bound = _bind(func, args, scene, room, project, index, name)
        result = func(**bound)
        new_scene, made = (result if isinstance(result, tuple) else (result, None))
        project.edit_scene(lambda _s: new_scene, room)
        return made if isinstance(made, (str, int)) else None
    except ops.OpError as err:
        raise ChangeError(index, name, str(err)) from err
    except (TypeError, ValueError) as err:
        if isinstance(err, ChangeError):
            raise
        raise ChangeError(index, name, str(err)) from err


def _call_project_op(project: Project, func: Callable[..., Any], args: Doc, index: int, name: str) -> str | None:
    params = inspect.signature(func).parameters
    unknown = sorted(set(args) - set(params))
    if unknown:
        raise ChangeError(index, name, f"unknown setting(s) {', '.join(unknown)}; it takes {', '.join(p for p in params if p != 'self')}.")
    args = {k: tuple(v) if isinstance(v, list) and k.startswith("at_") else v for k, v in args.items()}
    result = func(project, **args)
    return result if isinstance(result, str) else None


def _bind(func: Callable[..., Any], args: Doc, scene: Doc, room: str, project: Project, index: int, name: str) -> Doc:
    params = inspect.signature(func).parameters
    unknown = sorted(set(args) - set(params) - _IMPLICIT)
    if unknown:
        takes = [p for p in params if p not in _IMPLICIT]
        raise ChangeError(index, name, f"unknown setting(s) {', '.join(unknown)}; it takes {', '.join(takes)}.")
    bound: Doc = {"scene": scene}
    if "scene_key" in params:
        bound["scene_key"] = room
    for key, value in args.items():
        if key == "entity_id":
            value = _resolve_entity(scene, value, index, name)
        elif key == "prefab":
            value = _resolve_prefab(project, value, index, name)
        elif key == "entity" and isinstance(value, str):
            value = ops.find_entity(scene, _resolve_entity(scene, value, index, name))
        elif key == "cells" and isinstance(value, list):
            value = [tuple(cell) for cell in value]
        elif key == "anchor" and isinstance(value, list):
            value = tuple(value)
        elif key == "model" and isinstance(value, str):  # an HD-2D structure's .glb: it must exist and be usable
            from engine.hd2d.catalog import CatalogError, find  # noqa: PLC0415
            from engine.hd2d.glb import model_problem  # noqa: PLC0415

            try:
                listed = find(project.root, value) if not value.lower().endswith(".glb") else None
            except CatalogError:
                listed = None
            value = listed.model if listed is not None else value  # a catalogue id names its file
            problem = model_problem(project.root, value)
            if problem:
                raise ChangeError(index, name, problem)
        bound[key] = value
    missing = [p.name for p in params.values()
               if p.default is inspect.Parameter.empty and p.name not in bound and p.name not in _IMPLICIT]
    if missing:
        raise ChangeError(index, name, f"missing setting(s): {', '.join(missing)}.")
    return bound


def _deref(value: Any, created: dict[int, str | int], index: int, name: str) -> Any:
    if isinstance(value, str) and value.startswith("@") and value[1:].isdigit():
        ref = int(value[1:])
        if ref not in created:
            raise ChangeError(index, name, f"{value} refers to change {ref}, which made no object (or comes later).")
        return created[ref]
    if isinstance(value, list):
        return [_deref(v, created, index, name) for v in value]
    if isinstance(value, dict):
        return {k: _deref(v, created, index, name) for k, v in value.items()}
    return value


def _resolve_entity(scene: Doc, value: Any, index: int, name: str) -> str:
    try:
        return ops.entity_ref(scene, value)
    except ops.OpError as exc:
        raise ChangeError(index, name, str(exc)) from None


def models(project: Project) -> list[Doc]:
    """The project's Blender models, as AI tools read them (``read_project``'s ``models``): catalogue id, file,
    name, category, default turn and scale, collision, floors, licence, and whether the file is missing."""
    from engine.hd2d.catalog import CatalogError, assets  # noqa: PLC0415

    try:
        return [asset.as_dict() for asset in assets(project.root)]
    except CatalogError as err:
        return [{"error": str(err)}]


def prefabs(project: Project) -> list[Doc]:
    try:
        data = json.loads((project.root / "assets" / "prefabs.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [p for p in data if isinstance(p, dict) and isinstance(p.get("entity"), dict) and p.get("id")]


def _resolve_prefab(project: Project, value: Any, index: int, name: str) -> Doc:
    if isinstance(value, dict):
        return value
    text = str(value or "").strip()
    for prefab in prefabs(project):
        if text in (prefab["id"], prefab.get("display_name")):
            return prefab
    known = ", ".join(p["id"] for p in prefabs(project)) or "none"
    raise ChangeError(index, name, f"there is no object type '{text}'. This project has: {known}.")


def dry_run(project: Project, changes: list[Doc], *, base: Doc | None = None) -> tuple[Doc, Doc]:
    """``(before, after)`` documents for ``changes`` tried on a copy (``base``: start from these)."""
    trial = project.clone()
    if base is not None:
        trial.load_documents(base)
    before = copy.deepcopy(trial.all_documents())
    apply(trial, changes)
    return before, copy.deepcopy(trial.all_documents())


# --------------------------------------------------------------------------------------- diff
def changes_between(before: Doc, after: Doc) -> dict[tuple[Any, ...], tuple[Any, Any]]:
    """Every leaf that differs: ``{path: (old, new)}``. Lists of objects with ids (entities,
    tile layers) are matched by id, and tile lists cell by cell, so separate edits stay separate."""
    out: dict[tuple[Any, ...], tuple[Any, Any]] = {}
    _diff(before, after, (), out)
    return out


_MISSING = object()


def _diff(a: Any, b: Any, path: tuple[Any, ...], out: dict[tuple[Any, ...], tuple[Any, Any]]) -> None:
    if a is _MISSING or b is _MISSING:
        out[path] = (None if a is _MISSING else a, None if b is _MISSING else b)
        return
    if isinstance(a, dict) and isinstance(b, dict):
        for key in list(a) + [k for k in b if k not in a]:
            _diff(a.get(key, _MISSING), b.get(key, _MISSING), path + (key,), out)
        return
    if isinstance(a, list) and isinstance(b, list):
        if _keyed(a) and _keyed(b):
            ka, kb = {x["id"]: x for x in a}, {x["id"]: x for x in b}
            for key in list(ka) + [k for k in kb if k not in ka]:
                _diff(ka.get(key, _MISSING), kb.get(key, _MISSING), path + (f"#{key}",), out)
            return
        if len(a) == len(b) and all(not isinstance(x, (dict, list)) for x in a + b):
            for i, (x, y) in enumerate(zip(a, b)):
                if x != y:
                    out[path + (i,)] = (x, y)
            return
    if a != b:
        out[path] = (a, b)


def _keyed(items: list[Any]) -> bool:
    return bool(items) and all(isinstance(x, dict) and isinstance(x.get("id"), str) for x in items) \
        and len({x["id"] for x in items}) == len(items)


def conflicts(ours: dict[tuple[Any, ...], tuple[Any, Any]], theirs: dict[tuple[Any, ...], tuple[Any, Any]]) -> list[Doc]:
    """Places both sides changed differently (a path, or one inside the other). Equal results agree."""
    found = []
    for p, (_old, mine) in ours.items():
        for q, (_old2, other) in theirs.items():
            if p == q:
                if mine != other:
                    found.append({"path": _path_text(p), "what": _conflict_words(p), "studio": mine, "ai": other})
            elif p[: len(q)] == q or q[: len(p)] == p:
                deeper = p if len(p) > len(q) else q
                found.append({"path": _path_text(deeper), "what": _conflict_words(deeper), "studio": mine, "ai": other})
    return found


def _conflict_words(path: tuple[Any, ...]) -> str:
    if len(path) >= 4 and path[0] == "rooms" and path[2] == "entities":
        return f"{path[1]}: object {str(path[3]).lstrip('#')} {_friendly(path[4:]) if len(path) > 4 else '(the whole object)'}"
    return _path_text(path)


def _path_text(path: tuple[Any, ...]) -> str:
    return "/".join(str(part) for part in path)


# --------------------------------------------------------------------------------------- summary
def summarize(before: Doc, after: Doc) -> list[str]:
    """Plain-language lines for what changed between two whole-project views, room by room."""
    lines: list[str] = []
    world_b, world_a = before.get("world") or {}, after.get("world") or {}
    rooms_b, rooms_a = before.get("rooms") or {}, after.get("rooms") or {}
    for key in rooms_a:
        if key not in rooms_b:
            label = ((world_a.get("scenes") or {}).get(key) or {}).get("label") or key
            lines.append(f"New room: {label}")
    for key, room in rooms_a.items():
        label = ((world_a.get("scenes") or {}).get(key) or {}).get("label") or key
        old = rooms_b.get(key) or {"entities": []}
        olds = {e.get("id"): e for e in ops.entities(old)}
        news = {e.get("id"): e for e in ops.entities(room)}
        for eid, entity in news.items():
            name = entity.get("name") or eid
            if eid in olds and ops.water_of(olds[eid]) is not None and ops.water_of(entity) is None:
                lines.append(f"{label}: '{name}' stops being water")  # Milestone 19A: not its raw settings
                continue
            if eid not in olds:
                water = ops.water_of(entity)
                what = (f"{water['preset'].replace('_', ' ')} water {water['width']:g} x {water['height']:g}" if water
                        else entity.get("prefab_id") or ("a picture" if entity.get("sprite") else "no picture"))
                lines.append(f"{label}: adds '{name}' ({what}) at {entity.get('x', 0):g}, {entity.get('y', 0):g}")
                continue
            for path, (was, now) in changes_between(olds[eid], entity).items():
                lines.append(f"{label}: '{name}' {_friendly(path)}: {_short(was)} -> {_short(now)}")
        for eid, entity in olds.items():
            if eid not in news:
                lines.append(f"{label}: removes '{entity.get('name') or eid}'")
        tiles = [p for p in changes_between(old.get("tilemap") or {}, room.get("tilemap") or {}) if "tiles" in p]
        if tiles:
            lines.append(f"{label}: repaints {len(tiles)} tile(s)")
        lines += _structure_lines(label, ops.structures(old), ops.structures(room))
        lines += _weather_lines(label, old.get("settings") or {}, room.get("settings") or {})
        lines += _terrain_lines(label, old, room)
    if world_b.get("start_scene") != world_a.get("start_scene") and world_b:
        lines.append(f"Start room: {world_b.get('start_scene')} -> {world_a.get('start_scene')}")
    return lines


def _structure_lines(label: str, before: list[Doc], after: list[Doc]) -> list[str]:
    """HD-2D structures (``settings.hd2d.structures``) in words, metres and degrees (32 px = 1 m)."""
    def where(s: Doc) -> str:
        text = f"({float(s.get('x', 0)) / 32:.1f} m, {float(s.get('y', 0)) / 32:.1f} m"
        if s.get("elevation"):
            text += f", {float(s['elevation']) / 32:.1f} m up"
        if s.get("rotation"):
            text += f", turned {float(s['rotation']):g} degrees"
        return text + ")"

    olds = {s.get("id"): s for s in before if isinstance(s, dict)}
    news = {s.get("id"): s for s in after if isinstance(s, dict)}
    lines = [f"{label}: places structure '{sid}' ({s.get('model')}) at {where(s)}" for sid, s in news.items()
             if sid not in olds]
    lines += [f"{label}: moves structure '{sid}' {where(olds[sid])} -> {where(s)}" for sid, s in news.items()
              if sid in olds and olds[sid] != s]
    lines += [f"{label}: removes structure '{sid}'" for sid in olds if sid not in news]
    return lines


def _weather_words(effects: Any) -> str:
    """A room's ``settings.particles`` in words: "rain x3000 (wind 0.8 east m/s), leaves x400" (Milestone 18B)."""
    if not effects:
        return "none"
    if not isinstance(effects, list):
        return f"unreadable ({_short(effects)})"
    parts = []
    for e in effects:
        if not isinstance(e, dict):
            parts.append(f"unreadable ({_short(e)})")
            continue
        preset = e.get("preset", "?")
        text = ("leaves" if preset == "wind" else str(preset)) + (f" x{e['count']}" if "count" in e else "")
        wind = e.get("wind")
        if isinstance(wind, (list, tuple)) and len(wind) == 2 and all(isinstance(c, (int, float)) for c in wind):
            east, north = wind
            dirs = ([f"{abs(east):g} {'east' if east >= 0 else 'west'}"] if east else []) + (
                [f"{abs(north):g} {'north' if north >= 0 else 'south'}"] if north else [])
            text += f" (wind {', '.join(dirs)} m/s)" if dirs else " (no wind)"
        if e.get("enabled") is False:
            text += " (off)"
        parts.append(text)
    return ", ".join(parts)


def _terrain_lines(label: str, before: Doc, after: Doc) -> list[str]:
    """A room's sculpted ground changed, in words (Milestone 20A): how much of it, how far up and down, and what it
    left out of place ("'Elder' is 1.5 m above the ground"), not its stored heights; what was painted and the
    edges chosen (Milestone 20C)."""
    def terrain(scene: Doc) -> Any:
        hd2d = (scene.get("settings") or {}).get("hd2d") if isinstance(scene.get("settings"), dict) else None
        ground = hd2d.get("ground") if isinstance(hd2d, dict) else None
        return ground.get("terrain") if isinstance(ground, dict) else None

    if terrain(before) == terrain(after):
        return []
    from engine.hd2d.terrain import Terrain  # noqa: PLC0415

    try:
        old, new = (Terrain.from_ground(ops._parsed_ground(s)) for s in (before, after))
    except (ops.OpError, ValueError):
        return [f"{label}: the ground's sculpted heights change"]
    if len(old.heights) != len(new.heights):
        return [f"{label}: the ground's sculpted heights change"]
    lines = _paint_lines(label, old, new)
    deltas = [b - a for a, b in zip(old.heights, new.heights) if b != a]
    if not deltas:
        return lines
    area = len(deltas) * (old.cell / 32.0) ** 2
    up, down = max(0.0, max(deltas)) / 32.0, max(0.0, -min(deltas)) / 32.0
    moves = " and ".join(part for part in (f"raised up to {up:.2f} m" if up else "",
                                          f"lowered up to {down:.2f} m" if down else "") if part)
    low, high = new.range_z()
    lines.insert(0, f"{label}: ground sculpted over about {area:.0f} m²: {moves} (now {low:.2f} to {high:.2f} m)"
                 if not new.is_flat() else f"{label}: ground made flat again")
    lines += [f"{label}: left out of place (not moved): {words}" for words in ops.terrain_anchoring(after, before)]
    return lines


def _paint_lines(label: str, old: Any, new: Any) -> list[str]:
    """What a change painted (Milestone 20C): about how much ground became each material, and the edges."""
    from engine.hd2d.terrain import MATERIALS, PAINTED  # noqa: PLC0415

    lines = []
    if old.paint != new.paint:
        size = PAINTED * (new.nx + 1) * (new.ny + 1)
        a, b = bytes(old.paint or bytes(size)), bytes(new.paint or bytes(size))
        gained = [0] * len(MATERIALS)
        for k in range(0, size, PAINTED):
            if a[k:k + PAINTED] != b[k:k + PAINTED]:
                was = [255 - sum(a[k:k + PAINTED]), *a[k:k + PAINTED]]
                now = [255 - sum(b[k:k + PAINTED]), *b[k:k + PAINTED]]
                if was.index(max(was)) != now.index(max(now)):
                    gained[now.index(max(now))] += 1
        cell_m2 = (new.cell / 32.0) ** 2
        parts = [f"{name} about {n * cell_m2:.0f} m²" for name, n in zip(MATERIALS, gained) if n]
        lines.append(f"{label}: ground painted: {', '.join(parts)}" if parts
                     else f"{label}: ground painted a little (no place changes material)")
    if old.edges != new.edges:
        lines.append(f"{label}: material edges {new.edges}")
    return lines


def _effect_dicts(effects: Any) -> list[Doc]:
    return [e if isinstance(e, dict) else {} for e in (effects if isinstance(effects, list) else [])]


def _weather_lines(label: str, before: Doc, after: Doc) -> list[str]:
    """A room's weather settings (particles, weather_exposure) changed, in words."""
    lines = []
    old, new = before.get("particles"), after.get("particles")
    if old != new:
        was, now = _weather_words(old), _weather_words(new)
        if was == now:  # the change is in a setting the words leave out (opacity, gust, area, seed...): name it
            olds, news = _effect_dicts(old), _effect_dicts(new)
            keys: set[str] = set()
            for i in range(max(len(olds), len(news))):
                a, b = olds[i] if i < len(olds) else {}, news[i] if i < len(news) else {}
                keys |= {k for k in a.keys() | b.keys() if a.get(k) != b.get(k)}
            lines.append(f"{label}: weather {now}: changes {', '.join(sorted(keys)) or 'its settings'}")
        else:
            lines.append(f"{label}: weather {was} -> {now}")
    if before.get("weather_exposure") != after.get("weather_exposure"):
        lines.append(f"{label}: weather exposure {before.get('weather_exposure') or 'outdoor'} -> "
                     f"{after.get('weather_exposure') or 'outdoor'}")
    mirrors = [(s.get("hd2d") or {}).get("water_reflections") if isinstance(s.get("hd2d"), dict) else None
               for s in (before, after)]
    if mirrors[0] != mirrors[1]:  # Milestone 19B
        lines.append(f"{label}: water reflections {mirrors[0] or 'full'} -> {mirrors[1] or 'full'}")
    return lines


_BEHAVIOUR_WORDS = {
    ("ConditionalActivator", "require_flags"): "shows only when these flags are set",
    ("ConditionalActivator", "forbid_flags"): "is hidden once these flags are set",
    ("ConditionalActivator",): "shows only when (flags)",
    ("Dialogue", "require_flags"): "can be talked to when these flags are set",
    ("Dialogue", "forbid_flags"): "can't be talked to once these flags are set",
    ("Dialogue", "once"): "conversation only once",
    ("Dialogue", "auto_start"): "conversation starts by itself",
    ("Dialogue", "start_event"): "conversation starts when",
    ("PictureByFlags",): "picture changes (by flags)",
    ("TriggerVolume",): "trigger zone",
    ("SetGameStateOnEvent",): "sets flags when the zone is entered",
}


def _friendly(path: tuple[Any, ...]) -> str:
    """A property path in words where it's a common one: what a person reviewing changes reads."""
    if len(path) >= 2 and path[0] == "behaviour_config":
        behaviour, rest = str(path[1]), tuple(str(p) for p in path[2:])
        if behaviour == "Dialogue" and rest[:2] == ("dialogue", "nodes") and len(rest) >= 3:
            field = {"text": " says", "next": " then goes to", "speaker": " speaker", "choices": " choices"}.get(
                rest[3] if len(rest) > 3 else "", "")
            return f"conversation line '{rest[2]}'{field}"
        if behaviour == "Dialogue" and rest[:2] == ("dialogue", "starts"):
            return "conversation openings"
        if behaviour == "Dialogue" and rest[:2] == ("dialogue", "speaker"):
            return "conversation speaker"
        if behaviour == "WaterSurface" and rest:  # Milestone 19A
            return f"water {rest[0].replace('_', ' ')}"
        for key in ((behaviour, rest[0]) if rest else (), (behaviour,)):
            if key in _BEHAVIOUR_WORDS:
                return _BEHAVIOUR_WORDS[key]
        return f"{behaviour} setting {'/'.join(rest)}".strip()
    words = {("behaviours",): "behaviours", ("sprite",): "picture", ("components", "collider"): "collider",
             ("solid",): "blocks movement", ("scale",): "size", ("x",): "x", ("y",): "y", ("name",): "name"}
    return words.get(tuple(path[:2]) if path[:1] == ("components",) else tuple(path[:1]), _path_text(path))


def _short(value: Any, limit: int = 48) -> str:
    text = "(none)" if value is None else json.dumps(value) if not isinstance(value, str) else repr(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"
