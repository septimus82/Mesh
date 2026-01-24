from __future__ import annotations

import argparse
import json
from pathlib import Path

from mesh_cli.release_contract import release_contract_command


def _write_pack(root: Path, pack_id: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pack.json").write_text(json.dumps({"id": pack_id, "version": "1.0.0"}), encoding="utf-8")


def test_release_contract_report_ok(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    runner_root = tmp_path / "runner"
    runner_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(runner_root)

    pack_root = repo_root / "packs" / "core"
    _write_pack(pack_root, "core")

    fx_dir = pack_root / "fx"
    fx_dir.mkdir(parents=True, exist_ok=True)
    (fx_dir / "presets.json").write_text(
        json.dumps({"schema_version": 1, "presets": {"spark_hit": {"sprite": "packs/core/fx/spark.png"}}}),
        encoding="utf-8",
    )
    (fx_dir / "spark.png").write_text("", encoding="utf-8")

    data_dir = pack_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "prefabs.json").write_text(
        json.dumps([{"id": "torch_wisp", "entity": {}}]),
        encoding="utf-8",
    )

    scene_dir = pack_root / "scenes"
    scene_dir.mkdir(parents=True, exist_ok=True)
    (scene_dir / "test.json").write_text(
        json.dumps(
            {
                "entities": [
                    {
                        "behaviours": ["ParticleEmitter"],
                        "behaviour_config": {"ParticleEmitter": {"preset": "spark_hit"}},
                    },
                    {
                        "prefab_id": "torch_wisp",
                        "behaviours": ["PlayerController"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    artifacts_dir = repo_root / "artifacts"
    report_path = artifacts_dir / "release_report.json"
    args = argparse.Namespace(
        artifacts=str(artifacts_dir),
        repo_root=str(repo_root),
        report=str(report_path),
    )
    rc = release_contract_command(args)
    assert rc == 0
    assert report_path.exists()

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["summary"]["ok"] is True
    step_names = [step["name"] for step in payload["steps"]]
    assert step_names[:3] == ["pack-validate", "asset-audit", "content-contract"]
    assert all(step["ok"] for step in payload["steps"])
