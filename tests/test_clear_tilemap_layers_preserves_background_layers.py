from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from engine.background_layers import BackgroundLayer
from engine.scene_controller import SceneController

pytestmark = [pytest.mark.integration, pytest.mark.slow]


class _Window:
    def __init__(self) -> None:
        self.width = 800
        self.height = 600
        self.scene_loader = MagicMock()
        self.lighting = MagicMock()
        self.world_width = 0
        self.world_height = 0
        self.ui_controller = MagicMock()
        self.camera_controller = MagicMock()
        self.audio = MagicMock()
        self.quest_manager = MagicMock()
        self.game_state = MagicMock()
        self.input_controller = MagicMock()
        self.ctx = MagicMock()
        self.assets = MagicMock()
        self.player_hud = MagicMock()

    def clear_ui_elements(self) -> None:
        return None

    def register_ui_element(self, _element) -> None:  # noqa: ANN001
        return None

    def get_next_spawn_point(self):  # noqa: ANN001
        return None

    def clear_input_locks(self) -> None:
        return None


def test_clear_tilemap_layers_preserves_scene_background_layers(
    mock_arcade_window, mock_arcade_background
) -> None:
    """Regression: _clear_tilemap_layers must NOT wipe scene-level parallax layers.

    load_scene parses scene.background_layers, then clears tilemap state; an
    earlier bug reset self._background_layers inside _clear_tilemap_layers, which
    blanked the parallax backdrop on every load.
    """
    window = _Window()
    mock_arcade_window.return_value = window

    with patch("arcade.SpriteList"), patch("arcade.sprite_list.SpriteList"), patch(
        "arcade.gl.types.BufferDescription"
    ):
        controller = SceneController(window)

    parallax = [BackgroundLayer(id="ground", path="ground.png", z=0, parallax=1.0)]
    controller._background_layers = parallax

    # Tilemap-owned layers SHOULD be wiped by the clear.
    controller._tilemap_background_layers = [MagicMock()]
    controller._tilemap_foreground_layers = [MagicMock()]
    controller.tilemap_instance = MagicMock()
    controller.tilemap_instance.collision_sprites = MagicMock()

    controller._clear_tilemap_layers()

    # Scene-level parallax layers survive untouched...
    assert controller._background_layers is parallax
    assert [layer.id for layer in controller._background_layers] == ["ground"]
    # ...while tilemap-owned draw state is reset.
    assert controller._tilemap_background_layers == []
    assert controller._tilemap_foreground_layers == []
    assert controller.tilemap_instance is None
