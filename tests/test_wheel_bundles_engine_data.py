"""A pip-installed Mesh works out of the box: the wheel carries the engine's own bundled files (the allow-list in
pyproject.toml's [tool.setuptools.data-files], installed under <prefix>/share/mesh-engine), and only those.

This replaces the original test (2026-01), which expected the engine's packs/ to load from the wheel without a
project. Since 643970a (2026-06-30) project content resolves only inside the project, so a pip install needs what
new projects copy from the engine and the bundled monster data, not packs/ (docs/packaging.md).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
UNCONFIRMED_SPRITES = {"assets/sprites/animated_player.png", "assets/sprites/shelltide.png",
                       "assets/sprites/sproutling.png"}  # starter sprites whose licence is not confirmed: not bundled


def _allow_list() -> list[str]:
    data_files = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["setuptools"]["data-files"]
    return sorted(src for sources in data_files.values() for src in sources)


def _venv_python(venv_dir: Path) -> Path:
    return venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


PROBE = r'''
import json, logging, sys
from pathlib import Path
missing = []
class Catch(logging.Handler):
    def emit(self, record):
        if "starter asset missing" in record.getMessage() or "config.json unreadable" in record.getMessage():
            missing.append(record.getMessage())
logging.getLogger().addHandler(Catch())
from engine.paths import resolve_engine_bundled_path
from engine.project_scaffold import create_project
game = Path(sys.argv[1])
create_project(game, "Probe", template_id="blank")
species = resolve_engine_bundled_path("assets/data/monster_species.json")
print(json.dumps({
    "missing": missing,
    "files": sorted(p.relative_to(game).as_posix() for p in game.rglob("*") if p.is_file()),
    "input_bindings": bool(json.loads((game / "config.json").read_text(encoding="utf-8")).get("input_bindings")),
    "species_from": str(species), "species_loads": bool(json.loads(species.read_text(encoding="utf-8"))),
}))
'''


def test_the_wheel_bundles_the_engine_data_a_new_project_needs_and_nothing_else() -> None:
    allowed = _allow_list()
    assert allowed and not (set(allowed) & UNCONFIRMED_SPRITES)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        wheelhouse = tmp_path / "wheelhouse"
        subprocess.check_call([sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "-q", "-w", str(wheelhouse)],
                              cwd=str(REPO))
        wheel = next(wheelhouse.glob("*.whl"))
        with zipfile.ZipFile(wheel) as zf:
            names = [n.replace("\\", "/") for n in zf.namelist()]
        bundled = sorted(n.split("/data/share/mesh-engine/", 1)[1] for n in names if "/data/share/mesh-engine/" in n)
        assert bundled == allowed, "the wheel bundles exactly the allow-list"
        assert not any(n.startswith("packs/") or "/packs/" in n for n in names)

        venv = tmp_path / "venv"
        subprocess.check_call([sys.executable, "-m", "venv", str(venv)])
        subprocess.check_call([str(_venv_python(venv)), "-m", "pip", "install", "--no-deps", "-q", str(wheel)])
        # Creating a project needs Mesh's declared jsonschema and pillow, not the graphics stack (arcade).
        subprocess.check_call([str(_venv_python(venv)), "-m", "pip", "install", "-q", "jsonschema>=4,<5", "pillow>=10,<12"])
        work = tmp_path / "work"  # no repo markers here: the installed engine has only itself to go on
        work.mkdir()
        env = {k: v for k, v in os.environ.items() if k not in ("MESH_REPO_ROOT", "PYTHONPATH")}
        env.update({"MESH_USER_DIR": str(tmp_path / "user"), "MESH_PROJECTS_DIR": str(tmp_path / "projects")})
        out = subprocess.check_output([str(_venv_python(venv)), "-c", PROBE, str(work / "game")], cwd=str(work), env=env,
                                      text=True)
        result = json.loads(out.strip().splitlines()[-1])

    copied = {f for f in result["files"] if f.startswith("assets/")}
    assert {f for f in allowed if f.startswith("assets/")} <= copied, "a new project gets the bundled starter files"
    assert result["input_bindings"], "and the engine's default input bindings"
    assert all(any(s in m for s in UNCONFIRMED_SPRITES) for m in result["missing"]), result["missing"]
    assert "share" in result["species_from"] and "mesh-engine" in result["species_from"] and result["species_loads"]
