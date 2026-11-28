"""M17-L4-2: an HD-2D room's colour grade and vignette (engine.hd2d.post), checked in real frames (hidden window).

    py -3.13 tooling/hd2d_post_study.py OUT

Rooms: hd2d_lamp_glow_demo's four (the template village at night with its lamps' glowing heads (E2), Lakeside's cottage
and posts, #459's fixture room, the cottage interior) and an E1 emissive-swatches room. In each, the picture the renderer
makes (``draw(read_final=True)``):

- no post block, and a preset at strength 0: the original blit, byte for byte, nothing made;
- each preset: the composite runs (its uniforms set once, not per frame); characters as readable (|Weber contrast|
  against a ring round them, edge energy), the lamp glass and the E1 emission keep their hue, no new clipping, the
  night grade doesn't crush shadows;
- the vignette alone (Natural with and without it): the centre untouched, the corners darker;
- with the depth of field: the DoF draws into the composite's input (one chain target), and the world read
  (``draw(read=True)``) stays the world;
- the HUD: drawn after the renderer, its own pixels the same whatever the grade.
"""

from __future__ import annotations

import colorsys
import dataclasses
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(1, str(REPO / "tooling"))
PRESETS = ("natural", "golden_hour", "moonlight", "interior_warm")


def _np() -> Any:
    import numpy as np  # noqa: PLC0415

    return np


def luma(a: Any) -> Any:
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def settle(game: Any, scene: str) -> Any:
    game.load(scene)
    game.step(30)
    game.window.motion_time = 0.0
    if hasattr(game.window, "water_time"):
        game.window.water_time = 0.0
    return game.window.hd2d_renderer


def picture(game: Any, hd: Any) -> Any:
    np = _np()
    w, h = game.window.get_framebuffer_size()
    game.window.use()
    return np.flipud(np.frombuffer(hd.draw(read_final=True), dtype=np.uint8).reshape(h, w, 3)).copy()


def ring(mask: Any, n: int = 6) -> Any:
    m = mask.copy()
    for _ in range(n):
        g = m.copy()
        g[1:] |= m[:-1]
        g[:-1] |= m[1:]
        g[:, 1:] |= m[:, :-1]
        g[:, :-1] |= m[:, 1:]
        m = g
    return m & ~mask


def readability(img: Any, mask: Any) -> tuple[float, float]:
    np = _np()
    y = luma(img.astype(np.float64))
    inside, around = float(y[mask].mean()), float(y[ring(mask)].mean())
    ys, xs = np.nonzero(mask)
    sub, m = y[ys.min():ys.max() + 1, xs.min():xs.max() + 1], mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    gx, gy = np.abs(np.diff(sub, axis=1)), np.abs(np.diff(sub, axis=0))
    edge = float((gx[m[:, 1:] & m[:, :-1]]).mean() + (gy[m[1:, :] & m[:-1, :]]).mean()) / 2
    return (inside - around) / max(1.0, around), edge


def glass(hd: Any, img: Any) -> list[tuple[float, float]]:
    """(hue degrees, saturation) of the 8 brightest pixels round each lit lamp head in view."""
    np = _np()
    h, w = img.shape[:2]
    vp = np.asarray(hd.last_vp, dtype=np.float64)
    out = []
    for lamp in hd.lighting.lamps:
        if lamp.intensity <= 0:
            continue
        c = vp @ np.array([lamp.x / 32, lamp.y / 32, lamp.elevation / 32, 1.0])
        if c[3] <= 0:
            continue
        x, y = (c[0] / c[3] * 0.5 + 0.5) * w, (1 - (c[1] / c[3] * 0.5 + 0.5)) * h
        if not (14 <= x < w - 14 and 14 <= y < h - 14):
            continue
        px = img[int(y) - 14:int(y) + 15, int(x) - 10:int(x) + 11].reshape(-1, 3).astype(np.float64)
        top = px[np.argsort(luma(px))[-8:]].mean(axis=0) / 255
        hh, ss, _vv = colorsys.rgb_to_hsv(*top)
        out.append((hh * 360, ss))
    return out


def room(game: Any, scene: str) -> dict[str, Any]:
    from engine.hd2d.dof import SUBTLE  # noqa: PLC0415
    from engine.hd2d.post import Post  # noqa: PLC0415

    np = _np()
    hd = settle(game, scene)
    base = hd.settings
    r: dict[str, Any] = {"scene": scene}
    off = picture(game, hd)
    world = bytes(hd.draw(read=True))
    r["off"] = {"stage": hd.last_stage, "made": hd._composite is not None, "draw_calls": hd.draw_calls}
    hd.settings = dataclasses.replace(base, post=Post("natural", 0.0))
    zero = picture(game, hd)
    r["strength_zero"] = {"same": bool(np.array_equal(zero, off)), "stage": hd.last_stage, "made": hd._composite is not None}
    masks = []
    game.window.use()
    for sp in hd._sprites():
        w, h = game.window.get_framebuffer_size()
        m = np.flipud(np.frombuffer(hd.draw(solid=sp, read=True), dtype=np.uint8).reshape(h, w, 3)[..., 0] > 128)
        if m.sum() >= 40:
            masks.append(m)
    base_read = [readability(off, m) for m in masks]
    off_glass = glass(hd, off)
    yo = luma(off.astype(np.float64))
    r["presets"] = {}
    for name in PRESETS:
        hd.settings = dataclasses.replace(base, post=Post(name))
        img = picture(game, hd)
        updates = hd._composite.uniform_updates
        again = picture(game, hd)
        y = luma(img.astype(np.float64))
        rd = [readability(img, m) for m in masks]
        gl = glass(hd, img)
        dark = yo < 40
        r["presets"][name] = {
            "stage": hd.last_stage, "changed_share": round(float((np.abs(img.astype(int) - off.astype(int)).max(axis=2)
                                                                  > 0).mean()), 4),
            "repeat_same": bool(np.array_equal(img, again)), "uniform_updates_on_repeat": hd._composite.uniform_updates
            - updates, "draw_calls": hd.draw_calls,
            "weber_change_min": min((abs(a[0]) - abs(b[0]) for a, b in zip(rd, base_read)), default=None),
            "edge_ratio_min": min((a[1] / max(1e-6, b[1]) for a, b in zip(rd, base_read)), default=None),
            "glass_hue_shift_max": max((min(abs(a[0] - b[0]), 360 - abs(a[0] - b[0])) for a, b in zip(gl, off_glass)
                                        if b[1] > 0.4), default=None),
            "crushed_increase": round(float((y <= 8).mean() - (yo <= 8).mean()) * 100, 3),
            "clipped_increase": round(float((img >= 254).any(axis=2).mean() - (off >= 254).any(axis=2).mean()) * 100, 3),
            "dark_mean_ratio": round(float(y[dark].mean() / max(1e-6, yo[dark].mean())), 3) if dark.sum() > 200 else None,
            "world_read_unchanged": bytes(hd.draw(read=True)) == world}
    # the vignette alone: Natural without and with it
    hd.settings = dataclasses.replace(base, post=Post("natural", 1.0, 0.0))
    plain = picture(game, hd)
    hd.settings = dataclasses.replace(base, post=Post("natural", 1.0, 0.4))
    vig = picture(game, hd)
    h, w = plain.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    q = np.stack([((xx + 0.5) / w - 0.5) * (w / h), (yy + 0.5) / h - 0.5])
    rr = np.sqrt((q ** 2).sum(axis=0)) / np.hypot(0.5 * w / h, 0.5)
    centre, corner = rr < 0.55, rr > 0.95
    lp, lv = luma(plain.astype(np.float64)), luma(vig.astype(np.float64))
    r["vignette"] = {"centre_same": bool(np.array_equal(plain[centre], vig[centre])),
                     "corner_ratio": round(float(lv[corner].mean() / max(1e-6, lp[corner].mean())), 3)}
    # with the depth of field (forced on any driver): the DoF into the composite's input
    hd.settings = dataclasses.replace(base, depth_of_field=SUBTLE, post=Post("moonlight"))
    hd.dof_allow_software = True
    picture(game, hd)
    r["with_dof"] = {"stage": hd.last_stage, "chain_allocations": hd._composite.chain_allocations,
                     "world_read_unchanged": bytes(hd.draw(read=True)) == world}
    hd.dof_allow_software = False
    hd.settings = base
    r["off_again_same"] = bool(np.array_equal(picture(game, hd), off))
    return r


def known_texels(game: Any, scene: str) -> dict[str, Any]:
    """The grade's maths on known texels: decoded to linear light, graded, encoded, alpha kept. Exposure 1.5 alone (a
    grey stays grey): sRGB 100 -> linear 0.1274 x 1.5 = 0.1911 -> sRGB 121 (graded in sRGB values instead it would be
    150); saturation 0 alone: a colour becomes its luminance's grey."""
    from engine.hd2d.post import NEUTRAL  # noqa: PLC0415

    hd = settle(game, scene)
    ctx = hd.ctx
    comp = hd._final_composite()

    class Fixed:  # (a Post's uniforms, chosen here)
        def __init__(self, **u: Any) -> None:
            base = {"u_wb": NEUTRAL.white_balance, "u_exposure": 1.0, "u_contrast": 1.0, "u_saturation": 1.0,
                    "u_shadow_tint": (1.0, 1.0, 1.0), "u_highlight_tint": (1.0, 1.0, 1.0), "u_split": 0.0,
                    "u_protect": 0.0, "u_vignette": 0.0}
            self.u = {**base, **u}

        def uniforms(self) -> dict[str, Any]:
            return self.u

    def run(texel: tuple[int, int, int, int], post: Any) -> tuple[int, ...]:
        src = ctx.texture((4, 4), components=4, data=bytes(texel) * 16)
        depth = ctx.depth_texture((4, 4))
        depth.compare_func = None
        dst = ctx.texture((4, 4), components=4)
        fbo = ctx.framebuffer(color_attachments=[dst])
        try:
            fbo.use()
            comp.configure(post)
            with ctx.enabled_only():
                comp.render(hd._blit, src, depth)
            return tuple(fbo.read(components=4)[:4])
        finally:
            comp.configure(None)
            game.window.use()
            for o in (fbo, dst, src, depth):
                o.delete()

    return {"exposure_grey": run((100, 100, 100, 77), Fixed(u_exposure=1.5)),
            "saturation_zero": run((200, 60, 30, 255), Fixed(u_saturation=0.0)),
            "neutral": run((37, 180, 222, 9), Fixed()),
            # highlight protection: a bright warm texel (lamp glass) under a strong cool white balance
            "bright_protected": run((250, 180, 80, 255), Fixed(u_wb=(0.85, 0.95, 1.2), u_protect=0.9)),
            "bright_unprotected": run((250, 180, 80, 255), Fixed(u_wb=(0.85, 0.95, 1.2), u_protect=0.0)),
            "dark_protected": run((60, 50, 40, 255), Fixed(u_wb=(0.85, 0.95, 1.2), u_protect=0.9))}


def hud(game: Any, scene: str) -> dict[str, Any]:
    """The window as the game draws it (world, then HUD): the HUD's own pixels (where it covers the world fully) the
    same with and without the grade."""
    from engine.hd2d.post import Post  # noqa: PLC0415

    np = _np()
    hd = settle(game, scene)
    base = hd.settings

    def window() -> Any:
        return np.asarray(game.draw().convert("RGB")).astype(int)

    plain = window()
    hd.settings = dataclasses.replace(base, post=Post("golden_hour"))
    graded = window()
    kept = hd.draw
    hd.draw = lambda *a, **k: None  # (the HUD over nothing: where it is drawn)
    try:
        hd.settings = base
        alone = window()
        hd.settings = dataclasses.replace(base, post=Post("golden_hour"))
        alone_graded = window()
    finally:
        hd.draw = kept
        hd.settings = base
    covered = (np.abs(plain - alone).max(axis=2) == 0) & (alone.max(axis=2) > 0)  # opaque HUD: the world doesn't show
    return {"hud_pixels": int(covered.sum()), "hud_same": bool((np.abs(graded - plain).max(axis=2)[covered] == 0).all()),
            "hud_alone_same": bool(np.array_equal(alone, alone_graded)),
            "world_changed": bool((np.abs(graded - plain).max(axis=2)[~covered] > 0).any())}


def study(out: Path, *, size: tuple[int, int] = (960, 540)) -> dict[str, Any]:
    import hd2d_emissive_demo as em
    import hd2d_lamp_glow_demo as glow
    from hd2d_demo import HiddenGame

    from engine.project_scaffold import create_project  # noqa: PLC0415

    out.mkdir(parents=True, exist_ok=True)
    project = out / "game"
    rooms = glow.build(project)
    report: dict[str, Any] = {"size": list(size), "rooms": {}}
    game = HiddenGame(project, size=size)
    game.window.audio.set_muted(True)
    try:
        report["gl"] = str(game.window.ctx.info.RENDERER)
        for name, scene in rooms.items():
            report["rooms"][name] = room(game, scene)
        report["hud"] = hud(game, rooms["village"])
        report["texels"] = known_texels(game, rooms["village"])
    finally:
        game.close()
    emissive = out / "emissive"
    create_project(emissive, "Emission", "hd2d_rpg")
    model = em.swatches_glb(emissive / "assets" / "models" / "swatches.glb")
    em.place(emissive, f"assets/models/{model.name}", sun="night")
    game = HiddenGame(emissive, size=size)
    game.window.audio.set_muted(True)
    try:
        report["rooms"]["emissive"] = room(game, em.SCENE)
        report["emission"] = emission(game, em)
    finally:
        game.close()
    return report


def emission(game: Any, em: Any) -> dict[str, Any]:
    """E1's emissive swatches at night: each swatch's middle keeps its hue under every preset (they're bright: the
    highlight protection)."""
    from engine.hd2d.post import Post  # noqa: PLC0415

    hd = game.window.hd2d_renderer
    base = hd.settings

    def panels() -> dict[str, tuple[float, float, float]]:
        game.window.use()
        image = game.draw()
        vp = hd.last_vp
        out = {}
        for i, (name, *_rest) in enumerate(em.SWATCHES):
            r, g, b = em.pixel_at(image, vp, em.panel_points(i)["middle"])
            hh, ss, vv = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            out[name] = (hh * 360, ss, vv)
        return out

    before = panels()
    shifts: dict[str, float] = {}
    for name in PRESETS:
        hd.settings = dataclasses.replace(base, post=Post(name))
        now = panels()
        worst = 0.0
        for k, (h0, s0, v0) in before.items():
            if s0 > 0.3 and v0 > 0.5:  # (a coloured, bright swatch: hue means something)
                d = abs(now[k][0] - h0)
                worst = max(worst, min(d, 360 - d))
        shifts[name] = round(worst, 2)
    hd.settings = base
    return {"hue_shift_max": shifts, "coloured_swatches": sum(1 for (_h, s, v) in before.values() if s > 0.3 and v > 0.5)}


def main() -> None:
    out = Path(sys.argv[1])
    found = study(out)
    (out / "report.json").write_text(json.dumps(found, indent=1, default=str), encoding="utf-8")
    print(json.dumps(found, indent=1, default=str))


if __name__ == "__main__":
    os.environ.setdefault("MESH_STUDIO_NO_AI_BRIDGE", "1")
    main()
