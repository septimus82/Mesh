import json
import os
import sys
from pathlib import Path

from tests.subprocess_tools import run_checked


def _run(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> tuple[int, bytes, bytes]:
    res = run_checked(cmd, cwd=str(cwd), env=env, text=False, capture_output=True)
    return res.returncode, res.stdout, res.stderr


def test_lint_presets_reports_unknown_ids_and_is_deterministic(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'\nversion='0.0.0'\n", encoding="utf-8")
    (repo / "scenes").mkdir()
    (repo / "packs" / "p1" / "scenes").mkdir(parents=True)
    (repo / "packs" / "core_regions" / "data").mkdir(parents=True)
    (repo / "subdir").mkdir()

    (repo / "packs" / "core_regions" / "data" / "encounter_presets.json").write_text(
        json.dumps({"presets": [{"id": "ok"}]}, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    (repo / "scenes" / "a.json").write_text(
        json.dumps({"settings": {"encounter_preset_id": "missing"}}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (repo / "packs" / "p1" / "scenes" / "b.json").write_text(
        json.dumps({"settings": {"encounter_preset_id": "ok"}}, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    here = Path(__file__).resolve().parent.parent
    env = dict(os.environ)
    env["PYTHONPATH"] = str(here)

    out_path = repo / "out.json"
    cmd = [sys.executable, "-m", "mesh_cli", "lint-presets", "--out", str(out_path)]

    code1, stdout1, stderr1 = _run(cmd, cwd=repo / "subdir", env=env)
    assert code1 == 1
    assert stderr1 == b""
    assert stdout1.endswith(b"\n")

    code2, stdout2, stderr2 = _run(cmd, cwd=repo / "subdir", env=env)
    assert code2 == 1
    assert stderr2 == b""
    assert stdout2 == stdout1

    assert out_path.read_bytes() == stdout1
    payload = json.loads(stdout1.decode("utf-8"))
    assert payload["ok"] is False
    assert payload["summary"]["scene_count"] == 2
    assert payload["summary"]["reference_count"] == 2
    assert payload["summary"]["error_count"] == 1
    assert payload["errors"] == [
        {
            "code": "preset.unknown",
            "path": "scenes/a.json",
            "message": "Unknown encounter_preset_id 'missing'",
        }
    ]


def test_lint_presets_ok_when_no_unknown_ids(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'\nversion='0.0.0'\n", encoding="utf-8")
    (repo / "scenes").mkdir()
    (repo / "packs" / "core_regions" / "data").mkdir(parents=True)

    (repo / "packs" / "core_regions" / "data" / "encounter_presets.json").write_text(
        json.dumps({"presets": [{"id": "ok"}]}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (repo / "scenes" / "a.json").write_text(
        json.dumps({"settings": {"encounter_preset_id": "ok"}}, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    here = Path(__file__).resolve().parent.parent
    env = dict(os.environ)
    env["PYTHONPATH"] = str(here)

    cmd = [sys.executable, "-m", "mesh_cli", "lint-presets"]
    code, stdout, stderr = _run(cmd, cwd=repo, env=env)
    assert code == 0, stderr.decode("utf-8", errors="replace")
    assert stderr == b""
    payload = json.loads(stdout.decode("utf-8"))
    assert payload["ok"] is True
    assert payload["errors"] == []

