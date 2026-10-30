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
* the installed ``mesh`` command creates a project (``mesh new``) and diagnoses it without errors (``mesh doctor``).

A checkout that still has a file the wheel lost can't hide the loss: the checkout is never on the path, never the
working directory and never named in the environment. tests/test_wheel_bundles_engine_data.py runs this check and
proves it fails on broken wheels; CI's ``installed (<os>, py3.11)`` jobs run that test.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
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
    report["wheel"], report["problems"] = wheel.name, found
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print("\n".join([f"installed-product check of {wheel.name}: {'OK' if not found else 'FAILED'}", *found]))
    return 0 if not found else 1


if __name__ == "__main__":
    sys.exit(main())
