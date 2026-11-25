# S1-0 Technical Debt and Architecture Health Report

**Baseline:** parts A–D were checked at `9d3580b9` (`redesign/visual-editor`, after #633). The integration tip is now `7b2b884e`, which adds only #634, a report-only replay diagnostic. #660 was reproduced at `7b2b884e`.

**Inputs:**
- this branch's parts A–D and their evidence, including the generated-project verification in `evidence/s1v/`;
- the owner-supplied independent audit in draft PR #629;
- the coordinator's triage (`audit/deep-audit-triage`);
- every issue comment, including the independent challenge review and the s1v verification.

This synthesis ran no new tests. Where a reviewer corrected a part's claim, the corrected version is used, and §4 says so.

---

## 1. Bottom line

**Mesh's plumbing works, but the gameplay a creator authors on top of it mostly does not.**

These paths were driven through the real runtime and all work:
- project creation;
- Studio's project model and imports, including HD-2D;
- the authoring transaction (`mesh author`, MCP);
- room transitions into and out of HD-2D;
- room memory;
- quicksave and quickload across processes;
- the export, and the exported game running on its own bundled engine with per-player saves;
- the mesh_net character store over real sockets.

The authored gameplay layer is a different story. In the end-to-end chain (create → author → play → save → reopen → export), 11 creator-facing elements were tried. **6 broke and 1 needed a hand-edited file:**
- the once-only reward is paid again (#620);
- the shop never opens (#654), and in a created project it can't even be built (#652);
- the chest grants nothing (#636);
- pickups grant nothing (#652);
- every Studio "Has health" starts at 1 HP (#651);
- the unlocked gate still blocks (#639);
- the first quest needed a hand-written `quests.json` (#655).

The s1v verification repeated these on every playable template and on the export.

**Open confirmed defects at the integration tip:**

| Priority | Count | Issues |
|---|---|---|
| **P0** | **1** | #660: F4 opens the legacy editor in exported games, and Edit > Delete then permanently deletes game files. The fix is in flight (#662) |
| **P1** | **12 product + 1 CI safeguard** | #620, #622, #623†, #631, #636, #639, #640, #641, #642, #651, #652, #654†; CI: #612 |
| **P2** | 14 | #621, #624 (B–D), #627, #632, #637, #643, #644, #645, #648, #650, #653, #655, #656, #658 |
| **P3** | 5 confirmed | #646, #647, #649, #657, #663 |
| Suspected (tracked) | 1 | #638 (P3 if confirmed) |

† The severity is disputed between reviewers. See §4 and the decision brief.

**Fixes in flight:**
- #612: GC isolation, draft PR #661;
- #622: PR #635. The independent reviewer agent approved it at `8f83a161`; the approval is recorded in the coordinator's log, and there is no GitHub review object. The PR is still a GitHub draft and is blocked on #612;
- #660: draft PR #662.

**Already merged:** #625 (#619), #628 (#618), #633 (#624 phase A) and #634 (the #612 diagnostic).

**Why "supposedly completed systems never worked together"** comes down to five recurring test patterns (§3):
- the fake invents the API;
- the test calls the hook it assumes the runtime calls;
- the test asserts the document or internal state, not the outcome;
- a negative branch is missing;
- a parallel runtime is tested instead of the live one.

All 10 defects that part C analysed as case studies sat behind one of these patterns (#619, #620, #622 A/B, #636, #637, #639, #640, #641, #642). The P1s found after that analysis were not studied the same way. The seam each one slipped through:
- **#651:** tests build Health and Combat directly, bypassing the factory, and the real-window arena always writes `hp`. The construction path was never exercised.
- **#652 and #623:** tests run from the engine checkout, whose current folder has `items.json` and `saves/`. That environment masks both.
- **#654:** vendor tests call `handle_buy_request` directly; nothing opens a shop through interaction.
- **#660:** `test_legacy_ui_cleanup.py` calls `_toggle_editor` on fake windows instead of sending a real key (the test calls the hook it assumes the runtime calls).

The suite is large: 13,971 tests in 1,996 files.
- **Real-window files:** part C classifies a file as real-window when it constructs a GameWindow, the headless editor, or worker/Studio processes, or holds a `gl` test. 146 files qualify, holding 1,298 tests.
- **Of those, about 680 non-GL tests gate every PR**, roughly 5% of the suite.
- **3,717 tests sit in files that use a fake window and no real window** (a per-file classification).
- **Only 20 test doubles in the whole suite are spec'd.**

**The repairs are bounded. No broad rewrite is warranted.**
- Every confirmed defect has its root cause in a small, bounded set of functions. The largest are #651 (three causes across seven files) and the #623 family (five modules). Each has a fix of S or M size (`12_stabilization_roadmap.md`).
- The architectural risks (duplicate runtimes, the god-facade window, the change hub in `project_ops`) are real. But each one has a targeted containment step, and the evidence doesn't show that targeted repair is inadequate anywhere.

**Verdict:** Mesh is **not yet reliable enough to finish a game with**. It can get there in a bounded S1:
- 7 stages and about 55 small PRs, of which about 25 are the P0/P1 core;
- a measurable finish line (`12_stabilization_roadmap.md` §9).

The core of it is about 13 P1 fixes, a shared real-runtime contract test, and one end-to-end workflow test. That test runs in Extended; its HD-2D leg runs in the gpu lane, because it needs GL.

---

## 2. What was verified to work (real runtime)

| Area | Evidence |
|---|---|
| `mesh new` (5 of 7 templates start, walk and draw) | part D §3 (`scan_project_templates.py`); s1v `evidence/s1v/s1v_make.py` and the #652 issue comment. The make script's output file is not committed (`*_out.txt` is git-ignored) |
| Studio project model: rooms, imports (picture, tileset, sound, .glb), model reimport, HD-2D kit | part D W1/W2 |
| Authoring transaction (`mesh author apply`, 48 changes) and MCP `apply_ops` writes | part D W1 |
| Doors between 2D and HD-2D rooms; HD-2D room walks and draws | part D W3 |
| Room memory (defeated enemies stay gone after re-entry and load) | part D W4/W5 |
| F5, a new process, then F9: gold, flags, quests, inventory, room memory | part D W5 |
| `mesh export build`; the exported game on its own engine; per-player saves; nothing written into the bundle | part D W6; s1v `play_export*.txt` |
| mesh_net character store: restore after a real server restart, drop/resume, one session per character | part D W7 |
| Studio "Show when" (ConditionalActivator) works within the same visit | s1v (#653 comment) |
| Destructive-write primitives (`json_io`), Studio F15/S4 file release, HD-2D catalogue swap, export F4 ownership, mesh_net SQLite store | part A §3 (read and spot-checked) |
| Recently hardened modules kill all mutants: `project_save`, `entity_factory`, legacy file ops (through fake windows) | part C §2 |

---

## 3. Findings by class

Each significant finding carries one class: **Confirmed defect**, **Architectural risk**, **Suspected issue**, **Known limitation** or **Historical issue**. The full per-issue index is the appendix of `12_stabilization_roadmap.md`.

### 3.1 Confirmed defects (open)

| Issue | Finding | Sev (final) | Reach that carries the severity | Root-cause theme |
|---|---|---|---|---|
| #660 | F4 opens the legacy editor in exported and `main.py` games. Edit > Delete then unlinked a sprite and `config.json` (reproduced). The room files are exposed to the same delete; deleting them was not shown | **P0** | every exported game, by one key | gate on a route no key uses (#347) |
| #631 | Legacy Edit > Delete / palette "Delete Selected": no confirmation, no trash. In a real window the Del key does nothing (challenge correction) | P1 | legacy editor; through #660, exports | legacy file ops |
| #641 | Legacy file ops read `window.repo_root`, which never exists. The safe operations are inert; the plain ones act on the CWD | P1 | legacy editor | fake-only contract, CWD |
| #623 | Non-exported saves resolve against the CWD, so a project switch or `run_game(project_root=)` overwrites another project's slot | P1 (disputed: P2) | checkout project browser, legacy editor, public `run_game` API | CWD-relative paths |
| #642 | An MCP cutscene edit that reports success makes the project unopenable | P1 | AI authoring | unvalidated write, uncaught schema error |
| #622 | ActionListRunner inert; cutscene `find_sprite` missing; `.behaviours` read | P1 | Studio-addable behaviours | the test calls the hook / the fake invents the API |
| #651 | Health with no explicit `hp` starts at 1 HP; the player ignores its stats | P1 | every tool-authored Health, every template, exports | config defaults filled at construction and write time |
| #652 | No created project has `items.json`; pickups, shops, item drops and chest items fail | P1 | every created project, exports | scaffold gap; the item database raises |
| #654 | Studio "Shopkeeper" never opens (Vendor has no interact handler) | P1 (disputed: P2) | Studio picker | wiring |
| #636 | RewardChest marks itself looted and emits `reward_collected` but grants nothing | P1 | Studio "Treasure chest" | the fake invents the API |
| #639 | DoorLock unlocks but stays solid; pictures are never applied; door and button state are lost on re-entry and load | P1 | Studio picker | asserts state, not outcome; instance-only state |
| #640 | TriggerZone ignores "Event it sends" and emits `entered_zone` twice | P1 | Studio picker | document-shape tests |
| #620 | "Only once" / "Choice once" reward repeats after re-entry or load | P1 | Studio dialogue | instance-only state |
| #612 | ep05 replay budget flake: a pytest-heap gen-2 GC pause inside a timed tick | P1 (CI safeguard) | 4 of 7 CI flakes | test-harness measurement |
| #621 | One event completes two consecutive same-trigger quest stages | P2 | no shipped or authorable shape today | quest progress |
| #637 | Removed entities keep handling bus events until the room is left | P2 | any removal mid-room | lifecycle hook mismatch |
| #632 | Re-deleting a re-created file overwrites its earlier `.mesh_trash` copy | P2 | legacy editor | trash layout |
| #627 | Drops lose the item when it can't be granted. Confirmed only when `items.json` is missing (s1v: the drop and its gold are lost for good); suspected for a full inventory | P2 | enemy drops | grant result ignored |
| #643 | Player HUD health/level panel never draws (`window.player`) | P2 | every game with a player Health | fake-only contract |
| #644 | Console `quest`, `quest active` and `rules` raise | P2 | developer console | two quest managers |
| #645 | Legacy main menu Continue reads `saves/save_1.json`, which nothing writes | P2 | legacy main menu | two save systems |
| #653 | Entity-level `require_flags` is applied only at room load | P2 (was P1) | `mesh author` / MCP `set_entity_fields`; checkout sample content | documented load-time semantics |
| #655 | No supported tool can create a fresh project's first quest | P2 | every created project | scaffold gap |
| #656 | `lighting_playground` and `demo_slice` templates create projects that can't start | P2 | CLI-only templates | stale templates; contract test asserts the old shape |
| #658 | 14 of 15 sample solid gates can be walked round; the model catalogue stores an absolute source path | P2 content / P3 | checkout sample content; shared project folders | content |
| #624 B–D | mypy baseline-count guard is a no-op; baselines can grow; steps pass when their input is missing; mypy-island fails open | P2 (B: P2/P3) | CI | fail-open gates |
| #648 | No floor on the default suite; the gpu floor is 256 of 621 | P2 | CI | stale lane floors |
| #650 | Nine mutation survivors (quests, `project_ops`, vendor) | P2 (test gap) | regressions no test would catch | missing negative branches |
| #647 | `chance: 0` always drops, in the engine and in mesh_net's copy | P3 | Studio DropTable field | `x or default` |
| #646, #649, #657, #663 | Fake-only P3 attributes; silent CI gaps; MCP `list_scenes` empty; shop docs / talk+shop UX / `set_entity_fields` warning | P3 | developer, docs | mixed |

### 3.2 Architectural risks

| Id | Risk | Demonstrated impact | Containment proposed |
|---|---|---|---|
| D-1 | Two QuestManagers. The game uses `engine.quests`; GameStateController's default and about 35 test files use the lightweight one | #644, T-3 warnings; the tests' quest semantics are not the game's | Roadmap 6.1 |
| D-2 | Two hotkey systems that shadow each other | 5+ incidents; #660's F4 bypass is one more (`input_dispatch` shadows the router) | 6.3 |
| D-3 | The episode harness runs a `MagicMock()` window with a GameplayEventBus, so its "integration" episodes take the other event route | Masks wiring defects (#622 class) | 6.4 |
| D-4 | Two cutscene runtimes with disjoint command sets | `mesh cutscene validate` accepts what the game's schema refuses; #642 makes that fatal | 6.2 |
| D-5 | Two save systems (SaveManager vs `savegame.py`) | #645 | 6.6 |
| D-6 | Three inventory access paths | #636 | 4.4 |
| D-7 | mesh_net re-implements engine rules (gate, interaction ranking, drop roll) | Copied the #647 bug; the net gate behaves differently from #639 | 6.5 |
| D-11 | The legacy editor (59k lines) and `EditorModeController` (fan-out 74) are built into every GameWindow, games included | #660 is reachable at all because of this | 1.1 then 6.8 |
| CWD | Project files resolved against the current folder | #623, #641, `cutscenes.json`, the item database, `savegame.py` | 2.3 |
| Instance state | "Already happened" facts kept on behaviour instances, which are rebuilt on every room entry | #620, #636, #639 | 4.1 |
| Config defaults | `normalize_config(fill_defaults=True)` erases "author didn't say" | #651 (Health, Combat, CameraFollow, LightSource) | 3.1 |
| Coupling | `project_ops.py` (4,292 lines) co-changes with `studio_hd2d` / `hd2d/renderer` 27× each; `game.py` has fan-in 94 and fan-out 60 | Shotgun surgery on every HD-2D/Studio feature | Not in S1. Watch, and split only with evidence |
| Test doubles | 15 window attributes exist only on fakes; 20 spec'd doubles in 13,971 tests | 9 of the 10 part-C case-study defects | 3.0, 5.6 |

### 3.3 Suspected issues (not reproduced)

| Item | Where | Next step |
|---|---|---|
| F3 debug mode in shipped games unlocks debug hotkeys such as Ctrl+S scene save (#660 follow-up) | exported and `main.py` launches | Roadmap 1.2: verify first. If Ctrl+S writes into the bundle, treat it as P0 |
| T-2: quest `emit_events_on_complete` ignored; `reward.gold`/`xp` dropped by `normalize_reward` (triage) | 16 shipped uses | 6.1: verify (part D saw quest rewards paid, so it may be narrower) |
| #627: drops with a full inventory | `drop_table.py:119` | 4.4 |
| #638: a self-removing entity misses its own event; EventLogger is never subscribed | code reading | 4.5: verify or close |
| SetGameStateOnEvent `inc_counters` + `once` re-applied on every visit; one-shot Interactables that pay out | part B §3.4 | 4.1 rows |
| NEW-15: ownership-race test flake; replays-job flake on 2026-11-22 | CI | 5.3 |
| Two mesh_net servers opening one character store | part A | deferred |

### 3.4 Known limitations

Each is accepted by design or documented:
- `project_save` is not crash-safe (no fsync);
- `mesh new --force` deletes by design;
- exports need Mesh's dependencies installed;
- dev saves are not visible to the export (H9);
- multiplayer hosts only the packaged scenes;
- M4 D1–D4 and D8 (queue presets pending OD11; the greedy-liar window; `view_tick` reach; route timing parity; TCP head-of-line blocking);
- #496 items 2–6;
- ToggleSwitch sends only `switch_toggled`;
- TriggerVolume's "once" re-arms each visit;
- **`packs/` (the core_regions campaign and dev_sandbox) and `scenes/` are checkout-only sample content, not in the wheel.**

### 3.5 Historical issues (fixed; kept for the record)

| Item | Fixed by | Caveat |
|---|---|---|
| #618: legacy rename/move overwrites | #628 | The no-clobber logic is right, but **unreachable in a real window until #641 is fixed** (part B re-qualification). The acceptance for 2.1 re-runs the check in a real window |
| #619: shop charges without granting | #625 | V1/V2/V4 economy mutants still survive (#650) |
| #624 A: ruff/mypy gates pass with the tool missing | #633 | — |
| `solid_sprites` read from the window | earlier fix | The pattern recurs (#641, #643) |
| #612 cold-start theory | refuted by #634 | The GC root cause is confirmed |
| #496 item 1: owed unlocks | #510 | — |
| #347: "legacy editor off the normal path" | merged | **Never worked through a real key press** (#660) |

---

## 4. Corrections applied (challenge review and s1v)

| Item | Part's claim | Correction used here | Source |
|---|---|---|---|
| Sample-content reach (#636, #639, #651, #653, #654) | "Shipped content" | `packs/` and `scenes/` are checkout-only. P1s rest on the Studio and tool paths, not on the campaign | challenge review |
| #639 | 22 DoorLock scenes; campaign broken | 18–20 scenes. The campaign is passable by walking round the gates (#658). P1 on the Studio path | challenge |
| #651 | 154 configs, 102 without `hp`; root cause `fill_defaults` | 160 configs (prefabs merged), 102 without `hp` (94 campaign players). **Three causes:** (1) `project_ops.add_behaviour` writes `hp`/`max_hp`/`damage`, which alone breaks every tool-authored Health; (2) `fill_defaults=True` breaks hand-written partial configs; (3) `health.py:86` reads `config.get("max_hp", stats)` after `_merge_param_config` has copied every declared parameter, so the stats are unreachable regardless | challenge + s1v |
| #652 | The CWD-relative read breaks created projects | Generated `main.py` and exports chdir first. The causes are that nothing writes the file and that `inventory.py:45-49` raises. Also: with no items, a DropTable drop *and its gold* are lost for good | s1v |
| #653 | P1 | **P2.** The load-time gating is documented, Studio uses ConditionalActivator (which works), and re-entry works around it | challenge, upheld by s1v |
| #654 | P1 → P2 (challenge: Interactable with `interact_event=open_shop` works) | **P1 recommended** (s1v): the working route is undiscoverable, and the guide shows an event that is never sent | s1v |
| #631 | P1-proposed; Del key safe | **P1.** In a real window Del does nothing (the safe delete is inert, #641); Edit > Delete unlinks. Reached in a standalone launch via F4 → #660 | challenge |
| #623 | P1 (part A) | Challenge says **P2**: the menu project switch is blocked in standalone launches. Shown both ways; P1 recommended (decision brief D2) | challenge |
| #624 B | P1 | **P2/P3.** `tooling/mypy_baseline.txt` is committed, so growth shows in the diff | challenge |
| #640 | P1 | P1 upheld. The engine's own doc calls `on_trigger` a "Label". The campaign wires through `entered_zone` plus the zone name, so a fix must keep `entered_zone`. The double count was confirmed (+2 per entry) | challenge |
| #636 | 12 scenes | 12 by behaviour list (18 by text match). Created projects also depend on #652 (s1v: even with items the chest grants nothing) | challenge, s1v |
| "No P0" (parts A–D) | — | **Superseded by #660 (P0)**, found by the challenge review | challenge |
| #612 | cold start, then contention | Root cause: a gen-2 GC of pytest's heap (1145 of 1155 ms). Harness fix approved | #612 comments |

---

## 5. Reconciliation with the independent audit (draft PR #629)

| # | #629 finding (its severity) | Issue | Status at the tip | S1 severity | Roadmap |
|---|---|---|---|---|---|
| 1 | Legacy rename overwrites the destination (P1) | #618 | **Historical:** fixed by #628, issue closed. Real-window reach waits on #641 | closed | re-verified in 2.1 |
| 2 | Save slots cross project boundaries (P1) | #623 | **Confirmed, open** | P1 recommended (challenge: P2) | 2.3 |
| 3 | Reward chest grants nothing (P1) | #636 (supersedes #627's chest part) | **Confirmed, open** | P1 | 4.4 |
| 4 | Authored actions and cutscene steps fail (P1) | #622 | **Confirmed.** Fix PR #635 was approved by the independent reviewer agent at `8f83a161` (coordinator's log; no GitHub review object) and is blocked on #612 | P1 | 1.4 |
| 5 | One quest event advances two stages (P2) | #621 | **Confirmed, open** | P2 (agrees with #629) | 6.1 |
| 6 | One-shot dialogue reward resets (P2) | #620 | **Confirmed, open** | **P1** (disagrees with #629: it breaks an explicit Studio promise on the main path, without limit) | 4.2 |
| 7 | Removed entities keep handling events (P2) | #637 | **Confirmed, open**; does not multiply | P2 (agrees) | 4.5 |
| 8 | Ruff/mypy wrappers pass with the checker missing (P2) | #624 A (+ B–D) | **Historical** for A (#633). B–D confirmed, open | P2 (B: P2/P3) | 5.1 |

**#629's improvements and exclusions** are also confirmed:
- #619 was fixed by #625;
- #629 made no renderer measurements;
- its "test doubles supply missing interfaces" warning is the central finding of this report.

**How the roadmap differs from #629's remediation order:**

#629's order was:
1. #618;
2. #623;
3. #636;
4. #622;
5. #621, #620 and #637;
6. the gates (#624).

The roadmap departs from it as follows:

| Change | Why |
|---|---|
| #660 (P0, new) comes first (1.1) | It is the only P0 |
| #618 is done (#628), but its real-window re-verification moves into the legacy-editor item (2.1) with #641 and #631 | #628's fix is unreachable in a real window until #641 lands |
| #622 (1.4) moves ahead of #623 (2.3) and #636 (4.4) | Its fix is ready and blocked only on #612 |
| #636 moves to S1-4 (4.4), after #652 (3.2) and the facts mechanism (4.1) | Without persistence, a working grant creates a farmable reward. Item grants need `items.json` in created projects |
| #620 and #637 stay together in S1-4 (4.2, 4.5) | #620 now depends on the facts mechanism |
| #621 moves to S1-6 (6.1), which is not exit-required | It is P2, and its fix belongs with the quest-manager convergence |
| The gates (#624 B–D) run in parallel in S1-5 instead of last | They touch no `engine/` file |
| New P1s are interleaved through S1-2 and S1-3: #641, #642, #651, #652, #639, #640, #654 | Found after #629 |

**Disposition of draft PR #629:** **merge it as historical evidence**, together with or after the S1-0 docs. It is docs-only, faithfully records owner-supplied evidence with its provenance (audited at `49686331`), and is cited here. This report's table carries the reconciliation, so the audit document needs no edits. Alternative: close it as superseded. That loses the in-repo record of an owner-supplied input, so it is not recommended. See decision D8.

### Coordinator triage (`TRIAGE.md`, verified at `a4465258`)

| Triage item | Now |
|---|---|
| #618–#624 table | As §3. #621 → P2 (triage: P1); #623 → P1/P2 dispute (triage: P2); #624 → split A historical, B–D P2 |
| MCP cutscene ops (read only) | **Confirmed end to end:** #642, P1 |
| Quest `emit_events_on_complete`, reward gold/xp (T-2) | Still suspected; roadmap 6.1 |
| Spurious load warnings (T-3) | Cause found: the restore code targets the lightweight quest API (D-1). P3; roadmap 6.1 |
| Duplicate toast on quickload (T-4) | Not re-checked; P3; roadmap 7.5 |
| "GameWindow attributes (read, not run)" | Run in part B: `player` → #643; `editor*` → dead branches (#646); `gameplay_event_bus` → by design (D-3); `quest_runner`/`cutscene_runner`/`digest_tracker` → #646 |
| "Duplicate hotkey bindings — not checked" | Now demonstrated by #660 (D-2) |

---

## 6. Engine health in numbers

| Measure | Value | Source |
|---|---|---|
| Tests / files | 13,971 / 1,996 | part C §1.1 |
| Real-window test files: a file that constructs a GameWindow, the headless editor, or worker/Studio processes, or holds a `gl` test | 146 of 1,996 files (1,298 tests) | part C §1.2. This is the definition used throughout S1. Part B's narrower scan counted only GameWindows built through helpers it recognises: 49 of 2,027 files |
| Non-GL real-window tests gating every PR | ≈ 680 (≈ 5%) | part C §1.2 |
| Tests in files that use a fake window and no real window (per-file classification) | 3,717 (26.6%) | part C §1.2 |
| Spec'd doubles | 20 sites in 12 files | part C §1.2 |
| Window attributes production reads that only fakes provide | 15 | part B §1.1 |
| Mutation kill rate (40 hand mutants, 8 modules) | 70% own files, 75% wider; quests 1/5 | part C §2 |
| CI push wall, median / p90 | 13.7 / 15.7 min | part C §3.2 |
| Extended push wall, median / p90 | 37.4 / 38.7 min (Windows gpu shard 2/2 is the critical path) | part C §3.2 |
| Cost per merge | ≈ 345 job-minutes | part C §3.2 |
| Non-change attempt-1 CI failures | 4.1% of pushes (2/49), 6.1% of PRs (5/82); #612 is 4 of 7 | part C §3.5 |
| Lane floors | default suite: none; gpu 256 of 621; extended 162 = 162 | part C §3.4 |
| Largest change hub | `project_ops.py`, 4,292 lines, co-changes with 6 large files 15–27× | part B §4.2 |
| Legacy editor surface | 282 files, 59,182 lines, built into every window | part B D-11 |

---

## 7. What we could not check

Collected from each part, the s1v verification and this synthesis. **No feel, visual-quality or audio pass is claimed.**

| Part | Not checked |
|---|---|
| A | Real key input (interaction was driven through `perform_interaction`). #622 C, #624 B and NEW-3/4 are code-read only. #624 C/D and T-2–T-4 were not re-run. #627 drops with a full inventory. Two exports sharing a `game_id` (reasoned only). Two mesh_net servers on one store. `tooling/` (about 110 files) classified by purpose only. Whether the RewardChest dungeons are reachable in normal play |
| B | Real key input. Studio and editor launch for #642 (code read). The legacy editor's visible UI. Whether a campaign chapter is impassable (later answered by part D: none is). Music, weather, lights, ToggleSceneLights, QuestGiver end to end, Vendor stock persistence. `scan_behaviour_test_coverage.py` is approximate. Fake-window blind spots (`beh.window`, `setattr`). D-9 placement maths. Change coupling covers 300/600 commits |
| C | Per-test CI durations (no `--durations`; R2's cost is estimated). 40 mutants is a probe, not a score; V1/V2/V4 and S1 were not re-run wider. The five patterns are proven on 10 case studies only. Flake logs beyond about 3 days. The replays-job cause. Billing multipliers. R4 tree-equality was reasoned, not sampled |
| D | Studio's GUI itself (panels, picker UI, the Play button). Real OS input. The installed-wheel path (CI covers it). `mesh play`. Multiplayer progress through the client path (the tests' Driver teleports). Combat damage to the player. Audio (never played aloud). Cutscenes and ActionLists in the chain. Campaign exits beyond Ambush (static scan only). Web build, `package-player`, release. Exports on another machine |
| s1v | Studio GUI (ops only). Visible input. Uses the same hidden-window driver as part D |
| Synthesis | No new runs. #660's evidence logs are held by the coordinator (not re-read). PR #661/#662 diffs were not reviewed (in flight, reviewed elsewhere). Older open issues outside S1-0's scope (#357, #359, #390–#396, #466, …) were not re-verified (appendix of `12`) |

---

## 8. Provenance and the evidence slip

- **Commits on `docs/s1-0-investigation`:**
  - `f8efb42a` (part A);
  - `aa4ed794` (B);
  - `7ebae9bc` (C);
  - `1291f64b` (D);
  - `035d0280` (s1v evidence);
  - `30d44f27` (scrub);
  - this synthesis.
- **Evidence scripts** are in `docs/s1/evidence/` (exit 1 while the defect is present). CI data is in `evidence/data/`. s1v scripts and outputs are in `evidence/s1v/`.
- **Evidence slip (disclosed; corrected after review):**
  - Commit `035d0280` contains the owner's Windows username inside temp paths in 7 copied s1v outputs:
    - `docs/s1/evidence/s1v/play_export1.txt`;
    - `play_export2.txt`;
    - `play_n_adventure.txt`;
    - `play_n_blank.txt`;
    - `play_n_hd2d_rpg_2.txt`;
    - `play_n_monster.txt`;
    - `play_n_starter.txt`.
  - Commit `30d44f27` replaced it with `<home>`, and **the current tree is clean**.
  - **The branch is pushed to origin and the repository is public.** So the username is publicly readable today through commit `035d0280`. An earlier version of this section wrongly said the branch was unpushed.
  - Rewriting history was not authorised in S1-0. Whether to rewrite or delete the branch is owner decision **D15** (`14_owner_decision_brief.md`).
  - GitHub may keep serving a commit by its SHA after a force-push makes it unreachable, so a full purge may need a request to GitHub Support. Existing clones and forks keep their copies regardless.
- **Pre-existing occurrences, not from S1:** the same username appears in **6 tracked files on the integration branch** that predate S1. 3 of them are also on `main`. The username itself is not reproduced here.
  - `docs/map_collision_paint.md` (also on `main`);
  - `docs/monster_rpg_roadmap.md` (also on `main`);
  - `docs/reviews/milestone16_stage5b_evidence/pipeline_check.json`;
  - `docs/reviews/milestone4_screens/report.json`;
  - `docs/reviews/milestone9_test_audit.md`;
  - `tests/test_rmmz_passability_import.py` (also on `main`).

  Found with `git grep -l -i <username> HEAD` and `origin/main`. The reviewer counted 5; this check found 6. A scrub PR for these files is offered as an owner choice in D15. Their earlier history would still contain the username unless history is rewritten.
- **Not this branch's evidence:**
  - #660's repro logs (coordinator);
  - the triage repro scripts (`audit/deep-audit-triage:docs/audits/deep_audit_2026_11/repro/`);
  - #629's disposable-project reproductions (not re-run by #629's documenter).
