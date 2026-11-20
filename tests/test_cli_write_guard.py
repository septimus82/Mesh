"""Legacy CLI writers own the project or refuse (#462 A-04).

``place-npc``, ``new-npc``, ``new-scene``, ``scene ...`` and the other commands that write a project's files in place
used to write behind an open Mesh Studio. Now ``mesh_cli.write_guard`` owns the project for each of them (one guard in
``dispatch``). A second process holds the project's Studio lock here (the real OS lock, not a mock); the command runs
as a subprocess and must exit non-zero with the standard message and leave every file byte-identical.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from engine.editor import project_ownership
from engine.project_scaffold import create_project
from mesh_cli import write_guard
from mesh_cli.legacy.dispatch import build_parser
from tests.test_studio_project_ownership import REPO, ROOM

pytestmark = pytest.mark.integration  # (F13-A: subprocesses, OS locks)

HOLDER = ("import sys, time; sys.path.insert(0, sys.argv[1]); from engine.editor import project_ownership as o; "
          "h = o.acquire(sys.argv[2], o.STUDIO); print('held', flush=True); time.sleep(120)")
FAMILIES = {
    "place-npc": ["place-npc", "guard", "--into", ROOM],
    "new-npc": ["new-npc", "guard", "--into", ROOM],
    "new-scene": ["new-scene", "annex"],
    "new-behaviour": ["new-behaviour", "annex_behaviour"],
    "scene-create": ["scene", "create", "scenes/annex.json", "--width", "4", "--height", "4", "--tile-w", "16",
                     "--tile-h", "16", "--layer", "ground:0"],
    "scene-add-placeholder": ["scene", "add-placeholder", ROOM, "--x", "32", "--y", "32"],
    "tidy-scene": ["tidy-scene", ROOM],
}


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "game"
    create_project(path, "Game", template_id="blank")
    return path


@pytest.fixture
def studio_lock(root: Path) -> Iterator[None]:
    holder = subprocess.Popen([sys.executable, "-c", HOLDER, str(REPO), str(root)], stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout is not None and holder.stdout.readline().strip() == "held"
        yield
    finally:
        holder.kill()
        holder.wait()
        assert holder.stdout is not None
        holder.stdout.close()


def _files(root: Path) -> dict[str, str]:
    skip = {".mesh/owner.lock"}
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and p.relative_to(root).as_posix() not in skip}


def _mesh(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "mesh_cli", *args], cwd=cwd, capture_output=True, text=True,
                          timeout=300, env={**os.environ, "PYTHONPATH": str(REPO)})


@pytest.mark.parametrize("name", sorted(FAMILIES))
def test_command_is_refused_while_studio_has_the_project(root: Path, studio_lock: None, name: str) -> None:
    before = _files(root)
    result = _mesh(root, *FAMILIES[name])
    assert result.returncode == 1, result.stdout[-1500:]
    assert f"{FAMILIES[name][0]}: nothing was changed. Mesh Studio has this project open" in result.stdout
    assert _files(root) == before


def test_a_scene_path_in_the_project_is_refused_from_any_folder(root: Path, studio_lock: None, tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    before = _files(root)
    result = _mesh(elsewhere, "scene", "add-placeholder", str(root / ROOM), "--x", "1", "--y", "1")
    assert result.returncode == 1 and "nothing was changed. Mesh Studio has this project open" in result.stdout
    assert _files(root) == before


def test_dry_runs_and_readers_still_work_while_studio_has_the_project(root: Path, studio_lock: None) -> None:
    before = _files(root)
    assert _mesh(root, "schema-fix-ids", "--dry-run").returncode == 0
    assert _mesh(root, "list-scenes").returncode == 0
    assert _files(root) == before


@pytest.mark.parametrize("name", sorted(FAMILIES))
def test_command_still_works_with_no_owner_and_lets_the_project_go(root: Path, name: str) -> None:
    before = _files(root)
    result = _mesh(root, *FAMILIES[name])
    assert result.returncode == 0, result.stdout[-1500:]
    if name != "tidy-scene":  # (an already tidy scene is rewritten identically)
        assert _files(root) != before
    assert project_ownership.owned(root) is None  # released: Studio can open it now


def test_writes_project_classifies_commands() -> None:
    parse = build_parser().parse_args
    assert write_guard.writes_project(parse(["place-npc", "guard", "--into", ROOM]))
    assert write_guard.writes_project(parse(["schema-fix-ids"]))
    assert not write_guard.writes_project(parse(["schema-fix-ids", "--dry-run"]))
    assert not write_guard.writes_project(parse(["list-scenes"]))
    assert not write_guard.writes_project(argparse.Namespace(command=None))
