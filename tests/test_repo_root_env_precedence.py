from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from tests.subprocess_tools import run_checked


def test_env_var_wins_for_default_config_load(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'\nversion='0.0.0'\n", encoding="utf-8")
    (repo / "config.json").write_text(json.dumps({"title": "FROM_ENV"}, sort_keys=True) + "\n", encoding="utf-8")

    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.chdir(other)

    monkeypatch.setenv("MESH_REPO_ROOT", str(repo))

    from engine.config import load_config

    cfg = load_config()
    assert cfg.title == "FROM_ENV"


def test_invalid_env_var_raises_in_strict_mode(monkeypatch, tmp_path):
    bad = tmp_path / "does_not_exist"
    monkeypatch.setenv("MESH_REPO_ROOT", str(bad))

    from engine.repo_root import get_repo_root

    try:
        get_repo_root(strict=True)
        assert False, "expected ValueError"
    except ValueError as exc:
        msg = str(exc)
        assert msg.startswith("MESH_REPO_ROOT is set but is not a directory:")
        assert str(bad).replace("\\", "/") in msg.replace("\\", "/")


def test_cli_list_worlds_invalid_env_emits_deterministic_json_error(monkeypatch, tmp_path):
    bad = tmp_path / "nope"
    env = dict(os.environ)
    env["MESH_REPO_ROOT"] = str(bad)

    here = Path(__file__).resolve().parent.parent
    env["PYTHONPATH"] = str(here)

    proc = run_checked(
        [sys.executable, "-m", "mesh_cli", "list-worlds"],
        cwd=str(tmp_path),
        env=env,
    )
    assert proc.returncode == 2
    assert proc.stderr == ""
    out = proc.stdout
    assert out.lstrip().startswith("{")
    payload = json.loads(out)
    assert payload["ok"] is False
    assert "MESH_REPO_ROOT is set but is not a directory" in payload["error"]
    assert "\n" not in payload["error"]

