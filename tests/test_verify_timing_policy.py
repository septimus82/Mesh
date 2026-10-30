"""verify-all's timing policy (#422 F13): report-only steps, hard ceilings, missing timing evidence, and a verdict that
tells functional failures from timing-only ones. Measured against 443 CI runs in docs/reviews/h4_ci_timing_reliability.md."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest

import mesh_cli.verify as verify_mod
from tests.test_verify_release_notes_artifacts import _seed_repo

pytestmark = [pytest.mark.fast]

_REPO = Path(__file__).resolve().parents[1]
_BUDGET = _REPO / "tooling" / "metrics" / "verify_step_budget.json"


def _budget_file(tmp_path: Path, **extra: Any) -> Path:
    path = tmp_path / "verify_step_budget.json"
    payload = {"schema_version": 2, "tolerance_ms": 50, "budgets_ms": {"pytest-fast": 60000, "verify-demo": 10000},
               "ratio_limits": {"pytest-fast": 1.25, "verify-demo": 1.25}, **extra}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _durations(**ms: int) -> dict[str, Any]:
    return {"schema_version": 1, "steps": [{"name": n.replace("_", "-"), "ok": True, "ms": v} for n, v in ms.items()]}


def _guard(monkeypatch: pytest.MonkeyPatch, budget: Path, **ms: int) -> tuple[int, str, dict[str, Any]]:
    monkeypatch.setenv("MESH_VERIFY_STEP_BUDGET_NO_HISTORY", "1")
    monkeypatch.setattr(verify_mod, "_verify_step_budget_platform", lambda: "linux")
    return verify_mod._evaluate_verify_step_budget_guard(
        step_durations_payload=_durations(**ms), baseline_path=budget, update_command="noop", artifacts_dir=None
    )


def test_a_report_only_step_over_its_threshold_is_reported_not_failed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    budget = _budget_file(tmp_path, report_only_ceiling_ratios={"pytest-fast": 1.65})
    code, error, payload = _guard(monkeypatch, budget, pytest_fast=90000, verify_demo=9000)  # threshold 75 s

    assert (code, error, payload["ok"], payload["offenders"]) == (0, "", True, [])
    assert [o["name"] for o in payload["report_only_over"]] == ["pytest-fast"]
    row = next(r for r in payload["checked_steps"] if r["name"] == "pytest-fast")
    assert (row["policy"], row["ok"], row["gate_ok"], row["ceiling_ms"]) == ("report-only", False, True, 123750)
    assert verify_mod._report_only_timing_lines(payload) == [
        "pytest-fast took 90.00 s, over its 75.00 s threshold: reported, not failed (report-only, #422 F13); "
        "it fails over 123.75 s"]


def test_a_report_only_step_over_its_hard_ceiling_fails_and_rule_f_cannot_excuse_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    budget = _budget_file(tmp_path, report_only_ceiling_ratios={"pytest-fast": 1.65})
    code, error, payload = _guard(monkeypatch, budget, pytest_fast=130000, verify_demo=9000)

    assert (code, payload["ok"]) == (2, False)
    assert payload["offenders"] == [{"name": "pytest-fast", "delta_ms": 55000, "effective_ms": 130000, "over_ceiling": True}]
    assert "hard ceiling" in error
    advisory_says_ok = {"steps": [{"name": "pytest-fast", "advisory_verdict": "ok"}]}
    assert verify_mod._apply_rule_f(code, payload, advisory_says_ok)[0] == 2


def test_enforced_steps_keep_their_rule(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    budget = _budget_file(tmp_path, report_only_ceiling_ratios={"pytest-fast": 1.65})
    code, _error, payload = _guard(monkeypatch, budget, pytest_fast=60000, verify_demo=13000)  # threshold 12.5 s

    assert code == 2 and [o["name"] for o in payload["offenders"]] == ["verify-demo"]
    assert "over_ceiling" not in payload["offenders"][0]
    slow = {"steps": [{"name": "verify-demo", "advisory_verdict": "slow"}]}
    ok = {"steps": [{"name": "verify-demo", "advisory_verdict": "ok"}]}
    assert verify_mod._apply_rule_f(code, dict(payload), slow)[0] == 2
    assert verify_mod._apply_rule_f(code, dict(payload), ok)[0] == 0  # rule f as before


def test_missing_committed_budgets_never_read_as_a_pass(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    code, error, payload = _guard(monkeypatch, tmp_path / "absent.json", pytest_fast=1)
    assert (code, payload["ok"]) == (1, False)
    assert "baseline missing" in error


def test_the_committed_policy_has_ceilings_beyond_every_logged_runner() -> None:
    budget = json.loads(_BUDGET.read_text(encoding="utf-8"))
    # 1.25 x the worst step time / fixed threshold over 443 gated CI runs, 2026-10-25..30 (1.315 and 1.471).
    assert budget["report_only_ceiling_ratios"] == {"exception-policy-scan": 1.85, "pytest-fast": 1.65}
    assert set(budget["report_only_ceiling_ratios"]) <= set(budget["budgets_ms"])


def test_budgeted_steps_that_did_not_run_are_named() -> None:
    payload = {"checked_steps": [{"name": "pytest-fast"}, {"name": "web-smoke"}, {"name": "verify-demo"}]}
    steps = [
        {"name": "pytest-fast", "code": 0, "error": ""},
        {"name": "web-smoke", "code": 0, "error": "skipped: no web build"},
    ]
    assert verify_mod._budgeted_steps_not_measured(payload, steps) == ["verify-demo", "web-smoke"]


@pytest.mark.parametrize(
    ("steps", "timing", "expected"),
    [
        ([("ruff-gate", 1, "boom"), ("pytest-fast", 2, "skipped: previous step failed")], [],
         "FAILED (functional: ruff-gate)"),
        ([("ruff-gate", 0, "")], ["pytest-fast"], "FAILED (timing only: pytest-fast; every functional check passed)"),
        ([("pytest-fast-duration-guard", 2, "regressed")], [],
         "FAILED (timing only: pytest-fast-duration-guard; every functional check passed)"),
        ([("ruff-gate", 1, "boom")], ["pytest-fast"], "FAILED (functional: ruff-gate; timing: pytest-fast)"),
        ([("ruff-gate", 0, ""), ("web-smoke", 0, "skipped: no web build")], [], "OK"),
    ],
)
def test_the_verdict_tells_functional_from_timing_only(steps: list, timing: list, expected: str) -> None:
    rows = [{"name": n, "code": c, "error": e} for n, c, e in steps]
    assert verify_mod._verify_all_outcome(rows, timing) == expected


def test_annotations_only_inside_github_actions(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    verify_mod._github_annotation("warning", "t", "m")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    verify_mod._github_annotation("warning", "CI timing (report-only)", "pytest-fast over")
    assert capsys.readouterr().err == "::warning title=CI timing (report-only)::pytest-fast over\n"


# --- verify-all end to end (steps faked, the real budget guard and verdict) ---------------------------------------

def _args() -> argparse.Namespace:
    return argparse.Namespace(
        command="verify-all", world=None, out_dir=None, artifacts="artifacts", no_index=False, report=False,
        report_json=False, report_json_artifact=False, artifact_index=False, ci_bundle=False,
        release_notes_artifact=False, pytest_args=[],
    )


def _verify_all(monkeypatch: pytest.MonkeyPatch, repo: Path, *, ran: dict[str, int], budgets: dict[str, int] | None,
                report_only: dict[str, float] | None = None) -> tuple[dict, int]:
    _seed_repo(repo)
    if budgets is not None:
        metrics = repo / "tooling" / "metrics"
        metrics.mkdir(parents=True)
        (metrics / "verify_step_budget.json").write_text(json.dumps(
            {"schema_version": 2, "tolerance_ms": 50, "budgets_ms": budgets, "report_only_ceiling_ratios": report_only or {}}),
            encoding="utf-8")

    def _steps(ctx) -> None:  # noqa: ANN001
        for name in verify_mod.VERIFY_ALL_STEPS:
            if name in ran:
                ctx.add_step(name, 0, error="", artifact=None)
                ctx.step_duration_rows.append({"name": name, "ok": True, "ms": ran[name]})
            else:
                ctx.add_step(name, 0, error="skipped: not run in this test", artifact=None)
                ctx.step_duration_rows.append({"name": name, "ok": True, "ms": 0})
        ctx.exit_code = 0
        ctx.failure_seen = False

    monkeypatch.setattr(verify_mod, "run_verify_steps", _steps)
    monkeypatch.setattr(verify_mod, "_write_verify_step_speed_advisory", lambda **_kwargs: None)
    monkeypatch.setattr(verify_mod, "_verify_step_budget_platform", lambda: "linux")
    monkeypatch.setenv("MESH_VERIFY_STEP_BUDGET_NO_HISTORY", "1")
    monkeypatch.setenv("MESH_VERIFY_BUDGET_ENFORCE", "1")
    monkeypatch.chdir(repo)
    return verify_mod._build_verify_all_payload(_args())


def test_enforced_verify_all_fails_when_its_budgets_are_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
                                                                capsys: pytest.CaptureFixture[str]) -> None:
    payload, code = _verify_all(monkeypatch, tmp_path / "repo", ran={"pytest-fast": 50}, budgets=None)
    assert code != 0 and payload["ok"] is False
    assert "result: FAILED (timing only: step-time budget" in capsys.readouterr().err


def test_enforced_verify_all_fails_when_a_budgeted_step_never_ran(monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
                                                                  capsys: pytest.CaptureFixture[str]) -> None:
    payload, code = _verify_all(monkeypatch, tmp_path / "repo", ran={"pytest-fast": 50},
                                budgets={"pytest-fast": 60000, "web-smoke": 3000})
    err = capsys.readouterr().err
    assert code != 0 and payload["ok"] is False
    assert "timing evidence missing: web-smoke did not run" in err
    check = json.loads((tmp_path / "repo" / "artifacts" / "verify_step_budget_check.json").read_text(encoding="utf-8"))
    assert check["ok"] is False and check["not_measured"] == ["web-smoke"]


def test_enforced_verify_all_passes_a_report_only_overrun_and_says_so(monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
                                                                      capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    payload, code = _verify_all(monkeypatch, tmp_path / "repo", ran={"pytest-fast": 90000},
                                budgets={"pytest-fast": 60000}, report_only={"pytest-fast": 1.65})
    err = capsys.readouterr().err
    assert (code, payload["ok"]) == (0, True)
    assert "[Mesh][Verify] timing report-only: pytest-fast took 90.00 s" in err
    assert "::warning title=CI timing (report-only)::pytest-fast took 90.00 s" in err
    assert "[Mesh][Verify] result: OK" in err


def test_enforced_verify_all_fails_a_report_only_step_over_its_ceiling_as_timing_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    payload, code = _verify_all(monkeypatch, tmp_path / "repo", ran={"pytest-fast": 130000},
                                budgets={"pytest-fast": 60000}, report_only={"pytest-fast": 1.65})
    err = capsys.readouterr().err
    assert code == 2 and payload["ok"] is False
    assert "result: FAILED (timing only: pytest-fast; every functional check passed)" in err
    assert "::error title=verify-all failed on timing only::" in err


# --- the committed policy against 443 logged CI runs -------------------------------------------------------------

_TABLES = _REPO / "docs" / "reviews" / "h4_ci_timing_evidence" / "verify_timing_tables.json"


def _gate(steps: dict[str, list], ceilings: dict[str, float], scale: tuple[str, float] | None = None) -> tuple[set, set, set]:
    """(old failures, new failures, new report-only warnings) for one logged gated table; ``scale`` slows one step."""
    old, new, warn = set(), set(), set()
    for name, (now, adv_limit, limit) in steps.items():
        if limit is None:
            continue
        if scale and name == scale[0]:
            now *= scale[1]
        over = now > limit
        slow = now > adv_limit if adv_limit is not None else over  # no advisory: the fixed threshold decides
        if over and slow:
            old.add(name)
        if name in ceilings:
            if now > ceilings[name] * limit:
                new.add(name)
            elif over:
                warn.add(name)
        elif over and slow:
            new.add(name)
    return old, new, warn


def test_the_committed_policy_against_every_logged_ci_run() -> None:
    jobs = json.loads(_TABLES.read_text(encoding="utf-8"))["jobs"]
    ceilings = json.loads(_BUDGET.read_text(encoding="utf-8"))["report_only_ceiling_ratios"]
    for os_name, old_failures in (("linux", 55), ("windows", 10)):
        runs = [j["steps"] for j in jobs if j["os"] == os_name]
        assert len(runs) > 200
        results = [_gate(steps, ceilings) for steps in runs]
        assert sum(bool(old) for old, _, _ in results) == old_failures  # timing-only failures, no regression behind them
        assert sum(bool(new) for _, new, _ in results) == 0
        for step in ceilings:
            # A serious slowdown still fails the gate in most runs; a moderate one is still reported.
            severe = [_gate(steps, ceilings, (step, 2.5)) for steps in runs]
            assert sum(step in new for _, new, _ in severe) >= 0.8 * len(runs)
            moderate = [_gate(steps, ceilings, (step, 1.5)) for steps in runs]
            assert sum(step in new or step in warn for _, new, warn in moderate) >= 0.85 * len(runs)


def test_the_fast_tier_diagnostic_rerun_follows_the_gate_not_the_report_only_threshold() -> None:
    # The diagnostic reruns the whole fast tier: only when pytest-fast itself failed the gate.
    def payload(**row: object) -> dict[str, object]:
        return {"checked_steps": [{"name": "pytest-fast", **row}]}

    assert verify_mod._is_pytest_fast_budget_offender(payload(ok=False, gate_ok=True, policy="report-only")) is False
    assert verify_mod._is_pytest_fast_budget_offender(payload(ok=False, gate_ok=False, policy="report-only")) is True
    assert verify_mod._is_pytest_fast_budget_offender(payload(ok=False)) is True  # older payloads


def test_ci_budget_enforcement_does_not_leak_into_tests() -> None:
    # CI's verify-all runs this fast tier with MESH_VERIFY_BUDGET_ENFORCE=1 (tests/conftest.py clears it for tests).
    import os

    assert "MESH_VERIFY_BUDGET_ENFORCE" not in os.environ
