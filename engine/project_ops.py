"""Validated operations on Mesh project documents (scenes and the world file).

This is the one mutation layer for authored content: the Studio editor calls it,
and the AI/CLI layers are meant to call it too. Every operation is pure: it takes
documents, returns new documents, and never touches disk or a running game. An
operation that would leave a scene with new validation errors raises OpError
instead, with a message fit to show a user.
"""

from __future__ import annotations

import copy
import posixpath
import re
from typing import Any, Iterable

from engine.ai_ops import build_prefab_entity_definition
from engine.behaviours import load_builtin_behaviours
from engine.behaviours.registry import get_behaviour_info, list_behaviours
from engine.entity_paint_mode import make_entity_id
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


def _checked(before: Doc, after: Doc) -> Doc:
    """Reject an edit that introduces validation errors the scene didn't already have."""
    new = [e for e in scene_errors(after) if e not in set(scene_errors(before))]
    if new:
        raise OpError(new[0])
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


def remove_entity(scene: Doc, entity_id: str) -> Doc:
    find_entity(scene, entity_id)
    out = copy.deepcopy(scene)
    out["entities"] = [e for e in entities(out) if e.get("id") != entity_id]
    return out


def move_entity(scene: Doc, entity_id: str, x: float, y: float) -> Doc:
    out = copy.deepcopy(scene)
    entity = find_entity(out, entity_id)
    entity["x"], entity["y"] = round(float(x), 2), round(float(y), 2)
    return out


def rename_entity(scene: Doc, entity_id: str, name: str) -> Doc:
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
    except (TypeError, ValueError) as exc:
        raise OpError(f"'{spec.get('name')}' needs a {kind}, not '{value}'.") from exc
    return value


def set_behaviour_param(scene: Doc, entity_id: str, behaviour: str, param: str, value: Any) -> Doc:
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
    out = copy.deepcopy(scene)
    entity = find_entity(out, entity_id)
    if "Dialogue" not in entity_behaviours(entity):
        entity.setdefault("behaviours", []).append("Dialogue")
    config = entity.setdefault("behaviour_config", {}).setdefault("Dialogue", {})
    dialogue = config.get("dialogue") if isinstance(config.get("dialogue"), dict) else None
    if dialogue is None:
        dialogue = config["dialogue"] = {"speaker": entity.get("name") or "", "start": "root", "nodes": {}}
    start = dialogue.setdefault("start", "root")
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
    ax, ay = x + ARRIVAL_OFFSET[0], y + ARRIVAL_OFFSET[1]
    scene["entities"].append({
        "id": unique_entity_id(scene, make_entity_id(key, f"arrival_{to_key}", ax, ay)),
        "name": f"Arrival from {to_label}",
        "tag": "spawn_point",
        "spawn_id": arrive_as,
        "x": ax,
        "y": ay,
    })


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
