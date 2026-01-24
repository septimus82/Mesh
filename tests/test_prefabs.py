import json
import unittest
from unittest.mock import MagicMock, patch

from engine.prefabs import PrefabManager
from engine.validators.prefab_validator import PrefabValidator


class TestPrefabManager(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = PrefabManager()
        # Mock data
        self.mock_prefabs = {
            "base_enemy": {
                "id": "base_enemy",
                "tags": ["enemy"],
                "entity": {
                    "sprite": "base.png",
                    "Health": {"max_health": 10}
                }
            },
            "goblin": {
                "id": "goblin",
                "base": "base_enemy",
                "entity": {
                    "sprite": "goblin.png",
                    "Health": {"max_health": 15}
                }
            },
            "elite_goblin": {
                "id": "elite_goblin",
                "base": "goblin",
                "tags": ["elite"],
                "entity": {
                    "Health": {"max_health": 30}
                }
            }
        }
        self.mock_variants = {
            "v_strong": {
                "id": "v_strong",
                "hp_mult": 2.0,
                "tags_add": ["strong"]
            }
        }
        
        # Inject mock data
        self.manager._prefabs = self.mock_prefabs
        self.manager._variants = self.mock_variants
        self.manager._loaded = True

    def test_inheritance_resolution(self) -> None:
        # Test base
        base = self.manager.get_prefab("base_enemy")
        self.assertEqual(base["entity"]["Health"]["max_health"], 10)
        self.assertEqual(base["entity"]["sprite"], "base.png")
        
        # Test level 1 inheritance
        goblin = self.manager.get_prefab("goblin")
        self.assertEqual(goblin["entity"]["Health"]["max_health"], 15) # Overridden
        self.assertEqual(goblin["entity"]["sprite"], "goblin.png") # Overridden
        self.assertIn("enemy", goblin["tags"]) # Inherited
        
        # Test level 2 inheritance
        elite = self.manager.get_prefab("elite_goblin")
        self.assertEqual(elite["entity"]["Health"]["max_health"], 30)
        self.assertEqual(elite["entity"]["sprite"], "goblin.png") # Inherited from goblin
        self.assertIn("enemy", elite["tags"]) # Inherited from base
        self.assertIn("elite", elite["tags"]) # Added

    def test_variant_resolution(self) -> None:
        # Test variant application
        variant = self.manager.resolve_with_variant("goblin", "v_strong")
        
        # HP should be 15 * 2.0 = 30
        self.assertEqual(variant["entity"]["Health"]["max_health"], 30)
        
        # Tags should include added tag
        self.assertIn("strong", variant["tags"])
        self.assertIn("enemy", variant["tags"])

    def test_caching(self) -> None:
        # First call
        p1 = self.manager.get_prefab("goblin")
        # Second call
        p2 = self.manager.get_prefab("goblin")
        
        self.assertIs(p1, p2) # Should be same object from cache
        
        # Variant caching
        v1 = self.manager.resolve_with_variant("goblin", "v_strong")
        v2 = self.manager.resolve_with_variant("goblin", "v_strong")
        self.assertIs(v1, v2)

    def test_unknown_prefab(self) -> None:
        self.assertEqual(self.manager.get_prefab("unknown"), {})



class TestPrefabValidator(unittest.TestCase):
    @patch("engine.validators.prefab_validator.resolve_path")
    def test_validate_valid(self, mock_resolve):
        # Setup side effects for resolve_path
        def side_effect(path_str):
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            if "prefabs.json" in path_str:
                mock_path.read_text.return_value = json.dumps([
                    {"id": "p1", "entity": {}}
                ])
            elif "encounter_sets.json" in path_str:
                mock_path.read_text.return_value = json.dumps({
                    "encounter_sets": [
                        {"id": "es1", "enemy_prefab_ids": ["p1"]}
                    ]
                })
            return mock_path
            
        mock_resolve.side_effect = side_effect

        validator = PrefabValidator()
        self.assertTrue(validator.validate())
        self.assertEqual(len(validator.errors), 0)

    @patch("engine.validators.prefab_validator.resolve_path")
    def test_validate_duplicate(self, mock_resolve):
        def side_effect(path_str):
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            if "prefabs.json" in path_str:
                mock_path.read_text.return_value = json.dumps([
                    {"id": "p1", "entity": {}},
                    {"id": "p1", "entity": {}}
                ])
            elif "encounter_sets.json" in path_str:
                mock_path.read_text.return_value = json.dumps({"encounter_sets": []})
            return mock_path
            
        mock_resolve.side_effect = side_effect

        validator = PrefabValidator()
        self.assertFalse(validator.validate())
        self.assertIn("Duplicate prefab ID: 'p1'", validator.errors)

if __name__ == "__main__":
    unittest.main()
