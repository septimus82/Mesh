from __future__ import annotations

from engine.prefab_overrides import (
    compute_prefab_overrides,
    reset_all_prefab_overrides,
    reset_prefab_override,
)


def test_prefab_override_reset_single() -> None:
    prefab_base = {
        "behaviour_config": {"Health": {"hp": 10}},
    }
    entity = {
        "prefab_id": "p_guard",
        "x": 10,
        "y": 20,
        "behaviour_config": {"Health": {"hp": 3}},
    }
    changed = reset_prefab_override(entity, prefab_base, "behaviour_config.Health.hp")
    assert changed is True
    overrides = compute_prefab_overrides(entity, prefab_base)
    assert "behaviour_config.Health.hp" not in {o.field_path for o in overrides}
    assert entity["behaviour_config"]["Health"]["hp"] == 10
    assert entity["x"] == 10
    assert entity["y"] == 20


def test_prefab_override_reset_all() -> None:
    prefab_base = {
        "behaviour_config": {"Health": {"hp": 10}},
        "collision_poly": [[0, 0], [1, 0], [0, 1]],
    }
    entity = {
        "prefab_id": "p_guard",
        "x": 1,
        "y": 2,
        "behaviour_config": {"Health": {"hp": 4}, "AI": {"aggressive": True}},
        "collision_poly": [[0, 0], [2, 0], [0, 2]],
    }

    removed = reset_all_prefab_overrides(entity, prefab_base)
    assert removed >= 2
    overrides = compute_prefab_overrides(entity, prefab_base)
    paths = {o.field_path for o in overrides}
    assert "behaviour_config.Health.hp" not in paths
    assert "collision_poly" not in paths
    assert entity["x"] == 1
    assert entity["y"] == 2
