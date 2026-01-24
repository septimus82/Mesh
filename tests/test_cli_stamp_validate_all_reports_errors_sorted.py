import json
import shutil
from pathlib import Path

import mesh_cli
from engine.paths import get_content_roots, set_content_roots


def test_cli_stamp_validate_all_reports_errors_sorted(tmp_path: Path, capsys):
    original_roots = get_content_roots()
    set_content_roots([tmp_path])
    try:
        (tmp_path / "assets").mkdir(parents=True)
        (tmp_path / "assets" / "prefabs.json").write_text(json.dumps([{"id": "ok_prefab"}]), encoding="utf-8")

        stamps = tmp_path / "packs" / "p" / "stamps"
        stamps.mkdir(parents=True)
        (stamps / "bad.json").write_text(
            json.dumps(
                {
                    "id": "bad",
                    "width": 2,
                    "height": 2,
                    "tile_layers": [{"layer_id": "Ground", "tiles": [0]}],
                    "entities": [
                        {"prefab_id": "missing_prefab", "x": 0, "y": 0, "id_suffix": "a"},
                        {"prefab_id": "ok_prefab", "x": 0, "y": 0, "id_suffix": "a"},
                    ],
                }
            ),
            encoding="utf-8",
        )

        rc = mesh_cli.main(["stamp", "validate-all"])
        out_lines = [ln for ln in capsys.readouterr().out.splitlines() if "ERROR:" in ln]
        assert rc == 1
        # Sorted by (path, code, detail)
        assert out_lines == sorted(out_lines)
        assert any("stamp.entities.unknown_prefab" in ln for ln in out_lines)
        assert any("stamp.entities.duplicate_id_suffix" in ln for ln in out_lines)
        assert any("stamp.tile_layers.tiles_length" in ln for ln in out_lines)
    finally:
        set_content_roots(original_roots)
        shutil.rmtree(tmp_path / "packs", ignore_errors=True)
        shutil.rmtree(tmp_path / "assets", ignore_errors=True)

