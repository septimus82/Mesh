"""#460 Phase B: an HD-2D room's depth of field (engine.hd2d.dof) without a GPU: its settings (off by default, bounded,
a bad block set aside), the shader's twins (depth linearised as the renderer's own camera makes it, the blur radius
from depth), the focus on the followed character, software rendering named, the op,
and that a 2D room has none."""

from __future__ import annotations

import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine import project_ops as ops
from engine.hd2d import dof as d
from engine.hd2d.settings import Hd2dSettingsError, parse_hd2d

pytestmark = pytest.mark.fast


def _room(**hd2d: object) -> dict:
    return {"id": "r", "settings": {"hd2d": {"camera": {"pitch": 30.0}, **hd2d}}, "entities": []}


# ---------------------------------------------------------------------- settings
def test_off_without_a_block_and_subtle_when_turned_on() -> None:
    assert d.parse_dof(None) == d.OFF and not d.OFF.active
    assert parse_hd2d({}).depth_of_field == d.OFF and parse_hd2d({}).dof_error is None  # (every older room)
    on = d.parse_dof({"enabled": True})
    assert on == d.SUBTLE and on.active and d.parse_dof({}) == d.SUBTLE  # (a block means on)
    assert (on.focus_range, on.near_falloff, on.far_falloff, on.max_blur, on.strength) == (2.5, 10.0, 10.0, 2.5, 1.0)
    assert not d.parse_dof({"strength": 0}).active and not d.parse_dof({"enabled": False, "max_blur": 3}).active


@pytest.mark.parametrize("raw, names", [
    ({"max_blur": 6}, "max_blur"), ({"max_blur": 0.1}, "max_blur"), ({"strength": 1.5}, "strength"),
    ({"focus_range": -1}, "focus_range"), ({"near_falloff": math.nan}, "near_falloff"),
    ({"far_falloff": math.inf}, "far_falloff"), ({"strength": True}, "strength"), ({"enabled": 1}, "enabled"),
    ({"enabled": "yes"}, "enabled"), ({"tilt": 1}, "unknown keys: tilt"), ([1], "must be an object"),
    ({"max_blur": "3"}, "max_blur")])
def test_bad_settings_are_refused_naming_the_key(raw: object, names: str) -> None:
    with pytest.raises(d.DofError, match=names):
        d.parse_dof(raw)
    with pytest.raises(Hd2dSettingsError, match=names):  # (strict: validation and the ops)
        parse_hd2d({"depth_of_field": raw})
    lenient = parse_hd2d({"depth_of_field": raw}, lenient=True)  # (loading a room: off, the reason kept)
    assert lenient.depth_of_field == d.OFF and names in str(lenient.dof_error)


def test_stored_keeps_only_what_differs_and_nothing_for_an_untouched_room() -> None:
    assert d.stored(d.OFF) is None
    assert d.stored(d.SUBTLE) == {"enabled": True}
    assert d.stored(d.with_changes(d.SUBTLE, max_blur=3.0)) == {"enabled": True, "max_blur": 3.0}
    assert d.stored(d.with_changes(d.SUBTLE, enabled=False, max_blur=3.0)) == {"enabled": False, "max_blur": 3.0}
    for dof in (d.SUBTLE, d.with_changes(d.SUBTLE, enabled=False, strength=0.5)):
        assert d.parse_dof(d.stored(dof)) == dof  # (what is kept reads back the same)


def test_software_renderers_are_named_and_hardware_is_not() -> None:
    for name in ("llvmpipe (LLVM 21.1.8, 256 bits)", "softpipe", "Google SwiftShader", "Microsoft Basic Render Driver",
                 "Software Rasterizer"):
        assert d.software_renderer(name), name
    for name in ("NVIDIA GeForce RTX 4070/PCIe/SSE2", "AMD Radeon RX 7800", "Intel(R) Iris(R) Xe Graphics",
                 "Apple M2", "", None):
        assert d.software_renderer(name) is None, name
    ctx = SimpleNamespace(info=SimpleNamespace(RENDERER="llvmpipe (LLVM 22.1.1, 256 bits)"))
    reason = d.dof_unavailable_reason(ctx)
    assert reason and "llvmpipe" in reason and "software rendering" in reason
    assert d.dof_unavailable_reason(SimpleNamespace(info=SimpleNamespace(RENDERER="NVIDIA GeForce"))) is None
    assert d.dof_unavailable_reason(SimpleNamespace()) is None  # (no query: hardware assumed, as elsewhere)


# ---------------------------------------------------------------------- the shader's twins
def test_depth_linearises_as_the_renderer_s_own_camera_projects_it() -> None:
    from engine.hd2d.renderer import Camera

    for ortho in (False, True):
        cam = Camera(30.0, 12.0, 53.5, ortho)
        cam.target = (10.0, 20.0, 0.8)
        vp = cam.view_projection(16 / 9)
        eye = cam.eye()
        for along in (1.0, 20.0, 53.5, 80.0, 400.0):
            f = [t - e for t, e in zip(cam.target, eye)]
            n = math.sqrt(sum(c * c for c in f))
            p = [e + c / n * along for e, c in zip(eye, f)]
            clip = [sum(vp[r][k] * v for k, v in enumerate((*p, 1.0))) for r in range(4)]
            depth = (clip[2] / clip[3]) * 0.5 + 0.5  # (what the depth buffer holds)
            assert d.linear_depth(depth, ortho) == pytest.approx(along, rel=1e-6, abs=1e-6)
            assert d.view_depth(eye, cam.target, tuple(p)) == pytest.approx(along)


def test_the_blur_grows_with_distance_from_the_sharp_band_only() -> None:
    focus, band, near, far, radius = 50.0, 2.5, 10.0, 10.0, 2.5
    assert d.coc(50.0, focus, band, near, far, radius) == 0.0
    assert d.coc(52.5, focus, band, near, far, radius) == 0.0 and d.coc(47.5, focus, band, near, far, radius) == 0.0
    assert d.coc(57.5, focus, band, near, far, radius) == pytest.approx(1.25)  # halfway down the far falloff
    assert d.coc(42.5, focus, band, near, far, radius) == pytest.approx(-1.25)  # nearer: negative
    assert d.coc(500.0, focus, band, near, far, radius) == pytest.approx(2.5)  # the sky: the most, no more


def test_the_blur_scales_with_the_picture_and_the_samples_cover_it() -> None:
    assert d.blur_radius(d.SUBTLE, 720) == pytest.approx(2.5)
    assert d.blur_radius(d.SUBTLE, 1080) == pytest.approx(3.75)  # the same look in a bigger window
    assert d.blur_radius(d.with_changes(d.SUBTLE, strength=0.5), 720) == pytest.approx(1.25)
    assert d.taps_for(0.5) == d.TAPS_MIN and d.taps_for(2.5) == 24 and d.taps_for(10.0) == d.TAPS_MAX
    assert all(d.taps_for(r / 4) <= d.taps_for((r + 1) / 4) for r in range(40))


def test_the_sharp_band_covers_the_followed_character_s_own_depth() -> None:
    # an upright 1.5 m character, stretched by 1 / cos(pitch) as the renderer stands it: outdoors (pitch 30) and
    # indoors (pitch 55) it spans this much depth; half of it plus a margin is kept sharp around its middle
    for pitch in (30.0, 55.0):
        h = 1.5 / math.cos(math.radians(pitch))
        assert d.character_band(h, pitch) == pytest.approx(h * math.sin(math.radians(pitch)) / 2 + d.CHARACTER_MARGIN)
    assert d.character_band(1.5 / math.cos(math.radians(55.0)), 55.0) > d.SUBTLE.focus_range / 2


def test_the_renderer_focuses_on_the_followed_character_not_the_camera_distance() -> None:
    from engine.hd2d.renderer import Camera, Hd2dRenderer

    sprite = SimpleNamespace(mesh_tag="player", center_x=320.0, bottom=96.0, height=48.0, width=32.0)
    cam = Camera(30.0, 12.0, 53.5, False)
    cam.target = (10.0, 1.0, 0.8)  # (the camera held at the room's edge: the player isn't at its target)
    fake = SimpleNamespace(camera=cam, followed=lambda: sprite, elevation_of=lambda s: 0.0)
    focus, need = Hd2dRenderer.dof_focus(fake, cam, True)
    h = 1.5 / math.cos(math.radians(30.0))
    mid = (10.0, 3.0, h / 2)
    assert focus == pytest.approx(d.view_depth(cam.eye(), cam.target, mid))
    assert abs(focus - cam.distance) > 1.0 and need == pytest.approx(d.character_band(h, 30.0))
    nobody = SimpleNamespace(camera=cam, followed=lambda: None, elevation_of=lambda s: 0.0)
    assert Hd2dRenderer.dof_focus(nobody, cam, True) == (pytest.approx(53.5), 0.0)
    assert Hd2dRenderer.dof_focus(fake, cam, False) == (pytest.approx(53.5), 0.0)


# ---------------------------------------------------------------------- the op, its words, validation
def test_set_depth_of_field_writes_only_what_differs_and_off_removes_it() -> None:
    room = _room()
    on = ops.set_depth_of_field(room, enabled=True)
    assert on["settings"]["hd2d"]["depth_of_field"] == {"enabled": True}
    tuned = ops.set_depth_of_field(on, max_blur=3.0, far_falloff=20)
    assert tuned["settings"]["hd2d"]["depth_of_field"] == {"enabled": True, "max_blur": 3.0, "far_falloff": 20.0}
    kept = ops.set_depth_of_field(tuned, enabled=False)  # (off keeps the creator's values for next time)
    assert kept["settings"]["hd2d"]["depth_of_field"] == {"enabled": False, "max_blur": 3.0, "far_falloff": 20.0}
    assert "depth_of_field" not in ops.set_depth_of_field(on, enabled=False)["settings"]["hd2d"]
    assert ops.set_depth_of_field(tuned, preset="subtle")["settings"]["hd2d"]["depth_of_field"] == {"enabled": True}
    assert "depth_of_field" not in room["settings"]["hd2d"]  # (the room given is never changed)


def test_the_op_refuses_bad_values_a_2d_room_and_the_unapproved_preset() -> None:
    for bad in ({"max_blur": 6}, {"strength": -0.1}, {"enabled": "on"}, {"focus_range": 50}):
        with pytest.raises(ops.OpError):
            ops.set_depth_of_field(_room(), **bad)
    with pytest.raises(ops.OpError, match="subtle"):
        ops.set_depth_of_field(_room(), preset="miniature")  # (#460 Phase C, not authorised)
    with pytest.raises(ops.OpError, match="isn't an HD-2D room"):
        ops.set_depth_of_field({"settings": {}, "entities": []}, enabled=True)


def test_a_broken_block_is_set_aside_reported_and_repaired() -> None:
    from engine.scene_loader import environment_problems

    broken = _room(depth_of_field={"max_blur": 99, "enabled": "maybe"})
    assert any("depth_of_field" in p for p in environment_problems(broken))
    shown = ops.depth_of_field_of(broken)
    assert shown["enabled"] is False and "depth_of_field" in shown["error"]
    repaired = ops.set_depth_of_field(broken, enabled=True)
    assert repaired["settings"]["hd2d"]["depth_of_field"] == {"enabled": True}
    assert environment_problems(repaired) == []


def test_studio_reads_back_the_values_and_whether_the_camera_is_an_interior_s() -> None:
    shown = ops.depth_of_field_of(_room(depth_of_field={"enabled": True, "strength": 0.5}))
    assert shown == {"enabled": True, "focus_range": 2.5, "near_falloff": 10.0, "far_falloff": 10.0, "max_blur": 2.5,
                     "strength": 0.5, "error": None, "indoor": False}
    indoor = _room()
    indoor["settings"]["hd2d"]["camera"]["pitch"] = ops.CAMERA_PRESETS["indoor"]["pitch"]
    assert ops.depth_of_field_of(indoor)["indoor"] and not ops.depth_of_field_of(indoor)["enabled"]


def test_every_template_and_committed_room_is_off_by_default() -> None:
    root = Path(__file__).resolve().parents[1]
    rooms = [p for p in root.glob("**/scenes/**/*.json") if ".git" not in p.parts and "node_modules" not in p.parts]
    assert rooms
    for path in rooms:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, ValueError):
            continue
        hd2d = (data.get("settings") or {}).get("hd2d") if isinstance(data, dict) else None
        if isinstance(hd2d, dict):
            assert "depth_of_field" not in hd2d, path  # (no room ships with it on, or even present)
