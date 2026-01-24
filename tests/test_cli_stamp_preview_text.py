import json
from pathlib import Path

import mesh_cli


def test_cli_stamp_preview_text(tmp_path: Path, capsys):
    stamp_path = tmp_path / "stamp.json"
    # 4x3 grid via tile_layers
    stamp_path.write_text(
        json.dumps(
            {
                "id": "s",
                "width": 4,
                "height": 3,
                "tile_layers": [
                    {"layer_id": "Ground", "tiles": [0, 1, 0, 0, 2, 0, 0, 3, 0, 0, 0, 0]},
                ],
            }
        ),
        encoding="utf-8",
    )

    rc = mesh_cli.main(["stamp", "preview", str(stamp_path)])
    out = capsys.readouterr().out.splitlines()
    assert rc == 0
    assert out[0] == "s 4x3 layer=Ground"
    assert out[1:] == [
        ".#..",
        "#..#",
        "....",
    ]

