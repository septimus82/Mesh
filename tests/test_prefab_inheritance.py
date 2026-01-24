import unittest
from engine.prefabs import PrefabManager

class TestPrefabInheritance(unittest.TestCase):
    def setUp(self):
        self.manager = PrefabManager()
        # Inject test data directly
        self.manager._prefabs = {
            "base_unit": {
                "id": "base_unit",
                "entity": {
                    "sprite": "base.png",
                    "health": 100,
                    "speed": 10
                }
            },
            "soldier": {
                "id": "soldier",
                "base": "base_unit",
                "entity": {
                    "sprite": "soldier.png",
                    "damage": 10
                }
            },
            "elite_soldier": {
                "id": "elite_soldier",
                "base": "soldier",
                "entity": {
                    "health": 200,
                    "sprite": None  # Should inherit soldier.png, not base.png
                }
            },
            "ghost": {
                "id": "ghost",
                "base": "base_unit",
                "entity": {
                    "sprite": None, # Should inherit base.png
                    "speed": 20
                }
            }
        }
        self.manager._loaded = True

    def test_basic_inheritance(self):
        # Resolve soldier
        resolved = self.manager.get_prefab("soldier")
        entity = resolved["entity"]
        self.assertEqual(entity["sprite"], "soldier.png")
        self.assertEqual(entity["health"], 100) # Inherited
        self.assertEqual(entity["damage"], 10) # Added
        self.assertEqual(entity["speed"], 10) # Inherited

    def test_deep_inheritance(self):
        # Resolve elite_soldier -> soldier -> base_unit
        resolved = self.manager.get_prefab("elite_soldier")
        entity = resolved["entity"]
        self.assertEqual(entity["health"], 200) # Overridden
        self.assertEqual(entity["damage"], 10) # Inherited from soldier
        self.assertEqual(entity["speed"], 10) # Inherited from base_unit
        self.assertEqual(entity["sprite"], "soldier.png") # Inherited from soldier (closest)

    def test_sprite_none_handling(self):
        # Ghost has sprite: None, should inherit base.png
        resolved = self.manager.get_prefab("ghost")
        entity = resolved["entity"]
        self.assertEqual(entity["sprite"], "base.png")
        self.assertEqual(entity["speed"], 20)

    def test_entity_override(self):
        # Resolve soldier with entity override
        entity_data = {
            "prefab_id": "soldier",
            "x": 50,
            "health": 150
        }
        resolved = self.manager.resolve(entity_data)
        self.assertEqual(resolved["sprite"], "soldier.png")
        self.assertEqual(resolved["health"], 150) # Entity override
        self.assertEqual(resolved["damage"], 10) # Prefab value
        self.assertEqual(resolved["x"], 50)

if __name__ == "__main__":
    unittest.main()
