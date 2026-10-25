"""A pip-installed Mesh works out of the box: the wheel carries the engine's own bundled files (the allow-list in
pyproject.toml's [tool.setuptools.data-files], installed under <prefix>/share/mesh-engine), and only those; a new
project, the HD-2D RPG starter included, gets everything it uses from them, outside any checkout.

Replaces the original test (2026-01), which expected the engine's packs/ to load from the wheel without a project;
since 643970a (2026-06-30) a game's content resolves only inside its project (docs/packaging.md). The full
installed-engine acceptance (Mesh Studio, play, export) is tooling/hd2d_install_acceptance.py.
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
UNVERIFIED_SPRITES = {"assets/sprites/animated_player.png", "assets/sprites/shelltide.png",
                      "assets/sprites/sproutling.png"}  # provenance unverified: never bundled


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
import engine
from engine.paths import resolve_engine_bundled_path
from engine.project_scaffold import create_project
from engine.hd2d import catalog
work = Path(sys.argv[1])
create_project(work / "blank", "Blank", template_id="blank")
create_project(work / "village", "Village", template_id="hd2d_rpg")
species = resolve_engine_bundled_path("assets/data/monster_species.json")
village = work / "village"
print(json.dumps({
    "engine": engine.__file__,
    "missing": missing,
    "blank_files": sorted(p.relative_to(work / "blank").as_posix() for p in (work / "blank").rglob("*") if p.is_file()),
    "village_files": sorted(p.relative_to(village).as_posix() for p in village.rglob("*") if p.is_file()),
    "village_models": sorted(a.id for a in catalog.assets(village) if a.catalogued and not a.missing),
    "input_bindings": bool(json.loads((work / "blank" / "config.json").read_text(encoding="utf-8")).get("input_bindings")),
    "species_from": str(species), "species_loads": bool(json.loads(species.read_text(encoding="utf-8"))),
}))
'''


def test_the_wheel_bundles_exactly_the_allow_list_and_new_projects_need_nothing_else() -> None:
    allowed = _allow_list()
    assert allowed and not (set(allowed) & UNVERIFIED_SPRITES)
    assert all((REPO / f).is_file() for f in allowed), "every allow-listed file exists"
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
        assert not any(n.startswith(("packs/", "tooling/", "tests/")) for n in names)
        schemas = sorted(p.relative_to(REPO).as_posix() for p in (REPO / "engine" / "schemas").glob("*.json"))
        assert schemas and set(schemas) <= set(names), "the engine's own schemas travel with the package"

        venv = tmp_path / "venv"
        subprocess.check_call([sys.executable, "-m", "venv", str(venv)])
        subprocess.check_call([str(_venv_python(venv)), "-m", "pip", "install", "--no-deps", "-q", str(wheel)])
        # Creating projects needs Mesh's declared jsonschema and pillow, not the graphics stack (arcade).
        subprocess.check_call([str(_venv_python(venv)), "-m", "pip", "install", "-q", "jsonschema>=4,<5", "pillow>=10,<12"])
        work = tmp_path / "work"  # no repo markers here: the installed engine has only itself to go on
        work.mkdir()
        env = {k: v for k, v in os.environ.items() if k not in ("MESH_REPO_ROOT", "PYTHONPATH")}
        env.update({"MESH_USER_DIR": str(tmp_path / "user"), "MESH_PROJECTS_DIR": str(tmp_path / "projects")})
        out = subprocess.check_output([str(_venv_python(venv)), "-I", "-c", PROBE, str(work)], cwd=str(work), env=env,
                                      text=True)
        result = json.loads(out.strip().splitlines()[-1])
        venv_root = venv.resolve()

    assert Path(result["engine"]).resolve().is_relative_to(venv_root), "the installed engine, not a checkout"
    assert result["missing"] == [], result["missing"]
    assert {"assets/sprites/starter_hero.png", "assets/tilesets/starter.png", "assets/sprites/door.png"} <= set(result["blank_files"])
    assert result["input_bindings"], "the engine's default input bindings"
    assert "share" in result["species_from"] and "mesh-engine" in result["species_from"] and result["species_loads"]
    village = set(result["village_files"])
    assert {"assets/sprites/hd2d_hero.png", "assets/sounds/ui_open.wav", "assets/hd2d_starter/textures/grass.png"} <= village
    assert len(result["village_models"]) == 14 and not village & UNVERIFIED_SPRITES
