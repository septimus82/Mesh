from __future__ import annotations

import argparse
from pathlib import Path

from mesh_cli import replay as replay_commands


def test_replay_hash_expect_mismatch(tmp_path: Path, capsys) -> None:
    replay_path = tmp_path / "replay.json"
    replay_path.write_text('{"steps":[{"dump_state": true}]}', encoding="utf-8")

    expect_path = tmp_path / "expected.json"
    expect_path.write_text('{"hash": "deadbeef"}', encoding="utf-8")

    out_path = tmp_path / "hash.json"
    args = argparse.Namespace(
        replay=str(replay_path),
        frames=1,
        warmup=0,
        float_round=6,
        out=str(out_path),
        expect=str(expect_path),
    )

    code = replay_commands._handle_replay_hash(args)
    assert code == 2
    assert out_path.exists()

    stdout = capsys.readouterr().out
    assert "hash mismatch" in stdout
    assert "expected=deadbeef" in stdout
