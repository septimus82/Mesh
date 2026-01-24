from __future__ import annotations

import argparse
import json
from pathlib import Path

from engine.paths import reset_path_caches, set_content_roots
from mesh_cli import fx as fx_commands


def _write_pack(root: Path, pack_id: str, presets: dict[str, dict]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    payload = {"id": pack_id, "version": "1.0.0"}
    (root / "pack.json").write_text(json.dumps(payload), encoding="utf-8")
    fx_dir = root / "fx"
    fx_dir.mkdir(exist_ok=True)
    (fx_dir / "presets.json").write_text(
        json.dumps({"schema_version": 1, "presets": presets}),
        encoding="utf-8",
    )


def test_fx_validate_cli_ok(tmp_path: Path, capsys) -> None:
    pack_root = tmp_path / "packs" / "a"
    _write_pack(pack_root, "a", {"spark": {"mode": "burst", "count": 4}})

    set_content_roots([tmp_path])
    try:
        args = argparse.Namespace(command="fx", fx_command="validate")
        rc = fx_commands.handle(args)
        out = capsys.readouterr().out
    finally:
        reset_path_caches()

    assert rc == 0
    assert "[Mesh][FX] OK" in out
