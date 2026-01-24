import json
from pathlib import Path

import mesh_cli


def test_cli_scene_tilemap_brush_idempotent(tmp_path: Path):
    scene_path = tmp_path / "scene.json"
    scene_path.write_text(
        json.dumps(
            {
                "tilemap": {"width": 4, "height": 3, "tile_layers": [{"id": "Ground", "z": -100, "tiles": [0] * 12}]},
                "entities": [],
            }
        ),
        encoding="utf-8",
    )

    brush_path = tmp_path / "brush.json"
    brush_path.write_text(
        json.dumps(
            {
                "id": "corner_ruins_a",
                "w": 3,
                "h": 3,
                "mask_tile": -1,
                "tiles": [[12, 13, 14], [15, -1, 16], [17, 18, 19]],
            }
        ),
        encoding="utf-8",
    )

    argv = [
        "scene",
        "tilemap",
        "brush",
        str(scene_path),
        "--layer-id",
        "Ground",
        "--brush",
        str(brush_path),
        "--x",
        "1",
        "--y",
        "0",
        "--anchor",
        "tl",
    ]

    rc = mesh_cli.main(argv)
    assert rc == 0
    before = scene_path.read_text(encoding="utf-8")

    rc2 = mesh_cli.main(argv)
    assert rc2 == 0
    after = scene_path.read_text(encoding="utf-8")
    assert after == before
