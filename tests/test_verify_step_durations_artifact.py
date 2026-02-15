from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]


def _stub_config():
    return type("C", (), {"world_file": "worlds/main_world.json"})()


def test_verify_step_durations_artifact_schema_and_order(monkeypatch, tmp_path) -> None:
    import mesh_cli
    import mesh_cli.legacy_impl as mesh_cli_legacy
    from engine.encounter_report import EncounterReport

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'\nversion='0.0.0'\n", encoding="utf-8")
    (repo / "worlds").mkdir()
    (repo / "scenes").mkdir()
    (repo / "worlds" / "main_world.json").write_text(
        json.dumps({"scenes": {"main": {"path": "scenes/main.json"}}, "start_scene": "main"}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (repo / "scenes" / "main.json").write_text(json.dumps({"entities": []}, sort_keys=True) + "\n", encoding="utf-8")
    (repo / "replays").mkdir()
    (repo / "replays" / "00_smoke.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(repo)

    monkeypatch.setattr(mesh_cli_legacy, "load_config", _stub_config)
    monkeypatch.setattr(mesh_cli.verify_demo, "run_verify_demo", lambda *_a, **_k: 0)
    monkeypatch.setattr(
        mesh_cli.replay_suite,
        "run_replay_suite",
        lambda _folder: {"failed": 0, "passed": 1, "total": 1, "results": []},
    )
    monkeypatch.setattr(mesh_cli.validate_all, "main", lambda _argv: 0)
    monkeypatch.setattr(mesh_cli_legacy, "_resolve_scene_paths", lambda _p: ["scenes/x.json"])
    monkeypatch.setattr(mesh_cli_legacy, "generate_encounter_report", lambda **_k: EncounterReport())

    import engine.tooling.asset_doctor as asset_doctor

    monkeypatch.setattr(
        asset_doctor,
        "doctor_assets",
        lambda **_kwargs: {"ok": True, "errors": [], "warnings": [], "fixes": []},
    )
    monkeypatch.setattr(
        mesh_cli_legacy,
        "_inventory_list_scenes",
        lambda **_k: {"ok": True, "scenes": [], "summary": {"scene_count": 0, "issues_count": 0}},
    )
    monkeypatch.setattr(
        mesh_cli_legacy,
        "_inventory_list_worlds",
        lambda **_k: {"ok": True, "worlds": [], "summary": {"world_count": 0, "issues_count": 0}},
    )

    assert mesh_cli.main(["verify-all", "--artifacts", "artifacts"]) == 0

    artifact_path = repo / "artifacts" / "verify_step_durations.json"
    assert artifact_path.exists()
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == 1
    assert isinstance(payload["total_ms"], int)
    assert payload["total_ms"] >= 0
    steps = payload["steps"]
    assert isinstance(steps, list)
    assert [entry["name"] for entry in steps] == list(mesh_cli.VERIFY_ALL_STEPS)
    assert all(isinstance(entry.get("ok"), bool) for entry in steps)
    assert all(isinstance(entry.get("ms"), int) and entry["ms"] >= 0 for entry in steps)
    assert payload["total_ms"] == sum(int(entry["ms"]) for entry in steps)

