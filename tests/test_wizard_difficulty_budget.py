import pytest
from engine.tooling.scaffold import create_scene
from pathlib import Path
import json
import os

def test_wizard_difficulty_budget(tmp_path):
    scene_path = tmp_path / "test_dungeon.json"
    
    # Create scene with difficulty
    create_scene(
        str(scene_path),
        template_name="dungeon",
        extra_args={"difficulty": "hard"}
    )
    
    with open(scene_path, "r") as f:
        data = json.load(f)
        
    settings = data.get("settings", {})
    assert settings.get("encounter_budget_profile") == "hard"
    assert settings.get("encounter_budget") == 10 # Default for dungeon
