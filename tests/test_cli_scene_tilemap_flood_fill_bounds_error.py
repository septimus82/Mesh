import json
from pathlib import Path

import mesh_cli


def test_cli_scene_tilemap_flood_fill_errors_on_missing_dims(tmp_path: Path, capsys):
    scene_path = tmp_path / "scene.json"
    scene_path.write_text(json.dumps({"entities": [], "tilemap": {"tile_layers": [{"id": "Ground", "z": -100}]}}), encoding="utf-8")

    rc = mesh_cli.main(
        [
            "scene",
            "tilemap",
            "flood-fill",
            str(scene_path),
            "--layer-id",
            "Ground",
            "--x",
            "0",
            "--y",
            "0",
            "--tile",
            "1",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 1
    assert "dims_missing" in out


def test_cli_scene_tilemap_flood_fill_errors_on_out_of_bounds(tmp_path: Path, capsys):
    scene_path = tmp_path / "scene.json"
    scene_path.write_text(
        json.dumps(
            {
                "tilemap": {"width": 2, "height": 2, "tile_layers": [{"id": "Ground", "z": -100, "tiles": [0, 0, 0, 0]}]},
                "entities": [],
            }
        ),
        encoding="utf-8",
    )

    rc = mesh_cli.main(
        [
            "scene",
            "tilemap",
            "flood-fill",
            str(scene_path),
            "--layer-id",
            "Ground",
            "--x",
            "2",
            "--y",
            "0",
            "--tile",
            "1",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 1
    assert "out_of_bounds" in out


def test_cli_scene_tilemap_flood_fill_errors_on_max_tiles_exceeded_without_clip(tmp_path: Path, capsys):
    scene_path = tmp_path / "scene.json"
    w, h = 4, 4
    scene_path.write_text(
        json.dumps(
            {
                "tilemap": {"width": w, "height": h, "tile_layers": [{"id": "Ground", "z": -100, "tiles": [0] * (w * h)}]},
                "entities": [],
            }
        ),
        encoding="utf-8",
    )

    rc = mesh_cli.main(
        [
            "scene",
            "tilemap",
            "flood-fill",
            str(scene_path),
            "--layer-id",
            "Ground",
            "--x",
            "0",
            "--y",
            "0",
            "--tile",
            "1",
            "--max-tiles",
            "5",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 1
    assert "max_tiles_exceeded" in out

