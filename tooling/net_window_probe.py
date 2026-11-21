"""Local stdin/stdout test driver for one hidden Mesh client, never a network endpoint."""
from __future__ import annotations

import asyncio
import json
import sys
from unittest.mock import patch

from mesh_net.demo import OTHER, OWN, open_arena


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
                      "entity": arena.client.entity if arena.client else None}
            if cmd[0] == "capture":
                arena.draw(asyncio.get_running_loop().time())
                pixels = arena.arcade.get_image(0, 0, *arena.window.get_framebuffer_size()).convert("RGB")
                colors = {rgb for _, rgb in pixels.getcolors(maxcolors=pixels.width * pixels.height)}
                result["avatars"] = [OWN in colors, OTHER in colors]
                result["sign"] = any(s.mesh_name == "Arena sign" for s in arena.window.scene_controller.all_sprites)
            print("NET_PROOF " + json.dumps(result), flush=True)
    finally:
        arena.stop()
        await render


if __name__ == "__main__":
    from engine import optional_arcade

    original = optional_arcade.arcade.Window.__init__

    def hidden(window, *args, **kwargs):
        original(window, *args, **{**kwargs, "visible": False})

    with patch.object(optional_arcade.arcade.Window, "__init__", hidden), open_arena() as arena:
        asyncio.run(drive(arena, int(sys.argv[1])))
