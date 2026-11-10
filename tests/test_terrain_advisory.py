"""#422 CI-422A2: the terrain stroke's report-only measurements (tooling/terrain_advisory.py), and that the gated test
records them without ever judging them. No GL (tests/test_terrain_gpu.py measures them on real runs)."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))
import terrain_advisory as ta  # noqa: E402

pytestmark = pytest.mark.fast


def _trial(control: float, sculpt: float, release: float = 130.0, control_release: float = 40.0,
           committed: bool = True) -> dict:
    return {"control": [control - 1, control, control + 1], "sculpt": [sculpt - 2, sculpt, sculpt + 2],
            "release": release, "control_release": control_release, "committed": committed}


def test_the_thresholds_are_the_evidence_s() -> None:
    assert ta.THRESHOLDS == {"ratio": 1.6, "release_per_cpu": 8.0, "frame_per_cpu": 3.2}


def test_it_works_out_each_measurement_from_the_trials() -> None:
    trials = [_trial(40.0, 54.0, 130.0, 40.0), _trial(42.0, 56.7, 134.0, 44.0), _trial(41.0, 55.35, 128.0, 41.0)]
    out = ta.summarise(trials, 57.0, 24.0, overhead_s=8.123)
    assert out["complete"] and out["missing"] == [] and out["crossed"] == []
    assert out["ratio"] == pytest.approx(1.35, abs=1e-3)  # each trial's sculpt / control median, then their median
    assert out["incremental_ms"] == pytest.approx(14.35, abs=0.01)
    assert out["release_extra_ms"] == pytest.approx(90.0)  # release - the plain frame after it, median of the trials
    assert out["release_per_cpu"] == pytest.approx(90.0 / 24.0, abs=1e-3)
    assert out["frame_per_cpu"] == pytest.approx(57.0 / 24.0, abs=1e-3)
    assert out["sculpt_per_cpu"] == pytest.approx(55.35 / 24.0, abs=1e-3)
    assert (out["trials"], out["cpu_ms"], out["gate_frame_ms"], out["overhead_s"]) == (3, 24.0, 57.0, 8.12)
    assert out["control_ms"] == 41.0 and out["sculpt_ms"] == 55.35
    assert out["report_only"] is True and out["advisory"] == "within the advisory thresholds"


def test_a_crossing_is_labelled_and_reported_never_raised() -> None:
    slow = [_trial(40.0, 80.0, 1000.0, 40.0)] * 3  # ratio 2, release 960 ms
    out = ta.summarise(slow, 90.0, 24.0)
    assert out["crossed"] == ["frame_per_cpu", "ratio", "release_per_cpu"] and out["complete"]
    assert out["advisory"].startswith("CROSSED (advisory, not failed): ")
    assert "ratio 2.000 > 1.6" in out["advisory"] and "release_per_cpu 40.000 > 8.0" in out["advisory"]


def test_at_a_threshold_is_within_it() -> None:
    out = ta.summarise([_trial(40.0, 64.0, 240.0, 40.0)], 80.0, 25.0)  # ratio 1.6, release 200 / 25 = 8, 80 / 25 = 3.2
    assert (out["ratio"], out["release_per_cpu"], out["frame_per_cpu"]) == (1.6, 8.0, 3.2)
    assert out["crossed"] == [] and out["complete"]


@pytest.mark.parametrize("cpu", [None, 0, -3.0, float("nan"), float("inf"), "24", True])
def test_without_a_usable_calibration_only_the_ratio_is_given(cpu: object) -> None:
    out = ta.summarise([_trial(40.0, 54.0)], 57.0, cpu)
    assert not out["complete"] and "runner calibration (cpu_ms)" in out["missing"]
    assert out["ratio"] == pytest.approx(1.35, abs=1e-3)
    assert out["release_per_cpu"] is None and out["frame_per_cpu"] is None and out["cpu_ms"] is None
    assert out["advisory"].startswith("INCOMPLETE (advisory, not failed): ")


@pytest.mark.parametrize("trials", [None, [], "trials", [None], [{}]])
def test_without_trials_nothing_is_made_up(trials: object) -> None:
    out = ta.summarise(trials, 57.0, 24.0)
    assert not out["complete"] and out["trials"] == 0
    assert out["ratio"] is None and out["release_per_cpu"] is None
    assert out["frame_per_cpu"] == pytest.approx(57.0 / 24.0, abs=1e-3)  # (the backstop needs no trials)


def test_unusable_trials_are_named_and_left_out() -> None:
    trials = [_trial(40.0, 54.0), _trial(40.0, 54.0, committed=False), {"control": [0.0], "sculpt": [50.0], "committed": True},
              {"control": [float("nan")], "sculpt": [50.0], "committed": True},
              {**_trial(40.0, 54.0), "release": None}]
    out = ta.summarise(trials, 57.0, 24.0)
    assert out["missing"] == ["trial 2: its stroke wasn't committed", "trial 3: no usable frames",
                              "trial 4: no usable frames", "trial 5: no release timing"]
    assert out["trials"] == 2 and out["ratio"] == pytest.approx(1.35, abs=1e-3) and not out["complete"]


def test_a_failed_measurement_is_recorded_with_what_was_measured() -> None:
    out = ta.summarise([], None, 24.0, error="RuntimeError: out of memory")
    assert out["missing"][:2] == ["measurement failed: RuntimeError: out of memory", "gated stroke frame median"]
    assert out["advisory"].startswith("INCOMPLETE (advisory, not failed): measurement failed: RuntimeError")


def test_a_crossing_from_an_incomplete_measurement_says_both() -> None:
    out = ta.summarise([_trial(40.0, 80.0)], None, 24.0)
    assert out["crossed"] == ["ratio"] and not out["complete"]
    assert out["advisory"].startswith("CROSSED (advisory, not failed): ratio 2.000 > 1.6; INCOMPLETE: ")


def test_what_it_records_is_json() -> None:
    for out in (ta.summarise([_trial(40.0, 54.0)], 57.0, 24.0), ta.summarise(None, float("nan"), None, error="x")):
        assert json.loads(json.dumps(out, allow_nan=False)) == out


def _gated_test() -> ast.FunctionDef:
    tree = ast.parse((REPO / "tests" / "test_terrain_gpu.py").read_text(encoding="utf-8"))
    return next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                and n.name == "test_studio_sculpts_live_one_stroke_one_undo_step")


def test_the_gated_test_records_them_before_any_assertion_and_never_judges_them() -> None:
    fn = _gated_test()
    records = []
    for i, n in enumerate(fn.body):
        call = n.value if isinstance(n, ast.Expr) else None
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "record_testsuite_property":
            records.append((i, ast.literal_eval(call.args[0])))
    assert [name for _i, name in records] == ["measure.terrain_stroke", "measure.terrain_advisory"]
    first_assert = next(i for i, n in enumerate(fn.body) if isinstance(n, ast.Assert))
    assert records[-1][0] < first_assert, "recorded before any assertion, so failing runs report it too"
    for node in ast.walk(fn):
        if isinstance(node, ast.Assert):
            assert "advisory" not in ast.unparse(node), "report-only: never asserted"


def test_the_60_ms_gate_and_the_zero_reload_guard_stay_as_they_are() -> None:
    body = ast.unparse(_gated_test())
    assert "assert s['frame_ms']['median'] < 60 and s['commit_ms'] < 200, s" in body
    assert "assert (s['room_reloads'], s['scene_loads'], c['room_reloads'], c['scene_loads']) == (0, 0, 0, 0), (s, c)" in body
