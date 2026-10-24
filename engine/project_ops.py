"""Validated operations on Mesh project documents (scenes and the world file).

This is the one mutation layer for authored content: the Studio editor calls it,
and the AI/CLI layers are meant to call it too. Every operation is pure: it takes
documents, returns new documents, and never touches disk or a running game. An
operation that would leave a scene with new validation errors raises OpError
instead, with a message fit to show a user.
"""

from __future__ import annotations

import copy
import json
import posixpath
import re
from typing import Any, Iterable

from engine.ai_ops import build_prefab_entity_definition
from engine.behaviours import load_builtin_behaviours
from engine.behaviours.registry import get_behaviour_info, list_behaviours
from engine.entity_paint_mode import make_entity_id
from engine.physics_runtime import footprint
from engine.scene_loader import SceneLoader
from engine.tilemap_edit import TilemapDims, ensure_tiles_array, get_layer_by_id, set_tile
from engine.tilemap_flood_fill import flood_fill_indices

Doc = dict[str, Any]

DOOR_SPRITE = "assets/sprites/door.png"

# Maps use the engine's existing tilemap format: the scene's inline ``tile_layers`` hold
# the painted tiles (they override the map file's layers), and a small Tiled-format map
# file next to the room supplies the size and the tileset. Tile ids are Tiled gids
# (first gid 1); 0 is an empty cell.
TILESET_SOURCE = "assets/tilesets/starter.json"
TILE_SIZE = 32
GROUND, WALLS, OVERHEAD = "ground", "walls", "overhead"
# (id, z, collision). WALLS is the collision layer: anything painted there blocks. OVERHEAD
# has z >= 0, so the runtime draws it after characters (roofs, treetops); it never blocks.
MAP_LAYERS = ((GROUND, -20, False), (WALLS, -10, True), (OVERHEAD, 10, False))
STARTER_GRASS, STARTER_FLOOR, STARTER_WALL = 1, 5, 9  # gids in the starter tileset
# Arrival spot relative to its door: far enough that a 64px player doesn't touch a
# walk-in door (which would send them straight back).
ARRIVAL_OFFSET = (0.0, -96.0)


class OpError(ValueError):
    """The operation was rejected; ``str(err)`` is a user-facing reason."""


# --- lookup ---------------------------------------------------------------------------------


def entities(scene: Doc) -> list[Doc]:
    return [e for e in scene.get("entities") or [] if isinstance(e, dict)]


def find_entity(scene: Doc, entity_id: str) -> Doc:
    for entity in entities(scene):
        if entity.get("id") == entity_id:
            return entity
    raise OpError(f"There is no object with id '{entity_id}' in this room.")


def entity_ref(scene: Doc, ref: Any) -> str:
    """The id of the object ``ref`` names: its id, or its name when exactly one object has it."""
    text = str(ref or "").strip()
    if any(e.get("id") == text for e in entities(scene)):
        return text
    named = [e for e in entities(scene) if e.get("name") == text]
    if len(named) == 1 and named[0].get("id"):
        return str(named[0]["id"])
    if len(named) > 1:
        raise OpError(f"{len(named)} objects are called '{text}'; use an id.")
    raise OpError(f"There is no object '{text}' in this room.")


def unique_entity_id(scene: Doc, base: str) -> str:
    taken = {e.get("id") for e in entities(scene)}
    candidate, n = base, 2
    while candidate in taken:
        candidate = f"{base}_{n}"
        n += 1
    return candidate


def slug(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")
    return value or "room"


# --- validation -----------------------------------------------------------------------------

_LOADER = SceneLoader()


def scene_errors(scene: Doc) -> list[str]:
    report = _LOADER.validate_scene(_LOADER.apply_scene_defaults(copy.deepcopy(scene)))
    return list(report.errors)


def _schema_problem(scene: Doc) -> str | None:
    """Why the runtime's strict scene schema would refuse ``scene`` (None if it accepts it)."""
    from engine.schema_validation import SchemaValidationError, validate  # noqa: PLC0415

    try:
        validate(scene, "scene.schema.json", "scene")
    except SchemaValidationError as exc:
        return str(exc)
    return None


def _checked(before: Doc, after: Doc) -> Doc:
    """Reject an edit that introduces validation errors the scene didn't already have.

    Two checks: the scene loader's (lenient, content-aware) and the strict scene schema the
    runtime loads with. Without the second, an edit could save a room that then fails to load.
    """
    new = [e for e in scene_errors(after) if e not in set(scene_errors(before))]
    if new:
        raise OpError(new[0])
    problem = _schema_problem(after)
    if problem and _schema_problem(before) is None:
        raise OpError(f"That would make the room unloadable: {problem}")
    return after


# --- entities -------------------------------------------------------------------------------


def ensure_entity_ids(scene: Doc, scene_key: str) -> Doc:
    """Give every entity a stable id (older scenes may lack them); editing needs one."""
    out = copy.deepcopy(scene)
    for entity in entities(out):
        if not entity.get("id"):
            base = make_entity_id(scene_key, str(entity.get("name") or "object"), entity.get("x", 0), entity.get("y", 0))
            entity["id"] = unique_entity_id(out, base)
    return out


def place_prefab(scene: Doc, scene_key: str, prefab: Doc, x: float, y: float) -> tuple[Doc, str]:
    """A new object of a project object type (prefab), at ``(x, y)``; returns its id."""
    prefab_id = str(prefab.get("id") or "object")
    out = copy.deepcopy(scene)
    entity_id = unique_entity_id(out, make_entity_id(scene_key, prefab_id, x, y))
    entity = build_prefab_entity_definition(prefab, prefab_id, x, y, out, entity_id=entity_id)
    out.setdefault("entities", []).append(entity)
    return _checked(scene, out), entity_id


def paste_entity(scene: Doc, scene_key: str, entity: Doc, x: float, y: float) -> tuple[Doc, str]:
    """A copy of ``entity`` (from this or another room) at ``(x, y)``, with a fresh id and name."""
    if entity.get("tag") == "player":
        raise OpError("A room has one player; the player can't be copied.")
    if entity.get("spawn_id") or entity.get("tag") == "spawn_point":
        raise OpError("Arrival spots belong to their door; copy the door instead.")
    out = copy.deepcopy(scene)
    pasted = copy.deepcopy(entity)
    base = str(entity.get("name") or "Object")
    names, n, name = {e.get("name") for e in entities(out)}, 2, base
    while name in names:
        name, n = f"{base} {n}", n + 1
    pasted.update(name=name, x=round(float(x), 2), y=round(float(y), 2))
    pasted["id"] = unique_entity_id(out, make_entity_id(scene_key, slug(base), x, y))
    out.setdefault("entities", []).append(pasted)
    return _checked(scene, out), pasted["id"]


def set_entity_fields(scene: Doc, entity_id: str, **fields: Any) -> Doc:
    """Set top-level fields of an object (sprite, sprite_sheet, solid, scale...); None removes one.

    The scene schema checks the result, so an unknown field or a wrong type is refused.
    """
    out = copy.deepcopy(scene)
    entity = find_entity(out, entity_id)
    for name, value in fields.items():
        if name in ("id", "behaviours", "behaviour_config"):
            raise OpError(f"'{name}' has its own operations.")
        if value is None:
            entity.pop(name, None)
        else:
            entity[name] = copy.deepcopy(value)
    return _checked(scene, out)


def remove_entity(scene: Doc, entity_id: str) -> Doc:
    """Delete an object from the room."""
    find_entity(scene, entity_id)
    out = copy.deepcopy(scene)
    out["entities"] = [e for e in entities(out) if e.get("id") != entity_id]
    return out


def move_entity(scene: Doc, entity_id: str, x: float, y: float) -> Doc:
    """Move an object to ``(x, y)`` (world pixels; y points up)."""
    out = copy.deepcopy(scene)
    entity = find_entity(out, entity_id)
    entity["x"], entity["y"] = round(float(x), 2), round(float(y), 2)
    return out


def rename_entity(scene: Doc, entity_id: str, name: str) -> Doc:
    """Rename an object; a speaker who used the old name follows."""
    name = str(name).strip()
    if not name:
        raise OpError("A name can't be empty.")
    out = copy.deepcopy(scene)
    entity = find_entity(out, entity_id)
    old = entity.get("name")
    entity["name"] = name
    # A person called "Elder" should introduce themselves as Elder, unless the
    # speaker was deliberately set to something else.
    dialogue = _dialogue_doc(entity)
    if dialogue is not None and dialogue.get("speaker") in (None, "", old):
        dialogue["speaker"] = name
    return _checked(scene, out)


# --- behaviours -----------------------------------------------------------------------------


def behaviour_catalog() -> list[Doc]:
    """Every registered behaviour with its editable fields, for an "Add Behaviour" picker."""
    load_builtin_behaviours()
    return [
        {"name": info.name, "description": info.description, "fields": list(info.config_fields)}
        for info in sorted(list_behaviours(), key=lambda i: i.name)
    ]


def _fields(behaviour: str) -> dict[str, Doc]:
    load_builtin_behaviours()
    info = get_behaviour_info(behaviour)
    if info is None:
        raise OpError(f"Unknown behaviour '{behaviour}'.")
    return {f["name"]: f for f in info.config_fields}


def entity_behaviours(entity: Doc) -> list[str]:
    names = []
    for entry in entity.get("behaviours") or []:
        name = entry if isinstance(entry, str) else (entry.get("type") if isinstance(entry, dict) else None)
        if name:
            names.append(str(name))
    return names


def add_behaviour(scene: Doc, entity_id: str, behaviour: str) -> Doc:
    """Give an object a behaviour (see list_behaviours), with that behaviour's default settings."""
    fields = _fields(behaviour)
    out = copy.deepcopy(scene)
    entity = find_entity(out, entity_id)
    if behaviour in entity_behaviours(entity):
        raise OpError(f"This object already has {behaviour}.")
    entity.setdefault("behaviours", []).append(behaviour)
    config = entity.setdefault("behaviour_config", {}).setdefault(behaviour, {})
    for name, spec in fields.items():
        if name not in config and spec.get("default") is not None:
            config[name] = copy.deepcopy(spec["default"])
    return _checked(scene, out)


def remove_behaviour(scene: Doc, entity_id: str, behaviour: str) -> Doc:
    """Take a behaviour (and its settings) off an object."""
    out = copy.deepcopy(scene)
    entity = find_entity(out, entity_id)
    if behaviour not in entity_behaviours(entity):
        raise OpError(f"This object doesn't have {behaviour}.")
    entity["behaviours"] = [b for b in entity.get("behaviours") or [] if (b if isinstance(b, str) else b.get("type")) != behaviour]
    (entity.get("behaviour_config") or {}).pop(behaviour, None)
    return out


def coerce_field(spec: Doc, value: Any) -> Any:
    kind = spec.get("type")
    try:
        if kind == "bool":
            return value if isinstance(value, bool) else str(value).strip().lower() in {"1", "true", "yes", "on"}
        if kind == "int":
            return int(float(value))
        if kind == "float":
            return float(value)
        if kind == "string":
            return str(value)
        if kind == "array" and isinstance(value, str):
            text = value.strip()
            if text.startswith(("[", "{")):  # structured (JSON) text
                return json.loads(text)
            if is_point_list(spec):
                return points_from_text(text)
            return [part.strip() for part in text.split(",") if part.strip()]  # "a, b" -> ["a", "b"]
    except (TypeError, ValueError) as exc:
        raise OpError(f"'{spec.get('name')}' needs a {kind}, not '{value}'.") from exc
    return value


def is_point_list(spec: Doc) -> bool:
    """A setting that is a list of {x, y} points (patrol waypoints and the like)."""
    return spec.get("type") == "array" and "{x,y}" in str(spec.get("description", "")).replace(" ", "")


def points_from_text(text: str) -> list[Doc]:
    """``"100,200; 300,200"`` -> ``[{"x": 100, "y": 200}, {"x": 300, "y": 200}]`` (any separators between numbers)."""
    numbers = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", text)]
    if len(numbers) % 2:
        raise OpError("Write points as x,y pairs, like: 100,200; 300,200")
    return [{"x": numbers[i], "y": numbers[i + 1]} for i in range(0, len(numbers), 2)]


def points_text(value: Any) -> str:
    return "; ".join(f"{p.get('x', 0):g},{p.get('y', 0):g}" for p in value or [] if isinstance(p, dict))


def set_behaviour_param(scene: Doc, entity_id: str, behaviour: str, param: str, value: Any) -> Doc:
    """Set one setting of one of the object's behaviours (checked against the behaviour's fields)."""
    fields = _fields(behaviour)
    if param not in fields:
        raise OpError(f"{behaviour} has no setting called '{param}'.")
    out = copy.deepcopy(scene)
    entity = find_entity(out, entity_id)
    if behaviour not in entity_behaviours(entity):
        raise OpError(f"This object doesn't have {behaviour}.")
    entity.setdefault("behaviour_config", {}).setdefault(behaviour, {})[param] = coerce_field(fields[param], value)
    return _checked(scene, out)


# --- dialogue -------------------------------------------------------------------------------


def _dialogue_doc(entity: Doc) -> Doc | None:
    config = (entity.get("behaviour_config") or {}).get("Dialogue")
    if not isinstance(config, dict):
        return None
    dialogue = config.get("dialogue")
    return dialogue if isinstance(dialogue, dict) else None


def dialogue_text(entity: Doc) -> str:
    """The first thing a person says (the dialogue's start node)."""
    dialogue = _dialogue_doc(entity) or {}
    nodes = dialogue.get("nodes") or {}
    node = nodes.get(dialogue.get("start") or "root") or {}
    if isinstance(node, dict) and node.get("text") is not None:
        return str(node["text"])
    lines = ((entity.get("behaviour_config") or {}).get("Dialogue") or {}).get("dialogue_lines")
    return "\n".join(str(line) for line in lines) if isinstance(lines, list) else ""


def set_dialogue_text(scene: Doc, entity_id: str, text: str) -> Doc:
    """Set what the object says first (its conversation's opening line), creating the conversation if needed."""
    out = copy.deepcopy(scene)
    entity = find_entity(out, entity_id)
    if "Dialogue" not in entity_behaviours(entity):
        entity.setdefault("behaviours", []).append("Dialogue")
    config = entity.setdefault("behaviour_config", {}).setdefault("Dialogue", {})
    dialogue: Doc | None = config.get("dialogue") if isinstance(config.get("dialogue"), dict) else None
    if dialogue is None:
        dialogue = config["dialogue"] = {"speaker": entity.get("name") or "", "start": "root", "nodes": {}}
    start = str(dialogue.setdefault("start", "root"))
    dialogue.setdefault("nodes", {}).setdefault(start, {})["text"] = str(text)
    config.pop("dialogue_lines", None)  # the node graph is now the source of truth
    return _checked(scene, out)


# --- rooms and doors ------------------------------------------------------------------------


def world_rooms(world: Doc) -> list[tuple[str, str, str]]:
    """``(key, label, path)`` for every room registered in the world, start room first."""
    scenes = world.get("scenes") or {}
    rows = [(k, str(v.get("label") or k), str(v.get("path") or "")) for k, v in scenes.items() if isinstance(v, dict)]
    start = world.get("start_scene")
    return sorted(rows, key=lambda row: (row[0] != start, row[1].lower()))


def new_room(world: Doc, label: str, scenes_dir: str, player_template: Doc | None) -> tuple[Doc, Doc, str, str]:
    """Create a room document and register it. Returns ``(world, scene, key, path)``."""
    label = str(label).strip()
    if not label:
        raise OpError("A room needs a name.")
    existing = world.get("scenes") or {}
    if any(str(v.get("label", "")).lower() == label.lower() for v in existing.values() if isinstance(v, dict)):
        raise OpError(f"There is already a room called '{label}'.")
    key, n = slug(label), 2
    while key in existing:
        key, n = f"{slug(label)}_{n}", n + 1
    path = f"{scenes_dir.rstrip('/')}/{key}.json"
    scene: Doc = {"name": label, "schema_version": 1, "version": 1, "entities": []}
    if player_template is not None:
        player = copy.deepcopy(player_template)
        player["x"], player["y"] = 128.0, 128.0
        player["id"] = make_entity_id(key, "player", 128, 128)
        scene["entities"].append(player)
    out = copy.deepcopy(world)
    out.setdefault("scenes", {})[key] = {"label": label, "path": path, "tags": []}
    return out, _checked({"entities": []}, scene), key, path


def link_rooms(
    scene_a: Doc, key_a: str, label_a: str, at_a: tuple[float, float],
    scene_b: Doc, key_b: str, label_b: str, at_b: tuple[float, float],
) -> tuple[Doc, Doc]:
    """Add a walk-in door in each room leading to the other, each with an arrival spot beside it."""
    if key_a == key_b:
        raise OpError("A door has to lead to a different room.")
    out_a, out_b = copy.deepcopy(scene_a), copy.deepcopy(scene_b)
    _add_door(out_a, key_a, at_a, to_key=key_b, to_label=label_b, arrive_as=f"from_{key_b}")
    _add_door(out_b, key_b, at_b, to_key=key_a, to_label=label_a, arrive_as=f"from_{key_a}")
    return _checked(scene_a, out_a), _checked(scene_b, out_b)


def _add_door(scene: Doc, key: str, at: tuple[float, float], *, to_key: str, to_label: str, arrive_as: str) -> None:
    x, y = float(at[0]), float(at[1])
    spawn_into_target = f"from_{key}"
    door = {
        "id": unique_entity_id(scene, make_entity_id(key, f"door_to_{to_key}", x, y)),
        "name": f"Door to {to_label}",
        "tag": "door",
        "x": x,
        "y": y,
        "sprite": DOOR_SPRITE,
        "behaviours": ["SceneTransition"],
        "behaviour_config": {
            "SceneTransition": {
                "target_scene": to_key,
                "spawn_id": spawn_into_target,
                "trigger_on_touch": True,
                "target_tag": "player",
                "allow_interact": False,
            }
        },
    }
    scene.setdefault("entities", []).append(door)
    ax, ay = _arrival_spot(scene, x, y)
    scene["entities"].append({
        "id": unique_entity_id(scene, make_entity_id(key, f"arrival_{to_key}", ax, ay)),
        "name": f"Arrival from {to_label}",
        "tag": "spawn_point",
        "spawn_id": arrive_as,
        "x": ax,
        "y": ay,
    })



def _arrival_spot(scene: Doc, x: float, y: float) -> tuple[float, float]:
    """Where a player coming through the door appears: below it, unless that is off the map (a door near
    the bottom edge put arrivals in the void), then above it, then beside it. Rooms without a map keep below."""
    info = map_info(scene)
    offsets = (ARRIVAL_OFFSET, (0.0, -ARRIVAL_OFFSET[1]), (-ARRIVAL_OFFSET[1], 0.0), (ARRIVAL_OFFSET[1], 0.0))
    if info is None:
        return x + ARRIVAL_OFFSET[0], y + ARRIVAL_OFFSET[1]
    w, h = info["width"] * info["tilewidth"], info["height"] * info["tileheight"]
    margin = max(info["tilewidth"], info["tileheight"])  # keep clear of the border walls
    for dx, dy in offsets:
        ax, ay = x + dx, y + dy
        if margin <= ax <= w - margin and margin <= ay <= h - margin:
            return ax, ay
    return x + ARRIVAL_OFFSET[0], y + ARRIVAL_OFFSET[1]

# --- maps -----------------------------------------------------------------------------------


def map_info(scene: Doc) -> Doc | None:
    """``{width, height, tilewidth, tileheight, layers: {id: tiles}}`` for a room with a map."""
    tilemap = scene.get("tilemap")
    if not isinstance(tilemap, dict) or not isinstance(tilemap.get("tile_layers"), list):
        return None
    layers = {str(layer.get("id")): list(layer.get("tiles") or []) for layer in tilemap["tile_layers"] if isinstance(layer, dict)}
    return {
        "width": int(tilemap["width"]), "height": int(tilemap["height"]),
        "tilewidth": int(tilemap["tilewidth"]), "tileheight": int(tilemap["tileheight"]), "layers": layers,
    }


def map_file_paths(scene_path: str) -> tuple[str, str]:
    """``(project-relative, scene-relative)`` path of a room's map file: ``<pack>/maps/<room>.json``."""
    scene_path = scene_path.replace("\\", "/")
    scene_dir = posixpath.dirname(scene_path)
    name = posixpath.splitext(posixpath.basename(scene_path))[0]
    project_rel = posixpath.join(posixpath.dirname(scene_dir), "maps", f"{name}.json")
    return project_rel, posixpath.relpath(project_rel, scene_dir)


def map_skeleton(map_project_path: str, width: int, height: int, tile: int = TILE_SIZE,
                 tilesets: list[tuple[str, int]] | None = None) -> Doc:
    """The Tiled-format map file for a room: size, tilesets and empty layers (tiles live in the scene).

    ``tilesets`` is ``[(project-relative tileset file, firstgid)]``; the starter tileset by default.
    """
    here = posixpath.dirname(map_project_path)
    return {
        "type": "map", "orientation": "orthogonal", "renderorder": "right-down", "infinite": False,
        "width": width, "height": height, "tilewidth": tile, "tileheight": tile,
        "tilesets": [{"firstgid": gid, "source": posixpath.relpath(src, here)}
                     for src, gid in (tilesets or [(TILESET_SOURCE, 1)])],
        "layers": [
            {"name": name, "type": "tilelayer", "width": width, "height": height, "x": 0, "y": 0,
             "opacity": 1, "visible": True, "data": [0] * (width * height)}
            for name, _z, _collision in MAP_LAYERS
        ],
    }


def add_map(scene: Doc, scene_path: str, *, width: int, height: int, ground: int = 0, border: int = 0,
            tilesets: list[tuple[str, int]] | None = None) -> tuple[Doc, str, Doc]:
    """Give a room a map. Returns ``(scene, map file path, map file document)``."""
    if map_info(scene) is not None:
        raise OpError("This room already has a map.")
    if width < 4 or height < 4 or width > 256 or height > 256:
        raise OpError("A map must be between 4 and 256 tiles on each side.")
    project_rel, scene_rel = map_file_paths(scene_path)
    walls = [0] * (width * height)
    if border:
        for col in range(width):
            walls[col] = walls[(height - 1) * width + col] = border
        for row in range(height):
            walls[row * width] = walls[row * width + width - 1] = border
    tiles = {GROUND: [ground] * (width * height), WALLS: walls, OVERHEAD: [0] * (width * height)}
    out = copy.deepcopy(scene)
    out["tilemap"] = {
        "path": scene_rel, "width": width, "height": height, "tilewidth": TILE_SIZE, "tileheight": TILE_SIZE,
        "collision_layer_id": WALLS,
        "tile_layers": [
            {"id": name, "z": z, "draw": True, "collision": collision, "tiles": tiles[name]}
            for name, z, collision in MAP_LAYERS
        ],
    }
    return _checked(scene, out), project_rel, map_skeleton(project_rel, width, height, tilesets=tilesets)


def resize_map(scene: Doc, width: int, height: int) -> Doc:
    """The room with its map resized; rows and columns are added or cut at the top and right.

    Everything already painted, and every object, keeps its place in the world (the
    world's origin is the map's bottom-left corner).
    """
    if not (4 <= int(width) <= 256 and 4 <= int(height) <= 256):
        raise OpError("A map must be between 4 and 256 tiles on each side.")
    out = copy.deepcopy(scene)
    tilemap = out.get("tilemap")
    if not isinstance(tilemap, dict) or not isinstance(tilemap.get("tile_layers"), list):
        raise OpError("This room has no map yet.")
    old_w, old_h, new_w, new_h = int(tilemap["width"]), int(tilemap["height"]), int(width), int(height)
    shift = new_h - old_h  # rows gained (or lost) at the top
    for layer in tilemap["tile_layers"]:
        old = list(layer.get("tiles") or [0] * (old_w * old_h))
        new = [0] * (new_w * new_h)
        for row in range(old_h):
            if 0 <= row + shift < new_h:
                for col in range(min(old_w, new_w)):
                    new[(row + shift) * new_w + col] = old[row * old_w + col] if row * old_w + col < len(old) else 0
        layer["tiles"] = new
    tilemap["width"], tilemap["height"] = new_w, new_h
    return _checked(scene, out)


def map_size_for(scene: Doc, minimum: tuple[int, int] = (24, 16)) -> tuple[int, int]:
    """A map size (in tiles) that covers every object in the room, with a margin."""
    xs = [float(e.get("x", 0)) for e in entities(scene)] or [0.0]
    ys = [float(e.get("y", 0)) for e in entities(scene)] or [0.0]
    width = max(minimum[0], int(max(xs) // TILE_SIZE) + 4)
    height = max(minimum[1], int(max(ys) // TILE_SIZE) + 4)
    return width, height


def cell_at(info: Doc, x: float, y: float) -> tuple[int, int] | None:
    """The ``(col, row)`` under a world point, or None outside the map. Row 0 is the top row."""
    col = int(x // info["tilewidth"])
    row = int((info["height"] * info["tileheight"] - y) // info["tileheight"])
    if 0 <= col < info["width"] and 0 <= row < info["height"]:
        return col, row
    return None


def cell_center(info: Doc, col: int, row: int) -> tuple[float, float]:
    return ((col + 0.5) * info["tilewidth"], info["height"] * info["tileheight"] - (row + 0.5) * info["tileheight"])


def _map_layer(out: Doc, layer: str) -> tuple[list[int], TilemapDims]:
    tilemap = out.get("tilemap")
    if not isinstance(tilemap, dict) or not isinstance(tilemap.get("tile_layers"), list):
        raise OpError("This room has no map yet.")
    dims = TilemapDims(int(tilemap["width"]), int(tilemap["height"]))
    known = {name: (z, collision) for name, z, collision in MAP_LAYERS}
    if layer in known and not any(isinstance(e, dict) and e.get("id") == layer for e in tilemap["tile_layers"]):
        z, collision = known[layer]  # e.g. OVERHEAD on a map made before that layer existed
        tilemap["tile_layers"].append({"id": layer, "z": z, "draw": True, "collision": collision,
                                       "tiles": [0] * (dims.width * dims.height)})
    try:
        return ensure_tiles_array(get_layer_by_id(tilemap["tile_layers"], layer), dims=dims), dims
    except KeyError as exc:
        raise OpError(f"This map has no '{layer}' layer.") from exc


def paint_tiles(scene: Doc, layer: str, cells: Iterable[tuple[int, int]], tile: int | list[list[int]],
                anchor: tuple[int, int] = (0, 0)) -> Doc:
    """Set ``cells`` on ``layer`` to ``tile`` (0 clears them). Cells outside the map are ignored.

    ``tile`` may be a stamp, rows of gids: each cell then gets the stamp tile at its offset
    from ``anchor``, repeating, so any shape painted with a stamp tiles it seamlessly.
    """
    stamp = tile if isinstance(tile, list) else [[int(tile)]]
    out = copy.deepcopy(scene)
    tiles, dims = _map_layer(out, layer)
    for col, row in cells:
        if 0 <= col < dims.width and 0 <= row < dims.height:
            line = stamp[(row - anchor[1]) % len(stamp)]
            set_tile(tiles, dims=dims, x=col, y=row, tile=int(line[(col - anchor[0]) % len(line)]))
    return _checked(scene, out)


def rect_cells(a: tuple[int, int], b: tuple[int, int]) -> list[tuple[int, int]]:
    """Every cell of the rectangle with corners ``a`` and ``b`` (inclusive), row by row."""
    (c0, c1), (r0, r1) = sorted((a[0], b[0])), sorted((a[1], b[1]))
    return [(c, r) for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)]


def fill_cells(scene: Doc, layer: str, start: tuple[int, int]) -> list[tuple[int, int]]:
    """The area a fill at ``start`` covers: connected cells holding the same tile on ``layer``.

    On the ground layer the fill also stops at walls, so filling a walled room's floor
    stays inside the room, as it looks on screen.
    """
    info = map_info(scene)
    if info is None:
        raise OpError("This room has no map yet.")
    width, height = info["width"], info["height"]
    if not (0 <= start[0] < width and 0 <= start[1] < height):
        return []
    empty = [0] * (width * height)
    tiles = info["layers"].get(layer) or empty
    walls = info["layers"].get(WALLS) or empty
    # On the ground layer a cell's key also says whether a wall stands on it.
    keys = [tile * 2 + (bool(wall) if layer == GROUND else 0) for tile, wall in zip(tiles, walls)]
    col, row = start
    found = flood_fill_indices(keys, width, height, col, row, keys[row * width + col], max_tiles=width * height)
    return [(i % width, i // width) for i in sorted(found)]


# --- tilesets (Tiled tileset files that the map files reference) ---------------------------


def tileset_document(name: str, image_file: str, image_width: int, image_height: int, tile: int = TILE_SIZE) -> Doc:
    """A Tiled tileset file for an image of ``tile``-sized tiles next to it."""
    columns, rows = image_width // tile, image_height // tile
    if columns < 1 or rows < 1:
        raise OpError(f"The image is smaller than one {tile} px tile.")
    return {"type": "tileset", "name": name, "image": image_file, "imagewidth": image_width,
            "imageheight": image_height, "tilewidth": tile, "tileheight": tile, "columns": columns,
            "tilecount": columns * rows, "margin": 0, "spacing": 0}


def map_tilesets(map_doc: Doc, map_project_path: str) -> list[tuple[str, int]]:
    """``[(project-relative tileset file, firstgid)]`` a map file references, in order."""
    here = posixpath.dirname(map_project_path)
    return [(posixpath.normpath(posixpath.join(here, str(e["source"]))), int(e.get("firstgid", 1)))
            for e in map_doc.get("tilesets") or [] if isinstance(e, dict) and e.get("source")]


def with_tileset(map_doc: Doc, map_project_path: str, tileset_project_path: str, tile_counts: dict[str, int]) -> Doc:
    """``map_doc`` also referencing a tileset, after the ones it has, so existing tile ids keep their meaning.

    ``tile_counts`` maps a project-relative tileset file to its tile count.
    """
    current = map_tilesets(map_doc, map_project_path)
    out = copy.deepcopy(map_doc)
    if any(src == posixpath.normpath(tileset_project_path) for src, _ in current):
        return out
    next_gid = max([gid + int(tile_counts.get(src, 0)) for src, gid in current] or [1])
    out["tilesets"] = list(out.get("tilesets") or []) + [
        {"firstgid": next_gid, "source": posixpath.relpath(tileset_project_path, posixpath.dirname(map_project_path))}]
    return out


# =============================================================================================
# Visual event authoring (Milestone 5): pictures, animation, collision, conversations,
# conditions and trigger zones. Each maps a plain idea ("Show when", "Requires flag") onto
# the runtime's existing data: Animator clips, the Dialogue graph, ConditionalActivator,
# PictureByFlags, components.collider and TriggerVolume.
# =============================================================================================

_UNSET: Any = object()


# --- how a door shows (Milestone 12.2) ------------------------------------------------------------
# One door behaviour (SceneTransition); three ways to show it. A door picture; an invisible passage (an area the
# player walks into, outlined only in Studio); or an area over a door, stairs or opening painted on the map. The
# hidden styles keep the picture (hidden: picture_hidden) so choosing "door" again brings it back.
DOOR_STYLES = ("door", "passage", "map_art")
DOOR_STYLE_AREA = {"passage": (64.0, 64.0), "map_art": (32.0, 32.0)}  # a new area's size: a walkway, one tile


def door_style(entity: Doc) -> str:
    """How the door shows: "door" (its picture), "passage" or "map_art"."""
    style = entity.get("door_style")
    return style if style in DOOR_STYLES else "door"


def door_settings(entity: Doc) -> Doc:
    """A door's style, its area (when it has one), and how the player goes through: walking in, pressing E."""
    config = (entity.get("behaviour_config") or {}).get("SceneTransition") or {}
    return {"style": door_style(entity), "width": float(config.get("area_width") or 0),
            "height": float(config.get("area_height") or 0),
            "touch": bool(config.get("trigger_on_touch", False)), "interact": bool(config.get("allow_interact", True))}


def set_door(scene: Doc, entity_id: str, *, style: Any = _UNSET, width: Any = _UNSET, height: Any = _UNSET,
             touch: Any = _UNSET, interact: Any = _UNSET) -> Doc:
    """Change how a door shows and works. ``style``: "door" (a picture; the starter door if it has none),
    "passage" or "map_art" (the picture hidden, an area instead). ``width``/``height``: the area (px).
    ``touch``: walking into it goes through; ``interact``: pressing E beside it does. One of them stays on."""
    out = copy.deepcopy(scene)
    entity = find_entity(out, entity_id)
    config = _behaviour_config(entity, "SceneTransition", create=False)
    if config is None:
        raise OpError("That object isn't a door (it has no SceneTransition).")
    if style is not _UNSET:
        if style not in DOOR_STYLES:
            raise OpError(f"A door shows as one of: {', '.join(DOOR_STYLES)}.")
        if style == "door":
            entity.pop("door_style", None)
            entity.pop("picture_hidden", None)
            entity.setdefault("sprite", DOOR_SPRITE)
            config.pop("area_width", None)
            config.pop("area_height", None)
        else:
            entity["door_style"], entity["picture_hidden"] = style, True
            if not config.get("area_width") or not config.get("area_height"):
                config["area_width"], config["area_height"] = DOOR_STYLE_AREA[style]
    for key, value in (("area_width", width), ("area_height", height)):
        if value is not _UNSET:
            if door_style(entity) == "door":
                raise OpError("A door picture is its own area; choose Invisible passage or Map artwork to size one.")
            config[key] = round(_number(value, "The area's size", 8, 2048), 1)
    if touch is not _UNSET:
        config["trigger_on_touch"] = bool(touch)
    if interact is not _UNSET:
        config["allow_interact"] = bool(interact)
    if not config.get("trigger_on_touch") and not config.get("allow_interact", True):
        raise OpError("A door needs a way through: walking into it, pressing E, or both.")
    return _checked(scene, out)
_FLAG_NAME = re.compile(r"^[A-Za-z0-9_.:-]+$")
DIRECTIONS = ("down", "left", "right", "up")


def _unique_name(scene: Doc, base: str) -> str:
    names, n, name = {e.get("name") for e in entities(scene)}, 2, base
    while name in names:
        name, n = f"{base} {n}", n + 1
    return name


def flag_names(value: Any) -> list[str]:
    """Flag names from a list or comma-separated text, checked: ``"has_shovel, dug"``."""
    items = value.split(",") if isinstance(value, str) else list(value or [])
    names = [str(item).strip() for item in items if str(item).strip()]
    for name in names:
        if not _FLAG_NAME.match(name):
            raise OpError(f"'{name}' can't be a flag name: use letters, digits and _ (like has_shovel).")
    return list(dict.fromkeys(names))


def counter_steps(value: Any) -> dict[str, float]:
    """Counter changes from ``{"name": n}`` or text like ``"graves_opened, gold+5"`` (+1 if no number)."""
    if isinstance(value, dict):
        items = [(str(k), v) for k, v in value.items()]
    else:
        items = []
        for part in (value.split(",") if isinstance(value, str) else value or []):
            match = re.match(r"^\s*([A-Za-z0-9_.:-]+?)\s*(?:([+-])\s*(\d+(?:\.\d+)?))?\s*$", str(part))
            if not match:
                raise OpError(f"'{str(part).strip()}' isn't a counter change: write a name, or name+2.")
            amount = float(match.group(3) or 1) * (-1 if match.group(2) == "-" else 1)
            items.append((match.group(1), amount))
    out: dict[str, float] = {}
    for name, amount in items:
        flag_names([name])
        try:
            out[name] = float(amount)
        except (TypeError, ValueError) as exc:
            raise OpError(f"The change to '{name}' must be a number.") from exc
    return out


def _number(value: Any, what: str, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise OpError(f"{what} must be a number.") from exc
    if not low <= number <= high:
        raise OpError(f"{what} must be between {low:g} and {high:g}.")
    return number


def _behaviour_config(entity: Doc, behaviour: str, *, create: bool) -> Doc | None:
    """The config of one behaviour on ``entity`` (adding the behaviour if ``create``)."""
    if behaviour not in entity_behaviours(entity):
        if not create:
            return None
        entity.setdefault("behaviours", []).append(behaviour)
    root = entity.setdefault("behaviour_config", {})
    config: Doc = root.get(behaviour) if isinstance(root.get(behaviour), dict) else {}
    root[behaviour] = config
    return config


def _drop_behaviour(entity: Doc, behaviour: str) -> None:
    entity["behaviours"] = [b for b in entity.get("behaviours") or []
                            if (b if isinstance(b, str) else (b or {}).get("type")) != behaviour]
    (entity.get("behaviour_config") or {}).pop(behaviour, None)


# --- objects and pictures ---------------------------------------------------------------------


def place_blank(scene: Doc, scene_key: str, name: str, x: float, y: float) -> tuple[Doc, str]:
    """A new object with no picture or behaviours yet: a shovel, a grave, a trigger zone..."""
    out = copy.deepcopy(scene)
    label = _unique_name(out, str(name).strip() or "Object")
    entity_id = unique_entity_id(out, make_entity_id(scene_key, slug(label), x, y))
    out.setdefault("entities", []).append({"id": entity_id, "name": label, "x": round(float(x), 2), "y": round(float(y), 2)})
    return _checked(scene, out), entity_id


def set_picture(scene: Doc, entity_id: str, sprite: str | None, *, follow: bool = False) -> Doc:
    """Give an object a picture (a project-relative image path), or take it away (None).

    Animation settings are never dropped here: taking the picture away and choosing it again
    gets the animation back. The frame-list animation (``animations``/``sprite_sheet``) always
    cuts its frames from the current picture. ``follow=True`` also moves Animator clips that
    used the old picture onto the new one: right when the new sheet has the same frame layout.
    When it doesn't, see ``animation_fit`` and ``reset_animation``.
    """
    out = copy.deepcopy(scene)
    entity = find_entity(out, entity_id)
    old, new = entity.get("sprite"), str(sprite).strip() if sprite else None
    if new:
        entity["sprite"] = new
    else:
        entity.pop("sprite", None)
    if follow and new and old and new != old:
        for clip in ((entity.get("behaviour_config") or {}).get("Animator") or {}).get("animations", {}).values():
            if isinstance(clip, dict) and clip.get("sheet") == old:
                clip["sheet"] = new
    return _checked(scene, out)


def animation_fit(entity: Doc, image_size: Any) -> str | None:
    """Why the object's animation doesn't fit its picture (``image_size`` is (w, h) or None), else None.

    Pure: the caller measures the image. Checks the frame-list animation's grid against the
    picture, and Animator clips that cut frames from a different picture.
    """
    sprite = entity.get("sprite")
    sheet = entity.get("sprite_sheet") if isinstance(entity.get("sprite_sheet"), dict) else None
    if sheet and entity.get("animations") and image_size and sprite:
        need_w = int(sheet.get("frame_width") or 0) * int(sheet.get("columns") or 1)
        need_h = int(sheet.get("frame_height") or 0) * int(sheet.get("rows") or 1)
        if need_w > image_size[0] or need_h > image_size[1]:
            return (f"Its animation expects a {need_w}x{need_h} sheet of {sheet.get('frame_width')}x"
                    f"{sheet.get('frame_height')} frames; this picture is {image_size[0]}x{image_size[1]}.")
    others = sorted({str(c.get("sheet")) for c in animation_clips(entity).values()
                     if isinstance(c, dict) and c.get("sheet") and c.get("sheet") != sprite})
    if others:
        return f"Its animation still shows frames from {', '.join(others)}."
    return None


def animation_use_picture(scene: Doc, entity_id: str) -> Doc:
    """Point every Animator clip at the object's current picture (same frames, new art)."""
    out = copy.deepcopy(scene)
    entity = find_entity(out, entity_id)
    if not entity.get("sprite"):
        raise OpError("Give the object a picture first.")
    for clip in ((entity.get("behaviour_config") or {}).get("Animator") or {}).get("animations", {}).values():
        if isinstance(clip, dict):
            clip["sheet"] = entity["sprite"]
    return _checked(scene, out)


def reset_animation(scene: Doc, entity_id: str) -> Doc:
    """Remove all animation from an object (both kinds), so its picture shows as it is."""
    out = copy.deepcopy(scene)
    entity = find_entity(out, entity_id)
    entity.pop("animations", None)
    entity.pop("sprite_sheet", None)
    _drop_behaviour(entity, "Animator")
    return _checked(scene, out)


def set_look(scene: Doc, entity_id: str, *, scale: Any = _UNSET, flip_x: Any = _UNSET) -> Doc:
    """Set an object's size (scale) and whether its picture is mirrored."""
    fields: dict[str, Any] = {}
    if scale is not _UNSET:
        fields["scale"] = round(_number(scale, "The size", 0.1, 10), 3)
    if flip_x is not _UNSET:
        fields["flip_x"] = True if flip_x else None
    return set_entity_fields(scene, entity_id, **fields)


CHARACTER_TAGS = ("player", "npc")  # cast shadows from lamps unless told not to (light_compositor.CHARACTER_TAGS)


def casts_shadow(entity: Doc) -> bool:
    """Whether the object casts a shadow from lamps: its own setting, else yes for players and NPCs."""
    value = entity.get("cast_shadow")
    if isinstance(value, bool):
        return value
    if isinstance(value, dict) and isinstance(value.get("enabled"), bool):
        return bool(value["enabled"])
    return entity.get("tag") in CHARACTER_TAGS


def has_ground_shadow(entity: Doc) -> bool:
    """Whether the object has the small shadow under it: its own setting, else the default for what it is
    (yes for things on the floor; no for doors, passages, arrival spots and hidden pictures)."""
    from engine.sprite_shadow_model import ground_shadow_default  # noqa: PLC0415

    value = entity.get("shadow_enabled")
    return bool(value) if isinstance(value, bool) else ground_shadow_default(entity)


def set_shadows(scene: Doc, entity_id: str, *, ground: Any = _UNSET, cast: Any = _UNSET, height: Any = _UNSET,
                strength: Any = _UNSET, length: Any = _UNSET) -> Doc:
    """An object's shadows: ``ground`` (the small shadow under its feet) and ``cast`` (its shadow from lamps).

    ``height`` (px; None: from the picture), ``strength`` (0-1, how much of a lamp's light it blocks) and
    ``length`` (a multiplier) tune the cast shadow. Settings left at their defaults are not stored.
    """
    out = copy.deepcopy(scene)
    entity = find_entity(out, entity_id)
    if ground is not _UNSET:
        from engine.sprite_shadow_model import ground_shadow_default  # noqa: PLC0415

        entity.pop("shadow_enabled", None)
        if ground is not None and bool(ground) != ground_shadow_default(entity):
            entity["shadow_enabled"] = bool(ground)  # only what differs from the default is stored
    value = entity.get("cast_shadow")
    settings: Doc = dict(value) if isinstance(value, dict) else ({"enabled": value} if isinstance(value, bool) else {})
    if cast is not _UNSET:
        settings["enabled"] = bool(cast)
    if height is not _UNSET:
        settings["height"] = None if height in (None, "") else round(_number(height, "The height", 4, 1000), 1)
    if strength is not _UNSET:
        settings["strength"] = round(_number(strength, "The strength", 0, 1), 2)
    if length is not _UNSET:
        settings["length"] = round(_number(length, "The length", 0.2, 3), 2)
    default_cast = entity.get("tag") in CHARACTER_TAGS
    if settings.get("enabled") == default_cast:
        settings.pop("enabled")
    for key, default in (("height", None), ("strength", 0.85), ("length", 1.0)):
        if key in settings and settings[key] == default:
            settings.pop(key)
    if settings:
        entity["cast_shadow"] = settings
    else:
        entity.pop("cast_shadow", None)
    return _checked(scene, out)


# --- collision --------------------------------------------------------------------------------

COLLIDER_SHAPES = ("picture", "box", "circle")


def collider_of(entity: Doc, size: tuple[float, float] | None = None) -> Doc:
    """``{"kind": "picture"}``, or a box ``{w, h, offset_x, offset_y}`` or circle ``{r, ...}``.

    An automatic footprint (``auto``) has its numbers for ``size``, the picture's size as shown (32x32 if
    not given), and keeps ``auto: True``.
    """
    raw = (entity.get("components") or {}).get("collider") if isinstance(entity.get("components"), dict) else None
    if not isinstance(raw, dict) or raw.get("kind") not in ("box", "circle"):
        return {"kind": "picture"}
    if raw.get("kind") == "box" and raw.get("auto"):
        return {"kind": "box", "auto": True, **footprint(*(size or (32.0, 32.0)))}
    out: Doc = {"kind": raw["kind"], "offset_x": float(raw.get("offset_x", raw.get("ox", 0)) or 0),
                "offset_y": float(raw.get("offset_y", raw.get("oy", 0)) or 0)}
    if raw["kind"] == "box":
        out.update(w=float(raw.get("w", raw.get("width", 32)) or 32), h=float(raw.get("h", raw.get("height", 32)) or 32))
    else:
        out["r"] = float(raw.get("r", raw.get("radius", 16)) or 16)
    return out


def set_collider(scene: Doc, entity_id: str, kind: str, *, w: Any = 32, h: Any = 16, r: Any = 12,
                 offset_x: Any = 0, offset_y: Any = 0, auto: bool = False) -> Doc:
    """How the object collides: its whole ``picture``, a ``box`` footprint or a ``circle``.

    Footprints let a tall object block where it stands (a tree's trunk, not its canopy). ``auto`` makes a box
    the feet of whatever picture the object has, at whatever size (characters start this way).
    """
    if kind not in COLLIDER_SHAPES:
        raise OpError(f"A collider is one of: {', '.join(COLLIDER_SHAPES)}.")
    entity = find_entity(scene, entity_id)
    components = dict(entity.get("components") or {}) if isinstance(entity.get("components"), dict) else {}
    if kind == "picture":
        components.pop("collider", None)
    elif kind == "box" and auto:
        components["collider"] = {"kind": "box", "auto": True}
    else:
        collider: Doc = {"kind": kind, "offset_x": round(_number(offset_x, "The offset", -4096, 4096), 2),
                         "offset_y": round(_number(offset_y, "The offset", -4096, 4096), 2)}
        if kind == "box":
            collider.update(w=round(_number(w, "The width", 1, 4096), 2), h=round(_number(h, "The height", 1, 4096), 2))
        else:
            collider["r"] = round(_number(r, "The radius", 1, 2048), 2)
        components["collider"] = collider
    return set_entity_fields(scene, entity_id, components=components or None)


def set_solid(scene: Doc, entity_id: str, solid: bool) -> Doc:
    """Whether the object blocks movement (it can still be talked to either way)."""
    return set_entity_fields(scene, entity_id, solid=True if solid else None)


# --- animation (the Animator behaviour) -------------------------------------------------------


def animation_clips(entity: Doc) -> Doc:
    config = (entity.get("behaviour_config") or {}).get("Animator")
    clips = config.get("animations") if isinstance(config, dict) else None
    return copy.deepcopy(clips) if isinstance(clips, dict) else {}


def clip_spec(sheet: str, frame_width: Any, frame_height: Any, columns: int, row: Any, first: Any, count: Any,
              fps: Any, *, flip_x: bool = False, sheet_rows: int | None = None) -> Doc:
    """An Animator clip: ``count`` frames from ``row`` (0 = top), starting at column ``first``."""
    if not str(sheet or "").strip():
        raise OpError("Choose the image the frames come from.")
    fw, fh = int(_number(frame_width, "The frame width", 1, 4096)), int(_number(frame_height, "The frame height", 1, 4096))
    row_n, first_n = int(_number(row, "The row", 0, 4096)), int(_number(first, "The first frame", 0, 4096))
    count_n = int(_number(count, "The number of frames", 1, 4096))
    if sheet_rows is not None and row_n >= sheet_rows:
        raise OpError(f"The image has {sheet_rows} row(s) of frames: rows 0 to {sheet_rows - 1}.")
    if columns >= 1 and first_n + count_n > columns:
        raise OpError(f"That row has {columns} frames: frames {first_n + 1}-{first_n + count_n} don't fit.")
    spec: Doc = {"sheet": str(sheet), "frame_width": fw, "frame_height": fh,
                 "start": row_n * max(1, columns) + first_n, "frames": count_n, "fps": _number(fps, "The speed", 0.1, 120)}
    if flip_x:
        spec["flip_x"] = True
    return spec


def clip_position(clip: Doc, columns: int) -> tuple[int, int]:
    """``(row, first column)`` of a clip's first frame."""
    return divmod(int(clip.get("start", 0) or 0), max(1, int(columns)))


def character_clips(sheet: str, frame_width: Any, frame_height: Any, columns: int, rows: dict[str, Any], *,
                    walk_first: Any = 0, walk_count: Any = 3, idle_first: Any = 0, idle_count: Any = 1,
                    walk_fps: Any = 8, idle_fps: Any = 2, sheet_rows: int | None = None) -> Doc:
    """Idle and walk clips for each of the four directions, from one row per direction.

    A direction without a row (usually ``left``) mirrors ``right``.
    """
    clips: Doc = {}
    for direction in DIRECTIONS:
        row, flip = rows.get(direction), False
        if row in (None, "") and direction == "left":
            row, flip = rows.get("right"), True
        if row in (None, ""):
            raise OpError(f"Which row of frames walks {direction}?")
        clips[f"walk_{direction}"] = clip_spec(sheet, frame_width, frame_height, columns, row, walk_first, walk_count,
                                               walk_fps, flip_x=flip, sheet_rows=sheet_rows)
        clips[f"idle_{direction}"] = clip_spec(sheet, frame_width, frame_height, columns, row, idle_first, idle_count,
                                               idle_fps, flip_x=flip, sheet_rows=sheet_rows)
    return clips


def set_animation(scene: Doc, entity_id: str, clips: Doc) -> Doc:
    """Replace the object's Animator clips (adding the Animator; no clips removes it).

    With idle_ and walk_ clips for all four directions the Animator turns to face the way the
    object moves. The older frame-list animation (entity ``animations``) is dropped: two
    animation systems on one object fight over its picture.
    """
    out = copy.deepcopy(scene)
    entity = find_entity(out, entity_id)
    entity.pop("animations", None)
    if not clips:
        _drop_behaviour(entity, "Animator")
        return _checked(scene, out)
    config = _behaviour_config(entity, "Animator", create=True)
    assert config is not None
    config["animations"] = copy.deepcopy(clips)
    if all(f"{kind}_{d}" in clips for kind in ("idle", "walk") for d in DIRECTIONS):
        facing = config.get("facing_default") if config.get("facing_default") in DIRECTIONS else "down"
        config.update(directional_mode="4-way", enable_auto_state=True, idle_clip="idle_down", walk_clip="walk_down",
                      facing_default=facing, animation_state=f"idle_{facing}", speed_threshold=5.0)
    else:
        config["directional_mode"] = "none"
        if config.get("animation_state") not in clips:
            config["animation_state"] = next(iter(clips))
    return _checked(scene, out)


def set_clip(scene: Doc, entity_id: str, name: str, spec: Doc | None) -> Doc:
    """Add or replace one clip (None removes it)."""
    name = str(name).strip()
    if not name:
        raise OpError("A clip needs a name, like walk_left.")
    clips = animation_clips(find_entity(scene, entity_id))
    if spec is None:
        clips.pop(name, None)
    else:
        clips[name] = copy.deepcopy(spec)
    return set_animation(scene, entity_id, clips)


# --- conversations (the Dialogue behaviour's graph) -------------------------------------------


def conversation(entity: Doc) -> Doc:
    """An object's conversation, ready to show: lines (in order), start rules and options."""
    config = (entity.get("behaviour_config") or {}).get("Dialogue")
    config = config if isinstance(config, dict) else {}
    raw_graph = config.get("dialogue")
    graph: Doc = raw_graph if isinstance(raw_graph, dict) else {}
    raw_nodes = graph.get("nodes")
    nodes: Doc = raw_nodes if isinstance(raw_nodes, dict) else {}
    return {"speaker": str(graph.get("speaker") or entity.get("name") or ""),
            "start": graph.get("start") if graph.get("start") in nodes else next(iter(nodes), None),
            "nodes": copy.deepcopy(nodes), "starts": copy.deepcopy(graph.get("starts") or []),
            "require_flags": list(config.get("require_flags") or []), "forbid_flags": list(config.get("forbid_flags") or []),
            "auto_start": bool(config.get("auto_start")), "once": bool(config.get("once", True)),
            "legacy_lines": [str(x) for x in config.get("dialogue_lines") or [] if isinstance(x, str)] if not nodes else []}


def _graph(entity: Doc) -> tuple[Doc, Doc, Doc]:
    """``(Dialogue config, graph, nodes)`` for editing, creating the Dialogue if needed.

    Old one-list ``dialogue_lines`` become a chain of lines, so nothing typed before is lost.
    """
    fresh = "Dialogue" not in entity_behaviours(entity)
    config = _behaviour_config(entity, "Dialogue", create=True)
    assert config is not None
    if fresh:
        config["once"] = False  # a conversation you can have again; "Only once" turns this on
    graph = config.get("dialogue")
    if not isinstance(graph, dict):
        graph = config["dialogue"] = {"speaker": entity.get("name") or "", "nodes": {}}
    nodes = graph.get("nodes")
    if not isinstance(nodes, dict):
        nodes = graph["nodes"] = {}
    lines = config.pop("dialogue_lines", None)
    if not nodes and isinstance(lines, list):
        previous = None
        for text in [str(x) for x in lines if isinstance(x, (str, int, float)) and str(x).strip()]:
            node_id = _new_line_id(nodes)
            nodes[node_id] = {"text": text}
            if previous:
                nodes[previous]["next"] = node_id
            previous = node_id
    if nodes and graph.get("start") not in nodes:
        graph["start"] = next(iter(nodes))
    return config, graph, nodes


def _new_line_id(nodes: Doc) -> str:
    n = len(nodes) + 1
    while f"line_{n}" in nodes:
        n += 1
    return f"line_{n}"


def _node(nodes: Doc, node_id: str) -> Doc:
    node = nodes.get(node_id)
    if not isinstance(node, dict):
        raise OpError(f"This conversation has no line '{node_id}'.")
    return node


def _target(nodes: Doc, value: Any) -> str | None:
    target = str(value or "").strip()
    if target and target not in nodes:
        raise OpError(f"This conversation has no line '{target}' to go to.")
    return target or None


def add_line(scene: Doc, entity_id: str, *, after: str | None = None, text: str = "...",
             speaker: str | None = None, link: bool = True) -> tuple[Doc, str]:
    """A new line, after ``after`` (spliced into its flow) or at the end of the conversation.

    At the end, the last line runs on into it when it can (no next line, no choices); ``link=False`` adds
    it on its own instead, for an opening or a choice to lead to later.
    """
    out = copy.deepcopy(scene)
    entity = find_entity(out, entity_id)
    _config, graph, nodes = _graph(entity)
    node_id = _new_line_id(nodes)
    node: Doc = {"text": str(text).strip() or "..."}
    if speaker:
        node["speaker"] = str(speaker)
    if after:
        before = _node(nodes, after)
        if before.get("next"):
            node["next"] = before["next"]
        before["next"] = node_id
    elif nodes and link:
        last = next(reversed(nodes))
        if not nodes[last].get("next") and not nodes[last].get("choices"):
            nodes[last]["next"] = node_id
    nodes[node_id] = node
    graph.setdefault("start", node_id)
    return _checked(scene, out), node_id


def set_line(scene: Doc, entity_id: str, node_id: str, *, text: Any = _UNSET, speaker: Any = _UNSET,
             next_line: Any = _UNSET) -> Doc:
    """Edit a conversation line: its words, speaker, and the line that follows (empty: the conversation ends)."""
    out = copy.deepcopy(scene)
    _config, _graph_doc, nodes = _graph(find_entity(out, entity_id))
    node = _node(nodes, node_id)
    if text is not _UNSET:
        if not str(text).strip():
            raise OpError("A line needs some words.")
        node["text"] = str(text).strip()
    if speaker is not _UNSET:
        if str(speaker or "").strip():
            node["speaker"] = str(speaker).strip()
        else:
            node.pop("speaker", None)
    if next_line is not _UNSET:
        target = _target(nodes, next_line)
        if target == node_id:
            raise OpError("A line can't lead to itself.")
        if target:
            node["next"] = target
        else:
            node.pop("next", None)
    return _checked(scene, out)


def remove_line(scene: Doc, entity_id: str, node_id: str) -> Doc:
    """Delete a line; whatever led to it now leads where it led (or ends)."""
    out = copy.deepcopy(scene)
    _config, graph, nodes = _graph(find_entity(out, entity_id))
    removed = _node(nodes, node_id)
    if len(nodes) == 1:
        raise OpError("A conversation needs at least one line. Remove the Dialogue behaviour to remove it.")
    follow = removed.get("next") if removed.get("next") != node_id else None
    del nodes[node_id]
    for node in nodes.values():
        if node.get("next") == node_id:
            if follow:
                node["next"] = follow
            else:
                node.pop("next", None)
        for choice in node.get("choices") or []:
            if isinstance(choice, dict) and choice.get("next") == node_id:
                choice.pop("next", None)
    graph["starts"] = [rule for rule in graph.get("starts") or [] if isinstance(rule, dict) and rule.get("node") != node_id]
    if not graph["starts"]:
        graph.pop("starts")
    if graph.get("start") == node_id:
        graph["start"] = follow if follow in nodes else next(iter(nodes))
    return _checked(scene, out)


def add_choice(scene: Doc, entity_id: str, node_id: str, text: str = "Choice") -> Doc:
    """Add a choice to a conversation line (choices replace the line's 'then' link)."""
    out = copy.deepcopy(scene)
    _config, _graph_doc, nodes = _graph(find_entity(out, entity_id))
    node = _node(nodes, node_id)
    node.pop("next", None)  # with choices, each choice says where the conversation goes
    node.setdefault("choices", []).append({"text": str(text).strip() or "Choice"})
    return _checked(scene, out)


def set_choice(scene: Doc, entity_id: str, node_id: str, index: int, *, text: Any = _UNSET, next_line: Any = _UNSET,
               require_flags: Any = _UNSET, forbid_flags: Any = _UNSET, set_flags: Any = _UNSET,
               clear_flags: Any = _UNSET, add_counters: Any = _UNSET, once: Any = _UNSET) -> Doc:
    """Edit a choice: its words, where it leads, what it needs and what it changes."""
    out = copy.deepcopy(scene)
    _config, _graph_doc, nodes = _graph(find_entity(out, entity_id))
    choices = _node(nodes, node_id).get("choices") or []
    if not 0 <= index < len(choices):
        raise OpError("That choice isn't there any more.")
    choice = choices[index] if isinstance(choices[index], dict) else {"text": str(choices[index])}
    choices[index] = choice
    if text is not _UNSET:
        if not str(text).strip():
            raise OpError("A choice needs some words.")
        choice["text"] = str(text).strip()
    if next_line is not _UNSET:
        target = _target(nodes, next_line)
        if target:
            choice["next"] = target
        else:
            choice.pop("next", None)
    for key, value in (("require_flags", require_flags), ("forbid_flags", forbid_flags), ("clear_flags", clear_flags)):
        if value is not _UNSET:
            names = flag_names(value)
            if names:
                choice[key] = names
            else:
                choice.pop(key, None)
    if set_flags is not _UNSET:
        names = flag_names(set_flags)
        if names:
            choice["set_flags"] = {name: True for name in names}
        else:
            choice.pop("set_flags", None)
    if add_counters is not _UNSET:
        steps = counter_steps(add_counters)
        if steps:
            choice["inc_counters"] = steps
        else:
            choice.pop("inc_counters", None)
    if once is not _UNSET:
        if once:
            choice["once"] = True
        else:
            choice.pop("once", None)
    return _checked(scene, out)


def remove_choice(scene: Doc, entity_id: str, node_id: str, index: int) -> Doc:
    """Remove a conversation line's choice ``index`` (0 is the first)."""
    out = copy.deepcopy(scene)
    _config, _graph_doc, nodes = _graph(find_entity(out, entity_id))
    node = _node(nodes, node_id)
    choices = node.get("choices") or []
    if not 0 <= index < len(choices):
        raise OpError("That choice isn't there any more.")
    del choices[index]
    if not choices:
        node.pop("choices", None)
    return _checked(scene, out)


def set_conversation(scene: Doc, entity_id: str, *, speaker: Any = _UNSET, start: Any = _UNSET, once: Any = _UNSET,
                     auto_start: Any = _UNSET, require_flags: Any = _UNSET, forbid_flags: Any = _UNSET) -> Doc:
    """Conversation-wide options: who speaks, the first line, and when it can happen at all."""
    out = copy.deepcopy(scene)
    config, graph, nodes = _graph(find_entity(out, entity_id))
    if speaker is not _UNSET:
        graph["speaker"] = str(speaker or "").strip()
    if start is not _UNSET:
        target = _target(nodes, start)
        if not target:
            raise OpError("Choose the line the conversation starts with.")
        graph["start"] = target
    if once is not _UNSET:
        config["once"] = bool(once)
    if auto_start is not _UNSET:
        config["auto_start"] = bool(auto_start)
    for key, value in (("require_flags", require_flags), ("forbid_flags", forbid_flags)):
        if value is not _UNSET:
            config[key] = flag_names(value)
    return _checked(scene, out)


def set_start_rules(scene: Doc, entity_id: str, rules: list[Doc]) -> Doc:
    """Opening lines by flags, first match wins: ``[{node, require_flags, forbid_flags}]``."""
    out = copy.deepcopy(scene)
    _config, graph, nodes = _graph(find_entity(out, entity_id))
    clean = []
    for rule in rules:
        target = _target(nodes, rule.get("node"))
        if not target:
            raise OpError("Each opening needs the line it starts with.")
        clean.append({"node": target, "require_flags": flag_names(rule.get("require_flags")),
                      "forbid_flags": flag_names(rule.get("forbid_flags"))})
    if clean:
        graph["starts"] = clean
    else:
        graph.pop("starts", None)
    return _checked(scene, out)


# --- conditions and changing state ------------------------------------------------------------


def show_when(entity: Doc) -> tuple[list[str], list[str]]:
    """``(flags that must be set, flags that must be clear)`` for the object to be there."""
    config = (entity.get("behaviour_config") or {}).get("ConditionalActivator")
    if "ConditionalActivator" not in entity_behaviours(entity) or not isinstance(config, dict):
        return [], []
    return list(config.get("require_flags") or config.get("flags") or []), list(config.get("forbid_flags") or [])


def set_show_when(scene: Doc, entity_id: str, require: Any, forbid: Any) -> Doc:
    """Show the object only while flags allow (hidden objects don't block and can't be used)."""
    need, never = flag_names(require), flag_names(forbid)
    out = copy.deepcopy(scene)
    entity = find_entity(out, entity_id)
    if not need and not never:
        _drop_behaviour(entity, "ConditionalActivator")
    else:
        config = _behaviour_config(entity, "ConditionalActivator", create=True)
        assert config is not None
        config.update(require_flags=need, forbid_flags=never)
        config.pop("flags", None)
    return _checked(scene, out)


def picture_rules(entity: Doc) -> list[Doc]:
    config = (entity.get("behaviour_config") or {}).get("PictureByFlags")
    rules = config.get("pictures") if isinstance(config, dict) else None
    return copy.deepcopy(rules) if isinstance(rules, list) else []


def set_picture_rules(scene: Doc, entity_id: str, rules: list[Doc]) -> Doc:
    """Pictures the object switches to while flags allow: ``[{sprite, require_flags, forbid_flags}]``."""
    clean = []
    for rule in rules:
        sprite = str(rule.get("sprite") or "").strip()
        if not sprite:
            raise OpError("Each picture change needs a picture.")
        clean.append({"sprite": sprite, "require_flags": flag_names(rule.get("require_flags")),
                      "forbid_flags": flag_names(rule.get("forbid_flags"))})
    out = copy.deepcopy(scene)
    entity = find_entity(out, entity_id)
    if not clean:
        _drop_behaviour(entity, "PictureByFlags")
    else:
        config = _behaviour_config(entity, "PictureByFlags", create=True)
        assert config is not None
        config["pictures"] = clean
    return _checked(scene, out)


# --- trigger zones ----------------------------------------------------------------------------


def zone_event(entity_id: str) -> str:
    return f"zone_entered:{entity_id}"


def trigger_zone(entity: Doc) -> Doc | None:
    """The object's enter-zone trigger: size, once, and what entering does; None if it has none."""
    if "TriggerVolume" not in entity_behaviours(entity):
        return None
    configs = entity.get("behaviour_config") or {}
    volume = configs.get("TriggerVolume") or {}
    event = zone_event(str(entity.get("id")))
    dialogue = configs.get("Dialogue") or {}
    state = configs.get("SetGameStateOnEvent") or {}
    sets = list((state.get("set_flags") or {}).keys()) if state.get("event_type") == event else []
    return {"width": float(volume.get("width", 64) or 64), "height": float(volume.get("height", 64) or 64),
            "once": bool(volume.get("one_shot", False)), "set_flags": sets,
            "start_conversation": "Dialogue" in entity_behaviours(entity) and dialogue.get("start_event") == event}


def set_trigger_zone(scene: Doc, entity_id: str, *, width: Any, height: Any, once: bool = True,
                     start_conversation: bool = False, set_flags: Any = ()) -> Doc:
    """Make the object a zone the player walks into: it can start the object's conversation
    and set flags. Uses TriggerVolume (it announces the entry), Dialogue's start_event and
    SetGameStateOnEvent; nothing new runs."""
    w, h = _number(width, "The zone's width", 4, 8192), _number(height, "The zone's height", 4, 8192)
    flags = flag_names(set_flags)
    out = copy.deepcopy(scene)
    entity = find_entity(out, entity_id)
    event = zone_event(entity_id)
    state = (entity.get("behaviour_config") or {}).get("SetGameStateOnEvent")
    if "SetGameStateOnEvent" in entity_behaviours(entity) and isinstance(state, dict) and state.get("event_type") not in (None, "", event):
        raise OpError("This object already changes flags on another event; use a separate object for the zone.")
    volume = _behaviour_config(entity, "TriggerVolume", create=True)
    assert volume is not None
    volume.update(volume_type="rect", width=round(w, 2), height=round(h, 2), target_tags=["player"],
                  on_enter_event=event, on_exit_event=f"zone_left:{entity_id}", one_shot=bool(once), enabled=True)
    dialogue = _behaviour_config(entity, "Dialogue", create=False)
    if start_conversation:
        if dialogue is None:
            raise OpError("Write the conversation first (Dialogue tab), then let the zone start it.")
        dialogue["start_event"] = event
    elif dialogue is not None and dialogue.get("start_event") == event:
        dialogue.pop("start_event", None)
    if flags:
        config = _behaviour_config(entity, "SetGameStateOnEvent", create=True)
        assert config is not None
        config.update(event_type=event, set_flags={name: True for name in flags}, once=bool(once))
    elif "SetGameStateOnEvent" in entity_behaviours(entity):
        _drop_behaviour(entity, "SetGameStateOnEvent")
    return _checked(scene, out)


def remove_trigger_zone(scene: Doc, entity_id: str) -> Doc:
    """Stop the object being a trigger zone (its conversation stays)."""
    out = copy.deepcopy(scene)
    entity = find_entity(out, entity_id)
    event = zone_event(entity_id)
    _drop_behaviour(entity, "TriggerVolume")
    state = (entity.get("behaviour_config") or {}).get("SetGameStateOnEvent") or {}
    if state.get("event_type") == event:
        _drop_behaviour(entity, "SetGameStateOnEvent")
    dialogue = (entity.get("behaviour_config") or {}).get("Dialogue")
    if isinstance(dialogue, dict) and dialogue.get("start_event") == event:
        dialogue.pop("start_event", None)
    return _checked(scene, out)


# --- flags ------------------------------------------------------------------------------------


def flag_uses(rooms: dict[str, tuple[str, Doc]]) -> dict[str, list[str]]:
    """Every flag the project mentions, with where: ``{flag: ["Cemetery: Shovel sets it", ...]}``.

    ``rooms`` maps a room key to ``(label, scene)``. Flags have no separate list: a flag
    exists because something sets or checks it.
    """
    found: dict[str, list[str]] = {}

    def note(flag: Any, where: str) -> None:
        name = str(flag).strip()
        if name and where not in found.setdefault(name, []):
            found[name].append(where)

    def walk(value: Any, where: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in ("require_flags", "forbid_flags", "flags", "forbidden_flags"):
                    for flag in flag_list(item):
                        note(flag, f"{where} checks it")
                elif key in ("set_flags", "clear_flags"):
                    for flag in (item.keys() if isinstance(item, dict) else flag_list(item)):
                        note(flag, f"{where} {'sets' if key == 'set_flags' else 'clears'} it")
                else:
                    walk(item, where)
        elif isinstance(value, list):
            for item in value:
                walk(item, where)

    def flag_list(item: Any) -> list[str]:
        if isinstance(item, str):
            return [part.strip() for part in item.split(",") if part.strip()]
        return [str(x) for x in item] if isinstance(item, list) else []

    for _key, (label, scene) in rooms.items():
        for entity in entities(scene):
            walk({k: v for k, v in entity.items() if k not in ("x", "y")}, f"{label}: {entity.get('name') or 'object'}")
    return dict(sorted(found.items()))


# --- lighting -------------------------------------------------------------------------------
# Room lighting lives in the scene: ``lights`` (point lights the LightManager draws) and three room settings,
# each of which falls back to the project's when the room doesn't set it: ``lighting_enabled``,
# ``lighting_ambient_color`` (how light the room is away from the lamps) and ``lighting_shadows_mode``.

LIGHT_COLOURS: dict[str, str] = {"Warm": "#ffcc88", "White": "#ffffff", "Cold": "#88bbff",
                                 "Red": "#ff5555", "Green": "#66ff77", "Purple": "#bb77ff"}
AMBIENT_PRESETS: dict[str, list[int]] = {"Day": [255, 255, 255, 255], "Dusk": [150, 120, 140, 255],
                                         "Night": [60, 70, 110, 255], "Cave": [30, 30, 40, 255],
                                         "Black": [6, 6, 10, 255]}
FLICKER_DEFAULTS: Doc = {"flicker_amount": 0.2, "flicker_speed": 5.0}  # a torch; amount 0 would not move at all


def lights(scene: Doc) -> list[Doc]:
    value = scene.get("lights")
    return value if isinstance(value, list) else []


def _light(scene: Doc, index: int) -> Doc:
    items = lights(scene)
    if not 0 <= index < len(items) or not isinstance(items[index], dict):
        raise OpError("That light is no longer in this room.")
    return items[index]


def rgb(value: Any) -> list[int]:
    """A colour as ``[r, g, b]``: from ``"#rrggbb"`` or a list (anything else reads as white)."""
    if isinstance(value, str) and len(value.strip().lstrip("#")) == 6:
        try:
            text = value.strip().lstrip("#")
            return [int(text[i:i + 2], 16) for i in (0, 2, 4)]
        except ValueError:
            pass
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        try:
            return [max(0, min(255, int(c))) for c in value[:3]]
        except (TypeError, ValueError):
            pass
    return [255, 255, 255]


def _colour(value: Any) -> str | list[int]:
    if isinstance(value, str) and value in LIGHT_COLOURS:
        return LIGHT_COLOURS[value]
    if isinstance(value, (list, tuple)):
        if len(value) not in (3, 4):
            raise OpError("A colour needs red, green and blue.")
        return [int(_number(c, "Each colour part", 0, 255)) for c in value]
    if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value.strip()):
        return value.strip().lower()
    raise OpError(f"Unknown colour: {value!r}.")


SHADOW_SOFTNESS = ("sharp", "soft", "softer")  # shadow edges (engine/lighting/light_compositor.SOFTNESS)


SHADOW_QUALITY = ("low", "normal", "high")  # soft-edge smoothness against cost (light_compositor.QUALITY_SAMPLES)


def set_room_lighting(scene: Doc, *, enabled: Any = _UNSET, ambient: Any = _UNSET, shadows: Any = _UNSET,
                      softness: Any = _UNSET, edge: Any = _UNSET, shadow_strength: Any = _UNSET, quality: Any = _UNSET,
                      character_shadows: Any = _UNSET) -> Doc:
    """Change the room's lighting settings; ``None`` removes one, so the room follows the project again.

    ``softness`` is how soft shadow edges are: ``"sharp"``, ``"soft"`` or ``"softer"``. Fine-tuning:
    ``edge`` (the soft edge's width, 0-48 px, instead of the preset's), ``shadow_strength`` (0-1: how much
    of a lamp a wall blocks), ``quality`` (``"low"``, ``"normal"``, ``"high"``: smoother soft edges cost
    more) and ``character_shadows`` (whether characters cast shadows from lamps in this room).
    """
    out = copy.deepcopy(scene)
    settings = out.setdefault("settings", {})
    if not isinstance(settings, dict):
        raise OpError("This room's settings aren't readable.")
    if enabled is not _UNSET:
        if enabled is None:
            settings.pop("lighting_enabled", None)
        else:
            settings["lighting_enabled"] = bool(enabled)
    if ambient is not _UNSET:
        if ambient is None:
            settings.pop("lighting_ambient_color", None)
        else:
            value = AMBIENT_PRESETS.get(ambient) if isinstance(ambient, str) else ambient
            if not isinstance(value, (list, tuple)) or len(value) not in (3, 4):
                raise OpError(f"Unknown room light: {ambient!r}.")
            settings["lighting_ambient_color"] = [int(_number(c, "Each colour part", 0, 255)) for c in value[:3]] + [255]
    if shadows is not _UNSET:
        if shadows is None:
            settings.pop("lighting_shadows_mode", None)
        elif shadows in ("hard", "none"):
            settings["lighting_shadows_mode"] = shadows
        else:
            raise OpError("Shadows are either 'hard' or 'none'.")
    if softness is not _UNSET:
        if softness is None:
            settings.pop("lighting_shadow_softness", None)
        elif softness in SHADOW_SOFTNESS:
            settings["lighting_shadow_softness"] = softness
            settings.pop("lighting_shadow_edge", None)  # a preset chosen: its own edge again
        else:
            raise OpError("Shadow edges are 'sharp', 'soft' or 'softer'.")
    if edge is not _UNSET:
        if edge is None or edge == "":
            settings.pop("lighting_shadow_edge", None)
        else:
            settings["lighting_shadow_edge"] = round(_number(edge, "The shadow edge", 0, 48), 1)
    if shadow_strength is not _UNSET:
        value = None if shadow_strength in (None, "") else round(_number(shadow_strength, "The shadow strength", 0, 1), 2)
        if value is None or value == 1.0:
            settings.pop("lighting_shadow_strength", None)  # full strength is the default
        else:
            settings["lighting_shadow_strength"] = value
    if quality is not _UNSET:
        if quality is None or quality == "normal":
            settings.pop("lighting_shadow_quality", None)  # normal is the default
        elif quality in SHADOW_QUALITY:
            settings["lighting_shadow_quality"] = quality
        else:
            raise OpError("Shadow quality is 'low', 'normal' or 'high'.")
    if character_shadows is not _UNSET:
        if character_shadows is None or character_shadows is True:
            settings.pop("lighting_character_shadows", None)  # on is the default
        else:
            settings["lighting_character_shadows"] = False
    return _checked(scene, out)


def add_light(scene: Doc, x: float, y: float, *, color: Any = "Warm", radius: Any = 160) -> tuple[Doc, int]:
    """Place a point light; returns the scene and the new light's index."""
    out = copy.deepcopy(scene)
    if not isinstance(out.get("lights"), list):
        out["lights"] = []
    out["lights"].append({"x": float(round(x)), "y": float(round(y)), "radius": _number(radius, "Size", 8, 4000),
                          "color": _colour(color), "mode": "soft"})
    return _checked(scene, out), len(out["lights"]) - 1


def set_light(scene: Doc, index: int, *, x: Any = _UNSET, y: Any = _UNSET, radius: Any = _UNSET, color: Any = _UNSET,
              flicker_enabled: Any = _UNSET, flicker_amount: Any = _UNSET, flicker_speed: Any = _UNSET,
              enabled: Any = _UNSET, shadows: Any = _UNSET, flicker: Any = _UNSET, flicker_strength: Any = _UNSET,
              flicker_brightness: Any = _UNSET, flicker_reach: Any = _UNSET, flicker_irregularity: Any = _UNSET,
              mode: Any = _UNSET) -> Doc:
    """Change a light: position, size (radius), colour (a name, "#rrggbb" or [r, g, b]), flicker, on/off,
    whether walls block it (``shadows``; on unless set off, when the room has shadows on), and its falloff
    (``mode``: "soft" or "hard").

    ``flicker`` is a preset: "steady" (none), "candle", "torch", "fire", "faulty" or "custom";
    ``flicker_strength`` scales it (1 = as the preset). Custom flicker: ``flicker_speed`` (wavers a
    second), ``flicker_brightness`` (0-1), ``flicker_reach`` (0-0.5), ``flicker_irregularity`` (0-1).
    Changing one of those on a named preset makes a custom copy of it. ``flicker_enabled`` alone (from before
    presets) still works: on fills in a torch-like amount and speed if the light has none. Anything else the
    light carries (keys from older editors) is kept.
    """
    from engine.lighting.flicker import FLICKER_NAMES, FLICKER_PRESETS, FLICKER_RANGES  # noqa: PLC0415

    fields = {"x": x, "y": y, "radius": radius, "color": color, "flicker_enabled": flicker_enabled,
              "flicker_amount": flicker_amount, "enabled": enabled, "shadows": shadows}
    out = copy.deepcopy(scene)
    light = _light(out, index)
    if mode is not _UNSET:
        if mode not in ("soft", "hard"):
            raise OpError("A light's mode is 'soft' or 'hard'.")
        light["mode"] = mode
    if flicker is not _UNSET:
        if flicker not in FLICKER_NAMES:
            raise OpError(f"Flicker is one of: {', '.join(FLICKER_NAMES)}.")
        light["flicker_enabled"] = flicker != "steady"
        if flicker != "steady":
            if (flicker == "custom" and light.get("flicker_preset") in FLICKER_PRESETS
                    and "flicker_brightness" not in light):  # a custom of the owner's own is kept
                _custom_from(light, FLICKER_PRESETS[light["flicker_preset"]])
            light["flicker_preset"] = flicker
    custom = {"speed": flicker_speed, "brightness": flicker_brightness, "reach": flicker_reach,
              "irregularity": flicker_irregularity}
    if any(value is not _UNSET for value in custom.values()):
        if light.get("flicker_preset") in FLICKER_PRESETS:  # tuning a preset: a custom copy of it
            _custom_from(light, FLICKER_PRESETS[light["flicker_preset"]])
            light["flicker_preset"] = "custom"
        for name, value in custom.items():
            if value is not _UNSET:
                low, high = FLICKER_RANGES[name]
                light[f"flicker_{name}"] = round(_number(value, f"Flicker {name}", low, high), 3)
    if flicker_strength is not _UNSET:
        light["flicker_strength"] = round(_number(flicker_strength, "Flicker strength", 0, 3), 2)
        if light["flicker_strength"] == 1.0:
            light.pop("flicker_strength")
    for key, value in fields.items():
        if value is _UNSET:
            continue
        if key in ("x", "y"):
            light[key] = float(round(_number(value, key, -100000, 100000)))
        elif key == "radius":
            light[key] = float(round(_number(value, "Size", 8, 4000)))
        elif key == "color":
            light["color"] = _colour(value)
            light.pop("color_rgba", None)  # an older editor's override would hide the new colour
        elif key == "shadows":
            if value:
                light.pop("shadows", None)  # the default: no key, as older lights have
            else:
                light["shadows"] = False
        elif key in ("flicker_enabled", "enabled"):
            light[key] = bool(value)
            if key == "flicker_enabled" and value:
                for name, default in FLICKER_DEFAULTS.items():
                    if not light.get(name):
                        light[name] = default
        elif key == "flicker_amount":
            light[key] = _number(value, "Flicker amount", 0, 1)
    return _checked(scene, out)


def _custom_from(light: Doc, profile: Any) -> None:
    """Write a preset's values into the light's custom flicker settings (so "custom" starts from it)."""
    light["flicker_speed"] = profile.speed
    light["flicker_brightness"] = profile.brightness
    light["flicker_reach"] = profile.reach
    light["flicker_irregularity"] = profile.irregularity


def flicker_name(light: Doc) -> str:
    """The light's flicker as the Lighting panel names it: a preset, "custom", or "steady"."""
    if not light.get("flicker_enabled"):
        return "steady"
    preset = light.get("flicker_preset")
    return preset if isinstance(preset, str) and preset not in ("", "steady") else "custom"


def duplicate_light(scene: Doc, index: int, *, dx: float = 32, dy: float = -32) -> tuple[Doc, int]:
    """Copy a light a little to the side; returns the scene and the copy's index."""
    out = copy.deepcopy(scene)
    copied = copy.deepcopy(_light(out, index))
    copied.pop("id", None)
    copied["x"], copied["y"] = float(copied.get("x", 0)) + dx, float(copied.get("y", 0)) + dy
    out["lights"].append(copied)
    return _checked(scene, out), len(out["lights"]) - 1


def remove_light(scene: Doc, index: int) -> Doc:
    """Delete a light (later lights move down one index)."""
    out = copy.deepcopy(scene)
    _light(out, index)
    del out["lights"][index]
    return _checked(scene, out)


# --- the shared player ----------------------------------------------------------------------
# A game has one player. Each room keeps only where its player starts (a thin ``{"id", "x", "y",
# "prefab_id": "player"}`` entity) and the definition (picture, size, collision, behaviours, animation)
# is the project's ``player`` prefab in ``assets/prefabs.json``, which the runtime already resolves.
# Rooms are expanded for editing (the player looks like any object to the ops) and split again when stored.

PLAYER_PREFAB = "player"
ROOM_PLAYER_FIELDS = ("id", "x", "y")  # what a room decides about its player; everything else is shared


def shared_player_ids(scene: Doc) -> list[str]:
    """Ids of the room's entities that are the shared player."""
    return [str(e["id"]) for e in entities(scene) if e.get("prefab_id") == PLAYER_PREFAB and e.get("id")]


def thin_player(entity: Doc) -> Doc:
    """A room's reference to the shared player: where it starts, nothing else."""
    out: Doc = {key: copy.deepcopy(entity[key]) for key in ROOM_PLAYER_FIELDS if key in entity}
    out["prefab_id"] = PLAYER_PREFAB
    return out


def player_definition(entity: Doc) -> Doc:
    """What every room's player shares: the entity without its room-specific fields."""
    return {k: copy.deepcopy(v) for k, v in entity.items() if k not in ROOM_PLAYER_FIELDS and k != "prefab_id"}


def expand_players(scene: Doc, definition: Doc | None) -> Doc:
    """The room as an editor sees it: each shared-player reference filled in from ``definition``."""
    ids = shared_player_ids(scene)
    if not ids or definition is None:
        return scene
    out = copy.deepcopy(scene)
    out["entities"] = [{**copy.deepcopy(definition), **{k: e[k] for k in ROOM_PLAYER_FIELDS if k in e}}
                       if e.get("id") in ids and e.get("prefab_id") == PLAYER_PREFAB else e for e in entities(out)]
    return out


def split_players(scene: Doc, ids: Iterable[str]) -> tuple[Doc, Doc | None]:
    """Undo ``expand_players`` after an edit: ``(room with thin references, the player's definition or None)``.

    The definition comes back as the edited player has it, so changing the player's picture in any room
    changes the one definition every room uses.
    """
    wanted = set(ids)
    definition: Doc | None = None
    out = copy.deepcopy(scene)
    rebuilt = []
    for entity in entities(out):
        if entity.get("id") in wanted and entity.get("prefab_id") != PLAYER_PREFAB:
            definition = player_definition(entity)
            entity = thin_player(entity)
        rebuilt.append(entity)
    out["entities"] = rebuilt
    return out, definition


def legacy_player(scene: Doc) -> Doc | None:
    """A room's own full player entity (the pre-sharing layout), or None."""
    return next((e for e in entities(scene) if e.get("tag") == "player" and not e.get("prefab_id")), None)


_FIELD_LABELS = {"sprite": "picture", "scale": "size", "flip_x": "mirroring", "components": "collision",
                 "solid": "collision", "sprite_sheet": "animation", "animations": "animation", "behaviours": "behaviours",
                 "behaviour_config": "behaviour settings", "name": "name", "tag": "tag"}


def player_differences(players: dict[str, Doc], reference: str) -> dict[str, list[str]]:
    """For each room whose player differs from ``reference``'s: what differs, in words (picture, size...)."""
    base = player_definition(players[reference])
    out: dict[str, list[str]] = {}
    for key, entity in players.items():
        if key == reference:
            continue
        other = player_definition(entity)
        labels = sorted({_FIELD_LABELS.get(k, k) for k in set(base) | set(other) if base.get(k) != other.get(k)})
        if labels:
            out[key] = labels
    return out


def player_prefab_entry(definition: Doc) -> Doc:
    """The ``assets/prefabs.json`` entry that holds the shared player."""
    return {"id": PLAYER_PREFAB, "display_name": str(definition.get("name") or "Player"), "tags": ["player"],
            "metadata": {"shared_player": True, "note": "the game's player: every room uses it"},
            "entity": copy.deepcopy(definition)}
