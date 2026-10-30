"""Installed-product check (#422, H5): a Mesh wheel works as installed, with nothing taken from a checkout.

    python tooling/installed_product_check.py [--wheel WHEEL] [--out REPORT.json]

Builds the wheel from this checkout (or takes ``--wheel``), installs it with its declared dependencies into a fresh
virtual environment in a temporary folder, and runs the installed product from another temporary folder: Python
isolated (``-I``), with PYTHONPATH, PYTHONHOME and every MESH_* variable removed. It fails, naming each problem, unless

* every imported ``engine``/``mesh_cli`` module comes from that environment, no checkout path is importable and the
  development-only ``tooling`` package is absent;
* every bundled engine file (pyproject.toml's data-files allow-list) is installed under ``share/mesh-engine`` and the
  engine resolves it there;
* new projects (blank, HD-2D RPG) get everything they use from the installation;
* the installed ``mesh`` command creates a project (``mesh new``) and diagnoses it without errors (``mesh doctor``);
* (H7) a game made, checked and exported by the installed Mesh (``EXPORTS``: the 2D adventure and HD-2D RPG templates)
  runs as its player runs it: copied to another folder and started there (its main.py, in a hidden window) by a Python
  with Mesh's dependencies but not Mesh, it loads its start room from its own folder, walks the same distance twice at
  a fixed step, draws, logs no warning or error, closes, and leaves its folder as exported. An export needs those
  dependencies (arcade, pillow, jsonschema): it is not self-contained.

A checkout that still has a file the wheel lost can't hide the loss: the checkout is never on the path, never the
working directory and never named in the environment. The export and the exported game are also audited (``AUDIT``):
each file they open is classed as the installation, the project, the exported game, the player's environment or
elsewhere (a problem), and the checkout is off limits (touching it raises PermissionError and is a problem).
tests/test_wheel_bundles_engine_data.py runs this check and proves it fails on broken wheels and broken exports; CI's
``installed (<os>, py3.11)`` jobs run that test, with a display (Xvfb on Linux, Mesa's llvmpipe on Windows: the
exported games render in software, not on a GPU).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
MESH_PACKAGES = ("engine", "mesh_cli")
PROBE_TEMPLATES = ("blank", "hd2d_rpg")

PROBE = r'''
import json, logging, sys, traceback
from pathlib import Path
repo, work, allow_list = Path(sys.argv[1]).resolve(), Path(sys.argv[2]), json.loads(sys.argv[3])
facts = {"prefix": sys.prefix, "missing_assets": []}
class Catch(logging.Handler):
    def emit(self, record):
        message = record.getMessage()
        if "starter asset missing" in message or "config.json unreadable" in message:
            facts["missing_assets"].append(message)
logging.getLogger().addHandler(Catch())
try:
    import engine
    from engine.paths import resolve_engine_bundled_path
    from engine.project_scaffold import create_project
    from engine.hd2d import catalog
    facts["engine"] = engine.__file__
    share = Path(sys.prefix) / "share" / "mesh-engine"
    facts["bundled_missing"] = [f for f in allow_list if not (share / f).is_file()]
    resolved = {}
    for f in allow_list:
        try:
            resolved[f] = str(resolve_engine_bundled_path(f))
        except ValueError:
            continue  # not a path the engine resolves itself (a project copies it from the installation)
    facts["resolved_outside_share"] = sorted(f for f, p in resolved.items()
                                             if not Path(p).resolve().is_relative_to(share.resolve()))
    for template in sys.argv[4].split(","):
        target = work / template
        create_project(target, template.title(), template_id=template)
        facts[f"{template}_files"] = sorted(p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file())
    village = work / "hd2d_rpg"
    if village.is_dir():
        facts["hd2d_rpg_models"] = sorted(a.id for a in catalog.assets(village) if a.catalogued and not a.missing)
    blank_config = work / "blank" / "config.json"
    if blank_config.is_file():
        facts["blank_input_bindings"] = bool(json.loads(blank_config.read_text(encoding="utf-8")).get("input_bindings"))
    species = resolve_engine_bundled_path("assets/data/monster_species.json")
    facts["species_from"], facts["species_loads"] = str(species), bool(json.loads(species.read_text(encoding="utf-8")))
except BaseException:
    facts["error"] = traceback.format_exc(limit=4)
facts["modules_outside_prefix"] = sorted(
    name for name, module in list(sys.modules.items())
    if name.split(".")[0] in ("engine", "mesh_cli") and getattr(module, "__file__", None)
    and not Path(module.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()))
facts["checkout_on_path"] = sorted(p for p in sys.path if p and Path(p).resolve().is_relative_to(repo))
import importlib.util
facts["tooling_importable"] = importlib.util.find_spec("tooling") is not None
print("MESH-PROBE " + json.dumps(facts))
'''


# H7: the exported game and the export itself, watched. Prepended to the code a child Python runs: every file the child
# opens is counted by where it lies (the roots named in ROOTS, the child's environment, its base Python, the system's
# own places - the null device, the temp folder, /etc, /usr... - or elsewhere: a problem), and the checkout is off limits: opening or listing anything in it raises PermissionError and is recorded, so a file
# the export lost can't be found there. At exit, one MESH-AUDIT line reports it with the origin of every Mesh module.
AUDIT = r'''
import atexit, json, os, sys, tempfile
def _mesh_audit(checkout, roots):
    def norm(p):
        return os.path.normcase(os.path.realpath(p))
    def inside(p, root):
        return p == root or p.startswith(root.rstrip(os.sep) + os.sep)
    checkout = norm(checkout)
    named = sorted([(label, norm(path)) for label, path in roots.items()]
                   + [("environment", norm(sys.prefix)), ("python", norm(sys.base_prefix))]
                   + [("system", norm(p)) for p in (os.devnull, tempfile.gettempdir(),  # (ctypes' library lookups)
                                                   *(() if os.name == "nt" else ("/etc", "/proc", "/sys", "/dev", "/usr")))],
                   key=lambda r: -len(r[1]))
    def label(p):
        return next((name for name, root in named if inside(p, root)), "elsewhere")
    seen = {"read": {}, "written": {}, "denied": [], "elsewhere": []}
    def hook(event, args):
        if event == "open":
            mode, flags = (list(args[1:3]) + [None, None])[:2]
            paths = [(args[0], (isinstance(mode, str) and any(c in mode for c in "wax+"))
                      or bool((flags or 0) & (os.O_WRONLY | os.O_RDWR)))]
        elif event in ("os.listdir", "os.scandir"):
            paths = [(args[0] if args else ".", None)]
        elif event in ("shutil.copyfile", "shutil.copytree"):  # (a copy may bypass open(): CopyFile2 on Windows)
            paths = [(args[0], False), (args[1], True)]
        else:
            return
        for raw, writing in paths:
            if not isinstance(raw, (str, bytes, os.PathLike)):
                continue
            p = norm(os.fsdecode(raw))
            if inside(p, checkout):
                seen["denied"].append(p)
                raise PermissionError(f"the checkout is off limits here: {p}")
            if writing is None:
                continue
            where = label(p)
            kind = seen["written" if writing else "read"]
            kind[where] = kind.get(where, 0) + 1
            if where == "elsewhere" and p not in seen["elsewhere"] and len(seen["elsewhere"]) < 20:
                seen["elsewhere"].append(p)
    def report():
        modules = {}
        for name, module in list(sys.modules.items()):
            if name.split(".")[0] in ("engine", "mesh_cli") and getattr(module, "__file__", None):
                where = label(norm(module.__file__))
                modules[where] = modules.get(where, 0) + 1
        seen["modules"] = modules
        print("MESH-AUDIT " + json.dumps(seen), flush=True)
    atexit.register(report)
    sys.addaudithook(hook)
_mesh_audit(@CHECKOUT@, @ROOTS@)
del _mesh_audit
'''

# The exported game, started as a player starts it from another folder (`python <game>/main.py`: sys.path[0] is the
# game's folder, the working directory isn't) with two changes made from outside: the window is hidden, and the endless
# main loop is replaced by a bounded one at a fixed step: settle, walk right, draw and read the picture back, save, load
# the start room again and walk again (the same steps must give the same walk), load the save (back where it was).
GAME = r'''
import json, runpy, sys
from pathlib import Path
evidence, game = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(game))  # (as `python <game>/main.py` does: the script's folder first)
facts = {}
import engine.optional_arcade as optional_arcade
arcade = optional_arcade.arcade
shown = arcade.Window.__init__
def hidden(window, *args, **kwargs):
    kwargs["visible"] = False
    shown(window, *args, **kwargs)
arcade.Window.__init__ = hidden
from engine.game import GameWindow
def bounded(window):
    window._allow_dispatch_event = True  # (as inside pyglet's loop: events run now instead of waiting in its queue)
    scenes = window.scene_controller
    def steps(n):
        for _ in range(n):
            window.dispatch_event("on_update", 1 / 60)
    def player():
        hero = next(s for s in scenes.all_sprites if getattr(s, "mesh_tag", None) == "player")
        return [round(hero.center_x, 3), round(hero.center_y, 3)]
    def walk():
        steps(30)
        start = player()
        window.dispatch_event("on_key_press", arcade.key.RIGHT, 0)
        steps(30)
        window.dispatch_event("on_key_release", arcade.key.RIGHT, 0)
        steps(1)
        return start + player()
    facts["scene"] = getattr(scenes, "current_scene_path", None)
    facts["sprites"] = len(list(scenes.all_sprites))
    facts["hd2d"] = window.hd2d_renderer is not None
    facts["hd2d_error"] = getattr(window, "hd2d_error", None)
    facts["walk"] = walk()
    window.dispatch_event("on_draw")
    picture = arcade.get_image(0, 0, *window.get_framebuffer_size()).convert("RGB")
    picture.save(evidence / "frame.png")
    facts["colours"] = len(picture.getcolors(1 << 20) or [])
    facts["saved"] = window.save_manager.save_game("h7_check")  # (where the player stands now)
    facts["save_file"] = str(window.save_manager.get_save_path("h7_check").resolve())
    window.load_scene(facts["scene"])
    facts["walk_again"] = walk()
    facts["loaded"] = window.save_manager.load_game("h7_check")
    steps(2)
    facts["after_load"] = player()
    window.close()
    facts["closed"] = True
GameWindow.run = bounded
import engine, importlib.util
facts["engine"] = engine.__file__
facts["mesh_installed"] = importlib.util.find_spec("mesh_cli") is not None
runpy.run_path(str(game / "main.py"), run_name="__main__")
print("MESH-GAME " + json.dumps(facts), flush=True)
'''


def audited(code: str, repo: Path, roots: dict[str, Path]) -> str:
    """``code`` with ``AUDIT`` in front: the checkout ``repo`` off limits, files counted by the named ``roots``."""
    named = json.dumps({k: str(v) for k, v in roots.items()})
    return AUDIT.replace("@CHECKOUT@", repr(str(repo))).replace("@ROOTS@", named) + code


def _tagged(stdout: str, tag: str) -> dict[str, Any] | None:
    line = next((x for x in reversed(stdout.splitlines()) if x.startswith(tag + " ")), None)
    return None if line is None else dict(json.loads(line[len(tag) + 1:]))


def allow_list(repo: Path = REPO) -> list[str]:
    """The bundled engine files the wheel must carry: pyproject.toml's [tool.setuptools.data-files]."""
    data_files = tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["setuptools"]["data-files"]
    return sorted(src for sources in data_files.values() for src in sources)


def venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def venv_command(venv: Path, name: str) -> Path:
    return venv / ("Scripts" if os.name == "nt" else "bin") / (f"{name}.exe" if os.name == "nt" else name)


def build_wheel(dest: Path, repo: Path = REPO) -> Path:
    """The wheel of this checkout, built into ``dest``. The build/ and *.egg-info folders setuptools leaves in the
    checkout are removed again when this build made them."""
    before = {p.name for p in repo.iterdir()}
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "-q", "-w", str(dest)], cwd=str(repo))
    finally:
        for made in sorted(p for p in repo.iterdir() if p.name not in before):
            if made.is_dir() and (made.name == "build" or made.name.endswith(".egg-info")):
                shutil.rmtree(made)
    return next(dest.glob("*.whl"))


def make_venv(venv: Path) -> Path:
    subprocess.check_call([sys.executable, "-m", "venv", str(venv)])
    return venv_python(venv)


def install(venv: Path, wheel: Path, *, deps: bool = True) -> None:
    """Install ``wheel`` into ``venv``: with its declared dependencies, or (``deps=False``) replacing only Mesh."""
    extra = [] if deps else ["--no-deps", "--force-reinstall"]
    subprocess.check_call([str(venv_python(venv)), "-m", "pip", "install", "-q", "--disable-pip-version-check",
                           *extra, str(wheel)])


def clean_env(scratch: Path) -> dict[str, str]:
    """The environment the product runs in: no PYTHONPATH/PYTHONHOME, no MESH_* (e.g. MESH_REPO_ROOT); its own user,
    projects and settings folders."""
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME") and not k.startswith("MESH_")}
    env.update({"MESH_USER_DIR": str(scratch / "user"), "MESH_PROJECTS_DIR": str(scratch / "projects"),
                "MESH_RUNTIME_SETTINGS_PATH": str(scratch / "user" / "settings.json"), "PYTHONUTF8": "1"})
    return env


def run_probe(venv: Path, work: Path, *, repo: Path = REPO, leaky: bool = False) -> dict[str, Any]:
    """The installed product's own view of itself (``PROBE``), run isolated from ``work``. ``leaky`` runs it the way
    CI's old canary did (from the checkout, not isolated, the checkout on PYTHONPATH): only to prove the check sees it."""
    work.mkdir(parents=True, exist_ok=True)
    env = clean_env(work.parent)
    args = [str(venv_python(venv)), *([] if leaky else ["-I"]), "-c"]
    if leaky:
        env["PYTHONPATH"] = str(repo)
    proc = subprocess.run([*args, PROBE, str(repo), str(work), json.dumps(allow_list(repo)), ",".join(PROBE_TEMPLATES)],
                          cwd=str(repo if leaky else work), env=env, capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    line = next((x for x in reversed(proc.stdout.splitlines()) if x.startswith("MESH-PROBE ")), None)
    if line is None:
        return {"error": f"the probe printed no result (exit {proc.returncode}): {(proc.stderr or proc.stdout)[-1500:]}"}
    facts: dict[str, Any] = json.loads(line[len("MESH-PROBE "):])
    return facts


def run_cli(venv: Path, work: Path) -> dict[str, Any]:
    """The installed ``mesh`` command, from ``work``: ``mesh new`` then ``mesh doctor`` in the new project."""
    env = clean_env(work.parent)
    work.mkdir(parents=True, exist_ok=True)
    mesh = str(venv_command(venv, "mesh"))
    result: dict[str, Any] = {}
    for key, cmd, cwd in (("new", [mesh, "new", "cli_game", "--dest", str(work)], work),
                          ("doctor", [mesh, "doctor"], work / "cli_game"),
                          ("module_help", [str(venv_python(venv)), "-I", "-m", "mesh_cli", "--help"], work)):
        if not cwd.is_dir():
            result[key] = {"code": None, "output": f"not run: {cwd} does not exist"}
            continue
        proc = subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        result[key] = {"code": proc.returncode, "output": (proc.stdout + proc.stderr)[-1500:]}
    project = work / "cli_game"
    result["new_files"] = sorted(p.name for p in project.iterdir()) if project.is_dir() else []
    return result


def problems(probe: dict[str, Any], cli: dict[str, Any] | None) -> list[str]:
    """Everything wrong with the installed product, one line each (empty: it passes)."""
    found: list[str] = []
    if probe.get("error"):
        found.append(f"the installed engine failed: {probe['error'].strip().splitlines()[-1]}")
    for name in probe.get("modules_outside_prefix", []):
        found.append(f"{name} was imported from outside the installed environment")
    for path in probe.get("checkout_on_path", []):
        found.append(f"a checkout path is importable: {path}")
    if probe.get("tooling_importable"):
        found.append("the development-only tooling package is importable")
    found += [f"bundled file not installed: {f}" for f in probe.get("bundled_missing", [])]
    found += [f"bundled file resolved outside the installation: {f}" for f in probe.get("resolved_outside_share", [])]
    found += [f"a new project lacks a starter file: {m}" for m in probe.get("missing_assets", [])]
    if cli is not None:
        for key in ("new", "doctor", "module_help"):
            if cli[key]["code"] != 0:
                found.append(f"installed command failed ({key}, exit {cli[key]['code']}): "
                             f"{cli[key]['output'].strip().splitlines()[-1:] or ['no output']}")
        if cli["doctor"]["code"] == 0 and "errors=0" not in cli["doctor"]["output"]:
            found.append("mesh doctor reported errors in a new project")
        if not {"config.json", "main.py", "assets"} <= set(cli["new_files"]):
            found.append(f"mesh new made an incomplete project: {cli['new_files']}")
    return found


def requires(wheel: Path) -> list[str]:
    """The wheel's declared dependencies (Requires-Dist without extras): all an exported game runs on."""
    with zipfile.ZipFile(wheel) as zf:
        metadata = zf.read(next(n for n in zf.namelist() if n.endswith(".dist-info/METADATA"))).decode("utf-8")
    return [line.split(":", 1)[1].strip() for line in metadata.splitlines()
            if line.startswith("Requires-Dist:") and "extra ==" not in line]


def make_player_env(venv: Path, wheel: Path) -> None:
    """A player's environment: Mesh's dependencies, not Mesh (an export runs on them; it is not self-contained)."""
    make_venv(venv)
    subprocess.check_call([str(venv_python(venv)), "-m", "pip", "install", "-q", "--disable-pip-version-check",
                           *requires(wheel)])


def _run(cmd: list[str], cwd: Path, env: dict[str, str]) -> dict[str, Any]:
    proc = subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=900)
    return {"code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr,
            "audit": _tagged(proc.stdout, "MESH-AUDIT")}


CLI = "import runpy; runpy.run_module('mesh_cli', run_name='__main__', alter_sys=True)"


def export_game(venv: Path, work: Path, template: str, *, repo: Path = REPO) -> dict[str, Any]:
    """The installed ``mesh`` (``python -I -m mesh_cli``, audited) in ``work``: ``mesh new`` from ``template``,
    ``mesh doctor``, then ``mesh export build``. Returns each step's result and the bundle's folder."""
    work.mkdir(parents=True, exist_ok=True)
    env = clean_env(work)
    code = audited(CLI, repo, {"project": work, "user": work / "user"})
    project = work / template
    steps: dict[str, Any] = {}
    for key, args, cwd in (("new", ["new", template, "--template", template, "--dest", str(work)], work),
                           ("doctor", ["doctor"], project),
                           ("export", ["export", "build", "--deterministic"], project)):
        if not cwd.is_dir():
            steps[key] = {"code": None, "stdout": "", "stderr": f"not run: {cwd} does not exist", "audit": None}
            continue
        steps[key] = _run([str(venv_python(venv)), "-I", "-c", code, *args], cwd, env)
    return {"steps": steps, "bundle": project / "dist" / "bundle"}


def bundle_problems(bundle: Path) -> list[str]:
    """What's wrong with an exported game's folder against its own bundle_manifest.json (empty: it matches)."""
    manifest_path = bundle / "bundle_manifest.json"
    if not manifest_path.is_file():
        return ["the export has no bundle_manifest.json"]
    listed = {f["path"]: f["sha256"] for f in json.loads(manifest_path.read_text(encoding="utf-8"))["files"]}
    found: list[str] = []
    for name in ("main.py", "config.json", "engine/__init__.py"):
        if name not in listed:
            found.append(f"the export doesn't list {name}")
    for name, digest in sorted(listed.items()):
        path = bundle / name
        if not path.is_file():
            found.append(f"the export lacks a file its manifest lists: {name}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            found.append(f"an exported file differs from its manifest: {name}")
    on_disk = {p.relative_to(bundle).as_posix() for p in bundle.rglob("*") if p.is_file()
               and "__pycache__" not in p.parts  # (Python's bytecode, written as it runs)
               and p.relative_to(bundle).parts[0] != "saves"} - {"bundle_manifest.json"}  # (the game's own saves)
    found += [f"the export holds a file its manifest doesn't list: {name}" for name in sorted(on_disk - set(listed))]
    return found


def play(player: Path, bundle: Path, evidence: Path, *, repo: Path = REPO, leaky: bool = False) -> dict[str, Any]:
    """Run the exported game in ``bundle`` with the player's environment (``GAME``, audited), started from another
    folder, ``evidence`` (which gets its frame). ``leaky`` runs it the careless way (not isolated, the checkout on
    PYTHONPATH): only to prove that is seen."""
    evidence.mkdir(parents=True, exist_ok=True)
    env = clean_env(evidence)
    if leaky:
        env["PYTHONPATH"] = str(repo)
    code = audited(GAME, repo, {"game": bundle, "evidence": evidence, "user": evidence / "user"})
    result = _run([str(venv_python(player)), *([] if leaky else ["-I"]), "-c", code, str(evidence), str(bundle)],
                  evidence, env)
    result["game"] = _tagged(result["stdout"], "MESH-GAME")
    return result


def _audit_problems(step: str, audit: dict[str, Any] | None, home: str) -> list[str]:
    if audit is None:
        return [f"{step}: no audit report (the process died before exiting)"]
    found = [f"{step} tried to use the checkout: {p}" for p in audit["denied"][:5]]
    found += [f"{step} used a file outside the places it may: {p}" for p in audit["elsewhere"][:5]]
    found += [f"{step} ran {n} Mesh module(s) from {where}, not {home}"
              for where, n in audit["modules"].items() if where != home]
    return found


# The exported games checked, with the room each starts in and whether it renders in HD-2D.
EXPORTS = {"adventure": ("packs/core_regions/scenes/start.json", False),  # Mesh Studio's default 2D template
           "hd2d_rpg": ("packs/core_regions/scenes/start.json", True)}


def export_problems(export: dict[str, Any]) -> list[str]:
    """Everything wrong with making, checking and exporting a project with the installed ``mesh`` (empty: it passes)."""
    found: list[str] = []
    for key, step in export["steps"].items():
        if step["code"] != 0:
            tail = (step["stderr"] or step["stdout"]).strip().splitlines()[-1:] or ["no output"]
            found.append(f"mesh {key} failed (exit {step['code']}): {tail[0]}")
        elif key == "doctor" and "errors=0" not in step["stdout"]:
            found.append("mesh doctor reported errors in the new project")
        found += _audit_problems(f"mesh {key}", step["audit"], "environment")
    return found or bundle_problems(export["bundle"])


def game_problems(bundle: Path, run: dict[str, Any], *, start: str, hd2d: bool) -> list[str]:
    """Everything wrong with a run of the exported game in ``bundle`` (``play``), one line each (empty: it passes)."""
    game = run["game"]
    found = _audit_problems("the exported game", run["audit"], "game")
    if run["code"] != 0 or game is None:
        tail = run["stderr"].strip().splitlines()[-1:] or ["no output"]
        return [f"the exported game failed (exit {run['code']}): {tail[0]}", *found]
    if game["mesh_installed"]:
        found.append("Mesh is installed where the exported game ran: it must run without it")
    logged = sorted({line for line in run["stderr"].splitlines() if line.startswith(("WARNING:", "ERROR:", "CRITICAL:"))})
    found += [f"the exported game logged: {line[:300]}" for line in logged[:5]]
    if game["scene"] != start:
        found.append(f"the exported game started in {game['scene']!r}, not {start!r}")
    if game["hd2d"] != hd2d or game["hd2d_error"]:
        found.append(f"the exported game's HD-2D renderer: {game['hd2d']} (expected {hd2d}), error {game['hd2d_error']}")
    walk, again = game["walk"], game["walk_again"]
    if not walk[2] > walk[0]:
        found.append(f"the player didn't walk right in the exported game: {walk}")
    if [again[2] - again[0], again[3] - again[1]] != [walk[2] - walk[0], walk[3] - walk[1]]:
        found.append(f"the same steps walked differently: {walk} then {again}")
    if game["colours"] < 16:
        found.append(f"the exported game drew a near-blank frame ({game['colours']} colours)")
    if not (game["saved"] and game["loaded"]) or game["after_load"] != walk[2:]:
        found.append(f"the save didn't bring the player back to {walk[2:]}: saved {game['saved']}, loaded "
                     f"{game['loaded']}, at {game['after_load']}")
    if not game.get("closed"):
        found.append("the exported game didn't close its window")
    return found


def export_and_play(venv: Path, player: Path, scratch: Path, template: str) -> tuple[dict[str, Any], list[str]]:
    """``template`` made, checked and exported with the installed Mesh in ``scratch``/export, the export copied to
    ``scratch``/player/game and played there with the player's environment: (report, problems)."""
    export = export_game(venv, scratch / "export", template)
    found = export_problems(export)
    report: dict[str, Any] = {"export": export}
    if not found:
        game = scratch / "player" / "game"
        shutil.copytree(export["bundle"], game)
        report["play"] = run = play(player, game, scratch / "player" / "evidence")
        start, hd2d = EXPORTS[template]
        found = game_problems(game, run, start=start, hd2d=hd2d)
        found += [f"the game changed its own folder: {p}" for p in bundle_problems(game)]
    return report, found


def check(venv: Path, scratch: Path) -> tuple[dict[str, Any], list[str]]:
    """Run the probe and the CLI against ``venv`` in fresh folders under ``scratch``: (report, problems)."""
    probe = run_probe(venv, scratch / "probe_work")
    cli = run_cli(venv, scratch / "cli_work")
    return {"probe": probe, "cli": cli}, problems(probe, cli)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--wheel", type=Path, help="check this wheel instead of building one from the checkout")
    parser.add_argument("--out", type=Path, help="write the report (facts and problems) as JSON")
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="mesh-installed-") as tmp:
        scratch = Path(tmp)
        wheel = args.wheel.resolve() if args.wheel else build_wheel(scratch / "wheelhouse")
        venv = scratch / "venv"
        make_venv(venv)
        install(venv, wheel)
        report, found = check(venv, scratch)
        make_player_env(scratch / "player_env", wheel)
        for template in EXPORTS:
            report[f"export_{template}"], more = export_and_play(venv, scratch / "player_env", scratch / template, template)
            found += [f"{template}: {line}" for line in more]
    report["wheel"], report["problems"] = wheel.name, found
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=1, default=str) +"\n", encoding="utf-8")
    print("\n".join([f"installed-product check of {wheel.name}: {'OK' if not found else 'FAILED'}", *found]))
    return 0 if not found else 1


if __name__ == "__main__":
    sys.exit(main())
