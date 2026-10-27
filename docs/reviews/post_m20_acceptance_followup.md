# Post-M20 repository health: acceptance and critical fixes

Follow-up to [`post_m20_repository_health.md`](post_m20_repository_health.md), after the owner's acceptance (CONDITIONAL PASS) on 2026-10-27.

**Status: post-M20 integration closed (2026-10-27).** The next milestone is Lakeside Village. #344 is still a draft and `main` is untouched.

## Final integration

The owner approved #400 at `47eff43`, then #404 at `8d1c8b4` and #401 at `55a98aa`, and asked for #399 and this report to be integrated once their conditions were met. pytest 9.2.0, released on 2026-10-27, broke three tests on every branch; #404 fixed them.

| Order | PR | Approved head (unchanged) | Before merging | Merge commit on `redesign/visual-editor` |
|---|---|---|---|---|
| 1 | #402 test-suite performance | `0e2df09` | assertions unchanged; packaging determinism; CI timing-only | `2a7804a` |
| 2 | #400 CI timing: Rule F, rolling check, one run per commit | `47eff43` | CI green on both OSes; on the merged tree: 38 targeted tests and the analysis self-check | `6958a2c` |
| 3 | #399 the saved world (#390) | `c87583f` | merges cleanly; on the merged tree: 618 save-related tests, 6/6 saved-world GPU tests (hidden windows), the save-diagnostics contract and the tier ratchet | `4988eb2` |
| 4 | #404 pytest 9.2 compatibility (test-only) | `8d1c8b4` | owner-approved; 9,934 functional tests passed on both OSes; Linux's red result is a Rule F timing-budget failure (exception below) | `cdd4bc4` |
| 5 | #401 the release check (#394) | `55a98aa` | owner-approved; latest Windows and Linux CI passed, release bundle verification included; it carries the same test fix as #404 (cherry-picked), merged after #404 with the test file identical to #404's, so the change is neither duplicated nor undone | `005d089` |
| 6 | #403 this report | | documentation only | the merge of this PR |

**Verification of the final integration (`005d089`)**, without a full-suite rerun:

- **Targeted tests:** 119 tests in the files these merges touch pass under pytest 9.2.0 and under 8.4.2:
  - duplicate-to-grid and verify-demo;
  - the release bundle, self-verify and seeded determinism;
  - Rule F and the saved world;
  - the tier ratchet, `--help` and the workflow contract.
- **GPU tests:** 6/6 saved-world tests in hidden windows.

**Documented exception (#404):** its Linux CI job failed only verify-all's step-time budget. Rule F applied and confirmed it: the committed advisory model judges pytest-fast slow, the fast tier's growth (#373). Every functional test passed (9,934). It was not rerun for a green badge.

**#394's original CI exit 2 remains unproven.** It has not recurred since the diagnostics merged, and no root cause is claimed. The leading hypothesis (the pytest-fast duration ratchet) is still a hypothesis. The next occurrence will be classified by the kept reports.

**After the merges:**

- **The rolling check runs and publishes.** On the first integration push (`6958a2c`, job 122481850070) it:
  - collected 56 tests jobs;
  - wrote `--rolling 24` to the job summary;
  - raised its warning annotation: pytest-fast is a persistent regression on both OSes (1.104 Linux, 1.131 Windows), and Windows' exception-policy-scan too (1.107).

  It is report-only, so the job passed.
- **Stale statistics corrected:**
  - `_apply_rule_f`'s docstring now quotes the committed-model figures (failing 12 → 9 Linux, 13 → 2 Windows; ×1.25 detected 21/24 and 9/24), not the refit-model 0 % / 4 %;
  - the proposal's Rule F row says which model it assumes;
  - the proposal's status is "merged".
- **#401's diagnostics:**
  - the environment allow-list now shows only switches, seeds and encodings: `PYTHONPATH`, `PYTHONHOME`, `PYTEST_ADDOPTS` and `MESH_REPO_ROOT` are redacted (tested with a private-looking path);
  - a failed bundle prints whether release-check failed timing-only (the step-time budget, the pytest-fast duration guard) or functionally;
  - #394's original CI exit 2 is **not** claimed as explained: it has not recurred since the diagnostics, so there is no evidence of its cause yet.

**Unresolved, carried into Lakeside Village as known limits (not blockers):**

- **The fast tier's growth is not paid back.** Rule F still fails Linux runs where the committed model judges pytest-fast slow, and the rolling check reports it. Paying it back or refitting the model is a later decision.
- **#394's exit 2:** read the next occurrence from `artifacts/release_bundle_failure/` and the classification line.
- **#344's duplicate CI runs** remain (19 of 59).
- **A branch with no PR** gets no automatic CI run.

The sections below are the record as it was written during the review rounds.

## 0. Owner review round (2026-10-27): corrections and final statuses

The owner reviewed #399–#403 against GitHub's code and CI. That review found two genuine Windows test failures in #401 and a compatibility gap in #399, and it set conditions on #400 and #402. What was done:

| PR | Owner's finding or condition | Done | Commits | Status |
|---|---|---|---|---|
| **#401** (#394) | **STOP:** two genuine Windows failures in `test_verify_demo_command.py` (artifacts-scoped scratch; distinct paths across runs); redact the environment; collect only known-safe files | see below | `601c0fe`, `9f115e0`, `c794c54` | **CONDITIONAL PASS**: both formerly failing tests pass on Windows CI (`9f115e0`); the ratchet fix's CI (`c794c54`) was still running at writing |
| **#399** (#390) | saved objects overrode later authored dialogue, appearance and behaviour; a new save without its room loaded half-built | see below | `ea45381`, `c87583f` | **CONDITIONAL PASS**: all tests pass on CI (9,932); 3 jobs budget-only (#373), 1 still running at writing |
| **#400** (#373) | Rule F provisionally approved: implement it in the gate; keep the rolling check visible; don't overstate Windows detection; confirm the duplicate-run coverage (#344) | see below | `5800b1a`, `790a613`, `457b4a1` | **CONDITIONAL PASS**: owner decisions open (model refit; the trigger commit); CI on `457b4a1` still running at writing |
| **#402** | accepted in principle: verify head, assertions, packaging determinism and CI cause before merging; no `pytest-xdist`; note it doesn't fix the fast tier's growth | verified, then merged | `048fd3c`, `0e2df09` → **merged `2a7804a`** | merged |
| **#403** | this report: final statuses, findings, limitations | this section | | draft |

**#401: what the Windows failures were, and the fix.**

- **Cause:** on CI, pytest's `tmp_path` is long (`C:\Users\runneradmin\...\pytest-of-runneradmin\...`), so the 150-character fallback moved basetemp out of the artifacts-scoped scratch. The tests rightly forbid that. The fallback folder (`<temp>/mesh-vd/<pid-run>`) also wasn't unique per run.
- **Reproduced locally:** on `601c0fe`, with a CI-length tmp root, the same two tests fail. I hadn't hit it before because my local tmp path was shorter.
- **Fix:**
  - basetemp stays `<run root>/basetemp` whenever that fits;
  - past 150 characters it gets a new `mkdtemp` folder for that run alone. The run's root names it (`basetemp_location.txt`). It is removed when the run passes, and kept and reported when it fails.
- **Tests:** the two original tests keep every assertion and now pin the artifacts-scoped branch explicitly. The too-long branch has its own tests, the same on every machine:
  - unique per run, short, and removed on a pass;
  - kept on failure, reported.
- **Redaction:** the failure report lists `MESH_`/`PYTHON`/`PYTEST` variables by name. Values are shown only for a known-safe list; a fake token's value never reaches the file.
- **Report collection:** a failed bundle keeps only release-check's known reports (`FAILURE_REPORTS`): no debug bundle, test projects or payload.
- **A second CI failure (`c794c54`):** my new test lacked a tier marker, so the tier-marker ratchet failed. Fixed.

**#399: authored world, runtime state.**

- **Objects:** an object the room still has is now the room's as authored now (dialogue, picture, behaviours), standing where play left it (`x`, `y`, `elevation`). Its inner state (Health, quest hooks, dialogue progress) stays in `saved_entities`.
- **GPU test on a real save.** After the save, the creator:
  - rewrites the Elder's dialogue;
  - repaints a barrel;
  - gives Mara a new behaviour.

  All three reach the old save. The barrel's damage, the positions and the flag stay.
- **A new save without its room** is refused in `SaveManager` before anything is applied (`LOAD_ROOM_MISSING`, a toast). Mid-game the player stays where they are. The save file stays byte-identical and loads once the room is back (tested). The loader refuses too.
- **Saves are slim only when their room can be read.** A scene built in memory keeps its whole snapshot. Six existing round-trip tests caught this case.
- **Mutations:** each is caught by a named test.
  - the save's copy of an object winning again;
  - empty play-owned fields;
  - the refusal disabled.
- **Trade-off:** an object the creator moves after a save stays, in that save, where the save found it.

**#400: Rule F, implemented as a draft.**

- **The gate:** `verify-all` fails a step only when it is over its fixed threshold and the advisory calls it slow. Where the advisory can't judge, the fixed threshold decides (never fails open). The decision is recorded in `verify_step_budget_check.json` (`rule_f`).
- **Measured with the committed model,** on the 24 current-code runs per OS:

  | | Linux | Windows |
  |---|---|---|
  | Failing: fixed rule → Rule F | 12 → **9** | 13 → **2** |
  | pytest-fast ×1.25 detected | 21/24 | **9/24** |
  | pytest-fast ×1.5 detected | 24/24 | 22/24 |

  The model, fitted on 2026-10-25, correctly sees the fast tier's +15 % as slow, which is why Linux still fails. The 0 % / 4 % figures in the first proposal assumed a model refit on the current code, a recalibration that is the owner's call.
- **Windows detection, stated plainly:** an isolated 25 % slowdown on Windows is not reliably detected; reliable detection starts at about ×1.5.
- **Rolling check:** a report-only CI job runs on pushes to `redesign/visual-editor`. It posts to the job summary and raises a warning annotation, and never fails. A scheduled workflow wouldn't fire, because `schedule` runs only from `main`.
- **Duplicate runs:** about 40 of the 59 duplicates go. **#344's 19 stay:** each integration push runs, and so does #344's `pull_request` run. A branch with no PR gets no automatic run.

**#402, merged after verification.**

- **Head:** unchanged (`0e2df09`).
- **Assertions:** none changed (0 assertion lines differ).
- **Packaging determinism:** both byte-determinism tests pass on both OSes and catch the provenance mutation. The release bundle built and passed `bundle verify --strict` on Windows and Linux.
- **CI failures:** timing budgets only.
- **Not in it:** no `pytest-xdist`.
- **It does not fix the fast tier's timing growth (#373).**

## 1. Integration: #389, #395, #397

| PR | Verified before merging | Merged |
|---|---|---|
| #389, exported games start their game | unchanged head; scope (repo-root marker only); regression test fails before the fix; CI: all tests pass, budget-only failures (#373) | `798e122` |
| #395, environment settings robustness | unchanged head; scope; 8 regression tests; CI: all tests pass, budget-only failures | `a0c43eb` |
| #397, the checkpoint report | updated with both outcomes and #398, merged separately | `8613110` |

**The #373 timing failures were confirmed timing-only, not assumed:**

- Each job's log shows every test passing.
- `verify_step_budget` is the only failing verify item.
- No job was rerun for a badge, and no budget was changed.

## 2. #390, the saved world: draft [#399](https://github.com/septimus82/Mesh/pull/399)

- **Principle:** the authored room is authoritative; a save restores progress. Design and compatibility table: [`docs/design/saved_world.md`](../design/saved_world.md) (on #399).
- **Loading:** a save is composed from the room as it is now and the save's runtime state: player, objects, flags, quests, room memory, camera zoom. The objects are reconciled by id.
- **Saving:** new saves leave out the room's settings, map, lights and layers. The decorated room's save goes from 106 KB to about 26 KB.
- **Tests on real saves:** saves written by the engine before the change, in both 2D and HD-2D, still load. A re-sculpt, a cleared scatter and a new wind made after the save all show up. Deleted objects stay gone, added ones appear, and removed ones stay removed.
- **No destructive migration:** old saves are never rewritten.
- **Trade-offs, as first reported** (both corrected after the owner's review, section 0):
  - ~~authored fields of objects edited after a save stay as saved~~: now the room's object as authored now, where play left it;
  - ~~a new save whose room was deleted loads without the room's look~~: now refused clearly and recoverably;
  - `DoorLock` has no saved state (this predates #399, unchanged).
- **CI:** all tests pass; budget-only failures (#373), not rerun. Recorded on #399.

## 3. CI timing: draft [#400](https://github.com/septimus82/Mesh/pull/400)

Measured on 200 CI jobs (2026-10-25 to 27); proposal: [`ci_timing_proposal_373.md`](ci_timing_proposal_373.md).

- **The current rule** fails 50 % of Linux and 54 % of Windows jobs on the current code.
- **The cause is real growth** of the fast tier, +14–16 % since calibration. The rolling check detects it, and its control is clean.
- **Rules compared** under injected regressions:
  - fixed thresholds;
  - the advisory;
  - a reviewed recalibration;
  - fixed ceiling and advisory both (rule f): 0 % / 4 % false failures with a model refit on the current code (with the committed model: 9/24 and 2/24, section 0); ×1.25 detected on Linux, not reliably on Windows (from about ×1.5).
- **Recommended order:**
  1. pay the growth back;
  2. rule f;
  3. a rolling creep check;
  4. recalibrate only through the reviewed path.
- **Duplicated runs:** 59 of 61 commits ran twice (push and pull_request). #400 limits `push` to integration branches; its own run shows no duplicate.

## 4. #394, the Windows release check: draft [#401](https://github.com/septimus82/Mesh/pull/401)

- **Diagnostics first:** a failed release bundle now keeps its failed steps' reports in `artifacts/release_bundle_failure/`, which CI uploads.
- **The local failure:**
  - cause: Windows' 260-character path limit in verify-demo's nested basetemp;
  - fixed, with a regression test;
  - CI's whole sequence (pytest, then verify-all, then the release bundle) passes on Windows/Python 3.13;
  - the first fix broke two Windows CI tests; corrected in section 0.
- **CI's exit 2 is a different failure:**
  - CI's verify-demo passed; its inner verify-all stopped between `pytest-fast` and `player-package-gate`;
  - leading candidate: `pytest-fast-duration-guard`, whose baseline the outer verify-all writes in the same job;
  - not reproduced locally; the kept reports will name it next time.

## 5. Test-suite performance: [#402](https://github.com/septimus82/Mesh/pull/402), merged `2a7804a`

Findings: [`test_suite_performance.md`](test_suite_performance.md).

- **Changes**, each with before/after and a mutation that still fails:
  - the GPU tier from 19 min to about 8.5: the walk tests encoded evidence clips no assertion read;
  - in-process `--help` checks;
  - one provenance per release bundle: 92 s to 33 s for those files.
- **Proposed tiers:** Quick, Focused, Acceptance.
- **Measured, not done:**
  - `pytest-xdist` (the fast tier from 133 s to 71 s): a new dependency;
  - subprocess CLI tests (100 s);
  - shared scans and GPU setups.

## 6. Clean-installed engine (Part F)

- **Setup:**
  - the integrated tree (`8613110`, `git archive`) built as a wheel and installed in a fresh venv;
  - no `PYTHONPATH`, no `MESH_REPO_ROOT`;
  - hidden windows only;
  - every project in scratch.
- **Evidence:** [`acceptance_clean_install.json`](post_m20_repository_health_evidence/acceptance_clean_install.json).

| | 2D (starter) | HD-2D (hd2d_rpg) |
|---|---|---|
| `mesh new`, `mesh doctor` | ok, ok | ok, ok |
| Play (the player walks) | 150 px | 150 px |
| Studio edit and save | rain, wind | wind, motion, Meadow scatter (63), torch |
| Reopen and play | 150 px; 1,127 colours on screen against 673 before the rain | 150 px; scatter 63, motion on, wind as saved |
| Save, then reopen in a new window | player at (228, 128) both times, flag back | (740, 194) both times, flag back; 100.6 KB (#399 takes it to ~26 KB) |
| `mesh export build` | ok, 1,005 files, 9.6 MB | ok, 1,055 files, 10.2 MB, its scatter assets included |
| The exported game, with its own engine | starts in its room, the player walks 150 px (#389: was 0) | starts in its room, the player walks, scatter and motion as authored |
| Names the developer's checkout | no (project, bundle) | no |
| GPU objects after 5 room changes | identical (88 buffers, 6 textures, 3 framebuffers, 19 programs) | identical (cottage ↔ start: 127, 44, 6, 31) |
| GPU objects after 5 Studio Play/Stop | identical (90, 8, 5, 21); every F4 switched mode | identical (130, 46, 8, 33) |

Notes:

- The 2D starter has one room, so its "room changes" reload the same room.
- One click of a small brush (radius 10 px, about 0.1 m²) places no Small tree. Density is per square metre: radius 64 places 1 and radius 128 places 4. That is by design, though a creator may expect at least one. Recorded below.

## 7. Technical-debt roadmap (updated)

| Item | State | Impact | Next |
|---|---|---|---|
| **#373** CI timing | measured: real fast-tier growth plus runner variance; Rule F in the gate (draft #400); rolling check visible on integration pushes | 50 % of jobs red, all tests passing | owner: merge #400; decide on refitting the advisory model; pay the growth back (#402 didn't touch the fast tier) |
| **#390** saved world | **draft fix #399** | stale worlds in old saves; 4× save size | owner review; then authored-field split per behaviour |
| **#394** release check | **local cause fixed (#401)**; CI cause narrowed to 3 candidates | Windows release bundle red once | merge #401's diagnostics; read the next failure's report |
| Test-suite cost | **#402 merged** | GPU tier 19 → about 8.5 min; default suite about −85 s; the fast tier unchanged and still growing | subprocess and scan sharing; xdist not yet (owner) |
| **#391** Studio reloads the whole HD-2D room per edit | open | undo 1.9 s on the stress room | bounded follow-up |
| **#392** maintenance (op registry, module sizes, study helpers) | open | architecture QA | bounded follow-up |
| **#393** a bad key turns a room 2D | open | older engines open 20E rooms 2D | bounded follow-up |
| **#396** performance recommendations | open | measured payoffs in the checkpoint | with #391 |
| **#375** billboard sun shadows | unchanged | awaiting the owner's field decision | owner |
| **#381** precipitation defects | unchanged | snow-edge hops, gust impacts | open |
| **#359** stale replay goldens | unchanged, no drift | release ship job red | owner decision per case; goldens not re-recorded |
| **#398** 2D Starter Room presentation | recorded, not touched | first impression of the 2D starter | UI-polish task |
| Small brush places nothing for sparse collections | new observation | a creator's first click may do nothing | fold into #391's Studio work or a Studio hint |
| `release_bundle.py` F841 (unused `manifest`) | pre-existing, ratcheted | none | tidy with the next release-bundle change |

## 8. Unresolved risks

- **The budgets stay as they are until #400 is decided.** Every PR shows red timing badges with all tests passing. Read the logs, not the badges.
- **CI's #394 exit 2 is not reproduced.** If it is the duration ratchet, it is a timing check comparing two runs on one runner and belongs with #373.
- **`pytest-xdist` is measured on the fast tier only.** The default suite under it is untested; it has tests that write shared state (#334's class).
- **Rule F with the committed model** still fails Linux on the fast tier's growth (9/24). Going lower needs the model refit on current code, or the growth paid back. Neither is done.
- **Windows detects an isolated slowdown only from about ×1.5** under Rule F. A 25 % regression there can pass a single run; the rolling check is what sees sustained ones.
- **#399:** an object the creator moves after a save stays, in that save, where the save found it. `DoorLock` still has no saved state.
- **#401's exit 2 on CI** stays undiagnosed until the next occurrence; its kept reports will name the step.

## Housekeeping

- Worktrees `Mesh-health`, `Mesh-export`, `Mesh-ci`, `Mesh-perf` and `Mesh-docs` hold the draft branches. They are left in place for review.
- Scratch projects, venvs and runs live in the session's scratch folder and are removed after this report.
- The owner's checkout, stash, `user_settings.json`, untracked files and the M14 Check project were not touched.
