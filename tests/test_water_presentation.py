"""Milestone 19B: water that belongs to its place, headless: the presets with banks and depths, irregular and turned
shapes (what is walked through is what is drawn), the room's reflection setting, the checked edits Studio and AI make,
and Stage 19A's water kept as it was. The drawing is tests/test_water_gpu.py."""

from __future__ import annotations

import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine import authoring, water
from engine import project_ops as ops
from engine.hd2d.settings import Hd2dSettingsError, parse_hd2d

pytestmark = pytest.mark.fast


def test_the_new_presets_have_banks_and_depths_and_19a_s_are_unchanged() -> None:
    for name, shore in (("muddy_puddle", "mud"), ("natural_pond", "grass"), ("stone_pool", "stone")):
        w = water.parse_water({"preset": name})
        assert w.shore == shore and w.shore_width > 0 and 0 < w.depth <= 1 and w.ripples == 1.0, name
    # Stage 19A's presets, exactly as accepted (older rooms keep their look)
    assert water.PRESETS["puddle"] == water.Water("puddle", 64.0, 40.0, (0.42, 0.50, 0.58), 0.62, "ellipse", 0.15, 0.85,
                                                  True, True, "")
    assert water.PRESETS["pond"] == water.Water("pond", 224.0, 144.0, (0.16, 0.36, 0.42), 0.84, "ellipse", 0.6, 0.35,
                                                True, True, "")
    assert set(water.PRESET_NAMES) == set(water.PRESETS)


def test_a_natural_outline_is_irregular_fits_its_size_and_is_the_seed_s() -> None:
    w = water.parse_water({"preset": "natural_pond"})
    c0, amp, phase = water.outline(w)
    radii = [c0 + sum(a * math.cos((k + 2) * th + p) for k, (a, p) in enumerate(zip(amp, phase)))
             for th in (i * math.tau / 720 for i in range(720))]
    assert max(radii) <= 1.0 + 1e-9, "inside the ellipse its width and height make (Studio's handles mean it)"
    assert min(radii) > 0.55 and max(radii) - min(radii) > 0.1, "irregular, not a sliver"
    assert water.outline(w) == water.outline(water.parse_water({"preset": "natural_pond"})), "the same seed, the same"
    assert water.outline(w) != water.outline(water.parse_water({"preset": "natural_pond", "seed": 2}))
    assert water.outline(water.parse_water({"preset": "pond"})) == (1.0, (0.0,) * 4, (0.0,) * 4), "an ellipse"


def test_what_is_walked_through_is_the_outline_drawn() -> None:
    for raw in ({"preset": "natural_pond", "rotation": 30}, {"preset": "stone_pool", "rotation": -70},
                {"preset": "pond", "rotation": 45}):
        w = water.parse_water(raw)
        centre = (500.0, 300.0)
        for (x, y) in water.outline_points(w, centre, 36):
            inner = (centre[0] + (x - centre[0]) * 0.97, centre[1] + (y - centre[1]) * 0.97)
            outer = (centre[0] + (x - centre[0]) * 1.03, centre[1] + (y - centre[1]) * 1.03)
            assert water.inside(w, centre, inner) and not water.inside(w, centre, outer), (raw, x, y)


def test_turning_water_turns_where_it_is() -> None:
    long = water.parse_water({"preset": "pond", "width": 200, "height": 40})
    turned = water.parse_water({"preset": "pond", "width": 200, "height": 40, "rotation": 90})
    assert water.inside(long, (0, 0), (90, 0)) and not water.inside(long, (0, 0), (0, 90))
    assert water.inside(turned, (0, 0), (0, 90)) and not water.inside(turned, (0, 0), (90, 0))
    assert water.extent(turned) == (40.0, 200.0) and water.extent(long) == (200.0, 40.0)


def test_presets_and_settings_are_made_and_changed_by_one_checked_edit() -> None:
    scene, wid = ops.place_blank({"entities": []}, "start", "Pond", 320, 240)
    pond = ops.set_water(scene, wid, preset="natural_pond", seed=12, rotation=20, shore="stone", shore_width=20,
                         deep_colour="#102030", depth=0.8, ripples=0.5)
    got = ops.water_of(ops.find_entity(pond, wid))
    assert got is not None
    assert (got["preset"], got["seed"], got["rotation"], got["shore"], got["shore_width"], got["deep_colour"],
            got["depth"], got["ripples"]) == ("natural_pond", 12, 20.0, "stone", 20.0, "#102030", 0.8, 0.5)
    simple = ops.water_of(ops.find_entity(ops.set_water(pond, wid, preset="pond"), wid))
    assert simple is not None and simple["preset"] == "pond" and "shore" not in simple, "a simple pond has no bank"
    with pytest.raises(ops.OpError, match="simple pond has no shore"):
        ops.set_water(ops.set_water(pond, wid, preset="pond"), wid, shore="mud")
    back = ops.water_of(ops.find_entity(ops.set_water(ops.set_water(pond, wid, preset="pond"), wid,
                                                      preset="natural_pond"), wid))
    assert back is not None and back["shore"] == "grass" and back["seed"] == 7, "the preset's own look again"


def test_a_turned_pond_that_blocks_blocks_the_box_round_it() -> None:
    scene, wid = ops.place_blank({"entities": []}, "start", "Pond", 0, 0)
    pond = ops.set_water(scene, wid, preset="stone_pool", width=200, height=100, rotation=90, walkable=False)
    assert ops.find_entity(pond, wid)["components"]["collider"] == {"kind": "box", "offset_x": 0.0, "offset_y": 0.0,
                                                                    "w": 100.0, "h": 200.0}


def test_the_room_chooses_how_its_water_mirrors() -> None:
    room = {"entities": [], "settings": {"hd2d": {"structures": []}}}
    half = ops.set_water_reflections(room, "half")
    assert half["settings"]["hd2d"]["water_reflections"] == "half"
    assert parse_hd2d(half["settings"]["hd2d"]).water_reflections == "half"
    assert parse_hd2d({}).water_reflections == "full", "older rooms: as Stage 19A drew them"
    assert "water_reflections" not in ops.set_water_reflections(half, "full")["settings"]["hd2d"], "the default: no key"
    with pytest.raises(ops.OpError, match="full, half, sky"):
        ops.set_water_reflections(room, "mirror")
    with pytest.raises(ops.OpError, match="isn't HD-2D"):
        ops.set_water_reflections({"entities": []}, "sky")
    with pytest.raises(Hd2dSettingsError, match="water_reflections"):
        parse_hd2d({"water_reflections": "mirror"})


def test_placeholders_mean_the_preset_s_for_the_new_settings_too() -> None:
    plain = {"preset": "natural_pond", "width": 0, "height": 0, "colour": "", "opacity": 0, "shape": "", "waves": -1,
             "reflection": -1, "rotation": 0, "seed": 0, "shore": "", "shore_width": -1, "deep_colour": "",
             "depth": -1, "ripples": -1, "target_tags": []}
    assert water.parse_water(plain) == water.PRESETS["natural_pond"]
    assert water.parse_water({**plain, "preset": "pond"}) == water.PRESETS["pond"], "a simple pond: placeholders only"
    from engine.behaviours.water_surface import WaterSurface

    declared = {k: d.default for k, d in WaterSurface.PARAM_DEFS.items() if k != "target_tags"}
    assert {k: v for k, v in declared.items() if k in water.UNSET} == water.UNSET, "what a plain add writes"


def test_ai_makes_and_reviews_the_new_water(tmp_path: Path) -> None:
    from engine.project_scaffold import create_project
    from engine.studio_project import Project

    root = tmp_path / "game"
    create_project(root, "Game", template_id="hd2d_rpg")
    project = Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"])
    room = project.current
    before = project.scene(room)
    authoring.apply(project, [{"op": "place_blank", "room": room, "name": "Pool", "x": 400, "y": 400},
                              {"op": "set_water_reflections", "room": room, "mode": "half"}])
    wid = next(e["id"] for e in project.scene(room)["entities"] if e.get("name") == "Pool")
    authoring.apply(project, [{"op": "set_water", "room": room, "entity_id": wid, "preset": "stone_pool",
                               "rotation": 15}])
    lines = authoring.summarize({"rooms": {room: before}}, {"rooms": {room: project.scene(room)}})
    assert any("adds 'Pool' (stone pool water 160 x 112)" in line for line in lines), lines
    assert any("water reflections full -> half" in line for line in lines), lines
    turned = ops.set_water(project.scene(room), wid, shore="grass")
    assert any("'Pool' water shore: (none) -> 'grass'" in line for line in authoring.summarize(
        {"rooms": {room: project.scene(room)}}, {"rooms": {room: turned}})), "the AI review names the change"
    assert "set_water_reflections" in authoring.operations()


def test_studio_places_a_muddy_puddle_and_names_the_presets() -> None:
    import inspect

    from engine import studio

    assert 'preset="muddy_puddle"' in inspect.getsource(studio.Studio)
    assert water.PRESET_NAMES["natural_pond"] == "Natural pond"


def test_studio_s_outline_and_handles_follow_a_turned_water() -> None:
    from engine.studio import Studio, _water_settings

    entity = {"id": "w", "x": 100.0, "y": 100.0, "behaviours": ["WaterSurface"],
              "behaviour_config": {"WaterSurface": {"preset": "pond", "width": 100, "height": 40, "rotation": 90}}}
    fake = SimpleNamespace(panel="inspect", mode="edit", tool="select", tab="look", selected="w", zoom=1.0,
                           handle_drag=None, _entity=lambda _id: entity, _live_collider=lambda e: {"kind": "picture"},
                           _live_zone=lambda e: None)
    fake._live_water = lambda e: Studio._live_water(fake, e)
    handles = {h["name"]: (round(h["x"], 3), round(h["y"], 3)) for h in Studio._handles(fake)}
    assert handles["water_size"] == (120.0, 150.0), "its corner, turned with it"
    assert handles["water_turn"] == (62.0, 100.0), "beyond its top, turned with it"
    assert _water_settings(ops.water_of(entity) or {}).rotation == 90.0
    # dragging the turn handle round to the east turns it to -90 (its top faces east)
    fake.handle_drag = {"name": "water_turn", "entity": "w", "moved": True, "water": dict(ops.water_of(entity) or {})}
    Studio._drag_handle(fake, 200.0, 100.0)
    assert fake.handle_drag["water"]["rotation"] == -90.0
    fake.handle_drag = {"name": "water_size", "entity": "w", "moved": True, "water": dict(ops.water_of(entity) or {})}
    Studio._drag_handle(fake, 130.0, 160.0)  # in its own (turned) frame: 60 along it, 30 across
    assert (fake.handle_drag["water"]["width"], fake.handle_drag["water"]["height"]) == (120.0, 60.0)


def test_stage_19a_rows_draw_as_before() -> None:
    """The GPU rows of Stage 19A's water: its kind (0 puddle, 1 pond), no bank, no turn, full ripples, so the
    shader's Stage 19A path (pixel-identical: the 19B report's comparison against the base) is what draws it."""
    class Buf(SimpleNamespace):
        def write(self, data: bytes) -> None:
            self.data = data

    ctx = SimpleNamespace(buffer=lambda data=b"": Buf(size=len(data), data=data), geometry=lambda *a, **k: object(),
                          TRIANGLE_STRIP=5)
    gl = SimpleNamespace(BufferDescription=lambda *a, **k: (a, k))
    layer = water.WaterLayer.__new__(water.WaterLayer)
    layer.ctx, layer.gl, layer.quad, layer.geometry, layer.instances, layer._key, layer.count = ctx, gl, object(), None, None, None, 0
    entity = SimpleNamespace(center_x=64.0, center_y=96.0, mesh_entity_data={})
    layer.set_bodies([water.Body(entity, water.PRESETS["pond"]), water.Body(entity, water.PRESETS["stone_pool"])])
    pond, pool = layer._key
    assert len(pond) == 32 and pond[6] == 1.0 and pond[15] == 1.0 and pond[20:23] == (0.0, 0.0, 0.0)
    assert pool[6] == 2.0 and pool[20] == 3.0 and pool[21] == pytest.approx(12 / 32)
