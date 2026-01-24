from __future__ import annotations

import argparse
import json
from pathlib import Path

from mesh_cli.release_contract import release_contract_command


def _write_pack(root: Path, pack_id: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pack.json").write_text(json.dumps({"id": pack_id, "version": "1.0.0"}), encoding="utf-8")


def test_release_contract_fails_fast(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)

    pack_root = tmp_path / "packs" / "core"
    _write_pack(pack_root, "core")

    fx_dir = pack_root / "fx"
    fx_dir.mkdir(parents=True, exist_ok=True)
    (fx_dir / "presets.json").write_text(
        json.dumps({"schema_version": 1, "presets": {"bad_fx": {"alpha_curve": "nope"}}}),
        encoding="utf-8",
    )

    artifacts_dir = tmp_path / "artifacts"
    args = argparse.Namespace(artifacts=str(artifacts_dir))
    rc = release_contract_command(args)
    out = capsys.readouterr().out

    assert rc == 2
    assert "[Mesh][Release] content-contract" not in out
    assert not (artifacts_dir / "content_contract.log").exists()
