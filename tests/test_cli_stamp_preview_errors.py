import json
from pathlib import Path

import mesh_cli


def test_cli_stamp_preview_errors_on_missing_layer(tmp_path: Path, capsys):
    stamp_path = tmp_path / "stamp.json"
    stamp_path.write_text(
        json.dumps({"id": "s", "width": 2, "height": 2, "tile_layers": [{"layer_id": "A", "tiles": [0, 0, 0, 0]}]}),
        encoding="utf-8",
    )

    rc = mesh_cli.main(["stamp", "preview", str(stamp_path), "--layer", "Missing"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "stamp.layer_missing" in out


def test_cli_stamp_preview_errors_on_bad_tiles_length(tmp_path: Path, capsys):
    stamp_path = tmp_path / "stamp.json"
    stamp_path.write_text(
        json.dumps({"id": "s", "width": 2, "height": 2, "tile_layers": [{"layer_id": "A", "tiles": [0]}]}),
        encoding="utf-8",
    )

    rc = mesh_cli.main(["stamp", "preview", str(stamp_path)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "stamp.tiles_length_mismatch" in out

