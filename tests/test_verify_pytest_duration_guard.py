from __future__ import annotations

import json
from pathlib import Path

from mesh_cli.verify import _evaluate_pytest_fast_duration_guard


def _write_metrics(path: Path, seconds: list[float]) -> None:
    payload = [{"nodeid": f"tests/test_{idx}.py::test_{idx}", "seconds": value} for idx, value in enumerate(seconds)]
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_pytest_duration_guard_pass_updates_baseline(tmp_path: Path) -> None:
    metrics_path = tmp_path / "pytest_durations_fast.json"
    total_path = tmp_path / "pytest_fast_total_seconds.txt"
    top10_path = tmp_path / "pytest_fast_top10_seconds.txt"

    _write_metrics(metrics_path, [10.0, 5.0, 4.0])
    total_path.write_text("30.00", encoding="utf-8")
    top10_path.write_text("20.00", encoding="utf-8")

    code, error, total, top10, ok = _evaluate_pytest_fast_duration_guard(metrics_path, total_path, top10_path)

    assert code == 0
    assert error == ""
    assert ok is True
    assert total == 19.0
    assert top10 == 19.0
    assert total_path.read_text(encoding="utf-8").strip() == "19.00"
    assert top10_path.read_text(encoding="utf-8").strip() == "19.00"


def test_pytest_duration_guard_fail_on_regression(tmp_path: Path) -> None:
    metrics_path = tmp_path / "pytest_durations_fast.json"
    total_path = tmp_path / "pytest_fast_total_seconds.txt"
    top10_path = tmp_path / "pytest_fast_top10_seconds.txt"

    _write_metrics(metrics_path, [50.0, 50.0, 50.0])
    total_path.write_text("100.00", encoding="utf-8")
    top10_path.write_text("80.00", encoding="utf-8")

    code, error, total, top10, ok = _evaluate_pytest_fast_duration_guard(metrics_path, total_path, top10_path)

    assert code == 2
    assert "regressed" in error
    assert ok is False
    assert total == 150.0
    assert top10 == 150.0
