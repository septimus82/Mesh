"""#462 R5 remediation B (independent verification of remediation A): adapted authoring saves only the held project.

Finding 1: MCP ``apply_ops`` whose operations are room edits of a Studio project goes the authoring route
(``authoring_session.apply``: the project owned, ``Project.save``). The outer game's world listed a room in a content
pack that had since become a Mesh project of its own (open in Studio, its own lock): the save wrote that room behind
its Studio, under the outer project's lock. Now ``Project.save(owner=...)`` checks every file it is about to write
(the exact list handed to ``save_documents``) against the lock held, and refuses the whole save first.

Finding 3, the MCP side: a lock taken on a nested project covers only what it was taken as; its ``config.json``
removed mid-write, neither route writes the files (now the outer project's).

Studio and lock holders are their own processes (the OS lock).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from engine import authoring, authoring_session
from engine.ai_ops import AIOps
from engine.editor import project_ownership
from engine.mcp_server import tools
from engine.project_scaffold import create_project
from tests.test_studio_project_ownership import StudioProcess

pytestmark = pytest.mark.integration  # (F13-A: subprocesses, OS locks)
ROOM = "packs/core_regions/scenes/start.json"
CELLAR = "packs/region2/scenes/cellar.json"
LIGHT = {"x": 5, "y": 5, "radius": 40}


@pytest.fixture
def outer(tmp_path: Path) -> Path:
    root = tmp_path / "game"
    create_project(root, "Game", template_id="blank")
    return root


@pytest.fixture
def studios(tmp_path: Path) -> Iterator[Any]:
    started: list[StudioProcess] = []

    def open_studio(project: Path) -> StudioProcess:
        studio = StudioProcess(project, "nobridge", log=tmp_path / f"studio_{len(started)}.log",
                               env={"MESH_TEST_OWNER_WAIT": "0.3"})
        started.append(studio)
        assert studio.start["ready"], studio.start
        studio.ask("edit Unsaved Warden")
        return studio

    yield open_studio
    for studio in started:
        if studio.proc.poll() is None:
            studio.proc.kill()
        studio.end()


def _files(path: Path) -> dict[str, str]:
    skip = ("owner.lock", "live_session.json")
    return {p.relative_to(path).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(path.rglob("*")) if p.is_file() and p.name not in skip}


def _nested_pack(outer: Path) -> Path:
    """The outer world lists a room in packs/region2, which then becomes a Mesh project of its own."""
    region = outer / "packs/region2"
    (region / "scenes").mkdir(parents=True)
    shutil.copy(outer / ROOM, region / "scenes/cellar.json")
    world_path = outer / json.loads((outer / "config.json").read_text(encoding="utf-8"))["world_file"]
    world = json.loads(world_path.read_text(encoding="utf-8"))
    world["scenes"]["cellar"] = {"label": "Cellar", "path": CELLAR}
    world_path.write_text(json.dumps(world, indent=2), encoding="utf-8")
    (region / "worlds").mkdir()
    (region / "worlds/main.json").write_text(json.dumps({"id": "main", "name": "Region", "start_scene": "cellar",
        "scenes": {"cellar": {"label": "Cellar", "path": "scenes/cellar.json"}}}), encoding="utf-8")
    shutil.copytree(outer / "assets", region / "assets")
    (region / "config.json").write_text(json.dumps({"title": "Region 2", "world_file": "worlds/main.json",
                                                    "start_scene": "scenes/cellar.json"}), encoding="utf-8")
    return region


# ------------------------------------------------------------------------------------------------------ finding 1
def test_adapted_authoring_never_saves_a_room_of_a_nested_project(outer: Path, studios: Any) -> None:
    region = _nested_pack(outer)
    studio = studios(region)  # Mesh Studio has region2 open, with unsaved work; region2's lock is its
    before = _files(outer)
    result = tools.apply_ops([{"type": "add_light", "scene_path": CELLAR, "light": LIGHT}], root=str(outer),
                             validate=False)
    authored = result.get("authoring") or {}
    assert result["ok"] is False and authored, result  # (the adapted authoring route, not the file fallback)
    assert authored["reason"] == "save_failed" and authored["save"]["reason"] == "not_this_project", authored
    assert "packs/region2/scenes/cellar.json is in another Mesh project than the one held" in authored["message"]
    assert _files(outer) == before  # the nested project's files (and the outer's) byte-identical
    held = studio.ask("state")
    assert "Unsaved Warden" in held["names"] and held["unsaved"]
    assert project_ownership.owned(outer) is None


def test_the_persistence_path_refuses_it_whoever_calls_it_and_whether_or_not_the_nested_project_is_open(
        outer: Path) -> None:
    _nested_pack(outer)
    changes = tools._studio_changes([{"type": "add_light", "scene_path": CELLAR, "light": LIGHT}], str(outer))
    assert changes  # (what the adapted route sends)
    before = _files(outer)
    result = authoring_session.apply(outer, changes)  # (``mesh author apply`` too)
    assert result["ok"] is False and result["save"]["reason"] == "not_this_project", result
    assert _files(outer) == before


def test_a_normal_room_still_saves_through_adapted_authoring(outer: Path) -> None:
    _nested_pack(outer)  # (the nested room is there; this change doesn't touch it)
    result = tools.apply_ops([{"type": "add_light", "scene_path": ROOM, "light": LIGHT}], root=str(outer), validate=False)
    assert result["ok"] is True and result["authoring"]["source"] == "files", result
    assert len(json.loads((outer / ROOM).read_text(encoding="utf-8"))["lights"]) == 1
    nested = outer / "packs/region2"
    result = tools.apply_ops([{"type": "add_light", "scene_path": "scenes/cellar.json", "light": LIGHT}],
                             root=str(nested), validate=False)  # the nested project, under its own lock
    assert result["ok"] is True, result
    assert len(json.loads((nested / "scenes/cellar.json").read_text(encoding="utf-8")).get("lights") or []) == 1


# ------------------------------------------------------------------------------------------------------ finding 3
@pytest.mark.parametrize("route", ["adapted", "fallback"])
def test_a_nested_projects_lock_covers_nothing_once_it_stopped_being_a_project(
        outer: Path, studios: Any, route: str, monkeypatch: pytest.MonkeyPatch) -> None:
    inner = outer / "inner"
    create_project(inner, "Inner", template_id="blank")
    studios(outer)  # Mesh Studio has the outer project
    started, go = threading.Event(), threading.Event()
    owner_obj, name = (authoring, "apply") if route == "adapted" else (AIOps, "apply_job")
    original = getattr(owner_obj, name)

    def paused(*args: Any, **kwargs: Any) -> Any:
        started.set()
        assert go.wait(60)
        return original(*args, **kwargs)

    monkeypatch.setattr(owner_obj, name, paused)
    op = ({"type": "add_light", "scene_path": ROOM, "light": LIGHT} if route == "adapted" else
          {"type": "set_world_start", "world_path": "packs/core_regions/worlds/main.json", "start_scene": "x"})
    result: list[dict[str, Any]] = []
    thread = threading.Thread(target=lambda: result.append(tools.apply_ops([op], root=str(inner), validate=False)))
    thread.start()
    try:
        assert started.wait(60)  # holding the nested project's lock, mid-write
        assert (project_ownership.owned(inner, wait=0) or {}).get("kind") == project_ownership.AUTHORING
        (inner / "config.json").unlink()  # it stops being a project: its files are the outer project's
        before = _files(outer)
    finally:
        go.set()
        thread.join(60)
    assert result[0]["ok"] is False, result
    if route == "adapted":
        assert result[0]["authoring"]["save"]["reason"] == "not_this_project"
    else:
        assert "another Mesh project than the one held" in result[0]["results"][0]["message"]
    assert _files(outer) == before
