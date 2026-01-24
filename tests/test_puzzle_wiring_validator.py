import unittest
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from engine.tooling.validate_all import UnifiedValidator

class TestPuzzleWiringValidator(unittest.TestCase):
    def setUp(self):
        self.validator = UnifiedValidator(Path("."))
        self.validator.scene_loader = MagicMock()

    def test_valid_wiring(self):
        # Mock scene with valid wiring
        scene = {
            "entities": [
                {"id": "switch", "behaviours": {"SwitchInteract": {"event_id": "unlock_door"}}},
                {"id": "door", "behaviours": {"DoorLock": {"unlock_event": "unlock_door"}}}
            ]
        }
        self.validator.scene_loader.load_scene.return_value = scene
        
        ok = self.validator.validate_puzzle_wiring(Path("test_scene.json"))
        self.assertTrue(ok)
        self.assertEqual(len(self.validator.warnings), 0)
        self.assertEqual(len(self.validator.errors), 0)

    def test_missing_producer(self):
        # Mock scene with missing producer
        scene = {
            "entities": [
                {"id": "door", "behaviours": {"DoorLock": {"unlock_event": "unlock_door"}}}
            ]
        }
        self.validator.scene_loader.load_scene.return_value = scene
        
        ok = self.validator.validate_puzzle_wiring(Path("test_scene.json"))
        # Should be ok but with warning (default mode)
        self.assertTrue(ok)
        self.assertEqual(len(self.validator.warnings), 1)
        self.assertIn("listens to 'unlock_door' but no local SwitchInteract emits it", self.validator.warnings[0])

    def test_missing_producer_strict(self):
        # Mock scene with missing producer in strict mode
        self.validator.strict_compact = True
        scene = {
            "entities": [
                {"id": "door", "behaviours": {"DoorLock": {"unlock_event": "unlock_door"}}}
            ]
        }
        self.validator.scene_loader.load_scene.return_value = scene
        
        ok = self.validator.validate_puzzle_wiring(Path("test_scene.json"))
        self.assertFalse(ok)
        self.assertEqual(len(self.validator.errors), 1)
