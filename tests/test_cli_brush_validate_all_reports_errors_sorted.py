import json
import shutil
from pathlib import Path

import mesh_cli
from engine.paths import get_content_roots, set_content_roots


def test_cli_brush_validate_all_reports_errors_sorted(tmp_path: Path, capsys):
    original_roots = get_content_roots()
    set_content_roots([tmp_path])
    try:
        brushes = tmp_path / "packs" / "p" / "brushes"
        brushes.mkdir(parents=True)

        (brushes / "a.json").write_text(json.dumps({"id": "", "w": 1, "h": 1, "mask_tile": -1, "tiles": [[1]]}), encoding="utf-8")
        (brushes / "b.json").write_text(
            json.dumps({"id": "b", "w": 2, "h": 2, "mask_tile": -1, "tiles": [[1, "x"], [1, 1]]}),
            encoding="utf-8",
        )

        rc = mesh_cli.main(["brush", "validate-all"])
        out_lines = [ln for ln in capsys.readouterr().out.splitlines() if "ERROR:" in ln]
        assert rc == 1
        assert out_lines == sorted(out_lines)
        assert any("packs/p/brushes/a.json :: brush.id.required" in ln for ln in out_lines)
        assert any("packs/p/brushes/b.json :: brush.tiles[0][1].int" in ln for ln in out_lines)
    finally:
        set_content_roots(original_roots)
        shutil.rmtree(tmp_path / "packs", ignore_errors=True)

