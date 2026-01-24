import json
from pathlib import Path

import mesh_cli


def test_cli_room_scaffold_idempotent_no_diffs_on_rerun(tmp_path: Path, capsys) -> None:
    world_path = tmp_path / "world.json"
    from_scene = tmp_path / "from.json"
    to_scene = tmp_path / "to_room.json"
    stamp_path = tmp_path / "stamp.json"
    macro_path = tmp_path / "door_macro.json"

    from_scene.write_text(
        json.dumps(
            {
                "name": "From",
                "entities": [
                    {
                        "id": "from_spawn_10_20",
                        "tag": "spawn_point",
                        "spawn_id": "from_spawn",
                        "x": 10.0,
                        "y": 20.0,
                        "layer": "background",
                        "name": "from_spawn",
                        "behaviours": [],
                    }
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    world_path.write_text(
        json.dumps(
            {
                "id": "w",
                "start_scene": "from",
                "start_spawn": "from_spawn",
                "scenes": {"from": {"path": str(from_scene)}},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    stamp_path.write_text(
        json.dumps(
            {
                "id": "demo_stamp",
                "width": 2,
                "height": 2,
                "tiles": [{"layer_id": "Ground", "x": 0, "y": 0, "w": 2, "h": 2, "tile": 5}],
                "entities": [],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    macro_path.write_text(
        json.dumps(
            {
                "id": "door",
                "type": "macro",
                "macro_id": "macro.door_transition",
                "defaults": {"anchor": "player", "target_scene": "IGNORED", "spawn_id": "IGNORED"},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    argv = [
        "room",
        "scaffold",
        "--world",
        str(world_path),
        "--from-scene",
        str(from_scene),
        "--door-macro",
        str(macro_path),
        "--to-scene",
        str(to_scene),
        "--to-stamp",
        str(stamp_path),
        "--grid",
        "8x6",
        "--tile",
        "16x16",
        "--layers",
        "Ground:0",
        "--spawn-id",
        "to_entry",
        "--stamp-origin",
        "0,0",
        "--anchor",
        "cursor",
    ]

    assert mesh_cli.main(argv) == 0
    capsys.readouterr()

    before_world = world_path.read_text(encoding="utf-8")
    before_from = from_scene.read_text(encoding="utf-8")
    before_to = to_scene.read_text(encoding="utf-8")

    assert mesh_cli.main(argv) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[-1] == "ROOM_SCAFFOLD noop reason=no_changes"

    assert world_path.read_text(encoding="utf-8") == before_world
    assert from_scene.read_text(encoding="utf-8") == before_from
    assert to_scene.read_text(encoding="utf-8") == before_to

