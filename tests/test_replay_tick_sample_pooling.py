"""T-07: short replay episodes judge tick p95 over a pooled sample, never over their own handful of ticks."""

from __future__ import annotations

import argparse
import gc
import json
import os
import threading
import time
import weakref
from pathlib import Path

import pytest

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
    perf_path = tmp_path / "out" / case_id / "performance.json"
    return code, (_read_json(perf_path) if perf_path.exists() else {})


def _why(code: int, perf: dict, tmp_path: Path | None = None, case_id: str = "ep05") -> str:
    """#612: a failure here must name the violated metric / failure cause and the process state, not just ``1 == 0``.

    Defensive on purpose: a non-budget exit (exception in a run, golden mismatch) may leave no ``budget``/``performance``.
    """
    load = os.getloadavg() if hasattr(os, "getloadavg") else None
    # Only ever evaluated after a failure, so the heap census and the timed full collection cost the gate nothing.
    gc_stats, gc_count, tracked = gc.get_stats(), gc.get_count(), len(gc.get_objects())
    started = time.perf_counter()
    gc.collect()
    full_collect_ms = round((time.perf_counter() - started) * 1000.0, 1)
    parts = [
        f"exit={code}",
        f"budget={perf.get('budget')}",
        f"pooled={(perf.get('performance') or {}).get('pooled')}",
        f"threads={threading.active_count()} thread_names={[t.name for t in threading.enumerate()]}",
        f"gc_stats={gc_stats}",
        f"gc_threshold={gc.get_threshold()} gc_count_before={gc_count} gc_tracked_objects={tracked}",
        f"gc_freeze_count={gc.get_freeze_count()}",
        f"full_gc_collect_ms_after_failure={full_collect_ms}",
        f"loadavg={load}",
        f"cpus={os.cpu_count()}",
    ]
    if tmp_path is not None:
        out = tmp_path / "out"
        try:
            suite = _read_json(out / "suite_report.json")
            parts.append(f"suite_summary={suite.get('summary')}")
            for case in suite.get("cases") or []:
                parts.append(
                    f"case={ {k: case.get(k) for k in ('id', 'ok', 'run_ok', 'match', 'error', 'mismatches')} }"
                )
            report = _read_json(out / case_id / "replay_report.json")
            parts.append(
                f"replay_ok={report.get('ok')} determinism={report.get('determinism')} "
                f"run_1_error={(report.get('run_1') or {}).get('error')} run_2_error={(report.get('run_2') or {}).get('error')}"
            )
        except (OSError, ValueError, AttributeError) as exc:
            parts.append(f"suite_outputs_unreadable={exc!r}")
    return " ".join(parts)


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


def test_tick_violation_names_execution_and_tick_without_changing_the_verdict() -> None:
    """#612: report-only detail; the judged numbers and the violation list are what they were without it."""
    details = [[{"tick": i, "ms": ms, "start_ms": 20.0 + i} for i, ms in enumerate(run)] for run in
               ([2.0, 846.1, 3.0, 2.5], [2.0, 2.2, 2.1, 2.4])]
    pooled = pooled_timing_summary([[d["ms"] for d in run] for run in details], min_samples=8, tick_details=details)
    plain = pooled_timing_summary([[d["ms"] for d in run] for run in details], min_samples=8)
    assert {k: v for k, v in pooled.items() if k != "slowest_ticks_per_execution"} == plain
    assert [[t["tick"] for t in run] for run in pooled["slowest_ticks_per_execution"]] == [[1, 2, 3], [3, 1, 2]]
    limits = replays_module.ReplayBudgets(max_total_ms=3000.0, max_tick_ms_p95=50.0, max_tick_ms_max=150.0)
    budget = replays_module._evaluate_case_budget(
        budgets=limits,
        performance={"total_ms": 853.6, "tick_ms_p95": 3.0, "tick_ms_max": 846.1, "pooled": pooled},
        enforce_budgets=True,
    )
    assert [v["metric"] for v in budget["violations"]] == ["tick_ms_max"]
    assert budget["violations"][0]["ticks_over_threshold"] == [{"execution": 1, "tick": 1, "ms": 846.1, "start_ms": 21.0}]


# --- real replays -------------------------------------------------------------------------------------------------


def test_ep05_pools_enough_samples_and_passes_budget(tmp_path: Path) -> None:
    code, perf = _run_suite(tmp_path, "ep05")
    assert code == 0 and (perf.get("budget") or {}).get("ok") is True, _why(code, perf, tmp_path)
    pooled = perf["performance"]["pooled"]
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


# --- #612: timed executions are isolated from the host process's heap --------------------------------------------


class _Cycle:
    me: object = None


def _gc_state() -> tuple[bool, tuple[int, ...], int]:
    return gc.isenabled(), gc.get_threshold(), gc.get_freeze_count()


@pytest.fixture
def no_host_frozen_objects():
    if gc.get_freeze_count():
        pytest.skip("this process already froze objects; the harness leaves such a host alone")


def _probe_executions(monkeypatch, sample) -> list:  # noqa: ANN001
    """Wrap every timed execution: ``sample()`` runs just before it starts, its result is kept beside the execution."""
    real, seen = episode_module._run_replay_once, []

    def probe(spec, payload):  # noqa: ANN001
        before = sample()
        result = real(spec, payload)
        seen.append((before, result))
        return result

    monkeypatch.setattr(episode_module, "_run_replay_once", probe)
    return seen


def test_every_timed_execution_runs_with_the_host_heap_collected_then_frozen(
    tmp_path: Path, monkeypatch, no_host_frozen_objects
) -> None:
    """A big pre-existing heap sits in the permanent generation, out of reach of every collection a timed tick can
    trigger, for run_1, run_2 and every timing-only repeat; the host's old garbage was collected, not frozen with it."""
    heap = [[i] for i in range(300_000)]
    sentinel = heap[-1]
    garbage = _Cycle()
    garbage.me = garbage
    garbage_ref = weakref.ref(garbage)
    gc.collect()  # the cycle is now old (generation 2): no young collection before the harness can free it
    del garbage

    def sample() -> dict:
        return {
            "frozen": gc.get_freeze_count(),
            "garbage_alive": garbage_ref() is not None,
            "heap_collectable": any(o is sentinel for g in range(3) for o in gc.get_objects(g)),
        }

    seen = _probe_executions(monkeypatch, sample)
    assert _replay_check("ep01", tmp_path / "o", min_samples=40) == 0
    assert len(seen) == 5  # run_1, run_2 and three repeats
    for before, result in seen:
        assert result.ok
        assert before == {"frozen": before["frozen"], "garbage_alive": False, "heap_collectable": False}
        assert before["frozen"] >= len(heap)
    assert gc.get_freeze_count() == 0
    assert any(o is sentinel for o in gc.get_objects(2)), "unfrozen afterwards, collectable again"


def test_gc_state_is_restored_after_success_and_after_an_exception_mid_run(
    tmp_path: Path, monkeypatch, no_host_frozen_objects
) -> None:
    before = _gc_state()
    assert _replay_check("ep01", tmp_path / "ok", min_samples=40) == 0
    assert _gc_state() == before

    real, calls = episode_module._run_replay_once, {"n": 0}

    def explode_in_run_2(spec, payload):  # noqa: ANN001
        calls["n"] += 1
        if calls["n"] == 2:
            assert gc.get_freeze_count() > 0
            raise RuntimeError("boom mid-run")
        return real(spec, payload)

    monkeypatch.setattr(episode_module, "_run_replay_once", explode_in_run_2)
    assert _replay_check("ep01", tmp_path / "boom", min_samples=40) == 1
    assert calls["n"] == 2
    assert _gc_state() == before


def test_gc_disabled_by_the_host_stays_disabled(tmp_path: Path, no_host_frozen_objects) -> None:
    gc.disable()
    try:
        assert _replay_check("ep01", tmp_path / "o", min_samples=0) == 0
        assert gc.isenabled() is False and gc.get_freeze_count() == 0
    finally:
        gc.enable()


def test_a_host_that_froze_its_own_objects_is_left_exactly_as_it_was(
    tmp_path: Path, monkeypatch, no_host_frozen_objects
) -> None:
    """gc.unfreeze() would release the host's frozen objects too, so the harness must not freeze or unfreeze.

    The freeze count alone is not exact: a frozen object that is deallocated leaves the permanent generation, so in a
    big process the count drifts down by itself. Never up (nothing newly frozen), and the host's objects stay frozen.
    """
    host_object = [1, 2, 3]

    def collectable() -> bool:
        return any(o is host_object for g in range(3) for o in gc.get_objects(g))

    gc.freeze()
    try:
        frozen = gc.get_freeze_count()
        seen = _probe_executions(monkeypatch, lambda: (gc.get_freeze_count(), collectable()))
        assert _replay_check("ep01", tmp_path / "o", min_samples=0) == 0
        assert len(seen) == 2
        for (count, host_object_collectable), _ in seen:
            assert count <= frozen and not host_object_collectable
        assert 0 < gc.get_freeze_count() <= frozen and not collectable()
    finally:
        gc.unfreeze()


def test_replay_allocations_are_still_collected_and_timed_inside_ticks(
    tmp_path: Path, monkeypatch, no_host_frozen_objects
) -> None:
    """Freezing only removes the host's old heap: what a replay allocates is still collected inside its ticks and the
    pause is still part of the measured tick time (and the per-tick #634 gc breakdown)."""
    real_advance = episode_module._advance

    def allocating_advance(ctx, dt):  # noqa: ANN001
        live = [[i] for i in range(30_000)]  # alive across the tick, so the allocation counter really climbs
        real_advance(ctx, dt)
        del live

    monkeypatch.setattr(episode_module, "_advance", allocating_advance)
    seen = _probe_executions(monkeypatch, gc.get_freeze_count)
    assert _replay_check("ep01", tmp_path / "o", min_samples=0) == 0
    assert len(seen) == 2
    for frozen, result in seen:
        assert frozen > 0
        ticks = result.tick_details
        assert sum(sum(t["gc_collections"]) for t in ticks) >= len(ticks)  # at least one collection per tick
        assert sum(t["gc_ms"] for t in ticks) > 0.0
        assert all(t["ms"] >= t["gc_ms"] for t in ticks)
