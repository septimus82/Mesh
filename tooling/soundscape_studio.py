"""Milestone 21B: a soundscape authored in Mesh Studio and heard in the game, checked in hidden windows.

    py -3.13 tooling/soundscape_studio.py setup2d OUT        a fresh 2D starter project in OUT/2d (silent: master 0)
    py -3.13 tooling/soundscape_studio.py studio2d OUT       Studio's controls: Sound panel, + Add sound, choose its sound,
                                                             set it, drag it, undo/redo, rain and wind, save, reopen,
                                                             Play: walk to it and away; Play/Stop five times
    py -3.13 tooling/soundscape_studio.py setuplake OUT LAKE  a copy of the Lakeside Village project (LAKE: never written)
    py -3.13 tooling/soundscape_studio.py studiolake OUT     the village's soundscape, authored in its 3D view
    py -3.13 tooling/soundscape_studio.py walklake OUT       walking it: entrance, crossroads, pond, away, birds, weather,
                                                             rooms and back; the levels heard, and a software mix of them
    py -3.13 tooling/soundscape_studio.py exportlake OUT     ``mesh export build`` and the bundle's own engine
    py -3.13 tooling/soundscape_studio.py mix OUT            a stereo WAV of the walk, mixed in software from its log
    py -3.13 tooling/soundscape_studio.py perf OUT           frame cost with dozens of emitters in the village

Everything happens through Mesh Studio's own input events (clicks, drags, typing) and the game's (arrow keys), never
by writing room files. Silent: each project's master volume is 0, so the real audio backend decodes and plays every
loop (its players run and loop) but nothing reaches the speakers; levels are read before the master volume."""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(1, str(REPO / "tooling"))
SCENES = "packs/core_regions/scenes"
PX = 32.0


def _write(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=1, default=str) + "\n", encoding="utf-8")


def _silent(project: Path) -> None:
    config = json.loads((project / "config.json").read_text(encoding="utf-8"))
    config["master_volume"] = 0.0  # the backend plays; nothing reaches the speakers
    _write(project / "config.json", config)


_BASE = [0]  # players other code in this process already had registered when a phase began (a test run)


def _registered() -> int:
    """Players registered with Arcade since the phase began (the count is process-wide)."""
    from pyglet import media

    return len(media.Source._players) - _BASE[0]


def _begin() -> None:
    from pyglet import media

    _BASE[0] = len(media.Source._players)


# ---------------------------------------------------------------- driving Studio
def _widget(d: Any, text: str, where: Callable[[Any], bool] = lambda w: True) -> Any:
    for widget in d.studio.ui.walk_widgets():
        if getattr(widget, "text", None) == text and where(widget):
            return widget
    return None


def _press(d: Any, text: str, where: Callable[[Any], bool] = lambda w: True) -> None:
    """Click the button ``text`` (the one ``where`` picks, if several have it), scrolling the right panel to it."""
    for _ in range(30):
        widget = _widget(d, text, where)
        if widget is not None and getattr(widget, "rect", None) is not None and widget.rect.bottom > 30:
            r = widget.rect
            d.click(r.left + r.width / 2, r.bottom + r.height / 2)
            return
        d.window.dispatch_event("on_mouse_scroll", d.window.width - 100, d.window.height / 2, 0, -1)
        d.frame()
    raise AssertionError(f"no button {text!r}")


def _top(widget: Any) -> bool:
    return bool(widget.rect.bottom > widget.ui_manager.window.height - 60) if hasattr(widget, "ui_manager") else \
        widget.rect.bottom > 650


def _right(widget: Any) -> bool:
    return bool(widget.rect.left > 900)


def _map_point(d: Any, wx: float, wy: float) -> tuple[float, float]:
    sx, sy = d.window.camera.project((wx, wy))[:2]
    return float(sx), float(sy)


def _scene(d: Any) -> dict[str, Any]:
    scene: dict[str, Any] = d.studio.project.scene()
    return scene


def _emitters(scene: dict[str, Any]) -> list[dict[str, Any]]:
    from engine import project_ops as ops

    return [e for e in ops.entities(scene) if ops.sound_emitter_of(e) is not None]


def _loops(audio: Any) -> dict[str, float]:
    """The ambience loops playing and their levels before the master volume (volume x fade x ambience bus)."""
    return {key: round(t.volume * t.scale * audio.ambience_volume, 3) for key, t in audio._loops.items()}


def setup2d(out: Path) -> dict[str, Any]:
    project = out / "2d"
    if project.exists():
        shutil.rmtree(project)
    made = subprocess.run([sys.executable, "-m", "mesh_cli", "new", "2d", "--dest", str(out), "--template", "starter"],
                          cwd=REPO, capture_output=True, text=True, timeout=600)
    assert made.returncode == 0, made.stdout + made.stderr
    _silent(project)
    return {"project": str(project)}


def studio2d(out: Path) -> dict[str, Any]:
    """The 2D workflow, as a creator would: every step a click, a drag or typing in Mesh Studio."""
    _begin()
    from hd2d_studio_demo import StudioDriver

    project = out / "2d"
    pics = out / "pictures"
    pics.mkdir(exist_ok=True)
    d = StudioDriver(project)
    k = d.arcade.key
    report: dict[str, Any] = {"editing_registered_players": _registered()}
    try:
        _press(d, "Sound", _top)  # the top bar's Sound panel
        report["panel"] = d.studio.panel
        _press(d, "+ Add sound")
        d.click(*_map_point(d, 608, 128))  # where it is heard from
        emitter = _emitters(_scene(d))
        report["placed"] = [(e["name"], e["x"], e["y"], (e.get("behaviour_config") or {}).get("SoundEmitter")) for e in emitter]
        eid = emitter[0]["id"]
        report["selected_after_placing"] = d.studio.selected == eid
        _press(d, "Undo")  # creation undone and redone
        undone_count = len(_emitters(_scene(d)))
        _press(d, "Redo")
        report["create_undo_redo"] = [1, undone_count, len(_emitters(_scene(d)))]
        d.click(*_map_point(d, 608, 128))  # selected again with a click on its marker
        report["picked_by_clicking_its_marker"] = d.studio.selected == eid
        _press(d, "Choose sound...")
        report["picker"] = d.studio.panel
        d.picture(pics / "2d_01_sound_picker.png")
        _press(d, "Flowing water  (stream_loop.wav)")
        d.type_into("sound_volume", "70")
        d.type_into("sound_radius", "2")
        d.type_into("sound_distance", "12")
        before = dict((_emitters(_scene(d))[0].get("behaviour_config") or {}).get("SoundEmitter") or {})
        _press(d, "Undo")  # a property edit undone and redone
        undone = dict((_emitters(_scene(d))[0].get("behaviour_config") or {}).get("SoundEmitter") or {})
        _press(d, "Redo")
        report["property_undo_redo"] = [before.get("distance"), undone.get("distance"),
                                        ((_emitters(_scene(d))[0].get("behaviour_config") or {}).get("SoundEmitter") or {}).get("distance")]
        d.type_into("sound_distance", "8")
        report["set"] = (_emitters(_scene(d))[0].get("behaviour_config") or {}).get("SoundEmitter")
        report["copied_into_project"] = (project / "assets/ambience/stream_loop.wav").is_file()
        d.picture(pics / "2d_02_emitter_selected.png")
        d.drag(_map_point(d, 608, 128), _map_point(d, 640, 192))  # moved
        moved = _emitters(_scene(d))[0]
        _press(d, "Undo")
        undone = _emitters(_scene(d))[0]
        _press(d, "Redo")
        redone = _emitters(_scene(d))[0]
        report["move_undo_redo"] = [(moved["x"], moved["y"]), (undone["x"], undone["y"]), (redone["x"], redone["y"])]
        _press(d, "Sound", _top)
        _press(d, "Steady", _right)
        _press(d, "Breeze", _right)
        from engine import project_ops as ops

        report["weather"] = {"rain": ops.rain_strength(_scene(d)), "sounds": ops.weather_sounds_of(_scene(d)),
                             "wind": _scene(d).get("settings", {}).get("wind")}
        d.picture(pics / "2d_03_sound_panel.png")
        report["editing_after_authoring"] = {"registered_players": _registered(), "loops": d.window.audio.loops()}
        _press(d, "Save")
        report["saved_message"] = d.studio.message
    finally:
        d.close()

    room = json.loads((project / SCENES / "start.json").read_text(encoding="utf-8"))
    report["in_the_saved_file"] = {"emitters": [(e["x"], e["y"], e["behaviour_config"]["SoundEmitter"]) for e in _emitters(room)],
                                   "weather_sounds": room["settings"].get("weather_sounds"),
                                   "particles": room["settings"].get("particles")}
    d = StudioDriver(project)  # closed and reopened
    try:
        report["reopened"] = {"same_emitters": [(e["x"], e["y"], (e.get("behaviour_config") or {}).get("SoundEmitter"))
                                                for e in _emitters(_scene(d))] == report["in_the_saved_file"]["emitters"],
                              "unsaved": sorted(d.studio.project.dirty), "registered_players": _registered()}
        cycles = []
        for i in range(5):
            d.key(k.F4)
            for _ in range(20):
                d.frame()
                time.sleep(1 / 60)
            audio = d.window.audio
            row: dict[str, Any] = {"mode": d.studio.mode, "loops": _loops(audio), "registered": _registered()}
            if i == 0:  # the first play-test: walk east to the stream and back
                walk = []
                player = d.window.scene_controller._find_player_sprite()
                for direction, frames in ((k.RIGHT, 150), (k.LEFT, 150)):
                    d.window.dispatch_event("on_key_press", direction, 0)
                    for f in range(frames):
                        d.window.dispatch_event("on_update", 1 / 60)
                        if f % 15 == 0:
                            walk.append({"x": round(player.center_x), "loops": _loops(audio)})
                    d.window.dispatch_event("on_key_release", direction, 0)
                row["walk"] = walk
                d.picture(pics / "2d_04_play.png")
            d.key(k.F4)
            d.frame(5)
            row["after_stop"] = {"mode": d.studio.mode, "loops": d.window.audio.loops(), "registered": _registered()}
            cycles.append(row)
        report["play_stop"] = cycles
        d.picture(pics / "2d_05_back_to_editing.png")
    finally:
        d.close()
    report["after_close_registered"] = _registered()
    return report


LAKE_ROOM = "packs/core_regions/scenes/lakeside.json"
WATER_AT, BIRDS_AT, MEADOW_AT = (40.5, 29.0), (8.5, 33.5), (49.0, 19.0)  # m: by the inlet, in the north-west trees, east meadow
PLAYER_START = (29.5, 4.0)


def setuplake(out: Path, original: str) -> dict[str, Any]:
    """A copy of the owner's Lakeside Village project to work on (the original is only read)."""
    source, project = Path(original), out / "lake"
    if project.exists():
        shutil.rmtree(project)
    shutil.copytree(source, project, ignore=shutil.ignore_patterns("saves", "artifacts", ".mesh"))
    _silent(project)
    return {"copied_from": str(source), "project": str(project),
            "original_untouched": True}


def _ground(d_or_game: Any, x: float, y: float) -> float:
    """The ground's height (m) at (x, y) m."""
    renderer = getattr(getattr(d_or_game, "window", None), "hd2d_renderer", None)
    terrain = getattr(renderer, "terrain", None)
    return float(terrain.height(x * PX, y * PX)) / PX if terrain is not None else 0.0


def studiolake(out: Path) -> dict[str, Any]:
    """The village's soundscape, authored in Mesh Studio's 3D view with its own controls."""
    _begin()
    import m20c_material_study as m20c
    from hd2d_studio_demo import StudioDriver

    from engine import project_ops as ops

    project, pics = out / "lake", out / "pictures"
    pics.mkdir(exist_ok=True)
    d = StudioDriver(project)
    report: dict[str, Any] = {}
    try:
        _press(d, "Lakeside", lambda w: w.rect.left < 230)  # the room, from the Rooms list
        report["room"] = d.studio.project.current
        report["editing_registered_players"] = _registered()
        _press(d, "Sound", _top)
        placed = []
        for title, (x, y), sound, values in (
                ("Pond water", WATER_AT, "Flowing water  (stream_loop.wav)", {"sound_volume": "80", "sound_radius": "2.5",
                                                                             "sound_distance": "11"}),
                ("Birds", BIRDS_AT, "Birdsong  (birds_loop.wav)", {"sound_volume": "70", "sound_radius": "3",
                                                                   "sound_distance": "14"}),
                ("Meadow", MEADOW_AT, "Forest or meadow  (forest_loop.wav)", {"sound_volume": "45", "sound_radius": "6",
                                                                              "sound_distance": "16"})):
            _press(d, "+ Add sound")
            m20c._look_at(d, x, y, 22.0)
            d.click(*d.screen((x, y, _ground(d, x, y))))
            eid = d.studio.selected
            assert eid and ops.sound_emitter_of(d.studio._entity(eid) or {}) is not None, f"{title}: not placed"
            d.type_into("name", title)
            _press(d, "Choose sound...")
            _press(d, sound)
            for key, text in values.items():
                d.type_into(key, text)
            if title == "Birds":  # up in the trees: 4 m above the ground there
                d.type_into("sound_height", f"{_ground(d, x, y) + 4.0:.1f}")
            entity = d.studio._entity(eid) or {}
            placed.append({"name": entity.get("name"), "at_m": [round(float(entity["x"]) / PX, 2), round(float(entity["y"]) / PX, 2),
                                                                 round(float(entity.get("elevation", 0) or 0) / PX, 2)],
                           "sound": ops.sound_emitter_of(entity)})
            d.picture(pics / f"lake_01_{title.lower().replace(' ', '_')}.png")
            _press(d, "Sound", _top)  # back to the Sound panel for the next
            if d.studio.panel != "sound":
                _press(d, "Sound", _top)
        report["placed"] = placed
        _press(d, "Steady", _right)
        _press(d, "Gusty", _right)
        report["weather"] = {"rain": ops.rain_strength(_scene(d)), "sounds": ops.weather_sounds_of(_scene(d)),
                             "wind": _scene(d).get("settings", {}).get("wind")}
        m20c._look_at(d, 30.0, 26.0, 60.0)
        d.picture(pics / "lake_02_sound_panel_overview.png")
        report["editing_after_authoring"] = {"registered_players": _registered(), "loops": d.window.audio.loops()}
        _press(d, "Save")
        report["saved_message"] = d.studio.message
    finally:
        d.close()
    room = json.loads((project / LAKE_ROOM).read_text(encoding="utf-8"))
    saved = [(e["name"], e["x"], e["y"], e.get("elevation"), e["behaviour_config"]["SoundEmitter"]) for e in _emitters(room)]
    report["in_the_saved_file"] = {"emitters": saved, "weather_sounds": room["settings"].get("weather_sounds"),
                                   "particles": room["settings"].get("particles"), "wind": room["settings"].get("wind")}
    d = StudioDriver(project)
    try:
        _press(d, "Lakeside", lambda w: w.rect.left < 230)
        again = [(e["name"], e["x"], e["y"], e.get("elevation"), (e.get("behaviour_config") or {}).get("SoundEmitter"))
                 for e in _emitters(_scene(d))]
        report["reopened"] = {"same_emitters": again == saved, "unsaved": sorted(d.studio.project.dirty)}
        m20c._look_at(d, 40.0, 29.0, 26.0)
        d.studio.select(next(e["id"] for e in _emitters(_scene(d)) if e["name"] == "Pond water"))
        d.frame(3)
        d.picture(pics / "lake_03_reopened_pond_selected.png")
        k = d.arcade.key
        cycles = []
        for _ in range(5):
            d.key(k.F4)
            for _f in range(20):
                d.frame()
            cycles.append({"play": {"mode": d.studio.mode, "loops": d.window.audio.loops(), "registered": _registered()}})
            d.key(k.F4)
            d.frame(5)
            cycles[-1]["stop"] = {"mode": d.studio.mode, "loops": d.window.audio.loops(), "registered": _registered()}
        report["play_stop"] = cycles
    finally:
        d.close()
    report["after_close_registered"] = _registered()
    return report


def walklake(out: Path) -> dict[str, Any]:
    """The player walking the village (arrow keys; the game's own movement), every frame's soundscape logged."""
    from hd2d_demo import HiddenGame
    from hd2d_floors_demo import _feet, hold_key

    project = out / "lake"
    game = HiddenGame(project, size=(1280, 720))
    keys = game.arcade.key
    log: list[dict[str, Any]] = []
    frame = [0]

    def sample() -> None:
        frame[0] += 1
        audio, player = game.window.audio, game.window.scene_controller._find_player_sprite()
        fx, fy = _feet(player) if player is not None else (0.0, 0.0)
        log.append({"f": frame[0], "room": game.window.scene_controller.current_scene_path.rsplit("/", 1)[-1],
                    "at": [round(fx, 2), round(fy, 2)],
                    "loops": {key: [round(t.volume * t.scale * audio.ambience_volume, 4), round(t.pan or 0.0, 3), t.path]
                              for key, t in audio._loops.items()}})

    def walk(legs: list[tuple[int, int, float]]) -> None:
        for key, axis, target in legs:
            hold_key(game, game.player(), key, axis, target, 1500, each_frame=sample)

    def follow(goal: tuple[float, float]) -> bool:
        """Walk to ``goal`` (m) with the arrow keys, steering along the engine's own route (its navigation grid)."""
        world, player = game.window.hd2d_world, game.player()
        fx, fy = _feet(player)
        z = float(player.mesh_entity_data.get("elevation", 0.0)) / PX
        gz = _ground(game, *goal)
        route = world.path((fx, fy, z), (goal[0], goal[1], gz))
        held: set[int] = set()
        for wx, wy, _wz in route[::2] + [route[-1]] if route else []:
            for _ in range(240):
                fx, fy = _feet(player)
                if math.hypot(wx - fx, wy - fy) < 0.35:
                    break
                want = {k for k, on in ((keys.RIGHT, wx - fx > 0.15), (keys.LEFT, wx - fx < -0.15),
                                        (keys.UP, wy - fy > 0.15), (keys.DOWN, wy - fy < -0.15)) if on}
                for k in held - want:
                    game.window.dispatch_event("on_key_release", k, 0)
                for k in want - held:
                    game.window.dispatch_event("on_key_press", k, 0)
                held = want
                game.step(1)
                sample()
        for k in held:
            game.window.dispatch_event("on_key_release", k, 0)
        game.step(2)
        fx, fy = _feet(player)
        return math.hypot(goal[0] - fx, goal[1] - fy) < 1.0

    def stand(seconds: float) -> None:
        for _ in range(round(seconds * 60)):
            game.step(1)
            sample()

    def rain(on: bool) -> None:  # the weather's own switch (as Studio's weather preview uses): rain stops or starts
        layer = game.window.hd2d_renderer.particles
        for i, effect in enumerate(layer.effects):
            if effect.preset == "rain":
                layer.set_enabled(i, on)

    marks: dict[str, int] = {}
    try:
        game.load(LAKE_ROOM)
        game.step(5)
        from m20a_terrain_study import _put

        _put(game, 30.0, 2.0)
        rain(False)  # calm to start with
        stand(2.0)
        marks["1 entrance (calm)"] = len(log)
        walk([(keys.UP, 1, 11.5)])  # 1: from the entrance toward the crossroads
        marks["2 crossroads"] = len(log)
        walk([(keys.UP, 1, 22.0), (keys.RIGHT, 0, 33.9), (keys.UP, 1, 25.0), (keys.RIGHT, 0, 34.4),
              (keys.UP, 1, 27.0), (keys.RIGHT, 0, 34.95), (keys.UP, 1, 29.6)])  # 2: to the pond, over the inlet's bridge
        marks["3 at the pond (bridge's north end)"] = len(log)
        stand(1.0)
        reached = {"away": follow((22.0, 31.0))}  # 3: away from the pond, west along its north side
        marks["4 away from the pond"] = len(log)
        reached["birds"] = follow((10.5, 32.0))  # 4: up the hill, under the birds in the north-west trees
        marks["5 by the birds"] = len(log)
        stand(1.0)
        rain(True)  # 5: calm to rain
        stand(8.0)
        marks["6 raining"] = len(log)
        rain(False)  # 6: back to calm
        stand(10.0)
        marks["7 calm again"] = len(log)
        _put(game, 30.0, 3.0)  # 7: to the room's south door and through it, to the Village, and back
        stand(0.5)
        walk([(keys.DOWN, 1, 0.2)])
        stand(2.0)
        marks["8 in the Village"] = len(log)
        village = {"room": game.window.scene_controller.current_scene_path, "loops": dict(game.window.audio.loops())}
        walk([(keys.UP, 1, 7.0), (keys.RIGHT, 0, 38.5)])  # back: east along the Village's road, through its passage
        stand(1.0)
        walked_back = game.window.scene_controller.current_scene_path.endswith("lakeside.json")
        if not walked_back:  # (said in the report; the same room-loading path either way)
            game.load(LAKE_ROOM)
            game.step(2)
        rain(False)
        stand(2.0)
        marks["9 back in Lakeside"] = len(log)
        _put(game, 39.0, 28.0)
        stand(3.0)
        marks["10 back at the pond"] = len(log)
        back = {"walked_back_through_the_passage": walked_back, "loops": dict(game.window.audio.loops())}
    finally:
        game.window.close()
        closed = _registered()
        os.chdir(game._cwd)
    _write(out / "walk_log.json", log)

    def at(index: int) -> dict[str, Any]:
        row = log[max(0, index - 1)]
        return {"at": row["at"], "room": row["room"], "loops": {k.rsplit(":", 1)[-1]: v[0] for k, v in row["loops"].items()}}

    return {"frames": len(log), "marks": {name: at(i) for name, i in marks.items()}, "reached": reached,
            "village": village, "back": back,
            "registered_after_close": closed, "log": str(out / "walk_log.json")}


def mix(out: Path) -> dict[str, Any]:
    """A stereo WAV of the walk: each loop the engine played, decoded and looped, at the level and pan the engine gave
    it frame by frame (equal-power pan), summed. A controlled software mix of the engine's own commands, not a capture
    of the sound card (nothing was played aloud)."""
    import wave

    import numpy as np

    log = json.loads((out / "walk_log.json").read_text(encoding="utf-8"))
    rate, per_frame = 22050, 22050 // 60
    total = len(log) * per_frame
    left, right = np.zeros(total, np.float64), np.zeros(total, np.float64)
    sources: dict[str, np.ndarray] = {}
    starts: dict[str, int] = {}
    project = out / "lake"
    for i, row in enumerate(log):
        for key, (level, pan, path) in row["loops"].items():
            if path not in sources:
                with wave.open(str(project / path)) as w:
                    assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (rate, 1, 2), path
                    sources[path] = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float64) / 32768
            src = sources[path]
            start = starts.setdefault(key, i * per_frame)
            idx = (np.arange(i * per_frame, (i + 1) * per_frame) - start) % len(src)
            a = (pan + 1.0) * math.pi / 4
            chunk = src[idx] * level
            left[i * per_frame:(i + 1) * per_frame] += chunk * math.cos(a)
            right[i * per_frame:(i + 1) * per_frame] += chunk * math.sin(a)
    peak = float(max(np.max(np.abs(left)), np.max(np.abs(right)), 1e-9))
    stereo = np.empty(total * 2, np.float64)
    stereo[0::2], stereo[1::2] = left, right
    path = out / "lakeside_soundscape_mix.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(stereo, -1, 1) * 32767).astype("<i2").tobytes())
    return {"file": str(path), "seconds": round(total / rate, 1), "peak_dbfs": round(20 * math.log10(peak), 1),
            "clipped_samples": int(np.sum(np.abs(stereo) >= 1.0)), "loops_mixed": sorted({k for r in log for k in r["loops"]})}


def exportlake(out: Path) -> dict[str, Any]:
    project, bundle = out / "lake", out / "lake_export"
    if bundle.exists():
        shutil.rmtree(bundle)
    built = subprocess.run([sys.executable, "-m", "mesh_cli", "export", "build", "--out", str(bundle)], cwd=project,
                           capture_output=True, text=True, timeout=900, env={**os.environ, "PYTHONPATH": str(REPO)})
    room = json.loads((project / LAKE_ROOM).read_text(encoding="utf-8"))
    wanted = sorted({e["behaviour_config"]["SoundEmitter"]["sound"] for e in _emitters(room)}
                    | {v for k, v in (room["settings"].get("weather_sounds") or {}).items() if k in ("rain", "wind")})
    report: dict[str, Any] = {"export_code": built.returncode, "export_tail": (built.stdout + built.stderr)[-300:],
                              "sounds_in_bundle": {w: (bundle / w).is_file() for w in wanted}}
    code = f"""
import json, sys
sys.path.insert(0, {str(bundle)!r})
import engine
sys.path.insert(1, {str(REPO / "tooling")!r})
from hd2d_demo import HiddenGame
from m20a_terrain_study import _put
from pathlib import Path
from pyglet import media
game = HiddenGame(Path({str(bundle)!r}))
row = {{"engine_from": engine.__file__, "master_volume": game.window.audio.master_volume}}
try:
    game.load({LAKE_ROOM!r})
    game.step(5)
    _put(game, {WATER_AT[0] - 1.5}, {WATER_AT[1] - 1.0})
    game.step(240)
    scape = game.window.soundscape
    row.update(emitters=len(scape.emitters), loops={{k: round(t.volume * t.scale, 3) for k, t in game.window.audio._loops.items()}},
               registered=len(media.Source._players), unplayable=game.window.audio.diagnostics()["unplayable"])
finally:
    game.window.close()
    row["registered_after_close"] = len(media.Source._players)
print(json.dumps(row))
"""
    ran = subprocess.run([sys.executable, "-c", code], cwd=bundle, capture_output=True, text=True, timeout=900,
                         env={k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "MESH_REPO_ROOT")})
    try:
        report["bundle_run"] = json.loads(ran.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        report["bundle_run"] = {"failed": ran.stdout[-600:] + ran.stderr[-1500:]}
    return report


def perf(out: Path) -> dict[str, Any]:
    """Frame cost with dozens of emitters: the village (a scratch copy of the authored copy) with 48 more sound
    emitters scattered over it, the player walking; the soundscape's own time per frame and the players held."""
    from hd2d_demo import HiddenGame
    from hd2d_floors_demo import hold_key

    from engine import project_ops as ops
    from engine import sound_emitters

    base, project = out / "lake", out / "lake_perf"
    if project.exists():
        shutil.rmtree(project)
    shutil.copytree(base, project)
    room_path = project / LAKE_ROOM
    scene = json.loads(room_path.read_text(encoding="utf-8"))
    sounds = ["assets/ambience/stream_loop.wav", "assets/ambience/birds_loop.wav", "assets/ambience/forest_loop.wav"]
    for i in range(48):  # a perf scene (not an authoring demo): placed by the same operations Studio uses
        x, y = 4.0 + (i % 8) * 8.0, 4.0 + (i // 8) * 7.5
        scene, eid = ops.place_blank(scene, "lakeside", f"Perf {i}", x * PX, y * PX)
        scene = ops.set_sound_emitter(scene, eid, sound=sounds[i % 3], radius=64, distance=384, volume=0.6)
    room_path.write_text(json.dumps(scene), encoding="utf-8")
    game = HiddenGame(project, size=(1280, 720))
    keys = game.arcade.key
    timings: list[float] = []
    frames: list[float] = []
    real_update = sound_emitters.update

    def timed(window: Any, dt: float) -> None:
        t = time.perf_counter()
        real_update(window, dt)
        timings.append(time.perf_counter() - t)

    sound_emitters.update = timed
    peak = 0
    try:
        game.load(LAKE_ROOM)
        game.step(10)
        from m20a_terrain_study import _put

        _put(game, 8.0, 6.0)

        def each() -> None:
            nonlocal peak
            peak = max(peak, _registered())

        t0 = time.perf_counter()
        for key, axis, target in ((keys.UP, 1, 40.0), (keys.RIGHT, 0, 56.0), (keys.DOWN, 1, 8.0)):
            start = time.perf_counter()
            n = len(timings)
            hold_key(game, game.player(), key, axis, target, 1500, each_frame=each)
            frames.append((time.perf_counter() - start) / max(1, len(timings) - n))
        walked = time.perf_counter() - t0
        scape = game.window.soundscape
        report = {"emitters_in_room": len(scape.emitters), "frames": len(timings),
                  "soundscape_ms_per_frame": {"mean": round(1000 * sum(timings) / len(timings), 3),
                                              "p95": round(1000 * sorted(timings)[int(len(timings) * 0.95)], 3),
                                              "max": round(1000 * max(timings), 3)},
                  "whole_frame_ms_mean": round(1000 * walked / max(1, len(timings)), 2),
                  "slowest_frames_ms": sorted(((round(1000 * t, 2), i) for i, t in enumerate(timings)), reverse=True)[:6],
                  "peak_registered_players": peak, "max_active": sound_emitters.MAX_ACTIVE,
                  "loop_calls_per_frame": round(scape.loop_calls / max(1, scape.updates), 2)}
    finally:
        sound_emitters.update = real_update
        game.window.close()
        os.chdir(game._cwd)
    report["registered_after_close"] = _registered()
    return report


def menu(out: Path) -> dict[str, Any]:
    """The game's pause menu: its Settings page has the Ambience slider beside Music and SFX; moving it (arrow keys)
    turns the ambience playing down without restarting it, and the setting is kept for the next game."""
    from hd2d_demo import HiddenGame

    from engine.runtime_settings_storage import load_runtime_settings

    project = out / "lake"
    game = HiddenGame(project, size=(1280, 720))
    keys = game.arcade.key
    report: dict[str, Any] = {}
    try:
        game.load(LAKE_ROOM)
        game.step(120)
        audio, menu_ = game.window.audio, game.window.pause_menu
        before = {k: (t.player, round(t.volume * t.scale * audio.ambience_volume, 3)) for k, t in audio._loops.items()}
        menu_.toggle()
        menu_.state, menu_._settings_index = "settings", 0
        menu_._invalidate_layout()
        for key in (keys.DOWN, keys.DOWN):  # Music, SFX, then Ambience
            game.window.dispatch_event("on_key_press", key, 0)
            game.step(1)
        report["selected_row"] = menu_._SETTINGS_ROWS[menu_._settings_index][1]
        for _ in range(5):  # 5 % a press
            game.window.dispatch_event("on_key_press", keys.LEFT, 0)
            game.step(1)
        game.step(30)
        game.draw().convert("RGB").save(out / "pictures" / "menu_ambience_slider.png")
        after = {k: (t.player, round(t.volume * t.scale * audio.ambience_volume, 3)) for k, t in audio._loops.items()}
        report["ambience_volume"] = round(audio.ambience_volume, 3)
        report["music_and_sfx_unchanged"] = (audio.music_volume, audio.sfx_volume)
        report["loops_same_players"] = all(before[k][0] is after[k][0] for k in before if k in after)
        report["levels_before_after"] = {k.rsplit(":", 1)[-1]: (before[k][1], after[k][1]) for k in before if k in after}
        path = getattr(game.window, "runtime_settings_path", None)
        report["saved"] = round(load_runtime_settings(path).ambience_volume, 3) if path else None
    finally:
        game.window.close()
        os.chdir(game._cwd)
    return report


PHASES: dict[str, Callable[..., dict[str, Any]]] = {"setup2d": setup2d, "studio2d": studio2d, "setuplake": setuplake,
                                                   "studiolake": studiolake, "walklake": walklake, "mix": mix,
                                                   "exportlake": exportlake, "perf": perf, "menu": menu}


def main() -> None:
    phase, out = sys.argv[1], Path(sys.argv[2]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ["MESH_RUNTIME_SETTINGS_PATH"] = str(out / "user_settings.json")  # never a checkout's own file
    report = PHASES[phase](out, *sys.argv[3:])
    _write(out / f"{phase}.json", report)
    print(json.dumps(report, indent=1, default=str)[:6000])


if __name__ == "__main__":
    main()
