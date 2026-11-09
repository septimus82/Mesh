"""M17-L4-2 visual lab: the PRODUCTION colour grade and vignette (engine.hd2d.post through the renderer's final composite)
on the scratch Lakeside L1b copy, as the game draws it: draw(read_final=True) into an offscreen 1280x720 target,
motion/water time reset, 120 settle frames. Per shot x time x preset: the frame (top-down PNG) and metrics against
the original (preset off):
  frame   mean luma, crushed (luma <= 8) / clipped (a channel >= 254) %, dark detail (luma std among pixels the
          original has under 40), corners (mean luma of the 8% corner boxes, ratio to the original)
  colour  grass (green, saturated pixels of the original) and water/sky (blue) mean hue shift (deg) and saturation ratio
  sprites each on-screen character: |Weber| contrast change against a 6 px ring, edge-energy ratio, mean hue shift
  lamps   (lamp variants) the lamp glass: the 8 brightest pixels round each visible lamp head, hue shift (deg)
Usage: py -3.13 lab.py WORKTREE OUT [--shots a,b] [--presets a,b] [--strength S] [--mesa]
"""
from __future__ import annotations

import colorsys
import dataclasses
import json
import os
import sys
from pathlib import Path
from typing import Any

WT, OUT = Path(sys.argv[1]), Path(sys.argv[2])
L4A = Path(r"C:\Users\slebb\AppData\Local\Temp\claude\c18a071c64bbe7a7\bff3a484-a7b8-4c6b-bf14-a015c42db67e\scratchpad\l4a")
OUT.mkdir(parents=True, exist_ok=True)
if "--mesa" in sys.argv:
    sys.path.insert(0, str(L4A))
    import mesa_preload  # noqa: F401
sys.path.insert(0, str(WT))
sys.path.insert(1, str(WT / "tooling"))
os.chdir(WT)
import engine.optional_arcade  # noqa: E402,F401
import engine.hd2d.renderer as R  # noqa: E402

assert Path(R.__file__).resolve().is_relative_to(WT.resolve()), R.__file__
import numpy as np  # noqa: E402
from engine.hd2d.post import Post  # noqa: E402
from hd2d_demo import HiddenGame  # noqa: E402
from PIL import Image  # noqa: E402

W, H = 1280, 720
SC = "packs/core_regions/scenes"
SHOTS = {"village": ("lakeside", (1000, 520)), "shore": ("lakeside", (1400, 780)), "bridge": ("lakeside", (1100, 790)),
         "cottage": ("lakeside", (600, 540)), "interior": ("cottage", (294, 200))}
TIMES = {"day": "", "evening": "__l4_evening", "night_lamps": "__l4_night_lamps"}
PRESETS = ("off", "natural", "golden_hour", "moonlight", "interior_warm")


def opt(name: str, default: str | None) -> str | None:
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def luma(a: np.ndarray) -> np.ndarray:
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def hsv(a: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    f = a.astype(np.float64) / 255.0
    mx, mn = f.max(axis=-1), f.min(axis=-1)
    d = mx - mn
    s = np.where(mx > 0, d / np.maximum(mx, 1e-9), 0)
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    h = np.zeros_like(mx)
    m = d > 1e-9
    rc = np.where(m & (mx == r), ((g - b) / np.maximum(d, 1e-9)) % 6, 0)
    gc = np.where(m & (mx == g) & (mx != r), (b - r) / np.maximum(d, 1e-9) + 2, 0)
    bc = np.where(m & (mx == b) & (mx != r) & (mx != g), (r - g) / np.maximum(d, 1e-9) + 4, 0)
    h = (rc + gc + bc) * 60.0
    return h, s, mx


def hue_shift(a: np.ndarray, b: np.ndarray, mask: np.ndarray) -> float | None:
    if mask.sum() < 50:
        return None
    ha, _, _ = hsv(a[mask])
    hb, _, _ = hsv(b[mask])
    d = np.abs(hb - ha)
    d = np.minimum(d, 360 - d)
    return round(float(np.mean(d)), 2)


def dilate(mask: np.ndarray, n: int) -> np.ndarray:
    m = mask.copy()
    for _ in range(n):
        g = m.copy()
        g[1:] |= m[:-1]
        g[:-1] |= m[1:]
        g[:, 1:] |= m[:, :-1]
        g[:, :-1] |= m[:, 1:]
        m = g
    return m


def sprite_stats(img: np.ndarray, mask: np.ndarray) -> dict[str, float]:
    ring = dilate(mask, 6) & ~mask
    y = luma(img.astype(np.float64))
    ys, xs = np.nonzero(mask)
    sub = y[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    m = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    gx, gy = np.abs(np.diff(sub, axis=1)), np.abs(np.diff(sub, axis=0))
    edge = float((gx[m[:, 1:] & m[:, :-1]]).mean() + (gy[m[1:, :] & m[:-1, :]]).mean()) / 2
    inside, around = float(y[mask].mean()), float(y[ring].mean())
    return {"pixels": int(mask.sum()), "weber": (inside - around) / max(1.0, around), "edge": edge}


def lamp_glass(hd: Any, img: np.ndarray) -> list[dict[str, Any]]:
    out = []
    vp = np.asarray(hd.last_vp, dtype=np.float64)
    for i, lamp in enumerate(hd.lighting.lamps):
        if lamp.intensity <= 0:
            continue
        c = vp @ np.array([lamp.x / 32, lamp.y / 32, lamp.elevation / 32, 1.0])
        if c[3] <= 0:
            continue
        x, y = (c[0] / c[3] * 0.5 + 0.5) * W, (1 - (c[1] / c[3] * 0.5 + 0.5)) * H
        if not (14 <= x < W - 14 and 14 <= y < H - 14):
            continue
        px = img[int(y) - 14:int(y) + 15, int(x) - 10:int(x) + 11].reshape(-1, 3).astype(np.float64)
        top = px[np.argsort(luma(px))[-8:]].mean(axis=0)
        h, s, v = colorsys.rgb_to_hsv(*(top / 255))
        out.append({"lamp": i, "at": [round(x), round(y)], "rgb": [round(float(t)) for t in top],
                    "hue": round(h * 360, 2), "sat": round(s, 3), "glass": bool(s > 0.4 and v > 0.7)})
    return out


def corners(img: np.ndarray) -> float:
    y = luma(img.astype(np.float64))
    bw, bh = int(W * 0.08), int(H * 0.08)
    boxes = [y[:bh, :bw], y[:bh, -bw:], y[-bh:, :bw], y[-bh:, -bw:]]
    return float(np.mean([b.mean() for b in boxes]))


def main() -> None:
    shots = (opt("--shots", None) or ",".join(SHOTS)).split(",")
    presets = (opt("--presets", None) or ",".join(PRESETS)).split(",")
    strength = float(opt("--strength", "1") or 1)
    game = HiddenGame(L4A / "lakeside", size=(W, H))
    game.window.audio.set_muted(True)
    ctx = game.window.ctx
    tex = ctx.texture((W, H), components=4)
    fbo = ctx.framebuffer(color_attachments=[tex])
    metrics: dict[str, Any] = {"gl": str(ctx.info.RENDERER), "strength": strength}
    try:
        for shot in shots:
            base, feet = SHOTS[shot]
            for time, suffix in TIMES.items():
                if base == "cottage" and time != "day":
                    continue
                game.load(f"{SC}/{base}{suffix}.json")
                game.step(5)
                p = game.player()
                p.center_x, p.bottom = feet
                game.window.motion_time = 0.0
                if hasattr(game.window, "water_time"):
                    game.window.water_time = 0.0
                game.step(120)
                hd = game.window.hd2d_renderer
                settings = hd.settings
                fbo.use()
                masks = []
                for sp in hd._sprites():
                    a = np.frombuffer(hd.draw(solid=sp, read=True), dtype=np.uint8).reshape(H, W, 3)
                    m = np.flipud(a[..., 0] > 128)
                    if m.sum() >= 40:
                        masks.append(m)
                orig = None
                for preset in ["off", *[x for x in presets if x != "off"]]:
                    hd.settings = settings if preset == "off" else dataclasses.replace(
                        settings, post=Post(preset, strength))
                    fbo.use()
                    raw = hd.draw(read_final=True)
                    img = np.flipud(np.frombuffer(raw, dtype=np.uint8).reshape(H, W, 3)).copy()
                    key = f"{shot}__{time}__{preset}"
                    Image.fromarray(img).save(OUT / f"{key}.png")
                    e: dict[str, Any] = {"shot": shot, "time": time, "preset": preset, "stage": hd.last_stage}
                    y = luma(img.astype(np.float64))
                    e["mean_luma"] = round(float(y.mean()), 2)
                    e["crushed_pct"] = round(float((y <= 8).mean() * 100), 3)
                    e["clipped_pct"] = round(float((img >= 254).any(axis=2).mean() * 100), 3)
                    e["corners"] = round(corners(img), 2)
                    if "lamps" in time:
                        e["lamps"] = lamp_glass(hd, img)
                    if preset == "off":
                        orig = img
                        e["sprites"] = [sprite_stats(img, m) for m in masks]
                    else:
                        o = orig.astype(np.float64)
                        yo = luma(o)
                        h, s, v = hsv(orig)
                        grass = (h > 70) & (h < 160) & (s > 0.25) & (v > 0.12)
                        blue = (h > 180) & (h < 250) & (s > 0.2) & (v > 0.12)
                        dark = yo < 40
                        _, s2, _ = hsv(img)
                        e["grass_hue_shift"] = hue_shift(orig, img, grass)
                        e["grass_sat_ratio"] = round(float(s2[grass].mean() / max(1e-6, s[grass].mean())), 3) if grass.sum() > 50 else None
                        e["blue_hue_shift"] = hue_shift(orig, img, blue)
                        e["dark_detail_ratio"] = round(float(y[dark].std() / max(1e-6, yo[dark].std())), 3) if dark.sum() > 500 else None
                        e["dark_mean_ratio"] = round(float(y[dark].mean() / max(1e-6, yo[dark].mean())), 3) if dark.sum() > 500 else None
                        base_e = metrics[f"{shot}__{time}__off"]
                        e["crushed_increase"] = round(e["crushed_pct"] - base_e["crushed_pct"], 3)
                        e["clipped_increase"] = round(e["clipped_pct"] - base_e["clipped_pct"], 3)
                        e["corner_ratio"] = round(e["corners"] / max(1e-6, base_e["corners"]), 3)
                        sp = []
                        for m, so in zip(masks, base_e["sprites"]):
                            st = sprite_stats(img, m)
                            sp.append({"pixels": st["pixels"], "abs_weber_change": round(abs(st["weber"]) - abs(so["weber"]), 4),
                                       "edge_ratio": round(st["edge"] / max(1e-6, so["edge"]), 3),
                                       "hue_shift": hue_shift(orig, img, m)})
                        e["sprites"] = sp
                        if "lamps" in time:
                            shifts = []
                            for a, b in zip(base_e["lamps"], e["lamps"]):
                                if a["glass"]:
                                    d = abs(a["hue"] - b["hue"])
                                    shifts.append(round(min(d, 360 - d), 2))
                            e["glass_hue_shift"] = shifts
                    metrics[key] = e
                hd.settings = settings
                game.window.use()
                (OUT / "metrics.json").write_text(json.dumps(metrics, indent=1), encoding="utf-8")
                print(shot, time, flush=True)
    finally:
        game.close()


main()
