"""HD-2D online M1-A-3: single-player and the net authority give the same supported positions.

One crossing built by ``tooling/hd2d_floors_demo.py build`` (ground, stairs, a 2 m deck over an underpass, railings),
plus a scatter boulder and a solid crate on the ground under the deck (a 2D solid), is walked with one scripted
input sequence (diagonals included) on both runtimes:

- single-player: the game's ``PlayerController`` moving its sprite through ``World.move`` with the default (Arcade)
  sweep, at a fixed ``dt = 1/20``, on a World built from the files the way the game loads them (SceneLoader's
  entities, engine.hd2d.world.build_world);
- the authority: ``SceneRoom.step`` with v1 input frames (``speed / HZ`` a tick, diagonals normalised).

Per tick each records (x, y, elevation, floor, blocked); the traces must match (x/y to 1e-6 px, the rest exactly).
Both move the same body (the room template's picture size and collider; the gpu case checks the game window's player
has that movement box), so what is compared is the movement: the controller, the sweep and the floor solver."""

from __future__ import annotations

import ast
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

import pytest

from engine.hd2d.world import World
from engine.physics_model import entity_aabb
from mesh_net import scene_room
from mesh_net.scene_room import Body, Player, SceneRoom, config, disposable_project

pytestmark = pytest.mark.integration  # (builds a project in a folder, loads its room from files)

REPO = Path(__file__).resolve().parents[1]
SCENE = "packs/core_regions/scenes/start.json"
MODEL = "assets/models/stone_crossing.glb"
DT = 1 / 20  # single-player's fixed frame: the authority's tick (mesh_net.protocol.HZ)
BOULDER = (800, 96)  # px: on the ground east of the start (25 m, 3 m)
# A solid object with a box collider on the ground under the deck (14 m, 12 m): a 2D solid, at elevation 0
CRATE_X = 448.0
CRATE = {"id": "crate", "x": CRATE_X, "y": 384.0, "solid": True, "components": {"collider": {"kind": "box", "w": 32, "h": 32}}}
Row = tuple[float, float, float, "str | None", bool]  # x px, y px, elevation px, floor, blocked

# The crossing walked end to end: (dx, dy, ticks). Feet start at (16 m, 3 m) on the ground.
ROUTE = [
    (1, 0, 45),  # east into the boulder (stopped at 24.1 m)
    (-1, 0, 60),  # back west to the foot of the west stairs
    (-1, 1, 3),  # diagonal onto the stairs' line
    (0, 1, 12),  # up the west stairs
    (1, 1, 4),  # diagonal, still on the stairs
    (0, 1, 40),  # onto the west platform, on to its north edge (a ledge: no falling)
    (0, -1, 12),  # back south to the bridge's line
    (1, 0, 25),  # east onto the bridge deck
    (1, 1, 6),  # diagonal into the north railing: slides along it
    (0, 1, 8),  # straight into the railing
    (0, -1, 5),
    (1, 0, 16),  # off the bridge onto the east platform
    (1, 0, 20),  # to the east platform's east edge (a ledge)
    (-1, 0, 11),
    (0, -1, 14),  # down the east stairs
    (-1, -1, 4),  # diagonal, still on the stairs
    (0, -1, 20),  # onto the ground
    (0, 0, 3),  # let go
    (-1, 0, 22),  # west to the underpass's line
    (0, 1, 38),  # north, under the bridge (feet at 11.9 m)
    (1, 0, 16),  # east under the deck into the east platform's side (stopped at 18.7 m)
    (1, 1, 20),  # diagonal: north along the platform's west side, out from under the deck
    (-1, 0, 12),
    (0, 1, 30),  # on north through the underpass
]


def ticks(route: list[tuple[int, int, int]]) -> list[tuple[int, int]]:
    return [(dx, dy) for dx, dy, n in route for _ in range(n)]


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """The floors demo's project with a boulder scattered on its ground (by Studio's own edit) and the crate, as the
    current folder and the engine's user locations while this module runs (mesh_net.scene_room.disposable_project)."""
    from engine import project_ops as ops

    sys.path.insert(0, str(REPO / "tooling"))
    try:
        import hd2d_floors_demo
    finally:
        sys.path.remove(str(REPO / "tooling"))
    built = hd2d_floors_demo.build(tmp_path_factory.mktemp("parity") / "proj")
    files = {p.relative_to(built).as_posix(): p.read_bytes() for p in built.rglob("*") if p.is_file()}
    scene = ops.set_scatter(json.loads(files[SCENE]), {"boulder": [[*BOULDER, 0, 100]]})
    scene["entities"].append(CRATE)
    with disposable_project({**files, SCENE: json.dumps(scene).encode()}, scaffold=False) as root:
        yield root


def single_player_world(root: Path, model: bytes | None = None) -> tuple[World, list[SimpleNamespace]]:
    """The World single-player's window gets for the room (engine.hd2d.runtime.configure_scene's parse and builder,
    the entities as engine.scene_loader loads them), and its solid sprites (each solid entity as loaded; positions,
    collider and elevation are what movement reads); ``model``: the crossing's GLB read instead of its file."""
    from engine.behaviours import load_builtin_behaviours
    from engine.hd2d.glb import load_glb
    from engine.hd2d.settings import parse_hd2d
    from engine.hd2d.world import build_world
    from engine.scene_loader import SceneLoader

    load_builtin_behaviours()  # (as the game window has them)
    scene = SceneLoader().load_scene(str(root / SCENE))
    settings = scene["settings"]
    hd2d = parse_hd2d(settings["hd2d"], map_size_px=(settings["world_width"], settings["world_height"]), lenient=True)
    models = {}
    if model is not None:
        alt = root / "changed.glb"  # (inside the disposable project: removed with it)
        alt.write_bytes(model)
        models[MODEL] = load_glb(alt)
    world = build_world(hd2d, scene["entities"], scene_room.contained(root), models=models)[0]
    assert isinstance(world, World)
    solids = [sprite(float(e["x"]), float(e["y"]), (0.0, 0.0), e) for e in scene["entities"] if e.get("solid")]
    return world, solids


class Keys:
    """What PlayerController reads from the game's InputManager: one direction held."""

    def __init__(self) -> None:
        self.x = self.y = 0.0

    def get_axis(self, negative: str, positive: str) -> float:
        return self.x if negative == "move_left" else self.y

    def is_action_down(self, action: str) -> bool:
        return False


def sprite(x: float, y: float, size: tuple[float, float], entity: dict[str, Any]) -> SimpleNamespace:
    """A game sprite as World.move and the physics sweep read it."""
    return SimpleNamespace(center_x=x, center_y=y, width=size[0], height=size[1], scale_x=1.0,
                           mesh_entity_data=json.loads(json.dumps(entity)))


def row(body: Any, before: tuple[float, float], wanted: tuple[int, int], step: float) -> Row:
    moved = math.hypot(body.center_x - before[0], body.center_y - before[1])
    return (body.center_x, body.center_y, body.mesh_entity_data.get("elevation", 0.0),
            getattr(body, "mesh_hd2d_floor", None), bool(wanted != (0, 0) and moved < step - 1e-9))


def run_single_player(sp: tuple[World, list[SimpleNamespace]], room: SceneRoom, starts: list[tuple[float, float, float]],
                      scripts: list[list[tuple[int, int]]], solid_others: bool = False,
                      extra_solids: tuple[Any, ...] = ()) -> list[list[Row]]:
    """Each actor a sprite with the room template's PlayerController, its window's ``hd2d_world`` the World and its
    solid sprites the room's (``sp``: single_player_world), moved once a tick in order at ``dt = 1/20``.
    ``solid_others``: every other actor is one of its window's solids too (as a solid NPC would be); ``extra_solids``
    are too."""
    from engine.behaviours.player_controller import PlayerController

    world, scenery = sp
    size = room._template_size()
    actors = [sprite(x, y, size, {**room.template, "elevation": z}) for x, y, z in starts]
    keys = [Keys() for _ in actors]
    controllers = []
    for me, held in zip(actors, keys):
        solids = [*scenery, *(a for a in actors if a is not me and solid_others), *extra_solids]
        window = SimpleNamespace(input=held, hd2d_world=world, scene_controller=SimpleNamespace(solid_sprites=solids))
        controllers.append(PlayerController(me, window, **(config(room.template, "PlayerController") or {})))
    traces: list[list[Row]] = [[] for _ in actors]
    for tick in range(len(scripts[0])):
        for i, (me, pc) in enumerate(zip(actors, controllers)):
            keys[i].x, keys[i].y = scripts[i][tick]
            before = (me.center_x, me.center_y)
            pc.update(DT)
            traces[i].append(row(me, before, scripts[i][tick], room.step_px))
    return traces


def run_authority(room: SceneRoom, starts: list[tuple[float, float, float]],
                  scripts: list[list[tuple[int, int]]]) -> list[list[Row]]:
    """Each actor a player joined at its start, given a v1 input frame every tick, the room stepped once a tick."""
    size = room._template_size()
    eids = [room.join(Player(Body(x, y, *size, {**room.template, "elevation": z}))) for x, y, z in starts]
    traces: list[list[Row]] = [[] for _ in eids]
    for tick in range(len(scripts[0])):
        before = []
        for i, eid in enumerate(eids):
            dx, dy = scripts[i][tick]
            room.input(eid, {"v": 1, "type": "input", "entity": eid, "seq": tick + 1, "dx": dx, "dy": dy})
            body = room.players[eid].body
            before.append((body.center_x, body.center_y))
        room.step()
        for i, eid in enumerate(eids):
            traces[i].append(row(room.players[eid].body, before[i], scripts[i][tick], room.step_px))
    for eid in eids:
        room.leave(eid)
    return traces


def assert_same(a: list[Row], b: list[Row]) -> None:
    assert len(a) == len(b)
    for tick, (p, q) in enumerate(zip(a, b)):
        assert abs(p[0] - q[0]) <= 1e-6 and abs(p[1] - q[1]) <= 1e-6, f"tick {tick}: x/y {p[:2]} != {q[:2]}"
        assert p[2:] == q[2:], f"tick {tick}: (elevation, floor, blocked) {p[2:]} != {q[2:]}"


def transitions(trace: list[Row]) -> list[tuple[int, str | None, str | None]]:
    return [(t, a[3], b[3]) for t, (a, b) in enumerate(zip(trace, trace[1:]), 1) if a[3] != b[3]]


@pytest.fixture(scope="module")
def room(project: Path) -> SceneRoom:
    room = SceneRoom(project / SCENE, project)
    assert room.world is not None and [b.mesh_entity_data["id"] for b in room.solids()] == ["crate"]
    return room


@pytest.fixture(scope="module")
def traces(project: Path, room: SceneRoom) -> tuple[list[Row], list[Row]]:
    start = [(*room.spawn, 0.0)]
    script = [ticks(ROUTE)]
    single = run_single_player(single_player_world(project), room, start, script)[0]
    authority = run_authority(room, start, script)[0]
    return single, authority


def test_the_two_runtimes_trace_the_same_walk_diagonals_included(room: SceneRoom, traces: tuple) -> None:
    single, authority = traces
    world, solids = single_player_world(room.root)
    assert room.digest == world.collision_digest(), "built from the same files"
    assert [s.mesh_entity_data["id"] for s in solids] == ["crate"], "the same 2D solids"
    assert_same(single, authority)
    diagonal = [t for t, (dx, dy) in enumerate(ticks(ROUTE)) if dx and dy]
    moved_diagonally = [t for t in diagonal if not single[t][4]]
    assert len(moved_diagonally) >= 10, "diagonal ticks that moved freely are compared too"
    assert single[-1][3] == "ground" and single[-1][1] > 18.0 * 32, "through the underpass to the north"


def test_stairs_and_the_bridge_change_floor_on_the_same_tick(traces: tuple) -> None:
    single, authority = traces
    assert transitions(single) == transitions(authority)
    floors = [b for _t, _a, b in transitions(single)]
    assert floors == ["crossing/col_stairs_west", "crossing/col_landing_west", "crossing/col_platform_west",
                      "crossing/col_bridge_deck", "crossing/col_platform_east", "crossing/col_landing_east",
                      "crossing/col_stairs_east", "ground"], "stair up, bridge to platform, stair down"


def test_railings_ledges_and_the_boulder_block_in_both(room: SceneRoom, traces: tuple) -> None:
    single, authority = traces
    route_ticks = ticks(ROUTE)
    ends = {}
    t = 0
    for i, (_dx, _dy, n) in enumerate(ROUTE):
        t += n
        ends[i] = t - 1  # the segment's last tick
    for label, segment, floor in (("boulder", 0, "ground"), ("west platform's north edge", 5, "crossing/col_platform_west"),
                                  ("north railing", 9, "crossing/col_bridge_deck"),
                                  ("east platform's east edge", 12, "crossing/col_platform_east"),
                                  ("east platform's side, under the deck", 20, "ground")):
        last = ends[segment]
        assert route_ticks[last] != (0, 0)
        assert single[last][4] and authority[last][4], f"{label}: blocked in both"
        assert single[last][3] == authority[last][3] == floor, label
    assert single[ends[0]][0] < BOULDER[0] - 16, "the boulder stops it short of its middle"
    under = single[ends[20]]
    half = entity_aabb(Body(0.0, 0.0, *room._template_size(), room.template)).w / 2  # px: the feet box's
    assert 0.0 <= 19.0 * 32 - (under[0] + half) < room.step_px and 11.0 < (under[1] - 18) / 32 < 13.0, (
        "stopped within a step of the platform's side (19 m: a step that won't stand is refused whole), its feet "
        "under the deck (11 m to 13 m)")
    slide = single[ends[8] - 1], single[ends[8]]
    assert slide[1][0] > slide[0][0] and slide[1][1] == slide[0][1], "pushed diagonally into the railing: slides along"


def test_two_actors_on_two_floors_at_one_place_keep_their_floors(project: Path, room: SceneRoom) -> None:
    """One on the deck, one under it, at the same x/y, both walking west past the crate (a 2D solid on the ground under
    the deck). ``_on_level`` applies to the 2D solids in both runtimes: the crate stops the one under the deck and not
    the one on it. In single-player each actor is also a 2D solid of the other's window (as a solid NPC would be):
    through the deck neither blocks the other, so both trace exactly what the authority (whose players never block
    each other) traces, and what each traces alone."""
    at = (16.0 * 32, 12.0 * 32 + 18.0)  # sprite centre: feet at (16 m, 12 m)
    starts = [(*at, 64.0), (*at, 0.0)]
    on = ticks([(-1, 0, 11), (1, 1, 3), (1, -1, 5), (1, 0, 10)])  # west along the deck over the crate, and back
    under = ticks([(-1, 0, 11), (1, 1, 3), (1, -1, 5), (0, -1, 10)])  # west into the crate, then about
    sp = single_player_world(project)
    single = run_single_player(sp, room, starts, [on, under], solid_others=True)
    authority = run_authority(room, starts, [on, under])
    for mine, theirs in zip(single, authority):
        assert_same(mine, theirs)
    for i, script in enumerate((on, under)):
        assert_same(single[i], run_single_player(sp, room, [starts[i]], [script])[0])  # (as if alone)
    assert {r[2:4] for r in single[0]} == {(64.0, "crossing/col_bridge_deck")}, "on the deck throughout"
    assert {r[2:4] for r in single[1]} == {(0.0, "ground")}, "under it throughout"
    crate_west, crate_east = (CRATE_X - 16) / 32, (CRATE_X + 16) / 32  # m
    assert not any(r[4] for r in single[0]) and min(r[0] for r in single[0]) / 32 < crate_west, (
        "the one on the deck walks over the whole crate, unblocked")
    stopped = [t for t, r in enumerate(single[1]) if r[4]]
    assert stopped and stopped == [t for t, r in enumerate(authority[1]) if r[4]] and max(stopped) < 11, (
        "the crate stops the one under the deck, in both runtimes, on the same ticks")
    assert min(r[0] for r in single[1]) / 32 > crate_east, "short of the crate"
    # (the actors are live solids: on the deck's own level, one in the way stops it)
    beside = sprite(at[0] - 40.0, at[1], room._template_size(), {**room.template, "elevation": 64.0})
    blocked = run_single_player(sp, room, starts[:1], [on], extra_solids=(beside,))[0]
    assert any(r[4] for r in blocked[:11]), "a solid on its own level blocks it"


def test_a_changed_collider_is_detected(project: Path, room: SceneRoom, traces: tuple) -> None:
    """M1-A-2's mechanism: a client whose crossing has its deck collider 0.5 m higher builds another digest, so the
    join guard refuses it; were it let in, it would walk differently."""
    from mesh_net.scene_client import JoinRefused, check_window_world
    from tests.test_mesh_net_hd2d import raised_deck

    theirs = single_player_world(project, raised_deck((project / MODEL).read_bytes()))
    assert theirs[0].collision_digest() != room.digest
    with pytest.raises(JoinRefused, match="differs"):
        check_window_world(SimpleNamespace(hd2d_world=theirs[0], hd2d_error=None), room)
    walked = run_single_player(theirs, room, [(*room.spawn, 0.0)], [ticks(ROUTE)])[0]
    assert walked != traces[1], "the harness tells the two worlds apart"


def defined_names(source: str) -> set[str]:
    """Every name ``source`` defines: functions (async too) and classes, and every name or attribute an assignment
    binds, however nested its target (``a, (b, self.c) = ...``)."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        targets = (node.targets if isinstance(node, ast.Assign) else [node.target]
                   if isinstance(node, (ast.AnnAssign, ast.AugAssign)) else [])
        for target in targets:
            for part in ast.walk(target):
                if isinstance(part, ast.Name):
                    names.add(part.id)
                elif isinstance(part, ast.Attribute):
                    names.add(part.attr)
    return names


def test_the_authority_has_no_floor_solver_of_its_own(room: SceneRoom, monkeypatch: pytest.MonkeyPatch) -> None:
    """mesh_net defines no ``stand``, ``STEP`` or other piece of the floor solver: World.move does it all, given
    mesh_net.scene_room.move (N6's Arcade-free 2D sweep) as its sweep."""
    solver = {"stand", "STEP", "BODY", "DEEP", "heights_at", "_settle", "_step", "_on_level", "excess", "Surface"}
    for path in sorted((REPO / "mesh_net").rglob("*.py")):
        assert not defined_names(path.read_text(encoding="utf-8")) & solver, f"{path.relative_to(REPO)} defines a solver part"
    for source in ("STEP, BODY = 0.35, 1.5", "async def stand(): pass", "self.excess = 0", "[a, *heights_at] = b",
                   "STEP += 1", "class Surface: pass"):  # (what the scan must catch)
        assert defined_names(source) & solver, source
    calls: list[Any] = []
    original = World.move

    def spy(self: World, *args: Any, **kwargs: Any) -> None:
        calls.append(kwargs.get("sweep"))
        original(self, *args, **kwargs)

    monkeypatch.setattr(World, "move", spy)
    eid = room.join()
    room.input(eid, {"v": 1, "type": "input", "entity": eid, "seq": 1, "dx": 1, "dy": 1})
    room.step()
    room.leave(eid)
    assert calls == [scene_room.move], "the authority's movement is World.move with its sweep"

