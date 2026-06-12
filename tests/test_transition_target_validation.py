import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from engine.validators.transition_validator import TransitionValidator


class TestTransitionTargetValidation(unittest.TestCase):
    def setUp(self) -> None:
        self.test_dir = Path(tempfile.mkdtemp())
        self.world_path = self.test_dir / "world.json"
        self.scene1_path = self.test_dir / "scene1.json"
        self.scene2_path = self.test_dir / "scene2.json"

        # Basic world structure
        self.world_data = {
            "scenes": {
                "scene1": {"path": "scene1.json"},
                "scene2": {"path": "scene2.json"}
            }
        }

        # Basic scene structure
        self.scene_data = {
            "entities": []
        }

    def tearDown(self) -> None:
        shutil.rmtree(self.test_dir)

    def _write_json(self, path: Path, data: dict) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def test_valid_transitions(self) -> None:
        """Test that valid transitions pass validation."""
        # Scene 1 transitions to Scene 2 (by ID)
        scene1 = self.scene_data.copy()
        scene1["entities"] = [{
            "behaviours": {
                "SceneTransition": {"target_scene": "scene2"}
            }
        }]

        self._write_json(self.world_path, self.world_data)
        self._write_json(self.scene1_path, scene1)
        self._write_json(self.scene2_path, self.scene_data)

        with patch("engine.validators.transition_validator.resolve_path", side_effect=lambda p: self.test_dir / p):
            validator = TransitionValidator(strict=True)
            self.assertTrue(validator.validate(self.world_path))
            self.assertEqual(len(validator.errors), 0)

    def test_broken_transition_strict(self) -> None:
        """Test that broken transitions fail in strict mode."""
        # Scene 1 transitions to non-existent scene
        scene1 = self.scene_data.copy()
        scene1["entities"] = [{
            "behaviours": {
                "SceneTransition": {"target_scene": "non_existent_scene"}
            }
        }]

        self._write_json(self.world_path, self.world_data)
        self._write_json(self.scene1_path, scene1)
        self._write_json(self.scene2_path, self.scene_data)

        with patch("engine.validators.transition_validator.resolve_path", side_effect=lambda p: self.test_dir / p):
            validator = TransitionValidator(strict=True)
            self.assertFalse(validator.validate(self.world_path))
            self.assertIn("Scene 'scene1' has broken transition to 'non_existent_scene'", validator.errors)

    def test_broken_transition_non_strict(self) -> None:
        """Test that broken transitions warn in non-strict mode."""
        # Scene 1 transitions to non-existent scene
        scene1 = self.scene_data.copy()
        scene1["entities"] = [{
            "behaviours": {
                "SceneTransition": {"target_scene": "non_existent_scene"}
            }
        }]

        self._write_json(self.world_path, self.world_data)
        self._write_json(self.scene1_path, scene1)
        self._write_json(self.scene2_path, self.scene_data)

        with patch("engine.validators.transition_validator.resolve_path", side_effect=lambda p: self.test_dir / p):
            validator = TransitionValidator(strict=False)
            # Should return True (pass) but have warnings
            self.assertTrue(validator.validate(self.world_path))
            self.assertEqual(len(validator.errors), 0)
            self.assertIn("Scene 'scene1' has broken transition to 'non_existent_scene'", validator.warnings)

    def test_transition_by_path(self) -> None:
        """Test that transitions by file path are valid."""
        # Scene 1 transitions to Scene 2 (by path)
        scene1 = self.scene_data.copy()
        scene1["entities"] = [{
            "behaviours": {
                "SceneTransition": {"target_scene": "scene2.json"}
            }
        }]

        self._write_json(self.world_path, self.world_data)
        self._write_json(self.scene1_path, scene1)
        self._write_json(self.scene2_path, self.scene_data)

        with patch("engine.validators.transition_validator.resolve_path", side_effect=lambda p: self.test_dir / p):
            validator = TransitionValidator(strict=True)
            self.assertTrue(validator.validate(self.world_path))
