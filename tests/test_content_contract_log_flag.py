from __future__ import annotations

import argparse
import json
from pathlib import Path

from engine.tooling.content_commands import content_contract_command


def test_content_contract_log_flag(tmp_path: Path, capsys) -> None:
    scene_dir = tmp_path / "scenes"
    scene_dir.mkdir(parents=True, exist_ok=True)
    scene_path = scene_dir / "test.json"
    scene_path.write_text(json.dumps({"entities": []}), encoding="utf-8")

    log_path = tmp_path / "artifacts" / "content_contract.log"
    args = argparse.Namespace(
        paths=[str(scene_path)],
        repo_root=str(tmp_path),
        log=str(log_path),
        with_prefabs=False,
        with_behaviours=False,
    )
    rc = content_contract_command(args)
    out = capsys.readouterr().out

    assert rc == 0
    assert "[Mesh][Contract] OK" in out
    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8")
    assert "[Mesh][Contract] OK" in content
