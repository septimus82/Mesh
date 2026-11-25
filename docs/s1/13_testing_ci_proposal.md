# S1 Testing and CI Improvement Proposal

**Source:** part C (`03_testing_ci_debt.md`, costed recommendations 5.1–5.12, CI history up to run `45605002991`), plus parts A, B and D and s1v for what the tests missed. Roadmap items are in `12_stabilization_roadmap.md` (S1-5 and the test parts of S1-3 and S1-4).

## 1. Conclusion first

**The problem is where the tests point, not how many there are.**
- Mesh has 13,971 tests in 1,996 files. Only 146 files are real-window files: by part C's definition, a file that constructs a GameWindow, the headless editor, or worker/Studio processes, or holds a `gl` test. About 680 non-GL tests in those files (≈ 5%) gate every PR.
- 3,717 tests sit in files that use a fake window and no real window (a per-file classification). The whole suite has only 20 spec'd doubles.
- Every P1 that S1-0 found sat on a seam the tests skip (part C proved the pattern on 10 case studies; the later P1s are mapped in `10_health_report.md` §1):
  - event delivery;
  - removal;
  - room re-entry;
  - save/load across rooms;
  - Studio → runtime;
  - the project root;
  - real key input in a player launch (#660).

**The proposal adds confidence where it is missing and removes duplicate work:**
- **Add about 30 real-runtime contract rows** (6 contracts), **1 end-to-end creator workflow test**, **1 template smoke** and **about 10 mutation-proven assertions**. That is roughly 60 tests, not thousands.
- **Make every gate fail closed**, put **floors** on every lane, and adopt a written **flake policy**.
- **Remove duplicate execution** (R2–R4), and rebalance shards (B1, exit-required).
- **Keep the pytest-fast hard ceiling.** R1 is only a candidate, and only if the ceiling moves with it (§3).

**Net effect if everything here is approved:**

| Measure | Today | After S1 (all approved) | After S1 with D9 = no (B1 rebalancing still applied) |
|---|---|---|---|
| CI push wall, p90 | 15.7 min | ≈ 12–14 min | ≈ 15–15.7 min (meets E10 only because B1 splits Linux pytest; without B1, ≈ 16.7, **breaching E10**) |
| Extended push wall, p90 | 38.7 min | ≈ 35–36 min (B1 rebalancing −3 to −4 min; the gl e2e leg adds about 1 min to a gpu shard, not yet measured) | ≈ 35–36 min |
| Job-minutes per merge | ≈ 345 | ≈ 210–230 (≈ 200 if R1 is also approved with its ceiling kept) | ≈ 360 (E10 limit with D9 = no: ≤ 370) |
| Real-runtime tests on the six high-risk contracts | 0 of 6 contracts | 6 of 6 | 6 of 6 |
| Mutation kill (40-mutant probe) | 28/40 | ≥ 36/40 | ≥ 36/40 |
| Non-change CI failures | ≈ 5% (ep05 4 of 7) | ≤ 2% (target E9) | ≤ 2% |

The wall figures are estimates from part C's medians, since CI records no per-test durations. Each change below is measurable with `docs/s1/evidence/ci_timing_analysis.py`.

## 2. What the current suite misses, and the cheapest catch for each

| Pattern (part C §1.3) | Defects | Cheapest catch | Roadmap |
|---|---|---|---|
| The fake invents the API | #622 B, #636, #641; also #643, the fake-only attributes in #646 | Spec'd `fake_window()` generated from a real window, plus a meta-test that fails on a production read of an attribute nothing creates | 5.6 |
| The test calls the hook it assumes the runtime calls | #622 A, #637 | Drive through the real delivery and removal path: a removal contract over every subscriber, and a runner-delivery smoke | 5.6, 4.5 |
| Document or internal state asserted, not the outcome | #620, #639, #640, #651 | A picker contract: author through `project_ops`, play in a real window, assert what the creator sees, then revisit and save/load | 3.0 |
| Missing negative branch | #619; survivors Q1, Q3, Q5, O1, O3, O4, V1, V2, V4 | One assertion per survivor, each proven to kill its mutant | 5.5 |
| Parallel runtime tested instead of the live one | #642 (CutsceneRunner), D-3 (episode harness), D-7 (mesh_net copies) | Cross-component smokes (MCP write → GameWindow); one real-window episode; shared-function parity tests | 5.6, 6.2, 6.4, 6.5 |
| No test spans creation → export | #652, #655, #656, and the chain workarounds | One e2e workflow test plus a template smoke in Extended | 5.7 |

## 3. The proposal, costed

**Conventions:**
- **Where** is the lane: `pytest` = the required CI jobs on both OSes; `extended` = the Extended non-GL lane.
- **CI effect:** + adds, − saves; "wall" is on the critical path.

| # | Change | Catches / protects | Where | CI effect | Roadmap | Decision |
|---|---|---|---|---|---|---|
| **A1** | Shared hidden real-window fixture `real_game()` (`interact`, `frames`, `walk`, `revisit`, `save_load`) | Every runtime regression test in S1 | `pytest` | ≈ 0 by itself | 3.0 | no |
| **A2** | **Picker contract** over `behaviour_guide.GUIDES` (about 15 rows). Strict-xfail rows for open defects flip as fixes land | #620, #622 A, #636, #639, #640, #651, #652, #654 and the next one | `pytest` | **+≈ 30 s wall per OS** | 3.0 | no |
| **A3** | **Removal contract** over every behaviour that subscribes in `__init__` (12 today; new ones are picked up automatically) | #637 and every future subscriber | `pytest` | +≈ 6 s | 5.6 | no |
| **A4** | **Fake-only attribute meta-test** (`contract_gaps_real_window.py` as a test) plus a spec'd `fake_window()`; migrate the 133 MagicMock and 327 SimpleNamespace windows only as files are touched, case-study files first | #622 B, #636, #641, #643 class | `pytest` | +≈ 5 s (one real window plus an AST scan) | 5.6 | no |
| **A5** | **Two cross-component smokes:** a cutscene step on the real SceneController; MCP cutscene write → `GameWindow` | #622 B, #642 | `pytest` | +≈ 3 s | 5.6 | no |
| **A6** | **Fact persistence and CWD contracts:** re-entry and save/load of authored facts; CWD ≠ project for saves, items, cutscenes and legacy file ops | #620, #636, #639, #623, #641 | `pytest` | +≈ 10 s | 2.1, 2.3, 4.1 | no |
| **A7** | **Mutation-survivor assertions** (about 10) | Q1, Q3, Q5, O1, O3, O4, V1, V2, V4 | `pytest` | **< 2 s** | 5.5 | no |
| **A8** | **E2E creator workflow test**, in two parts. **(i)** Non-GL chain (`e2e` marker, which has no users today): `mesh new` → Studio ops, `mesh author` and MCP authoring of every picker feature → a door to a 2D room → `main.py` play with keys through `dispatch_event` → F5 → new process → F9 → export → exported play, save and reload. **(ii)** HD-2D leg (a door into an HD-2D room, walk, draw, return): marked `gl`, so it runs only in the gpu lane with `MESH_GL_SMOKE`, per repo policy. Promoted from `e2e_creation_to_export_chain.py` and the s1v scripts | The whole create → export chain (E3) | (i) `extended`, both OSes; (ii) gpu lane | (i) +≈ 2–4 min job-min per OS (estimate); expected to leave Extended wall unchanged, since the `extended` job would reach about 6–9 min against the 30–37 min gpu shards, but not measured. (ii) +≈ 1 min in one gpu shard per OS; wall impact depends on B1's placement and is not established | 5.7 | no |
| **A9** | **Template smoke:** every `--template` id creates, starts, walks and draws (the `hd2d_rpg` draw check sits in the gl part) | #656 class (E4) | `extended` (+ gpu for HD-2D) | +≈ 1 min job-min; wall expected unchanged (not measured) | 5.7 | no |
| **G1** | **Gates fail closed:** mypy-island reads its returncode; "tooling unavailable" exits 2; silent missing-input steps report `skipped:` and CI fails on un-allow-listed skips | #624 C/D, the mypy-island probe | `verify` | +≈ 5 s | 5.1 | no |
| **G2** | **Baseline growth checked against the merge base**; the mypy count guard reads the committed baseline. RUF100 has moved to roadmap 7.6, after S1-4, because it edits about 2,355 `noqa` lines across `engine/`, `mesh_cli/` and `mesh_net/` and would conflict with the fix PRs | #624 B/C | `verify` | +≈ 5 s | 5.1 | no |
| **G3** | **Lane floors:** gpu 256 → about 600; Windows shard check `--min-selected` about 13,500; Linux JUnit plus a floor; a contract test keeps every floor within 5% of collection | #648 (E6) | all | ≈ 0 | 5.2 | no |
| **G4** | **Silent gaps:** `.[mcp]` in the Linux pytest job; delete `pyrightconfig.json`; replays print failing cases | #649 | `pytest`, `replays` | +≈ 10 s install | 5.4 | no |
| **R1** | **Fast tier once (only with its gate preserved).** Today the pytest-fast step in verify-all is a **failing gate**: it fails over a hard ceiling of 130.4 s (#427, part C §3.4), and it exercises the fast tier as its own collection (`-m fast` skips modules without fast tests, `conftest.py:244-255`). Skipping it in CI's `verify` jobs (`MESH_SKIP_PYTEST_FAST=1`) is acceptable only if both move to a new home: a cheap `pytest -m fast --collect-only` with a count floor, plus a **failing** ceiling computed from the pytest job's durations for fast-marked tests. That ceiling needs recalibration, because durations inside the full suite differ from a standalone run. Making the budget report-only would **remove a failing gate**: that needs your explicit approval, and #373 would then close by removal, not by a fix | duplicate execution | `verify` | **−≈ 3.6 job-min per run** (≈ −10 per merge); off the critical path. Recommended: decline, unless the preserved-ceiling variant is built | 5.8 | **D9** (gate change) |
| **R2** | **Second verify-all out of the pytest job:** first measure the `verify_all_audit_artifacts` fixture (17 test files) with `--durations`. If it costs minutes, feed those audit tests the `verify` job's reports, or unit-test the audits on fixtures | duplicate execution on the critical path | `pytest` | **est. −1.5 to −3 min wall per OS** (measure before deciding) | 5.8 | **D9** |
| **R3** | Fold the `web-smoke` job into verify-all's identical steps, or the reverse | duplicate execution | CI | −≈ 0.5 job-min | 5.8 | D9 |
| **R4** | **Push-side dedup:** skip a push run's jobs only when a green PR run tested the **identical tree** (the merge commit's tree hash equals the tested merge ref's tree) at the same workflow revision, and link that run as evidence, as the #344 rule does. If the base moved, the trees differ and the run happens, which keeps the #600 + #601 combined-tree protection | the same tree tested twice | CI and Extended | **up to −58 (CI) and −104 (Extended) job-min per merge** when the PR was current (≈ −45% of per-merge cost) | 5.8 | **D9** |
| **B1** | **Rebalance the Windows gpu plan** from measured timings (shard 2/2 takes 37.2 min, shard 1/2 29.6); optionally 3 shards. **Shard Linux pytest in two.** **Exit-required:** it is the offset that keeps E10 within budget | critical path | Extended, CI | Extended wall **−3 to −4 min** (balanced; ≈ −12 with 3 shards, +≈ 3 job-min); CI wall −1 to −2 min (+≈ 2 job-min) | 5.9 | no (no change to what runs) |
| **P1** | **Flake policy** (§5) and a quarantine mechanism | #612-class gate trust (E9) | all | ≈ 0 | 5.3 | **D10** |
| **P2** | **Lane budgets** in the existing report-only `timing rolling check`: pytest (ubuntu) p90 ≤ 15 min; Windows shards ≤ 13; verify ≤ 7; Extended wall ≤ 40. A PR adding > 30 s to a required lane names its offset or justification | slow growth | report-only | ≈ 0 | 5.8 | no |
| **C1** | **Retire document-shape tests:** the 24 `*_content_contract.py` files (246 tests) assert JSON values that nothing reads (#640). Replace them with one data-driven content check that loads each chapter in the real runtime for its key interactions, or rely on verify-all's content audit for shape | maintenance, false confidence | `pytest` | small − | 6.x / opportunistic | no |

**Sum of the additions to required lanes:**
- ≈ +55–60 s wall per OS (A2–A7, G1, G2, G4);
- offset by R2 (−1.5 to −3 min) and B1 (CI −1 to −2 min).

Without R2, the Linux shard split in B1 is what keeps CI p90 within E10's ≤ 16 min. That is why B1 (roadmap 5.9) is exit-required.

## 4. Lane map after S1 (what runs where)

| Lane | Runs | Changes in S1 |
|---|---|---|
| `pytest` (required, every PR and push, both OSes) | default suite (`not slow and not e2e`) | + contracts A2–A7; + floor (G3); − in-suite verify-all if R2 approved; Linux possibly 2 shards (B1) |
| `verify` (required) | verify-all, release bundle, baseline diff | the fast tier and its failing 130.4 s ceiling stay, unless D9 approves R1 with the ceiling moved; gates fail closed (G1, G2) |
| `acceptance`, `installed`, `replays`, `arcade3-canary`, `web-smoke` | unchanged | `replays` prints failing cases (G4); `web-smoke` folded into verify-all (R3, if approved) |
| Extended `extended` (every push and dispatch) | `(slow or e2e) and not gl` | + e2e workflow part (i) (A8) + template smoke (A9); floor stays equal to the count |
| Extended `gpu` (2–3 shards per OS) | `gl` | rebalanced (B1); floor 256 → about 600 (G3); + the e2e HD-2D leg (A8 ii) |
| Extended `quarantine` (new, report-only) | quarantined tests with live issues | §5 |
| Push runs (CI, Extended) | the merge commit | skipped only on proven identical-tree evidence (R4, if approved) |

## 5. Flake quarantine policy (proposed; decision D10)

1. **Never weaken.** A failing-but-flaky test is never loosened, silently retried or skipped. Budgets and limits change only on evidence and with owner approval (as for #612).
2. **Quarantine needs all four:**
   1. an open issue holding the failure evidence (run id, log excerpt);
   2. an entry in `tests/baselines/quarantine.txt` naming the test, the issue and an **expiry ≤ 30 days**;
   3. the test moves to the Extended `quarantine` lane, where it **still runs and reports**;
   4. a contract test that fails CI on an expired or issue-less entry (the `never_runs.txt` pattern).
3. **Required lanes keep `-W error`.** A re-run attempt is a manual decision, recorded in the PR or issue. A push failure is re-run only with the owner's or coordinator's authority (existing practice).
4. **Quarantine triggers:** the second non-change attempt-1 failure of the same test within 30 days. NEW-15 (the ownership race) and the 2026-11-22 replays-job failures are watched under this rule. #612 is fixed at the root instead (#661).
5. **Reporting:** the flake rate (E9) is recomputed at every stage boundary from `fetch_ci_history.sh` plus `ci_timing_analysis.py`.

## 6. Growth rules (keep the suite bounded)

- **A new runtime behaviour adds one row** to the picker, removal or fact contract, not a new fake-window test file.
- **No new MagicMock or SimpleNamespace window** in a file that tests runtime behaviour. Use `fake_window()` (spec'd) or `real_game()`. The meta-test enforces the attribute side.
- **Every fix PR ships one real-runtime regression test with a mutation proof.** Extra unit tests are optional.
- **The +30 s rule:** a PR that adds more than 30 s to a required lane names its offset (R1, R2, B1, C1) or its justification.
- **Floors move only on purpose** (the documented `test_tiers.py` rule), and the contract test keeps them within 5% of collection.

## 7. Measurement plan (how the exit criteria are checked)

| Exit criterion | Tool | Cadence |
|---|---|---|
| E3, E4 (e2e, templates) | the Extended `extended` lane result over 5 consecutive pushes | each stage boundary |
| E5, E6 (gates, floors) | their own contract tests in `pytest` and `verify` | every run |
| E8 (6 contracts) | test ids present and green; meta-test allow-list ⊆ open issues | every run |
| E9 (flakes) | `docs/s1/evidence/fetch_ci_history.sh` + `ci_timing_analysis.py` (attempt-1 failures classified from logs; executed runs only, with an R4-skipped push counted through its linked PR-side run) | each stage boundary |
| E10 (time, cost) | `ci_timing_analysis.py` (median, p90, job-min per merge over 30 executed runs; skipped runs excluded) | each stage boundary |
| E11 (mutation) | each named #650 mutant killed by its named test, via `docs/s1/evidence/mutation_probe.py` (test lists and anchors updated in 5.5) + `mutation_run.sh` (one process at a time) | once at close |

## 8. What this proposal does not do

- It does not add thousands of tests, migrate all 3,717 fake-window tests at once, or chase a coverage percentage.
- It does not add physical-GPU CI (the gpu lane stays Mesa).
- It does not change performance budgets.
- It does not run full stress locally (the owner's CPU limit). Heavy validation stays in CI and Extended.
- It does not prove Studio's GUI. Agents may not run visible GUI automation, so the owner's hands-on acceptance (E12, D13) is the only GUI check.
