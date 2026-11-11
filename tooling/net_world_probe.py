"""Local stdin/stdout test driver for one hidden world window (mesh_net.world_client), never a network endpoint.

Commands: ``state``, ``press KEY``, ``release KEY``, ``capture``, ``quit``. Each prints one ``NET_PROOF {json}`` line.
``capture`` is tooling/net_scene_probe.py's: avatars counted by the pixels the scene renderer drew for them.
"""
from __future__ import annotations

import asyncio
import json
import sys
from unittest.mock import patch

from mesh_net.world import expedition_files
from mesh_net.world_client import SIZE, WorldArena
from tooling.net_scene_probe import capture


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
            if cmd[0] in ("press", "release"):
                event = "on_key_press" if cmd[0] == "press" else "on_key_release"
                arena.window.dispatch_event(event, getattr(arena.arcade.key, cmd[1]), 0)
            result = {"phase": arena.phase, "player": arena.player, "room": arena.room, "key": arena.key,
                      "shown": arena.shown, "entity": arena.entity, "state": arena.state, "party": arena.party,
                      "status": arena.status, "identity": arena.identity, "loads": arena.loads, "trace": list(arena.trace),
                      "scene_path": getattr(arena.window.scene_controller, "current_scene_path", None)}
            if cmd[0] == "capture" and arena.view is not None:
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

    with patch.object(optional_arcade.arcade.Window, "__init__", hidden), \
            open_arena(expedition_files(), SIZE, WorldArena) as arena:
        asyncio.run(drive(arena, int(sys.argv[1])))
