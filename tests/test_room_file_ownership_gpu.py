"""#462 S4 in Mesh Studio's own window (hidden): a room made, undone and made again; a room redone whose map was deleted.

Studio loads a room's map file from disk from the moment the room is made, so this needs the real window: the person
makes "Cellar" (2D, then HD-2D), undoes it with Ctrl+Z and makes "Cellar" again. That was refused ("There is already a
file at .../maps/cellar.json"); now it is a new room, ``cellar_2``, drawn, play-tested and saved. And a room undone
whose map file is deleted meanwhile is whole again on Ctrl+Y: drawn and play-tested from its map file, which is written
again before the room is shown. GL-gated: set MESH_GL_SMOKE=1.
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
def driver(tmp_path: Path) -> Iterator[Any]:
    import hd2d_floors_demo
    from hd2d_studio_demo import StudioDriver

    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    project = hd2d_floors_demo.build(tmp_path / "HD-2D studio")
    d = StudioDriver(project)
    try:
        yield d
    finally:
        d.close()
        os.environ.pop("MESH_STUDIO_NO_AI_BRIDGE", None)


def _make(d: Any, kind: str, label: str) -> str:
    studio = d.studio
    studio.new_room_form = {"kind": kind, "width": 24, "depth": 16, "outdoor": True}
    studio.create_room(label)
    d.advance()
    assert studio.message.startswith(f"Created {label}"), studio.message
    return str(studio.project.current)


def _play_a_little(d: Any) -> None:
    studio = d.studio
    studio.play()
    d.advance(5)
    assert studio.mode == "play", studio.message
    studio.stop()
    d.advance()
    assert studio.mode == "edit"


@pytest.mark.parametrize("kind", ["2d", "hd2d"])
def test_a_room_made_again_after_undo_in_studio(driver: Any, kind: str) -> None:
    d, studio = driver, driver.studio
    k, ctrl = d.arcade.key, d.arcade.key.MOD_CTRL
    root = studio.project.root
    key = _make(d, kind, "Cellar")
    old_map = studio.project.map_path(key)
    assert key == "cellar" and (root / old_map).is_file()

    d.key(k.Z, ctrl)
    assert key not in studio.project.world["scenes"] and (root / old_map).is_file()
    again = _make(d, kind, "Cellar")  # was: refused, the old map file in the way
    new_map = studio.project.map_path(again)
    assert again == "cellar_2" and studio.project.label(again) == "Cellar"
    assert (root / new_map).is_file() and not (root / old_map).exists()
    d.advance(3)
    _play_a_little(d)
    d.key(k.S, ctrl)
    assert studio.message.startswith("Saved"), studio.message
    world = json.loads((root / studio.project.world_file).read_text(encoding="utf-8"))
    assert again in world["scenes"] and key not in world["scenes"]


@pytest.mark.parametrize("kind", ["2d", "hd2d"])
def test_a_room_whose_map_was_deleted_while_undone_comes_back_whole_in_studio(driver: Any, kind: str) -> None:
    d, studio = driver, driver.studio
    k, ctrl = d.arcade.key, d.arcade.key.MOD_CTRL
    root = studio.project.root
    key = _make(d, kind, "Cellar")
    map_rel = studio.project.map_path(key)
    made = (root / map_rel).read_bytes()

    d.key(k.Z, ctrl)
    (root / map_rel).unlink()  # (deleted outside Studio while the room was undone)
    d.key(k.Y, ctrl)
    assert key in studio.project.world["scenes"] and (root / map_rel).read_bytes() == made
    studio.switch_room(key)
    d.advance(3)
    assert studio.project.current == key
    _play_a_little(d)
    d.key(k.S, ctrl)
    assert studio.message.startswith("Saved"), studio.message
    assert studio.project.kept_files == []


def test_closing_studio_removes_a_map_file_only_an_undone_room_used(driver: Any) -> None:
    d, studio = driver, driver.studio
    k, ctrl = d.arcade.key, d.arcade.key.MOD_CTRL
    root = studio.project.root
    saved_map = studio.project.map_path(_make(d, "2d", "Attic"))
    d.key(k.S, ctrl)
    undone_map = studio.project.map_path(_make(d, "2d", "Cellar"))
    d.key(k.Z, ctrl)
    d.key(k.S, ctrl)
    assert not studio.project.is_dirty and (root / undone_map).is_file()
    assert studio.on_close() is False, "nothing unsaved: Studio closes without asking"
    assert not (root / undone_map).exists() and (root / saved_map).is_file()


def test_discarding_unsaved_changes_on_close_removes_the_new_rooms_map_file(driver: Any) -> None:
    d, studio = driver, driver.studio
    k, ctrl = d.arcade.key, d.arcade.key.MOD_CTRL
    root = studio.project.root
    saved_map = studio.project.map_path(_make(d, "hd2d", "Attic"))
    d.key(k.S, ctrl)
    unsaved_map = studio.project.map_path(_make(d, "2d", "Cellar"))
    assert studio.project.is_dirty and studio.on_close() is True, "unsaved: Studio asks first"
    studio._close_choice("discard")
    assert not (root / unsaved_map).exists() and (root / saved_map).is_file()
