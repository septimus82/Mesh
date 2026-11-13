"""#422 F13-D: what the committed Windows timing policy (tooling/metrics/verify_step_budget.json and the runner-speed model
verify_step_speed_model.json, as mesh_cli.verify applies them) does with the fast tier this change restores, on every
runner speed CI has been calibrated on, and with a fast tier that really regressed. Nothing here changes the policy:
it pins what the policy decides, so a later change that would stop it catching a regression fails here.

- The restored fast tier (``RESTORED_MS`` at runner speed 1.0, the level after #437 on 2026-11-02, 111-120 s) is reported
  but never failed, on the fastest, the median and the slowest calibrated runner.
- The run that failed (43367798102: 213.97 s at speed 1.28) fails as it did; the waterfall PR's run at the same speed
  (43298153060: 181.34 s at 1.27) passes as it did.
- A substantial regression is still caught, and never excused by the speed advisory: on the slowest calibrated runner
  from x1.4 the restored time, on a median runner from x1.7, on the fastest only from x2.5 (the ceiling is a fixed
  time; gradual growth on fast runners is the rolling check's to see, ci_timing_analysis.py --rolling).
- An enforced step's overrun is excused only on a runner slow enough to explain it (rule f): the same duration fails on
  a median runner.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import mesh_cli.verify as verify_mod
from mesh_cli.verify_speed_advisory import build_speed_advisory

pytestmark = pytest.mark.fast

_REPO = Path(__file__).resolve().parents[1]
_BUDGET = _REPO / "tooling" / "metrics" / "verify_step_budget.json"
_MODEL = json.loads((_REPO / "tooling" / "metrics" / "verify_step_speed_model.json").read_text(encoding="utf-8"))
_WIN = _MODEL["platforms"]["windows"]
SLOWEST, FASTEST = (float(v) for v in reversed(_WIN["speed_seen"]))
RESTORED_MS = 120_000  # the fast tier at runner speed 1.0 that this change restores (CI after #437: 111-120 s)


def _run(speed: float, **steps_ms: int) -> dict[str, Any]:
    """A Windows verify-all run on a runner of ``speed``: every reference step its reference time x speed (so the speed
    estimate is exactly ``speed``), the named steps as given."""
    ms = {name: round(ref * speed) for name, ref in _WIN["speed_reference_ms"].items()}
    ms.update({name.replace("_", "-"): value for name, value in steps_ms.items()})
    return {"schema_version": 1, "steps": [{"name": n, "ok": True, "ms": v} for n, v in ms.items()]}


def _gate(monkeypatch: pytest.MonkeyPatch, run: dict[str, Any]) -> tuple[int, dict[str, Any], dict[str, Any]]:
    """The step-budget gate with the committed budgets, rule f applied with the committed advisory: (code, payload,
    advisory)."""
    monkeypatch.setenv("MESH_VERIFY_STEP_BUDGET_NO_HISTORY", "1")
    monkeypatch.setattr(verify_mod, "_verify_step_budget_platform", lambda: "windows")
    code, _error, payload = verify_mod._evaluate_verify_step_budget_guard(
        step_durations_payload=run, baseline_path=_BUDGET, update_command="noop", artifacts_dir=None)
    advisory = build_speed_advisory(step_durations_payload=run, budget_payload=payload, model=_MODEL,
                                    platform="windows", enforcement_active=True)
    code, _record = verify_mod._apply_rule_f(code, payload, advisory)
    return code, payload, advisory


def _fast_tier_at(speed: float, at_median_ms: float = RESTORED_MS) -> int:
    """The fast tier's time on a runner of ``speed``, by the model's own slope for it."""
    return round(at_median_ms * speed ** float(_WIN["steps"]["pytest-fast"]["slope"]))


def _row(payload: dict[str, Any], name: str) -> dict[str, Any]:
    return next(r for r in payload["checked_steps"] if r["name"] == name)


@pytest.mark.parametrize("speed", [FASTEST, 1.0, SLOWEST])
def test_the_restored_fast_tier_is_never_failed_on_any_calibrated_runner(monkeypatch: pytest.MonkeyPatch,
                                                                         speed: float) -> None:
    code, payload, _advisory = _gate(monkeypatch, _run(speed, pytest_fast=_fast_tier_at(speed)))
    row = _row(payload, "pytest-fast")
    assert code == 0 and row["gate_ok"] and row["policy"] == "report-only", row
    assert row["effective_ms"] < 0.8 * row["ceiling_ms"], ("a fifth or more of headroom under the hard ceiling", row)


def test_the_failed_post_merge_run_fails_as_it_did_and_the_pr_run_passes_as_it_did(
        monkeypatch: pytest.MonkeyPatch) -> None:
    code, payload, _advisory = _gate(monkeypatch, _run(1.28, pytest_fast=213_973))
    assert code != 0 and payload["offenders"][0]["name"] == "pytest-fast" and payload["offenders"][0]["over_ceiling"]
    assert _row(payload, "pytest-fast")["ceiling_ms"] == 201_003
    code, payload, _advisory = _gate(monkeypatch, _run(1.27, pytest_fast=181_341))
    assert code == 0 and _row(payload, "pytest-fast")["gate_ok"]


@pytest.mark.parametrize(("speed", "growth"), [(SLOWEST, 1.4), (1.0, 1.7), (FASTEST, 2.5)])
def test_a_substantial_fast_tier_regression_is_still_caught_and_never_excused(monkeypatch: pytest.MonkeyPatch,
                                                                              speed: float, growth: float) -> None:
    regressed = round(_fast_tier_at(speed) * growth)
    code, payload, advisory = _gate(monkeypatch, _run(speed, pytest_fast=regressed))
    assert code != 0, (speed, growth, regressed)
    assert payload["rule_f"]["failed"] == ["pytest-fast"], payload["rule_f"]  # (no runner speed excuses it)
    flagged = next(s for s in advisory["steps"] if s["name"] == "pytest-fast")
    assert flagged["advisory_verdict"] == "slow", flagged


def test_an_enforced_step_s_overrun_is_excused_only_on_a_runner_slow_enough_to_explain_it(
        monkeypatch: pytest.MonkeyPatch) -> None:
    params = _WIN["steps"]["verify-demo"]
    # what the slowest calibrated runner is expected to take (just over the fixed threshold, well within its allowance)
    on_slowest = round(float(params["base_ms"]) * SLOWEST ** float(params["slope"]) * 1.05)
    run = _run(SLOWEST, pytest_fast=_fast_tier_at(SLOWEST), verify_demo=on_slowest)
    code, payload, _advisory = _gate(monkeypatch, run)
    assert not _row(payload, "verify-demo")["ok"] and _row(payload, "verify-demo")["policy"] == "enforced"
    assert code == 0 and payload["rule_f"]["excused_by_advisory"] == ["verify-demo"], payload["rule_f"]
    run = _run(1.0, pytest_fast=_fast_tier_at(1.0), verify_demo=on_slowest)  # the same time on a median runner
    code, payload, _advisory = _gate(monkeypatch, run)
    assert code != 0 and payload["rule_f"]["failed"] == ["verify-demo"], payload["rule_f"]
