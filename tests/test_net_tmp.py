"""A killed server's mesh-room folder is removed by the test that killed it, passing or failing (tests/net_tmp)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.net_tmp import private_temp

pytestmark = pytest.mark.integration  # (a real subprocess and the file system)

REPO = Path(__file__).resolve().parents[1]


def _killed_server(env: dict[str, str], base: str) -> list[str]:
    """Start the packaged co-op server, wait until it listens, kill it outright; the mesh-room folders it left."""
    proc = subprocess.Popen([sys.executable, "-m", "mesh_net.server", "--coop", "--port", "0"], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, cwd=REPO, env=env)
    try:
        for line in proc.stdout:  # type: ignore[union-attr]
            if "listening" in line:
                break
    finally:
        proc.kill()
        proc.communicate(timeout=30)
    return [p.name for p in Path(base).glob("mesh-room-*")]


def test_a_killed_servers_room_folder_goes_with_the_private_temp():
    with private_temp() as (env, base):
        assert _killed_server(env, base)  # the child really used it: a hard kill does leave the folder
    assert not Path(base).exists()


def test_the_private_temp_is_removed_when_the_test_fails():
    with pytest.raises(RuntimeError), private_temp() as (env, base):
        assert _killed_server(env, base)
        seen = base
        raise RuntimeError("the test body failed")
    assert not Path(seen).exists()
