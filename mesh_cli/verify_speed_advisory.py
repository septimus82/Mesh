"""Runner-speed check of verify-all's slow steps. It never fails a run by itself; under rule f (#400) it can only excuse
a fixed-threshold failure it judges within this runner's speed-adjusted range (mesh_cli.verify._apply_rule_f).

The enforced slow-step budgets (``tooling/metrics/verify_step_budget.json``, ``_evaluate_verify_step_budget_guard`` in
``mesh_cli/verify.py``) stay as they are. Next to them, this module judges each modelled step against what the run's own
runner predicts (leave-one-out calibration, rule "B" of ``docs/reviews/milestone16_stage6b_ci_timing.md``):

* speed_j = exp(median over the reference steps k != j of log(current_k / speed_reference_k)): the runner's speed,
  estimated without step j, so a slow step can never normalise its own time away;
* expected_j = base_j * speed_j ** slope_j and advisory threshold_j = expected_j * allowance_j.

The parameters come from ``tooling/metrics/verify_step_speed_model.json``, which ``tooling/ci_timing_analysis.py
--write-model`` fits from CI samples. With fewer than ``min_reference_steps`` reference steps left for a step, the step
gets no estimate and only the enforced verdict is reported. See ``docs/reviews/ci_timing_advisory_proposal.md``.
"""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any

ADVISORY_SCHEMA_VERSION = 1
MODEL_RELATIVE_PATH = Path("tooling") / "metrics" / "verify_step_speed_model.json"
DEFAULT_MIN_REFERENCE_STEPS = 3
# A run whose speed lies this far outside the calibrated range is reported as such (the slopes are extrapolated there).
CALIBRATION_MARGIN = 1.10


def load_speed_model(path: Path) -> dict[str, Any] | None:
    """The model JSON, or None when the file does not exist. A malformed file raises ValueError (or OSError)."""
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("platforms"), dict):
        raise ValueError(f"{path.name}: expected an object with a 'platforms' object")
    return raw


def _current_ms(step_durations_payload: dict[str, Any]) -> dict[str, int]:
    """Steps that ran and passed. Skipped steps are recorded as 0 ms and a failed step's time means little."""
    rows = step_durations_payload.get("steps")
    result: dict[str, int] = {}
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict) and isinstance(row.get("name"), str) and isinstance(row.get("ms"), (int, float)):
            if row["ms"] > 0 and row.get("ok", True) is not False:
                result[row["name"]] = int(row["ms"])
    return result


def runner_speed(current_ms: dict[str, int], reference_ms: dict[str, float], *, exclude: str = "") -> tuple[float, int] | None:
    """(speed factor, reference steps used): the median ratio of the reference steps to their reference times, without ``exclude``."""
    logs = [math.log(current_ms[k] / float(v)) for k, v in reference_ms.items() if k != exclude and k in current_ms and float(v) > 0.0]
    if not logs:
        return None
    return math.exp(statistics.median(logs)), len(logs)


def _enforced_rows(budget_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = budget_payload.get("checked_steps")
    return {str(r["name"]): r for r in rows if isinstance(r, dict) and "name" in r} if isinstance(rows, list) else {}


def build_speed_advisory(
    *,
    step_durations_payload: dict[str, Any],
    budget_payload: dict[str, Any],
    model: dict[str, Any] | None,
    platform: str,
    enforcement_active: bool,
) -> dict[str, Any]:
    """The advisory verdict per step next to the enforced one. Pure: reads its inputs, changes none of them."""
    current = _current_ms(step_durations_payload)
    enforced = _enforced_rows(budget_payload)
    platform_model = model.get("platforms", {}).get(platform) if model else None
    status = "ok" if isinstance(platform_model, dict) else ("no_model" if model is None else "no_platform_model")
    pm: dict[str, Any] = platform_model if isinstance(platform_model, dict) else {}
    reference = {str(k): float(v) for k, v in dict(pm.get("speed_reference_ms", {})).items()}
    modelled = dict(pm.get("steps", {}))
    min_refs = int(model.get("min_reference_steps", DEFAULT_MIN_REFERENCE_STEPS)) if model else DEFAULT_MIN_REFERENCE_STEPS
    seen = pm.get("speed_seen")
    whole = runner_speed(current, reference)
    run_speed = whole[0] if whole else None
    beyond = None
    if run_speed is not None and isinstance(seen, list) and len(seen) == 2:
        beyond = run_speed > float(seen[1]) * CALIBRATION_MARGIN or run_speed < float(seen[0]) / CALIBRATION_MARGIN

    steps = []
    for name in sorted(set(modelled) | set(enforced)):
        row: dict[str, Any] = {"name": name, "current_ms": current.get(name)}
        params = modelled.get(name)
        estimate = runner_speed(current, reference, exclude=name) if isinstance(params, dict) else None
        if not isinstance(params, dict):
            verdict = "not modelled"
        elif name not in current:
            verdict = "not run"
        elif estimate is None or estimate[1] < min_refs:
            verdict = "no estimate"
        else:
            speed, used = estimate
            expected = float(params["base_ms"]) * speed ** float(params["slope"])
            threshold = expected * float(params["allowance"])
            verdict = "slow" if current[name] > threshold else "ok"
            row.update(speed=round(speed, 4), expected_ms=round(expected), advisory_threshold_ms=round(threshold))
            row["ratio_to_expected"] = round(current[name] / expected, 3)
        row["reference_steps_used"] = estimate[1] if estimate else 0
        row["advisory_verdict"] = verdict
        budget = enforced.get(name)
        row["enforced_threshold_ms"] = budget.get("threshold_ms") if budget else None
        row["enforced_verdict"] = ("ok" if budget.get("ok") else "over") if budget else "not budgeted"
        row["enforced_policy"] = str(budget.get("policy") or "enforced") if budget else None
        steps.append(row)

    def names(pred: Any) -> list[str]:
        return [r["name"] for r in steps if pred(r)]

    return {
        "schema_version": ADVISORY_SCHEMA_VERSION,
        "advisory_only": True,
        "note": "Never fails a run by itself. Rule f: a fixed-threshold failure counts only where this says slow "
                "(or can't judge); see verify_step_budget_check.json, rule_f.",
        "status": status,
        "platform": platform,
        "model_fitted": {k: pm.get(k) for k in ("runs", "first_run", "last_run")} if pm else None,
        "enforcement_active": bool(enforcement_active),
        "run_speed": round(run_speed, 4) if run_speed is not None else None,
        "speed_seen": seen if isinstance(seen, list) else None,
        "speed_beyond_calibration": beyond,
        "steps": steps,
        "advisory_flagged": names(lambda r: r["advisory_verdict"] == "slow"),
        "enforced_flagged": names(lambda r: r["enforced_verdict"] == "over"),
        "disagreements": names(
            lambda r: r["advisory_verdict"] in ("ok", "slow") and r["enforced_verdict"] in ("ok", "over")
            and (r["advisory_verdict"] == "slow") != (r["enforced_verdict"] == "over")
        ),
    }


def _sec(ms: Any) -> str:
    return f"{ms / 1000.0:.2f}" if isinstance(ms, (int, float)) else "-"


def format_speed_advisory(payload: dict[str, Any]) -> list[str]:
    """A short per-step comparison for the console."""
    tag = "[Mesh][Verify][advisory]"
    head = (f"{tag} runner-speed check ({payload['platform']}): never fails a run by itself; rule f: a step over its "
            "fixed threshold fails only if this also says slow.")
    if payload["status"] != "ok":
        return [head, f"{tag} {payload['status'].replace('_', ' ')}: enforced verdicts only."]
    seen = payload.get("speed_seen") or ["?", "?"]
    speed = payload.get("run_speed")
    speed_text = f"{speed:.2f}" if speed is not None else "-"
    lines = [head, f"{tag} run speed {speed_text} (calibrated range {seen[0]}-{seen[1]}; 1.0 = median CI runner)"]
    if payload.get("speed_beyond_calibration"):
        lines.append(f"{tag} NOTE: this runner is outside every calibrated runner; advisory limits are extrapolated.")
    lines.append(f"  {'step':<24}{'now s':>8}{'speed':>7}{'expect s':>10}{'adv. limit s':>14}  {'advisory':<12}{'enf. limit s':>13}  enforced")
    for r in payload["steps"]:
        spd = f"{r['speed']:.2f}" if "speed" in r else "-"
        lines.append(
            f"  {r['name']:<24}{_sec(r['current_ms']):>8}{spd:>7}{_sec(r.get('expected_ms')):>10}{_sec(r.get('advisory_threshold_ms')):>14}  "
            f"{r['advisory_verdict']:<12}{_sec(r['enforced_threshold_ms']):>13}  {r['enforced_verdict']}"
            + (" (report-only)" if r.get("enforced_policy") == "report-only" else "")
        )
    disagree = payload["disagreements"]
    agree = "advisory and enforced decisions agree on every step judged by both"
    lines.append(f"{tag} " + (f"decisions differ on: {', '.join(disagree)}" if disagree else agree))
    return lines
