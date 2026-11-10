"""#485: HD-2D billboards (characters, signs, doors, scatter, tree canopies' sun shadows, campfires) stand up for the
camera drawing the frame. In Mesh Studio, a fixed Studio camera's picture and sun shadow map stay byte-identical
whatever the unseen game camera does (pitch or anything else), with sun shadows on and off, in the village, the
village with trees, a meadow and a campfire, and the cottage; with matching cameras the game's path and Studio's
draw the same picture; in play every billboard follows the game camera, walking or still. Hidden windows only. Set
MESH_GL_SMOKE=1."""

from __future__ import annotations

import json
import math
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
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))
SCENES = "packs/core_regions/scenes"
ROOMS = {"village": ("start", False), "village_decor": ("start", True), "cottage": ("cottage", False)}
FIELDS = ("target", "pitch", "fov", "distance", "ortho", "yaw")
KINDS = ("texture", "framebuffer", "program", "buffer", "geometry", "vertex_array")
GAME_CAMERA_CHANGES = {  # the unseen game camera, under a fixed Studio camera
    "pitch_60": {"pitch": 60.0},
    "pitch_15": {"pitch": 15.0},
    "orthographic": {"ortho": True},
    "aspect_4_3": {"_aspect": 4 / 3},  # (the game picture's aspect: the renderer keeps it, not the camera)
    "everything": {"target": (40.0, -20.0, 2.0), "pitch": 70.0, "yaw": 90.0, "distance": 90.0, "fov": 40.0,
                   "ortho": True, "_aspect": 1.0},
}
STUDIO_POSES = {  # Studio's camera (pitch, orbit, zoom): parity with the game's path at the same camera
    "default": {},
    "pitch_25_orbit_300": {"pitch": 25.0, "yaw": 300.0},
    "pitch_65_zoomed": {"pitch": 65.0, "distance_scale": 0.6},
    "orbit_35": {"yaw": 35.0},
    "play": {"play": True},  # the game camera as play places it: the room's pitch (30 outdoors, 55 in the cottage)
}


def stretch_for(pitch: float) -> float:
    return 1.0 / max(0.5, math.cos(math.radians(pitch)))


def _project(root: Path, room: str, decor: bool) -> Path:
    from engine import project_ops as ops
    from engine.project_scaffold import create_project

    project = root / room
    create_project(project, "Billboards", template_id="hd2d_rpg")
    if decor:  # trees (canopies cast the sun's shadow), a meadow and a campfire, where Studio's camera looks
        path = project / SCENES / f"{room}.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        dabs = [[480, 560], [800, 600], [640, 820], [960, 760], [380, 860]]
        doc = ops.scatter_stroke(doc, "Small tree", dabs, radius=200, density=0.08, seed=7)
        doc = ops.scatter_stroke(doc, "Meadow", dabs, radius=200, seed=8)
        doc, eid = ops.place_blank(doc, room, "Campfire", 720.0, 700.0)
        doc = ops.set_campfire(doc, eid)
        path.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return project


def _depth(texture: Any) -> bytes:
    """A depth texture's texels (arcade's read() can't read depth)."""
    from pyglet import gl

    w, h = texture.size
    buf = (gl.GLfloat * (w * h))()
    glo = texture.glo.value if hasattr(texture.glo, "value") else texture.glo
    gl.glActiveTexture(gl.GL_TEXTURE0)
    gl.glBindTexture(gl.GL_TEXTURE_2D, glo)
    gl.glGetTexImage(gl.GL_TEXTURE_2D, 0, gl.GL_DEPTH_COMPONENT, gl.GL_FLOAT, buf)
    gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
    return bytes(buf)


def _instrument(hd: Any, rec: dict) -> None:
    """Record the stretch every billboard kind is given this frame, and the character billboards' heights."""
    from engine.hd2d.renderer import PIXELS_PER_METRE

    quads = hd._sprite_quads

    def sprite_quads(sprites: list[Any], shadows: bool, right: Any = (1.0, 0.0, 0.0), **kw: Any) -> Any:
        verts, idx, ranges = quads(sprites, shadows, right, **kw)
        groups: dict[int, list[Any]] = {}  # (grouped by texture in sprite order, as the quads are)
        for s in sprites:
            groups.setdefault(id(hd._sprite_texture(s.texture)), []).append(s)
        textured = [r for r in ranges if r[0] is not None]
        stretches = set()
        for (tex, first, count), members in zip(textured, groups.values()):
            for q, s in zip(range(0, count, 6), members):
                i = idx[first + q] * 5  # (its first corner: bottom; its third: top)
                stretches.add(round((verts[i + 12] - verts[i + 2]) / (abs(s.height) / PIXELS_PER_METRE), 5))
        assert len(stretches) <= 1, stretches  # (every billboard the same: the drawing camera's)
        rec["sprites"] = stretches.pop() if stretches else None
        rec["heights"] = sorted({round(verts[idx[f + q] * 5 + 12] - verts[idx[f + q] * 5 + 2], 4)
                                 for _t, f, c in textured for q in range(0, c, 6)})
        rec["drawn_heights"] = sorted({round(abs(s.height) / PIXELS_PER_METRE, 4) for s in sprites})
        return verts, idx, ranges

    hd._sprite_quads = sprite_quads
    for name, layer in (("scatter", hd.scatter), ("fire", hd.fire_sprites)):
        if layer is None:
            continue
        casters, sprites = layer.draw_casters, layer.draw_sprites

        def cast(vp: Any, time: float, right: Any, stretch: float, _name: str = name, _f: Any = casters) -> Any:
            rec[f"{_name}_casters"] = stretch
            return _f(vp, time, right, stretch)

        def spr(vp: Any, last_vp: Any, focus: Any, right: Any, stretch: float, *a: Any, _name: str = name,
                _f: Any = sprites, **k: Any) -> Any:
            rec[f"{_name}_sprites"] = stretch
            return _f(vp, last_vp, focus, right, stretch, *a, **k)

        layer.draw_casters, layer.draw_sprites = cast, spr


def _studio_room(root: Path, name: str) -> dict:
    from hd2d_demo import HiddenGame

    from engine.studio import open_studio

    room, decor = ROOMS[name]
    project = _project(root / name, room, decor)
    game = HiddenGame(project, size=(960, 540))
    game.window.audio.set_muted(True)
    scene = f"{SCENES}/{room}.json"
    out: dict = {"independence": {}, "parity": {}}
    try:
        game.load(scene)
        studio = open_studio(game.window, project, "packs/core_regions/worlds/main.json", scene)
        assert studio is not None
        w, view = game.window, studio.hd2d
        view.advance_motion = view.advance_weather = lambda dt: None  # a still view: motion, weather, fire, water
        for _ in range(5):
            w.dispatch_event("on_update", 1 / 60)
            w.dispatch_event("on_draw")
            w.ctx.gc()
        hd, ctx = view.renderer, view.renderer.ctx
        _, _, vw, vh = (int(v) for v in view.viewport())
        rec: dict = {}
        _instrument(hd, rec)
        out["has"] = {"scatter": hd.scatter is not None, "fire": hd.fire_sprites is not None,
                      "shadows": bool(hd.lighting.enabled)}

        def picture(camera: Any) -> tuple[bytes, bytes | None, dict]:
            rec.clear()
            tex = ctx.texture((vw, vh), components=4)
            fbo = ctx.framebuffer(color_attachments=[tex])
            kept_cut = hd._bind_cutaway
            hd._bind_cutaway = lambda program, cam: kept_cut(program, None)  # (play's roof cutaway: Studio has none)
            try:
                fbo.use()
                pixels = bytes(hd.draw(read_final=True, camera=camera))
            finally:
                hd._bind_cutaway = kept_cut
                w.use()
                fbo.delete()
                tex.delete()
                ctx.gc()
            lit = hd.lighting
            sun = _depth(lit.sun_map) if lit.enabled and lit.sun_map is not None else None
            return pixels, sun, dict(rec)

        def live() -> dict[str, int]:
            return {k: getattr(ctx.stats, k)[0] - getattr(ctx.stats, k)[1] for k in KINDS}

        game_cam, studio_cam = hd.camera, view.camera
        saved = {f: getattr(game_cam, f) for f in FIELDS}
        shadows = hd.lighting.enabled

        def cycle() -> None:  # every case below, once
            for shadows_on in (True, False):
                hd.lighting.enabled = shadows_on and shadows
                base = picture(studio_cam)
                cases: dict = {"base_stretch": base[2]}
                for label, change in GAME_CAMERA_CHANGES.items():
                    aspect = hd._aspect
                    for f, v in change.items():
                        setattr(hd if f == "_aspect" else game_cam, f, v)
                    pic = picture(studio_cam)
                    for f, v in saved.items():
                        setattr(game_cam, f, v)
                    hd._aspect = aspect
                    cases[label] = {"picture_same": pic[0] == base[0], "sun_map_same": pic[1] == base[1],
                                    "stretch": pic[2]}
                out["independence"]["shadows_on" if shadows_on else "shadows_off"] = cases
            hd.lighting.enabled = shadows
            out["studio_pitch"], out["game_pitch"] = studio_cam.pitch, game_cam.pitch
            home = {f: getattr(studio_cam, f) for f in FIELDS}
            for label, pose in STUDIO_POSES.items():
                if pose.get("play"):  # play's own camera: following the player at the room's pitch, fov, distance
                    ready, hd._camera_ready = hd._camera_ready, False  # (Studio never places it: placed as play's
                    hd.update(0.0)                                      # first frame places it)
                    hd._camera_ready = ready
                    for f in FIELDS:
                        setattr(studio_cam, f, getattr(game_cam, f))
                for f, v in pose.items():
                    if f == "distance_scale":
                        studio_cam.distance = home["distance"] * v
                    elif f != "play":
                        setattr(studio_cam, f, v)
                studio_pic = picture(studio_cam)
                for f in FIELDS:
                    setattr(game_cam, f, getattr(studio_cam, f))
                ready, hd._camera_ready = hd._camera_ready, True  # (placed: not snapped back to its character)
                game_pic = picture(None)  # the game's path: its own camera, now Studio's
                hd._camera_ready = ready
                out["parity"][label] = {"pitch": studio_cam.pitch, "same": studio_pic[0] == game_pic[0],
                                        "colours": len(set(studio_pic[0][::4093])),  # (not an empty view)
                                        "studio_stretch": studio_pic[2], "game_stretch": game_pic[2]}
                for f, v in saved.items():
                    setattr(game_cam, f, v)
                for f, v in home.items():
                    setattr(studio_cam, f, v)

        cycle()  # (a first pass creates what new views need: per-program vertex arrays, scatter chunks...)
        out["live_before"] = live()
        cycle()  # ...and the same pass again allocates nothing more
        out["live_after"] = live()
    finally:
        game.close()
    return out


@pytest.fixture(scope="module")
def studio(tmp_path_factory: pytest.TempPathFactory) -> dict:
    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    root = tmp_path_factory.mktemp("billboards")
    return {name: _studio_room(root, name) for name in ROOMS}


def _expect_all(stretches: dict, expected: float, kinds: tuple[str, ...]) -> None:
    for kind in kinds:
        assert stretches.get(kind) == pytest.approx(expected, abs=1e-5), (kind, stretches)


def _kinds(has: dict, shadows: bool) -> tuple[str, ...]:
    kinds = ["sprites"]
    if has["scatter"]:
        kinds += ["scatter_sprites"] + (["scatter_casters"] if shadows else [])
    if has["fire"]:
        kinds.append("fire_sprites")
    return tuple(kinds)


@pytest.mark.parametrize("name", list(ROOMS))
def test_a_fixed_studio_camera_ignores_the_unseen_game_camera(studio: dict, name: str) -> None:
    r = studio[name]
    assert r["has"]["shadows"]
    assert r["studio_pitch"] != r["game_pitch"]  # (the case #485 hid: the room's pitch is not Studio's)
    if name == "village_decor":
        assert r["has"]["scatter"] and r["has"]["fire"], r["has"]
    expected = stretch_for(r["studio_pitch"])
    for mode, cases in r["independence"].items():
        kinds = _kinds(r["has"], mode == "shadows_on")
        _expect_all(cases["base_stretch"], expected, kinds)
        for label in GAME_CAMERA_CHANGES:
            case = cases[label]
            assert case["picture_same"] and case["sun_map_same"], (name, mode, label)
            _expect_all(case["stretch"], expected, kinds)


@pytest.mark.parametrize("name", list(ROOMS))
def test_character_billboards_stand_as_tall_as_studio_s_pitch_needs(studio: dict, name: str) -> None:
    r = studio[name]
    expected = stretch_for(r["studio_pitch"])
    stretched = r["independence"]["shadows_on"]["pitch_60"]["stretch"]  # (the game camera at 60°, Studio's not)
    assert stretched["heights"] == sorted({round(h * expected, 4) for h in stretched["drawn_heights"]}), stretched
    wrong = stretch_for(60.0)
    assert stretched["heights"] != sorted({round(h * wrong, 4) for h in stretched["drawn_heights"]})


@pytest.mark.parametrize("name", list(ROOMS))
def test_game_and_studio_draw_the_same_picture_from_the_same_camera(studio: dict, name: str) -> None:
    r = studio[name]
    assert r["parity"]["play"]["pitch"] == r["game_pitch"] != r["studio_pitch"]
    for label, case in r["parity"].items():
        assert case["same"] and case["colours"] > 20, (name, label, case["colours"])
        expected = stretch_for(case["pitch"])
        kinds = _kinds(r["has"], True)
        _expect_all(case["studio_stretch"], expected, kinds)
        _expect_all(case["game_stretch"], expected, kinds)


@pytest.mark.parametrize("name", list(ROOMS))
def test_no_gl_objects_are_left_behind(studio: dict, name: str) -> None:
    assert studio[name]["live_after"] == studio[name]["live_before"]


@pytest.mark.parametrize("name", ["village_decor", "cottage"])
def test_in_play_every_billboard_follows_the_game_camera_walking_or_still(tmp_path: Path, name: str) -> None:
    from hd2d_demo import HiddenGame

    room, decor = ROOMS[name]
    game = HiddenGame(_project(tmp_path, room, decor), size=(960, 540))
    game.window.audio.set_muted(True)
    try:
        game.load(f"{SCENES}/{room}.json")
        frames, player = [], game.player()
        if decor:  # beside the campfire: the camera following it sees the fire
            player.center_x, player.center_y = 660.0, 640.0
        game.step(30)
        game.draw()  # (the layers a frame creates, created: they're instrumented below)
        hd = game.window.hd2d_renderer
        rec: dict = {}
        _instrument(hd, rec)
        for k in range(6):
            if k:  # walk up and right: the camera follows
                for _ in range(4):
                    player.center_x += 2.0
                    player.center_y += 1.5
                    game.step(1)
            rec.clear()
            frames.append(game.draw().tobytes())
            _expect_all(rec, stretch_for(hd.camera.pitch), _kinds({"scatter": hd.scatter is not None,
                                                                   "fire": hd.fire_sprites is not None}, True))
        assert len(set(frames)) == len(frames)  # (moving)
        if decor:
            assert hd.scatter is not None and hd.fire_sprites is not None
    finally:
        game.close()
