import json
from pathlib import Path

import mesh_cli


def test_cli_scene_tilemap_fill_rect_errors_on_invalid_rect(tmp_path: Path, capsys):
    scene_path = tmp_path / "scene.json"
    scene_path.write_text(
        json.dumps(
            {
                "tilemap": {"width": 2, "height": 2, "tile_layers": [{"id": "Ground", "z": -100}]},
                "entities": [],
            }
        ),
        encoding="utf-8",
    )

    rc = mesh_cli.main(
        [
            "scene",
            "tilemap",
            "fill-rect",
            str(scene_path),
            "--layer-id",
            "Ground",
            "--x0",
            "1",
            "--y0",
            "0",
            "--x1",
            "0",
            "--y1",
            "0",
            "--tile",
            "3",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 2
    assert "x0<=x1" in out


def test_cli_scene_tilemap_fill_rect_errors_on_missing_layer(tmp_path: Path):
    scene_path = tmp_path / "scene.json"
    scene_path.write_text(
        json.dumps(
            {
                "tilemap": {"width": 2, "height": 2, "tile_layers": [{"id": "Ground", "z": -100}]},
                "entities": [],
            }
        ),
        encoding="utf-8",
    )

    rc = mesh_cli.main(
        [
            "scene",
            "tilemap",
            "fill-rect",
            str(scene_path),
            "--layer-id",
            "Missing",
            "--x0",
            "0",
            "--y0",
            "0",
            "--x1",
            "0",
            "--y1",
            "0",
            "--tile",
            "3",
        ]
    )
    assert rc == 1


def test_cli_scene_tilemap_fill_rect_errors_on_out_of_bounds(tmp_path: Path):
    scene_path = tmp_path / "scene.json"
    scene_path.write_text(
        json.dumps(
            {
                "tilemap": {"width": 2, "height": 2, "tile_layers": [{"id": "Ground", "z": -100}]},
                "entities": [],
            }
        ),
        encoding="utf-8",
    )

    rc = mesh_cli.main(
        [
            "scene",
            "tilemap",
            "fill-rect",
            str(scene_path),
            "--layer-id",
            "Ground",
            "--x0",
            "0",
            "--y0",
            "0",
            "--x1",
            "2",
            "--y1",
            "0",
            "--tile",
            "3",
        ]
    )
    assert rc == 1


def test_cli_scene_tilemap_fill_rect_errors_on_missing_dims(tmp_path: Path, capsys):
    scene_path = tmp_path / "scene.json"
    scene_path.write_text(json.dumps({"tilemap": {"tile_layers": [{"id": "Ground", "z": -100}]} , "entities": []}), encoding="utf-8")

    rc = mesh_cli.main(
        [
            "scene",
            "tilemap",
            "fill-rect",
            str(scene_path),
            "--layer-id",
            "Ground",
            "--x0",
            "0",
            "--y0",
            "0",
            "--x1",
            "0",
            "--y1",
            "0",
            "--tile",
            "1",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 1
    assert "cannot determine tilemap dimensions" in out

