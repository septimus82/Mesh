"""Milestone 21C2: the weather outside heard from indoors, to hear and to measure. One throwaway two-room game.

    py -3.13 tooling/indoor_weather_demo.py setup OUT    OUT/game: the HD-2D starter village and its cottage's inside,
                                                         as the template makes them (silent: master volume 0)
    py -3.13 tooling/indoor_weather_demo.py studio OUT   Mesh Studio (hidden window), by its own controls: rain and wind
                                                         for the village; in the cottage, the Sound panel's "Hear
                                                         outside weather indoors" with nothing set (it says why nothing
                                                         is heard), then rain and wind set; undo, redo, save, reopen;
                                                         Play: in through the door and out; Play/Stop; the switch off
    py -3.13 tooling/indoor_weather_demo.py walk OUT     the game alone (hidden window): the same walk, every frame's
                                                         levels logged (OUT/walk_log.json); a save made indoors and
                                                         loaded; the cottage started in directly
    py -3.13 tooling/indoor_weather_demo.py export OUT   ``mesh export build``, and the bundle's own engine playing it
    py -3.13 tooling/indoor_weather_demo.py mix OUT      a stereo WAV of the walk, mixed in software from its log
    py -3.13 tooling/indoor_weather_demo.py perf OUT     the soundscape's cost per update outside and inside

    py -3.13 tooling/indoor_weather_demo.py listen OUT   FOR A PERSON LISTENING: makes OUT/listen (master volume 0.8)
                                                         and walks it through the speakers, each step captioned here
                                                         (under a minute). To walk it yourself afterwards:
                                                             cd OUT/listen  then  py -3.13 -m mesh_cli play
                                                         (arrow keys; the cottage is west of the start, its door on
                                                         its south side)

The rain and wind are Mesh's own ``assets/ambience/rain_loop.wav`` and ``wind_loop.wav`` (10 s mono loops: the rain cut
from a CC0 recording, the wind synthesised by Mesh; ``assets/NOTICE.md``). Nothing here writes outside OUT. Except for
``listen``, everything is silent: the backend plays every loop, at master volume 0."""

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
VILLAGE = f"{SCENES}/start.json"
PX = 32.0
DOOR_X, DOOR_Y = 10.0, 10.5  # m: the cottage's door is north of here; walking north from (DOOR_X, 6) goes in
INSIDE_DOOR_X, INSIDE_DOOR_Y = 8.0, 3.4  # m, in the cottage: its south doorway; walking south at INSIDE_DOOR_X goes out
RAIN, WIND = "Steady", "Strong"  # the Sound panel's own buttons (rain 3,000 drops; wind 9 m/s, gusts 0.3)


def _write(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=1, default=str) + "\n", encoding="utf-8")


def _project(root: Path, volume: float) -> Any:
    from engine.project_scaffold import create_project
    from engine.studio_project import Project

    if root.exists():
        raise SystemExit(f"{root} exists already: give a new OUT folder")
    create_project(root, "Rain on the Cottage", "hd2d_rpg")
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    config["master_volume"] = volume  # 0: the backend plays; nothing reaches the speakers
    _write(root / "config.json", config)
    return Project(root, config["world_file"])


def _cottage(project: Any) -> str:
    return str(next(key for key, *_rest in project.rooms() if "cottage" in project.label(key).lower()))


def _authored(root: Path, volume: float, indoors: bool = True) -> Any:
    """The game with its weather set as an AI tool sets it (Mesh's authoring operations, then saved): steady rain and
    a strong wind in the village; the same set in the cottage as the weather outside it, heard in there if ``indoors``."""
    from engine import authoring
    from engine.sound_emitters import library

    project = _project(root, volume)
    sounds = {p.name: project.import_sound(p) for p in library() if p.name in ("rain_loop.wav", "wind_loop.wav")}
    weather: list[dict[str, Any]] = [{"op": "set_rain", "strength": "steady"}, {"op": "set_wind", "speed": 9.0, "gust": 0.3},
                                     {"op": "set_weather_sounds", "rain": sounds["rain_loop.wav"],
                                      "wind": sounds["wind_loop.wav"]}]
    authoring.apply(project, weather)
    project.current = _cottage(project)
    authoring.apply(project, weather + ([{"op": "set_weather_sounds", "indoors": True}] if indoors else []))
    project.save()
    return project


def setup(out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    project = _project(out / "game", 0.0)
    return {"rooms": [project.label(key) for key, *_rest in project.rooms()], "cottage": _cottage(project)}


# ---------------------------------------------------------------------------------------------- reading the game
def _registered() -> int:
    from pyglet import media

    return len(media.Source._players)


def _feet(window: Any) -> tuple[float, float]:
    from engine.physics_runtime import _sprite_to_aabb

    box = _sprite_to_aabb(window.scene_controller._find_player_sprite())
    return box.x / PX, box.y / PX


def _room(window: Any) -> str:
    return str(window.scene_controller.current_scene_path or "").replace("\\", "/").rsplit("/", 1)[-1]


def _rain_on_screen(window: Any) -> int:
    """Rain effects in the room's particles as drawn (an indoor room's are left out)."""
    renderer = getattr(window, "hd2d_renderer", None)
    layer = getattr(renderer, "particles", None) if renderer is not None else getattr(window, "scene_particles", None)
    return sum(1 for e in getattr(layer, "effects", ()) or () if e.preset == "rain")


class _Walk:
    """The player walked with the arrow keys (the game's own movement and doors), every frame's soundscape logged."""

    def __init__(self, window: Any, keys: Any, real_time: bool = False, base: int = 0) -> None:
        """``base``: the players this process had registered before the game started (pyglet's count is
        process-wide: in a test run, other tests' players are in it), so that the log counts this game's own."""
        self.window, self.keys, self.real_time, self.base = window, keys, real_time, base
        self.log: list[dict[str, Any]] = []

    def frame(self) -> None:
        self.window.dispatch_event("on_update", 1 / 60)
        if self.real_time:
            import pyglet

            pyglet.app.platform_event_loop.dispatch_posted_events()  # (loops loop on pyglet's posted events)
            time.sleep(1 / 60)
        audio = self.window.audio
        self.log.append({"f": len(self.log), "room": _room(self.window), "rain_on_screen": _rain_on_screen(self.window),
                         "loops": {key: [round(t.volume * t.scale * audio.ambience_volume, 4), round(t.pan or 0.0, 3), t.path]
                                   for key, t in audio._loops.items()},
                         "registered": _registered() - self.base})

    def stand(self, seconds: float) -> None:
        for _ in range(round(seconds * 60)):
            self.frame()

    def _hold(self, key: int, done: Callable[[], bool], limit: int) -> bool:
        self.window.dispatch_event("on_key_press", key, 0)
        reached = False
        for _ in range(limit):
            if done():
                reached = True
                break
            self.frame()
        self.window.dispatch_event("on_key_release", key, 0)
        self.frame()
        return reached

    def to(self, axis: int, target: float, limit: int = 1500) -> bool:
        """Hold an arrow key until the player's feet reach ``target`` (m) on ``axis`` (0 east, 1 north)."""
        sign = 1 if target > _feet(self.window)[axis] else -1
        key = ((self.keys.LEFT, self.keys.RIGHT), (self.keys.DOWN, self.keys.UP))[axis][sign > 0]
        return self._hold(key, lambda: (_feet(self.window)[axis] - target) * sign >= 0, limit)

    def through(self, key: int, limit: int = 600) -> bool:
        """Hold an arrow key until the room changes (a door walked into)."""
        before = _room(self.window)
        gone = self._hold(key, lambda: _room(self.window) != before, limit)
        for _ in range(20):
            self.frame()
        return gone


def _levels(row: dict[str, Any]) -> dict[str, float]:
    return {name: row["loops"].get(f"weather:{name}", [0.0])[0] for name in ("rain", "wind")}


def _summary(log: list[dict[str, Any]], marks: dict[str, int]) -> dict[str, Any]:
    steps = {name: max((abs(_levels(a)[name] - _levels(b)[name]) for a, b in zip(log, log[1:])), default=0.0)
             for name in ("rain", "wind")}
    return {"frames": len(log), "marks": marks,
            "at_marks": {name: {"room": log[i - 1]["room"], **_levels(log[i - 1]), "rain_on_screen": log[i - 1]["rain_on_screen"],
                                "registered": log[i - 1]["registered"]} for name, i in marks.items()},
            "largest_change_in_one_frame": {k: round(v, 4) for k, v in steps.items()},
            "lowest_after_the_first_three_seconds": {name: min(_levels(r)[name] for r in log[180:]) for name in ("rain", "wind")},
            "most_players_registered": max(r["registered"] for r in log),
            "loops_heard": sorted({k for row in log for k in row["loops"]})}


def _route(walk: _Walk, say: Callable[[str], None] | None = None) -> dict[str, int]:
    """Outside in the rain and wind; west along the road and in through the cottage's door; inside; out again."""
    marks: dict[str, int] = {}
    keys = walk.keys

    def step(name: str, text: str, seconds: float, move: Callable[[], Any] | None = None) -> None:
        if say is not None:
            say(text)
        if move is not None:
            move()
        walk.stand(seconds)
        marks[name] = len(walk.log)

    step("outside", "Outside in the village: steady rain and a strong wind, both plain. The wind comes and goes a "
         "little with its gusts.", 6.0)
    step("at_the_door", "Walking west along the road to the cottage: still outside, the weather unchanged.", 1.0,
         lambda: walk.to(0, DOOR_X))
    step("inside", "In through the cottage's door. No rain falls in here. The rain and wind should sink over a "
         "second or two to about a third, and carry on: the same sounds, not cut, not started again.", 8.0,
         lambda: walk.through(keys.UP))
    step("inside_later", "Still inside: the weather steady and quiet outside the walls.", 3.0)
    walk.to(0, INSIDE_DOOR_X)
    step("outside_again", "Out through the door. The rain and wind should rise again over a second or two to what "
         "they were, with no jump and no second copy.", 8.0, lambda: walk.through(keys.DOWN))
    return marks


def _game(project: Path, scene: str = VILLAGE) -> Any:
    from hd2d_demo import HiddenGame

    game = HiddenGame(project, size=(1280, 720))
    game.window.load_scene(scene)
    return game


def _settled(window: Any, seconds: float = 10.0) -> dict[str, Any]:
    for _ in range(round(seconds * 60)):
        window.dispatch_event("on_update", 1 / 60)
    audio = window.audio
    return {"room": _room(window), "rain_on_screen": _rain_on_screen(window),
            **{name: round(next((t.volume * t.scale * audio.ambience_volume for k, t in audio._loops.items()
                                 if k == f"weather:{name}"), 0.0), 4) for name in ("rain", "wind")}}


def walk(out: Path) -> dict[str, Any]:
    """The game alone. The walk; then a quick save made in the cottage, the village walked back to, and the save
    loaded; then a new game window started in the cottage directly."""
    project = out / "game"
    cottage = f"{SCENES}/{next(p.name for p in (project / SCENES).glob('*.json') if 'cottage' in p.name.lower())}"
    base = _registered()
    game = _game(project)
    keys = game.arcade.key
    try:
        run = _Walk(game.window, keys, base=base)
        marks = _route(run)
        _write(out / "walk_log.json", run.log)
        report: dict[str, Any] = {"walk": _summary(run.log, marks)}
        # a save made indoors, loaded from outdoors
        run.to(0, DOOR_X)
        run.through(keys.UP)
        inside = _settled(game.window)
        game.window.dispatch_event("on_key_press", keys.F5, 0)  # quick save
        game.window.dispatch_event("on_key_release", keys.F5, 0)
        run.to(0, INSIDE_DOOR_X)
        run.through(keys.DOWN)
        outside = _settled(game.window, 6.0)
        game.window.dispatch_event("on_key_press", keys.F9, 0)  # quick load
        game.window.dispatch_event("on_key_release", keys.F9, 0)
        report["save_made_indoors"] = {"inside_before_saving": inside, "outside_before_loading": outside,
                                       "after_loading": _settled(game.window), "registered": _registered() - base}
    finally:
        game.window.close()
        os.chdir(game._cwd)
    report["registered_after_close"] = _registered() - base
    game = _game(project, cottage)  # a new game, started in the cottage
    try:
        report["started_indoors"] = {**_settled(game.window), "registered": _registered() - base}
    finally:
        game.window.close()
        os.chdir(game._cwd)
    report["registered_after_second_close"] = _registered() - base
    return report


def mix(out: Path) -> dict[str, Any]:
    """A stereo WAV of the walk: the loops the engine played, at the levels the engine gave them frame by frame. A
    software mix of the engine's own commands, not a recording of the sound card."""
    import wave

    import numpy as np

    log = json.loads((out / "walk_log.json").read_text(encoding="utf-8"))
    rate, per_frame = 22050, 22050 // 60
    total = len(log) * per_frame
    left, right = np.zeros(total, np.float64), np.zeros(total, np.float64)
    sources: dict[str, Any] = {}
    for i, row in enumerate(log):
        for _key, (level, pan, path) in row["loops"].items():
            if path not in sources:
                with wave.open(str(out / "game" / path)) as w:
                    assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (rate, 1, 2), path
                    sources[path] = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float64) / 32768
            src = sources[path]
            idx = np.arange(i * per_frame, (i + 1) * per_frame) % len(src)
            angle = (pan + 1.0) * math.pi / 4
            left[i * per_frame:(i + 1) * per_frame] += src[idx] * level * math.cos(angle)
            right[i * per_frame:(i + 1) * per_frame] += src[idx] * level * math.sin(angle)
    stereo = np.empty(total * 2, np.float64)
    stereo[0::2], stereo[1::2] = left, right
    path = out / "rain_on_the_cottage_mix.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(stereo, -1, 1) * 32767).astype("<i2").tobytes())
    return {"file": str(path), "seconds": round(total / rate, 1), "clipped_samples": int(np.sum(np.abs(stereo) >= 1.0))}


# ---------------------------------------------------------------------------------------------- Mesh Studio
def studio(out: Path) -> dict[str, Any]:
    """The whole of it by Mesh Studio's own controls (hidden window; clicks as a person's), from the template as made."""
    from hd2d_studio_demo import StudioDriver

    from engine import project_ops as ops

    project = out / "game"
    base = _registered()
    d = StudioDriver(project)
    k = d.arcade.key
    report: dict[str, Any] = {}

    def scene() -> dict[str, Any]:
        return dict(d.studio.project.scene())

    def panel() -> None:
        if d.studio.panel != "sound":
            d.studio.open_sound()
            d.advance(2)

    def flag() -> Any:
        return (scene().get("settings", {}).get("weather_sounds") or {}).get("indoors")

    def said() -> str:
        return str(ops.indoor_weather(scene())["message"])

    def shown(text: str) -> bool:
        return any(text in " ".join(label.split()) for label in d.labels())  # (a long label is wrapped over lines)

    try:
        village_key = d.studio.project.current
        cottage_key = _cottage(d.studio.project)
        panel()
        d.button(RAIN)  # the village's rain and wind: their sounds are chosen with them
        d.button(WIND)
        report["village"] = {"rain": ops.rain_strength(scene()), "sounds": ops.weather_sounds_of(scene()),
                             "says": said(), "says_it_on_screen": shown(said()),
                             "outdoors_switch": d.has_button("Outdoors (rain and snow fall): On"),
                             "indoor_switch_shown": any(t.startswith("Hear outside weather indoors") for t in d.texts())}
        d.studio.switch_room(cottage_key)  # (the Rooms list's button for it)
        d.advance(2)
        panel()
        report["cottage_as_made"] = {"indoor": ops.indoor_weather(scene())["indoor"], "says": said(),
                                     "says_it_on_screen": shown(said()),
                                     "rain_label": shown("Rain outside (not shown in here: this room is indoors)"),
                                     "outdoors_switch": d.has_button("Outdoors (rain and snow fall): Off"),
                                     "indoor_switch": d.has_button("Hear outside weather indoors: Off")}
        d.button("Hear outside weather indoors", prefix=True)  # on, with no weather set yet
        report["on_with_nothing_set"] = {"setting": flag(), "message": d.studio.message, "says": said(),
                                         "says_it_on_screen": shown(said())}
        d.button(RAIN)
        d.button(WIND)
        report["cottage_set"] = {"setting": flag(), "rain": ops.rain_strength(scene()), "sounds": ops.weather_sounds_of(scene()),
                                 "heard": {key: ops.indoor_weather(scene())[key] for key in ("rain", "wind")},
                                 "says": said(), "says_it_on_screen": shown(said()),
                                 "copied_into_project": [(project / p).is_file() for p in (
                                     "assets/ambience/rain_loop.wav", "assets/ambience/wind_loop.wav")]}
        states = [flag()]
        d.button("Hear outside weather indoors", prefix=True)  # off
        states.append(flag())
        report["message_off"] = d.studio.message
        d.button("Undo")
        states.append(flag())
        d.button("Redo")
        states.append(flag())
        d.button("Undo")
        states.append(flag())
        report["on_clicked_off_undo_redo_undo"] = states
        d.button("Save")
        report["saved_message"] = d.studio.message
        report["editing_registered_players"] = _registered() - base
    finally:
        d.close()
    saved = json.loads((project / SCENES / "cottage.json").read_text(encoding="utf-8")) if (
        project / SCENES / "cottage.json").is_file() else {}
    report["in_the_saved_file"] = {key: saved.get("settings", {}).get(key) for key in ("weather_exposure", "weather_sounds")}

    d = StudioDriver(project)  # closed and reopened
    try:
        d.studio.switch_room(cottage_key)
        d.advance(2)
        report["reopened"] = {"setting": flag(), "says": said(), "unsaved": sorted(d.studio.project.dirty)}
        d.studio.switch_room(village_key)
        d.advance(2)
        cycles = []
        for i in range(3):
            if i == 2:
                d.studio.switch_room(cottage_key)  # the third play-test starts in the cottage
                d.advance(2)
            d.key(k.F4)
            row: dict[str, Any] = {"mode": d.studio.mode, "started_in": _room(d.window)}
            if i == 0:
                run = _Walk(d.window, k, base=base)
                row["walk"] = _summary(run.log, _route(run))
            else:
                row["settled"] = _settled(d.window, 8.0)
            row["playing"] = {"loops": sorted(d.window.audio.loops()), "registered": _registered() - base}
            d.key(k.F4)
            d.advance(5)
            row["after_stop"] = {"mode": d.studio.mode, "loops": d.window.audio.loops(), "registered": _registered() - base}
            cycles.append(row)
        report["play_stop"] = cycles
        panel()  # (still in the cottage) the switch off: the room as it was before
        d.button("Hear outside weather indoors", prefix=True)
        d.key(k.F4)
        report["switched_off"] = {"setting": flag(), "says": said(), "played": _settled(d.window, 8.0),
                                  "loops": sorted(d.window.audio.loops())}
        d.key(k.F4)
        d.advance(5)
    finally:
        d.close()
    report["after_close_registered"] = _registered() - base
    return report


# ---------------------------------------------------------------------------------------------- export
def export(out: Path) -> dict[str, Any]:
    """``mesh export build`` of the game as Studio saved it, then the bundle's own engine: the village, the cottage."""
    project, bundle = out / "game", out / "game_export"
    if bundle.exists():
        shutil.rmtree(bundle)
    built = subprocess.run([sys.executable, "-m", "mesh_cli", "export", "build", "--out", str(bundle)], cwd=project,
                           capture_output=True, text=True, timeout=900, env={**os.environ, "PYTHONPATH": str(REPO)})
    report: dict[str, Any] = {"export_code": built.returncode, "export_tail": (built.stdout + built.stderr)[-300:],
                              "sounds_in_bundle": {w: (bundle / w).is_file() for w in (
                                  "assets/ambience/rain_loop.wav", "assets/ambience/wind_loop.wav")}}
    cottage = next((p.name for p in (project / SCENES).glob("*.json") if "cottage" in p.name.lower()), "")
    code = f"""
import json, sys
sys.path.insert(0, {str(bundle)!r})
import engine
sys.path.insert(1, {str(REPO / "tooling")!r})
from hd2d_demo import HiddenGame
from indoor_weather_demo import _settled
from pathlib import Path
from pyglet import media
game = HiddenGame(Path({str(bundle)!r}), size=(1280, 720))
row = {{"engine_from": engine.__file__, "master_volume": game.window.audio.master_volume}}
try:
    game.load({VILLAGE!r})
    row["village"] = _settled(game.window)
    game.load({SCENES + "/" + cottage!r})
    row["cottage"] = _settled(game.window, 15.0)
    row["registered"] = len(media.Source._players)
    row["unplayable"] = game.window.audio.diagnostics()["unplayable"]
finally:
    game.window.close()
    row["registered_after_close"] = len(media.Source._players)
print(json.dumps(row))
"""
    ran = subprocess.run([sys.executable, "-c", code], cwd=bundle, capture_output=True, text=True, timeout=900,
                         env={k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "MESH_REPO_ROOT")})
    try:
        report["bundle_run"] = json.loads(ran.stdout.strip().splitlines()[-1])
        report["bundle_run"]["engine_is_the_bundles"] = Path(report["bundle_run"]["engine_from"]).resolve().is_relative_to(
            bundle.resolve())
    except (IndexError, ValueError):
        report["bundle_run"] = {"failed": ran.stdout[-600:] + ran.stderr[-1500:]}
    return report


# ---------------------------------------------------------------------------------------------- cost
def perf(out: Path, indoors: str = "on") -> dict[str, Any]:
    """The soundscape's update timed in the village and in the cottage, the player standing (``indoors``: "on", or "off"
    for the same game with the cottage not asking to hear outside: what this build costs a room made before it; an
    older engine doesn't know the setting, so only "off" runs on one)."""
    from engine import sound_emitters

    root = out / f"perf_{indoors}"
    _authored(root, 0.0, indoors == "on")
    cottage = f"{SCENES}/{next(p.name for p in (root / SCENES).glob('*.json') if 'cottage' in p.name.lower())}"
    times: list[float] = []
    real = sound_emitters.update

    def timed(window: Any, dt: float) -> None:
        start = time.perf_counter()
        real(window, dt)
        times.append((time.perf_counter() - start) * 1e6)

    def measure(window: Any) -> dict[str, Any]:
        for _ in range(240):
            window.dispatch_event("on_update", 1 / 60)
        times.clear()
        for _ in range(2000):
            window.dispatch_event("on_update", 1 / 60)
        ordered = sorted(times)
        return {"updates_timed": len(times), "mean_us": round(sum(times) / len(times), 2),
                "median_us": round(ordered[len(ordered) // 2], 2), "p95_us": round(ordered[int(len(ordered) * 0.95)], 2),
                "loops": sorted(window.audio.loops())}

    base = _registered()
    game = _game(root)
    sound_emitters.update = timed  # (engine.game_runtime.tick calls it through the module)
    try:
        report: dict[str, Any] = {"indoors": indoors, "village": measure(game.window)}
        game.window.load_scene(cottage)
        report["cottage"] = measure(game.window)
        report["players_registered"] = _registered() - base
    finally:
        sound_emitters.update = real
        game.window.close()
        os.chdir(game._cwd)
    report["players_registered_after_close"] = _registered() - base
    return report


# ---------------------------------------------------------------------------------------------- for a person
def listen(out: Path) -> dict[str, Any]:
    """The owner's listening pass, through the speakers. Only ever run by a person, on purpose."""
    _authored(out / "listen", 0.8)
    base = _registered()
    game = _game(out / "listen")
    steps: list[str] = []

    def say(text: str) -> None:
        if text:
            steps.append(text)
            print(f"[{len(steps):2d}] {text}", flush=True)

    try:
        run = _Walk(game.window, game.arcade.key, real_time=True, base=base)
        summary = _summary(run.log, _route(run, say))
    finally:
        game.window.close()
        os.chdir(game._cwd)
    print(f"\nTo walk it yourself:  cd \"{out / 'listen'}\"  then  py -3.13 -m mesh_cli play", flush=True)
    return {"steps": steps, "summary": summary}


PHASES: dict[str, Callable[..., dict[str, Any]]] = {"setup": setup, "studio": studio, "walk": walk, "export": export,
                                                    "mix": mix, "perf": perf, "listen": listen}


def main() -> None:
    phase, out = sys.argv[1], Path(sys.argv[2]).resolve()
    os.environ.setdefault("MESH_STUDIO_NO_AI_BRIDGE", "1")
    os.environ.setdefault("MESH_RUNTIME_SETTINGS_PATH", str(out / "user_settings.json"))  # never the checkout's own
    out.mkdir(parents=True, exist_ok=True)
    report = PHASES[phase](out, *sys.argv[3:])
    _write(out / f"{phase}{'_' + sys.argv[3] if len(sys.argv) > 3 else ''}.json", report)
    print(json.dumps(report, indent=1, default=str)[:7000])


if __name__ == "__main__":
    main()
