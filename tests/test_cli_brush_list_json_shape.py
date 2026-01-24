import json
import shutil
from pathlib import Path

import mesh_cli
from engine.paths import get_content_roots, set_content_roots


def test_cli_brush_list_json_shape(tmp_path: Path, capsys):
    original_roots = get_content_roots()
    set_content_roots([tmp_path])
    try:
        brushes = tmp_path / "packs" / "p" / "brushes"
        brushes.mkdir(parents=True)
        (brushes / "c.json").write_text(json.dumps({"id": "c", "w": 2, "h": 1, "mask_tile": -1, "tiles": [[1, -1]]}), encoding="utf-8")

        rc = mesh_cli.main(["brush", "list", "--format", "json"])
        payload = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert payload["ok"] is True
        assert payload["count"] == 1
        assert payload["brushes"][0]["pack_id"] == "p"
        assert payload["brushes"][0]["id"] == "c"
        assert payload["brushes"][0]["w"] == 2
        assert payload["brushes"][0]["h"] == 1
        assert payload["brushes"][0]["path"] == "packs/p/brushes/c.json"
    finally:
        set_content_roots(original_roots)
        shutil.rmtree(tmp_path / "packs", ignore_errors=True)

