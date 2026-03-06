from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import engine.optional_arcade as optional_arcade
from engine.behaviours.combat import Combat

pytestmark = [pytest.mark.fast]


class _MockEntity(optional_arcade.arcade.Sprite):
    def __init__(self, name: str, *, tag: str = "", x: float = 0.0, y: float = 0.0) -> None:
        super().__init__()
        self.mesh_name = name
        self.mesh_tag = tag
        self.mesh_behaviours_runtime = []
        self.center_x = float(x)
        self.center_y = float(y)


def test_high_frequency_world_attack_sfx_uses_world_sfx_helper() -> None:
    window = MagicMock()
    window.scene_controller = MagicMock()
    window.scene_controller._create_sprite.return_value = None
    window.audio = MagicMock()

    entity = _MockEntity("Player", tag="player", x=9.0, y=-4.0)
    combat = Combat(entity, window, cooldown=1.0, attack_sound="assets/sounds/attack.wav")

    assert combat.attack() is True
    window.audio.play_world_sfx.assert_called_once_with(
        "assets/sounds/attack.wav",
        world_pos=(9.0, -4.0),
        window=window,
        base_volume=0.5,
        profile="attack",
    )
    window.audio.play_sound.assert_not_called()
