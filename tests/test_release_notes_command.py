from __future__ import annotations

import json
from pathlib import Path

import pytest

import mesh_cli
from mesh_cli.release_notes import build_release_notes

pytestmark = [pytest.mark.fast]


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_release_notes_is_deterministic_and_prefers_verify_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    _write_json(
        artifacts_dir / "verify_report.json",
        {
            "schema_version": 1,
            "verify_summary": {"ok": False, "failing_steps": ["from-report"]},
            "budgets": {
                "exception_budget": {"current_count": 2, "baseline_count": 3, "ok": False},
                "verify_step_budget": {"ok": False, "worst_offender": {"name": "from-report-worst", "delta_ms": 99}},
            },
            "timing": {"total_ms": 123, "top5": []},
            "runtime_diagnostics": {
                "swallowed_exceptions": {
                    "total": 4,
                    "distinct": 2,
                    "top5_sites": [{"site": "site_b", "count": 2}, {"site": "site_a", "count": 3}],
                },
                "shadow_backend": {"selected": "shadow-gpu", "reason": "capable", "fallbacks": []},
            },
            "read_files": ["verify_all_summary.json"],
        },
    )
    _write_json(
        artifacts_dir / "verify_all_summary.json",
        {"ok": True, "steps": [{"name": "ignored", "ok": True}]},
    )
    _write_json(
        artifacts_dir / "verify_step_durations.json",
        {
            "schema_version": 1,
            "total_ms": 1111,
            "steps": [
                {"name": "b-step", "ms": 20, "ok": True},
                {"name": "a-step", "ms": 20, "ok": False},
                {"name": "c-step", "ms": 10, "ok": True},
            ],
        },
    )
    _write_json(artifacts_dir / "index.json", {"schema_version": 1, "ok": True})

    rc = mesh_cli.main(["release-notes", "--artifacts", str(artifacts_dir), "--title", "Fixture Title"])
    assert rc == 0
    first = capsys.readouterr().out

    rc = mesh_cli.main(["release-notes", "--artifacts", str(artifacts_dir), "--title", "Fixture Title"])
    assert rc == 0
    second = capsys.readouterr().out

    assert first == second
    assert "# Fixture Title" in first
    assert "- Verify: ok=false, failing_steps=[from-report]" in first
    assert "- Exception budget: 2/3 ok=false" in first
    assert "- Step budget: ok=false worst=from-report-worst delta_ms=99" in first
    assert "- Total verify ms: 123" in first
    assert "| a-step | 20 | false |" in first
    assert "| b-step | 20 | true |" in first
    assert "- Swallowed exceptions: total=4 distinct=2 top sites: (site_a=3, site_b=2)" in first
    assert "- Shadow backend: selected=shadow-gpu reason=capable" in first
    assert "\n- index.json\n" in first
    assert "\n- verify_report.json\n" in first


def test_release_notes_missing_files_use_placeholders(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    rc = mesh_cli.main(["release-notes", "--artifacts", str(artifacts_dir)])
    assert rc == 0
    out = capsys.readouterr().out

    assert "- Verify: ok=?, failing_steps=[]" in out
    assert "- Exception budget: ?/? ok=?" in out
    assert "- Step budget: ok=? worst=? delta_ms=?" in out
    assert "- Total verify ms: ?" in out
    assert "- Swallowed exceptions: total=? distinct=? top sites: (none)" in out
    assert "- Shadow backend: selected=? reason=?" in out
    assert "\n## Files read\n- ?\n" in out


def test_release_notes_honors_max_sites_and_max_steps(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    _write_json(
        artifacts_dir / "verify_step_durations.json",
        {
            "schema_version": 1,
            "total_ms": 100,
            "steps": [
                {"name": "step4", "ms": 40, "ok": True},
                {"name": "step3", "ms": 30, "ok": False},
                {"name": "step2", "ms": 20, "ok": True},
                {"name": "step1", "ms": 10, "ok": True},
            ],
        },
    )
    _write_json(
        artifacts_dir / "swallowed_exceptions.json",
        {
            "schema_version": 1,
            "ok": True,
            "total": 10,
            "distinct": 4,
            "per_site": [
                {"site": "site1", "count": 1},
                {"site": "site3", "count": 3},
                {"site": "site4", "count": 4},
                {"site": "site2", "count": 2},
            ],
        },
    )

    rc = mesh_cli.main(
        [
            "release-notes",
            "--artifacts",
            str(artifacts_dir),
            "--max-sites",
            "2",
            "--max-steps",
            "2",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    rows = [
        line
        for line in lines
        if line.startswith("| ")
        and line != "| step | ms | ok |"
        and line != "| --- | ---: | :---: |"
    ]
    assert rows == ["| step4 | 40 | true |", "| step3 | 30 | false |"]
    assert "- Swallowed exceptions: total=10 distinct=4 top sites: (site4=4, site3=3)" in out


def test_release_notes_out_writes_exact_bytes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        artifacts_dir / "verify_step_durations.json",
        {
            "schema_version": 1,
            "total_ms": 10,
            "steps": [{"name": "step-a", "ms": 10, "ok": True}],
        },
    )

    out_path = tmp_path / "notes.md"
    rc = mesh_cli.main(["release-notes", "--artifacts", str(artifacts_dir), "--out", str(out_path)])
    assert rc == 0
    assert capsys.readouterr().out == ""

    expected = build_release_notes(artifacts_dir, title=None, max_sites=5, max_steps=5)
    assert out_path.read_bytes() == expected.encode("utf-8")


def test_release_notes_missing_artifacts_dir_exits_2(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = tmp_path / "missing_artifacts"
    rc = mesh_cli.main(["release-notes", "--artifacts", str(missing)])
    assert rc == 2
    assert "artifacts directory not found" in capsys.readouterr().err

