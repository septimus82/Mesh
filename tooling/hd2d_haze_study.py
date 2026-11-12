"""M17-L4-3: an HD-2D room's atmospheric depth (engine.hd2d.haze), checked in real frames (hidden window).

    py -3.13 tooling/hd2d_haze_study.py OUT

Rooms: hd2d_lamp_glow_demo's four (the template village, Lakeside's cottage and posts, #459's fixture room, the cottage
interior). In each, the picture the renderer makes (``draw(read_final=True)``) against the world's own depth buffer:

- no haze block, and a preset at strength 0: the original blit, byte for byte, nothing made;
- each preset: the composite runs (its uniforms set once, not per frame), and **every pixel's haze is the one its own
  depth calls for**: the share it moved toward the haze colour (read back in linear light) against
  ``engine.hd2d.haze.amount`` of its depth (read from the depth buffer, linearised); pixels nearer than the onset are
  their original bytes exactly; characters keep their contrast; the onset lies beyond the followed character's depth;
- the camera moving (the player walking): each frame still matches its depth, the onset stays put relative to the focus;
- a flat (orthographic) camera: the same, with its own linearisation;
- with the colour grade and the depth of field: haze, then grade, the DoF into the composite's input;
- known texels: near depth is the texel exactly, far depth the linear-light mix, alpha kept;
- the HUD: drawn after the renderer, its own pixels the same with the haze;
- a driver refusing the composite: the original picture, the reason kept (software GL runs the haze: it is cheap).
"""

from __future__ import annotations

import ctypes
import dataclasses
import json
import math
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(1, str(REPO / "tooling"))
PRESETS = ("daytime", "evening")
CONTRAST = 0.15  # a channel's |haze - original| (linear) at least this: its share readable past 8-bit rounding


def _np() -> Any:
    import numpy as np  # noqa: PLC0415

    return np


def luma(a: Any) -> Any:
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def lin(a: Any) -> Any:
    np = _np()
    c = a.astype(np.float64) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def settle(game: Any, scene: str) -> Any:
    game.load(scene)
    game.step(30)
    game.window.motion_time = 0.0
    if hasattr(game.window, "water_time"):
        game.window.water_time = 0.0
    return game.window.hd2d_renderer


def picture(game: Any, hd: Any) -> Any:
    """The picture as drawn (rows bottom-up, as the depth buffer's)."""
    np = _np()
    w, h = game.window.get_framebuffer_size()
    game.window.use()
    return np.frombuffer(hd.draw(read_final=True), dtype=np.uint8).reshape(h, w, 3).copy()


def depth_of(hd: Any) -> Any:
    """The world's depth buffer as drawn last (0-1, rows bottom-up)."""
    from pyglet import gl  # noqa: PLC0415

    np = _np()
    tex = hd._fbo_parts[1]
    w, h = tex.size
    buf = (ctypes.c_float * (w * h))()
    gl.glActiveTexture(gl.GL_TEXTURE0)
    gl.glBindTexture(gl.GL_TEXTURE_2D, tex.glo.value if hasattr(tex.glo, "value") else tex.glo)
    gl.glGetTexImage(gl.GL_TEXTURE_2D, 0, gl.GL_DEPTH_COMPONENT, gl.GL_FLOAT, buf)
    gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
    return np.frombuffer(buf, dtype=np.float32).reshape(h, w).astype(np.float64)


def metres(d: Any, ortho: bool) -> Any:
    from engine.hd2d.dof import FAR, NEAR  # noqa: PLC0415

    return NEAR + d * (FAR - NEAR) if ortho else NEAR * FAR / (FAR - d * (FAR - NEAR))


def depth_match(hd: Any, off: Any, hazed: Any) -> dict[str, Any]:
    """Each pixel's haze against the one its own depth calls for (engine.hd2d.haze.amount)."""
    np = _np()
    h = hd.last_haze
    colour = np.asarray(hd._haze_values[2]["u_haze_color"], dtype=np.float64)
    d = depth_of(hd)
    z = metres(d, hd.camera.ortho)
    x = np.maximum(0.0, z - h["onset"]) / h["falloff"]
    want = np.where(d < 1.0, h["strength"] * (1.0 - np.exp(-3.0 * x * x)), 0.0)  # (the backdrop: never hazed)
    o, n = lin(off), lin(hazed)
    gap = colour - o
    ch = np.argmax(np.abs(gap), axis=2)
    pick = np.take_along_axis
    g = pick(gap, ch[..., None], 2)[..., 0]
    got = (pick(n, ch[..., None], 2)[..., 0] - pick(o, ch[..., None], 2)[..., 0]) / np.where(np.abs(g) > 1e-9, g, 1.0)
    readable = np.abs(g) >= CONTRAST
    err = np.abs(got - want)[readable]
    near = want <= 0.0
    bins = [float(want[(z >= a) & (z < b)].mean()) if ((z >= a) & (z < b)).sum() > 50 else None
            for a, b in zip(np.linspace(z.min(), z.max(), 7)[:-1], np.linspace(z.min(), z.max(), 7)[1:])]
    return {"pixels": int(readable.sum()), "backdrop_share": round(float((d >= 1.0).mean()), 4),
            "err_p99": round(float(np.percentile(err, 99)), 4) if err.size else None,
            "err_max": round(float(err.max()), 4) if err.size else None,
            "near_share": round(float(near.mean()), 4), "near_same": bool(np.array_equal(off[near], hazed[near])),
            "hazed_share": round(float((want > 0.002).mean()), 4), "most": round(float(want.max()), 4),
            "z_range": [round(float(z.min()), 2), round(float(z.max()), 2)],
            "by_depth": [None if b is None else round(b, 4) for b in bins]}


def readability(img: Any, mask: Any) -> tuple[float, float]:
    np = _np()

    def ring(m: Any, k: int = 6) -> Any:
        r = m.copy()
        for _ in range(k):
            g = r.copy()
            g[1:] |= r[:-1]
            g[:-1] |= r[1:]
            g[:, 1:] |= r[:, :-1]
            g[:, :-1] |= r[:, 1:]
            r = g
        return r & ~m

    y = luma(img.astype(np.float64))
    inside, around = float(y[mask].mean()), float(y[ring(mask)].mean())
    ys, xs = np.nonzero(mask)
    sub, m = y[ys.min():ys.max() + 1, xs.min():xs.max() + 1], mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    gx, gy = np.abs(np.diff(sub, axis=1)), np.abs(np.diff(sub, axis=0))
    edge = float((gx[m[:, 1:] & m[:, :-1]]).mean() + (gy[m[1:, :] & m[:-1, :]]).mean()) / 2
    return (inside - around) / max(1.0, around), edge


def room(game: Any, scene: str) -> dict[str, Any]:
    from engine.hd2d.dof import SUBTLE  # noqa: PLC0415
    from engine.hd2d.haze import CHARACTER_MARGIN, Haze, light_of, linear, shown  # noqa: PLC0415
    from engine.hd2d.post import Post  # noqa: PLC0415

    np = _np()
    hd = settle(game, scene)
    base = hd.settings
    r: dict[str, Any] = {"scene": scene}
    off = picture(game, hd)
    world = bytes(hd.draw(read=True))
    r["off"] = {"stage": hd.last_stage, "made": hd._composite is not None, "draw_calls": hd.draw_calls}
    hd.settings = dataclasses.replace(base, haze=Haze("daytime", strength=0.0))
    zero = picture(game, hd)
    r["strength_zero"] = {"same": bool(np.array_equal(zero, off)), "stage": hd.last_stage,
                          "made": hd._composite is not None}
    masks = []
    w, h = game.window.get_framebuffer_size()
    for sp in hd._sprites():
        game.window.use()
        m = np.frombuffer(hd.draw(solid=sp, read=True), dtype=np.uint8).reshape(h, w, 3)[..., 0] > 128
        if m.sum() >= 40:
            masks.append(m)
    base_read = [readability(off, m) for m in masks]
    r["presets"] = {}
    for name in PRESETS:
        hd.settings = dataclasses.replace(base, haze=Haze(name))
        img = picture(game, hd)
        match = depth_match(hd, off, img)
        updates = hd._composite.uniform_updates
        again = picture(game, hd)
        rd = [readability(img, m) for m in masks]
        focus, band = hd.dof_focus(hd.camera, True)
        st = hd.lighting.settings  # (the light the room is lit by, worked out here apart from the renderer)
        light = light_of(st.ambient, st.ambient_color, hd.lighting.sun, st.sun_intensity, st.sun_color)
        expect = [linear(c) for c in shown(Haze(name), light)]
        r["presets"][name] = {
            "light": [round(c, 4) for c in light],
            "lit_as_the_room": max(abs(a - b) for a, b in zip(hd._haze_values[2]["u_haze_color"], expect)) < 1e-6,
            "stage": hd.last_stage, "match": match, "repeat_same": bool(np.array_equal(img, again)),
            "uniform_updates_on_repeat": hd._composite.uniform_updates - updates, "draw_calls": hd.draw_calls,
            "world_read_unchanged": bytes(hd.draw(read=True)) == world,
            "weber_change_min": min((abs(a[0]) - abs(b[0]) for a, b in zip(rd, base_read)), default=None),
            "weber_ratio_min": min((abs(a[0]) / max(1e-6, abs(b[0])) for a, b in zip(rd, base_read)
                                    if abs(b[0]) > 0.02), default=None),
            "edge_ratio_min": min((a[1] / max(1e-6, b[1]) for a, b in zip(rd, base_read)), default=None),
            "onset_beyond_character": (hd.followed() is None
                                       or hd.last_haze["onset"] >= focus + band + CHARACTER_MARGIN - 1e-6),
            "clipped_increase": round(float((img >= 254).any(axis=2).mean() - (off >= 254).any(axis=2).mean()) * 100, 3)}
    # a start of 0: the renderer still keeps the haze off the followed character's depth (and characters readable)
    hd.settings = dataclasses.replace(base, haze=Haze("evening", start=0.0))
    img = picture(game, hd)
    focus, band = hd.dof_focus(hd.camera, True)
    rd = [readability(img, m) for m in masks]
    r["start_zero"] = {"followed": hd.followed() is not None, "onset": round(hd.last_haze["onset"] - focus, 4),
                       "band": round(band, 4), "match": depth_match(hd, off, img)["err_p99"],
                       "player_weber_ratio": None if not rd else round(abs(rd[0][0]) / max(1e-6, abs(base_read[0][0])),
                                                                      4)}
    # with the colour grade, then with the depth of field too (forced on any driver)
    hd.settings = dataclasses.replace(base, post=Post("golden_hour"))
    graded = picture(game, hd)
    hd.settings = dataclasses.replace(base, post=Post("golden_hour"), haze=Haze("evening"))
    both = picture(game, hd)
    near = metres(depth_of(hd), hd.camera.ortho) <= hd.last_haze["onset"]
    r["with_grade"] = {"stage": hd.last_stage, "near_same_as_grade": bool(np.array_equal(graded[near], both[near])),
                       "far_changed": bool((np.abs(both.astype(int) - graded.astype(int)).max(axis=2)[~near] > 0).any())}
    hd.settings = dataclasses.replace(base, depth_of_field=SUBTLE, haze=Haze("evening"))
    hd.dof_allow_software = True
    picture(game, hd)
    r["with_dof"] = {"stage": hd.last_stage, "chain_allocations": hd._composite.chain_allocations,
                     "world_read_unchanged": bytes(hd.draw(read=True)) == world}
    hd.dof_allow_software = False
    hd.settings = base
    r["off_again_same"] = bool(np.array_equal(picture(game, hd), off))
    return r


def night(game: Any, project: Path, scene: str) -> dict[str, Any]:
    """The same room under Studio's night sun (``project_ops.set_hd2d_sun(preset="night")``, a copy of the scene): the
    same haze lit by the night is dim, and still each pixel's haze matches its depth."""
    from engine import project_ops as ops  # noqa: PLC0415
    from engine.hd2d.haze import Haze, light_of, linear, shown  # noqa: PLC0415

    def lit(hd: Any) -> tuple[list[float], list[float]]:
        st = hd.lighting.settings
        light = light_of(st.ambient, st.ambient_color, hd.lighting.sun, st.sun_intensity, st.sun_color)
        return [round(c, 4) for c in light], [round(c, 4) for c in shown(Haze("daytime"), light)]

    day_hd = settle(game, scene)
    _day_light, day_shown = lit(day_hd)
    doc = json.loads((project / scene).read_text(encoding="utf-8"))
    night_scene = str(Path(scene).with_name("haze_night.json").as_posix())
    (project / night_scene).write_bytes(json.dumps(ops.set_hd2d_sun(doc, preset="night"), indent=2).encode("utf-8"))
    hd = settle(game, night_scene)
    base = hd.settings
    try:
        off = picture(game, hd)
        hd.settings = dataclasses.replace(base, haze=Haze("daytime"))
        img = picture(game, hd)
        light, now = lit(hd)
        st = hd.lighting.settings
        exact = shown(Haze("daytime"), light_of(st.ambient, st.ambient_color, hd.lighting.sun, st.sun_intensity,
                                                st.sun_color))
        expect = [linear(c) for c in exact]
        return {"light": light, "shown": now, "day_shown": day_shown, "match": depth_match(hd, off, img),
                "lit_as_the_room": max(abs(a - b) for a, b in zip(hd._haze_values[2]["u_haze_color"], expect)) < 1e-6}
    finally:
        hd.settings = base


def walking(game: Any, scene: str) -> dict[str, Any]:
    """The player walks; every few frames the picture is checked against its depth, and the onset's place relative to
    the focus (which follows the player) is recorded: it must not drift."""
    from engine.hd2d.haze import Haze  # noqa: PLC0415

    hd = settle(game, scene)
    base = hd.settings
    frames = []
    key = game.arcade.key
    try:
        for step, k in enumerate((key.RIGHT, key.RIGHT, key.UP, key.UP, key.LEFT)):
            game.hold(k, 12)
            hd.settings = base
            off = picture(game, hd)
            hd.settings = dataclasses.replace(base, haze=Haze("daytime"))
            img = picture(game, hd)
            match = depth_match(hd, off, img)
            frames.append({"step": step, "target": [round(v, 3) for v in hd.camera.target],
                           "onset_minus_focus": round(hd.last_haze["onset"] - hd.last_haze["focus"], 6),
                           "err_p99": match["err_p99"], "near_same": match["near_same"]})
    finally:
        hd.settings = base
    return {"frames": frames, "moved": len({tuple(f["target"]) for f in frames}),
            "onset_offsets": sorted({f["onset_minus_focus"] for f in frames})}


def flat_camera(game: Any, scene: str) -> dict[str, Any]:
    from engine.hd2d.haze import Haze  # noqa: PLC0415

    hd = settle(game, scene)
    base = hd.settings
    hd.camera.ortho = True
    try:
        off = picture(game, hd)
        hd.settings = dataclasses.replace(base, haze=Haze("evening", start=0.0, falloff=6.0))
        img = picture(game, hd)
        return depth_match(hd, off, img)
    finally:
        hd.camera.ortho = False
        hd.settings = base


def known_texels(game: Any, scene: str) -> dict[str, Any]:
    """The haze's maths on known texels: a 4x4 colour target and a depth cleared to a known value, drawn by the real
    composite with known haze values (no grade)."""
    from engine.hd2d.dof import FAR, NEAR  # noqa: PLC0415

    hd = settle(game, scene)
    ctx = hd.ctx
    comp = hd._final_composite()
    colour = (0.2, 0.4, 0.8)  # linear

    def depth_for(metres_away: float) -> float:  # the perspective depth buffer value of a point that far
        return (FAR - NEAR * FAR / metres_away) / (FAR - NEAR)

    def run(texel: Sequence[int], away: float | None, strength: float, onset: float, falloff: float) -> list[int]:
        src = ctx.texture((4, 4), components=4, data=bytes(texel) * 16)
        depth = ctx.depth_texture((4, 4))
        depth.compare_func = None
        holder = ctx.framebuffer(color_attachments=[ctx.texture((4, 4), components=4)], depth_attachment=depth)
        dst = ctx.texture((4, 4), components=4)
        fbo = ctx.framebuffer(color_attachments=[dst])
        try:
            holder.use()
            holder.clear(color=(0, 0, 0, 0), depth=1.0 if away is None else depth_for(away))  # (None: nothing drawn)
            fbo.use()
            comp.configure(None, {"u_haze": strength, "u_haze_color": colour, "u_haze_falloff": falloff})
            comp.frame(onset, False)
            with ctx.enabled_only():
                comp.render(hd._blit, src, depth)
            return list(fbo.read(components=4)[:4])
        finally:
            comp.configure(None)
            game.window.use()
            for o in (fbo, dst, src, holder, depth):
                o.delete()

    def model(texel: Sequence[int], away: float | None, strength: float, onset: float, falloff: float) -> list[int]:
        x = 0.0 if away is None else max(0.0, away - onset) / falloff
        a = strength * (1.0 - math.exp(-3.0 * x * x))
        out = []
        for c8, h in zip(texel[:3], colour):
            c = c8 / 255.0
            v = c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
            v = v + (h - v) * a
            e = v * 12.92 if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055
            out.append(round(e * 255))
        return [*out, texel[3]]

    def graded(texel: Sequence[int], haze: dict[str, Any] | None, away: float) -> list[int]:
        from engine.hd2d.post import Post  # noqa: PLC0415

        src = ctx.texture((4, 4), components=4, data=bytes(texel) * 16)
        depth = ctx.depth_texture((4, 4))
        depth.compare_func = None
        holder = ctx.framebuffer(color_attachments=[ctx.texture((4, 4), components=4)], depth_attachment=depth)
        dst = ctx.texture((4, 4), components=4)
        fbo = ctx.framebuffer(color_attachments=[dst])
        try:
            holder.use()
            holder.clear(color=(0, 0, 0, 0), depth=depth_for(away))
            fbo.use()
            comp.configure(Post("golden_hour", 1.0, 0.0), haze)
            comp.frame(30.0, False)
            with ctx.enabled_only():
                comp.render(hd._blit, src, depth)
            return list(fbo.read(components=4)[:4])
        finally:
            comp.configure(None)
            game.window.use()
            for o in (fbo, dst, src, holder, depth):
                o.delete()

    haze_u = {"u_haze": 0.5, "u_haze_color": colour, "u_haze_falloff": 10.0}
    hazed_first = run((90, 60, 30, 200), 80.0, 0.5, 30.0, 10.0)
    order = {"both": graded((90, 60, 30, 200), haze_u, 80.0),
             "haze_then_grade": graded(hazed_first, None, 80.0),
             "grade_then_haze": model(graded((90, 60, 30, 200), None, 80.0), 80.0, 0.5, 30.0, 10.0)}
    cases = {"near": ((37, 180, 222, 9), 20.0, 0.5, 30.0, 10.0), "at_onset": ((37, 180, 222, 9), 30.0, 0.5, 30.0, 10.0),
             "mid": ((37, 180, 222, 9), 36.0, 0.5, 30.0, 10.0), "far": ((90, 60, 30, 200), 80.0, 0.5, 30.0, 10.0),
             "distant": ((90, 60, 30, 255), 499.0, 0.3, 30.0, 10.0),
             "backdrop": ((18, 14, 11, 255), None, 0.5, 0.0, 1.0)}
    return {**{k: {"got": run(*v), "model": model(*v)} for k, v in cases.items()}, "order": order}


def hud(game: Any, scene: str) -> dict[str, Any]:
    """The window as the game draws it (world, then HUD), with and without a strong haze: the HUD is drawn after it.

    Where the HUD is fully opaque (the same pixel drawn over pure black and over pure white: no world can show through
    it), its pixels are the same bytes with and without the haze, and the same as the HUD drawn alone. Where it is
    translucent (the hint's dark box, text edges), the window is the HUD composited over the world it covers: its
    coverage, recovered from the black and white frames, laid over the hazed world gives the hazed window (within
    8-bit rounding). A haze applied after the HUD would change both. (A mask from "the window equals the HUD alone over
    black" also takes in nearly-opaque edge pixels that only round alike over that world: CI's Linux fonts, #500.)"""
    from engine.hd2d.haze import Haze  # noqa: PLC0415

    np = _np()
    hd = settle(game, scene)
    base = hd.settings
    strong = dataclasses.replace(base, haze=Haze("evening", strength=0.5, start=0.0, falloff=1.0))
    w, h = game.window.get_framebuffer_size()

    def window() -> Any:
        return np.asarray(game.draw().convert("RGB")).astype(int)

    def world_under() -> Any:  # the world as it lands in the window before the HUD (the same draw on_draw makes)
        game.window.use()
        return np.flipud(np.frombuffer(hd.draw(read_final=True), dtype=np.uint8).reshape(h, w, 3)).astype(int)

    def hud_over(colour: tuple[int, int, int, int]) -> Any:  # the HUD alone, drawn over one flat colour
        kept = hd.draw
        hd.draw = lambda *a, **k: game.window.ctx.active_framebuffer.clear(color=colour)
        try:
            return window()
        finally:
            hd.draw = kept

    hd.settings = base
    plain, world = window(), world_under()
    hd.settings = strong
    hazed, world_hazed = window(), world_under()
    hd.settings = base
    black, white = hud_over((0, 0, 0, 255)), hud_over((255, 255, 255, 255))
    game.window.use()
    drawn = (black.max(axis=2) > 0) | (white.min(axis=2) < 255)  # the HUD covers these pixels at all
    opaque = drawn & (np.abs(white - black).max(axis=2) == 0)
    clear = (white - black) / 255.0  # per channel: how much of what is behind shows through
    translucent = drawn & ~opaque

    def worst(img: Any, behind: Any) -> int:
        predicted = np.rint(black + clear * behind)
        return int(np.abs(img - predicted).max(axis=2)[translucent].max()) if translucent.any() else 0

    return {"hud_pixels": int(opaque.sum()), "translucent_pixels": int(translucent.sum()),
            "opaque_same": bool(np.array_equal(plain[opaque], hazed[opaque])
                                and np.array_equal(plain[opaque], black[opaque])),
            "opaque_changed": int((np.abs(hazed - plain).max(axis=2)[opaque] > 0).sum()),
            "over_world_error": worst(plain, world), "over_hazed_world_error": worst(hazed, world_hazed),
            "behind_changed": int((np.abs(world_hazed - world).max(axis=2)[translucent] > 0).sum()),
            "world_changed": bool((np.abs(hazed - plain).max(axis=2)[~drawn] > 0).any())}


def refused(game: Any, scene: str) -> dict[str, Any]:
    """A driver refusing the composite's program: the original picture, the reason kept, nothing pretended."""
    import engine.hd2d.renderer as R  # noqa: PLC0415
    from engine.hd2d.haze import Haze  # noqa: PLC0415

    np = _np()
    hd = settle(game, scene)
    base = hd.settings
    off = picture(game, hd)
    kept = R.FinalComposite

    class Refused:
        def __init__(self, *a: Any, **k: Any) -> None:
            raise R._gpu_refused()[0]("program refused (simulated)")

    setattr(R, "FinalComposite", Refused)  # noqa: B010  # (the renderer's own name for it, swapped for this check)
    try:
        if hd._composite is not None:
            hd._composite.release()
            hd._composite = None
        hd.settings = dataclasses.replace(base, haze=Haze("evening"))
        img = picture(game, hd)
        return {"stage": hd.last_stage, "same": bool(np.array_equal(img, off)), "reason": hd.composite_unavailable}
    finally:
        setattr(R, "FinalComposite", kept)  # noqa: B010
        hd.composite_unavailable = None
        hd.settings = base


def study(out: Path, *, size: tuple[int, int] = (960, 540)) -> dict[str, Any]:
    import hd2d_lamp_glow_demo as glow
    from hd2d_demo import HiddenGame

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
        report["hud"] = hud(game, rooms["village"])  # (first: the room's hint is on screen)
        report["night"] = night(game, project, rooms["village"])
        report["walking"] = walking(game, rooms["village"])
        report["flat_camera"] = flat_camera(game, rooms["village"])
        report["texels"] = known_texels(game, rooms["village"])
        report["refused"] = refused(game, rooms["village"])
    finally:
        game.close()
    return report


def main() -> None:
    out = Path(sys.argv[1])
    found = study(out)
    (out / "report.json").write_text(json.dumps(found, indent=1, default=str), encoding="utf-8")
    print(json.dumps(found, indent=1, default=str))


if __name__ == "__main__":
    main()
