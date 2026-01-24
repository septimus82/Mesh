import unittest
from engine.prefabs import PrefabManager

class TestPrefabInheritanceCycles(unittest.TestCase):
    def setUp(self):
        self.manager = PrefabManager()
        self.manager._loaded = True

    def test_direct_cycle(self):
        self.manager._prefabs = {
            "A": {"id": "A", "base": "B", "entity": {}},
            "B": {"id": "B", "base": "A", "entity": {}}
        }
        # Should return None and log error (or raise if we changed implementation, but current impl catches RecursionError and returns None)
        resolved = self.manager.get_prefab("A")
        self.assertIsNone(resolved)

    def test_self_cycle(self):
        self.manager._prefabs = {
            "A": {"id": "A", "base": "A", "entity": {}}
        }
        resolved = self.manager.get_prefab("A")
        self.assertIsNone(resolved)

    def test_indirect_cycle(self):
        self.manager._prefabs = {
            "A": {"id": "A", "base": "B", "entity": {}},
            "B": {"id": "B", "base": "C", "entity": {}},
            "C": {"id": "C", "base": "A", "entity": {}}
        }
        resolved = self.manager.get_prefab("A")
        self.assertIsNone(resolved)

    def test_missing_base(self):
        self.manager._prefabs = {
            "A": {"id": "A", "base": "Missing", "entity": {"x": 1}}
        }
        # Should return empty dict or partial?
        # Implementation returns {} if base is missing.
        # Wait, if base is missing, _resolve_inheritance returns {}.
        # Then get_prefab returns {}.
        # Wait, if base is missing, _resolve_inheritance calls _prefabs.get("Missing") which is None.
        # Then it returns {}.
        # Then A merges {} with its entity.
        # So it should return A's entity.
        
        # Let's check implementation:
        # prefab_def = self._prefabs.get(prefab_id) -> Gets A
        # base_id = "Missing"
        # if base_id:
        #   base_entity = self._resolve_inheritance("Missing") -> Returns {} because _prefabs.get("Missing") is None
        #   merged = base_entity.copy() -> {}
        #   merge A's entity over {}
        #   return merged
        
        resolved = self.manager.get_prefab("A")
        self.assertEqual(resolved["entity"]["x"], 1)

    def test_max_depth(self):
        # Create a chain of 25 prefabs
        prefabs = {}
        for i in range(25):
            prefabs[f"P{i}"] = {
                "id": f"P{i}",
                "base": f"P{i+1}" if i < 24 else None,
                "entity": {"val": i}
            }
        self.manager._prefabs = prefabs
        
        # P0 -> P1 -> ... -> P24
        # Depth 24. Max is 20.
        resolved = self.manager.get_prefab("P0")
        self.assertIsNone(resolved)

if __name__ == "__main__":
    unittest.main()
