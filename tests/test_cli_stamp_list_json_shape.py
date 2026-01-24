import json
import shutil
from pathlib import Path

import mesh_cli
from engine.paths import get_content_roots, set_content_roots


def test_cli_stamp_list_json_shape(tmp_path: Path, capsys):
    original_roots = get_content_roots()
    set_content_roots([tmp_path])
    try:
        stamps = tmp_path / "packs" / "p" / "stamps"
        stamps.mkdir(parents=True)
        (stamps / "s.json").write_text(
            json.dumps(
                {
                    "id": "s",
                    "width": 2,
                    "height": 3,
                    "tiles": [{"layer_id": "Ground", "x": 0, "y": 0, "w": 1, "h": 1, "tile": 5}],
                    "entities": [{"prefab_id": "x", "x": 0, "y": 0, "id_suffix": "a"}],
                }
            ),
            encoding="utf-8",
        )

        rc = mesh_cli.main(["stamp", "list", "--format", "json"])
        out = capsys.readouterr().out
        assert rc == 0
        payload = json.loads(out)
        assert payload["ok"] is True
        assert payload["count"] == 1
        assert payload["stamps"][0]["pack_id"] == "p"
        assert payload["stamps"][0]["id"] == "s"
        assert payload["stamps"][0]["w"] == 2
        assert payload["stamps"][0]["h"] == 3
        assert payload["stamps"][0]["layer_ids"] == ["Ground"]
        assert payload["stamps"][0]["entity_count"] == 1
        assert payload["stamps"][0]["path"] == "packs/p/stamps/s.json"
    finally:
        set_content_roots(original_roots)
        shutil.rmtree(tmp_path / "packs", ignore_errors=True)

