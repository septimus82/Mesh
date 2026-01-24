import unittest
from unittest.mock import patch

from engine.encounter_cost import get_effective_encounter_cost
from engine.prefabs import PrefabManager


class TestVariantIsEliteFlag(unittest.TestCase):
    @patch("engine.prefabs.PrefabManager.load")
    def test_variant_sets_is_elite(self, _mock_load):
        pm = PrefabManager()

        pm._prefabs = {
            "base_enemy": {
                "id": "base_enemy",
                "entity": {"encounter_cost": 1.0},
            }
        }
        pm._variants = {
            "elite_variant": {
                "is_elite": True,
                "cost_mult": 2.0,
                "tags_add": ["elite"],
            }
        }

        result = pm.resolve_with_variant("base_enemy", "elite_variant")
        assert result is not None

        self.assertTrue(result["entity"].get("is_elite"))
        self.assertEqual(get_effective_encounter_cost(result), 2.0)

    @patch("engine.prefabs.PrefabManager.load")
    def test_variant_default_is_not_elite(self, _mock_load):
        pm = PrefabManager()
        pm._prefabs = {
            "base_enemy": {
                "id": "base_enemy",
                "entity": {"encounter_cost": 1.0},
            }
        }
        pm._variants = {
            "normal_variant": {
                "cost_mult": 1.0,
            }
        }

        result = pm.resolve_with_variant("base_enemy", "normal_variant")
        assert result is not None

        self.assertFalse(bool(result["entity"].get("is_elite")))
        self.assertEqual(get_effective_encounter_cost(result), 1.0)


if __name__ == "__main__":
    unittest.main()

