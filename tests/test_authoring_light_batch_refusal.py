"""A-07b: a batch can't shift or remove a light it added earlier (an ``@N`` may name it).

Before: ``add_light`` then ``remove_light`` of a lower (or the same) index silently moved (or dropped) the light the
batch's own ``@N`` meant. Now the whole batch is refused and no file changes. Through ``authoring.apply`` and the
MCP ``apply_ops`` path.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import authoring
from engine.authoring import ChangeError
from engine.mcp_server import tools
from engine.project_scaffold import create_project
from engine.studio_project import Project

pytestmark = pytest.mark.integration
SCENE = "packs/core_regions/scenes/start.json"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "game"
    create_project(path, "Game", template_id="blank")
    return path


def _project(root: Path) -> Project:
    return Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"])


def _xs(root: Path, scene: str = SCENE) -> list[float]:
    return [lt["x"] for lt in json.loads((root / scene).read_text(encoding="utf-8")).get("lights", [])]


def _seed(root: Path, n: int = 2) -> None:
    _run(_project(root), [{"op": "add_light", "x": 10 * (i + 1), "y": 0} for i in range(n)])


def _run(project: Project, changes: list) -> dict:
    result = authoring.apply(project, changes)
    project.save()
    return result


def _snapshot(root: Path) -> dict[Path, bytes]:
    return {p: p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file() and ".mesh" not in p.parts}


add = {"op": "add_light", "x": 99, "y": 0}


@pytest.mark.parametrize("removed", [0, 2])  # a lower index (shifts @0) / the created light itself (vanishes)
def test_authoring_refuses_remove_that_shifts_or_drops_an_added_light(root: Path, removed: int) -> None:
    _seed(root)
    before = _snapshot(root)
    project = _project(root)
    with pytest.raises(ChangeError) as err:
        authoring.apply(project, [add, {"op": "remove_light", "index": removed}, {"op": "set_light", "index": "@0", "radius": 50}])
    assert err.value.index == 1 and "'start'" in str(err.value) and "[2]" in str(err.value)
    project.save()
    assert _snapshot(root) == before


@pytest.mark.parametrize("removed", [0, 2])
def test_mcp_refuses_the_same_and_changes_no_file(root: Path, removed: int) -> None:
    _seed(root)
    before = _snapshot(root)
    result = tools.apply_ops([{"type": "add_light", "scene_path": SCENE, "light": {"x": 99, "y": 0}},
                              {"type": "delete_light", "scene_path": SCENE, "index": removed}], root=str(root))
    assert not result["ok"]
    assert _snapshot(root) == before


def test_removing_a_light_with_none_added_in_the_room_is_allowed(root: Path) -> None:
    _seed(root, 3)
    _run(_project(root), [{"op": "remove_light", "index": 0}, add])
    assert _xs(root) == [20.0, 30.0, 99.0]
    result = tools.apply_ops([{"type": "delete_light", "scene_path": SCENE, "index": 0}], root=str(root))
    assert result["ok"], result
    assert _xs(root) == [30.0, 99.0]


def test_remove_then_add_is_allowed(root: Path) -> None:
    _seed(root)
    created = _run(_project(root), [{"op": "remove_light", "index": 0}, add,
                                    {"op": "set_light", "index": "@1", "radius": 50}])["created"]
    assert created[1] == 1 and _xs(root) == [20.0, 99.0]


def test_a_light_added_in_another_room_is_unaffected(root: Path) -> None:
    project = _project(root)
    other = project.add_room("Cellar")
    start = project.current
    _run(project, [{"op": "add_light", "room": start, "x": 1, "y": 0}, {"op": "add_light", "room": start, "x": 2, "y": 0}])
    _run(project, [{"op": "add_light", "room": other, "x": 7, "y": 0}, {"op": "remove_light", "room": start, "index": 0}])
    assert _xs(root) == [2.0]
    with pytest.raises(ChangeError):
        authoring.apply(project, [{"op": "add_light", "room": other, "x": 8, "y": 0},
                                  {"op": "remove_light", "room": other, "index": 0}])
