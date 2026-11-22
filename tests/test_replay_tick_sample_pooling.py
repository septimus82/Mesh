"""T-07: short replay episodes judge tick p95 over a pooled sample, never over their own handful of ticks."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import mesh_cli
from mesh_cli import episode as episode_module
from mesh_cli import replays as replays_module
from mesh_cli.episode import MAX_TIMING_EXECUTIONS, _compute_percentile_ms, pooled_timing_summary

BUDGETS = {"max_tick_ms_max": 150.0, "max_tick_ms_p95": 50.0, "max_total_ms": 5000.0}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _suite(tmp_path: Path, case_id: str) -> Path:
    suite = tmp_path / "suite.json"
    case = {
        "id": case_id,
        "scene": next(c["scene"] for c in _repo_suite() if c["id"] == case_id),
        "script": f"replays/{case_id}.json",
        "golden": f"replays/golden/{case_id}_golden.json",
        "budgets": BUDGETS,
    }
    suite.write_text(json.dumps([case]), encoding="utf-8")
    return suite


def _repo_suite() -> list[dict]:
    return json.loads(Path("replays/suite.json").read_text(encoding="utf-8"))


def _run_suite(tmp_path: Path, case_id: str) -> tuple[int, dict]:
    code = mesh_cli.main(
        ["replays", "run", "--suite", str(_suite(tmp_path, case_id)), "--out-dir", str(tmp_path / "out"),
         "--seed", "123", "--budgets-only-on", "all", "--quiet"]
    )
    return code, _read_json(tmp_path / "out" / case_id / "performance.json")


def _replay_check(case_id: str, out_dir: Path, *, min_samples: int) -> int:
    case = next(c for c in _repo_suite() if c["id"] == case_id)
    return episode_module.handle(
        argparse.Namespace(
            command="episode", episode_command="replay-check", scene=case["scene"], script=f"replays/{case_id}.json",
            out_dir=str(out_dir), seed=123, quiet=True, episode_json=False, timing_min_samples=min_samples,
        )
    )


# --- statistics ---------------------------------------------------------------------------------------------------


def test_single_short_run_p95_is_its_max() -> None:
    """The base behaviour that made ep05 flaky: under 20 samples, one stalled tick IS the p95."""
    ticks = [2.5] * 17 + [65.1]
    assert _compute_percentile_ms(ticks, 0.95) == 65.1


def test_isolated_outlier_does_not_dominate_pooled_p95() -> None:
    pooled = pooled_timing_summary([[2.5] * 18, [2.5] * 17 + [200.0], [2.5] * 18], min_samples=40)
    assert pooled["pooled_count"] == 54
    assert pooled["tick_ms_p95"] == 2.5 < 50.0
    assert pooled["tick_ms_max"] == 200.0  # still reported for diagnosis
    assert pooled["samples_per_execution"] == [18, 18, 18] and pooled["executions"] == 3 and pooled["repeats"] == 1
    assert pooled["min_samples_met"] is True


def test_two_outliers_in_forty_samples_are_ignored_three_are_not() -> None:
    base = [2.5] * 40
    assert _compute_percentile_ms([*base[:38], 200.0, 200.0], 0.95) == 2.5
    assert _compute_percentile_ms([*base[:37], 200.0, 200.0, 200.0], 0.95) == 200.0


def test_budget_judges_pooled_p95_but_keeps_the_canonical_max() -> None:
    limits = replays_module.ReplayBudgets(max_total_ms=3000.0, max_tick_ms_p95=50.0, max_tick_ms_max=150.0)
    ok = replays_module._evaluate_case_budget(
        budgets=limits, performance={"total_ms": 60.0, "tick_ms_p95": 2.5, "tick_ms_max": 65.0}, enforce_budgets=True
    )
    assert ok["ok"] is True
    stalled = replays_module._evaluate_case_budget(
        budgets=limits, performance={"total_ms": 60.0, "tick_ms_p95": 2.5, "tick_ms_max": 200.0}, enforce_budgets=True
    )
    assert [v["metric"] for v in stalled["violations"]] == ["tick_ms_max"]


# --- real replays -------------------------------------------------------------------------------------------------


def test_ep05_pools_enough_samples_and_passes_budget(tmp_path: Path) -> None:
    code, perf = _run_suite(tmp_path, "ep05")
    pooled = perf["performance"]["pooled"]
    assert code == 0 and perf["budget"]["ok"] is True
    assert pooled["pooled_count"] >= replays_module.MIN_TICK_SAMPLES and pooled["min_samples_met"] is True
    assert pooled["executions"] <= MAX_TIMING_EXECUTIONS
    assert perf["performance"]["tick_ms_p95"] == pooled["tick_ms_p95"]
    assert perf["performance"]["tick_ms_count"] == 18  # canonical execution's own samples


def test_sustained_per_tick_slowdown_fails_the_p95_budget(tmp_path: Path, monkeypatch) -> None:
    real_advance = episode_module._advance

    def slow_advance(ctx, dt):  # noqa: ANN001
        time.sleep(0.06)
        return real_advance(ctx, dt)

    monkeypatch.setattr(episode_module, "_advance", slow_advance)
    code, perf = _run_suite(tmp_path, "ep01")
    assert code != 0
    assert "tick_ms_p95" in [v["metric"] for v in perf["budget"]["violations"]]
    assert perf["performance"]["pooled"]["tick_ms_p95"] > 50.0


def test_repeats_do_not_change_replay_state(tmp_path: Path) -> None:
    single, pooled = tmp_path / "single", tmp_path / "pooled"
    assert _replay_check("ep01", single, min_samples=0) == 0
    assert _replay_check("ep01", pooled, min_samples=40) == 0
    for name in ("digests.json", "events.ndjson", "final_state_bundle.json"):
        assert (single / name).read_bytes() == (pooled / name).read_bytes(), name
    a, b = _read_json(single / "replay_report.json"), _read_json(pooled / "replay_report.json")
    for key in ("expected_event_digest", "expected_world_digest", "expected_final_state_digest", "determinism"):
        assert a[key] == b[key]
    assert "pooled" not in _read_json(single / "timings.json")["timing"]
    assert _read_json(pooled / "timings.json")["timing"]["pooled"]["executions"] == 5


def test_repeat_that_diverges_from_run_1_fails_the_check(tmp_path: Path, monkeypatch) -> None:
    real = episode_module._run_replay_once
    calls = {"n": 0}

    def flaky(spec, payload):  # noqa: ANN001
        result = real(spec, payload)
        calls["n"] += 1
        if calls["n"] == 3:
            result.digests = [*result.digests, {"digest": "diverged"}]
        return result

    monkeypatch.setattr(episode_module, "_run_replay_once", flaky)
    assert _replay_check("ep01", tmp_path / "o", min_samples=40) == 1


def test_execution_cap_bounds_repeats(tmp_path: Path) -> None:
    assert _replay_check("ep01", tmp_path / "o", min_samples=10_000) == 0
    pooled = _read_json(tmp_path / "o" / "timings.json")["timing"]["pooled"]
    assert pooled["executions"] == MAX_TIMING_EXECUTIONS and pooled["min_samples_met"] is False
