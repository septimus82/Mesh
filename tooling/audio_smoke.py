"""M21A: Mesh's music, buses and cleanup on the real audio backend (pyglet's driver on this machine), in hidden windows.

    py -3.13 tooling/audio_smoke.py setup OUT [--audible]   a starter project in OUT/project whose rooms use music
    py -3.13 tooling/audio_smoke.py game OUT     rooms, crossfades, loops, pause, save/load, broken files, buses, close
    py -3.13 tooling/audio_smoke.py studio OUT   Mesh Studio: silent while editing; Play/Stop ten times
    py -3.13 tooling/audio_smoke.py export OUT   ``mesh export build``; the bundle's own engine plays the music
    py -3.13 tooling/audio_smoke.py listen OUT   FOR A PERSON LISTENING: about 70 s through the speakers, captioned

**Silent by default:** the project's master volume is 0, so the backend decodes and plays every track (its players
run, advance and loop) but nothing reaches the speakers. Levels are reported before the master volume. ``--audible``
keeps the master volume at 1 for a person listening.

What it measures is the backend's own state (players registered, each one's playing flag, time and volume), never
how anything sounds. The music is Mesh's own synthesised loops, plus the CC0 tracks in
``tooling/audio_test_assets.json`` when they are present (checked by SHA-256; kept outside the repository)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
SCENES = "packs/core_regions/scenes"
DUNGEON, FOREST = "assets/music/dungeon_theme.wav", "assets/music/forest_theme.wav"
TOWN, WOODS = "assets/music/TownTheme.mp3", "assets/ambience/Forest_Ambience.mp3"  # (when the CC0 files are present)
BROKEN = {"empty": "assets/music/broken_empty.wav", "not_audio": "assets/music/broken_text.ogg",
          "truncated": "assets/music/broken_truncated.mp3"}
ROOMS: dict[str, dict[str, Any]] = {
    "dungeon": {"music": DUNGEON},
    "dungeon_quiet": {"music": DUNGEON, "music_volume": 0.5},
    "forest": {"music": FOREST},
    "town": {"music": TOWN},
    "no_setting": {},
    "silence": {"music": None},
    "missing": {"music": "assets/music/not_there.wav"},
    **{f"broken_{k}": {"music": v} for k, v in BROKEN.items()},
}


def third_party() -> dict[str, Path]:
    """The CC0 test files that are present and intact: id -> path."""
    manifest = json.loads((REPO / "tooling/audio_test_assets.json").read_text(encoding="utf-8"))
    root = Path(os.environ.get("MESH_AUDIO_ASSETS", "D:/Games/Mesh-audio-assets/downloads"))
    found = {}
    for asset in manifest["assets"]:
        path = root / asset["file"]
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == asset["sha256"]:
            found[asset["id"]] = path
    return found


def setup(out: Path, audible: bool) -> dict[str, Any]:
    project = out / "project"
    if project.exists():
        shutil.rmtree(project)
    made = subprocess.run([sys.executable, "-m", "mesh_cli", "new", "project", "--dest", str(out), "--template", "starter"],
                          cwd=REPO, capture_output=True, text=True, timeout=600)
    assert made.returncode == 0, made.stdout + made.stderr
    for folder in ("assets/music", "assets/ambience"):
        (project / folder).mkdir(parents=True, exist_ok=True)
    for track in (DUNGEON, FOREST):
        shutil.copy(REPO / track, project / track)
    shutil.copytree(REPO / "assets/sounds", project / "assets/sounds", dirs_exist_ok=True)  # Mesh's own effects
    cc0 = third_party()
    if "town_theme" in cc0:
        shutil.copy(cc0["town_theme"], project / TOWN)
    if "forest_ambience" in cc0:
        shutil.copy(cc0["forest_ambience"], project / WOODS)
    (project / BROKEN["empty"]).write_bytes(b"")
    (project / BROKEN["not_audio"]).write_text("not audio at all", encoding="utf-8")
    source = cc0.get("town_theme", REPO / DUNGEON)
    (project / BROKEN["truncated"]).write_bytes(source.read_bytes()[:4000])
    start_path = project / SCENES / "start.json"
    start = json.loads(start_path.read_text(encoding="utf-8"))
    for name, music in ROOMS.items():
        room = json.loads(json.dumps(start))
        room["name"] = name
        settings = room.setdefault("settings", {})
        settings.pop("music", None)
        settings.update(music)
        (project / SCENES / f"{name}.json").write_text(json.dumps(room, indent=1), encoding="utf-8")
    start.setdefault("settings", {})["music"] = TOWN if "town_theme" in cc0 else DUNGEON  # Studio's and the export's
    start_path.write_text(json.dumps(start, indent=1), encoding="utf-8")
    config = json.loads((project / "config.json").read_text(encoding="utf-8"))
    config.update({"music_crossfade_enabled": True, "music_crossfade_out_s": 1.0, "music_crossfade_in_s": 1.0,
                   "master_volume": 1.0 if audible else 0.0})
    (project / "config.json").write_text(json.dumps(config, indent=1), encoding="utf-8")
    return {"project": str(project), "rooms": sorted(ROOMS), "cc0_files": sorted(cc0), "audible": audible}


def _registered() -> int:
    from pyglet import media

    return len(media.Source._players)


def _level(audio: Any, track: Any) -> float:
    """A track's loudness before the master volume: its own volume x its fade x its bus's volume."""
    return round(float(track.volume * track.scale) * float(getattr(audio, f"{track.bus}_volume")), 3)


class _Run:
    def __init__(self, game: Any) -> None:
        self.game, self.window, self.audio = game, game.window, game.window.audio

    def enter(self, room: str) -> None:
        self.game.load(f"{SCENES}/{room}.json")

    def play(self, seconds: float) -> None:
        """Frames in real time, so the backend's players advance as they would in a game. pyglet's posted events are
        delivered too, as ``arcade.run``'s event loop does: a player's end of stream (where a loop starts again) is one."""
        import pyglet

        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            self.window.dispatch_event("on_update", 1 / 60)
            pyglet.app.platform_event_loop.dispatch_posted_events()
            time.sleep(1 / 60)

    def track(self) -> Any:
        return self.audio._music_track

    def state(self) -> dict[str, Any]:
        track = self.track()
        return {"music": self.audio.music_path, "registered_players": _registered(),
                "live": self.audio.diagnostics()["live_players"],
                "player": None if track is None else {"playing": bool(track.player.playing),
                                                      "time": round(float(track.player.time), 2),
                                                      "level": _level(self.audio, track),
                                                      "output_volume": round(float(track.player.volume), 3)}}

    def crossfade(self, room: str) -> dict[str, Any]:
        """Into ``room``: both tracks sampled through the overlap, then the old one's release."""
        a = self.track()
        self.enter(room)
        b = self.track()
        samples = []
        for _ in range(4):
            before = (float(a.player.time), float(b.player.time))
            self.play(0.2)
            samples.append({side: {"playing": bool(t.player.playing), "advanced_s": round(float(t.player.time) - t0, 2),
                                   "level": _level(self.audio, t)}
                            for side, t, t0 in (("old", a, before[0]), ("new", b, before[1]))})
        self.play(0.6)
        return {"from": a.path, "to": b.path, "overlap": samples,
                "after": {**self.state(), "old_still_playing": bool(a.player.playing)}}


def game_checks(project: Path, out: Path) -> dict[str, Any]:
    sys.path.insert(0, str(REPO / "tooling"))
    from hd2d_demo import HiddenGame
    from pyglet.media import get_audio_driver

    town = (project / TOWN).is_file()
    game = HiddenGame(project)
    run = _Run(game)
    report: dict[str, Any] = {"driver": type(get_audio_driver()).__name__, "before": _registered(),
                              "master_volume": run.audio.master_volume}
    try:
        run.enter("dungeon")
        run.play(1.2)
        first = run.track().player
        report["entered_dungeon"] = run.state()
        run.enter("no_setting")
        run.play(0.6)
        report["no_setting_keeps_it"] = {**run.state(), "same_player": run.track().player is first}
        run.enter("dungeon_quiet")
        run.play(1.2)
        report["same_track_again"] = {**run.state(), "same_player": run.track().player is first}
        report["crossfade_wav_to_wav"] = run.crossfade("forest")
        if town:
            report["crossfade_wav_to_mp3"] = run.crossfade("town")
            track = run.track()  # an MP3 loops: past its end, it goes on from the start
            track.player.seek(track.player.source.duration - 0.5)
            before = float(track.player.time)
            run.play(1.2)
            report["mp3_loops"] = {"before_end_s": round(before, 2), "after_s": round(float(track.player.time), 2),
                                   "duration_s": round(float(track.player.source.duration), 2),
                                   "playing": bool(track.player.playing), "same_player": run.track() is track}

        run.enter("silence")
        run.play(1.3)
        report["explicit_silence"] = run.state()

        rooms = ["dungeon", "forest", "no_setting", "dungeon_quiet", "silence"] + (["town"] if town else [])
        peak = 0
        for i in range(60):  # rapid room changes: two frames in each room
            run.enter(rooms[i % len(rooms)])
            run.play(2 / 60)
            peak = max(peak, _registered())
        run.enter("forest")
        run.play(2.5)
        report["rapid_room_changes"] = {"rooms_entered": 60, "peak_registered_players": peak, **run.state()}

        run.enter("dungeon")  # pause in the middle of a crossfade: it finishes; unpaused, the music carries on
        run.play(0.3)
        run.window.paused = True
        run.play(1.3)
        paused = run.state()
        run.window.paused = False
        run.play(0.5)
        report["pause_and_resume"] = {"paused": paused, "resumed": run.state()}

        run.enter("no_setting")  # the dungeon theme carries on here: the save records it
        run.play(0.3)
        report["save_ok"] = bool(run.window.save_manager.save_game("audio_smoke"))
        saved = json.loads(next((project / "saves").rglob("audio_smoke*.json")).read_text(encoding="utf-8"))
        report["save_meta_music"] = saved.get("meta", {}).get("music")
        run.enter("silence")
        run.play(1.3)
        report["silent_before_load"] = run.state()
        report["load_ok"] = bool(run.window.save_manager.load_game("audio_smoke"))
        run.play(1.3)
        report["after_loading_the_save"] = run.state()

        playing = run.track().player
        broken: dict[str, Any] = {}
        for room in ("missing", "broken_empty", "broken_not_audio"):
            run.enter(room)
            run.play(0.3)
            broken[room] = {"music": run.audio.music_path, "same_player": run.track().player is playing}
        broken["unplayable"] = run.audio.diagnostics()["unplayable"]
        run.enter("broken_truncated")  # loads (a few KB of a real file), plays what there is, and loops on it
        run.play(1.5)
        broken["broken_truncated"] = run.state()
        report["broken_files"] = broken
        run.enter("dungeon")
        run.play(1.2)
        playing = run.track().player

        if (project / WOODS).is_file():  # the ambience bus: a loop, never duplicated, on its own volume
            loops = []
            for _ in range(3):
                run.audio.play_loop("woods", WOODS, volume=0.8, fade_in_s=0.5)
                run.play(0.6)
                loops.append(_registered())
            loop = run.audio._loops["woods"]
            run.audio.set_ambience_volume(0.5)
            report["ambience_loop"] = {"registered_after_each_request": loops, "playing": bool(loop.player.playing),
                                       "time": round(float(loop.player.time), 2), "level": _level(run.audio, loop),
                                       "music_level_unchanged": _level(run.audio, run.track())}
            run.audio.stop_loop("woods", fade_out_s=0.5)
            run.play(0.8)
            report["ambience_loop"]["after_stop"] = {"loops": run.audio.loops(), "registered": _registered()}
            run.audio.set_ambience_volume(1.0)

        run.audio.play_sound("assets/sounds/footstep.wav")
        run.audio.play_sound("assets/sounds/hit.wav")
        run.play(0.3)
        report["after_sfx"] = {**run.state(), "same_player": run.track().player is playing}
        run.audio.set_music_volume(0.3)
        run.audio.set_muted(True, "music")
        muted = run.state()
        run.audio.set_muted(False, "music")
        report["buses"] = {"music_muted": muted, "unmuted": run.state(), "same_player": run.track().player is playing}
        run.audio.set_music_volume(1.0)
    finally:
        game.window.close()
        report["after_close"] = {"registered_players": _registered(),
                                 "live": game.window.audio.diagnostics()["live_players"],
                                 "released_players": game.window.audio.released_players}
        os.chdir(game._cwd)
    return report


def studio(project_root: Path, out: Path) -> dict[str, Any]:
    sys.path.insert(0, str(REPO / "tooling"))
    from hd2d_studio_demo import StudioDriver

    d = StudioDriver(project_root)
    k = d.arcade.key
    audio = d.window.audio
    report: dict[str, Any] = {"master_volume": audio.master_volume,
                              "editing": {"music": audio.music_path, "registered_players": _registered()}}
    cycles = []
    try:
        for _ in range(10):
            d.key(k.F4)
            for _f in range(30):
                d.frame()
                time.sleep(1 / 60)
            track = audio._music_track
            playing = {"mode": d.studio.mode, "music": audio.music_path, "registered_players": _registered(),
                       "player_playing": bool(track.player.playing) if track else False}
            d.key(k.F4)
            d.frame(5)
            cycles.append({"play": playing, "stop": {"mode": d.studio.mode, "music": audio.music_path,
                                                     "registered_players": _registered()}})
        d.studio._reload()  # an edit's reload in the editor: still silent
        report["edit_reload"] = {"music": audio.music_path, "registered_players": _registered()}
    finally:
        d.close()
    report["play_stop"] = cycles
    report["released_players"] = audio.released_players
    report["after_close"] = {"registered_players": _registered()}
    return report


def export(out: Path) -> dict[str, Any]:
    project, bundle = out / "project", out / "export"
    if bundle.exists():
        shutil.rmtree(bundle)
    built = subprocess.run([sys.executable, "-m", "mesh_cli", "export", "build", "--out", str(bundle)], cwd=project,
                           capture_output=True, text=True, timeout=900, env={**os.environ, "PYTHONPATH": str(REPO)})
    report: dict[str, Any] = {"export_code": built.returncode, "export_tail": (built.stdout + built.stderr)[-300:],
                              "music_in_bundle": [t for t in (DUNGEON, FOREST, TOWN) if (bundle / t).is_file()]}
    code = f"""
import json, sys, time
sys.path.insert(0, {str(bundle)!r})
import engine
sys.path.insert(1, {str(REPO / "tooling")!r})
from hd2d_demo import HiddenGame
from pathlib import Path
from pyglet import media
game = HiddenGame(Path({str(bundle)!r}))
row = {{"engine_from": engine.__file__, "master_volume": game.window.audio.master_volume}}
try:
    game.window.load_scene(game.window.engine_config.start_scene or "packs/core_regions/scenes/start.json")
    end = time.perf_counter() + 1.5
    while time.perf_counter() < end:
        game.window.dispatch_event("on_update", 1 / 60)
        time.sleep(1 / 60)
    track = game.window.audio._music_track
    row.update(music=game.window.audio.music_path, registered=len(media.Source._players),
               playing=bool(track and track.player.playing), time=round(float(track.player.time), 2) if track else None)
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


def listen(project: Path, out: Path) -> dict[str, Any]:
    """The owner's listening pass: the transitions and sounds M21A makes, through the speakers, each step captioned
    in the terminal. Only ever run by a person, on purpose: the master volume is 0.7 (not the project's 0)."""
    sys.path.insert(0, str(REPO / "tooling"))
    from hd2d_demo import HiddenGame

    game = HiddenGame(project)
    run = _Run(game)
    run.audio.set_master_volume(0.7)
    steps: list[str] = []

    def say(text: str, seconds: float) -> None:
        steps.append(text)
        print(f"[{len(steps):2d}] {text}", flush=True)
        run.play(seconds)

    try:
        run.enter("dungeon")
        say("Dungeon theme (Mesh's synthesised loop) starts at once. Listen for its loop seam every 4 s.", 9.0)
        run.enter("no_setting")
        say("A room with no music setting: the dungeon theme should carry on with no gap or restart.", 4.0)
        run.enter("forest")
        say("Crossfade (1 s) to the forest theme: both overlap; no dip to silence, no jump in loudness.", 6.0)
        if (project / TOWN).is_file():
            run.enter("town")
            say("Crossfade to Town Theme (CC0 MP3, cynicmusic): smooth, at a similar loudness?", 10.0)
            track = run.track()
            track.player.seek(track.player.source.duration - 4.0)
            say("Town Theme's loop seam: its last 4 s, then back to its start. Any click or gap?", 8.0)
        if (project / WOODS).is_file():
            run.audio.play_loop("woods", WOODS, volume=0.8, fade_in_s=2.0)
            say("Forest ambience (CC0, TinyWorlds) fades in under the music on the ambience bus.", 8.0)
            run.audio.set_ambience_volume(0.3)
            say("Ambience bus turned down to 0.3: only the ambience gets quieter; the music stays.", 5.0)
        for sound in ("footstep", "hit", "ui_click", "attack"):
            run.audio.play_sound(f"assets/sounds/{sound}.wav")
            run.play(0.5)
        say("Four sound effects (footstep, hit, click, attack) over the music: too loud or too quiet beside it?", 2.0)
        run.audio.set_music_volume(0.3)
        say("Music bus turned down to 0.3: the music drops at once, without restarting.", 4.0)
        run.audio.set_music_volume(1.0)
        run.audio.stop_loop("woods", fade_out_s=1.5)
        run.enter("silence")
        say("A silent room: the music fades out over 1 s and stops. Nothing should be left playing.", 4.0)
    finally:
        game.window.close()
        os.chdir(game._cwd)
    return {"steps": steps}


def main() -> None:
    phase, out = sys.argv[1], Path(sys.argv[2]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    project = out / "project"
    report = {"setup": lambda: setup(out, "--audible" in sys.argv), "game": lambda: game_checks(project, out),
              "studio": lambda: studio(project, out), "export": lambda: export(out),
              "listen": lambda: listen(project, out)}[phase]()
    (out / f"{phase}.json").write_text(json.dumps(report, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=1, default=str))


if __name__ == "__main__":
    main()
