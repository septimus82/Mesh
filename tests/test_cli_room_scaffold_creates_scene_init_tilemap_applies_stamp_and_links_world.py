import json
from pathlib import Path

import mesh_cli


def test_cli_room_scaffold_creates_scene_init_tilemap_applies_stamp_and_links_world(tmp_path: Path, capsys) -> None:
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

    rc = mesh_cli.main(argv)
    out = capsys.readouterr().out
    assert rc == 0
    assert out.splitlines()[-1].startswith("ROOM_SCAFFOLD ok ")

    assert to_scene.exists()

    to_payload = json.loads(to_scene.read_text(encoding="utf-8"))
    tilemap = to_payload.get("tilemap")
    assert isinstance(tilemap, dict)
    assert tilemap.get("width") == 8
    assert tilemap.get("height") == 6

    layers = tilemap.get("tile_layers")
    assert isinstance(layers, list)
    ground = next((layer for layer in layers if isinstance(layer, dict) and layer.get("id") == "Ground"), None)
    assert isinstance(ground, dict)
    tiles = ground.get("tiles")
    assert isinstance(tiles, list)
    assert tiles[0] == 5
    assert tiles[1] == 5
    assert tiles[8] == 5
    assert tiles[9] == 5

    world_payload = json.loads(world_path.read_text(encoding="utf-8"))
    scenes_map = world_payload["scenes"]
    normalized_to_path = str(to_scene).replace("\\", "/")
    to_key = next(k for k, v in scenes_map.items() if v.get("path") == normalized_to_path)

    from_payload = json.loads(from_scene.read_text(encoding="utf-8"))
    entities = from_payload.get("entities")
    assert isinstance(entities, list)
    transition = next(e for e in entities if e.get("id") == f"from_transition_{to_key}_10_20_0_0")
    cfg = transition["behaviour_config"]["SceneTransition"]
    assert cfg["target_scene"] == to_key
    assert cfg["spawn_id"] == "to_entry"
    assert cfg["spawn_point"] == "to_entry"
