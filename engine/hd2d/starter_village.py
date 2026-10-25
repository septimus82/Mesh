"""The HD-2D RPG project template (Milestone 16 Stage 6A, developer-only until its distribution gate passes): a small
playable village made from Mesh's HD-2D starter kit, built with the same validated operations as Mesh Studio.

What a new project gets:

- the starter kit in its model catalogue (``assets/hd2d_starter``, copied by ``engine.hd2d.catalog.install_kit``):
  buildings, wall and roof modules, platforms, stairs, a bridge, path tiles and props, each with its picture;
- **Village** (the start room, 40 x 32 m): two 2 m plateaus joined by a bridge you can walk across or under, a
  staircase up each, a cottage you can walk into (its door leads to the second room), a shop with a shopkeeper,
  lamp posts with lamps, fences, crates and barrels, an elder on the east plateau and a sign by the path;
- **Cottage** (the second room): the inside of the cottage, with a person to talk to and a door back;
- the starter characters (``starter_hero``, ``starter_villager``, ``starter_merchant``; Mesh's own art, see
  docs/starter_art.md), walking in four directions; the Person and Sign objects to place more.

Everything is written relative to the project: no path of the machine that made it.
"""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from typing import Any

from engine import json_io
from engine import project_ops as ops

PX = 32.0  # px per metre
KIT = "assets/hd2d_starter"
GRASS = f"{KIT}/textures/grass.png"
MERCHANT_SHEET = "assets/sprites/starter_merchant.png"
# The game's dialogue and menu sounds: tones synthesised by tooling/generate_sounds.py (Mesh's own).
UI_SOUNDS = tuple(f"assets/sounds/ui_{name}.wav" for name in ("open", "close", "click", "hover"))
START = "packs/core_regions/scenes/start.json"
WORLD = "packs/core_regions/worlds/main.json"
VILLAGE_W, VILLAGE_H = 40, 32  # m (one 32 px tile per metre)
MARGIN = 4.0  # m of grass around the village, so the camera never looks past the ground's edge
FEET_48 = 18.0  # px: a 48 px character's feet are this far below its centre (engine.physics_runtime.footprint)
FEET_32 = 12.0  # ... and a 32 px sign's

# (id, model, x m, y m, turn degrees): the village's structures, placed in this order.
VILLAGE = [
    *[(f"plateau_west_{i + 1}", "platform_4m", 4.0 + 4 * i, 20.0, 0.0) for i in range(3)],
    *[(f"plateau_east_{i + 1}", "platform_4m", 20.0 + 4 * i, 20.0, 0.0) for i in range(3)],
    ("bridge", "bridge_6m", 16.0, 20.0, 0.0),
    ("stairs_west", "stairs", 11.0, 15.0, 0.0),
    ("stairs_east", "stairs", 26.0, 15.0, 0.0),
    ("cottage", "cottage", 6.0, 8.0, 0.0),
    ("shop", "shop", 24.0, 8.0, 0.0),
    *[(f"path_north_{i + 1}", "path_2m", 16.0, 1.0 + 2 * i, 0.0) for i in range(11)],
    *[(f"path_east_west_{i + 1}", "path_2m", x, 3.0, 0.0) for i, x in enumerate(v for v in range(2, 31, 2) if v != 16)],
    ("fence_1", "fence_2m", 3.0, 12.0, 0.0),
    ("fence_2", "fence_2m", 5.0, 12.0, 0.0),
    ("fence_3", "fence_2m", 2.0, 11.0, 90.0),
    ("crate_1", "crate", 20.5, 5.0, 0.0),
    ("crate_2", "crate", 20.5, 6.1, 15.0),
    ("barrel_1", "barrel", 27.6, 5.0, 0.0),
    ("barrel_2", "barrel", 28.5, 5.6, 0.0),
    ("lamp_west", "lamp_post", 13.5, 5.0, 0.0),
    ("lamp_east", "lamp_post", 18.5, 5.0, 0.0),
]


def _read(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _hd2d(width_m: float, height_m: float, *, ground: bool = True, pitch: float = 34.0, distance: float = 15.0,
          ambient: float = 0.45) -> dict[str, Any]:
    out: dict[str, Any] = {"structures": [], "camera": {"pitch": pitch, "fov": 30, "distance": distance, "follow": "player"},
                           "sun": {"direction": [0.35, 0.5, 0.79], "color": "#fff0d8", "intensity": 1.0},
                           "ambient": ambient}
    if ground:
        out["ground"] = {"texture": GRASS, "from": [0, 0], "to": [width_m * PX, height_m * PX]}
    return out


def _map(scene: dict[str, Any], scene_path: str, width: int, height: int, root: Path) -> dict[str, Any]:
    """A plain map of the room's size (Mesh Studio paints on it; HD-2D draws the models, not the tiles)."""
    scene, map_path, skeleton = ops.add_map(scene, scene_path, width=width, height=height, ground=ops.STARTER_GRASS)
    json_io.write_json_atomic(root / map_path, skeleton)
    scene.setdefault("settings", {}).update({"world_width": width * PX, "world_height": height * PX})
    return scene


def _at(x: float, y: float) -> tuple[float, float]:
    """A village position (m, as in VILLAGE) in the room: px, inside the grass margin."""
    return (x + MARGIN) * PX, (y + MARGIN) * PX


def _place(scene: dict[str, Any], sid: str, model: str, x: float, y: float, turn: float = 0.0,
           *, margin: bool = True) -> dict[str, Any]:
    px, py = _at(x, y) if margin else (x * PX, y * PX)
    scene, _sid = ops.place_structure(scene, f"assets/models/{model}.glb", px, py, rotation=turn, structure_id=sid)
    return scene


def _lamp(scene: dict[str, Any], x: float, y: float, height_m: float, colour: str, radius: float,
          *, margin: bool = True) -> dict[str, Any]:
    px, py = _at(x, y) if margin else (x * PX, y * PX)
    scene, index = ops.add_light(scene, px, py, color=colour, radius=radius)
    return ops.set_light(scene, index, elevation=height_m * PX, intensity=1.6)


def _talker(entity: dict[str, Any], name: str, lines: str) -> dict[str, Any]:
    out = copy.deepcopy(entity)  # its own behaviour settings: never another character's
    out["name"] = name
    config = out.setdefault("behaviour_config", {})
    config["Dialogue"] = {"dialogue": {"speaker": name, "start": "root", "nodes": {"root": {"text": lines}}}, "once": False}
    return out


def build(root: Path, engine_root: Path, person: dict[str, Any], sign: dict[str, Any],
          walking: Any, blank_scene: dict[str, Any]) -> None:
    """Write the village into the new project at ``root`` (its base files are already there). ``person`` and
    ``sign`` are the template's Person and Sign entities, ``walking(entity, sheet)`` sets up a walking sheet and
    ``blank_scene`` is a start room with the player."""
    from engine.hd2d import catalog  # noqa: PLC0415  # only the HD-2D template loads the 3D code

    catalog.install_kit(root, engine_root / KIT)
    for rel in (GRASS, f"{KIT}/textures/dirt.png", MERCHANT_SHEET, *UI_SOUNDS):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(engine_root / rel, root / rel)

    # -- the village
    village = json.loads(json.dumps(blank_scene))
    village["name"] = "Village"
    village = _map(village, START, VILLAGE_W, VILLAGE_H, root)
    village["settings"]["hd2d"] = _hd2d(VILLAGE_W, VILLAGE_H)
    village["settings"]["lighting_shadow_softness"] = "soft"
    for sid, model, x, y, turn in VILLAGE:
        village = _place(village, sid, model, x, y, turn)
    village["lights"] = [{"id": "sky", "type": "ambient", "color": "#9aa6d0", "mode": "soft"}]
    for x in (13.5, 18.5):
        village = _lamp(village, x, 5.0, 2.5, "#ffb060", 224)
    player = next(e for e in village["entities"] if e.get("tag") == "player")
    player["x"], player["y"] = _at(16.0, 1.5)
    player["y"] += FEET_48
    elder = _talker(person, "Elder", "Welcome to Mesh Village!\nThe bridge joins the two hills; you can walk under it "
                                     "too.\nThe cottage is open: walk in through its door.")
    elder.update({"id": "start_elder", "x": _at(24.0, 20.0)[0], "y": _at(24.0, 20.0)[1] + FEET_48, "elevation": 2.0 * PX})
    mara = _talker(walking({**person}, MERCHANT_SHEET), "Mara", "Fresh bread and lamp oil!\n"
                                                                "Esc opens the menu: save your game there.")
    mara.update({"id": "start_mara", "x": _at(24.0, 8.5)[0], "y": _at(24.0, 8.5)[1] + FEET_48, "elevation": 0.1 * PX})
    welcome = _talker(sign, "", "Mesh Village\nNorth: the hills and the bridge.  West: the cottage.  East: the shop.")
    welcome.pop("name")
    welcome.update({"id": "start_welcome_sign", "name": "Sign", "x": _at(17.5, 4.5)[0], "y": _at(17.5, 4.5)[1] + FEET_32})
    village["entities"] += [elder, mara, welcome]

    # -- the cottage's inside, a second room with a door each way
    world = _read(root / WORLD)
    world["scenes"]["start"]["label"] = "Village"
    world, inside, inside_key, inside_path = ops.new_room(world, "Cottage", "packs/core_regions/scenes", player)
    inside = _map(inside, inside_path, 16, 12, root)
    inside["settings"]["hd2d"] = _hd2d(16, 12, ground=False, pitch=55.0, distance=10.0, ambient=0.55)
    inside = _place(inside, "room", "interior", 8.0, 6.0, margin=False)
    inside["lights"] = []
    inside = _lamp(inside, 8.0, 7.0, 2.0, "#ffd29a", 200, margin=False)
    tomas = _talker(person, "Tomas", "Make yourself at home.\nThe door behind the table takes you back outside.")
    tomas.update({"id": f"{inside_key}_tomas", "x": 10.0 * PX, "y": 5.0 * PX + FEET_48, "elevation": 0.1 * PX})
    inside["entities"].append(tomas)
    for e in inside["entities"]:
        if e.get("tag") == "player":
            e["x"], e["y"], e["elevation"] = 8.0 * PX, 4.5 * PX + FEET_48, 0.1 * PX
    # A door in the cottage's doorway, and one by the table inside; each arrival spot is 3 m south of its door.
    village, inside = ops.link_rooms(village, "start", "Village", _at(6.0, 5.9), inside, inside_key, "Cottage",
                                     (6.4 * PX, 7.6 * PX))
    for e in inside["entities"]:  # the inside's door and arrival stand on the wooden floor, 0.1 m up
        if e.get("tag") in ("door", "spawn_point"):
            e["elevation"] = 0.1 * PX
    json_io.write_json_atomic(root / START, village)
    json_io.write_json_atomic(root / inside_path, inside)
    json_io.write_json_atomic(root / WORLD, world)
