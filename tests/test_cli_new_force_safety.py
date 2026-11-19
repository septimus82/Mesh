"""A-01: ``mesh new --force`` / ``mesh new_project --force`` never delete outside their own target.

Every case runs the production CLI in a subprocess (cwd = tmp_path) and only ever builds
targets inside ``tmp_path``. Each refusal must exit nonzero and leave every byte under
``outer/`` unchanged.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration]

_REPO = Path(__file__).resolve().parents[1]


def _cli(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(_REPO)}
    return subprocess.run(
        [sys.executable, "-m", "mesh_cli", *args], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120
    )


def _snapshot(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


@pytest.fixture
def layout(tmp_path: Path) -> tuple[Path, Path]:
    """(outer, dest): outer/sandbox/dest is --dest; outer/victim and outer/sandbox hold markers."""
    outer = tmp_path / "outer"
    dest = outer / "sandbox" / "dest"
    dest.mkdir(parents=True)
    (outer / "victim").mkdir()
    (outer / "victim" / "MARKER.txt").write_bytes(b"victim\n")
    (outer / "sandbox" / "KEEP.txt").write_bytes(b"keep\n")
    (dest / "other.txt").write_bytes(b"other\n")
    # Every possible victim looks like a Mesh project, so the config.json rule alone can never save it.
    for folder in (outer / "victim", outer / "sandbox", dest):
        (folder / "config.json").write_bytes(b"{}\n")
    return outer, dest


def _invoke(tmp_path: Path, cmd: str, name: str, dest: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    if cmd == "new":
        return _cli(tmp_path, "new", name, "--dest", str(dest), "--force", *extra)
    return _cli(tmp_path, "new_project", name, str(dest), "--force", *extra)


@pytest.mark.parametrize("cmd", ["new", "new_project"])
@pytest.mark.parametrize(
    "name_for",
    [
        pytest.param(lambda outer: "../../victim", id="sibling-via-dotdot"),
        pytest.param(lambda outer: "..", id="dotdot"),
        pytest.param(lambda outer: ".", id="dot"),
        pytest.param(lambda outer: str(outer / "victim"), id="absolute"),
        pytest.param(lambda outer: "sub/dir", id="forward-separator"),
        pytest.param(lambda outer: "sub" + chr(92) + "dir", id="backslash-separator"),
    ],
)
def test_bad_names_are_refused_without_touching_anything(tmp_path, layout, cmd, name_for) -> None:
    outer, dest = layout
    before = _snapshot(outer)
    result = _invoke(tmp_path, cmd, name_for(outer), dest)
    assert result.returncode != 0, result.stdout + result.stderr
    assert _snapshot(outer) == before


@pytest.mark.parametrize("cmd", ["new", "new_project"])
def test_force_refuses_a_non_project_folder(tmp_path, layout, cmd) -> None:
    outer, dest = layout
    target = dest / "notes"
    target.mkdir()
    (target / "precious.txt").write_bytes(b"precious\n")
    before = _snapshot(outer)
    result = _invoke(tmp_path, cmd, "notes", dest)
    assert result.returncode != 0, result.stdout + result.stderr
    assert "not a Mesh project" in result.stderr
    assert _snapshot(outer) == before


@pytest.mark.skipif(os.name != "nt", reason="junctions are Windows-only; the Windows lane runs this on Windows")
@pytest.mark.parametrize("cmd", ["new", "new_project"])
def test_force_refuses_a_junction_target(tmp_path, layout, cmd) -> None:
    outer, dest = layout
    link = dest / "linked"
    done = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outer / "victim")], capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
    before = _snapshot(outer)
    try:
        result = _invoke(tmp_path, cmd, "linked", dest)
        assert result.returncode != 0, result.stdout + result.stderr
        assert _snapshot(outer) == before
    finally:
        os.rmdir(link)  # removes only the junction, never its target


@pytest.mark.skipif(os.name == "nt", reason="symlink test for POSIX; the Linux lane runs this on Linux")
@pytest.mark.parametrize("cmd", ["new", "new_project"])
def test_force_refuses_a_symlink_target(tmp_path, layout, cmd) -> None:
    outer, dest = layout
    (dest / "linked").symlink_to(outer / "victim", target_is_directory=True)
    before = _snapshot(outer)
    result = _invoke(tmp_path, cmd, "linked", dest)
    assert result.returncode != 0, result.stdout + result.stderr
    assert _snapshot(outer) == before


@pytest.mark.parametrize("cmd", ["new", "new_project"])
def test_valid_new_and_force_over_a_mesh_project_still_work(tmp_path, layout, cmd) -> None:
    outer, dest = layout
    assert _invoke(tmp_path, cmd, "game", dest).returncode == 0
    project = dest / "game"
    assert (project / "config.json").is_file()
    (project / "stale.txt").write_bytes(b"stale\n")
    result = _invoke(tmp_path, cmd, "game", dest)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (project / "config.json").is_file()
    assert not (project / "stale.txt").exists()
    assert (dest / "other.txt").read_bytes() == b"other\n"
    assert (outer / "victim" / "MARKER.txt").read_bytes() == b"victim\n"
