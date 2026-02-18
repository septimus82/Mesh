from __future__ import annotations

import builtins
import importlib.util
import json

import pytest


pytestmark = [pytest.mark.fast]


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


def test_verify_all_skips_tooling_only_steps_when_tooling_missing(monkeypatch, tmp_path, capsys):
    import mesh_cli
    import mesh_cli.legacy_impl as mesh_cli_legacy
    import mesh_cli.verify_steps.pipeline as verify_pipeline
    from engine.encounter_report import EncounterReport
    import engine.tooling.asset_doctor as asset_doctor

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (repo / "replays").mkdir()
    (repo / "replays" / "00_smoke.json").write_text("{}", encoding="utf-8")
    (repo / "sub").mkdir()
    monkeypatch.chdir(repo / "sub")

    monkeypatch.setattr(mesh_cli_legacy, "load_config", _stub_config)
    monkeypatch.setattr(mesh_cli.verify_demo, "run_verify_demo", lambda *_a, **_k: 0)
    monkeypatch.setattr(mesh_cli.replay_suite, "run_replay_suite", lambda _folder: {"failed": 0})
    monkeypatch.setattr(mesh_cli.validate_all, "main", lambda _argv: 0)
    monkeypatch.setattr(mesh_cli_legacy, "_resolve_scene_paths", lambda _p: ["scenes/x.json"])
    monkeypatch.setattr(mesh_cli_legacy, "generate_encounter_report", lambda **_k: EncounterReport())
    monkeypatch.setattr(
        asset_doctor,
        "doctor_assets",
        lambda **_kwargs: {"ok": True, "errors": [], "warnings": [], "fixes": []},
    )
    monkeypatch.setattr(mesh_cli_legacy, "_inventory_list_scenes", lambda: {"ok": True, "scenes": [], "summary": {"scene_count": 0, "issues_count": 0}})
    monkeypatch.setattr(mesh_cli_legacy, "_inventory_list_worlds", lambda: {"ok": True, "worlds": [], "summary": {"world_count": 0, "issues_count": 0}})

    original_import = builtins.__import__

    def _blocked_import(name, globals=None, locals=None, fromlist=(), level=0):  # type: ignore[no-untyped-def]
        if name == "tooling" or name.startswith("tooling."):
            raise ModuleNotFoundError("No module named 'tooling'", name="tooling")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _blocked_import)

    original_find_spec = importlib.util.find_spec

    def _blocked_find_spec(name, package=None):  # type: ignore[no-untyped-def]
        if name == "tooling.pytest_fast":
            return None
        return original_find_spec(name, package)

    monkeypatch.setattr(verify_pipeline.importlib.util, "find_spec", _blocked_find_spec)

    code = mesh_cli.main(["verify-all"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    by_name = {step["name"]: step for step in payload["steps"]}
    assert by_name["mypy-gate"]["ok"] is True
    assert by_name["mypy-gate"]["error"] == "skipped: tooling package unavailable"
    assert by_name["mypy-baseline-guard"]["ok"] is True
    assert by_name["mypy-baseline-guard"]["error"] == "skipped: tooling package unavailable"
    assert by_name["mypy-island"]["ok"] is True
    assert by_name["mypy-island"]["error"] == "skipped: tooling package unavailable"
    assert by_name["pytest-fast"]["ok"] is True
    assert by_name["pytest-fast"]["error"] == "skipped: running under pytest"
    assert by_name["pytest-fast-duration-guard"]["ok"] is True
    assert by_name["pytest-fast-duration-guard"]["error"] == "skipped: pytest-fast not run"
