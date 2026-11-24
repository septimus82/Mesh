"""M4-4 (owner decision OD7): FloorRoute's decision logic is one shared, graphics-free model (engine.hd2d.route).

Single-player's ``FloorRoute`` behaviour is a thin adapter over it, and it walks exactly as it walked before the model
was extracted: its traces (position, elevation, floor, velocity, stranded) on four scenarios, recorded from the
behaviour as it was at 94f1792c (before M4-4) into ``tests/fixtures/floor_route_traces.json``, are walked again here:

- ``warden_20hz``: the floors demo's warden route (east platform 2 m up, its stairs, the ground, under the bridge and
  back up) at the authority's tick, 1/20 s;
- ``blocked_20hz``: the same route with a solid crate on its first ground point: it plans again and again, then gives
  that point up for a while (said once);
- ``walk_out_60hz``: put in a river's deep water, it walks out, never deeper, and on with its route (#461 R4B);
- ``stranded_60hz``: at the bottom of a pit in blocking water with no way out: stranded, said once.

Recorded with ``record()`` below (run from a checkout of the old behaviour); the scenario builders here are the
ones that recorded them.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable
from unittest import mock

import pytest

from engine.hd2d.world import World

pytestmark = pytest.mark.integration  # (builds projects in folders, reads models)

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "floor_route_traces.json"
SCENE = "packs/core_regions/scenes/start.json"
CRATE = {"id": "crate", "x": 704.0, "y": 96.0 + 18.0, "solid": True,
         "components": {"collider": {"kind": "box", "w": 40, "h": 40}}}  # (on the warden's first ground point)


def floors_demo(folder: Path) -> Path:
    """tooling/hd2d_floors_demo.py's crossing, built into ``folder``."""
    sys.path.insert(0, str(REPO / "tooling"))
    try:
        import hd2d_floors_demo
    finally:
        sys.path.remove(str(REPO / "tooling"))
    return Path(hd2d_floors_demo.build(folder))


def crossing(project: Path, extra: list[dict[str, Any]] = ()) -> tuple[World, dict[str, Any], tuple[float, float],
                                                                         list[SimpleNamespace]]:
    """The World single-player builds for the crossing (as tests/test_hd2d_net_parity.py does), the warden as loaded,
    its picture size, and the room's solid sprites (``extra`` entities added to the scene)."""
    from engine.hd2d.settings import parse_hd2d
    from engine.hd2d.world import build_world
    from engine.scene_loader import SceneLoader
    from mesh_net.scene_room import contained, picture_size

    path = project / SCENE
    if extra:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["entities"] += [dict(e) for e in extra]
        path.write_text(json.dumps(data), encoding="utf-8")
    scene = SceneLoader().load_scene(str(path))
    settings = scene["settings"]
    hd2d = parse_hd2d(settings["hd2d"], map_size_px=(settings["world_width"], settings["world_height"]), lenient=True)
    world = build_world(hd2d, scene["entities"], contained(project))[0]
    assert isinstance(world, World)
    warden = next(e for e in scene["entities"] if e["id"] == "warden")
    size = picture_size(warden, project)
    assert size is not None
    solids = [walker(e, (0.0, 0.0)) for e in scene["entities"] if e.get("solid")]
    return world, warden, size, solids


class Walker(SimpleNamespace):
    """A game sprite as FloorRoute and World.move read it."""

    @property
    def bottom(self) -> float:
        return float(self.center_y) - float(self.height) / 2


def walker(entity: dict[str, Any], size: tuple[float, float]) -> Walker:
    return Walker(center_x=float(entity["x"]), center_y=float(entity["y"]), width=size[0], height=size[1], scale_x=1.0,
                  mesh_name=str(entity.get("mesh_name") or ""), mesh_entity_data=json.loads(json.dumps(entity)))


def run(sprite: Any, world: World, config: dict[str, Any], dt: float, frames: int,
        solids: list[Any] = ()) -> dict[str, Any]:
    """The FloorRoute behaviour on ``sprite`` in a window with ``world`` and ``solids``, updated ``frames`` times at
    ``dt``: a row per update (x, y px; elevation px; floor; velocity px/s; stranded), and what it said (its log
    warnings and gameplay events)."""
    from engine.behaviours import floor_route

    said: list[str] = []
    window = SimpleNamespace(hd2d_world=world, scene_controller=SimpleNamespace(solid_sprites=list(solids)))
    behaviour = floor_route.FloorRouteBehaviour(sprite, window, **config)
    rows = []
    with (mock.patch.object(floor_route.logger, "warning", lambda msg, *a: said.append(msg % a)),
          mock.patch("engine.event_emit.emit_gameplay_event",
                     lambda _w, kind, payload, **_k: said.append(f"event {kind} {sorted(payload.items())}"))):
        for _ in range(frames):
            behaviour.update(dt)
            rows.append([sprite.center_x, sprite.center_y, sprite.mesh_entity_data.get("elevation", 0.0),
                         getattr(sprite, "mesh_hd2d_floor", None), getattr(sprite, "mesh_velocity_x", 0.0),
                         getattr(sprite, "mesh_velocity_y", 0.0), bool(getattr(sprite, "mesh_hd2d_stranded", None))])
    return {"rows": rows, "said": said}


def warden(folder: Path, dt: float, frames: int, extra: list[dict[str, Any]] = ()) -> dict[str, Any]:
    """The warden walking its route in the crossing, loaded as the game loads it (the project the current folder:
    mesh_net.scene_room.disposable_project)."""
    from mesh_net.scene_room import disposable_project

    built = floors_demo(folder)
    files = {p.relative_to(built).as_posix(): p.read_bytes() for p in built.rglob("*") if p.is_file()}
    with disposable_project(files, scaffold=False) as root:
        world, entity, size, solids = crossing(root, extra)
        return run(walker(entity, size), world, entity["behaviour_config"]["FloorRoute"], dt, frames, solids)


def water(build: Callable[[], dict[str, Any]], x: float, y: float, route: list[list[float]], frames: int) -> dict[str, Any]:
    """tests/test_water_passable.py's NPC (a 32 x 48 px character, its feet box automatic) put at (x, y) px."""
    from tests.test_water_passable import _floor, _world

    world = _world(build())
    z = _floor(world, x, y)
    npc = Walker(center_x=x, center_y=y + 18, width=32.0, height=48.0, scale_x=1.0, mesh_name="Npc",
                 mesh_entity_data={"elevation": z * 32.0, "components": {"collider": {"kind": "box", "auto": True}}})
    return run(npc, world, {"route": route, "speed": 60.0, "wait": 0.0}, 1 / 60, frames)


def scenarios(folder: Path) -> dict[str, Callable[[], dict[str, Any]]]:
    from tests.test_water_passable import _room, _uneven

    return {
        "warden_20hz": lambda: warden(folder / "warden", 1 / 20, 900),
        "blocked_20hz": lambda: warden(folder / "blocked", 1 / 20, 400, [CRATE]),
        "walk_out_60hz": lambda: water(_room, 200.0, 600.0, [[200.0, 800.0, 0.0], [300.0, 800.0, 0.0]], 600),
        "stranded_60hz": lambda: water(_uneven, 1082.0, 292.0, [[200.0, 800.0, 0.0]], 720),
    }


SAMPLE = 25  # every this many updates' rows are kept in full (to show where a trace departs); all are digested


def digest(rows: list[list[Any]]) -> str:
    """Every row, its numbers to 1e-3 (px, px/s), as one SHA-256."""
    rounded = [[round(v, 3) if isinstance(v, float) else v for v in row] for row in rows]
    return hashlib.sha256(json.dumps(rounded, separators=(",", ":")).encode()).hexdigest()


def recording(trace: dict[str, Any]) -> dict[str, Any]:
    return {"updates": len(trace["rows"]), "digest": digest(trace["rows"]), "said": trace["said"],
            "samples": [[i, *row] for i, row in enumerate(trace["rows"]) if i % SAMPLE == 0 or i == len(trace["rows"]) - 1]}


def record(folder: Path) -> None:
    """Write the fixture from the behaviour this checkout has (run once, before the extraction)."""
    FIXTURE.write_text(json.dumps({name: recording(make()) for name, make in scenarios(folder).items()},
                                  indent=0) + "\n", encoding="utf-8")


def assert_same_trace(name: str, got: dict[str, Any], want: dict[str, Any]) -> None:
    assert len(got["rows"]) == want["updates"], name
    for i, *b in want["samples"]:
        a = got["rows"][i]
        assert abs(a[0] - b[0]) <= 1e-4 and abs(a[1] - b[1]) <= 1e-4, f"{name} update {i}: x/y {a[:2]} != {b[:2]}"
        assert abs(a[4] - b[4]) <= 1e-3 and abs(a[5] - b[5]) <= 1e-3, f"{name} update {i}: velocity {a[4:6]} != {b[4:6]}"
        assert a[2:4] == b[2:4] and a[6] == b[6], f"{name} update {i}: (elevation, floor) {a[2:4]} != {b[2:4]}, stranded"
    assert got["said"] == want["said"], name
    assert digest(got["rows"]) == want["digest"], f"{name}: the same at every sample, but some update differs"


@pytest.fixture(scope="module")
def recorded() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["warden_20hz", "blocked_20hz", "walk_out_60hz", "stranded_60hz"])
def test_single_player_walks_exactly_as_before_the_extraction(name: str, recorded: dict[str, Any],
                                                              tmp_path: Path) -> None:
    assert_same_trace(name, scenarios(tmp_path)[name](), recorded[name])


def test_the_recorded_traces_cover_legs_waits_floors_replans_walk_out_and_stranding(recorded: dict[str, Any]) -> None:
    """What the fixture pins (so a scenario that stopped exercising its case can't pass vacuously)."""
    warden_rows = [row[1:] for row in recorded["warden_20hz"]["samples"]]
    assert {"crossing/col_platform_east", "crossing/col_stairs_east", "ground"} <= {
        r[3] for r in warden_rows}, "down the stairs and back up"
    assert any(r[4:6] == [0.0, 0.0] for r in warden_rows) and any(r[4:6] != [0.0, 0.0] for r in warden_rows), (
        "it walks and it stands (at its points)")
    assert sum("can't get through" in s for s in recorded["blocked_20hz"]["said"]) == 1, "replans, then backs off once"
    walk_out = recorded["walk_out_60hz"]["samples"]
    assert not walk_out[0][7] and not walk_out[-1][7] and walk_out[-1][2] > 700, "walked out and on its route"
    stranded = recorded["stranded_60hz"]
    assert stranded["samples"][-1][7] and sum("is stranded" in s for s in stranded["said"]) == 1
    assert sum(s.startswith("event stranded") for s in stranded["said"]) == 1
