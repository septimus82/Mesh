# verify-all slow-step budgets: the advisory runner-speed check

**Status: advisory only.** The enforced slow-step budgets (`tooling/metrics/verify_step_budget.json`), the enforcement
logic in `mesh_cli/verify.py` (`_evaluate_verify_step_budget_guard`) and the CI workflows are unchanged. The advisory
check never fails a run. Replacing the enforced rule with it needs a separate owner review; this document collects what
that review would need.

Background: `docs/reviews/milestone16_stage6b_ci_timing.md` (rule "B", leave-one-out calibration).

## What advisory mode does

After verify-all's enforced budget check, `mesh_cli/verify_speed_advisory.py` judges every modelled step against what
the run's own runner predicts:

- **Runner speed for step j.** speed_j = exp(median over the reference steps k ≠ j of log(current_k / reference_k)).
  The reference steps are those with a median of at least 200 ms in the fitted runs, without the cache-bound mypy steps:
  8 steps on Linux, 11 on Windows. Step j is left out of its own estimate, so a slow step cannot normalise its own time
  away. A test proves it: changing only step j's time by any factor from 0.1 to 100 leaves speed_j unchanged.
- **Expected time and advisory threshold.** expected_j = base_j × speed_j^slope_j, and threshold_j = expected_j ×
  allowance_j, where allowance_j = exp(4σ_j).
- **No estimate.** With fewer than 3 reference steps present (skipped steps are recorded as 0 ms and failed steps are
  not used), a step gets "no estimate", and only the enforced verdict is reported for it.
- **Outside calibration.** A run whose overall speed is more than 10% outside the fastest and slowest fitted runners is
  reported as such. The limits are then extrapolated along the fitted slopes, so a uniformly slow runner still passes and
  a doubled step is still flagged.
- **Model parameters.** They live in `tooling/metrics/verify_step_speed_model.json`, written by
  `python tooling/ci_timing_analysis.py --data <data> --write-model tooling/metrics/verify_step_speed_model.json` from
  the post-optimisation CI samples. mypy-gate is not modelled: its time (0.9 to 30 s) follows the mypy cache, not the
  runner. A test checks that the committed model is exactly the fit of the committed data.
- **Output.**
  - It writes `artifacts/verify_step_speed_advisory.json`, which CI uploads with the rest of `artifacts/` in
    `mesh-artifacts-<os>-py3.11`.
  - It prints a short table to stderr.
  - The file is not added to verify-all's `artifacts.written` list or `index.json`, so the artifact bundle contract and
    the CI baseline diff are unchanged.

## What it does not do

- It does not change the exit code, `ok`, or `verify_step_budget_check.json`.
  - The helper returns nothing and only reads the enforced payload.
  - Tests run verify-all with a model that flags every step, with no model and with a malformed model, each with the
    enforced check passing and failing. In every case the exit code and `ok` are what the enforced check alone gives.
- It does not use the history median that the enforced check uses locally. It judges the current run only.
- It cannot see a slowdown that hits every step equally: that looks like a slow runner. The rolling check below covers
  it.
- A malformed model file is skipped with one stderr line (`runner-speed check skipped: ...`). It does not fail anything.

## How to read its output

A recorded CI run (Windows run 40210460482, one of the two observed false failures), with the committed model:

```
[Mesh][Verify] verify slow-step budget exceeded (windows budgets): pytest-fast: budget_ms=93708 tolerance_ms=50 ratio_limit=1.30 threshold_ms=121820 current_ms=125398 ...
[Mesh][Verify][advisory] runner-speed check (windows): advisory only, never fails the run; enforced budgets unchanged.
[Mesh][Verify][advisory] run speed 1.25 (calibrated range 0.621-1.302; 1.0 = median CI runner)
  step                       now s  speed  expect s  adv. limit s  advisory     enf. limit s  enforced
  exception-policy-scan       3.61   1.27      3.30          4.56  ok                   3.74  ok
  player-package-gate         1.97   1.27      2.09          2.47  ok                   2.91  ok
  pytest-fast               125.40   1.24    113.66        166.50  ok                 121.82  over
  swallow-scan-gate           4.41   1.24      3.89          5.42  ok                      -  not budgeted
  verify-demo                22.96   1.24     24.18         33.23  ok                  25.69  ok
  web-smoke                   5.37   1.27      5.82          7.08  ok                   7.12  ok
[Mesh][Verify][advisory] decisions differ on: pytest-fast
```

**The columns:**

| Column | Meaning |
|---|---|
| speed | This step's leave-one-out runner speed (1.25 = 25% slower than the median CI runner) |
| expect s | The time this runner predicts |
| adv. limit s | The advisory threshold |
| advisory | `ok` or `slow`; otherwise `no estimate`, `not run` or `not modelled` |
| enf. limit s, enforced | The unchanged enforced check, copied from `verify_step_budget_check.json` |

**Reading this run.** pytest-fast failed the enforced budget on a runner 25% slower than the median. It was 10% over
what that runner predicts (`ratio_to_expected` 1.103 in the JSON), so the advisory says `ok`. The last line names the
steps where the two decisions differ.

**The JSON artifact** holds, per step:

- `speed`, `expected_ms`, `advisory_threshold_ms`, `ratio_to_expected` and `reference_steps_used`;
- `advisory_verdict`, `enforced_threshold_ms` and `enforced_verdict`.

For the run, it holds `run_speed`, `speed_seen`, `speed_beyond_calibration`, `enforcement_active`, `advisory_flagged`,
`enforced_flagged` and `disagreements`.

**On a developer machine** the model still describes CI runners, so read local advisory verdicts as rough.

- **The local run measured.** One local verify-all on the owner's Windows machine (2026-10-25) measured run speed 1.62.
  That is outside calibration, and the note line was printed.
- **The steps scaled unlike any CI runner.** exception-policy-scan was faster than on the median runner, while
  verify-demo and player-package-gate were 2.2× slower.
- **Locally the advisory flagged player-package-gate.** The enforced rule (not enforced locally) reported pytest-fast,
  verify-demo and player-package-gate over budget.

## The refreshed analysis

**New samples.** Every CI run listed by `gh run list --workflow CI --limit 80` was checked for its two
`mesh-artifacts-*-py3.11` artifacts:

- **New runs.** Five workflow runs were not in the data and had a `verify_step_durations.json`:
  - 40222853627 and 40222857452 (387103e);
  - 40224821544 and 40224824845 (0fd517a);
  - 40211602309 (cc4930e), a cancelled run. Its Linux verify-all had completed, and its Windows artifact is empty.
- **Older runs.** All the older runs' artifacts are empty or expired: CI keeps artifacts for 7 days and older runs
  never reached verify-all.
- **Added: 9 job samples.** 5 Linux and 4 Windows, all post-optimisation. The data file now holds 80 samples: 36 Linux
  and 35 Windows post-opt samples, plus 9 pre-opt.
- **Still one day.** The data still spans one day (2026-10-25, 11:41 to 19:11 UTC). This is a small addition: it
  narrows nothing fundamental, and the caveats of the original analysis stand.

**Prospective check.** The model fitted on the old 71 samples alone judged the 9 new ones before they were added:

- None was flagged by the advisory or by the enforced rule.
- The largest advisory ratio (current / advisory threshold) was 0.98 (Linux web-smoke, run 40224821544). The largest
  Windows ratio was 0.95 (pytest-fast, 40222857452).

**Parameters, old data → old + new** (k = 4; base = expected ms on the median runner):

| Step | Linux base s | Linux slope | Linux σ | Linux allowance | Windows base s | Windows slope | Windows σ | Windows allowance |
|---|---|---|---|---|---|---|---|---|
| pytest-fast | 62.8 → 64.3 | 0.74 → 0.73 | 0.035 → 0.035 | 1.15 → 1.15 | 93.9 → 95.6 | 0.80 → 0.80 | 0.086 → 0.096 | 1.41 → 1.47 |
| verify-demo | 8.99 → 9.20 | 1.40 → 1.37 | 0.068 → 0.067 | 1.31 → 1.31 | 17.46 → 18.01 | 1.33 → 1.36 | 0.077 → 0.080 | 1.36 → 1.37 |
| exception-policy-scan | 2.77 → 2.84 | 0.73 → 0.74 | 0.057 → 0.059 | 1.26 → 1.27 | 2.92 → 2.95 | 0.49 → 0.48 | 0.083 → 0.081 | 1.39 → 1.38 |
| swallow-scan-gate | 3.09 → 3.16 | 0.80 → 0.81 | 0.052 → 0.051 | 1.23 → 1.22 | 3.39 → 3.41 | 0.62 → 0.60 | 0.086 → 0.083 | 1.41 → 1.39 |
| web-smoke | 3.44 → 3.52 | 0.87 → 0.86 | 0.029 → 0.034 | 1.12 → 1.15 | 4.79 → 4.84 | 0.78 → 0.77 | 0.051 → 0.049 | 1.23 → 1.22 |
| player-package-gate | 1.02 → 1.03 | 0.95 → 0.93 | 0.029 → 0.031 | 1.13 → 1.13 | 1.66 → 1.68 | 0.90 → 0.91 | 0.042 → 0.042 | 1.18 → 1.18 |

**How the parameters moved:**

- The slopes moved by at most 0.03, and most σ by less than 10%.
- **Windows pytest-fast σ rose 11%** (allowance 1.41 to 1.47). The fast tier keeps growing as tests are added. After
  allowing for runner speed, it grew about 10% from the first to the last fitted run on both OSes, and a one-day fit
  counts that drift as noise.
- Every base rose 0.6–3.2%, for the same reason.
- The runner range barely changed: speed 0.62–1.15 on Linux and 0.62–1.30 on Windows, with fastest to slowest 1.85×
  and 2.10×.

**Before and after.** Each run is judged by a rule fitted on the other runs (cross-validated). A is the advisory rule
exactly as verify-all evaluates it: B with a constant allowance, without B's prediction-interval widening, so it is a
little more sensitive. Where a cell has two numbers, they are old data → old + new.

| | Current enforced rule | B (analysis) | A (advisory, as shipped) |
|---|---|---|---|
| False failures, either OS (workflow runs) | 2/31 → 2/35 | 1/31 → 0/35 | 1/31 → 0/35 |
| Windows jobs failing on a ×1.3 runner-like slowdown | 14/31 → 18/35 | 2/31 → 0/35 | 2/31 → 0/35 |
| Linux jobs failing on a ×1.3 runner-like slowdown | 17/31 → 20/36 | 0/31 → 0/36 | 0/31 → 0/36 |
| Windows jobs failing on a ×1.3 uniform slowdown (every step exactly ×1.3) | 16/31 → 20/35 | 1/31 → 4/35 | 2/31 → 4/35 |
| ×1.5 isolated regression, either OS: pytest-fast / verify-demo / exception-policy-scan / web-smoke | 90/81/94/81% → 91/83/94/83% | 100/100/97/100% → 100/100/97/100% | 100/100/100/100% → 100/100/100/100% |
| ×1.25 isolated regression, either OS: verify-demo / exception-policy-scan | 48/68% → 51/69% | 19/29% → 34/31% | 29/42% → 37/43% |
| swallow-scan-gate ×1.5, either OS | not checked | 100% → 100% | 100% → 100% |
| ×1.5 pytest-fast regression, Windows job alone | 71% → 74% | 68% → 43% | 74% → 49% |
| Real pre-optimisation regression: Linux / Windows jobs flagged | 3/5, 3/4 | 5/5, 2/4 | 5/5, 2/4 |

**What the new samples changed:**

- **The one false failure is gone.** The single cross-validated false failure of B and A (run 40212122684, 74f6eef,
  pytest-fast on a fast runner) is no longer flagged once the wider Windows pytest-fast allowance is fitted.
- **The price is Windows-only pytest-fast detection.** A ×1.5 pytest-fast regression is caught by the Windows job alone
  in 49% of runs, down from 74%. Either OS together still catches 100%, because the Linux job's allowance is 1.15.
- **Uniform ×1.3 slowdowns trip A in 4 of 35 Windows jobs.** These are synthetic: every step exactly ×1.3, unlike real
  runners. The steps with low slopes (exception-policy-scan 0.48, swallow-scan-gate 0.60) cannot absorb a uniform ×1.3,
  so this is expected. The runner-like slowdown, which follows the fitted slopes, trips nothing.

**Reproduce:** `python tooling/ci_timing_analysis.py --data docs/reviews/milestone16_stage6b_evidence/ci_timing_data.json`
prints every number above. Policy rows "a.", "B." and "A.", and the "Either OS" table at the end.

## The rolling long-term check (proposed; available as `--rolling`)

A per-run leave-one-out rule is blind to a slowdown that hits every step by the same factor: each run just looks like a
slower runner. A **persistent** slowdown, though, moves statistics taken over many runs, judged against a **frozen**
model (the committed `verify_step_speed_model.json`, not one refitted on the same runs):

- **Uniform slowdowns:** the median runner speed over the last N runs. It is flagged when it exceeds
  exp(4 × 1.2533 × sd_speed / √N), with sd_speed = 0.183 (Linux) or 0.233 (Windows) from the model. The factor 1.2533
  is the efficiency of a median of normal draws.
- **Persistent single-step regressions:** the median over the last N runs of the step's runner-adjusted residual,
  log(observed / expected). It is flagged when it exceeds exp(4 × 1.2533 × σ_step / √N).

The smallest persistent slowdown each check detects at 4 sd, from the refreshed data, against the threshold it would
replace:

| Window | Uniform slowdown, Linux / Windows | pytest-fast | verify-demo | exception-policy-scan | swallow-scan-gate | web-smoke | player-package-gate |
|---|---|---|---|---|---|---|---|
| per run (the advisory itself) | invisible | 1.15 / 1.47 | 1.31 / 1.37 | 1.27 / 1.38 | 1.22 / 1.39 | 1.15 / 1.22 | 1.13 / 1.18 |
| 10 runs | 1.34 / 1.45 | 1.06 / 1.16 | 1.11 / 1.13 | 1.10 / 1.14 | 1.08 / 1.14 | 1.06 / 1.08 | 1.05 / 1.07 |
| 20 runs | 1.23 / 1.30 | 1.04 / 1.11 | 1.08 / 1.09 | 1.07 / 1.09 | 1.06 / 1.10 | 1.04 / 1.06 | 1.04 / 1.05 |

At 3 sd, the uniform limits are 1.24 / 1.32 at 10 runs and 1.17 / 1.22 at 20 runs.

**Run it:**

```
python tooling/ci_timing_analysis.py --data recent.json --rolling 20 [--model tooling/metrics/verify_step_speed_model.json]
```

It prints the median speed and its limit, then a per-step table of median observed/expected against its limit, with
`ok`, `PERSISTENT SLOWDOWN` or `PERSISTENT REGRESSION`.

**Example.** The model fitted on the old data only, applied to the last 10 runs, which include the 9 new samples:

- Linux median speed 0.98 (limit 1.32); Windows 1.14 (limit 1.46).
- Every step is `ok`.
- Linux pytest-fast came closest, at 1.041 against a limit of 1.057: that is the fast tier's growth during the day.

**Proposed use:**

- **Scheduling.** A scheduled job, or a step of the existing weekly workflow, runs the check on the last 20
  `push`-event CI runs of the main integration branch. Pull-request runs of unmerged code would blur it.
- **Collecting the samples.** CI artifacts expire after 7 days, which is why 79 older runs had no timings. So the same
  job should harvest each run's `verify_step_durations.json` into the data file, with `--index` and `--durations-dir`,
  which merge into `--data`.
- **Advisory, like the per-run check.** A flag means "look at it".

**What it cannot tell apart.** A slower hosted-runner fleet looks the same as a uniform code slowdown. On a flag, compare
the step totals of an unchanged older commit run again on today's runners.

**Not built:** the scheduled workflow itself. It would be a new workflow file, and the workflows were to stay untouched.

## Evidence to gather before any review of switching enforcement

1. **20 to 30 CI workflow runs with the advisory in place**, after this lands: 40 to 60 job samples. Spread them over at
   least 5 days and several branches, so the runner pool and the test suite change between them.
2. **Agreement statistics from those runs.** Per step and OS, count each case:
   - both pass;
   - both flag;
   - enforced flags but advisory passes: expected on slow runners, so record the run speed;
   - advisory flags but enforced passes: expected for regressions on fast runners.

   Review every disagreement by hand: was it a real code change, a slow runner or an anomaly?
3. **The thresholds a switch would need**, as a proposal for the owner, not a decision made here:
   - no more than 1 advisory false flag in 30 workflow runs, and that one explained by a runner anomaly;
   - no enforced failure that the advisory missed and that turned out real.
4. **A refit at 60 or more samples per platform**, compared with today's fit. Stability would mean slopes within ±0.1
   and σ within ±20%. Windows pytest-fast needs attention: its σ is inflated by test growth. Two options:
   - fit it with a time trend;
   - refit after accepted growth, so growth does not become allowance.
5. **The rolling check run weekly over the same period**, to see its real false-flag rate.
6. **Optional:** a fixed stdlib calibration workload (a few hundred ms, timed in verify-all) recorded alongside. It gives
   a runner speed independent of every product step, and would separate uniform code slowdowns from slow runners.

## What a switch would involve

1. **The budgets.** Two options:
   - make the model file the enforced budget for CI platforms;
   - fold it into `verify_step_budget.json` v3 per platform: `speed_reference_ms`, and per step `base_ms`, `slope`,
     `allowance`.

   Either way, keep today's budgets as the fallback for platforms without a model, for "no estimate" steps and for
   local runs.
2. **The check.** `_evaluate_verify_step_budget_guard` would decide with the leave-one-out rule, put speed, expected ms
   and threshold into its message and payload, and keep the payload schema compatible for its readers: the release notes,
   debug report, trends and editor overlay.
3. **Fitting.** Budgets would be refitted from at least 20 CI samples by `--write-model`. Today's "update baseline"
   command, which sets budgets from one possibly slow run, would be retired for CI platforms.
4. **Tests.** The current advisory tests become enforcement tests:
   - an isolated ×1.5 or ×2 regression fails;
   - a uniformly slow runner passes;
   - a missing reference step falls back;
   - a step never normalises itself.
5. **The rolling check as a scheduled workflow**, advisory at first.
6. **An owner decision on k** (4 today) and on the refit cadence.

None of this is done here. **The enforced rule is unchanged; replacing it needs a separate owner review.**

## Caveats

- **The samples still span one day**, and only 9 are new.
- **Fast-tier growth widens the Windows allowance.** The fast tier grows as tests are added. That widened the Windows
  pytest-fast allowance to 1.47, so a Windows job alone catches a ×1.5 pytest-fast regression only about half the time;
  the Linux job, at allowance 1.15, still catches it.
- **The tails are heavier than normal**, so k = 4 is an empirical choice, not a probability statement.
- **The prospective check is small:** 9 samples, all passing under both rules. It shows no harm, not a benefit.
