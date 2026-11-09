"""M17-L4-2: an HD-2D room's colour grade and vignette (``settings.hd2d.post``; engine.hd2d.post), without a GPU: what
the block means and refuses (naming the key), what is stored (nothing for off, only what differs from the preset),
strength scaling every value from neutral, and the project operation Studio and AIs share."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from engine import authoring
from engine import project_ops as ops
from engine.hd2d.post import NEUTRAL, PRESETS, Post, PostError, parse_post, stored
from engine.hd2d.settings import Hd2dSettingsError, parse_hd2d

pytestmark = [pytest.mark.fast]

ROOM: dict[str, Any] = {"settings": {"hd2d": {"structures": [], "camera": {"pitch": 30}}}, "entities": []}


def test_no_block_is_off_and_the_presets_are_the_four() -> None:
    assert parse_post(None) is None
    assert set(PRESETS) == {"natural", "golden_hour", "moonlight", "interior_warm"}
    assert parse_post({"preset": "natural"}) == Post("natural", 1.0, None)
    assert parse_post({"preset": "moonlight", "strength": 0.25, "vignette": 0}) == Post("moonlight", 0.25, 0.0)


@pytest.mark.parametrize("raw, names", [
    ([], "must be an object"),
    ({}, "settings.hd2d.post.preset must be one of natural, golden_hour, moonlight, interior_warm"),
    ({"preset": "morning_mist"}, "preset must be one of"),
    ({"preset": "off"}, "preset must be one of"),
    ({"preset": "natural", "exposure": 1.2}, "unknown keys: exposure"),
    ({"preset": "natural", "strength": 1.5}, "settings.hd2d.post.strength must be a number from 0 to 1"),
    ({"preset": "natural", "strength": True}, "strength must be a number"),
    ({"preset": "natural", "strength": "1"}, "strength must be a number"),
    ({"preset": "natural", "vignette": 0.6}, "settings.hd2d.post.vignette must be a number from 0 to 0.5"),
    ({"preset": "natural", "vignette": float("nan")}, "vignette must be a number"),
])
def test_a_bad_block_is_refused_naming_the_key(raw: Any, names: str) -> None:
    with pytest.raises(PostError, match=names.replace(".", r"\.")):
        parse_post(raw)


def test_only_what_differs_is_stored() -> None:
    assert stored(None) is None
    assert stored(Post("natural")) == {"preset": "natural"}
    assert stored(Post("natural", 1.0, PRESETS["natural"].vignette)) == {"preset": "natural"}  # (its own vignette)
    assert stored(Post("golden_hour", 0.5, 0.3)) == {"preset": "golden_hour", "strength": 0.5, "vignette": 0.3}
    for raw in ({"preset": "moonlight"}, {"preset": "moonlight", "strength": 0.4}, {"preset": "natural", "vignette": 0}):
        assert stored(parse_post(raw)) == raw  # (round trip)


def test_strength_scales_every_value_from_neutral_and_zero_is_the_original() -> None:
    zero = Post("golden_hour", 0.0)
    assert not zero.active and Post("golden_hour", 0.01).active
    u0, u1, half = zero.uniforms(), Post("golden_hour").uniforms(), Post("golden_hour", 0.5).uniforms()
    g = PRESETS["golden_hour"]
    assert u0["u_wb"] == NEUTRAL.white_balance and u0["u_contrast"] == 1.0 and u0["u_saturation"] == 1.0
    assert u0["u_split"] == 0.0 and u0["u_vignette"] == 0.0 and u0["u_exposure"] == 1.0
    assert u1["u_wb"] == g.white_balance and u1["u_contrast"] == g.contrast and u1["u_vignette"] == g.vignette
    assert half["u_saturation"] == pytest.approx(1 + (g.saturation - 1) / 2)
    assert half["u_vignette"] == pytest.approx(g.vignette / 2)
    assert Post("natural", 1.0, 0.3).uniforms()["u_vignette"] == 0.3


def test_the_presets_keep_to_their_briefs() -> None:
    moon, warm = PRESETS["moonlight"], PRESETS["interior_warm"]
    assert moon.contrast == 1.0 and moon.white_balance[2] > moon.white_balance[0]  # cooler, no added contrast
    assert moon.protect >= 0.85  # (warm lamp glass kept)
    assert warm.contrast == 1.0 and warm.exposure >= 1.0  # (dark surroundings not darkened further)
    gold = PRESETS["golden_hour"]
    assert gold.highlight_tint[0] > gold.highlight_tint[2] and gold.shadow_tint[2] > gold.shadow_tint[0]
    assert all(0 <= p.vignette <= 0.25 for p in PRESETS.values())


def test_the_room_settings_read_it_strictly_or_set_it_aside() -> None:
    raw = copy.deepcopy(ROOM["settings"]["hd2d"])
    assert parse_hd2d(raw).post is None
    assert parse_hd2d({**raw, "post": {"preset": "natural", "strength": 0.5}}).post == Post("natural", 0.5)
    with pytest.raises(Hd2dSettingsError, match="unknown keys: tint"):
        parse_hd2d({**raw, "post": {"preset": "natural", "tint": 1}})
    lenient = parse_hd2d({**raw, "post": {"preset": "sepia"}}, lenient=True)
    assert lenient.post is None and "preset must be one of" in str(lenient.post_error)


def test_the_operation_sets_resets_and_turns_off_only_its_own_key() -> None:
    room = copy.deepcopy(ROOM)
    before = json.dumps(room, sort_keys=True)
    on = ops.set_hd2d_post(room, preset="golden_hour")
    assert on["settings"]["hd2d"]["post"] == {"preset": "golden_hour"} and json.dumps(room, sort_keys=True) == before
    tuned = ops.set_hd2d_post(on, strength=0.6, vignette=0.25)
    assert tuned["settings"]["hd2d"]["post"] == {"preset": "golden_hour", "strength": 0.6, "vignette": 0.25}
    assert ops.set_hd2d_post(tuned, vignette=None)["settings"]["hd2d"]["post"] == {"preset": "golden_hour",
                                                                                  "strength": 0.6}
    assert ops.set_hd2d_post(tuned, preset="moonlight")["settings"]["hd2d"]["post"] == {"preset": "moonlight"}  # reset
    off = ops.set_hd2d_post(tuned, preset="off")
    assert json.dumps(off, sort_keys=True) == before  # (the room exactly as it was: no key)
    view = ops.post_of(tuned)
    assert view == {"preset": "golden_hour", "label": "Golden hour", "strength": 0.6, "vignette": 0.25,
                    "vignette_default": PRESETS["golden_hour"].vignette, "error": None}
    assert ops.post_of(room)["preset"] is None


@pytest.mark.parametrize("change, message", [
    ({"strength": 0.5}, "picture treatment is off: choose a preset first"),
    ({"preset": "sepia"}, "Picture preset must be one of off, natural"),
    ({"preset": "natural", "strength": 2}, "settings.hd2d.post.strength must be a number from 0 to 1"),
    ({"preset": "natural", "vignette": -0.1}, "settings.hd2d.post.vignette must be a number"),
    ({"preset": "off", "strength": 0.5}, "there is no strength or vignette to set"),
])
def test_the_operation_refuses_bad_changes_saying_why(change: dict[str, Any], message: str) -> None:
    with pytest.raises(ops.OpError, match=message.replace(".", r"\.")):
        ops.set_hd2d_post(copy.deepcopy(ROOM), **change)


def test_a_2d_room_has_no_picture_to_grade() -> None:
    with pytest.raises(ops.OpError, match="isn't an HD-2D room"):
        ops.set_hd2d_post({"settings": {}, "entities": []}, preset="natural")


def test_an_unreadable_block_is_shown_and_can_be_repaired() -> None:
    broken = copy.deepcopy(ROOM)
    broken["settings"]["hd2d"]["post"] = {"preset": "sepia"}
    assert ops.post_of(broken)["preset"] is None and "preset must be one of" in ops.post_of(broken)["error"]
    assert ops.set_hd2d_post(broken, preset="natural")["settings"]["hd2d"]["post"] == {"preset": "natural"}


def test_it_is_an_authoring_operation_and_its_reader_is_not() -> None:
    found = authoring.operations()
    assert "set_hd2d_post" in found and "post_of" not in found
    described = next(d for d in authoring.describe() if d["op"] == "set_hd2d_post")
    assert {p["name"] for p in described["params"]} >= {"preset", "strength", "vignette"}
