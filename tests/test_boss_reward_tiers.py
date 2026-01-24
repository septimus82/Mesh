import unittest
import json
from pathlib import Path

class TestBossRewardTiers(unittest.TestCase):
    def setUp(self):
        self.items_path = Path("assets/data/items.json")
        with open(self.items_path, "r", encoding="utf-8") as f:
            self.items_data = json.load(f)
        self.items = {item["id"]: item for item in self.items_data.get("items", [])}

    def load_scene(self, path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_boss_entity(self, scene_data, boss_name):
        for entity in scene_data.get("entities", []):
            if entity.get("name") == boss_name or entity.get("mesh_name") == boss_name:
                return entity
        return None

    def test_ridge_boss_rewards(self):
        scene_path = Path("packs/core_regions/scenes/Ridge Outpost_dungeon.json")
        scene = self.load_scene(scene_path)
        boss = self.get_boss_entity(scene, "Ridge_Boss")
        self.assertIsNotNone(boss, "Ridge_Boss not found")

        drop_table = boss.get("behaviour_config", {}).get("DropTable", {})
        drops = drop_table.get("drops", [])
        
        found_item = False
        for drop in drops:
            item_id = drop.get("item_id")
            if item_id == "warden_mace":
                found_item = True
                item = self.items.get(item_id)
                self.assertIsNotNone(item, "warden_mace not defined in items.json")
                tier = item.get("effects", {}).get("tier")
                self.assertEqual(tier, 2, "Ridge Boss item should be Tier 2")
        
        self.assertTrue(found_item, "Ridge Boss missing warden_mace drop")

    def test_hollow_boss_rewards(self):
        scene_path = Path("packs/core_regions/scenes/Hollow Grove_dungeon.json")
        scene = self.load_scene(scene_path)
        boss = self.get_boss_entity(scene, "Hollow_Boss")
        self.assertIsNotNone(boss, "Hollow_Boss not found")

        drop_table = boss.get("behaviour_config", {}).get("DropTable", {})
        drops = drop_table.get("drops", [])
        
        found_item = False
        for drop in drops:
            item_id = drop.get("item_id")
            if item_id == "shadow_blade":
                found_item = True
                item = self.items.get(item_id)
                self.assertIsNotNone(item, "shadow_blade not defined in items.json")
                tier = item.get("effects", {}).get("tier")
                self.assertEqual(tier, 3, "Hollow Boss item should be Tier 3")
        
        self.assertTrue(found_item, "Hollow Boss missing shadow_blade drop")

    def test_ashen_boss_rewards(self):
        scene_path = Path("packs/core_regions/scenes/Ashen_dungeon.json")
        scene = self.load_scene(scene_path)
        boss = self.get_boss_entity(scene, "Ashen_Boss")
        self.assertIsNotNone(boss, "Ashen_Boss not found")

        drop_table = boss.get("behaviour_config", {}).get("DropTable", {})
        drops = drop_table.get("drops", [])
        
        found_item = False
        for drop in drops:
            item_id = drop.get("item_id")
            if item_id == "cinder_staff":
                found_item = True
                item = self.items.get(item_id)
                self.assertIsNotNone(item, "cinder_staff not defined in items.json")
                tier = item.get("effects", {}).get("tier")
                self.assertEqual(tier, 3, "Ashen Boss item should be Tier 3")
        
        self.assertTrue(found_item, "Ashen Boss missing cinder_staff drop")

if __name__ == "__main__":
    unittest.main()
