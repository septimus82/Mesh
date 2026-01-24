import json
from pathlib import Path

import mesh_cli


def test_cli_world_link_scenes_bidirectional_is_idempotent(tmp_path: Path) -> None:
    scene_a = tmp_path / "a.json"
    scene_b = tmp_path / "b.json"
    world_path = tmp_path / "world.json"

    scene_a.write_text(json.dumps({"name": "A", "entities": []}), encoding="utf-8")
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

    args = [
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
        "--bidirectional",
    ]

    rc = mesh_cli.main(args)
    assert rc == 0

    payload_a = json.loads(scene_a.read_text(encoding="utf-8"))
    payload_b = json.loads(scene_b.read_text(encoding="utf-8"))

    ent_a = next(e for e in payload_a["entities"] if e.get("id") == "a_transition_B_10_20_0_0")
    cfg_a = ent_a["behaviour_config"]["SceneTransition"]
    assert cfg_a["target_scene"] == "B"
    assert cfg_a["spawn_id"] == "spawn_b"

    ent_b = next(e for e in payload_b["entities"] if e.get("id") == "b_transition_A_30_40_0_0")
    cfg_b = ent_b["behaviour_config"]["SceneTransition"]
    assert cfg_b["target_scene"] == "A"
    assert cfg_b["spawn_id"] == "spawn_a"

    before_a = scene_a.read_text(encoding="utf-8")
    before_b = scene_b.read_text(encoding="utf-8")
    rc2 = mesh_cli.main(args)
    assert rc2 == 0
    after_a = scene_a.read_text(encoding="utf-8")
    after_b = scene_b.read_text(encoding="utf-8")
    assert after_a == before_a
    assert after_b == before_b

