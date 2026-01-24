from __future__ import annotations

import json
from pathlib import Path


def test_cli_scene_add_placeholder_inserts_entity_and_is_idempotent(tmp_path: Path, capsys) -> None:
    import mesh_cli

    scene_path = tmp_path / "demo_scene.json"
    scene_path.write_text(
        json.dumps(
            {
                "name": "Demo Scene",
                "schema_version": 1,
                "version": 1,
                "settings": {},
                "entities": [],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    code = mesh_cli.main(["scene", "add-placeholder", str(scene_path), "--x", "10", "--y", "20"])
    capsys.readouterr()
    assert code == 0

    payload = json.loads(scene_path.read_text(encoding="utf-8"))
    entities = payload.get("entities")
    assert isinstance(entities, list)
    assert len(entities) == 1
    entity = entities[0]
    assert entity.get("prefab_id") == "theme_enemy_placeholder"
    assert entity.get("x") == 10.0
    assert entity.get("y") == 20.0
    assert entity.get("id") == "demo_scene_themedenemy_10_20_0_0"

    # Re-run: deterministic id already exists => no-op (no duplicate)
    code2 = mesh_cli.main(["scene", "add-placeholder", str(scene_path), "--x", "10", "--y", "20"])
    capsys.readouterr()
    assert code2 == 0

    payload2 = json.loads(scene_path.read_text(encoding="utf-8"))
    entities2 = payload2.get("entities")
    assert isinstance(entities2, list)
    assert len(entities2) == 1
    assert entities2[0].get("id") == "demo_scene_themedenemy_10_20_0_0"

