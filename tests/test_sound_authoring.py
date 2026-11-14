"""Milestone 21B: authoring sounds (what Mesh Studio and AI tools edit through): sound emitters, the room's rain and
weather sounds, sound files in a project, and the export finding them. Headless."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import engine.project_ops as ops
from engine.sound_emitters import library, sound_problem

pytestmark = pytest.mark.fast

STREAM = "assets/ambience/stream_loop.wav"


def _room() -> dict:
    return {"name": "Room", "settings": {}, "entities": []}


def _sound(scene: dict, **fields: object) -> tuple[dict, str]:
    scene, eid = ops.place_blank(scene, "room", "Sound", 320, 240)
    return ops.set_sound_emitter(scene, eid, **fields), eid


def test_a_sound_emitter_is_an_object_with_checked_settings() -> None:
    scene, eid = _sound(_room())
    entity = ops.find_entity(scene, eid)
    assert entity["behaviours"] == ["SoundEmitter"] and "sprite" not in entity
    assert ops.sound_emitter_of(entity)["sound"] == ""  # none chosen yet: the inspector asks for one
    scene = ops.set_sound_emitter(scene, eid, sound="assets\\ambience\\stream_loop.wav", volume=0.6, radius=96,
                                  distance=480, stereo=False)
    got = ops.sound_emitter_of(ops.find_entity(scene, eid))
    assert got == {"sound": STREAM, "volume": 0.6, "radius": 96.0, "distance": 480.0, "stereo": False, "loop": True,
                   "enabled": True, "fade_in": 1.0, "fade_out": 1.0}
    for bad, reason in (({"distance": 50}, "must be less than"), ({"volume": 3}, "from 0 to 1"),
                        ({"sound": "notes.txt"}, ".wav, .ogg or .mp3")):
        with pytest.raises(ops.OpError, match=reason):
            ops.set_sound_emitter(scene, eid, **bad)
    with pytest.raises(ops.OpError, match="from 0 to 1"):  # the generic behaviour-setting path is checked too
        ops.set_behaviour_param(scene, eid, "SoundEmitter", "volume", 5)


def test_a_hand_edited_emitter_the_game_cant_use_says_why() -> None:
    scene, eid = _sound(_room(), sound=STREAM)
    ops.find_entity(scene, eid)["behaviour_config"]["SoundEmitter"]["radius"] = -4
    got = ops.sound_emitter_of(ops.find_entity(scene, eid))
    assert "radius" in got["error"] and got["volume"] == 0.8


def test_rain_strengths_keep_the_rooms_other_weather() -> None:
    scene = ops.set_particles(_room(), [{"preset": "wind", "count": 200}])
    assert ops.rain_strength(scene) == "off"
    for strength, drops in (("light", 1200), ("steady", 3000), ("heavy", 6000)):
        scene = ops.set_rain(scene, strength)
        effects = scene["settings"]["particles"]
        assert ops.rain_strength(scene) == strength and effects[0] == {"preset": "rain", "count": drops}
        assert {"preset": "wind", "count": 200} in effects  # the leaves stay
    scene = ops.set_rain(scene, "off")
    assert scene["settings"]["particles"] == [{"preset": "wind", "count": 200}]
    with pytest.raises(ops.OpError, match="Rain must be"):
        ops.set_rain(scene, "drizzle")


def test_weather_sounds_are_set_and_removed() -> None:
    scene = ops.set_weather_sounds(_room(), rain="assets/ambience/rain_loop.wav", rain_volume=0.4)
    assert scene["settings"]["weather_sounds"] == {"rain": "assets/ambience/rain_loop.wav", "rain_volume": 0.4}
    assert ops.weather_sounds_of(scene)["wind_volume"] == 0.5
    scene = ops.set_weather_sounds(scene, rain="")
    assert "weather_sounds" not in scene["settings"]
    with pytest.raises(ops.OpError, match="from 0 to 1"):
        ops.set_weather_sounds(scene, rain="assets/ambience/rain_loop.wav", rain_volume=4)


def test_the_library_is_wav_loops_this_computer_can_play() -> None:
    names = [p.name for p in library()]
    assert names == ["birds_loop.wav", "forest_loop.wav", "rain_loop.wav", "stream_loop.wav", "wind_loop.wav"]
    assert all(sound_problem(p) is None for p in library())


def test_sound_files_are_checked_before_they_are_used(tmp_path: Path) -> None:
    (tmp_path / "empty.wav").write_bytes(b"")
    (tmp_path / "words.ogg").write_text("not a sound", encoding="utf-8")
    (tmp_path / "picture.png").write_bytes(b"\x89PNG")
    assert "no sound file" in sound_problem(tmp_path / "missing.wav")
    assert "isn't a sound file" in sound_problem(tmp_path / "picture.png")
    assert "can't play empty.wav" in sound_problem(tmp_path / "empty.wav")
    assert "can't play words.ogg" in sound_problem(tmp_path / "words.ogg")


def test_a_project_imports_a_sound_once_and_lists_its_sounds(tmp_path: Path) -> None:
    from engine.studio_project import Project

    project = Project.__new__(Project)  # (only its folder is needed here)
    project.root = tmp_path / "game"
    project.root.mkdir()
    stream = next(p for p in library() if p.name == "stream_loop.wav")
    assert project.import_sound(stream) == STREAM
    assert project.import_sound(stream) == STREAM  # the same file again: not copied twice
    other = tmp_path / "elsewhere" / "stream_loop.wav"
    other.parent.mkdir()
    shutil.copy(next(p for p in library() if p.name == "rain_loop.wav"), other)
    assert project.import_sound(other) == "assets/ambience/stream_loop_2.wav"  # same name, other sound: kept apart
    assert project.import_sound(project.root / STREAM) == STREAM  # already in the project: used where it is
    (project.root / "assets" / "sounds").mkdir()
    shutil.copy(stream, project.root / "assets" / "sounds" / "step.wav")
    assert project.sounds() == [STREAM, "assets/ambience/stream_loop_2.wav", "assets/sounds/step.wav"]
    (tmp_path / "bad.wav").write_bytes(b"")
    with pytest.raises(ops.OpError, match="can't play"):
        project.import_sound(tmp_path / "bad.wav")


def test_the_export_finds_a_rooms_sounds(tmp_path: Path) -> None:
    from engine.tooling.asset_manifest import _extract_refs_from_scene

    scene, _eid = _sound(_room(), sound=STREAM)
    scene = ops.set_weather_sounds(scene, rain="assets/ambience/rain_loop.wav", wind="assets/ambience/wind_loop.wav")
    refs = {r.asset_id: r.field_path for r in _extract_refs_from_scene(scene, "room.json")}
    assert refs[STREAM].endswith("behaviour_config.SoundEmitter.sound")
    assert refs["assets/ambience/rain_loop.wav"] == "settings.weather_sounds.rain"
    assert refs["assets/ambience/wind_loop.wav"] == "settings.weather_sounds.wind"


def test_the_scene_loader_accepts_a_sound_emitter(tmp_path: Path) -> None:
    from engine.scene_loader import SceneLoader

    scene, _eid = _sound(_room(), sound=STREAM, radius=64, distance=320)
    scene = ops.set_weather_sounds(scene, rain="assets/ambience/rain_loop.wav")
    path = tmp_path / "room.json"
    path.write_text(json.dumps(scene), encoding="utf-8")
    loaded = SceneLoader().load_scene(str(path))
    behaviours = loaded["entities"][0]["behaviours"]
    assert loaded["name"] == "Room" and [b["type"] if isinstance(b, dict) else b for b in behaviours] == ["SoundEmitter"]
