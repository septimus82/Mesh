import json
import pytest
from pathlib import Path
from engine.inventory import load_item_database

def test_drop_table_tiers():
    # Load item db to check tiers
    db = load_item_database()
    
    # Helper to get tier
    def get_tier(item_id):
        item = db.items.get(item_id)
        if not item:
            return 0 # Unknown item
        return item.effects.get("tier", 0)

    # Define regions and allowed tiers
    regions = {
        "Ridge Outpost_dungeon.json": {"min": 1, "max": 1},
        "Hollow Grove_dungeon.json": {"min": 1, "max": 2},
        "Ashen_dungeon.json": {"min": 2, "max": 2}
    }
    
    base_path = Path("packs/core_regions/scenes")
    
    for scene_file, tier_range in regions.items():
        path = base_path / scene_file
        if not path.exists():
            continue
            
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        entities = data.get("entities", [])
        for ent in entities:
            behavious = ent.get("behaviours", [])
            if "DropTable" in behavious:
                config = ent.get("behaviour_config", {}).get("DropTable", {})
                drops = config.get("drops", [])
                
                # Allow bosses to drop items 1 tier higher
                name = str(ent.get("name") or ent.get("mesh_name") or "")
                is_boss = ("Boss" in name) or (ent.get("variant_id") == "boss") or bool(ent.get("is_boss"))
                allowed_max = tier_range["max"] + 1 if is_boss else tier_range["max"]
                
                for drop in drops:
                    item_id = drop.get("item_id")
                    if item_id:
                        tier = get_tier(item_id)
                        if tier > 0: # Ignore non-tiered items like potions
                            assert tier_range["min"] <= tier <= allowed_max, \
                                f"Item {item_id} (Tier {tier}) in {scene_file} is out of range {tier_range} (Boss={is_boss})"
