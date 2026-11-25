# S1-0 part C: do Mesh's tests protect the engine's behaviour? Portfolio, mutation probes, CI, M3/M4 debt

Checked against **`9d3580b9`** (`redesign/visual-editor`, after #633), on top of parts A (`docs/s1/01_audit_reconciliation.md`) and B (`docs/s1/02_contracts_lifecycle_coupling.md`). This is investigation only: no production code or test changed. CI history runs up to the #634 merge (`45605002991`, 2026-11-25).

**Method:**
- Local runs used `py -3.13` with `PYTHONPATH=<this worktree>`, one Python process at a time:
  - pytest collection;
  - 59 short targeted pytest runs for the mutation probes;
  - two small repro/probe scripts.
- The only exception: some probe test files (Studio ownership, MCP) start their own child Python, one at a time.
- No full suite, no verify-all, no stress run, no visible window.
- CI timing comes only from GitHub history:
  - `gh run list`, and `gh api .../runs/<id>/jobs?filter=all` (all attempts);
  - job logs read through `gh api .../jobs/<id>/logs`, to classify failures;
  - no artifact was downloaded.
- Every mutated module was copied back and SHA-256-checked after each mutant. `git diff --quiet` on `engine/` and `mesh_net/` was clean after every group, and is clean at commit.

**Classes:** CONFIRMED, ARCHITECTURAL RISK, SUSPECTED, KNOWN LIMITATION, HISTORICAL. **Severity:** part A's scale (P0 data loss or main-path crash … P3 latent, cosmetic or developer-only).

**Tracked, cited, not re-reported:** #612, #618–#624, #627, #631, #632, #636–#646.

### Evidence (`docs/s1/evidence/`)

| File | What | Result |
|---|---|---|
| `portfolio_plugin.py` | pytest plugin (`-p docs.s1.evidence.portfolio_plugin --collect-only`): lane markers per test, after the conftest hooks | `data/portfolio_by_file.csv` (1996 files) |
| `scan_test_portfolio.py` | static: kind of test double per file, joined to the CSV | `data/portfolio_summary.txt` |
| `mutation_probe.py` + `mutation_run.sh` | 40 hand-written mutants in 8 modules, plus survivors re-run against wider test sets; one Python process at a time | `data/mutation_results.jsonl` |
| `fetch_ci_history.sh` | runs and jobs (every attempt) for CI and Extended | `data/ci_runs.tsv` (275 runs), `data/ci_jobs.tsv` (3490 jobs) |
| `ci_timing_analysis.py` | medians, p90s, critical path, job-minutes, attempts | `data/ci_timing_report.txt` |
| `probe_gate_fail_open.py` | mypy-island with mypy unavailable | exit 1 (fails open) |
| `repro_drop_chance_zero.py` | `"chance": 0` in DropTable and in mesh_net's copy | exit 1 (NEW-11) |

---

## 1. Test portfolio

### 1.1 By lane

One `--collect-only` with addopts cleared collects **13,971 tests in 1,996 files**. Per-lane selections (each its own `--collect-only -m ...`):

| Lane (where it runs) | Selection | Tests | Floor (`min_selected`) | Notes |
|---|---|---|---|---|
| default suite (CI `pytest` jobs, every PR and push, both OSes) | `not slow and not e2e` | 13,792 | **none** | 621 of these are `gl` tests, which skip without `MESH_GL_SMOKE` (`default_skip` = 630) |
| fast tier (inside verify-all in CI's `verify` jobs; `tier0`) | `fast` | 6,292 | none | **all also run in the default suite** (§3.3) |
| `extended` (Extended workflow, every push + feature dispatch) | `(slow or e2e) and not gl`, minus the wheel test | 162 | 162 | the floor equals the count: tight |
| `gpu` (Extended, 2 shards per OS) | `gl` | 621 | **256** | the floor is 41% of the count (§3.4) |
| `acceptance` (CI, every PR, both OSes) | `gl` in 4 files | 23 | 22 | a subset of `gpu`, so it runs again on push |
| installed (CI) | `test_wheel_bundles_engine_data.py`, `--noconftest` | (one module) | — | |

Marker shares (a test can carry several):
- `fast` 6,292 (45.0%), `integration` 2,653 (19.0%), `slow` 179 (1.3%);
- **`e2e` 0**: the marker is defined but nothing uses it;
- `gl` 621 (4.4%), `gpu_hardware` 1;
- **unmarked 4,973 (35.6%)**: ratcheted by `tests/baselines/unmarked_test_nodeids.txt` (5,044 lines), so this cannot grow.

### 1.2 By kind of test double (`scan_test_portfolio.py`, regex per file, approximate)

| Kind of file | Files | Tests | Share of tests |
|---|---|---|---|
| Real window: constructs GameWindow, the headless editor, the worker processes or Studio processes, or holds a `gl` test | 146 | 1,298 | 9.3% |
| … of which only run outside the required `pytest` jobs (`gl`: Extended's gpu lane, plus 23 in acceptance) | — | 621 | 4.4% |
| Child processes (`subprocess` / `sys.executable`) | 109 | 1,497 | 10.7% |
| A fake window (MagicMock / Mock / SimpleNamespace window, or a hand-written `*Window*` class), **and no real window** | 423 | 3,717 | 26.6% |
| `unittest.mock`, any | 337 | 1,927 | 13.8% |
| … with any `spec=` / `spec_set=` / `autospec` | **12** | 58 | 0.4% |
| Static source scans (`ast.parse`, globbing `*.py`) | 54 | 593 | 4.2% |
| Plain (none of the above: data, pure functions, documents) | 1,149 | 7,325 | 52.4% |

Sites:
- 1,224 `MagicMock(`;
- 133 MagicMock/Mock windows, 327 SimpleNamespace windows and 165 fake `*Window*` classes;
- **20 spec'd doubles in the whole suite.**

No test constructs `engine.studio.Studio` in process with a real window. Studio is reached three ways:
- through child processes (`StudioProcess`, `StudioDriver`);
- through GL tests;
- or by calling Studio's unbound methods on a SimpleNamespace "self". For example, `tests/test_studio_canvas.py:16-25` calls `Studio._draw_canvas(fake)`.

**Reading.**
- About 680 non-GL real-window tests (≈5%) gate every PR. A fake-window test that has no real-window counterpart is about 5.5 times as common (3,717 tests).
- An unspec'd double accepts any attribute. So the fake-window class can bless an interface that production lacks, which is exactly what part B's §1 measured: 15 window attributes exist only on fakes.
- Coverage by count is high (14k tests), but it sits mostly at the unit/document level. The seams between the systems (event delivery, removal, room re-entry, save/load across rooms, Studio→runtime) are where parts A and B found every P1.

### 1.3 Case studies: the tests that existed for each defect, and why they passed

| Defect | Tests that existed | Why they passed | Pattern |
|---|---|---|---|
| #619 shop charges without granting | `tests/test_vendor_shop.py` (real `GameStateController` + `MeshEventBus` in a StubWindow) | Only the happy path and "not enough gold". No test made the inventory refuse | **missing negative branch** (not mocking). The mutants show the same gap remains: V1 (exact-price purchase refused), V2 (out-of-stock still sold) and V4 (selling an item you don't own pays) all survive the vendor tests |
| #620 "Only once" reward repeats | `test_project_ops_authoring.py` asserts the stored `talk["once"]`; `test_runtime_diagnose.py` uses `once: False` | Assertions on the **authored document** and on one visit. No test revisits a room or loads a save | document-level assertion; no lifecycle test. Mutant O4 (the toggle always stores True) even survives the document tests and the Studio/MCP tests |
| #622 A ActionListRunner inert | `test_action_list_integration.py`, an "integration" test with a `MagicMock()` window and MagicMock entities | It calls `action_runner.handle_event(...)` itself (lines 115, 166, 247, 355). The runtime delivers through `on_event` | **the test calls the method it assumes the runtime calls** |
| #622 B missing `find_sprite` | `test_cutscene.py:30-35` | `DummySceneController` *defines* `find_sprite`, which the real SceneController lacks | **the fake invents the API** |
| #636 RewardChest grants nothing | `test_puzzle_behaviours.py:50-62` | A MagicMock player whose `inventory.add_gold` is asserted to have been called | the fake invents the API |
| #637 removed entity keeps listening | `test_puzzle_subscription_lifecycle.py` | It calls `destroy()` directly, on MagicMock-window behaviours. The real-window removal tests cover only the 4 behaviours that have `on_destroy` | calls what the runtime never calls |
| #639 DoorLock still blocks | `test_puzzle_behaviours.py:36-46` | It asserts `door.locked` and the emitted event; a MagicMock entity silently accepts `properties["solid"] = False`. No collision/`solid_sprites` assertion | asserts internal state, not the creator-visible outcome |
| #640 TriggerZone ignores `on_trigger` | 30 files name TriggerZone; the 24 `*_content_contract.py` files (246 tests) assert e.g. `tz.get("on_trigger") == expected` (`test_act1_chapter3_slice.py:44`) | They assert that the scene JSON **contains** a value nothing ever reads. No real-window test of emission | document tests bless dead configuration |
| #641 legacy file ops use the CWD | 6 test files give a fake window `repo_root`; part A's #618 check used `SimpleNamespace(repo_root=...)` | The real window has no `repo_root`. The file-ops logic itself is well tested: **all 5 file-ops mutants are killed (§2)**, but only through a window that doesn't exist | the fake invents the API. High kill rate, wrong seam |
| #642 MCP cutscene breaks start-up | Cutscene tests drive `cutscene_runtime/runner.py` (the *other* cutscene runtime, part B D-4); MCP validation tests never touch `cutscenes.json` | No test writes through MCP and then constructs a GameWindow | parallel runtime; no cross-component smoke test |

Five patterns account for all ten defects:
1. **The fake invents the API** (#622 B, #636, #641). Spec'd fakes would have turned each of these into an AttributeError.
2. **The test calls the hook it assumes the runtime calls** (#622 A, #637).
3. **Internal state or the document is asserted, not the outcome** (#620, #639, #640).
4. **Missing negative branch** (#619).
5. **A parallel runtime is tested instead of the live one** (#642; part B D-3/D-4).

Patterns 1–3 are cheap to catch with a handful of real-runtime contract tests (§5.1). None needs more unit tests.

---

## 2. Mutation blindness (manual probes, 40 mutants, 8 modules)

**Procedure** (`mutation_run.sh`):
- one exact text replacement per mutant;
- the module's own test files, **with the default addopts (what CI's pytest job selects)**, `-x`, one process;
- a baseline run first: every group's baseline was green.

Survivors were then re-run against a wider set (every test file that names the module or its API) to separate "untested" from "tested elsewhere".

| Group (module) | Own test files (tests) | Killed / 5 | Survivors (own files) | Survivors after the wider set |
|---|---|---|---|---|
| save/load `engine/save_runtime/entity_state.py` | 6 (124) | 4 | S1 | S1 (not re-run) |
| project save `engine/project_save.py` | 4 (130) | **5** | — | — |
| inventory/vendor `engine/behaviours/vendor.py` | 3 (19) | 2 | V1, V2, V4 | (not re-run) |
| quests `engine/quest_runtime/progress.py` | 16 (118) | **1** | Q1, Q3, Q4, Q5 | **Q1, Q3, Q5** survive 69 files / 525 tests (`data/quests_wide_tests.txt`); Q4 killed by `test_savegame_snapshot.py` |
| entity lifecycle `engine/scene_controller_parts/entity_factory.py` | 6 (50) | **5** | — | — |
| Studio `engine/project_ops.py` | 3 (58) | 2 | O1, O3, O4 | **O1, O3, O4** survive 12 files / 194 tests, Studio process, MCP and AI tests included (`data/project_ops_wide_tests.txt`) |
| mesh_net `mesh_net/scene_room.py` | 2 (147) | 4 | N4 | N4 killed by `test_hd2d_same_level.py` |
| editor file ops `editor_file_ops_controller.py` | 6 (88) | **5** | — | — (but through fake windows: #641) |

**Kill rate:**
- 28/40 (70%) with the module's own files;
- 30/40 (75%) with the wider sets;
- by group, from 1/5 (quests) to 5/5 (project_save, entity_factory, file ops).

The strong groups are the ones remediation work hardened recently, with mutation proof (F3, B-05, #618/#628). The weak ones are older gameplay rules.

**Survivors that matter** (each is a hypothetical regression no test would notice; production is correct today):

| Mutant | What it breaks | Why it matters |
|---|---|---|
| **Q1** | a stage keyed on `payload_value` completes for any value (kill *wolf* = kill *boar*) | Silent wrong quest progress on every shipped quest that filters by payload. The 19 content-contract files only check the JSON |
| **Q3** | completing an already completed quest pays its reward again | A farmable reward (the #620 class) with no guard test |
| **Q5** | `complete_stage` completes a stage that is not the current one | Skips stages: the #621 class |
| **O3** | `set_solid(False)` can no longer make an object passable | The creator unticks "solid" in Studio and the object still blocks |
| **O4** | the conversation's "Only once" toggle always stores True | The authoring half of #620 is unguarded too |
| **O1** | `remove_entity` of an unknown id silently "succeeds" | An MCP/AI remove of a wrong id reports success |
| **V1 / V2 / V4** | exact-price purchase refused / out-of-stock still sold / selling an item you don't own pays gold | Economy rules beside #619, still untested after #625 (cf. #627's surviving mutant O5) |
| S1 | a load no longer writes the restored position into `mesh_entity_data` | Lower: what reads that dict after a load (editor, re-save) was not traced |

Every survivor needs one small, fast assertion (§5.4), not a new suite.

---

## 3. CI and Extended

### 3.1 Structure (`.github/workflows/ci.yml`, `extended.yml`, `.github/actions/mesh-ci-setup`)

**CI** (every PR and every push to the integration branch). Jobs:
- `pytest`: Linux whole; Windows as 2 module shards;
- `verify` ×2: verify-all + release bundle + strict bundle verify + baseline diff;
- `installed` ×2; `acceptance` ×2; `replays` (Linux); `arcade3-canary`; `web-smoke`;
- `tests (<os>)` fan-ins (`tooling/ci_require_jobs.py`; Windows also runs `tooling/ci_shards.py check`);
- `timing rolling check` (report only).

**Extended** (every push, nightly from main, dispatch, and PRs that touch the lane policy):
- `extended` ×2, and `gpu` as 2 shards per OS with a fan-in (`ci_shards.py check --min-selected 256`).

`dedup` (`tooling/extended_dedup.py`) skips only the #344 integration→main PR whose tree is the push-tested head's.

### 3.2 Timing (last 30 non-cancelled runs each; `data/ci_timing_report.txt`)

| Workflow / event | Wall, median / p90 (min) | Job-minutes per run, median | Critical path (completed last) |
|---|---|---|---|
| CI, push to the integration branch | **13.7 / 15.7** (max 30.6) | 58 | `tests (windows)` 23×, `tests (ubuntu)` 7× |
| CI, feature-branch PRs | 14.2 / 16.2 | 57 | same |
| Extended, push | **37.4 / 38.7** | 104 | `gpu (windows)` 15×, `gpu (ubuntu)` 15× |
| Extended, dispatched on feature branches | 36.2 / 38.8 | 108 | same |

Per job (CI push; minutes, median / p90):
- `pytest (ubuntu)` **13.1 / 15.0**;
- `pytest (windows) shard 1/2` 11.2 / 12.4, shard 2/2 11.0 / 13.0;
- `verify (windows)` 5.5 / 6.2, `verify (ubuntu)` 3.5 / 4.2;
- `installed (windows)` 3.1, `acceptance (windows)` 2.5;
- everything else is under 2.

Per job (Extended push):
- `gpu (windows) shard 2/2` **37.2 / 38.3**, shard 1/2 29.6 / 33.4;
- `gpu (ubuntu)` shards 17.2 / 16.3;
- `extended` 4.5 (Windows) and 3.2 (Linux).

**Queue time is negligible:** the median wait from job creation to start is 3 s for every job, and the p90 is ≤ 1 min (one 2.5 min p90 on feature-PR Linux pytest). The runs' wall time is run time: the critical path is
- CI: the Linux pytest job (13 min) or a Windows shard, plus the fan-in;
- Extended: the Windows gpu shard 2/2, 7.6 min longer than shard 1/2 (an unbalanced plan).

**Cost per merge** in the window (49 CI pushes, 82 feature-PR CI runs, 35 feature Extended dispatches): about 1.7 PR CI runs + 1 push CI run + 0.7–1 Extended dispatch + 1 Extended push. That is ≈ 1.7×57 + 58 + ~0.8×108 + 104 ≈ **345 job-minutes per merge**. When the PR is up to date with its base, the push runs re-test the PR's tree (§3.3, item R4).

### 3.3 Redundant execution

| # | What runs twice | Evidence | Cost per CI run | Class |
|---|---|---|---|---|
| R1 | **The fast tier, 6,292 tests**: the `pytest` job runs the whole default suite; the `verify` job's verify-all runs `tooling.pytest_fast` again | verify logs: pytest-fast took 95.8 / 85.4 / 99.6 s (Linux) and 122.2 / 114.9 / 116.3 s (Windows) on the last three pushes | **≈ 3.6 job-min** (off the critical path) | CONFIRMED |
| R2 | **A second verify-all inside the pytest job**: the `verify_all_audit_artifacts` fixture (`tests/_verify_all_audit.py`, 17 test files) runs `mesh verify-all` minus fast tier, demo, replays and asset doctor, so the mypy gate, both exception scans and every audit run in the pytest job too | `tests/conftest.py:226-231` | not measured (CI runs no `--durations`); about the verify job's non-pytest-fast time, ~1.5–3 min per OS, **on the critical path** | CONFIRMED (duplication); cost estimated |
| R3 | `web-smoke` job (build-web + headless runtime smoke + web structural smoke) vs verify-all's `web-smoke` and `runtime-player-smoke` steps in both `verify` jobs | `ci.yml:209-219`; `pipeline.py:965+`, `:825+` | ~0.5 job-min | CONFIRMED |
| R4 | **The same tree tested twice per merge**: the feature PR's CI (merge ref) and the push run of its merge commit; the feature-branch Extended dispatch and the Extended push | 82 PR runs and 35 dispatches against 49 pushes | up to ~58 (CI) + ~104 (Extended) job-min per merge when the base did not move | ARCHITECTURAL RISK (cost). The push run is deliberately "the result that counts" (it catches combined trees: #600 + #601) |
| R5 | `acceptance` (23 GL tests) runs in CI on every PR and push, and again inside Extended's gpu lane | `test_tiers.py` `ACCEPTANCE` ⊂ `gl` | ~1.5–2.5 job-min per Extended run | by design (cheap) |
| R6 | Wheel builds: `arcade3-canary` builds and installs a wheel; `installed` ×2 build theirs; the release bundle job builds another | `ci.yml:143-159`, `:668-675` | < 1 job-min each | minor |

### 3.4 Gate status (after #633; each re-checked at `9d3580b9`)

| Gate | Fails closed? | Evidence | Class / tracking |
|---|---|---|---|
| ruff-gate, tool missing | **yes** | part A re-ran it: exit 2 | HISTORICAL (#633) |
| mypy-gate, tool missing | **yes** | part A: exit 2 | HISTORICAL (#633) |
| **mypy-island**, mypy can't run | **no**: exit 0 "ok - 21 modules clean" | `probe_gate_fail_open.py` (exit 1). `tooling/mypy_island.py:148-159` collects lines containing `" error: "` and never reads `returncode`. Inside verify-all this is masked: mypy-gate fails first and the later steps are skipped. Standalone it is open | CONFIRMED (#624 phase B list), P3 |
| "tooling package unavailable" → code 0 | **no** | `pipeline.py:422-424` (mypy-gate), `:466-468` (baseline guard), `:492-494` (ruff), `:518-520` (island), `:597-599`, `:725-727`, `:757-759` (pytest-fast). Reachable only without `tooling/` (an installed wheel running verify-all) | CONFIRMED (#624), P3 |
| mypy-baseline-guard | **no-op in CI** | `pipeline.py:451-457`: `.mesh/` is git-ignored, so with no count file `previous_count = current_count` | CONFIRMED (#624 B) |
| Baselines can grow unchecked | **yes, they can** | `tooling/ruff_baseline.txt` (926 lines), `mypy_baseline.txt` (75), `exception_policy_baseline.json`: `ruff_gate --update-baseline` rewrites the file and the same PR passes; only mypy has a growth guard (the no-op above). `tests/baselines/unmarked_test_nodeids.txt` is ratcheted by `test_tier_marker_ratchet.py` | CONFIRMED (#624 C) |
| RUF100 (unused `noqa`) | **off** | `pyproject.toml:305-307` selects `E, F, I, W` only. 2,355 `noqa` comments in engine/mesh_cli/mesh_net/tooling go unchecked, most naming rules that aren't enabled (`BLE001`, `PLC0415`, …) | CONFIRMED (#624 list) |
| Steps that pass when their input is missing, with an empty error (indistinguishable from a pass) | **no** | `player-package-gate` (`pipeline.py:897-899`: no `scenes/runtime_smoke_scene.json`), `runtime-player-smoke` (`:872-874`: no smoke scene), `perf-baseline-compare` (`:1088-1090`: no scene set or baseline), `content-audit` (`:2327-2329`: no content roots). Labelled skips with code 0: `verify-demo` (no arcade), `web-smoke` (three reasons, `:979-987`), `pytest-fast` (under pytest, or `MESH_SKIP_PYTEST_FAST=1`) | CONFIRMED (#624 D) |
| Timing budgets (`pytest-fast` over its threshold) | report-only up to a hard ceiling (fails over 130.4 s) | verify log 45605002991 | by design (#422 F13) |
| **Lane floors** | partly | `extended` 162 = actual 162; `acceptance` 22 vs actual 23; **`gpu` 256 vs actual 621** (59% of GL tests could vanish and the lane stays green); **the default suite has no floor**: Linux `pytest -q` fails only at 0 tests (exit 5), and the Windows `ci_shards.py check` runs with `--min-selected 0` (`ci.yml:827`; `ci_shards.py:298`), checking the shards against what they collected, not against a count. `-m fast` collection skips modules without the bytes "fast" (`conftest.py:244-255`), contract-checked by `fast_tests_outside_rule` | **CONFIRMED, NEW-13** (P2 safeguard) |
| pyright | **configured, never run** | `pyrightconfig.json` (2026-02, `db86a6cb`; `venv: .venv`; **`mesh_net` not in `include`**); `git grep pyright` in `.github`, `tooling`, `mesh_cli` finds nothing | CONFIRMED, P3 (NEW-14) |
| **MCP-present test** | **always skips in CI** | `tests/test_mcp_server_tools_contract.py:336-342` skips when `server.HAS_MCP` is false; every CI job installs `.[dev]`, which lacks `mcp` (`pyproject.toml:20-34`); the runtime `pytest.skip` is invisible to the `never_runs` contract, which sees only markers. So `build_server()` with the real FastMCP (tool registration) is never exercised in CI | CONFIRMED, P3 (NEW-14) |
| `replays` job | fails closed, but blind | `--quiet` (`ci.yml:777`): the 2026-11-22 failures logged only "the replay suite failed (exit 1)", with no case name or reason (the reason is in the artifact) | CONFIRMED observability gap (NEW-14) |
| `timing rolling check`, PR-comment steps | `continue-on-error` | reporting only | by design |

### 3.5 Flaky tests (attempt-1 failures unrelated to the change)

Classified from the logs of every attempt-1 failure in the window (`data/ci_jobs.tsv`):

| Failure | Runs | Branches | Class |
|---|---|---|---|
| `test_replay_tick_sample_pooling.py::test_ep05_pools_enough_samples_and_passes_budget` (tick_ms_max 884.6 ms against a 150 ms limit, Windows) | 4: 45374348407, 45448769012, 45571127783, **45585825244 (push, #628 merge)** | 3 feature + 1 push; **two after #614** (merged 11-24 19:11) | KNOWN: #612 |
| `replays (ubuntu)` job, exit 1, cause not in the log (`--quiet`) | 2: **45028645649 (push)**, 45032020671 | both 2026-11-22, both green on attempt 2 | **SUSPECTED flake** (likely a Linux time budget; NEW-14) |
| `test_ai_write_paths.py::test_studio_and_a_plan_starting_at_once_never_both_have_the_project` (Windows: "An outside tool is writing this project's files right now") | 1: 44994370624 | feature, green on attempt 2 | **SUSPECTED flake**: a race in an ownership-race test (NEW-15) |
| `test_mesh_net_hd2d_gpu.py` deck tests ("not settled after 12 legs"; no looting / door through the deck) | 2: 45181132747 (dispatch), 45202555678 (PR) | feature branches during M3 acceptance and #605, next runs green after changes | not classifiable from the logs (development or a merge interaction); watch |
| Windows terrain frame flake (#508 note) | 0 in 35 Extended pushes | — | KNOWN, not seen in this window |

The rest of the 22 feature-PR failures were real (mypy-gate, a contract test catching a new pattern, a 75.8 ms proxy timing bug that #617 fixed, #622 work in progress).

**Flake rate:**
- **CI, integration-branch pushes:** 2 of 49 runs hit a non-change failure on attempt 1 (**4.1%**). One was ep05/#612, one the replays job.
- **Feature PR CI:** 5 of 82 (**6.1%**). Three were ep05, one replays, one the ownership race.
- **Combined:** ≈ 5% of CI runs. ep05 alone causes 4 of the 7.
- **Extended pushes:** 0 of 35.
- **Re-runs:** only 3 runs in the window used a second attempt. The push failure 45585825244 was not re-run; the next merge's run was the evidence.

---

## 4. M3/M4 technical debt (online/mesh_net foundations N6–N8, M4-0..M4-6)

Sources: `docs/plans/m4_checkpoint.md` §3–§4, `docs/plans/m4_online_combat.md` §4 and §6, issue #496, the #630/#634 reviews (memory notes), #627, and the mesh_net code.

| # | Item | Where | Class | Notes / cost to carry |
|---|---|---|---|---|
| D1 | Three input-queue presets kept until the owner chooses (`drain` provisional; `deep`, `small`; plus `--input-depth/hold/drain` flags and `MESH_NET_QUEUE*` env) | `mesh_net/scene_room.py:133-140`, `server.py:274-330` | KNOWN LIMITATION (owner decision OD11; none of the three meets every criterion) | Three code paths and three measurement columns until decided. Remove two presets and their knobs once the owner plays the demo |
| D2 | Greedy-liar burst: the 600 ms claim window (13 attacks on consecutive ticks at cooldown 2; 2 at the co-op room's 10) | `test_mesh_net_combat.py::test_a_lying_client_gains_one_caps_worth_at_most` | KNOWN LIMITATION (before any public deployment) | Mitigation named, not built: a shorter window and a per-player rate check |
| D3 | `view_tick` bound: any pose in the last 300 ms (+31% / +52% reach on the bandit; ~8 px elevation on stairs) | M4-5 | KNOWN LIMITATION (PvE only, never PvP as built) | Bound by each client's measured delay before deployment |
| D4 | hd2d enemy/route parity: `FloorRoute` stands one update per waypoint, so 70 px/s authored walks 52 px/s online against ~64 in single-player | M4-4 | KNOWN LIMITATION (owner decision: fixing it changes single-player traces) | Movement and route are shared and parity-tested (`test_hd2d_net_parity.py:380,405`); the *timing* is not |
| D5 | The M4 demo world is built from repository files at run time: `tooling/m4_demo_world.files()` imports `tooling/hd2d_floors_demo.py` by pushing `tooling/` onto `sys.path` (`m4_latency_probe.py:316-320`) and composes the crossing, expedition and co-op files | `tooling/m4_demo_world.py:57+`; `tests/test_m4_demo_world.py` imports `tooling` | ARCHITECTURAL RISK | `tooling` is not in the wheel (`pyproject.toml:58` packages `engine*`, `mesh_cli*`, `mesh_net*`), so the playable demo needs a source checkout, and a test depends on tooling internals. Package the demo world as data (as `mesh_net/coop` and `mesh_net/expedition` are) |
| D6 | Probe/proxy duplication | `tooling/m4_latency_probe.py`, `tooling/net_delay_proxy.py`, `tooling/net_world_probe.py` | **HISTORICAL** for the link model: M4-6 moved `Link` into the proxy and the probe imports it (plan §4 M4-6). ARCHITECTURAL RISK for the rest | The probe drives `mesh_net.demo.Arena` (shared). The remaining duplication is world assembly (D5) and two probe windows' command handling (`net_world_probe.py`) |
| D7 | **mesh_net re-implements engine rules** | `scene_room.py` | ARCHITECTURAL RISK; one CONFIRMED consequence (NEW-11) | **Shared and parity-tested:** movement step, `FloorRoute`, `same_level`, the combat model (`resolve_attack`), physics. **Copied, not guarded:** (a) DoorLock/SwitchInteract as the lever/gate rule (`_use`, `locked`, `:958-983`; part B D-7: the net gate opens for good, the engine door stays solid, #639); (b) interaction selection, an inline copy of `engine.interaction.select_interaction_candidate`'s ranking (`:959-981`, "priority, facing, distance, then id"); (c) DropTable's normalisation and roll (`roll_drops`, `:1048-1068`, "the same normalisation, random stream and draws"), **which copied the `chance: 0` bug (NEW-11)** |
| D8 | TCP head-of-line blocking; the delay proxy is chunk-level with a per-message loss model; rendered evidence is one run per cell; the simulation has no phase drift | checkpoint §4 | KNOWN LIMITATION | A real-network check is owed before promising action-game feel |
| D9 | Owed tests from reviews | — | KNOWN, owed | **#630 (M4-6):** L03 (reversal-after-send order; a surviving mutant) and L04 (aim anchor after the avatar moved). **#634:** asserts for X4 (slowest ms == `tick_ms_max`) and X5 (gc generation crediting), plus the PR-body note on gc-callback overhead. **#627 (from #625):** `vendor.py:107/116` `str(item_id)` consistency, and a non-stackable item with `max_stack > 1` test (surviving mutant O5) |
| D10 | N8 follow-ups (#496): items cannot be removed; a copy of a store could grant loot again; disconnected party members get no loot; a window must rejoin after a restart; the test-only `fault` hook in `CharacterStore`; no migration path beyond schema 1 | `mesh_net/characters.py`, `persistence.py` | KNOWN LIMITATION (#496 open; item 1, owed unlocks, done in #510) | — |
| D11 | Part B D-3: the episode harness runs a MagicMock window with a GameplayEventBus, so the "integration" episodes take the other event route | `mesh_cli/episode.py:563-573` | ARCHITECTURAL RISK (part B) | Listed here because the M3/M4 replay and episode goldens rely on it |
| D12 | TODO/FIXME scan of `mesh_net/` and the M4 tooling | — | none found | The only markers are the "provisional" queue default (D1) |

---

## 5. Recommendations: more confidence without a longer suite

Estimated CI effect per run: + adds runtime, − saves. "Wall" is the critical path; "job-min" is runner cost.

| # | Change | Expected effect | Cost | CI-minute impact |
|---|---|---|---|---|
| **5.1** | **Five real-runtime contract pieces** (part B §1.6): (1) one shared hidden real-window fixture with `interact`, `frames`, `revisit` and `save_load` helpers; (2) one parametrised "picker behaviour" contract over `behaviour_guide.GUIDES` (~15 rows: author through `project_ops` → load → drive → assert the creator-visible outcome → revisit and save/load); (3) one removal contract over the 12 behaviours that subscribe in `__init__`; (4) spec'd fakes plus the meta-test from `contract_gaps_real_window.py`; (5) two cross-component smokes (cutscene step on the real SceneController; MCP cutscene write → GameWindow) | Catches patterns 1–3 of §1.3, which covers 9 of the 10 case-study defects and NEW-5/6/8 | ~1–2 PRs of test code; no production change | The real-window tests in `entity_factory` run 50 in 20 s, so ~0.4 s each: ~15 rows × ~2 s + ~12 × 0.5 s + smokes ≈ **+45–60 s per OS** on the pytest job (the critical path on Linux, unless placed in the Windows shards or offset by 5.6) |
| **5.2** | **Spec'd fakes**: a `fake_window()` built from a manifest of the real window's attributes (generated from a real hidden window by the meta-test, which fails when it drifts), and `spec=` on entity/interactor MagicMocks. Migrate the 133 MagicMock and 327 SimpleNamespace windows as files are touched, starting with the case-study files | A fake can no longer offer what production lacks (#622 B, #636, #641, NEW-8) | one helper + meta-test; then incremental | ≈ 0 |
| **5.3** | **Fail-closed gates** (all small): mypy-island reads its return code; "tooling unavailable" is code 2 in CI (or the CI step asserts no `skipped:` steps); the four silent "input missing" steps report `skipped:` and CI fails on any; the mypy baseline guard compares against the merge base's `tooling/mypy_baseline.txt` instead of `.mesh/`; a CI check that no baseline file grew without a `baseline-growth:` line in the PR; enable RUF100 with `lint.external` for the documentation-only codes; delete `pyrightconfig.json` or run pyright (I'd delete it: nothing runs it and it excludes mesh_net) | Closes #624 B/C/D and the items in §3.4 | one PR each; most under 30 lines | ≈ 0 (+5 s) |
| **5.4** | **Minimum selected-count guards**: `gpu` `min_selected` 256 → ~600 (`test_tiers.py:83`, `extended.yml` `--min-selected`); pass `--min-selected` (e.g. 13,500) to the Windows shards' check; give the Linux pytest job `--junitxml` and the same floor (via `test_tiers.lane_problems`, which exists) | A marker, conftest or rule change that silently drops tests turns red | ~20 lines | ≈ 0 |
| **5.5** | **Targeted tests for the mutation survivors** Q1, Q3, Q5, O1, O3, O4, V1, V2, V4 (and S1 after tracing its readers); keep `mutation_probe.py`'s table as the proof (each new test must kill its mutant) | Closes the measured blind spots in quests, Studio ops and the economy | ~10 small tests | **< 2 s** |
| **5.6** | **Remove duplicate execution**: (a) R1: run verify-all with `MESH_SKIP_PYTEST_FAST=1` in CI's `verify` jobs, since the pytest job already ran every fast test. Keep the fast-tier timing budget as a separate report-only step on push, or feed it from the pytest job's durations. (b) R2: measure the in-suite verify-all fixture with `--durations`; if it is minutes, give the 17 audit tests the verify job's reports instead (or unit-test the audits on fixtures) and drop the second verify-all from the critical path. (c) R3: fold the `web-smoke` job into verify-all's steps (or the reverse) | Same evidence, less work | 1 PR each | (a) **−3.6 job-min/run**, ≈ −10 job-min/merge; (b) est. **−1.5 to −3 min wall per OS**; (c) −0.5 job-min |
| **5.7** | **R4 dedup on push**: extend `tooling/extended_dedup.py` to the push side. Skip a push run's jobs only when a green PR run tested **the identical tree** (tree hash of the merge commit == the PR merge ref's tested tree) at the same workflow revision, and link that run as evidence, exactly as the #344 rule does. Any doubt and the run goes ahead | Keeps the combined-tree protection (base moved → trees differ → the run happens) | 1 PR (the pattern exists) | up to **−58 (CI) and −104 (Extended) job-min per merge** when the PR was current: ≈ −45% of per-merge cost |
| **5.8** | **Lane rebalancing**: re-split the Windows gpu plan (shard 2/2 37.2 min vs 1/2 29.6) from the measured timings; optionally 3 Windows gpu shards. Shard the Linux pytest job in two (it is CI's critical path at 13.1 min, against 11–12 per Windows shard) | Shorter feedback, same tests | `ci_shards.py` plan edits | Extended wall −3 to −4 min (balanced) or ≈ −12 min (3 shards, +~3 job-min setup); CI wall ≈ −1 to −2 min (+~2 job-min setup) |
| **5.9** | **Flake policy (never weaken):** a failing-but-flaky test is never loosened, retried silently or skipped. It may be quarantined only by (1) an open issue with the evidence, (2) a `quarantine` entry in a committed baseline file naming the issue and an expiry date, (3) moving to an Extended `quarantine` lane that still runs and reports it, (4) a contract test that fails on an expired or issue-less entry (as `never_runs.txt` does). Required lanes keep `-W error`; re-run attempts stay a manual decision, recorded in the PR | Keeps the required gate honest; ep05 (#612), the replays job and the ownership race become visible, tracked items | 1 PR (marker, baseline, contract test) | ≈ 0 |
| **5.10** | **Runtime budgets per lane**, read by the existing `timing rolling check` (report-only today): pytest (ubuntu) p90 ≤ 15 min, Windows shards p90 ≤ 13, verify ≤ 7, Extended wall p90 ≤ 40. Plus a rule: a PR adding > 30 s to a required lane names its offset (5.6/5.8) or its justification | Stops slow growth without blocking real tests | doc + thresholds in `tooling/metrics` | ≈ 0 |
| **5.11** | **Merge or retire document-shape tests**: the 24 `*_content_contract.py` files (246 tests) assert authored JSON values (#640 showed they bless configuration nothing reads). Replace them with one data-driven content contract that loads each chapter in the real runtime for its key interactions, or rely on verify-all's content audit for shape | Less code to maintain, assertions on outcomes | 1–2 PRs | small (−) |
| **5.12** | **Small coverage fixes**: install `.[mcp]` in one CI job (the Linux pytest job) so `test_server_build_succeeds_when_mcp_present` runs; drop `--quiet` from the `replays` job, or print the failing cases on failure | MCP tool registration tested; replay failures diagnosable | 2 lines each | +~10 s install |

**Net effect if 5.1–5.8 land together:**
- Required CI wall goes from ~14 min to ≈ 12–13 min (+1 min of contract tests, −1.5–3 min for R2, −1–2 min from sharding).
- Per-merge cost goes from ≈ 345 job-min to ≈ 200 (5.7 and 5.6a dominate).
- Confidence comes from about 30 real-runtime contract rows and about 10 mutation-proven assertions, not from thousands of new tests.

---

## 6. New confirmed defects (issue-ready)

### NEW-11 (P3): a drop with `"chance": 0` always drops (engine DropTable and mesh_net's copy)

- **Title:** DropTable reads `chance: 0` as "unset" and drops every time (`float(x or 1.0)`); `min_quantity: 0` becomes 1; mesh_net's `roll_drops` copied the rule.
- **Severity:** P3. A wrong outcome on a Studio-editable field (DropTable's "drops" list in the picker, `behaviour_guide.py:121`). No shipped content uses a 0 chance (scan: only positive chances).
- **Evidence:** `docs/s1/evidence/repro_drop_chance_zero.py` exits 1. It uses the real DropTable instance and its real roll, 200 seeded rolls each:
  ```
  chance     0: engine DropTable dropped 200/200 | mesh_net roll_drops dropped 200/200
  chance  -0.5: engine DropTable dropped   0/200 | mesh_net roll_drops dropped   0/200
  normalised entry for chance 0, min_quantity 0: {... 'chance': 1.0, 'min_quantity': 1, ...}
  ```
- **Root cause:** `engine/behaviours/drop_table.py:62-63` and `mesh_net/scene_room.py:1059-1060` (`float(entry.get("chance", 1.0) or 1.0)`, `int(... or 1)`). `_roll`'s `chance <= 0.0` branch (`drop_table.py:101`) is reachable only by a negative chance.
- **Fix:**
  - default only when the key is missing or None (`1.0 if v is None else float(v)`), the same for the quantities;
  - make mesh_net call the engine's normalisation instead of a copy (part of D7).
- **Regression:**
  - chance 0 never drops, in both runtimes;
  - a parity test asserting both use one function;
  - mutation proof (restore `or 1.0`).

### NEW-13 (P2, CI safeguard): lane selection floors are missing or loose

- **Title:** The default suite has no minimum test count on either OS, and the gpu lane's floor (256) is 41% of its selection (621). A conftest, marker or collection change can drop most tests and stay green.
- **Evidence:** §1.1 and §3.4:
  - collection counts 13,792 / 621;
  - `ci.yml:286` (`pytest -q`, no floor);
  - `ci.yml:827` and `ci_shards.py:298` (`--min-selected` defaults to 0);
  - `test_tiers.py:83` and `extended.yml` (`--min-selected 256`).
- **Root cause:** the floors were set when lanes were created (#422 H6) and not raised as tests grew. The default suite never had one.
- **Fix:** see 5.4. Raise `gpu` to just under the measured count, and add floors to the Windows shard check and the Linux pytest job. "Lower it only on purpose" is already the documented rule (`test_tiers.py:56-58`).
- **Regression:** a unit test of `lane_problems` / `ci_shards.check` with a selection under the floor; a contract test that each floor is within 5% of the current collection.

### NEW-14 (P3, CI coverage/observability): three silent CI gaps

1. **The MCP SDK path is never tested in CI.** `test_server_build_succeeds_when_mcp_present` always skips, because CI installs `.[dev]` without `mcp`, and the `never_runs` contract cannot see runtime skips. Fix: install `.[mcp]` in one job. Regression: the test runs (not skipped) in that job's report.
2. **pyright is configured but never run**, and its config excludes `mesh_net`. Fix: delete `pyrightconfig.json` (or run it).
3. **The `replays` job's `--quiet` hides which case failed:** the two 2026-11-22 failures show only "exit 1". Fix: print failing cases on failure.

### NEW-15 (SUSPECTED flake, track only)

- **Test:** `tests/test_ai_write_paths.py::test_studio_and_a_plan_starting_at_once_never_both_have_the_project`.
- **Evidence:** it failed once on Windows (run 44994370624, attempt 1, shard 1/2) with "An outside tool is writing this project's files right now. Try again in a moment.", and was green on attempt 2.
- **Severity:** none observed for users. A racing-start test can see the other contender's lock window.
- **Action:** quarantine per 5.9 only if it recurs. Investigate whether the test's "starting at once" assumption needs a retry-until-owned or a deterministic barrier.

### Also worth an issue (not defects): mutation-survivor test gaps

One issue listing Q1, Q3, Q5, O1, O3, O4, V1, V2 and V4 with their mutant texts (`mutation_probe.py`), each to be killed by one new assertion (5.5).

### Verified only (already tracked, so not re-filed)

mypy-island fail-open, "tooling unavailable" = 0, the mypy baseline guard, baseline growth, RUF100, and the silent "input missing" steps (all #624); ep05 (#612).

---

## 7. What I could not check

- **Per-test durations in CI:** CI's pytest jobs run without `--durations` or JUnit on Linux. So the in-suite verify-all fixture (R2) and the source-scan tests' cost are estimated, not measured. I did not download artifacts (Windows shard JUnit files exist there).
- **Mutation scope:**
  - 40 mutants is a probe, not a mutation score;
  - the vendor survivors (V1, V2, V4) and S1 were not re-run against a wider set (the shop panel tests, for example);
  - quests and project_ops were.
- **Whether the five patterns in §1.3 hold beyond the ten case studies:** the counts in §1.2 are regex-based, and "real window" counts a file as real when any of its tests is.
- **Flakes:**
  - logs older than the window (about 3 days, 275 runs) were not read;
  - the replays-job cause is not in the logs;
  - the `test_mesh_net_hd2d_gpu.py` deck failures could not be classified from the logs.
- **Billing:** whether Windows minutes are billed at a multiplier for this repository is not known, so job-minutes are raw.
- **D4/D8 network behaviour:** taken from the M4 documents; not re-measured.
- **R4 dedup safety:** that the PR merge-ref tree equals the pushed merge commit's tree when the base did not move was reasoned from GitHub's merge semantics, not verified on a sample of runs.
- **The legacy, Studio and real-key paths for the survivors (O3 in the Studio inspector, for example):** not driven, by rule (no visible automation).
