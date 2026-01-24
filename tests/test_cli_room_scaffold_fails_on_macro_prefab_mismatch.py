import json
from pathlib import Path

import mesh_cli


def test_cli_room_scaffold_fails_on_macro_prefab_mismatch(tmp_path: Path, capsys) -> None:
    world_path = tmp_path / "world.json"
    from_scene = tmp_path / "from.json"
    to_scene = tmp_path / "to_room.json"
    stamp_path = tmp_path / "stamp.json"
    macro_path = tmp_path / "objective_macro.json"

    # Cursor anchor resolves to the from-scene spawn point (10,20) in the scaffold command.
    # The objective_zone macro uses deterministic ids based on scene stem + zone_id + x/y.
    conflicting_id = "from_macro_triggerzone_z1_10_20_0_0"

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
                    },
                    {"id": conflicting_id, "prefab_id": "slime_blob", "x": 10.0, "y": 20.0},
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
                "width": 1,
                "height": 1,
                "tiles": [{"layer_id": "Ground", "x": 0, "y": 0, "w": 1, "h": 1, "tile": 5}],
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
                "id": "objective_z1",
                "type": "macro",
                "macro_id": "macro.objective_zone",
                "defaults": {"anchor": "cursor", "zone_id": "z1", "set_flag": "f1", "radius": 10},
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
        "4x4",
        "--tile",
        "16x16",
        "--layers",
        "Ground:0",
        "--spawn-id",
        "to_entry",
        "--anchor",
        "cursor",
    ]

    rc = mesh_cli.main(argv)
    out = capsys.readouterr().out
    assert rc == 1
    assert "prefab_mismatch" in out
    assert conflicting_id in out

