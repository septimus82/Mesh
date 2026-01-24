from __future__ import annotations

import argparse
import json
from pathlib import Path

from engine.tooling.content_commands import content_contract_command


def _write_pack(root: Path, pack_id: str, presets: dict[str, dict]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pack.json").write_text(json.dumps({"id": pack_id, "version": "1.0.0"}), encoding="utf-8")
    fx_dir = root / "fx"
    fx_dir.mkdir(exist_ok=True)
    (fx_dir / "presets.json").write_text(
        json.dumps({"schema_version": 1, "presets": presets}),
        encoding="utf-8",
    )


def test_content_contract_bad_preset_and_missing_sprite(tmp_path: Path, capsys) -> None:
    pack_root = tmp_path / "packs" / "core"
    _write_pack(pack_root, "core", {"spark_hit": {"alpha_curve": "nope"}})

    scene_dir = pack_root / "scenes"
    scene_dir.mkdir(parents=True, exist_ok=True)
    scene_payload = {
        "entities": [
            {
                "name": "fx",
                "x": 0,
                "y": 0,
                "behaviours": ["ParticleEmitter"],
                "behaviour_config": {
                    "ParticleEmitter": {
                        "preset": "core:missing",
                        "sprite": "packs/core/fx/missing.png",
                    }
                },
            }
        ]
    }
    (scene_dir / "test.json").write_text(json.dumps(scene_payload), encoding="utf-8")

    args = argparse.Namespace(paths=None, repo_root=str(tmp_path))
    rc = content_contract_command(args)
    out = capsys.readouterr().out

    assert rc == 2
    assert "packs/core/scenes/test.json" in out
    assert "/entities/0/behaviour_config/ParticleEmitter" in out
    assert "missing.png" in out
    assert "pack=core" in out
    assert "Unknown preset" in out
