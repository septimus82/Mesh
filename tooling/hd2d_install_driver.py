"""Milestone 16 Stage 6B: the installed-engine acceptance, the part that runs INSIDE a clean pip-installed Mesh.

tooling/hd2d_install_acceptance.py builds the wheel, installs it into a fresh virtual environment outside the
repository, copies this driver and the hidden-window harness (hd2d_demo, hd2d_floors_demo, hd2d_studio_demo,
hd2d_starter_demo) beside it, and runs it with that environment's Python in isolated mode (``-I``), from a folder with
no repository in sight. Nothing here may import from the repository; it checks that it doesn't.

    <venv python> -I hd2d_install_driver.py OUT REPO PLAYER_PYTHON

1. ``mesh new Village --template hd2d_rpg`` (the installed command);
2-9. tooling/hd2d_starter_demo.check on that project: open it in Mesh Studio, move the shop, turn a crate, place a
   person on the raised plateau in 3D, change a lamp, browse the starter kit and place a lamp post, an AI's sign, save,
   reopen (everything kept), play up the stairs, over and under the bridge, three conversations, the sign, into the
   cottage, quick save and load, stop;
10. ``mesh export build`` in the project, then the exported game started from the bundle by a Python that has
   Mesh's dependencies and not Mesh (PLAYER_PYTHON): the HD-2D village loads and the player walks.
Also the HD-2D visual standard and the cutaway measured in a fresh project (tooling/hd2d_visual_study.py's walk), a
2D project (``--template starter``) made, played and opened in Mesh Studio, and the template still developer-only.
Pictures and OUT/acceptance.json.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

OUT, REPO, PLAYER_PYTHON = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
HARNESS = Path(__file__).resolve().parent
sys.path.insert(0, str(HARNESS))

BUNDLE_PROBE = r'''
"""Start the exported game from its bundle (sys.argv[1]) in a hidden window, as its main.py does, and walk."""
import json, os, sys
from pathlib import Path
bundle, out = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(bundle))
os.chdir(bundle)
from engine.dpi_bootstrap import set_process_dpi_unaware
set_process_dpi_unaware()
import engine, engine.optional_arcade as optional_arcade
arcade = optional_arcade.arcade
original = arcade.Window.__init__
def hidden(window, *args, **kwargs):
    kwargs["visible"] = False
    original(window, *args, **kwargs)
arcade.Window.__init__ = hidden
from engine.config import load_config
from engine.game import GameWindow
from engine.game_runtime.scene_flow import resolve_game_start_scene
config = load_config()
window = GameWindow(width=1280, height=720, title="bundle", vsync=False, config=config, config_path="config.json")
window._allow_dispatch_event = True
start = config.main_menu_scene or resolve_game_start_scene(engine_config=config,
    world_controller=getattr(window, "world_controller", None)) or config.start_scene
window.load_scene(start)
for _ in range(90):
    window.dispatch_event("on_update", 1 / 60)
player = next(s for s in window.scene_controller.all_sprites if getattr(s, "mesh_tag", None) == "player")
before = (player.center_x, player.center_y)
window.dispatch_event("on_key_press", arcade.key.UP, 0)
for _ in range(45):
    window.dispatch_event("on_update", 1 / 60)
window.dispatch_event("on_key_release", arcade.key.UP, 0)
window.dispatch_event("on_update", 1 / 60)
window.dispatch_event("on_draw")
arcade.get_image(0, 0, *window.get_framebuffer_size()).convert("RGB").save(out / "20_exported_game.png")
result = {"engine": engine.__file__, "start": start, "hd2d": window.hd2d_renderer is not None,
          "hd2d_error": getattr(window, "hd2d_error", None), "walked_m": round((player.center_y - before[1]) / 32, 2)}
window.close()
print(json.dumps(result))
'''


def _run(args: list[str], cwd: Path, timeout: int = 900) -> dict[str, Any]:
    t = time.perf_counter()
    r = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
    return {"args": [Path(a).name if os.sep in a or "/" in a else a for a in args], "code": r.returncode,
            "seconds": round(time.perf_counter() - t, 1), "stdout": r.stdout[-3000:], "stderr": r.stderr[-3000:]}


def _within(path: str | Path, root: Path) -> bool:
    return Path(path).resolve().is_relative_to(root.resolve())


def two_d_project(mesh: Path, projects: Path, evidence: Path) -> dict[str, Any]:
    """A 2D starter project from the installed engine: played a little, and opened in Mesh Studio."""
    from hd2d_demo import HiddenGame
    from hd2d_studio_demo import StudioDriver

    made = _run([str(mesh), "new", "Pond", "--template", "starter", "--dest", str(projects)], OUT / "work")
    pond = projects / "Pond"
    config = json.loads((pond / "config.json").read_text(encoding="utf-8"))
    game = HiddenGame(pond, size=(1280, 720))
    try:
        game.load(config["start_scene"])
        game.step(60)
        player = game.player()
        y0 = player.center_y
        game.hold(game.arcade.key.UP, 30)
        game.draw().convert("RGB").save(evidence / "21_2d_starter_played.png")
        walked = round((player.center_y - y0) / 32, 2)
        hd2d = game.window.hd2d_renderer
    finally:
        game.close()
    d = StudioDriver(pond)
    try:
        d.frame(20)
        d.picture(evidence / "22_2d_starter_in_studio.png")
        studio_room = d.studio.project.current
        hd2d_in_studio = d.studio.hd2d.active
    finally:
        d.close()
    return {"new": made, "walked_up_m": walked, "hd2d_renderer": hd2d is not None, "studio_room": studio_room,
            "studio_hd2d": hd2d_in_studio}


def presentation(evidence: Path) -> dict[str, Any]:
    """The HD-2D visual standard and the cutaway, from the installed engine, in a fresh HD-2D project: the camera
    settings it wrote, no empty background, the player drawn at exactly 2x, and the player seen behind the cottage
    (cutaway) but still under the bridge deck (not cut)."""
    import hd2d_visual_study as study

    from engine.hd2d.settings import parse_hd2d

    project = study.new_project(OUT / "projects", "Presentation", stage6a=False)
    rooms = {name: json.loads((project / study.SCENES / f"{name}.json").read_text(encoding="utf-8"))
             for name in ("start", "cottage")}
    cameras = {name: room["settings"]["hd2d"]["camera"] for name, room in rooms.items()}
    sheets = sorted({e.get("sprite") for room in rooms.values() for e in room["entities"] if e.get("tag") == "npc"})
    cut = sorted(st.id for st in parse_hd2d(rooms["start"]["settings"]["hd2d"]).structures if st.cutaway)
    game = study.HiddenGame(project, size=study.SIZE)
    try:
        game.load(f"{study.SCENES}/start.json")
        game.step(90)
        walk = study.Walk(game, evidence, "installed")
        walk.go("UP", 1, 15.0)
        walk.shot("centre")
        walk.go("LEFT", 0, 13.5)
        walk.go("UP", 1, 14.8)
        walk.go("LEFT", 0, 10.0)
        walk.shot("behind_cottage")
        walk.go("RIGHT", 0, 20.0)
        walk.go("UP", 1, 24.0)
        walk.shot("under_bridge")
    finally:
        game.close()
    return {"cameras": cameras, "npc_sheets": sheets, "cutaway": cut,
            "sun": rooms["start"]["settings"]["hd2d"]["sun"]["direction"], "spots": walk.spots}


def main() -> int:
    import engine
    from engine.project_templates import list_templates

    venv = Path(sys.prefix)
    report: dict[str, Any] = {
        "engine": str(Path(engine.__file__).resolve()),
        "engine_from_venv": _within(engine.__file__, venv),
        "repo_on_sys_path": [p for p in sys.path if p and _within(p, REPO)],
        "repo_env": {k: v for k, v in os.environ.items() if k in ("MESH_REPO_ROOT", "PYTHONPATH")},
        "cwd_outside_repo": not _within(Path.cwd(), REPO),
        "hd2d_rpg_in_launcher": "hd2d_rpg" in [t.id for t in list_templates(launcher_only=True)],
    }
    assert report["engine_from_venv"] and not report["repo_on_sys_path"] and report["cwd_outside_repo"], report
    mesh = Path(sys.executable).parent / ("mesh.exe" if os.name == "nt" else "mesh")
    projects, evidence = OUT / "projects", OUT / "evidence"
    projects.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True, exist_ok=True)

    # 1. create with the installed command
    report["new"] = _run([str(mesh), "new", "Village", "--template", "hd2d_rpg", "--dest", str(projects)], OUT / "work")
    village = projects / "Village"

    # 2-9. Mesh Studio and the game, through window events only
    import hd2d_starter_demo

    report["workflow"] = hd2d_starter_demo.check(evidence, project=village)

    # 10. export a standalone game, and start it with Mesh's dependencies only
    report["export"] = _run([str(mesh), "export", "build"], village)
    bundle = village / "dist" / "bundle"
    probe = OUT / "probe" / "bundle_probe.py"
    probe.parent.mkdir(exist_ok=True)
    probe.write_text(BUNDLE_PROBE, encoding="utf-8")
    ran = _run([str(PLAYER_PYTHON), "-I", str(probe), str(bundle), str(evidence)], bundle)
    report["exported_game"] = {"run": ran, "result": json.loads(ran["stdout"].strip().splitlines()[-1]) if ran["code"] == 0
                               else None, "files": sum(1 for p in bundle.rglob("*") if p.is_file())}
    paths = json.loads((bundle / "bundle_manifest.json").read_text(encoding="utf-8"))
    report["exported_game"]["manifest_repo_root"] = paths.get("repo_root")

    report["presentation"] = presentation(evidence)
    report["two_d"] = two_d_project(mesh, projects, evidence)
    (OUT / "acceptance.json").write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
