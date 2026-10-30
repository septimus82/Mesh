# H4: CI timing reliability (#422 F13, F13b; #373)

Base `redesign/visual-editor` at `aa29101` (H3's parallel CI). The objective was to make timing measurement trustworthy without weakening functional verification. The method:
- confirm each reported problem in the code;
- measure the timing rules against every CI run whose log still has them;
- change only what that evidence supports.

## 1. Findings, checked against the code

| # | Reported | Verdict | Evidence |
|---|---|---|---|
| 1 | The duration guard sums the 25 slowest pytest entries and calls it total execution time | **Confirmed** | `tooling/pytest_fast.py` runs `--durations 25`, so `.mesh/metrics/pytest_durations_fast.json` holds only the 25 slowest setup/call/teardown entries. `_read_pytest_fast_durations` summed them as `total`, and the docstring called it "the sum of individual test durations". In CI the "total" was about 40 s of a 77 s step running about 5,000 tests. |
| 2 | Baselines initialised or overwritten by the run being measured | **Confirmed for the duration guard; not for the step budget** | **Guard:** a missing baseline became the current value, and every passing run overwrote it. `.mesh/` is git-ignored, so every CI job started without one. CI's verify-all then wrote one, and minutes later the bundle's release check (`repo_root="."`, same checkout) compared itself with it. Locally the baseline could creep up by up to 15% per pass. The guide's "keep them committed (or persisted in CI workspace)" was never possible. **Step budget:** its history median excludes the current run's file and archives the previous one before writing, and in CI the artifacts folder starts empty, so it isn't self-referential. |
| 3 | Runner speed estimated from other verification steps | **Confirmed; the method holds, the calibration doesn't** | Speed = the median over the *other* reference steps of current ÷ reference (leave-one-out, so a slow step can't excuse itself). Over 443 runs the well-calibrated steps sit at actual ÷ expected ≈ 1.0 (verify-demo 0.975, web-smoke 1.013, player-package gate 0.973), so the estimator tracks runner speed. |
| 4 | Models calibrated on the old sequential layout | **Confirmed** | `verify_step_speed_model.json` was fitted from 36 Linux and 35 Windows runs on **2026-10-25 within about 7.5 hours**, in the sequential `tests` job. Since then: #418, H2, new tests, #426, and H3's split. `pytest-fast` now runs at a median **1.122** (Linux) and **1.173** (Windows) of its expected time; its 4σ allowance (1.1495) is exceeded in **81/220** Linux runs; split runs sit at 1.20. The rolling check (`timing-rolling`, on every integration push) reports **PERSISTENT REGRESSION** for `pytest-fast`, `exception-policy-scan` and `swallow-scan-gate` on both OSes, so it no longer distinguishes anything. |
| 5 | Regressions vs runner variability | **Confirmed: not separated at the fine threshold** | Of 222 Ubuntu jobs, **55 (25%) failed for timing only** (over the fixed threshold *and* "slow" per the stale model), with no regression behind them. Windows: 10/221. All on `pytest-fast` (55 / 6) and `exception-policy-scan` (8 / 4). |

## 2. Data
**Source:** every completed `tests`/`verify` job of `ci.yml` from 2026-10-25 to 30 whose log carries verify-all's advisory table: 443 jobs (222 Ubuntu, 221 Windows), all branches, PR and push. Logs outlast artifacts (90 days against 7).
- **What was taken:** the first table is the gated verify-all. For each step it gives seconds, the leave-one-out speed, expected time, advisory limit and the enforced threshold in force at the time.
- **What's committed:** a trimmed copy, `h4_ci_timing_evidence/verify_timing_tables.json` (seconds, advisory limit, threshold per step), which the replay test reads.
- **What the logs lack:** two of the eight speed-reference steps aren't printed. So alternative speed estimators can't be replayed from logs; the decisions below don't need them.

| Step | Timing-only failures, Linux / Windows | actual ÷ expected median, L / W | Worst actual ÷ fixed threshold, L / W |
|---|---|---|---|
| pytest-fast | **55 / 6** | 1.122 / 1.173 | 1.275 / 1.315 |
| exception-policy-scan | **8 / 4** | 1.096 / 1.094 | 1.334 / 1.471 |
| verify-demo | 0 / 0 | 0.975 / 0.982 | 0.903 / 1.258 |
| web-smoke | 0 / 0 | 1.013 / 1.006 | 0.847 / 0.945 |
| player-package-gate | 0 / 0 | 0.973 / 0.974 | 0.609 / 0.904 |

## 3. Decision
1. **Duration guard: trustworthy or silent.**
   - It judges only against a baseline recorded on purpose (`MESH_RECORD_PYTEST_FAST_BASELINE=1`), which carries the time, commit, platform, Python and entry count, keeps earlier baselines in `history`, and is compared only like with like.
   - Without one (any fresh checkout, every CI job) it reports and doesn't pass (`ok: null`, step note `report-only: baseline none`).
   - It never writes its own baseline.
   - Names say what's measured: `slowest_entries_seconds`, `slowest10_seconds`, `entries`, plus the step's real elapsed `wall_seconds`, reported separately.
   - The old `.txt` baselines are left on disk, listed, and never read or written.
2. **Step budget: report-only where enforcement is shown to be invalid.**
   - `pytest-fast` and `exception-policy-scan` are report-only (`report_only_ceiling_ratios` in `verify_step_budget.json`). Their cost grows with the repository and their calibration is stale; over their threshold they're printed, recorded (`report_only_over`) and annotated as a GitHub warning.
   - **Hard ceiling, enforced and never excused by rule f:** threshold × 1.65 (`pytest-fast`) and × 1.85 (`exception-policy-scan`). That's 1.25 × the worst ratio in the 443 runs, rounded up to 0.05; no logged run came within 20% of it. In seconds: Ubuntu 130.4 s and 6.6 s; Windows 201.0 s and 6.9 s.
   - The three calibrated steps keep rule f unchanged.
   - Thresholds, budgets, ratio limits and the model are **unchanged**. No threshold was raised.
3. **No timing evidence is not a timing pass.**
   - If the committed budget file is missing, the guard returns `ok: false` (before, `ok: true`).
   - A budgeted step that didn't run (absent or skipped) in an otherwise passing enforced run fails it: `timing evidence missing: <step> did not run`, with `not_measured` in `verify_step_budget_check.json`.
4. **Functional and timing failures are told apart.**
   - verify-all ends with `[Mesh][Verify] result: OK | FAILED (functional: …) | FAILED (timing only: …; every functional check passed)`.
   - A timing-only failure is also a GitHub error annotation saying so.
   - Functional failures are unchanged.
5. **Side effect (F13b):** the fast-tier diagnostic rerun, which runs the whole fast tier again, now follows the gate. It reran on every Ubuntu timing failure (25% of jobs); now only when `pytest-fast` breaches its ceiling.

## 4. Validation
**Replay** of the committed policy over the 443 logged runs. This is `test_the_committed_policy_against_every_logged_ci_run`, which is deterministic.

| | Ubuntu (222) | Windows (221) |
|---|---|---|
| Timing failures without a regression, old → new | **55 → 0** | **10 → 0** |
| Report-only warnings in the same runs | 75 | 98 |
| `pytest-fast` × 1.5: old fails / new fails / new visible | 207 / 4 / 207 | 192 / 51 / 193 |
| `pytest-fast` × 2.0 | 220 / 155 / 220 | 219 / 160 / 219 |
| `pytest-fast` × 2.5 | 220 / 208 / 220 | 219 / 195 / 219 |
| `exception-policy-scan` × 2.0 / × 2.5, new fails | 88 / 181 | 81 / 179 |
| Enforced steps × 1.5, old = new | verify-demo 123, web-smoke 148, gate 0 | 115, 147, 50 |

**Tests** (`tests/test_verify_timing_policy.py`, 18 tests; `tests/test_verify_pytest_duration_guard.py`, 9 tests):
- report-only under and over the ceiling;
- rule f can't excuse a ceiling breach; enforced steps are unchanged;
- missing budgets; steps that didn't run;
- the verdict line; annotations only in Actions;
- four end-to-end verify-all runs: missing budgets, missing step, report-only overrun, ceiling breach;
- the diagnostic rerun;
- for the guard: fresh checkout twice (as CI's verify-all and the bundle), names, legacy files, recording with history, a regression against a recorded baseline without overwriting it, platform/Python/entry-count mismatch, and an unreadable baseline.

**Mutation proof:** each of these turns tests red:
- removing the missing-evidence check;
- passing on missing budgets;
- letting rule f excuse a ceiling breach;
- letting the guard write its own baseline;
- ignoring report-only.

**Requirements:**
- **Functional failures stay red:** steps, the full pytest job and the H3 fan-in are untouched.
- **Missing reports can't give false greens:** a missing budget file or an unmeasured step fails an enforced run. Missing jobs or reports are already red through the fan-in (`tooling/ci_require_jobs.py`) and `artifacts-validate`.
- **Stalls stay bounded:** `timeout-minutes` 120 on `pytest` and `verify`, 10 on the fan-in, are unchanged.

## 5. Limits and the way back to enforcement
- **The trade-off.** The two report-only steps now fail the gate only for serious slowdowns, about × 2 or more. Moderate ones (+15–50%) are visible as warnings but don't fail. The old gate "caught" them only alongside a 25% false-failure rate on Ubuntu; at a single run, neither can separate a +25% regression from runner noise with the current calibration.
- **Warnings are still frequent:** 34% / 44% of normal runs. This is because the committed thresholds and model predate the repository's growth. So are the rolling check's permanent PERSISTENT REGRESSION verdicts. Neither is meaningful again until recalibrated.
- **Recalibration** (follow-up, needs review):
  - wait until the current layout (H3 + #426) has at least 24 runs per OS on the integration branch; the `timing-rolling` job's collector gathers them;
  - refit with `tooling/ci_timing_analysis.py --write-model`, and propose new budgets with the same evidence;
  - replay the result over the recorded tables plus the new runs;
  - re-enable enforcement for a step only where the replay shows about 0 false failures.
- **Evidence limits.** The logs lack two speed-reference steps, so alternative speed estimators (for instance one based on the `pytest` job) weren't evaluated. The history covers 6 days, mostly on the sequential layout.
