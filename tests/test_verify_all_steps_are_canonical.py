from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]


def test_verify_all_steps_are_canonical(monkeypatch, tmp_path, capsys) -> None:
    import mesh_cli
    import mesh_cli.legacy_impl as mesh_cli_legacy
    from engine.encounter_report import EncounterReport

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (repo / "replays").mkdir()
    (repo / "replays" / "00_smoke.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(repo)

    monkeypatch.setattr(mesh_cli_legacy, "load_config", lambda: type("C", (), {"world_file": "worlds/main_world.json"})())
    monkeypatch.setattr(mesh_cli.verify_demo, "run_verify_demo", lambda *_a, **_k: 0)
    monkeypatch.setattr(mesh_cli.replay_suite, "run_replay_suite", lambda _folder: {"failed": 0, "passed": 1, "total": 1, "results": []})
    monkeypatch.setattr(mesh_cli.validate_all, "main", lambda _argv: 0)
    monkeypatch.setattr(mesh_cli_legacy, "_resolve_scene_paths", lambda _p: ["scenes/x.json"])
    monkeypatch.setattr(mesh_cli_legacy, "generate_encounter_report", lambda **_k: EncounterReport())
    import engine.tooling.asset_doctor as asset_doctor

    monkeypatch.setattr(asset_doctor, "doctor_assets", lambda **_kwargs: {"ok": True, "errors": [], "warnings": [], "fixes": []})
    monkeypatch.setattr(mesh_cli_legacy, "_inventory_list_scenes", lambda: {"ok": True, "scenes": [], "summary": {"scene_count": 0, "issues_count": 0}})
    monkeypatch.setattr(mesh_cli_legacy, "_inventory_list_worlds", lambda: {"ok": True, "worlds": [], "summary": {"world_count": 0, "issues_count": 0}})

    assert mesh_cli.main(["verify-all"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert [s["name"] for s in payload["steps"]] == list(mesh_cli.VERIFY_ALL_STEPS)
    assert len(set(mesh_cli.VERIFY_ALL_STEPS)) == len(mesh_cli.VERIFY_ALL_STEPS)
