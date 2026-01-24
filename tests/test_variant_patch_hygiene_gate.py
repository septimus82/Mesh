import json
import pytest
from pathlib import Path
from engine.paths import resolve_path

def test_variant_patch_hygiene():
    """
    Enforce hygiene rules for variant patches:
    1. Must declare base_prefab_id (or explicit wildcard "*").
    2. Naming conventions for boss_/elite_ prefixes.
    3. Stat multiplier sanity checks.
    """
    # Locate the file - assuming core_regions for now as it's the main one
    path = resolve_path("packs/core_regions/data/variant_patches.json")
    if not path.exists():
        pytest.skip("core_regions variant_patches.json not found")
    
    with open(path, "r") as f:
        patches = json.load(f)
        
    for patch in patches:
        pid = patch.get("id")
        
        # 1. Base Prefab Declaration
        # User requirement: "Every patch must declare: base_prefab_id"
        # We accept "*" as a generic wildcard.
        assert "base_prefab_id" in patch, f"Patch '{pid}' missing 'base_prefab_id'. Use '*' for generic patches."
        
        # 2. Naming Conventions
        if pid.startswith("boss_"):
            tags = patch.get("tags_add", [])
            # Handle case where tags_add might be None or not a list (though schema usually enforces list)
            if not isinstance(tags, list):
                tags = []
            
            is_boss = patch.get("is_boss", False)
            has_tag = "boss" in tags
            assert has_tag or is_boss, f"Patch '{pid}' starts with 'boss_' but missing 'boss' tag or is_boss flag"
            
        if pid.startswith("elite_"):
            tags = patch.get("tags_add", [])
            if not isinstance(tags, list):
                tags = []
                
            is_elite = patch.get("is_elite", False)
            has_tag = "elite" in tags
            assert has_tag or is_elite, f"Patch '{pid}' starts with 'elite_' but missing 'elite' tag or is_elite flag"
            
        # 3. Stat Sanity
        # hp_mult, damage_mult, speed_mult > 0
        # ceiling 10x unless allow_extreme
        allow_extreme = patch.get("allow_extreme", False)
        
        for stat in ["hp_mult", "damage_mult", "speed_mult"]:
            if stat in patch:
                val = patch[stat]
                assert isinstance(val, (int, float)), f"Patch '{pid}' {stat} must be a number"
                assert val > 0, f"Patch '{pid}' {stat} must be > 0"
                if not allow_extreme:
                    assert val <= 10, f"Patch '{pid}' {stat} {val} exceeds limit 10 (set 'allow_extreme': true to bypass)"
