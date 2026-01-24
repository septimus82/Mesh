from __future__ import annotations

import json


def test_spawn_placeholder_safety_validator_main_world_passes() -> None:
    import mesh_cli

    from engine.validators.spawn_placeholder_safety_validator import validate_spawn_placeholder_safety

    scene_paths = mesh_cli._resolve_scene_paths("worlds/main_world.json")
    payload = validate_spawn_placeholder_safety(scene_paths, min_dist=48.0)
    assert payload["ok"] is True
    assert payload["issues"] == []


def test_spawn_placeholder_safety_validator_reports_overlap_with_player(tmp_path) -> None:
    from engine.validators.spawn_placeholder_safety_validator import validate_spawn_placeholder_safety

    scene_path = tmp_path / "unsafe_scene.json"
    scene_path.write_text(
        json.dumps(
            {
                "name": "UnsafeScene",
                "entities": [
                    {"id": "player", "name": "Player", "tag": "player", "x": 100.0, "y": 100.0, "behaviours": []},
                    {
                        "id": "placeholder",
                        "name": "ThemedEnemy",
                        "prefab_id": "theme_enemy_placeholder",
                        "x": 100.0,
                        "y": 100.0,
                        "behaviours": [],
                    },
                ],
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    payload = validate_spawn_placeholder_safety([str(scene_path)], min_dist=48.0)
    assert payload["ok"] is False
    issues = payload["issues"]
    assert isinstance(issues, list) and len(issues) >= 1
    assert any(
        (i.get("placeholder_id") == "placeholder" and i.get("reason") == "near_player_start")
        for i in issues
        if isinstance(i, dict)
    )

