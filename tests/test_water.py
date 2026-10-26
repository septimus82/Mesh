"""Milestone 19A: puddles and ponds, headless: their settings, the checked edits Studio and AI make, the AI review's
words, footsteps through the water, and the registry a room keeps. The drawing is tests/test_water_gpu.py."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from engine import authoring, water
from engine import project_ops as ops

pytestmark = pytest.mark.fast


def test_presets_fill_in_what_an_object_leaves_out() -> None:
    puddle, pond = water.parse_water({"preset": "puddle"}), water.parse_water({"preset": "pond", "width": 300})
    assert (puddle.width, puddle.height, puddle.walkable, puddle.rain_ripples) == (64.0, 40.0, True, True)
    assert pond.width == 300.0 and pond.height == water.PRESETS["pond"].height and pond.waves > puddle.waves
    custom = water.parse_water({"preset": "pond", "colour": "#102030", "shape": "rect", "walkable": False})
    assert custom.colour == pytest.approx((16 / 255, 32 / 255, 48 / 255)) and custom.shape == "rect" and not custom.walkable


@pytest.mark.parametrize(("raw", "message"), [
    ({"preset": "lake"}, "preset must be one of"),
    ({"preset": "pond", "volume": 3}, "unknown setting"),
    ({"preset": "pond", "depth": 0.5}, "simple pond has no depth"),  # Stage 19A's look has no bank or depths
    ({"preset": "puddle", "shore": "mud"}, "simple puddle has no shore"),
    ({"preset": "natural_pond", "shore": "sand"}, "shore must be one of"),
    ({"preset": "natural_pond", "seed": 1.5}, "seed must be a whole number"),
    ({"preset": "natural_pond", "depth": 2}, "depth"),
    ({"preset": "stone_pool", "deep_colour": "deep"}, "deep_colour"),
    ({"preset": "stone_pool", "shore_width": 99}, "shore_width"),
    ({"preset": "pond", "colour": "blue"}, "colour like"),
    ({"preset": "pond", "width": 2}, "width"),
    ({"preset": "pond", "opacity": 2}, "opacity"),
    ({"preset": "pond", "shape": "star"}, "shape must be one of"),
    ({"preset": "pond", "walkable": "yes"}, "walkable"),
    ([], "must be an object"),
])
def test_bad_water_is_refused_with_the_reason(raw: Any, message: str) -> None:
    with pytest.raises(water.WaterError, match=message):
        water.parse_water(raw)


def test_what_counts_as_in_the_water() -> None:
    round_ = water.parse_water({"preset": "pond", "width": 200, "height": 100})
    square = water.parse_water({"preset": "pond", "width": 200, "height": 100, "shape": "rect"})
    assert water.inside(round_, (0, 0), (0, 0)) and water.inside(round_, (0, 0), (95, 0))
    assert not water.inside(round_, (0, 0), (90, 45)), "a round pond's corner is dry"
    assert water.inside(square, (0, 0), (90, 45)) and not water.inside(square, (0, 0), (101, 0))


def test_the_rain_s_strength_for_ripples() -> None:
    effects = (SimpleNamespace(preset="rain", count=3000, speed=1.0), SimpleNamespace(preset="snow", count=9000, speed=1.0))
    assert water.rain_rate(effects, (True, True)) == 1.0, "snow doesn't ripple water"
    assert water.rain_rate(effects, (False, True)) == 0.0 and water.rain_rate((), ()) == 0.0
    assert water.rain_rate((SimpleNamespace(preset="rain", count=20000, speed=1.0),), (True,)) == 2.0, "capped"


def test_water_is_made_and_changed_by_one_checked_edit() -> None:
    scene, wid = ops.place_blank({"entities": []}, "start", "Pond", 320, 240)
    pond = ops.set_water(scene, wid, preset="pond", width=200, height=120, walkable=False)
    entity = ops.find_entity(pond, wid)
    assert entity["behaviours"] == ["WaterSurface"] and entity["solid"] is True, "a pond that blocks is solid"
    assert entity["components"]["collider"] == {"kind": "box", "offset_x": 0.0, "offset_y": 0.0, "w": 200.0, "h": 120.0}
    wading = ops.find_entity(ops.set_water(pond, wid, walkable=True), wid)
    assert "solid" not in wading and "components" not in wading, "walkable again: what blocking added is gone"
    assert "WaterSurface" not in ops.entity_behaviours(ops.find_entity(ops.remove_water(pond, wid), wid))
    assert "solid" not in ops.find_entity(ops.remove_water(pond, wid), wid)
    with pytest.raises(ops.OpError, match="colour like"):
        ops.set_water(pond, wid, colour="blue")


def test_a_new_preset_brings_its_own_size_unless_one_was_chosen() -> None:
    scene, wid = ops.place_blank({"entities": []}, "start", "W", 0, 0)
    puddle = ops.set_water(scene, wid, preset="puddle")
    assert ops.water_of(ops.find_entity(ops.set_water(puddle, wid, preset="pond"), wid))["width"] == 224.0
    sized = ops.set_water(puddle, wid, width=120)
    assert ops.water_of(ops.find_entity(ops.set_water(sized, wid, preset="pond"), wid))["width"] == 120.0


def test_ai_makes_water_with_the_same_operations_and_the_review_says_so(tmp_path: Path) -> None:
    from engine.project_scaffold import create_project
    from engine.studio_project import Project

    root = tmp_path / "game"
    create_project(root, "Game", template_id="blank")
    project = Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"])
    room = project.current
    authoring.apply(project, [{"op": "place_blank", "room": room, "name": "Pond", "x": 200, "y": 160}])
    wid = next(e["id"] for e in project.scene(room)["entities"] if e.get("name") == "Pond")
    authoring.apply(project, [{"op": "set_water", "room": room, "entity_id": wid, "preset": "pond", "width": 180}])
    assert ops.water_of(ops.find_entity(project.scene(room), wid))["width"] == 180.0
    with pytest.raises(authoring.ChangeError, match="preset must be one of"):
        authoring.apply(project, [{"op": "set_water", "room": room, "entity_id": wid, "preset": "lake"}])
    lines = authoring.summarize({"rooms": {room: {"entities": []}}}, {"rooms": {room: project.scene(room)}})
    assert any("adds 'Pond' (pond water 180 x 144)" in line for line in lines), lines
    changed = ops.set_water(project.scene(room), wid, colour="#224466")
    assert f"{room}: 'Pond' water colour: (none) -> '#224466'" in authoring.summarize(
        {"rooms": {room: project.scene(room)}}, {"rooms": {room: changed}})
    assert {"set_water", "remove_water"} <= set(authoring.operations())


class _Sprite(SimpleNamespace):
    @property
    def bottom(self) -> float:
        return self.center_y - 16


def _room(*sprites: Any) -> Any:
    return SimpleNamespace(scene_controller=SimpleNamespace(all_sprites=list(sprites)), water_bodies=[], water_steps=[],
                           water_time=0.0)


def test_walking_through_water_splashes_each_step(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine.behaviours import water_surface

    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(water_surface, "emit_gameplay_event", lambda w, kind, payload, **_: events.append((kind, payload)))
    pond = _Sprite(center_x=200.0, center_y=200.0, mesh_name="Pond", mesh_entity_data={})
    hero = _Sprite(center_x=60.0, center_y=216.0, mesh_tag="player", mesh_name="Hero")
    window = _room(pond, hero)
    behaviour = water_surface.WaterSurface(pond, window, preset="pond", width=200, height=100)
    assert len(window.water_bodies) == 1 and pond.mesh_drawn is False, "registered; the water is its picture"
    for _ in range(40):  # walks east across it, 6 px a frame
        hero.center_x += 6
        behaviour.update(1 / 60)
    assert 10 <= behaviour.steps <= 16 and len(events) == behaviour.steps, "a step every 14 px in the water"
    assert events[0][0] == "water_step" and events[0][1]["who"] == "Hero" and events[0][1]["water"] == "Pond"
    assert len(window.water_steps) == water.MAX_STEPS, "the newest ripples kept, bounded"
    before = behaviour.steps
    hero.center_y = 400.0  # out of the water
    behaviour.update(1 / 60)
    assert behaviour.steps == before


def test_a_room_load_starts_its_water_afresh() -> None:
    released: list[bool] = []
    window = SimpleNamespace(water_bodies=["old"], water_steps=[(0, 0, 0)], water_time=9.0,
                             scene_water=SimpleNamespace(release=lambda: released.append(True)))
    water.reset(window)
    assert window.water_bodies == [] and window.water_steps == [] and window.water_time == 0.0
    assert released == [True] and window.scene_water is None
    water.advance(window, 0.5)
    assert window.water_time == 0.0, "no water: no clock"


def test_studio_offers_water_among_its_objects() -> None:
    from engine.studio import BUILT_IN_OBJECTS

    assert {"id": "water", "display_name": "Water", "built_in": "water"} in BUILT_IN_OBJECTS


def test_placeholders_mean_the_preset_s_everywhere() -> None:
    """What adding the behaviour plainly writes ("", 0, -1) is the preset's, for the game, Studio and AI alike."""
    plain = {"preset": "pond", "width": 0, "height": 0, "colour": "", "opacity": 0, "shape": "", "waves": -1,
             "reflection": -1, "target_tags": []}
    assert water.parse_water(plain) == water.PRESETS["pond"]
    scene = {"entities": [{"id": "w", "name": "W", "x": 0, "y": 0, "behaviours": ["WaterSurface"],
                           "behaviour_config": {"WaterSurface": dict(plain)}}]}
    wider = ops.set_water(scene, "w", width=300)
    assert ops.water_of(ops.find_entity(wider, "w"))["width"] == 300.0, "editable after a plain add_behaviour"


def test_a_hand_broken_water_shows_as_its_preset_with_the_reason_and_breaks_nothing() -> None:
    scene = {"entities": [{"id": "w", "name": "W", "x": 0, "y": 0, "behaviours": ["WaterSurface"],
                           "behaviour_config": {"WaterSurface": {"preset": "lake", "width": "big"}}}]}
    shown = ops.water_of(ops.find_entity(scene, "w"))
    assert shown is not None and shown["width"] == water.PRESETS["puddle"].width and "preset must be one of" in shown["error"]
    lines = authoring.summarize({"rooms": {"r": {"entities": []}}}, {"rooms": {"r": scene}})
    assert lines and "puddle water" in lines[0]
    with pytest.raises(ops.OpError, match="preset must be one of"):
        ops.set_behaviour_param(ops.set_water({"entities": [{"id": "v", "name": "V", "x": 0, "y": 0}]}, "v"), "v",
                                "WaterSurface", "preset", "lake")


def test_removing_water_reads_as_such() -> None:
    scene, wid = ops.place_blank({"entities": []}, "r", "Pond", 0, 0)
    pond = ops.set_water(scene, wid, preset="pond", walkable=False)
    assert authoring.summarize({"rooms": {"r": pond}}, {"rooms": {"r": ops.remove_water(pond, wid)}}) == [
        "r: 'Pond' stops being water"]


def test_show_when_flags_hide_water_and_its_splashes(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine.behaviours import water_surface

    monkeypatch.setattr(water_surface, "emit_gameplay_event", lambda *a, **k: None)
    gate = SimpleNamespace(met=False)
    activator = type("ConditionalActivator", (), {"_requirements_met": lambda self: gate.met})()
    pond = _Sprite(center_x=200.0, center_y=200.0, mesh_name="Pond", mesh_entity_data={},
                   mesh_behaviours_runtime=[activator])
    hero = _Sprite(center_x=150.0, center_y=216.0, mesh_tag="player", mesh_name="Hero")
    window = _room(pond, hero)
    behaviour = water_surface.WaterSurface(pond, window, preset="pond", width=200, height=100)
    assert water.bodies_of(window) == [], "its flag is off: no water"
    for _ in range(10):
        hero.center_x += 6
        behaviour.update(1 / 60)
    assert behaviour.steps == 0, "and no splashes"
    gate.met = True
    assert len(water.bodies_of(window)) == 1
    hero.center_x += 20
    behaviour.update(1 / 60)
    assert behaviour.steps == 1


def test_a_missing_step_sound_is_told_once_and_steps_go_quiet(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine.behaviours.water_surface import WaterSurface

    told: list[str] = []
    monkeypatch.setattr(WaterSurface, "_log", lambda self, message: told.append(message))
    pond = _Sprite(center_x=0.0, center_y=0.0, mesh_name="Pond", mesh_entity_data={})
    behaviour = WaterSurface(pond, _room(pond), preset="pond", step_sound="assets/sounds/no_such_splash.wav")
    assert behaviour.sound == "" and len(told) == 1 and "not found" in told[0]


def test_a_2d_room_whose_water_the_driver_refuses_carries_on_without_it() -> None:
    class Refusing:
        def program(self, **_: Any) -> Any:
            raise RuntimeError("no program (injected)")

    body = water.Body(SimpleNamespace(center_x=0.0, center_y=0.0, mesh_entity_data={}), water.PRESETS["puddle"])
    window = SimpleNamespace(water_bodies=[body], hd2d_renderer=None, ctx=Refusing(), scene_water=None)
    water.reset(window)
    window.water_bodies = [body]
    water.draw_2d(window)
    water.draw_2d(window)  # not tried again every frame
    assert "injected" in window.scene_water_error and window.scene_water is None
    water.reset(window)
    assert window.scene_water_error is None, "the room's next load tries again"
