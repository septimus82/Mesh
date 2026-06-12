from pathlib import Path
from unittest.mock import MagicMock, patch

from engine.tooling.validate_all import UnifiedValidator


def test_validate_all_world_success():
    # Mock dependencies
    with patch("engine.tooling.validate_all.SceneLoader") as MockLoader, \
         patch("engine.tooling.validate_all.EventValidator") as MockEventValidator:

        mock_loader = MockLoader.return_value
        mock_loader.validate_scene_file.return_value.ok = True
        mock_loader.validate_scene_file.return_value.errors = []
        mock_loader.validate_scene_file.return_value.warnings = []

        mock_ev = MockEventValidator.return_value
        mock_ev.errors = []
        mock_ev.warnings = []

        validator = UnifiedValidator(Path("."))

        # Mock world data
        world_data = {
            "scenes": {
                "test_scene": {"path": "scenes/test_scene.json"}
            }
        }

        # Mock file existence
        with patch("pathlib.Path.exists", return_value=True), \
             patch.object(validator, "validate_puzzle_wiring", return_value=True), \
             patch("builtins.open", new_callable=MagicMock) as mock_open:

             mock_file = mock_open.return_value.__enter__.return_value
             mock_file.read.return_value = "{}"

             # We need to mock open() but validate_world calls validate_scene which calls validate_scene_file
             # validate_scene_file is mocked.
             # validate_world also checks existence of scene paths.

             result = validator.validate_world(Path("worlds/test_world.json"), world_data)
             assert result is True
             assert len(validator.errors) == 0

def test_validate_all_scene_failure():
    with patch("engine.tooling.validate_all.SceneLoader") as MockLoader:
        mock_loader = MockLoader.return_value
        mock_loader.validate_scene_file.return_value.ok = False
        mock_loader.validate_scene_file.return_value.errors = ["Invalid entity"]

        validator = UnifiedValidator(Path("."))

        with patch("builtins.open", new_callable=MagicMock) as mock_open:
            mock_file = mock_open.return_value.__enter__.return_value
            mock_file.read.return_value = "{}"
            result = validator.validate_scene(Path("scenes/bad_scene.json"))

            assert result is False
            assert "Scene scenes\\bad_scene.json: Invalid entity" in validator.errors or \
                   "Scene scenes/bad_scene.json: Invalid entity" in validator.errors

def test_validate_all_events_failure():
    with patch("engine.tooling.validate_all.EventValidator") as MockEventValidator:
        mock_ev = MockEventValidator.return_value
        mock_ev.errors = ["Undefined event 'boom'"]

        validator = UnifiedValidator(Path("."))
        # Mock world data with no scenes to skip scene validation part
        world_data = {"scenes": {}}

        result = validator.validate_world(Path("worlds/test.json"), world_data)

        assert result is False
        assert "Undefined event 'boom'" in validator.errors
