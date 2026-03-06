import json

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]


def _stub_config():
    return type(
        "C",
        (),
        {
            "width": 1,
            "height": 1,
            "title": "t",
            "fullscreen": False,
            "vsync": False,
            "start_scene": "scenes/test.json",
            "world_file": "worlds/main_world.json",
        },
    )()


def test_cli_verify_all_success_path(monkeypatch, tmp_path, capsys):
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

    calls: dict[str, object] = {}

    def stub_verify_demo(pytest_args, **kwargs):
        calls["verify_demo_pytest_args"] = list(pytest_args)
        calls["verify_demo_kwargs"] = dict(kwargs)
        return 0

    def stub_replay_suite(_folder):
        calls["verify_replays"] = True
        return {"failed": 0, "passed": 1, "total": 1, "results": []}

    def stub_validate_all(_argv):
        calls["verify_strict"] = True
        return 0

    monkeypatch.setattr(mesh_cli_legacy, "load_config", _stub_config)
    monkeypatch.setattr(mesh_cli.verify_demo, "run_verify_demo", stub_verify_demo)
    monkeypatch.setattr(mesh_cli.replay_suite, "run_replay_suite", stub_replay_suite)
    monkeypatch.setattr(mesh_cli.validate_all, "main", stub_validate_all)
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

    code = mesh_cli.main(["verify-all"])
    out = capsys.readouterr().out
    payload = json.loads(out)

    assert code == 0
    assert payload["ok"] is True
    assert payload["artifacts"]["dir"] is None
    assert payload["artifacts"]["written"] == {
        "doctor_assets": None,
        "stamp_audit": None,
        "brush_audit": None,
        "macro_audit": None,
        "room_audit": None,
        "encounter_coverage_matrix": None,
        "exception_budget": None,
        "content_audit": None,
        "encounter_audit_summary": None,
        "encounter_audit_compact": None,
        "encounter_headroom": None,
        "perf_run": None,
        "perf_compare": None,
        "player_package_manifest": None,
        "player_package_check": None,
        "player_package_runtime_smoke": None,
        "player_package_runtime_diagnostics_snapshot": None,
        "runtime_smoke": None,
        "runtime_diagnostics_snapshot": None,
        "replays_summary": None,
        "scenes_index": None,
        "verify_step_budget_check": None,
        "verify_step_durations": None,
        "verify_all_summary": None,
        "worlds_index": None,
    }
    assert [s["name"] for s in payload["steps"]] == list(mesh_cli.VERIFY_ALL_STEPS)
    for step in payload["steps"]:
        assert step["ok"] is True
        assert step["code"] == 0
        if step["name"] in {"pytest-fast", "pytest-fast-duration-guard"}:
            assert step["error"]
        else:
            assert step["error"] == ""
        assert step["artifact"] is None

    assert calls["verify_demo_pytest_args"] == []
    assert calls["verify_demo_kwargs"] == {"capture_output": True, "quiet": True}
    assert calls.get("verify_replays") is True
    assert calls.get("verify_strict") is True


def test_cli_verify_all_failure_short_circuits(monkeypatch, tmp_path, capsys):
    import mesh_cli
    import mesh_cli.legacy_impl as mesh_cli_legacy

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (repo / "replays").mkdir()
    (repo / "replays" / "00_smoke.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(repo)

    called = {"validate_all": 0, "list_scenes": 0, "list_worlds": 0}

    monkeypatch.setattr(mesh_cli_legacy, "load_config", _stub_config)
    monkeypatch.setattr(mesh_cli.verify_demo, "run_verify_demo", lambda *_a, **_k: 0)
    monkeypatch.setattr(mesh_cli.replay_suite, "run_replay_suite", lambda _folder: {"failed": 1})

    import engine.tooling.asset_doctor as asset_doctor

    monkeypatch.setattr(asset_doctor, "doctor_assets", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("should be skipped")))
    monkeypatch.setattr(mesh_cli_legacy, "_resolve_scene_paths", lambda _p: (_ for _ in ()).throw(AssertionError("should be skipped")))
    monkeypatch.setattr(mesh_cli_legacy, "generate_encounter_report", lambda **_k: (_ for _ in ()).throw(AssertionError("should be skipped")))

    def stub_validate_all(_argv):
        called["validate_all"] += 1
        return 0

    monkeypatch.setattr(mesh_cli.validate_all, "main", stub_validate_all)
    monkeypatch.setattr(mesh_cli_legacy, "_inventory_list_scenes", lambda: called.__setitem__("list_scenes", called["list_scenes"] + 1) or {})
    monkeypatch.setattr(mesh_cli_legacy, "_inventory_list_worlds", lambda: called.__setitem__("list_worlds", called["list_worlds"] + 1) or {})

    code = mesh_cli.main(["verify-all"])
    out = capsys.readouterr().out
    payload = json.loads(out)

    assert code == 1
    assert payload["ok"] is False
    assert [s["name"] for s in payload["steps"]] == list(mesh_cli.VERIFY_ALL_STEPS)
    assert payload["steps"][1]["ok"] is False
    assert payload["steps"][1]["code"] == 1
    assert payload["steps"][1]["error"] != ""
    assert payload["steps"][2]["ok"] is False and payload["steps"][2]["code"] == 2
    assert payload["steps"][2]["error"] == "skipped: previous step failed"
    assert payload["steps"][3]["ok"] is False and payload["steps"][3]["code"] == 2
    assert payload["steps"][3]["error"] == "skipped: previous step failed"
    assert payload["steps"][4]["ok"] is False and payload["steps"][4]["code"] == 2
    assert payload["steps"][4]["error"] == "skipped: previous step failed"
    assert payload["steps"][5]["ok"] is False and payload["steps"][5]["code"] == 2
    assert payload["steps"][5]["error"] == "skipped: previous step failed"

    assert called["validate_all"] == 0
    assert called["list_scenes"] == 0
    assert called["list_worlds"] == 0


def test_cli_verify_all_out_dir_writes_indices(monkeypatch, tmp_path, capsys):
    import mesh_cli
    import mesh_cli.legacy_impl as mesh_cli_legacy
    from engine.encounter_report import EncounterReport

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (repo / "replays").mkdir()
    (repo / "replays" / "00_smoke.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(repo)

    scenes_payload = {"ok": True, "scenes": [{"path": "scenes/a.json"}], "summary": {"scene_count": 1, "issues_count": 0}}
    worlds_payload = {"ok": True, "worlds": [{"path": "worlds/w.json"}], "summary": {"world_count": 1, "issues_count": 0}}

    writes: list[tuple[str, dict]] = []

    def stub_write_json_atomic(path, payload, **kwargs):
        writes.append((path.as_posix(), {"payload": payload, "kwargs": dict(kwargs)}))

    monkeypatch.setattr(mesh_cli_legacy, "load_config", _stub_config)
    monkeypatch.setattr(mesh_cli.verify_demo, "run_verify_demo", lambda *_a, **_k: 0)
    monkeypatch.setattr(mesh_cli.replay_suite, "run_replay_suite", lambda _folder: {"failed": 0})
    monkeypatch.setattr(mesh_cli.validate_all, "main", lambda _argv: 0)
    monkeypatch.setattr(mesh_cli_legacy, "_resolve_scene_paths", lambda _p: ["scenes/x.json"])
    monkeypatch.setattr(mesh_cli_legacy, "generate_encounter_report", lambda **_k: EncounterReport())
    import engine.tooling.asset_doctor as asset_doctor

    monkeypatch.setattr(
        asset_doctor,
        "doctor_assets",
        lambda **_kwargs: {"ok": True, "errors": [], "warnings": [], "fixes": []},
    )
    monkeypatch.setattr(mesh_cli_legacy, "_inventory_list_scenes", lambda: scenes_payload)
    monkeypatch.setattr(mesh_cli_legacy, "_inventory_list_worlds", lambda: worlds_payload)

    import engine.persistence_io as persistence_io

    monkeypatch.setattr(persistence_io, "write_json_atomic", stub_write_json_atomic)

    code = mesh_cli.main(["verify-all", "--out-dir", "artifacts"])
    out = capsys.readouterr().out
    payload = json.loads(out)

    assert code == 0
    assert payload["ok"] is True
    outs = {s["name"]: s.get("artifact") for s in payload["steps"]}
    assert outs["encounter-audit"] is None
    assert outs["list-scenes"] == "artifacts/scenes_index.json"
    assert outs["list-worlds"] == "artifacts/worlds_index.json"

    assert [w[0] for w in writes] == [
        (repo / "artifacts" / "scenes_index.json").as_posix(),
        (repo / "artifacts" / "worlds_index.json").as_posix(),
    ]
    assert writes[0][1]["payload"] == scenes_payload
    assert writes[1][1]["payload"] == worlds_payload
    assert writes[0][1]["kwargs"]["sort_keys"] is True
    assert writes[0][1]["kwargs"]["trailing_newline"] is True


def test_cli_verify_all_passthrough_forwarded_to_verify_demo(monkeypatch, tmp_path, capsys):
    import mesh_cli
    import mesh_cli.legacy_impl as mesh_cli_legacy
    from engine.encounter_report import EncounterReport

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (repo / "replays").mkdir()
    (repo / "replays" / "00_smoke.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(repo)

    got: dict[str, object] = {}

    def stub_verify_demo(pytest_args, **_kwargs):
        got["pytest_args"] = list(pytest_args)
        return 0

    monkeypatch.setattr(mesh_cli_legacy, "load_config", _stub_config)
    monkeypatch.setattr(mesh_cli.verify_demo, "run_verify_demo", stub_verify_demo)
    monkeypatch.setattr(mesh_cli.replay_suite, "run_replay_suite", lambda _folder: {"failed": 0})
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

    code = mesh_cli.main(["verify-all", "--", "--maxfail=1"])
    out = capsys.readouterr().out
    payload = json.loads(out)

    assert code == 0
    assert payload["ok"] is True
    assert got["pytest_args"] == ["--maxfail=1"]


def test_cli_verify_all_rejects_unsafe_passthrough(monkeypatch, capsys):
    import mesh_cli

    monkeypatch.setattr(mesh_cli.verify_demo, "run_verify_demo", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("should not run")))

    code = mesh_cli.main(["verify-all", "--", "-k", "smoke"])
    out = capsys.readouterr().out
    payload = json.loads(out)

    assert code == 2
    assert payload["ok"] is False
    assert [s["name"] for s in payload["steps"]] == list(mesh_cli.VERIFY_ALL_STEPS)
    assert payload["steps"][0]["ok"] is False
    assert payload["steps"][0]["code"] == 2
    assert payload["steps"][0]["error"] != ""
    assert payload["steps"][1]["code"] == 2
    assert payload["steps"][1]["error"] == "skipped: previous step failed"
    assert payload["steps"][2]["code"] == 2
    assert payload["steps"][2]["error"] == "skipped: previous step failed"

    code = mesh_cli.main(["verify-all", "--", "tests/test_smoke.py"])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert code == 2
    assert payload["steps"][0]["ok"] is False
    assert payload["steps"][0]["code"] == 2
