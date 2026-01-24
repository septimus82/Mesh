import json
from pathlib import Path

import mesh_cli


def test_cli_scene_validate_backgrounds_ok(tmp_path: Path, capsys):
    scene_path = tmp_path / "scene.json"
    scene_path.write_text(
        json.dumps(
            {
                "background_layers": [
                    {"id": "Sky", "path": "assets/bg/sky.png", "z": -1000, "parallax": 0.2, "repeat_x": True},
                    {"id": "Mountains", "path": "assets/bg/m.png", "z": -900, "parallax": 0.4, "repeat_x": False},
                ],
                "entities": [],
            }
        ),
        encoding="utf-8",
    )
    rc = mesh_cli.main(["scene", "validate-backgrounds", str(scene_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "OK" in out


def test_cli_scene_validate_backgrounds_errors_sorted(tmp_path: Path, capsys):
    scene_path = tmp_path / "scene.json"
    scene_path.write_text(
        json.dumps(
            {
                "background_layers": [
                    {"id": "B", "path": "", "z": -1, "parallax": 3.0},
                    {"id": "A", "path": "x.png", "z": "nope", "repeat_x": "yes"},
                    {"id": "A", "path": "y.png", "z": -2},
                ],
                "entities": [],
            }
        ),
        encoding="utf-8",
    )
    rc = mesh_cli.main(["scene", "validate-backgrounds", str(scene_path)])
    out_lines = [line for line in capsys.readouterr().out.splitlines() if "ERROR:" in line]
    assert rc == 1
    assert out_lines[0].split(" :: ")[1] == "A"
    assert any(" :: A :: id :: " in line for line in out_lines)
    assert any(" :: A :: repeat_x :: " in line for line in out_lines)
    assert any(" :: A :: z :: " in line for line in out_lines)
    assert any(" :: B :: path :: " in line for line in out_lines)
    assert any(" :: B :: parallax :: " in line for line in out_lines)
