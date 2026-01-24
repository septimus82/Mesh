import json
import shutil
from pathlib import Path

import mesh_cli
from engine.paths import get_content_roots, set_content_roots


def test_cli_macro_list_sorted_text(tmp_path: Path, capsys):
    original_roots = get_content_roots()
    set_content_roots([tmp_path])
    try:
        macros_a = tmp_path / "packs" / "a_pack" / "macros"
        macros_b = tmp_path / "packs" / "b_pack" / "macros"
        macros_a.mkdir(parents=True)
        macros_b.mkdir(parents=True)

        (macros_b / "z.json").write_text(
            json.dumps(
                {
                    "id": "z",
                    "type": "macro",
                    "macro_id": "macro.door_transition",
                    "defaults": {"anchor": "player", "target_scene": "scenes/x.json", "spawn_id": "s"},
                }
            ),
            encoding="utf-8",
        )
        (macros_a / "b.json").write_text(
            json.dumps(
                {
                    "id": "b",
                    "type": "macro",
                    "macro_id": "macro.door_transition",
                    "defaults": {"anchor": "player", "target_scene": "scenes/x.json", "spawn_id": "s"},
                }
            ),
            encoding="utf-8",
        )
        (macros_a / "a.json").write_text(
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

        rc = mesh_cli.main(["macro", "list", "--format", "text"])
        out = capsys.readouterr().out.strip().splitlines()
        assert rc == 0
        assert out[0].startswith("a_pack a ")
        assert out[1].startswith("a_pack b ")
        assert out[2].startswith("b_pack z ")
        assert "path=packs/a_pack/macros/a.json" in out[0]
    finally:
        set_content_roots(original_roots)
        shutil.rmtree(tmp_path / "packs", ignore_errors=True)


def test_cli_macro_list_json_shape(tmp_path: Path, capsys):
    original_roots = get_content_roots()
    set_content_roots([tmp_path])
    try:
        macros_a = tmp_path / "packs" / "a_pack" / "macros"
        macros_a.mkdir(parents=True)
        (macros_a / "a.json").write_text(
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

        rc = mesh_cli.main(["macro", "list", "--format", "json"])
        payload = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert payload["ok"] is True
        assert payload["count"] == 1
        row = payload["macros"][0]
        assert set(row.keys()) == {"id", "macro_id", "pack_id", "path", "step_count"}
        assert row["pack_id"] == "a_pack"
        assert row["id"] == "a"
    finally:
        set_content_roots(original_roots)
        shutil.rmtree(tmp_path / "packs", ignore_errors=True)


def test_cli_macro_validate_all_reports_errors_sorted(tmp_path: Path, capsys):
    original_roots = get_content_roots()
    set_content_roots([tmp_path])
    try:
        macros_a = tmp_path / "packs" / "a_pack" / "macros"
        macros_a.mkdir(parents=True)
        (macros_a / "bad1.json").write_text(json.dumps({"id": "bad1", "type": "macro"}), encoding="utf-8")
        (macros_a / "bad2.json").write_text(
            json.dumps(
                {
                    "id": "bad2",
                    "type": "macro",
                    "macro_id": "macro.door_transition",
                    "defaults": {"not_a_key": 1},
                }
            ),
            encoding="utf-8",
        )

        rc = mesh_cli.main(["macro", "validate-all"])
        out = capsys.readouterr().out.strip().splitlines()
        assert rc == 1
        assert out == sorted(out)
        assert any("macro_asset.macro_id.required" in line for line in out)
        assert any("macro_asset.unknown_arg" in line for line in out)
    finally:
        set_content_roots(original_roots)
        shutil.rmtree(tmp_path / "packs", ignore_errors=True)
