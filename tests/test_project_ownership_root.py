"""#462 R4/R5 remediation: the one rule for whose project a file is, and so whose lock a writer must hold.

A Mesh project is the nearest folder, the path's own or above, with a ``config.json`` (links and junctions
resolved). An ordinary folder inside a project is that project's; a folder with its own ``config.json`` is a nested
project with its own owner. ``ownership_root`` is the lock a writer starting anywhere in a project takes;
``in_project`` is what a writer holding it may change. ``AIOps(project=...)`` enforces it on every path it reads for a
write or writes.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from engine.ai_ops import AIOps
from engine.editor import project_ownership
from engine.editor.project_ownership import in_project, ownership_root, project_root
from engine.project_scaffold import create_project

pytestmark = pytest.mark.integration  # (F13-A: real files, a second process)
REPO = Path(__file__).resolve().parents[1]
REGION = "packs/core_regions"


@pytest.fixture
def outer(tmp_path: Path) -> Path:
    root = tmp_path / "game"
    create_project(root, "Game", template_id="blank")
    create_project(root / "inner", "Inner", template_id="blank")  # a nested project, its own owner
    return root


def test_whose_project_a_path_is(outer: Path, tmp_path: Path) -> None:
    inner = outer / "inner"
    assert project_root(outer) == outer.resolve()
    assert project_root(outer / REGION / "scenes/start.json") == outer.resolve()  # an ordinary folder: the project's
    assert project_root(outer / "scenes/not_yet/new.json") == outer.resolve()  # (paths that don't exist yet too)
    assert project_root(inner / REGION / "scenes/start.json") == inner.resolve()  # a nested project: its own
    assert project_root(outer / "inner/../scenes/x.json") == outer.resolve()  # (``..`` resolved)
    assert project_root(tmp_path / "nowhere") is None

    assert ownership_root(outer / REGION) == outer.resolve()  # started inside: the project's lock, not the folder's
    assert ownership_root(inner / REGION) == inner.resolve()
    assert ownership_root(tmp_path / "loose") == (tmp_path / "loose").resolve()  # in no project: the folder itself

    assert in_project(outer, outer / REGION / "scenes/start.json")
    assert not in_project(outer, inner / REGION / "scenes/start.json")  # the nested project's: not with outer's lock
    assert in_project(inner, inner / REGION / "scenes/start.json")
    assert not in_project(outer, tmp_path / "elsewhere.json")
    assert not in_project(outer, outer / "inner/../../elsewhere.json")
    assert in_project(tmp_path / "loose", tmp_path / "loose/a/b.json")  # a loose folder: its files, no project's
    assert not in_project(tmp_path, outer / "scenes/x.json")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows paths (case, junctions); the default lane runs this on Windows")
def test_windows_case_and_junctions(outer: Path, tmp_path: Path) -> None:
    assert ownership_root(str(outer / REGION).upper()) == outer.resolve()
    assert in_project(str(outer).upper(), str(outer / REGION / "scenes/start.json").lower())
    junction = outer / "shortcut"  # a junction inside the outer project, into the nested one
    made = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(outer / "inner" / REGION)],
                          capture_output=True, text=True)
    assert made.returncode == 0, made.stdout + made.stderr
    try:
        assert project_root(junction / "scenes/start.json") == (outer / "inner").resolve()
        assert not in_project(outer, junction / "scenes/start.json")
    finally:
        os.rmdir(junction)  # (removes the junction only, never what it points to)


def test_a_link_into_a_nested_project_is_the_nested_projects(outer: Path) -> None:
    link = outer / "link"
    try:
        link.symlink_to(outer / "inner" / REGION, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symbolic links can't be made here ({exc})")
    assert not in_project(outer, link / "scenes/start.json")
    assert in_project(outer / "inner", link / "scenes/start.json")


def test_writers_starting_in_different_folders_of_one_project_take_one_lock(outer: Path) -> None:
    held = project_ownership.acquire(ownership_root(outer), project_ownership.AUTHORING)
    try:
        other = subprocess.run([sys.executable, "-c", (
            "import sys; sys.path.insert(0, sys.argv[1]); from engine.editor import project_ownership as o\n"
            "try:\n    o.acquire(o.ownership_root(sys.argv[2]), o.AUTHORING, wait=0.2); print('ACQUIRED')\n"
            "except o.OwnedElsewhere as e:\n    print('REFUSED', e.holder.get('kind'))"),
            str(REPO), str(outer / REGION / "scenes")], capture_output=True, text=True, timeout=120)
        assert other.stdout.strip().splitlines()[-1] == "REFUSED authoring", other.stdout + other.stderr
        assert not (outer / REGION / "scenes/.mesh").exists()  # no second lock identity for an inner folder
        nested = subprocess.run([sys.executable, "-c", (
            "import sys; sys.path.insert(0, sys.argv[1]); from engine.editor import project_ownership as o\n"
            "h = o.acquire(o.ownership_root(sys.argv[2]), o.AUTHORING, wait=0.2); print('ACQUIRED', h.root.name)"),
            str(REPO), str(outer / "inner" / REGION)], capture_output=True, text=True, timeout=120)
        assert nested.stdout.strip().splitlines()[-1] == "ACQUIRED inner", nested.stdout + nested.stderr  # its own owner
    finally:
        held.release()


def test_aiops_held_to_a_project_writes_its_files_and_no_nested_projects(outer: Path) -> None:
    ops = AIOps(outer / REGION, project=ownership_root(outer / REGION))  # started inside, the project held
    assert ops.add_light("scenes/start.json", {"x": 1, "y": 1, "radius": 9}).ok  # an ordinary folder: allowed
    nested = outer / "inner" / REGION / "scenes/start.json"
    before = nested.read_bytes()
    whole = AIOps(outer, project=outer)
    refused = whole.apply_job({"operations": [{"type": "add_light", "scene_path": f"inner/{REGION}/scenes/start.json",
                                               "light": {"x": 1, "y": 1, "radius": 9}}]})
    assert not refused["ok"] and "another Mesh project than the one held" in refused["results"][0]["message"]
    with pytest.raises(ValueError, match="another Mesh project than the one held"):
        whole.create_scene("inner/scenes/attic")
    assert nested.read_bytes() == before and not (outer / "inner/scenes/attic.json").exists()
    assert AIOps(outer / "inner", project=outer / "inner").add_light(f"{REGION}/scenes/start.json", {"x": 2, "y": 2}).ok
    assert AIOps(outer).add_light(f"inner/{REGION}/scenes/start.json", {"x": 3, "y": 3}).ok  # (no project held: as before)
