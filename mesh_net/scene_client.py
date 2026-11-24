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

from engine.animation_state import request_animation_state
from engine.behaviours.combat import _try_rumble
from engine.interaction import DEFAULT_INTERACT_MAX_DIST

from . import protocol as wire
from .demo import Arena, open_arena
from .scene_room import Feedback, Prediction, SceneRoom, check_progress, check_state, coop_files, parse_input

KEEP = ("Animator",)  # draws the picture the server's movement implies
FOLLOW = "CameraFollow"  # the local player's avatar keeps the scene's own camera behaviour
SIZE = (640, 360)
PEER_TINT = (255, 214, 140)
DROP_COLOR = (240, 200, 70, 255)
USED_TINT = (128, 128, 128)
FLASH_TINT = (255, 96, 96)  # an enemy the server confirms hit, for FLASH_S
FLASH_S = 0.15
HIT_SOUND = "assets/sounds/hit.wav"  # (engine.behaviours.hitbox's, as are its volume and profile)


class JoinRefused(RuntimeError):
    """This window can't join the room: it would play it differently from the server (check_window_world)."""


def check_window_world(window: Any, room: SceneRoom) -> None:
    """The join guard for an HD-2D room (M1-A-2): this window plays it only on the collision world the server runs.

    The room's identity already holds the collision digest of what this client's own files build (SceneRoom), which
    the server's must match; but the window's own build can still fall back to 2D (engine.hd2d.runtime.configure_scene:
    a texture missing, the driver refusing) or differ. So the window joins only with a World (``hd2d_world``, no
    ``hd2d_error``) whose digest is the room's. A 2D room needs nothing."""
    if room.digest is None:
        return
    world, error = getattr(window, "hd2d_world", None), getattr(window, "hd2d_error", None)
    if world is None or error:
        raise JoinRefused(f"this window plays the HD-2D room in 2D ({error or 'no collision world'}): it can't join "
                          "a room the server runs on 3D floors")
    if world.collision_digest() != room.digest:
        raise JoinRefused("this window's HD-2D collision world differs from the room the server runs")


class SceneView:
    """One room's presentation in a GameWindow: the loaded scene with only the presentation behaviours (KEEP), one
    avatar per player the server reports, and the gate, lever, enemy and drop states it sends. A world client
    (mesh_net.world_client) builds one per room it enters."""

    def __init__(self, window: Any, arcade: Any, room: SceneRoom) -> None:
        check_window_world(window, room)  # (before anything changes in the window)
        self.window, self.arcade = window, arcade
        self.room, self.identity = room, room.identity
        sc = self.scene = window.scene_controller
        sprites = [s for s in sc.all_sprites if getattr(s, "mesh_id", None)]
        loaded = sorted(s.mesh_id for s in sprites)
        if loaded != room.ids:
            raise RuntimeError(f"the loaded room's objects differ from its scene file's: missing "
                               f"{sorted(set(room.ids) - set(loaded))}, extra {sorted(set(loaded) - set(room.ids))}")
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
        self.enemy_colors = {i: tuple(self.sprites[i].color) for i in room.enemies}
        self.flashes: dict[str, float] = {}  # enemy -> seconds of its hit flash left

    def check(self, msg: wire.Message) -> None:
        check_state(msg, self.identity, self.room)
        named = {*msg["open"], *msg["used"], *msg["drops"], *(r[0] for r in msg["enemies"]), *(r[0] for r in msg["loot"])}
        if not named <= self.sprites.keys():
            raise wire.Invalid("the server names objects this room does not have")

    def _keep(self, sprite: Any, names: tuple[str, ...]) -> None:
        sprite.mesh_behaviours = [b for b in sprite.mesh_behaviours if b in names]
        self.scene._rebuild_behaviours_for_sprite(sprite)

    def near_drop(self, x: float, y: float, state: wire.Message) -> bool:
        return any(math.hypot(x - self.sprites[i].center_x, y - self.sprites[i].center_y) <= DEFAULT_INTERACT_MAX_DIST
                   for i in state["drops"])

    def swing(self, eid: int, own: bool) -> None:
        """Combat.attack's presentation on the avatar of ``eid``: its attack animation and sound, and for the local
        player (``own``) the rumble. Presentation only: whether it hits, the server says (``flash``)."""
        sprite = self.avatars.get(eid)
        if sprite is None:
            return
        if getattr(sprite, "mesh_animator", None):
            request_animation_state(sprite, str(self.room.combat["attack_anim"]), priority=10, ttl=0.5)
        audio = getattr(self.window, "audio", None)
        if audio is not None:
            audio.play_world_sfx(str(self.room.combat["attack_sound"]), world_pos=(float(sprite.center_x),
                                 float(sprite.center_y)), window=self.window, base_volume=0.5, profile="attack")
        if own:
            _try_rumble(self.window, 0.2, 0.03)

    def flash(self, enemy: str) -> None:
        """A hit the server confirmed (the enemy's hit count rose): the enemy flashes and the Hitbox's hit sound plays."""
        sprite = self.sprites[enemy]
        sprite.color = FLASH_TINT
        self.flashes[enemy] = FLASH_S
        audio = getattr(self.window, "audio", None)
        if audio is not None:
            audio.play_world_sfx(HIT_SOUND, world_pos=(float(sprite.center_x), float(sprite.center_y)),
                                 window=self.window, base_volume=0.6, profile="melee")

    def _spawn(self, eid: int, own: bool) -> Any:
        data = {**self.template, "id": f"net_player_{eid}", "name": f"Player {eid}"}
        sprite = self.scene._create_sprite(data)
        self._keep(sprite, KEEP + ((FOLLOW,) if own else ()))
        if not own:
            sprite.color = PEER_TINT
        self.scene.entities.enqueue_spawn(sprite, layer_name=data.get("layer") or "entities", is_solid=False)
        return sprite

    def sync(self, state: wire.Message | None, positions: dict[int, tuple[float, float, float, str | None]],
             own: int | None, dt: float) -> None:
        """Make the room look like ``state``, its players at ``positions`` (x, y, elevation, floor: a snapshot row's,
        mesh_net.protocol) (``own``: the local player's avatar)."""
        for enemy in list(self.flashes):
            self.flashes[enemy] -= dt
            if self.flashes[enemy] <= 0:
                del self.flashes[enemy]
                self.sprites[enemy].color = self.enemy_colors[enemy]
        for eid in [e for e in self.avatars if e not in positions]:
            self.scene.entities.enqueue_despawn(self.avatars.pop(eid))
        for eid, (x, y, elevation, floor) in positions.items():
            sprite = self.avatars.get(eid)
            if sprite is None:
                sprite = self.avatars[eid] = self._spawn(eid, eid == own)
                sprite.center_x, sprite.center_y = x, y
            vx, vy = ((x - sprite.center_x) / dt, (y - sprite.center_y) / dt) if dt > 0 else (0.0, 0.0)
            sprite.center_x, sprite.center_y = x, y
            sprite.mesh_velocity_x, sprite.mesh_velocity_y = vx, vy  # the Animator walks or stands by these
            if self.room.world is not None:  # HD-2D: where the server stands it (what the renderer draws from)
                sprite.mesh_entity_data["elevation"] = elevation
                sprite.mesh_hd2d_floor = floor
        renderer = getattr(self.window, "hd2d_renderer", None)
        if renderer is not None:  # (every frame: a room change or a resume brings a new renderer and avatar)
            renderer.camera_target = self.avatars.get(own) if own is not None else None
        if state is None:
            return
        for door in self.doors:
            self.sprites[door].visible = door not in state["open"]
        for lever in self.levers:
            self.sprites[lever].color = USED_TINT if lever in state["used"] else self.colors[lever]
        for enemy, hp, *_ in state["enemies"]:  # (its hit count and placement: Feedback; M4-4 moves it)
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
        renderer = getattr(self.window, "hd2d_renderer", None)
        if renderer is not None:  # (single-player's tick does this: the HD-2D camera moves toward its target)
            renderer.update(dt)
        lighting = getattr(self.window, "lighting", None)
        if lighting is not None:
            lighting.update(dt)
        self.window.on_draw()


class SceneArena(Arena):
    feedback: Feedback
    prediction: Prediction

    def __init__(self, window: Any, arcade: Any, root: Path, scene: str) -> None:
        super().__init__(window, arcade)
        self.view = SceneView(window, arcade, SceneRoom(root / scene, root))  # what the server builds, from own files
        self.identity = self.view.identity
        self.checks = {"check": self.view.check, "check_input": parse_input, "progress": check_progress}
        self.feedback = Feedback()
        self.prediction = Prediction()
        self.last: float | None = None

    # (the room's presentation, as tooling/net_scene_probe.py reads it)
    scene = property(lambda self: self.view.scene)
    sprites = property(lambda self: self.view.sprites)
    avatars = property(lambda self: self.view.avatars)
    drops = property(lambda self: self.view.drops)

    def press(self, symbol: int, modifiers: int) -> bool:
        client = self.client
        if symbol == self.arcade.key.SPACE and client and symbol not in self.action_keys:
            self.action_keys.add(symbol)
            tick = self.feedback.press(self.clock())  # (in the cooldown: no swing, and nothing sent)
            if tick is not None:
                self.act("attack", tick)  # the server judges its cooldown on this tick, as the window did
                self.view.swing(client.entity, own=True)  # at once: the server confirms only a hit
            return True
        if symbol == self.arcade.key.E and client and symbol not in self.action_keys:
            self.action_keys.add(symbol)
            # (where the window shows itself: the server runs it from there, Prediction)
            body = self.prediction.body
            own = next(r for r in client.state["players"] if r[0] == client.entity)
            x, y = (body.center_x, body.center_y) if body else (own[1], own[2])
            self.act("take" if self.view.near_drop(x, y, client.state) else "use")
            return True
        return super().press(symbol, modifiers)

    def on_state(self, state: wire.Message, entity: int, fresh: bool) -> None:
        """Others' swings and every hit, as the server's counters confirm them, and the own avatar reconciled; a
        welcome is a new baseline, and a new prediction."""
        if fresh:
            self.feedback.baseline(state, self.view.room.cooldown, self.clock())
            self.prediction.start(self.view.room, state, entity)
            return
        self.prediction.reconcile(state, entity)
        swung, hit = self.feedback.update(state, entity, self.clock())
        for eid in swung:
            self.view.swing(eid, own=False)
        for enemy in hit:
            self.view.flash(enemy)

    def describe(self, state: wire.Message, entity: int) -> str:
        enemies = ", ".join(f"{self.sprites[r[0]].mesh_name} {r[1]:g}" for r in state["enemies"])
        loot = sum(1 for _, holder in state["loot"] if holder == entity)
        gate = "open" if state["open"] else "locked"
        return f"P{entity} | gate {gate} | {enemies} | loot {loot} | E use/take, Space attack, F2 leave"

    def draw(self, now: float) -> None:
        """Remote players two ticks behind, as Playback plays them; the local one where it predicts itself."""
        dt = 0.0 if self.last is None else min(0.1, now - self.last)
        self.last = now
        client = self.client
        state = client.state if client else None
        positions = self.playback.positions(now) if state else {}
        if client and state and self.prediction.body is not None:
            positions[client.entity] = self.prediction.shown(dt)
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
