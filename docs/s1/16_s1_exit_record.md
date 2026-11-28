# S1 exit record

**S1 is complete.** It closed on 2026-11-27 at integration commit `4e937002`, as a risk-based exit the owner approved.

- **Met:** E1–E8 and E11.
- **Owner exceptions:** E9 and E10. Their observation windows were incomplete (tracked in #736).
- **E12:** accepted by the owner.

Stabilization work stops here. Any remaining debt goes to the normal backlog (§4). M5 and M6 do not start automatically.

## 1. Exit criteria at `4e937002`

The criteria are defined in [12_stabilization_roadmap.md](12_stabilization_roadmap.md) §9.

| # | Criterion | Result | Evidence |
|---|---|---|---|
| E1 | No unresolved confirmed P0 | **Met** | No P0 is open. Export launches keep F4 and the state-changing debug keys inert (`test_legacy_editor_gate_real_window.py`, `test_dev_tools_gate_real_window.py`, `test_debug_keys_dev_launch_real_window.py`) |
| E2 | Every confirmed P1 fixed or dispositioned | **Met** | Every P1 in the appendix is closed by a merged PR. #621 and #653 were reclassified as P2 under D2. No P1 was opened during S1 |
| E3 | Critical end-to-end workflow | **Met** | `test_e2e_creator_workflow.py` (the non-GL chain plus the HD-2D leg) has no xfail or workaround steps. It was green on 18 consecutive executed Extended pushes (45799704953 → 45910493844) at the exit audit |
| E4 | Every listed template starts | **Met** | There is a template smoke test for each `list_templates()` id, plus the GL draw |
| E5 | Gates fail closed | **Met** | Every gate in §3.4 has a test with its tool absent, and an un-allow-listed `skipped:` step fails CI. Baseline growth, including new report-only ceiling keys, needs a `baseline-growth:` commit line. `MESH_REQUIRE_MCP=1` is set on Linux |
| E6 | Lane floors | **Met** | Default suite: 13,600 floor vs 14,234 collected on both OSes. gpu: 605 floor vs 625. extended: 189 vs 189. acceptance: 22 vs 23. A 5% band contract test enforces them |
| E7 | No known destructive filesystem or save-data problem | **Met** | #623, #631, #632, #641, #642 and #660 are closed. The bugs S1 found are fixed: #665 (#715), #675 (#716, #717) and #721 (#722). Re-running the part A §3 sweep found no confirmed row (#718). #390 is excluded by owner disposition under D1 (b) |
| E8 | Runtime coverage of the 6 high-risk contracts | **Met** | Contracts 1–6 run as real-window tests in the default suite (#708, #709). The fake-only-attribute meta-test passes (#712), and each allow-list entry cites #705, #706 or #646. Picker contract: `BROKEN = {}` |
| E9 | CI is reliable | **Owner exception** | §2 |
| E10 | CI and Extended stay manageable | **Owner exception** (CI p90 only) | §2 |
| E11 | Measured blind spots closed | **Met** | Each of the 9 #650 mutants is killed by its named test (#698) |
| E12 | Owner hands-on acceptance | **Accepted** | §3 |

## 2. E9 and E10: owner exceptions

The owner chose not to wait for the rolling windows. Counts include only executed push runs on `redesign/visual-editor`. Nothing was rerun.

### E9: attempt-1 failures not caused by the change

The limits are at most 2% of the last 50 CI runs, and 0 of the last 30 Extended runs.

| Lane | Count | Runs | Cause and fix | When it leaves the window |
|---|---|---|---|---|
| CI | **2 / 50 (4.0%)** | 45585825244 | ep05 replay tick budget (#612, fixed by #661) | 2nd CI push after 45945815996 |
| | | 45901129489 | The MCP ownership race test expected `studio_open`, but a starting Studio safely refused with `studio_session_uncertain` (#724, test-only fix #725) | 40th CI push after 45945815996 |
| Extended | **1 / 30** | 45917533138 | Real mesh_net defect: a server stall over 3 s used up every session's input budget (#727). Fixed by #728, which adds a capped stall credit | 24th Extended push after 45945815934 |

**Uncertainty:**
- Each failure was judged unrelated from its diff and the next green push, and each has a merged fix.
- Small samples: one more unrelated failure within the next 40 CI or 24 Extended pushes would keep E9 over its limit.

### E10: wall time and cost

These are the last 30 executed push runs, covering both shard plans.

| Measure | Value | Limit | Met? |
|---|---|---|---|
| CI push p90 | 21.0 min (median 15.6; 14 of 30 over 16) | ≤ 16 | no |
| Extended push p90 | 38.5 min | ≤ 40 | yes |
| Job-min per merge (part C's run mix) | ≈ 367 | ≤ 390 | yes |

Since #726 split Windows pytest into three shards, over 7 runs:
- CI push p90 is 11.7 min (median 11.4). The one run over 16 min waited 4.3 min for a runner.
- Extended push p90 is 25.3 min.
- Job-min per merge is about 373.

**Uncertainty:**
- 7 runs are too few to establish a p90.
- Runner queueing is the remaining risk.
- If CI runs stay at 16 min or under, the 30-run window clears after about 17 more CI pushes.

### Conditions attached by the owner

- Keep measuring E9 and E10 during normal development.
- **No cosmetic commits, redundant PRs or artificial workflow runs** to manufacture passing statistics.
- Keep every existing CI gate and regression test.
- Investigate any new unrelated attempt-1 failure as before.

## 3. E12: owner acceptance

The instructions given to the owner covered:
- creating a Starter Room project in the Studio launcher;
- authoring the E3 items A–K with the behaviour picker;
- playing through `main.py`;
- saving with F5, restarting and loading with F9;
- running `mesh_cli export build` and playing the export.

These ran against a clean checkout of `4e937002`. **The owner accepted E12 on 2026-11-27.** The record shows that the full eight-row checklist was not completed and logged. Acceptance was the owner's call, as §9 allows.

Bug found during the session: running `export build` outside a project reports OK and writes an empty `dist/bundle` into the current folder (#737, P2, backlog).

## 4. Carried into the normal backlog

None of these block anything. They keep their roadmap references, and their severity stays as recorded on each issue.

| Issue | Summary | Roadmap ref |
|---|---|---|
| #737 | `export build` outside a project reports OK (P2) | — (found at E12) |
| #390 | Saves embed whole-room settings, which go stale after edits | E7 exclusion, D1 (b) |
| #621 | One event completes two quest stages that share a trigger (P2) | 6.1 |
| #644 | Developer console `quest`/`rules` commands fail against real objects (P2) | 6.1 |
| #645 | Legacy main menu Continue reads a save that no game writes (P2) | 6.6 |
| #627 | Granted items are lost when the inventory is full (P2) | 4.4 |
| #653 | Flag-gated entities only spawn at room load (P2) | 6.7 |
| #658 | Shipped solid gates can be walked round; absolute source path stored (P2/P3) | 7.3 |
| #647 | A drop with chance 0 always drops (P3) | 6.5 |
| #646 | Runtime attributes that only test fakes provide (P3) | 7.1 |
| #663 | Shop, talk and `require_flags` P3 bundle | 7.2 |
| #718 | P3 data-integrity risks from the sweep re-run | 7.4 |
| #719 | Process-wide caches survive a project switch (P3) | — |
| #659 | Question: GC hitches in long sessions | deferred; measure after S1 |
| #702, #714, #705, #706 | Hardening of the quarantine contract and the fake-window meta-test (P3) | 5.3 / E8 follow-ups |
| #735 | Review follow-ups from #731 and #732 | — |
| #701 | Watch item: replays job failed twice on 2026-11-22 | — |
| #672, #680, #683, #685, #496 | Earlier P2/P3 follow-ups that S1 left open | — |

These were not required for exit, and they move to the backlog with the items above:
- **S1-6:** bounded convergence of duplicate runtimes.
- **S1-7:** optional P3 cleanup, including 7.6 RUF100.
- **5.8:** R4 push/PR dedup. It was not built because linked PR runs (p90 ≈ 25.5 min) would have counted against E10 under the counting rule.
