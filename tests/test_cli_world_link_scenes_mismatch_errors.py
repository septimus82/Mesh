import json
from pathlib import Path

import mesh_cli


def test_cli_world_link_scenes_errors_on_mismatch(tmp_path: Path, capsys) -> None:
    scene_a = tmp_path / "a.json"
    scene_b = tmp_path / "b.json"
    world_path = tmp_path / "world.json"

    scene_a.write_text(
        json.dumps(
            {
                "name": "A",
                "entities": [
                    {
                        "id": "a_transition_B_10_20_0_0",
                        "name": "TransitionTo_B",
                        "tag": "trigger",
                        "x": 10.0,
                        "y": 20.0,
                        "behaviours": [{"type": "SceneTransition", "params": {}}],
                        "behaviour_config": {"SceneTransition": {"target_scene": "NOT_B", "spawn_id": "spawn_b"}},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    scene_b.write_text(json.dumps({"name": "B", "entities": []}), encoding="utf-8")
    world_path.write_text(
        json.dumps(
            {
                "id": "w",
                "scenes": {
                    "A": {"path": str(scene_a)},
                    "B": {"path": str(scene_b)},
                },
            }
        ),
        encoding="utf-8",
    )

    before_a = scene_a.read_text(encoding="utf-8")
    rc = mesh_cli.main(
        [
            "world",
            "link-scenes",
            str(world_path),
            "--from-key",
            "A",
            "--to-key",
            "B",
            "--from-scene",
            str(scene_a),
            "--to-scene",
            str(scene_b),
            "--from-x",
            "10",
            "--from-y",
            "20",
            "--to-x",
            "30",
            "--to-y",
            "40",
            "--from-spawn",
            "spawn_a",
            "--to-spawn",
            "spawn_b",
        ]
    )
    assert rc == 1
    out = capsys.readouterr().out
    assert "SceneTransition.target_scene" in out
    assert scene_a.read_text(encoding="utf-8") == before_a

