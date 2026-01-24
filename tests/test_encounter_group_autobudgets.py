import pytest
import json
from pathlib import Path
from engine.tooling import scaffold

def test_autobudget_rounding(tmp_path):
    # Test with a budget that doesn't divide cleanly
    scene_path = tmp_path / "rounding.json"
    # Base budget 10.
    # Gauntlet: 33.3% -> 3.33.
    # Ints: 3, 3, 4.
    
    extra_args = {
        "encounter_layout": "gauntlet",
        "difficulty": "normal"
    }
    
    scaffold.create_scene(str(scene_path), template_name="dungeon", extra_args=extra_args)
    
    with open(scene_path, "r") as f:
        data = json.load(f)
        
    budgets = data["settings"]["encounter_group_budgets"]
    total = sum(budgets.values())
    assert total == 10
    assert budgets["wave_1"] == 3
    assert budgets["wave_2"] == 3
    assert budgets["wave_3"] == 4

def test_autobudget_large_numbers(tmp_path):
    # If we manually set a large budget in the template (simulated by modifying scaffold logic or just trusting the math)
    # But we can't easily change base budget from extra_args unless we pass it?
    # scaffold.py uses hardcoded 10 for dungeon.
    # But ruins uses 8.
    
    scene_path = tmp_path / "ruins_gauntlet.json"
    extra_args = {
        "encounter_layout": "gauntlet",
        "difficulty": "normal"
    }
    
    scaffold.create_scene(str(scene_path), template_name="ruins", extra_args=extra_args)
    
    with open(scene_path, "r") as f:
        data = json.load(f)
        
    budgets = data["settings"]["encounter_group_budgets"]
    # Base 8.
    # 8 * 0.333 = 2.664 -> 2.
    # Wave 1: 2. Wave 2: 2. Wave 3: 4.
    total = sum(budgets.values())
    assert total == 8
    assert budgets["wave_1"] == 2
    assert budgets["wave_2"] == 2
    assert budgets["wave_3"] == 4
