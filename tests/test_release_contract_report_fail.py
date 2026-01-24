from __future__ import annotations

import argparse
import json
from pathlib import Path

from mesh_cli.release_contract import release_contract_command


def _write_pack(root: Path, pack_id: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pack.json").write_text(json.dumps({"id": pack_id, "version": "1.0.0"}), encoding="utf-8")


def test_release_contract_report_fail(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    runner_root = tmp_path / "runner"
    runner_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(runner_root)

    pack_root = repo_root / "packs" / "core"
    _write_pack(pack_root, "core")

    fx_dir = pack_root / "fx"
    fx_dir.mkdir(parents=True, exist_ok=True)
    (fx_dir / "presets.json").write_text(
        json.dumps({"schema_version": 1, "presets": {"bad_fx": {"alpha_curve": "nope"}}}),
        encoding="utf-8",
    )

    report_path = repo_root / "artifacts" / "release_report.json"
    args = argparse.Namespace(
        artifacts="artifacts",
        repo_root=str(repo_root),
        report=str(report_path),
    )
    rc = release_contract_command(args)
    assert rc == 2
    assert report_path.exists()

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["summary"]["ok"] is False
    assert payload["summary"]["failed_step"] == "pack-validate"
    assert [step["name"] for step in payload["steps"]] == ["pack-validate"]
