from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]


def _stub_config():
    return type("C", (), {"world_file": "worlds/main_world.json"})()


def test_verify_all_includes_doctor_assets_warning_ok(monkeypatch, tmp_path, capsys):
    import mesh_cli
    import mesh_cli.legacy_impl as mesh_cli_legacy
    from engine.encounter_report import EncounterReport

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'\nversion='0.0.0'\n", encoding="utf-8")
    (repo / "config.json").write_text("{}\n", encoding="utf-8")
    (repo / "assets" / "data").mkdir(parents=True)
    (repo / "assets" / "data" / "quests.json").write_text("[]\n", encoding="utf-8")
    (repo / "assets" / "data" / "events.json").write_text("[]\n", encoding="utf-8")
    (repo / "replays").mkdir()
    (repo / "replays" / "00_smoke.json").write_text("{}", encoding="utf-8")
    (repo / "worlds").mkdir()
    (repo / "scenes").mkdir()
    (repo / "sub").mkdir()

    (repo / "scenes" / "main.json").write_text(
        json.dumps(
            {
                "entities": [
                    {
                        "behaviours": ["SceneTransition"],
                        "behaviour_config": {"SceneTransition": {"target_scene": "scenes/missing.json"}},
                    }
                ]
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (repo / "worlds" / "main_world.json").write_text(
        json.dumps({"scenes": {"main": {"path": "scenes/main.json"}}, "start_scene": "main"}, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(repo / "sub")

    monkeypatch.setattr(mesh_cli_legacy, "load_config", _stub_config)
    monkeypatch.setattr(mesh_cli.verify_demo, "run_verify_demo", lambda *_a, **_k: 0)
    monkeypatch.setattr(mesh_cli.replay_suite, "run_replay_suite", lambda _folder: {"failed": 0, "passed": 1, "total": 1, "results": []})
    monkeypatch.setattr(mesh_cli.validate_all, "main", lambda _argv: 0)
    monkeypatch.setattr(mesh_cli_legacy, "_resolve_scene_paths", lambda _p: ["scenes/main.json"])
    monkeypatch.setattr(mesh_cli_legacy, "generate_encounter_report", lambda **_k: EncounterReport())
    monkeypatch.setattr(mesh_cli_legacy, "_inventory_list_scenes", lambda **_k: {"ok": True, "scenes": [], "summary": {"scene_count": 0, "issues_count": 0}})
    monkeypatch.setattr(mesh_cli_legacy, "_inventory_list_worlds", lambda **_k: {"ok": True, "worlds": [], "summary": {"world_count": 0, "issues_count": 0}})

    assert mesh_cli.main(["verify-all"]) == 0
    payload = json.loads(capsys.readouterr().out)

    names = [s["name"] for s in payload["steps"]]
    assert names == list(mesh_cli.VERIFY_ALL_STEPS)

    by_name = {s["name"]: s for s in payload["steps"]}
    assert by_name["world-progression-check"]["code"] == 0
    assert by_name["spawn-placeholder-safety"]["code"] == 0
    assert by_name["encounter-coverage"]["code"] == 0
    assert by_name["encounter-coverage-matrix"]["code"] == 0
    doctor_step = by_name["doctor-assets"]
    assert doctor_step["ok"] is True and doctor_step["code"] == 0
    assert by_name["encounter-audit"]["code"] == 0
    assert by_name["list-scenes"]["code"] == 0
    assert by_name["list-worlds"]["code"] == 0


def test_verify_all_doctor_assets_failure_skips_later_steps(monkeypatch, tmp_path, capsys):
    import mesh_cli
    import mesh_cli.legacy_impl as mesh_cli_legacy

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'\nversion='0.0.0'\n", encoding="utf-8")
    (repo / "config.json").write_text("{}\n", encoding="utf-8")
    (repo / "assets" / "data").mkdir(parents=True)
    (repo / "assets" / "data" / "quests.json").write_text(
        json.dumps([{"id": "Q1"}, {"id": " q1 "}], sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (repo / "assets" / "data" / "events.json").write_text("[]\n", encoding="utf-8")
    (repo / "replays").mkdir()
    (repo / "replays" / "00_smoke.json").write_text("{}", encoding="utf-8")
    (repo / "sub").mkdir()
    monkeypatch.chdir(repo / "sub")

    monkeypatch.setattr(mesh_cli_legacy, "load_config", _stub_config)
    monkeypatch.setattr(mesh_cli.verify_demo, "run_verify_demo", lambda *_a, **_k: 0)
    monkeypatch.setattr(mesh_cli.replay_suite, "run_replay_suite", lambda _folder: {"failed": 0, "passed": 1, "total": 1, "results": []})
    monkeypatch.setattr(mesh_cli.validate_all, "main", lambda _argv: 0)

    monkeypatch.setattr(mesh_cli_legacy, "_resolve_scene_paths", lambda _p: [])
    monkeypatch.setattr(mesh_cli_legacy, "generate_encounter_report", lambda **_k: (_ for _ in ()).throw(AssertionError("should be skipped")))
    monkeypatch.setattr(mesh_cli_legacy, "_inventory_list_scenes", lambda **_k: (_ for _ in ()).throw(AssertionError("should be skipped")))
    monkeypatch.setattr(mesh_cli_legacy, "_inventory_list_worlds", lambda **_k: (_ for _ in ()).throw(AssertionError("should be skipped")))

    assert mesh_cli.main(["verify-all"]) == 1
    payload = json.loads(capsys.readouterr().out)

    doctor_step = next(s for s in payload["steps"] if s["name"] == "doctor-assets")
    assert doctor_step["ok"] is False
    assert doctor_step["code"] == 1
    assert doctor_step["error"] != ""

    list_scenes = next(s for s in payload["steps"] if s["name"] == "list-scenes")
    list_worlds = next(s for s in payload["steps"] if s["name"] == "list-worlds")
    audit_step = next(s for s in payload["steps"] if s["name"] == "encounter-audit")
    assert audit_step["code"] == 2 and audit_step["error"] == "skipped: previous step failed"
    assert list_scenes["code"] == 2 and list_scenes["error"] == "skipped: previous step failed"
    assert list_worlds["code"] == 2 and list_worlds["error"] == "skipped: previous step failed"


def test_verify_all_artifacts_writes_doctor_assets_json(monkeypatch, tmp_path, capsys):
    import mesh_cli
    import mesh_cli.legacy_impl as mesh_cli_legacy
    from engine.encounter_report import EncounterReport

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'\nversion='0.0.0'\n", encoding="utf-8")
    (repo / "config.json").write_text("{}\n", encoding="utf-8")
    (repo / "assets" / "data").mkdir(parents=True)
    (repo / "assets" / "data" / "quests.json").write_text("[]\n", encoding="utf-8")
    (repo / "assets" / "data" / "events.json").write_text("[]\n", encoding="utf-8")
    (repo / "replays").mkdir()
    (repo / "replays" / "00_smoke.json").write_text("{}", encoding="utf-8")
    (repo / "sub").mkdir()
    monkeypatch.chdir(repo / "sub")

    monkeypatch.setattr(mesh_cli_legacy, "load_config", _stub_config)
    monkeypatch.setattr(mesh_cli.verify_demo, "run_verify_demo", lambda *_a, **_k: 0)
    monkeypatch.setattr(mesh_cli.replay_suite, "run_replay_suite", lambda _folder: {"failed": 0, "passed": 1, "total": 1, "results": []})
    monkeypatch.setattr(mesh_cli.validate_all, "main", lambda _argv: 0)
    monkeypatch.setattr(mesh_cli_legacy, "_resolve_scene_paths", lambda _p: ["scenes/x.json"])
    monkeypatch.setattr(mesh_cli_legacy, "generate_encounter_report", lambda **_k: EncounterReport())
    monkeypatch.setattr(mesh_cli_legacy, "_inventory_list_scenes", lambda **_k: {"ok": True, "scenes": [], "summary": {"scene_count": 0, "issues_count": 0}})
    monkeypatch.setattr(mesh_cli_legacy, "_inventory_list_worlds", lambda **_k: {"ok": True, "worlds": [], "summary": {"world_count": 0, "issues_count": 0}})

    assert mesh_cli.main(["verify-all", "--artifacts", "artifacts"]) == 0
    payload = json.loads(capsys.readouterr().out)

    artifacts_dir = repo / "artifacts"
    assert (artifacts_dir / "doctor_assets.json").exists()
    assert (artifacts_dir / "encounter_audit_summary.json").exists()
    assert (artifacts_dir / "encounter_audit_compact.json").exists()
    assert (artifacts_dir / "encounter_headroom.json").exists()
    assert (artifacts_dir / "stamp_audit.json").exists()
    assert (artifacts_dir / "brush_audit.json").exists()

    written = payload["artifacts"]["written"]
    assert written["doctor_assets"] == "artifacts/doctor_assets.json"
    doctor_step = next(s for s in payload["steps"] if s["name"] == "doctor-assets")
    assert doctor_step["artifact"] == "artifacts/doctor_assets.json"

    assert written["stamp_audit"] == "artifacts/stamp_audit.json"
    assert written["brush_audit"] == "artifacts/brush_audit.json"
    assert written["encounter_audit_summary"] == "artifacts/encounter_audit_summary.json"
    assert written["encounter_audit_compact"] == "artifacts/encounter_audit_compact.json"
    assert written["encounter_headroom"] == "artifacts/encounter_headroom.json"
    audit_step = next(s for s in payload["steps"] if s["name"] == "encounter-audit")
    assert audit_step["artifact"] == "artifacts/encounter_audit_summary.json"
