import json
from pathlib import Path

import mesh_cli


def test_cli_stamp_preview_tile_filter(tmp_path: Path, capsys):
    stamp_path = tmp_path / "stamp.json"
    stamp_path.write_text(
        json.dumps(
            {
                "id": "s",
                "width": 3,
                "height": 2,
                "tile_layers": [{"layer_id": "Ground", "tiles": [5, 0, 5, 2, 5, 2]}],
            }
        ),
        encoding="utf-8",
    )

    rc = mesh_cli.main(["stamp", "preview", str(stamp_path), "--layer", "Ground", "--tile", "5"])
    out = capsys.readouterr().out.splitlines()
    assert rc == 0
    assert out[0] == "s 3x2 layer=Ground"
    assert out[1:] == [
        "#.#",
        ".#.",
    ]

