"""Milestone 22A: an HD-2D room made in Mesh Studio, its game camera and its sun set there, checked in hidden windows.

    py -3.13 tooling/hd2d_room_studio.py studio OUT        a fresh 2D starter project: + New room > HD-2D (40 x 30 m,
                                                           outdoors) > Create (the starter kit comes in); Camera and
                                                           sun...: Wide, pitch 38, See it; Evening, sun from 260;
                                                           undo / redo; Save, reopen; Play: the game's camera and sun
                                                           are what was set; export, and the bundle's own engine
    py -3.13 tooling/hd2d_room_studio.py lakeside OUT LAKE  a copy of Lakeside Village (LAKE: only read): its camera
                                                           and sun changed in Studio, saved, reopened

Everything is done with Mesh Studio's own input events (clicks, typing), never by writing room files. The player's
settings file is OUT's own; nothing is played aloud (the projects' master volume is 0)."""

from __future__ import annotations

import json
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


def _write(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=1, default=str) + "\n", encoding="utf-8")


def _silent(project: Path) -> None:
    config = json.loads((project / "config.json").read_text(encoding="utf-8"))
    config["master_volume"] = 0.0
    _write(project / "config.json", config)


def _press(d: Any, text: str, where: Callable[[Any], bool] = lambda w: True) -> None:
    def find() -> Any:
        return next((w for w in d.studio.ui.walk_widgets() if getattr(w, "text", None) == text and where(w)), None)

    if not d._scroll_panels(find):  # the panel it is in, scrolled as a person would
        raise AssertionError(f"no button {text!r}")
    d.frame()
    r = find().rect
    d.click(r.left + r.width / 2, r.bottom + r.height / 2)


def _left(widget: Any) -> bool:
    return bool(widget.rect.left < 230)


def _right(widget: Any) -> bool:
    return bool(widget.rect.left > 900)


def _hd2d(d: Any) -> dict[str, Any]:
    settings = d.studio.project.scene().get("settings") or {}
    hd2d: dict[str, Any] = settings.get("hd2d") or {}
    return hd2d


def _renderer_state(window: Any) -> dict[str, Any]:
    r = window.hd2d_renderer
    s = r.settings
    return {"camera": {"pitch": s.camera.pitch, "fov": s.camera.fov, "distance": s.camera.distance,
                       "bounds": list(s.camera.bounds) if s.camera.bounds else None},
            "sun": [round(v, 4) for v in s.sun], "sun_intensity": s.sun_intensity, "ambient": s.ambient,
            "sky": [round(v, 3) for v in s.sky]}


def studio(out: Path, *, full: bool = True) -> dict[str, Any]:
    """``full``: also export it and check the HD-2D template (slower; the GPU test leaves those to this tool)."""
    from hd2d_studio_demo import StudioDriver

    from engine import project_ops as ops
    from engine.studio_hd2d import game_view

    pics = out / "pictures"
    pics.mkdir(exist_ok=True)
    project = out / "game"
    if project.exists():
        shutil.rmtree(project)
    made = subprocess.run([sys.executable, "-m", "mesh_cli", "new", "game", "--dest", str(out), "--template", "starter"],
                          cwd=REPO, capture_output=True, text=True, timeout=600)
    assert made.returncode == 0, made.stdout + made.stderr
    _silent(project)
    report: dict[str, Any] = {"kit_before": (project / "assets/hd2d_starter/textures/grass.png").is_file()}
    d = StudioDriver(project)
    try:
        _press(d, "+ New room", _left)
        d.type_into("room_name", "Meadow")
        _press(d, "HD-2D (3D)", _right)
        d.type_into("room_width", "40")
        d.type_into("room_depth", "30")
        _press(d, "Outdoors", _right)
        d.picture(pics / "01_new_room_panel.png")
        _press(d, "Create", _right)
        d.frame(10)
        report["created"] = {"room": d.studio.project.current, "hd2d_view": bool(d.studio.hd2d.active),
                             "message": d.studio.message, "ground_to": _hd2d(d).get("ground", {}).get("to"),
                             "kit_now": (project / "assets/hd2d_starter/textures/grass.png").is_file()}
        d.picture(pics / "02_new_hd2d_room.png")
        _press(d, "Camera and sun...", _left)
        report["panel"] = d.studio.panel
        _press(d, "Wide", _right)
        d.type_into("cam_pitch", "38")
        _press(d, "See it", _right)
        d.frame(3)
        d.picture(pics / "03_see_it_game_camera.png")
        report["see_it_editor_camera"] = {"pitch": d.studio.hd2d.camera.pitch, "fov": d.studio.hd2d.camera.fov,
                                          "distance": round(d.studio.hd2d.camera.distance, 3)}
        _press(d, "Evening", _right)
        d.type_into("sun_azimuth", "260")
        set_sun = ops.hd2d_sun_of(d.studio.project.scene())
        _press(d, "Undo")
        undone = ops.hd2d_sun_of(d.studio.project.scene())
        _press(d, "Redo")
        report["sun_set_undo_redo"] = [set_sun["azimuth"], undone["azimuth"], ops.hd2d_sun_of(d.studio.project.scene())["azimuth"]]
        report["camera"] = ops.hd2d_camera_of(d.studio.project.scene())
        report["sun"] = ops.hd2d_sun_of(d.studio.project.scene())
        report["view_renderer"] = _renderer_state(d.window)
        d.picture(pics / "04_evening_sun.png")
        _press(d, "Save")
        report["saved"] = d.studio.message
    finally:
        d.close()
    room = json.loads((project / SCENES / "meadow.json").read_text(encoding="utf-8"))
    report["in_the_saved_file"] = {"camera": room["settings"]["hd2d"]["camera"], "sun": room["settings"]["hd2d"]["sun"],
                                   "ambient": room["settings"]["hd2d"]["ambient"], "sky": room["settings"]["hd2d"].get("sky")}
    d = StudioDriver(project)
    try:
        _press(d, "Meadow", _left)
        report["reopened"] = {"same": _hd2d(d) == room["settings"]["hd2d"], "unsaved": sorted(d.studio.project.dirty)}
        k = d.arcade.key
        d.key(k.F4)
        for _ in range(30):
            d.frame()
            time.sleep(1 / 60)
        report["in_play"] = {"mode": d.studio.mode, **_renderer_state(d.window)}
        r = d.window.hd2d_renderer  # the follow camera, kept inside the room, against Studio's "See it" for this shape
        report["play_vs_see_it"] = {"aspect": round(r._aspect, 4), "play": [round(v, 4) for v in r.camera.target],
                                    "see_it": [round(v, 4) for v in game_view(d.studio.project.scene(), r._aspect).target]}
        d.picture(pics / "05_play.png")
        d.key(k.F4)
        d.frame(5)
    finally:
        d.close()
    if full:
        report["export"] = _export(project, out)
        report["template_untouched"] = _template_check(out)
    return report


def _export(project: Path, out: Path) -> dict[str, Any]:
    bundle = out / "export"
    if bundle.exists():
        shutil.rmtree(bundle)
    built = subprocess.run([sys.executable, "-m", "mesh_cli", "export", "build", "--out", str(bundle)], cwd=project,
                           capture_output=True, text=True, timeout=900, env={**os.environ, "PYTHONPATH": str(REPO)})
    code = f"""
import json, sys
sys.path.insert(0, {str(bundle)!r})
import engine
sys.path.insert(1, {str(REPO / "tooling")!r})
from hd2d_demo import HiddenGame
from pathlib import Path
game = HiddenGame(Path({str(bundle)!r}))
try:
    game.load("{SCENES}/meadow.json")
    game.step(10)
    s = game.window.hd2d_renderer.settings
    print(json.dumps({{"engine_from": engine.__file__, "pitch": s.camera.pitch, "fov": s.camera.fov,
                      "sun": [round(v, 4) for v in s.sun], "grass": Path({str(bundle)!r}, "assets/hd2d_starter/textures/grass.png").is_file()}}))
finally:
    game.window.close()
"""
    ran = subprocess.run([sys.executable, "-c", code], cwd=bundle, capture_output=True, text=True, timeout=900,
                         env={k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "MESH_REPO_ROOT")})
    try:
        run = json.loads(ran.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        run = {"failed": ran.stdout[-600:] + ran.stderr[-1500:]}
    return {"code": built.returncode, "bundle_run": run}


def _template_check(out: Path) -> dict[str, Any]:
    """The HD-2D template still makes the same village (its room files, byte for byte, as the template's own test
    expects them: two fresh projects compared)."""
    rooms = []
    for name in ("t1", "t2"):
        target = out / name
        if target.exists():
            shutil.rmtree(target)
        made = subprocess.run([sys.executable, "-m", "mesh_cli", "new", name, "--dest", str(out), "--template", "hd2d_rpg"],
                              cwd=REPO, capture_output=True, text=True, timeout=600)
        assert made.returncode == 0, made.stdout + made.stderr
        rooms.append({p.name: p.read_bytes() for p in sorted((target / SCENES).glob("*.json"))})
    return {"rooms": sorted(rooms[0]), "deterministic": rooms[0] == rooms[1]}


def lakeside(out: Path, original: str) -> dict[str, Any]:
    from hd2d_studio_demo import StudioDriver

    from engine import project_ops as ops

    project = out / "lake"
    if project.exists():
        shutil.rmtree(project)
    shutil.copytree(original, project, ignore=shutil.ignore_patterns("saves", "artifacts", ".mesh"))
    _silent(project)
    pics = out / "pictures"
    pics.mkdir(exist_ok=True)
    d = StudioDriver(project)
    report: dict[str, Any] = {}
    try:
        _press(d, "Lakeside", _left)
        report["before"] = {"camera": ops.hd2d_camera_of(d.studio.project.scene()), "sun": ops.hd2d_sun_of(d.studio.project.scene())}
        _press(d, "Camera and sun...", _left)
        d.type_into("cam_view", "14")
        _press(d, "Morning", _right)
        d.type_into("sun_elevation", "25")
        _press(d, "See it", _right)
        d.frame(3)
        d.picture(pics / "06_lakeside_morning_see_it.png")
        report["after"] = {"camera": ops.hd2d_camera_of(d.studio.project.scene()), "sun": ops.hd2d_sun_of(d.studio.project.scene())}
        _press(d, "Save")
    finally:
        d.close()
    d = StudioDriver(project)
    try:
        _press(d, "Lakeside", _left)
        report["reopened_same"] = {"camera": ops.hd2d_camera_of(d.studio.project.scene()) == report["after"]["camera"],
                                   "sun": ops.hd2d_sun_of(d.studio.project.scene()) == report["after"]["sun"]}
    finally:
        d.close()
    return report


def main() -> None:
    phase, out = sys.argv[1], Path(sys.argv[2]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ["MESH_RUNTIME_SETTINGS_PATH"] = str(out / "user_settings.json")  # never a checkout's own file
    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    report = {"studio": lambda: studio(out), "lakeside": lambda: lakeside(out, sys.argv[3])}[phase]()
    _write(out / f"{phase}.json", report)
    print(json.dumps(report, indent=1, default=str)[:5000])


if __name__ == "__main__":
    main()
