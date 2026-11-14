# Duplicate `verify-all` runs in CI (#422)

Where a whole `verify-all` runs across the workflows and inside the test lanes, what each run costs, and which runs
only repeated another. Measured at `c9dc39d` (2026-11-14). Raw data: `ci_verify_all_duplicates_evidence/`.

## Finding

- **No workflow runs `verify-all` twice in one job any more.** H2 (#424) and F13-B (#438) removed those: CI's release
  bundle takes its job's verify-all on evidence, and the baseline update is told not to run its own.
- **The required checks' critical path has nothing to remove.** It is the `pytest` jobs (about 480 s on both
  systems); `verify` finishes earlier (207 s Linux, 360 s Windows). The default suite runs the verify-all pipeline 3
  times, on stubbed folders, 0.15 s in all.
- **The one confirmed duplicate was in the Extended workflow's `extended` lane.** Fourteen audit test modules ran the
  same `verify-all --artifacts <tmp> --no-index` on the checkout **16 times in one pytest process**, each to read one
  report. That was 72% of the lane's test time on both systems. They now share one run: **16 runs become 1**.
- **It is not on a critical path.** Extended's wall time is its GPU shards (about 2,000 s); the `extended` lane job is
  about 420 s (Linux) and 570 s (Windows). The saving is runner time and the local lane's time, not time to a verdict.

## Execution map

Times are from CI run 43570919963 (push, `c9dc39d`) and Extended run 43570920009 unless a range is given.

| Workflow / job | Trigger | Command | What it verifies | Context | Time | Repeats another? |
|---|---|---|---|---|---|---|
| `ci.yml` / `verify (<os>)` | push, PR, dispatch | `mesh_cli verify-all --artifacts artifacts --ci-bundle --release-notes-artifact --reuse-evidence` | all 32 steps: demo, replays, strict validation, mypy and ruff gates, exception scans, the fast tier with its timing guard, runtime, package and web smokes, the content audits | checkout, py3.11, Linux and Windows | 111 s / 208 s | **Independent.** One a job |
| same job: warm-up | | `pytest --collect-only` | nothing (collection only) | | 33 s / 43 s | Collection happens again inside the fast tier. Deliberate (H3): it keeps the timed fast tier as warm as it was after the full suite |
| same job: release bundle | | `mesh_cli release bundle --reuse-verify-all artifacts` | release check, demo, bundle | | 10 s / 29 s | **Already removed** (F13-B): reuses the job's verify-all on evidence, or runs its own when the evidence doesn't hold |
| same job: `artifacts-diff` x3, `bundle verify` x2 | | same input, three and two output formats | | | under 5 s each | Same check, another format; too small to matter |
| `ci.yml` / `pytest (<os>)` | push, PR, dispatch | `pytest -q` (Windows: two shards) | the default suite | checkout | 449 s; 409 s + 288 s | **Critical path.** Its fast tests also run in `verify`'s fast tier (76.5 s / 141.5 s there): a repeat across parallel jobs, kept (see classification) |
| `ci.yml` / `installed (<os>)` | push, PR, dispatch | `pytest --noconftest tests/test_wheel_bundles_engine_data.py`, which builds and installs the wheel | the installed product | wheel in its own environment | 68 s / 126 s | Independent |
| `ci.yml` / `acceptance (<os>)` | push, PR, dispatch | `tooling.test_tiers acceptance` | creator workflows in real windows | checkout, Mesa | 58 s / 102 s | A subset of Extended's gpu lane, on purpose (H6: a required check) |
| `ci.yml` / `web-smoke`, `arcade3-canary` | push, PR, dispatch | `build-web`, `play-runtime --headless-smoke`, `web-smoke`; Arcade 3 smokes | web target; Arcade 3 | their own environments | 39 s, 48 s | `web-smoke` repeats two small verify-all steps (3 to 6 s there) as a required check of its own |
| `ci.yml` / `tests (<os>)` | push, PR, dispatch | `ci_require_jobs.py`, `ci_shards.py check` | that the four jobs above succeeded | | 8 to 10 s | Fan-in |
| `ci.yml` / `ship` | `release/*` only | `release ship` (one verify-all, in its release candidate's bundle; the promotion runs none) | release candidate and final | checkout, Linux | not run on the integration branch | Independent |
| `extended.yml` / `extended (<os>)` | push, dispatch, schedule | `tooling.test_tiers extended` (`-m "(slow or e2e) and not gl"`) | slow and end-to-end tests | checkout | job 317 to 603 s / 413 to 690 s (14 runs) | **Held the duplicate:** 16 identical verify-alls, see below |
| `extended.yml` / `gpu (<os>, shard k/2)` | push, dispatch, schedule | `tooling.test_tiers --shard k/2 gpu` | real-window tests | checkout, Mesa | 14 to 35 min | No verify-all |
| `update_ci_baseline.yml` | dispatch | `verify-all ...`, then `baseline-update --artifacts artifacts --no-verify-all` | regenerates the CI baseline | checkout, Linux | never run | Already one run: the update is told not to run its own |
| `update_weekly_trends.yml`, `weekly_health.yml` | schedule (on `main`), dispatch | one `verify-all` each (`weekly_health` after `pytest -q -W error`) | weekly trend and health | checkout | last ran on `main` 2026-09-21, failing | One a job |
| `release_draft.yml` | dispatch | `release-preflight` (runs one verify-all itself) | the commit being released | checkout, Linux | never run | One a run. With downloaded artifacts it still runs its own into that folder: see remaining opportunities |

## Inside the test lanes: every run of the verify-all pipeline

Counted with a spy on `mesh_cli.verify.run_verify_steps` (the one function every verify-all goes through) and on
`subprocess.run`, locally (Windows, Python 3.13), same commit before and after.

| Lane | Pipeline runs before | after | Of which the audit command on the checkout |
|---|---|---|---|
| default (`pytest -q`, the required check) | 3 (0.15 s, stubbed folders) | 3 | 0 |
| extended | **34** | **19** | **16 → 1** |

The other 18 runs in the extended lane are tests of verify-all's own behaviour (its JSON output, exit codes, step order,
pass-through arguments, artifacts on failure), each in its own seeded project folder with its own stand-ins. They are
different checks and are unchanged. Seven of them cost about 24 s each because verify-all's tooling gates (mypy, the
exception scans) look at the engine's own source whichever folder the run is in: see remaining opportunities.

One more verify-all in the lane is a subprocess (`test_mesh_cli_verify_all_runs_headless_without_arcade`): a fresh
interpreter in which arcade cannot be imported. A different condition; kept.

## Classification

| Repetition | Class | Decision |
|---|---|---|
| 16 audit tests each running the same verify-all on the checkout, in one process | **B: redundant in the same execution context** (same command, same files, same stand-ins, same interpreter; byte-identical reports) | **Removed: one shared run** |
| The fast tier: in `verify`'s verify-all and in the `pytest` job's default suite | C: reusable in principle | Kept. verify-all's fast tier is a step it promises and the one that is timed; skipping it in CI would change what a green verify-all means, and it is not on the critical path |
| `verify`'s collection warm-up before verify-all | A (setup the timing depends on) | Kept (H3) |
| `acceptance` in CI and the gpu lane in Extended | A: separately enforced guarantee | Kept (H6) |
| `web-smoke` job and verify-all's web and runtime smokes | A: a required check of its own; seconds | Kept |
| verify-all on Linux and on Windows; checkout and installed wheel | A: different platforms and distributions | Kept |
| Tests of verify-all's behaviour in seeded folders (18 runs) | A: different checks | Kept |
| `artifacts-diff` and `bundle verify` in several formats | B, seconds | Left: not worth a change |

## The correction

- `tests/_verify_all_audit.py::run_once`: the run every audit test made, once. The command is unchanged and whole
  (`verify-all --artifacts <dir> --no-index`), in the checkout, with the stand-ins the tests always used (demo,
  replay suite, `validate-all`, asset doctor), all undone when the run ends. A non-zero exit raises.
- `tests/conftest.py::verify_all_audit_artifacts`: a session fixture giving that run's reports folder, like the
  existing `exception_policy_scan` fixture.
- The 14 modules (16 tests) ask for the fixture instead of running verify-all; what each asserts is untouched. Names,
  markers and lanes are unchanged.

No workflow, verify-all code, marker, shard, threshold or budget changed. `verify-all` run directly is what it was.

**Why the removed runs were redundant.** The 16 calls had one command and one checkout. Their setup blocks came in
two forms that differ only in where they set the scene and world list stand-ins (11 on `mesh_cli.legacy_impl`, where
the pipeline reads them; 5 on the `mesh_cli` package, where it does not, so those ran the real lists). With
`--no-index` neither list is written. The shared run uses the form that stands in for less. Running both old forms
and the shared run side by side: all 8 reports the audit tests read are byte-identical in the three runs, as are 753
of the 764 files written; the 11 others carry timings or temporary paths and no audit test reads them
(`equivalence.json`).

## Measured

| | Before | After |
|---|---|---|
| verify-all pipeline runs in the extended lane (local spy) | 34 | 19 |
| of which the audit command on the checkout | 16 | 1 |
| `build-web` / `package-player` subprocesses those runs start | 16 / 16 | 1 / 1 |
| Extended lane, local wall time (Windows, Python 3.13; 179 tests both times, same ids) | 1,713.7 s | 897.5 s |
| the 16 audit tests in it | 809.5 s | 49.3 s |
| verify-all invocations by workflow steps | 1 a job | 1 a job (unchanged) |
| Required checks and their names | unchanged | unchanged |
| Required-check critical path (`pytest` jobs) | about 480 s | unchanged: nothing on it was duplicated |

CI before, from the lane's JUnit in seven Extended runs on the integration branch (2026-11-13..14):

| | Linux | Windows |
|---|---|---|
| the 16 audit tests | 261 to 332 s (median 285) | 292 to 409 s (median 373) |
| share of the lane's pytest time | 72 to 74% | 70 to 72% |
| lane pytest time | 357 to 460 s | 405 to 585 s |
| expected to go (all but the first, cold, run) | 219 to 278 s (median 244) | 251 to 347 s (median 317) |

The CI figures after are in the pull request, from its own Extended run. Runners differ by up to about 1.5 times in
speed from run to run, so one run places the result inside that range and proves no exact number.

## Regression protection (`tests/test_verify_all_duplicate_runs_policy.py`, fast, no verify-all runs)

- The shared run is one call of the whole command, in the checkout, with the four stand-ins, and leaves the working
  directory and the stand-ins as it found them.
- A failed run (exit 1, exit 2, or an exception) raises, so every test that shares it fails; nothing is left patched.
- The fixture is session-scoped, defined once, calls that run once, and writes outside the checkout.
- No test function runs verify-all on the checkout itself, read from the code's shape (a list or code string naming
  `verify-all`, with a working directory made from `__file__`): 6 shapes that must be seen and 5 that must not are
  each a test. Two runs are allowed by name, with their reason: the shared one and the headless one.
- All 16 audit tests ask for the fixture.
- The workflows: every workflow file is in a map of the steps that run verify-all; each job runs it at most once;
  CI's `verify` job runs one per runner with `--reuse-evidence` and its bundle step carries
  `--reuse-verify-all artifacts`; the baseline update carries `--no-verify-all`.

Existing tests already cover the rest and were not duplicated: standalone verify-all's steps and their order
(`test_verify_all_steps_are_canonical`), failure propagation inside verify-all and the release check
(`test_cli_verify_all`, `test_verify_all_reuse_bundle`), the installed wheel (`test_wheel_bundles_engine_data`, `test_test_lanes_contract`),
the fan-ins (`test_ci_require_jobs`, `test_gpu_shards`), and the push/pull-request rule (`test_extended_dedup`).

## Limits and remaining opportunities

- **The policy reads code shape.** A verify-all hidden behind a helper in another module, or a checkout path not made
  from `__file__`, is not seen.
- **A failed shared run fails 16 tests at once** with one cause, where 16 separate runs used to fail one by one.
- **Seeded-folder verify-all tests still pay for the real tooling gates** (7 runs of about 24 s locally): the mypy
  gate and the scans check the engine's source wherever the run is. Standing those steps in for tests that are about
  something else would save about 2 to 3 minutes of the lane, but it changes what those tests exercise: a separate
  decision.
- **The fast tier runs in two parallel jobs.** Removing it from CI's verify-all needs cross-job evidence and changes
  the timing gate; it would not shorten the critical path.
- **`release_draft.yml` with downloaded artifacts** still runs its own verify-all into the downloaded folder. That
  protects the release commit (the download carries no commit identity), but it overwrites what was downloaded. It has
  never run; worth a look before the first release.
- **`weekly_health.yml` and `update_weekly_trends.yml`** run from `main` and last ran, failing, on 2026-09-21.
