import json
from pathlib import Path

import mesh_cli


def test_cli_brush_preview_text(tmp_path: Path, capsys):
    brush_path = tmp_path / "brush.json"
    brush_path.write_text(
        json.dumps(
            {
                "id": "b",
                "w": 4,
                "h": 3,
                "mask_tile": -1,
                "tiles": [[-1, 1, -1, -1], [2, -1, -1, 3], [-1, -1, -1, -1]],
            }
        ),
        encoding="utf-8",
    )

    rc = mesh_cli.main(["brush", "preview", str(brush_path)])
    out = capsys.readouterr().out.splitlines()
    assert rc == 0
    assert out[0] == "b 4x3 layer=tiles"
    assert out[1:] == [
        ".#..",
        "#..#",
        "....",
    ]


def test_cli_brush_preview_tile_filter(tmp_path: Path, capsys):
    brush_path = tmp_path / "brush.json"
    brush_path.write_text(
        json.dumps(
            {
                "id": "b",
                "w": 4,
                "h": 3,
                "mask_tile": -1,
                "tiles": [[-1, 1, -1, -1], [2, -1, -1, 3], [-1, -1, -1, -1]],
            }
        ),
        encoding="utf-8",
    )

    rc = mesh_cli.main(["brush", "preview", str(brush_path), "--tile", "3"])
    out = capsys.readouterr().out.splitlines()
    assert rc == 0
    assert out[0] == "b 4x3 layer=tiles"
    assert out[1:] == [
        "....",
        "...#",
        "....",
    ]

