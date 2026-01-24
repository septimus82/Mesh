import json
import shutil
from pathlib import Path

import mesh_cli
from engine.paths import get_content_roots, set_content_roots


def test_cli_capture_list_sorted_text(tmp_path: Path, capsys):
    original_roots = get_content_roots()
    set_content_roots([tmp_path])
    try:
        stamps = tmp_path / "packs" / "p" / "stamps"
        brushes = tmp_path / "packs" / "p" / "brushes"
        stamps.mkdir(parents=True)
        brushes.mkdir(parents=True)

        # Captured by filename prefix.
        (stamps / "capture_stamp_1x1.json").write_text(
            json.dumps({"id": "capture_stamp_1x1", "width": 1, "height": 1, "tiles": [{"layer_id": "Ground", "x": 0, "y": 0, "w": 1, "h": 1, "tile": 1}]}),
            encoding="utf-8",
        )
        # Captured by metadata.
        (brushes / "custom.json").write_text(
            json.dumps({"id": "custom", "w": 1, "h": 1, "mask_tile": -1, "tiles": [[1]], "metadata": {"source": "capture_mode"}}),
            encoding="utf-8",
        )
        # Not captured.
        (brushes / "normal.json").write_text(json.dumps({"id": "normal", "w": 1, "h": 1, "mask_tile": -1, "tiles": [[1]]}), encoding="utf-8")

        rc = mesh_cli.main(["capture", "list", "--format", "text"])
        out = capsys.readouterr().out.strip().splitlines()
        assert rc == 0
        assert out == sorted(out)
        assert any("p stamp capture_stamp_1x1" in ln for ln in out)
        assert any("p brush custom" in ln for ln in out)
        assert not any("normal" in ln for ln in out)
    finally:
        set_content_roots(original_roots)
        shutil.rmtree(tmp_path / "packs", ignore_errors=True)

