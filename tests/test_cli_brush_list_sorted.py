import json
import shutil
from pathlib import Path

import mesh_cli
from engine.paths import get_content_roots, set_content_roots


def test_cli_brush_list_sorted_text(tmp_path: Path, capsys):
    original_roots = get_content_roots()
    set_content_roots([tmp_path])
    try:
        brushes_a = tmp_path / "packs" / "a_pack" / "brushes"
        brushes_b = tmp_path / "packs" / "b_pack" / "brushes"
        brushes_a.mkdir(parents=True)
        brushes_b.mkdir(parents=True)

        (brushes_b / "b.json").write_text(json.dumps({"id": "b", "w": 1, "h": 1, "mask_tile": -1, "tiles": [[1]]}), encoding="utf-8")
        (brushes_a / "z.json").write_text(json.dumps({"id": "z", "w": 1, "h": 1, "mask_tile": -1, "tiles": [[1]]}), encoding="utf-8")
        (brushes_a / "a.json").write_text(json.dumps({"id": "a", "w": 1, "h": 1, "mask_tile": -1, "tiles": [[1]]}), encoding="utf-8")

        rc = mesh_cli.main(["brush", "list", "--format", "text"])
        out = capsys.readouterr().out.strip().splitlines()
        assert rc == 0
        assert out[0].startswith("a_pack a ")
        assert out[1].startswith("a_pack z ")
        assert out[2].startswith("b_pack b ")
        assert "path=packs/a_pack/brushes/a.json" in out[0]
    finally:
        set_content_roots(original_roots)
        shutil.rmtree(tmp_path / "packs", ignore_errors=True)

