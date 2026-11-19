"""#462: Mesh Studio's tileset import never writes a file of another Mesh project.

Importing a tileset writes its picture and description into the project's ``assets/tilesets`` and adds it to the map
file of every room the world lists, straight away (not part of a save). The outer game's world lists a room of a
content pack that is a Mesh project of its own, open in its own Mesh Studio: the outer Studio's import rewrote that
project's map file behind its Studio, pointing it at a tileset outside it. Now every destination is worked out first
and checked against the hold Studio has (``Project.import_tileset(owner=...)``, ``Ownership.owns``): any file of
another project refuses the whole import before anything is written.

Each Studio is a real process with a real hidden window (``engine.studio.open_studio`` through
``tests/studio_owner_process.py real``); the import is the Import tileset panel's own action. GL-gated:
MESH_GL_SMOKE=1. The same rules on ``Project.import_tileset`` without a window: tests/test_tileset_import_ownership.py.
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
from tests.test_studio_project_ownership import REPO, StudioProcess, _files

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                       reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)"),
]
MAP = "packs/core_regions/maps/start.json"  # (a scaffolded project's start room's map file)
NESTED_MAP = f"packs/region2/{MAP}"


@pytest.fixture
def outer(tmp_path: Path) -> Path:
    """The outer game; its world lists the start room of packs/region2, a Mesh project of its own."""
    root = tmp_path / "game"
    create_project(root, "Game", template_id="blank")
    create_project(root / "packs/region2", "Region 2", template_id="blank")
    world_path = root / json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"]
    world = json.loads(world_path.read_text(encoding="utf-8"))
    world["scenes"]["cellar"] = {"label": "Cellar", "path": "packs/region2/packs/core_regions/scenes/start.json"}
    world_path.write_text(json.dumps(world, indent=2), encoding="utf-8")
    return root


@pytest.fixture
def image(tmp_path: Path) -> str:
    from PIL import Image

    path = tmp_path / "rocks.png"
    Image.new("RGBA", (64, 32), (90, 90, 90, 255)).save(path)
    return str(path)


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


def _sources(path: Path) -> list[str]:
    return [str(t.get("source")) for t in json.loads(path.read_text(encoding="utf-8")).get("tilesets") or []]


def _holder_pid(root: Path) -> Any:
    return (project_ownership.owned(root) or {}).get("pid")


def _import(studio: StudioProcess, path: str, name: str) -> dict[str, Any]:
    return studio.ask("import_tileset " + json.dumps({"path": path, "tile": "32", "name": name}))


def test_outer_studios_import_never_writes_a_map_file_another_studio_owns(
        outer: Path, image: str, studios: Any, tmp_path: Path) -> None:
    nested = outer / "packs/region2"
    child = studios(nested)  # Mesh Studio on the nested project: its lock
    parent = studios(outer)  # Mesh Studio on the outer project: its own lock

    # two writers, each in its own project: the nested project's own Studio imports into it
    done = _import(child, image, "Moss")
    assert done["ok"] and done["message"].startswith("Imported Moss: 2 tiles"), done
    assert (nested / "assets/tilesets/moss.png").is_file() and (nested / "assets/tilesets/moss.json").is_file()
    assert any(s.endswith("assets/tilesets/moss.json") for s in _sources(nested / MAP))
    child.ask("edit Child Unsaved")
    parent.ask("edit Outer Unsaved")
    before = _files(outer)  # (the nested project's files included)

    # the outer Studio's import: its own map and tileset files are allowed, the nested map is not: refused whole
    refused = _import(parent, image, "Rocks")
    assert refused["ok"] is False and refused["panel"] == "import_tileset", refused
    message = refused["message"]
    assert message.startswith(f"Not imported: {NESTED_MAP} is in another Mesh project than the one held"), message
    assert "so nothing was written: that project has its own owner" in message
    assert _files(outer) == before  # no picture, no description, no map file changed, in either project
    assert not (outer / "assets/tilesets/rocks.png").exists() and not (outer / "assets/tilesets/rocks.json").exists()

    # both locks still their legitimate owners'; both Studios' unsaved work still there
    assert _holder_pid(outer) == parent.start["pid"] and _holder_pid(nested) == child.start["pid"]
    held = child.ask("state")
    assert "Child Unsaved" in held["names"] and held["unsaved"]
    held = parent.ask("state")
    assert "Outer Unsaved" in held["names"] and held["unsaved"]
    assert child.close() == 0 and parent.close() == 0

    # an ordinary project imports as before: picture, description, every room's map
    plain = tmp_path / "plain"
    create_project(plain, "Plain", template_id="blank")
    studio = studios(plain)
    done = _import(studio, image, "Rocks")
    assert done["ok"] and done["message"].startswith("Imported Rocks: 2 tiles"), done
    assert (plain / "assets/tilesets/rocks.png").is_file() and (plain / "assets/tilesets/rocks.json").is_file()
    assert any(s.endswith("assets/tilesets/rocks.json") for s in _sources(plain / MAP))
    assert studio.close() == 0
