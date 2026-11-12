"""M17-L4-3: an HD-2D room's atmospheric depth (``settings.hd2d.haze``; engine.hd2d.haze), without a GPU: what the
block means and refuses (naming the key), what is stored (nothing for off, only what differs from the preset), the
haze's curve over distance (nothing before the onset, no corner there, 95% at the falloff, never past the strength),
where it begins (never on the followed character), how the room's light lights it, and the project operation Studio
and AIs share."""

from __future__ import annotations

import copy
import json
import math
from typing import Any

import pytest

from engine import authoring
from engine import project_ops as ops
from engine.hd2d.haze import CHARACTER_MARGIN, PRESETS, Haze, HazeError, amount, light_of, onset, parse_haze, shown, stored, uniforms
from engine.hd2d.settings import Hd2dSettingsError, parse_hd2d
from engine.scene_loader import environment_problems

pytestmark = [pytest.mark.fast]

ROOM: dict[str, Any] = {"settings": {"hd2d": {"structures": [], "camera": {"pitch": 30}}}, "entities": []}
DAY = (0.45, (1.0, 1.0, 1.0), (-0.45, -0.55, 0.7), 1.0, (1.0, 240 / 255, 216 / 255))  # Lakeside's noon
EVENING = (0.38, (1.0, 1.0, 1.0), (-0.9192, -0.3345, 0.2079), 0.85, (1.0, 176 / 255, 112 / 255))
NIGHT = (0.22, (1.0, 1.0, 1.0), (0.2802, -0.7698, 0.5736), 0.25, (143 / 255, 166 / 255, 224 / 255))


def test_no_block_is_off_and_the_presets_are_daytime_and_evening() -> None:
    assert parse_haze(None) is None
    assert set(PRESETS) == {"daytime", "evening"}
    assert parse_haze({"preset": "daytime"}) == Haze("daytime")
    h = parse_haze({"preset": "evening", "strength": 0.2, "color": "#ffeedd", "start": 5, "falloff": 40})
    assert h == Haze("evening", 0.2, (1.0, 0xee / 255, 0xdd / 255), 5.0, 40.0)
    assert h.values.strength == 0.2 and Haze("evening").values == PRESETS["evening"]


@pytest.mark.parametrize("raw, names", [
    ([], "must be an object"),
    ({}, "settings.hd2d.haze.preset must be one of daytime, evening"),
    ({"preset": "fog"}, "preset must be one of"),
    ({"preset": "off"}, "preset must be one of"),
    ({"preset": ["daytime"]}, "preset must be one of"),
    ({"preset": "daytime", "density": 1}, "unknown keys: density"),
    ({"preset": "daytime", "strength": 0.6}, "settings.hd2d.haze.strength must be a number from 0 to 0.5"),
    ({"preset": "daytime", "strength": -0.1}, "strength must be a number from 0 to 0.5"),
    ({"preset": "daytime", "strength": True}, "strength must be a number"),
    ({"preset": "daytime", "start": 41}, "settings.hd2d.haze.start must be a number from 0 to 40"),
    ({"preset": "daytime", "falloff": 0.5}, "settings.hd2d.haze.falloff must be a number from 1 to 80"),
    ({"preset": "daytime", "falloff": float("inf")}, "falloff must be a number"),
    ({"preset": "daytime", "color": "blue"}, "settings.hd2d.haze.color must be a colour"),
    ({"preset": "daytime", "color": 7}, "color must be a colour"),
])
def test_a_bad_block_is_refused_naming_the_key(raw: Any, names: str) -> None:
    with pytest.raises(HazeError, match=names.replace(".", r"\.")):
        parse_haze(raw)


def test_the_boundaries_are_accepted() -> None:
    for raw in ({"preset": "daytime", "strength": 0, "start": 0, "falloff": 1},
                {"preset": "evening", "strength": 0.5, "start": 40, "falloff": 80}):
        assert parse_haze(raw) is not None
    assert not Haze("daytime", strength=0.0).active and Haze("daytime", strength=0.001).active


def test_only_what_differs_is_stored() -> None:
    assert stored(None) is None
    assert stored(Haze("daytime")) == {"preset": "daytime"}
    own = PRESETS["daytime"]
    assert stored(Haze("daytime", own.strength, own.color, own.start, own.falloff)) == {"preset": "daytime"}
    for raw in ({"preset": "evening"}, {"preset": "evening", "strength": 0.1, "color": "#102030"},
                {"preset": "daytime", "start": 0.0, "falloff": 5.0}):
        assert stored(parse_haze(raw)) == raw  # (round trip)


def test_the_curve_is_nothing_before_the_onset_smooth_and_capped() -> None:
    assert amount(10.0, 10.0, 5.0, 0.3) == 0.0 and amount(3.0, 10.0, 5.0, 0.3) == 0.0
    assert amount(15.0, 10.0, 5.0, 0.3) == pytest.approx(0.3 * (1 - math.exp(-3)))  # 95% at onset + falloff
    assert amount(1e6, 10.0, 5.0, 0.3) == pytest.approx(0.3)  # (never past the strength)
    eps = 1e-3
    assert amount(10.0 + eps, 10.0, 5.0, 0.3) / eps < 1e-3  # no corner: its slope starts at zero, no edge on screen
    values = [amount(10.0 + d / 10, 10.0, 5.0, 0.3) for d in range(200)]
    assert all(b >= a for a, b in zip(values, values[1:]))  # (more distant, never less haze)
    steps = [b - a for a, b in zip(values, values[1:])]
    assert max(steps) < 0.3 * 0.05  # (no step: a smooth ramp, not bands)


def test_it_never_starts_on_the_followed_character() -> None:
    assert onset(50.0, 4.0, None) == 54.0  # (Studio's view, or nobody followed: start beyond the target)
    assert onset(50.0, 4.0, 0.7) == 54.0  # (the start already beyond the character)
    assert onset(50.0, 0.0, 0.7) == pytest.approx(50.0 + 0.7 + CHARACTER_MARGIN)  # (a start of 0 is moved out)
    for preset in PRESETS.values():
        assert preset.start >= 1.0 + CHARACTER_MARGIN  # (the presets leave a character's depth alone themselves)


def test_the_room_s_light_lights_it() -> None:
    day, evening, night = light_of(*DAY), light_of(*EVENING), light_of(*NIGHT)
    assert all(0.0 <= c <= 1.0 for c in (*day, *evening, *night))
    assert min(day) > 0.9 and max(night) < 0.45  # (bright by day, dim at night: it never glows on its own)
    assert evening[0] > evening[2] + 0.2  # (the evening sun warms it)
    below = light_of(0.3, (1.0, 1.0, 1.0), (0.0, -1.0, -0.2), 1.0, (1.0, 1.0, 1.0))
    assert below == pytest.approx((0.3, 0.3, 0.3))  # (a sun below the horizon adds nothing)
    lit = shown(Haze("daytime"), night)
    assert all(lit[i] <= PRESETS["daytime"].color[i] * night[i] + 1e-9 for i in range(3))
    u = uniforms(Haze("daytime"), day)
    assert u["u_haze"] == PRESETS["daytime"].strength and u["u_haze_falloff"] == PRESETS["daytime"].falloff
    assert all(0.0 <= c <= 1.0 for c in u["u_haze_color"])  # (linear light)


def test_the_presets_keep_to_their_briefs() -> None:
    day, eve = PRESETS["daytime"], PRESETS["evening"]
    assert day.strength < eve.strength <= 0.35  # (subtle by day, moderate in the evening, never heavy)
    assert day.color[2] > day.color[0] and eve.color[0] > eve.color[2]  # (cool by day, warm in the evening)
    assert all(p.falloff >= 20 for p in PRESETS.values())  # (gradual across a village camera's depth)


def test_the_room_settings_read_it_strictly_or_set_it_aside() -> None:
    raw = copy.deepcopy(ROOM["settings"]["hd2d"])
    assert parse_hd2d(raw).haze is None
    assert parse_hd2d({**raw, "haze": {"preset": "daytime", "strength": 0.1}}).haze == Haze("daytime", 0.1)
    with pytest.raises(Hd2dSettingsError, match="unknown keys: tint"):
        parse_hd2d({**raw, "haze": {"preset": "daytime", "tint": 1}})
    lenient = parse_hd2d({**raw, "camera": {"pitch": 40}, "haze": {"preset": ["daytime"]}}, lenient=True)
    assert lenient.haze is None and "preset must be one of" in str(lenient.haze_error)
    assert lenient.camera.pitch == 40  # (the rest of the room read as usual)
    room = copy.deepcopy(ROOM)
    room["settings"]["hd2d"]["haze"] = {"preset": "daytime", "strength": 2}
    problems = environment_problems(room)  # (mesh validate, AI validation)
    assert len(problems) == 1 and "settings.hd2d.haze.strength must be a number" in problems[0], problems


def test_the_operation_sets_resets_and_turns_off_only_its_own_key() -> None:
    room = copy.deepcopy(ROOM)
    before = json.dumps(room, sort_keys=True)
    on = ops.set_hd2d_haze(room, preset="evening")
    assert on["settings"]["hd2d"]["haze"] == {"preset": "evening"} and json.dumps(room, sort_keys=True) == before
    tuned = ops.set_hd2d_haze(on, strength=0.2, color="#aabbcc", start=6, falloff=30)
    assert tuned["settings"]["hd2d"]["haze"] == {"preset": "evening", "strength": 0.2, "start": 6, "falloff": 30,
                                                 "color": "#aabbcc"}
    assert ops.set_hd2d_haze(tuned, color=None, start=None)["settings"]["hd2d"]["haze"] == {
        "preset": "evening", "strength": 0.2, "falloff": 30}
    assert ops.set_hd2d_haze(tuned, preset="daytime")["settings"]["hd2d"]["haze"] == {"preset": "daytime"}  # reset
    off = ops.set_hd2d_haze(tuned, preset="off")
    assert json.dumps(off, sort_keys=True) == before  # (the room exactly as it was: no key)
    assert ops.haze_of(tuned) == {"preset": "evening", "label": "Evening", "strength": 0.2, "color": "#aabbcc",
                                  "start": 6.0, "falloff": 30.0, "error": None}
    assert ops.haze_of(room) == {"preset": None, "error": None}


@pytest.mark.parametrize("change, message", [
    ({"strength": 0.2}, "haze is off: choose a preset first"),
    ({"preset": "fog"}, "Haze preset must be one of off, daytime, evening"),
    ({"preset": ["daytime"]}, "Haze preset must be one of off, daytime, evening"),
    ({"preset": "daytime", "strength": 0.8}, "settings.hd2d.haze.strength must be a number from 0 to 0.5"),
    ({"preset": "daytime", "color": "teal-ish"}, "settings.hd2d.haze.color must be a colour"),
    ({"preset": "daytime", "falloff": 0}, "settings.hd2d.haze.falloff must be a number from 1 to 80"),
    ({"preset": "off", "strength": 0.2}, "The haze is off: there is nothing to set"),
])
def test_the_operation_refuses_bad_changes_saying_why(change: dict[str, Any], message: str) -> None:
    room = copy.deepcopy(ROOM)
    before = json.dumps(room, sort_keys=True)
    with pytest.raises(ops.OpError, match=message.replace(".", r"\.")):
        ops.set_hd2d_haze(room, **change)
    assert json.dumps(room, sort_keys=True) == before


def test_a_2d_room_has_no_depth_to_haze() -> None:
    with pytest.raises(ops.OpError, match="isn't an HD-2D room"):
        ops.set_hd2d_haze({"settings": {}, "entities": []}, preset="daytime")


def test_an_unreadable_block_is_shown_and_can_be_repaired() -> None:
    broken = copy.deepcopy(ROOM)
    broken["settings"]["hd2d"]["haze"] = {"preset": "fog", "strength": 0.2}
    assert ops.haze_of(broken)["preset"] is None and "preset must be one of" in ops.haze_of(broken)["error"]
    with pytest.raises(ops.OpError, match="choose a preset first"):
        ops.set_hd2d_haze(broken, strength=0.1)
    assert ops.set_hd2d_haze(broken, preset="daytime")["settings"]["hd2d"]["haze"] == {"preset": "daytime"}
    assert ops.set_hd2d_haze(broken, preset="off") == ROOM


def test_it_is_an_authoring_operation_and_its_reader_is_not() -> None:
    found = authoring.operations()
    assert "set_hd2d_haze" in found and "haze_of" not in found
    described = next(d for d in authoring.describe() if d["op"] == "set_hd2d_haze")
    assert {p["name"] for p in described["params"]} >= {"preset", "strength", "color", "start", "falloff"}


def test_the_review_says_what_changed() -> None:
    before = copy.deepcopy(ROOM)
    after = ops.set_hd2d_haze(ops.set_hd2d_haze(before, preset="evening"), strength=0.2, color="#aabbcc")
    lines = authoring.summarize({"rooms": {"start": before}}, {"rooms": {"start": after}})
    assert any("haze evening (strength 0.2, colour #aabbcc)" in line for line in lines), lines
    off = authoring.summarize({"rooms": {"start": after}}, {"rooms": {"start": before}})
    assert any("haze off" in line for line in off), off
