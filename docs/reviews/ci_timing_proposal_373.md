# CI timing: a measured proposal (#373)

**Status: approved by the owner and merged (#400, `6958a2c`), 2026-10-27.** No budget, ratio or tolerance changed. Its changes:

- the analysis tool skips runs whose `verify-all` stopped before `pytest-fast`, and adds rule f to its comparisons;
- the evidence;
- one CI trigger change (section 4), kept as its own commit so it can be dropped;
- after the owner's provisional approval: **rule f in the enforcement gate**, and a report-only rolling check on integration pushes (section 3), in their own commit.

## 1. What is failing, and why

Data: every CI `tests` job from 2026-10-25 20:20 to 2026-10-27 16:52 (204 jobs, from the `verify_step_durations.json` of each job's artifact). Four jobs at `bb8b10b` are left out: `mypy-gate` really failed there and every later step read 0 ms. Evidence: [`ci_timing_373_evidence/`](ci_timing_373_evidence/).

- **On the current code** (24 runs per OS since the M20B merge, 07:14 today), the committed fixed rule fails:
  - **50 % of Linux jobs and 54 % of Windows jobs**;
  - **75 % of workflow runs** on at least one OS;
  - every one of those failures had all tests passing.
- **It is not only runner variance. The fast tier got heavier.** Speed-normalised against the advisory model fitted on 2026-10-25, `pytest-fast` costs 1.14–1.15× and `exception-policy-scan` 1.11–1.14× on both OSes. The rolling check (`--rolling 24`) calls both a **persistent regression**. On the 24 calibration runs of 2026-10-25 it flags nothing (the control).
- **Per commit**, the ratio climbs:
  - from 0.93–1.06 (2026-10-25, M16 Stage 6);
  - to 1.04–1.12 (M18B–M20A);
  - to 1.12–1.19 (M20B–M20E and the post-M20 checkpoint).

  It is gradual: each milestone adds fast tests. The fast tier grew from **4,565 to 4,827 tests (+5.7 %)** between `0fd517a` and `8613110`, while its normalised time grew about 16 %. So the new tests are heavier than the average fast test. Per-test profiles are in the test-suite findings (Part D).
- So the fixed rule is doing its job, sensing a real 16 % growth. But it does so as a coin flip on each job: whether a run fails depends on the runner it lands on, and no single change is to blame.

## 2. The rules compared (cross-validated on the current code, regressions injected)

Rules are fitted leave-one-run-out: the run being judged never helps fit the rule that judges it.

- **"Detects"** columns: one step multiplied in every historical run. They show the share of runs where that step is flagged.
- **"Slow runner"**: every step ×1.3 the way runners actually differ. That is a false failure for a per-run rule, but the right failure for a creep detector.

Full tables: [`report_current_code.md`](ci_timing_373_evidence/report_current_code.md).

| Rule | OS | False failures | Slow runner ×1.3 fails | pytest-fast ×1.25 detected | ×1.5 | ×2 | exception-policy-scan ×1.25 |
|---|---|---|---|---|---|---|---|
| **a. Current fixed thresholds** | Linux | **50 %** | 92 % | 88 % | 100 % | 100 % | 83 % |
| | Windows | **54 %** | 79 % | 79 % | 92 % | 100 % | 79 % |
| **A. Advisory, speed-adjusted, leave-one-out** (what verify-all already prints) | Linux | 12 % | 8 % | 100 % | 100 % | 100 % | 8 % |
| | Windows | 4 % | 0 % | 12 % | 96 % | 100 % | 8 % |
| **c2. Reviewed recalibration** (the committed budgets' own method, refit on the current code) | Linux | 4 % | 75 % | 67 % | 96 % | 100 % | 38 % |
| | Windows | 4 % | 62 % | 54 % | 71 % | 92 % | 4 % |
| **f. a and A both** (#373 option 1; model refit on the current code, see below) | Linux | **0 %** | 4 % | **88 %** | 100 % | 100 % | 8 % |
| | Windows | 4 % (1 run) | 0 % | 12 % | **92 %** | 100 % | 8 % |

**Reading it:**

- **No per-run rule detects a 25 % isolated slowdown on Windows without false failures.** Windows runners differ by 0.62–1.30× (2.1:1), which is larger than the regression. Only the current thresholds and the recalibration see ×1.25 there, and they pay for it in false failures or in failing slow runners.
- **The recalibration (c2) cuts false failures to 4 %, but it loosens a lot.** The recalibrated Windows `pytest-fast` limit would be 155 s, against 121.8 s today. The window also had slower runners (median speed 1.11–1.18), so a raw median bakes them in. Its ×1.25 detection falls to 54–67 %.
- **Rule f** keeps the fixed ceiling as an absolute bound. It fails only when the advisory agrees:
  - Linux: 0 false failures and 88 % detection of ×1.25;
  - Windows: one false failure in 24 and 92 % detection of ×1.5. **It does not reliably detect an isolated 25 % slowdown on Windows**: 12 % here, 38 % with the committed model (below). Only slowdowns of about 50 % or more are caught reliably there.
- **These rule-f rows fit the advisory model on the current code** (leave-one-out). The gate as implemented (section 3) judges against the committed model, fitted on 2026-10-25 before the fast tier grew. Measured with that model on the same runs:

  | Committed model (as implemented) | Linux | Windows |
  |---|---|---|
  | Fixed threshold alone fails | 12/24 | 13/24 |
  | Rule f fails | **9/24** (the model correctly sees the +15 % growth as slow) | 2/24 |
  | pytest-fast ×1.25 detected | 21/24 | 9/24 |
  | pytest-fast ×1.5 detected | 24/24 | 22/24 |

  Getting to the 0 % / 4 % rows means refitting the model on the current code (`--write-model`). That accepts the growth, so it is a recalibration and needs the owner's decision.
- **Creep can only be seen across runs.** The rolling check caught today's +14–16 % on both OSes, and its control is clean. No per-run rule (f, A) can see a uniform 16 % growth, by construction.

## 3. Recommendation

In the order I'd do them; each is independent:

1. **Pay back the growth instead of raising limits.** Part D's test-suite findings trim the fast tier's repeated setup. If the fast tier gets back ~16 %, today's budgets fit again with nothing loosened. This is preferable to recalibrating.
2. **Enforce rule f** (fixed ceiling and advisory both) instead of the fixed rule alone. It is #373's option 1, provisionally approved by the owner, and **implemented and merged** (`6958a2c`; `mesh_cli/verify.py`, `_apply_rule_f`).
   - A step over its fixed threshold fails unless the advisory judges it within this runner's range.
   - Where the advisory can't judge (no model, no estimate, not run, an error), the fixed threshold decides alone, so the rule never fails open.
   - The decision is written to `verify_step_budget_check.json` (`rule_f`), and an excused step is named on stderr.
   - With the committed model: Linux 12/24 → 9/24 failing, Windows 13/24 → 2/24 (above). Windows detects an isolated slowdown reliably only from about ×1.5.
3. **Keep creep visible (implemented on this branch):** a report-only `timing rolling check` job in `ci.yml` runs on every push to `redesign/visual-editor`.
   - It collects the branch's last 30 runs (`tooling/ci_timing_collect.py`) and writes `--rolling 24` to the job summary.
   - It raises a warning annotation on a persistent regression, and never fails.
   - It is the only rule that detected the real regression.
   - **First run on the integration branch** (push `6958a2c`, job 122481850070): it collected 56 tests jobs, published to the job summary and raised its warning. pytest-fast is a persistent regression on both OSes (median observed/expected 1.104 Linux, 1.131 Windows), and so is Windows' exception-policy-scan (1.107).
   - A scheduled workflow would not run here: GitHub fires `schedule` only from the default branch, `main`.
4. **Recalibrate only through the reviewed path, and only if 1 doesn't happen.** That means `update_ci_baseline.yml`, `pytest-fast` and `exception-policy-scan` only, from speed-normalised medians (the advisory model's `base_ms`, refit with `--write-model`), not raw medians from a slow-runner window.
5. **Run CI once per commit** (section 4).

Rejected:

- raising every threshold;
- a re-run policy, which hides the 50 %;
- "same-run total normalisation", which detects nothing (0 % at ×2) because a step slowdown inflates its own normaliser.

## 4. Duplicated runs and reuse of evidence

**Push and pull_request run the same commit twice.** `ci.yml` triggers on every `push` and every `pull_request`. Concurrency groups don't merge them: the key is the PR number for one event and the ref for the other. Since 2026-10-25 20:00:

- 120 runs covered 61 commits, and **59 commits ran twice**;
- `tests` jobs used 40.6 runner-hours, **19.9 of them duplicates**;
- 19 duplicates are on `redesign/visual-editor` itself (its pushes, plus draft #344's `pull_request` runs, since #344 targets `main`);
- 40 are feature branches with a PR.

The repository is public, so this costs no money. It costs queue time and concurrent-job slots. Each duplicate also doubles a commit's chance of a red timing badge: at a 75 % false-failure rate per workflow run, about 94 % of commits show a red cross somewhere.

**The change on this branch** (its own commit): `push` runs only for `main`, `redesign/visual-editor` and `release/**`. Feature branches run through their PR; `workflow_dispatch` still runs any branch.

**Coverage, exactly** (from the 120 runs measured above):

| Commits | Before | After |
|---|---|---|
| Feature branch with an open PR (40 of the 59 duplicates) | push run (branch head) + PR run (merge with base) | **PR run only** (the merge with base: the evidence a merge decision needs) |
| `redesign/visual-editor` (19 duplicates, through draft **#344** → `main`) | push run + #344's PR run | **unchanged: still both.** Pushes to the integration branch keep their push run (post-merge evidence). Every such push also updates #344, whose `pull_request` run tests the branch merged into `main`. |
| A branch pushed with no PR open | push run | **no automatic run** until a PR is opened or a run is dispatched |
| `main`, `release/**` | push (+ PR if any) | unchanged |

- Removed: about 40 of the 59 duplicate runs (68 %).
- **Kept: #344's duplication** (19 of 59).
- The PR run tests the merge result, not the branch head. They differ only when the base has moved, and then the merge result is the one that matters.

**Removing #344's duplicate is possible but not done.** A job-level `if:` would skip `pull_request` runs whose head is `redesign/visual-editor`. #344's merge-into-`main` result would then go untested until `main` is updated. That changes what #344's checks prove, so it is the owner's call.

**In-job duplication.** Medians of 20 green runs, `tests` job:

| | Linux | Windows |
|---|---|---|
| Whole job | 570 s | 932 s |
| Full pytest (`not slow and not e2e`, includes every fast test) | 231 s | 392 s |
| `verify-all` (its `pytest-fast` runs the fast tier again) | 96 s | 152 s |
| Release bundle (its `release-check` runs **`verify-all` again**, then export, demo and audits) | 178 s | 293 s |

The same commit's fast tier runs three times per job, and `verify-all` twice. A safe reuse of evidence:

- `release-check` takes the outer `verify-all`'s summary, without running it again, when four things match:
  1. the summary's provenance (commit, tree state) is this checkout's;
  2. it passed;
  3. it ran in this job;
  4. nothing was written to the tree since (the tree's state at bundle time equals the summary's).
- Saving: ≈ 96 s (Linux) and ≈ 150 s (Windows) per job, 16–17 %. Not done here: it changes the release contract, and #394 (the inner run's failure) should be closed first.

The full pytest and `pytest-fast` overlap is deliberate: `pytest-fast` is the timed, budgeted measurement #373 is about. It is kept.

## 5. How the numbers were made

```
python tooling/ci_timing_analysis.py --data docs/reviews/ci_timing_373_evidence/ci_timing_data_2026-10-25_27.json --model tooling/metrics/verify_step_speed_model.json --rolling 24
python tooling/ci_timing_analysis.py --data <the 2026-10-27 07:00+ runs of that file> > report_current_code.md
python tooling/ci_timing_analysis.py --data docs/reviews/milestone16_stage6b_evidence/ci_timing_data.json --model tooling/metrics/verify_step_speed_model.json --rolling 24   # the control
python tooling/ci_timing_analysis.py --self-check
```

The data file holds all 200 usable jobs; the current-code report uses the 48 since 07:00 on 2026-10-27. Fast-tier test counts: `pytest -m fast --collect-only -q` on a `git archive` of each commit.
