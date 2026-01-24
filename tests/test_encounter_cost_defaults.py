import pytest
from engine.prefabs import PrefabManager
from engine.encounter_cost import BOSS_COST_MULT, ELITE_COST_MULT, get_effective_encounter_cost

def test_encounter_cost_defaults():
    pm = PrefabManager()
    # Mock loading
    pm._prefabs = {
        "base": {"entity": {"encounter_cost": 5}},
        "default": {"entity": {}},
        "inherited": {"base": "base", "entity": {}},
        "override": {"base": "base", "entity": {"encounter_cost": 10}}
    }
    pm._loaded = True
    
    # Check explicit cost
    p1 = pm.get_prefab("base")
    assert p1["entity"]["encounter_cost"] == 5
    
    # Check default cost
    p2 = pm.get_prefab("default")
    assert p2["entity"].get("encounter_cost", 1) == 1

    # Check inherited cost
    p3 = pm.get_prefab("inherited")
    assert p3["entity"]["encounter_cost"] == 5

    # Check overridden cost
    p4 = pm.get_prefab("override")
    assert p4["entity"]["encounter_cost"] == 10
    pm = PrefabManager()
    pm._prefabs = {
        "base": {"entity": {"encounter_cost": 10}}
    }
    pm._variants = {
        "mult": {"cost_mult": 2.0},
        "add": {"cost_add": 5},
        "both": {"cost_mult": 0.5, "cost_add": 2}
    }
    pm._loaded = True
    
    # Mult
    v1 = pm.resolve_with_variant("base", "mult")
    assert v1["entity"]["encounter_cost"] == 20.0
    v2 = pm.resolve_with_variant("base", "add")
    assert v2["entity"]["encounter_cost"] == 15.0 # 10 * 1.0 + 5
    
    # Both
    v3 = pm.resolve_with_variant("base", "both")
    assert v3["entity"]["encounter_cost"] == 7.0 # 10 * 0.5 + 2


def test_encounter_cost_tiers_boss_overrides_elite() -> None:
    base = {"encounter_cost": 10}
    elite = {"encounter_cost": 10, "is_elite": True}
    boss = {"encounter_cost": 10, "is_boss": True}
    both = {"encounter_cost": 10, "is_elite": True, "is_boss": True}

    assert get_effective_encounter_cost(base) == 10
    assert get_effective_encounter_cost(elite) == 10 * ELITE_COST_MULT
    assert get_effective_encounter_cost(boss) == 10 * BOSS_COST_MULT
    assert get_effective_encounter_cost(both) == 10 * BOSS_COST_MULT
