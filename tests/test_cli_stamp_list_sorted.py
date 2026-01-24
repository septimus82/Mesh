import json
import shutil
from pathlib import Path

import mesh_cli
from engine.paths import get_content_roots, set_content_roots


def test_cli_stamp_list_sorted_text(tmp_path: Path, capsys):
    original_roots = get_content_roots()
    set_content_roots([tmp_path])
    try:
        stamps_a = tmp_path / "packs" / "a_pack" / "stamps"
        stamps_b = tmp_path / "packs" / "b_pack" / "stamps"
        stamps_a.mkdir(parents=True)
        stamps_b.mkdir(parents=True)

        (stamps_b / "room.json").write_text(json.dumps({"id": "room", "width": 2, "height": 2, "tiles": []}), encoding="utf-8")
        (stamps_a / "z.json").write_text(json.dumps({"id": "z", "width": 1, "height": 1, "tiles": []}), encoding="utf-8")
        (stamps_a / "a.json").write_text(json.dumps({"id": "a", "width": 1, "height": 1, "tiles": []}), encoding="utf-8")

        rc = mesh_cli.main(["stamp", "list", "--format", "text"])
        out = capsys.readouterr().out.strip().splitlines()
        assert rc == 0
        assert out[0].startswith("a_pack a ")
        assert out[1].startswith("a_pack z ")
        assert out[2].startswith("b_pack room ")
        assert "path=packs/a_pack/stamps/a.json" in out[0]
    finally:
        set_content_roots(original_roots)
        shutil.rmtree(tmp_path / "packs", ignore_errors=True)

