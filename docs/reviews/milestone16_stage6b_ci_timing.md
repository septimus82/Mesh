# verify-all slow-step budgets: Windows runner variability (Milestone 16 Stage 6B, Part E)

**Data:** 2026-10-25, CI workflow, job `tests (<os>, py3.11)`, step verify-all; 71 job samples from 36 workflow runs.
`tooling/ci_timing_analysis.py --data milestone16_stage6b_evidence/ci_timing_data.json` prints every number here.
**No budget, baseline, workflow or engine file was changed.**

## Summary

- **The two failures were slow runners, not code.** Both Windows failures on PR #344's pull_request runs (run
  `40210460482`, pytest-fast 125.4 s > 121.8 s; run `40214571672`, exception-policy-scan 3.97 s > 3.74 s) came from the
  two slowest of 31 Windows runners, with speed factors 1.27 and 1.32 (median runner = 1.0). In both runs every step
  was slow, and the failing step was within what its runner predicts.
- **Runner speed dominates step times.**
  - Fastest to slowest runner: **2.12×** on Windows, 1.78× on Linux.
  - For the budgeted steps, the speed of the run's *other* steps explains 70–97% of each step's (log) time variance:
    Windows pytest-fast 84%, verify-demo 94%, exception-policy-scan 70%; Linux 85–97%.
  - The push and pull_request runs of one commit get unrelated runners (speed correlation −0.20 on Windows, −0.04 on
    Linux), and pull_request runs are not slower (slower in 7 of 15 pairs). Both failures landing on PR runs was
    chance.
- **Same-run total normalisation is unsafe, as the owner suspected.** pytest-fast is about 65% of the run's step total,
  so its own regression raises the normaliser: a ×2 regression moves its share by only ×1.21. Measured: it detects
  **0%** of ×2 pytest-fast regressions on both OSes, and 0 of 9 real regression runs.
- **The recommended rule (B) is leave-one-out speed calibration.**
  - Estimate the runner's speed for step j as the median over 7–10 *other* reference steps of (step / its median).
  - Threshold = base × speed^slope × allowance, with the slope and allowance fitted per platform and step from at
    least 20 CI runs, and allowance = exp(4σ).
  - It flags genuine isolated slowdowns far better than today, and stops failing on slow runners.

## Before and after

Cross-validated: each run is judged by a rule fitted on the other runs. Injected regressions multiply one step.

| | Current rule | Recommended (B) |
|---|---|---|
| False failures, either OS (31 workflow runs) | 2/31 | 1/31 |
| Windows jobs failing on a realistic ×1.3-slower runner | 14/31 | 2/31 |
| Linux jobs failing on a realistic ×1.3-slower runner | 17/31 | 0/31 |
| ×1.5 isolated regression detected: pytest-fast / verify-demo / exception-policy-scan / web-smoke | 90 / 81 / 94 / 81% | 100 / 100 / 97 / 100% |
| swallow-scan-gate ×1.5 (not budgeted today) | 0% | 100% |
| ×2 isolated regression detected | 94–100% | 100% |
| Real earlier regression (pre-optimisation runs: pytest-fast ×1.19–1.32, exception-policy-scan ×1.10–1.73 of the runner-adjusted expectation) | 3/5 workflow runs | 5/5 |

**What B gives up:**

- **Small ×1.25 regressions** in verify-demo and exception-policy-scan: detected 19% and 29%, against 48% and 68% today.
  Today's rule only "detects" them on slow runners: the same luck that causes its false failures.
- **A slowdown that hits every step equally** looks like a slow runner, so it is invisible within one run. A scheduled
  rolling median across 10–20 main runs covers it: it detects uniform slowdowns of about 1.31× (Windows) and 1.22×
  (Linux) at 20 runs, and persistent single-step regressions of 1.05–1.15× at 10 runs.
- **The remaining false failure** is run `40212122684` (74f6eef, pull_request). pytest-fast took 88.2 s on a fast
  runner (speed 0.65), where about 63 s was expected. The next commit (one documentation line different) ran normally,
  so this was a runner anomaly.

## The other options

| Option | Result |
|---|---|
| A static per-platform ratio | Would need about ×2.3 for Windows pytest-fast to stop false failures, losing most detection |
| Re-running a failed job | A new runner. False failures fall from 6% to 0.2% for about 0.9 Windows job-minutes per run, but detection falls too (pytest-fast ×1.5: 71% to 50%). Repeating verify-all inside the same job costs 2.3 min and can't help: the runner is the same. |
| Calibrating against the full-pytest step | Fails for pytest-fast: the fast tests run inside full pytest too (3/3/35% detection) |
| A fixed stdlib calibration workload, timed in milliseconds | Truly independent, and it would also separate uniform code slowdowns from slow runners. No history exists yet; record it for about 20 runs and re-evaluate. |

## Recommendation (not made)

Adopt B with k = 4 on both platforms, plus a scheduled rolling-median check, and don't budget mypy-gate: its time
(0.9–30 s) follows the mypy cache, not the runner. This is not a blanket increase: the threshold follows the measured
runner. Windows pytest-fast's limit would be:

| Runner | Limit |
|---|---|
| Fastest observed | about 87 s (against 121.8 s today) |
| Median | about 128 s |
| Slowest observed | about 160 s, where its expected time is about 113 s |

On Linux, every budgeted step except verify-demo gets a *tighter* allowance than today.

| Step (Windows / Linux) | Slope | σ | Allowance | Today's threshold / median |
|---|---|---|---|---|
| pytest-fast | 0.80 / 0.74 | 0.086 / 0.035 | 1.42 / 1.15 | 1.35 / 1.27 |
| verify-demo | 1.33 / 1.40 | 0.077 / 0.068 | 1.37 / 1.32 | 1.48 / 1.53 |
| exception-policy-scan | 0.49 / 0.73 | 0.083 / 0.057 | 1.40 / 1.26 | 1.29 / 1.26 |
| web-smoke | 0.78 / 0.87 | 0.051 / 0.029 | 1.23 / 1.13 | 1.46 / 1.48 |
| player-package-gate | 0.90 / 0.95 | 0.042 / 0.030 | 1.19 / 1.13 | 1.75 / 2.02 |
| swallow-scan-gate (new) | 0.62 / 0.80 | 0.086 / 0.052 | 1.42 / 1.23 | — |

**The change it would need:**

1. **Budgets.** `verify_step_budget.json` v3, per platform:
   - `speed_reference_ms`;
   - per step: `base_ms`, `slope`, `allowance`;
   - the current budgets kept as the fallback for local machines.
2. **The check.** `mesh_cli/verify.py`'s budget guard computes each step's speed from the other steps and reports the
   speed and the expected time in its message.
3. **Fitting.** Budgets are fitted from at least 20 CI samples, not one run, which today's "update baseline" command
   does from a single, possibly slow, run.
4. **Tests.** A uniformly slow runner passes; one step at ×2 fails; a missing reference step falls back.
5. **An advisory scheduled trend check** on main.

## Caveats

- **The data spans one day.** Refit after about 20 more runs.
- **The tails are heavier than normal** (the 74f6eef anomaly is at z ≈ 4.4), so k = 4 is an empirical choice.
- **pytest-fast grew** by about 11% (Linux) and 7% (Windows) during the day, after allowing for runner speed, as tests
  were added. The model needs refitting when accepted growth uses up the 1.15 Linux allowance.
- **79 older runs** have no step timings: verify-all didn't run, or the artifact expired.
