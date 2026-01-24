import json
import shutil
from pathlib import Path

import mesh_cli
from engine.paths import get_content_roots, set_content_roots


def test_macro_validate_all_unknown_defaults_key_errors_sorted(tmp_path: Path, capsys) -> None:
    original_roots = get_content_roots()
    set_content_roots([tmp_path])
    try:
        macros = tmp_path / "packs" / "a_pack" / "macros"
        macros.mkdir(parents=True)
        (macros / "bad.json").write_text(
            json.dumps(
                {
                    "id": "bad",
                    "type": "macro",
                    "macro_id": "macro.door_transition",
                    "defaults": {"anchor": "player", "target_scene": "scenes/x.json", "spawn_id": "s", "extra": 1},
                }
            ),
            encoding="utf-8",
        )

        rc = mesh_cli.main(["macro", "validate-all"])
        out = capsys.readouterr().out.strip().splitlines()
        assert rc == 1
        assert out == sorted(out)
        assert any("macro_asset.unknown_arg" in line for line in out)
    finally:
        set_content_roots(original_roots)
        shutil.rmtree(tmp_path / "packs", ignore_errors=True)

