"""M17-L4-4: an HD-2D room's bloom (``settings.hd2d.bloom``; engine.hd2d.bloom), without a GPU: what the block means
and refuses (naming the key), what is stored (nothing for off, only what differs from the preset), the soft knee (none
well below the threshold, all above it, smooth between), the chain's sizes (a fixed share of the picture at any size),
that every program drawing into the world writes its emission, the composite's order, and the project operation
Studio and AIs share."""

from __future__ import annotations

import copy
import json
import re
from typing import Any

import pytest

from engine import authoring
from engine import project_ops as ops
from engine.hd2d.bloom import BASE_HEIGHT, KNEE, LEVELS, OUTPUTS, PRESETS, Bloom, BloomError, base_size, knee_weight, level_sizes, parse_bloom, stored
from engine.hd2d.settings import Hd2dSettingsError, parse_hd2d
from engine.scene_loader import environment_problems

pytestmark = [pytest.mark.fast]

ROOM: dict[str, Any] = {"settings": {"hd2d": {"structures": [], "camera": {"pitch": 30}}}, "entities": []}


def test_no_block_is_off_and_the_presets_are_subtle_and_warm() -> None:
    assert parse_bloom(None) is None
    assert set(PRESETS) == {"subtle", "warm"}
    assert parse_bloom({"preset": "subtle"}) == Bloom("subtle")
    b = parse_bloom({"preset": "warm", "strength": 1.5, "threshold": 0.2, "spread": 0.4})
    assert b == Bloom("warm", 1.5, 0.2, 0.4) and b.values.strength == 1.5 and b.active
    assert Bloom("warm").values == PRESETS["warm"] and not Bloom("warm", strength=0.0).active


@pytest.mark.parametrize("raw, names", [
    ([], "must be an object"),
    ({"strength": 1}, "preset must be one of subtle, warm"),
    ({"preset": "glow"}, "preset must be one of subtle, warm"),
    ({"preset": "subtle", "tint": "#fff"}, "unknown keys: tint"),
    ({"preset": "subtle", "strength": 3.5}, "strength must be a number from 0 to 3"),
    ({"preset": "subtle", "strength": True}, "strength must be a number"),
    ({"preset": "subtle", "threshold": -0.1}, "threshold must be a number from 0 to 1"),
    ({"preset": "subtle", "spread": float("nan")}, "spread must be a number from 0 to 1"),
    ({"preset": "subtle", "spread": "wide"}, "spread must be a number"),
])
def test_a_bad_block_is_refused_naming_the_key(raw: Any, names: str) -> None:
    with pytest.raises(BloomError, match=names):
        parse_bloom(raw)


def test_the_boundaries_are_accepted() -> None:
    assert parse_bloom({"preset": "warm", "strength": 0, "threshold": 0, "spread": 0}) == Bloom("warm", 0.0, 0.0, 0.0)
    assert parse_bloom({"preset": "warm", "strength": 3, "threshold": 1, "spread": 1}) == Bloom("warm", 3.0, 1.0, 1.0)


def test_only_what_differs_is_stored() -> None:
    assert stored(None) is None
    assert stored(Bloom("subtle")) == {"preset": "subtle"}
    k = PRESETS["warm"]
    assert stored(Bloom("warm", k.strength, k.threshold, k.spread)) == {"preset": "warm"}
    assert stored(Bloom("warm", 1.0, None, 0.3)) == {"preset": "warm", "strength": 1.0, "spread": 0.3}


def test_the_knee_passes_nothing_well_below_all_above_and_is_smooth_between() -> None:
    t = 0.4
    k = t * KNEE
    assert knee_weight(t - k - 0.01, t) == 0.0 and knee_weight(0.0, t) == 0.0
    for y in (t + k + 0.01, 0.9, 2.0, 4.0):  # above the knee: exactly what is over the threshold
        assert knee_weight(y, t) * y == pytest.approx(y - t)
    ys = [t - k + i * (2 * k) / 200 for i in range(201)]
    passed = [knee_weight(y, t) * y for y in ys]
    assert all(b >= a for a, b in zip(passed, passed[1:]))  # (rises steadily: no step)
    steps = [b - a for a, b in zip(passed, passed[1:])]
    assert max(abs(b - a) for a, b in zip(steps, steps[1:])) < 1e-4  # (no corner: its slope changes smoothly)
    assert knee_weight(0.3, 0.0) == pytest.approx(1.0)  # threshold 0: every emitter, whole


def test_the_chain_is_a_fixed_share_of_the_picture() -> None:
    assert base_size((1280, 720)) == (640, BASE_HEIGHT) == base_size((1920, 1080))
    assert base_size((960, 540)) == (640, 360) and base_size((800, 600)) == (480, 360)
    sizes = level_sizes((1920, 1080))
    assert len(sizes) == LEVELS and sizes[0] == (640, 360) and sizes[-1] == (20, 12)
    assert level_sizes((1280, 720)) == sizes  # (720p and 1080p: the same glow, as a share of the picture)


def test_the_presets_keep_to_their_briefs() -> None:
    subtle, warm = PRESETS["subtle"], PRESETS["warm"]
    assert subtle.strength < warm.strength and subtle.threshold > warm.threshold and subtle.spread < warm.spread
    assert all(p.strength <= 2.0 and p.spread <= 0.7 for p in PRESETS.values())  # (restrained: no haze of glow)


def test_every_program_drawing_into_the_world_writes_its_emission() -> None:
    """While bloom is on the world's framebuffer has a second attachment: a program drawing into it that didn't write
    f_emit would leave it undefined (garbage glow). Every world program declares both outputs and writes f_emit."""
    from engine import scene_particles, water
    from engine.hd2d import renderer, scatter_layer

    programs = {"mesh": renderer.MESH_FS, "ground": renderer.GROUND_FS, "sprite": renderer.SPRITE_FS,
                "shadow blob": renderer.SHADOW_FS, "scatter": scatter_layer.BILLBOARD_FS, "water": water.FS,
                "river": water.RIVER_FS, "particles": scene_particles.FS}
    for name, fs in programs.items():
        assert OUTPUTS in fs, name
        assert "out vec4 f_color;" not in fs.replace(OUTPUTS, ""), name  # (no second, unplaced output)
        writes = len(re.findall(r"\bf_color = ", fs))
        assert writes and len(re.findall(r"\bf_emit = ", fs)) >= writes, name  # (each return path writes both)


def test_the_composite_adds_the_glow_after_the_haze_and_before_the_grade() -> None:
    from engine.hd2d.composite import COMPOSITE_FS

    body = COMPOSITE_FS[COMPOSITE_FS.index("void main()"):]
    haze, glow, grade = body.index("mix(o, u_haze_color, a)"), body.index("o += b"), body.index("u_wb * u_exposure")
    assert haze < glow < grade
    assert "b == vec3(0.0)" in body  # (nothing glowing, nothing else: the texel exactly)


def test_the_room_settings_read_it_strictly_or_set_it_aside() -> None:
    raw = copy.deepcopy(ROOM["settings"]["hd2d"])
    assert parse_hd2d(raw).bloom is None
    assert parse_hd2d({**raw, "bloom": {"preset": "warm", "strength": 1}}).bloom == Bloom("warm", 1.0)
    with pytest.raises(Hd2dSettingsError, match="unknown keys: tint"):
        parse_hd2d({**raw, "bloom": {"preset": "warm", "tint": 1}})
    lenient = parse_hd2d({**raw, "camera": {"pitch": 40}, "bloom": {"preset": ["warm"]}}, lenient=True)
    assert lenient.bloom is None and "preset must be one of" in str(lenient.bloom_error)
    assert lenient.camera.pitch == 40  # (the rest of the room read as usual)
    room = copy.deepcopy(ROOM)
    room["settings"]["hd2d"]["bloom"] = {"preset": "warm", "strength": 9}
    problems = environment_problems(room)  # (mesh validate, AI validation)
    assert len(problems) == 1 and "settings.hd2d.bloom.strength must be a number" in problems[0], problems


def test_the_operation_sets_resets_and_turns_off_only_its_own_key() -> None:
    room = copy.deepcopy(ROOM)
    before = json.dumps(room, sort_keys=True)
    on = ops.set_hd2d_bloom(room, preset="warm")
    assert on["settings"]["hd2d"]["bloom"] == {"preset": "warm"} and json.dumps(room, sort_keys=True) == before
    tuned = ops.set_hd2d_bloom(on, strength=1.5, threshold=0.2, spread=0.4)
    assert tuned["settings"]["hd2d"]["bloom"] == {"preset": "warm", "strength": 1.5, "threshold": 0.2, "spread": 0.4}
    assert ops.set_hd2d_bloom(tuned, threshold=None)["settings"]["hd2d"]["bloom"] == {
        "preset": "warm", "strength": 1.5, "spread": 0.4}
    assert ops.set_hd2d_bloom(tuned, preset="subtle")["settings"]["hd2d"]["bloom"] == {"preset": "subtle"}  # reset
    off = ops.set_hd2d_bloom(tuned, preset="off")
    assert json.dumps(off, sort_keys=True) == before  # (the room exactly as it was: no key)
    assert ops.bloom_of(tuned) == {"preset": "warm", "label": "Warm", "strength": 1.5, "threshold": 0.2,
                                   "spread": 0.4, "error": None}
    assert ops.bloom_of(room) == {"preset": None, "error": None}


@pytest.mark.parametrize("change, message", [
    ({"strength": 1}, "bloom is off: choose a preset first"),
    ({"preset": "glow"}, "Bloom preset must be one of off, subtle, warm"),
    ({"preset": ["warm"]}, "Bloom preset must be one of off, subtle, warm"),
    ({"preset": "warm", "strength": 4}, "settings.hd2d.bloom.strength must be a number from 0 to 3"),
    ({"preset": "warm", "threshold": 2}, "settings.hd2d.bloom.threshold must be a number from 0 to 1"),
    ({"preset": "warm", "spread": -1}, "settings.hd2d.bloom.spread must be a number from 0 to 1"),
    ({"preset": "off", "strength": 1}, "Bloom is off: there is nothing to set"),
])
def test_the_operation_refuses_bad_changes_saying_why(change: dict[str, Any], message: str) -> None:
    room = copy.deepcopy(ROOM)
    before = json.dumps(room, sort_keys=True)
    with pytest.raises(ops.OpError, match=message.replace(".", r"\.")):
        ops.set_hd2d_bloom(room, **change)
    assert json.dumps(room, sort_keys=True) == before


def test_a_2d_room_has_no_bloom() -> None:
    with pytest.raises(ops.OpError, match="isn't an HD-2D room"):
        ops.set_hd2d_bloom({"settings": {}, "entities": []}, preset="warm")


def test_an_unreadable_block_is_shown_and_can_be_repaired() -> None:
    broken = copy.deepcopy(ROOM)
    broken["settings"]["hd2d"]["bloom"] = {"preset": "glow", "strength": 1}
    assert ops.bloom_of(broken)["preset"] is None and "preset must be one of" in ops.bloom_of(broken)["error"]
    with pytest.raises(ops.OpError, match="choose a preset first"):
        ops.set_hd2d_bloom(broken, strength=1)
    assert ops.set_hd2d_bloom(broken, preset="warm")["settings"]["hd2d"]["bloom"] == {"preset": "warm"}
    assert ops.set_hd2d_bloom(broken, preset="off") == ROOM


def test_it_is_an_authoring_operation_and_its_reader_is_not() -> None:
    found = authoring.operations()
    assert "set_hd2d_bloom" in found and "bloom_of" not in found
    described = next(d for d in authoring.describe() if d["op"] == "set_hd2d_bloom")
    assert {p["name"] for p in described["params"]} >= {"preset", "strength", "threshold", "spread"}


def test_the_review_says_what_changed() -> None:
    before = copy.deepcopy(ROOM)
    after = ops.set_hd2d_bloom(ops.set_hd2d_bloom(before, preset="warm"), strength=1.5, spread=0.4)
    lines = authoring.summarize({"rooms": {"start": before}}, {"rooms": {"start": after}})
    assert any("bloom warm (strength 1.5, spread 0.4)" in line for line in lines), lines
    off = authoring.summarize({"rooms": {"start": after}}, {"rooms": {"start": before}})
    assert any("bloom off" in line for line in off), off
