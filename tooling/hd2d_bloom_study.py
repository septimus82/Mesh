"""M17-L4-4: an HD-2D room's bloom (engine.hd2d.bloom), checked in real frames (hidden window).

    py -3.13 tooling/hd2d_bloom_study.py OUT

Rooms: the template village at night, its two lamp posts lit (hd2d_lamp_glow_demo), and Milestone 23B's woodland
clearing at night (a campfire's flames and embers, a torch: tooling/m23b_fire_study). In each, the picture the renderer
makes (``draw(read_final=True)``), the world's emission attachment and the bloom's own levels, read back:

- no bloom block, and a preset at strength 0: the original picture, byte for byte, nothing of bloom made;
- each preset: **the emission is the emitters'**: non-zero only on the lamp heads (the village), every other surface
  zero; the prefilter's level is the CPU's threshold, knee and cap of that emission, averaged over the texels each of
  its pixels covers; the glow's total light is the light that passed (no gain, no loss); the picture changes only
  around emitters, and is its original bytes far from every one;
- what is merely bright (the village by day, its lamps off: sunlit walls, paths, sky): no emission, the picture exactly;
- an emitter behind a character: its emission hidden where the character covers it (the depth test, as its colour);
- the camera moving: the glow's light stays the light that passed in every frame; repeated frames are identical;
- the picture's size: the same glow, as a share of the picture, at 960x540 and 1920x1080;
- with the haze (an emitter in it glows as dimly as it shows), the depth of field (bloom after it, from the sharp
  emission) and the grade (bloom before it): known texels through the real composite give each order's maths;
- the HUD (drawn after the renderer): its opaque pixels are the same bytes under a strong glow;
- a driver refusing bloom (its program, or the emission framebuffer): bloom off, the reason kept, the haze and grade
  still drawn; turned off, every GPU object of it freed; a new picture size remakes its targets, nothing leaked.
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
PRESETS = ("subtle", "warm")
FAR_PX = 0.4  # share of the picture's height: farther than this from every emitter, the picture is its original bytes


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
    """The picture as drawn (rows bottom-up, as the GPU's)."""
    np = _np()
    w, h = game.window.get_framebuffer_size()
    game.window.use()
    return np.frombuffer(hd.draw(read_final=True), dtype=np.uint8).reshape(h, w, 3).copy()


def floats(tex: Any, depth: bool = False) -> Any:
    """A texture read back as floats (rows bottom-up): RGB, or the depth."""
    from pyglet import gl  # noqa: PLC0415

    np = _np()
    w, h = tex.size
    n = 1 if depth else 3
    buf = (ctypes.c_float * (w * h * n))()
    gl.glActiveTexture(gl.GL_TEXTURE0)
    gl.glBindTexture(gl.GL_TEXTURE_2D, tex.glo.value if hasattr(tex.glo, "value") else tex.glo)
    gl.glGetTexImage(gl.GL_TEXTURE_2D, 0, gl.GL_DEPTH_COMPONENT if depth else gl.GL_RGB, gl.GL_FLOAT, buf)
    gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
    out = np.frombuffer(buf, dtype=np.float32).astype(np.float64)
    return out.reshape(h, w) if depth else out.reshape(h, w, 3)


def levels(hd: Any) -> tuple[Any, Any, Any]:
    """(emission, the prefilter's level, the glow) of the last frame, as floats."""
    b = hd._bloom
    return floats(b.emission), floats(b._chain[1][0][1]), floats(b._chain[2][0][1])


def prefiltered(emission: Any, base: tuple[int, int], threshold: float, haze: Any = None) -> Any:
    """The prefilter's level as the CPU computes it: each texel's threshold, knee and cap (and the haze at its depth:
    ``haze`` = (factor per texel)), averaged over exactly the texels each level pixel covers."""
    from engine.hd2d.bloom import KNEE, MAX_SOURCE, MIN_KNEE  # noqa: PLC0415

    np = _np()
    e = emission.copy()
    y = luma(e)
    cap = np.where(y > MAX_SOURCE, MAX_SOURCE / np.maximum(y, 1e-9), 1.0)
    e *= cap[..., None]
    y = np.minimum(y, MAX_SOURCE)
    if haze is not None:
        e *= haze[..., None]
        y = y * haze
    knee = max(threshold * KNEE, MIN_KNEE)
    soft = np.clip(y - threshold + knee, 0.0, 2.0 * knee) ** 2 / (4.0 * knee)
    w = np.where(y > 0, np.maximum(soft, y - threshold) / np.maximum(y, 1e-5), 0.0)
    e *= w[..., None]
    h0, w0 = e.shape[:2]
    bw, bh = base

    def weights(n: int, m: int) -> Any:  # (m, n): how much of each source texel each target pixel covers
        s = n / m
        out = np.zeros((m, n))
        for i in range(m):
            lo, hi = i * s, (i + 1) * s
            for j in range(int(math.floor(lo)), min(n, int(math.ceil(hi)))):
                out[i, j] = min(hi, j + 1) - max(lo, j)
        return out / s

    wy, wx = weights(h0, bh), weights(w0, bw)
    rows = (wy @ e.reshape(h0, w0 * 3)).reshape(bh, w0, 3)  # (separable: rows, then columns)
    return np.einsum("ikc,lk->ilc", rows, wx, optimize=True)


def near(mask: Any, r: float) -> Any:
    """Pixels with a True pixel of ``mask`` within ``r`` px across and up (a square: an integral image)."""
    np = _np()
    k = int(math.ceil(r))
    s = np.pad(mask.astype(np.int64), ((k + 1, k), (k + 1, k))).cumsum(0).cumsum(1)
    h, w = mask.shape
    y0, x0 = np.arange(h), np.arange(w)
    lo_y, hi_y, lo_x, hi_x = y0[:, None], y0[:, None] + 2 * k + 1, x0[None, :], x0[None, :] + 2 * k + 1
    a = s[hi_y, hi_x] - s[lo_y, hi_x] - s[hi_y, lo_x] + s[lo_y, lo_x]
    return a > 0


def with_bloom(base: Any, preset: str | None, **values: Any) -> Any:
    from engine.hd2d.bloom import Bloom  # noqa: PLC0415

    return dataclasses.replace(base, bloom=None if preset is None else Bloom(preset, **values))


def room(game: Any, scene: str, *, heads: bool) -> dict[str, Any]:
    """Off, strength 0, each preset and a strong glow, as above. ``heads``: the room's only emitters are lamp heads."""
    import hd2d_lamp_glow_demo as glow  # noqa: PLC0415

    np = _np()
    hd = settle(game, scene)
    base = hd.settings
    out: dict[str, Any] = {}
    hd.settings = with_bloom(base, None)
    hd._final_composite()  # (the shared composite, made for the haze or the grade as for bloom, kept until release)
    off = picture(game, hd)
    objects = len(hd.gl_objects())
    h = off.shape[0]
    out["off"] = {"stage": hd.last_stage, "made": hd._bloom is not None}
    hd.settings = with_bloom(base, "warm", strength=0.0)
    zero = picture(game, hd)
    out["zero"] = {"same": bool(np.array_equal(zero, off)), "stage": hd.last_stage, "made": hd._bloom is not None}
    boxes = glow.head_boxes(game) if heads else []
    for name, values in (("subtle", {}), ("warm", {}), ("strong", {"strength": 3.0, "threshold": 0.0, "spread": 0.8})):
        hd.settings = with_bloom(base, "warm" if name == "strong" else name, **values)
        img = picture(game, hd)
        emission, level, glow_ = levels(hd)
        v = hd.settings.bloom.values
        model = prefiltered(emission, level.shape[1::-1], v.threshold)
        lit = luma(emission) > 0
        inside = np.zeros_like(lit)
        for x0, y0, x1, y1 in boxes:  # (boxes' rows from the top; the emission's from the bottom)
            inside[max(0, h - y1):max(0, h - y0), max(0, x0):max(0, x1)] = True
        changed = np.abs(img.astype(int) - off.astype(int)).max(axis=2) > 0
        far = ~near(lit, FAR_PX * h)
        added = luma(lin(img) - lin(off))
        close = near(lit, 0.1 * h)
        out[name] = {
            "stage": hd.last_stage, "passes": (hd.last_bloom or {}).get("passes"),
            "emitting_px": int(lit.sum()), "emitting_outside_heads": int((lit & ~inside).sum()) if heads else None,
            "emission_max": float(luma(emission).max()),
            "prefilter_error": float(np.abs(level - model).max()), "prefilter_max": float(model.max()),
            "energy_passed": float(luma(level).sum()), "energy_glow": float(luma(glow_).sum()),
            "changed": int(changed.sum()), "changed_far": int((changed & far).sum()), "far_px": int(far.sum()),
            "added_near_share": float(added[close].sum() / max(added.sum(), 1e-9)),
            "max_change": int(np.abs(img.astype(int) - off.astype(int)).max()),
            "repeat_same": bool(np.array_equal(picture(game, hd), img)),
        }
    hd.settings = with_bloom(base, None)
    after = picture(game, hd)
    out["off_again"] = {"same": bool(np.array_equal(after, off)), "made": hd._bloom is not None,
                        "objects_more": len(hd.gl_objects()) - objects}
    hd.settings = base
    return out


def capped(game: Any, scene: str) -> dict[str, Any]:
    """Lamps twelve times as strong: their lamp heads emit past ``MAX_SOURCE``; the prefilter caps each such texel (the
    CPU model caps it too), so one strong light can't flood the picture."""
    from engine.hd2d.bloom import MAX_SOURCE  # noqa: PLC0415

    hd = settle(game, scene)
    base = hd.settings
    hd.settings = with_bloom(base, "warm")
    picture(game, hd)
    emission, level, _g = levels(hd)
    model = prefiltered(emission, level.shape[1::-1], hd.settings.bloom.values.threshold)
    hd.settings = base
    return {"emission_max": float(luma(emission).max()), "cap": MAX_SOURCE, "prefilter_max": float(model.max()),
            "prefilter_luma_max": float(luma(model).max()), "level_luma_max": float(luma(level).max()),
            "prefilter_error": float(_np().abs(level - model).max())}


def spreads(game: Any, scene: str) -> dict[str, Any]:
    """The same glow (strength, threshold) at spread 0.2 and 0.9: the wider spread puts more of its light farther from
    the emitters, holding the same light."""
    hd = settle(game, scene)
    base = hd.settings
    out: dict[str, Any] = {}
    for s in (0.2, 0.9):
        hd.settings = with_bloom(base, "warm", strength=2.0, threshold=0.1, spread=s)
        picture(game, hd)
        _e, level, glow_ = levels(hd)
        g = luma(glow_)
        close = near(luma(level) > 0, 6)  # (level pixels: 6 of them is 1/60 of the picture's height)
        out[str(s)] = {"far_share": float(g[~close].sum() / max(g.sum(), 1e-9)),
                       "glow_over_passed": float(g.sum() / max(luma(level).sum(), 1e-9))}
    hd.settings = base
    return out


def merely_bright(game: Any, scene: str) -> dict[str, Any]:
    """A room where nothing emits under a strong glow: no emission anywhere and the picture exactly. The village by day
    with its lamps off (sunlit walls, paths: don't glow); the cottage interior (its surroundings are the backdrop, where
    nothing is drawn: no emission there either, whatever the sky's colour)."""
    np = _np()
    hd = settle(game, scene)
    base = hd.settings
    hd.settings = with_bloom(base, None)
    off = picture(game, hd)
    hd.settings = with_bloom(base, "warm", strength=3.0, threshold=0.0, spread=1.0)
    on = picture(game, hd)
    emission = floats(hd._bloom.emission)
    backdrop = int((floats(hd._fbo_parts[1], depth=True) >= 1.0).sum())
    hd.settings = base
    return {"same": bool(np.array_equal(on, off)), "emission_sum": float(emission.sum()), "stage": hd.last_stage,
            "bright_px": int((luma(off.astype(float) / 255.0) > 0.7).sum()), "backdrop_px": backdrop}


def occluded(game: Any, scene: str) -> dict[str, Any]:
    """The player, made three times as tall (a lamp head stands higher than a character could cover from this camera),
    stood 2 m in front of a lamp head (the camera held still): where the player covers the head, no emission; with the
    player stood aside, those pixels emit (so the check means something). The player is drawn after the lamp post."""
    import copy  # noqa: PLC0415

    from engine.hd2d.lighting import lamp_head  # noqa: PLC0415
    from engine.hd2d.settings import PIXELS_PER_METRE as PPM  # noqa: PLC0415

    np = _np()
    hd = settle(game, scene)
    base = hd.settings
    hd.settings = with_bloom(base, "warm")
    cam = copy.deepcopy(hd.camera)
    p = game.player()
    lamp = next(li for li in hd.settings.lights if lamp_head((li.x / PPM, li.y / PPM, li.elevation / PPM),
                                                             hd.settings.structures, hd.models) is not None)
    head = (lamp.x / PPM, lamp.y / PPM, lamp.elevation / PPM)
    eye = cam.eye()
    toward = (eye[0] - head[0], eye[1] - head[1])
    n = math.hypot(*toward) or 1.0
    spot = (head[0] + toward[0] / n * 2.0, head[1] + toward[1] / n * 2.0)
    w, h = game.window.get_framebuffer_size()
    kept_scale = p.scale
    p.scale = (kept_scale[0] * 3, kept_scale[1] * 3)

    def emitting() -> Any:
        game.window.use()
        hd.draw(camera=cam, read_final=True)
        return luma(floats(hd._bloom.emission)) > 0

    p.center_x, p.bottom = spot[0] * PPM, spot[1] * PPM
    hd.draw(camera=cam)  # (this frame's sprites: the player where it now stands)
    covered = np.frombuffer(hd.draw(solid=p, read=True, camera=cam), dtype=np.uint8).reshape(h, w, 3)
    mask = (covered[..., 0] > 200) & (covered[..., 1] < 60)
    in_front = emitting()
    p.center_x += 6 * PPM  # stood aside
    aside = emitting()
    p.scale = kept_scale
    hd.settings = base
    return {"player_px": int(mask.sum()), "emitting_under_player_aside": int((aside & mask).sum()),
            "emitting_under_player": int((in_front & mask).sum())}


def moving(game: Any, scene: str, frames: int = 24) -> dict[str, Any]:
    """The player walks (the camera follows): every frame's glow holds the light that passed its threshold."""
    np = _np()
    hd = settle(game, scene)
    base = hd.settings
    hd.settings = with_bloom(base, "warm")
    p = game.player()
    ratios, passed = [], []
    for _ in range(frames):
        p.center_x += 1.7  # px a frame: the camera moves by fractions of a pixel
        p.bottom += 0.9
        game.step(1)
        picture(game, hd)
        _e, level, glow_ = levels(hd)
        passed.append(float(luma(level).sum()))
        ratios.append(float(luma(glow_).sum() / max(luma(level).sum(), 1e-9)))
    hd.settings = base
    spread = float(np.std(passed) / max(np.mean(passed), 1e-9))
    return {"glow_over_passed_min": min(ratios), "glow_over_passed_max": max(ratios), "passed_variation": spread}


def sizes(game: Any, scene: str) -> dict[str, Any]:
    """The same view drawn at 960x540 and 1920x1080 (offscreen, the renderer's viewport): the glow is the same share of
    the picture (the chain is a fixed share of it)."""
    np = _np()
    hd = settle(game, scene)
    base = hd.settings
    hd.settings = with_bloom(base, "warm")
    ctx = game.window.ctx
    out: dict[str, Any] = {}
    glows = {}
    for w, h in ((960, 540), (1920, 1080)):
        tex = ctx.texture((w, h), components=4)
        fbo = ctx.framebuffer(color_attachments=[tex])
        try:
            fbo.use()
            hd.draw(viewport=(0, 0, w, h), camera=hd.camera)
            _e, _level, g = levels(hd)
            glows[h] = luma(g)
            out[f"{w}x{h}"] = {"base": list(g.shape[1::-1]), "glow": float(luma(g).sum())}
        finally:
            game.window.use()
            fbo.delete()
            tex.delete()
    a, b = glows[540].ravel(), glows[1080].ravel()
    out["correlation"] = float(np.corrcoef(a, b)[0, 1]) if a.std() > 0 and b.std() > 0 else 0.0
    out["energy_ratio"] = float(b.sum() / max(a.sum(), 1e-9))
    hd.settings = base
    return out


def with_haze(game: Any, scene: str) -> dict[str, Any]:
    """Under a strong haze, the prefilter dims each emission texel by the haze at its own depth (CPU model)."""
    from engine.hd2d.haze import Haze  # noqa: PLC0415

    np = _np()
    hd = settle(game, scene)
    base = hd.settings
    hd.settings = dataclasses.replace(with_bloom(base, "warm"), haze=Haze("evening", strength=0.5, start=0.0,
                                                                         falloff=2.0))
    picture(game, hd)
    emission, level, _g = levels(hd)
    from engine.hd2d.dof import FAR, NEAR  # noqa: PLC0415

    d = floats(hd._fbo_parts[1], depth=True)
    m = NEAR * FAR / (FAR - d * (FAR - NEAR))
    h = hd.last_haze
    x = np.maximum(m - h["onset"], 0.0) / h["falloff"]
    factor = np.where(d < 1.0, 1.0 - h["strength"] * (1.0 - np.exp(-3.0 * x * x)), 1.0)
    model = prefiltered(emission, level.shape[1::-1], hd.settings.bloom.values.threshold, factor)
    plain = prefiltered(emission, level.shape[1::-1], hd.settings.bloom.values.threshold)
    hd.settings = base
    return {"error": float(np.abs(level - model).max()), "max": float(model.max()),
            "dimmed_by": float(1.0 - luma(model).sum() / max(luma(plain).sum(), 1e-9))}


def with_dof(game: Any, scene: str) -> dict[str, Any]:
    """With the depth of field: the composite after it (its chain), the glow added; far from emitters the DoF picture's
    own bytes."""
    np = _np()
    from engine.hd2d.dof import SUBTLE  # noqa: PLC0415

    hd = settle(game, scene)
    base = hd.settings
    hd.dof_allow_software = True
    try:
        hd.settings = dataclasses.replace(base, depth_of_field=SUBTLE, bloom=None)
        dof = picture(game, hd)
        dof_stage = hd.last_stage
        hd.settings = dataclasses.replace(with_bloom(base, "warm"), depth_of_field=SUBTLE)
        both = picture(game, hd)
        lit = luma(floats(hd._bloom.emission)) > 0
        far = ~near(lit, FAR_PX * both.shape[0])
        changed = np.abs(both.astype(int) - dof.astype(int)).max(axis=2) > 0
        return {"dof_stage": dof_stage, "stage": hd.last_stage, "changed": int(changed.sum()),
                "changed_far": int((changed & far).sum())}
    finally:
        hd.dof_allow_software = False
        hd.settings = base


def known_texels(game: Any, scene: str) -> dict[str, Any]:
    """The composite's maths on known texels: a 4x4 colour, a depth, a glow of a known value, through the real program:
    no glow is the texel exactly; the glow is added in linear light; after the haze; before the grade."""
    from engine.hd2d.dof import FAR, NEAR  # noqa: PLC0415
    from engine.hd2d.post import Post  # noqa: PLC0415

    hd = settle(game, scene)
    ctx = hd.ctx
    comp = hd._final_composite()
    haze_colour = (0.2, 0.4, 0.8)

    def depth_for(metres_away: float) -> float:
        return (FAR - NEAR * FAR / metres_away) / (FAR - NEAR)

    def run(texel: Sequence[int], glow: Sequence[float], strength: float, *, haze: dict[str, Any] | None = None,
            post: Any = None, away: float = 60.0) -> list[int]:
        import array  # noqa: PLC0415

        src = ctx.texture((4, 4), components=4, data=bytes(texel) * 16)
        g = ctx.texture((4, 4), components=3, dtype="f4", data=array.array("f", list(glow) * 16).tobytes())
        depth = ctx.depth_texture((4, 4))
        depth.compare_func = None
        holder = ctx.framebuffer(color_attachments=[ctx.texture((4, 4), components=4)], depth_attachment=depth)
        dst = ctx.texture((4, 4), components=4)
        fbo = ctx.framebuffer(color_attachments=[dst])
        try:
            holder.use()
            holder.clear(color=(0, 0, 0, 0), depth=depth_for(away))
            fbo.use()
            comp.configure(post, haze, strength)
            comp.frame(30.0, False)
            with ctx.enabled_only():
                comp.render(hd._blit, src, depth, g)
            return list(fbo.read(components=4)[:4])
        finally:
            comp.configure(None)
            game.window.use()
            for o in (fbo, dst, src, g, holder, depth):
                o.delete()

    def enc(v: float) -> int:
        v = min(1.0, max(0.0, v))
        return round((v * 12.92 if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055) * 255)

    def dec(c8: int) -> float:
        c = c8 / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    def model(texel: Sequence[int], glow: Sequence[float], strength: float, a: float = 0.0) -> list[int]:
        return [enc(dec(c) + (h - dec(c)) * a + g * strength) for c, g, h in zip(texel[:3], glow, haze_colour)] \
            + [texel[3]]

    texel = (60, 50, 40, 200)
    glow = (0.08, 0.05, 0.02)
    haze_u = {"u_haze": 0.5, "u_haze_color": haze_colour, "u_haze_falloff": 10.0}
    a = 0.5 * (1.0 - math.exp(-3.0 * ((60.0 - 30.0) / 10.0) ** 2))
    golden = Post("golden_hour", 1.0, 0.0)
    graded_sum = run(model(texel, glow, 2.0), (0.0, 0.0, 0.0), 0.0, post=golden)  # grade of (texel + glow)
    out = {
        "none": {"got": run(texel, (0.0, 0.0, 0.0), 2.0), "model": list(texel)},
        "added": {"got": run(texel, glow, 2.0), "model": model(texel, glow, 2.0)},
        "clipped": {"got": run((250, 240, 230, 255), (2.0, 2.0, 2.0), 3.0), "model": [255, 255, 255, 255]},
        "after_haze": {"got": run(texel, glow, 2.0, haze=haze_u), "model": model(texel, glow, 2.0, a)},
        "before_grade": {"got": run(texel, glow, 2.0, post=golden), "grade_of_sum": graded_sum,
                         "sum_of_grade": model(run(texel, (0.0, 0.0, 0.0), 0.0, post=golden), glow, 2.0)},
    }
    return out


def hud(game: Any, scene: str) -> dict[str, Any]:
    """The window as the game draws it (world, then HUD) with a strong glow: the HUD's opaque pixels (the same over
    pure black and pure white) are the same bytes with and without it."""
    np = _np()
    hd = settle(game, scene)
    base = hd.settings

    def window() -> Any:
        return np.asarray(game.draw().convert("RGB")).astype(int)

    def hud_over(colour: tuple[int, int, int, int]) -> Any:
        kept = hd.draw
        hd.draw = lambda *a, **k: game.window.ctx.active_framebuffer.clear(color=colour)
        try:
            return window()
        finally:
            hd.draw = kept

    hd.settings = with_bloom(base, None)
    plain = window()
    hd.settings = with_bloom(base, "warm", strength=3.0, threshold=0.0, spread=1.0)
    glowing = window()
    hd.settings = base
    black, white = hud_over((0, 0, 0, 255)), hud_over((255, 255, 255, 255))
    game.window.use()
    drawn = (black.max(axis=2) > 0) | (white.min(axis=2) < 255)
    opaque = drawn & (np.abs(white - black).max(axis=2) == 0)
    return {"hud_pixels": int(opaque.sum()),
            "opaque_same": bool(np.array_equal(plain[opaque], glowing[opaque])
                                and np.array_equal(plain[opaque], black[opaque])),
            "world_changed": bool((np.abs(glowing - plain).max(axis=2)[~drawn] > 0).any())}


def refused(game: Any, scene: str) -> dict[str, Any]:
    """A driver refusing bloom's program, then its framebuffer: bloom off, the reason kept; with the haze on too, the
    haze's picture exactly (the composite still runs); nothing of bloom left allocated."""
    import engine.hd2d.renderer as R  # noqa: PLC0415
    from engine.hd2d.bloom import BloomPass  # noqa: PLC0415
    from engine.hd2d.haze import Haze  # noqa: PLC0415

    np = _np()
    hd = settle(game, scene)
    base = hd.settings
    hazed = dataclasses.replace(base, haze=Haze("evening"))
    hd.settings = base
    off = picture(game, hd)
    hd.settings = hazed
    haze_only = picture(game, hd)
    out: dict[str, Any] = {}

    class Refused:
        def __init__(self, *a: Any, **k: Any) -> None:
            raise R._gpu_refused()[0]("program refused (simulated)")

    def no_framebuffer(self: Any, colour: Any, depth: Any) -> Any:
        raise ValueError("framebuffer incomplete (simulated)")

    for name in ("program", "framebuffer"):
        kept = R.BloomPass, BloomPass.world_target
        if name == "program":
            setattr(R, "BloomPass", Refused)  # noqa: B010  # (the renderer's own name for it, swapped for this check)
        else:
            setattr(BloomPass, "world_target", no_framebuffer)  # noqa: B010
        try:
            hd._free_bloom()
            hd.bloom_unavailable = None
            hd.settings = with_bloom(base, "warm")
            alone = picture(game, hd)
            hd.settings = with_bloom(hazed, "warm")
            with_haze_ = picture(game, hd)
            out[name] = {"alone_same": bool(np.array_equal(alone, off)),
                         "with_haze_same": bool(np.array_equal(with_haze_, haze_only)),
                         "stage": hd.last_stage, "reason": hd.bloom_unavailable, "made": hd._bloom is not None}
        finally:
            setattr(R, "BloomPass", kept[0])  # noqa: B010
            setattr(BloomPass, "world_target", kept[1])  # noqa: B010
            hd.bloom_unavailable = None
            hd.settings = base
    return out


def lifecycle(game: Any, scene: str) -> dict[str, Any]:
    """Made the first frame bloom is on; a new picture size remakes its targets (none leaked); off frees it all."""
    hd = settle(game, scene)
    base = hd.settings
    ctx = game.window.ctx
    hd.settings = with_bloom(base, None)
    hd._final_composite()  # (shared, as in ``room``)
    picture(game, hd)
    before = len(hd.gl_objects())
    hd.settings = with_bloom(base, "warm")
    picture(game, hd)
    on = len(hd.gl_objects())
    allocations = hd._bloom.allocations
    memory = hd._bloom.memory_bytes()
    tex = ctx.texture((800, 600), components=4)
    fbo = ctx.framebuffer(color_attachments=[tex])
    try:
        fbo.use()
        hd.draw(viewport=(0, 0, 800, 600), camera=hd.camera)
        resized = {"objects": len(hd.gl_objects()), "allocations": hd._bloom.allocations,
                   "emission": list(hd._bloom.emission.size)}
    finally:
        game.window.use()
        fbo.delete()
        tex.delete()
    picture(game, hd)
    hd.settings = with_bloom(base, None)
    picture(game, hd)
    after = len(hd.gl_objects())
    hd.settings = base
    return {"objects_off": before, "objects_on": on, "objects_after_off": after, "allocations_first": allocations,
            "memory_bytes": memory, "resized": resized, "made_after_off": hd._bloom is not None}


def study(out: Path, *, size: tuple[int, int] = (960, 540)) -> dict[str, Any]:
    import hd2d_lamp_glow_demo as glow
    import m23b_fire_study as fire
    from hd2d_demo import HiddenGame

    out.mkdir(parents=True, exist_ok=True)
    project = out / "game"
    rooms = glow.build(project)
    night = glow.village_variant(project, "bloom_night", lambda lights: lights)
    bright = glow.village_variant(project, "bloom_bright_night", lambda lights: glow._lamps(lights, intensity=12.0))
    day_dark = glow.village_variant(project, "bloom_lamps_off_noon", lambda lights: glow._lamps(lights, enabled=False))
    report: dict[str, Any] = {"size": list(size)}
    game = HiddenGame(project, size=size)
    game.window.audio.set_muted(True)
    try:
        report["gl"] = str(game.window.ctx.info.RENDERER)
        report["hud"] = hud(game, rooms["village"])  # (first: the room's hint is on screen; its lamp heads emit)
        report["village"] = room(game, night, heads=True)
        report["merely_bright"] = merely_bright(game, day_dark)
        report["backdrop"] = merely_bright(game, rooms["cottage"])
        report["capped"] = capped(game, bright)
        report["spreads"] = spreads(game, night)
        report["occluded"] = occluded(game, night)
        report["moving"] = moving(game, night)
        report["sizes"] = sizes(game, night)
        report["haze"] = with_haze(game, night)
        report["dof"] = with_dof(game, night)
        report["texels"] = known_texels(game, night)
        report["refused"] = refused(game, night)
        report["lifecycle"] = lifecycle(game, night)
    finally:
        game.close()
    clearing = fire.make_project(out, "clearing", night=True)
    game = HiddenGame(clearing, size=size)
    game.window.audio.set_muted(True)
    try:
        fire_room = room(game, fire.ROOM, heads=False)
        report["campfire"] = fire_room
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
