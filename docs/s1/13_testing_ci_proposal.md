# S1 Testing and CI Improvement Proposal

**Source:** part C (`03_testing_ci_debt.md`, costed recommendations 5.1–5.12, CI history up to run `45605002991`), plus parts A, B and D and s1v for what the tests missed. Roadmap items are in `12_stabilization_roadmap.md` (S1-5 and the test parts of S1-3 and S1-4).

## 1. Conclusion first

**The problem is where the tests point, not how many there are.**
- Mesh has 13,971 tests, but about 5% of the tests that gate a PR use a real window. 3,717 tests use a fake window with no real counterpart, and the whole suite has only 20 spec'd doubles.
- Every P1 that S1-0 found sat on a seam the tests skip:
  - event delivery;
  - removal;
  - room re-entry;
  - save/load across rooms;
  - Studio → runtime;
  - the project root.

**The proposal adds confidence where it is missing and removes duplicate work:**
- **Add about 30 real-runtime contract rows** (6 contracts), **1 end-to-end creator workflow test**, **1 template smoke** and **about 10 mutation-proven assertions**. That is roughly 60 tests, not thousands.
- **Make every gate fail closed**, put **floors** on every lane, and adopt a written **flake policy**.
- **Remove duplicate execution** (R1–R4) and rebalance shards.

**Net effect if everything here is approved:**

| Measure | Today | After S1 (all approved) | After S1 with D9 = no (B1 rebalancing still applied) |
|---|---|---|---|
| CI push wall, p90 | 15.7 min | ≈ 12–14 min | ≈ 15–15.7 min (meets E10 only because B1 splits Linux pytest; without B1, ≈ 16.7, **breaching E10**) |
| Extended push wall, p90 | 38.7 min | ≈ 35 min | ≈ 35 min (the e2e test is off the critical path) |
| Job-minutes per merge | ≈ 345 | ≈ 200–220 | ≈ 360 |
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
| **A8** | **E2E creator workflow test** (`e2e` marker, which has no users today): `mesh new` → Studio ops, `mesh author` and MCP authoring of every picker feature → `main.py` play with keys through `dispatch_event` → F5 → new process → F9 → export → exported play, save and reload. Promoted from `e2e_creation_to_export_chain.py` and the s1v scripts | The whole create → export chain (E3) | `extended`, both OSes | **+≈ 2–4 min per OS in job-min (estimate); 0 on Extended wall** (the `extended` job is 3–4.5 min against a 37 min gpu critical path) | 5.7 | no |
| **A9** | **Template smoke:** every `--template` id creates, starts, walks and draws | #656 class (E4) | `extended` | +≈ 1 min job-min; 0 wall | 5.7 | no |
| **G1** | **Gates fail closed:** mypy-island reads its returncode; "tooling unavailable" exits 2; silent missing-input steps report `skipped:` and CI fails on un-allow-listed skips | #624 C/D, the mypy-island probe | `verify` | +≈ 5 s | 5.1 | no |
| **G2** | **Baseline growth checked against the merge base**; the mypy count guard reads the committed baseline; RUF100 on | #624 B/C | `verify` | +≈ 5 s | 5.1 | no |
| **G3** | **Lane floors:** gpu 256 → about 600; Windows shard check `--min-selected` about 13,500; Linux JUnit plus a floor; a contract test keeps every floor within 5% of collection | #648 (E6) | all | ≈ 0 | 5.2 | no |
| **G4** | **Silent gaps:** `.[mcp]` in the Linux pytest job; delete `pyrightconfig.json`; replays print failing cases | #649 | `pytest`, `replays` | +≈ 10 s install | 5.4 | no |
| **R1** | **Fast tier once:** verify-all in CI's `verify` jobs runs with `MESH_SKIP_PYTEST_FAST=1`, because the pytest job already ran all 6,292 fast tests. The fast-tier timing budget moves to a report-only step fed from the pytest job's durations | duplicate execution | `verify` | **−≈ 3.6 job-min per run** (≈ −10 per merge); off the critical path | 5.8 | **D9** |
| **R2** | **Second verify-all out of the pytest job:** first measure the `verify_all_audit_artifacts` fixture (17 test files) with `--durations`. If it costs minutes, feed those audit tests the `verify` job's reports, or unit-test the audits on fixtures | duplicate execution on the critical path | `pytest` | **est. −1.5 to −3 min wall per OS** (measure before deciding) | 5.8 | **D9** |
| **R3** | Fold the `web-smoke` job into verify-all's identical steps, or the reverse | duplicate execution | CI | −≈ 0.5 job-min | 5.8 | D9 |
| **R4** | **Push-side dedup:** skip a push run's jobs only when a green PR run tested the **identical tree** (the merge commit's tree hash equals the tested merge ref's tree) at the same workflow revision, and link that run as evidence, as the #344 rule does. If the base moved, the trees differ and the run happens, which keeps the #600 + #601 combined-tree protection | the same tree tested twice | CI and Extended | **up to −58 (CI) and −104 (Extended) job-min per merge** when the PR was current (≈ −45% of per-merge cost) | 5.8 | **D9** |
| **B1** | **Rebalance the Windows gpu plan** from measured timings (shard 2/2 takes 37.2 min, shard 1/2 29.6); optionally 3 shards. Optionally shard Linux pytest in two | critical path | Extended, CI | Extended wall **−3 to −4 min** (balanced; ≈ −12 with 3 shards, +≈ 3 job-min); CI wall −1 to −2 min (+≈ 2 job-min) | 5.8 | no (no change to what runs) |
| **P1** | **Flake policy** (§5) and a quarantine mechanism | #612-class gate trust (E9) | all | ≈ 0 | 5.3 | **D10** |
| **P2** | **Lane budgets** in the existing report-only `timing rolling check`: pytest (ubuntu) p90 ≤ 15 min; Windows shards ≤ 13; verify ≤ 7; Extended wall ≤ 40. A PR adding > 30 s to a required lane names its offset or justification | slow growth | report-only | ≈ 0 | 5.8 | no |
| **C1** | **Retire document-shape tests:** the 24 `*_content_contract.py` files (246 tests) assert JSON values that nothing reads (#640). Replace them with one data-driven content check that loads each chapter in the real runtime for its key interactions, or rely on verify-all's content audit for shape | maintenance, false confidence | `pytest` | small − | 6.x / opportunistic | no |

**Sum of the additions to required lanes:**
- ≈ +55–60 s wall per OS (A2–A7, G1, G2, G4);
- offset by R2 (−1.5 to −3 min) and B1 (CI −1 to −2 min).

Without R2 or the Linux shard split, CI p90 rises by about 1 minute and E10 would need an offset, so B1's Linux split becomes mandatory.

## 4. Lane map after S1 (what runs where)

| Lane | Runs | Changes in S1 |
|---|---|---|
| `pytest` (required, every PR and push, both OSes) | default suite (`not slow and not e2e`) | + contracts A2–A7; + floor (G3); − in-suite verify-all if R2 approved; Linux possibly 2 shards (B1) |
| `verify` (required) | verify-all, release bundle, baseline diff | − fast tier (R1, if approved); gates fail closed (G1, G2) |
| `acceptance`, `installed`, `replays`, `arcade3-canary`, `web-smoke` | unchanged | `replays` prints failing cases (G4); `web-smoke` folded into verify-all (R3, if approved) |
| Extended `extended` (every push and dispatch) | `(slow or e2e) and not gl` | + e2e workflow (A8) + template smoke (A9); floor stays equal to the count |
| Extended `gpu` (2 shards per OS) | `gl` | rebalanced (B1); floor 256 → about 600 (G3) |
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
| E9 (flakes) | `docs/s1/evidence/fetch_ci_history.sh` + `ci_timing_analysis.py` (attempt-1 failures classified from logs) | each stage boundary |
| E10 (time, cost) | `ci_timing_analysis.py` (median, p90, job-min per merge over 30 runs) | each stage boundary |
| E11 (mutation) | `docs/s1/evidence/mutation_probe.py` + `mutation_run.sh` (one process at a time) | once at close |

## 8. What this proposal does not do

- It does not add thousands of tests, migrate all 3,717 fake-window tests at once, or chase a coverage percentage.
- It does not add physical-GPU CI (the gpu lane stays Mesa).
- It does not change performance budgets.
- It does not run full stress locally (the owner's CPU limit). Heavy validation stays in CI and Extended.
- It does not prove Studio's GUI. Agents may not run visible GUI automation, so the owner's hands-on acceptance (E12, D13) is the only GUI check.
