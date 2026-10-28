"""Milestone 22A: an HD-2D room made in Mesh Studio (its size), its gameplay camera, and its sun, ambient light and sky:
the operations Studio and AI tools edit through. Headless."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import engine.project_ops as ops
from engine.hd2d.settings import parse_hd2d

pytestmark = pytest.mark.fast

PATH = "packs/core_regions/scenes/meadow.json"


def _room(width: float = 40, depth: float = 30, *, outdoor: bool = True) -> dict:
    scene, _map_path, _skeleton = ops.make_hd2d_room({"name": "Meadow", "entities": []}, PATH, width, depth,
                                                     outdoor=outdoor)
    return scene


def test_a_new_hd2d_room_is_the_templates_own_recipe_at_its_size() -> None:
    from engine.hd2d.starter_village import INDOOR_VIEW, OUTDOOR_VIEW, _camera, _hd2d

    outdoor, indoor = _room(), _room(16, 12, outdoor=False)
    assert outdoor["settings"]["hd2d"] == _hd2d(40, 30, _camera(30.0, OUTDOOR_VIEW, (0, 0, 40, 30)))
    expected = _hd2d(16, 12, _camera(55.0, INDOOR_VIEW, (0, 0, 16, 12)), ambient=0.55, sky="#120e0b")
    assert indoor["settings"]["hd2d"] == expected
    assert (outdoor["settings"]["world_width"], outdoor["settings"]["world_height"]) == (1280.0, 960.0)
    assert outdoor["tilemap"]["width"] == 40 and outdoor["tilemap"]["height"] == 30  # a plain map of its size
    parse_hd2d(outdoor["settings"]["hd2d"])


def test_a_new_hd2d_room_replaces_a_2d_map_and_refuses_odd_sizes() -> None:
    scene, _path, _skeleton = ops.add_map({"name": "R", "entities": []}, PATH, width=20, height=15,
                                          ground=ops.STARTER_FLOOR, border=ops.STARTER_WALL)
    scene, _path, _skeleton = ops.make_hd2d_room(scene, PATH, 24, 18)
    assert scene["tilemap"]["width"] == 24
    for bad in (4, 300, "wide", True, math.nan):
        with pytest.raises(ops.OpError, match="8 to 256 m"):
            ops.make_hd2d_room({"name": "R", "entities": []}, PATH, bad, 20)


def test_the_camera_is_set_in_what_the_player_sees() -> None:
    scene = _room()
    assert ops.hd2d_camera_of(scene)["view"] == pytest.approx(11.25) and ops.hd2d_camera_of(scene)["pitch"] == 30
    scene = ops.set_hd2d_camera(scene, view=15, pitch=45, height=1.2)
    cam = ops.hd2d_camera_of(scene)
    assert (cam["view"], cam["pitch"], cam["height"]) == (pytest.approx(15.0), 45.0, 1.2)
    raw = scene["settings"]["hd2d"]["camera"]
    assert raw["distance"] == pytest.approx(15 / 2 / math.tan(math.radians(6)), abs=1e-3)  # the view at its lens
    assert raw["follow"] == "player" and raw["bounds"] == [0.0, 0.0, 1280.0, 960.0]
    scene = ops.set_hd2d_camera(scene, bounded=False)
    assert "bounds" not in scene["settings"]["hd2d"]["camera"]
    scene = ops.set_hd2d_camera(scene, bounded=True)  # back: the room's ground
    assert scene["settings"]["hd2d"]["camera"]["bounds"] == [0.0, 0.0, 1280.0, 960.0]
    for preset, values in ops.CAMERA_PRESETS.items():
        cam = ops.hd2d_camera_of(ops.set_hd2d_camera(scene, preset=preset))
        assert cam["view"] == pytest.approx(values["view"]) and cam["pitch"] == values["pitch"], preset
    for bad, reason in (({"pitch": 95}, "pitch"), ({"view": 1}, "view must be 2 to 200"), ({"ortho": "yes"}, "true or false"),
                        ({"preset": "drone"}, "preset must be")):
        with pytest.raises(ops.OpError, match=reason):
            ops.set_hd2d_camera(scene, **bad)


def test_the_sun_is_set_by_where_it_is_in_the_sky() -> None:
    scene = _room()
    sun = ops.hd2d_sun_of(scene)  # Mesh's default: high in the south-west
    assert (sun["azimuth"], sun["elevation"], sun["color"], sun["ambient"], sun["sky"]) == (
        pytest.approx(219.3, abs=0.1), pytest.approx(44.6, abs=0.1), "#fff0d8", 0.45, "#76a0d6")
    scene = ops.set_hd2d_sun(scene, azimuth=90, elevation=30, color="#ffcc88", intensity=0.8, ambient=0.3, sky="#204060")
    raw = scene["settings"]["hd2d"]
    assert raw["sun"]["direction"] == pytest.approx([math.cos(math.radians(30)), 0.0, 0.5], abs=1e-4)  # from the east
    assert (raw["sun"]["color"], raw["sun"]["intensity"], raw["ambient"], raw["sky"]) == ("#ffcc88", 0.8, 0.3, "#204060")
    sun = ops.hd2d_sun_of(scene)
    assert (sun["azimuth"], sun["elevation"]) == (pytest.approx(90.0), pytest.approx(30.0))
    parsed = parse_hd2d(raw)
    assert parsed.sun_intensity == 0.8 and parsed.ambient == 0.3
    for preset in ops.SUN_PRESETS:
        parse_hd2d(ops.set_hd2d_sun(scene, preset=preset)["settings"]["hd2d"])
    for bad, reason in (({"elevation": 2}, "elevation"), ({"intensity": 20}, "intensity"), ({"color": "warm"}, "colour"),
                        ({"sky": 3}, "sky must be"), ({"preset": "dusk"}, "preset must be")):
        with pytest.raises(ops.OpError, match=reason):
            ops.set_hd2d_sun(scene, **bad)


def test_a_2d_room_has_no_camera_or_sun_to_set() -> None:
    for op in (ops.set_hd2d_camera, ops.set_hd2d_sun):
        with pytest.raises(ops.OpError, match="isn't an HD-2D room"):
            op({"name": "R", "entities": [], "settings": {}}, preset="noon" if op is ops.set_hd2d_sun else "outdoor")


@pytest.fixture(scope="module")
def starter(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("m22a")
    made = subprocess.run([sys.executable, "-m", "mesh_cli", "new", "game", "--dest", str(out), "--template", "starter"],
                          cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=600)
    assert made.returncode == 0, made.stdout + made.stderr
    return out / "game"


def test_a_2d_projects_first_hd2d_room_brings_the_starter_kit_and_undoes(starter: Path, tmp_path: Path) -> None:
    from engine.studio_project import Project

    root = tmp_path / "game"
    shutil.copytree(starter, root)
    assert not (root / "assets/hd2d_starter/textures/grass.png").exists()
    project = Project.open(root, "packs/core_regions/worlds/main.json")
    key, installed = project.add_hd2d_room("Meadow", 40, 30)
    assert installed and (root / "assets/hd2d_starter/textures/grass.png").is_file()
    models = json.loads((root / "assets/models/catalog.json").read_text(encoding="utf-8"))["models"]
    assert {"cottage", "bridge_6m"} <= {m["id"] for m in models}
    hd2d = project.scene(key)["settings"]["hd2d"]
    assert hd2d["ground"]["to"] == [1280.0, 960.0]
    assert any(e.get("tag") == "player" for e in project.scene(key)["entities"])  # the shared player, filled in
    key2, again = project.add_hd2d_room("Cave", 16, 12, outdoor=False)
    assert not again  # the kit is there now: nothing copied twice
    project.undo()
    project.undo()
    assert key not in project.world["scenes"] and key2 not in project.world["scenes"]


def test_a_new_hd2d_rooms_player_starts_in_its_middle() -> None:
    """A 2D room's player starts near its corner; in an HD-2D room the camera keeps inside the room, so a corner start
    squeezed the player into the picture's edge."""
    scene = {"name": "R", "entities": [{"id": "r_player", "prefab_id": "player", "x": 128.0, "y": 128.0}]}
    scene, _path, _skeleton = ops.make_hd2d_room(scene, PATH, 40, 30)
    assert (scene["entities"][0]["x"], scene["entities"][0]["y"]) == (640.0, 480.0)
