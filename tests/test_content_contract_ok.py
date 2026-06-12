from __future__ import annotations

import argparse
from pathlib import Path

from engine.tooling.content_commands import content_contract_command
from tests.fixture_repo import copy_minipack_repo


def test_content_contract_ok(tmp_path: Path, capsys) -> None:
    repo_root = copy_minipack_repo(tmp_path)
    args = argparse.Namespace(paths=None, repo_root=str(repo_root))
    rc = content_contract_command(args)
    out = capsys.readouterr().out

    assert rc == 0
    assert "[Mesh][Contract] OK" in out
