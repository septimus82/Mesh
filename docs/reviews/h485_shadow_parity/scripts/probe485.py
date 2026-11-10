"""H-485A: does the unseen game camera change Mesh Studio's HD-2D picture of a fixed Studio camera, and through what?

    py -3.13 -I probe485.py WORKTREE OUT_DIR [--mesa] [--room start|cottage] [--poses]

Opens a fresh hd2d_rpg project's room in Mesh Studio (hidden window), freezes time (motion, weather, water, the
player), draws Studio's picture of a fixed Studio camera, then changes ONE property of the renderer's own (game)
camera at a time, draws the same Studio picture again and records what changed:
  * the picture (share of pixels, bounding box), with real sun shadows on and with them off;
  * the sun's view-projection and the sun shadow map's depth texels;
  * the characters' billboard geometry (_sprite_quads) and the canopy casters'/scatter sprites' right + stretch;
  * the fires chosen (lamps added this frame), the cameras.
``--poses``: repeats the comparison for several Studio camera poses (orbit, pitch, zoom: a moving Studio camera).
Writes OUT_DIR/probe_<room>.json and diff pictures."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

WT, OUT = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
ROOM = sys.argv[sys.argv.index("--room") + 1] if "--room" in sys.argv else "start"
if "--mesa" in sys.argv:
    sys.path.insert(0, str(Path(__file__).resolve().parent))  # mesa_preload.py beside this script (its mesa/x64 copy)
    import mesa_preload  # noqa: F401
sys.path.insert(0, str(WT))
sys.path.insert(1, str(WT / "tooling"))
os.chdir(WT)
import numpy as np  # noqa: E402
from hd2d_demo import SCENES, HiddenGame  # noqa: E402
from PIL import Image  # noqa: E402

import engine.hd2d.renderer as R  # noqa: E402
import engine.optional_arcade  # noqa: E402,F401
from engine.project_scaffold import create_project  # noqa: E402

assert Path(R.__file__).resolve().is_relative_to(WT), R.__file__
KINDS = ("texture", "framebuffer", "program", "buffer", "geometry", "vertex_array")
OUT.mkdir(parents=True, exist_ok=True)
SCATTER = "--scatter" in sys.argv
project = OUT / f"proj_{ROOM}{'_scatter' if SCATTER else ''}"
if not project.exists():
    create_project(project, "Game", template_id="hd2d_rpg")
    if SCATTER:  # trees (canopies cast the sun's shadow) and a meadow (grass billboards) where Studio looks
        from engine.project_ops import scatter_stroke
        path = project / "packs/core_regions/scenes" / f"{ROOM}.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        dabs = [[480, 560], [800, 600], [640, 820], [960, 760], [380, 860]]
        doc = scatter_stroke(doc, "Small tree", dabs, radius=200, density=0.08, seed=7)
        doc = scatter_stroke(doc, "Meadow", dabs, radius=200, seed=8)
        path.write_text(json.dumps(doc, indent=1), encoding="utf-8")

from engine.studio import open_studio  # noqa: E402

game = HiddenGame(project, size=(1280, 720))
game.window.audio.set_muted(True)
scene = f"{SCENES}/{ROOM}.json"
game.load(scene)
studio = open_studio(game.window, project, "packs/core_regions/worlds/main.json", scene)
assert studio is not None
view = studio.hd2d
view.advance_motion = view.advance_weather = lambda dt: None  # a still view
w = game.window
for _ in range(5):
    w.dispatch_event("on_update", 1 / 60)
    w.dispatch_event("on_draw")
    w.ctx.gc()
hd = view.renderer
ctx = hd.ctx
w.motion_time = 0.0
if hasattr(w, "water_time"):
    w.water_time = 0.0
_, _, VW, VH = (int(v) for v in view.viewport())


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:16]


def live() -> dict[str, int]:
    return {k: getattr(ctx.stats, k)[0] - getattr(ctx.stats, k)[1] for k in KINDS}


rec: dict = {}
orig_quads = hd._sprite_quads


def quads(sprites, shadows, right=(1.0, 0.0, 0.0), **kw):  # type: ignore[no-untyped-def]
    verts, idx, ranges = orig_quads(sprites, shadows, right, **kw)
    rec["sprite_quads"] = sha(verts.tobytes())
    rec["sprites"] = len(sprites)
    return verts, idx, ranges


hd._sprite_quads = quads
sc_layer = hd.scatter
if sc_layer is not None:
    orig_cast, orig_spr = sc_layer.draw_casters, sc_layer.draw_sprites

    def cast(vp_cols, time, right, stretch):  # type: ignore[no-untyped-def]
        rec["canopy_casters"] = {"right": [round(v, 6) for v in right], "stretch": round(stretch, 6),
                                 "blocks": len(sc_layer.canopy_blocks)}
        return orig_cast(vp_cols, time, right, stretch)

    def spr(vp_cols, vp, focus, right, stretch, *a, **k):  # type: ignore[no-untyped-def]
        rec["scatter_sprites"] = {"right": [round(v, 6) for v in right], "stretch": round(stretch, 6)}
        return orig_spr(vp_cols, vp, focus, right, stretch, *a, **k)

    sc_layer.draw_casters, sc_layer.draw_sprites = cast, spr


def cam_state(c) -> dict:  # type: ignore[no-untyped-def]
    return {"target": [round(v, 4) for v in c.target], "pitch": c.pitch, "yaw": c.yaw, "fov": c.fov,
            "distance": round(c.distance, 4), "ortho": c.ortho, "right": [round(v, 6) for v in c.right()]}


def studio_picture() -> tuple[np.ndarray, dict]:
    """Studio's picture of its own camera (Studio's call: camera + its canvas size), at the origin of a target."""
    rec.clear()
    tex = ctx.texture((VW, VH), components=4)
    fbo = ctx.framebuffer(color_attachments=[tex])
    try:
        fbo.use()
        b = bytes(hd.draw(read_final=True, camera=view.camera))
    finally:
        w.use()
        fbo.delete()
        tex.delete()
    lt = hd.lighting
    info = dict(rec)
    info["sun_vp"] = sha(np.asarray(lt.sun_vp, dtype=np.float64).tobytes())
    depth = depth_texels(lt.sun_map) if lt.enabled and lt.sun_map is not None else None
    info["sun_map"] = sha(depth.tobytes()) if depth is not None else None
    info["_sun_depth"] = depth
    info["extra_lamps"] = [(round(lamp.x, 2), round(lamp.y, 2)) for lamp in lt.extra_lamps]
    info["last_vp"] = sha(np.asarray(hd.last_vp, dtype=np.float64).tobytes())
    return np.flipud(np.frombuffer(b, dtype=np.uint8).reshape(VH, VW, 3)).copy(), info


def depth_texels(tex) -> np.ndarray:  # type: ignore[no-untyped-def]
    """The depth texture's texels (arcade can't read a depth texture: glGetTexImage directly)."""
    from pyglet import gl
    tw, th = tex.size
    buf = (gl.GLfloat * (tw * th))()
    gl.glActiveTexture(gl.GL_TEXTURE0)
    glo = tex.glo.value if hasattr(tex.glo, "value") else tex.glo
    gl.glBindTexture(gl.GL_TEXTURE_2D, glo)
    gl.glGetTexImage(gl.GL_TEXTURE_2D, 0, gl.GL_DEPTH_COMPONENT, gl.GL_FLOAT, buf)
    gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
    return np.frombuffer(bytes(buf), dtype=np.float32).reshape(th, tw).copy()


def diff(a: np.ndarray, b: np.ndarray) -> dict:
    m = np.abs(a.astype(int) - b.astype(int)).max(axis=2) > 0
    if not m.any():
        return {"changed": 0.0}
    ys, xs = np.nonzero(m)
    return {"changed": round(float(m.mean()), 5), "pixels": int(m.sum()),
            "bbox": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]}


game_cam = hd.camera
FIELDS = ("target", "pitch", "fov", "distance", "ortho", "yaw")
saved = tuple(getattr(game_cam, f) for f in FIELDS) + (hd._aspect, hd._camera_ready)


def restore() -> None:
    for f, v in zip(FIELDS, saved):
        setattr(game_cam, f, v)
    hd._aspect, hd._camera_ready = saved[-2], saved[-1]


sc = view.camera
t = game_cam.target
PERTURB = {
    "repeat": {},
    "target": {"target": (t[0] + 7.0, t[1] + 5.0, t[2] + 1.0)},
    "pitch_to_studio": {"pitch": sc.pitch},
    "pitch_60": {"pitch": 60.0},
    "yaw_45": {"yaw": 45.0},
    "fov_plus_10": {"fov": game_cam.fov + 10.0},
    "distance_x2": {"distance": game_cam.distance * 2},
    "ortho_toggle": {"ortho": not game_cam.ortho},
    "aspect_1": {"_aspect": 1.0},
    "camera_ready_toggle": {"_camera_ready": not hd._camera_ready},
    "all_to_studio_as_485": {f: getattr(sc, f) for f in FIELDS},
    "all_but_pitch_to_studio": {f: getattr(sc, f) for f in FIELDS if f != "pitch"},
}


def run(label: str) -> dict:
    out: dict = {"studio_cam": cam_state(sc), "game_cam": cam_state(game_cam), "cases": {}}
    shadows = hd.lighting.enabled
    for shadow_on in ([True, False] if shadows else [False]):
        hd.lighting.enabled = shadow_on
        restore()
        base_pic, base_info = studio_picture()
        before = live()
        key = "shadows_on" if shadow_on else "shadows_off"
        out[key] = {"base": {k: v for k, v in base_info.items() if not k.startswith("_")}, "cases": {}}
        for name, change in PERTURB.items():
            restore()
            for f, v in change.items():
                setattr(hd if f.startswith("_") else game_cam, f, v)
            pic, info = studio_picture()
            restore()
            changed = {k: [base_info.get(k), info.get(k)] for k in set(base_info) | set(info)
                       if not k.startswith("_") and base_info.get(k) != info.get(k)}
            if "sun_map" in changed:
                changed["sun_map_texels_changed"] = int((base_info["_sun_depth"] != info["_sun_depth"]).sum())
            d = diff(base_pic, pic)
            out[key]["cases"][name] = {"picture": d, "instrumented_changes": changed}
            if d["changed"] and name in ("pitch_to_studio", "all_to_studio_as_485", "pitch_60") and shadow_on:
                m = (np.abs(base_pic.astype(int) - pic.astype(int)).max(axis=2) > 0)
                vis = base_pic.copy()
                vis[m] = (255, 0, 255)
                Image.fromarray(np.hstack([base_pic, pic, vis])).save(OUT / f"{ROOM}{'_scatter' if SCATTER else ''}_{label}_{name}.png")
        restore()
        again, _ = studio_picture()
        out[key]["restored_same"] = bool(np.array_equal(again, base_pic))
        out[key]["live_before_after"] = [before, live()]
    hd.lighting.enabled = shadows
    restore()
    # parity: the game's own path, its camera set to Studio's, against Studio's path (the same frame otherwise)
    for f in FIELDS:
        setattr(game_cam, f, getattr(sc, f))
    hd._camera_ready = True
    studio_pic, _ = studio_picture()
    tex = ctx.texture((VW, VH), components=4)
    fbo = ctx.framebuffer(color_attachments=[tex])
    try:
        fbo.use()
        kept_cut = hd._bind_cutaway
        hd._bind_cutaway = lambda mp, cam: kept_cut(mp, None)  # (play's roof cutaway off: Studio has none)
        game_b = bytes(hd.draw(read_final=True))
    finally:
        hd._bind_cutaway = kept_cut
        w.use()
        fbo.delete()
        tex.delete()
    restore()
    game_pic = np.flipud(np.frombuffer(game_b, dtype=np.uint8).reshape(VH, VW, 3))
    out["parity_game_path_vs_studio_same_camera"] = diff(studio_pic, game_pic)
    return out


report: dict = {"worktree": str(WT), "room": ROOM, "scatter_added": SCATTER, "viewport": [VW, VH], "gl": ctx.info.RENDERER,
                "shadows": hd.lighting.enabled, "scatter": sc_layer is not None,
                "canopy_blocks": len(sc_layer.canopy_blocks) if sc_layer is not None else 0,
                "pose_default": run("default")}
if "--poses" in sys.argv:
    poses = {"orbit_35": dict(yaw=35.0), "orbit_-60_pitch_25": dict(yaw=300.0, pitch=25.0),
             "pitch_65_zoom": dict(pitch=65.0, distance=sc.distance * 0.6), "pan": dict(target=(sc.target[0] + 6, sc.target[1] - 4, sc.target[2]))}
    home = {f: getattr(sc, f) for f in FIELDS}
    report["poses"] = {}
    for name, p in poses.items():
        for f, v in p.items():
            setattr(sc, f, v)
        report["poses"][name] = run(name)
        for f, v in home.items():
            setattr(sc, f, v)
report["live_end"] = live()
(OUT / f"probe_{ROOM}{'_scatter' if SCATTER else ''}.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
game.close()
print(json.dumps({k: v for k, v in report.items() if k not in ("pose_default", "poses")}))
for key in ("shadows_on", "shadows_off"):
    if key in report["pose_default"]:
        for name, c in report["pose_default"][key]["cases"].items():
            print(key, name, c["picture"], sorted(c["instrumented_changes"]))
print("parity", report["pose_default"]["parity_game_path_vs_studio_same_camera"])
