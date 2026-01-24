import json
import os
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> tuple[int, bytes, bytes]:
    res = subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True)
    return res.returncode, res.stdout, res.stderr


def _base_env() -> dict[str, str]:
    here = Path(__file__).resolve().parent.parent
    env = dict(os.environ)
    env["PYTHONPATH"] = str(here)
    return env


def test_doctor_assets_happy_path_ok_true(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'\nversion='0.0.0'\n", encoding="utf-8")
    (repo / "config.json").write_text(json.dumps({"title": "x"}, sort_keys=True) + "\n", encoding="utf-8")

    (repo / "assets" / "data").mkdir(parents=True)
    (repo / "assets" / "data" / "quests.json").write_text("[]\n", encoding="utf-8")
    (repo / "assets" / "data" / "events.json").write_text("[]\n", encoding="utf-8")

    (repo / "scenes").mkdir()
    (repo / "worlds").mkdir()
    (repo / "subdir").mkdir()

    (repo / "scenes" / "target.json").write_text(json.dumps({"entities": []}, sort_keys=True) + "\n", encoding="utf-8")
    (repo / "scenes" / "main.json").write_text(
        json.dumps(
            {
                "entities": [
                    {
                        "id": "tz1",
                        "behaviours": ["TriggerZone"],
                        "behaviour_config": {"TriggerZone": {"zone_id": "z1"}},
                    },
                    {
                        "id": "t1",
                        "behaviours": ["SceneTransition"],
                        "behaviour_config": {"SceneTransition": {"target_scene": "scenes/target.json"}},
                    },
                ]
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    (repo / "worlds" / "w.json").write_text(
        json.dumps(
            {"id": "w", "start_scene": "s1", "scenes": {"s1": {"path": "scenes/main.json"}}},
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    cmd = [sys.executable, "-m", "mesh_cli", "doctor-assets"]
    code, stdout, stderr = _run(cmd, cwd=repo / "subdir", env=_base_env())
    assert code == 0, stderr.decode("utf-8", errors="replace")
    assert stderr == b""
    assert stdout.endswith(b"\n")
    payload = json.loads(stdout.decode("utf-8"))
    assert payload["ok"] is True
    assert payload["errors"] == []
    assert payload["warnings"] == []
    assert payload["fixes"] == []
    cache = payload.get("cache")
    assert isinstance(cache, dict)
    assert isinstance(cache.get("hits"), int)
    assert isinstance(cache.get("misses"), int)
    assert isinstance(cache.get("entries"), int)


def test_doctor_assets_invalid_env_emits_deterministic_json_error(tmp_path: Path) -> None:
    bad = tmp_path / "nope"
    env = _base_env()
    env["MESH_REPO_ROOT"] = str(bad)

    code, stdout, _stderr = _run([sys.executable, "-m", "mesh_cli", "doctor-assets"], cwd=tmp_path, env=env)
    assert code == 2
    payload = json.loads(stdout.decode("utf-8"))
    assert payload["ok"] is False
    assert payload["warnings"] == []
    assert payload["fixes"] == []
    assert payload["errors"][0]["code"] == "repo_root.invalid"
    assert "MESH_REPO_ROOT is set but is not a directory" in payload["errors"][0]["message"]
    assert "\n" not in payload["errors"][0]["message"]


def test_doctor_assets_strict_escalates_missing_zone_id(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'\nversion='0.0.0'\n", encoding="utf-8")
    (repo / "config.json").write_text("{}\n", encoding="utf-8")
    (repo / "assets" / "data").mkdir(parents=True)
    (repo / "assets" / "data" / "quests.json").write_text("[]\n", encoding="utf-8")
    (repo / "assets" / "data" / "events.json").write_text("[]\n", encoding="utf-8")
    (repo / "scenes").mkdir()
    (repo / "sub").mkdir()

    (repo / "scenes" / "a.json").write_text(
        json.dumps({"entities": [{"behaviours": ["TriggerZone"], "behaviour_config": {"TriggerZone": {}}}]}, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )

    cmd = [sys.executable, "-m", "mesh_cli", "doctor-assets", "--strict"]
    code, stdout, _stderr = _run(cmd, cwd=repo / "sub", env=_base_env())
    assert code == 1
    payload = json.loads(stdout.decode("utf-8"))
    assert payload["ok"] is False
    assert any(e["code"] == "trigger_zone.zone_id.required" for e in payload["errors"])


def test_doctor_assets_fix_sets_zone_id_and_is_idempotent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'\nversion='0.0.0'\n", encoding="utf-8")
    (repo / "config.json").write_text("{}\n", encoding="utf-8")
    (repo / "assets" / "data").mkdir(parents=True)
    (repo / "assets" / "data" / "quests.json").write_text("[]\n", encoding="utf-8")
    (repo / "assets" / "data" / "events.json").write_text("[]\n", encoding="utf-8")
    (repo / "scenes").mkdir()
    (repo / "sub").mkdir()

    scene_path = repo / "scenes" / "a.json"
    scene_path.write_text(
        json.dumps(
            {"entities": [{"id": "E1", "behaviours": ["TriggerZone"], "behaviour_config": {"TriggerZone": {}}}]},
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    cmd = [sys.executable, "-m", "mesh_cli", "doctor-assets", "--fix"]
    code1, stdout1, _stderr1 = _run(cmd, cwd=repo / "sub", env=_base_env())
    assert code1 == 0
    payload1 = json.loads(stdout1.decode("utf-8"))
    assert payload1["ok"] is True
    assert payload1["errors"] == []
    assert payload1["warnings"] == []
    assert any(f["code"] == "trigger_zone.zone_id.autofix" for f in payload1["fixes"])

    updated = json.loads(scene_path.read_text(encoding="utf-8"))
    tz_cfg = updated["entities"][0]["behaviour_config"]["TriggerZone"]
    assert tz_cfg["zone_id"] == "E1"

    code2, stdout2, _stderr2 = _run(cmd, cwd=repo / "sub", env=_base_env())
    assert code2 == 0
    payload2 = json.loads(stdout2.decode("utf-8"))
    assert payload2["ok"] is True
    assert payload2["errors"] == []
    assert payload2["warnings"] == []
    assert payload2["fixes"] == []
    cache2 = payload2.get("cache")
    assert isinstance(cache2, dict)
    assert isinstance(cache2.get("hits"), int)
    assert isinstance(cache2.get("misses"), int)
    assert isinstance(cache2.get("entries"), int)
