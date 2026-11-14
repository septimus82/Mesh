"""Post-M20 repository health checkpoint: the environmental settings' edges. AI and Studio edit the wind the same
way; a broken motion block can be repaired and doesn't block other edits; the validators (``mesh validate``, AI
validation) report what a room loading would set aside; a 2D room says when its wind is set aside."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine import project_ops as ops
from engine.scene_loader import SceneLoader, environment_problems

pytestmark = pytest.mark.fast


def _hd2d_room(**hd2d: object) -> dict:
    return {"name": "Room", "settings": {"world_width": 640, "world_height": 480,
                                         "hd2d": {"ground": {"texture": "assets/g.png", "from": [0, 0], "to": [640, 480]},
                                                  **hd2d}},
            "entities": []}


def test_set_wind_changes_only_what_is_given_as_studio_does() -> None:
    room = ops.set_wind(_hd2d_room(), speed=6, direction=45, gust=0.2)
    gusty = ops.set_wind(room, gust=0.9)
    assert gusty["settings"]["wind"] == {"speed": 6.0, "direction": 45.0, "gust": 0.9}
    turned = ops.set_wind(gusty, direction=90)
    assert turned["settings"]["wind"] == {"speed": 6.0, "direction": 90.0, "gust": 0.9}
    assert "wind" not in ops.set_wind(turned, speed=0)["settings"]
    broken = copy.deepcopy(room)
    broken["settings"]["wind"] = {"speed": 99}  # (hand-edited: a wind that can't be read counts as calm)
    assert ops.set_wind(broken, speed=3)["settings"]["wind"] == {"speed": 3.0, "direction": 0.0, "gust": 0.0}


def test_a_broken_motion_block_can_be_repaired_and_doesnt_block_other_edits() -> None:
    room = _hd2d_room(motion={"assets": {"nope": {}}})
    repaired = ops.set_motion(room, enabled=True)
    assert repaired["settings"]["hd2d"]["motion"] == {}
    placed, _sid = ops.place_structure(room, "assets/models/hut.glb", 100, 100)
    assert len(placed["settings"]["hd2d"]["structures"]) == 1
    assert placed["settings"]["hd2d"]["motion"] == {"assets": {"nope": {}}}  # (left as it was: not this edit's)


def test_ground_edits_read_only_the_ground() -> None:
    room = _hd2d_room(motion={"sway": 9}, scatter={"grass_tuft": [[10, 10, 0, 100]]})
    sculpted = ops.sculpt_terrain(room, "raise", 320, 240, 64, 16)  # (a broken motion block: not the ground's)
    assert sculpted["settings"]["hd2d"]["ground"].get("terrain")


def test_validators_report_what_a_load_would_set_aside(tmp_path: Path) -> None:
    bad = _hd2d_room(water_reflections="mirror")
    bad["settings"].update(wind={"speed": 99}, particles=[{"preset": "hail"}], weather_exposure="cave")
    bad["entities"] = [{"id": "p", "name": "Pond", "x": 64, "y": 64, "behaviours": ["WaterSurface"],
                        "behaviour_config": {"WaterSurface": {"preset": "lake"}}}]
    problems = environment_problems(bad)
    assert any("wind.speed" in p for p in problems) and any("hail" in p for p in problems)
    assert any("water_reflections" in p for p in problems) and any("lake" in p for p in problems)
    path = tmp_path / "room.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    report = SceneLoader().validate_scene_file(str(path))
    assert not report.ok and any("wind.speed" in e for e in report.errors)
    assert environment_problems(_hd2d_room()) == [] and environment_problems({"entities": []}) == []
    # (loading is not changed: the runtime's own check doesn't refuse the room for these)
    assert SceneLoader().validate_scene(SceneLoader().apply_scene_defaults(copy.deepcopy(bad))).ok


def test_committed_rooms_have_no_environment_problems() -> None:
    root = Path(__file__).resolve().parents[1]
    rooms = [p for p in root.glob("packs/**/scenes/**/*.json")]
    assert rooms
    for path in rooms:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            assert environment_problems(data) == [], path


def test_a_2d_room_says_when_its_wind_is_set_aside() -> None:
    from engine import scene_particles

    window = SimpleNamespace(ctx=None, hd2d_renderer=None)
    scene_particles.configure(window, {"particles": [{"preset": "rain"}], "wind": {"speed": 99}})
    assert window.scene_particles_error is None
    assert "wind is set aside" in (window.scene_particles_notice or "")
