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

Wire v3 (M4-2): each player row adds the input it last consumed (``ack``) and its attack count, each enemy row its hit
count and placement. An attack is Combat's persistent hitbox, server-side (owner decision OD10, :class:`Hitbox`).
Clients show their own swing at once and a hit only once a snapshot confirms it (:class:`Feedback`).

M4-3: the server reads one input a tick (owner decision OD11: DEPTH, HOLD) and walks each body through
:meth:`SceneRoom.walk`, the one movement step; a client predicts its own avatar through the same step and reconciles
it with each snapshot (:class:`Prediction`, owner decision OD3).

M4-4 (owner decision OD7): an enemy that walks a ``FloorRoute`` in an HD-2D room walks it here, each tick, through
engine.hd2d.route.FloorRoute, the one model single-player's behaviour runs (World.path and World.move with this
module's sweep); its row carries where it is now, and hits are judged there. Any other way of moving an enemy, or a
solid, is refused at load (MOVERS): it would stand still here while it walks in single-player.

M4-5 (owner decision of 2026-11-25, OD5): bounded lag compensation. An attack's ``view_tick`` (the tick its window
showed the enemies at: Playback's cursor) has its targets judged where they were then (REWIND_CAP, SceneRoom.history,
SceneRoom._judged_at), the attacker where it stands now; never further back than 300 ms, never ahead, never before the
attacker joined this room instance, never an enemy's pose from another identity. Damage, death, drops and cooldowns
stay this tick's.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
from collections import deque
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
from .playback import between

if TYPE_CHECKING:  # (2D rooms never load the 3D code)
    from engine.hd2d.route import FloorRoute
    from engine.hd2d.world import World

ACTIONS = ("attack", "take", "use")
MAX_OBJECTS = 32  # doors + levers + enemies: keeps a full snapshot inside one frame
BOUND = 100_000.0  # coordinate sanity limit on the wire (x, y and elevation, px)
MAX_FLOOR = 128  # characters in a floor id on the wire
ROUNDING = 0.005  # px: how far a snapshot's x/y (rounded to 0.01 px) may be from the authority's
FLIP_MASK = 0x80000000 | 0x40000000 | 0x20000000  # engine.tilemap.FLIP_MASK (that module needs Arcade)
# The authored defaults of the behaviours read here (their PARAM_DEFS; a test keeps them equal).
SPEED = 150.0
COMBAT = {"damage": 1.0, "cooldown": 1.0, "range": 32.0, "hitbox_size": 32.0, "target_tag": "enemy",
          "attack_anim": "attack", "attack_sound": "assets/sounds/attack.wav"}
HITBOX_S = 0.2  # the hitbox Combat makes lives this long (engine.behaviours.combat: its Hitbox's "duration")
# An attack's COOLDOWN is judged on the tick its client meant it for (the input's ``tick``: Player.attacks), as the
# client judged it, so latency and TCP's bunching never refuse a swing the window showed. A claim older than this many
# ticks when the server reads it is stale: dropped, never run (SceneRoom.stale_attacks counts it); a claim of a tick
# not yet reached counts as now. The claim decides only whether the cooldown has passed: the attack itself, its hitbox,
# hits, damage and death are the server's, on its current geometry and floors, never a past tick's (owner condition 4;
# OD5's separate 300 ms lag-compensation cap, REWIND_CAP, is apart: only an attack's view_tick ever selects a past
# pose, never this claim). The one place the window is set.
# Owner decision 2026-11-24: 600 ms (12 ticks) approved for the cooperative PvE prototype only (docs/plans/
# m4_online_combat.md). Measured (M4-2 "As implemented"; mashing, 3 seeds x 8 sessions, about 900 swings a profile),
# the oldest an honest claim read was 4 ticks at 100 ms RTT +-10 ms, 10 with 1% loss (owner decision OD1's envelope:
# 2 ticks to spare) and 14 at 200 ms with 1% loss (beyond it: 7 of 895 swings stale, counted).
COOLDOWN_CLAIM_WINDOW = 12
# Lag compensation (M4-5; owner decision of 2026-11-25 on OD5, cooperative PvE prototype only): an attack whose input
# carries ``view_tick`` (the tick, a fraction between two, its window showed the enemies at: Playback's cursor when the
# key was read) is judged with its targets where they were then and the attacker where it stands now
# (SceneRoom._judged_at, SceneRoom._rewound). At most this many ticks back (300 ms): an older view is clamped to it. A
# view ahead of this tick, one from before the attacker joined this room instance, or one with REWIND off, is judged
# where the targets are now, as before M4-5 (counted: future_views, unseen_views; clamped_views). Never a hit invented:
# an enemy whose poses for that time are missing, or another identity's (a new Enemy under its id), is judged now.
REWIND_CAP = 6
REWIND = True  # the game's own; mesh_net.server --rewind off (or MESH_NET_REWIND=0) and the probe's --rewind off: none
PENDING = 4  # attacks, and uses or takes, a player may have waiting (one of each is read a tick); more are dropped
# How the server reads inputs (owner decision OD11, M4-3): each tick reads ONE input, the oldest waiting, and walks one
# step with its direction; at most ``depth`` wait (a full queue drops its oldest: the newest direction wins). An input's
# actions wait apart (``attacks``, ``actions``: PENDING each, one of each kind a tick) and run once the tick reads
# their own input or a later one, so a dropped direction never loses an attack, a use or a take. A tick with nothing
# waiting walks only while under ``hold`` ticks from the last input read (its own included): with hold 1, never a step
# no input gave. While the player stands, of two still inputs waiting, the older is dropped (it would walk nowhere, as
# the one after it; its actions run with that one: never a correction). ``drain`` (0: off): whenever more than one
# input has waited ``drain`` ticks in a row, the oldest waiting is dropped (its direction, never its actions): a backlog
# decays, at a one-step correction each, instead of lasting until the player stands. Never a drop that would take the
# inputs still waiting somewhere else than a step from where they lead, or onto another floor (SceneRoom._forks: walked
# both ways through the one step); the count runs on, so a later tick drains instead. Why: a step short beside a fork
# in the floors (the stairs' edge and the landing or ground beside them, where one floor blocks a walk the other
# doesn't) sends the inputs the window replays down the other branch, a correction of many steps with an elevation and
# floor snap (measured: M4-3 "As implemented"). Elsewhere a dropped step corrects one step.
# Why: TCP holds everything behind a lost segment for RTT + RTO (6 ticks at 100 ms, 8 at 200 ms), then delivers it at
# once. A shallow queue drops that burst (corrections); a deep one keeps it and runs that many ticks behind while the
# player walks on; the drain keeps it and then gives the lateness back a step at a time. Measured, per preset, in
# docs/plans/m4_online_combat.md (M4-3 "As implemented").
# THE DEFAULT IS PROVISIONAL (owner decision, 2026-11-24): "drain", subject to the owner playing the alternatives in the
# M4 demo; it is not the permanent architecture. All three stay selectable (mesh_net.server: --queue, --input-*).
QUEUE_PRESETS = {
    "drain": (8, 1, 4),  # deep, never walking on, a lasting backlog drained a step every 4 ticks (PROVISIONAL default)
    "deep": (8, 1, 0),  # deep, never walking on, no drain: no correction from a held burst; lateness while walking
    "small": (2, 5, 0),  # OD11's starting depth with the old 5-tick lease: little lateness; corrections after a burst
}
QUEUE = "drain"
DEPTH, HOLD, DRAIN = QUEUE_PRESETS[QUEUE]
QUEUE_LIMITS = {"depth": (1, 20), "hold": (1, wire.HZ // 4), "drain": (2, 20)}  # (drain 0 is off)
# The behaviours that move their character in single-player. This authority moves only an enemy's FloorRoute, in an
# HD-2D room (M4-4; in a 2D room FloorRoute moves nothing, here or in single-player). An enemy, or anything solid,
# carrying any other (or a solid non-enemy carrying FloorRoute in an HD-2D room) would stand still here while it walks
# in single-player: refused at load (SceneRoom).
MOVERS = ("ChaseTarget", "EnemyAI", "FleeFromTarget", "FloorRoute", "FollowPath", "FollowTarget", "NpcSchedule",
          "Patrol", "PatrolChase", "PatrolPath", "PlayerController", "RangedEnemyAI", "SequencePlayer", "Wander")


def queue_settings(depth: object = None, hold: object = None, drain: object = None,
                   preset: object = None) -> tuple[int, int, int]:
    """The server's input-queue settings (depth, hold, drain), checked: each given value, else the preset's
    (QUEUE_PRESETS; None: DEPTH, HOLD, DRAIN). Whole numbers within QUEUE_LIMITS (depth up to a second of input, hold up
    to the old 5-tick lease, drain 0 or 2-20 ticks); anything else, or an unknown preset, is refused (ValueError)."""
    if preset is not None and (not isinstance(preset, str) or preset not in QUEUE_PRESETS):
        raise ValueError(f"input queue preset must be one of {', '.join(QUEUE_PRESETS)}, not {str(preset)[:16]!r}")
    base = QUEUE_PRESETS[preset] if isinstance(preset, str) else (DEPTH, HOLD, DRAIN)
    values: dict[str, Any] = {name: base[i] if value is None else value for i, (name, value) in
              enumerate((("depth", depth), ("hold", hold), ("drain", drain)))}
    for name, value in values.items():
        low, high = QUEUE_LIMITS[name]
        if type(value) is not int or not (low <= value <= high or (name == "drain" and value == 0)):
            raise ValueError(f"input queue {name} must be a whole number in {low}-{high}"
                             f"{' or 0 (off)' if name == 'drain' else ''}, not {value!r}")
    return values["depth"], values["hold"], values["drain"]


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


def facing_of(dx: int, dy: int, current: int) -> int:
    """The facing (an index into FACINGS, as the wire has it) an input's direction gives: its horizontal part when that
    is at least as long, else its vertical part; ``current`` for no direction."""
    if not (dx or dy):
        return current
    return FACINGS.index((dx, 0) if abs(dx) >= abs(dy) and dx else (0, dy))


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
class Hitbox:
    """Single-player's hitbox (engine.behaviours.hitbox.Hitbox, which Combat makes), on the server (owner decision
    OD10): it stays where it was made; each tick ages it and, until it is as old as its lifetime, it damages each live
    enemy it overlaps on the attacker's level as the attacker stands that tick, each enemy once."""

    area: Aabb
    age: int = 0  # the ticks it has been updated (the first: the tick it was made)
    hit: set[str] = field(default_factory=set)
    # M4-5: the (past) tick its targets are judged at on the tick it was made (``made``), None: where they are now.
    # Each later update keeps the same lag (at + ticks since made), as its window's view goes on lagging by as much.
    at: float | None = None
    made: int = 0


@dataclass
class Player:
    body: Body
    dx: int = 0  # the direction of the last input read (-1, 0 or 1 each, as the wire has it)
    dy: int = 0
    facing: int = 3
    seq: int = 0  # the newest input received
    held: int = HOLD  # ticks since the last input was read (0: this tick's); it walks while under the room's hold
    deep: int = 0  # ticks in a row that more than one input waited after the read (the room's drain)
    moves: deque[tuple[int, int, int]] = field(default_factory=deque)  # inputs waiting (seq, dx, dy), at most DEPTH
    actions: list[tuple[int, str]] = field(default_factory=list)  # uses and takes waiting (seq of its input, action)
    # attacks waiting (seq of its input, tick meant for, view tick or None: M4-5)
    attacks: list[tuple[int, int, float | None]] = field(default_factory=list)
    joined: int = 0  # the room's tick when it joined this room instance: no view before it was ever its own (M4-5)
    attack_after: int = 0  # the first tick an attack may be meant for (its cooldown, judged on meant ticks)
    ack: int = 0  # the seq of the last input a tick read (wire v3), since it joined this room
    attack_seq: int = 0  # the attacks started since it joined this room (wire v3)
    hitboxes: list[Hitbox] = field(default_factory=list)  # its live ones


@dataclass
class Enemy:
    body: Body
    state: TargetState
    solid: bool
    loot: list[dict[str, Any]] = field(default_factory=list)
    dropped: bool = False  # loot is on the ground
    holder: Player | None = None
    hit_seq: int = 0  # the hits it has taken in this room instance (wire v3)
    route: FloorRoute | None = None  # HD-2D: the FloorRoute it walks (M4-4), each tick while alive


def hitbox_ticks(hz: int = wire.HZ) -> int:
    """The update on which single-player's Hitbox removes itself at a fixed step of 1/``hz`` s: each update adds the
    step to its timer, and the one that reaches HITBOX_S removes it; every update before checks overlaps. That is
    ceil(HITBOX_S * hz) (4 at 20 Hz: 3 checking ticks), counted as the Hitbox counts it."""
    timer, updates = 0.0, 0
    while timer < HITBOX_S:
        timer += 1 / hz
        updates += 1
    return updates


class SceneRoom:
    """Same interface as mesh_net.simulation.Room, so mesh_net.server.Server hosts either."""

    def __init__(self, path: Path, root: Path | None = None, *, depth: int | None = None, hold: int | None = None,
                 drain: int | None = None, rewind: bool | None = None) -> None:
        """``depth``, ``hold``, ``drain``: the input queue's settings (queue_settings; None: DEPTH, HOLD, DRAIN).
        ``rewind``: lag compensation (M4-5; None: REWIND)."""
        self.depth, self.hold, self.drain = queue_settings(depth, hold, drain)
        self.rewind = REWIND if rewind is None else bool(rewind)
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
        self.combat = combat  # (a client presents a swing with its animation and sound: mesh_net.scene_client)
        self.lifetime = hitbox_ticks()

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
            b = body(e, root)
            b.mesh_entity_data = dict(e)  # (its own: walking sets its elevation)
            self.enemies[e["id"]] = Enemy(b, state, bool(e.get("solid")), roll_drops(config(e, "DropTable")),
                                          route=self._route(b))
        for e in others:
            self._refuse_mover(e)
        if self.world is not None and any(e.route for e in self.enemies.values()):
            self.world.walkable()  # (its navigation grid, built now rather than on the first tick)
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
        # Attacks not run (diagnostics; never on the wire): stale (meant more than COOLDOWN_CLAIM_WINDOW ticks ago), refused in
        # the cooldown; actions dropped because PENDING were already waiting; directions dropped from a full queue
        # (depth), and directions the drain dropped from a lasting backlog (drain) (their actions still run).
        self.stale_attacks = self.refused_attacks = self.dropped_actions = self.dropped_moves = self.drained_moves = 0
        # M4-5 (diagnostics, never on the wire): views ahead of the tick, older than REWIND_CAP (clamped), from before
        # the attacker joined (both judged now).
        self.future_views = self.clamped_views = self.unseen_views = 0
        # Each live enemy's pose after each of the last REWIND_CAP + 1 ticks, as its snapshot row has it: tick ->
        # {id: (the Enemy, x, y, elevation px, floor)}. Bounded; kept only with rewind on (_remember).
        self.history: deque[tuple[int, dict[str, tuple[Enemy, float, float, float, str | None]]]] = deque(
            maxlen=REWIND_CAP + 1)
        self._remember()
        try:
            wire.encode({"v": wire.VERSION, **self._worst_snapshot()})
        except wire.Invalid as exc:
            raise Unsupported("the room's largest snapshot would not fit in one frame (shorter ids, fewer objects)") from exc

    def _route(self, b: Body) -> FloorRoute | None:
        """An enemy's FloorRoute in an HD-2D room (engine.hd2d.route: the model single-player's behaviour runs), or
        None. Refused where it can't stand at its start: single-player would first walk it out (or strand it, saying
        so in a gameplay event a shared room doesn't have)."""
        cfg = config(b.mesh_entity_data, "FloorRoute")
        if cfg is None or self.world is None:
            return None
        if not self.stands(b):
            raise Unsupported(f"HD-2D: the enemy '{b.mesh_entity_data['id']}' walks a FloorRoute but can't stand where "
                              "it is at its elevation (no floor within a step, or inside a wall or under a low deck)")
        from engine.hd2d.route import FloorRoute  # noqa: PLC0415  # (2D rooms never load the 3D code)

        return FloorRoute.from_config(cfg)

    def _refuse_mover(self, e: dict[str, Any]) -> None:
        """MOVERS: an enemy moving by anything but FloorRoute, or a solid moving at all, is refused (Unsupported)."""
        enemy = e["id"] in self.enemies
        moving = [n for n in MOVERS if config(e, n) is not None
                  and not (n == "FloorRoute" and (enemy or self.world is None))]
        if moving and (enemy or e.get("solid")):
            what = "the enemy" if enemy else "the solid"
            raise Unsupported(f"{what} '{e['id']}' moves by {moving[0]}, which this server does not run (online, only "
                              "FloorRoute moves an enemy, in an HD-2D room): it would stand still here")

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
        player.joined = self.tick  # (its first state here is this tick's: no view of this room before it, M4-5)
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
                "players": [[wire.MAX_SEQ - i, far, far, 3, far, floor, wire.MAX_SEQ, wire.MAX_SEQ]
                            for i in range(wire.MAX_PLAYERS)],
                "open": sorted(self.doors), "used": sorted(self.levers),
                "enemies": [[i, e.state.max_hp, wire.MAX_SEQ, far, far, far, floor] for i, e in self.enemies.items()],
                "drops": sorted(self.enemies), "loot": [[i, wire.MAX_SEQ] for i in self.enemies]}

    def leave(self, eid: int) -> Player:
        p = self.players.pop(eid)
        p.dx = p.dy = 0
        p.seq, p.held, p.deep = 0, self.hold, 0
        p.moves.clear()  # (no input sent for this room ever walks it in another)
        p.actions.clear()
        p.attacks.clear()
        p.ack = p.attack_seq = 0  # (counted per room join: wire v3)
        p.hitboxes.clear()
        return p

    def input(self, eid: int, msg: wire.Message) -> None:
        seq, dx, dy, action = parse_input(msg, eid)
        p = self.players[eid]
        if seq <= p.seq:
            return
        p.seq = seq
        if len(p.moves) >= self.depth:  # (full: the oldest direction goes; its actions stay, and run with this one)
            p.moves.popleft()
            self.dropped_moves += 1
        p.moves.append((seq, dx, dy))
        # (never one action replacing another: each runs in turn, one of each kind a tick)
        if action == "attack" and len(p.attacks) < PENDING:
            p.attacks.append((seq, msg["tick"], msg.get("view_tick")))
        elif action is not None and action != "attack" and len(p.actions) < PENDING:
            p.actions.append((seq, action))
        elif action is not None:
            self.dropped_actions += 1

    # --- simulation -----------------------------------------------------------------------------------

    def solids(self, state: wire.Message | None = None) -> list[Body]:
        """What blocks a walk now; given a (checked) snapshot of this room, what blocked as it was then: its gates
        open, its enemies alive (HP above 0) where its rows put them (a client's prediction: Prediction; M4-4's enemies
        move)."""
        if state is None:
            locked = self.locked
            enemies = [e.body for e in self.enemies.values() if e.solid and not e.state.dead]
        else:
            locked, rows = set(self.doors) - set(state["open"]), {r[0]: r for r in state["enemies"] if r[1] > 0}
            enemies = [Body(r[3], r[4], e.body.width, e.body.height, {**e.body.mesh_entity_data, "elevation": r[5]}, r[6])
                       for i, e in self.enemies.items() if e.solid and (r := rows.get(i)) is not None]
        doors = [b for i, (b, _) in self.doors.items() if b is not None and i in locked]
        return self.scenery + doors + enemies

    def walk(self, body: Body, dx: int, dy: int, solids: list[Body]) -> None:
        """One tick of one body's walk (owner decision OD3): an input's direction (``dx``, ``dy``: -1, 0 or 1; a
        diagonal normalised) at the player template's speed through ``solids``: in an HD-2D room the one floor solver
        (World.move) with this module's sweep, in a 2D room the sweep alone; then within the wire's bound (an open map
        has no edge). The one movement step: the authority's (step) and a client's prediction of its own avatar
        (Prediction) both run this, never a second."""
        if not (dx or dy):
            return
        ndx, ndy = (dx, dy) if not (dx and dy) else (dx / math.sqrt(2), dy / math.sqrt(2))
        delta = (ndx * self.step_px, ndy * self.step_px)
        if self.world is not None:
            self.world.move(body, delta, solids, sweep=move)
        else:
            move(body, delta, solids)
        body.center_x = max(-BOUND, min(BOUND, body.center_x))
        body.center_y = max(-BOUND, min(BOUND, body.center_y))

    def step(self) -> None:
        """One tick. First each enemy walking a FloorRoute walks (_walk_enemies), so this tick's hits and blocking are
        where the enemies are now (an attack with a view: where they were then, M4-5), and their poses are kept
        (_remember). Then each player (by entity id): the oldest input waiting is read (OD11: DEPTH; its
        direction and facing, and ``ack``; while standing, an older still input is dropped first: DEPTH's note); its
        earlier hitboxes update; the actions whose input has been read run, one attack and one use or take, from where
        the player stands (where its client showed it when they were pressed: Prediction); then it walks one step
        (walk), while under HOLD ticks from the last input read."""
        self.tick += 1
        self._walk_enemies()
        self._remember()
        solids = self.solids()
        for eid, p in sorted(self.players.items()):
            while len(p.moves) > 1 and not any(p.moves[0][1:]) and not any(p.moves[1][1:]):
                p.moves.popleft()  # (standing: the older of two still inputs, which walks nowhere: a tick given back)
            if p.moves:
                p.ack, p.dx, p.dy = p.moves.popleft()
                p.held = 0
                p.facing = facing_of(p.dx, p.dy, p.facing)
                p.deep = p.deep + 1 if len(p.moves) > 1 else 0
                if self.drain and p.deep >= self.drain and not self._forks(p, solids):  # (a lasting backlog: its
                    # oldest direction goes, never an action; never at a fork: DEPTH's note)
                    p.moves.popleft()
                    p.deep = 0
                    self.drained_moves += 1
            else:
                p.held += 1
            if p.hitboxes:  # its earlier attacks' hitboxes, where they were made, the attacker as it now stands
                p.hitboxes = [box for box in p.hitboxes if self._strike(p, box)]
                solids = self.solids()
            if p.attacks and self._ready(p, p.attacks[0][0]):
                _seq, meant, view = p.attacks.pop(0)
                if self._may_attack(p, meant):
                    p.attack_seq += 1
                    self._attack(p, view)
                    solids = self.solids()
            action = p.actions.pop(0)[1] if p.actions and self._ready(p, p.actions[0][0]) else None
            if action == "use":
                self._use(p)
                solids = self.solids()  # a gate that just opened stops blocking from here on
            elif action == "take":
                self._take(p)
            if p.held < self.hold:
                self.walk(p.body, p.dx, p.dy, solids)

    def _walk_enemies(self) -> None:
        """Each live enemy with a FloorRoute (by id) walks one tick of it (1/HZ s; M4-4): the model single-player's
        behaviour runs, through World.path and World.move with this module's sweep, blocked by what blocks now (the
        enemies before it where they have just walked). Players never block it, as single-player's player (not solid)
        doesn't."""
        solids = None
        for _, enemy in sorted(self.enemies.items()):
            if enemy.route is not None and not enemy.state.dead:
                solids = self.solids() if solids is None else solids
                enemy.route.update(self.world, enemy.body, 1 / wire.HZ, solids, sweep=move)

    def _remember(self) -> None:
        """This tick's pose of each live enemy, as this tick's snapshot row carries it (x/y to 0.01 px, elevation to
        0.001 px, floor), with the Enemy it belongs to (M4-5: history). Enemies move only in _walk_enemies, so it is
        taken right after (and once at load). Nothing kept with rewind off."""
        if self.rewind:
            self.history.append((self.tick, {i: (e, round(e.body.center_x, 2), round(e.body.center_y, 2),
                                                 *self.level(e.body))
                                             for i, e in self.enemies.items() if not e.state.dead}))

    def _judged_at(self, p: Player, view: Any) -> float | None:
        """The (past) tick an attack's targets are judged at, from its ``view_tick`` (M4-5), checked against this room's
        own history: None (where they are now, as before M4-5) with rewind off or no view, for a view ahead of this
        tick (counted: future_views) or from before ``p`` joined this room instance (no state of it was its own then:
        unseen_views); else the view, but never more than REWIND_CAP ticks back (an older one is clamped: clamped_views).
        The attacker is never rewound: the hitbox is made where it stands now."""
        if not self.rewind or view is None:
            return None
        if view > self.tick:
            self.future_views += 1
            return None
        if view < p.joined:
            self.unseen_views += 1
            return None
        if view < self.tick - REWIND_CAP:
            self.clamped_views += 1
            return float(self.tick - REWIND_CAP)
        return float(view) if view < self.tick else None

    def _rewound(self, at: float) -> dict[str, Body]:
        """Each enemy as it stood at tick ``at`` (a fraction: between the two ticks around it, as Playback.enemies shows
        it, playback.between), from history. Only an enemy alive in both of those ticks' poses and still the same Enemy
        (not another identity under its id); the rest are judged where they are now. Nothing older than history keeps:
        a time it no longer covers gives none."""
        lo, hi = math.floor(at), math.ceil(at)
        past = dict(self.history)
        if lo not in past or hi not in past:
            return {}
        rewound = {}
        for enemy_id, enemy in self.enemies.items():
            a, b = past[lo].get(enemy_id), past[hi].get(enemy_id)
            if a is None or b is None or a[0] is not enemy or b[0] is not enemy:
                continue
            x, y, z, floor = between(a[1:], b[1:], at - lo)
            data = {**enemy.body.mesh_entity_data, "elevation": z}
            rewound[enemy_id] = Body(x, y, enemy.body.width, enemy.body.height, data, floor)
        return rewound

    def _forks(self, p: Player, solids: list[Body]) -> bool:
        """Whether the drain dropping ``p``'s oldest waiting input would change where this tick's step and the inputs
        still waiting take it by more than a step, or leave it on another floor: both walked (walk: the one step) from
        a copy of its body as a snapshot would show it. The window replays those inputs from the snapshot, so that is
        about the correction the drop costs (inputs still in flight unseen). One step is the drain's price."""
        ends = []
        for skip in (False, True):
            b = p.body
            twin = Body(b.center_x, b.center_y, b.width, b.height, dict(b.mesh_entity_data), b.mesh_hd2d_floor)
            for i, (_seq, dx, dy) in enumerate([(p.ack, p.dx, p.dy), *p.moves]):
                if not (skip and i == 1):
                    self.walk(twin, dx, dy, solids)
            ends.append(twin)
        kept, dropped = ends
        return (kept.mesh_hd2d_floor != dropped.mesh_hd2d_floor
                or math.dist((kept.center_x, kept.center_y), (dropped.center_x, dropped.center_y)) > self.step_px * 1.01)

    @staticmethod
    def _ready(p: Player, seq: int) -> bool:
        """Whether the action carried by input ``seq`` may run this tick: once that input (or a later one) is read."""
        return seq <= p.ack

    def _may_attack(self, p: Player, meant: int) -> bool:
        """Whether an attack meant for tick ``meant`` starts now. Its cooldown is judged on the meant tick, as the
        client judged it, within [now - COOLDOWN_CLAIM_WINDOW, now]: a claim of a tick not yet reached counts as now, an older
        one is stale and dropped (counted, never run). Refused in the cooldown otherwise (counted).

        What a client lying about its ticks gains: meant ticks that start attacks rise at least a cooldown apart and are
        never older than COOLDOWN_CLAIM_WINDOW when read, and at most one starts a tick. So over any W ticks at most
        1 + (W + COOLDOWN_CLAIM_WINDOW) // cooldown attacks start, against 1 + W // cooldown judged on arrival: the same long-run
        rate, plus one cap's worth. Its most on consecutive ticks, after a pause, claiming the oldest tick accepted each
        tick: 1 + COOLDOWN_CLAIM_WINDOW // (cooldown - 1) for a cooldown of 2 ticks or more (13 at 2, 7 at 3, 4 at 5, 2 at 10);
        a cooldown of 1 tick allows one a tick anyway."""
        if meant < self.tick - COOLDOWN_CLAIM_WINDOW:
            self.stale_attacks += 1
            return False
        meant = min(meant, self.tick)
        if meant < p.attack_after:
            self.refused_attacks += 1
            return False
        p.attack_after = meant + self.cooldown
        return True

    def _level(self, a: Body, b: Body) -> bool:
        """Whether ``a`` may use, attack or pick up ``b``: engine.hd2d.world.same_level (M3-4), single-player's own
        rule. Always in a 2D room (which never loads the 3D code)."""
        if self.world is None:
            return True
        from engine.hd2d.world import same_level  # noqa: PLC0415

        return same_level(self.world, a, b)

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
            if d > radius or not self._level(p.body, Body(float(entity["x"]), float(entity["y"]), *size, entity)):
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

    def _attack(self, p: Player, view: Any = None) -> None:
        """Combat's hitbox (range ahead, hitbox_size square), made where the attacker stands now, and its first update
        (this tick's: _strike); it is kept for the rest of its lifetime (step). ``view``: the attack's view tick, which
        may judge its targets where they were (M4-5: _judged_at)."""
        fx, fy = FACINGS[p.facing]
        box = Hitbox(Aabb(p.body.center_x + fx * self.reach, p.body.center_y + fy * self.reach, self.hitbox, self.hitbox),
                     at=self._judged_at(p, view), made=self.tick)
        if self._strike(p, box):
            p.hitboxes.append(box)

    def _strike(self, p: Player, box: Hitbox) -> bool:
        """One update of a Hitbox ``p`` made: it ages a tick; until its lifetime, each enemy alive now whose shape it
        overlaps, on the attacker's level as the attacker stands now (as single-player's Hitbox asks), that it has not
        hit yet takes Health's damage rule. With a view (M4-5: ``box.at``) the shape and level are the enemy's then, as
        far back as when the box was made (_rewound); the damage, death and drop are now's. False once it has expired
        (that update checks nothing, as the Hitbox's last)."""
        box.age += 1
        if box.age >= self.lifetime:
            return False
        rewound = self._rewound(box.at + (self.tick - box.made)) if box.at is not None else {}
        for enemy_id, enemy in sorted(self.enemies.items()):
            target = rewound.get(enemy_id, enemy.body)
            if enemy_id in box.hit or enemy.state.dead or not shapes_overlap(box.area, entity_shape(target)):
                continue
            if not self._level(p.body, target):
                continue
            box.hit.add(enemy_id)
            enemy.hit_seq += 1
            spec = AttackSpec(f"player:{id(p)}", enemy_id, self.damage, 0.0, "combat.default")
            enemy.state, result = resolve_attack(spec, enemy.state)
            if result.target_dead and enemy.loot:
                enemy.dropped = True
        return True

    def _take(self, p: Player) -> None:
        for _, enemy in sorted(self.enemies.items()):
            if (enemy.dropped and self._near(p, enemy.body.center_x, enemy.body.center_y) is not None
                    and self._level(p.body, enemy.body)):
                enemy.dropped, enemy.holder = False, p
                return

    def snapshot(self) -> wire.Message:
        owner = {id(p): eid for eid, p in self.players.items()}
        return {"v": wire.VERSION, "type": "scene_state", "tick": self.tick, "scene": self.identity,
                "players": [[eid, round(p.body.center_x, 2), round(p.body.center_y, 2), p.facing, *self.level(p.body),
                             p.ack, p.attack_seq] for eid, p in sorted(self.players.items())],
                "open": sorted(set(self.doors) - self.locked), "used": sorted(self.used),
                "enemies": [[i, e.state.hp, e.hit_seq, round(e.body.center_x, 2), round(e.body.center_y, 2),
                             *self.level(e.body)] for i, e in sorted(self.enemies.items())],
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
    """An input frame from the owner of ``eid``: eight directions and an optional action (and its ticks: wire v3)."""
    wire.input_fields(msg)
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
    for row in players:  # [entity, x, y, facing, elevation, floor, ack, attack_seq] (mesh_net.protocol)
        if (not isinstance(row, list) or len(row) != 8 or not wire.integer(row[0], 1) or row[0] in seen
                or not all(_number(v) for v in (row[1], row[2], row[4])) or not wire.integer(row[3], 0, 3)
                or not _floor(row[5]) or not wire.integer(row[6], 0) or not wire.integer(row[7], 0)):
            raise wire.Invalid("invalid player row")
        seen.add(row[0])
    for key in ("open", "used", "drops"):
        if type(msg[key]) is not list or len(msg[key]) > MAX_OBJECTS or not all(isinstance(i, str) for i in msg[key]):
            raise wire.Invalid(f"invalid {key}")
    enemies = msg["enemies"]  # [id, hp, hit_seq, x, y, elevation, floor]
    if type(enemies) is not list or len(enemies) > MAX_OBJECTS or not all(
            isinstance(r, list) and len(r) == 7 and isinstance(r[0], str) and _number(r[1]) and r[1] >= 0
            and wire.integer(r[2], 0) and all(_number(v) for v in r[3:6]) and _floor(r[6]) for r in enemies) \
            or len({r[0] for r in enemies}) != len(enemies):
        raise wire.Invalid("invalid enemies")
    loot = msg["loot"]
    if type(loot) is not list or len(loot) > MAX_OBJECTS or not all(
            isinstance(r, list) and len(r) == 2 and isinstance(r[0], str)
            and (r[1] is None or (wire.integer(r[1], 1) and r[1] in seen)) for r in loot):
        raise wire.Invalid("invalid loot")
    if room is not None:
        check_levels(players, room)
        check_enemies(enemies, room)


def _floor(value: Any) -> bool:
    """A floor id as the wire carries one (mesh_net.protocol), or none."""
    return value is None or (isinstance(value, str) and 0 < len(value) <= MAX_FLOOR)


def check_enemies(rows: list[Any], room: SceneRoom) -> None:
    """Each (well-formed) enemy row against the client's own room: an enemy it has, placed as a body can be there. A 2D
    room: elevation 0 and no floor. An HD-2D room: no floor (a body the authority never stood on one), or a floor its
    collision world has, under the enemy's own box within a step of its elevation (check_levels' rule: floor_under;
    M4-4's enemies walk, so its 0.01 px rounding at a floor's edge too)."""
    if any(r[0] not in room.enemies for r in rows):
        raise wire.Invalid("an enemy row names an enemy this room does not have")
    if room.world is None:
        if any(r[5] != 0 or r[6] is not None for r in rows):
            raise wire.Invalid("a 2D room's enemy row carries an elevation or a floor")
        return
    for enemy_id, _hp, _hits, x, y, elevation, floor in rows:
        if floor is None:
            continue
        if floor not in room.floor_ids:
            raise wire.Invalid(f"an enemy row stands on a floor this room does not have: {str(floor)[:48]!r}")
        body = room.enemies[enemy_id].body
        if not floor_under(room, Body(x, y, body.width, body.height, body.mesh_entity_data), floor, elevation):
            raise wire.Invalid(f"an enemy row's floor {floor!r} is not under it at elevation {elevation:g} px")


def check_progress(before: wire.Message, after: wire.Message, own: int, sent: int) -> None:
    """A client's check of a newer (checked) scene_state against the last it applied in the same room instance (wire
    v3): no player's ``ack`` or ``attack_seq`` and no enemy's ``hit_seq`` goes back, and its own ``ack`` (entity
    ``own``) is never a ``seq`` beyond ``sent``, the last it sent. Anything else is stale or inconsistent: refused."""
    rows = {r[0]: r for r in before["players"]}
    for row in after["players"]:
        if row[0] == own and row[6] > sent:
            raise wire.Invalid("the server acknowledges an input this client never sent")
        old = rows.get(row[0])
        if old is not None and (row[6] < old[6] or row[7] < old[7]):
            raise wire.Invalid("a player's acknowledgement or attack count went back")
    hits = {r[0]: r[2] for r in before["enemies"]}
    if any(r[2] < hits.get(r[0], 0) for r in after["enemies"]):
        raise wire.Invalid("an enemy's hit count went back")


RECKONING = wire.HZ  # snapshots in a row (a second's), all late, after which a client's reckoning comes down (Feedback)


class Feedback:
    """A client's combat presentation (owner decision OD4): its own swing the moment it is pressed, others' swings
    and every hit only as the server's counters confirm them (wire v3).

    ``press`` mirrors the attack cooldown (SceneRoom.cooldown, from the room's own player template) on the room's
    tick, as the client reckons it (``tick``: a snapshot's tick advanced by the time since it came, taking the one
    that came soonest); it returns that tick, which the attack's input carries, and the server judges the cooldown on
    it (SceneRoom._may_attack). So a press the window swings for is one the server runs, whatever latency and TCP's
    bunching do to its arrival, unless it reaches the server more than COOLDOWN_CLAIM_WINDOW ticks after that tick (then it is
    stale: dropped, and the swing reads as a miss). A press within the cooldown swings for nothing and sends nothing.

    The reckoning may come down: a server that stalls skips the ticks it missed (mesh_net.server.Server._run_clock), so
    its tick falls behind the clock, and the reckoning follows once RECKONING snapshots in a row (a second's) all came
    more than a tick later than the soonest. Meanwhile (the stall and about a second after it) the reckoning runs
    ahead, its ticks count as now, and a swing shown then can be refused in the cooldown (counted:
    SceneRoom.refused_attacks). The window never swings early for it: the cooldown runs from the last swing's tick as
    it was sent, which a reckoning that came down reaches only later.
    ``update`` reads each newer state against the last, after its checks (check_state, check_progress). Its counters
    and tick are a room instance's: ``baseline`` takes them anew at a welcome (a resume's too) and at every enter."""

    def __init__(self) -> None:
        self.cooldown = 0  # ticks
        self.offset = -math.inf  # the room's tick minus the client's clock (s) times HZ, at the soonest snapshot
        self.samples: deque[float] = deque(maxlen=RECKONING)  # that difference for the latest snapshots
        self.last = -math.inf  # the tick of the last swing shown
        self.swings: dict[int, int] = {}  # entity -> attack_seq last applied
        self.hits: dict[str, int] = {}  # enemy -> hit_seq last applied

    def tick(self, now: float) -> int:
        """The room's tick at ``now`` (s on the client's clock), as this client reckons it. Not ahead of the server's
        while the server keeps time (each snapshot's tick came no sooner than it was made); it comes down after a server
        stall (the class's note)."""
        return math.floor(now * wire.HZ + self.offset + 1e-6) if self.offset > -math.inf else 0

    def baseline(self, state: wire.Message, cooldown: int, now: float) -> None:
        """A new room instance or session: what ``state`` (applied at ``now``) counts is already seen, and its tick
        starts the reckoning. ``cooldown``: the room's, in ticks. The last swing's tick is kept while it is not ahead of
        the reckoned tick (the same room, resumed: its cooldown still runs there); else it is another count of ticks.
        (So a resume straight after a swing shown during a server stall, its tick claimed ahead of the server's,
        forgets that swing: the next press may swing inside the server's cooldown, and that one attack is refused,
        counted in SceneRoom.refused_attacks. One at most: the swing it shows starts the cooldown anew.)"""
        self.cooldown = cooldown
        self.samples.clear()
        self.samples.append(state["tick"] - now * wire.HZ)
        self.offset = self.samples[0]
        if self.last > self.tick(now):
            self.last = -math.inf
        self.swings = {r[0]: r[7] for r in state["players"]}
        self.hits = {r[0]: r[2] for r in state["enemies"]}

    def press(self, now: float) -> int | None:
        """The tick an attack pressed at ``now`` (s) is meant for, when it swings (shown at once, and sent with that
        tick); None within the cooldown of the last swing (nothing shown, nothing sent)."""
        tick = self.tick(now)
        if tick < self.last + self.cooldown:
            return None
        self.last = tick
        return tick

    def update(self, state: wire.Message, own: int, now: float) -> tuple[list[int], list[str]]:
        """The players other than ``own`` who started an attack, and the enemies hit, since the last state applied
        (at ``now``)."""
        self.samples.append(state["tick"] - now * wire.HZ)
        recent = max(self.samples)
        # The soonest snapshot so far, unless the latest RECKONING all came more than a tick later than it would have
        # (no jitter or TCP retransmission delays that many in a row: the server's tick fell behind, a stall); then
        # the soonest of those.
        self.offset = recent if recent < self.offset - 1 and len(self.samples) == RECKONING else max(self.offset, recent)
        swung = [r[0] for r in state["players"] if r[0] != own and r[7] > self.swings.get(r[0], r[7])]
        hit = [r[0] for r in state["enemies"] if r[2] > self.hits.get(r[0], 0)]
        self.swings = {r[0]: r[7] for r in state["players"]}
        self.hits = {r[0]: r[2] for r in state["enemies"]}
        return swung, hit


SMOOTH_S = 0.1  # s: a correction's x/y offset fades out over this (Prediction.shown)


class Prediction:
    """A client's own avatar, ahead of the server (owner decision OD3, M4-3): presentation only. The server alone places
    bodies; nothing predicted is ever sent.

    Each input this client sends walks the avatar at once through SceneRoom.walk, the authority's own step (one movement
    implementation, never a second), and waits in ``inputs`` until a snapshot's ``ack`` says the server has read it.
    Each snapshot (``reconcile``) puts the avatar back on the server's row (x, y, elevation, floor) and walks the inputs
    the server has not read yet again, through what blocked in that snapshot. The server reads one input a tick (OD11),
    so with no loss and nothing changing the result is where the avatar already was; otherwise (an input the server
    dropped from a full queue, after a stall or an outage longer than DEPTH ticks; a gate or an enemy the snapshot
    changed) the difference is a correction. Its x/y offset fades out over SMOOTH_S; elevation and floor take the server's at once,
    so the avatar is never drawn between floors. Hidden per-body solver state is never carried (the floor solver's
    water escape cap, ``mesh_hd2d_deep_cap``, is not on the wire): replays start without it, so a prediction there can
    differ until the next snapshot puts it back (online rooms refuse such water today: hd2d_world, owner decision D4).

    A direction pressed between two sends builds the next input at once (``press``): the avatar moves on the frame
    that reads the key, and that input is the one the next send carries (``next``, then ``sent`` with its seq). The
    send rate stays one input a tick.

    ``start`` at a welcome (a resume's too) and when a room is first shown after an enter; ``stop`` at an enter and at a
    session's end: no input is ever walked again in another room or session."""

    def __init__(self) -> None:
        self.room: SceneRoom | None = None
        self.body: Body | None = None  # the predicted avatar (None: not predicting)
        # [seq (None: built, not sent yet), dx, dy] of each input the server has not read, oldest first. (Bounded far
        # beyond a session's life without a snapshot: wire.read gives up on a silent server after 5 s.)
        self.inputs: deque[list[Any]] = deque(maxlen=10 * wire.HZ)
        self.state: wire.Message | None = None  # the latest snapshot: what blocks (SceneRoom.solids)
        self.offset = (0.0, 0.0)  # the x/y correction (px) shown at its fullest, fading out over ``fade`` s
        self.fade = 0.0

    def start(self, room: SceneRoom, state: wire.Message, own: int) -> None:
        """Predict anew from the server's row for ``own`` in ``state`` (``room``: this client's copy of the room)."""
        self.room, self.state = room, state
        self.body = self._place(next(r for r in state["players"] if r[0] == own))
        self.inputs.clear()
        self.offset, self.fade = (0.0, 0.0), 0.0

    def stop(self) -> None:
        self.body, self.state = None, None
        self.inputs.clear()

    def press(self, direction: tuple[int, int]) -> bool:
        """A direction key pressed: unless an input is already built and not sent, build the next one now (True)."""
        if self.body is not None and (not self.inputs or self.inputs[-1][0] is not None):
            self._build(direction)
            return True
        return False

    def next(self, direction: tuple[int, int]) -> tuple[int, int]:
        """The direction the next input sends: the one built at a press since the last send, else ``direction`` (the
        keys held now), built now. (Not predicting: ``direction``.)"""
        if self.body is None:
            return direction
        if not self.inputs or self.inputs[-1][0] is not None:
            self._build(direction)
        return self.inputs[-1][1], self.inputs[-1][2]

    def sent(self, seq: int) -> None:
        """The input ``next`` gave goes out as ``seq``."""
        if self.inputs and self.inputs[-1][0] is None:
            self.inputs[-1][0] = seq

    def _build(self, direction: tuple[int, int]) -> None:
        assert self.room is not None and self.body is not None
        self.inputs.append([None, *direction])
        self.room.walk(self.body, *direction, self.room.solids(self.state))

    def _place(self, row: list[Any]) -> Body:
        assert self.room is not None
        return Body(row[1], row[2], *self.room.size, {**self.room.template, "elevation": row[4]}, row[5])

    def _shown_offset(self) -> tuple[float, float]:
        k = self.fade / SMOOTH_S
        return self.offset[0] * k, self.offset[1] * k

    def reconcile(self, state: wire.Message, own: int) -> tuple[float, float, bool]:
        """A newer (checked) snapshot: back to its row, the inputs it hasn't read walked again. Returns the correction:
        how far (px) the avatar moved in x/y and in elevation, and whether its floor changed. (Not predicting: none.)"""
        if self.body is None or self.room is None:
            return 0.0, 0.0, False
        row = next(r for r in state["players"] if r[0] == own)
        while self.inputs and self.inputs[0][0] is not None and self.inputs[0][0] <= row[6]:
            self.inputs.popleft()
        before, level = (self.body.center_x, self.body.center_y), self.room.level(self.body)
        self.state, self.body = state, self._place(row)
        solids = self.room.solids(state)
        for _, dx, dy in self.inputs:
            self.room.walk(self.body, dx, dy, solids)
        ex, ey = before[0] - self.body.center_x, before[1] - self.body.center_y
        if ex or ey:
            shown = self._shown_offset()
            self.offset, self.fade = (shown[0] + ex, shown[1] + ey), SMOOTH_S
        z, floor = self.room.level(self.body)
        return math.hypot(ex, ey), abs(z - level[0]), floor != level[1]

    def shown(self, dt: float) -> tuple[float, float, float, str | None]:
        """Where to draw the avatar ``dt`` s after the last call: (x, y, elevation, floor) as a snapshot row has them,
        the x/y with what is left of the corrections' offset."""
        assert self.room is not None and self.body is not None
        self.fade = max(0.0, self.fade - dt)
        ox, oy = self._shown_offset()
        return (self.body.center_x + ox, self.body.center_y + oy, *self.room.level(self.body))


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
    w, h = room.size
    for row in players:
        floor = row[5]
        if floor not in room.floor_ids:
            raise wire.Invalid(f"a player row stands on a floor this room does not have: {str(floor)[:48]!r}")
        if not floor_under(room, Body(row[1], row[2], w, h, room.template), floor, row[4]):
            raise wire.Invalid(f"a player row's floor {floor!r} is not under it at elevation {row[4]:g} px")


def floor_under(room: SceneRoom, body: Body, floor: str, elevation: float) -> bool:
    """Whether ``floor`` lies under ``body``'s feet (its movement box's centre: where World.move stands it) within a
    step (World.STEP) of ``elevation`` px, sampled there and at the corners of the wire's 0.01 px rounding, so the
    rounding itself never refuses a floor's own edge (check_levels, check_enemies)."""
    from engine.hd2d.settings import PIXELS_PER_METRE  # noqa: PLC0415
    from engine.hd2d.world import STEP  # noqa: PLC0415

    assert room.world is not None
    box = entity_aabb(body)
    z = elevation / PIXELS_PER_METRE
    x, y, r = box.x / PIXELS_PER_METRE, box.y / PIXELS_PER_METRE, ROUNDING / PIXELS_PER_METRE
    return any(s.floor == floor and abs(height - z) <= STEP + 1e-6
               for px, py in ((x, y), (x - r, y - r), (x + r, y - r), (x - r, y + r), (x + r, y + r))
               for height, s in room.world.heights_at(px, py))
