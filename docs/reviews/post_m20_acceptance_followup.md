# Post-M20 repository health: acceptance and critical fixes

Follow-up to [`post_m20_repository_health.md`](post_m20_repository_health.md), after the owner's acceptance (CONDITIONAL PASS) on 2026-10-27.

**Status: stopped for the owner's review.** Lakeside Village and Audio & Atmosphere have not begun. #344 is still a draft and `main` is untouched. Every new PR is a draft.

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
- **Trade-offs reported:**
  - authored fields of objects edited after a save stay as saved;
  - a new save whose room was deleted loads without the room's look;
  - `DoorLock` has no saved state (this predates #399).
- **CI:** all tests pass; budget-only failures (#373), not rerun. Recorded on #399.

## 3. CI timing: draft [#400](https://github.com/septimus82/Mesh/pull/400)

Measured on 200 CI jobs (2026-10-25 to 27); proposal: [`ci_timing_proposal_373.md`](ci_timing_proposal_373.md).

- **The current rule** fails 50 % of Linux and 54 % of Windows jobs on the current code.
- **The cause is real growth** of the fast tier, +14–16 % since calibration. The rolling check detects it, and its control is clean.
- **Rules compared** under injected regressions:
  - fixed thresholds;
  - the advisory;
  - a reviewed recalibration;
  - fixed ceiling and advisory both (rule f): 0 % / 4 % false failures, 88 % detection of ×1.25 on Linux and 92 % of ×1.5 on Windows.
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
  - CI's whole sequence (pytest, then verify-all, then the release bundle) passes on Windows/Python 3.13.
- **CI's exit 2 is a different failure:**
  - CI's verify-demo passed; its inner verify-all stopped between `pytest-fast` and `player-package-gate`;
  - leading candidate: `pytest-fast-duration-guard`, whose baseline the outer verify-all writes in the same job;
  - not reproduced locally; the kept reports will name it next time.

## 5. Test-suite performance: draft [#402](https://github.com/septimus82/Mesh/pull/402)

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
| **#373** CI timing | measured: real fast-tier growth plus runner variance | 50 % of jobs red, all tests passing | owner decision on #400; pay back via #402's next steps |
| **#390** saved world | **draft fix #399** | stale worlds in old saves; 4× save size | owner review; then authored-field split per behaviour |
| **#394** release check | **local cause fixed (#401)**; CI cause narrowed to 3 candidates | Windows release bundle red once | merge #401's diagnostics; read the next failure's report |
| Test-suite cost | **#402** | GPU tier 19 min; default suite 6.5 min; the fast tier grows each milestone | xdist decision; subprocess and scan sharing |
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
- **#399's composition** keeps saved objects' authored fields; an object's edited dialogue doesn't reach older saves.

## Housekeeping

- Worktrees `Mesh-health`, `Mesh-export`, `Mesh-ci`, `Mesh-perf` and `Mesh-docs` hold the draft branches. They are left in place for review.
- Scratch projects, venvs and runs live in the session's scratch folder and are removed after this report.
- The owner's checkout, stash, `user_settings.json`, untracked files and the M14 Check project were not touched.
