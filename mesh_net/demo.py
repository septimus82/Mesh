"""Separate Mesh client process. Run python -m mesh_net.demo in each terminal."""

from __future__ import annotations

import argparse
import asyncio
import time
from contextlib import contextmanager
from importlib.resources import files

from . import protocol as wire
from .client import Client, connect
from .playback import Playback
from .scene_room import PENDING, Feedback, Prediction, disposable_project

OWN = (61, 225, 188)
OTHER = (255, 191, 76)


@contextmanager
def open_arena(files_: dict[str, bytes] | None = None, size: tuple[int, int] = (wire.WIDTH, wire.HEIGHT),
               make=lambda window, arcade, root, scene: Arena(window, arcade)):
    """Each client owns a disposable Mesh project and a single GL context."""
    with disposable_project(files_ or {}) as root:
        from engine import optional_arcade
        from engine.config import load_config
        from engine.game import GameWindow

        path = root / "config.json"
        config = load_config(str(path))
        config.cocreative_live_bridge_enabled = False
        scene = config.start_scene
        if files_ is None:
            (root / scene).write_bytes(files("mesh_net").joinpath("sample_room.json").read_bytes())
        window = GameWindow(width=size[0], height=size[1], title="Mesh local room",
                            vsync=False, resizable=False, config=config, config_path=str(path))
        try:
            window.load_scene(scene)
            yield make(window, optional_arcade.arcade, root, scene)
        finally:
            window.close()


def reason(exc: BaseException) -> str:
    """Why a session ended, short, for the caption: a refusal's own words (wire.Invalid: another protocol version,
    a refused character, a malformed frame), else the error's kind."""
    text = str(exc) if isinstance(exc, wire.Invalid) else ""
    return text[:64] or type(exc).__name__


class Arena:
    def __init__(self, window, arcade) -> None:
        self.window, self.arcade = window, arcade
        key = arcade.key
        self.directions = {key.W: (0, 1), key.UP: (0, 1), key.S: (0, -1), key.DOWN: (0, -1),
                           key.A: (-1, 0), key.LEFT: (-1, 0), key.D: (1, 0), key.RIGHT: (1, 0)}
        self.keys: list[int] = []
        self.action_keys: set[int] = set()
        # Actions pressed and not yet sent, oldest first, each with the tick it is meant for (None: the next) and, for an
        # attack, the tick the window showed when it was pressed (M4-5's view_tick; None: none): one rides each input
        # sent, so none replaces another (an attack whose swing showed is sent even if E follows at once).
        self.actions: list[tuple[str, int | None, float | None]] = []
        # How many of those may ride the input a direction press built (the ones pressed before it: the avatar showed
        # them from before its step, where the server runs them); later ones wait for the input after it. None: no
        # input built at a press is waiting.
        self.riders: int | None = None
        self.running = True
        self.request: str | None = "resume"
        self.client: Client | None = None
        self.token: str | None = None
        self.checks: dict = {}  # connect()'s validators; mesh_net.scene_client passes the scene room's
        self.playback = Playback()
        self.local_interpolation = False
        # A scene room's (mesh_net.scene_client, mesh_net.world_client): its combat presentation and the room's tick as
        # reckoned (every input carries it: one estimate), and its own avatar's prediction. None in the 2D sample.
        self.feedback: Feedback | None = None
        self.prediction: Prediction | None = None
        self.clock = time.monotonic  # (s) when a key press happened (tests: a virtual clock)
        self.status = "Connecting"
        window.push_handlers(on_key_press=self.press, on_key_release=self.release,
                             on_close=self.stop, on_deactivate=self.blur)

    def press(self, symbol: int, modifiers: int) -> bool:
        key = self.arcade.key
        if symbol in self.directions and symbol not in self.keys:
            self.keys.append(symbol)
            if self.prediction is not None and self.prediction.press(self.directions[symbol]):
                self.riders = len(self.actions)  # (the avatar moved on this frame: the next input is built now)
                if any(action == "attack" for action, _, _ in self.actions):
                    self.aim()  # (a waiting attack rides that input: the server turns first, then strikes)
        elif symbol in (key.SPACE, key.E) and self.client and symbol not in self.action_keys:
            self.action_keys.add(symbol)
            self.act("attack" if symbol == key.SPACE else "take")
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

    def act(self, action: str, tick: int | None = None, view: float | None = None) -> None:
        """Queue an action to send. An attack whose swing the window showed (it has its meant tick, and ``view``, the
        tick the window showed then: Playback's cursor) always queues (the cooldown already spaces them); any other
        action while fewer than PENDING wait (the server keeps no more)."""
        if tick is not None or sum(t is None for _, t, _ in self.actions) < PENDING:
            self.actions.append((action, tick, view))

    def next_action(self, limit: int | None = None) -> tuple[str | None, int | None, float | None]:
        """What the next input carries: the oldest attack whose swing showed first (its meant tick ages while it
        waits: SceneRoom._may_attack's cap), else the oldest other action, each with its view tick; (None, None, None)
        when nothing waits. ``limit``: only the oldest that many may go (``riders``)."""
        pool = self.actions[:limit] if limit is not None else self.actions
        for index, (_, tick, _) in enumerate(pool):
            if tick is not None:
                return self.actions.pop(index)
        return self.actions.pop(0) if pool else (None, None, None)

    def outgoing(self) -> tuple[tuple[int, int], str | None, int | None, float | None]:
        """The next input: its direction (a predicting window's built input, else the keys held), its action, the
        tick it is meant for (an attack's as its swing reckoned it; else the room's tick as reckoned now: Feedback;
        None in the 2D sample: the next) and its view tick (an attack's, M4-5; else None). The caller says
        ``prediction.sent(seq)`` before it goes."""
        direction = self.directions[self.keys[-1]] if self.keys else (0, 0)
        limit, self.riders = self.riders, None
        if self.prediction is not None:
            built = bool(self.prediction.inputs) and self.prediction.inputs[-1][0] is None  # (at a press)
            direction = self.prediction.next(direction)
            limit = limit if built else None
        action, tick, view = self.next_action(limit)
        if action == "attack":
            self.aim()  # (the input it rides is known now, and so the facing the server will strike in)
        if tick is None and self.feedback is not None:
            tick = self.feedback.tick(self.clock())
        return direction, action, tick, view

    def aim(self) -> None:
        """A waiting attack's input changed or became known: the facing the server will strike in may differ from the
        one its swing showed at the press (a quick reversal). A scene room's arena turns the shown swing to it;
        presentation only, nothing sent changes. (The 2D sample shows no swing.)"""

    def blur(self) -> bool:
        """Focus lost: release every held key (none sticks), but keep the actions pressed: they are still sent."""
        self.keys.clear()
        self.action_keys.clear()
        return True

    def stop(self) -> bool:
        self.running = False
        return True

    async def session(self, port: int) -> None:
        try:
            async with connect(port, self.token, **self.checks) as client:
                self.client, self.token = client, client.resume
                self.playback = Playback(client.check)
                loop = asyncio.get_running_loop()
                self.playback.push(client.state, loop.time())
                self.on_state(client.state, client.entity, True)

                async def send_inputs() -> None:
                    due = loop.time()
                    while True:
                        direction, action, tick, view = self.outgoing()
                        if self.prediction is not None:
                            self.prediction.sent(client.seq + 1)  # (Client.input numbers it so)
                        await client.input(*direction, action=action, tick=tick, view_tick=view)
                        due = max(due + 1 / wire.HZ, loop.time())  # fixed schedule: no drift; after a stall, one extra send
                        await asyncio.sleep(due - loop.time())

                async def receive_states() -> None:
                    while True:
                        state = await client.receive()
                        self.playback.push(state, loop.time())
                        self.on_state(state, client.entity, False)
                        self.status = self.describe(state, client.entity)

                tasks = [asyncio.create_task(send_inputs()), asyncio.create_task(receive_states())]
                try:
                    done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        task.result()
                finally:
                    client.writer.close()
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
        except (OSError, EOFError, TimeoutError, wire.Invalid) as exc:
            self.status = f"Disconnected ({reason(exc)}) | R resume / N new"
        finally:
            self.client = None
            self.blur()
            self.actions.clear()  # (the session they were pressed in is over: never sent in another)
            self.riders = None
            if self.prediction is not None:
                self.prediction.stop()  # (nor walked again in another)
            self.playback = Playback()

    def on_state(self, state: wire.Message, entity: int, fresh: bool) -> None:
        """A state the client applied (``fresh``: the welcome's, a session's first). A scene room presents combat."""

    def describe(self, state: wire.Message, entity: int) -> str:
        loot = int(state["holder"] == entity)
        return f"P{entity} | HP {state['enemy_hp']} | loot {loot} | arrows, Space attack, E take, F2 leave"

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
            positions = self.playback.positions(now)
            if not self.local_interpolation:
                positions[self.client.entity] = next((x, y) for eid, x, y in state["players"]
                                                     if eid == self.client.entity)
            for eid, (x, y) in positions.items():
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
