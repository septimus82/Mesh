"""M17-L4A scratch lab: matched 1280x720 world frames of the scratch Lakeside copy, with prototype post effects.

For each shot (scene variant + the player's feet, so the camera follows to a fixed place) the world is drawn exactly
as the game draws it (Hd2dRenderer.draw into an offscreen RGBA8 target: its plain blit, or the EXISTING depth of field
when a candidate turns it on in-process), then postfx.PostPass runs the candidate. Deterministic: motion/water time
reset, 120 settle frames, no HUD (the world only: Mesh draws HUD/menus after the world in both play and Studio).

Writes <out>/<shot>__<time>__<candidate>.png (top-down) and <out>/metrics.json:
  frame: mean luma, % crushed (luma <= 8), % clipped (a channel >= 254), near/far band RMS contrast + saturation
  sprites: per on-screen character, Weber contrast against a 6 px ring round it, and edge energy (mean gradient) in
           it, each also as a ratio to the original
  lamps (lamp variants): each lamp head's 5x5 colour, hue and saturation

Usage: py -3.13 lab.py OUT [--mesa] [--only shot,shot] [--times a,b] [--cands a,b] [--baseline]
"""
from __future__ import annotations

import colorsys
import dataclasses
import json
import os
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
WT = Path(r"D:\Games\Mesh-l4a")
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
for name in ("APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME", "MESH_USER_DIR", "MESH_PROJECTS_DIR"):
    os.environ[name] = str(HERE / "env" / name.lower())
    Path(os.environ[name]).mkdir(parents=True, exist_ok=True)
if "--mesa" in sys.argv:
    import mesa_preload  # noqa: F401
sys.path.insert(0, str(WT))
sys.path.insert(0, str(WT / "tooling"))
sys.path.insert(0, str(HERE))
os.chdir(WT)
import engine.optional_arcade  # noqa: E402,F401
import engine.hd2d.renderer as R  # noqa: E402

assert Path(R.__file__).resolve().is_relative_to(WT), R.__file__
import numpy as np  # noqa: E402
from engine.hd2d.dof import SUBTLE, DepthOfField  # noqa: E402
from hd2d_demo import HiddenGame  # noqa: E402
from PIL import Image  # noqa: E402
from postfx import Post, PostPass  # noqa: E402
from presets import GRADES, HAZES  # noqa: E402

PROJECT = HERE / "lakeside"
SC = "packs/core_regions/scenes"
W, H = 1280, 720


def opt(name: str, default: str | None) -> str | None:
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


SHOTS = {  # name: (scene base, feet px, note)
    "village": ("lakeside", (1000, 520), "village centre / crossroads: shop, lamp posts, paths"),
    "shore": ("lakeside", (1400, 780), "shoreline and the lake"),
    "bridge": ("lakeside", (1100, 790), "the bridge over the stream, water both sides"),
    "cottage": ("lakeside", (600, 540), "in front of the cottage (south face)"),
    "cottage2": ("lakeside", (640, 170), "north cottage from the arrival path"),
    "interior": ("cottage", (294, 200), "the cottage interior (its one lamp on, as authored)"),
}
TIMES = {"authored": "", "morning": "__l4_morning", "noon": "__l4_noon", "evening": "__l4_evening",
         "night": "__l4_night", "night_lamps": "__l4_night_lamps"}
INTERIOR_TIMES = ("authored",)


MINIATURE = DepthOfField(enabled=True, focus_range=1.5, near_falloff=6.0, far_falloff=8.0, max_blur=3.5)
TIME_KIND = {"authored": "day", "noon": "day", "morning": "morning", "evening": "evening", "night": "night",
             "night_lamps": "night"}


def candidates(shot: str, time: str) -> dict[str, Post]:
    kind = "interior" if shot == "interior" else TIME_KIND[time]
    haze = HAZES.get(TIME_KIND[time], HAZES["day"]) if shot != "interior" else None
    vig = {"vig": 0.18}
    c: dict[str, Post] = {
        "original": Post(label="original"),
        "grade": Post(label=f"grade ({kind})", **GRADES[kind]),
        "vignette": Post(label="vignette 0.18", **vig),
        "vignette_strong": Post(label="vignette 0.35", vig=0.35),
        "dof_subtle": Post(label="existing DoF: Subtle", dof=SUBTLE),
        "dof_miniature": Post(label="existing DoF: miniature values", dof=MINIATURE),
    }
    if haze:
        c["haze"] = Post(label=f"haze ({TIME_KIND[time]})", **haze)
        c["haze_overlay"] = Post(label="control: same colour, flat overlay of the haze's mean amount",
                                 **{**haze, "haze_start": -1e3, "haze_range": 1.0, "haze_height": 0.0})
        c["combo"] = Post(label="combined candidate", **{**GRADES[kind], **haze}, **vig)
        c["combo_dof"] = Post(label="combined + DoF Subtle", **{**GRADES[kind], **haze}, **vig, dof=SUBTLE)
    else:
        c["combo"] = Post(label="combined candidate", **GRADES[kind], vig=0.2)
    c["debug_depth"] = Post(label="debug: depth from focus", debug=1)
    if haze:
        c["debug_haze"] = Post(label="debug: haze amount", debug=2, **haze)
    return c


def luma(a: np.ndarray) -> np.ndarray:
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def band_stats(img: np.ndarray, rows: slice) -> dict[str, float]:
    b = img[rows].astype(np.float64)
    y = luma(b)
    mx, mn = b.max(axis=2), b.min(axis=2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0)
    return {"rms_contrast": round(float(y.std() / max(1.0, y.mean())), 4), "mean_luma": round(float(y.mean()), 2),
            "saturation": round(float(sat.mean()), 4)}


def frame_stats(img: np.ndarray) -> dict[str, object]:
    y = luma(img.astype(np.float64))
    return {"mean_luma": round(float(y.mean()), 2), "crushed_pct": round(float((y <= 8).mean() * 100), 3),
            "clipped_pct": round(float((img >= 254).any(axis=2).mean() * 100), 3),
            "far_band": band_stats(img, slice(0, H // 3)), "near_band": band_stats(img, slice(2 * H // 3, H))}


def dilate(mask: np.ndarray, n: int) -> np.ndarray:
    m = mask.copy()
    for _ in range(n):  # 4-neighbour growth, n steps
        g = m.copy()
        g[1:] |= m[:-1]
        g[:-1] |= m[1:]
        g[:, 1:] |= m[:, :-1]
        g[:, :-1] |= m[:, 1:]
        m = g
    return m


def sprite_stats(img: np.ndarray, mask: np.ndarray) -> dict[str, float] | None:
    if mask.sum() < 20:
        return None
    ring = dilate(mask, 6) & ~mask  # a 6 px ring round the sprite
    y = luma(img.astype(np.float64))
    ys, xs = np.nonzero(mask)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    sub = y[y0:y1, x0:x1]
    gx, gy = np.abs(np.diff(sub, axis=1)), np.abs(np.diff(sub, axis=0))
    m = mask[y0:y1, x0:x1]
    edge = float((gx[:, :][m[:, 1:] & m[:, :-1]]).mean() + (gy[m[1:, :] & m[:-1, :]]).mean()) / 2
    inside, around = float(y[mask].mean()), float(y[ring].mean())
    return {"pixels": int(mask.sum()), "luma": round(inside, 2), "ring_luma": round(around, 2),
            "weber": round((inside - around) / max(1.0, around), 4), "edge_energy": round(edge, 3)}


def lamp_heads(renderer: Any, img: np.ndarray) -> list[dict[str, object]]:
    out = []
    vp = np.asarray(renderer.last_vp, dtype=np.float64)
    for i, lamp in enumerate(renderer.lighting.lamps):
        if lamp.intensity <= 0:
            continue
        c = vp @ np.array([lamp.x / 32, lamp.y / 32, lamp.elevation / 32, 1.0])
        if c[3] <= 0:
            continue
        x, y = (c[0] / c[3] * 0.5 + 0.5) * W, (1 - (c[1] / c[3] * 0.5 + 0.5)) * H
        if not (4 <= x < W - 4 and 4 <= y < H - 4):
            continue
        px = img[max(0, int(y) - 14):int(y) + 15, max(0, int(x) - 10):int(x) + 11].reshape(-1, 3).astype(np.float64)
        top = px[np.argsort(luma(px))[-8:]]  # the glass: the 8 brightest pixels round the head
        brightest = top.mean(axis=0)
        r, g, b = (brightest / 255).tolist()
        hh, ss, vv = colorsys.rgb_to_hsv(r, g, b)
        out.append({"lamp": i, "at": [round(x), round(y)], "rgb": [int(v) for v in brightest],
                    "hue_deg": round(hh * 360, 1), "sat": round(ss, 3), "val": round(vv, 3)})
    return out


def main() -> None:
    only = (opt("--only", None) or ",".join(SHOTS)).split(",")
    times_opt = opt("--times", None)
    cand_opt = opt("--cands", None)
    game = HiddenGame(PROJECT, size=(W, H))
    window = game.window
    window.audio.set_muted(True)
    ctx = window.ctx
    target_tex = ctx.texture((W, H), components=4)
    target = ctx.framebuffer(color_attachments=[target_tex])
    metrics: dict[str, object] = {"gl": str(ctx.info.RENDERER), "size": [W, H]}
    mpath = OUT / "metrics.json"
    if mpath.exists():
        metrics.update(json.loads(mpath.read_text(encoding="utf-8")))
    post_pass = None
    try:
        for shot in only:
            base, feet, note = SHOTS[shot]
            times = INTERIOR_TIMES if shot == "interior" else tuple(TIMES)
            if times_opt:
                times = tuple(t for t in times if t in times_opt.split(","))
            for time in times:
                scene = f"{SC}/{base}{TIMES[time]}.json"
                game.load(scene)
                game.step(5)
                p = game.player()
                p.center_x, p.bottom = feet
                window.motion_time = 0.0
                if hasattr(window, "water_time"):
                    window.water_time = 0.0
                game.step(120)
                hd = window.hd2d_renderer
                if post_pass is None:
                    post_pass = PostPass(ctx, R.BLIT_VS, hd._blit, (W, H))
                post_pass.quad = hd._blit  # (this room's renderer: the last one's geometry was released with it)
                base_settings = hd.settings
                # sprite masks (each on-screen character drawn flat against the world's depth)
                masks = []
                target.use()
                for sp in hd._sprites():
                    raw = hd.draw(solid=sp, read=True)
                    a = np.frombuffer(raw, dtype=np.uint8).reshape(H, W, 3)
                    m = a[..., 0] > 128
                    if m.sum() >= 20:
                        masks.append((getattr(sp, "name", None) or type(sp).__name__, m))
                cands = candidates(shot, time)
                if cand_opt:
                    cands = {k: v for k, v in cands.items() if k in cand_opt.split(",") or k == "original"}
                if "--baseline" in sys.argv:
                    cands = {"original": cands["original"]}
                haze_mean = None
                orig_img = None
                orig_sprites: list[dict[str, float] | None] = []
                for cname, post in cands.items():
                    hd.settings = dataclasses.replace(base_settings, depth_of_field=post.dof) if post.dof is not None \
                        else base_settings
                    target.use()
                    target.clear(color=(0, 0, 0, 255))
                    hd.draw()
                    focus = hd.dof_focus(hd.camera, True)[0]
                    if cname == "haze_overlay" and haze_mean is not None:
                        post.haze_max = haze_mean  # the same average amount of the same colour, everywhere
                    if post.active():
                        raw = post_pass.run(target_tex, hd._fbo_parts[1], hd, post, focus)
                    else:
                        raw = target.read(components=3)
                    img = np.flipud(np.frombuffer(raw, dtype=np.uint8).reshape(H, W, 3)).copy()
                    key = f"{shot}__{time}__{cname}"
                    if cname == "haze":  # its mean amount over the frame (the overlay control matches it)
                        dbg = Post(**{**{f: getattr(post, f) for f in ("haze", "haze_col", "haze_start", "haze_range",
                                                                       "haze_max", "haze_height")}, "debug": 2})
                        hraw = post_pass.run(target_tex, hd._fbo_parts[1], hd, dbg, focus)
                        haze_mean = float(np.frombuffer(hraw, dtype=np.uint8).mean()) / 255.0
                    Image.fromarray(img).save(OUT / f"{key}.png")
                    if cname.startswith("debug"):
                        continue
                    entry: dict[str, object] = {"shot": shot, "time": time, "candidate": cname, "label": post.label,
                                                "scene": scene, "note": note, "frame": frame_stats(img),
                                                "dof": hd.last_dof and {k: v for k, v in hd.last_dof.items()
                                                                         if k != "settings"},
                                                "focus_m": round(focus, 3), "post": post.as_dict()}
                    sprites = [sprite_stats(img, np.flipud(m)) for _n, m in masks]
                    if cname == "original":
                        orig_img, orig_sprites = img, sprites
                        if not post.active():  # the pass with everything off must be the input exactly
                            ident = post_pass.run(target_tex, hd._fbo_parts[1], hd, Post(debug=0), focus)
                            same = bytes(ident) == bytes(raw)
                            world = hd.draw(read=True)  # (the world FBO as drawn, before any composite)
                            entry["identity_pass_exact"] = same
                            entry["blit_equals_world"] = (bytes(world) == bytes(raw)) if hd.last_dof is None else None
                            target.use()
                    kept: list[dict[str, Any]] = []
                    entry["sprites"] = kept
                    for s, o in zip(sprites, orig_sprites):
                        if s is None or o is None:
                            continue
                        s = dict(s)
                        s["weber_ratio"] = round(s["weber"] / o["weber"], 3) if abs(o["weber"]) > 1e-3 else None
                        s["edge_ratio"] = round(s["edge_energy"] / max(1e-6, o["edge_energy"]), 3)
                        kept.append(s)
                    if orig_img is not None and cname != "original":
                        d = np.abs(img.astype(np.int16) - orig_img.astype(np.int16)).max(axis=2)
                        entry["changed_pct"] = round(float((d > 0).mean() * 100), 2)
                        entry["mean_abs_delta"] = round(float(d.mean()), 3)
                    if "lamps" in time:
                        entry["lamp_heads"] = lamp_heads(hd, img)
                    metrics[key] = entry
                hd.settings = base_settings
                mpath.write_text(json.dumps(metrics, indent=1), encoding="utf-8")
                print(shot, time, len(cands), flush=True)
    finally:
        game.close()


if __name__ == "__main__":
    main()
