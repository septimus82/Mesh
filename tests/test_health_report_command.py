from __future__ import annotations

import json
from pathlib import Path

import pytest

import mesh_cli
import mesh_cli.health_report as health_report

pytestmark = [pytest.mark.fast]


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_health_report_schema_and_determinism_from_non_repo_cwd(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "fake_repo"
    _write(repo / "engine" / "a.py", "x=1\ny=2\nz=3\n")
    _write(repo / "mesh_cli" / "c.py", "a=1\nb=2\nc=3\nd=4\ne=5\nf=6\ng=7\n")
    _write(repo / "tooling" / "b.py", "a=1\nb=2\nc=3\nd=4\ne=5\nf=6\ng=7\n")
    _write(
        repo / "tooling" / "mypy_baseline.txt",
        "foo.py:1: error: x\nbar.py:2: error: y\nnote: not an error line\n",
    )
    _write(repo / "tooling" / "metrics" / "exception_budget_count.txt", "11\n")

    artifacts_dir = repo / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / "exception_budget.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "ok": True,
                "current_count": 9,
                "baseline_count": 11,
                "files_scanned": [],
                "per_file_counts": {},
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (artifacts_dir / "verify_step_durations.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "total_ms": 15,
                "steps": [
                    {"name": "step-b", "ok": True, "ms": 10},
                    {"name": "step-a", "ok": True, "ms": 5},
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(health_report, "_repo_root_from_module", lambda: repo.resolve())
    monkeypatch.chdir(tmp_path)

    assert mesh_cli.main(["health-report", "--artifacts", "artifacts"]) == 0
    out_path = artifacts_dir / "health_report.json"
    assert out_path.exists()
    first_text = out_path.read_text(encoding="utf-8")
    payload = json.loads(first_text)

    assert payload["schema_version"] == 1
    assert payload["repo_root"] == repo.resolve().as_posix()
    assert payload["signals"]["exception_budget"] == {"baseline": 11, "current": 9, "ok": True}
    assert payload["signals"]["verify_step_durations"]["total_ms"] == 15
    assert payload["signals"]["verify_step_durations"]["steps"] == [
        {"name": "step-b", "ms": 10, "ok": True},
        {"name": "step-a", "ms": 5, "ok": True},
    ]
    assert payload["signals"]["mypy_baseline"]["error_count"] == 2

    hotspots = payload["signals"]["hotspots"]
    assert hotspots == sorted(
        hotspots,
        key=lambda row: (-int(row["nonempty_lines"]), str(row["path"])),
    )

    assert mesh_cli.main(["health-report", "--artifacts", "artifacts"]) == 0
    second_text = out_path.read_text(encoding="utf-8")
    assert first_text == second_text


def test_health_report_missing_verify_artifacts_use_nulls(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "fake_repo"
    _write(repo / "engine" / "only.py", "x=1\n")
    (repo / "mesh_cli").mkdir(parents=True, exist_ok=True)
    (repo / "tooling").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(health_report, "_repo_root_from_module", lambda: repo.resolve())
    monkeypatch.chdir(tmp_path)

    assert mesh_cli.main(["health-report", "--artifacts", "out_artifacts"]) == 0
    payload = json.loads((repo / "out_artifacts" / "health_report.json").read_text(encoding="utf-8"))

    assert payload["schema_version"] == 1
    assert payload["signals"]["exception_budget"] == {"baseline": None, "current": None, "ok": None}
    assert payload["signals"]["verify_step_durations"] == {"total_ms": None, "steps": None}
    assert payload["signals"]["mypy_baseline"] == {"error_count": None}
    assert isinstance(payload["signals"]["hotspots"], list)
