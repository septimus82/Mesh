"""Doors (SceneTransition), hitboxes and projectiles check their collisions sprite against sprite (their hit boxes),
never through a SpriteList made for the check: a SpriteList holds GPU buffers and a sprite keeps every list it joins,
so one per update grew the GPU's buffers and the player's ``sprite_lists`` without end (5 buffers an update while a
walk-in door was in the room)."""

from __future__ import annotations

from typing import Any

import pytest

import engine.optional_arcade as optional_arcade
from engine.behaviours.hitbox import Hitbox
from engine.behaviours.projectile import Projectile
from engine.behaviours.scene_transition import SceneTransition

pytestmark = pytest.mark.fast
arcade = optional_arcade.arcade


class StubSceneController:
    def __init__(self, sprites: list[Any]) -> None:
        self.all_sprites = sprites


class StubWindow:
    def __init__(self, sprites: list[Any]) -> None:
        self.scene_controller = StubSceneController(sprites)


def _sprite(tag: str, x: float = 0.0, y: float = 0.0, size: int = 32, angle: float = 0.0) -> Any:
    sprite = arcade.SpriteSolidColor(size, size, color=(255, 255, 255, 255))
    sprite.mesh_tag, sprite.mesh_behaviours_runtime = tag, []
    sprite.center_x, sprite.center_y, sprite.angle = x, y, angle
    return sprite


def _no_sprite_lists(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_: Any, **__: Any) -> Any:
        raise AssertionError("a SpriteList made for a collision check")

    monkeypatch.setattr(arcade, "SpriteList", refuse)
    monkeypatch.setattr(arcade, "check_for_collision_with_list", refuse)


def test_a_walk_in_door_checks_without_sprite_lists_and_the_player_keeps_none(monkeypatch: pytest.MonkeyPatch) -> None:
    door, player = _sprite("door"), _sprite("player", 500, 500)
    behaviour = SceneTransition(door, StubWindow([door, player]), target_scene="scenes/any.json", trigger_on_touch=True)
    before = len(player.sprite_lists)
    _no_sprite_lists(monkeypatch)
    for _ in range(1000):
        behaviour.update(1 / 60)
    assert len(player.sprite_lists) == before, "the player joins no list per update"


def test_hitboxes_and_projectiles_check_without_sprite_lists(monkeypatch: pytest.MonkeyPatch) -> None:
    hitbox_sprite, enemy = _sprite("hitbox"), _sprite("enemy", 500, 500)
    hitbox = Hitbox(hitbox_sprite, StubWindow([hitbox_sprite, enemy]), target_tag="enemy")
    shot, target = _sprite("projectile"), _sprite("player", 500, 500)
    projectile = Projectile(shot, StubWindow([shot, target]), target_tag="player", lifetime=100.0, speed=0.0)
    _no_sprite_lists(monkeypatch)
    for _ in range(200):
        hitbox.update(1 / 60)
        projectile.update(1 / 60)
    assert len(enemy.sprite_lists) == 0 and len(target.sprite_lists) == 0


def test_a_door_s_touch_is_its_hit_box_as_before() -> None:
    """A door turned 45 degrees: its hit box is a diamond inside a bigger bounding box. Where a small player touches
    it agrees, position by position, with arcade's list check (what the door used before)."""
    door = _sprite("door", 0, 0, size=64, angle=45)
    probe = arcade.SpriteList(lazy=True)  # lazy: no GPU, made once, for the comparison only
    seen = {True: 0, False: 0}
    for gx in range(-60, 61, 6):
        for gy in range(-60, 61, 6):
            player = _sprite("player", gx, gy, size=8)
            fired: list[Any] = []
            behaviour = SceneTransition(door, StubWindow([door, player]), target_scene="scenes/any.json",
                                        trigger_on_touch=True)
            setattr(behaviour, "_trigger_transition", lambda **kw: fired.append(kw))  # noqa: B010
            behaviour.update(1 / 60)
            probe.clear()
            probe.append(player)
            expected = bool(arcade.check_for_collision_with_list(door, probe))
            assert bool(fired) == expected, (gx, gy)
            seen[expected] += 1
            if fired:
                assert fired[0]["actor"] is player and fired[0]["reason"] == "collision"
    assert seen[True] > 20 and seen[False] > 20
    corner = _sprite("player", 40, 40, size=8)  # inside the bounding box, outside the diamond
    assert not arcade.check_for_collision(door, corner)


def test_a_door_never_touches_itself() -> None:
    """As arcade's list check did: a door tagged like its target (an odd setup) doesn't fire on its own box."""
    door = _sprite("player")
    fired: list[Any] = []
    behaviour = SceneTransition(door, StubWindow([door]), target_scene="scenes/any.json", trigger_on_touch=True)
    setattr(behaviour, "_trigger_transition", lambda **kw: fired.append(kw))  # noqa: B010
    behaviour.update(1 / 60)
    assert fired == []
