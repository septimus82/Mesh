from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

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


def test_lighting_occluders_override_precedence(mock_arcade_window, mock_arcade_background) -> None:
    window = _Window()
    mock_arcade_window.return_value = window
    with patch("arcade.SpriteList"), patch("arcade.sprite_list.SpriteList"), patch("arcade.gl.types.BufferDescription"):
        controller = SceneController(window)

    explicit = [{"id": "wall1", "type": "rect", "x": 10, "y": 10, "width": 20, "height": 30}]
    scene_data = {
        "settings": {},
        "tilemap": {
            "collision_layer_id": "platforms",
            "layers": [{"name": "ground", "z": -100}, {"name": "platforms", "z": -50}],
            "path": "assets/tilemaps/demo_map.json",
        },
        "entities": [],
        "occluders": explicit,
    }
    window.scene_loader.load_scene.return_value = scene_data

    with patch("engine.lighting.occluders.build_occluders_from_scene_payload") as builder:
        controller.load_scene("dummy_explicit_occluders.json")
        builder.assert_not_called()

    window.lighting.configure_scene_occluders.assert_called_with(explicit)
