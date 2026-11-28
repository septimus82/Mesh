"""#462 S2 in Mesh Studio's own window (hidden): a saved new room undone, saved, redone and saved again.

The person creates a room (a 2D room, then an HD-2D one), saves with Ctrl+S, undoes the room with Ctrl+Z and saves
again. Studio's Save crashed there (KeyError: the room looked up in a world without it). Now each save says so, the
world on disk drops the room and gets it back on Ctrl+Y and Ctrl+S, and the project reopens with the room and its
contents. GL-gated: set MESH_GL_SMOKE=1.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from engine import optional_arcade

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                       reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)"),
    pytest.mark.filterwarnings("ignore:draw_text is an extremely slow function"),
    pytest.mark.filterwarnings("ignore:UIInputText is now a UIStyledWidget:DeprecationWarning"),
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))


@pytest.fixture
def driver(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    import hd2d_floors_demo
    from hd2d_studio_demo import StudioDriver

    monkeypatch.setenv("MESH_STUDIO_NO_AI_BRIDGE", "1")
    project = hd2d_floors_demo.build(tmp_path / "HD-2D studio")
    d = StudioDriver(project)
    try:
        yield d
    finally:
        d.close()


def _rooms_on_disk(project: Any) -> set[str]:
    return set(json.loads((project.root / project.world_file).read_text(encoding="utf-8"))["scenes"])


@pytest.mark.parametrize("kind", ["2d", "hd2d"])
def test_a_saved_new_room_undone_saves_redoes_and_reopens_in_studio(driver: Any, kind: str) -> None:
    d, studio = driver, driver.studio
    k, ctrl = d.arcade.key, d.arcade.key.MOD_CTRL
    origin = studio.project.current
    studio.new_room_form = {"kind": kind, "width": 24, "depth": 16, "outdoor": True}
    studio.create_room("Cellar")
    d.advance()
    key = studio.project.current
    assert key != origin and studio.project.is_dirty
    room_file = studio.project.root / studio.project.path(key)

    d.key(k.S, ctrl)
    assert not studio.project.is_dirty and key in _rooms_on_disk(studio.project) and room_file.is_file()
    saved = room_file.read_bytes()

    d.key(k.Z, ctrl)  # the room's creation
    assert key not in studio.project.world["scenes"] and studio.project.current == origin
    d.key(k.S, ctrl)  # was: KeyError out of Studio's Save
    assert studio.message.startswith("Saved"), studio.message
    assert not studio.project.is_dirty and key not in _rooms_on_disk(studio.project)
    assert room_file.read_bytes() == saved  # (its file is left as it is)

    d.key(k.Y, ctrl)
    assert key in studio.project.world["scenes"] and studio.project.is_dirty
    d.key(k.S, ctrl)
    assert studio.message.startswith("Saved"), studio.message
    assert not studio.project.is_dirty and key in _rooms_on_disk(studio.project)
    assert room_file.read_bytes() == saved

    from engine.studio_project import Project

    again = Project(studio.project.root, studio.project.world_file)
    assert again.scene(key)["name"] == studio.project.scene(key)["name"]
    assert again.map_path(key) and (again.root / str(again.map_path(key))).is_file()
