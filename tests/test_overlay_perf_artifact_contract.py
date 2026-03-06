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


def _make_args(*, artifacts: str, ci_bundle: bool) -> argparse.Namespace:
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
        ci_bundle=ci_bundle,
        release_notes_artifact=False,
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


def test_overlay_perf_artifact_written_in_ci_bundle(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import mesh_cli.verify as verify_mod

    repo = tmp_path / "repo"
    _seed_repo(repo)
    monkeypatch.chdir(repo)
    _patch_fast_success(monkeypatch)
    monkeypatch.setattr(
        verify_mod,
        "_fetch_overlay_perf_snapshot",
        lambda: {
            "schema_version": 1,
            "metrics": {
                "command_palette_provider": {"count": 2, "total_ms": 3.5, "max_ms": 2.0},
                "providers_total": {"count": 4, "total_ms": 8.5, "max_ms": 3.0},
            },
        },
    )

    payload, code = verify_mod._build_verify_all_payload(_make_args(artifacts="artifacts", ci_bundle=True))
    assert code == 0
    written = payload["artifacts"]["written"]
    assert written["overlay_perf"] == "artifacts/overlay_perf.json"

    artifact_path = repo / "artifacts" / "overlay_perf.json"
    assert artifact_path.exists()
    data = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert set(data.keys()) == {"schema_version", "metrics"}
    assert set(data["metrics"].keys()) == {"command_palette_provider", "providers_total"}
    for metric in data["metrics"].values():
        assert set(metric.keys()) == {"count", "max_ms", "total_ms"}


def test_overlay_perf_artifact_key_none_when_ci_bundle_off(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import mesh_cli.verify as verify_mod

    repo = tmp_path / "repo"
    _seed_repo(repo)
    monkeypatch.chdir(repo)
    _patch_fast_success(monkeypatch)

    payload, code = verify_mod._build_verify_all_payload(_make_args(artifacts="artifacts", ci_bundle=False))
    assert code == 0
    written = payload["artifacts"]["written"]
    assert "overlay_perf" in written
    assert written["overlay_perf"] is None
    assert not (repo / "artifacts" / "overlay_perf.json").exists()
