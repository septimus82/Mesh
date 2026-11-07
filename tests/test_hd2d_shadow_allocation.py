"""M17-L3 C2: which of an HD-2D room's lights get one of its MAX_SHADOW_LIGHTS shadow maps, which ask and don't
(they shine through walls), and which aren't lit (``engine.hd2d.settings.shadow_allocation``): the same reading the
renderer gets (``parse_scene_lights``), as Studio and the AI tools show it. The limit and its order are unchanged.
The renderer's side: tests/test_hd2d_shadow_allocation_gpu.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.hd2d import settings as S
from engine.mcp_server import tools
from engine.studio import HD2D_SHADOW_NOTES, HD2D_SHADOW_TAGS, hd2d_shadow_summary

pytestmark = pytest.mark.fast


def _lamp(x: float, **extra: object) -> dict:
    return {"x": x, "y": 100.0, "radius": 160.0, "color": "#ffcc88", **extra}


LIGHTS = [
    {"id": "sky", "type": "ambient", "color": "#9aa6d0"},
    _lamp(100.0),  # asks (the default): the first map
    _lamp(200.0, shadows=False),  # lit, no shadows
    _lamp(300.0, enabled=False),  # off: takes nothing
    _lamp(400.0, shadows=True),  # asks: the second map
    _lamp(500.0),  # asks: the maps are taken
    _lamp(600.0, radius=0),  # can't be used
    "not a light",
    {**_lamp(700.0), "radius": "big"},
]


def test_each_light_says_what_the_room_does_with_it() -> None:
    assert S.MAX_SHADOW_LIGHTS == 2  # (unchanged: C2 shows the limit, it doesn't raise it)
    assert S.shadow_allocation(LIGHTS) == [S.AMBIENT, S.SHADOW_MAP, S.NO_SHADOWS, S.LIGHT_OFF, S.SHADOW_MAP,
                                           S.OVER_SHADOW_LIMIT, S.UNUSABLE, S.UNUSABLE, S.UNUSABLE]


def test_the_allocation_is_exactly_the_renderers_reading() -> None:
    # the lamps the renderer lights, in order, cast shadows exactly where the allocation says SHADOW_MAP
    lamps = S.parse_scene_lights(LIGHTS, {})["lights"]
    lit = [status for status in S.shadow_allocation(LIGHTS) if status in (S.SHADOW_MAP, S.NO_SHADOWS,
                                                                            S.OVER_SHADOW_LIMIT)]
    assert [lamp.shadows for lamp in lamps] == [status == S.SHADOW_MAP for status in lit]
    assert [lamp.x for lamp in lamps] == [100.0, 200.0, 400.0, 500.0]


def test_lamps_past_the_eighth_are_not_lit_and_say_so() -> None:
    lights = [_lamp(float(i * 10), shadows=False) for i in range(10)]
    assert S.shadow_allocation(lights) == [S.NO_SHADOWS] * S.MAX_LIGHTS + [S.OVER_LIGHT_LIMIT] * 2
    assert len(S.parse_scene_lights(lights, {})["lights"]) == S.MAX_LIGHTS


def test_turning_an_earlier_lights_shadows_off_hands_its_map_on() -> None:
    lights = [_lamp(100.0), _lamp(200.0), _lamp(300.0)]
    assert S.shadow_allocation(lights) == [S.SHADOW_MAP, S.SHADOW_MAP, S.OVER_SHADOW_LIMIT]
    lights[0]["shadows"] = False
    assert S.shadow_allocation(lights) == [S.NO_SHADOWS, S.SHADOW_MAP, S.SHADOW_MAP]


def test_nothing_or_junk_reads_as_no_lights() -> None:
    assert S.shadow_allocation(None) == [] and S.shadow_allocation({"x": 1}) == []
    assert S.parse_scene_lights(None, {})["lights"] == ()


def test_studio_words_for_the_allocation() -> None:
    allocation = S.shadow_allocation(LIGHTS)
    assert hd2d_shadow_summary(allocation) == ("Shadow maps: 2 of 2 in use. 1 more light set to cast shadows gets "
                                               "none and shines through walls.")
    assert hd2d_shadow_summary([S.SHADOW_MAP]) == "Shadow maps: 1 of 2 in use."
    many = [S.SHADOW_MAP] * 2 + [S.OVER_SHADOW_LIMIT] * 2 + [S.OVER_LIGHT_LIMIT]
    assert hd2d_shadow_summary(many) == ("Shadow maps: 2 of 2 in use. 2 more lights set to cast shadows get none and "
                                         "shine through walls. 1 light past the first 8 give no light.")
    assert HD2D_SHADOW_TAGS[S.OVER_SHADOW_LIMIT] == " - no shadow map"
    assert "shines through walls" in HD2D_SHADOW_NOTES[S.OVER_SHADOW_LIMIT]
    assert S.AMBIENT not in HD2D_SHADOW_NOTES and S.AMBIENT not in HD2D_SHADOW_TAGS  # (the room light: no note)


def _scene(tmp_path: Path, hd2d: bool) -> str:
    scene = {"name": "Room", "entities": [], "lights": LIGHTS[:6],
             "settings": {"hd2d": {"structures": []}} if hd2d else {}}
    path = tmp_path / "scenes" / "room.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(scene), encoding="utf-8")
    return "scenes/room.json"


def test_the_ai_tools_list_each_lights_shadow_map_in_an_hd2d_room(tmp_path: Path) -> None:
    listed = tools.list_lights(_scene(tmp_path, hd2d=True), str(tmp_path))
    assert listed["ok"] and listed["hd2d_shadow_maps"] == 2
    assert [row["hd2d_shadow"] for row in listed["lights"]] == [S.AMBIENT, S.SHADOW_MAP, S.NO_SHADOWS, S.LIGHT_OFF,
                                                                 S.SHADOW_MAP, S.OVER_SHADOW_LIMIT]


def test_a_2d_rooms_listing_is_unchanged(tmp_path: Path) -> None:
    listed = tools.list_lights(_scene(tmp_path, hd2d=False), str(tmp_path))
    assert listed["ok"] and "hd2d_shadow_maps" not in listed
    assert all("hd2d_shadow" not in row for row in listed["lights"])
