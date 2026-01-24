from __future__ import annotations


def test_world_progression_check_main_world_reaches_milestones() -> None:
    from engine.tooling.world_progression import check_world_progression

    result = check_world_progression(
        "worlds/main_world.json",
        required_scene_paths=("scenes/cellar.json", "scenes/door_interior.json"),
    )
    assert result.ok is True
    assert result.start_scene_key == "door_field"
    assert "scenes/cellar.json" in result.required_scene_paths
    assert "scenes/door_interior.json" in result.required_scene_paths
    assert not result.missing_scene_paths

