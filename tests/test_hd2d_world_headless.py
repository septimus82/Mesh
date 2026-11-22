"""HD-2D online M1-A-1: one collision world, built by one builder (engine.hd2d.world.build_world) that reads its own
models, for single-player, Mesh Studio and the graphics-free net authority; moving through it needs no Arcade (the 2D
sweep is passed in); and a collision fingerprint (World.collision_digest) that is the same in every process."""

from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from engine.hd2d.glb import GlbError
from engine.hd2d.scatter import ASSETS
from engine.hd2d.settings import parse_hd2d
from engine.hd2d.world import World, build_world

REPO = Path(__file__).resolve().parents[1]
CROSSING = REPO / "tooling" / "hd2d_assets" / "stone_crossing.glb"
BOULDER = ASSETS["boulder"].model


def _deck_glb(path: Path, deck: float = 2.0, colour: tuple[float, float, float] = (1.0, 0.0, 0.0)) -> Path:
    """A one-triangle model: drawn ("art", in ``colour``) and a walkable deck ``deck`` m up (a floor collider)."""
    tri = struct.pack("<9f", 0, deck, 0, 4, deck, 0, 0, deck, -4)  # (glTF is Y-up)
    doc = {"asset": {"version": "2.0"}, "scenes": [{"nodes": [0, 1]}],
           "nodes": [{"name": "art", "mesh": 0}, {"name": "col_deck", "mesh": 1, "extras": {"mesh_collision": "floor"}}],
           "materials": [{"pbrMetallicRoughness": {"baseColorFactor": [*colour, 1.0]}}],
           "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "material": 0}]},
                      {"primitives": [{"attributes": {"POSITION": 0}}]}],
           "buffers": [{"byteLength": len(tri)}], "bufferViews": [{"buffer": 0, "byteLength": len(tri)}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"}]}
    js = json.dumps(doc).encode()
    js += b" " * (-len(js) % 4)
    body = struct.pack("<I4s", len(js), b"JSON") + js + struct.pack("<I4s", len(tri), b"BIN\0") + tri
    path.write_bytes(b"glTF" + struct.pack("<II", 2, 12 + len(body)) + body)
    return path


def _crossing(scatter: dict[str, Any] | None = None, **structure: Any) -> dict[str, Any]:
    return {"structures": [{"id": "crossing", "model": "crossing.glb", "x": 512, "y": 384, **structure}],
            "ground": {"to": [1024, 768]}, **({"scatter": scatter} if scatter else {})}


def _resolve(root: Path | None = None) -> Any:
    files = {"crossing.glb": CROSSING}
    return lambda rel: files.get(rel, (root or REPO / "nowhere") / rel)


def _digest(hd2d: dict[str, Any], resolve: Any = None, entities: Any = None) -> str:
    world, _models, _aside = build_world(parse_hd2d(hd2d), entities, resolve or _resolve())
    assert world is not None
    return world.collision_digest()


@pytest.mark.fast
def test_the_builder_reads_the_structures_and_blocking_scatter_itself() -> None:
    settings = parse_hd2d(_crossing({"boulder": [[128, 96, 0, 100]], "grass_tuft": [[200, 96, 0, 100]]}))
    world, models, set_aside = build_world(settings, [], _resolve())
    assert set(models) == {"crossing.glb", BOULDER} and set_aside == {}
    assert world is not None and world._models is models, "the World reads the dict the renderer is given"
    assert [w.name for w in world.walls if w.name.startswith("scatter:")], "the boulder blocks"
    assert world.stand(4.0, 3.0, 0.0, 0.3, 0.19) is None and world.stand(16.0, 3.0, 0.0, 0.3, 0.19) == (0.0, "ground")


@pytest.mark.fast
def test_a_room_gets_a_world_by_runtimes_rule_and_studio_can_ask_for_one() -> None:
    flat = parse_hd2d({"ground": {"to": [640, 480]}})
    world, models, _ = build_world(flat, None, _resolve())
    assert world is None and models == {}, "nothing to collide with: the room keeps 2D movement"
    assert isinstance(build_world(flat, None, _resolve(), always=True)[0], World)
    given: dict[str, Any] = {}
    assert build_world(parse_hd2d(_crossing()), None, _resolve(), models=given)[1] is given, "read in place"


@pytest.mark.fast
def test_an_unreadable_structure_fails_the_build_and_an_unreadable_scatter_model_is_set_aside(tmp_path: Path) -> None:
    (tmp_path / "broken.glb").write_bytes(b"not a model")
    with pytest.raises(GlbError, match="broken.glb"):
        build_world(parse_hd2d({"structures": [{"model": "broken.glb"}], "ground": {"to": [640, 480]}}), None,
                    lambda rel: tmp_path / rel)
    (tmp_path / BOULDER).parent.mkdir(parents=True)
    (tmp_path / BOULDER).write_bytes(b"not a model either")  # (the project's own copy, found before Mesh's)
    world, models, set_aside = build_world(parse_hd2d(_crossing({"boulder": [[128, 96, 0, 100]]})), None,
                                           _resolve(tmp_path))
    assert world is not None and BOULDER not in models and list(set_aside) == [BOULDER]
    assert "can't be read" in set_aside[BOULDER]
    assert not [w for w in world.walls if w.name.startswith("scatter:")], "set aside: it blocks nothing"
    assert world.stand(4.0, 3.0, 0.0, 0.3, 0.19) == (0.0, "ground")


@pytest.mark.integration
def test_single_player_plays_a_room_whose_structure_cant_be_read_2d(tmp_path: Path) -> None:
    from engine.hd2d.runtime import configure_scene
    from engine.paths import get_content_roots, set_content_roots

    (tmp_path / "broken.glb").write_bytes(b"not a model")
    roots = get_content_roots()
    set_content_roots([tmp_path])
    try:
        window = SimpleNamespace(hd2d_renderer=None)
        configure_scene(window, {"hd2d": {"structures": [{"model": "broken.glb"}], "ground": {"to": [640, 480]}}})
    finally:
        set_content_roots(roots)
    assert window.hd2d_renderer is None and window.hd2d_world is None
    assert "broken.glb" in window.hd2d_error


@pytest.mark.fast
def test_studios_new_collision_world_comes_from_the_builder_with_the_rooms_ponds() -> None:
    from engine.studio_hd2d import Hd2dView

    pond = {"id": "pond", "x": 160, "y": 160, "behaviour_config": {"WaterSurface": {"preset": "pond", "walkable": False}}}
    renderer = SimpleNamespace(settings=parse_hd2d({"ground": {"to": [640, 480]}}), models={}, _resolve=_resolve())
    view = SimpleNamespace(studio=SimpleNamespace(project=SimpleNamespace(scene=lambda: {"entities": [pond]})))
    world = Hd2dView._new_world(view, renderer)  # (unbound: only what it reads)
    assert isinstance(world, World) and world._models is renderer.models
    assert [p.id for p, _box in world.ponds] == ["pond"], "Studio's collision world has the ponds play has"


@pytest.mark.fast
def test_the_fingerprint_follows_collision_and_only_collision(tmp_path: Path) -> None:
    base = _digest(_crossing({"boulder": [[128, 96, 0, 100]]}))
    assert _digest(_crossing({"boulder": [[128, 96, 0, 100]]})) == base, "identical rooms"
    assert _digest(_crossing({"boulder": [[128, 96, 0, 100]]}, x=513)) != base, "the walls moved (1 px)"
    assert _digest(_crossing({"boulder": [[128, 96, 0, 100]]}, elevation=1)) != base, "the deck raised"
    assert _digest(_crossing({"boulder": [[128, 97, 0, 100]]})) != base, "the boulder moved"
    assert _digest(_crossing({"boulder": [[128, 96, 0, 100], [700, 96, 0, 100]]})) != base, "a boulder added"
    assert _digest(_crossing({"boulder": [[128, 96, 0, 100]], "grass_tuft": [[200, 96, 0, 100]]})) == base, \
        "grass blocks nothing"
    lit = {**_crossing({"boulder": [[128, 96, 0, 100]]}), "ambient": 0.3, "sky": [10, 20, 30]}
    assert _digest(lit) == base, "lighting is drawn, not collided with"

    room = {"structures": [{"id": "deck", "model": "deck.glb", "x": 64, "y": 64}], "ground": {"to": [640, 480]}}
    resolve = tmp_path.joinpath
    _deck_glb(tmp_path / "deck.glb")
    deck = _digest(room, resolve)
    _deck_glb(tmp_path / "deck.glb", colour=(0.0, 0.0, 1.0))
    assert _digest(room, resolve) == deck, "a texture/colour change only: the same collision"
    _deck_glb(tmp_path / "deck.glb", deck=2.01)
    assert _digest(room, resolve) != deck, "the collider moved 1 cm"

    pond = {"id": "pond", "x": 300, "y": 300, "behaviour_config": {"WaterSurface": {"preset": "pond", "walkable": False}}}
    wet = _digest(_crossing(), entities=[pond])
    assert wet != _digest(_crossing()), "a pond's rule is collision"
    assert _digest(_crossing(), entities=[{**pond, "x": 301}]) != wet


# A child process: builds the crossing room (a structure, a scatter boulder, sculpted ground) with the builder, walks a
# net Body up the stairs and across the bridge and another into the boulder with the authority's Arcade-free sweep,
# prints its fingerprint, and says what graphics or Studio modules it loaded.
_CHILD = r"""
import json, sys
from pathlib import Path
from engine.hd2d.settings import parse_hd2d
from engine.hd2d.world import build_world
from mesh_net.scene_room import Body, move

hd2d, crossing = json.loads(sys.argv[1]), Path(sys.argv[2])
world, models, aside = build_world(parse_hd2d(hd2d), [], lambda rel: crossing if rel == "crossing.glb" else Path("x") / rel)
assert world is not None and world.terrain is not None and not aside, aside

def body(x, y):
    return Body(x * 32, y * 32 + 18, 32.0, 48.0, {"elevation": 0.0, "components": {"collider": {"kind": "box", "auto": True}}})

hero = body(10, 3)
for _ in range(110):
    world.move(hero, (0, 2.5), [], sweep=move)
assert hero.mesh_entity_data["elevation"] == 64.0 and hero.mesh_hd2d_floor == "crossing/col_platform_west", hero
for _ in range(200):
    world.move(hero, (2.5, 0), [], sweep=move)
assert hero.mesh_entity_data["elevation"] == 64.0 and hero.center_x / 32 > 19, "across the bridge"
walker = body(1.5, 3)
for _ in range(80):
    world.move(walker, (2.5, 0), [], sweep=move)
assert 2.5 < walker.center_x / 32 < 4.0 and walker.mesh_entity_data["elevation"] == 0.0, walker
print(json.dumps({"digest": world.collision_digest(),
                  "loaded": [k for k in ("arcade", "pyglet", "engine.game", "engine.studio", "engine.physics_runtime")
                             if k in sys.modules]}))
"""


@pytest.mark.integration
def test_the_world_is_built_and_walked_without_graphics_and_its_fingerprint_is_the_same_in_every_process() -> None:
    from engine import project_ops as ops

    room = {"entities": [], "settings": {"world_width": 1024, "world_height": 768,
                                         "hd2d": _crossing({"boulder": [[128, 96, 0, 100]]})}}
    hd2d = ops.sculpt_terrain_stroke(room, "raise", [[940, 700, 40]], 64)["settings"]["hd2d"]  # (a hill off the way)
    here = _digest(hd2d)
    for seed in ("1", "2"):
        env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(REPO)}
        out = subprocess.run([sys.executable, "-c", _CHILD, json.dumps(hd2d), str(CROSSING)], cwd=REPO, env=env,
                             capture_output=True, text=True, check=False)
        assert out.returncode == 0, out.stderr
        got = json.loads(out.stdout.strip().splitlines()[-1])
        assert got["loaded"] == [], f"graphics or Studio loaded: {got['loaded']}"
        assert got["digest"] == here, "the same room, the same fingerprint, in any process"
