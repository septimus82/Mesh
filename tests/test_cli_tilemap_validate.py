import json
from pathlib import Path

import mesh_cli


def test_cli_tilemap_validate_ok(tmp_path: Path, capsys):
    map_path = tmp_path / "map.json"
    map_path.write_text(json.dumps({"width": 2, "height": 2}), encoding="utf-8")

    scene_path = tmp_path / "scene.json"
    scene_path.write_text(
        json.dumps(
            {
                "tilemap": {
                    "path": str(map_path),
                    "tile_layers": [
                        {"id": "Ground", "z": -100, "parallax": 1.0, "tiles": [0, 0, 0, 0]},
                        {"id": "Clouds", "z": -200, "parallax": 0.5, "tiles": [0, 0, 0, 0]},
                    ],
                }
            }
        ),
        encoding="utf-8",
    )

    rc = mesh_cli.main(["tilemap", "validate", str(scene_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "OK" in out


def test_cli_tilemap_validate_reports_sorted_errors(tmp_path: Path, capsys):
    map_path = tmp_path / "map.json"
    map_path.write_text(json.dumps({"width": 2, "height": 2}), encoding="utf-8")

    scene_path = tmp_path / "scene.json"
    scene_path.write_text(
        json.dumps(
            {
                "tilemap": {
                    "path": str(map_path),
                    "tile_layers": [
                        {"id": "B", "z": 0, "parallax": 2.5, "tiles": [0, 0, 0, 0]},
                        {"id": "A", "z": "nope", "tiles": [0, 0, 0]},
                        {"id": "A", "z": 0},
                    ],
                }
            }
        ),
        encoding="utf-8",
    )

    rc = mesh_cli.main(["tilemap", "validate", str(scene_path)])
    out_lines = [line for line in capsys.readouterr().out.splitlines() if "ERROR:" in line]
    assert rc == 1
    assert len(out_lines) >= 3
    assert " :: A :: id :: " in out_lines[0]
    assert " :: A :: tiles :: " in out_lines[1]
    assert " :: A :: z :: " in out_lines[2]
    assert any(" :: B :: parallax :: " in line for line in out_lines)

