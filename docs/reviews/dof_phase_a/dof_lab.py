"""#460 Phase A scratch lab: the prototype depth-aware DoF pass (dof_pass.py) on scratch copies of real Mesh HD-2D rooms,
in a hidden game window. Nothing in the product is changed: the pass is attached to this process's renderer instance
only, after the renderer has drawn its world (it overwrites the renderer's final blit, before fog, post-processing
and the HUD, exactly where a shipped pass would replace that blit).

    py -3.13 dof_lab.py PROJECT OUT [--size WxH] [--frames N]

Writes OUT/report.json and OUT/*.png (off / subtle / miniature / CoC map per view).
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(os.environ.get("ACC_REPO", r"D:\Games\Mesh-s4"))
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))
sys.path.insert(0, str(HERE))
PROJECT, OUT = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
ARGS = sys.argv[3:]
SIZE = tuple(int(v) for v in (ARGS[ARGS.index("--size") + 1] if "--size" in ARGS else "1280x720").split("x"))
FRAMES = int(ARGS[ARGS.index("--frames") + 1]) if "--frames" in ARGS else 120
MOTION = int(ARGS[ARGS.index("--motion") + 1]) if "--motion" in ARGS else 45  # frames walked, each drawn twice
LOOPS = int(ARGS[ARGS.index("--loops") + 1]) if "--loops" in ARGS else 300  # frames drawn to look for GL growth
for name in ("APPDATA", "XDG_DATA_HOME", "MESH_USER_DIR", "MESH_PROJECTS_DIR", "LOCALAPPDATA"):
    os.environ[name] = str(OUT / "env" / name.lower())
    Path(os.environ[name]).mkdir(parents=True, exist_ok=True)

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from dof_pass import PRESETS, DofPass, linear_depth  # noqa: E402

SET = ARGS[ARGS.index("--set") + 1] if "--set" in ARGS else "lakeside"
VIEWS = {  # (name, scene, where the player is put, px; None: where the room puts it)
    "lakeside": [("lakeside_start", "packs/core_regions/scenes/lakeside.json", None),
                 ("lakeside_shop", "packs/core_regions/scenes/lakeside.json", (1168.0, 456.0)),  # just south of the shop
                 ("lakeside_bridge", "packs/core_regions/scenes/lakeside.json", (1040.0, 900.0)),  # river and bridge
                 ("lakeside_cottage_interior", "packs/core_regions/scenes/cottage.json", None)],
    "template": [("village_start", "packs/core_regions/scenes/start.json", None),
                 ("village_shop", "packs/core_regions/scenes/start.json", (896.0, 290.0)),  # just south of the shop
                 ("village_bridge", "packs/core_regions/scenes/start.json", (640.0, 660.0)),  # below the bridge
                 ("template_cottage_interior", "packs/core_regions/scenes/cottage.json", None)],
}
REPORT: dict[str, Any] = {"size": list(SIZE), "frames_timed": FRAMES, "set": SET, "views": {}}
STATE: dict[str, Any] = {"preset": None, "debug": False, "world_ns": None, "dof": None}


def save() -> None:
    (OUT / "report.json").write_text(json.dumps(REPORT, indent=1, default=str) + "\n", encoding="utf-8")


def main() -> None:
    from hd2d_demo import HiddenGame

    g = HiddenGame(PROJECT, size=SIZE)
    w = g.window
    w.audio.set_muted(True)
    ctx = w.ctx
    REPORT["gl"] = {"vendor": ctx.info.VENDOR, "renderer": ctx.info.RENDERER, "version": list(ctx.gl_version)}
    STATE["dof"] = dof = DofPass(ctx)
    world_q = ctx.query(samples=False, time=True, primitives=False)

    def player_focus() -> float:
        """The followed player's distance along the camera's view axis (m): the middle of its billboard, which the
        renderer stands upright on the sprite's feet (``sprite.bottom``) and stretches by 1 / cos(pitch). Not the
        camera's distance: the camera stops at the room's bounds, so the player isn't always at its target."""
        return player_span()[0]

    def player_span() -> tuple[float, float]:
        """(the billboard's middle depth, half its depth span) in metres: an upright billboard under a camera looking
        down spans h * sin(pitch) of depth, top nearer than feet."""
        import math as _m

        from engine.hd2d.settings import PIXELS_PER_METRE as PX

        hd2d = w.hd2d_renderer
        cam = hd2d.camera
        p = g.player()
        stretch = 1.0 / max(0.5, _m.cos(_m.radians(cam.pitch)))
        h = abs(p.height) / PX * stretch
        eye, t = cam.eye(), cam.target
        f = [t[i] - eye[i] for i in range(3)]
        n = sum(v * v for v in f) ** 0.5
        q = (p.center_x / PX, p.bottom / PX, hd2d.elevation_of(p) / PX + h / 2)
        mid = sum((q[i] - eye[i]) * f[i] / n for i in range(3))
        return mid, h * _m.sin(_m.radians(cam.pitch)) / 2

    def attach() -> Any:
        hd2d = w.hd2d_renderer
        if getattr(hd2d, "_dof_lab", False):
            return hd2d
        original = hd2d.draw

        def draw(**kw: Any) -> Any:
            plain = not kw.get("camera") and kw.get("solid") is None and not kw.get("viewport")
            with world_q:
                result = original(**kw)
            STATE["world_ns"] = world_q.time_elapsed
            params = PRESETS.get(STATE["preset"]) if STATE["preset"] else None
            if plain and (params is not None or STATE["debug"]):
                colour, depth = hd2d._fbo_parts
                mid, half = player_span()
                use = dict(params or PRESETS["miniature"])
                use["range"] = max(use["range"], half + 0.25)  # (the whole character inside the sharp band)
                dof.render(colour, depth, hd2d.camera, use, debug=STATE["debug"], focus=mid)
            else:
                dof.last_ns = None
            return result

        hd2d.draw = draw
        hd2d._dof_lab = True
        return hd2d

    def frame(preset: str | None, *, debug: bool = False) -> np.ndarray:
        STATE["preset"], STATE["debug"] = preset, debug
        img = g.draw().convert("RGB")
        return np.asarray(img).copy()

    def depth_m() -> np.ndarray:
        """The world's last depth buffer, linearised to metres along the view axis (bottom row first)."""
        from pyglet import gl as raw

        hd2d = w.hd2d_renderer
        fw, fh = (int(v) for v in hd2d._fbo.size)
        buf = (raw.GLfloat * (fw * fh))()
        previous = ctx.active_framebuffer
        raw.glBindFramebuffer(raw.GL_READ_FRAMEBUFFER, hd2d._fbo.glo)
        raw.glReadPixels(0, 0, fw, fh, raw.GL_DEPTH_COMPONENT, raw.GL_FLOAT, buf)
        previous.use(force=True)
        d = np.frombuffer(buf, dtype=np.float32).reshape(fh, fw)
        return np.flipud(linear_depth(d.astype(np.float64), bool(hd2d.camera.ortho)))  # top row first, as images

    def sharp(img: np.ndarray, y0: int, y1: int, x0: int, x1: int) -> float:
        """Gradient energy of a patch (grey): how much fine detail is left."""
        p = img[y0:y1, x0:x1].astype(np.float64).mean(axis=2)
        return float((np.abs(np.diff(p, axis=0)).mean() + np.abs(np.diff(p, axis=1)).mean()) / 2)

    def player_screen() -> tuple[int, int]:
        hd2d = w.hd2d_renderer
        p = g.player()
        from engine.hd2d.settings import PIXELS_PER_METRE as PX
        vp = hd2d.last_vp
        x, y, z = p.center_x / PX, p.center_y / PX, hd2d.elevation_of(p) / PX + 0.75
        c = [sum(vp[r][k] * v for k, v in enumerate((x, y, z, 1.0))) for r in range(4)]
        sx = (c[0] / c[3] * 0.5 + 0.5) * SIZE[0]
        sy = (1 - (c[1] / c[3] * 0.5 + 0.5)) * SIZE[1]
        return int(round(sx)), int(round(sy))

    def timed(preset: str | None, n: int) -> dict[str, Any]:
        dof_ns, world_ns, wall = [], [], []
        for _ in range(n):
            g.step(1)
            t = time.perf_counter()
            frame(preset)
            ctx.finish()
            wall.append((time.perf_counter() - t) * 1000)
            world_ns.append(STATE["world_ns"])
            if dof.last_ns is not None:
                dof_ns.append(dof.last_ns)
        med = lambda xs: round(statistics.median(xs) / 1e6, 3) if xs else None  # noqa: E731
        p95 = lambda xs: round(sorted(xs)[int(len(xs) * 0.95) - 1] / 1e6, 3) if xs else None  # noqa: E731
        return {"dof_gpu_ms_median": med(dof_ns), "dof_gpu_ms_p95": p95(dof_ns), "world_gpu_ms_median": med(world_ns),
                "frame_wall_ms_median": round(statistics.median(wall), 3)}

    def view(name: str, scene: str, place: tuple[float, float] | None) -> None:
        g.load(scene)
        g.step(5)
        hd2d = attach()
        if place is not None:
            p = g.player()
            p.center_x, p.center_y = place
        g.step(90)  # the camera settles on the player
        frame(None)
        cam = hd2d.camera
        facts: dict[str, Any] = {"scene": scene, "camera": {"pitch": cam.pitch, "fov": cam.fov, "distance": cam.distance,
                                                            "ortho": cam.ortho}}
        shots = {}
        for preset in ("off", "subtle", "miniature"):
            img = frame(None if preset == "off" else preset)
            shots[preset] = img
            Image.fromarray(img).save(OUT / f"{name}_{preset}.png")
        z = depth_m()
        Image.fromarray(frame(None, debug=True)).save(OUT / f"{name}_coc_miniature.png")
        sx, sy = player_screen()
        facts["player_screen"] = [sx, sy]
        zp = float(np.median(z[max(0, sy - 3):sy + 3, max(0, sx - 3):sx + 3]))
        focus = player_focus()
        facts["focus_m"] = round(focus, 3)
        facts["camera_distance_m"] = round(cam.distance, 3)
        facts["player_depth_m"] = round(zp, 3)
        sky = z > 400
        facts["depth_span_m"] = [round(float(z[~sky].min()), 2), round(float(z[~sky].max()), 2)] if (~sky).any() else None
        # the player stays legible: its own visible pixels (the renderer's "solid" draw: it, flat red, against the
        # world's depth), compared with DoF off
        raw = hd2d.draw(solid=g.player(), read=True)
        fw, fh = (int(v) for v in hd2d._fbo.size)
        solid = np.flipud(np.frombuffer(raw, dtype=np.uint8).reshape(fh, fw, 3))
        mask = (solid[..., 0] > 200) & (solid[..., 1] < 60) & (solid[..., 2] < 60)
        facts["player_pixels"] = int(mask.sum())
        if mask.any():
            facts["player_depth_from_pixels_m"] = [round(float(np.percentile(z[mask], q)), 3) for q in (2, 50, 98)]
        facts["player_billboard_mid_and_half_span_m"] = [round(v, 3) for v in player_span()]
        facts["player_pixels_diff"] = {
            k: {"mean": round(float(np.abs(shots[k].astype(int) - shots["off"])[mask].mean()), 3) if mask.any() else None,
                "max": int(np.abs(shots[k].astype(int) - shots["off"])[mask].max()) if mask.any() else None,
                "changed_share": round(float((np.abs(shots[k].astype(int) - shots["off"]).max(axis=2)[mask] > 2).mean()), 4)
                if mask.any() else None} for k in ("subtle", "miniature")}
        # pixels in the sharp band: unchanged unless a blurred nearer object spills over them (meant)
        for k in ("subtle", "miniature"):
            band = np.abs(z - player_focus()) <= max(PRESETS[k]["range"], player_span()[1] + 0.25)
            changed = np.abs(shots[k].astype(int) - shots["off"]).max(axis=2) > 2
            facts.setdefault("in_focus_band", {})[k] = {"pixels": int(band.sum()),
                                                         "changed_share": round(float(changed[band].mean()), 4)}
        # same screen height, different depth: along rows above the player, find an at-focus run and a far run
        params = PRESETS["miniature"]
        comparisons = []
        for row in range(max(8, sy - 260), max(9, sy - 20), 8):
            line = z[row]
            sharp_cols = np.where(np.abs(line - focus) <= params["range"])[0]
            far_cols = np.where((line - focus >= params["range"] + params["falloff_f"]) & (line < 400))[0]
            sharp_cols = sharp_cols[(sharp_cols > 8) & (sharp_cols < SIZE[0] - 8)]
            far_cols = far_cols[(far_cols > 8) & (far_cols < SIZE[0] - 8)]
            if len(sharp_cols) >= 12 and len(far_cols) >= 12:
                a, b = int(np.median(sharp_cols)), int(np.median(far_cols))
                pa, pb = (row - 4, row + 4, a - 4, a + 4), (row - 4, row + 4, b - 4, b + 4)
                za, zb = float(np.median(z[pa[0]:pa[1], pa[2]:pa[3]])), float(np.median(z[pb[0]:pb[1], pb[2]:pb[3]]))
                if abs(za - focus) > params["range"] or zb - focus < params["range"] or zb > 400:
                    continue
                if min(sharp(shots["off"], *pa), sharp(shots["off"], *pb)) < 4.0:
                    continue  # (a flat patch shows no blur either way)
                ratio = lambda k, p: round(sharp(shots[k], *p) / max(1e-6, sharp(shots["off"], *p)), 3)  # noqa: E731
                comparisons.append({"row": row, "at_focus": {"col": a, "depth_m": round(za, 2),
                                                             "detail_kept": {k: ratio(k, pa) for k in ("subtle", "miniature")}},
                                    "far": {"col": b, "depth_m": round(zb, 2),
                                            "detail_kept": {k: ratio(k, pb) for k in ("subtle", "miniature")}}})
        facts["same_row_comparisons"] = comparisons[:6]
        facts["same_row_found"] = len(comparisons)
        # timing
        facts["timing"] = {p: timed(None if p == "off" else p, FRAMES) for p in ("off", "subtle", "miniature")}
        REPORT["views"][name] = facts
        save()

    outdoor = VIEWS[SET][0][1]
    for name, scene, place in VIEWS[SET]:
        view(name, scene, place)

    # ---- off is the world's own pixels; a zero-strength pass is bit-identical to them
    g.load(outdoor)
    g.step(60)
    attach()
    off = frame(None)
    zero = dict(PRESETS["subtle"], max_n=0.0, max_f=0.0)
    PRESETS["zero"] = zero
    zero_img = frame("zero")
    REPORT["zero_strength_bit_identical_to_off"] = bool(np.array_equal(off, zero_img))

    # ---- the HUD is drawn after the pass: a toast's glyph pixels are identical with DoF on
    hud = w.player_hud
    hud.enqueue_toast("Depth of field: the HUD stays sharp")
    g.step(2)
    with_toast_off, with_toast_dof = frame(None), frame("miniature")
    hud.clear_toasts()
    without = frame(None)
    glyphs = (np.abs(with_toast_off.astype(int) - without).max(axis=2) > 120) & (with_toast_off.min(axis=2) > 225)
    REPORT["hud"] = {"glyph_pixels": int(glyphs.sum()),
                     "glyph_pixels_changed_by_dof": int((np.abs(with_toast_dof.astype(int) - with_toast_off).max(axis=2)
                                                         > 0)[glyphs].sum()),
                     "glyph_max_delta": int(np.abs(with_toast_dof.astype(int) - with_toast_off).max(axis=2)[glyphs].max())
                     if glyphs.any() else None}
    Image.fromarray(with_toast_dof).save(OUT / "hud_toast_miniature.png")

    # ---- camera motion: walking, each frame drawn off and with DoF; DoF must not add frame-to-frame change
    k = g.arcade.key
    seq: dict[str, list[np.ndarray]] = {"off": [], "miniature": []}
    w.dispatch_event("on_key_press", k.RIGHT, 0)
    for _ in range(MOTION):
        g.step(1)
        seq["off"].append(frame(None).astype(np.int16))
        seq["miniature"].append(frame("miniature").astype(np.int16))
    w.dispatch_event("on_key_release", k.RIGHT, 0)
    change = {kk: float(np.mean([np.abs(b - a).mean() for a, b in zip(v, v[1:])])) for kk, v in seq.items()}
    REPORT["motion"] = {"mean_frame_to_frame_change": {kk: round(v, 3) for kk, v in change.items()},
                        "dof_over_off": round(change["miniature"] / max(1e-9, change["off"]), 3)}
    still = [frame("miniature") for _ in range(3)]
    REPORT["still_frames_identical_with_dof"] = bool(all(np.array_equal(still[0], s) for s in still[1:]))

    # ---- GPU objects: none made per frame; resizes rebuild the renderer's target only
    def counts() -> dict[str, int]:
        ctx.gc()
        return {kk: getattr(ctx.stats, kk)[0] - getattr(ctx.stats, kk)[1] for kk in ("texture", "framebuffer", "program",
                                                                                       "buffer", "geometry")}
    control_before = counts()
    for _ in range(LOOPS):
        g.step(1)
        frame(None)
    control_after = counts()
    before = counts()
    for _ in range(LOOPS):
        g.step(1)
        frame("miniature")
    after = counts()
    sizes = {}
    for size in ((960, 540), (1600, 900), SIZE):
        w.set_size(*size)
        g.step(2)
        img = frame("miniature")
        sizes[f"{size[0]}x{size[1]}"] = {"frame": list(img.shape[:2][::-1]), "fbo": list(w.hd2d_renderer._fbo.size),
                                         "dof_ms": round((dof.last_ns or 0) / 1e6, 3), "objects": counts()}
    REPORT["gl_objects"] = {"off_before_300_frames": control_before, "off_after_300_frames": control_after,
                            "before_300_frames": before, "after_300_frames": after, "after_resizes": sizes}
    save()
    g.window.close()


if __name__ == "__main__":
    try:
        main()
    finally:
        save()
        print(json.dumps({k: v for k, v in REPORT.items() if k != "views"}, indent=1, default=str))
