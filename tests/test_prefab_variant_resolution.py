import pytest
from unittest.mock import patch, MagicMock
from engine.prefabs import PrefabManager

@pytest.fixture
def prefab_manager():
    return PrefabManager()

def test_load_variants(prefab_manager):
    mock_variants = [
        {
            "id": "test_variant",
            "hp_mult": 1.5,
            "tags_add": ["variant"]
        }
    ]
    
    with patch("engine.paths.resolve_path") as mock_resolve:
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.read_text.return_value = str(mock_variants).replace("'", '"')
        
        # We need to handle multiple calls to resolve_path (prefabs.json and variant_patches.json)
        # But PrefabManager.load() calls resolve_path("assets/prefabs.json") first.
        # Let's just mock the variants loading part by patching json.loads or similar if needed,
        # or better, just rely on the fact that it tries to load from a specific path.
        
        # Actually, let's just manually inject variants for unit testing logic
        prefab_manager._variants = {v["id"]: v for v in mock_variants}
        prefab_manager._loaded = True
        
        variant = prefab_manager.get_variant("test_variant")
        assert variant is not None
        assert variant["hp_mult"] == 1.5

def test_resolve_with_variant_not_found(prefab_manager):
    prefab_manager._prefabs = {"p1": {"id": "p1", "entity": {"name": "Base"}}}
    prefab_manager._variants = {}
    prefab_manager._loaded = True
    
    # Should return base if variant not found
    resolved = prefab_manager.resolve_with_variant("p1", "missing_variant")
    assert resolved["entity"]["name"] == "Base"
    
    # Clear cache to force reload of new prefabs
    prefab_manager._resolved_cache.clear()
    prefab_manager._resolved_variant_cache.clear()
    
    prefab_manager._prefabs = {
        "p1": {
            "id": "p1", 
            "entity": {
                "name": "Base",
                "tags": ["base"],
                "Health": {"max_health": 100, "current_health": 100},
                "Combat": {"damage": 10},
                "Movement": {"speed": 5.0}
            }
        }
    }
    prefab_manager._variants = {
        "v1": {
            "id": "v1",
            "hp_mult": 2.0,
            "damage_mult": 0.5,
            "speed_mult": 1.2,
            "tags_add": ["added"],
            "tags_remove": ["base"],
            "sprite_override": "new_sprite.png"
        }
    }
    prefab_manager._loaded = True
    
    resolved = prefab_manager.resolve_with_variant("p1", "v1")
    
    assert resolved["entity"]["name"] == "Base"
    assert resolved["entity"]["sprite"] == "new_sprite.png"
    assert "added" in resolved["tags"]
    assert "base" not in resolved["tags"]
    assert resolved["entity"]["Health"]["max_health"] == 200
    assert resolved["entity"]["Combat"]["damage"] == 5
    assert resolved["entity"]["Movement"]["speed"] == 6.0

def test_resolve_with_variant_caching(prefab_manager):
    prefab_manager._prefabs = {"p1": {"id": "p1", "entity": {"name": "Base"}}}
    prefab_manager._variants = {"v1": {"id": "v1", "tags_add": ["v1"]}}
    prefab_manager._loaded = True
    
    # First call
    r1 = prefab_manager.resolve_with_variant("p1", "v1")
    assert "v1" in r1["tags"]
    
    # Modify cache to verify it's used
    prefab_manager._resolved_variant_cache["p1|v1"] = {"name": "Cached"}
    
    r2 = prefab_manager.resolve_with_variant("p1", "v1")
    assert r2["name"] == "Cached"
