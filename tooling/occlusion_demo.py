"""Milestone 21C1: a sound behind a wall, to hear and to measure. Two throwaway projects, made by this script.

    py -3.13 tooling/occlusion_demo.py setup OUT    OUT/hd2d: the HD-2D starter village with flowing water behind its
                                                    cottage; OUT/2d: a 2D room, a hum behind a wall of tiles (silent:
                                                    master volume 0)
    py -3.13 tooling/occlusion_demo.py studio OUT   Mesh Studio (hidden window): the emitter's "Quieter behind walls"
                                                    switch clicked off and on, undone, redone, saved, reopened; Play:
                                                    the player walks behind the cottage and out; Play/Stop three times
    py -3.13 tooling/occlusion_demo.py walk OUT     the games alone (hidden windows): the walk behind the wall and back,
                                                    every frame's levels logged (OUT/walk_hd2d.json, OUT/walk_2d.json)
    py -3.13 tooling/occlusion_demo.py mix OUT      a stereo WAV of the HD-2D walk, mixed in software from its log
    py -3.13 tooling/occlusion_demo.py perf OUT     the soundscape's cost per update with 60 emitters about the village

    py -3.13 tooling/occlusion_demo.py listen OUT   FOR A PERSON LISTENING: makes OUT/listen (master volume 0.8) and
                                                    walks it through the speakers, each step captioned here (about a
                                                    minute). To walk it yourself afterwards:
                                                        cd OUT/listen  then  py -3.13 -m mesh_cli play
                                                    (arrow keys; the water is north of the cottage, behind it)

The water is Mesh's own ``assets/ambience/stream_loop.wav`` (a 10 s mono loop cut from a CC0 recording: author and
source in ``assets/NOTICE.md``); the 2D room's hum is the same file. Nothing here writes outside OUT. Except for
``listen``, everything is silent: the backend plays every loop, at master volume 0."""

from __future__ import annotations

import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(1, str(REPO / "tooling"))
SCENE = "packs/core_regions/scenes/start.json"
PX = 32.0
WATER = "assets/ambience/stream_loop.wav"
WATER_AT = (10.0, 15.5)  # m: north of the cottage (its walls: x 7.5 to 12.5, y 10 to 14, 2.5 m tall)
CLEAR_AT = (20.0, 14.5)  # m: on the north path, the cottage not between
BEHIND_AT = (20.0, 7.0)  # m: down the path, at the crossroads: the cottage's east wall is between
DEEP_AT = (10.5, 7.0)  # m: west along the road, in front of the cottage's door: the whole cottage is between
EDGE_AT = (11.0, 8.0)  # m north on that path: a clear line at the first, the cottage's corner between at the second
HUM_TILE, HUM_CLEAR, HUM_BEHIND = (12, 5), (3, 14), (3, 5)  # the 2D room: the hum, and two places to stand (tiles,
# counted from the room's south-west corner; both within its full-strength radius)
WALL_TILES = [(9, y) for y in range(2, 8)]  # a wall six tiles tall between HUM_BEHIND and the hum


def _write(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=1, default=str) + "\n", encoding="utf-8")


def _project(root: Path, name: str, template: str, volume: float) -> Any:
    from engine.project_scaffold import create_project
    from engine.studio_project import Project

    if root.exists():
        raise SystemExit(f"{root} exists already: give a new OUT folder")
    create_project(root, name, template)
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    config["master_volume"] = volume  # 0: the backend plays; nothing reaches the speakers
    _write(root / "config.json", config)
    return Project(root, config["world_file"])


def _hd2d_project(root: Path, volume: float) -> dict[str, Any]:
    """The HD-2D starter village with flowing water north of its cottage, made as an AI tool makes it: through
    Mesh's own authoring operations, then saved."""
    from engine import authoring
    from engine import project_ops as ops

    project = _project(root, "Behind the Cottage", "hd2d_rpg", volume)
    sound = project.import_sound(ops_library("stream_loop.wav"))
    player = next(e for e in project.scene()["entities"] if "player" in str(e.get("tag", "")) or e.get("id", "").endswith("player"))
    authoring.apply(project, [
        {"op": "place_blank", "name": "Water behind the cottage", "x": WATER_AT[0] * PX, "y": WATER_AT[1] * PX},
        {"op": "set_sound_emitter", "entity_id": "@0", "sound": sound, "volume": 0.9, "radius": 3 * PX,
         "distance": 24 * PX, "occlusion": True},
        {"op": "move_entity", "entity_id": player["id"], "x": CLEAR_AT[0] * PX, "y": CLEAR_AT[1] * PX},
    ])
    project.save()
    emitter = next(e for e in project.scene()["entities"] if e.get("name") == "Water behind the cottage")
    return {"project": str(root), "emitter": emitter["id"], "settings": ops.sound_emitter_of(emitter),
            "player_start_m": list(CLEAR_AT)}


def ops_library(name: str) -> Path:
    from engine.sound_emitters import library

    return Path(next(p for p in library() if p.name == name))


def _two_d_project(root: Path, volume: float) -> dict[str, Any]:
    """A blank 2D room: a wall of tiles, a hum behind it, the player in front."""
    from engine import authoring
    from engine import project_ops as ops

    project = _project(root, "Behind the Wall", "blank", volume)
    sound = project.import_sound(ops_library("stream_loop.wav"))
    scene = project.scene()
    tile_w = int((scene.get("tilemap") or {}).get("tilewidth") or 32)
    player = next(e for e in scene["entities"] if "player" in str(e.get("tag", "")) or e.get("id", "").endswith("player"))

    def centre(tile: tuple[int, int]) -> tuple[float, float]:
        return (tile[0] + 0.5) * tile_w, (tile[1] + 0.5) * tile_w

    rows = int((scene.get("tilemap") or {}).get("height") or 16)
    cells = [(x, rows - 1 - y) for x, y in WALL_TILES]  # (a tile layer's rows count down from the top)
    project.edit_scene(lambda room: ops.paint_tiles(room, "walls", cells, 9))
    authoring.apply(project, [
        {"op": "place_blank", "name": "Hum behind the wall", "x": centre(HUM_TILE)[0], "y": centre(HUM_TILE)[1]},
        {"op": "set_sound_emitter", "entity_id": "@0", "sound": sound, "volume": 0.9, "radius": 13 * tile_w,
         "distance": 20 * tile_w, "occlusion": True},
        {"op": "move_entity", "entity_id": player["id"], "x": centre(HUM_CLEAR)[0], "y": centre(HUM_CLEAR)[1]},
    ])
    project.save()
    emitter = next(e for e in project.scene()["entities"] if e.get("name") == "Hum behind the wall")
    return {"project": str(root), "emitter": emitter["id"], "tile": tile_w, "settings": ops.sound_emitter_of(emitter)}


def setup(out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    return {"hd2d": _hd2d_project(out / "hd2d", 0.0), "2d": _two_d_project(out / "2d", 0.0)}


# ---------------------------------------------------------------------------------------------- reading the game
def _heard(window: Any) -> dict[str, list[Any]]:
    """Each ambience loop as the engine has it now: [level before the master volume, pan, file]."""
    audio = window.audio
    return {key: [round(t.volume * t.scale * audio.ambience_volume, 4), round(t.pan or 0.0, 3), t.path]
            for key, t in audio._loops.items()}


def _registered() -> int:
    from pyglet import media

    return len(media.Source._players)


def _feet(window: Any) -> tuple[float, float]:
    from engine.physics_runtime import _sprite_to_aabb

    player = window.scene_controller._find_player_sprite()
    box = _sprite_to_aabb(player)
    return box.x / PX, box.y / PX


class _Walk:
    """The player walked with the arrow keys (the game's own movement), every frame's soundscape logged."""

    def __init__(self, window: Any, keys: Any, real_time: bool = False) -> None:
        self.window, self.keys, self.real_time = window, keys, real_time
        self.log: list[dict[str, Any]] = []

    def frame(self) -> None:
        self.window.dispatch_event("on_update", 1 / 60)
        if self.real_time:
            import pyglet

            pyglet.app.platform_event_loop.dispatch_posted_events()  # (loops loop on pyglet's posted events)
            time.sleep(1 / 60)
        scape = self.window.soundscape
        fx, fy = _feet(self.window)
        self.log.append({"f": len(self.log), "at": [round(fx, 2), round(fy, 2)], "loops": _heard(self.window),
                         "behind_walls": [e.key for e in scape.emitters if e.blocked], "asks": scape.wall_asks})

    def stand(self, seconds: float) -> None:
        for _ in range(round(seconds * 60)):
            self.frame()

    def to(self, axis: int, target: float, limit: int = 1500) -> bool:
        """Hold an arrow key until the player's feet reach ``target`` (m) on ``axis`` (0 east, 1 north)."""
        at = _feet(self.window)[axis]
        sign = 1 if target > at else -1
        key = ((self.keys.LEFT, self.keys.RIGHT), (self.keys.DOWN, self.keys.UP))[axis][sign > 0]
        self.window.dispatch_event("on_key_press", key, 0)
        reached = False
        for _ in range(limit):
            if (_feet(self.window)[axis] - target) * sign >= 0:
                reached = True
                break
            self.frame()
        self.window.dispatch_event("on_key_release", key, 0)
        self.frame()
        return reached

    def level(self, prefix: str = "emitter:") -> float:
        row = self.log[-1]["loops"]
        return next((v[0] for k, v in row.items() if k.startswith(prefix)), 0.0)


def _summary(log: list[dict[str, Any]], marks: dict[str, int]) -> dict[str, Any]:
    levels = [next((v[0] for k, v in row["loops"].items() if k.startswith("emitter:")), 0.0) for row in log]
    pans = [next((v[1] for k, v in row["loops"].items() if k.startswith("emitter:")), 0.0) for row in log]
    steps = [abs(a - b) for a, b in zip(levels, levels[1:])]
    return {"frames": len(log), "marks": marks,
            "levels_at_marks": {name: levels[i - 1] for name, i in marks.items()},
            "pans_at_marks": {name: pans[i - 1] for name, i in marks.items()},
            "behind_walls_at_marks": {name: bool(log[i - 1]["behind_walls"]) for name, i in marks.items()},
            "largest_change_in_one_frame": round(max(steps), 4) if steps else 0.0,
            "silent_frames_after_the_first_second": sum(1 for v in levels[60:] if v <= 0.0),
            "wall_questions_asked": log[-1]["asks"], "loops_heard": sorted({k for row in log for k in row["loops"]})}


def _route_hd2d(walk: _Walk, say: Any = None) -> dict[str, int]:
    """Clear on the north path; down to the crossroads (the cottage's corner comes between); west to its door (the
    whole cottage between); back the same way."""
    marks: dict[str, int] = {}

    def step(name: str, text: str, seconds: float, move: Any = None) -> None:
        if say is not None:
            say(text)
        if move is not None:
            move()
        walk.stand(seconds)
        marks[name] = len(walk.log)

    step("clear", "Standing on the north path: the water is heard clearly, from the left (it is to the west).", 4.0)
    step("behind", "Walking south down the path. Part-way the cottage comes between: the water sinks, gradually, "
         "over about a second. It should not cut out, click or start again.", 3.0, lambda: walk.to(1, BEHIND_AT[1]))
    step("deep", "Walking west along the road to the cottage's door. The water stays low and steady behind the "
         "cottage, a little louder as you come nearer to it, and moves toward the middle.", 3.0,
         lambda: walk.to(0, DEEP_AT[0]))
    step("behind_again", "Walking back east to the crossroads: still behind the cottage, still low.", 2.0,
         lambda: walk.to(0, BEHIND_AT[0]))
    step("clear_again", "Walking north up the path. As the cottage's corner clears, the water comes back to full, "
         "gradually: the same sound, not a restart.", 4.0, lambda: walk.to(1, CLEAR_AT[1]))
    walk.to(1, EDGE_AT[0])
    for i in range(3):
        step(f"edge_in_{i}", "Three quick steps behind the cottage's corner and out again: each a smooth dip and "
             "return, with no click, gap or restart." if i == 0 else "", 0.4, lambda: walk.to(1, EDGE_AT[1]))
        step(f"edge_out_{i}", "", 0.4, lambda: walk.to(1, EDGE_AT[0]))
    step("end", "Back up the north path: the water as at the start.", 3.0, lambda: walk.to(1, CLEAR_AT[1]))
    return marks


def _route_2d(walk: _Walk, tile: float) -> dict[str, int]:
    marks: dict[str, int] = {}
    walk.stand(2.0)
    marks["clear"] = len(walk.log)
    walk.to(1, (HUM_BEHIND[1] + 0.5) * tile / PX)
    walk.stand(2.5)
    marks["behind"] = len(walk.log)
    walk.to(1, (HUM_CLEAR[1] + 0.5) * tile / PX)
    walk.stand(2.5)
    marks["clear_again"] = len(walk.log)
    return marks


def _game(project: Path) -> Any:
    from hd2d_demo import HiddenGame

    game = HiddenGame(project, size=(1280, 720))
    game.window.load_scene(SCENE)
    return game


def walk(out: Path) -> dict[str, Any]:
    report: dict[str, Any] = {}
    for name in ("hd2d", "2d"):
        before = _registered()
        game = _game(out / name)
        try:
            run = _Walk(game.window, game.arcade.key)
            tile = float(getattr(game.window.scene_controller.tilemap_instance, "tile_size", (32, 32))[0] or 32)
            marks = _route_hd2d(run) if name == "hd2d" else _route_2d(run, tile)
            _write(out / f"walk_{name}.json", run.log)
            report[name] = {**_summary(run.log, marks), "players_registered_while_playing": _registered() - before,
                            "hd2d": game.window.hd2d_renderer is not None,
                            "hd2d_error": getattr(game.window, "hd2d_error", None)}
        finally:
            game.window.close()
            os.chdir(game._cwd)
        report[name]["players_registered_after_close"] = _registered() - before
    return report


def mix(out: Path) -> dict[str, Any]:
    """A stereo WAV of the HD-2D walk: the loop the engine played, at the level and pan the engine gave it frame by
    frame (equal-power pan). A software mix of the engine's own commands, not a recording of the sound card."""
    import wave

    import numpy as np

    log = json.loads((out / "walk_hd2d.json").read_text(encoding="utf-8"))
    rate, per_frame = 22050, 22050 // 60
    total = len(log) * per_frame
    left, right = np.zeros(total, np.float64), np.zeros(total, np.float64)
    sources: dict[str, Any] = {}
    for i, row in enumerate(log):
        for _key, (level, pan, path) in row["loops"].items():
            if path not in sources:
                with wave.open(str(out / "hd2d" / path)) as w:
                    assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (rate, 1, 2), path
                    sources[path] = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float64) / 32768
            src = sources[path]
            idx = np.arange(i * per_frame, (i + 1) * per_frame) % len(src)
            angle = (pan + 1.0) * math.pi / 4
            left[i * per_frame:(i + 1) * per_frame] += src[idx] * level * math.cos(angle)
            right[i * per_frame:(i + 1) * per_frame] += src[idx] * level * math.sin(angle)
    stereo = np.empty(total * 2, np.float64)
    stereo[0::2], stereo[1::2] = left, right
    path = out / "behind_the_cottage_mix.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(stereo, -1, 1) * 32767).astype("<i2").tobytes())
    return {"file": str(path), "seconds": round(total / rate, 1),
            "clipped_samples": int(np.sum(np.abs(stereo) >= 1.0))}


# ---------------------------------------------------------------------------------------------- Mesh Studio
def studio(out: Path) -> dict[str, Any]:
    """The switch in Mesh Studio's own inspector (hidden window, clicks as a person's), and the game played from it."""
    from hd2d_studio_demo import StudioDriver

    from engine import project_ops as ops

    project = out / "hd2d"
    base = _registered()
    d = StudioDriver(project)
    k = d.arcade.key
    report: dict[str, Any] = {}

    def emitter() -> dict[str, Any]:
        return next(e for e in d.studio.project.scene()["entities"] if e.get("name") == "Water behind the cottage")

    def setting() -> Any:
        return emitter()["behaviour_config"]["SoundEmitter"].get("occlusion")

    try:
        d.studio.select(emitter()["id"])
        d.advance(2)
        report["inspector_shows_the_switch"] = d.has_button("Quieter behind walls: On")
        states = [setting()]
        d.button("Quieter behind walls", prefix=True)  # off
        states.append(setting())
        report["message_off"] = d.studio.message
        d.button("Quieter behind walls", prefix=True)  # on again
        states.append(setting())
        report["message_on"] = d.studio.message
        d.button("Undo")
        states.append(setting())
        d.button("Undo")
        states.append(setting())
        d.button("Redo")
        states.append(setting())
        d.button("Redo")
        states.append(setting())
        report["clicked_off_on_undo_undo_redo_redo"] = states
        d.button("Save")
        report["saved_message"] = d.studio.message
        report["editing_registered_players"] = _registered() - base
    finally:
        d.close()
    saved = json.loads((project / SCENE).read_text(encoding="utf-8"))
    config = next(e for e in saved["entities"] if e.get("name") == "Water behind the cottage")["behaviour_config"]
    report["in_the_saved_file"] = config["SoundEmitter"]

    d = StudioDriver(project)  # closed and reopened
    try:
        d.studio.select(emitter()["id"])
        d.advance(2)
        report["reopened"] = {"setting": (ops.sound_emitter_of(emitter()) or {}).get("occlusion"), "unsaved": sorted(d.studio.project.dirty)}
        cycles = []
        for i in range(3):
            d.key(k.F4)
            row: dict[str, Any] = {"mode": d.studio.mode}
            if i == 0:
                run = _Walk(d.window, k)
                marks = _route_hd2d(run)
                row["walk"] = _summary(run.log, marks)
            else:
                for _ in range(40):
                    d.window.dispatch_event("on_update", 1 / 60)
            row["playing"] = {"loops": sorted(d.window.audio.loops()), "registered": _registered() - base}
            d.key(k.F4)
            d.advance(5)
            row["after_stop"] = {"mode": d.studio.mode, "loops": d.window.audio.loops(), "registered": _registered() - base}
            cycles.append(row)
        report["play_stop"] = cycles
    finally:
        d.close()
    report["after_close_registered"] = _registered() - base
    return report


# ---------------------------------------------------------------------------------------------- cost
def perf(out: Path, occlusion: str = "on") -> dict[str, Any]:
    """The soundscape's update timed in the village with 60 emitters about it (``occlusion``: "on", or "off" for the
    same room with none of them minding walls: what this build costs a room made before it), the player walking the
    route. Run it on another checkout's engine by starting this script from that checkout."""
    import tracemalloc

    from engine import sound_emitters
    from engine.studio_project import Project

    root = out / f"perf_{occlusion}"
    made = _hd2d_project(root, 0.0)
    project = Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"])
    from engine import authoring

    changes: list[dict[str, Any]] = []
    for i in range(59):  # with the water: 60 emitters, in a ring of rings about the village
        angle, reach = i * 2.399963, 4.0 + (i % 9) * 2.0
        x, y = 20.0 + math.cos(angle) * reach * 1.6, 12.0 + math.sin(angle) * reach
        changes.append({"op": "place_blank", "name": f"Perf {i}", "x": round(x * PX, 1), "y": round(y * PX, 1)})
        setting: dict[str, Any] = {"op": "set_sound_emitter", "entity_id": f"@{2 * i}", "sound": WATER,
                                   "radius": 2 * PX, "distance": 16 * PX}
        if occlusion == "on":
            setting["occlusion"] = True
        changes.append(setting)
    authoring.apply(project, changes)
    if occlusion != "on":
        from engine import project_ops as ops

        project.edit_scene(lambda room: ops.set_sound_emitter(room, made["emitter"], occlusion=False))
    project.save()

    times: list[float] = []
    real = sound_emitters.update

    def timed(window: Any, dt: float) -> None:
        start = time.perf_counter()
        real(window, dt)
        times.append((time.perf_counter() - start) * 1e6)

    base = _registered()
    game = _game(root)
    sound_emitters.update = timed  # (engine.game_runtime.tick calls it through the module)
    try:
        run = _Walk(game.window, game.arcade.key)
        run.stand(2.0)
        times.clear()
        tracemalloc.start()
        before = tracemalloc.take_snapshot()
        marks = _route_hd2d(run)
        engine_dir = str(REPO / "engine")  # (the engine's own allocations: not this walk's log)
        retained = sum(s.size_diff for s in tracemalloc.take_snapshot().compare_to(before, "filename")
                       if s.traceback[0].filename.startswith(engine_dir))
        tracemalloc.stop()
        scape = game.window.soundscape
        ordered = sorted(times)
        report = {"occlusion": occlusion, "emitters": len(scape.emitters), "updates_timed": len(times),
                  "update_us": {"mean": round(sum(times) / len(times), 1), "median": round(ordered[len(ordered) // 2], 1),
                                "p95": round(ordered[int(len(ordered) * 0.95)], 1), "max": round(ordered[-1], 1)},
                  "wall_questions_asked": getattr(scape, "wall_asks", None),
                  "wall_questions_per_update": round(getattr(scape, "wall_asks", 0) / max(1, scape.updates), 3),
                  "walls_in_the_room": len(game.window.hd2d_world.walls),
                  "walls_a_sound_does_not_pass": len(getattr(scape, "walls", [])),
                  "players_registered": _registered() - base, "loops_playing": len(game.window.audio.loops()),
                  "engine_bytes_retained_over_the_walk": retained, "frames": len(run.log), "marks": marks}
    finally:
        sound_emitters.update = real
        game.window.close()
        os.chdir(game._cwd)
    report["players_registered_after_close"] = _registered() - base
    return report


# ---------------------------------------------------------------------------------------------- for a person
def listen(out: Path) -> dict[str, Any]:
    """The owner's listening pass, through the speakers. Only ever run by a person, on purpose."""
    made = _hd2d_project(out / "listen", 0.8)
    game = _game(out / "listen")
    steps: list[str] = []

    def say(text: str) -> None:
        if text:
            steps.append(text)
            print(f"[{len(steps):2d}] {text}", flush=True)

    try:
        run = _Walk(game.window, game.arcade.key, real_time=True)
        marks = _route_hd2d(run, say)
        summary = _summary(run.log, marks)
    finally:
        game.window.close()
        os.chdir(game._cwd)
    print(f"\nTo walk it yourself:  cd \"{out / 'listen'}\"  then  py -3.13 -m mesh_cli play", flush=True)
    return {"project": made["project"], "steps": steps, "summary": summary}


PHASES: dict[str, Callable[..., dict[str, Any]]] = {"setup": setup, "studio": studio, "walk": walk, "mix": mix, "perf": perf, "listen": listen}


def main() -> None:
    phase, out = sys.argv[1], Path(sys.argv[2]).resolve()
    os.environ.setdefault("MESH_STUDIO_NO_AI_BRIDGE", "1")
    os.environ.setdefault("MESH_RUNTIME_SETTINGS_PATH", str(out / "user_settings.json"))  # never the checkout's own
    out.mkdir(parents=True, exist_ok=True)
    report = PHASES[phase](out, *sys.argv[3:])
    _write(out / f"{phase}{'_' + sys.argv[3] if len(sys.argv) > 3 else ''}.json", report)
    print(json.dumps(report, indent=1, default=str)[:6000])


if __name__ == "__main__":
    main()
