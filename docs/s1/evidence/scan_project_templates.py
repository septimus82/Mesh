"""S1-0 part D: every shipped project template, created with ``mesh new --template T`` and played headlessly.

    py -3.13 docs/s1/evidence/scan_project_templates.py        (PYTHONPATH = this checkout)

For each template in engine.project_templates: create it in a temp folder (mesh_cli main), note which gameplay data
files it ships (items.json, quests.json), run ``mesh doctor`` in it, then run its own main.py in a child process (one
at a time; GameWindow.run replaced by a script: hidden, muted, never-activated window; the game's own key input and
update loop): does the start room load, is there a player, does holding RIGHT move it, does a frame draw, which errors
are logged. Exits 1 when a template's start room has no walkable player or its start crashes. Temp folder removed.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]

DRIVER = r'''
import json, runpy, sys
from pathlib import Path
GAME, HIDDEN = Path(sys.argv[1]), sys.argv[2]
import importlib.util
spec = importlib.util.spec_from_file_location("hidden_windows", HIDDEN)
hw = importlib.util.module_from_spec(spec); spec.loader.exec_module(hw); hw.no_activate()
import engine.optional_arcade as optional_arcade
arcade = optional_arcade.arcade
_shown = arcade.Window.__init__
def _hidden(self, *a, **k):
    k["visible"] = False
    _shown(self, *a, **k)
arcade.Window.__init__ = _hidden
from engine.game import GameWindow
facts = {}
def drive(window):
    window._allow_dispatch_event = True
    window.audio.set_master_volume(0.0)
    sc = window.scene_controller
    def step(n):
        for _ in range(n):
            window.dispatch_event("on_update", 1 / 60)
    step(10)
    facts["scene"] = Path(str(sc.current_scene_path or "")).name
    facts["sprites"] = len(list(sc.all_sprites))
    hero = sc._find_player_sprite()
    facts["player"] = hero is not None
    facts["hd2d"] = window.hd2d_renderer is not None
    if hero is not None:
        x0, y0 = hero.center_x, hero.center_y
        for key in (arcade.key.RIGHT, arcade.key.LEFT, arcade.key.UP, arcade.key.DOWN):
            window.dispatch_event("on_key_press", key, 0); step(20)
            window.dispatch_event("on_key_release", key, 0); step(2)
            hero = sc._find_player_sprite()
            if abs(hero.center_x - x0) + abs(hero.center_y - y0) > 10:
                break
        facts["moved"] = round(abs(hero.center_x - x0) + abs(hero.center_y - y0), 1)
    window.dispatch_event("on_draw")
    facts["drew"] = True
    window.close()
GameWindow.run = drive
try:
    runpy.run_path(str(GAME / "main.py"), run_name="__main__")
except SystemExit:
    pass
print("MESH-TEMPLATE " + json.dumps(facts), flush=True)
'''


def main() -> int:
    sys.path.insert(0, str(REPO))
    os.chdir(REPO)
    import engine
    from engine.project_templates import list_templates
    from mesh_cli.main import main as mesh

    print("engine from", Path(engine.__file__).relative_to(REPO.parent).as_posix())
    tmp = Path(tempfile.mkdtemp(prefix="mesh_s1_templates_"))
    driver = tmp / "driver.py"
    driver.write_text(DRIVER, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith("MESH_")}
    env["MESH_RUNTIME_SETTINGS_PATH"] = str(tmp / "settings.json")
    defects = []
    try:
        for template in list_templates():
            quiet = io.StringIO()
            with contextlib.redirect_stdout(quiet), contextlib.redirect_stderr(quiet):
                code = mesh(["new", template.id, "--template", template.id, "--dest", str(tmp)])
            root = tmp / template.id
            data = {name: (root / "assets/data" / name).is_file() for name in ("items.json", "quests.json")}
            doctor = None
            if code == 0:
                cwd = Path.cwd()
                os.chdir(root)
                try:
                    with contextlib.redirect_stdout(quiet), contextlib.redirect_stderr(quiet):
                        doctor = mesh(["doctor"])
                finally:
                    os.chdir(cwd)
            proc = subprocess.run([sys.executable, str(driver), str(root), str(REPO / "tooling" / "hidden_windows.py")],
                                  cwd=str(tmp), env=env, capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=300) if code == 0 else None
            facts, errors = {}, []
            if proc is not None:
                line = next((x for x in reversed(proc.stdout.splitlines()) if x.startswith("MESH-TEMPLATE ")), None)
                facts = json.loads(line.split(" ", 1)[1]) if line else {"crashed": (proc.stdout + proc.stderr)[-600:]}
                errors = sorted({x.strip()[:150] for x in (proc.stdout + proc.stderr).splitlines()
                                 if ("ERROR" in x or "Traceback" in x or "WARNING" in x) and "MESH-TEMPLATE" not in x})
            ok = code == 0 and facts.get("player") and facts.get("moved", 0) > 10
            print(f"{template.id:20} launcher={template.launcher!s:5} new={code} doctor={doctor} data={data} "
                  f"play={facts}")
            for e in errors[:6]:
                print("      log:", e)
            if not ok:
                defects.append(template.id)
    finally:
        os.chdir(REPO)
        listing = sorted(p.name for p in tmp.iterdir())
        shutil.rmtree(tmp, ignore_errors=True)  # (the temp folder this script created)
        print("removed temp folder holding:", listing)
    if defects:
        print("DEFECT: templates whose start room has no walkable player or crashed:", defects)
        return 1
    print("every template starts with a walkable player")
    return 0


if __name__ == "__main__":
    sys.exit(main())
