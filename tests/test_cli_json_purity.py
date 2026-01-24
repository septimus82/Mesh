from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]


def test_suppress_stdout_restores_on_exception(capsys):
    from engine.logging_tools import suppress_stdout

    try:
        with suppress_stdout():
            print("NOISE")  # noqa: T201
            raise ValueError("boom")
    except ValueError:
        pass

    print("OK")  # noqa: T201
    out = capsys.readouterr().out
    assert "OK" in out
    assert "NOISE" not in out


def test_list_scenes_stdout_is_pure_json_even_if_noisy(monkeypatch, tmp_path, capsys):
    import mesh_cli
    import mesh_cli.legacy_impl as mesh_cli_legacy

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (repo / "sub").mkdir()
    monkeypatch.chdir(repo / "sub")

    def noisy_list_scenes(*_a, **_k):
        print("NOISE")  # noqa: T201
        return {"ok": True, "scenes": [], "summary": {"scene_count": 0, "issues_count": 0}}

    monkeypatch.setattr(mesh_cli_legacy, "_inventory_list_scenes", noisy_list_scenes)
    assert mesh_cli.main(["list-scenes"]) == 0
    out = capsys.readouterr().out
    assert "NOISE" not in out
    assert out.lstrip().startswith("{")
    assert json.loads(out)["ok"] is True


def test_verify_all_stdout_is_pure_json_even_if_noisy(monkeypatch, tmp_path, capsys):
    import mesh_cli
    import mesh_cli.legacy_impl as mesh_cli_legacy

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (repo / "replays").mkdir()
    (repo / "replays" / "00_smoke.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(repo)

    def noisy_verify_demo(_args, **_kwargs):
        print("NOISE")  # noqa: T201
        return 0

    def noisy_replay_suite(_folder):
        print("NOISE")  # noqa: T201
        return {"failed": 0, "passed": 1, "total": 1, "results": []}

    def noisy_validate_all(_argv):
        print("NOISE")  # noqa: T201
        return 0

    def noisy_generate_encounter_report(**_kwargs):
        print("NOISE")  # noqa: T201
        from engine.encounter_report import EncounterReport

        return EncounterReport()

    def noisy_list_scenes():
        print("NOISE")  # noqa: T201
        return {"ok": True, "scenes": [], "summary": {"scene_count": 0, "issues_count": 0}}

    def noisy_list_worlds():
        print("NOISE")  # noqa: T201
        return {"ok": True, "worlds": [], "summary": {"world_count": 0, "issues_count": 0}}

    monkeypatch.setattr(mesh_cli_legacy, "load_config", lambda: type("C", (), {"world_file": "worlds/main_world.json"})())
    monkeypatch.setattr(mesh_cli.verify_demo, "run_verify_demo", noisy_verify_demo)
    monkeypatch.setattr(mesh_cli.replay_suite, "run_replay_suite", noisy_replay_suite)
    monkeypatch.setattr(mesh_cli.validate_all, "main", noisy_validate_all)
    import engine.tooling.asset_doctor as asset_doctor

    def noisy_doctor_assets(**_kwargs):
        print("NOISE")  # noqa: T201
        return {"ok": True, "errors": [], "warnings": [], "fixes": []}

    monkeypatch.setattr(asset_doctor, "doctor_assets", noisy_doctor_assets)
    monkeypatch.setattr(mesh_cli_legacy, "_resolve_scene_paths", lambda _p: ["scenes/x.json"])
    monkeypatch.setattr(mesh_cli_legacy, "generate_encounter_report", noisy_generate_encounter_report)
    monkeypatch.setattr(mesh_cli_legacy, "_inventory_list_scenes", noisy_list_scenes)
    monkeypatch.setattr(mesh_cli_legacy, "_inventory_list_worlds", noisy_list_worlds)

    assert mesh_cli.main(["verify-all"]) == 0
    out = capsys.readouterr().out
    assert "NOISE" not in out
    payload = json.loads(out)
    assert payload["ok"] is True
    assert [s["name"] for s in payload["steps"]] == list(mesh_cli.VERIFY_ALL_STEPS)


def test_replay_script_stdout_is_pure_json_even_if_noisy(monkeypatch, tmp_path, capsys):
    import mesh_cli

    script_path = tmp_path / "script.json"
    script_path.write_text(json.dumps({"steps": []}), encoding="utf-8")

    def noisy_load(_path):
        print("NOISE")  # noqa: T201
        return {"steps": []}

    def noisy_run(_script, **_kwargs):
        print("NOISE")  # noqa: T201
        return {"a": 1, "b": 2}

    monkeypatch.setattr(mesh_cli.replay_script, "load_replay_script", noisy_load)
    monkeypatch.setattr(mesh_cli.replay_script, "run_replay_script", noisy_run)

    assert mesh_cli.main(["replay-script", str(script_path)]) == 0
    out = capsys.readouterr().out
    assert "NOISE" not in out
    assert json.loads(out) == {"a": 1, "b": 2}


def test_encounter_report_stdout_is_pure_json_even_if_noisy(monkeypatch, capsys):
    import mesh_cli
    import mesh_cli.legacy_impl as mesh_cli_legacy

    from engine.encounter_report import EncounterReport

    def noisy_generate(*_a, **_k):
        print("NOISE")  # noqa: T201
        return EncounterReport()

    monkeypatch.setattr(mesh_cli_legacy, "_resolve_scene_paths", lambda _p: ["scenes/x.json"])
    monkeypatch.setattr(mesh_cli_legacy, "generate_encounter_report", noisy_generate)

    assert mesh_cli.main(["encounter-report", "scenes/x.json", "--json"]) == 0
    out = capsys.readouterr().out
    assert "NOISE" not in out
    payload = json.loads(out)
    assert payload.get("schema_version") == 1
    assert "scenes" in payload
