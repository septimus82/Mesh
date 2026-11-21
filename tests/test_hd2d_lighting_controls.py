"""M17-L3 C3: what Studio's lighting panel offers in an HD-2D room is what the HD-2D renderer reads.

Every room lighting setting Studio (or the AI) can write is either read by HD-2D or listed as unused there
(``engine.hd2d.settings.IGNORED_ROOM_SETTINGS``): the unused ones change nothing the renderer gets, the read ones and
the controls Studio shows in an HD-2D room (shadows on/off, edges, strength, each lamp's brightness, height, colour,
size, on/off, shadows) each change it. Shadows on/off is ``settings.hd2d.shadows`` (``project_ops.set_hd2d_shadows``);
with them off, the shadow allocation and the AI's light listing say so."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from engine import project_ops as ops
from engine.hd2d import settings as S

pytestmark = pytest.mark.fast


def _room() -> dict[str, Any]:
    scene: dict[str, Any] = {"settings": {"world_width": 768, "world_height": 512,
                                          "hd2d": {"structures": [], "sun": [-0.45, -0.55, 0.7], "ambient": 0.4}},
                             "lights": [{"id": "sky", "type": "ambient", "color": "#9aa6d0", "mode": "soft"}]}
    for x in (200.0, 400.0, 600.0):
        scene, _ = ops.add_light(scene, x, 256.0)
    return scene


def _drawn(scene: dict[str, Any]) -> S.Hd2dSettings:
    """What the renderer gets for this scene, as engine.hd2d.runtime builds it."""
    settings = scene["settings"]
    hd2d = S.parse_hd2d(settings["hd2d"], map_size_px=(768.0, 512.0), lenient=True)
    return dataclasses.replace(hd2d, **S.parse_scene_lights(scene.get("lights"), settings))


# Every room lighting setting set_room_lighting writes, with a value that isn't its default.
ROOM_CHANGES: dict[str, dict[str, Any]] = {
    "lighting_enabled": {"enabled": False}, "lighting_ambient_color": {"ambient": "Cave"},
    "lighting_shadows_mode": {"shadows": "none"}, "lighting_shadow_softness": {"softness": "soft"},
    "lighting_shadow_edge": {"edge": 12}, "lighting_shadow_strength": {"shadow_strength": 0.4},
    "lighting_shadow_quality": {"quality": "high"}, "lighting_character_shadows": {"character_shadows": False},
}
READ_ROOM_SETTINGS = ("lighting_shadow_softness", "lighting_shadow_strength")


def test_every_room_lighting_setting_is_read_by_hd2d_or_listed_as_unused_there() -> None:
    written = set()
    for change in ROOM_CHANGES.values():
        written |= set(ops.set_room_lighting(_room(), **change)["settings"]) - set(_room()["settings"])
    assert written == set(ROOM_CHANGES)  # (a new room setting must be added here, and classified)
    assert set(S.IGNORED_ROOM_SETTINGS) | set(READ_ROOM_SETTINGS) == written
    assert not set(S.IGNORED_ROOM_SETTINGS) & set(READ_ROOM_SETTINGS)


@pytest.mark.parametrize("key", S.IGNORED_ROOM_SETTINGS)
def test_a_setting_listed_as_unused_changes_nothing_hd2d_draws(key: str) -> None:
    room = _room()
    assert _drawn(ops.set_room_lighting(room, **ROOM_CHANGES[key])) == _drawn(room)


@pytest.mark.parametrize("key", READ_ROOM_SETTINGS)
def test_a_setting_studio_offers_in_hd2d_changes_what_it_draws(key: str) -> None:
    room = _room()
    assert _drawn(ops.set_room_lighting(room, **ROOM_CHANGES[key])) != _drawn(room)


def test_flicker_changes_nothing_hd2d_draws() -> None:
    room = _room()
    for change in ({"flicker": "torch"}, {"flicker": "custom", "flicker_speed": 9}, {"flicker_strength": 2.0}):
        assert _drawn(ops.set_light(room, 1, **change)) == _drawn(room)


@pytest.mark.parametrize("change", [{"intensity": 2.5}, {"intensity": 0}, {"elevation": 96}, {"color": "Cold"},
                                    {"radius": 300}, {"enabled": False}, {"shadows": False}, {"x": 250}])
def test_each_lamp_control_studio_offers_in_hd2d_changes_what_it_draws(change: dict[str, Any]) -> None:
    room = _room()
    assert _drawn(ops.set_light(room, 1, **change)) != _drawn(room)


def test_brightness_is_validated_and_drawn_as_written() -> None:
    room = ops.set_light(_room(), 1, intensity="2.5")
    assert room["lights"][1]["intensity"] == 2.5 and _drawn(room).lights[0].intensity == 2.5
    for bad in (-0.1, 10.5, "bright", float("nan")):
        with pytest.raises(ops.OpError):
            ops.set_light(room, 1, intensity=bad)
    assert _drawn(ops.set_light(room, 1, intensity=0)).lights[0].intensity == 0.0


def test_dimmer_and_brighter_steps_at_the_bounds() -> None:
    from engine.studio import _brighter, _dimmer

    assert _dimmer(1.6) == 1.28 and _dimmer(0.0625) == 0.05
    assert _dimmer(0.06) == 0.05 and _dimmer(0.05) == 0.0  # (the smallest step: to 0, not stuck at 0.05)
    assert _dimmer(0.01) == 0.0 and _dimmer(0.0) == 0.0  # (below the smallest step too; Studio disables it at 0)
    assert _brighter(0.0) == 0.06 and _brighter(8.0) == 10.0 and _brighter(10.0) == 10.0
    for level in [0.0, 0.01, 0.04, 0.05, 0.06, 0.0625, 0.1, 0.5, 1.0, 1.6, 3.0, 9.99, 10.0]:
        down, up = _dimmer(level), _brighter(level)
        assert down < level or down == level == 0.0, level  # (never raises it; always lowers it above 0)
        assert up > level or up == level == 10.0, level
        for value in (down, up):  # (each within set_light's 0-10)
            assert _drawn(ops.set_light(_room(), 1, intensity=value)).lights[0].intensity == value
    level, steps = 10.0, 0
    while level > 0.0:  # (Dimmer from the top reaches 0)
        level, steps = _dimmer(level), steps + 1
    assert steps < 30


def test_the_room_light_colour_tints_hd2d_ambient() -> None:
    room = _room()
    assert _drawn(ops.set_light(room, 0, color="Red")).ambient_color != _drawn(room).ambient_color


def test_shadows_on_and_off_is_settings_hd2d_shadows() -> None:
    room = _room()
    off = ops.set_hd2d_shadows(room, False)
    assert off["settings"]["hd2d"]["shadows"] is False and _drawn(off).shadows is False
    assert {k: v for k, v in off["settings"].items() if k != "hd2d"} == {k: v for k, v in room["settings"].items()
                                                                         if k != "hd2d"}  # (nothing else)
    on = ops.set_hd2d_shadows(off, True)
    assert "shadows" not in on["settings"]["hd2d"] and _drawn(on).shadows is True and on == room
    for bad in ("off", 0, None):
        with pytest.raises(ops.OpError):
            ops.set_hd2d_shadows(room, bad)
    with pytest.raises(ops.OpError):
        ops.set_hd2d_shadows({"settings": {}, "lights": []}, False)  # (a 2D room: no HD-2D shadows)


def test_with_the_rooms_shadows_off_no_light_has_a_shadow_map() -> None:
    room = ops.set_light(_room(), 3, shadows=False)
    room["lights"] += [ops.add_light(room, 700.0, 256.0)[0]["lights"][-1]]  # a third lamp asking for shadows
    assert S.scene_shadow_allocation(room) == [S.AMBIENT, S.SHADOW_MAP, S.SHADOW_MAP, S.NO_SHADOWS,
                                               S.OVER_SHADOW_LIMIT]
    off = ops.set_hd2d_shadows(room, False)
    assert S.room_shadows(off) is False and S.room_shadows(room) is True
    assert S.scene_shadow_allocation(off) == [S.AMBIENT, S.ROOM_SHADOWS_OFF, S.ROOM_SHADOWS_OFF, S.NO_SHADOWS,
                                              S.ROOM_SHADOWS_OFF]
    assert S.shadow_allocation(off["lights"]) == S.shadow_allocation(room["lights"])  # (the lights' own reading)


def test_studio_says_the_rooms_shadows_are_off() -> None:
    from engine.studio import HD2D_SHADOW_NOTES, hd2d_shadow_summary

    statuses = [S.AMBIENT, S.ROOM_SHADOWS_OFF, S.ROOM_SHADOWS_OFF]
    assert hd2d_shadow_summary(statuses, room_shadows=False) == ("Shadows are off in this room: every light shines "
                                                                 "through walls.")
    assert "shines through walls" in HD2D_SHADOW_NOTES[S.ROOM_SHADOWS_OFF]
    assert hd2d_shadow_summary([S.SHADOW_MAP]) == "Shadow maps: 1 of 2 in use."  # (C2's line, unchanged)


def _listing(tmp_path: Path, scene: dict[str, Any]) -> dict[str, Any]:
    from engine.mcp_server.tools import list_lights

    (tmp_path / "room.json").write_text(json.dumps(scene), encoding="utf-8")
    return list_lights("room.json", str(tmp_path))


def test_the_ai_listing_reads_lights_as_hd2d_does(tmp_path: Path) -> None:
    room = ops.set_room_lighting(ops.set_light(ops.set_light(_room(), 1, intensity=2.5), 2, flicker="torch"),
                                 enabled=False, quality="high", softness="soft")
    listing = _listing(tmp_path, room)
    assert [row["intensity"] for row in listing["lights"]] == [1.0, 2.5, 1.0, 1.0]
    assert [row["hd2d_ignored"] for row in listing["lights"]] == [[], [], ["flicker"], []]
    assert listing["hd2d_room_shadows"] is True
    assert listing["hd2d_ignored_settings"] == ["lighting_enabled", "lighting_shadow_quality"]
    off = _listing(tmp_path, ops.set_hd2d_shadows(room, False))
    assert off["hd2d_room_shadows"] is False
    assert [row["hd2d_shadow"] for row in off["lights"]] == S.scene_shadow_allocation(ops.set_hd2d_shadows(room, False))


def test_a_2d_rooms_ai_listing_is_unchanged(tmp_path: Path) -> None:
    scene = {"settings": {"lighting_enabled": True}, "lights": [{"x": 1, "y": 2, "radius": 50, "intensity": 3}]}
    listing = _listing(tmp_path, scene)
    assert set(listing) == {"ok", "scene_path", "count", "lights"}
    assert set(listing["lights"][0]) == {"index", "id", "type", "x", "y", "radius", "color", "enabled"}
