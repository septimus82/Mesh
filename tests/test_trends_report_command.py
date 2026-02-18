from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _make_trend_file(path: Path) -> None:
    _write(
        path,
        {
            "schema_version": 1,
            "entries": [
                {
                    "timestamp_utc": "2026-02-10T00:00:00Z",
                    "package_version": "0.4.0",
                    "public_api_semver": "1.0.0",
                    "verify_ok": False,
                    "verify_total_ms": 1000,
                    "mypy_budget_ok": False,
                    "exception_budget_ok": True,
                    "swallowed_total": 9,
                    "shadow_backend_selected": "mask",
                },
                {
                    "timestamp_utc": "2026-02-17T00:00:00Z",
                    "package_version": "0.4.1",
                    "public_api_semver": "1.0.0",
                    "verify_ok": True,
                    "verify_total_ms": 1100,
                    "mypy_budget_ok": True,
                    "exception_budget_ok": False,
                    "swallowed_total": 7,
                    "shadow_backend_selected": "overlay",
                },
            ],
        },
    )


def test_trends_report_determinism(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import mesh_cli.trends_report as report

    repo = tmp_path / "repo"
    trend_file = repo / "tooling" / "metrics" / "weekly_trends.json"
    _make_trend_file(trend_file)
    monkeypatch.setattr(report, "_repo_root_from_module", lambda: repo)

    rc1 = report.main(["--trend-file", str(trend_file), "--format", "json", "--last", "8"])
    out1 = capsys.readouterr().out
    rc2 = report.main(["--trend-file", str(trend_file), "--format", "json", "--last", "8"])
    out2 = capsys.readouterr().out
    assert rc1 == 0
    assert rc2 == 0
    assert out1 == out2


def test_trends_report_delta_correctness(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import mesh_cli.trends_report as report

    repo = tmp_path / "repo"
    trend_file = repo / "tooling" / "metrics" / "weekly_trends.json"
    _make_trend_file(trend_file)
    monkeypatch.setattr(report, "_repo_root_from_module", lambda: repo)

    rc = report.main(["--trend-file", str(trend_file), "--format", "json", "--last", "8"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    deltas = payload["deltas"]
    assert deltas["verify_total_ms"] == 100
    assert deltas["swallowed_total"] == -2
    assert deltas["verify_ok"] == "false -> true"
    assert deltas["mypy_budget_ok"] == "false -> true"
    assert deltas["exception_budget_ok"] == "true -> false"
    assert deltas["shadow_backend_selected"] == "mask -> overlay"


def test_trends_report_missing_file_exit_2(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import mesh_cli.trends_report as report

    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    missing = repo / "tooling" / "metrics" / "weekly_trends.json"
    monkeypatch.setattr(report, "_repo_root_from_module", lambda: repo)
    rc = report.main(["--trend-file", str(missing)])
    assert rc == 2


def test_trends_report_json_and_markdown_formats(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import mesh_cli.trends_report as report

    repo = tmp_path / "repo"
    trend_file = repo / "tooling" / "metrics" / "weekly_trends.json"
    _make_trend_file(trend_file)
    monkeypatch.setattr(report, "_repo_root_from_module", lambda: repo)

    rc_json = report.main(["--trend-file", str(trend_file), "--format", "json"])
    out_json = capsys.readouterr().out
    assert rc_json == 0
    payload = json.loads(out_json)
    assert payload["schema_version"] == 1
    assert "latest" in payload
    assert "deltas" in payload
    assert "history" in payload

    rc_md = report.main(["--trend-file", str(trend_file), "--format", "markdown"])
    out_md = capsys.readouterr().out
    assert rc_md == 0
    assert "## Trends delta panel" in out_md
    assert "### Delta vs previous" in out_md
    assert "| timestamp_utc | verify_total_ms | swallowed_total |" in out_md
