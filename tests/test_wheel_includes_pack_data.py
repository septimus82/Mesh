from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def test_wheel_includes_pack_data_and_presets_load() -> None:
    repo_root = Path(__file__).resolve().parent.parent

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        wheel_dir = tmp_path / "wheelhouse"
        wheel_dir.mkdir(parents=True, exist_ok=True)

        subprocess.check_call(
            [sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "-w", str(wheel_dir)],
            cwd=str(repo_root),
        )
        wheels = sorted(wheel_dir.glob("*.whl"))
        assert wheels, "Expected a wheel to be built"
        wheel_path = wheels[0]

        expected_rel_paths = []
        for p in sorted((repo_root / "packs").rglob("data/*.json")):
            expected_rel_paths.append(p.relative_to(repo_root).as_posix())

        assert expected_rel_paths, "Expected at least one packs/**/data/*.json file"

        with zipfile.ZipFile(wheel_path, "r") as zf:
            names = [n.replace("\\", "/") for n in zf.namelist()]
        missing = []
        for rel in expected_rel_paths:
            if not any(n.endswith(rel) for n in names):
                missing.append(rel)
        assert not missing, f"Wheel missing pack data files: {missing}"

        venv_dir = tmp_path / "venv"
        subprocess.check_call([sys.executable, "-m", "venv", str(venv_dir)])
        py = _venv_python(venv_dir)
        subprocess.check_call([str(py), "-m", "pip", "install", "--no-deps", str(wheel_path)])

        workdir = tmp_path / "workdir"
        workdir.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        env.pop("MESH_REPO_ROOT", None)
        env.pop("PYTHONPATH", None)

        code = (
            "from engine.encounter_sets import get_theme_manager\n"
            "tm = get_theme_manager()\n"
            "preset = tm.get_encounter_preset('normal')\n"
            "assert preset is not None, 'expected preset normal to load from packaged data'\n"
        )
        subprocess.check_call([str(py), "-c", code], cwd=str(workdir), env=env)
