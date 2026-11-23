"""Local stdin/stdout test driver for one hidden world window (mesh_net.world_client), never a network endpoint.

Commands: ``state``, ``press KEY``, ``release KEY``, ``capture``, ``port N`` (join that server next), ``look`` (an HD-2D
room), ``frame PATH`` (save the window's picture), ``quit``. Each prints one ``NET_PROOF {json}`` line.
``capture`` is tooling/net_scene_probe.py's: avatars counted by the pixels the scene renderer drew for them.

Arguments: ``PORT [KEY_FILE] [--project DIR] [--fail-hd2d]``. ``--project``: play that project folder's world (its
files copied into this window's own disposable project) instead of the packaged expedition; ``--fail-hd2d``: every HD-2D
room's 3D build fails as a driver refusing a buffer would (engine.hd2d.runtime then plays it 2D, ``hd2d_error`` set).
In an HD-2D room every reply has ``window``: what this window's own objects say (see ``window_facts``).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from contextlib import ExitStack, nullcontext
from pathlib import Path
from typing import Any
from unittest.mock import patch

from mesh_net.world import expedition_files
from mesh_net.world_client import SIZE, WorldArena, read_character
from tooling.net_scene_probe import capture, rendered

PX = 32.0  # engine.hd2d.settings.PIXELS_PER_METRE
# Only the keys this probe sends reach the client or the game window: they carry OWN, a modifier bit no keyboard sets
# (pyglet may queue an event and deliver it later, so only a mark on the event itself tells them apart). Any other key
# event (a hidden window can still be activated, and then it has the keyboard) is stopped and counted (``foreign_keys``).
OWN, FOREIGN = 1 << 24, [0]


def only_dispatched(handler: Any) -> Any:
    def guarded(self: Any, symbol: int, modifiers: int) -> Any:
        if modifiers & OWN:
            return handler(self, symbol, modifiers & ~OWN)
        FOREIGN[0] += 1
        return True  # (handled: nothing else sees it)
    return guarded


def window_facts(arena) -> dict[str, Any] | None:
    """An HD-2D room as this window holds it: each avatar's x, y (px), elevation (px: what the renderer draws it at,
    Hd2dRenderer.elevation_of) and floor; which avatar the renderer's ``camera_target`` and ``followed()`` are; the
    camera's target (m) and height over the followed feet. None without a view."""
    view, w = arena.view, arena.window
    if view is None:
        return None
    r = getattr(w, "hd2d_renderer", None)

    def which(sprite: Any) -> int | None:
        return next((eid for eid, s in view.avatars.items() if s is sprite), None) if sprite is not None else None

    return {"hd2d": r is not None,
            "avatars": {eid: [s.center_x, s.center_y, r.elevation_of(s) if r else None,
                              getattr(s, "mesh_hd2d_floor", None)] for eid, s in view.avatars.items()},
            "camera_target": which(r.camera_target) if r else None, "followed": which(r.followed()) if r else None,
            "camera": list(r.camera.target) if r else None, "camera_height": r.settings.camera.height if r else None}


def look(arena) -> dict[str, Any]:
    """What the window drew of each avatar in an HD-2D room: the picture rendered with every avatar, then without each
    one in turn; the pixels that changed (``drawn``) and their box (``box``: left, top, right, bottom, rows from the
    top). ``feet``: the screen row the renderer's camera puts that avatar's feet at, at each elevation the snapshot
    row (``row``) or the floors could put it (0 and 2 m), to compare with where it was drawn."""
    from PIL import ImageChops  # noqa: PLC0415

    r = arena.window.hd2d_renderer
    arena.draw(asyncio.get_running_loop().time())
    full = rendered(arena)
    fw, fh = full.size
    vp = r.camera.view_projection(fw / fh)
    rows = {row[0]: row for row in arena.state["players"]} if arena.state else {}
    out: dict[str, Any] = {}
    for eid, sprite in arena.avatars.items():
        sprite.visible = False
        try:
            without = rendered(arena)
        finally:
            sprite.visible = True
        diff = ImageChops.difference(full, without).convert("L").point(lambda v: 255 if v else 0)

        def row_at(z_px: float, s: Any = sprite) -> float:
            p = (s.center_x / PX, s.bottom / PX, z_px / PX)
            c = [sum(vp[i][k] * (p[k] if k < 3 else 1.0) for k in range(4)) for i in range(4)]
            return round(float((0.5 - c[1] / c[3] * 0.5) * fh), 1)

        own_row = rows.get(eid)
        out[str(eid)] = {"drawn": diff.histogram()[255], "box": diff.getbbox(),
                         "feet": {"row": row_at(own_row[4]) if own_row else None, "0": row_at(0.0), "64": row_at(64.0)}}
    info = arena.window.ctx.info
    return {"size": [fw, fh], "avatars": out, "gl": [info.VENDOR, info.RENDERER]}


async def drive(arena, port: int) -> None:
    # A hidden window has no focus of its own: the OS deactivates it when another test window loads a room, and the
    # client (rightly, for a player switching windows) then lets go of held keys. Driven by this probe, it keeps them.
    arena.window.remove_handlers(on_deactivate=arena.blur)
    render = asyncio.create_task(arena.run(port))
    try:
        while True:
            line = await asyncio.to_thread(sys.stdin.readline)
            if not line:
                return
            cmd = line.strip().split()
            if render.done():
                render.result()
            if cmd[0] == "quit":
                return
            if cmd[0] == "port":  # the server to join next (a restarted one)
                arena.port = int(cmd[1])
            if cmd[0] in ("press", "release"):
                event = "on_key_press" if cmd[0] == "press" else "on_key_release"
                arena.window.dispatch_event(event, getattr(arena.arcade.key, cmd[1]), OWN)
            if cmd[0] == "frame":  # this window's picture, read back from its framebuffer
                arena.draw(asyncio.get_running_loop().time())
                rendered(arena).save(cmd[1])
            result = {"phase": arena.phase, "player": arena.player, "room": arena.room, "key": arena.key,
                      "shown": arena.shown, "entity": arena.entity, "state": arena.state, "party": arena.party,
                      "status": arena.status, "identity": arena.identity, "loads": arena.loads, "trace": list(arena.trace),
                      "sheet": arena.sheet, "refused": arena.refused, "refusal": arena.refusal, "seq": arena.seq,
                      "foreign_keys": FOREIGN[0],
                      "window": window_facts(arena), "hd2d_error": getattr(arena.window, "hd2d_error", None),
                      "scene_path": getattr(arena.window.scene_controller, "current_scene_path", None)}
            if cmd[0] == "capture" and arena.view is not None:
                result.update(capture(arena))
            if cmd[0] == "look" and arena.view is not None and getattr(arena.window, "hd2d_renderer", None) is not None:
                result["look"] = look(arena)
            print("NET_PROOF " + json.dumps(result), flush=True)
    finally:
        arena.stop()
        await render


if __name__ == "__main__":
    from engine import optional_arcade
    from mesh_net.demo import open_arena

    original = optional_arcade.arcade.Window.__init__
    parser = argparse.ArgumentParser()
    parser.add_argument("port", type=int)
    parser.add_argument("key_file", nargs="?")  # (N8: a character key file)
    parser.add_argument("--project", type=Path)
    parser.add_argument("--fail-hd2d", action="store_true")
    args = parser.parse_args()
    character = read_character(args.key_file) if args.key_file else None
    files = expedition_files()
    if args.project is not None:  # (its .mesh folder of caches and records stays behind)
        files = {p.relative_to(args.project).as_posix(): p.read_bytes() for p in args.project.rglob("*")
                 if p.is_file() and ".mesh" not in p.relative_to(args.project).parts}

    def hidden(window, *args, **kwargs):
        original(window, *args, **{**kwargs, "visible": False})

    def refused(renderer, *args, **kwargs):
        raise RuntimeError("simulated: the driver refused a buffer")

    fail = patch("engine.hd2d.renderer.Hd2dRenderer.__init__", refused) if args.fail_hd2d else nullcontext()
    # A project's pictures go in evidence: its first room's controls hint is left out. (The client never ticks the
    # HUD, so that 4 s toast would cover the middle of every picture for good.)
    hint = patch("engine.ui_overlays.hud.PlayerHUD.maybe_show_controls_hint", return_value=None) \
        if args.project is not None else nullcontext()
    from engine.game import GameWindow

    with ExitStack() as keys:
        for cls, names in ((WorldArena, ("press", "release")), (GameWindow, ("on_key_press", "on_key_release"))):
            for name in names:
                keys.enter_context(patch.object(cls, name, only_dispatched(getattr(cls, name))))
        with patch.object(optional_arcade.arcade.Window, "__init__", hidden), fail, hint, \
                open_arena(files, SIZE, WorldArena) as arena:
            arena.character = character
            asyncio.run(drive(arena, args.port))
