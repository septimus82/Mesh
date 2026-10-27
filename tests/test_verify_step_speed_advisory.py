"""The advisory runner-speed check (mesh_cli/verify_speed_advisory.py): leave-one-out calibration that flags isolated
step regressions, lets slow runners pass, degrades to "no estimate" without enough reference steps, and never changes
the enforced slow-step verdict or verify-all's exit code."""

from __future__ import annotations

import argparse
import copy
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from mesh_cli import verify as verify_mod
from mesh_cli.verify_speed_advisory import MODEL_RELATIVE_PATH, build_speed_advisory, format_speed_advisory, load_speed_model
from tooling import ci_timing_analysis as cta

pytestmark = [pytest.mark.fast]

_REPO = Path(__file__).resolve().parents[1]
_DATA = _REPO / "docs" / "reviews" / "milestone16_stage6b_evidence" / "ci_timing_data.json"
_BUDGET = _REPO / "tooling" / "metrics" / "verify_step_budget.json"

# A synthetic platform: six reference steps, three of them also checked; slope 1, allowance 1.3.
_REF = {"ref-a": 1000, "ref-b": 2000, "ref-c": 3000, "pytest-fast": 60000, "verify-demo": 9000, "web-smoke": 3500}
_CHECKED = ("pytest-fast", "verify-demo", "web-smoke")


def _model(**overrides: Any) -> dict[str, Any]:
    steps = {name: {"base_ms": _REF[name], "slope": 1.0, "allowance": 1.3, "sigma": 0.066, "n": 30} for name in _CHECKED}
    platform = {"runs": 30, "speed_reference_ms": dict(_REF), "speed_seen": [0.6, 1.4], "speed_log_sd": 0.2, "steps": steps}
    platform.update(overrides)
    return {"schema_version": 1, "min_reference_steps": 3, "platforms": {"linux": platform}}


def _durations(step_ms: Mapping[str, float]) -> dict[str, Any]:
    return {"schema_version": 1, "steps": [{"name": n, "ok": True, "ms": int(ms)} for n, ms in sorted(step_ms.items())]}


def _budget(over: tuple[str, ...] = ()) -> dict[str, Any]:
    rows = [{"name": n, "threshold_ms": int(_REF[n] * 1.25), "ok": n not in over} for n in _CHECKED]
    return {"schema_version": 2, "ok": not over, "checked_steps": rows, "offenders": []}


def _advise(step_ms: Mapping[str, float], *, model: dict[str, Any] | None = None, budget: dict[str, Any] | None = None) -> dict[str, Any]:
    return build_speed_advisory(
        step_durations_payload=_durations(step_ms),
        budget_payload=budget if budget is not None else _budget(),
        model=_model() if model is None else model,
        platform="linux",
        enforcement_active=True,
    )


def _row(payload: dict[str, Any], name: str) -> dict[str, Any]:
    return next(r for r in payload["steps"] if r["name"] == name)


@pytest.mark.parametrize("factor", [1.5, 2.0])
@pytest.mark.parametrize("step", _CHECKED)
def test_an_isolated_regression_of_one_step_is_flagged(step: str, factor: float) -> None:
    for runner in (0.7, 1.0, 1.3):  # on a fast, a median and a slow runner alike
        steps = {n: v * runner for n, v in _REF.items()}
        steps[step] *= factor
        payload = _advise(steps)
        assert payload["advisory_flagged"] == [step], (runner, payload["advisory_flagged"])
        assert _row(payload, step)["speed"] == pytest.approx(runner, rel=1e-3), "the regressed step does not move its own speed"


@pytest.mark.parametrize("runner", [0.62, 0.8, 1.3, 1.4])
def test_a_uniformly_slower_or_faster_runner_is_not_flagged(runner: float) -> None:
    payload = _advise({n: v * runner for n, v in _REF.items()})
    assert payload["advisory_flagged"] == []
    assert payload["run_speed"] == pytest.approx(runner, rel=1e-3)
    assert payload["speed_beyond_calibration"] is False
    assert {r["advisory_verdict"] for r in payload["steps"]} == {"ok"}


def test_a_runner_slower_than_any_seen_passes_but_is_reported() -> None:
    payload = _advise({n: v * 2.5 for n, v in _REF.items()})
    assert payload["advisory_flagged"] == [], "the slopes extrapolate: a uniformly slow runner still passes"
    assert payload["speed_beyond_calibration"] is True
    assert any("outside every calibrated runner" in line for line in format_speed_advisory(payload))
    # A real regression on such a runner is still caught.
    steps = {n: v * 2.5 for n, v in _REF.items()}
    steps["verify-demo"] *= 2.0
    assert _advise(steps)["advisory_flagged"] == ["verify-demo"]


def test_a_steps_own_time_never_enters_its_own_speed_estimate() -> None:
    base = {n: v * 1.1 for n, v in _REF.items()}
    for name in _CHECKED:
        speeds = set()
        for factor in (0.1, 0.5, 1.0, 2.0, 10.0, 100.0):
            steps = dict(base)
            steps[name] *= factor
            speeds.add(_row(_advise(steps), name)["speed"])
        assert len(speeds) == 1, (name, speeds)


def test_missing_reference_steps_degrade_to_no_estimate_with_the_enforced_verdict_kept() -> None:
    # pytest-fast with three other reference steps left: still estimated.
    three = {"pytest-fast": 120000, "ref-a": 1000, "ref-b": 2000, "ref-c": 3000}
    row = _row(_advise(three, budget=_budget(over=("pytest-fast",))), "pytest-fast")
    assert row["reference_steps_used"] == 3 and row["advisory_verdict"] == "slow"
    # Two left: no estimate, and the enforced verdict is still reported.
    two = {"pytest-fast": 120000, "ref-a": 1000, "ref-b": 2000}
    payload = _advise(two, budget=_budget(over=("pytest-fast",)))
    row = _row(payload, "pytest-fast")
    assert row["advisory_verdict"] == "no estimate" and "speed" not in row and "advisory_threshold_ms" not in row
    assert row["enforced_verdict"] == "over" and row["enforced_threshold_ms"] == 75000
    assert payload["enforced_flagged"] == ["pytest-fast"] and payload["disagreements"] == []
    assert _row(payload, "web-smoke")["advisory_verdict"] == "not run"
    # A skipped step (recorded as 0 ms) or a failed one is not used as a reference.
    durations = _durations({"pytest-fast": 120000, "ref-a": 1000, "ref-b": 2000, "ref-c": 0})
    durations["steps"].append({"name": "verify-demo", "ok": False, "ms": 9000})
    payload = build_speed_advisory(step_durations_payload=durations, budget_payload=_budget(), model=_model(), platform="linux", enforcement_active=True)
    assert _row(payload, "pytest-fast")["advisory_verdict"] == "no estimate"


def test_no_model_or_no_platform_model_reports_enforced_verdicts_only() -> None:
    steps = {n: float(v) for n, v in _REF.items()}
    for model, status in ((None, "no_model"), ({"platforms": {"windows": {}}}, "no_platform_model")):
        payload = build_speed_advisory(
            step_durations_payload=_durations(steps), budget_payload=_budget(over=("web-smoke",)), model=model, platform="linux", enforcement_active=False
        )
        assert payload["status"] == status
        assert {r["advisory_verdict"] for r in payload["steps"]} == {"not modelled"}
        assert payload["enforced_flagged"] == ["web-smoke"]
        assert "enforced verdicts only" in format_speed_advisory(payload)[-1]


def test_the_advisory_reads_but_never_changes_its_inputs() -> None:
    durations = _durations({n: v * 1.2 for n, v in _REF.items()})
    budget = _budget(over=("pytest-fast",))
    model = _model()
    before = copy.deepcopy((durations, budget, model))
    payload = build_speed_advisory(step_durations_payload=durations, budget_payload=budget, model=model, platform="linux", enforcement_active=True)
    assert (durations, budget, model) == before
    # Enforced verdicts are copied through, and the disagreement is named.
    assert payload["enforced_flagged"] == ["pytest-fast"] and payload["advisory_flagged"] == []
    assert payload["disagreements"] == ["pytest-fast"]
    assert any("decisions differ on: pytest-fast" in line for line in format_speed_advisory(payload))


# --------------------------------------------------------------------------- the committed model and the real CI data


def _real_runs(os_name: str) -> list[cta.Run]:
    return [r for r in cta.load_data(_DATA) if r.os == os_name and r.regime == "post-opt"]


def test_the_committed_model_is_the_fit_of_the_committed_data() -> None:
    committed = load_speed_model(_REPO / MODEL_RELATIVE_PATH)
    assert committed is not None
    assert committed ==cta.build_model(cta.load_data(_DATA), _BUDGET, cta.DEFAULT_K), "refit with ci_timing_analysis.py --write-model"
    for platform in committed["platforms"].values():
        assert "mypy-gate" not in platform["steps"] and "mypy-gate" not in platform["speed_reference_ms"]


@pytest.mark.parametrize("os_name", ["linux", "windows"])
def test_verify_all_evaluates_exactly_the_rule_the_analysis_validates(os_name: str) -> None:
    model = load_speed_model(_REPO / MODEL_RELATIVE_PATH)
    assert model is not None
    pm = model["platforms"][os_name]
    for run in _real_runs(os_name):
        payload = build_speed_advisory(
            step_durations_payload=_durations(run.steps), budget_payload={}, model=model, platform=os_name, enforcement_active=True
        )
        for name in pm["steps"]:
            estimate = cta.model_estimate(pm, {k: float(v) for k, v in run.steps.items()}, name)
            assert estimate is not None
            assert _row(payload, name)["advisory_threshold_ms"] == pytest.approx(estimate[1], abs=1.0)


def test_the_two_observed_windows_false_failures_pass_the_advisory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Runs 40210460482 and 40214571672 failed the enforced budgets on the two slowest Windows runners (fitted in-sample)."""
    monkeypatch.setattr(verify_mod, "_verify_step_budget_platform", lambda: "windows")
    monkeypatch.setenv("MESH_VERIFY_STEP_BUDGET_NO_HISTORY", "1")
    model = load_speed_model(_REPO / MODEL_RELATIVE_PATH)
    by_id = {r.run_id: r for r in _real_runs("windows")}
    for run_id, failed_step in ((40210460482, "pytest-fast"), (40214571672, "exception-policy-scan")):
        durations = _durations(by_id[run_id].steps)
        code, _err, budget = verify_mod._evaluate_verify_step_budget_guard(
            step_durations_payload=durations, baseline_path=_BUDGET, update_command="noop", artifacts_dir=tmp_path
        )
        payload = build_speed_advisory(step_durations_payload=durations, budget_payload=budget, model=model, platform="windows", enforcement_active=True)
        assert code == 2 and payload["enforced_flagged"] == [failed_step]
        assert payload["advisory_flagged"] == [] and payload["disagreements"] == [failed_step]
        assert payload["run_speed"] > 1.2, "both were slow runners"
        # The same run with that step doubled is flagged.
        doubled = dict(by_id[run_id].steps)
        doubled[failed_step] *= 2
        payload = build_speed_advisory(
            step_durations_payload=_durations(doubled), budget_payload=budget, model=model, platform="windows", enforcement_active=True
        )
        assert payload["advisory_flagged"] == [failed_step]


# --------------------------------------------------------------------------- verify-all wiring: artifact, output, exit code


def _seed_model(repo: Path, model: dict[str, Any]) -> None:
    path = repo / MODEL_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(model), encoding="utf-8")


def _flag_everything_model() -> dict[str, Any]:
    """Every verify-all step is a reference step and every one is 'slow' (threshold far below its 1 ms)."""
    names = list(verify_mod.VERIFY_ALL_STEPS)
    steps = {n: {"base_ms": 0.001, "slope": 1.0, "allowance": 1.0, "sigma": 0.0, "n": 30} for n in names}
    return {"min_reference_steps": 3, "platforms": {verify_mod._verify_step_budget_platform(): {"speed_reference_ms": {n: 1 for n in names}, "steps": steps}}}


def _verify_all_args() -> argparse.Namespace:
    return argparse.Namespace(
        command="verify-all", world=None, out_dir=None, artifacts="artifacts", no_index=False, report=False, report_json=False,
        report_json_artifact=False, artifact_index=False, ci_bundle=False, release_notes_artifact=False, pytest_args=[],
    )


@pytest.mark.parametrize("enforced_over", [False, True])
@pytest.mark.parametrize("model", [None, "flag-everything", "malformed"])
def test_the_advisory_never_changes_verify_all_outcome(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str], enforced_over: bool, model: str | None
) -> None:
    from tests.test_verify_release_notes_artifacts import _patch_fast_success, _seed_repo

    _patch_fast_success(monkeypatch)
    monkeypatch.setenv("MESH_VERIFY_BUDGET_ENFORCE", "1")
    if enforced_over:
        row = {"name": "pytest-fast", "budget_ms": 1, "tolerance_ms": 0, "ratio_limit": 1.0, "threshold_ms": 0, "current_ms": 1,
               "median_ms": None, "effective_ms": 1, "delta_ms": 1, "ok": False}
        budget = {"schema_version": 2, "ok": False, "tolerance_ms": 0, "candidates_used": [], "checked_steps": [row], "offenders": []}
        monkeypatch.setattr(verify_mod, "_evaluate_verify_step_budget_guard", lambda **_kw: (2, "verify slow-step budget exceeded", budget))
    repo = tmp_path / "repo"
    _seed_repo(repo)
    if model == "flag-everything":
        _seed_model(repo, _flag_everything_model())
    elif model == "malformed":
        (repo / MODEL_RELATIVE_PATH).parent.mkdir(parents=True, exist_ok=True)
        (repo / MODEL_RELATIVE_PATH).write_text("{not json", encoding="utf-8")
    monkeypatch.chdir(repo)

    payload, code = verify_mod._build_verify_all_payload(_verify_all_args())

    assert (payload["ok"], code) == ((False, 2) if enforced_over else (True, 0))
    err = capsys.readouterr().err
    advisory_path = repo / "artifacts" / "verify_step_speed_advisory.json"
    if model == "malformed":
        assert not advisory_path.exists() and "[Mesh][Verify][advisory] runner-speed check skipped: JSONDecodeError" in err
        return
    advisory = json.loads(advisory_path.read_text(encoding="utf-8"))
    assert advisory["advisory_only"] is True and "[Mesh][Verify][advisory]" in err
    budget_check = json.loads((repo / "artifacts" / "verify_step_budget_check.json").read_text(encoding="utf-8"))
    assert budget_check["ok"] is (not enforced_over), "the enforced payload is written as the guard returned it"
    if model == "flag-everything":
        assert advisory["status"] == "ok" and advisory["advisory_flagged"], "the advisory flagged steps, and the run outcome did not move"
    else:
        assert advisory["status"] == "no_model"


def _over(*names: str) -> dict:
    return {"ok": False, "offenders": [{"name": n, "delta_ms": 100, "effective_ms": 1000} for n in names]}


def _advisory(**verdicts: str) -> dict:
    return {"steps": [{"name": n.replace("_", "-"), "advisory_verdict": v} for n, v in verdicts.items()]}


def test_rule_f_fails_a_step_only_when_the_fixed_threshold_and_the_advisory_agree() -> None:
    """#400: over the fixed threshold and slow on this runner: fails; over but within this runner's range: excused."""
    from mesh_cli.verify import _apply_rule_f

    assert _apply_rule_f(2, _over("pytest-fast"), _advisory(pytest_fast="slow"))[0] == 2
    code, record = _apply_rule_f(2, _over("pytest-fast"), _advisory(pytest_fast="ok"))
    assert code == 0 and record["excused_by_advisory"] == ["pytest-fast"] and record["failed"] == []
    code, record = _apply_rule_f(2, _over("pytest-fast", "verify-demo"),
                                 _advisory(pytest_fast="ok", verify_demo="slow"))
    assert code == 2 and record["failed"] == ["verify-demo"]  # (one confirmed step is enough)
    assert _apply_rule_f(0, {"ok": True, "offenders": []}, _advisory(pytest_fast="slow"))[0] == 0  # (never fails by itself)


def test_rule_f_never_fails_open_where_the_advisory_cannot_judge() -> None:
    """No advisory, no estimate, not modelled, not run: the fixed threshold alone decides."""
    from mesh_cli.verify import _apply_rule_f

    assert _apply_rule_f(2, _over("pytest-fast"), None)[0] == 2
    for verdict in ("no estimate", "not modelled", "not run"):
        assert _apply_rule_f(2, _over("pytest-fast"), _advisory(pytest_fast=verdict))[0] == 2
    assert _apply_rule_f(2, _over("web-smoke"), _advisory(pytest_fast="ok"))[0] == 2  # (a step it didn't judge)
