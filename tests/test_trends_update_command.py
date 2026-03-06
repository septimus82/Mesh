from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: object) -> None:
    _write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    _write_text(
        repo / "pyproject.toml",
        "\n".join(
            [
                "[project]",
                "name = \"mesh-engine\"",
                "version = \"0.4.0\"",
                "",
            ]
        ),
    )
    _write_text(
        repo / "engine" / "public_api" / "version.py",
        "\n".join(
            [
                "from __future__ import annotations",
                "",
                "PUBLIC_API_VERSION = \"1.0\"",
                "PUBLIC_API_SEMVER = \"1.0.0\"",
                "",
            ]
        ),
    )
    return repo


def _make_artifacts(repo: Path) -> Path:
    artifacts = repo / "artifacts"
    _write_json(
        artifacts / "verify_report.json",
        {
            "schema_version": 1,
            "verify_summary": {"ok": True},
            "budgets": {
                "exception_budget": {"ok": True},
            },
            "timing": {"total_ms": 1234},
            "runtime_diagnostics": {
                "swallowed_exceptions": {"total": 7},
                "shadow_backend": {"selected": "overlay"},
            },
        },
    )
    _write_json(
        artifacts / "verify_all_summary.json",
        {
            "ok": True,
            "steps": [
                {"name": "mypy-gate", "ok": True},
            ],
        },
    )
    _write_json(
        artifacts / "artifact_index.json",
        {
            "schema_version": 1,
            "written": {"verify_report": "artifacts/verify_report.json"},
        },
    )
    return artifacts


def _make_overlay_perf_artifact(artifacts: Path) -> None:
    _write_json(
        artifacts / "overlay_perf.json",
        {
            "schema_version": 1,
            "metrics": {
                "providers_total": {"count": 4, "total_ms": 8.0, "max_ms": 3.0},
                "command_palette_provider": {"count": 2, "total_ms": 3.5, "max_ms": 2.5},
            },
        },
    )


def _make_verify_step_budget_artifact(artifacts: Path) -> None:
    _write_json(
        artifacts / "verify_step_budget_check.json",
        {
            "schema_version": 2,
            "ok": True,
            "tolerance_ms": 50,
            "candidates_used": [],
            "checked_steps": [
                {
                    "name": "mypy-gate",
                    "budget_ms": 26000,
                    "tolerance_ms": 50,
                    "ratio_limit": 1.35,
                    "threshold_ms": 35100,
                    "current_ms": 19000,
                    "median_ms": None,
                    "effective_ms": 19000,
                    "delta_ms": -16100,
                    "ok": True,
                },
                {
                    "name": "pytest-fast",
                    "budget_ms": 20000,
                    "tolerance_ms": 50,
                    "ratio_limit": 1.25,
                    "threshold_ms": 25000,
                    "current_ms": 11234,
                    "median_ms": None,
                    "effective_ms": 11234,
                    "delta_ms": -13766,
                    "ok": True,
                },
            ],
            "offenders": [],
        },
    )


def test_trends_update_determinism(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import mesh_cli.trends_update as trends

    repo = _make_repo(tmp_path)
    artifacts = _make_artifacts(repo)
    monkeypatch.setattr(trends, "_repo_root_from_module", lambda: repo)
    monkeypatch.setattr(trends, "_utc_now_iso", lambda: "2026-02-17T00:00:00Z")

    trend1 = repo / "tooling" / "metrics" / "weekly_trends_a.json"
    trend2 = repo / "tooling" / "metrics" / "weekly_trends_b.json"

    assert trends.main(["--artifacts", str(artifacts), "--trend-file", str(trend1)]) == 0
    assert trends.main(["--artifacts", str(artifacts), "--trend-file", str(trend2)]) == 0
    assert trend1.read_bytes() == trend2.read_bytes()


def test_trends_update_truncates_to_26_entries(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import mesh_cli.trends_update as trends

    repo = _make_repo(tmp_path)
    artifacts = _make_artifacts(repo)
    monkeypatch.setattr(trends, "_repo_root_from_module", lambda: repo)
    monkeypatch.setattr(trends, "_utc_now_iso", lambda: "2026-02-17T00:00:00Z")

    trend_file = repo / "tooling" / "metrics" / "weekly_trends.json"
    _write_json(
        trend_file,
        {
            "schema_version": 1,
            "entries": [{"timestamp_utc": f"2026-01-{i:02d}T00:00:00Z", "n": i} for i in range(30)],
        },
    )

    assert trends.main(["--artifacts", str(artifacts), "--trend-file", str(trend_file)]) == 0
    payload = json.loads(trend_file.read_text(encoding="utf-8"))
    entries = payload.get("entries")
    assert isinstance(entries, list)
    assert len(entries) == 26
    assert isinstance(entries[-1], dict)
    assert entries[-1].get("timestamp_utc") == "2026-02-17T00:00:00Z"


def test_trends_update_handles_missing_verify_artifacts_gracefully(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import mesh_cli.trends_update as trends

    repo = _make_repo(tmp_path)
    artifacts = repo / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(trends, "_repo_root_from_module", lambda: repo)
    monkeypatch.setattr(trends, "_utc_now_iso", lambda: "2026-02-17T00:00:00Z")

    trend_file = repo / "tooling" / "metrics" / "weekly_trends.json"
    assert trends.main(["--artifacts", str(artifacts), "--trend-file", str(trend_file)]) == 0

    payload = json.loads(trend_file.read_text(encoding="utf-8"))
    entries = payload.get("entries")
    assert isinstance(entries, list)
    assert len(entries) == 1
    row = entries[0]
    assert isinstance(row, dict)
    assert row.get("verify_ok") == "?"
    assert row.get("verify_total_ms") == "?"
    assert row.get("mypy_budget_ok") == "?"
    assert row.get("exception_budget_ok") == "?"
    assert row.get("swallowed_total") == "?"
    assert row.get("shadow_backend_selected") == "?"
    assert row.get("pytest_fast_ms") is None
    assert row.get("pytest_fast_threshold_ms") is None
    assert row.get("overlay_perf") is None


def test_trends_update_reads_overlay_perf_when_present(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import mesh_cli.trends_update as trends

    repo = _make_repo(tmp_path)
    artifacts = _make_artifacts(repo)
    _make_overlay_perf_artifact(artifacts)
    monkeypatch.setattr(trends, "_repo_root_from_module", lambda: repo)
    monkeypatch.setattr(trends, "_utc_now_iso", lambda: "2026-02-17T00:00:00Z")

    trend_file = repo / "tooling" / "metrics" / "weekly_trends.json"
    assert trends.main(["--artifacts", str(artifacts), "--trend-file", str(trend_file)]) == 0

    payload = json.loads(trend_file.read_text(encoding="utf-8"))
    entries = payload.get("entries")
    assert isinstance(entries, list) and len(entries) == 1
    row = entries[0]
    assert isinstance(row, dict)
    overlay_perf = row.get("overlay_perf")
    assert isinstance(overlay_perf, dict)
    assert overlay_perf == {
        "providers_total": {"count": 4, "total_ms": 8.0, "max_ms": 3.0, "avg_ms": 2.0},
        "command_palette_provider": {"count": 2, "total_ms": 3.5, "max_ms": 2.5, "avg_ms": 1.75},
    }


def test_trends_update_reads_pytest_fast_budget_metrics_when_present(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import mesh_cli.trends_update as trends

    repo = _make_repo(tmp_path)
    artifacts = _make_artifacts(repo)
    _make_verify_step_budget_artifact(artifacts)
    monkeypatch.setattr(trends, "_repo_root_from_module", lambda: repo)
    monkeypatch.setattr(trends, "_utc_now_iso", lambda: "2026-02-17T00:00:00Z")

    trend_file = repo / "tooling" / "metrics" / "weekly_trends.json"
    assert trends.main(["--artifacts", str(artifacts), "--trend-file", str(trend_file)]) == 0

    payload = json.loads(trend_file.read_text(encoding="utf-8"))
    entries = payload.get("entries")
    assert isinstance(entries, list) and len(entries) == 1
    row = entries[0]
    assert isinstance(row, dict)
    assert row.get("pytest_fast_ms") == 11234
    assert row.get("pytest_fast_threshold_ms") == 25000
