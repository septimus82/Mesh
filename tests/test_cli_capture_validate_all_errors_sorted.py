import json
import shutil
from pathlib import Path

import mesh_cli
from engine.paths import get_content_roots, set_content_roots


def test_cli_capture_validate_all_errors_sorted(tmp_path: Path, capsys):
    original_roots = get_content_roots()
    set_content_roots([tmp_path])
    try:
        (tmp_path / "assets").mkdir(parents=True)
        (tmp_path / "assets" / "prefabs.json").write_text(json.dumps([{"id": "crate"}]), encoding="utf-8")

        stamps = tmp_path / "packs" / "p" / "stamps"
        brushes = tmp_path / "packs" / "p" / "brushes"
        stamps.mkdir(parents=True)
        brushes.mkdir(parents=True)

        # Invalid captured stamp (dims invalid).
        (stamps / "capture_bad.json").write_text(json.dumps({"id": "capture_bad", "width": 0, "height": 1, "tiles": []}), encoding="utf-8")
        # Invalid captured brush (tiles wrong type).
        (brushes / "capture_bad_brush.json").write_text(
            json.dumps({"id": "capture_bad_brush", "w": 1, "h": 1, "mask_tile": -1, "tiles": "nope"}),
            encoding="utf-8",
        )

        rc = mesh_cli.main(["capture", "validate-all"])
        out_lines = [ln for ln in capsys.readouterr().out.splitlines() if "ERROR:" in ln]
        assert rc == 1
        assert out_lines == sorted(out_lines)
        assert any("capture_bad.json" in ln for ln in out_lines)
        assert any("capture_bad_brush.json" in ln for ln in out_lines)
    finally:
        set_content_roots(original_roots)
        shutil.rmtree(tmp_path / "packs", ignore_errors=True)
        shutil.rmtree(tmp_path / "assets", ignore_errors=True)

