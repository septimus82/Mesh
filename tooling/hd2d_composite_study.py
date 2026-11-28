"""M17-L4-1: the HD-2D final composite, checked in real frames (hidden windows).

    py -3.13 tooling/hd2d_composite_study.py OUT

Rooms: the four of hd2d_lamp_glow_demo (the template village with its lamps' glowing heads (E2), Lakeside's cottage
and posts, #459's fixture room, the cottage interior) and an E1 emissive-swatches room. In each room, the picture the
renderer makes (``draw(read_final=True)``: what lands in the window) is compared:

- off (the blit, as every room is drawn) with the forced identity composite: the same bytes, the same draw calls,
  one more GL program and nothing else; repeated frames identical; the world before the composite (``read``)
  unchanged;
- the depth of field (Subtle) with and without the identity composite after it: the same bytes; on a software
  rasteriser the depth of field stays bypassed (and is forced once to check the chained path there too);
- picture sizes changing (offscreen targets of two sizes): the composite's one chain target remade, nothing piling up;
- room changes: the renderers' GL objects freed with them (live counts per kind, as the depth of field's check).

Mesh Studio (its own hidden window): the canvas (offset from the window's corner) drawn with Studio's camera, off and
identity, against the same camera drawn at the origin of an offscreen target of the canvas's size; Studio's lines
(grid, selection) off and identity; the game's camera path against Studio's for the same view.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(1, str(REPO / "tooling"))
SCENES = "packs/core_regions/scenes"
KINDS = ("texture", "framebuffer", "program", "buffer", "geometry")


def live(ctx: Any) -> dict[str, int]:
    """GL objects alive now, per kind (arcade's created - freed)."""
    return {k: getattr(ctx.stats, k)[0] - getattr(ctx.stats, k)[1] for k in KINDS}


def digest(data: Any) -> str:
    return hashlib.sha256(bytes(data)).hexdigest()[:16]


def settle(game: Any, scene: str) -> Any:
    game.load(scene)
    game.step(30)
    game.window.motion_time = 0.0
    if hasattr(game.window, "water_time"):
        game.window.water_time = 0.0
    return game.window.hd2d_renderer


def picture(hd: Any, **kw: Any) -> bytes:
    return bytes(hd.draw(read_final=True, **kw))


def room(game: Any, scene: str) -> dict[str, Any]:
    from engine.hd2d.dof import SUBTLE  # noqa: PLC0415

    hd = settle(game, scene)
    ctx = hd.ctx
    game.window.use()
    r: dict[str, Any] = {"scene": scene}
    hd.force_identity_composite = False
    world = bytes(hd.draw(read=True))
    off = picture(hd)
    r["off"] = {"digest": digest(off), "stage": hd.last_stage, "draw_calls": hd.draw_calls, "live": live(ctx),
                "repeat_same": picture(hd) == off, "blit_is_the_world": off == world,
                "composite_made": hd._composite is not None}
    hd.force_identity_composite = True
    ident = picture(hd)
    r["identity"] = {"same_as_off": ident == off, "stage": hd.last_stage, "draw_calls": hd.draw_calls,
                     "live": live(ctx), "repeat_same": picture(hd) == ident,
                     "world_read_unchanged": bytes(hd.draw(read=True)) == world}
    hd.force_identity_composite = False
    r["off_again_same"] = picture(hd) == off
    # alpha too (the window's read is RGB): off and identity into an offscreen RGBA8 target, every channel
    tex = ctx.texture((len(off) // 3 // game.window.get_framebuffer_size()[1], game.window.get_framebuffer_size()[1]),
                      components=4)
    fbo = ctx.framebuffer(color_attachments=[tex])
    try:
        fbo.use()
        hd.draw()
        rgba_off = bytes(fbo.read(components=4))
        hd.force_identity_composite = True
        hd.draw()
        rgba_id = bytes(fbo.read(components=4))
    finally:
        hd.force_identity_composite = False
        game.window.use()
        fbo.delete()
        tex.delete()
    r["rgba"] = {"identity_same": rgba_id == rgba_off, "non_opaque": sum(1 for a in rgba_off[3::4] if a != 255)}
    base = hd.settings
    hd.settings = dataclasses.replace(base, depth_of_field=SUBTLE)
    try:
        status = hd.dof_status()[0]
        dof = picture(hd)
        dof_stage = hd.last_stage
        hd.force_identity_composite = True
        dof_id = picture(hd)
        r["dof"] = {"status": status, "stage": dof_stage, "identity_stage": hd.last_stage,
                    "changed_the_picture": dof != off, "identity_same": dof_id == dof,
                    "world_read_unchanged": bytes(hd.draw(read=True)) == world}
        hd.force_identity_composite = False
        hd.dof_allow_software = True  # (the depth of field forced on, whatever the driver: the chain checked)
        forced = picture(hd)
        forced_stage = hd.last_stage
        hd.force_identity_composite = True
        forced_id = picture(hd)
        r["dof_forced"] = {"stage": forced_stage, "identity_stage": hd.last_stage, "identity_same": forced_id == forced,
                           "changed_the_picture": forced != off,
                           "chain_allocations": hd._composite.chain_allocations if hd._composite else None}
    finally:
        hd.force_identity_composite = False
        hd.dof_allow_software = False
        hd.settings = base
    r["off_after_dof_same"] = picture(hd) == off
    r["live_end"] = live(ctx)
    return r


def sizes(game: Any, scene: str, dims: tuple[tuple[int, int], ...]) -> dict[str, Any]:
    """The same room into offscreen targets of other sizes (the picture's size changing): identity = blit at each,
    the chain target remade once per new size and the old one freed."""
    from engine.hd2d.dof import SUBTLE  # noqa: PLC0415

    hd = settle(game, scene)
    ctx = hd.ctx
    out: dict[str, Any] = {}
    base = hd.settings
    hd.settings = dataclasses.replace(base, depth_of_field=SUBTLE)
    hd.dof_allow_software = True
    try:
        for step, (w, h) in enumerate(dims):
            tex = ctx.texture((w, h), components=4)
            fbo = ctx.framebuffer(color_attachments=[tex])
            try:
                fbo.use()
                hd.force_identity_composite = False
                hd.settings = base
                plain = picture(hd)
                hd.force_identity_composite = True
                plain_id = picture(hd)
                hd.settings = dataclasses.replace(base, depth_of_field=SUBTLE)
                hd.force_identity_composite = False
                dof = picture(hd)
                hd.force_identity_composite = True
                dof_id = picture(hd)
                out[f"{step}:{w}x{h}"] = {"identity_same": plain_id == plain, "dof_identity_same": dof_id == dof,
                                   "bytes": len(plain), "world_fbo": list(hd._fbo.size),
                                   "chain": list(hd._composite._chain[1].size) if hd._composite._chain else None,
                                   "chain_allocations": hd._composite.chain_allocations, "live": live(ctx)}
            finally:
                game.window.use()
                fbo.delete()
                tex.delete()
    finally:
        hd.force_identity_composite = False
        hd.dof_allow_software = False
        hd.settings = base
    return out


def texels(game: Any, scene: str) -> dict[str, Any]:
    """The identity itself on known data: random RGBA bytes (every alpha) at an odd size through the composite, into a
    target of that size and into an offset viewport of a larger one: every byte back, in place."""
    import random  # noqa: PLC0415

    hd = settle(game, scene)
    ctx = hd.ctx
    comp = hd._final_composite()
    w, h = 333, 211
    data = random.Random(481).randbytes(w * h * 4)
    src = ctx.texture((w, h), components=4, data=data)
    depth = ctx.depth_texture((w, h))
    depth.compare_func = None
    out: dict[str, Any] = {}
    try:
        for name, size, viewport in (("same_size", (w, h), None), ("offset_viewport", (w + 70, h + 40), (50, 30, w, h))):
            dst = ctx.texture(size, components=4)
            fbo = ctx.framebuffer(color_attachments=[dst])
            try:
                fbo.use()
                fbo.clear(color=(0, 0, 0, 0))
                with ctx.enabled_only():
                    full = ctx.viewport
                    if viewport:
                        ctx.viewport = viewport
                    comp.render(hd._blit, src, depth)
                    ctx.viewport = full
                got = bytes(fbo.read(viewport=viewport or (0, 0, w, h), components=4))
                out[name] = {"same": got == data, "alphas": len(set(data[3::4]))}
            finally:
                game.window.use()
                fbo.delete()
                dst.delete()
    finally:
        src.delete()
        depth.delete()
    return out


def release_check(game: Any, scene: str) -> dict[str, Any]:
    """The composite's objects (program + chain target) are deleted by the renderer's release."""
    from engine.hd2d.dof import SUBTLE  # noqa: PLC0415

    hd = settle(game, scene)
    base = hd.settings
    hd.settings = dataclasses.replace(base, depth_of_field=SUBTLE)
    hd.dof_allow_software = True
    hd.force_identity_composite = True
    picture(hd)
    objects = hd._composite.gl_objects()
    in_list = all(any(o is g for g in hd.gl_objects()) for o in objects)
    before = live(hd.ctx)
    hd.release()
    after = live(hd.ctx)
    return {"composite_objects": len(objects), "listed_in_gl_objects": in_list, "composite_after": hd._composite,
            "freed": {k: before[k] - after[k] for k in KINDS}}


def studio(project: Path) -> dict[str, Any]:
    """Mesh Studio's editing view of the start room: offset canvas, identity, lines, the game's camera path."""
    import numpy as np  # noqa: PLC0415
    from hd2d_studio_demo import StudioDriver

    d = StudioDriver(project)
    out: dict[str, Any] = {}
    try:
        view = d.studio.hd2d
        view.advance_motion = view.advance_weather = lambda dt: None  # (a still view)
        d.advance(5)
        d.window.motion_time = 0.0
        hd = d.renderer
        ctx = hd.ctx
        vpt = tuple(int(v) for v in view.viewport())
        out["viewport"] = list(vpt)
        x, y, w, h = vpt

        after_calls: list[bool] = []
        drawn_after = hd._overlay_after

        def counted(*a: Any, **k: Any) -> None:  # (whether Studio's lines went after the picture, not into the world)
            after_calls.append(hd.force_identity_composite)
            drawn_after(*a, **k)

        def canvas(identity: bool, lines: bool) -> Any:
            hd.force_identity_composite = identity
            kept = view._overlay
            if not lines:
                view._overlay = lambda vp: None
            try:
                d.window.clear()
                view.draw()  # (Studio's own call: its camera, its viewport, its lines)
                return np.asarray(d.arcade.get_image(x, y, w, h).convert("RGB")).copy()
            finally:
                view._overlay = kept
                hd.force_identity_composite = False

        def at_origin(identity: bool, camera: Any) -> bytes:
            tex = ctx.texture((w, h), components=4)
            fbo = ctx.framebuffer(color_attachments=[tex])
            try:
                fbo.use()
                hd.force_identity_composite = identity
                return picture(hd, camera=camera)
            finally:
                hd.force_identity_composite = False
                d.window.use()
                fbo.delete()
                tex.delete()

        plain, ident = canvas(False, False), canvas(True, False)
        flip = lambda b: np.flipud(np.frombuffer(b, dtype=np.uint8).reshape(h, w, 3))  # noqa: E731
        origin_off, origin_id = flip(at_origin(False, view.camera)), flip(at_origin(True, view.camera))
        out["canvas_identity_same"] = bool(np.array_equal(plain, ident))
        out["canvas_equals_origin"] = bool(np.array_equal(plain, origin_off))
        out["canvas_identity_equals_origin_identity"] = bool(np.array_equal(ident, origin_id))
        out["read_final_in_canvas"] = bool(np.array_equal(
            plain, flip(picture(hd, camera=view.camera, viewport=vpt))))
        hd._overlay_after = counted
        try:
            lines_off, lines_id = canvas(False, True), canvas(True, True)
        finally:
            hd._overlay_after = drawn_after
        out["lines_after_calls"] = after_calls  # (off: into the world as ever; identity: after it)
        mask = np.abs(lines_off.astype(int) - plain.astype(int)).max(axis=2) > 0
        delta = np.abs(lines_id.astype(int) - lines_off.astype(int)).max(axis=2)
        out["lines"] = {"pixels": int(mask.sum()), "outside_lines_same": bool((delta[~mask] == 0).all()),
                        "line_pixels_same_share": round(float((delta[mask] == 0).mean()), 4) if mask.any() else None,
                        "line_pixels_max_delta": int(delta[mask].max()) if mask.any() else None}
        # the game's path (no camera passed: its own, cutaway and weather as in play) for Studio's view
        game_cam = hd.camera
        saved = (game_cam.target, game_cam.pitch, game_cam.fov, game_cam.distance, game_cam.ortho, game_cam.yaw,
                 hd._camera_ready)
        sc = view.camera
        game_cam.target, game_cam.pitch, game_cam.fov, game_cam.distance, game_cam.ortho = (
            sc.target, sc.pitch, sc.fov, sc.distance, sc.ortho)
        game_cam.yaw = sc.yaw
        hd._camera_ready = True  # (else its first draw puts it over the player first: Studio never placed it)
        try:
            kept_cut = hd._bind_cutaway
            game_pic = flip(at_origin(True, None))
            # Studio's path again now, so both are drawn with the sun's shadow map fitted to the same game camera
            # (the renderer fits it to the game's camera and aspect whichever camera draws the picture)
            studio_same_fit = flip(at_origin(True, sc))
            game_again = flip(at_origin(True, None))
            hd._bind_cutaway = lambda mp, cam: kept_cut(mp, None)  # (the same, with play's cutaway off)
            game_nocut = flip(at_origin(True, None))
        finally:
            hd._bind_cutaway = kept_cut
            (game_cam.target, game_cam.pitch, game_cam.fov, game_cam.distance, game_cam.ortho, game_cam.yaw,
             hd._camera_ready) = saved
        diff = np.abs(game_pic.astype(int) - origin_id.astype(int)).max(axis=2) > 0
        out["game_path"] = {"same_as_earlier_studio_picture": bool(not diff.any()),
                            "changed_share_vs_earlier": round(float(diff.mean()), 5),
                            "same_as_studio_same_shadow_fit": bool(np.array_equal(game_again, studio_same_fit)),
                            "game_repeat_same": bool(np.array_equal(game_pic, game_again)),
                            "studio_without_cutaway_same": bool(np.array_equal(game_nocut, studio_same_fit))}
        # Studio's window resized: a new canvas size, identity still the same picture
        d.window.set_size(1100, 640)
        d.window.on_resize(1100, 640)
        d.advance(2)
        vpt2 = tuple(int(v) for v in view.viewport())
        x, y, w, h = vpt2
        out["resized"] = {"viewport": list(vpt2), "identity_same": bool(np.array_equal(canvas(False, False),
                                                                                    canvas(True, False))),
                          "world_fbo": list(hd._fbo.size)}
        out["live"] = live(ctx)
    finally:
        d.close() if hasattr(d, "close") else d.game.close()
    return out


def study(out: Path, *, size: tuple[int, int] = (960, 540), with_studio: bool = True) -> dict[str, Any]:
    import hd2d_emissive_demo as em
    import hd2d_lamp_glow_demo as glow
    from hd2d_demo import HiddenGame

    from engine.hd2d.dof import dof_unavailable_reason  # noqa: PLC0415
    from engine.project_scaffold import create_project  # noqa: PLC0415

    out.mkdir(parents=True, exist_ok=True)
    project = out / "game"
    rooms = glow.build(project)
    report: dict[str, Any] = {"size": list(size), "rooms": {}}
    game = HiddenGame(project, size=size)
    game.window.audio.set_muted(True)
    try:
        ctx = game.window.ctx
        report["gl"] = str(ctx.info.RENDERER)
        report["software_renderer"] = dof_unavailable_reason(ctx) is not None
        for name, scene in rooms.items():
            report["rooms"][name] = room(game, scene)
        visits = []
        for name in ("village", "cottage", "village", "cottage", "village"):  # composite + DoF on every visit
            hd = settle(game, rooms[name])
            hd.force_identity_composite = True
            picture(hd)
            visits.append({"room": name, "live": live(hd.ctx)})
            hd.force_identity_composite = False
        report["room_changes"] = visits
        report["sizes"] = sizes(game, rooms["village"], ((640, 360), (800, 450), (640, 360)))
        report["texels"] = texels(game, rooms["village"])
        report["release"] = release_check(game, rooms["village"])
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
    finally:
        game.close()
    if with_studio:
        report["studio"] = studio(project)
    return report


def main() -> None:
    out = Path(sys.argv[1])
    os.environ.setdefault("MESH_STUDIO_NO_AI_BRIDGE", "1")
    found = study(out)
    (out / "report.json").write_text(json.dumps(found, indent=1, default=str), encoding="utf-8")
    print(json.dumps(found, indent=1, default=str))


if __name__ == "__main__":
    main()
