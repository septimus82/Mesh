"""Milestone 16 Stage 6B: the HD-2D RPG template from a clean pip-installed Mesh, outside the repository.

    py -3.13 tooling/hd2d_install_acceptance.py OUT

1. builds the wheel (``pip wheel .``) and checks it carries exactly pyproject.toml's bundled-file allow-list;
2. creates two fresh virtual environments in OUT: ``mesh_venv`` with the wheel installed as a person installs it
   (its dependencies from the package index), and ``player_venv`` with only Mesh's dependencies (to run an exported
   game without Mesh);
3. copies the hidden-window harness and tooling/hd2d_install_driver.py to OUT/tooling (they import only ``engine``,
   which can then only be the installed one) and runs the driver there with mesh_venv's Python in isolated mode, from
   OUT/work, with every repository and Mesh variable removed from the environment and Mesh's user and projects
   folders pointed into OUT (the owner's own are never touched);
4. checks the driver's report (OUT/acceptance.json) and prints a summary.

Hidden windows only. OUT must be a new or empty folder; everything is written inside it.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
HARNESS = ("hd2d_demo.py", "hd2d_floors_demo.py", "hd2d_studio_demo.py", "hd2d_starter_demo.py", "hd2d_visual_study.py",
           "hd2d_install_driver.py")
TEST_MODEL = REPO / "tooling" / "hd2d_assets" / "cottage_v2.glb"  # the workflow imports one model through Studio


def _python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _pip(python: Path, *args: str) -> None:
    subprocess.check_call([str(python), "-m", "pip", "install", "-q", "--disable-pip-version-check", *args])


def _allow_list() -> list[str]:
    data_files = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["setuptools"]["data-files"]
    return sorted(src for sources in data_files.values() for src in sources)


def _clean_env(out: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("MESH_") and k not in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PYTHONSTARTUP")}
    env.update({"MESH_USER_DIR": str(out / "user"), "MESH_PROJECTS_DIR": str(out / "projects"),
                "MESH_STUDIO_NO_AI_BRIDGE": "1"})
    return env


def run(out: Path) -> dict[str, Any]:
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty: give a new folder")
    out.mkdir(parents=True, exist_ok=True)
    for sub in ("work", "user", "projects"):
        (out / sub).mkdir()

    # 1. the wheel
    wheelhouse = out / "wheelhouse"
    subprocess.check_call([sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "-q", "-w", str(wheelhouse)], cwd=str(REPO))
    wheel = next(wheelhouse.glob("*.whl"))
    with zipfile.ZipFile(wheel) as zf:
        names = [n.replace("\\", "/") for n in zf.namelist()]
        requires = [line.split(":", 1)[1].strip() for line in
                    zf.read(next(n for n in names if n.endswith(".dist-info/METADATA"))).decode().splitlines()
                    if line.startswith("Requires-Dist:") and "extra ==" not in line]
    bundled = sorted(n.split("/data/share/mesh-engine/", 1)[1] for n in names if "/data/share/mesh-engine/" in n)
    report: dict[str, Any] = {"wheel": wheel.name, "wheel_bytes": wheel.stat().st_size, "bundled_files": len(bundled),
                              "bundled_is_allow_list": bundled == _allow_list(), "requires": requires}

    # 2. the two environments
    mesh_venv, player_venv = out / "mesh_venv", out / "player_venv"
    for venv in (mesh_venv, player_venv):
        subprocess.check_call([sys.executable, "-m", "venv", str(venv)])
    _pip(_python(mesh_venv), str(wheel))
    _pip(_python(player_venv), *requires)
    freeze = subprocess.check_output([str(_python(mesh_venv)), "-m", "pip", "freeze"], text=True).split()
    report["installed"] = sorted(f for f in freeze if f.split("==")[0].lower() in ("mesh-engine", "arcade", "pyglet", "pillow", "jsonschema"))

    # 3. the harness, away from the repository (it finds its sibling modules and its import test model relative to
    # its own folder, which holds no engine), and the driver in the installed environment
    tooling = out / "tooling"
    (tooling / "hd2d_assets").mkdir(parents=True)
    for name in HARNESS:
        shutil.copyfile(REPO / "tooling" / name, tooling / name)
    shutil.copyfile(TEST_MODEL, tooling / "hd2d_assets" / TEST_MODEL.name)
    driver = subprocess.run([str(_python(mesh_venv)), "-I", str(tooling / "hd2d_install_driver.py"), str(out), str(REPO),
                             str(_python(player_venv))], cwd=str(out / "work"), env=_clean_env(out),
                            capture_output=True, text=True, timeout=3600)
    (out / "driver.log").write_text(driver.stdout + "\n--- stderr ---\n" + driver.stderr, encoding="utf-8")
    report["driver_exit"] = driver.returncode
    if driver.returncode == 0:
        report["acceptance"] = json.loads((out / "acceptance.json").read_text(encoding="utf-8"))
    (out / "install_report.json").write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", type=Path)
    report = run(parser.parse_args().out)
    print(json.dumps({k: v for k, v in report.items() if k != "acceptance"}, indent=2))
    print("driver exit:", report["driver_exit"])


if __name__ == "__main__":
    main()
