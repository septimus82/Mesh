"""Local stdin/stdout test driver for one hidden co-op scene window (mesh_net.scene_client), never a network endpoint.

Commands: ``state``, ``press KEY``, ``release KEY``, ``capture``, ``quit``. Each prints one ``NET_PROOF {json}`` line.
``capture`` renders the frame twice, with and without the avatars, and reports how many pixels each avatar
changed inside its picture's box on screen: drawn by the scene renderer, where the camera puts it.
"""
from __future__ import annotations

import asyncio
import json
import sys
from typing import Any
from unittest.mock import patch

from mesh_net.scene_client import SIZE, SceneArena
from mesh_net.scene_room import coop_files


def rendered(arena) -> Any:
    arena.window.on_draw()
    return arena.arcade.get_image(0, 0, *arena.window.get_framebuffer_size()).convert("RGB")


def capture(arena) -> dict:
    arena.draw(asyncio.get_running_loop().time())
    with_avatars = rendered(arena)
    for sprite in arena.avatars.values():
        sprite.visible = False
    try:
        without = rendered(arena)
    finally:
        for sprite in arena.avatars.values():
            sprite.visible = True
    fw, fh = arena.window.get_framebuffer_size()
    sx, sy = fw / arena.window.width, fh / arena.window.height
    drawn = {}
    for eid, sprite in arena.avatars.items():
        px, py = arena.window.camera.project((sprite.center_x, sprite.center_y))[:2]
        x0, x1 = int((px - sprite.width / 2) * sx), int((px + sprite.width / 2) * sx)
        y0, y1 = int(fh - (py + sprite.height / 2) * sy), int(fh - (py - sprite.height / 2) * sy)
        drawn[eid] = sum(with_avatars.getpixel((x, y)) != without.getpixel((x, y))
                         for x in range(max(0, x0), min(fw, x1)) for y in range(max(0, y0), min(fh, y1)))
    sc = arena.scene
    tiles = sorted([s.center_x, s.center_y, s.width, s.height] for s in sc.tilemap_instance.collision_sprites)
    return {"drawn": drawn, "camera": list(arena.window.camera.position)[:2],
            "avatars": {eid: [s.center_x, s.center_y, s.width, s.height, list(s.color)[:3]] for eid, s in arena.avatars.items()},
            "objects": {i: [s.center_x, s.center_y, s.width, s.height, bool(s.visible)] for i, s in arena.sprites.items()},
            "drops": sorted(arena.drops), "tiles": tiles,
            "players": sorted(s.mesh_id for s in sc.all_sprites if getattr(s, "mesh_tag", None) == "player"),
            "behaviours": {str(getattr(s, "mesh_id", "")): [type(b).__name__ for b in s.mesh_behaviours_runtime]
                           for s in sc.all_sprites if getattr(s, "mesh_behaviours_runtime", None)}}


async def drive(arena, port: int) -> None:
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
            if cmd[0] in ("press", "release"):
                event = "on_key_press" if cmd[0] == "press" else "on_key_release"
                arena.window.dispatch_event(event, getattr(arena.arcade.key, cmd[1]), 0)
            result = {"state": arena.client.state if arena.client else None,
                      "entity": arena.client.entity if arena.client else None,
                      "identity": arena.identity, "status": arena.status}
            if cmd[0] == "capture":
                result.update(capture(arena))
            print("NET_PROOF " + json.dumps(result), flush=True)
    finally:
        arena.stop()
        await render


if __name__ == "__main__":
    from engine import optional_arcade
    from mesh_net.demo import open_arena

    original = optional_arcade.arcade.Window.__init__

    def hidden(window, *args, **kwargs):
        original(window, *args, **{**kwargs, "visible": False})

    with patch.object(optional_arcade.arcade.Window, "__init__", hidden), open_arena(coop_files(), SIZE, SceneArena) as arena:
        asyncio.run(drive(arena, int(sys.argv[1])))
