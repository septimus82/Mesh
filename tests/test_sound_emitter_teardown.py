"""AS-3: deleting an entity that carries a SoundEmitter stops its sound at once (not at the next room change).

Real hidden GameWindow and scene controller (harness of tests/_b01_arena.py); only the audio backend is a counting
stand-in, so nothing is played aloud. "Playing" is read from the backend's live players and ``audio.loops()``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Iterator

import pytest

import engine.audio as audio_mod
from engine import optional_arcade
from engine import sound_emitters as se
from tests._b01_arena import PIC, Arena, close_window, make_window
from tests.test_audio_buses_and_scene_music import Backend
from tests.test_behaviour_teardown_on_delete_paths import IDS, PATHS

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]

HERO = {"id": "hero", "name": "Hero", "tag": "player", "x": 50, "y": 50, "sprite": PIC}
WATER = "assets/ambience/stream_loop.wav"
BIRDS = "assets/ambience/birds_loop.wav"


def _emitter(eid: str, sound: str) -> dict[str, Any]:
    return {"id": eid, "name": eid, "x": 80, "y": 50, "sprite": PIC, "layer": "entities",
            "behaviours": ["SoundEmitter"], "behaviour_config": {"SoundEmitter": {"sound": sound, "fade_in": 0.0}}}


@pytest.fixture()
def backend(monkeypatch: pytest.MonkeyPatch) -> Backend:
    fake = Backend()
    monkeypatch.setattr(audio_mod.optional_arcade.arcade, "Sound", fake.sound)
    monkeypatch.setattr(audio_mod.optional_arcade.arcade, "stop_sound", fake.stop)
    return fake


@pytest.fixture()
def arena(tmp_path: Path, backend: Backend) -> Iterator[Arena]:
    window = make_window()
    try:
        yield Arena(window, tmp_path)
    finally:
        close_window(window)


def _frames(arena: Arena, n: int = 5) -> None:
    for _ in range(n):
        arena.window.audio.update(1 / 60)
        se.update(arena.window, 1 / 60)


def _start(arena: Arena, backend: Backend) -> tuple[Any, Any]:
    arena.write_room(HERO, _emitter("water", WATER), _emitter("birds", BIRDS))
    arena.enter()
    _frames(arena)
    assert len(backend.playing("stream_loop.wav")) == 1 and len(backend.playing("birds_loop.wav")) == 1
    return arena.by_id("water"), arena.by_id("birds")


def test_kill_stops_its_sound_at_once_and_leaves_the_other_emitter(arena: Arena, backend: Backend) -> None:
    water, _birds = _start(arena, backend)
    water.kill()
    assert backend.playing("stream_loop.wav") == []  # before any frame or room change
    assert len(backend.playing("birds_loop.wav")) == 1
    _frames(arena)
    assert backend.playing("stream_loop.wav") == [] and len(backend.playing("birds_loop.wav")) == 1
    assert len(backend.live()) == 1  # nothing else left playing (the room's music is not an emitter)


@pytest.mark.parametrize("remove", PATHS, ids=IDS)
def test_every_delete_path_stops_its_sound(arena: Arena, backend: Backend, remove: Callable[[Arena, Any], None]) -> None:
    water, _birds = _start(arena, backend)
    remove(arena, water)
    assert backend.playing("stream_loop.wav") == []
    assert WATER not in arena.window.audio.loops().values()
    assert len(backend.playing("birds_loop.wav")) == 1


def test_a_second_teardown_is_safe(arena: Arena, backend: Backend) -> None:
    water, _birds = _start(arena, backend)
    behaviour = next(b for b in water.mesh_behaviours_runtime if type(b).__name__ == "SoundEmitter")
    water.kill()
    behaviour.on_destroy()  # (the backend asserts a player is never released twice)
    behaviour.on_destroy()
    assert len(backend.playing("birds_loop.wav")) == 1
