from __future__ import annotations

from pathlib import Path

import pytest

from tooling import ruff_gate

pytestmark = pytest.mark.fast


def test_ruff_gate_drift_immunity_for_shifted_lines() -> None:
    message = "Local variable `x` is assigned to but never used"
    baseline = [{"filename": "engine/example.py", "location": {"row": 10, "column": 1}, "code": "F841", "message": message}]
    current = [{"filename": "engine/example.py", "location": {"row": 99, "column": 12}, "code": "F841", "message": message}]

    baseline_lines = ruff_gate.normalize_findings(baseline, Path.cwd())
    current_lines = ruff_gate.normalize_findings(current, Path.cwd())

    assert ruff_gate.find_new_findings(current_lines, baseline_lines) == []


def test_ruff_gate_fails_on_new_finding() -> None:
    baseline_lines = ["engine/example.py: F841 Local variable `x` is assigned to but never used"]
    current_lines = [*baseline_lines, "engine/example.py: F821 Undefined name `missing`"]

    assert ruff_gate.find_new_findings(current_lines, baseline_lines) == ["engine/example.py: F821 Undefined name `missing`"]


def test_ruff_gate_fails_on_duplicate_growth() -> None:
    baseline_lines = ["engine/example.py: W293 Blank line contains whitespace"]
    current_lines = [*baseline_lines, *baseline_lines]

    assert ruff_gate.find_new_findings(current_lines, baseline_lines) == ["engine/example.py: W293 Blank line contains whitespace"]


def test_ruff_gate_update_baseline_writes_normalized_occurrences(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    baseline_path = tmp_path / "ruff_baseline.txt"
    monkeypatch.setattr(ruff_gate, "BASELINE_PATH", baseline_path)
    monkeypatch.setattr(ruff_gate, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        ruff_gate,
        "_run_ruff",
        lambda repo_root: (
            1,
            [
                "engine/example.py: W293 Blank line contains whitespace",
                "engine/example.py: W293 Blank line contains whitespace",
            ],
        ),
    )

    assert ruff_gate.main(["--update-baseline"]) == 0

    assert baseline_path.read_text(encoding="utf-8").splitlines() == [
        "engine/example.py: W293 Blank line contains whitespace",
        "engine/example.py: W293 Blank line contains whitespace",
    ]


def test_ruff_gate_day_one_green() -> None:
    assert ruff_gate.main([]) == 0


def test_ruff_baseline_contains_no_f821_entries() -> None:
    text = ruff_gate.BASELINE_PATH.read_text(encoding="utf-8")

    assert " F821 " not in text
