"""A Mesh game window playing a scene hosted by ``python -m mesh_net.server --coop``.

Run ``python -m mesh_net.scene_client`` in two terminals. The room loads through the ordinary scene loader and
draws through the ordinary renderer and camera. The server owns every rule, so the window keeps only the
presentation behaviours (KEEP) and places what each snapshot says: one avatar per connected player, made from
the scene's player definition, plus the state of the gate, the lever, the enemy and its drop.
"""

from __future__ import annotations

import argparse
import asyncio
import math
from pathlib import Path
from typing import Any

from engine.interaction import DEFAULT_INTERACT_MAX_DIST

from . import protocol as wire
from .demo import Arena, open_arena
from .scene_room import SceneRoom, check_state, coop_files, parse_input

KEEP = ("Animator",)  # draws the picture the server's movement implies
FOLLOW = "CameraFollow"  # the local player's avatar keeps the scene's own camera behaviour
SIZE = (640, 360)
PEER_TINT = (255, 214, 140)
DROP_COLOR = (240, 200, 70, 255)
USED_TINT = (128, 128, 128)


class SceneView:
    """One room's presentation in a GameWindow: the loaded scene with only the presentation behaviours (KEEP), one
    avatar per player the server reports, and the gate, lever, enemy and drop states it sends. A world client
    (mesh_net.world_client) builds one per room it enters."""

    def __init__(self, window: Any, arcade: Any, room: SceneRoom) -> None:
        self.window, self.arcade = window, arcade
        self.identity = room.identity
        sc = self.scene = window.scene_controller
        sprites = [s for s in sc.all_sprites if getattr(s, "mesh_id", None)]
        if sorted(s.mesh_id for s in sprites) != room.ids:
            raise RuntimeError("the loaded room's objects differ from its scene file's")
        self.sprites = {s.mesh_id: s for s in sprites}
        template = next(s for s in sprites if getattr(s, "mesh_tag", None) == "player")
        self.template = dict(template.mesh_entity_data)
        sc.entities.enqueue_despawn(template)  # every player is an avatar the server reports, this one included
        del self.sprites[template.mesh_id]
        for sprite in self.sprites.values():
            self._keep(sprite, KEEP)
        sc.entities.apply_pending_ops(sc)
        self.doors, self.levers = sorted(room.doors), sorted(room.levers)
        self.colors = {i: tuple(self.sprites[i].color) for i in self.levers}
        self.avatars: dict[int, Any] = {}
        self.drops: dict[str, Any] = {}

    def check(self, msg: wire.Message) -> None:
        check_state(msg, self.identity)
        named = {*msg["open"], *msg["used"], *msg["drops"], *(r[0] for r in msg["enemies"]), *(r[0] for r in msg["loot"])}
        if not named <= self.sprites.keys():
            raise wire.Invalid("the server names objects this room does not have")

    def _keep(self, sprite: Any, names: tuple[str, ...]) -> None:
        sprite.mesh_behaviours = [b for b in sprite.mesh_behaviours if b in names]
        self.scene._rebuild_behaviours_for_sprite(sprite)

    def near_drop(self, x: float, y: float, state: wire.Message) -> bool:
        return any(math.hypot(x - self.sprites[i].center_x, y - self.sprites[i].center_y) <= DEFAULT_INTERACT_MAX_DIST
                   for i in state["drops"])

    def _spawn(self, eid: int, own: bool) -> Any:
        data = {**self.template, "id": f"net_player_{eid}", "name": f"Player {eid}"}
        sprite = self.scene._create_sprite(data)
        self._keep(sprite, KEEP + ((FOLLOW,) if own else ()))
        if not own:
            sprite.color = PEER_TINT
        self.scene.entities.enqueue_spawn(sprite, layer_name=data.get("layer") or "entities", is_solid=False)
        return sprite

    def sync(self, state: wire.Message | None, positions: dict[int, tuple[float, float]], own: int | None,
             dt: float) -> None:
        """Make the room look like ``state``, its players at ``positions`` (``own``: the local player's avatar)."""
        for eid in [e for e in self.avatars if e not in positions]:
            self.scene.entities.enqueue_despawn(self.avatars.pop(eid))
        for eid, (x, y) in positions.items():
            sprite = self.avatars.get(eid)
            if sprite is None:
                sprite = self.avatars[eid] = self._spawn(eid, eid == own)
                sprite.center_x, sprite.center_y = x, y
            vx, vy = ((x - sprite.center_x) / dt, (y - sprite.center_y) / dt) if dt > 0 else (0.0, 0.0)
            sprite.center_x, sprite.center_y = x, y
            sprite.mesh_velocity_x, sprite.mesh_velocity_y = vx, vy  # the Animator walks or stands by these
        if state is None:
            return
        for door in self.doors:
            self.sprites[door].visible = door not in state["open"]
        for lever in self.levers:
            self.sprites[lever].color = USED_TINT if lever in state["used"] else self.colors[lever]
        for enemy, hp in state["enemies"]:
            self.sprites[enemy].visible = hp > 0
        for enemy in [e for e in self.drops if e not in state["drops"]]:
            self.scene.entities.enqueue_despawn(self.drops.pop(enemy))
        for enemy in state["drops"]:
            if enemy not in self.drops:
                drop = self.drops[enemy] = self.arcade.SpriteCircle(6, DROP_COLOR)
                drop.center_x, drop.center_y = self.sprites[enemy].center_x, self.sprites[enemy].center_y
                drop.mesh_id = drop.mesh_name = f"drop:{enemy}"
                self.scene.entities.enqueue_spawn(drop, layer_name="entities", is_solid=False)

    def draw(self, dt: float) -> None:
        self.scene.entities.apply_pending_ops(self.scene)
        self.scene.update(dt)  # the kept behaviours: animation, and the local avatar's camera follow
        lighting = getattr(self.window, "lighting", None)
        if lighting is not None:
            lighting.update(dt)
        self.window.on_draw()


class SceneArena(Arena):
    def __init__(self, window: Any, arcade: Any, root: Path, scene: str) -> None:
        super().__init__(window, arcade)
        self.view = SceneView(window, arcade, SceneRoom(root / scene, root))  # what the server builds, from own files
        self.identity = self.view.identity
        self.checks = {"check": self.view.check, "check_input": parse_input}
        self.last: float | None = None

    # (the room's presentation, as tooling/net_scene_probe.py reads it)
    scene = property(lambda self: self.view.scene)
    sprites = property(lambda self: self.view.sprites)
    avatars = property(lambda self: self.view.avatars)
    drops = property(lambda self: self.view.drops)

    def press(self, symbol: int, modifiers: int) -> bool:
        client = self.client
        if symbol == self.arcade.key.E and client and symbol not in self.action_keys:
            self.action_keys.add(symbol)
            own = next(r for r in client.state["players"] if r[0] == client.entity)
            self.action = "take" if self.view.near_drop(own[1], own[2], client.state) else "use"
            return True
        return super().press(symbol, modifiers)

    def describe(self, state: wire.Message, entity: int) -> str:
        enemies = ", ".join(f"{self.sprites[i].mesh_name} {hp:g}" for i, hp in state["enemies"])
        loot = sum(1 for _, holder in state["loot"] if holder == entity)
        gate = "open" if state["open"] else "locked"
        return f"P{entity} | gate {gate} | {enemies} | loot {loot} | E use/take, Space attack, F2 leave"

    def draw(self, now: float) -> None:
        """Remote players two ticks behind, as Playback plays them; the local one where the server last put it."""
        dt = 0.0 if self.last is None else min(0.1, now - self.last)
        self.last = now
        client = self.client
        state = client.state if client else None
        positions = self.playback.positions(now) if state else {}
        if client and state:
            own = next(r for r in state["players"] if r[0] == client.entity)
            positions[own[0]] = (own[1], own[2])
        self.view.sync(state, positions, client.entity if client else None, dt)
        self.view.draw(dt)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=46870)
    args = parser.parse_args()
    with open_arena(coop_files(), SIZE, SceneArena) as arena:
        asyncio.run(arena.run(args.port))


if __name__ == "__main__":
    main()
