from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

from engine.lighting.occluders import OCCLUDER_CACHE
from engine.scene_controller import SceneController


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


def test_occluder_cache_invalidation_on_tilemap_clear(mock_arcade_window, mock_arcade_background) -> None:
    window = _Window()
    mock_arcade_window.return_value = window

    with patch("arcade.SpriteList"), patch("arcade.sprite_list.SpriteList"), patch("arcade.gl.types.BufferDescription"):
        controller = SceneController(window)

    OCCLUDER_CACHE.scene_path = "scenes/test.json"
    OCCLUDER_CACHE.revision = 123
    OCCLUDER_CACHE.value = [{"id": "cached"}]

    controller._tilemap_background_layers = [MagicMock()]
    controller._tilemap_foreground_layers = [MagicMock()]
    controller.tilemap_instance = MagicMock()
    controller.tilemap_instance.collision_sprites = MagicMock()

    controller._clear_tilemap_layers()

    assert OCCLUDER_CACHE.scene_path is None
    assert OCCLUDER_CACHE.revision == -1
    assert OCCLUDER_CACHE.value is None
