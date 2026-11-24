"""A Mesh game window playing the world hosted by ``python -m mesh_net.server --expedition``.

Run ``python -m mesh_net.world_client`` in two terminals. Each room loads through ``GameWindow.load_scene`` and
draws through the ordinary renderer and camera; the server owns every rule, transition and party. The window
loads a room when the server says the player has entered it (``enter``), and until it has, it sends no input.

Keys: arrows/WASD move, Space attack, E use/take, P create a party, I invite the nearest player, Y accept and
N decline an invitation, L leave the party, F2 disconnect, R resume, Esc quit.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import time
from collections import deque
from pathlib import Path
from typing import Any

from engine.scene_runtime.room_memory import VAR as ROOM_MEMORY

from . import protocol as wire
from .demo import Arena, open_arena, reason
from .playback import Playback
from .scene_client import JoinRefused, SceneView
from .scene_room import Feedback, Prediction, check_progress, check_state
from .world import World, check_frame, check_welcome, expedition_files

SIZE = (640, 360)
NOTICE_TEXT = {"need_party": "an expedition needs a party (P)", "no_instance": "no free expedition room",
               "room_full": "that room is full", "transfer_failed": "the way is blocked (try again)",
               "left_expedition": "you left the party's expedition", "in_party": "already in a party",
               "not_leader": "only the leader invites", "no_player": "nobody to invite", "busy": "they are busy",
               "no_invite": "no such invitation", "party_full": "the party is full", "invited": "invited! Y/N",
               "picked_up": "picked up", "inventory_full": "no room for it (it stays here)",
               "storage_failed": "could not be saved (nothing changed; try again)", "unlocked": "unlocked!",
               "unlock_owed": "unlock earned; the server's storage is failing, so it is kept and recorded later",
               "unlock_not_kept": "unlock earned but NOT saved: the server's storage is failing",
               "storage_unavailable": "the server's storage is failing: no new expedition until it recovers"}


class WorldArena(Arena):
    feedback: Feedback
    prediction: Prediction

    def __init__(self, window: Any, arcade: Any, root: Path, scene: str) -> None:
        super().__init__(window, arcade)
        world = World(root)  # the rooms as the server validates them, built from this window's own files
        self.identity = world.identity
        self.defs = world.defs
        self.identities = {key: d.proto.identity for key, d in world.defs.items()}
        self.phase = "connecting"  # connecting -> loading (an enter not yet shown) -> playing; disconnected
        self.player: int | None = None
        self.room: str | None = None  # the room the server last said this player is in
        self.key: str | None = None
        self.entity: int | None = None
        self.state: wire.Message | None = None
        self.pending: wire.Message | None = None  # an enter whose room the window has not loaded yet
        self.view: SceneView | None = None
        self.shown: str | None = None  # the room the view shows
        self.party: wire.Message | None = None
        self.character: dict[str, str] | None = None  # N8: {"id", "key"} of the character this window plays
        self.sheet: wire.Message | None = None  # the server's account of that character (items, unlocks)
        self.refused: str | None = None
        self.refusal: str | None = None  # why this window left the room it was put in (JoinRefused): shown until it plays
        self.port: int | None = None  # another server to join next time (a restarted one), instead of run()'s
        self.notice: tuple[str, float] | None = None
        self.requests: list[wire.Message] = []
        self.seq = 0
        self.feedback = Feedback()
        self.prediction = Prediction()  # (predicting only in the room on screen: from when it shows to the next enter)
        self.last: float | None = None
        self.loads: list[str] = []  # the rooms this window loaded, in order (for diagnostics and tests)
        self.trace: deque[tuple[float, str]] = deque(maxlen=48)  # (monotonic seconds, what happened): diagnostics

    # (the shown room's presentation, as tooling/net_world_probe.py reads it)
    scene = property(lambda self: self.view.scene)
    sprites = property(lambda self: self.view.sprites)
    avatars = property(lambda self: self.view.avatars if self.view else {})
    drops = property(lambda self: self.view.drops)

    @property
    def connected(self) -> bool:
        return self.phase in ("loading", "playing")

    def note(self, event: str) -> None:
        self.trace.append((round(time.monotonic(), 3), event))

    def press(self, symbol: int, modifiers: int) -> bool:
        key = self.arcade.key
        if symbol in (key.F2, key.R, key.N, key.ESCAPE):
            self.note(f"key {symbol} ({self.phase}, request {self.request})")
        if symbol in self.directions:
            return super().press(symbol, modifiers)
        if self.connected and symbol not in self.action_keys:
            self.action_keys.add(symbol)
            if symbol == key.SPACE:
                # Only in the room on screen (inputs wait while one loads), and never in the cooldown: then a swing
                # shows at once and the attack is sent; the server confirms only a hit.
                tick = (self.feedback.press(self.clock()) if self.phase == "playing" and self.view is not None
                        and self.shown == self.room and self.entity is not None else None)
                if tick is not None and self.view is not None and self.entity is not None:
                    self.act("attack", tick)  # the server judges its cooldown on this tick, as the window did
                    self.view.swing(self.entity, own=True)
            elif symbol == key.E:
                own = self._own()
                # Only in the room on screen, as an attack: never one pressed while the next room loads (it would run
                # in a room the player hasn't seen). (The view shows the state's room: just after an enter it doesn't.)
                if (self.phase == "playing" and self.view is not None and self.state is not None
                        and self.shown == self.room):
                    body = self.prediction.body  # (where the window shows itself: the server runs it from there)
                    at = (body.center_x, body.center_y) if body else (own[1], own[2]) if own is not None else None
                    near = at is not None and self.view.near_drop(at[0], at[1], self.state)
                    self.act("take" if near else "use")
            elif symbol == key.P:
                self._ask("create")
            elif symbol == key.I:
                target = self._nearest()
                if target is not None:
                    self._ask("invite", player=target)
            elif symbol in (key.Y, key.N) and self.party and self.party["invites"]:
                self._ask("accept" if symbol == key.Y else "decline", party=self.party["invites"][0][0])
            elif symbol == key.L:
                self._ask("leave")
            elif symbol in (key.ESCAPE, key.F2):
                return super().press(symbol, modifiers)
            return True
        if symbol in (key.R, key.N) and not self.connected:
            self.request = "resume" if symbol == key.R else "new"
            return True
        return super().press(symbol, modifiers) if symbol in (key.ESCAPE, key.F2) else True

    def _ask(self, op: str, **fields: int) -> None:
        if len(self.requests) < 4:
            self.requests.append({"v": wire.VERSION, "type": "party", "op": op, **fields})

    def _own(self) -> list[Any] | None:
        if self.state is None:
            return None
        return next((r for r in self.state["players"] if r[0] == self.entity), None)

    def _nearest(self) -> int | None:
        """The player id of the nearest other avatar in this room (the party view maps avatars to players)."""
        own = self._own()
        if own is None or self.party is None or self.state is None:
            return None
        pids = {eid: pid for pid, eid in self.party["nearby"]}
        others = [(math.hypot(r[1] - own[1], r[2] - own[2]), pids[r[0]]) for r in self.state["players"]
                  if r[0] != self.entity and r[0] in pids]
        return min(others)[1] if others else None

    def on_frame(self, msg: wire.Message, now: float) -> None:
        """Apply one validated frame. Order-independent: a room's state counts only for the room the latest enter
        named, with ticks strictly increasing within it."""
        kind = msg["type"]
        if kind == "enter":
            identity, room = self.identities[msg["key"]], self.defs[msg["key"]].proto
            check_state(msg["state"], identity, room)  # (its rows against this window's own room, before any is kept)
            self.room, self.key, self.entity = msg["room"], msg["key"], msg["entity"]
            self.state = msg["state"]
            self.feedback.baseline(self.state, room.cooldown, now)  # (another room instance: its own counters)
            self.actions.clear()  # (what was pressed in the last room is never sent into this one)
            self.riders = None
            self.prediction.stop()  # (nor walked again in this one)
            self.playback = Playback(lambda s: check_state(s, identity, room))
            self.playback.push(self.state, now)
            self.pending, self.phase = msg, "loading"
        elif kind == "room_state":
            if msg["room"] != self.room or self.key is None:
                return  # sent before this player left that room
            state = msg["state"]
            check_state(state, self.identities[self.key], self.defs[self.key].proto)
            if self.state is not None and state["tick"] <= self.state["tick"]:
                raise wire.Invalid("room state out of order")
            own = self.entity
            if own is None or not any(r[0] == own for r in state["players"]):
                raise wire.Invalid("room state without the player's own avatar")
            if self.state is not None:
                check_progress(self.state, state, own, self.seq)
            self.state = state
            self.playback.push(state, now)
            self.prediction.reconcile(state, own)  # (predicting only once the room shows)
            swung, hit = self.feedback.update(state, own, now)
            if self.view is not None and self.shown == self.room:  # (a view still loading shows none of it)
                for eid in swung:
                    self.view.swing(eid, own=False)
                for enemy in hit:
                    self.view.flash(enemy)
        elif kind == "party":
            self.party = msg
        elif kind == "character":
            self.sheet = msg
        elif kind == "notice":
            self.notice = (msg["code"], now + 3.0)

    async def session(self, port: int) -> None:
        port = self.port or port
        loop = asyncio.get_running_loop()
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", port, limit=wire.MAX_BYTES), 3)
            try:
                join = {"v": wire.VERSION, "type": "join", "resume": self.token}
                if self.character is not None and self.token is None:
                    join["character"] = self.character
                writer.write(wire.encode(join))
                hello = await wire.read(reader)
                if hello.get("type") == "refused":  # the server said why it would not take this character
                    wire.fields(hello, "refused", "code")
                    self.refused = str(hello["code"])[:32]
                    self.note(f"refused: {self.refused}")
                    raise wire.Invalid(f"refused ({self.refused})")
                check_welcome(hello, self.identity)
                self.player, self.token, self.phase = hello["player"], hello["resume"], "loading"
                self.note(f"welcome as P{self.player}")

                async def send() -> None:
                    due = loop.time()
                    while not writer.is_closing():  # (see below: a missed cancellation still ends here)
                        for request in self.requests:
                            writer.write(wire.encode(request))
                        self.requests.clear()
                        if self.phase == "playing" and self.shown == self.room and self.entity is not None:
                            # (no input while a room loads)
                            direction, action, tick = self.outgoing()
                            assert tick is not None  # (this window reckons the room's tick: Feedback)
                            self.seq += 1
                            self.prediction.sent(self.seq)
                            writer.write(wire.encode(wire.input_frame(self.entity, self.seq, *direction, tick, action,
                                                                      room=self.room)))
                        await asyncio.wait_for(writer.drain(), 2)
                        due = max(due + 1 / wire.HZ, loop.time())  # fixed schedule: no drift; after a stall, one extra send
                        await asyncio.sleep(due - loop.time())

                async def receive() -> None:
                    while True:
                        msg = await wire.read(reader)
                        check_frame(msg, self.identities)
                        self.on_frame(msg, loop.time())
                        self.status = self.caption()

                tasks = [asyncio.create_task(send()), asyncio.create_task(receive())]
                try:
                    done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        task.result()
                    self.status = "Disconnected (connection ended) | R resume / N new"  # (a loop ended quietly)
                finally:
                    # Close first, then wait. On Python 3.11 asyncio.wait_for can drop a cancellation that lands as
                    # its inner result arrives (fixed in 3.12), so a send or receive loop may run on after cancel():
                    # with the connection already closed, its next write or read ends it, and the server sees the
                    # player leave (hosted Windows, Extended 42978577824: F2 left the session sending forever).
                    self.note("closing")
                    writer.close()
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
            finally:
                writer.close()
                try:
                    await asyncio.wait_for(writer.wait_closed(), 2)
                except (OSError, TimeoutError):
                    writer.transport.abort()
                self.note("closed")
        except (OSError, EOFError, TimeoutError, wire.Invalid) as exc:
            self.note(f"session ended: {type(exc).__name__}")
            self.status = f"Disconnected ({reason(exc)}) | R resume / N new"
        except asyncio.CancelledError:
            self.note("session cancelled")
            raise
        finally:
            self.phase, self.room, self.pending = "disconnected", None, None
            self.blur()
            self.actions.clear()  # (the session they were pressed in is over: never sent in another)
            self.riders = None
            self.prediction.stop()
            self.requests.clear()

    def caption(self) -> str:
        label = self.defs[self.key].label if self.key else "?"
        party = self.party or {}
        if party.get("party"):
            names = ",".join(f"P{p}{'' if online else '(away)'}" for p, online, _ in party["members"])
            group = f"party {names} lead P{party['leader']}"
        else:
            group = "no party (P create, I invite)"
        invites = f" | invite from P{party['invites'][0][1]} Y/N" if party.get("invites") else ""
        notice = f" | {NOTICE_TEXT.get(self.notice[0], self.notice[0])}" if self.notice else ""
        sheet = self.sheet
        own = (f"{sheet['name']} ({sum(q for _, q in sheet['items'])} items, {len(sheet['unlocks'])} unlocks) | "
               if sheet else "")
        return f"{own}P{self.player} {label} | {group}{invites}{notice}"

    def draw(self, now: float) -> None:
        if self.refusal is not None and not self.connected:  # (over the disconnect's own caption, until it plays a room)
            self.status = f"Refused: {self.refusal} | N new"
        if self.notice and now > self.notice[1]:
            self.notice = None
            self.status = self.caption() if self.connected else self.status
        if self.pending is not None and self.pending["room"] == self.room and self.key is not None:
            # Single-player room memory (engine.scene_runtime.room_memory) would record this window's own edits (the
            # scene's player definition, which the view removes) as collected, as load_scene leaves a room, and leave
            # them out when it loads again (a return visit, or a resume into the room on screen). Here the server owns
            # every room's state: the room being left records nothing (no room path), and nothing recorded remains.
            self.window.scene_controller.room_path = None
            state = getattr(self.window, "game_state_controller", None)
            if state is not None:
                state.set_var(ROOM_MEMORY, {})
            self.window.load_scene(self.defs[self.key].path)  # the room the server put this player in
            self.loads.append(self.room)
            try:
                self.view = SceneView(self.window, self.arcade, self.defs[self.key].proto)
            except JoinRefused as exc:  # (HD-2D: this window would play the room differently): leave, never play it
                self.note(f"refused the room: {exc}")
                self.view, self.pending, self.refusal, self.request = None, None, str(exc), "disconnect"
                self.token = None  # (no resume back into that room; a retained character is refused there again)
                self.window.clear(color=(16, 16, 24))
                return
            self.shown, self.pending, self.last, self.phase, self.refusal = self.room, None, None, "playing", None
            if self.state is not None and self.entity is not None:  # (predicting from the latest row, nothing sent yet)
                self.prediction.start(self.defs[self.key].proto, self.state, self.entity)
        dt = 0.0 if self.last is None else min(0.1, now - self.last)
        self.last = now
        if self.view is None:
            self.window.clear(color=(16, 16, 24))
            return
        state = self.state if self.connected and self.shown == self.room else None
        positions = self.playback.positions(now) if state else {}
        if state and self.entity is not None and self.prediction.body is not None:
            positions[self.entity] = self.prediction.shown(dt)
        self.view.sync(state, positions, self.entity if state else None, dt)
        self.view.draw(dt)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=46870)
    parser.add_argument("--character", help="the key file of the character to play (N8: python -m "
                                            "mesh_net.characters create STORE NAME --key-file FILE)")
    args = parser.parse_args()
    character = read_character(args.character) if args.character else None
    with open_arena(expedition_files(), SIZE, WorldArena) as arena:
        arena.character = character
        asyncio.run(arena.run(args.port))


def read_character(path: str) -> dict[str, str]:
    """A character's key file: its id and access key (never shown)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("id"), str) or not isinstance(data.get("key"), str):
        raise SystemExit(f"{path} is not a character key file")
    return {"id": data["id"], "key": data["key"]}


if __name__ == "__main__":
    main()
