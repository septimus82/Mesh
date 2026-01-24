import json
from pathlib import Path

import mesh_cli


def test_cli_world_add_scene_is_idempotent_and_normalizes_paths(tmp_path: Path) -> None:
    world_path = tmp_path / "world.json"
    world_path.write_text(json.dumps({"id": "w", "scenes": {}}), encoding="utf-8")

    rc = mesh_cli.main(
        [
            "world",
            "add-scene",
            str(world_path),
            "--key",
            "foo",
            "--path",
            r"scenes\foo.json",
        ]
    )
    assert rc == 0
    payload = json.loads(world_path.read_text(encoding="utf-8"))
    assert payload["scenes"]["foo"]["path"] == "scenes/foo.json"

    before = world_path.read_text(encoding="utf-8")
    rc2 = mesh_cli.main(
        [
            "world",
            "add-scene",
            str(world_path),
            "--key",
            "foo",
            "--path",
            r"scenes\foo.json",
        ]
    )
    assert rc2 == 0
    after = world_path.read_text(encoding="utf-8")
    assert after == before

