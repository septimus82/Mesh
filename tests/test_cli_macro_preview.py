from __future__ import annotations

import json
import shutil
from pathlib import Path

import mesh_cli
from engine.paths import get_content_roots, set_content_roots


def test_cli_macro_preview_json_shape(tmp_path: Path, capsys) -> None:
    original_roots = get_content_roots()
    set_content_roots([tmp_path])
    try:
        macros = tmp_path / "packs" / "a_pack" / "macros"
        macros.mkdir(parents=True)
        (macros / "a.json").write_text(
            json.dumps(
                {
                    "id": "a",
                    "type": "macro",
                    "macro_id": "macro.door_transition",
                    "defaults": {"anchor": "player", "target_scene": "scenes/x.json", "spawn_id": "s"},
                    "steps": [{"key": "anchor", "kind": "pick", "options": ["player", "cursor", "primary"]}],
                }
            ),
            encoding="utf-8",
        )

        rc = mesh_cli.main(["macro", "preview", "packs/a_pack/macros/a.json", "--format", "json"])
        payload = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert payload["ok"] is True
        assert payload["pack_id"] == "a_pack"
        assert payload["id"] == "a"
        assert payload["macro_id"] == "macro.door_transition"
        assert payload["path"] == "packs/a_pack/macros/a.json"
        assert payload["defaults"]["target_scene"] == "scenes/x.json"
        assert isinstance(payload["steps"], list) and payload["steps"]
        assert int(payload["entity_change_count"]) >= 0
        assert int(payload["config_change_count"]) >= 0
    finally:
        set_content_roots(original_roots)
        shutil.rmtree(tmp_path / "packs", ignore_errors=True)


def test_cli_macro_preview_text(tmp_path: Path, capsys) -> None:
    original_roots = get_content_roots()
    set_content_roots([tmp_path])
    try:
        macros = tmp_path / "packs" / "a_pack" / "macros"
        macros.mkdir(parents=True)
        (macros / "a.json").write_text(
            json.dumps(
                {
                    "id": "a",
                    "type": "macro",
                    "macro_id": "macro.door_transition",
                    "defaults": {"anchor": "player", "target_scene": "scenes/x.json", "spawn_id": "s"},
                }
            ),
            encoding="utf-8",
        )

        rc = mesh_cli.main(["macro", "preview", "packs/a_pack/macros/a.json", "--format", "text"])
        out = capsys.readouterr().out.strip().splitlines()
        assert rc == 0
        assert out[0].startswith("a_pack a macro_id=macro.door_transition ")
        assert "path=packs/a_pack/macros/a.json" in out[0]
        assert out[1].startswith("preview entity_changes=")
        assert out[2].startswith('defaults={"anchor": "player"')
    finally:
        set_content_roots(original_roots)
        shutil.rmtree(tmp_path / "packs", ignore_errors=True)
