"""Milestone 23D evidence: the starting room and room music, authored in Mesh Studio (hidden windows; Studio's own
input events; silent: every project's master volume is 0, and the editor plays nothing).

    py -3.13 tooling/m23d_start_music_studio.py creator OUT   # Village as the start room; Track A, carry on,
                                                              # silence; save, reopen; start room undo/redo/reopen
    py -3.13 tooling/m23d_start_music_studio.py game OUT      # (after creator) a new game: where it starts, the
                                                              # music through the doors Village -> Woodland -> Ruins
                                                              # -> Village, from the audio manager's own state
    py -3.13 tooling/m23d_start_music_studio.py crossfade OUT # (after creator) the same with the project's crossfade on
    py -3.13 tooling/m23d_start_music_studio.py saves OUT     # (after creator) a save made in Woodland still loads
                                                              # there after the start room changes in Studio
    py -3.13 tooling/m23d_start_music_studio.py export OUT    # (after creator) the exported game on its own engine
    py -3.13 tooling/m23d_start_music_studio.py older OUT     # an older world naming no start room, a room storing
                                                              # "music": null: opened, edited, saved: kept

The project is disposable (OUT/m23d): Mesh's starter template ("Start", 2D) and three rooms added with Studio's own
project operations: Village (2D), Woodland (HD-2D) and Ruins (2D), joined by walk-in doors Village-Woodland,
Woodland-Ruins and Ruins-Village. Track A is Mesh's own assets/music/forest_theme.wav, imported through Studio's
Import music file... (the file dialog's answer given, as no dialog can be driven in a hidden window).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))
import engine.optional_arcade  # noqa: E402,F401,I001  # (first: DPI-unaware before anything loads pyglet)
from hd2d_demo import HiddenGame  # noqa: E402

WORLD = "packs/core_regions/worlds/main.json"
TRACK_A = REPO / "assets" / "music" / "forest_theme.wav"
TRACK_A_REL = "assets/music/forest_theme.wav"
ROOMS = ("village", "woodland", "ruins")
LINKS = (("village", "woodland"), ("woodland", "ruins"), ("ruins", "village"))


def _silent(project: Path, **config: Any) -> None:
    path = project / "config.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update({"master_volume": 0.0, **config})  # (the backend plays; nothing reaches the speakers)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def make_project(out: Path) -> Path:
    """Mesh's starter template and Village, Woodland (HD-2D) and Ruins, doors between them: Studio's own project
    operations (the setup; every start room and music choice is made in Studio afterwards)."""
    from engine.studio_project import Project

    project = out / "m23d"
    if project.exists():
        shutil.rmtree(project)
    made = subprocess.run([sys.executable, "-m", "mesh_cli", "new", "m23d", "--dest", str(out), "--template", "starter"],
                          cwd=REPO, capture_output=True, text=True, timeout=600)
    assert made.returncode == 0, made.stdout + made.stderr
    _silent(project)
    studio_project = Project(project, WORLD)
    keys = {"village": studio_project.add_room("Village"),
            "woodland": studio_project.add_hd2d_room("Woodland", 24, 18)[0],
            "ruins": studio_project.add_room("Ruins")}
    assert list(keys.values()) == list(ROOMS), keys
    offsets: dict[str, int] = {}

    def door_at(key: str) -> tuple[float, float]:
        player = next(e for e in studio_project.scene(key).get("entities", []) if e.get("tag") == "player")
        k = offsets[key] = offsets.get(key, 0) + 1
        return float(player["x"]) + (128.0 if k == 1 else -128.0), float(player["y"]) + 64.0

    for a, b in LINKS:
        studio_project.link_rooms(a, door_at(a), b, door_at(b))
    studio_project.save()
    return project


def _rooms_of(project: Path) -> dict[str, Any]:
    """As saved: the world's start room, and each room's settings.music (``"(none)"``: no music setting)."""
    world = json.loads((project / WORLD).read_text(encoding="utf-8"))
    out: dict[str, Any] = {"start_scene": world.get("start_scene", "(none)")}
    for key in ROOMS:
        room = json.loads((project / world["scenes"][key]["path"]).read_text(encoding="utf-8"))
        settings = room.get("settings") or {}
        out[key] = settings["music"] if "music" in settings else "(none)"
    return out


def _audio(window: Any) -> dict[str, Any]:
    """The audio manager's own state: the track playing (its path, its object and its player, and how far it has
    played), what is fading out, live and released players, the master volume."""
    audio = window.audio
    track = getattr(audio, "_music_track", None)
    player = getattr(track, "player", None)
    diag = audio.diagnostics()
    return {"music": diag["music"], "fading_out": diag["fading_out"], "live_players": diag["live_players"],
            "released_players": diag["released_players"], "master": diag["volumes"]["master"],
            "track_id": id(track) if track is not None else None, "player_id": id(player) if player is not None else None,
            "played_s": round(float(getattr(player, "time", 0.0) or 0.0), 3), "scene_music": audio.scene_music}


def _studio(project: Path) -> Any:
    from hd2d_studio_demo import StudioDriver

    return StudioDriver(project)


def _room(d: Any, key: str) -> None:
    if d.studio.project.current != key:
        d.studio.set_left_tab("rooms")
        d.frame()
        d.button(d.studio.project.label(key))
        d.frame(2)


def _music(d: Any) -> None:
    if d.studio.panel != "music":
        d.studio.set_left_tab("audio")
        d.frame()
        d.button("Room music...")
        d.frame()


def _picture(d: Any, path: Path) -> None:
    d.window.dispatch_event("on_mouse_motion", d.window.width // 3, d.window.height // 2, 0, 0)
    d.frame(2)
    d.picture(path)


def _start_rows(d: Any) -> list[str]:
    return [t for t in d.labels() if t.startswith(("New games start in", "A new game starts", "This world names"))]


# ---------------------------------------------------------------------- phases
def creator(out: Path) -> dict[str, Any]:
    import engine.studio_sound as studio_sound

    out.mkdir(parents=True, exist_ok=True)
    project = make_project(out)
    pics = out / "pictures"
    pics.mkdir(exist_ok=True)
    report: dict[str, Any] = {"made": _rooms_of(project)}
    asked = studio_sound.ask_path
    setattr(studio_sound, "ask_path", lambda **_kw: str(TRACK_A))  # noqa: B010  # (the file dialog's answer)
    try:
        d = _studio(project)
        try:
            k = d.arcade.key
            report["opened_in"] = d.studio.project.current
            d.studio.set_left_tab("rooms")
            d.frame()
            report["before"] = {"start_rows": _start_rows(d), "audio": _audio(d.window)}
            _room(d, "village")
            report["village_offered"] = d.has_button("Set as starting room")
            d.button("Set as starting room")
            report["set_village"] = {"start": d.studio.project.start_key(), "editing": d.studio.project.current,
                                     "dirty": d.studio.project.world_dirty, "rows": _start_rows(d),
                                     "message": d.studio.message}
            _picture(d, pics / "d01_rooms_village_start.png")
            # 1. Village plays Track A (imported through Studio)
            _music(d)
            _picture(d, pics / "d02_music_panel_village_before.png")
            d.button("Play a track")
            report["picker"] = {"panel": d.studio.panel, "has_import": d.has_button("Import music file...")}
            d.button("Import music file...")
            report["village_music"] = {"panel_after": d.studio.panel, "room": _room_music(d),
                                       "imported_file": (project / TRACK_A_REL).is_file(), "message": d.studio.message}
            _picture(d, pics / "d03_music_village_track_a.png")
            # 2. Woodland carries on (first made silent, then Continue: the key taken away again)
            _room(d, "woodland")
            _music(d)
            d.button("Silence")
            silent_first = _room_music(d)
            d.button("Continue previous music")
            report["woodland_music"] = {"after_silence": silent_first, "after_continue": _room_music(d)}
            _picture(d, pics / "d04_music_woodland_continue.png")
            # 3. Ruins is silent
            _room(d, "ruins")
            _music(d)
            d.button("Silence")
            report["ruins_music"] = _room_music(d)
            _picture(d, pics / "d05_music_ruins_silence.png")
            report["editing_audio"] = _audio(d.window)  # (the editor: nothing plays)
            # Play (F4) tests the room being edited; Stop: silent again
            d.key(k.F4)
            d.frame(30)
            report["play_ruins"] = {"mode": d.studio.mode, "room": d.window.scene_controller.current_scene_path,
                                    "audio": _audio(d.window)}
            d.key(k.F4)
            d.frame(5)
            report["after_stop_audio"] = _audio(d.window)
            # 4. save, close
            d.key(k.S, k.MOD_CTRL)
            report["saved_message"] = d.studio.message
        finally:
            d.close()
        report["saved"] = _rooms_of(project)
        # 5. reopen: the three states, as Studio shows them
        d = _studio(project)
        try:
            k = d.arcade.key
            report["reopened"] = {"opened_in": d.studio.project.current,
                                  "rooms": {key: ops_music(d, key) for key in ROOMS},
                                  "unsaved": d.studio.project.is_dirty}
            _music(d)
            report["reopened"]["every_room"] = [t for t in d.labels() if t.split(":")[0].replace(" (start)", "")
                                                in ("Village", "Woodland", "Ruins", "Start")]
            _picture(d, pics / "d06_reopened_every_room.png")
            # Play (F4) in Village: Studio's play-test plays its track, as the game does; Stop: silent again
            _room(d, "village")
            d.key(k.F4)
            d.frame(30)
            report["play_village"] = {"mode": d.studio.mode, "room": d.window.scene_controller.current_scene_path,
                                      "audio": _audio(d.window)}
            d.key(k.F4)
            d.frame(5)
            report["play_village"]["after_stop"] = _audio(d.window)
            # 6. Woodland as the start room: undo, redo, save, reopen
            _room(d, "woodland")
            d.studio.set_left_tab("rooms")
            d.frame()
            d.button("Set as starting room")
            steps = {"set": (d.studio.project.start_key(), d.studio.project.current)}
            d.key(k.Z, k.MOD_CTRL)
            steps["undo"] = (d.studio.project.start_key(), d.studio.project.current)
            d.key(k.Y, k.MOD_CTRL)
            steps["redo"] = (d.studio.project.start_key(), d.studio.project.current)
            d.key(k.S, k.MOD_CTRL)
            steps["saved"] = _rooms_of(project)["start_scene"]
            d.key(k.Z, k.MOD_CTRL)  # (undo after Save: the world is to save again)
            steps["undo_after_save"] = (d.studio.project.start_key(), d.studio.project.world_dirty)
            d.key(k.Y, k.MOD_CTRL)
            d.key(k.S, k.MOD_CTRL)
            steps["saved_again"] = _rooms_of(project)["start_scene"]
            report["woodland_start"] = steps
            _picture(d, pics / "d07_rooms_woodland_start.png")
        finally:
            d.close()
        d = _studio(project)
        try:
            report["reopened_woodland"] = {"start": d.studio.project.start_key(), "opened_in": d.studio.project.current}
            # 7. Village again
            _room(d, "village")
            d.studio.set_left_tab("rooms")
            d.frame()
            d.button("Set as starting room")
            d.key(d.arcade.key.S, d.arcade.key.MOD_CTRL)
            report["restored_village"] = {"start": d.studio.project.start_key(), "rows": _start_rows(d)}
        finally:
            d.close()
    finally:
        setattr(studio_sound, "ask_path", asked)  # noqa: B010
    report["final"] = _rooms_of(project)
    return report


def _room_music(d: Any) -> dict[str, Any]:
    from engine import project_ops as ops

    return dict(ops.room_music(d.studio.project.scene()))


def ops_music(d: Any, key: str) -> dict[str, Any]:
    from engine import project_ops as ops

    return dict(ops.room_music(d.studio.project.scene(key)))


def _travel(game: HiddenGame, to: str, *, frames: int = 120) -> bool:
    """Through the walk-in door to room ``to``: the player stands on it, the game's own touch takes them through."""
    window = game.window
    door = next(s for s in window.scene_controller.all_sprites
                if ((getattr(s, "mesh_entity_data", None) or {}).get("behaviour_config") or {})
                .get("SceneTransition", {}).get("target_scene") == to)
    player = game.player()
    target = json.loads((Path.cwd() / WORLD).read_text(encoding="utf-8"))["scenes"][to]["path"]
    for _ in range(frames):
        if window.scene_controller.current_scene_path == target:
            return True
        player.center_x, player.center_y = door.center_x, door.center_y
        game.step(1)
    return bool(window.scene_controller.current_scene_path == target)


def _new_game(project: Path) -> tuple[HiddenGame, dict[str, Any]]:
    """A new game, started as ``main.py`` starts one: the world's start room (``resolve_game_start_scene``)."""
    from engine.game_runtime.scene_flow import resolve_game_start_scene

    game = HiddenGame(project, size=(960, 540))
    window = game.window
    start = resolve_game_start_scene(engine_config=window.engine_config, world_controller=window.world_controller)
    assert start is not None
    spawn = window.world_controller.get_start_spawn()
    if spawn:
        window.set_next_spawn_point(spawn)
    game.load(start)
    game.step(30)
    return game, {"start_path": start, "start_key": window.world_controller.get_start_scene_key()}


def _route(game: HiddenGame) -> dict[str, Any]:
    """Village -> Woodland -> Ruins -> Village through the doors, the music at each step from the audio manager."""
    out: dict[str, Any] = {"village": _audio(game.window)}
    game.step(60)
    out["village_1s_later"] = _audio(game.window)
    for room, name in (("woodland", "woodland"), ("ruins", "ruins"), ("village", "village_again")):
        out[f"{name}_arrived"] = _travel(game, room)
        out[name] = _audio(game.window)
        game.step(60)
        out[f"{name}_1s_later"] = _audio(game.window)
    return out


def game(out: Path) -> dict[str, Any]:
    project = out / "m23d"
    cwd = os.getcwd()
    try:
        game_, start = _new_game(project)
        try:
            return {**start, "room": game_.window.scene_controller.current_scene_path, "route": _route(game_)}
        finally:
            game_.close()
    finally:
        os.chdir(cwd)


def crossfade(out: Path) -> dict[str, Any]:
    """The same route in a copy of the project with its existing crossfade setting on (1 s out, 0.5 s in)."""
    source, project = out / "m23d", out / "m23d_crossfade"
    if project.exists():
        shutil.rmtree(project)
    shutil.copytree(source, project)
    _silent(project, music_crossfade_enabled=True, music_crossfade_out_s=1.0, music_crossfade_in_s=0.5)
    cwd = os.getcwd()
    try:
        game_, start = _new_game(project)
        try:
            route: dict[str, Any] = {"village": _audio(game_.window)}
            route["woodland_arrived"] = _travel(game_, "woodland")
            route["woodland"] = _audio(game_.window)
            route["ruins_arrived"] = _travel(game_, "ruins")
            route["ruins_at_once"] = _audio(game_.window)
            game_.step(30)
            route["ruins_0.5s"] = _audio(game_.window)
            game_.step(60)
            route["ruins_1.5s"] = _audio(game_.window)
            return {**start, "route": route}
        finally:
            game_.close()
    finally:
        os.chdir(cwd)


def saves(out: Path) -> dict[str, Any]:
    """A new game; through the door to Woodland; saved there (slot "m23d"). Then, in Studio, the start room set to
    Ruins and saved. A new game now starts in Ruins; the save still loads into Woodland, with Track A (Woodland has
    no music setting: the save's recorded music plays, docs/audio.md), and its file is untouched by Studio. Then the
    start room is set back to Village in Studio."""
    project = out / "m23d"
    cwd = os.getcwd()
    report: dict[str, Any] = {}
    try:
        game_, _start = _new_game(project)
        try:
            report["travelled"] = _travel(game_, "woodland")
            report["saved_in"] = game_.window.scene_controller.current_scene_path
            report["save_ok"] = game_.window.save_manager.save_game("m23d")
        finally:
            game_.close()
        os.chdir(cwd)
        slot = next((project / "saves").glob("m23d*"))
        before = slot.read_bytes()
        d = _studio(project)
        try:
            _room(d, "ruins")
            d.studio.set_left_tab("rooms")
            d.frame()
            d.button("Set as starting room")
            d.key(d.arcade.key.S, d.arcade.key.MOD_CTRL)
            report["studio_start"] = d.studio.project.start_key()
        finally:
            d.close()
        report["slot_untouched_by_studio"] = slot.read_bytes() == before
        game_, start = _new_game(project)
        try:
            report["new_game_starts_in"] = start["start_key"]
            report["new_game_room"] = game_.window.scene_controller.current_scene_path
            report["loaded"] = game_.window.save_manager.load_game("m23d")
            game_.step(30)
            # (a save loads its room from the slot: the slot records which room, and the room's own objects come back)
            report["slot_records"] = json.loads(slot.read_text(encoding="utf-8"))["meta"]["scene_path"]
            ids = sorted(str(getattr(s, "mesh_id", "") or "") for s in game_.window.scene_controller.all_sprites)
            report["loaded_room_objects"] = [i for i in ids if i]
            report["loaded_is_hd2d"] = getattr(game_.window, "hd2d_renderer", None) is not None  # (Woodland is HD-2D)
            report["save_music"] = _audio(game_.window)
        finally:
            game_.close()
        os.chdir(cwd)
        d = _studio(project)
        try:
            _room(d, "village")
            d.studio.set_left_tab("rooms")
            d.frame()
            d.button("Set as starting room")
            d.key(d.arcade.key.S, d.arcade.key.MOD_CTRL)
            report["start_back"] = d.studio.project.start_key()
        finally:
            d.close()
    finally:
        os.chdir(cwd)
    return report


def export(out: Path) -> dict[str, Any]:
    """``mesh export build`` of the project; the bundle run on its own engine in a hidden window: its new game's
    start room and the music route, as ``game``."""
    project, bundle = out / "m23d", out / "m23d_export"
    if bundle.exists():
        shutil.rmtree(bundle)
    built = subprocess.run([sys.executable, "-m", "mesh_cli", "export", "build", "--out", str(bundle)], cwd=project,
                           capture_output=True, text=True, timeout=900, env={**os.environ, "PYTHONPATH": str(REPO)})
    report: dict[str, Any] = {"export_code": built.returncode, "music_in_bundle": (bundle / TRACK_A_REL).is_file()}
    code = f"""
import json, os, sys
sys.path.insert(0, {str(bundle)!r})
import engine
import engine.optional_arcade
sys.path.insert(1, {str(REPO / "tooling")!r})
import m23d_start_music_studio as tool
from pathlib import Path
game, start = tool._new_game(Path({str(bundle)!r}))
try:
    row = {{"engine_in_bundle": str(Path(engine.__file__)).startswith({str(bundle)!r}), **start,
            "route": tool._route(game)}}
finally:
    game.close()
print("RESULT " + json.dumps(row, default=str))
"""
    ran = subprocess.run([sys.executable, "-c", code], cwd=bundle, capture_output=True, text=True, timeout=900,
                         env={k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "MESH_REPO_ROOT")})
    line = next((ln for ln in ran.stdout.splitlines() if ln.startswith("RESULT ")), None)
    report["bundle_run"] = json.loads(line[7:]) if line else {"failed": ran.stdout[-600:] + ran.stderr[-1500:]}
    return report


def older(out: Path) -> dict[str, Any]:
    """An older project: its world names no start room (``start_scene`` and the rooms' "start" tag taken away, as a
    hand-written world may have it: the game starts at its config's ``start_scene`` path, the template's Start) and
    Ruins stores ``"music": null`` while Woodland has no music setting. Opened in Studio (it says where
    a new game starts), Village given a track there, saved: the world still names no start room, Ruins is still
    null and Woodland still has no setting; reopened, the same."""
    out.mkdir(parents=True, exist_ok=True)
    project = make_project(out)
    world_path = project / WORLD
    world = json.loads(world_path.read_text(encoding="utf-8"))
    world.pop("start_scene", None)
    for scene in world["scenes"].values():  # (nor a room tagged "start": the game falls back to its config's scene)
        scene.pop("tags", None)
    world_path.write_text(json.dumps(world, indent=2) + "\n", encoding="utf-8")
    ruins = project / world["scenes"]["ruins"]["path"]
    room = json.loads(ruins.read_text(encoding="utf-8"))
    room.setdefault("settings", {})["music"] = None  # (as an older room has it, written by hand)
    ruins.write_text(json.dumps(room, indent=2) + "\n", encoding="utf-8")
    shutil.copyfile(TRACK_A, project / TRACK_A_REL)
    report: dict[str, Any] = {"before": _rooms_of(project)}
    d = _studio(project)
    try:
        d.studio.set_left_tab("rooms")
        d.frame()
        report["rows"] = _start_rows(d)
        report["opened_in"] = d.studio.project.current
        report["dirty_on_open"] = d.studio.project.is_dirty
        _room(d, "village")
        _music(d)
        d.button("Play a track")
        d.button(TRACK_A_REL.removeprefix("assets/"))
        d.key(d.arcade.key.S, d.arcade.key.MOD_CTRL)
        report["saved_message"] = d.studio.message
    finally:
        d.close()
    report["after"] = _rooms_of(project)
    d = _studio(project)
    try:
        report["reopened"] = {key: ops_music(d, key) for key in ROOMS}
        report["reopened_start"] = d.studio.project.start_key()
    finally:
        d.close()
    return report


PHASES: dict[str, Callable[[Path], dict[str, Any]]] = {
    "creator": creator, "game": game, "crossfade": crossfade, "saves": saves, "export": export, "older": older}


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("phase", choices=sorted(PHASES))
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    print(json.dumps(PHASES[args.phase](args.out), indent=1, default=str))


if __name__ == "__main__":
    main()
