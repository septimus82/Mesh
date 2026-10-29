# H2 (F13 / F13b): CI feedback time, test effectiveness and one bounded improvement

Repository health, audit tracker #422 (F13, F13b); related #373. Base: `redesign/visual-editor` at `b5b1786`.

Measurements come from the CI runs' own step timings and logs:

- 40951732377 (#423; attempt 1 Windows, attempt 2 Ubuntu);
- 40946115930 and 40941136374 (#421);
- one local baseline run of the default selection on Windows, with `-rs --durations=40`.

No CI run was triggered to collect evidence.

## 1. Where the time goes

**Required PR wall time is set by the Windows `tests` job.** In the three latest PR runs, the last required check
finished at **+14.4, +18.1 and +16.6 min**, with about 3 s of queueing each time. `web-smoke` and `arcade3-canary`
finish in under 1 min. A merged PR then triggers a second full run on the integration-branch push. That probably
explains the "about 30 minutes" a change takes end to end.

**One required `tests` job, step by step** (run 40951732377):

| Step | Ubuntu (att. 2) | Windows (att. 1) |
|---|---|---|
| Checkout, Python, install, compile | ~35 s | ~60 s |
| `pytest -q`: the full default selection (10,124 passed) | 253 s | 332 s |
| `verify-all` (artifacts) | 115 s | 155 s |
| `release bundle` (seeded) | 212 s | 291 s |
| bundle verify, diffs, upload | ~10 s | ~15 s |
| **Job total** | **10.6 min** | **14.3 min** |

**Inside one `verify-all`** (Ubuntu): `pytest-fast` 75.7 s, `mypy-gate` 13.8 s, `verify-demo` 10.0 s, `web-smoke`
4.0 s, `swallow-scan-gate` 3.3 s, `exception-policy-scan` 3.2 s, and smaller steps. That's about 113 s in all.

**The same validation runs repeatedly in one job:**

| Work | Times per `tests` job | Where |
|---|---|---|
| The fast tier's tests | **4** | in the full `pytest -q` (the fast tier is a subset of it); in `pytest-fast` in CI's `verify-all`; in `pytest-fast` in the bundle's `release-check`; in `pytest-fast` in the bundle's demo-run's own `release-check` |
| A whole `verify-all` (fast tier, mypy, demo, web-smoke, scans) | **3** | CI's step; the bundle's `release-check`; demo-run's `release-check` |
| `export build` | **4** | inside each `release-check` (×2), demo-run's own step, and the bundle's own step |

The bundle's two `release-check` runs are the **same command on the same checkout, with the same arguments, in the
same process**: only the folder they write to differs. In the Windows log, the bundle step is the bundle's
`verify-all` (134 s, `pytest-fast` 100.84 s), then demo-run's `verify-all` (**140 s**, `pytest-fast` 105.38 s), then
about 16 s of export, zip and self-verify.

**Fast tier, normalised by the advisory's run speed** (`pytest-fast` ÷ speed):

| Run | Ubuntu | Speed | Normalised |
|---|---|---|---|
| #421 `f6dbf03` | 77.45 s | 1.10 | 70.4 |
| #421 `926c3a7` | 78.44 s | 1.12 | 70.0 |
| #423 attempt 1 | 83.97 s | 1.21 | 69.4 (**failed**: speed outside the calibrated range) |
| #423 attempt 2 | 75.69 s | 1.10 | 68.8 |

The fast tier's work is flat at about 69–70 normalised. Failures come from slow runners hitting a threshold set with
about 3 s of headroom. `exception-policy-scan`: Ubuntu 3.16–4.04 s against 3.56 s; Windows 3.29–4.03 s against 3.74 s.

## 2. Test inventory (baseline `b5b1786`)

Local Windows default selection: **10,126 passed, 262 skipped, 163 deselected** (10,553 collected). CI reports
10,124 / 260, because CI runs the packaging-hygiene tests that a local run skips.

**Skipped (262, by reason from `-rs`):**

- **257: GPU / GL opt-in** (`MESH_GL_SMOKE=1`, real-window tests). The largest files: shadow compositing 16, water 16,
  Studio workspace 14, shadow corners 13, terrain 13, the HD-2D asset pipeline 12, the starter 12, Studio workflow
  polish 12.
- **3: packaging hygiene,** skipped locally and run in CI (`CI=true`).
- **1:** `monster_minimal_spike` isn't present beside Mesh.
- **1:** no allowed alias pairs are defined.

**Deselected (163, `slow` or `e2e`):** mostly CLI help-text regressions (stamps 11, AI 7, assets 7, QA 6, pipeline 5,
scene management 5, world 4), the scene-controller facade guard 9, CLI JSON purity 5, `verify-all` CLI 5, the preset
header toast 5, and the lighting contract 4.

**Coverage gaps, reported and not changed here:**

- **No workflow runs the 163 `slow`/`e2e` tests.** `weekly_health` also uses the default selection.
- **No CI lane runs the 257 GPU tests** (audit F8). They protect creator workflows (Studio, real-window play, save and
  reopen) and are run by hand.

**The slowest individual tests** (local default run): perf-run thresholds 12.4 s, scatter-diagnostics hash seeds
10.7 s, the perf-run replay report 7.3 s, generated-docs freshness 5.3 s, doctor-assets fix 4.8 s, the
logging-policy repository scan 4.8 s, list-scenes determinism 4.7 s, durable-write policy scan 4.2 s, asset hygiene
4.2 s, and the export-bundle overwrite guard 4.1 s. The rest of the top 20 are 2.7–3.7 s, mostly repository-wide
policy scans and CLI determinism checks. No single test dominates: the cost is the size of the tier plus the
repeats above.

## 3. Prioritised improvements

1. **The bundle's demo-run reuses the bundle's own `release-check`** (this PR). It removes 1 of 3 `verify-all` runs,
   1 `export build` and 1 `debug-bundle` per job: about **140 s on Windows and about 100 s on Ubuntu**. It's
   identical work (above), so no distinct validation is lost.
2. **The bundle's `release-check` reuses CI's `verify-all` step,** which runs earlier in the same job on the same
   checkout. That's about 115–155 s more per job, and one more fast-tier execution gone. It needs an explicit
   provenance decision: the bundle would embed reports produced by the CI step, not by its own run. That's a design
   change to `release check`; proposed, not done.
3. **Split each OS's `tests` job in two parallel jobs:** (a) `pytest -q`, (b) `verify-all`, then bundle and bundle
   verify. Neither needs the other's results. Windows wall time would go from about 14 min to about 7–8 min, and
   Ubuntu from about 10.6 to about 5.5 min, for slightly more runner minutes. The required checks' names change, so
   branch protection must be updated by the owner. Proposed, not done.
4. **The fast tier runs again after the full suite passed.** Its timing gate needs a measured run, so this stays
   until the gate can use the default run's own durations for the fast subset. That's a design question for #373;
   proposed only.
5. **Skip the integration-branch push run when the merged tree equals the PR head CI just passed.** A `--no-ff`
   merge of an up-to-date branch yields the identical tree, as the last six merges did. The push run currently
   repeats the whole PR run (and feeds the timing rolling check). Needs a careful rule, so proposed only.
6. **Lanes for the uncovered tests:** a scheduled `slow`/`e2e` lane, and a curated GPU lane (F8).

None of these deletes tests, relabels tests, or changes thresholds.

## 4. The implementation (item 1)

`mesh_cli/release_bundle.py` `_step_demo_run` runs `mesh demo pipeline` with its first step (`release-check`) replaced
by a copy of the bundle's own `release/` reports into `demo/release/`. That copy is what the demo's run would have
written there. The bundle stops at the first failed step, so this only happens after the bundle's own release check
passed. The demo report records the step as `{"dir": "release/", "reused_from": "release/"}`. Every other demo step
(new game, campaign replay check, debug export, export build) runs as before.

`mesh demo pipeline` on its own is unchanged and still runs its own release check. The CI workflow, thresholds,
markers and branch protection are unchanged.

**Tests:** `tests/test_release_bundle_demo_reuse.py` (fast, 2 tests):

- The bundle runs `release check` **once**, the demo's `release/` holds byte-identical reports, the demo report
  records the reuse, and the demo's later steps still run.
- The demo pipeline on its own still runs its release check.

The first test fails on `b5b1786` ("assert 2 == 1": release check ran twice). The existing release-bundle and demo
tests pass: 128 in the related set.

**Local limit:** a full `mesh release bundle` doesn't complete on this Windows machine, on `b5b1786` or with this
change. Its release check's `verify-all` stops at `web-smoke` (web build tooling isn't installed locally), the same
way both times. End-to-end evidence therefore comes from CI.

## 5. Before and after

The before figures are measured from the base CI runs above. The after figures come from this PR's single CI run:
see the PR description.
