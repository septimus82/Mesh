from __future__ import annotations

from engine.prefab_overrides import compute_prefab_overrides


def test_prefab_override_diff_is_stable() -> None:
    prefab_base = {
        "sprite": "base.png",
        "behaviour_config": {"Health": {"hp": 10, "regen": 1}},
        "collision_poly": [[0, 0], [1, 0], [0, 1]],
    }
    entity = {
        "prefab_id": "p_guard",
        "x": 5,
        "y": 6,
        "behaviour_config": {
            "Health": {"hp": 5, "regen": 1},
            "AI": {"aggressive": True},
        },
        "collision_poly": [[0, 0], [2, 0], [0, 2]],
    }

    overrides = compute_prefab_overrides(entity, prefab_base)
    paths = [o.field_path for o in overrides]
    assert paths == sorted(paths)
    assert "behaviour_config.Health.hp" in paths
    assert "behaviour_config.AI.aggressive" in paths
    assert "collision_poly" in paths
    assert "x" not in paths
    assert "y" not in paths
