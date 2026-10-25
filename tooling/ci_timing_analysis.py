"""Reliability analysis of the verify-all slow-step budgets on CI runners.

verify-all fails a CI job when a budgeted step takes longer than its threshold (``mesh_cli/verify.py``,
``_evaluate_verify_step_budget_guard``; budgets in ``tooling/metrics/verify_step_budget.json``). Hosted runners differ in
speed from job to job, so this script replays historical CI timings against the current rule and against candidate rules,
and measures for each rule:

* false failures on the historical runs (no code regression intended);
* detection of synthetic isolated regressions (one step multiplied by 1.25, 1.5 or 2 in each historical run);
* behaviour under a synthetic whole-run slowdown (every step multiplied by 1.3).

Every fitted rule is evaluated by leave-one-run-out cross-validation: the run being judged never contributes to the
medians, slopes or spreads that judge it.

Input is either a compact data file (``--data``, written by ``--write-data``) or an index plus a folder of the
``verify_step_durations.json`` files taken from the ``mesh-artifacts-<os>-py3.11`` CI artifacts (``--index`` and
``--durations-dir``). Index entries: ``run_id``, ``os`` (``linux``/``windows``), ``event``, ``sha``, ``date``, ``regime``
(``post-opt`` for the code the budgets were measured on, ``pre-opt`` for the slower code before it), ``durations``
(file name), and optionally ``job_s`` and ``full_pytest_s`` (the whole CI job and its full-pytest step, in seconds).

``--write-model`` fits the advisory runner-speed model that verify-all reads (``tooling/metrics/verify_step_speed_model.json``,
evaluated by ``mesh_cli/verify_speed_advisory.py``; policy "A" below is that exact rule). ``--rolling N`` judges the last N
runs per OS against a committed model, for persistent slowdowns that a per-run rule cannot see.

Usage::

    python tooling/ci_timing_analysis.py --data data.json > report.md
    python tooling/ci_timing_analysis.py --index index.json --durations-dir durations --write-data data.json
    python tooling/ci_timing_analysis.py --data data.json --index new.json --durations-dir new --write-data data.json  # merge
    python tooling/ci_timing_analysis.py --data data.json --write-model tooling/metrics/verify_step_speed_model.json
    python tooling/ci_timing_analysis.py --data recent.json --rolling 20

Standard library only; the output is deterministic for a given input.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

IMPORTANT_STEPS = ("pytest-fast", "verify-demo", "mypy-gate", "exception-policy-scan", "swallow-scan-gate", "web-smoke")
STEP_FACTORS = (1.25, 1.5, 2.0)
WHOLE_RUN_FACTOR = 1.3
DEFAULT_K = 4.0
SENSITIVITY_K = (3.0, 3.5, 4.0, 4.5)
TREND_WINDOWS = (5, 10, 20)
SIGMA_FLOOR = 0.02
# A run whose speed factor is more than this much beyond the slowest runner seen in training is not normalised further,
# so a uniform code slowdown cannot hide completely behind "a slow runner".
SPEED_CAP_MARGIN = 1.10
EMPIRICAL_RATIO_MARGIN = 0.10
# Steps that set the runner speed factor: long enough to time well, and not dominated by a cache.
REFERENCE_MIN_MS = 200
REFERENCE_EXCLUDE = frozenset({"mypy-gate", "mypy-island"})
# Copies of the constants in mesh_cli/verify.py (kept local so this script imports nothing from the repo).
DEFAULT_RATIO_LIMIT = 1.25
DEFAULT_TOLERANCE_MS = 50
NULL_MEDIAN_MARGIN_MS = {"player-package-gate": 700, "verify-demo": 250, "web-smoke": 600}
EXTERNAL_KEY = "<full pytest>"
DEFAULT_BUDGET_PATH = Path(__file__).resolve().parent / "metrics" / "verify_step_budget.json"
DEFAULT_MODEL_PATH = Path(__file__).resolve().parent / "metrics" / "verify_step_speed_model.json"
# Copy of mesh_cli/verify_speed_advisory.py's DEFAULT_MIN_REFERENCE_STEPS: with fewer reference steps left, no estimate.
MIN_REFERENCE_STEPS = 3
# The median of n iid normal draws has sd ~ MEDIAN_SD_FACTOR * sd / sqrt(n).
MEDIAN_SD_FACTOR = 1.2533


@dataclass(frozen=True)
class Run:
    run_id: int
    os: str
    event: str
    sha: str
    date: str
    regime: str
    job_s: float | None
    full_pytest_s: float | None
    steps: dict[str, int]


@dataclass(frozen=True)
class Sample:
    """The timings a rule sees for one run: verify-all steps (ms) and the same job's full pytest step (ms), if known."""

    steps: dict[str, float]
    external_ms: float | None


Checker = Callable[[Sample], frozenset[str]]
Fitter = Callable[[Sequence[Run]], Checker]


def sample_of(run: Run) -> Sample:
    return Sample({k: float(v) for k, v in run.steps.items()}, run.full_pytest_s * 1000.0 if run.full_pytest_s else None)


def inject_step(sample: Sample, step: str, factor: float) -> Sample:
    """One step regresses by ``factor``. The fast tier also runs inside the full pytest step, so that grows by the same ms."""
    steps = dict(sample.steps)
    added = steps[step] * (factor - 1.0)
    steps[step] += added
    external = sample.external_ms
    if external is not None and step == "pytest-fast":
        external += added
    return Sample(steps, external)


def inject_all(sample: Sample, factor: float, slopes: Mapping[str, float] | None = None) -> Sample:
    """Whole run slower by ``factor``: uniformly, or like a slower runner (each step by factor**slope, slopes from the data)."""
    slopes = slopes or {}
    external = sample.external_ms * factor ** slopes.get(EXTERNAL_KEY, 1.0) if sample.external_ms is not None else None
    return Sample({k: v * factor ** slopes.get(k, 1.0) for k, v in sample.steps.items()}, external)


# ---------------------------------------------------------------------------------------------------------------- loading


def _run_from_entry(entry: Mapping[str, object], steps: dict[str, int]) -> Run:
    def opt_float(key: str) -> float | None:
        value = entry.get(key)
        return float(value) if isinstance(value, (int, float)) else None

    return Run(
        run_id=int(str(entry["run_id"])),
        os=str(entry["os"]),
        event=str(entry["event"]),
        sha=str(entry["sha"]),
        date=str(entry["date"]),
        regime=str(entry.get("regime", "post-opt")),
        job_s=opt_float("job_s"),
        full_pytest_s=opt_float("full_pytest_s"),
        steps=steps,
    )


def _steps_from_durations(payload: Mapping[str, object]) -> dict[str, int]:
    rows = payload.get("steps")
    result: dict[str, int] = {}
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict) and isinstance(row.get("name"), str) and isinstance(row.get("ms"), (int, float)):
                result[str(row["name"])] = int(row["ms"])
    return result


def load_index(index_path: Path, durations_dir: Path) -> list[Run]:
    runs = []
    for entry in json.loads(index_path.read_text(encoding="utf-8")):
        payload = json.loads((durations_dir / str(entry["durations"])).read_text(encoding="utf-8"))
        runs.append(_run_from_entry(entry, _steps_from_durations(payload)))
    return sorted(runs, key=lambda r: (r.os, r.date, r.run_id))


def load_data(path: Path) -> list[Run]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    runs = [_run_from_entry(entry, {str(k): int(v) for k, v in entry["steps"].items()}) for entry in payload["runs"]]
    return sorted(runs, key=lambda r: (r.os, r.date, r.run_id))


def write_data(runs: Sequence[Run], path: Path) -> None:
    entries = [
        {
            "run_id": r.run_id,
            "os": r.os,
            "event": r.event,
            "sha": r.sha,
            "date": r.date,
            "regime": r.regime,
            "job_s": r.job_s,
            "full_pytest_s": r.full_pytest_s,
            "steps": dict(sorted(r.steps.items())),
        }
        for r in runs
    ]
    payload = {
        "schema_version": 1,
        "source": "GitHub Actions workflow CI of septimus82/Mesh; artifact mesh-artifacts-<os>-py3.11, verify_step_durations.json",
        "units": {"steps": "ms", "job_s": "s", "full_pytest_s": "s"},
        "runs": entries,
    }
    path.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def current_thresholds(budget_path: Path, os_name: str) -> dict[str, int]:
    """The thresholds verify-all applies on a fresh CI runner (no history, so no median and the null-median margins apply)."""
    raw = json.loads(budget_path.read_text(encoding="utf-8"))
    budgets = dict(raw.get("budgets_ms", {}))
    ratios = dict(raw.get("ratio_limits", {}))
    platform = raw.get("platforms", {}).get(os_name)
    if isinstance(platform, dict):
        budgets.update(platform.get("budgets_ms", {}))
        ratios.update(platform.get("ratio_limits", {}))
    tolerance = int(raw.get("tolerance_ms", DEFAULT_TOLERANCE_MS))
    result = {}
    for name, budget in budgets.items():
        ratio = float(ratios.get(name, DEFAULT_RATIO_LIMIT))
        result[name] = max(int(budget) + tolerance, int(int(budget) * ratio)) + NULL_MEDIAN_MARGIN_MS.get(name, 0)
    return result


# --------------------------------------------------------------------------------------------------------------- statistics


def p90(values: Sequence[float]) -> float:
    return statistics.quantiles(values, n=10, method="inclusive")[8] if len(values) > 1 else values[0]


def cv(values: Sequence[float]) -> float:
    return statistics.stdev(values) / statistics.mean(values) if len(values) > 1 else 0.0


@dataclass(frozen=True)
class LineFit:
    """y = a + b*z + e with residual spread ``sigma``; ``upper`` is the one-sided k-sigma prediction bound."""

    a: float
    b: float
    sigma: float
    n: int
    z_mean: float
    sxx: float
    slope_fitted: bool

    def upper(self, z: float, k: float) -> float:
        inflation = 1.0 + 1.0 / self.n
        if self.slope_fitted and self.sxx > 0.0:
            inflation += (z - self.z_mean) ** 2 / self.sxx
        return self.a + self.b * z + k * self.sigma * math.sqrt(inflation)


def fit_line(z: Sequence[float], y: Sequence[float], slope: float | None) -> LineFit:
    n = len(y)
    z_mean = statistics.fmean(z)
    sxx = sum((v - z_mean) ** 2 for v in z)
    if slope is None:
        b = sum((zi - z_mean) * (yi - statistics.fmean(y)) for zi, yi in zip(z, y)) / sxx if sxx > 0.0 else 0.0
        params = 2
    else:
        b = slope
        params = 1
    a = statistics.fmean(yi - b * zi for zi, yi in zip(z, y))
    sse = sum((yi - a - b * zi) ** 2 for zi, yi in zip(z, y))
    sigma = max(SIGMA_FLOOR, math.sqrt(sse / max(1, n - params)))
    return LineFit(a, b, sigma, n, z_mean, sxx, slope is None)


def reference_medians(train: Sequence[Run]) -> dict[str, float]:
    names = set.intersection(*(set(r.steps) for r in train))
    medians = {name: float(statistics.median(r.steps[name] for r in train)) for name in sorted(names)}
    return {k: v for k, v in medians.items() if v >= REFERENCE_MIN_MS and k not in REFERENCE_EXCLUDE}


def log_speed(steps: Mapping[str, float], ref: Mapping[str, float], exclude: str = "") -> float:
    """Runner speed factor (log, 0 = median runner): median over the reference steps, leaving out ``exclude``."""
    return statistics.median(math.log(max(steps[k], 1.0) / m) for k, m in ref.items() if k != exclude and k in steps)


def runner_slopes(post: Sequence[Run]) -> dict[str, float]:
    """How strongly each step follows the runner speed (log-log slope on the other steps' speed), over all given runs."""
    ref = reference_medians(post)
    slopes = {}
    for name in sorted(set.intersection(*(set(r.steps) for r in post))):
        z = [log_speed({k: float(v) for k, v in r.steps.items()}, ref, exclude=name) for r in post]
        slopes[name] = fit_line(z, [math.log(max(r.steps[name], 1)) for r in post], None).b
    with_external = [r for r in post if r.full_pytest_s]
    if len(with_external) > 2:
        z = [log_speed({k: float(v) for k, v in r.steps.items()}, ref) for r in with_external]
        slopes[EXTERNAL_KEY] = fit_line(z, [math.log(float(r.full_pytest_s or 1.0)) for r in with_external], None).b
    return slopes


# ----------------------------------------------------------------------------------------------------------------- policies


def current_policy(thresholds: Mapping[str, int]) -> Fitter:
    def fit(_train: Sequence[Run]) -> Checker:
        def check(sample: Sample) -> frozenset[str]:
            return frozenset(n for n, t in thresholds.items() if sample.steps.get(n, 0.0) > t)

        return check

    return fit


def empirical_ratio_policy(checked: Sequence[str]) -> Fitter:
    """The method behind the committed budgets: median, limit = slowest/median + 10 points, from all training runs."""

    def fit(train: Sequence[Run]) -> Checker:
        limits = {}
        for name in checked:
            values = [float(r.steps[name]) for r in train]
            median = statistics.median(values)
            limits[name] = median * (max(values) / median + EMPIRICAL_RATIO_MARGIN)

        def check(sample: Sample) -> frozenset[str]:
            return frozenset(n for n, t in limits.items() if sample.steps[n] > t)

        return check

    return fit


def normalised_policy(checked: Sequence[str], *, covariate: str, slope: float | None, k: float, cap: bool = False) -> Fitter:
    """log(step) <= a + b*z + k*sigma, where z is a per-run speed covariate.

    covariate: ``none`` (fixed per-platform limit from the spread), ``total`` (same-run total, unsafe), ``loo`` (median of
    the other reference steps of the same run), ``external`` (the job's full pytest step, measured before verify-all).
    """

    def fit(train: Sequence[Run]) -> Checker:
        ref = reference_medians(train)
        total_median = statistics.median(sum(r.steps.values()) for r in train)
        externals = [r.full_pytest_s * 1000.0 for r in train if r.full_pytest_s]
        external_median = statistics.median(externals) if externals else 1.0

        def z_of(sample: Sample, name: str) -> float:
            if covariate == "none":
                return 0.0
            if covariate == "total":
                return math.log(sum(sample.steps.values()) / total_median)
            if covariate == "loo":
                return log_speed(sample.steps, ref, exclude=name)
            if sample.external_ms is None:
                return 0.0
            return math.log(sample.external_ms / external_median)

        fits: dict[str, tuple[LineFit, float]] = {}
        for name in checked:
            train_samples = [sample_of(r) for r in train]
            z = [z_of(s, name) for s in train_samples]
            y = [math.log(max(s.steps[name], 1.0)) for s in train_samples]
            fits[name] = (fit_line(z, y, slope), max(z) + math.log(SPEED_CAP_MARGIN))

        def check(sample: Sample) -> frozenset[str]:
            flagged = set()
            for name, (line, z_cap) in fits.items():
                z = z_of(sample, name)
                if cap:
                    z = min(z, z_cap)
                if math.log(max(sample.steps[name], 1.0)) > line.upper(z, k):
                    flagged.add(name)
            return frozenset(flagged)

        return check

    return fit


def recommended_policy(checked: Sequence[str], k: float) -> Fitter:
    return normalised_policy(checked, covariate="loo", slope=None, k=k)


def model_checked_steps(thresholds: Mapping[str, int]) -> list[str]:
    """Steps the advisory model covers: the budgeted and important ones, without the cache-bound mypy steps."""
    return sorted((set(thresholds) | set(IMPORTANT_STEPS)) - REFERENCE_EXCLUDE)


def fit_platform_model(post: Sequence[Run], checked: Sequence[str], k: float) -> dict[str, Any]:
    """The advisory model for one platform: B's fitted line per step, with a constant allowance exp(k*sigma)."""
    ref = reference_medians(post)
    speeds = [log_speed({kk: float(v) for kk, v in r.steps.items()}, ref) for r in post]
    steps: dict[str, Any] = {}
    for name in checked:
        z = [log_speed({kk: float(v) for kk, v in r.steps.items()}, ref, exclude=name) for r in post]
        line = fit_line(z, [math.log(max(r.steps[name], 1)) for r in post], None)
        steps[name] = {
            "base_ms": round(math.exp(line.a)),
            "slope": round(line.b, 4),
            "sigma": round(line.sigma, 4),
            "allowance": round(math.exp(k * line.sigma), 4),
            "n": line.n,
        }
    return {
        "runs": len(post),
        "first_run": min(r.date for r in post),
        "last_run": max(r.date for r in post),
        "speed_reference_ms": {name: round(v) for name, v in ref.items()},
        "speed_seen": [round(math.exp(min(speeds)), 3), round(math.exp(max(speeds)), 3)],
        "speed_log_sd": round(statistics.stdev(speeds), 4),
        "steps": steps,
    }


def model_estimate(platform_model: Mapping[str, Any], steps: Mapping[str, float], name: str) -> tuple[float, float] | None:
    """(expected ms, advisory threshold ms) for one step, by the formula of mesh_cli/verify_speed_advisory.py; None = no estimate."""
    params = platform_model["steps"][name]
    ref = platform_model["speed_reference_ms"]
    logs = [math.log(max(steps[kk], 1.0) / float(v)) for kk, v in ref.items() if kk != name and kk in steps]
    if len(logs) < MIN_REFERENCE_STEPS:
        return None
    expected = float(params["base_ms"]) * math.exp(statistics.median(logs)) ** float(params["slope"])
    return expected, expected * float(params["allowance"])


def model_policy(checked: Sequence[str], k: float) -> Fitter:
    """A. The advisory rule exactly as verify-all evaluates it, fitted on the training runs."""

    def fit(train: Sequence[Run]) -> Checker:
        model = fit_platform_model(train, checked, k)

        def check(sample: Sample) -> frozenset[str]:
            flagged = set()
            for name in checked:
                estimate = model_estimate(model, sample.steps, name) if name in sample.steps else None
                if estimate is not None and sample.steps[name] > estimate[1]:
                    flagged.add(name)
            return frozenset(flagged)

        return check

    return fit


def policies(thresholds: Mapping[str, int], checked: Sequence[str], k: float) -> list[tuple[str, Fitter]]:
    return [
        ("a. current rule (committed budgets)", current_policy(thresholds)),
        ("x. same-run total normalisation (unsafe)", normalised_policy(checked, covariate="total", slope=1.0, k=k)),
        ("b1. leave-one-out speed, unit slope", normalised_policy(checked, covariate="loo", slope=1.0, k=k)),
        ("B. recommended: leave-one-out speed, fitted slope", recommended_policy(checked, k)),
        ("A. advisory model (B as verify-all evaluates it)", model_policy(model_checked_steps(thresholds), k)),
        ("b3. B + speed cap", normalised_policy(checked, covariate="loo", slope=None, k=k, cap=True)),
        ("c1. per-platform limit, k*sigma of log time", normalised_policy(checked, covariate="none", slope=0.0, k=k)),
        ("c2. per-platform limit, slowest/median + 0.10", empirical_ratio_policy(checked)),
        ("e. external calibration (job's full pytest)", normalised_policy(checked, covariate="external", slope=None, k=k)),
    ]


def cross_validate(runs: Sequence[Run], fitter: Fitter) -> list[tuple[Run, Checker]]:
    return [(run, fitter([r for r in runs if r is not run])) for run in runs]


# ------------------------------------------------------------------------------------------------------------------ output


def table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def frac(count: int, total: int) -> str:
    return f"{count}/{total} ({100.0 * count / total:.0f}%)" if total else "n/a"


def sec(ms: float) -> str:
    return f"{ms / 1000.0:.2f}"


def distribution_section(os_name: str, post: Sequence[Run], pre: Sequence[Run], thresholds: Mapping[str, int]) -> str:
    names = sorted(
        {n for n in set.intersection(*(set(r.steps) for r in post)) if statistics.median(r.steps[n] for r in post) >= REFERENCE_MIN_MS}
        | set(thresholds),
        key=lambda n: -statistics.median(r.steps.get(n, 0) for r in post),
    )
    rows = []
    for name in names:
        values = [float(r.steps.get(name, 0)) for r in post]
        median = statistics.median(values)
        threshold = thresholds.get(name)
        over_post = sum(1 for v in values if threshold is not None and v > threshold)
        over_pre = sum(1 for r in pre if threshold is not None and r.steps.get(name, 0) > threshold)
        rows.append(
            [
                name,
                sec(median),
                sec(p90(values)),
                sec(max(values)),
                f"{max(values) / median:.2f}",
                f"{cv(values):.2f}",
                sec(threshold) if threshold is not None else "-",
                f"{threshold / median:.2f}" if threshold is not None else "-",
                frac(over_post, len(post)) if threshold is not None else "-",
                frac(over_pre, len(pre)) if threshold is not None and pre else "-",
            ]
        )
    head = ["step", "median s", "p90 s", "max s", "max/median", "CV", "threshold s", "threshold/median", "over (post-opt)", "over (pre-opt)"]
    return f"### {os_name}: per-step distribution, {len(post)} post-opt runs\n\n" + table(head, rows)


def speed_section(os_name: str, post: Sequence[Run], thresholds: Mapping[str, int]) -> str:
    ref = reference_medians(post)
    speed = {r.run_id: log_speed({k: float(v) for k, v in r.steps.items()}, ref) for r in post}
    factors = sorted(math.exp(v) for v in speed.values())
    out = [f"### {os_name}: runner speed factor (median of {len(ref)} reference steps: {', '.join(ref)})", ""]
    out.append(
        f"Speed factor over {len(post)} runs: min {factors[0]:.2f}, median {statistics.median(factors):.2f}, max {factors[-1]:.2f}; "
        f"slowest/fastest {factors[-1] / factors[0]:.2f}; sd of log {statistics.pstdev(list(speed.values())):.3f}."
    )
    rows = []
    for name in sorted(set(ref) | set(IMPORTANT_STEPS) | set(thresholds)):
        z = [log_speed({k: float(v) for k, v in r.steps.items()}, ref, exclude=name) for r in post]
        y = [math.log(max(r.steps[name], 1)) for r in post]
        line = fit_line(z, y, None)
        resid = [yi - line.a - line.b * zi for zi, yi in zip(z, y)]
        order = list(range(len(post)))
        rows.append(
            [
                name,
                f"{statistics.correlation(z, y):.2f}",
                f"{line.b:.2f}",
                f"{1.0 - statistics.pvariance(resid) / statistics.pvariance(y):.2f}",
                f"{statistics.pstdev(y):.3f}",
                f"{statistics.pstdev(resid):.3f}",
                f"{statistics.correlation(order, resid):.2f}",
                f"{math.exp(fit_line([float(i) for i in order], resid, None).b * (len(order) - 1)):.3f}",
            ]
        )
    head = ["step", "corr with other steps' speed", "slope", "variance explained", "sd log (raw)", "sd log (residual)", "residual drift corr"]
    head.append("runner-adjusted growth, first to last run")
    out += ["", table(head, rows)]

    check = current_policy(thresholds)([])
    rank = {rid: i + 1 for i, rid in enumerate(sorted(speed, key=lambda rid: -speed[rid]))}
    run_rows = []
    for r in sorted(post, key=lambda r: -speed[r.run_id]):
        flagged = sorted(check(sample_of(r)))
        run_rows.append([r.run_id, r.sha[:7], r.event, f"{math.exp(speed[r.run_id]):.2f}", rank[r.run_id], ", ".join(flagged) or "-"])
    out += ["", "Runs, slowest first (flagged = steps over the current thresholds):", "", table(["run", "sha", "event", "speed", "rank", "flagged"], run_rows)]

    pairs = []
    by_sha: dict[str, list[Run]] = {}
    for r in post:
        by_sha.setdefault(r.sha, []).append(r)
    for sha, group in sorted(by_sha.items()):
        push = [r for r in group if r.event == "push"]
        pr = [r for r in group if r.event == "pull_request"]
        if push and pr:
            pairs.append((speed[push[0].run_id], speed[pr[0].run_id]))
    if len(pairs) > 2:
        diffs = [math.exp(b - a) for a, b in pairs]
        out += [
            "",
            f"Same commit, push vs pull_request ({len(pairs)} pairs): PR/push speed ratio median {statistics.median(diffs):.2f}, "
            f"range {min(diffs):.2f}-{max(diffs):.2f}; correlation of the two runs' speed factors "
            f"{statistics.correlation([a for a, _ in pairs], [b for _, b in pairs]):.2f}; PR slower in "
            f"{sum(1 for d in diffs if d > 1.0)}/{len(diffs)}.",
        ]
    return "\n".join(out)


def policy_section(os_name: str, post: Sequence[Run], pre: Sequence[Run], thresholds: Mapping[str, int], k: float) -> str:
    checked = sorted(set(thresholds) | set(IMPORTANT_STEPS))
    out = [f"### {os_name}: policies (k = {k}; cross-validated over {len(post)} post-opt runs)", ""]
    out.append(
        f"Checked steps: current rule {', '.join(sorted(thresholds))}; other rules {', '.join(checked)}. "
        "Detection = the regressed step itself is flagged. Uniform = every step x"
        f"{WHOLE_RUN_FACTOR}; runner-like = every step x{WHOLE_RUN_FACTOR}**slope (the slopes in the speed table), i.e. the way the "
        "observed runners differ; both count runs with any step flagged."
    )
    slopes = runner_slopes(post)
    head = ["policy", "false failures (runs)", f"uniform x{WHOLE_RUN_FACTOR} fails", f"runner-like x{WHOLE_RUN_FACTOR} fails"]
    head += [f"{name} x{f}" for name in IMPORTANT_STEPS for f in STEP_FACTORS]
    rows = []
    pre_rows = []
    details: list[list[object]] = []
    for label, fitter in policies(thresholds, checked, k):
        folds = cross_validate(post, fitter)
        base = sum(1 for r, c in folds if c(sample_of(r)))
        whole = sum(1 for r, c in folds if c(inject_all(sample_of(r), WHOLE_RUN_FACTOR)))
        runner_like = sum(1 for r, c in folds if c(inject_all(sample_of(r), WHOLE_RUN_FACTOR, slopes)))
        row: list[object] = [label, frac(base, len(post)), frac(whole, len(post)), frac(runner_like, len(post))]
        for r, c in folds:
            flagged_now = sorted(c(sample_of(r)))
            if flagged_now:
                details.append([label, r.run_id, r.sha[:7], r.event, ", ".join(flagged_now)])
        for name in IMPORTANT_STEPS:
            for f in STEP_FACTORS:
                if label.startswith("a.") and name not in thresholds:
                    row.append("not checked")
                    continue
                hits = sum(1 for r, c in folds if name in c(inject_step(sample_of(r), name, f)))
                row.append(f"{100.0 * hits / len(post):.0f}%")
        rows.append(row)
        if pre:
            full_fit = fitter(post)
            flagged = [", ".join(sorted(full_fit(sample_of(r)))) or "-" for r in pre]
            pre_rows.append([label, frac(sum(1 for f in flagged if f != "-"), len(pre))] + flagged)
    out += ["", table(head, rows), "", "Historical runs each rule fails (cross-validated):", "", table(["policy", "run", "sha", "event", "flagged"], details)]
    if pre:
        out += [
            "",
            "Real regression: the pre-optimisation code (slower pytest-fast and exception-policy-scan), judged by rules fitted on all "
            "post-opt runs:",
            "",
            table(["policy", "runs flagged"] + [f"{r.run_id} ({r.sha[:7]} {r.event})" for r in pre], pre_rows),
        ]
    return "\n".join(out)


def real_regression_section(os_name: str, post: Sequence[Run], pre: Sequence[Run]) -> str:
    """How large the pre-optimisation slowdown really was: observed / expected for that run's runner (fitted on post-opt)."""
    ref = reference_medians(post)
    names = ("pytest-fast", "exception-policy-scan", "swallow-scan-gate", "verify-demo")
    lines = {}
    for name in names:
        z = [log_speed({k: float(v) for k, v in r.steps.items()}, ref, exclude=name) for r in post]
        lines[name] = fit_line(z, [math.log(max(r.steps[name], 1)) for r in post], None)
    rows = []
    for r in pre:
        steps = {k: float(v) for k, v in r.steps.items()}
        row: list[object] = [r.run_id, r.sha[:7], r.event, f"{math.exp(log_speed(steps, ref)):.2f}"]
        for name in names:
            line = lines[name]
            row.append(f"{math.exp(math.log(steps[name]) - line.a - line.b * log_speed(steps, ref, exclude=name)):.2f}")
        rows.append(row)
    head = ["run", "sha", "event", "speed"] + [f"{n} observed/expected" for n in names]
    return f"### {os_name}: size of the real pre-optimisation regression\n\n" + table(head, rows)


def trend_section(os_name: str, post: Sequence[Run]) -> str:
    """Uniform (whole-run) regressions look like a slow runner in one run, but they move the median over many runs."""
    ref = reference_medians(post)
    speeds = [log_speed({k: float(v) for k, v in r.steps.items()}, ref) for r in post]
    sd = statistics.stdev(speeds)
    rows = []
    for n in TREND_WINDOWS:
        if n > len(speeds):
            continue
        medians = [statistics.median(speeds[i : i + n]) for i in range(len(speeds) - n + 1)]
        # Median of n independent runner draws: sd ~ 1.2533 * sd / sqrt(n); a uniform slowdown above k sd of it is visible.
        sd_median = 1.2533 * sd / math.sqrt(n)
        rows.append(
            [
                n,
                f"{math.exp(min(medians)):.2f}-{math.exp(max(medians)):.2f}",
                f"{sd_median:.3f}",
                f"{math.exp(3.0 * sd_median):.2f}",
                f"{math.exp(DEFAULT_K * sd_median):.2f}",
            ]
        )
    head = ["window (runs)", "rolling median speed, observed range", "sd of log median (iid)", "detectable uniform slowdown, 3 sd", f"{DEFAULT_K:g} sd"]
    step_rows = []
    for name in IMPORTANT_STEPS:
        z = [log_speed({k: float(v) for k, v in r.steps.items()}, ref, exclude=name) for r in post]
        sigma = fit_line(z, [math.log(max(r.steps[name], 1)) for r in post], None).sigma
        windows = [f"{math.exp(DEFAULT_K * 1.2533 * sigma / math.sqrt(n)):.2f}" for n in TREND_WINDOWS]
        step_rows.append([name, f"{sigma:.3f}", f"{math.exp(DEFAULT_K * sigma):.2f}"] + windows)
    step_head = ["step", "residual sigma", "per run"] + [f"median of {n} runs" for n in TREND_WINDOWS]
    return (
        f"### {os_name}: uniform regressions via the rolling median of the run speed factor\n\n"
        f"Per-run speed sd of log {sd:.3f} over {len(speeds)} runs.\n\n" + table(head, rows) + "\n\n"
        "A persistent isolated regression, judged on the median of the runner-adjusted residuals of the last n runs "
        f"(smallest factor above {DEFAULT_K:g} sd):\n\n" + table(step_head, step_rows)
    )


def combined_section(runs: Sequence[Run], budget_path: Path, k: float) -> str:
    """A code regression usually shows on both OSes; a PR fails if either job flags the regressed step."""
    os_names = sorted({r.os for r in runs})
    labels = ("a. current rule", "B. recommended", "A. advisory model")
    folds: dict[tuple[str, str], dict[int, tuple[Run, Checker]]] = {}
    for os_name in os_names:
        post = [r for r in runs if r.os == os_name and r.regime == "post-opt"]
        thresholds = current_thresholds(budget_path, os_name)
        checked = sorted(set(thresholds) | set(IMPORTANT_STEPS))
        fitters = (current_policy(thresholds), recommended_policy(checked, k), model_policy(model_checked_steps(thresholds), k))
        for label, fitter in zip(labels, fitters):
            folds[(os_name, label)] = {r.run_id: (r, c) for r, c in cross_validate(post, fitter)}
    shared = sorted(set.intersection(*(set(folds[(o, labels[1])]) for o in os_names)))

    def flagged(label: str, run_id: int, name: str | None, factor: float) -> bool:
        for os_name in os_names:
            run, check = folds[(os_name, label)][run_id]
            hits = check(sample_of(run) if name is None else inject_step(sample_of(run), name, factor))
            if hits if name is None else name in hits:
                return True
        return False

    rows = []
    for label in labels:
        row: list[object] = [label, frac(sum(1 for rid in shared if flagged(label, rid, None, 1.0)), len(shared))]
        for name in IMPORTANT_STEPS:
            for f in STEP_FACTORS:
                row.append(f"{100.0 * sum(1 for rid in shared if flagged(label, rid, name, f)) / len(shared):.0f}%")
        rows.append(row)
    head = ["policy", "workflow runs with a false failure"] + [f"{n} x{f}" for n in IMPORTANT_STEPS for f in STEP_FACTORS]
    return f"## Either OS: {len(shared)} workflow runs with both jobs (regression injected into both)\n\n" + table(head, rows)


def retry_section(os_name: str, post: Sequence[Run], thresholds: Mapping[str, int], k: float) -> str:
    """d. Re-run the job once on failure: a run fails only if two independent runners both fail."""
    checked = sorted(set(thresholds) | set(IMPORTANT_STEPS))
    n = len(post)
    job_min = statistics.median(r.job_s for r in post if r.job_s) / 60.0
    common = set.intersection(*(set(r.steps) for r in post))
    verify_min = sum(statistics.median(r.steps[name] for r in post) for name in common) / 60000.0
    out = [
        f"### {os_name}: re-run on failure (median job {job_min:.1f} min)",
        "",
        f"Repeating verify-all inside the same job would add about {verify_min:.1f} min per run (sum of step medians) and cannot remove "
        "the runner-level part of the variance (the 'variance explained' column of the speed table).",
        "",
    ]
    rows = []
    for label, fitter in (
        ("a. current rule", current_policy(thresholds)),
        ("B. recommended", recommended_policy(checked, k)),
    ):
        folds = cross_validate(post, fitter)
        first = sum(1 for r, c in folds if c(sample_of(r)))
        row: list[object] = [label, frac(first, n), f"{100.0 * max(0, first * (first - 1)) / (n * (n - 1)):.1f}%", f"{first / n * job_min:.2f}"]
        for name in ("pytest-fast", "exception-policy-scan", "verify-demo"):
            for f in STEP_FACTORS:
                if label.startswith("a.") and name not in thresholds:
                    row.append("not checked")
                    continue
                hits = sum(1 for r, c in folds if name in c(inject_step(sample_of(r), name, f)))
                row.append(f"{100.0 * hits / n:.0f}% -> {100.0 * max(0, hits * (hits - 1)) / (n * (n - 1)):.0f}%")
        rows.append(row)
    head = ["policy", "first-attempt false failures", "false failures after one re-run", "extra job min per run"]
    head += [f"{name} x{f} (one try -> both tries)" for name in ("pytest-fast", "exception-policy-scan", "verify-demo") for f in STEP_FACTORS]
    out.append(table(head, rows))
    return "\n".join(out)


def sensitivity_section(os_name: str, post: Sequence[Run], thresholds: Mapping[str, int]) -> str:
    checked = sorted(set(thresholds) | set(IMPORTANT_STEPS))
    rows = []
    for k in SENSITIVITY_K:
        folds = cross_validate(post, recommended_policy(checked, k))
        row: list[object] = [k, frac(sum(1 for r, c in folds if c(sample_of(r))), len(post))]
        for name in ("pytest-fast", "exception-policy-scan", "verify-demo", "web-smoke"):
            for f in (1.25, 1.5):
                row.append(f"{100.0 * sum(1 for r, c in folds if name in c(inject_step(sample_of(r), name, f))) / len(post):.0f}%")
        rows.append(row)
    head = ["k", "false failures"] + [f"{n} x{f}" for n in ("pytest-fast", "exception-policy-scan", "verify-demo", "web-smoke") for f in (1.25, 1.5)]
    return f"### {os_name}: recommended rule, sensitivity to k\n\n" + table(head, rows)


def allowance_section(os_name: str, post: Sequence[Run], thresholds: Mapping[str, int], k: float) -> str:
    """What the recommended rule allows over the runner-adjusted expectation, per step (fitted on all post-opt runs)."""
    ref = reference_medians(post)
    rows = []
    for name in sorted(set(thresholds) | set(IMPORTANT_STEPS)):
        z = [log_speed({kk: float(v) for kk, v in r.steps.items()}, ref, exclude=name) for r in post]
        y = [math.log(max(r.steps[name], 1)) for r in post]
        line = fit_line(z, y, None)
        median = statistics.median(r.steps[name] for r in post)
        rows.append(
            [
                name,
                sec(median),
                f"{line.b:.2f}",
                f"{line.sigma:.3f}",
                f"{math.exp(line.upper(line.z_mean, k) - line.a - line.b * line.z_mean):.2f}",
                f"{math.exp(max(z)):.2f}",
                f"{thresholds[name] / median:.2f}" if name in thresholds else "-",
            ]
        )
    head = ["step", "median s", "slope b", "residual sigma", "allowed ratio over expectation", "max speed seen (other steps)", "current threshold/median"]
    return f"### {os_name}: recommended rule parameters (all post-opt runs)\n\n" + table(head, rows)


def report(runs: Sequence[Run], budget_path: Path, k: float) -> str:
    out = [
        "# verify-all step-budget reliability on CI",
        "",
        f"Runs: {len(runs)} ({', '.join(f'{os_name} {sum(1 for r in runs if r.os == os_name)}' for os_name in sorted({r.os for r in runs}))}). "
        f"Budgets: {budget_path.name}.",
    ]
    for os_name in sorted({r.os for r in runs}):
        post = [r for r in runs if r.os == os_name and r.regime == "post-opt"]
        pre = [r for r in runs if r.os == os_name and r.regime == "pre-opt"]
        thresholds = current_thresholds(budget_path, os_name)
        out += [
            "",
            f"## {os_name}",
            "",
            distribution_section(os_name, post, pre, thresholds),
            "",
            speed_section(os_name, post, thresholds),
            "",
            policy_section(os_name, post, pre, thresholds, k),
            "",
            real_regression_section(os_name, post, pre) if pre else "",
            "",
            trend_section(os_name, post),
            "",
            retry_section(os_name, post, thresholds, k),
            "",
            sensitivity_section(os_name, post, thresholds),
            "",
            allowance_section(os_name, post, thresholds, k),
        ]
    if len({r.os for r in runs}) > 1:
        out += ["", combined_section(runs, budget_path, k)]
    return "\n".join(out) + "\n"


def build_model(runs: Sequence[Run], budget_path: Path, k: float) -> dict[str, Any]:
    platforms = {}
    for os_name in sorted({r.os for r in runs}):
        post = [r for r in runs if r.os == os_name and r.regime == "post-opt"]
        platforms[os_name] = fit_platform_model(post, model_checked_steps(current_thresholds(budget_path, os_name)), k)
    return {
        "schema_version": 1,
        "advisory_only": True,
        "description": (
            "Runner-speed model for verify-all's ADVISORY slow-step check (mesh_cli/verify_speed_advisory.py). It never "
            "fails a run; the enforced budgets are verify_step_budget.json. Expected = base_ms * speed**slope, advisory "
            "threshold = expected * allowance (allowance = exp(k*sigma)); speed = median over the speed_reference_ms steps "
            "other than the judged one of current/reference. Refit with tooling/ci_timing_analysis.py --write-model."
        ),
        "fitted_from": "post-opt CI samples (tests job, step verify-all) of GitHub Actions workflow CI",
        "k": k,
        "min_reference_steps": MIN_REFERENCE_STEPS,
        "platforms": platforms,
    }


def write_model(runs: Sequence[Run], budget_path: Path, k: float, path: Path) -> None:
    path.write_text(json.dumps(build_model(runs, budget_path, k), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def rolling_report(runs: Sequence[Run], model: Mapping[str, Any], window: int, k: float) -> str:
    """Persistent slowdowns: the last ``window`` runs per OS, judged against a committed (frozen) model.

    A uniform slowdown of every step looks like a slow runner to the per-run rule; over many runs it moves the median
    runner speed instead. A persistent single-step regression moves the median of that step's runner-adjusted residual.
    Both are compared with k standard deviations of a median of ``window`` independent runs.
    """
    out = [f"# Rolling verify-all timing check (last {window} runs per OS; k = {k:g})", ""]
    for os_name in sorted({r.os for r in runs}):
        pm = model.get("platforms", {}).get(os_name)
        recent = sorted((r for r in runs if r.os == os_name and r.regime == "post-opt"), key=lambda r: (r.date, r.run_id))[-window:]
        if not isinstance(pm, dict) or not recent:
            out += [f"## {os_name}: no model or no runs", ""]
            continue
        ref = {name: float(v) for name, v in pm["speed_reference_ms"].items()}
        n = len(recent)
        speeds = [log_speed({kk: float(v) for kk, v in r.steps.items()}, ref) for r in recent]
        speed_limit = math.exp(k * MEDIAN_SD_FACTOR * float(pm["speed_log_sd"]) / math.sqrt(n))
        median_speed = math.exp(statistics.median(speeds))
        verdict = "PERSISTENT SLOWDOWN" if median_speed > speed_limit else "ok"
        out += [
            f"## {os_name}: {n} runs, {recent[0].date} to {recent[-1].date}",
            "",
            f"Median runner speed {median_speed:.3f} (limit {speed_limit:.3f}; fitted runs' range {pm['speed_seen'][0]}-{pm['speed_seen'][1]}): {verdict}.",
            "",
        ]
        rows = []
        for name, params in sorted(pm["steps"].items()):
            resid = []
            for r in recent:
                steps = {kk: float(v) for kk, v in r.steps.items()}
                estimate = model_estimate(pm, steps, name) if name in steps else None
                if estimate is not None:
                    resid.append(math.log(max(steps[name], 1.0) / estimate[0]))
            if not resid:
                rows.append([name, "-", "-", "no data"])
                continue
            limit = math.exp(k * MEDIAN_SD_FACTOR * float(params["sigma"]) / math.sqrt(len(resid)))
            factor = math.exp(statistics.median(resid))
            rows.append([name, f"{factor:.3f}", f"{limit:.3f}", "PERSISTENT REGRESSION" if factor > limit else "ok"])
        out += [table(["step", "median observed/expected", "limit", "verdict"], rows), ""]
    return "\n".join(out)


def demo() -> None:
    """Self-check on synthetic runs: a slow runner passes the recommended rule, an isolated 2x regression does not."""
    names = ("pytest-fast", "verify-demo", "web-smoke", "exception-policy-scan", "swallow-scan-gate", "mypy-gate", "player-package-gate", "verify-strict")
    base = {n: 1000.0 * (i + 1) for i, n in enumerate(names)}
    runs = []
    for i in range(12):
        # Run i is 5% slower per index (a slower runner) with up to 2% per-step jitter.
        steps = {n: int(v * (1.0 + 0.05 * i) * (1.0 + 0.01 * ((i * 7 + j) % 3))) for j, (n, v) in enumerate(base.items())}
        runs.append(Run(i, "linux", "push", f"{i:07d}", f"2026-01-{i + 1:02d}", "post-opt", None, None, steps))
    check = recommended_policy(IMPORTANT_STEPS, DEFAULT_K)(runs[1:])
    slow = sample_of(runs[0])
    assert not check(inject_all(slow, 1.3)), "a uniformly slower runner must pass"
    assert "pytest-fast" in check(inject_step(slow, "pytest-fast", 2.0)), "an isolated 2x regression must be flagged"
    assert not check(slow)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--data", type=Path, help="compact data file written by --write-data")
    parser.add_argument("--index", type=Path, help="index of runs (JSON list)")
    parser.add_argument("--durations-dir", type=Path, help="folder with the runs' verify_step_durations JSON files")
    parser.add_argument("--budget", type=Path, default=DEFAULT_BUDGET_PATH, help="verify_step_budget.json to replay")
    parser.add_argument("--k", type=float, default=DEFAULT_K, help="sigma multiple for the fitted rules")
    parser.add_argument("--write-data", type=Path, help="write the compact data file (--data and --index together: merged) and exit")
    parser.add_argument("--write-model", type=Path, help="fit the advisory speed model from the post-opt runs, write it and exit")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH, help="advisory speed model judged against by --rolling")
    parser.add_argument("--rolling", type=int, metavar="N", help="rolling check of the last N runs per OS against --model, then exit")
    parser.add_argument("--self-check", action="store_true", help="run the synthetic self-check and exit")
    args = parser.parse_args(argv)
    if args.self_check:
        demo()
        print("self-check ok")
        return 0
    if args.data is None and (args.index is None or args.durations_dir is None):
        parser.error("give --data, or --index with --durations-dir")
    loaded = load_data(args.data) if args.data is not None else []
    if args.index is not None and args.durations_dir is not None:
        known = {(r.run_id, r.os) for r in loaded}
        loaded += [r for r in load_index(args.index, args.durations_dir) if (r.run_id, r.os) not in known]
    runs = sorted(loaded, key=lambda r: (r.os, r.date, r.run_id))
    if args.write_data is not None:
        write_data(runs, args.write_data)
        return 0
    if args.write_model is not None:
        write_model(runs, args.budget, args.k, args.write_model)
        return 0
    if args.rolling is not None:
        print(rolling_report(runs, json.loads(args.model.read_text(encoding="utf-8")), args.rolling, args.k), end="")
        return 0
    print(report(runs, args.budget, args.k), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
