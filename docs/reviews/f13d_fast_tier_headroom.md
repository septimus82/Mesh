# #422 F13-D — Windows fast-tier headroom

## What failed
Post-merge CI 43367798102 (`40d71a4`, #502 merged) failed `verify (windows-latest)` on timing alone: `pytest-fast`
took 213.97 s against its 201.003 s hard ceiling (Windows budget 93,708 ms x ratio limit 1.30 = threshold 121,820 ms,
x report-only ceiling ratio 1.65). Every functional check passed. The run is kept as it was; it was not rerun.

## Root cause
**The fast tier grew 33% since its last cut (#437, 2026-10-31), almost all of it integration-heavy tests marked fast,
which left slow Windows runners at the edge of a ceiling that did its job.** Evidence:

`docs/reviews/f13d_fast_tier_evidence/windows_pytest_fast_history.csv`: every Windows verify job since 2026-11-02
(154), its `pytest-fast` time, the run's runner speed (the speed advisory's leave-one-out estimate from ten other verify
steps) and that time at speed 1.0 (by the speed model's own slope for the step, 0.797):

| period | runs | at speed 1.0: median (min-max) |
|---|---|---|
| 11-02..11-03, after #437, before rivers | 41 | 116.1 s (111.2-135.2) |
| 11-03..11-04, rivers R1-R4A | 18 | 128.2 s (114.5-153.1) |
| 11-05..11-12, after R4B, before waterfalls | 74 | 154.8 s (143.1-198.2), log sd 0.052 |
| 11-12..11-13, waterfalls (509895e, 89204b2, 40d71a4) | 3 | 157.8 s (149.9-175.7) |

- **Tests added:** +39 s at speed 1.0 between the first and third periods, in steps with the rivers PRs (R2 #464, R3
  #465, R4A #467 and above all R4B #468). On this machine the fast tier at `8a607b8` (#437) took 126.7 s, at `40d71a4`
  171.8-176.2 s; by module (`--durations=0`, measured phases 104.8 -> 155.8 s): `test_water_passable` +15.5 s (new,
  R4B), `test_export_bundle` +8.6 s (F4/H7 exports added to an existing fast module), `test_verify_all_reuse` +5.2 s
  (new, F13-B), `test_river_tool` +4.6, `test_river_bed` +4.1, `test_river_mouth` +1.8, `test_river_falls` +1.0 (#502),
  `test_river` +0.8 — 41.6 of the 51 s.
- **Runner variability:** the failed run was on a slow runner (speed 1.28, the calibrated range 0.621-1.302) and
  high for it: 175.7 s at speed 1.0 against the period's median 154.8 s (+13.5%, 2.4 sd). The waterfall PR's first run
  (181.34 s at speed 1.27, 509895e) was 149.9 s at speed 1.0; the code between the two differs by 4 fast tests (about
  1 s): **the 181.34 -> 213.97 s step at equal runner speed is run-to-run variation on a tier that left no room for it**.
  At 155 s a runner at the slowest calibrated speed takes a median 191 s and passes 201 s about one run in six.
- **Stale calibration:** the budgets and the speed model were fitted 2026-10-25 (fast tier then about 93 s), so the
  advisory's `expected` for `pytest-fast` (base 95.6 s) has been about 0.6 of the real time since 11-05: the advisory
  calls every run "slow" and rule f can no longer excuse anything for this step. The fixed hard ceiling is the only
  working limit, and it is not obsolete: it caught a 33% growth on the slowest runners.
- **Waterfalls (#502):** about 1 s of the 51 (`test_river_falls`, 15 tests, 4.2 s of call time locally).

## Remediation (tests only; no budget, threshold, ceiling, model, CI or shard change)
1. **The integration-heavy tests the fast tier gained since #437 move to the integration tier** (as #437 did): 34
   tests. The default suite runs `not slow and not e2e`, so every one still runs in every CI run (the Linux and
   Windows `pytest` jobs) and locally with `pytest`; only verify-all's fast tier, a second copy of them, drops them.
   Every test keeps exactly one tier marker (`tests/test_tier_marker_ratchet.py`).

   | module | moved | stays fast | why they are integration (the repo's markers: integration = filesystem-heavy, multi-module) |
   |---|---|---|---|
   | `test_export_bundle.py` | 3 (16.0 s) | 4 (sounds, own folder) | each builds whole export bundles from a scaffolded project; one runs the bundle in a subprocess |
   | `test_water_passable.py` | 15 (14.7 s) | 9 (0.8 s: passable data, storage, blocking-by-outline rules) | each builds a World and simulates characters and NPC route planning over many frames (0.3-3.2 s each) |
   | `test_authoring_session.py` | 5 (6.6 s) | 3 (offline apply, validated path, save keeps a version) | a CLI subprocess against the API; Studio sessions over project files |
   | `test_river_tool.py` | 7 (4.6 s) | — | Studio's River tool over a project, each 0.56-0.91 s |
   | `test_river_bed.py` | 4 (2.9 s) | 10 (carving, scatter, banks) | character walks through a World over carved terrain; an AI carve with save and undo |
2. **Redundant work removed:** `test_docs_verify_fails_on_each_stale_generated_doc_and_passes_when_fresh` regenerated
   every generated doc twice per doc; each doc made stale alone still fails the check, and one check after all are put
   back replaces the per-doc ones (only the doc just put back had changed). 5.6 -> 3.7 s locally.
3. **The policy pinned** (`tests/test_verify_windows_fast_tier_policy.py`, fast, on the committed budget and speed model):
   the restored tier is never failed on the fastest, median or slowest calibrated runner and keeps a fifth of the
   ceiling as headroom; the failed run fails as it did and the PR run passes as it did; a substantial regression is
   still caught and never excused (slowest runner from x1.4 the restored time, median from x1.7, fastest from x2.5); an
   enforced step's overrun is excused only on a runner slow enough to explain it (`verify-demo`: excused at speed 1.302,
   the same time fails at 1.0).

## Before and after (this machine, Windows, Python 3.13, `pytest -m fast`, alternating runs)
| | runs | wall | tests |
|---|---|---|---|
| before (`40d71a4`) | 2 | 176.2 s, 171.8 s | 5,836 passed, 7 skipped |
| after | 3 | 125.8 s, 126.0 s, 126.1 s | 5,810 passed, 7 skipped (34 integration, +8 new policy tests) |

-27% (about 48 s); the same as at #437 (126.7 s). Scaled to CI: about 112 s at speed 1.0 (from 155), about 139 s on
the slowest calibrated runner: 62 s (31%) under the 201 s ceiling, where a run would need +45% (z about 7 at the
measured run-to-run spread) to fail by chance.

## Not changed, and what it leaves
- Budgets, ratio limits, report-only ceilings, the speed model, CI workflows, GPU shards, terrain gates, networking.
- The ceiling is a fixed time: a slow runner sees growth sooner than a fast one (x1.4 against x2.5 above). The
  rolling check (`ci_timing_analysis.py --rolling`, report-only) is what sees gradual growth; refitting the speed model
  so rule f can judge `pytest-fast` again, and a speed-scaled ceiling, are possible follow-ups (not proposed here: the
  fixed ceiling worked).
- Growth comes back the way it came: integration-heavy tests marked fast. New World simulations, exports, Studio
  sessions and CLI subprocesses belong in the integration tier (as #437 said for filesystem, bridge and subprocess
  tests).
