"""#462: a tileset import writes only files of the project its writer holds (``Project.import_tileset(owner=...)``).

The import's destinations (the tileset's picture and description, and the map file of every room the world lists) are
worked out first and each checked against the hold (``Ownership.owns``); any file of another Mesh project refuses the
whole import before anything is written. Mesh Studio's own import passes its hold (real windows:
tests/test_studio_tileset_ownership_gpu.py). Holders are real OS locks; the nested project's Studio is its own process.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from engine import authoring
from engine import project_ops as ops
from engine.editor import project_ownership
from engine.project_scaffold import create_project
from engine.studio_project import Project
from tests.test_studio_project_ownership import StudioProcess

pytestmark = pytest.mark.integration  # (F13-A: subprocesses, OS locks)
MAP = "packs/core_regions/maps/start.json"
NESTED_MAP = f"packs/region2/{MAP}"


@pytest.fixture
def outer(tmp_path: Path) -> Path:
    root = tmp_path / "game"
    create_project(root, "Game", template_id="blank")
    create_project(root / "packs/region2", "Region 2", template_id="blank")
    world_path = root / json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"]
    world = json.loads(world_path.read_text(encoding="utf-8"))
    world["scenes"]["cellar"] = {"label": "Cellar", "path": "packs/region2/packs/core_regions/scenes/start.json"}
    world_path.write_text(json.dumps(world, indent=2), encoding="utf-8")
    return root


@pytest.fixture
def image(tmp_path: Path) -> Path:
    from PIL import Image

    path = tmp_path / "rocks.png"
    Image.new("RGBA", (64, 32), (90, 90, 90, 255)).save(path)
    return path


@pytest.fixture
def held(outer: Path) -> Iterator[Any]:
    """The outer project held as Mesh Studio holds it."""
    hold = project_ownership.acquire(outer, project_ownership.STUDIO, wait=2.0)
    yield hold
    hold.release()


def _open(root: Path) -> Project:
    return Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"])


def _files(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and ".mesh" not in p.relative_to(root).parts}


def _sources(path: Path) -> list[str]:
    return [str(t.get("source")) for t in json.loads(path.read_text(encoding="utf-8")).get("tilesets") or []]


def _refused(project: Project, image: Path, held: Any) -> str:
    before = _files(project.root)
    with pytest.raises(ops.OpError) as caught:
        project.import_tileset(image, 32, "Rocks", owner=held)
    assert _files(project.root) == before  # nothing written: the allowed files (picture, description, own map) neither
    return str(caught.value)


def test_a_nested_project_another_studio_holds_refuses_the_whole_import(
        outer: Path, image: Path, held: Any, tmp_path: Path) -> None:
    nested = outer / "packs/region2"
    child = StudioProcess(nested, "nobridge", log=tmp_path / "child.log", env={"MESH_TEST_OWNER_WAIT": "0.3"})
    try:
        assert child.start["ready"], child.start
        child.ask("edit Child Unsaved")
        project = _open(outer)
        authoring.apply(project, [{"op": "place_prefab", "prefab": "person", "x": 64, "y": 64}])
        revision, scene = project.revision, json.dumps(project.scene(), sort_keys=True)
        message = _refused(project, image, held)
        assert message == (f"Not imported: {NESTED_MAP} is in another Mesh project than the one held ({held.root}), "
                           "so nothing was written: that project has its own owner.")
        assert project.is_dirty and project.revision == revision  # (the outer edit, unsaved, as it was)
        assert json.dumps(project.scene(), sort_keys=True) == scene
        assert (project_ownership.owned(nested) or {}).get("pid") == child.start["pid"]
        state = child.ask("state")
        assert "Child Unsaved" in state["names"] and state["unsaved"]
    finally:
        child.close()


def test_another_projects_map_refuses_it_whether_or_not_that_project_is_open(outer: Path, image: Path, held: Any) -> None:
    assert project_ownership.owned(outer / "packs/region2") is None
    assert _refused(_open(outer), image, held).startswith(f"Not imported: {NESTED_MAP} is in another Mesh project")


def test_ordinary_imports_write_every_destination(outer: Path, image: Path, held: Any, tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    create_project(plain, "Plain", template_id="blank")
    with project_ownership.acquire(plain, project_ownership.STUDIO, wait=2.0) as hold:
        result = _open(plain).import_tileset(image, 32, "Rocks", owner=hold)
    assert result == {"name": "Rocks", "source": "assets/tilesets/rocks.json", "count": 2, "scaled": False}
    assert (plain / "assets/tilesets/rocks.png").is_file() and (plain / "assets/tilesets/rocks.json").is_file()
    assert any(s.endswith("assets/tilesets/rocks.json") for s in _sources(plain / MAP))

    # two writers, each in its own project: the nested project under its own lock imports into itself, while the
    # outer project is held by another writer
    nested = outer / "packs/region2"
    with project_ownership.acquire(nested, project_ownership.STUDIO, wait=2.0) as hold:
        _open(nested).import_tileset(image, 32, "Moss", owner=hold)
    assert any(s.endswith("assets/tilesets/moss.json") for s in _sources(nested / MAP))
    assert not (outer / "assets/tilesets/moss.json").exists() and held.held
