from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


def _write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _seed_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _write(repo / "pyproject.toml", {"project": {"name": "mesh-test", "version": "0.0.0"}})


def _make_args(*, artifacts: str, release_notes_artifact: bool) -> argparse.Namespace:
    return argparse.Namespace(
        command="verify-all",
        world=None,
        out_dir=None,
        artifacts=artifacts,
        no_index=False,
        report=False,
        report_json=False,
        report_json_artifact=False,
        artifact_index=False,
        ci_bundle=False,
        release_notes_artifact=release_notes_artifact,
        pytest_args=[],
    )


def _patch_fast_success(monkeypatch: pytest.MonkeyPatch) -> None:
    import mesh_cli.verify as verify_mod

    def _fake_run_verify_steps(ctx) -> None:
        for name in verify_mod.VERIFY_ALL_STEPS:
            ctx.add_step(name, 0, error="", artifact=None)
            ctx.step_duration_rows.append({"name": name, "ok": True, "ms": 1})
        ctx.pytest_fast_metrics = {"ok": True, "total": 1.0, "top10": 0.5}
        ctx.exit_code = 0
        ctx.failure_seen = False

    monkeypatch.setattr(verify_mod, "run_verify_steps", _fake_run_verify_steps)
    monkeypatch.setattr(
        verify_mod,
        "_evaluate_verify_step_budget_guard",
        lambda **_kwargs: (
            0,
            "",
            {
                "schema_version": 2,
                "ok": True,
                "tolerance_ms": 50,
                "candidates_used": [],
                "checked_steps": [],
                "offenders": [],
            },
        ),
    )
    monkeypatch.setattr(
        verify_mod,
        "_fetch_shadow_backend_diagnostics",
        lambda: {"schema_version": 1, "selected": "none", "reason": "test", "fallbacks": []},
    )
    monkeypatch.setattr(
        verify_mod,
        "_fetch_swallowed_exceptions_snapshot",
        lambda: {"schema_version": 1, "ok": True, "total": 0, "distinct": 0, "per_site": []},
    )


def test_release_notes_artifact_flag_writes_files_and_registers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import mesh_cli.verify as verify_mod

    repo = tmp_path / "repo"
    _seed_repo(repo)
    monkeypatch.chdir(repo)
    _patch_fast_success(monkeypatch)

    payload, code = verify_mod._build_verify_all_payload(
        _make_args(artifacts="artifacts", release_notes_artifact=True)
    )
    assert code == 0
    written = payload["artifacts"]["written"]
    assert written["release_notes_json"] == "artifacts/release_notes.json"
    assert written["release_notes_md"] == "artifacts/release_notes.md"

    notes_json = repo / "artifacts" / "release_notes.json"
    notes_md = repo / "artifacts" / "release_notes.md"
    assert notes_json.exists()
    assert notes_md.exists()
    notes_payload = json.loads(notes_json.read_text(encoding="utf-8"))
    assert notes_payload["schema_version"] == 1
    assert notes_md.read_text(encoding="utf-8").startswith("#")


def test_release_notes_artifact_bytes_are_deterministic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import mesh_cli.verify as verify_mod

    repo = tmp_path / "repo"
    _seed_repo(repo)
    monkeypatch.chdir(repo)
    _patch_fast_success(monkeypatch)
    args = _make_args(artifacts="artifacts", release_notes_artifact=True)
    _payload_a, code_a = verify_mod._build_verify_all_payload(args)
    assert code_a == 0
    json_bytes_a = (repo / "artifacts" / "release_notes.json").read_bytes()
    md_bytes_a = (repo / "artifacts" / "release_notes.md").read_bytes()

    import shutil

    shutil.rmtree(repo / "artifacts")
    _patch_fast_success(monkeypatch)
    _payload_b, code_b = verify_mod._build_verify_all_payload(args)
    assert code_b == 0
    json_bytes_b = (repo / "artifacts" / "release_notes.json").read_bytes()
    md_bytes_b = (repo / "artifacts" / "release_notes.md").read_bytes()

    assert json_bytes_a == json_bytes_b
    assert md_bytes_a == md_bytes_b


def test_release_notes_artifact_flag_unset_leaves_keys_none(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import mesh_cli.verify as verify_mod

    repo = tmp_path / "repo"
    _seed_repo(repo)
    monkeypatch.chdir(repo)
    _patch_fast_success(monkeypatch)

    payload, code = verify_mod._build_verify_all_payload(
        _make_args(artifacts="artifacts", release_notes_artifact=False)
    )
    assert code == 0
    written = payload["artifacts"]["written"]
    assert "release_notes_json" in written
    assert "release_notes_md" in written
    assert written["release_notes_json"] is None
    assert written["release_notes_md"] is None
    assert not (repo / "artifacts" / "release_notes.json").exists()
    assert not (repo / "artifacts" / "release_notes.md").exists()


def test_release_notes_artifact_best_effort_preserves_failure_exit_code(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import mesh_cli.verify as verify_mod

    repo = tmp_path / "repo"
    _seed_repo(repo)
    monkeypatch.chdir(repo)

    def _fake_failed_run_verify_steps(ctx) -> None:
        first = True
        for name in verify_mod.VERIFY_ALL_STEPS:
            if first:
                ctx.add_step(name, 1, error="failed", artifact=None)
                ctx.step_duration_rows.append({"name": name, "ok": False, "ms": 1})
                first = False
            else:
                ctx.skipped_step(name)
                ctx.step_duration_rows.append({"name": name, "ok": True, "ms": 0})
        ctx.pytest_fast_metrics = {"ok": None, "total": None, "top10": None}
        ctx.exit_code = 1
        ctx.failure_seen = True

    monkeypatch.setattr(verify_mod, "run_verify_steps", _fake_failed_run_verify_steps)
    monkeypatch.setattr(
        verify_mod,
        "_evaluate_verify_step_budget_guard",
        lambda **_kwargs: (
            0,
            "",
            {
                "schema_version": 2,
                "ok": True,
                "tolerance_ms": 50,
                "candidates_used": [],
                "checked_steps": [],
                "offenders": [],
            },
        ),
    )
    monkeypatch.setattr(
        verify_mod,
        "_fetch_shadow_backend_diagnostics",
        lambda: {"schema_version": 1, "selected": "none", "reason": "test", "fallbacks": []},
    )
    monkeypatch.setattr(
        verify_mod,
        "_fetch_swallowed_exceptions_snapshot",
        lambda: {"schema_version": 1, "ok": True, "total": 0, "distinct": 0, "per_site": []},
    )
    monkeypatch.setattr(
        "mesh_cli.release_notes.build_release_notes_payload",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    payload, code = verify_mod._build_verify_all_payload(
        _make_args(artifacts="artifacts", release_notes_artifact=True)
    )
    assert code == 1
    assert payload["ok"] is False
