"""#461 R4B: where characters may go into water, in the real game and Studio, hidden windows (GL-gated:
MESH_GL_SMOKE=1).

Play (the R3 study village: a stream deep but for a ford, a bridge over it; the R4 study village: a stream into a
natural pond), with the window's own keys:
- a stream set to "block": the player stops at its edge, even at the ford, and still crosses on the bridge's deck;
- set to "wade" (1 m): the player wades across its deep (0.8 m) stretch;
- a pond that blocks: the player stops at its visible shore, not at the box round it;
- an NPC whose route starts in the deep stream walks out (never deeper) and goes on.
Studio: the River panel's and the water inspector's Walking into it choices, one undo step each. Export: the bundle
keeps them, and its room walks the same."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from engine import optional_arcade

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                       reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)"),
    pytest.mark.filterwarnings("ignore:draw_text is an extremely slow function"),
    pytest.mark.filterwarnings("ignore:UIInputText is now a UIStyledWidget:DeprecationWarning"),
    pytest.mark.filterwarnings("ignore:.*style dict.*:DeprecationWarning"),
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))
P = 32.0


def _edit(project: Path, change: Any) -> None:
    from hd2d_demo import SCENES

    path = project / SCENES / "start.json"
    scene = change(json.loads(path.read_text(encoding="utf-8")))
    path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")


def test_a_stream_set_to_block_or_wade_is_walked_so_whatever_its_depth(tmp_path: Path) -> None:
    import r3_river_bed_study as study
    from hd2d_demo import SCENES, HiddenGame

    from engine import project_ops as ops

    blocked = study.make_project(tmp_path, "block", carved=True)
    _edit(blocked, lambda s: ops.set_river(s, "brook", passable="block"))
    game = HiddenGame(blocked, size=(1280, 720))
    try:
        game.load(f"{SCENES}/start.json")
        game.step(3)
        left = game.arcade.key.A
        ford = study.walk(game, (study.EAST_BANK_X, study.FORD_Y, 0.0), left, 150)
        assert ford["x"] > 690.0 and ford["deepest"] == 0.0, ("stopped at its edge, even at the ford", ford)
        deck = study.walk(game, study.DECK, left, 150)
        assert deck["x"] < 600.0 and abs(deck["z"] - study.DECK[2]) < 0.05, ("across on the bridge's deck", deck)
    finally:
        game.close()
    waded = study.make_project(tmp_path, "wade", carved=True)
    _edit(waded, lambda s: ops.set_river(s, "brook", passable="wade", wade_depth=1.0))
    game = HiddenGame(waded, size=(1280, 720))
    try:
        game.load(f"{SCENES}/start.json")
        game.step(3)
        deep = study.walk(game, (study.EAST_BANK_X, study.DEEP_Y, 0.0), game.arcade.key.A, 200)
        assert deep["x"] < study.WEST_BANK_X + 16 and 0.5 < deep["deepest"] <= 1.0, ("waded across the deep", deep)
    finally:
        game.close()


def test_a_blocking_pond_stops_the_player_at_its_shore_not_its_box(tmp_path: Path) -> None:
    import r3_river_bed_study as walker
    import r4_river_mouth_study as study
    from hd2d_demo import SCENES, HiddenGame

    from engine import project_ops as ops
    from engine.water import extent, inside

    project = study.make_project(tmp_path, "pond", carved=True)
    pond = study.pond_id(project)
    _edit(project, lambda s: ops.set_water(s, pond, walkable=False))  # (auto: blocks, as Lakeside's lake)
    scene = study.scene_of(project)
    entity = ops.find_entity(scene, pond)
    assert entity.get("solid") is True, "(its 2D box is there, as before: a 3D room no longer meets it)"
    game = HiddenGame(project, size=(1280, 720))
    try:
        game.load(f"{SCENES}/start.json")
        game.step(3)
        body = game.window.water_bodies[0]
        centre = (float(body.entity.center_x), float(body.entity.center_y))
        y = study.POND["y"] + 0.8 * study.POND["height"] / 2  # (off its middle: its shore well inside its box)
        shore = next(x for x in range(1100, 300, -1) if inside(body.water, centre, (x, y)))
        box_right = centre[0] + extent(body.water)[0] / 2
        went = walker.walk(game, (box_right + 120.0, y, 0.0), game.arcade.key.A, 240)
        assert went["x"] < box_right - 8, ("past where its box began", went, box_right)
        assert shore < went["x"] < shore + 40, ("stopped at its shore", went, shore)
    finally:
        game.close()


def test_an_npc_put_in_deep_water_walks_out_and_goes_on(tmp_path: Path) -> None:
    import r3_river_bed_study as study
    from hd2d_demo import SCENES, HiddenGame

    from engine.physics_runtime import _sprite_to_aabb

    project = study.make_project(tmp_path, "npc", carved=True)
    start_x = 610.0  # (the deep stretch's middle, at DEEP_Y)

    def add_npc(scene: dict[str, Any]) -> dict[str, Any]:
        scene["entities"].append({
            "id": "wader", "prefab_id": "person", "mesh_name": "Wader", "x": start_x, "y": study.DEEP_Y + 18.0,
            "elevation": -24.0, "behaviours": ["FloorRoute"],
            # (feet as wide as the player's: the person picture's own box, 2.4 m, can't fit in a 3 m channel at all)
            "components": {"collider": {"kind": "box", "offset_x": 0.0, "offset_y": -18.0, "w": 24.0, "h": 12.0}},
            "behaviour_config": {"FloorRoute": {"route": [[800.0, 1000.0, 0.0], [800.0, 1060.0, 0.0]],
                                                "speed": 60.0, "wait": 0.5}}})
        return scene

    _edit(project, add_npc)
    game = HiddenGame(project, size=(1280, 720))
    try:
        game.load(f"{SCENES}/start.json")
        game.step(2)
        world = game.window.hd2d_world
        npc = game.sprite("Wader")
        box = _sprite_to_aabb(npc)
        floor = min(h for h, _s in world.heights_at(box.x / P, box.y / P))
        npc.mesh_entity_data["elevation"] = floor * P  # (on the bed, deep)
        start = world.deepest(box.x / P, box.y / P, floor, box.w / 64, box.h / 64)
        assert start > 0.5, start
        deepest = start
        for _ in range(360):
            game.step(1)
            box = _sprite_to_aabb(npc)
            z = npc.mesh_entity_data["elevation"] / P
            deepest = max(deepest, world.deepest(box.x / P, box.y / P, z, box.w / 64, box.h / 64))
        assert deepest <= start + 0.05 + 1e-9, ("never deeper", start, deepest)
        assert world.stand(box.x / P, box.y / P, z, 0.3, 0.19) is not None, "out of the deep water"
        assert getattr(npc, "mesh_hd2d_stranded", None) is None and npc.center_x > 700, ("on its way", npc.center_x)
    finally:
        game.close()


def test_studio_sets_walking_into_it_for_a_stream_and_a_pond_one_undo_step_each(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import r4_river_mouth_study as study
    from hd2d_studio_demo import StudioDriver

    from engine import project_ops as ops

    monkeypatch.setenv("MESH_STUDIO_NO_AI_BRIDGE", "1")
    project = study.make_project(tmp_path, "studio", carved=True)
    pond = study.pond_id(project)
    d = StudioDriver(project)
    try:
        k, studio = d.arcade.key, d.studio
        d.button("Terrain")
        d.button("River")
        d.button("Select 'brook'")

        def brook() -> dict[str, Any]:
            return dict(ops.rivers(studio.project.scene())[0])

        undo0 = len(studio.project._undo)
        d.button("Block")
        assert brook().get("passable") == "block" and len(studio.project._undo) == undo0 + 1
        d.button("Wade")
        d.type_into("river_wade_depth", "1.2")
        assert brook().get("passable") == "wade" and brook().get("wade_depth") == 1.2
        d.key(k.Z, k.MOD_CTRL)
        d.key(k.Z, k.MOD_CTRL)
        assert brook().get("passable") == "block", "undone: one step each"
        d.key(k.Z, k.MOD_CTRL)
        assert "passable" not in brook(), "as before"
        d.button("River")  # (River off: the inspector)
        studio.select(pond)
        d.advance(2)
        d.button("Block")
        water = ops.water_of(ops.find_entity(studio.project.scene(), pond))
        assert water is not None and water["passable"] == "block"
        d.key(k.Z, k.MOD_CTRL)
        water = ops.water_of(ops.find_entity(studio.project.scene(), pond))
        assert water is not None and water["passable"] == "auto"
    finally:
        d.close()


def test_passable_survives_save_export_and_reload(tmp_path: Path) -> None:
    import dataclasses

    import r4_river_mouth_study as study

    from engine import project_ops as ops
    from engine.hd2d.river import ponds_of
    from engine.hd2d.settings import parse_hd2d
    from engine.hd2d.world import World
    from engine.tooling.export_bundle import build_bundle

    project = study.make_project(tmp_path, "export", carved=True)
    pond = study.pond_id(project)
    _edit(project, lambda s: ops.set_water(ops.set_river(s, "brook", passable="wade", wade_depth=0.6), pond,
                                           passable="block"))
    code, _manifest = build_bundle(project, tmp_path / "bundle", deterministic=True)
    assert code == 0
    rel = f"{study.SCENES}/start.json"
    exported = next(p for p in (tmp_path / "bundle").rglob("start.json") if p.as_posix().endswith(rel))
    source = json.loads((project / rel).read_text(encoding="utf-8"))
    copied = json.loads(exported.read_text(encoding="utf-8"))
    assert copied["settings"]["hd2d"]["rivers"] == source["settings"]["hd2d"]["rivers"]
    assert copied["entities"] == source["entities"]
    answers = []
    for s in (source, copied):
        world = World(dataclasses.replace(parse_hd2d(s["settings"]["hd2d"]), structures=()), {},
                      ponds_of(s["entities"]))
        answers.append([world.stand(x / P, y / P, min(h for h, _s in world.heights_at(x / P, y / P)), 0.3, 0.19)
                        is not None for x in range(500, 760, 20) for y in (1000, 1150, 1240)])
    assert answers[0] == answers[1] and not all(answers[0]), answers
