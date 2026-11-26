"""verify-all fails closed (#624 phase B): a step whose tooling is missing, or whose input is missing, fails the run.

Each case runs the real pipeline (``mesh_cli.main(["verify-all", ...])``) on a synthetic repo, with the heavy gates
stubbed to pass, and blocks exactly one thing.
"""

from __future__ import annotations

import builtins
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests._verify_skips import SYNTHETIC_REPO_SKIPS, allow_synthetic_repo_skips

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


def _synthetic_repo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, captured: dict[str, Any] | None = None) -> Path:
    """A repo with no step inputs, every step's heavy work stubbed to pass."""
    import engine.tooling.asset_doctor as asset_doctor
    import mesh_cli
    import mesh_cli.legacy_impl as mesh_cli_legacy
    from engine.encounter_report import EncounterReport
    from tooling import find_blanket_swallow, mypy_gate, mypy_island, ruff_gate, scan_exception_policies

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (repo / "replays").mkdir()
    (repo / "replays" / "00_smoke.json").write_text("{}", encoding="utf-8")
    (repo / "sub").mkdir()
    monkeypatch.chdir(repo / "sub")
    monkeypatch.delenv("MESH_REPO_ROOT", raising=False)

    def _verify_demo(pytest_args, **kwargs):
        if captured is not None:
            captured["pytest_args"] = list(pytest_args)
            captured["kwargs"] = dict(kwargs)
        return 0

    monkeypatch.setattr(mesh_cli_legacy, "load_config", _stub_config)
    monkeypatch.setattr(mesh_cli.verify_demo, "run_verify_demo", _verify_demo)
    monkeypatch.setattr(mesh_cli.replay_suite, "run_replay_suite", lambda _folder: {"failed": 0})
    monkeypatch.setattr(mesh_cli.validate_all, "main", lambda _argv: 0)
    monkeypatch.setattr(mesh_cli_legacy, "_resolve_scene_paths", lambda _p: ["scenes/x.json"])
    monkeypatch.setattr(mesh_cli_legacy, "generate_encounter_report", lambda **_k: EncounterReport())
    monkeypatch.setattr(asset_doctor, "doctor_assets", lambda **_k: {"ok": True, "errors": [], "warnings": [], "fixes": []})
    monkeypatch.setattr(mesh_cli_legacy, "_inventory_list_scenes", lambda: {"ok": True, "scenes": [], "summary": {"scene_count": 0, "issues_count": 0}})
    monkeypatch.setattr(mesh_cli_legacy, "_inventory_list_worlds", lambda: {"ok": True, "worlds": [], "summary": {"world_count": 0, "issues_count": 0}})
    for gate in (mypy_gate, mypy_island, ruff_gate, find_blanket_swallow):
        monkeypatch.setattr(gate, "main", lambda _argv: 0)
    monkeypatch.setattr(scan_exception_policies, "scan", lambda _roots, *, repo_root: {
        "ble001_count_total": 0, "silent_broad_catch_count_total": 0, "missing_ble001_reason_total": 0})
    return repo


def _block_tooling_import(monkeypatch: pytest.MonkeyPatch, module: str, nth: int) -> None:
    """``from tooling import <module>`` raises ModuleNotFoundError on its ``nth`` call, as without the package."""
    original_import = builtins.__import__
    calls = {"n": 0}

    def _blocked_import(name: str, globals: dict[str, Any] | None = None, locals: dict[str, Any] | None = None,
                        fromlist: tuple[str, ...] | None = (), level: int = 0) -> ModuleType:
        if name == "tooling" and module in (fromlist or ()):
            calls["n"] += 1
            if calls["n"] == nth:
                raise ModuleNotFoundError(f"No module named 'tooling.{module}'", name=f"tooling.{module}")
        return original_import(name, globals, locals, fromlist or (), level)

    monkeypatch.setattr(builtins, "__import__", _blocked_import)


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, dict[str, dict[str, Any]], dict[str, Any]]:
    import mesh_cli

    code = mesh_cli.main(["verify-all", *argv])
    payload = json.loads(capsys.readouterr().out)
    return code, {step["name"]: step for step in payload["steps"]}, payload


@pytest.mark.parametrize(("step", "module", "nth"), [
    ("mypy-gate", "mypy_gate", 1),
    ("mypy-baseline-guard", "mypy_gate", 2),  # the guard's own import, after mypy-gate's succeeded
    ("ruff-gate", "ruff_gate", 1),
    ("mypy-island", "mypy_island", 1),
    ("swallow-scan-gate", "find_blanket_swallow", 1),
    ("exception-policy-scan", "scan_exception_policies", 1),
    ("pytest-fast", "pytest_fast", 0),  # found with find_spec, not imported
])
def test_verify_all_fails_when_a_steps_tooling_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str], step: str, module: str, nth: int
) -> None:
    import mesh_cli.verify_steps.pipeline as verify_pipeline

    _synthetic_repo(monkeypatch, tmp_path)
    allow_synthetic_repo_skips(monkeypatch)
    if module == "pytest_fast":
        original_find_spec = importlib.util.find_spec
        monkeypatch.setattr(verify_pipeline.importlib.util, "find_spec",
                            lambda name, package=None: None if name == "tooling.pytest_fast"
                            else original_find_spec(name, package))
    else:
        _block_tooling_import(monkeypatch, module, nth)

    code, by_name, payload = _run(capsys)

    assert code == 2, by_name[step]
    assert payload["ok"] is False
    assert (by_name[step]["ok"], by_name[step]["code"], by_name[step]["error"]) == (False, 2, "tooling package unavailable")
    assert by_name["list-worlds"]["error"] == "skipped: previous step failed"


@pytest.mark.parametrize("skip", list(SYNTHETIC_REPO_SKIPS), ids=lambda key: f"{key[0]}:{key[1]}")
def test_verify_all_fails_on_a_skip_that_is_not_allow_listed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str], skip: tuple[str, str]
) -> None:
    """Each step whose input is missing reports ``skipped: <reason>``, and verify-all fails on it unless allow-listed."""
    repo = _synthetic_repo(monkeypatch, tmp_path)
    step, reason = skip
    if reason == "skipped: no scenes/runtime_smoke_scene.json":  # reached only with the packaging sources present
        (repo / "engine").mkdir()
        (repo / "mesh_cli").mkdir()
    allow_synthetic_repo_skips(monkeypatch, except_for=skip)

    code, by_name, payload = _run(capsys, "--artifacts", str(repo / "artifacts"))

    assert code == 2, by_name[step]
    assert payload["ok"] is False
    assert (by_name[step]["ok"], by_name[step]["code"]) == (False, 2)
    assert by_name[step]["error"] == f"skip not allow-listed (pipeline.ALLOWED_SKIPS): {reason}"


def test_allow_listed_skips_still_pass(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The production allow-list's skips pass, and each missing-input step says what it skipped (no empty pass)."""
    _synthetic_repo(monkeypatch, tmp_path)
    allow_synthetic_repo_skips(monkeypatch)

    code, by_name, payload = _run(capsys)  # no --artifacts: web-smoke's allow-listed skip

    assert code == 0, [s for s in by_name.values() if not s["ok"]]
    assert payload["ok"] is True
    for step, error in [
        ("pytest-fast", "skipped: running under pytest"),
        ("pytest-fast-duration-guard", "skipped: pytest-fast not run"),
        ("web-smoke", "skipped: artifacts directory required"),
        ("runtime-player-smoke", "skipped: no smoke scene"),
        ("player-package-gate", "skipped: no engine/ and mesh_cli/ sources"),
        ("perf-baseline-compare", "skipped: no perf scene set or baseline"),
        ("content-audit", "skipped: no content roots"),
    ]:
        assert (by_name[step]["ok"], by_name[step]["error"]) == (True, error)


def test_mesh_skip_pytest_fast_is_not_an_allow_listed_skip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Outside pytest, MESH_SKIP_PYTEST_FAST=1 would drop the fast tier and its failing timing ceiling (D9): it fails."""
    _synthetic_repo(monkeypatch, tmp_path)
    allow_synthetic_repo_skips(monkeypatch)
    monkeypatch.setenv("MESH_SKIP_PYTEST_FAST", "1")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delitem(sys.modules, "pytest")  # restored at teardown

    code, by_name, _payload = _run(capsys)

    assert code == 2
    assert by_name["pytest-fast"]["error"] == "skip not allow-listed (pipeline.ALLOWED_SKIPS): skipped: MESH_SKIP_PYTEST_FAST=1"


def test_verify_all_routes_verify_demo_to_artifacts_scoped_scratch(monkeypatch, tmp_path, capsys):
    captured: dict[str, Any] = {}
    repo = _synthetic_repo(monkeypatch, tmp_path, captured)
    allow_synthetic_repo_skips(monkeypatch)

    artifacts_dir = repo / "artifacts"
    code, _by_name, payload = _run(capsys, "--artifacts", str(artifacts_dir))

    assert code == 0
    assert payload["ok"] is True
    assert captured["pytest_args"] == []
    assert captured["kwargs"] == {
        "capture_output": True,
        "quiet": True,
        "log_path": artifacts_dir / "verify_demo.log",
        "scratch_dir": artifacts_dir / "verify_demo_pytest",
    }
