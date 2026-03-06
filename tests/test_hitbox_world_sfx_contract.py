from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import engine.optional_arcade as optional_arcade
from engine.behaviours.health import Health
from engine.behaviours.hitbox import Hitbox

pytestmark = [pytest.mark.fast]


class _MockEntity(optional_arcade.arcade.Sprite):
    def __init__(self, name: str, *, tag: str = "", x: float = 0.0, y: float = 0.0) -> None:
        super().__init__()
        self.mesh_name = name
        self.mesh_tag = tag
        self.mesh_behaviours_runtime = []
        self.center_x = float(x)
        self.center_y = float(y)


def test_hitbox_damage_uses_world_sfx_helper() -> None:
    window = MagicMock()
    window.scene_controller = MagicMock()
    window.audio = MagicMock()

    hitbox_entity = _MockEntity("Hitbox", tag="player", x=0.0, y=0.0)
    hitbox = Hitbox(hitbox_entity, window, damage=2.0, target_tag="enemy", duration=1.0)

    target = _MockEntity("Target", tag="enemy", x=7.5, y=3.25)
    target.mesh_behaviours_runtime = [Health(target, window, max_hp=10.0, hp=10.0)]
    window.scene_controller.all_sprites = [hitbox_entity, target]

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            optional_arcade.arcade,
            "check_for_collision_with_list",
            lambda _sprite, _targets: [target],
        )
        hitbox.update(0.1)

    window.audio.play_world_sfx.assert_called_once_with(
        "assets/sounds/hit.wav",
        world_pos=(7.5, 3.25),
        window=window,
        base_volume=0.6,
        profile="melee",
    )
    window.audio.play_sound.assert_not_called()
