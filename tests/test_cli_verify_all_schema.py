from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]


def _stub_config():
    return type("C", (), {"world_file": "worlds/main_world.json"})()


def test_verify_all_schema_success_with_artifacts(monkeypatch, tmp_path, capsys):
    import mesh_cli
    import mesh_cli.legacy_impl as mesh_cli_legacy
    from engine.encounter_report import EncounterReport

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
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
    import engine.tooling.asset_doctor as asset_doctor

    monkeypatch.setattr(
        asset_doctor,
        "doctor_assets",
        lambda **_kwargs: {"ok": True, "errors": [], "warnings": [], "fixes": []},
    )
    monkeypatch.setattr(mesh_cli_legacy, "_inventory_list_scenes", lambda: {"ok": True, "scenes": [], "summary": {"scene_count": 0, "issues_count": 0}})
    monkeypatch.setattr(mesh_cli_legacy, "_inventory_list_worlds", lambda: {"ok": True, "worlds": [], "summary": {"world_count": 0, "issues_count": 0}})

    assert mesh_cli.main(["verify-all", "--artifacts", "artifacts"]) == 0
    out = capsys.readouterr().out
    payload = json.loads(out)

    assert set(payload.keys()) == {"artifacts", "ok", "steps", "pytest_fast"}
    assert payload["ok"] is True
    assert payload["artifacts"]["dir"] == "artifacts"
    written = payload["artifacts"]["written"]
    assert set(written.keys()) == {
        "verify_all_summary",
        "verify_step_durations",
        "verify_step_budget_check",
        "shadow_backend",
        "swallowed_exceptions",
        "release_notes_json",
        "release_notes_md",
        "scenes_index",
        "worlds_index",
        "replays_summary",
        "doctor_assets",
        "stamp_audit",
        "brush_audit",
        "macro_audit",
        "room_audit",
        "encounter_coverage_matrix",
        "exception_budget",
        "content_audit",
        "encounter_audit_summary",
        "encounter_audit_compact",
        "encounter_headroom",
        "authoring_trace",
        "authoring_trace_budget_check",
        "verify_report",
        "artifact_index",
    }
    assert written["verify_all_summary"] == "artifacts/verify_all_summary.json"
    assert written["verify_step_durations"] == "artifacts/verify_step_durations.json"
    assert written["verify_step_budget_check"] == "artifacts/verify_step_budget_check.json"
    assert written["scenes_index"] == "artifacts/scenes_index.json"
    assert written["worlds_index"] == "artifacts/worlds_index.json"
    assert written["replays_summary"] == "artifacts/replays_summary.json"
    assert written["encounter_coverage_matrix"] == "artifacts/encounter_coverage_matrix.json"
    assert written["exception_budget"] == "artifacts/exception_budget.json"
    assert written["content_audit"] is None
    assert written["stamp_audit"] == "artifacts/stamp_audit.json"
    assert written["brush_audit"] == "artifacts/brush_audit.json"
    assert written["macro_audit"] == "artifacts/macro_audit.json"
    assert written["room_audit"] == "artifacts/room_audit.json"
    assert written["doctor_assets"] == "artifacts/doctor_assets.json"
    assert written["encounter_audit_summary"] == "artifacts/encounter_audit_summary.json"
    assert written["encounter_audit_compact"] == "artifacts/encounter_audit_compact.json"
    assert written["encounter_headroom"] == "artifacts/encounter_headroom.json"
    assert written["shadow_backend"] == "artifacts/shadow_backend.json"
    assert written["swallowed_exceptions"] == "artifacts/swallowed_exceptions.json"
    assert written["release_notes_json"] is None
    assert written["release_notes_md"] is None
    assert written["authoring_trace"] is None
    assert written["authoring_trace_budget_check"] is None
    assert written["verify_report"] is None
    assert written["artifact_index"] is None
    assert all("\\" not in (v or "") for v in written.values())

    assert [s["name"] for s in payload["steps"]] == list(mesh_cli.VERIFY_ALL_STEPS)
    for step in payload["steps"]:
        assert set(step.keys()) == {"artifact", "code", "error", "name", "ok"}
        assert step["ok"] is True
        assert step["code"] == 0
        if step["name"] in {"pytest-fast", "pytest-fast-duration-guard"}:
            assert step["error"]
        else:
            assert step["error"] == ""
        assert step["artifact"] in {None, *written.values()}


def test_verify_all_schema_failure_includes_skipped_steps(monkeypatch, tmp_path, capsys):
    import mesh_cli
    import mesh_cli.legacy_impl as mesh_cli_legacy

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (repo / "replays").mkdir()
    (repo / "replays" / "00_smoke.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(repo)

    monkeypatch.setattr(mesh_cli_legacy, "load_config", _stub_config)
    monkeypatch.setattr(mesh_cli.verify_demo, "run_verify_demo", lambda *_a, **_k: 0)
    monkeypatch.setattr(mesh_cli.replay_suite, "run_replay_suite", lambda _folder: {"failed": 0, "passed": 1, "total": 1, "results": []})
    monkeypatch.setattr(mesh_cli.validate_all, "main", lambda _argv: 1)
    monkeypatch.setattr(mesh_cli_legacy, "_resolve_scene_paths", lambda _p: (_ for _ in ()).throw(AssertionError("should be skipped")))
    monkeypatch.setattr(mesh_cli_legacy, "generate_encounter_report", lambda **_k: (_ for _ in ()).throw(AssertionError("should be skipped")))
    import engine.tooling.asset_doctor as asset_doctor

    monkeypatch.setattr(asset_doctor, "doctor_assets", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("should be skipped")))
    monkeypatch.setattr(mesh_cli_legacy, "_inventory_list_scenes", lambda: (_ for _ in ()).throw(AssertionError("should be skipped")))
    monkeypatch.setattr(mesh_cli_legacy, "_inventory_list_worlds", lambda: (_ for _ in ()).throw(AssertionError("should be skipped")))

    assert mesh_cli.main(["verify-all", "--artifacts", "artifacts"]) == 1
    out = capsys.readouterr().out
    payload = json.loads(out)

    assert payload["ok"] is False
    steps = payload["steps"]
    assert [s["name"] for s in steps] == list(mesh_cli.VERIFY_ALL_STEPS)
    strict = steps[2]
    assert strict["ok"] is False
    assert strict["code"] != 0
    assert strict["error"] != ""
    assert "\n" not in strict["error"]
    for step in steps[3:]:
        assert step["code"] == 2
        assert step["error"] == "skipped: previous step failed"

    written = payload["artifacts"]["written"]
    assert written["verify_all_summary"] == "artifacts/verify_all_summary.json"
    assert written["verify_step_durations"] == "artifacts/verify_step_durations.json"
    assert written["verify_step_budget_check"] == "artifacts/verify_step_budget_check.json"
    assert written["shadow_backend"] == "artifacts/shadow_backend.json"
    assert written["swallowed_exceptions"] == "artifacts/swallowed_exceptions.json"
    assert written["release_notes_json"] is None
    assert written["release_notes_md"] is None
    assert written["replays_summary"] == "artifacts/replays_summary.json"
    assert written["stamp_audit"] is None
    assert written["brush_audit"] is None
    assert written["macro_audit"] is None
    assert written["room_audit"] is None
    assert written["encounter_coverage_matrix"] is None
    assert written["exception_budget"] is None
    assert written["content_audit"] is None
    assert written["encounter_audit_summary"] is None
    assert written["encounter_audit_compact"] is None
    assert written["encounter_headroom"] is None
    assert written["scenes_index"] is None
    assert written["worlds_index"] is None
    assert written["doctor_assets"] is None
    assert written["authoring_trace"] is None
    assert written["authoring_trace_budget_check"] is None
    assert written["verify_report"] is None
    assert written["artifact_index"] is None


def test_verify_all_path_normalization_uses_forward_slashes(tmp_path):
    import mesh_cli

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    assert mesh_cli._normalize_path_for_json(r"artifacts\\weird.json", repo_root=repo_root) == "artifacts/weird.json"
