import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from engine.lighting import LightManager
from engine.scene_controller import SceneController

pytestmark = [pytest.mark.integration, pytest.mark.slow]

# Mock Window
class MockWindow:
    def __init__(self):
        self.width = 800
        self.height = 600
        self.scene_loader = MagicMock()
        # We initialize LightManager, but we'll patch its internals
        self.lighting = LightManager(self, enabled=True)
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

    def clear_ui_elements(self):
        pass

    def register_ui_element(self, element):
        pass

    def get_next_spawn_point(self):
        return None

    def clear_input_locks(self):
        pass

def test_lighting_contract_theme_implicit(mock_arcade_lighting, mock_arcade_window, mock_arcade_background):
    """
    Verify that loading a scene with a theme (and no explicit lights)
    correctly configures the LightManager with the theme's lighting hint.
    """
    window = MockWindow()
    mock_arcade_window.return_value = window

    # Force availability after patching
    window.lighting.available = True
    window.lighting._layer = MagicMock()

    with patch("engine.optional_arcade.arcade.SpriteList"):
        controller = SceneController(window)

    # Load the scene file content
    # We use the existing dev_sandbox scene which uses "moss" theme
    scene_path = "packs/dev_sandbox/scenes/encounter_group_test.json"
    real_path = Path("d:/Games/Mesh") / scene_path

    # Ensure file exists (it should in this workspace)
    if not real_path.exists():
        pytest.skip(f"Scene file not found: {real_path}")

    with open(real_path, "r") as f:
        scene_data = json.load(f)

    window.scene_loader.load_scene.return_value = scene_data

    # Load the scene
    controller.load_scene(scene_path)

    # Check snapshot
    snapshot = window.lighting.get_lighting_snapshot()

    # Verify the contract
    assert snapshot["enabled"] is True
    assert snapshot["light_count"] == 1

    light = snapshot["lights"][0]
    # "moss" theme -> "green_dim" hint -> specific config in SceneController
    # {"type": "ambient", "color": [50, 100, 50], "intensity": 0.4}
    assert light["type"] == "ambient"
    assert light["color"] == [50, 100, 50]
    assert light["intensity"] == 0.4

    # Verify that keys not in the config are not in the snapshot
    assert "x" not in light
    assert "y" not in light

def test_lighting_contract_explicit_lights(mock_arcade_lighting, mock_arcade_window, mock_arcade_background):
    """
    Verify that loading a scene with explicit lights overrides the theme.
    """
    window = MockWindow()
    mock_arcade_window.return_value = window

    window.lighting.available = True
    window.lighting._layer = MagicMock()

    with patch("engine.optional_arcade.arcade.SpriteList"):
        controller = SceneController(window)

    # Create a scene data with both theme and explicit lights
    scene_data = {
        "settings": {
            "region_theme": "moss"
        },
        "lights": [
            {"type": "point", "x": 100, "y": 100, "radius": 50, "color": [255, 255, 255]}
        ]
    }

    window.scene_loader.load_scene.return_value = scene_data

    controller.load_scene("dummy_path.json")

    snapshot = window.lighting.get_lighting_snapshot()

    assert snapshot["light_count"] == 1
    light = snapshot["lights"][0]

    # Should match explicit lights, NOT theme
    assert light["type"] == "point"
    assert light["x"] == 100
    assert light["y"] == 100
    assert light["color"] == [255, 255, 255]

def test_lighting_contract_occluders(mock_arcade_lighting, mock_arcade_window, mock_arcade_background):
    """
    Verify that loading a scene with occluders correctly populates the snapshot.
    """
    window = MockWindow()
    mock_arcade_window.return_value = window

    window.lighting.available = True
    window.lighting._layer = MagicMock()

    with patch("engine.optional_arcade.arcade.SpriteList"):
        controller = SceneController(window)

    # Create a scene data with occluders
    scene_data = {
        "settings": {},
        "occluders": [
            {"id": "wall1", "type": "rect", "x": 10, "y": 10, "width": 100, "height": 20},
            {"id": "poly1", "type": "poly", "points": [[0,0], [10,0], [5,10]]},
            {"type": "rect", "x": 200, "y": 200, "width": 50, "height": 50} # No ID
        ]
    }

    window.scene_loader.load_scene.return_value = scene_data

    controller.load_scene("dummy_occluders.json")

    snapshot = window.lighting.get_lighting_snapshot()

    assert "occluders" in snapshot
    assert snapshot["occluder_count"] == 3

    occluders = snapshot["occluders"]

    # Verify sorting: id/name -> type -> bbox
    # 1. "" (no id)
    # 2. "poly1"
    # 3. "wall1"

    assert occluders[0]["type"] == "rect"
    assert "id" not in occluders[0]
    assert occluders[0]["rect"] == [200, 200, 50, 50]

    assert occluders[1]["id"] == "poly1"
    assert occluders[1]["type"] == "poly"
    assert occluders[1]["points_count"] == 3
    assert occluders[1]["bbox"] == [0, 0, 10, 10]

    assert occluders[2]["id"] == "wall1"
    assert occluders[2]["type"] == "rect"
    assert occluders[2]["rect"] == [10, 10, 100, 20]

def test_lighting_contract_variant_e_occluders(mock_arcade_lighting, mock_arcade_window, mock_arcade_background):
    """
    Verify that Golden Slice Variant E actually contains occluders.
    """
    window = MockWindow()
    mock_arcade_window.return_value = window

    window.lighting.available = True
    window.lighting._layer = MagicMock()

    # Mock optional_arcade.arcade.get_window to return our mock window if needed, or patch SpriteList
    # But SceneController uses optional_arcade.arcade.SpriteList which needs a window context.
    # We can mock the layers to avoid real SpriteList creation.
    with patch("engine.optional_arcade.arcade.SpriteList"):
        controller = SceneController(window)
    controller.layers = {
        "background": MagicMock(),
        "entities": MagicMock(),
        "foreground": MagicMock(),
    }
    controller.solid_sprites = MagicMock()

    # Load the actual variant E scene file
    scene_path = "packs/core_regions/scenes/Ridge Outpost_dungeon_variant_e.json"
    real_path = Path("d:/Games/Mesh") / scene_path

    if not real_path.exists():
        pytest.skip(f"Scene file not found: {real_path}")

    with open(real_path, "r") as f:
        scene_data = json.load(f)

    window.scene_loader.load_scene.return_value = scene_data

    controller.load_scene(scene_path)

    snapshot = window.lighting.get_lighting_snapshot()

    assert "occluders" in snapshot
    assert snapshot["occluder_count"] >= 3

    # Check for specific IDs we added
    occluder_ids = [o.get("id") for o in snapshot["occluders"]]
    assert "hallway_wall" in occluder_ids
    assert "boss_pillar" in occluder_ids
    assert "corner_wedge" in occluder_ids
