"""#462 R1 with Mesh Studio itself: a revision read before Studio closed and opened again never passes for the reopened
project's, each Studio a real process with a real (hidden) window (``engine.studio.open_studio``, through
``tests/studio_owner_process.py real``): Studio's own way of opening a project gives each opening its identity.
The AI is ``engine.authoring_session``, in this process. GL-gated: MESH_GL_SMOKE=1. Without a window, and the rest:
tests/test_studio_revision_identity.py.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from engine import authoring_session, optional_arcade
from engine.project_scaffold import create_project
from tests.test_studio_project_ownership import REPO, ROOM, StudioProcess

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                       reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)"),
]


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "game"
    create_project(path, "Game", template_id="blank")
    return path


@pytest.fixture
def studios(tmp_path: Path) -> Iterator[Any]:
    """``open(root)`` starts Mesh Studio (a real hidden window, live session on) in its own process."""
    started: list[StudioProcess] = []
    settings = str(tmp_path / "user_settings.json")  # (each Studio's own settings file: never the checkout's)

    def open_studio(root: Path) -> StudioProcess:
        env = {"MESH_TEST_OWNER_WAIT": "0.3", "MESH_RUNTIME_SETTINGS_PATH": settings, "PYTHONPATH": str(REPO),
               "MESH_STUDIO_NO_AI_BRIDGE": None}
        studio = StudioProcess(root, "real", log=tmp_path / f"studio_{len(started)}.log", env=env)
        assert studio.start["ready"], studio.start
        started.append(studio)
        return studio

    yield open_studio
    for studio in started:
        if studio.proc.poll() is None:
            studio.proc.kill()
        studio.end()


def test_mesh_studio_reopened_never_takes_a_revision_read_before(root: Path, studios: Any) -> None:
    setup = studios(root)
    setup.ask("edit Warden")
    setup.ask("save")
    assert setup.close() == 0
    warden = next(e["id"] for e in json.loads((root / ROOM).read_text(encoding="utf-8"))["entities"]
                  if e.get("name") == "Warden")
    rename = [{"op": "rename_entity", "entity_id": warden, "name": "AI Warden"}]

    a = studios(root)
    read = authoring_session.read_project(root)
    a.ask(f"rename {warden} Creator Warden")
    assert a.ask("save")["saved"] == [ROOM]
    assert a.close() == 0
    b = studios(root)
    fresh = authoring_session.read_project(root)
    assert read["revision"] == fresh["revision"] and read["revision_id"] != fresh["revision_id"]

    assert authoring_session.propose(root, rename, base_revision=read["revision"])["reason"] == "revision_id_required"
    assert authoring_session.propose(root, rename,
                                     base_revision_id=read["revision_id"])["reason"] == "revision_from_another_session"
    assert b.ask("state")["pending"] == []
    staged = authoring_session.propose(root, rename, base_revision_id=fresh["revision_id"])
    assert staged["ok"] and b.ask("state")["pending"] == ["Changes from an AI"]
    assert b.ask("accept")["result"]["ok"] and "AI Warden" in b.ask("state")["names"]
    assert b.ask("undo")["done"] and "Creator Warden" in b.ask("state")["names"]
    assert b.close() == 0
