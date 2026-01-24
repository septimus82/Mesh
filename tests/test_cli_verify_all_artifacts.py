from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]


def _stub_config():
    return type(
        "C",
        (),
        {
            "world_file": "worlds/main_world.json",
        },
    )()


def test_verify_all_artifacts_success_writes_expected_files(monkeypatch, tmp_path, capsys):
    import mesh_cli
    import mesh_cli.legacy_impl as mesh_cli_legacy

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (repo / "worlds").mkdir()
    (repo / "scenes").mkdir()
    (repo / "worlds" / "main_world.json").write_text(
        json.dumps({"scenes": {"main": {"path": "scenes/main.json"}}, "start_scene": "main"}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (repo / "scenes" / "main.json").write_text(json.dumps({"entities": []}, sort_keys=True) + "\n", encoding="utf-8")
    (repo / "replays").mkdir()
    (repo / "replays" / "00_smoke.json").write_text("{}", encoding="utf-8")
    (repo / "sub").mkdir()
    monkeypatch.chdir(repo / "sub")

    scenes_payload = {"ok": True, "scenes": [], "summary": {"scene_count": 0, "issues_count": 0}}
    worlds_payload = {"ok": True, "worlds": [], "summary": {"world_count": 0, "issues_count": 0}}
    replays_payload = {"failed": 0, "passed": 1, "total": 1, "results": []}

    monkeypatch.setattr(mesh_cli_legacy, "load_config", _stub_config)
    monkeypatch.setattr(mesh_cli.verify_demo, "run_verify_demo", lambda *_a, **_k: 0)
    monkeypatch.setattr(mesh_cli.replay_suite, "run_replay_suite", lambda _folder: replays_payload)
    monkeypatch.setattr(mesh_cli.validate_all, "main", lambda _argv: 0)
    import engine.tooling.asset_doctor as asset_doctor

    monkeypatch.setattr(
        asset_doctor,
        "doctor_assets",
        lambda **_kwargs: {"ok": True, "errors": [], "warnings": [], "fixes": [], "cache": {"hits": 0, "misses": 0, "entries": 0}},
    )
    monkeypatch.setattr(mesh_cli_legacy, "_inventory_list_scenes", lambda: scenes_payload)
    monkeypatch.setattr(mesh_cli_legacy, "_inventory_list_worlds", lambda: worlds_payload)

    artifacts_dir = repo / "artifacts"
    assert mesh_cli.main(["verify-all", "--artifacts", "artifacts"]) == 0

    stdout_text = capsys.readouterr().out
    stdout_bytes = stdout_text.encode("utf-8")

    summary_path = artifacts_dir / "verify_all_summary.json"
    assert summary_path.exists()
    assert summary_path.read_bytes() == stdout_bytes
    assert json.loads(stdout_text)["ok"] is True

    scenes_path = artifacts_dir / "scenes_index.json"
    worlds_path = artifacts_dir / "worlds_index.json"
    replays_path = artifacts_dir / "replays_summary.json"
    doctor_path = artifacts_dir / "doctor_assets.json"

    assert scenes_path.exists()
    assert worlds_path.exists()
    assert replays_path.exists()
    assert doctor_path.exists()

    assert json.loads(scenes_path.read_text(encoding="utf-8")) == scenes_payload
    assert json.loads(worlds_path.read_text(encoding="utf-8")) == worlds_payload
    assert json.loads(replays_path.read_text(encoding="utf-8")) == replays_payload
    doctor_payload = json.loads(doctor_path.read_text(encoding="utf-8"))
    assert doctor_payload["ok"] is True
    assert doctor_payload["errors"] == []
    assert doctor_payload["warnings"] == []
    assert doctor_payload["fixes"] == []
    cache = doctor_payload.get("cache")
    assert isinstance(cache, dict)


def test_verify_all_artifacts_failure_does_not_clobber_old_ok_artifacts(monkeypatch, tmp_path, capsys):
    import mesh_cli
    import mesh_cli.legacy_impl as mesh_cli_legacy

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
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

    artifacts_dir = repo / "artifacts"
    artifacts_dir.mkdir()

    old_scenes = b"{\"ok\": true}\n"
    old_worlds = b"{\"ok\": true}\n"
    old_replays = b"{\"failed\": 0}\n"
    old_doctor = b"{\"ok\": true}\n"
    (artifacts_dir / "scenes_index.json").write_bytes(old_scenes)
    (artifacts_dir / "worlds_index.json").write_bytes(old_worlds)
    (artifacts_dir / "replays_summary.json").write_bytes(old_replays)
    (artifacts_dir / "doctor_assets.json").write_bytes(old_doctor)

    monkeypatch.setattr(mesh_cli_legacy, "load_config", _stub_config)
    monkeypatch.setattr(mesh_cli.verify_demo, "run_verify_demo", lambda *_a, **_k: 0)
    monkeypatch.setattr(mesh_cli.replay_suite, "run_replay_suite", lambda _folder: {"failed": 0, "passed": 1, "total": 1, "results": []})
    monkeypatch.setattr(mesh_cli.validate_all, "main", lambda _argv: 1)
    import engine.tooling.asset_doctor as asset_doctor

    monkeypatch.setattr(asset_doctor, "doctor_assets", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("should be skipped")))

    assert mesh_cli.main(["verify-all", "--artifacts", "artifacts"]) == 1
    stdout_text = capsys.readouterr().out
    assert json.loads(stdout_text)["ok"] is False

    summary_path = artifacts_dir / "verify_all_summary.json"
    assert summary_path.exists()

    assert (artifacts_dir / "scenes_index.json").read_bytes() == old_scenes
    assert (artifacts_dir / "worlds_index.json").read_bytes() == old_worlds
    # verify-replays succeeds before verify-strict fails, so replays_summary is refreshed.
    assert (artifacts_dir / "replays_summary.json").read_bytes() != old_replays
    assert (artifacts_dir / "doctor_assets.json").read_bytes() == old_doctor


def test_verify_all_artifacts_no_index_skips_scene_world_indices(monkeypatch, tmp_path, capsys):
    import mesh_cli
    import mesh_cli.legacy_impl as mesh_cli_legacy

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
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
    monkeypatch.setattr(mesh_cli.replay_suite, "run_replay_suite", lambda _folder: {"failed": 0, "passed": 1, "total": 1, "results": []})
    monkeypatch.setattr(mesh_cli.validate_all, "main", lambda _argv: 0)
    import engine.tooling.asset_doctor as asset_doctor

    monkeypatch.setattr(
        asset_doctor,
        "doctor_assets",
        lambda **_kwargs: {"ok": True, "errors": [], "warnings": [], "fixes": [], "cache": {"hits": 0, "misses": 0, "entries": 0}},
    )
    monkeypatch.setattr(mesh_cli_legacy, "_inventory_list_scenes", lambda: {"ok": True, "scenes": [], "summary": {"scene_count": 0, "issues_count": 0}})
    monkeypatch.setattr(mesh_cli_legacy, "_inventory_list_worlds", lambda: {"ok": True, "worlds": [], "summary": {"world_count": 0, "issues_count": 0}})

    assert mesh_cli.main(["verify-all", "--artifacts", "artifacts", "--no-index"]) == 0
    _ = capsys.readouterr().out

    artifacts_dir = repo / "artifacts"
    assert (artifacts_dir / "verify_all_summary.json").exists()
    assert (artifacts_dir / "replays_summary.json").exists()
    assert (artifacts_dir / "doctor_assets.json").exists()
    assert not (artifacts_dir / "scenes_index.json").exists()
    assert not (artifacts_dir / "worlds_index.json").exists()
