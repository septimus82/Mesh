"""#422 CI-422A3: the terrain stroke's enforced performance gate (tooling/terrain_advisory.py), which replaced the
absolute 60 ms frame median: its thresholds, that it fails closed on any missing, incomplete or invalid measurement,
that the observed runs and the injected faults land where the evidence says, and that the gated test records it before
any assertion and judges it last. No GL (tests/test_terrain_gpu.py measures it on real runs)."""

from __future__ import annotations

import ast
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))
import terrain_advisory as ta  # noqa: E402

pytestmark = pytest.mark.fast
N = ta.STEPS


def _trial(control: float, sculpt: float, release: float = 130.0, control_release: float = 40.0,
           committed: bool = True) -> dict[str, Any]:
    return {"control": [control - 1, control, control + 1] * 3 + [control],
            "sculpt": [sculpt - 2, sculpt, sculpt + 2] * 3 + [sculpt],
            "release": release, "control_release": control_release, "committed": committed}


def _trials(n: int = ta.TRIALS, **kwargs: Any) -> list[dict[str, Any]]:
    return [_trial(40.0, 54.0, **kwargs) for _ in range(n)]


def _judge(trials: Any, gate: Any = 57.0, cpu: Any = 24.0, **kwargs: Any) -> dict[str, Any]:
    return ta.summarise(trials, gate, cpu, gate_frames=kwargs.pop("gate_frames", ta.GATE_FRAMES),
                        required_gate_frames=ta.GATE_FRAMES, **kwargs)


def _observed(ratio: float, release_per_cpu: float, frame_per_cpu: float, cpu: float) -> dict[str, Any]:
    """A run with these measurements: 6 valid trials of that ratio and release, and that gated frame median."""
    control = 40.0
    trials = [_trial(control, control * ratio, 40.0 + release_per_cpu * cpu, 40.0) for _ in range(ta.TRIALS)]
    return _judge(trials, frame_per_cpu * cpu, cpu)


def test_the_thresholds_and_the_requirements_are_the_evidence_s() -> None:
    assert ta.THRESHOLDS == {"ratio": 1.6, "release_per_cpu": 8.0, "frame_per_cpu": 3.2}
    assert (ta.WARM, ta.TRIALS, ta.STEPS, ta.GATE_FRAMES, ta.LEGACY_FRAME_MS) == (1, 6, 10, 48, 60.0)


def test_it_works_out_each_measurement_and_passes_a_complete_fault_free_run() -> None:
    trials = [_trial(40.0, 54.0, 130.0, 40.0), _trial(42.0, 56.7, 134.0, 44.0), _trial(41.0, 55.35, 128.0, 41.0)] * 2
    out = _judge(trials, overhead_s=8.123)
    assert out["verdict"] == "PASS" and out["problems"] == [] and out["complete"] and out["crossed"] == []
    assert out["ratio"] == pytest.approx(1.35, abs=1e-3)  # each trial's sculpt / control median, then their median
    assert out["incremental_ms"] == pytest.approx(14.35, abs=0.01)
    assert out["release_extra_ms"] == pytest.approx(90.0)  # release - the plain frame after it, median of the trials
    assert out["release_per_cpu"] == pytest.approx(90.0 / 24.0, abs=1e-3)
    assert out["frame_per_cpu"] == pytest.approx(57.0 / 24.0, abs=1e-3)
    assert out["sculpt_per_cpu"] == pytest.approx(55.35 / 24.0, abs=1e-3)
    assert (out["trials"], out["required_trials"], out["cpu_ms"], out["gate_frame_ms"], out["overhead_s"]) == (
        6, 6, 24.0, 57.0, 8.12)
    assert out["legacy_60ms"] == {"report_only": True, "limit_ms": 60.0, "frame_median_ms": 57.0,
                                  "would_have_failed": False}


def test_a_crossing_fails_and_names_every_threshold_crossed() -> None:
    out = _judge(_trials(release=1000.0), gate=90.0)  # ratio 1.35 but release 960 ms, frame 90 / 24
    assert out["crossed"] == ["frame_per_cpu", "release_per_cpu"] and out["complete"]
    assert out["problems"] == ["frame_per_cpu 3.750 > 3.2", "release_per_cpu 40.000 > 8.0"]
    assert out["verdict"] == "FAIL: frame_per_cpu 3.750 > 3.2; release_per_cpu 40.000 > 8.0"
    out = _judge([_trial(40.0, 80.0)] * ta.TRIALS)
    assert out["crossed"] == ["ratio"] and out["verdict"].startswith("FAIL: ratio 2.000 > 1.6")


def test_at_a_threshold_is_within_it() -> None:
    out = _judge([_trial(40.0, 64.0, 240.0, 40.0)] * ta.TRIALS, 80.0, 25.0)  # 1.6; 200 / 25 = 8; 80 / 25 = 3.2
    assert (out["ratio"], out["release_per_cpu"], out["frame_per_cpu"]) == (1.6, 8.0, 3.2)
    assert out["verdict"] == "PASS"


# Every fault-free observation with these measurements (Extended, CI-422A2's report-only week): (run, OS, CPU,
# legacy 60 ms median, ratio, calibrated release, calibrated frame, cpu_ms). The two 8370C rows failed the old gate.
OBSERVED = [
    ("42858598998", "Windows", "Xeon 8573C", 57.17, 1.32, 4.009, 2.642, 21.64),
    ("42858598998", "Linux", "EPYC 7763", 48.9, 1.364, 3.681, 2.449, 19.97),
    ("42871555328", "Linux", "Xeon 8370C", 50.78, 1.324, 3.478, 2.63, 19.31),
    ("42871555328", "Windows", "Xeon 6973P-C", 49.97, 1.305, 4.056, 2.756, 18.13),
    ("42886645746", "Windows", "EPYC 7763", 56.89, 1.362, 3.645, 2.251, 25.27),
    ("42886645746", "Linux", "EPYC 7763", 52.75, 1.375, 3.968, 2.628, 20.07),
    ("42915543045", "Windows", "EPYC 9V74", 46.75, 1.322, 3.576, 2.445, 19.12),
    ("42915543045", "Linux", "EPYC 9V74", 39.02, 1.338, 3.364, 2.454, 15.9),
    ("42919513624", "Linux", "EPYC 7763", 47.7, 1.361, 2.22, 1.438, 33.17),
    ("42919513624", "Windows", "EPYC 7763", 56.63, 1.37, 3.695, 2.332, 24.28),
    ("42965042459", "Linux", "EPYC 7763", 49.61, 1.357, 3.704, 2.479, 20.01),
    ("42965042459 a1", "Windows", "Xeon 8370C", 67.09, 1.288, 3.621, 2.614, 25.67),
    ("42965042459 a2", "Windows", "Xeon 8370C", 60.33, 1.329, 3.634, 2.589, 23.3),
]


@pytest.mark.parametrize(("run", "os_", "cpu_name", "legacy", "ratio", "release", "frame", "cpu"), OBSERVED,
                         ids=[f"{r[0]}-{r[1]}" for r in OBSERVED])
def test_every_observed_fault_free_run_passes_including_the_old_gate_s_false_failures(
        run: str, os_: str, cpu_name: str, legacy: float, ratio: float, release: float, frame: float,
        cpu: float) -> None:
    out = _observed(ratio, release, frame, cpu)
    assert out["verdict"] == "PASS", (run, os_, cpu_name, out)
    assert out["legacy_60ms"]["would_have_failed"] is (legacy >= 60), (run, legacy, out["legacy_60ms"])


# The injected faults' mildest values on any runner (CI-422A2 detection runs; evidence/422a-terrain-timing).
@pytest.mark.parametrize(("fault", "ratio", "release", "frame", "crossed"), [
    ("rebuild every chunk (mildest of 13 runs)", 1.816, 3.63, 2.6, ["ratio"]),
    ("reload on release (mildest Linux run)", 1.361, 12.533, 2.5, ["release_per_cpu"]),
    ("reload on release (mildest Windows run)", 1.32, 41.673, 2.5, ["release_per_cpu"]),
    ("rebuild every chunk, evidence branch's mildest frame", 1.84, 3.4, 3.30, ["frame_per_cpu", "ratio"]),
])
def test_the_injected_faults_fail(fault: str, ratio: float, release: float, frame: float, crossed: list[str]) -> None:
    out = _observed(ratio, release, frame, 20.0)
    assert out["crossed"] == crossed and out["verdict"].startswith("FAIL: "), (fault, out)


@pytest.mark.parametrize("cpu", [None, 0, -3.0, float("nan"), float("inf"), "24", True])
def test_without_a_usable_calibration_it_fails(cpu: object) -> None:
    out = _judge(_trials(), cpu=cpu)
    assert out["verdict"].startswith("FAIL: ") and not out["complete"]
    assert "incomplete: runner calibration (cpu_ms)" in out["problems"]
    assert "release_per_cpu: not measured" in out["problems"] and "frame_per_cpu: not measured" in out["problems"]
    assert out["ratio"] == pytest.approx(1.35, abs=1e-3)  # (still reported)


@pytest.mark.parametrize("trials", [None, [], "trials", [None], [{}], _trials(ta.TRIALS - 1), _trials(ta.TRIALS + 1)])
def test_anything_but_the_required_trials_fails(trials: object) -> None:
    out = _judge(trials)
    n = len(trials) if isinstance(trials, list) and all(isinstance(t, dict) and t for t in trials) else 0
    assert out["verdict"].startswith("FAIL: ") and not out["complete"], out
    assert f"incomplete: {n} of {ta.TRIALS} interleaved trials valid" in out["problems"], out


def _broken(change: str) -> dict[str, Any]:
    t = _trial(40.0, 54.0)
    if change == "a block cut short":
        t["sculpt"] = t["sculpt"][:-1]
    elif change == "a block with an extra frame":
        t["control"] = [*t["control"], 40.0]
    elif change == "a non-finite frame":
        t["sculpt"][3] = float("nan")
    elif change == "an infinite frame":
        t["control"][0] = float("inf")
    elif change == "a zero frame":
        t["control"][0] = 0.0
    elif change == "a frame that isn't a number":
        t["sculpt"][0] = "54"
    elif change == "no frames":
        t["control"] = None
    elif change == "a stroke not committed":
        t["committed"] = False
    elif change == "committed as truthy, not True":
        t["committed"] = 1
    elif change == "no release timing":
        t["release"] = None
    elif change == "a non-finite release":
        t["control_release"] = float("nan")
    return t


@pytest.mark.parametrize("change", ["a block cut short", "a block with an extra frame", "a non-finite frame",
                                    "an infinite frame", "a zero frame", "a frame that isn't a number", "no frames",
                                    "a stroke not committed", "committed as truthy, not True", "no release timing",
                                    "a non-finite release"])
def test_one_invalid_trial_fails_the_gate_even_with_the_rest_valid(change: str) -> None:
    trials = _trials()
    trials[2] = _broken(change)
    out = _judge(trials)
    assert out["verdict"].startswith("FAIL: ") and not out["complete"], (change, out)
    assert out["missing"][0].startswith("trial 3: ") and out["trials"] == ta.TRIALS - 1, (change, out)
    assert out["ratio"] == pytest.approx(1.35, abs=1e-3)  # what was valid is still reported


@pytest.mark.parametrize(("gate", "frames", "why"), [
    (None, ta.GATE_FRAMES, "gated stroke frame median"), (float("nan"), ta.GATE_FRAMES, "gated stroke frame median"),
    (0.0, ta.GATE_FRAMES, "gated stroke frame median"), (57.0, ta.GATE_FRAMES - 1, "gated stroke: 47 of 48 frames"),
    (57.0, None, "gated stroke: None of 48 frames"), (57.0, 0, "gated stroke: 0 of 48 frames"),
])
def test_a_gated_stroke_cut_short_or_unmeasured_fails(gate: Any, frames: Any, why: str) -> None:
    out = _judge(_trials(), gate=gate, gate_frames=frames)
    assert out["verdict"].startswith("FAIL: ") and f"incomplete: {why}" in out["problems"], out


def test_a_measurement_error_fails_even_with_complete_data() -> None:
    out = _judge(_trials(), error="RuntimeError: out of memory")
    assert out["problems"] == ["incomplete: measurement failed: RuntimeError: out of memory"]
    assert out["verdict"] == "FAIL: incomplete: measurement failed: RuntimeError: out of memory"
    assert out["ratio"] == pytest.approx(1.35, abs=1e-3)


def test_the_legacy_60_ms_comparison_is_reported_never_judged() -> None:
    for gate, failed in ((59.99, False), (60.0, True), (67.09, True)):
        out = _judge(_trials(), gate=gate, cpu=25.0)
        assert out["legacy_60ms"]["would_have_failed"] is failed and out["verdict"] == "PASS", out
    assert _judge(_trials(), gate=None)["legacy_60ms"]["would_have_failed"] is None


def test_what_it_records_is_json_and_it_never_raises() -> None:
    for out in (_judge(_trials()), ta.summarise(None, float("nan"), None, error="x", gate_frames=object(),
                                                required_gate_frames=48), ta.summarise({"x": 1}, "57", [], steps=0)):
        assert json.loads(json.dumps(out, allow_nan=False)) == out
        assert out["verdict"] == "PASS" or out["problems"]


@pytest.mark.integration
def test_a_failure_mid_measurement_is_reported_and_fails_the_gate() -> None:
    # m20b_sculpt_study._advisory: the trials raise part way; the calibration still runs; the verdict fails (fail-closed)
    import m20b_sculpt_study as study

    def boom(_name: str) -> None:
        raise RuntimeError("the Raise button is gone")

    d = SimpleNamespace(button=boom, studio=SimpleNamespace(hd2d=SimpleNamespace(stroke=None)),
                        arcade=SimpleNamespace(key=None, MOUSE_BUTTON_LEFT=1))
    out = study._advisory(d, 57.0, gate_frames=ta.GATE_FRAMES, required_gate_frames=ta.GATE_FRAMES)
    assert out["verdict"].startswith("FAIL: ") and out["trials"] == 0, out
    assert "incomplete: measurement failed: RuntimeError: the Raise button is gone" in out["problems"], out
    assert out["cpu_ms"] and math.isfinite(out["cpu_ms"]), out  # the diagnostics that were measurable


# --- the gated test (tests/test_terrain_gpu.py) ----------------------------------------------------------------------

def _gated_test() -> ast.FunctionDef:
    tree = ast.parse((REPO / "tests" / "test_terrain_gpu.py").read_text(encoding="utf-8"))
    return next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                and n.name == "test_studio_sculpts_live_one_stroke_one_undo_step")


def test_the_gated_test_records_everything_before_any_assertion() -> None:
    fn = _gated_test()
    records = []
    for i, n in enumerate(fn.body):
        call = n.value if isinstance(n, ast.Expr) else None
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "record_testsuite_property":
            records.append((i, ast.literal_eval(call.args[0])))
    assert [name for _i, name in records] == ["measure.terrain_stroke", "measure.terrain_advisory"]
    first_assert = next(i for i, n in enumerate(fn.body) if isinstance(n, ast.Assert))
    assert records[-1][0] < first_assert, "recorded before any assertion, so failing runs report it too"


def test_the_gate_is_enforced_last_with_the_zero_reload_and_commit_guards_kept() -> None:
    fn = _gated_test()
    asserts = [ast.unparse(n) for n in fn.body if isinstance(n, ast.Assert)]
    # functional first, so a slow runner can't hide a functional regression; then the commit guard; the verdict last
    assert asserts[0] == ("assert (s['room_reloads'], s['scene_loads'], c['room_reloads'], c['scene_loads']) == "
                          "(0, 0, 0, 0), (s, c)")
    assert asserts[-2:] == ["assert s['commit_ms'] < 200, s",
                            "assert gate['verdict'] == 'PASS' and gate['problems'] == [], gate"]
    assert sum("gate" in a for a in asserts) == 1
    assert not any("frame_ms" in a or "60" in a or "legacy" in a for a in asserts), "the 60 ms median is report-only"
