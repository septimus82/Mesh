"""#462 P1: Mesh Studio's own save (Ctrl+S) never writes a room of another Mesh project.

The outer game's world lists a room in a content pack that later became a Mesh project of its own. Both are open, each
in its own Mesh Studio holding its own lock. The nested project's Studio saved its room; the outer Studio then saved
an older edit of that room with Ctrl+S and overwrote it, saying "Saved". Studio now hands its own hold on the project
to the save (``Project.save(owner=...)``, R5's destination check), so a save with any file of another project is
refused whole, before anything is written, and every edit stays unsaved in both Studios.

Each Studio is a real process with a real hidden window (``engine.studio.open_studio`` through
``tests/studio_owner_process.py real``), saved by the window's own Ctrl+S key event. GL-gated: MESH_GL_SMOKE=1.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from engine import optional_arcade
from engine.editor import project_ownership
from engine.project_scaffold import create_project
from tests.test_studio_project_ownership import REPO, ROOM, StudioProcess, _files

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                       reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)"),
]
CELLAR = f"packs/region2/{ROOM}"  # the nested project's own room, listed by the outer world as "cellar"


@pytest.fixture
def outer(tmp_path: Path) -> Path:
    """The outer game; its world lists a room in packs/region2, which then becomes a Mesh project of its own."""
    root = tmp_path / "game"
    create_project(root, "Game", template_id="blank")
    create_project(root / "packs/region2", "Region 2", template_id="blank")
    world_path = root / json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"]
    world = json.loads(world_path.read_text(encoding="utf-8"))
    world["scenes"]["cellar"] = {"label": "Cellar", "path": CELLAR}
    world_path.write_text(json.dumps(world, indent=2), encoding="utf-8")
    return root


@pytest.fixture
def studios(tmp_path: Path) -> Iterator[Any]:
    started: list[StudioProcess] = []
    settings = str(tmp_path / "user_settings.json")  # (each Studio's own settings file: never the checkout's)

    def open_studio(root: Path) -> StudioProcess:
        env = {"MESH_TEST_OWNER_WAIT": "0.3", "MESH_RUNTIME_SETTINGS_PATH": settings, "PYTHONPATH": str(REPO),
               "MESH_STUDIO_NO_AI_BRIDGE": "1"}
        studio = StudioProcess(root, "real", "nobridge", log=tmp_path / f"studio_{len(started)}.log", env=env)
        started.append(studio)
        assert studio.start["ready"], studio.start
        return studio

    yield open_studio
    for studio in started:
        if studio.proc.poll() is None:
            studio.proc.kill()
        studio.end()


def _names(path: Path) -> list[str]:
    return [str(e.get("name")) for e in json.loads(path.read_text(encoding="utf-8"))["entities"]]


def _holder_pid(root: Path) -> Any:
    return (project_ownership.owned(root) or {}).get("pid")


def test_outer_studios_ctrl_s_never_overwrites_a_room_another_studio_owns(outer: Path, studios: Any) -> None:
    nested = outer / "packs/region2"
    child = studios(nested)  # Mesh Studio on the nested project: its lock
    parent = studios(outer)  # Mesh Studio on the outer project: its own lock
    assert parent.ask(f"room {CELLAR}")["room"] == "cellar"
    parent.ask("edit Outer Old Edit")  # the outer Studio's edit of the nested room, older than the child's save

    # the nested project's own Studio saves its room (Ctrl+S): that still works
    child.ask("edit Child Work")
    saved = child.ask("ctrl_s")
    assert saved["ok"] and saved["message"] == "Saved 1 file(s)." and not saved["unsaved"], saved
    assert "Child Work" in _names(nested / ROOM)
    child.ask("edit Child Unsaved")
    before = _files(outer)  # (the nested project's files included)

    # the outer Studio's Ctrl+S: refused whole, nothing written, nothing said to be saved
    refused = parent.ask("ctrl_s")
    assert refused["ok"] is False and refused["unsaved"] and refused["rooms_unsaved"] == ["cellar"], refused
    message = refused["message"]
    assert message.startswith(f"Couldn't save: {CELLAR} is in another Mesh project than the one held"), message
    assert "so nothing was saved: that project has its own owner" in message
    assert message.endswith("Your changes are still here, unsaved."), message
    assert _files(outer) == before and not list(outer.rglob("*.outside-change.bak"))
    assert "Outer Old Edit" not in _names(nested / ROOM)

    # both locks still their legitimate owners'; both Studios' unsaved work still there
    assert _holder_pid(outer) == parent.start["pid"] and _holder_pid(nested) == child.start["pid"]
    held = child.ask("state")
    assert "Child Unsaved" in held["names"] and held["unsaved"]
    held = parent.ask("state")
    assert "Outer Old Edit" in held["names"] and held["unsaved"]

    # a mixed save (the outer project's own room too) is refused whole: not even the valid file is written
    parent.ask(f"room {ROOM}")
    parent.ask("edit Outer Room Work")
    refused = parent.ask("ctrl_s")
    assert refused["ok"] is False and len(refused["rooms_unsaved"]) == 2 and "cellar" in refused["rooms_unsaved"]
    assert refused["message"].startswith(f"Couldn't save: {CELLAR} is in another Mesh project"), refused
    assert _files(outer) == before
    assert "Outer Room Work" not in _names(outer / ROOM)

    # the outer project's own rooms still save normally
    assert parent.ask("undo")["done"] and parent.ask("undo")["done"]
    assert parent.ask("state")["unsaved"] is False
    parent.ask(f"room {ROOM}")  # (undo went back to the room it changed: the cellar)
    parent.ask("edit Outer Saved Work")
    saved = parent.ask("ctrl_s")
    assert saved["ok"] and saved["message"] == "Saved 1 file(s)." and not saved["unsaved"], saved
    assert "Outer Saved Work" in _names(outer / ROOM)
    assert {k: v for k, v in _files(outer).items() if k.startswith("packs/region2/")} == {
        k: v for k, v in before.items() if k.startswith("packs/region2/")}

    assert child.close() == 0 and parent.close() == 0
    assert project_ownership.owned(outer) is None and project_ownership.owned(nested) is None
