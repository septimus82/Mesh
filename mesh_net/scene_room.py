"""Server authority for one Mesh scene (N6). Graphics-free: never imports Arcade, pyglet, GameWindow or Studio.

The scene is the file Studio saves. Its authored definitions say what the server simulates:

* the ``tag: "player"`` entity is the template every connected player is spawned from (picture size, collider,
  ``PlayerController.speed``, ``Combat``); it is never simulated itself;
* ``solid`` entities block movement through the engine's own collider shapes and sweep (engine.physics_model);
* ``SwitchInteract`` + ``DoorLock`` sharing an event id are a lever and the gate it opens;
* ``Health`` (+ ``DropTable``) on a ``tag: "enemy"`` entity is an enemy whose HP, death and loot the server owns.

Painted collision tiles block too. Everything else is scenery here. Scenes whose collision this authority cannot
reproduce (collision tiles kept only in a map file, flag-gated objects) are refused at load (:class:`Unsupported`)
rather than simulated differently from single-player.

HD-2D rooms (M1-A-2) walk on the one collision world single-player builds (engine.hd2d.world.build_world, from this
project's files, no GL) through ``World.move`` with this module's Arcade-free sweep (``move``): one floor solver. Each
body's elevation is its ``mesh_entity_data["elevation"]``, as a sprite's. Refused (:func:`hd2d_world`) where this
authority would differ from single-player: a room single-player plays 2D, water that limits walking (owner D4), a
template that can't stand where it is. The room's ``World.collision_digest`` is part of its identity, so a client whose
files give another collision world is refused before it enters (mesh_net.scene_client.check_window_world adds its
window's own world). Snapshots carry each body's elevation and floor (wire v2, mesh_net.protocol); clients place
avatars there and check them against their own world (check_state), never send them.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
from collections.abc import Callable, Iterator
from contextlib import chdir, contextmanager
from dataclasses import dataclass, field
from functools import cache
from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Any

from engine.combat_model import AttackSpec, TargetState, resolve_attack
from engine.interaction import DEFAULT_INTERACT_MAX_DIST
from engine.physics_model import (
    Aabb,
    Circle,
    MoveRequest,
    collider_shape,
    entity_aabb,
    entity_shape,
    shape_aabb,
    shapes_overlap,
    sweep_axis_separate,
)

from . import protocol as wire

if TYPE_CHECKING:  # (2D rooms never load the 3D code)
    from engine.hd2d.world import World

ACTIONS = ("attack", "take", "use")
MAX_OBJECTS = 32  # doors + levers + enemies: keeps a full snapshot inside one frame
BOUND = 100_000.0  # coordinate sanity limit on the wire (x, y and elevation, px)
MAX_FLOOR = 128  # characters in a floor id on the wire
ROUNDING = 0.005  # px: how far a snapshot's x/y (rounded to 0.01 px) may be from the authority's
FLIP_MASK = 0x80000000 | 0x40000000 | 0x20000000  # engine.tilemap.FLIP_MASK (that module needs Arcade)
# The authored defaults of the behaviours read here (their PARAM_DEFS; a test keeps them equal).
SPEED = 150.0
COMBAT = {"damage": 1.0, "cooldown": 1.0, "range": 32.0, "hitbox_size": 32.0, "target_tag": "enemy"}
# The packaged co-op room (tooling/make_coop_scene.py): where each file goes in a project.
COOP_FILES = {"packs/core_regions/scenes/start.json": "scene.json", "packs/core_regions/maps/start.json": "map.json",
              "assets/prefabs.json": "prefabs.json"}
COOP_SCENE = "packs/core_regions/scenes/start.json"
COOP_TILESET = ("assets/tilesets/starter.json", "assets/tilesets/starter.png")
FACINGS = ((1, 0), (0, 1), (-1, 0), (0, -1))  # right, up, left, down: the wire carries the index


class Unsupported(ValueError):
    """The scene asks for something this authority cannot run the way single-player does."""


def config(entity: dict[str, Any], behaviour: str) -> dict[str, Any] | None:
    """A behaviour's settings as the engine builds them (behaviour_config, then the entry's params), or None."""
    found = None
    for entry in entity.get("behaviours") or []:
        name = entry if isinstance(entry, str) else entry.get("type") if isinstance(entry, dict) else None
        if name == behaviour:
            found = entry.get("params") if isinstance(entry, dict) else None
            break
    else:
        return None
    root = entity.get("behaviour_config") or {}
    return {**(root.get(behaviour) or {}), **(found or {})}


def picture_size(entity: dict[str, Any], root: Path) -> tuple[float, float] | None:
    """The size the client's sprite has: the starting Animator frame or the picture, times ``scale``."""
    scale = float(entity.get("scale") or 1.0)
    animator = config(entity, "Animator") or {}
    clips = animator.get("animations") if isinstance(animator.get("animations"), dict) else {}
    if clips:
        clip = clips.get(animator.get("animation_state")) or clips.get(animator.get("idle_clip")) or next(iter(clips.values()))
        try:
            return float(clip["frame_width"]) * scale, float(clip["frame_height"]) * scale
        except (KeyError, TypeError, ValueError) as exc:
            raise Unsupported(f"entity '{entity.get('id')}' has an Animator clip without a frame size") from exc
    if entity.get("animations") or entity.get("sprite_sheet"):
        return None  # frame-list animation: give it a box or circle collider
    sprite = entity.get("sprite")
    if not isinstance(sprite, str) or not sprite:
        return None
    from PIL import Image  # noqa: PLC0415

    from engine.repo_root import bundled_file  # noqa: PLC0415

    path = root / sprite if (root / sprite).is_file() else bundled_file(sprite)
    if path is None:
        return None
    try:
        with Image.open(path) as image:
            return image.width * scale, image.height * scale
    except OSError as exc:
        raise Unsupported(f"entity '{entity.get('id')}' has an unreadable picture '{sprite}'") from exc


@dataclass
class Body:
    """What engine.physics_model reads from a sprite, without a sprite."""

    center_x: float
    center_y: float
    width: float
    height: float
    mesh_entity_data: dict[str, Any]
    mesh_hd2d_floor: str | None = None  # HD-2D: the floor it stands on (World.move sets it; SceneRoom.join first)


def body(entity: dict[str, Any], root: Path) -> Body:
    collider = (entity.get("components") or {}).get("collider") or {}
    explicit = collider.get("kind") in ("box", "circle") and not collider.get("auto")
    size = picture_size(entity, root)
    if size is None and not explicit:
        raise Unsupported(f"entity '{entity.get('id')}' needs a picture or a box/circle collider")
    w, h = size or (0.0, 0.0)
    return Body(float(entity.get("x", 0.0)), float(entity.get("y", 0.0)), w, h, entity)


def move(mover: Body, delta: tuple[float, float], solids: list[Body]) -> None:
    """engine.physics_runtime.move_entity_with_physics for a collider-shaped mover, without Arcade."""
    shape = entity_shape(mover)
    start = shape_aabb(shape)
    radius = shape.radius if isinstance(shape, Circle) else None

    def query(aabb: Aabb) -> list[Aabb]:
        probe = Circle(aabb.x, aabb.y, radius) if radius else aabb
        return [shape_aabb(s) for s in map(entity_shape, solids) if shapes_overlap(probe, s)]

    result = sweep_axis_separate(MoveRequest("player", (start.x, start.y), delta, start), query)
    mover.center_x += result.final_pos[0] - start.x
    mover.center_y += result.final_pos[1] - start.y


@cache
def behaviour_metadata() -> dict[str, Any]:
    """The behaviours scene validation knows, for a process that hasn't loaded them (loading them imports Arcade):
    mesh_net/behaviours.json, engine.behaviours.registry.validation_metadata's copy (a test keeps it current)."""
    data: dict[str, Any] = json.loads(files("mesh_net").joinpath("behaviours.json").read_text(encoding="utf-8"))
    return data


def load_scene(path: Path) -> tuple[str, dict[str, Any]]:
    """The scene with its entities as the engine's loader resolves them (engine.scene_loader.SceneLoader.load_scene:
    an entity that fails ``validate_entity`` is left out, the rest get prefabs and defaults), and the SHA-256 of that.
    A scene single-player would load as its empty fallback (it fails ``validate_scene``) is refused. (A room's
    identity adds the collision geometry its files give: SceneRoom.identity.)"""
    from engine.behaviours.registry import register_validation_metadata  # noqa: PLC0415
    from engine.migrations import migrate_payload  # noqa: PLC0415
    from engine.scene_loader import SceneLoader  # noqa: PLC0415
    from engine.schema_validation import validate  # noqa: PLC0415

    register_validation_metadata(behaviour_metadata())  # (only what isn't registered: loaded behaviours win)
    data = path.read_bytes()
    migrated = migrate_payload("scene", json.loads(data.decode("utf-8")))
    validate(migrated, "scene.schema.json", path)
    loader = SceneLoader()
    scene = loader.apply_scene_defaults(migrated)
    report = loader.validate_scene(scene, validate_entities=False)
    if not report.ok:
        raise Unsupported(f"single-player loads this scene as an empty room: {'; '.join(report.errors)}")
    scene["entities"] = [loader.apply_entity_defaults(e) for i, e in enumerate(scene["entities"])
                         if loader.validate_entity(e, index=i).ok]  # (what single-player keeps, by its own check)
    canonical = json.dumps(scene, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode()).hexdigest(), scene


@contextmanager
def disposable_project(files: dict[str, bytes], name: str = "Mesh local room", scaffold: bool = True) -> Iterator[Path]:
    """A temporary folder holding ``files`` as the current folder and the engine's user/save/project locations,
    for one process's lifetime. ``scaffold``: a whole new Mesh project (Studio's New Project) under them; that
    validates through the behaviour registry, which imports Arcade, so the graphics-free server goes without."""
    with TemporaryDirectory(prefix="mesh-room-") as temp, chdir(temp):
        root = Path(temp)
        paths = {"MESH_USER_DIR": "user", "MESH_RUNTIME_SETTINGS_PATH": "user/settings.json",
                 "MESH_PROJECTS_DIR": "projects", "MESH_PROJECTS_PATH": "user/projects.json",
                 "MESH_SAVE_DIR": "saves", "MESH_REPO_ROOT": "."}
        previous = {name: os.environ.get(name) for name in paths}
        try:
            for key, relative in paths.items():
                os.environ[key] = str(root / relative)
            if scaffold:
                from engine.project_scaffold import create_project  # noqa: PLC0415

                create_project(root, name)
            for rel, data in files.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_bytes(data)
            yield root
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


def coop_files() -> dict[str, bytes]:
    """The packaged co-op room (mesh_net/coop) as project files, with the engine's starter tileset its map uses
    (what every new project holds), so a bare folder is enough for the server."""
    from engine.repo_root import bundled_file  # noqa: PLC0415

    room = {rel: files("mesh_net").joinpath("coop", name).read_bytes() for rel, name in COOP_FILES.items()}
    tileset = {}
    for rel in COOP_TILESET:
        path = bundled_file(rel)
        if path is None:
            raise FileNotFoundError(f"bundled file not installed: {rel}")
        tileset[rel] = path.read_bytes()
    return {**tileset, **room}


def contained(root: Path) -> Callable[[str], Path]:
    """A scene path to the project's file, refused (Hd2dSettingsError) when it lies, links followed, outside the
    project: engine.hd2d.runtime._contained's rule, with the project folder as the one content root."""
    from engine.hd2d.settings import Hd2dSettingsError  # noqa: PLC0415

    base = root.resolve()

    def resolve(rel: str) -> Path:
        path = root / rel
        if not path.resolve().is_relative_to(base):
            raise Hd2dSettingsError(f"'{rel}' lies outside the project's content (a link out of it?)")
        return path

    return resolve


def hd2d_world(scene: dict[str, Any], root: Path) -> World | None:
    """The room's collision world (engine.hd2d.world.World) as single-player builds it, or None for a 2D room.

    engine.hd2d.runtime.configure_scene's lenient parse and its builder (build_world, which reads the models itself),
    from this project's files. Unsupported where this authority would move characters differently from single-player:
    a room single-player plays 2D (its HD-2D block or a structure can't be read; or nothing in it is 3D to walk on, so
    single-player moves it in 2D under a 3D picture), collision single-player sets aside (broken sculpted heights,
    scatter or rivers, an unreadable scatter model), and water that limits walking (``rivers or ponds``, as
    World._wet: owner decision D4)."""
    settings = scene.get("settings") or {}
    raw = settings.get("hd2d")
    if raw is None:  # (engine.hd2d.runtime: any value makes a 3D room)
        return None
    from engine.hd2d.glb import GlbError  # noqa: PLC0415  # (2D rooms never load the 3D code)
    from engine.hd2d.settings import Hd2dSettingsError, parse_hd2d  # noqa: PLC0415
    from engine.hd2d.world import build_world  # noqa: PLC0415

    w, h = settings.get("world_width"), settings.get("world_height")
    map_size = (float(w), float(h)) if isinstance(w, (int, float)) and isinstance(h, (int, float)) else None
    try:
        hd2d = parse_hd2d(raw, map_size_px=map_size, lenient=True)
        world, _models, set_aside = build_world(hd2d, scene["entities"], contained(root))
    except (Hd2dSettingsError, GlbError) as exc:
        raise Unsupported(f"HD-2D room that single-player plays 2D (its 3D build fails): {exc}") from exc
    aside = [e for e in (hd2d.terrain_error, hd2d.scatter_error, hd2d.rivers_error) if e] + list(set_aside.values())
    if aside:
        raise Unsupported(f"HD-2D room whose collision single-player partly sets aside: {'; '.join(aside)}")
    if world is None:
        raise Unsupported("HD-2D room with nothing 3D to walk on (no colliders, sculpted ground or rivers): "
                          "single-player moves it in 2D")
    if world.rivers or world.ponds:
        raise Unsupported("HD-2D room with rivers or ponds that limit walking: water is not run online (owner D4)")
    return world


def refuse_unsupported(scene: dict[str, Any]) -> None:
    for entity in scene["entities"]:
        if entity.get("require_flags") or entity.get("forbid_flags"):  # engine.scene_entity_gating
            raise Unsupported(f"entity '{entity.get('id')}' depends on game flags, which a shared room does not have")


def positive(value: Any) -> float | None:
    """engine.interaction's reading of an authored radius: a finite number above zero, else none."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0.0 else None


def tile_bodies(scene: dict[str, Any], scene_dir: Path) -> list[Body]:
    """The blocking tiles engine.tilemap builds from the scene's painted collision layers (one tile-sized box each).

    Only Studio's inline ``tiles`` grids, and JSON tilesets read as engine.tilemap reads them; anything else (a
    collision layer kept only in the map file, a missing or TSX tileset) is refused."""
    tilemap = scene.get("tilemap")
    if not isinstance(tilemap, dict):
        return []
    blocking = tilemap.get("collision_layer_id")
    layers = [layer for layer in tilemap.get("tile_layers") or tilemap.get("layers") or []
              if isinstance(layer, dict) and (layer.get("collision") or (blocking and _name(layer) == blocking))]
    if not layers:
        return []
    try:
        return _tiles(tilemap, layers, scene_dir)
    except Unsupported:
        raise
    except (OSError, ValueError, KeyError, TypeError) as exc:  # (json.JSONDecodeError is a ValueError)
        raise Unsupported(f"the scene's map or tileset cannot be read as the engine reads it: {exc!r}") from exc


def _name(layer: dict[str, Any]) -> str:
    return str(layer.get("id") or layer.get("name") or layer.get("layer") or "")


def _tiles(tilemap: dict[str, Any], layers: list[dict[str, Any]], scene_dir: Path) -> list[Body]:
    map_path = scene_dir / str(tilemap["path"])
    payload = json.loads(map_path.read_text(encoding="utf-8"))
    if str(payload.get("orientation", "")).lower() != "orthogonal":
        raise Unsupported("the map is not orthogonal (engine.tilemap loads no tiles from it)")
    tw, th = int(payload["tilewidth"]), int(payload["tileheight"])
    tilesets = []  # (first gid, tile count, tile width, tile height), as engine.tilemap._load_tilesets builds them
    for entry in payload.get("tilesets") or []:
        source = entry.get("source")
        if source and not str(source).lower().endswith(".json"):
            raise Unsupported(f"tileset '{source}' is not a JSON tileset")
        data = json.loads((map_path.parent / source).read_text(encoding="utf-8")) if source else entry
        base = (map_path.parent / source).parent if source else map_path.parent
        if (not (base / str(data["image"])).is_file() or int(data["tilecount"]) <= 0
                or int(data.get("imagewidth", 0)) <= 0 or int(data.get("imageheight", 0)) <= 0):
            raise Unsupported(f"tileset '{source or data.get('name')}' lacks a picture, its size or a tile count")
        tilesets.append((int(entry.get("firstgid", 1)), int(data["tilecount"]), int(data["tilewidth"]),
                         int(data["tileheight"])))
    tilesets.sort()
    width, height = int(payload["width"]), int(payload["height"])
    w, h = tilemap.get("width"), tilemap.get("height")
    if isinstance(w, int) and isinstance(h, int) and w > 0 and h > 0:  # the scene's size wins (engine.tilemap)
        width, height = w, h
    offsets = {str(raw.get("name")): (float(raw.get("offsetx", 0.0)), float(raw.get("offsety", 0.0)))
               for raw in payload.get("layers", []) if isinstance(raw, dict)}
    bodies = []
    for layer in layers:
        tiles = layer.get("tiles")
        if not isinstance(tiles, list) or len(tiles) != width * height:
            raise Unsupported(f"collision layer '{_name(layer)}' has no inline tiles of the map's size")
        ox, oy = offsets.get(_name(layer), (0.0, 0.0))
        for index, raw_gid in enumerate(tiles):
            gid = int(raw_gid or 0) & ~FLIP_MASK
            owner = [t for t in tilesets if t[0] <= gid < t[0] + t[1]]
            if not gid or not owner:
                continue  # an empty cell, or a tile no tileset has: engine.tilemap draws and blocks nothing there
            col, row = index % width, index // width
            bodies.append(Body((col + 0.5) * tw + ox, height * th - (row + 0.5) * th + oy, *owner[-1][2:], {}))
    return bodies


@dataclass
class Player:
    body: Body
    dx: float = 0.0
    dy: float = 0.0
    facing: int = 3
    seq: int = 0
    last_input: int = -100
    action: str | None = None
    attack_after: int = 0


@dataclass
class Enemy:
    body: Body
    state: TargetState
    solid: bool
    loot: list[dict[str, Any]] = field(default_factory=list)
    dropped: bool = False  # loot is on the ground
    holder: Player | None = None


class SceneRoom:
    """Same interface as mesh_net.simulation.Room, so mesh_net.server.Server hosts either."""

    def __init__(self, path: Path, root: Path | None = None) -> None:
        root = root or path.parent
        scene_hash, scene = load_scene(path)
        refuse_unsupported(scene)
        self.world = hd2d_world(scene, root)  # HD-2D: the one collision world; None for a 2D room
        self.digest: str | None = self.world.collision_digest() if self.world is not None else None
        self.floor_ids: frozenset[str] = frozenset()  # every floor a body can stand on (a 2D room: none)
        if self.world is not None:
            grounds = {"ground"} if self.world.terrain is not None else set()
            self.floor_ids = frozenset({s.floor for s in self.world.surfaces} | grounds)
            if any(len(f) > MAX_FLOOR for f in self.floor_ids):
                raise Unsupported(f"HD-2D room with a floor id longer than {MAX_FLOOR} characters (the wire's limit): "
                                  "shorter structure ids or collider names")
        entities = scene["entities"]
        ids = [e.get("id") for e in entities]
        if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
            raise Unsupported("every entity needs its own id (Studio gives each one)")
        players = [e for e in entities if e.get("tag") == "player"]
        if len(players) != 1:
            raise Unsupported(f"the scene needs exactly one player template, found {len(players)}")
        template = players[0]
        self.template, self.root = template, root
        self.spawn = (float(template["x"]), float(template["y"]))
        self.size = self._template_size()  # (read once: a client checks every row with it, check_levels)
        if collider_shape(Body(*self.spawn, *self._template_size(), template)) is None:
            raise Unsupported("the player template needs a sized box or circle collider (Studio characters start with "
                              "an automatic one); Arcade's picture hit boxes cannot run without Arcade")
        if not self.stands(Body(*self.spawn, *self._template_size(), template)):
            raise Unsupported(f"HD-2D: the player template '{template['id']}' can't stand where it is at its "
                              "elevation (no floor within a step, or inside a wall or under a low deck)")
        self.step_px = float((config(template, "PlayerController") or {}).get("speed", SPEED)) / wire.HZ
        combat = {**COMBAT, **(config(template, "Combat") or {})}
        self.damage, self.reach, self.hitbox = float(combat["damage"]), float(combat["range"]), float(combat["hitbox_size"])
        self.cooldown = max(1, math.ceil(float(combat["cooldown"]) * wire.HZ))
        self.target_tag = str(combat["target_tag"])

        others = [e for e in entities if e is not template]
        self.levers = {e["id"]: (e, c) for e in others if (c := config(e, "SwitchInteract")) is not None}
        # Sized once here (an unreadable picture is refused now, not mid-game). A lever with no picture can't be
        # used, as engine.interaction._present has it.
        self.lever_sizes = {i: picture_size(e, root) for i, (e, _) in self.levers.items()}
        self.used: set[str] = set()
        self.doors = {e["id"]: (body(e, root) if e.get("solid") else None, c) for e in others
                      if (c := config(e, "DoorLock")) is not None}
        self.locked = {i for i, (_, c) in self.doors.items() if c.get("starts_locked", True)}
        self.enemies: dict[str, Enemy] = {}
        for e in others:
            health = config(e, "Health")
            if health is None or e.get("tag") != self.target_tag:
                continue
            health = {**{k: e[k] for k in ("max_hp", "hp", "invulnerable") if k in e}, **health}  # Health reads both
            hp = float(health.get("max_hp", 1.0))
            state = TargetState(hp=float(health.get("hp", hp)), max_hp=hp, invulnerable=bool(health.get("invulnerable")))
            self.enemies[e["id"]] = Enemy(body(e, root), state, bool(e.get("solid")), roll_drops(config(e, "DropTable")))
        if len(self.levers) + len(self.doors) + len(self.enemies) > MAX_OBJECTS:
            raise Unsupported(f"more than {MAX_OBJECTS} networked objects")
        networked = set(self.levers) | set(self.doors) | set(self.enemies)
        self.scenery = tile_bodies(scene, path.parent) + [body(e, root) for e in others
                                                          if e.get("solid") and e["id"] not in networked]
        self.ids = sorted(e["id"] for e in entities)
        geometry = [[b.center_x, b.center_y, b.width, b.height] for b in self.solids_ever()]
        geometry.append(list(self._template_size()))
        collision = [self.digest] if self.digest is not None else []  # (a 2D room's identity is as before)
        self.identity = hashlib.sha256(json.dumps([scene_hash, geometry, *collision]).encode()).hexdigest()

        self.tick = 0
        self.next_id = 1
        self.players: dict[int, Player] = {}
        try:
            wire.encode({"v": wire.VERSION, **self._worst_snapshot()})
        except wire.Invalid as exc:
            raise Unsupported("the room's largest snapshot would not fit in one frame (shorter ids, fewer objects)") from exc

    # --- sessions (called by mesh_net.server) ---------------------------------------------------------

    def join(self, player: Player | None = None) -> int:
        if len(self.players) >= wire.MAX_PLAYERS:
            raise wire.Invalid("room full")
        if player is None:
            player = Player(Body(*self.spawn, *self._template_size(), dict(self.template)))  # (its own elevation)
        if self.world is not None and player.body.mesh_hd2d_floor is None:  # (a body not yet moved here)
            from engine.hd2d.world import elevation_of  # noqa: PLC0415

            stood = self._stand(player.body, elevation_of(player.body))
            if stood is None:  # (never expected: spawns and arrivals are checked to stand; nothing changed yet)
                raise wire.Invalid("the body can't stand where it joins")
            player.body.mesh_hd2d_floor = stood[1]
        eid, self.next_id = self.next_id, self.next_id + 1
        self.players[eid] = player
        return eid

    def level(self, body: Body) -> tuple[float, str | None]:
        """What the wire says of where ``body`` stands (mesh_net.protocol): its elevation (px) and floor; (0, None)
        in a 2D room."""
        if self.world is None:
            return 0, None
        from engine.hd2d.settings import PIXELS_PER_METRE  # noqa: PLC0415
        from engine.hd2d.world import elevation_of  # noqa: PLC0415

        return round(elevation_of(body) * PIXELS_PER_METRE, 3), body.mesh_hd2d_floor

    def _template_size(self) -> tuple[float, float]:
        return picture_size(self.template, self.root) or (0.0, 0.0)

    def stands(self, body: Body) -> bool:
        """Whether ``body`` can be where it is at its elevation: World.stand asked as World.move asks it (the movement
        box, in metres). Always in a 2D room."""
        if self.world is None:
            return True
        from engine.hd2d.world import elevation_of  # noqa: PLC0415

        return self._stand(body, elevation_of(body)) is not None

    def floors(self, body: Body) -> set[float]:
        """Every elevation (m, to 1 mm) ``body``, centred where it is, could stand at (several under a bridge)."""
        from engine.hd2d.settings import PIXELS_PER_METRE  # noqa: PLC0415

        assert self.world is not None
        box = entity_aabb(body)
        return {round(stood[0], 3) for h, _s in self.world.heights_at(box.x / PIXELS_PER_METRE, box.y / PIXELS_PER_METRE)
                if (stood := self._stand(body, h)) is not None}

    def _stand(self, body: Body, z: float) -> tuple[float, str] | None:
        from engine.hd2d.settings import PIXELS_PER_METRE  # noqa: PLC0415

        assert self.world is not None
        box = entity_aabb(body)
        return self.world.stand(box.x / PIXELS_PER_METRE, box.y / PIXELS_PER_METRE, z, box.w / 2 / PIXELS_PER_METRE,
                                box.h / 2 / PIXELS_PER_METRE)

    def solids_ever(self) -> list[Body]:
        """Everything that can block. The identity covers it, so clients also agree on the room's collision."""
        return self.scenery + [b for b, _ in self.doors.values() if b is not None] + [e.body for e in self.enemies.values()]

    def _worst_snapshot(self) -> wire.Message:
        """The largest snapshot this room can send (ticks and ids at their wire maximum: never reached)."""
        far = -BOUND + 0.01
        floor = max(sorted(self.floor_ids), key=len, default=None)
        return {"type": "scene_state", "tick": wire.MAX_SEQ, "scene": self.identity,
                "players": [[wire.MAX_SEQ - i, far, far, 3, far, floor] for i in range(wire.MAX_PLAYERS)],
                "open": sorted(self.doors), "used": sorted(self.levers),
                "enemies": [[i, e.state.max_hp] for i, e in self.enemies.items()],
                "drops": sorted(self.enemies), "loot": [[i, wire.MAX_SEQ] for i in self.enemies]}

    def leave(self, eid: int) -> Player:
        p = self.players.pop(eid)
        p.dx = p.dy = 0.0
        p.seq, p.last_input, p.action = 0, -100, None
        return p

    def input(self, eid: int, msg: wire.Message) -> None:
        seq, dx, dy, action = parse_input(msg, eid)
        p = self.players[eid]
        if seq > p.seq:
            p.seq, p.last_input = seq, self.tick
            p.dx, p.dy = (dx, dy) if not (dx and dy) else (dx / math.sqrt(2), dy / math.sqrt(2))
            if dx or dy:
                p.facing = FACINGS.index((dx, 0) if abs(dx) >= abs(dy) and dx else (0, dy))
            if p.action is None:
                p.action = action

    # --- simulation -----------------------------------------------------------------------------------

    def solids(self) -> list[Body]:
        doors = [b for i, (b, _) in self.doors.items() if b is not None and i in self.locked]
        alive = [e.body for e in self.enemies.values() if e.solid and not e.state.dead]
        return self.scenery + doors + alive

    def step(self) -> None:
        self.tick += 1
        solids = self.solids()
        for eid, p in sorted(self.players.items()):
            if self.tick - p.last_input <= wire.HZ // 4 and (p.dx or p.dy):
                delta = (p.dx * self.step_px, p.dy * self.step_px)
                if self.world is not None:  # HD-2D: the shared floor solver, its 2D part this module's sweep
                    self.world.move(p.body, delta, solids, sweep=move)
                else:
                    move(p.body, delta, solids)
                # An open map has no edge: stay inside what clients accept on the wire.
                p.body.center_x = max(-BOUND, min(BOUND, p.body.center_x))
                p.body.center_y = max(-BOUND, min(BOUND, p.body.center_y))
            action, p.action = p.action, None
            if action == "use":
                self._use(p)
                solids = self.solids()  # a gate that just opened stops blocking the players after this one
            elif action == "attack" and self.tick >= p.attack_after:
                p.attack_after = self.tick + self.cooldown
                self._attack(p)
                solids = self.solids()
            elif action == "take":
                self._take(p)

    def _near(self, p: Player, x: float, y: float, radius: float = DEFAULT_INTERACT_MAX_DIST) -> float | None:
        d = math.hypot(p.body.center_x - x, p.body.center_y - y)
        return d if d <= radius else None

    def _use(self, p: Player) -> None:
        """engine.interaction.select_interaction_candidate over the levers that may still be used: in reach and not
        behind the player beyond contact distance, ranked by priority, facing, distance, then id."""
        fx, fy = FACINGS[p.facing]
        reach = []
        for lever_id, (entity, cfg) in self.levers.items():
            event = str(cfg.get("event_id") or "")
            size = self.lever_sizes[lever_id]
            if not event or size is None or (cfg.get("one_shot") and lever_id in self.used):
                continue
            authored = positive(entity.get("interact_radius"))
            radius = min(DEFAULT_INTERACT_MAX_DIST, authored) if authored else DEFAULT_INTERACT_MAX_DIST
            dx, dy = float(entity["x"]) - p.body.center_x, float(entity["y"]) - p.body.center_y
            d = math.hypot(dx, dy)
            if d > radius:
                continue
            alignment = (dx * fx + dy * fy) / d if d > 0 else 1.0
            if alignment < 0.0 and d > max(8.0, (max(p.body.width, p.body.height) + max(size)) * 0.5):
                continue
            priority = max((n for v in (entity.get("interaction_priority"), entity.get("interact_priority"))
                            if (n := _int(v)) is not None), default=0)
            reach.append((-priority, -alignment, d, lever_id, event))
        if reach:
            *_, lever_id, event = min(reach)
            self.used.add(lever_id)
            self.locked -= {i for i, (_, c) in self.doors.items() if c.get("unlock_event") == event}  # locked -> open only

    def _attack(self, p: Player) -> None:
        """Combat's hitbox (range ahead, hitbox_size square) against each live enemy's shape; Health's damage rule."""
        fx, fy = FACINGS[p.facing]
        hit = Aabb(p.body.center_x + fx * self.reach, p.body.center_y + fy * self.reach, self.hitbox, self.hitbox)
        for enemy_id, enemy in sorted(self.enemies.items()):
            if enemy.state.dead or not shapes_overlap(hit, entity_shape(enemy.body)):
                continue
            spec = AttackSpec(f"player:{id(p)}", enemy_id, self.damage, 0.0, "combat.default")
            enemy.state, result = resolve_attack(spec, enemy.state)
            if result.target_dead and enemy.loot:
                enemy.dropped = True

    def _take(self, p: Player) -> None:
        for _, enemy in sorted(self.enemies.items()):
            if enemy.dropped and self._near(p, enemy.body.center_x, enemy.body.center_y) is not None:
                enemy.dropped, enemy.holder = False, p
                return

    def snapshot(self) -> wire.Message:
        owner = {id(p): eid for eid, p in self.players.items()}
        return {"v": wire.VERSION, "type": "scene_state", "tick": self.tick, "scene": self.identity,
                "players": [[eid, round(p.body.center_x, 2), round(p.body.center_y, 2), p.facing, *self.level(p.body)]
                            for eid, p in sorted(self.players.items())],
                "open": sorted(set(self.doors) - self.locked), "used": sorted(self.used),
                "enemies": [[i, e.state.hp] for i, e in sorted(self.enemies.items())],
                "drops": sorted(i for i, e in self.enemies.items() if e.dropped),
                "loot": [[i, owner.get(id(e.holder))] for i, e in sorted(self.enemies.items()) if e.holder is not None]}


def _int(value: Any) -> int | None:
    """engine.interaction._read_priority's reading: int(value), never a bool."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def roll_drops(cfg: dict[str, Any] | None) -> list[dict[str, Any]]:
    """What DropTable gives when its enemy dies: the same normalisation, random stream and draws (one roll per drop,
    then its quantity), so a seeded table drops what it drops in single-player."""
    if not cfg:
        return []
    seed = cfg.get("seed")
    rng = random.Random(None if seed == -1 else seed)
    loot = []
    for entry in cfg.get("drops") or []:
        if not isinstance(entry, dict):
            continue
        chance = max(0.0, min(1.0, float(entry.get("chance", 1.0) or 1.0)))
        low = int(entry.get("min_quantity", entry.get("quantity", 1)) or 1)
        high = max(low, int(entry.get("max_quantity", low) or low))
        if chance < 1.0 and (chance <= 0.0 or rng.random() > chance):
            continue
        quantity = rng.randint(low, high)
        if quantity > 0:
            loot.append({"item_id": str(entry["item_id"]).strip() if entry.get("item_id") else None,
                         "gold": int(entry["gold"]) if entry.get("gold") is not None else None, "quantity": quantity})
    return loot


def parse_input(msg: wire.Message, eid: int) -> tuple[int, int, int, str | None]:
    """An input frame from the owner of ``eid``: eight directions and an optional action."""
    optional = ("action",) if "action" in msg else ()
    wire.fields(msg, "input", "entity", "seq", "dx", "dy", *optional)
    action = msg.get("action")
    if action is not None and action not in ACTIONS:
        raise wire.Invalid("unknown action")
    if not wire.integer(msg["entity"], eid, eid) or not wire.integer(msg["seq"], 1):
        raise wire.Invalid("invalid owner or sequence")
    dx, dy = msg["dx"], msg["dy"]
    if not wire.integer(dx, -1, 1) or not wire.integer(dy, -1, 1):
        raise wire.Invalid("direction components are -1, 0 or 1")
    return msg["seq"], dx, dy, action


def _number(value: Any) -> bool:
    """A finite wire number within the coordinate bound (NaN fails every comparison, so it never passes)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and abs(value) <= BOUND


def check_state(msg: wire.Message, scene: str | None = None, room: SceneRoom | None = None) -> None:
    """A client's validation of one scene_state frame (and, given its own scene's identity, that they match; given its
    own room, that every body stands where the client's own collision world says it can: check_levels)."""
    if not isinstance(msg, dict):
        raise wire.Invalid("invalid scene snapshot")
    wire.fields(msg, "scene_state", "tick", "scene", "players", "open", "used", "enemies", "drops", "loot")
    if not wire.integer(msg["tick"], 0) or not isinstance(msg["scene"], str) or len(msg["scene"]) != 64:
        raise wire.Invalid("invalid scene snapshot")
    if scene is not None and msg["scene"] != scene:
        raise wire.Invalid("the server runs a different scene file")
    players = msg["players"]
    if type(players) is not list or len(players) > wire.MAX_PLAYERS:
        raise wire.Invalid("invalid players")
    seen = set()
    for row in players:  # [entity, x, y, facing, elevation, floor] (mesh_net.protocol)
        if (not isinstance(row, list) or len(row) != 6 or not wire.integer(row[0], 1) or row[0] in seen
                or not all(_number(v) for v in (row[1], row[2], row[4])) or not wire.integer(row[3], 0, 3)
                or not (row[5] is None or (isinstance(row[5], str) and 0 < len(row[5]) <= MAX_FLOOR))):
            raise wire.Invalid("invalid player row")
        seen.add(row[0])
    for key in ("open", "used", "drops"):
        if type(msg[key]) is not list or len(msg[key]) > MAX_OBJECTS or not all(isinstance(i, str) for i in msg[key]):
            raise wire.Invalid(f"invalid {key}")
    for key, check in (("enemies", lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0),
                       ("loot", lambda v: v is None or (wire.integer(v, 1) and v in seen))):
        rows = msg[key]
        if type(rows) is not list or len(rows) > MAX_OBJECTS or not all(
                isinstance(r, list) and len(r) == 2 and isinstance(r[0], str) and check(r[1]) for r in rows):
            raise wire.Invalid(f"invalid {key}")
    if room is not None:
        check_levels(players, room)


def check_levels(players: list[Any], room: SceneRoom) -> None:
    """Each (well-formed) row's elevation and floor against the client's own room. A 2D room: elevation 0, no floor.
    An HD-2D room: a floor its collision world has, and one that is there, under the row's feet, within a step
    (World.STEP: what a body standing on it may be off by) of the row's elevation; anything else is inconsistent with
    the world both sides run, and refused (never adjusted). The feet are sampled at the row's x/y and the corners of
    its 0.01 px rounding, so the rounding itself never refuses a floor's own edge."""
    if room.world is None:
        if any(row[4] != 0 or row[5] is not None for row in players):
            raise wire.Invalid("a 2D room's player row carries an elevation or a floor")
        return
    from engine.hd2d.settings import PIXELS_PER_METRE  # noqa: PLC0415
    from engine.hd2d.world import STEP  # noqa: PLC0415

    w, h = room.size
    for row in players:
        floor, z = row[5], row[4] / PIXELS_PER_METRE
        if floor not in room.floor_ids:
            raise wire.Invalid(f"a player row stands on a floor this room does not have: {str(floor)[:48]!r}")
        box = entity_aabb(Body(row[1], row[2], w, h, room.template))
        x, y, r = box.x / PIXELS_PER_METRE, box.y / PIXELS_PER_METRE, ROUNDING / PIXELS_PER_METRE
        if not any(s.floor == floor and abs(height - z) <= STEP + 1e-6
                   for px, py in ((x, y), (x - r, y - r), (x + r, y - r), (x - r, y + r), (x + r, y + r))
                   for height, s in room.world.heights_at(px, py)):
            raise wire.Invalid(f"a player row's floor {floor!r} is not under it at elevation {row[4]:g} px")
