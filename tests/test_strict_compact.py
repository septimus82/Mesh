import pytest
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from engine.tooling.validate_all import UnifiedValidator


pytestmark = pytest.mark.builtin_behaviours

def test_strict_compact_failure(tmp_path):
    # Create a scene with redundant defaults
    scene_path = tmp_path / "redundant.json"
    scene_data = {
        "name": "Redundant Scene",
        "settings": {
            "background_color": "black", # Default
            "world_width": 2048, # Default
            "world_height": 2048 # Default
        },
        "layers": [
            { "name": "background" },
            { "name": "entities" },
            { "name": "foreground" }
        ], # Default
        "entities": []
    }
    with open(scene_path, "w") as f:
        json.dump(scene_data, f)
        
    validator = UnifiedValidator(tmp_path, strict_compact=True, check_events=False)
    
    # We need to mock SceneLoader and compact_scene_payload to behave realistically
    # OR we can rely on the actual implementation if it's importable.
    # Since we are testing the integration in validate_all, using real logic is better if possible.
    # But SceneLoader might need assets.
    # Let's try to use real logic but mock file system if needed.
    # Here we used tmp_path so file system is real.
    
    result = validator.validate_scene(scene_path)
    
    assert result is False
    assert any("is not compact" in err for err in validator.errors)
    # The error message might be "Settings key 'background_color' is redundant" instead of top-level
    # because "settings" key exists in both (if not empty), but content differs.
    # Wait, if settings is fully redundant, compact_scene_payload removes it.
    # So "settings" key is in original but not in compacted.
    # So it should hit "Top-level key 'settings' is redundant".
    
    # Let's print errors to debug if it fails
    print(validator.errors)
    
    assert any("Top-level key 'settings' is redundant" in err for err in validator.errors) or \
           any("Settings key" in err for err in validator.errors) or \
           any("Top-level key 'layers' is redundant" in err for err in validator.errors)

def test_strict_compact_success(tmp_path):
    # Create a compact scene
    scene_path = tmp_path / "compact.json"
    scene_data = {
        "name": "Compact Scene",
        "version": 1,
        "schema_version": 1
    }
    with open(scene_path, "w") as f:
        json.dump(scene_data, f)
        
    validator = UnifiedValidator(tmp_path, strict_compact=True, check_events=False)
    result = validator.validate_scene(scene_path)
    
    if not result:
        print("\nErrors:", validator.errors)
        with open(scene_path, "r") as f:
            print("Original:", json.load(f))

    assert result is True
    assert len(validator.errors) == 0
