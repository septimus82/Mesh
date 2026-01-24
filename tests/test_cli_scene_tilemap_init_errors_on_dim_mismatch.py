import json
from pathlib import Path

import mesh_cli


def test_cli_scene_tilemap_init_errors_on_dim_mismatch(tmp_path: Path, capsys):
    scene_path = tmp_path / "scene.json"
    scene_path.write_text(
        json.dumps(
            {
                "tilemap": {"width": 2, "height": 2, "tilewidth": 16, "tileheight": 16, "tile_layers": [{"id": "Ground", "z": -100, "tiles": [0, 0, 0, 0]}]},
                "entities": [],
            }
        ),
        encoding="utf-8",
    )

    rc = mesh_cli.main(
        [
            "scene",
            "tilemap",
            "init",
            str(scene_path),
            "--width",
            "3",
            "--height",
            "3",
            "--tile-w",
            "16",
            "--tile-h",
            "16",
            "--layer",
            "Ground:-100",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 1
    assert "use scene tilemap resize" in out

