import json

from engine.tooling import scaffold


def test_wizard_layout_standard(tmp_path):
    scene_path = tmp_path / "standard.json"
    extra_args = {
        "encounter_layout": "standard",
        "difficulty": "normal" # Should imply budget 10 for dungeon
    }

    scaffold.create_scene(str(scene_path), template_name="dungeon", extra_args=extra_args)

    with open(scene_path, "r") as f:
        data = json.load(f)

    settings = data["settings"]
    budgets = settings.get("encounter_group_budgets")
    assert budgets is not None
    # Standard: 40% entry, 60% mid. Base 10.
    # Entry: 4, Mid: 6.
    assert budgets["entry"] == 4
    assert budgets["mid"] == 6

    # Check entities
    entities = data["entities"]
    groups = [e.get("encounter_group") for e in entities if e.get("prefab_id") == "theme_enemy_placeholder"]
    assert "entry" in groups
    assert "mid" in groups

def test_wizard_layout_bossed(tmp_path):
    scene_path = tmp_path / "bossed.json"
    extra_args = {
        "encounter_layout": "bossed",
        "difficulty": "normal"
    }

    scaffold.create_scene(str(scene_path), template_name="dungeon", extra_args=extra_args)

    with open(scene_path, "r") as f:
        data = json.load(f)

    settings = data["settings"]
    budgets = settings.get("encounter_group_budgets")
    # Bossed: 30%, 45%, 25%. Base 10.
    # Entry: 3. Mid: 4 (int(4.5)). Boss_guard: 3 (remainder: 10 - 3 - 4 = 3).
    assert budgets["entry"] == 3
    assert budgets["mid"] == 4
    assert budgets["boss_guard"] == 3

def test_wizard_layout_gauntlet(tmp_path):
    scene_path = tmp_path / "gauntlet.json"
    extra_args = {
        "encounter_layout": "gauntlet",
        "difficulty": "normal"
    }

    scaffold.create_scene(str(scene_path), template_name="dungeon", extra_args=extra_args)

    with open(scene_path, "r") as f:
        data = json.load(f)

    settings = data["settings"]
    budgets = settings.get("encounter_group_budgets")
    # Gauntlet: 33.3% each. Base 10.
    # Wave 1: 3. Wave 2: 3. Wave 3: 4 (remainder).
    assert budgets["wave_1"] == 3
    assert budgets["wave_2"] == 3
    assert budgets["wave_3"] == 4
