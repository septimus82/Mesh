from __future__ import annotations

import argparse
import json
from pathlib import Path

from engine.tooling.content_commands import content_contract_command


def _write_pack(root: Path, pack_id: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pack.json").write_text(json.dumps({"id": pack_id, "version": "1.0.0"}), encoding="utf-8")


def test_content_contract_behaviours_ok_and_fail(tmp_path: Path, capsys) -> None:
    pack_root = tmp_path / "packs" / "core"
    _write_pack(pack_root, "core")
    scene_dir = pack_root / "scenes"
    scene_dir.mkdir(parents=True, exist_ok=True)

    ok_scene = scene_dir / "ok.json"
    ok_scene.write_text(
        json.dumps({"entities": [{"behaviours": ["ParticleEmitter"]}]}),
        encoding="utf-8",
    )
    args = argparse.Namespace(
        paths=[str(ok_scene)],
        repo_root=str(tmp_path),
        with_prefabs=False,
        with_behaviours=True,
    )
    rc = content_contract_command(args)
    out = capsys.readouterr().out
    assert rc == 0
    assert "[Mesh][Contract] OK" in out

    bad_scene = scene_dir / "bad.json"
    bad_scene.write_text(
        json.dumps({"entities": [{"behaviours": ["ParticleEmitter", "NotARealBehaviour"]}]}),
        encoding="utf-8",
    )
    args = argparse.Namespace(
        paths=[str(bad_scene)],
        repo_root=str(tmp_path),
        with_prefabs=False,
        with_behaviours=True,
    )
    rc = content_contract_command(args)
    out = capsys.readouterr().out
    assert rc == 2
    assert "packs/core/scenes/bad.json" in out
    assert "/entities/0/behaviours/1" in out
    assert "Unknown behaviour" in out
    assert "pack=core" in out
