"""GPU-lane measurements and runner calibration (#422): reported on every run, judged against nothing, never failing a
lane, and the terrain frame-time assertion they explain unchanged."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from tooling import runner_calibration, test_tiers

pytestmark = [pytest.mark.fast]

REPO = Path(__file__).resolve().parents[1]
JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" errors="0" failures="0" skipped="0" tests="2" time="3.5">
<properties>
<property name="measure.terrain_stroke" value='{"frame_ms": {"median": 57.1, "n": 48}, "commit_ms": 17.6}' />
<property name="measure.note" value="not json" />
<property name="something_else" value="1" />
</properties>
<testcase classname="tests.test_terrain_gpu" name="test_a" time="3.0" />
<testcase classname="tests.test_terrain_gpu" name="test_b" time="0.5" />
</testsuite></testsuites>
"""


def test_a_lane_summary_carries_the_values_tests_recorded(tmp_path: Path) -> None:
    junit = tmp_path / "pytest_gpu.xml"
    junit.write_text(JUNIT, encoding="utf-8")
    run = test_tiers.summarize_junit(junit)
    assert (run.selected, run.passed) == (2, 2)
    assert run.measurements == {"terrain_stroke": {"frame_ms": {"median": 57.1, "n": 48}, "commit_ms": 17.6},
                                "note": "not json"}


def test_a_failing_test_beside_a_measurement_is_still_reported_as_failed(tmp_path: Path) -> None:
    junit = tmp_path / "pytest_gpu.xml"
    junit.write_text(JUNIT.replace('name="test_b" time="0.5" />',
                                   'name="test_b" time="0.5"><failure message="assert (62.63 &lt; 60)" /></testcase>'),
                     encoding="utf-8")
    run = test_tiers.summarize_junit(junit)
    assert run.failed == ["tests.test_terrain_gpu::test_b"] and run.passed == 1
    assert run.measurements["terrain_stroke"]["frame_ms"]["median"] == 57.1


def test_only_the_gpu_lane_calibrates_the_runner() -> None:
    assert {name for name, tier in test_tiers.TIERS.items() if tier.calibrate} == {"gpu"}


@pytest.mark.parametrize("broken", ["raises", "garbage", "nothing"])
def test_a_calibration_that_fails_is_reported_never_raised(monkeypatch: pytest.MonkeyPatch, broken: str) -> None:
    def run(*_a: Any, **_k: Any) -> subprocess.CompletedProcess[str]:
        if broken == "raises":
            raise subprocess.TimeoutExpired("python", 120)
        return subprocess.CompletedProcess([], 1, "Traceback ..." if broken == "garbage" else "", "")

    monkeypatch.setattr(test_tiers.subprocess, "run", run)
    result = test_tiers.runner_calibration()
    assert set(result) == {"error"} and result["error"]


def test_the_calibration_measures_the_cpu_even_when_it_cant_draw(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_gl() -> float:
        raise RuntimeError("no GL context")

    monkeypatch.setattr(runner_calibration, "gl_frame_ms", no_gl)
    result = runner_calibration.calibrate()
    assert result["gl_error"] == "RuntimeError: no GL context" and "gl_frame_ms" not in result
    assert isinstance(result["cpu"], str) and result["cpu"] and int(result["vcpus"]) >= 1 and result["cpu_ms"] > 0


def test_the_terrain_stroke_is_recorded_before_its_unchanged_assertions() -> None:
    source = (REPO / "tests" / "test_terrain_gpu.py").read_text(encoding="utf-8")
    body = source[source.index("def test_studio_sculpts_live_one_stroke_one_undo_step"):]
    body = body[:body.index("\n\n\n")]
    record = body.index('record_testsuite_property("measure.terrain_stroke"')
    # The 60 ms limit and the rest of the assertion, byte for byte as before (#422: never weakened).
    limit = 'assert s["frame_ms"]["median"] < 60 and s["commit_ms"] < 200, s  # no room reload per click'
    assert body.count(limit) == 1
    assert record < body.index("    assert "), "recorded before any assertion, so failing runs report it too"


def test_the_lane_summary_shows_the_runner_and_the_measurements() -> None:
    text = (REPO / ".github" / "workflows" / "extended.yml").read_text(encoding="utf-8")
    step = text[text.index("- name: Lane summary"):text.index("- name: Upload lane reports")]
    assert 'foreach ($when in "before", "after")' in step and "$s.runner.$when" in step
    assert "llvmpipe frame $($c.gl_frame_ms) ms $($c.gl_error)" in step and "no calibration: $($c.error)" in step
    assert "$s.measurements.PSObject.Properties" in step
