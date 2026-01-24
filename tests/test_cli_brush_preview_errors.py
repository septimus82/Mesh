import json
from pathlib import Path

import mesh_cli


def test_cli_brush_preview_rejects_invalid_shape(tmp_path: Path, capsys):
    brush_path = tmp_path / "bad_brush.json"
    brush_path.write_text(json.dumps({"id": "bad", "w": 1, "h": 1, "mask_tile": -1, "tiles": "nope"}), encoding="utf-8")

    rc = mesh_cli.main(["brush", "preview", str(brush_path)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "brush.invalid" in out
    assert "brush.tiles.array" in out


def test_cli_brush_preview_rejects_non_object_root(tmp_path: Path, capsys):
    brush_path = tmp_path / "bad_root.json"
    brush_path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    rc = mesh_cli.main(["brush", "preview", str(brush_path)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "brush.root_type" in out

