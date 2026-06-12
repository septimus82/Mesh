"""Tests for Asset Spawn contract."""

from engine.asset_index import AssetRow
from engine.editor_asset_ops import spawn_entity_from_asset


def test_spawn_entity_from_asset_determinism(tmp_path):
    scene_json: dict = {"entities": {}}
    rel_path = "assets/sprites/char.png"
    pos = (100.0, 200.0)

    # First spawn
    scene_json, eid1 = spawn_entity_from_asset(scene_json, rel_path, pos)

    assert eid1 == "asset_char_1"
    assert eid1 in scene_json["entities"]
    entity = scene_json["entities"][eid1]
    assert entity["x"] == 100.0
    assert entity["y"] == 200.0
    assert entity["texture"] == rel_path

    # Second spawn (collision)
    scene_json, eid2 = spawn_entity_from_asset(scene_json, rel_path, pos)
    assert eid2 == "asset_char_2"
    assert eid2 in scene_json["entities"]
    assert len(scene_json["entities"]) == 2

def test_spawn_entity_sanitization():
    scene_json: dict = {"entities": {}}
    # Weird filename
    rel_path = "assets/weird-name!.png"

    _, eid = spawn_entity_from_asset(scene_json, rel_path, (0,0))
    # alphanumeric only in ID usually preferred
    assert eid.startswith("asset_weird_name_")

def test_editor_controller_integration(monkeypatch):
    """Test controller calls ops correctly."""
    from unittest.mock import MagicMock

    from engine.editor_controller import EditorModeController

    # Mock window and deps
    window = MagicMock()
    window.camera.position = (50.0, 50.0)

    scene_data = {"entities": {}}
    window.scene_controller._loaded_scene_data = scene_data

    # Mock AssetRow
    row = AssetRow(rel_path="assets/test.png", kind="image", display_name="test.png")

    controller = EditorModeController(window)
    # Inject filtered rows
    controller._asset_browser_filtered_rows = [row]
    controller.asset_browser_selection_index = 0

    # Act
    controller._activate_selected_asset()

    # Assert
    assert controller.scene_dirty is False
    assert controller.asset_place_active is True
    # Check toast
    window.player_hud.enqueue_toast.assert_called_with("Placement Mode: test.png")
    # Check NO scene reload yet
    window.scene_controller.reload_scene.assert_not_called()


def test_editor_controller_non_image(monkeypatch):
    from unittest.mock import MagicMock

    from engine.editor_controller import EditorModeController

    window = MagicMock()
    scene_data = {"entities": {}}
    window.scene_controller._loaded_scene_data = scene_data

    row = AssetRow(rel_path="assets/sound.wav", kind="audio", display_name="sound.wav")

    controller = EditorModeController(window)
    controller._asset_browser_filtered_rows = [row]
    controller.asset_browser_selection_index = 0

    controller._activate_selected_asset()

    # Should not act on scene
    assert controller.scene_dirty is False
    assert len(scene_data["entities"]) == 0
    # Should copy/toast
    window.player_hud.enqueue_toast.assert_called_with("Copied: assets/sound.wav")

