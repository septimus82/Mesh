"""pytest-fast-duration-guard (#422 F13): it judges only against a baseline someone recorded on purpose.

Before, a missing baseline became the current run's own numbers and every pass overwrote it, so a fresh checkout (every
CI job) compared a run with itself and a local baseline crept up with each pass. And its "total" was the sum of the 25
slowest pytest entries, not the suite's time.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from mesh_cli.verify import _evaluate_pytest_fast_duration_guard, _pytest_fast_identity

pytestmark = [pytest.mark.fast]

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)


def _metrics_dir(tmp_path: Path) -> Path:
    # The guard's real layout, <repo>/.mesh/metrics (recording asks git for the commit two levels up).
    path = tmp_path / ".mesh" / "metrics"
    path.mkdir(parents=True)
    return path


def _write_durations(metrics: Path, seconds: list[float]) -> Path:
    path = metrics / "pytest_durations_fast.json"
    path.write_text(json.dumps([{"nodeid": f"tests/test_{i}.py::test_{i}", "seconds": s} for i, s in enumerate(seconds)]),
                    encoding="utf-8")
    return path


def _record(metrics: Path, seconds: list[float], **overrides: object) -> Path:
    durations = _write_durations(metrics, seconds)
    baseline = metrics / "pytest_fast_duration_baseline.json"
    code, _, _ = _evaluate_pytest_fast_duration_guard(durations, baseline, record=True, now=NOW)
    assert code == 0
    if overrides:
        payload = json.loads(baseline.read_text(encoding="utf-8"))
        payload.update(overrides)
        baseline.write_text(json.dumps(payload), encoding="utf-8")
    return baseline


def test_a_fresh_checkout_only_reports_and_never_makes_its_own_baseline(tmp_path: Path) -> None:
    metrics = _metrics_dir(tmp_path)
    durations = _write_durations(metrics, [10.0, 5.0, 4.0])
    baseline = metrics / "pytest_fast_duration_baseline.json"

    for _ in range(2):  # the second run (a bundle's release check, in CI) must not judge against the first
        code, error, result = _evaluate_pytest_fast_duration_guard(durations, baseline, wall_seconds=77.03)
        assert (code, error, result["ok"], result["baseline"]) == (0, "", None, "none")
    assert not baseline.exists()
    assert sorted(p.name for p in metrics.iterdir()) == ["pytest_durations_fast.json"]


def test_the_entry_sums_and_the_wall_clock_are_reported_apart_under_their_own_names(tmp_path: Path) -> None:
    durations = _write_durations(_metrics_dir(tmp_path), [3.0] * 12 + [1.0] * 13)
    _, _, result = _evaluate_pytest_fast_duration_guard(durations, tmp_path / "none.json", wall_seconds=77.034)
    assert result["entries"] == 25
    assert result["slowest_entries_seconds"] == 49.0  # the 25 slowest entries, not the suite
    assert result["slowest10_seconds"] == 30.0
    assert result["wall_seconds"] == 77.03  # the step's elapsed time, measured separately
    assert "total" not in result and "top10" not in result


def test_the_old_self_written_baselines_are_left_alone_and_not_used(tmp_path: Path) -> None:
    metrics = _metrics_dir(tmp_path)
    durations = _write_durations(metrics, [50.0, 50.0, 50.0])
    (metrics / "pytest_fast_total_seconds.txt").write_text("1.00", encoding="utf-8")  # would be a huge "regression"
    (metrics / "pytest_fast_top10_seconds.txt").write_text("1.00", encoding="utf-8")

    code, _, result = _evaluate_pytest_fast_duration_guard(durations, metrics / "pytest_fast_duration_baseline.json")

    assert (code, result["ok"]) == (0, None)
    assert result["legacy_baseline_files"] == ["pytest_fast_top10_seconds.txt", "pytest_fast_total_seconds.txt"]
    assert (metrics / "pytest_fast_total_seconds.txt").read_text(encoding="utf-8") == "1.00"


def test_recording_keeps_provenance_and_the_earlier_baselines(tmp_path: Path) -> None:
    metrics = _metrics_dir(tmp_path)
    baseline = _record(metrics, [10.0, 5.0, 4.0])
    first = json.loads(baseline.read_text(encoding="utf-8"))
    assert first["recorded_at"] == "2026-10-30T12:00:00Z"
    assert {k: first[k] for k in ("platform", "python")} == _pytest_fast_identity()
    assert (first["entries"], first["slowest_entries_seconds"], first["history"]) == (3, 19.0, [])
    assert "git_sha" in first

    _record(metrics, [11.0, 5.0, 4.0])
    second = json.loads(baseline.read_text(encoding="utf-8"))
    assert second["slowest_entries_seconds"] == 20.0
    assert second["history"] == [{k: v for k, v in first.items() if k != "history"}]


def test_a_recorded_baseline_catches_a_regression_and_is_not_overwritten(tmp_path: Path) -> None:
    metrics = _metrics_dir(tmp_path)
    baseline = _record(metrics, [10.0, 5.0, 4.0])
    before = baseline.read_text(encoding="utf-8")

    durations = _write_durations(metrics, [30.0, 20.0, 10.0])  # 19 -> 60 s: +41 s and x3.2
    code, error, result = _evaluate_pytest_fast_duration_guard(durations, baseline)
    assert (code, result["ok"]) == (2, False)
    assert "regressed" in error and "2026-10-30T12:00:00Z" in error

    durations = _write_durations(metrics, [11.0, 5.0, 4.0])  # within +20 s
    code, _, result = _evaluate_pytest_fast_duration_guard(durations, baseline)
    assert (code, result["ok"]) == (0, True)
    assert baseline.read_text(encoding="utf-8") == before  # a passing run doesn't move the baseline either


@pytest.mark.parametrize(("field", "value"), [("platform", "elsewhere"), ("python", "2.7"), ("entries", 25)])
def test_a_baseline_from_another_platform_python_or_entry_count_is_not_a_comparison(
    tmp_path: Path, field: str, value: object
) -> None:
    metrics = _metrics_dir(tmp_path)
    baseline = _record(metrics, [10.0, 5.0, 4.0], **{field: value})
    durations = _write_durations(metrics, [30.0, 20.0, 10.0])

    code, _, result = _evaluate_pytest_fast_duration_guard(durations, baseline)

    assert (code, result["ok"]) == (0, None)
    assert f"{field} differ" in result["baseline"]


def test_an_unreadable_baseline_is_reported_not_trusted(tmp_path: Path) -> None:
    metrics = _metrics_dir(tmp_path)
    baseline = metrics / "pytest_fast_duration_baseline.json"
    baseline.write_text("{not json", encoding="utf-8")
    durations = _write_durations(metrics, [30.0])

    code, _, result = _evaluate_pytest_fast_duration_guard(durations, baseline)

    assert (code, result["ok"]) == (0, None)
    assert result["baseline"].startswith("unreadable")
    assert baseline.read_text(encoding="utf-8") == "{not json"
