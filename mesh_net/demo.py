"""Separate Mesh client process. Run python -m mesh_net.demo in each terminal."""

from __future__ import annotations

import argparse
import asyncio
import os
from contextlib import chdir, contextmanager
from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory

from . import protocol as wire
from .client import Client, connect
from .playback import Playback

OWN = (61, 225, 188)
OTHER = (255, 191, 76)


@contextmanager
def open_arena():
    """Each client owns a disposable Mesh project and a single GL context."""
    with TemporaryDirectory(prefix="mesh-room-") as temp, chdir(temp):
        root = Path(temp)
        paths = {"MESH_USER_DIR": "user", "MESH_RUNTIME_SETTINGS_PATH": "user/settings.json",
                 "MESH_PROJECTS_DIR": "projects", "MESH_PROJECTS_PATH": "user/projects.json",
                 "MESH_SAVE_DIR": "saves", "MESH_REPO_ROOT": "."}
        previous = {name: os.environ.get(name) for name in paths}
        try:
            for name, relative in paths.items():
                os.environ[name] = str(root / relative)
            from engine import optional_arcade
            from engine.config import load_config
            from engine.game import GameWindow
            from engine.project_scaffold import create_project

            create_project(root, "Mesh local room")
            path = root / "config.json"
            config = load_config(str(path))
            config.cocreative_live_bridge_enabled = False
            scene = config.start_scene
            (root / scene).write_bytes(files("mesh_net").joinpath("sample_room.json").read_bytes())
            window = GameWindow(width=wire.WIDTH, height=wire.HEIGHT, title="Mesh local room",
                                vsync=False, resizable=False, config=config, config_path=str(path))
            try:
                window.load_scene(scene)
                yield Arena(window, optional_arcade.arcade)
            finally:
                window.close()
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


class Arena:
    def __init__(self, window, arcade) -> None:
        self.window, self.arcade = window, arcade
        key = arcade.key
        self.directions = {key.W: (0, 1), key.UP: (0, 1), key.S: (0, -1), key.DOWN: (0, -1),
                           key.A: (-1, 0), key.LEFT: (-1, 0), key.D: (1, 0), key.RIGHT: (1, 0)}
        self.keys: list[int] = []
        self.action_keys: set[int] = set()
        self.action: str | None = None
        self.running = True
        self.request: str | None = "resume"
        self.client: Client | None = None
        self.token: str | None = None
        self.playback = Playback()
        self.status = "Connecting"
        window.push_handlers(on_key_press=self.press, on_key_release=self.release,
                             on_close=self.stop, on_deactivate=self.blur)

    def press(self, symbol: int, modifiers: int) -> bool:
        key = self.arcade.key
        if symbol in self.directions and symbol not in self.keys:
            self.keys.append(symbol)
        elif symbol in (key.SPACE, key.E) and self.client and symbol not in self.action_keys:
            self.action_keys.add(symbol)
            self.action = "attack" if symbol == key.SPACE else "take"
        elif symbol == key.ESCAPE:
            self.stop()
        elif symbol == key.F2:
            self.request = "disconnect"
        elif symbol in (key.R, key.N) and self.client is None:
            self.request = "resume" if symbol == key.R else "new"
        return True

    def release(self, symbol: int, modifiers: int) -> bool:
        self.action_keys.discard(symbol)
        if symbol in self.keys:
            self.keys.remove(symbol)
        return True

    def blur(self) -> bool:
        self.keys.clear()
        self.action_keys.clear()
        self.action = None
        return True

    def stop(self) -> bool:
        self.running = False
        return True

    async def session(self, port: int) -> None:
        try:
            async with connect(port, self.token) as client:
                self.client, self.token = client, client.resume
                self.playback = Playback()
                loop = asyncio.get_running_loop()
                self.playback.push(client.state, loop.time())
                next_input = 0.0
                while True:
                    if loop.time() >= next_input:
                        direction = self.directions[self.keys[-1]] if self.keys else (0, 0)
                        action, self.action = self.action, None
                        await client.input(*direction, action=action)
                        next_input = loop.time() + 0.8 / wire.HZ
                    state = await client.receive()
                    self.playback.push(state, loop.time())
                    loot = int(state["holder"] == client.entity)
                    self.status = f"P{client.entity} | HP {state['enemy_hp']} | loot {loot} | arrows, Space attack, E take, F2 leave"
        except (OSError, EOFError, TimeoutError, wire.Invalid) as exc:
            self.status = f"Disconnected ({type(exc).__name__}) | R resume / N new"
        finally:
            self.client = None
            self.blur()
            self.playback = Playback()

    def draw(self, now: float) -> None:
        self.window.clear(color=(32, 47, 57))
        self.window.scene_controller.draw()
        self.window.default_camera.use()
        if self.client:
            state = self.client.state
            if state["enemy_hp"]:
                self.arcade.draw_circle_filled(*wire.ENEMY_AT, 7, (235, 91, 89))
            elif state["pickup"]:
                self.arcade.draw_circle_filled(*wire.ENEMY_AT, 5, (149, 224, 82))
            for eid, (x, y) in self.playback.positions(now).items():
                self.arcade.draw_circle_filled(x, y, 4, OWN if eid == self.client.entity else OTHER)

    async def run(self, port: int) -> None:
        task = None
        caption = ""
        loop = asyncio.get_running_loop()
        try:
            while self.running:
                self.window.dispatch_events()
                if self.request is not None:
                    request, self.request = self.request, None
                    if task:
                        task.cancel()
                        await asyncio.gather(task, return_exceptions=True)
                        task = None
                    if request == "disconnect":
                        self.status = "Disconnected | R resume / N new"
                    else:
                        if request == "new":
                            self.token = None
                        task = asyncio.create_task(self.session(port))
                if task and task.done():
                    task.result()
                    task = None
                if self.status != caption:
                    caption = self.status
                    self.window.set_caption(caption)
                self.draw(loop.time())
                self.window.flip()
                await asyncio.sleep(1 / 60)
        finally:
            if task:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=46870)
    args = parser.parse_args()
    with open_arena() as arena:
        asyncio.run(arena.run(args.port))


if __name__ == "__main__":
    main()
