# S1 Stabilization Roadmap

**Goal:** make Mesh reliable enough to build and finish games with, so that a creator stops discovering that supposedly completed systems never worked together.

**Inputs:**
- `10_health_report.md` (findings, classes, corrected severities);
- `11_subsystem_risk_map.md`;
- `13_testing_ci_proposal.md`, the source of the CI costs used below.

**Decisions** referenced as D1–D14 are in `14_owner_decision_brief.md`.

## 1. Summary

**Stages:** 7, ordered P0 → P1 → P2 → P3. Each stage is a set of small, independently reviewable PRs.

| Stage | Theme | Items (by priority) | PRs (approx.) | Exit-required? |
|---|---|---|---|---|
| **S1-1** | Close the P0; land in-flight work | P0 1, P1 3 (one is a P0/P1 candidate), housekeeping 1 | 4 | yes |
| **S1-2** | Destructive operations and save-data integrity | P1 3, P2 1 | 5 | yes |
| **S1-3** | Studio-authored features work at runtime | P1 5, P2 1 (test fixture) | 10 | yes |
| **S1-4** | Authored state persists; entities end cleanly | P1 4, P2 1 | 6 | yes |
| **S1-5** | Gates, CI trust, real-runtime contracts | P1 1, P2 6, P3 1 | 14 | yes, except 5.4 and 5.8 |
| **S1-6** | Bounded convergence of duplicate runtimes (P2 debt with demonstrated impact) | P2 9 | 11 | no: carry forward with owner disposition |
| **S1-7** | Optional cleanup | P3 5 | ~5 | no |

**Totals:**
- **42 items:** P0 1, P1 16, P2 18, P3 6, plus 1 housekeeping item (1.5). Item 1.2 is counted under P1 until verified.
- **About 55 PRs.** About 25 of them make up the P0/P1 core and its two exit-required enablers (2.2 and 3.0).

**Parallelism:**
- S1-5 touches only `tests/`, `tooling/` and CI. It can run alongside S1-2 to S1-4 once S1-1 has landed.
- S1-3 and S1-4 both edit `puzzle_behaviours.py`. Test the **combined merge tree** before the second of any two parallel PRs on one module merges (the #600 + #601 lesson).

**Complexity:**
- **S:** one PR, a small production diff, about a day.
- **M:** one to three PRs, or a cross-module change.
- **L:** a multi-stage change.

There are no L items in S1-1 to S1-5.

**CI cost per item:**
- Real-window tests cost about 0.4 s each.
- A picker-contract row costs about 2 s (part C §5.1).
- Unless stated otherwise, each P1 fix adds about 3–5 s per OS to the required `pytest` jobs.

**Every fix PR follows the established rules:**
1. Reproduce first, with the script in `docs/s1/evidence/` (it exits 1 while the defect is present).
2. Add a regression test through the **real runtime**: a hidden GameWindow, `perform_interaction`, keys through `dispatch_event`, the real loader or save/load.
3. Prove the test with a mutation: reverting the fix fails it.
4. Have it independently reviewed.
5. Keep existing saves, project formats and replays loading.
6. Dispatch Extended before merging any runtime change.

---

## 2. S1-1: close the P0 and land in-flight work

### 1.1 #660: F4 opens the legacy editor in exported games (P0), in flight as #662

- **Problem / evidence:** reproduced on an export at `7b2b884e`. The sequence is F4 via `dispatch_event`, then Edit > Delete on `config.json` and an asset. Both are unlinked. The editor also starts the live-session server and writes `bundle/.mesh/live_session.json`.
- **Root cause:** `input_dispatch.py:39-43` handles F4 and calls `editor.toggle()` before the key router runs. `legacy_editor_allowed` (`action_runtime/registry.py:34-38`) guards only the action-registry route, which no key uses.
- **Approach (#662):** enforce `legacy_editor_allowed` once, at the top of `EditorModeController.toggle` (`editor/overlays_modals.py:72`), which every route calls. Open editors and play-tests can still close.
- **Files:** `engine/editor/overlays_modals.py`; tests.
- **Dependencies / risks:** none. Risk: `mesh edit` and `MESH_LEGACY_EDITOR=1` must still open the editor (both are covered by #662's tests).
- **Compatibility:** owners who used F4 in game runs need `MESH_LEGACY_EDITOR=1`. This was already #347's documented contract.
- **Acceptance:** #660's list, all run on a real hidden window with keys through `dispatch_event`:
  - in a game launch, F4 leaves the editor inactive and `live_bridge is None`;
  - editor mode and the env var still open it;
  - an open editor still closes;
  - end to end, F4 then delete leaves the file intact;
  - mutation proof.
- **Complexity:** S. **Decision:** no (D3 covers the wider legacy strategy).

### 1.2 Debug mode (F3) in shipped games (suspected; P0 if it writes the bundle, otherwise P1)

- **Problem / evidence:** #660's follow-up. F3 toggles `engine_config.debug_mode` with no launch check (`input_dispatch.py:202-203`).
  - Debug mode unlocks F12/F7/F8 debug battles, F10 `debug_breed_first_party_pair` and the F9 batching toggle (`:157-199`).
  - Per #660 it also unlocks Ctrl+S scene save.
  - Nothing verifies what Ctrl+S writes in an export.
- **Root cause:** the same as #660. Developer affordances are reachable in player launches because no launch-mode gate applies on the key path.
- **Approach:**
  1. Verify on an export, as #660's repro does: F3, then Ctrl+S. Check whether any room or project file changes.
  2. Gate debug mode's **state-changing** hotkeys in non-editor launches with the predicate #662 uses, or an equivalent `developer_tools_allowed`. Read-only overlays may stay (D4).
- **Files:** `engine/game_runtime/input_dispatch.py`, the Ctrl+S debug save handler, tests.
- **Dependencies / risks:** after 1.1. Risk: developers who rely on F3 in `main.py` runs (offer the env var).
- **Compatibility:** shipped games lose the cheat and debug keys; editor launches keep them.
- **Acceptance:** real-window export launch: F3 then Ctrl+S changes no file under the bundle, F10 changes no party state, and editor launch mode still allows them. Mutation proof.
- **Complexity:** S. **Decision:** **D4** (what debug mode may do in shipped games).

### 1.3 #612: ep05 replay budget flake (P1, CI safeguard), in flight as #661

- **Problem / evidence:** 4 of the 7 non-change CI failures in the window. The #634 diagnostic showed that 1,145 of a 1,155 ms tick was a gen-2 GC pause of pytest's heap. There were no imports, and CPU time matched wall time.
- **Root cause:** a full collection of the long-lived test process's heap lands inside a timed tick.
- **Approach (#661, owner-approved):** `gc.collect()` then `gc.freeze()` around the timed executions in `mesh_cli/episode.py` `_handle_replay_check`, and `unfreeze` in a `finally`. Every budget stays unchanged.
- **Files:** `mesh_cli/episode.py`, tests.
- **Dependencies / risks:** none. Risk: a freeze leak, covered by #661's freeze-count handling.
- **Compatibility:** replay results and digests are unchanged.
- **Acceptance:** #661's tests pass. Then **0 ep05 failures in the next 30 CI runs** feeds exit criterion E9. The #634 review's owed asserts (X4, X5) are tracked in 6.9.
- **Complexity:** S. **Decision:** no (already approved). #659 (GC hitches in game sessions) stays an unscheduled investigation, by owner decision.

### 1.4 #622: live-runtime wiring for ActionLists and cutscenes (P1), in flight as #635

- **Problem / evidence:** ActionListRunner is inert under live `on_event` delivery; cutscene `move_entity` / `camera_focus` raise on the missing `find_sprite`; `.behaviours` is read where sprites have `mesh_behaviours_runtime` (triage repro; part A).
- **Approach:** PR #635 (approved in review; still a GitHub draft): `subscribed_event_types` / `on_event`, `find_entity`, `mesh_behaviours_runtime`.
- **Files:** `action_list_runner.py`, `cutscene_controller.py`, tests.
- **Dependencies / risks:** **merge after 1.3**, since its CI hit the #612 flake. Dispatch Extended (runtime event delivery). Later 2.4 and 6.2 touch `cutscene_controller.py`, so land this first.
- **Compatibility:** scenes that relied on actions doing nothing will now act (11 repo scenes). That is intended.
- **Acceptance:** #635's real-delivery tests, plus Extended green.
- **Complexity:** S. **Decision:** no.

### 1.5 Issue hygiene (no code)

Bring the issue titles and labels in line with the corrected severities, as housekeeping:
- #653 → P2;
- #654, #623 → as decided in D2;
- #631 → P1;
- #624 → B is P2/P3.

Also:
- link #618's closure to the real-window caveat (it is re-verified in 2.1);
- narrow #627 to drops plus the vendor nits.

**Complexity:** S. **Decision:** D2.

---

## 3. S1-2: destructive operations and save-data integrity

### 2.1 Legacy file ops: one root and safe delete for every entry point (#641 + #631; re-verify #618)

- **Problem / evidence:** `repro_legacy_file_ops_wrong_root.py` shows two failures in a real window:
  - the safe delete, rename and move return False (inert);
  - the plain Delete unlinks the **CWD's** file.

  Edit > Delete and the palette's "Delete Selected" unlink with no dialog and no trash (#631, re-run by the challenge review in a standalone launch via F4).
- **Root cause:** `editor_file_ops_controller.py` reads `window.repo_root` at 11 sites. No production code creates that attribute, and 6 test fakes supply it. The global delete chain goes to `delete_selected_paths` → `unlink()` (`:743`).
- **Approach:**
  1. File ops take their root from `self.controller._get_repo_root()`, the root the explorer already shows. Delete every `window.repo_root` read, and refuse with a toast instead of falling back to `"."`.
  2. Route `editor.delete` and the palette command through the existing safe delete (confirmation plus trash). Don't add a second implementation.

  **Alternative (D3 option B):** make all legacy delete, rename and move refuse with a message.
- **Files:** `engine/editor/asset_ops/editor_file_ops_controller.py`, `selection_clipboard.py`, tests.
- **Dependencies / risks:** after 1.1, which lowers the urgency because it closes the export route. 2.2 follows in the same file. Risk: the module kills 5/5 mutants only through fakes, so its tests must move to a real window.
- **Compatibility:** none for data. Existing `.mesh_trash` folders stay readable.
- **Acceptance:** all on a real window with the CWD ≠ project:
  - delete, rename and move touch only the project's file;
  - the CWD's same-named file stays byte-identical;
  - the V2 operations return True;
  - every delete entry point (menu, palette, Del under each focus) asks first and leaves a trash copy;
  - `verify_618_rename_toctou.py` re-run against a real window shows #618 truly closed;
  - mutation proof (restore `or "."`; restore the direct unlink).
- **Complexity:** M (one PR, two commits). **Decision:** **D3** (repair vs disable vs retire).

### 2.2 #632: unique trash entries (P2)

- **Problem / evidence:** delete, re-create, then delete again overwrites `.mesh_trash/<op_id>`, and the first copy is lost. The op_id is a plan hash.
- **Root cause:** `os.replace` into a deterministic path (`:149-150`); `.mesh_trash` is not excluded from the reference scan.
- **Approach:**
  - add a per-staging nonce or timestamp to the trash path;
  - never replace an existing entry;
  - exclude `.mesh_trash` from `list_repo_json_assets`.
- **Files:** `editor_file_ops_controller.py`, tests.
- **Dependencies:** after 2.1.
- **Compatibility:** old trash layout stays readable.
- **Acceptance:** delete, re-create, delete leaves both copies recoverable; the refactor ignores `.mesh_trash`; mutation proof.
- **Complexity:** S. **Decision:** no (if D3 picks "disable", this becomes moot and is closed with it).

### 2.3 One project-root resolver; saves stop following the CWD (#623 and the CWD family)

- **Problem / evidence:** `repro_saves_follow_cwd.py`: project B's quicksave lands in project A's `saves/`. Other CWD-relative project reads:
  - `cutscenes.json` (`cutscene_controller.py:54`);
  - the item database (`inventory.py:45`);
  - `savegame.py:138`;
  - `.mesh/ai_history.jsonl`.

  #641 belongs to the same family, but is fixed in 2.1 through the editor's existing root.
- **Root cause:** there is no single pinned project root; modules assume the CWD is the project. `main.py` and `mesh edit` chdir, which hides the problem; `run_game(project_root=)`, the checkout project browser and the legacy editor don't.
- **Approach:**
  1. **PR 1:** one resolver, `project_root(window)` or the existing game root. `DEFAULT_SAVE_DIR` resolves against it (`save_runtime/storage.py:97-98`). As a read-only fallback, find an existing CWD-relative slot and offer it, but never write there.
  2. **PR 2:** route the cutscene, item-database and `savegame.py` reads through the resolver.
- **Files:** `engine/save_runtime/storage.py`, `cutscene_controller.py`, `inventory.py`, `savegame.py`, `public_api.py`, tests.
- **Dependencies / risks:** after 1.4, which edits `cutscene_controller.py`. 3.2 (#652) may adopt the resolver but doesn't need it. Risk: anything else that silently relies on the CWD; grep for `Path("saves")`, `"assets/data` and similar.
- **Compatibility:** existing saves in CWD-relative folders stay readable. Exports are unchanged (they use per-player folders).
- **Acceptance:** all in one process with an unchanged CWD:
  - two projects keep distinct quicksaves and reload their own;
  - an existing CWD-relative save is still offered;
  - a game started with the CWD ≠ project loads that project's `cutscenes.json` and items;
  - mutation proof.
- **Complexity:** M. **Decision:** **D5** (one resolver); the severity dispute is D2.

### 2.4 #642: MCP cutscene writes are validated; a bad `cutscenes.json` never blocks start-up (P1)

- **Problem / evidence:** `repro_mcp_cutscene_blocks_start.py`. `apply_ops` with `add_cutscene` and a `fade_to_black` step reports success, and then `GameWindow(...)` raises SchemaValidationError.
- **Root cause:**
  - `ai_ops.add_or_update_cutscene` / `insert_cutscene_step` write unvalidated;
  - `run_validation` skips `cutscenes.json`;
  - `game.py:592-595` catches only FileNotFoundError.
- **Approach:**
  1. Validate against `cutscene.schema.json` before writing; refuse with the schema message.
  2. Add `cutscenes.json` to `run_validation`.
  3. In `GameWindow.__init__`, catch SchemaValidationError, skip the bad file or entry, and show a toast and a log line.
- **Files:** `engine/ai_ops.py`, `engine/mcp_server/tools.py`, `engine/game.py`, tests.
- **Dependencies:** after 1.4 (the same controller); coordinate with 6.2 (cutscene schema convergence).
- **Compatibility:** projects with a bad file now open, with a warning.
- **Acceptance:**
  - a bad MCP op is refused and the file is unchanged;
  - a hand-broken `cutscenes.json` lets the game and `mesh edit` start, with the error reported;
  - mutation proof for both halves.
- **Complexity:** S–M. **Decision:** no.

---

## 4. S1-3: Studio-authored features work at runtime

### 3.0 Shared real-window contract fixture and picker-contract skeleton (P2, enabler)

- **Problem / evidence:** 9 of the 10 part-C case-study defects passed tests that used fakes or asserted documents. Only 49 of 2,027 test files use a real window. No test authors a behaviour through Studio ops and plays it.
- **Approach:**
  - **Fixture:** `real_game(scenes)` (hidden, muted, never activated, throwaway scenes; the pattern of `_hidden_game.py` and `tests/_game_window_live.py`) with these helpers:
    - `interact` → `perform_interaction`;
    - `frames(n)`;
    - `walk(dx, dy)` through the real mover;
    - `revisit(room)`;
    - `save_load()`.
  - **Contract:** one parametrised `test_picker_behaviour_contract.py` over `behaviour_guide.GUIDES`. Each row:
    1. authors the behaviour through `project_ops` (the Studio path);
    2. loads and drives it;
    3. asserts the creator-visible outcome;
    4. asserts the declared persistence rule after `revisit` and save/load.
  - Rows for currently broken features carry `xfail(strict=True, reason="#NNN")`, so each fix PR flips its own row, and an unexpected pass fails CI.
- **Files:** `tests/_real_game.py`, `tests/test_picker_behaviour_contract.py`.
- **Dependencies:** none; land first in S1-3. Fix PRs adopt it.
- **Compatibility:** n/a.
- **Acceptance:** every guided behaviour has a row, or an explicit "not runtime-testable: reason" entry. The rows for #636, #639, #640, #651, #652, #654 and #620 are strict-xfail with their issue number.
- **CI cost:** about 15 rows × 2 s ≈ **+30 s per OS** (part C §5.1).
- **Complexity:** M. **Decision:** no.

### 3.1 #651: behaviour configs keep "author didn't say"; Health starts full; the player uses its stats (P1)

- **Problem / evidence:**
  - `repro_health_starts_at_one.py`;
  - s1v on all 5 playable templates and the export: "Health 50" starts at 1/50; the player is 1/1 with damage 1, against stats of 30 HP and 5 attack.
- **Root cause** (three, corrected by the challenge review and s1v):
  1. `project_ops.add_behaviour` (`:352-354`) writes `hp`, `max_hp` and `damage`.
  2. `registry.create_behaviour` → `normalize_config(fill_defaults=True)` (`registry.py:106,208,230`), so `_explicit_params` contains every field.
  3. `health.py:86` reads `config.get("max_hp", stats)` after `_merge_param_config` has copied every declared parameter, so the stats are unreachable whatever happens with (2).

  The same dead branch exists in `combat.py:100`, `camera_follow.py:120,129` and `light_source.py:143`.
- **Approach:**
  - **PR 1 (runtime):** the factory passes the keys actually provided. `_explicit_params` then means "authored". Health and Combat check `"max_hp" in self._explicit_params` / `"damage" in ...`. Audit the four readers.
  - **PR 2 (authoring):** `add_behaviour` stops writing derived-when-absent fields (Health `hp`, the player's `max_hp`, Combat `damage`). Studio's "Starts with" stays optional.
- **Files:** `engine/behaviours/registry.py`, `base.py`, `health.py`, `combat.py`, `camera_follow.py`, `light_source.py`, `engine/project_ops.py`, tests.
- **Dependencies / risks:** independent. **Risk:** sample-content balance changes (94 campaign players go from 1 to 30 HP), and replay or trace goldens may change. Run Extended and the `replays` job, and re-bless only with the owner's approval.
- **Compatibility:**
  - Old saves are unaffected (`saveable_state` carries hp/max_hp).
  - **Existing tool-written files keep their explicit `hp: 1.0`** (D12: a `mesh doctor` warning plus an opt-in fix, never a silent rewrite).
- **Acceptance:**
  - `{"max_hp": 50}` starts at 50;
  - a player Health with no config gets the stats' max_hp, and Combat with no damage gets the stats' attack;
  - explicit `hp: 10, max_hp: 50` keeps 10;
  - a Studio `add_behaviour` "Health 50" starts at 50;
  - picker rows flip;
  - mutation proof (restore `fill_defaults=True`; restore the `add_behaviour` defaults).
- **Complexity:** M. **Decision:** **D12** (existing files); otherwise no.

### 3.2 Project scaffolding and data: #652 (P1), #655 (P2), #656 (P2), #657 (P3)

- **Problem / evidence:**
  - **#652:** no `items.json` in any of the 7 templates or 3 Studio-created projects, so pickups give 0, the Vendor isn't built, and drops are lost along with their gold (s1v).
  - **#655:** MCP `add_quest_definition` needs an existing file, and `mesh new-quest` crashes or writes a list root.
  - **#656:** two templates write the pre-schema format.
  - **#657:** `list_scenes` returns `[]`.
- **Root cause:**
  - nothing writes `items.json`, and `ItemDatabase.load` raises (`inventory.py:45-49`);
  - quest tooling assumes the file exists, and `--target` is misused as a file path;
  - the templates are stale and the contract test asserts the old shape;
  - `list_scenes` globs `scenes/` only.
- **Approach (four PRs):**
  1. **#652:** the scaffold writes a small starter `assets/data/items.json` (D7), and `load_item_database` returns an empty database with one log line when the file is missing. Unknown ids are then refused through the existing #619 messages.
  2. **#655:** `add_or_update_quest_definition` creates `{"quests": []}` atomically under ownership. `mesh new-quest` gets an output path defaulting to `assets/data/quests.json`, writes the object form, and refuses or migrates a list root.
  3. **#656:** retire both templates (recommended; their own code says Studio can't edit them) or port them. Add a test that starts every listed template's scene through the real loader.
  4. **#657:** `list_scenes` lists the world file's rooms, falling back to `scenes/`.
- **Files:** `engine/project_scaffold.py`, `project_templates.py`, `inventory.py`, `ai_ops.py`, `mesh_cli/authoring.py`, `engine/tooling/scaffold.py`, `mcp_server/tools.py`, `pyproject.toml` (data allow-list if the items come from the engine), tests.
- **Dependencies / risks:** **#652 comes first**, because it blocks verifying #654 (3.5) and #636 (4.4) on generated projects. Risk: the wheel allow-list (#345 policy) must include any new data file; the installed check covers it.
- **Compatibility:**
  - existing projects without the file degrade gracefully instead of raising;
  - a list-rooted `quests.json` gets a clear message;
  - retiring the templates removes two `--template` ids (document it).
- **Acceptance:**
  - `mesh new` with each launcher template, then pickup, shop purchase and drop through the real window, all work;
  - with the file deleted, the pickup is refused with a message, nothing raises, the Vendor is built, and the drop's gold still arrives;
  - `mesh new`, then MCP quest add, and the quest loads;
  - every listed template starts;
  - `list_scenes` names `packs/core_regions/scenes/start.json`;
  - mutation proof per PR.
- **Complexity:** S each (M total). **Decision:** **D7** (item scaffold policy); retiring the #656 templates is in D7's note.

### 3.3 #639a: unlocked doors stop blocking; open/used pictures apply (P1)

- **Problem / evidence:** `repro_lever_door_studio_puzzle.py`. The chain was cut in two by the gate, and all 15 solid sample gates stay solid (part D). P1 on the Studio path, with the challenge correction applied.
- **Root cause:** `DoorLock._update_collision` writes `entity.properties["solid"]`, which nothing reads. Solidity is membership of `scene_controller.solid_sprites`. `open_sprite` and `active_sprite` are stored but unused (`puzzle_behaviours.py:115-119` is a `pass`).
- **Approach:** remove the door from `solid_sprites` on unlock and re-add it on relock; apply the pictures through the asset manager; drop the `properties` write.
- **Files:** `engine/behaviours/puzzle_behaviours.py`, tests.
- **Dependencies:** none. The persistence half is 4.3. **mesh_net parity:** see 6.5.
- **Compatibility:** sample gates now open, as authored.
- **Acceptance:**
  - press, then walk through, with the real mover;
  - the gate leaves `solid_sprites`;
  - the open picture shows;
  - `starts_locked: false` never blocks;
  - the picker row flips;
  - mutation proof (restore the `properties` write).
- **Complexity:** S. **Decision:** no.

### 3.4 #640: TriggerZone sends the creator's event, and `entered_zone` once (P1)

- **Problem / evidence:** `repro_studio_picker_behaviours.py`: the configured event fires 0×, and `entered_zone` is delivered 2× (the challenge review saw a counter get +2).
- **Root cause:** `trigger_zone.py:52` reads `on_trigger` for the log line only; `:85-104` emits through both `emit_gameplay_event` and `window.emit_signal`.
- **Approach:**
  - emit `on_trigger` when it is set;
  - emit `entered_zone` once (drop `emit_signal`, as SL-2 did);
  - **keep `entered_zone`**, because the campaign wires through it;
  - align the engine doc ("Label") with Studio ("Event it sends").
- **Files:** `engine/behaviours/trigger_zone.py`, tests.
- **Dependencies:** none.
- **Compatibility:** anything counting `entered_zone` now counts once. Scan sample content for counters on `entered_zone` before merging.
- **Acceptance:**
  - the configured event fires once per entry;
  - a bus subscriber and an `on_event` listener each see one `entered_zone`;
  - two consecutive `entered_zone` quest stages advance one per entry;
  - mutation proof.
- **Complexity:** S. **Decision:** no.

### 3.5 #654: Studio's Shopkeeper opens on E (P1 recommended; disputed)

- **Problem / evidence:** `repro_shopkeeper_never_opens.py`; s1v: the obvious Studio routes (Shopkeeper only, or a talking Person plus Shopkeeper) never open the shop on any generated project. The working route (a separate Interactable with `interact_event=open_shop`) is undiscoverable, and `developer_guide.md:385` shows an event that is never sent.
- **Root cause:** Vendor listens only for a global `open_shop` (`vendor.py:50,61-63,80-84`) and has no `on_interact`. `set_choice` can't author a choice event.
- **Approach:**
  1. Vendor gets `can_interact_with` / `on_interact`, opening its own stock (respecting `shop_id`). With Dialogue present, pick and document one rule: the shop opens at the conversation's end, or on a choice (D2 note). This also fixes #663 item 2 (talk and shop opening together).
  2. `set_choice` accepts `event`.
  3. Content: the Ashen and Hollow Grove merchants get the Ridge pattern, and `showcase_interior` gets `stock`.
  4. Fix the guide example (#663 item 1).
- **Files:** `engine/behaviours/vendor.py`, `project_ops.py`, docs, sample scenes, tests.
- **Dependencies:** **after 3.2 (#652)**, without which the Vendor isn't built in created projects. #637 (4.5) removes Vendor's never-released subscription; the order doesn't matter.
- **Compatibility:** an existing `listen_event` still works.
- **Acceptance:**
  - E on a Studio-authored Shopkeeper opens its stock, and a purchase works;
  - two Vendors in one room open only their own stock;
  - the sample Ashen merchant opens;
  - the picker row flips;
  - mutation proof.
- **Complexity:** M. **Decision:** D2 (severity) and the talk-plus-shop rule (noted in D2).

---

## 5. S1-4: authored state persists; entities end cleanly

### 4.1 Per-entity "facts" in room memory (P1 enabler)

- **Problem / evidence:** rooms are rebuilt from file on every entry, and room memory stores only removed objects. `scan_instance_only_state.py` lists 29 classes with progress-like instance fields. Confirmed losses: #620, #636 `looted`, #639 door/button. Suspected: SetGameStateOnEvent `inc_counters` + `once`, and one-shot Interactables that pay out.
- **Root cause:** there is no declared model for "this already happened", per room and entity. `saveable_state` covers only the current room at save time.
- **Approach (one mechanism):**
  - room memory gains `facts[room][entity_id] = {...}`, stored in game-state vars, so saves carry it;
  - behaviours declare their fact fields;
  - the factory applies facts on construction (re-entry and load), and behaviours write facts when they change;
  - a missing record means "as authored", which keeps old saves loading.
- **Files:** `engine/scene_runtime/room_memory.py`, `scene_controller_parts/entity_factory.py`, `behaviours/base.py`, tests.
- **Dependencies:** none. 4.2, 4.3 and 4.4 depend on it.
- **Compatibility:** old saves load with "as authored"; the save format gains one optional key.
- **Acceptance:** a test behaviour's fact survives re-entry and save → load → revisit; a save made before the fact existed loads; mutation proof.
- **Complexity:** M. **Decision:** **D6** (the state model).

### 4.2 #620: "Only once" dialogue and choices stay spent (P1)

- **Problem / evidence:** `repro_dialogue_once_reward_repeats.py`; chain E: the overpayment is carried in saves.
- **Root cause:** `_has_played` and the choice-once markers live on the Dialogue instance.
- **Approach:** store them as facts (4.1), keyed by room, entity and choice.
- **Files:** `engine/behaviours/dialogue.py`, tests.
- **Dependencies:** 4.1.
- **Compatibility:** saves made before the fix carry no fact, so a reward already paid once can be paid one more time after the upgrade (once). Document this.
- **Acceptance:** re-entry and save → load → revisit pay once; the picker row flips; mutant O4 is killed (with 5.5); mutation proof.
- **Complexity:** S. **Decision:** D6.

### 4.3 #639b: door unlock and "Only once" button press persist (P1)

- **Approach:** DoorLock `unlocked` and SwitchInteract `activated` become facts (4.1).
- **Files:** `puzzle_behaviours.py`, and remove the "TODO: add save" allow-list entries in `test_save_participation_policy.py`.
- **Dependencies:** 4.1 and 3.3.
- **Compatibility:** old saves → "as authored".
- **Acceptance:** after re-entry and save → load → revisit, the gate stays open and the button stays spent. The sample Ch2 Ambush pair passes. Mutation proof.
- **Complexity:** S. **Decision:** D6.

### 4.4 #636 + #627: the chest and drops grant through the game-state inventory (P1)

- **Problem / evidence:**
  - `repro_reward_chest_grants_nothing.py`: the chest is looted and the event emitted, but potions and gold stay at 0. s1v saw the same with an item list present.
  - #627: drops lose the item when it can't be granted. With no `items.json` the gold is lost too, because `drop_table.py:119` raises before the gold line.
- **Root cause:**
  - RewardChest grants only via `interactor.inventory` (which players don't have) and `add_gold` (which doesn't exist);
  - `looted` is set first and never persisted;
  - DropTable ignores `add_item`'s result and orders the gold after the item.
- **Approach (two PRs; persistence before the grant, or the fix creates a farmable reward):**
  1. `looted` becomes a fact (4.1).
  2. Grant through `get_or_create_inventory(game_state.values)` and the `gold` counter, reusing the partial-add pattern from pickups.
     - Full inventory: don't loot, toast "can't carry", emit nothing.
     - Set `looted` and emit only after a successful grant.
     - DropTable: grant the gold independently, and leave refused items as a world pickup or a toast (decide consistently with pickups).
     - Fold in the vendor nits (`str(item_id)` at `vendor.py:107/116`).
- **Files:** `puzzle_behaviours.py`, `drop_table.py`, `vendor.py`, tests.
- **Dependencies:** 4.1 and 3.2.
- **Compatibility:** old saves → "not yet looted".
- **Acceptance:**
  - empty inventory: the item and gold arrive, then `looted`, then the event;
  - a full stack, an owned non-stackable item and an unknown id are refused cleanly;
  - a gold-only chest works;
  - re-entry and save/load don't pay twice;
  - drops with a full inventory and with no `items.json` keep the gold;
  - mutant O5 is killed;
  - mutation proof.
- **Complexity:** M. **Decision:** D6; the full-inventory rule is in D7's note.

### 4.5 Lifecycle: #637 (P2) and #638 (P3, suspected)

- **Problem / evidence:** `repro_removed_entity_keeps_listening.py`: a removed door still unlocks, and a removed counter still counts. Listeners don't multiply.
- **Root cause:** `_end_behaviours` calls only `on_destroy`, while six behaviours release in `destroy()` / `dispose()`, or never (Vendor).
- **Approach:**
  - in `_end_behaviours`, run and clear `sprite.mesh_behaviour_unsubscribes` (unsubscribe is idempotent), which covers all 12 subscribers;
  - verify #638 through real delivery, then fix or close it. NEW-3 (a self-removing entity misses its own event) is latent and masked; NEW-4 (EventLogger) can be fixed by subscribing in `__init__`.
- **Files:** `entity_factory.py`, tests.
- **Dependencies:** none. The removal contract in 5.6 generalises the test.
- **Compatibility:** the sample rusted key (SetGameStateOnEvent on a self-removing pickup) must still set its flag.
- **Acceptance:**
  - each of the six behaviours through each removal path changes nothing after removal;
  - the rusted key still works;
  - re-entry and save/load give one listener each;
  - mutation proof.
- **Complexity:** S. **Decision:** no.

---

## 6. S1-5: gates, CI trust, real-runtime contracts

These items are costed in `13_testing_ci_proposal.md`. Only `tests/`, `tooling/`, `.github/` and `pyproject.toml` change.

| Item | Problem / evidence | Root cause | Approach | Files | Deps / risks | Compat | Acceptance | Cx | Decision |
|---|---|---|---|---|---|---|---|---|---|
| **5.1 Gates fail closed: #624 B–D (P2)** | The mypy-island exits 0 when mypy can't run (`probe_gate_fail_open.py`). "Tooling unavailable" → code 0 at 7 sites in `pipeline.py`. Four steps pass silently when their input is missing. Baselines can grow in the same PR. The mypy count guard is a no-op. RUF100 is off (2,355 unchecked `noqa`) | Gates parse output and ignore return codes; ratchets compare against git-ignored state | Three PRs: (a) mypy-island reads its returncode; "tooling unavailable" is code 2; silent steps report `skipped:` and CI fails on any skip not in an allow-list. (b) Baseline-growth check against the merge base (any growth needs a `baseline-growth:` line in the PR); the mypy guard compares against the merge base's `tooling/mypy_baseline.txt`. (c) RUF100 with `lint.external` for documentation-only codes | `tooling/mypy_island.py`, `mesh_cli/verify_steps/pipeline.py`, `tooling/*_gate.py`, `pyproject.toml`, `ci.yml` | Risk: RUF100 cleanup churn (keep it to one mechanical PR) | none | Each gate has a test with the tool or input absent → nonzero; a baseline-growth PR without the marker fails | S×3 | no |
| **5.2 Lane floors: #648 (P2)** | No floor on the default suite; gpu 256 vs 621 | Floors set at lane creation and never raised | Raise gpu to about 600; `--min-selected` about 13,500 on the Windows shard check; Linux job JUnit plus the same floor via `test_tiers.lane_problems` | `ci.yml`, `extended.yml`, `test_tiers.py`, `ci_shards.py` | Risk: a legitimate test removal must lower the floor on purpose (the documented rule) | none | A selection under the floor fails (unit test); a contract test keeps each floor within 5% of collection | S | no |
| **5.3 Flake policy and quarantine (P2)** | ≈ 5% non-change failures; reruns are ad hoc; NEW-15 and the replays-job flake are untracked | No policy mechanism | Quarantine only with an issue, a dated `quarantine` baseline entry, an Extended lane that still runs and reports it, and a contract test that fails on expired or issue-less entries. No silent retries; required lanes keep `-W error`. Triage the older gate-trust issues #359, #394, #466 here | `tests/baselines/quarantine.txt`, conftest, `extended.yml`, contract test | Risk: quarantine used as a dumping ground (expiry prevents it) | none | The contract test exists; every quarantined id has a live issue and an expiry ≤ 30 days | S | **D10** |
| **5.4 Silent CI gaps: #649 (P3)** | MCP-present test always skips; pyright configured, never run, excludes mesh_net; `replays --quiet` hides the failing case | CI installs `.[dev]` only; leftover config | Install `.[mcp]` in the Linux pytest job; delete `pyrightconfig.json`; print failing replay cases on failure | `ci.yml`, `pyrightconfig.json` | none | none | The MCP test runs (not skipped) in that job's report | S | no |
| **5.5 Mutation survivors: #650 (P2)** | Q1, Q3, Q5, O1, O3, O4, V1, V2, V4 survive | Missing negative branches | About 10 assertions, each proven to kill its mutant with `mutation_probe.py` | tests only | none | none | Re-running the 8-group probe gives ≥ 36/40 killed | S | no |
| **5.6 Contract-suite completion (P2)** | 15 fake-only window attributes; 20 spec'd doubles; no removal contract; no cross-component smokes | Unspec'd doubles bless missing APIs | (a) A removal contract parametrised over every behaviour that subscribes in `__init__`. (b) `contract_gaps_real_window.py` as a meta-test: fail on a production `getattr(window, x)` for an `x` nothing creates (allow-list with issue numbers). (c) A `fake_window()` generated from a real window's attributes, plus `spec=` for entity and interactor mocks, migrated as files are touched, starting with the case-study files. (d) Smokes: a cutscene step on the real SceneController; MCP cutscene write → GameWindow | tests, `tests/_real_game.py` | After 3.0 and 4.5. Risk: the meta-test needs an allow-list for lazily created attributes | none | The meta-test is green with every allow-list entry tied to an issue; the removal contract covers all subscribers | M | no |
| **5.7 End-to-end creator workflow and template smoke (P1, verification)** | Part D's chain needed workarounds; no CI test composes creation → export | No test spans the seams | Promote `e2e_creation_to_export_chain.py` and the s1v scripts to `tests/test_e2e_creator_workflow.py` (marker `e2e`, Extended `extended` lane, both OSes). Promote `scan_project_templates.py` to a template smoke. Steps for open defects are strict-xfail with the issue number until fixed | tests, `extended.yml`, `test_tiers.py` | Lands early; goes fully green after S1-3 and S1-4. Risk: runtime (estimate 2–4 min per OS, off Extended's critical path) | none | See exit criterion E3 | M | no |
| **5.8 CI cost (P2)** | ≈ 345 job-min per merge; fast tier run twice; second verify-all in the pytest job; the same tree tested twice per merge; Windows gpu shards unbalanced | Duplicate execution (R1–R4); a stale shard plan | (a) R1: verify-all with `MESH_SKIP_PYTEST_FAST=1` in CI's `verify` jobs; R3: fold `web-smoke`. (b) R2: measure the in-suite verify-all fixture with `--durations`, then drop it from the critical path if it costs minutes. (c) R4: push-side dedup only when a green PR run tested the **identical tree** at the same workflow revision. (d) Re-split the Windows gpu plan; optionally shard Linux pytest | `ci.yml`, `extended.yml`, `tooling/extended_dedup.py`, `ci_shards.py` | R4 must keep combined-tree protection (base moved → trees differ → runs) | none | Per-merge job-min and p90 measured with `ci_timing_analysis.py` (E10) | S×4 | **D9** |

---

## 7. S1-6: bounded convergence of duplicate runtimes (P2; not exit-required)

**Rule:** contain, don't rewrite. Each item removes the demonstrated failure mode. The full merge of the duplicate stays a post-S1 option.

| Item | Problem / evidence | Root cause | Approach (bounded) | Files | Deps / risks | Compat | Acceptance | Cx | Decision |
|---|---|---|---|---|---|---|---|---|---|
| **6.1 One QuestManager: #621, #644, T-2, T-3** | #621: one event completes two stages (`repro_quest_one_event_two_stages.py`). #644: console `quest` / `quest active` / `rules` raise. T-3: warnings on every load. T-2: suspected ignored fields. Quests kill 1/5 mutants | D-1: tests and the restore code use the lightweight API | (1) GameStateController's default becomes `engine.quests.QuestManager`; move tests to it; retire the lightweight API's production callers (console, `quest_state.py` restore, golden-slice label). (2) #621: an event completes at most one stage per quest; the second pass re-checks starts only. (3) Verify T-2 and fix it, or close it | `game_state_controller.py`, `quest_manager.py`, `quests.py`, `quest_runtime/progress.py`, `console_runtime/*`, `save_runtime/quest_state.py`, about 35 test files | Risk: test churn (mechanical); dispatch Extended | quest save format unchanged | Console commands run on a real window; `handle_event` with consecutive same-trigger stages advances one; no restore warnings; Q1/Q3/Q5 killed | M | **D11a** |
| **6.2 Cutscene runtimes** | D-4: `mesh cutscene validate` accepts commands the game's schema refuses | Two runtimes, two schemas | `mesh cutscene validate/simulate` validates against `cutscene.schema.json` (the live one) first; document CutsceneRunner as the CLI/test runner. Merging the runtimes is post-S1 | `cutscene_runtime/schema.py`, `mesh_cli` cutscene command | After 1.4 and 2.4 | none | A file the game refuses is refused by `validate` | S | **D11b** |
| **6.3 Hotkeys** | D-2: 5+ shadowing incidents; #660 | Two dispatchers | A binding-matrix test: every documented binding fires under each state (game, editor, Creator Mode, pause, console), driven through `dispatch_event`. A lint that fails when one key is bound in both systems without an explicit precedence entry. Merging the dispatchers is post-S1 | tests; `input_dispatch.py` and router tables (read) | Risk: the matrix needs a states fixture | none | The matrix test exists; a deliberately shadowed binding fails it | M | **D11c** |
| **6.4 Episode harness on MagicMock windows** | D-3 / M4 D11: "integration" episodes take the GameplayEventBus route | The harness builds a `MagicMock()` window | Add one real-window episode run (hidden GameWindow) of an existing episode; label the MagicMock episodes "harness" in test names and docs so they are not counted as integration evidence. A full migration is post-S1 | `mesh_cli/episode.py`, `tests/test_episode_0*` | Risk: goldens may differ on the real route, which is itself a finding | goldens unchanged for the harness | One episode passes on a real window | M | **D11d** |
| **6.5 mesh_net shared rules: #647** | D-7: copied gate, interaction-ranking and drop rules; #647 copied into both | Copy-paste for authority-side code | mesh_net calls the engine's pure functions: DropTable normalisation (fixing #647 in both places: default only when missing or None) and `select_interaction_candidate`. Add a parity test for the gate after 3.3/4.3 (net "open for good" vs engine) | `mesh_net/scene_room.py`, `engine/behaviours/drop_table.py`, `engine/interaction.py` | Risk: the net replay goldens | net protocol unchanged | `chance: 0` never drops in either runtime; a parity test asserts one function | S–M | **D11e** |
| **6.6 Player-facing fake-only contracts: #643, #645** | #643: HUD panel never draws. #645: Continue never sees saves | `window.player`; D-5 `savegame.py` | #643: one `find_player(window)` helper (via `scene_controller._find_player_sprite`) for the HUD and the debug bundle. #645: Continue uses SaveManager (latest slot or quicksave); `savegame.py` becomes read-only import | `ui_overlays/hud.py`, `debug_bundle.py`, `main_menu_overlay.py`, `savegame.py` | none | old `save_1.json` still readable | Real window: the HUD view model shows hp/max_hp; F5 then Continue loads the quicksave | S×2 | no |
| **6.7 Flag-gated entities: #653** | Exits gated by entity-level `require_flags` appear only after re-entry (65–71 sample exits; tool-producible via `set_entity_fields`) | Documented load-time semantics | Keep the semantics. (1) `set_entity_fields` warns and points to `set_show_when` (#663 item 3 rides here). (2) A one-off script converts the sample exits to ConditionalActivator. Re-evaluating at runtime is the alternative (D14) | `project_ops.py` / authoring ops, `packs/` content, docs | Content-only risk | none | The Ambush exit appears in the same visit; a warning on the entity-level gate | S–M | **D14** |
| **6.8 Legacy editor out of game launches** | D-11: `EditorModeController` (fan-out 74) and its overlays are built in every GameWindow; #660 | Construction is unconditional | Construct the legacy editor and register its overlays only when `legacy_editor_allowed` could become true. Defence in depth after 1.1 | `engine/game.py`, `ui_dispatcher.py`, `editor_controller.py` | Risk: code reaching `window.editor_controller` in games (scan first) | editor launches unchanged | A game launch has no editor controller; F4 in a game is a no-op | M | **D3** |
| **6.9 M3/M4 owed tests and the demo world** | D9: owed tests #630 L03/L04, #634 X4/X5. D5: the M4 demo world is built from `tooling/` at run time (not in the wheel; a test imports tooling) | Review follow-ups not yet scheduled | Add the owed tests; package the demo world as data like `mesh_net/coop` and `expedition`, or state "checkout-only" explicitly (relates to #357) | `tests/test_mesh_net_*`, `tooling/m4_demo_world.py` | none | none | Each owed test kills its named mutant; the demo world loads without `tooling/` on `sys.path` (or the docs say checkout-only) | S–M | no (D1 = OD11 queue presets stays an owner decision outside S1) |

---

## 8. S1-7: optional P3 cleanup (opportunistic only)

| Item | Covers | Approach | Cx |
|---|---|---|---|
| 7.1 Fake-only P3 bundle | #646 (plugin `console` / `asset_manager`, debug panels, legacy overlays, `purge_trash`, workspace scene key, inspector history, golden-slice label, dead `saveable` helpers) | Read the real attribute or delete the dead branch; driven by the 5.6 meta-test allow-list | S–M |
| 7.2 Authoring and docs bundle | #663 (item 1 in 3.5, item 2 in 3.5, item 3 in 6.7; close when those land) | Close-out only | — |
| 7.3 Sample content | #658 (walls or tilemap around 14 walk-round gates; the model catalogue stores a basename or project-relative path) | Content PR plus a one-line provenance change | S |
| 7.4 Data-integrity P3s (part A §3) | A copied project shares its `game_id`; non-exported settings overwritten; Studio reimport rollback non-atomic (`studio_hd2d.py:2807-2823`); mesh_net owed-journal fixed temp name; launcher dump fixed `.tmp` | Unique temp names / atomic restore; `game_id` regenerated on copy detection (D-free) | S each |
| 7.5 Developer-only P3s | T-4 duplicate toast; D-9 five snap helpers (#392); D-10 three-layer persistence proxy; queued events in a door frame reach the next room (document it); QuestHook harness-only leak; a docstring for `current_scene_path` after a load | Small cleanups | S each |

---

## 9. The S1 finish line (exit criteria)

S1 is **done** when every criterion below holds at one integration commit. Technical debt is not zero at that point. Anything not listed is carried into the post-S1 backlog with an owner disposition.

| # | Criterion | Measure (concrete) | Today |
|---|---|---|---|
| **E1** | No unresolved confirmed P0 | `gh issue list` with a P0 label or title → 0 open; F4 and debug-mode keys are no-ops in an export launch (1.1, 1.2 tests) | 1 (#660) |
| **E2** | Every confirmed P1 fixed or owner-dispositioned | Each P1 in the appendix is closed by a merged PR with a real-runtime regression test and a mutation proof, **or** the issue carries a written owner disposition (deferred / won't fix, with the reason) | 12 product P1s plus #612 open |
| **E3** | Critical end-to-end workflow verified | `tests/test_e2e_creator_workflow.py` (5.7) passes in Extended on Windows and Linux for **5 consecutive integration pushes**, with **zero strict-xfail steps and zero workaround steps** (no hand-written data files, no `solid_sprites` patching). Steps: `mesh new` (each launcher template) → author through Studio ops, `mesh author` and MCP: dialogue with a once-reward, shop, chest, pickup, enemy with Health and drops, lever + gate, zone, quest, cutscene, doors to 2D and HD-2D → play via `main.py` with keys through `dispatch_event` → F5 → new process → F9 → `mesh export build` → exported play, save and reload | 6 of 11 elements broken, 1 workaround |
| **E4** | Every listed template starts | The template smoke (5.7): every id `mesh new --template` accepts starts, walks and draws | 5 of 7 |
| **E5** | Quality gates fail closed and give trustworthy results | Every gate in `03_testing_ci_debt.md` §3.4 has a test showing a nonzero exit with its tool or input absent; CI fails on any un-allow-listed `skipped:` step; baseline growth needs a PR marker (5.1) | mypy-island, 7 "unavailable" sites and 4 silent steps fail open |
| **E6** | Lane floors in place | The default suite (both OSes), gpu, extended and acceptance each have a floor ≥ 95% of the current collection, enforced by a contract test (5.2) | default suite: none; gpu: 41% |
| **E7** | No unresolved known destructive filesystem or save-data problem | #623, #631, #632, #641, #642 and #660 closed. Every legacy delete path confirms and trashes (or is disabled per D3). A re-run of the part A §3 sweep has no CONFIRMED row | 6 open |
| **E8** | Realistic runtime integration coverage for the **6 high-risk contracts** | Each has a real-window parametrised test in the required `pytest` jobs: **(1)** picker behaviour → creator-visible outcome (100% of `behaviour_guide.GUIDES` rows, or a reasoned exclusion); **(2)** entity removal → listeners released (all subscribers); **(3)** authored facts survive re-entry and save/load; **(4)** a Studio/MCP write → GameWindow opens (cutscene, quest, items); **(5)** live event delivery for runners (ActionList, cutscene) on the real SceneController; **(6)** project-root resolution with the CWD ≠ project (saves, items, cutscenes, legacy file ops). Plus: the fake-only-attribute meta-test is green, and every allow-list entry is tied to an issue | 0 of 6 |
| **E9** | CI is reliable | Attempt-1 failures not caused by the change: **≤ 2% of the last 50 integration-branch CI pushes** (today 4.1% of 49), and **0 in the last 30 Extended pushes**. Every quarantined test has an issue and an expiry (5.3) | 4.1% / 0% |
| **E10** | CI and Extended stay manageable | Over the last 30 runs at close: CI push p90 ≤ **15.7 min** and Extended push p90 ≤ **38.7 min** (today's levels; the contract and e2e tests must be offset). Per-merge cost ≤ **345 job-min** (≤ 250 if D9's dedup is approved). Measured with `docs/s1/evidence/ci_timing_analysis.py` | 15.7 / 38.7 / 345 |
| **E11** | Measured blind spots closed | A re-run of `mutation_probe.py` on its 8 groups gives ≥ 36/40 killed, and all 9 #650 survivors killed | 28/40 |
| **E12** | Owner hands-on acceptance (if D13 = yes) | The owner authors the E3 project once in the **Studio GUI** and plays it, since agents may not run visible GUI automation. Pass or fail is the owner's call; no feel or quality pass is implied otherwise | not done |

**Not required for exit:** S1-6 and S1-7. Each open P2 or P3 is carried into the post-S1 backlog with its roadmap reference.

---

## 10. Dependency summary

```
1.3 #612 (#661) ──► 1.4 #622 (#635) ──► 2.3 PR2, 2.4 #642 ──► 6.2
1.1 #660 (#662) ──► 1.2 debug keys ; 1.1 ──► 2.1 #641+#631 ──► 2.2 #632 ; 1.1 ──► 6.8
3.0 fixture ──► (all S1-3/S1-4 fix PRs adopt it) ──► 5.6 ──► 7.1
3.2 #652 ──► 3.5 #654 ; 3.2 ──► 4.4 #636+#627 ; 3.2 + S1-3 + S1-4 ──► 5.7 green (E3)
4.1 facts ──► 4.2 #620, 4.3 #639b (also after 3.3), 4.4 #636 (persistence before grant)
3.4 #640, 3.1 #651, 4.5 #637, S1-5 items: independent
Parallel PRs on puzzle_behaviours.py (3.3, 4.3, 4.4): test the combined merge tree
```

---

## Appendix: every issue and finding → roadmap item

| Issue / finding | Final sev (class) | Roadmap item | State |
|---|---|---|---|
| #660 | P0 (confirmed) | 1.1 | PR #662 in flight |
| F3 debug mode in shipped games (from #660) | P0/P1 candidate (suspected) | 1.2 | not filed; file on verification |
| #612 | P1 CI safeguard (confirmed) | 1.3 | PR #661 in flight |
| #659 | investigation (not a defect) | deferred: owner said no action authorised; measure after S1 | open |
| #622 | P1 (confirmed) | 1.4 | PR #635 approved, blocked on #612 |
| #618 | historical | 2.1 (real-window re-verification) | closed (#628) |
| #619 | historical | — (V1/V2/V4 survivors in 5.5) | closed (#625) |
| #641 | P1 (confirmed) | 2.1 | open |
| #631 | P1 (confirmed) | 2.1 | open |
| #632 | P2 (confirmed) | 2.2 | open |
| #623 | P1 recommended / P2 (confirmed; disputed) | 2.3 | open |
| `cutscenes.json`, item DB, `savegame.py`, `ai_history` CWD reads | architectural risk | 2.3 | not filed |
| #642 (T-1) | P1 (confirmed) | 2.4 | open |
| #651 | P1 (confirmed) | 3.1 | open |
| #652 | P1 (confirmed) | 3.2 | open |
| #655 | P2 (confirmed) | 3.2 | open |
| #656 | P2 (confirmed) | 3.2 | open |
| #657 | P3 (confirmed) | 3.2 | open |
| #639 | P1 (confirmed) | 3.3 (solidity, pictures) + 4.3 (persistence) | open |
| #640 | P1 (confirmed) | 3.4 | open |
| #654 | P1 recommended / P2 (confirmed; disputed) | 3.5 | open |
| #620 | P1 (confirmed) | 4.2 | open |
| #636 | P1 (confirmed) | 4.4 | open |
| #627 | P2 (confirmed without items; suspected when full) | 4.4 | open |
| #637 | P2 (confirmed) | 4.5 | open |
| #638 | P3 (suspected) | 4.5 | open |
| #624 | A historical (#633); B P2/P3; C/D P2 (confirmed) | 5.1 | open |
| #648 | P2 (confirmed) | 5.2 | open |
| NEW-15 ownership-race flake; replays-job flake | suspected | 5.3 | tracked in #649 |
| #649 | P3 (confirmed) | 5.4 | open |
| #650 | P2 (test gap) | 5.5 | open |
| 15 fake-only window attributes (class) | architectural risk | 5.6 (meta-test) | — |
| #621 | P2 (confirmed) | 6.1 | open |
| #644 | P2 (confirmed) | 6.1 | open |
| T-2 quest `emit_events_on_complete`, reward gold/xp | P2 (suspected) | 6.1 | not filed |
| T-3 restore warnings | P3 (architectural, cause found) | 6.1 | not filed |
| D-1 two quest managers | architectural risk | 6.1 | — |
| D-4 two cutscene runtimes | architectural risk | 6.2 | — |
| D-2 two hotkey systems | architectural risk | 6.3 | — |
| D-3 / M4 D11 episode harness on MagicMock | architectural risk | 6.4 | — |
| #647 | P3 (confirmed) | 6.5 | open |
| D-7 mesh_net duplicating engine rules | architectural risk | 6.5 | — |
| #643 | P2 (confirmed) | 6.6 | open |
| #645 / D-5 two save systems | P2 (confirmed) | 6.6 | open |
| #653 | P2 (confirmed; was P1) | 6.7 | open |
| D-11 legacy editor built into every window | architectural risk | 6.8 | — |
| M4 D9 owed tests (#630 L03/L04; #634 X4/X5) | known, owed | 6.9 | — |
| M4 D5 demo world needs `tooling/` (+ #357) | architectural risk | 6.9 | — |
| M4 D6 probe/proxy world-assembly duplication | architectural risk | deferred (folds into D5's packaging) | — |
| M4 D1 queue presets (OD11) | known limitation | deferred: owner decision OD11 pending, outside S1 | — |
| M4 D2, D3, D4, D8 | known limitations | deferred: before any public deployment | — |
| M4 D10 / #496 items 2–6 | known limitations | deferred (prototype); item 1 historical (#510) | open |
| #646 | P3 (confirmed) | 7.1 | open |
| #663 | P3 (confirmed) | 7.2 (items ride in 3.5 and 6.7) | open |
| #658 | P2 content / P3 | 7.3 | open |
| Part A P3s: `game_id` copy, settings overwrite, reimport rollback, owed journal temp name, launcher dump | P3 (architectural) | 7.4 | not filed |
| T-4 duplicate toast | P3 (suspected) | 7.5 | not filed |
| D-9 snap maths (#392), D-10 persistence proxy | P3 (architectural) | 7.5 | #392 open |
| Queued events in a door frame (part B §3.3) | P3 (confirmed semantics) | 7.5 (document) | not filed |
| QuestHook harness-only leak | P3 (architectural) | 7.5 | not filed |
| `current_scene_path` after a load | not a defect | 7.5 (docstring) | — |
| D-6 three inventory paths | architectural risk | 4.4 | — |
| D-8 removal funnel | keep single (no action) | — | — |
| `project_ops` / Studio / HD-2D change hub; scene-controller sprawl | architectural risk | deferred: no defect traced to it; watch | — |
| Studio `project_save` not crash-safe; `--force` by design; exports need deps; dev saves not visible to the export; multiplayer only packaged scenes; ToggleSwitch fixed event; TriggerVolume per-visit once | known limitations | deferred (by design) | — |
| Two mesh_net servers on one store | suspected | deferred (prototype) | not filed |
| Legacy editor full retirement (#347 migration list) | architectural | deferred: post-S1 (D3) | — |
| #347 | historical (merged PR; its gate never worked by key, see #660) | 1.1 | merged |
| #629 (draft PR, independent audit) | evidence | D8 (merge as historical evidence); its 8 findings are mapped in `10_health_report.md` §5 | draft |

**Open issues outside S1-0's scope (not re-verified; listed so nothing is lost):**

| Issue | Disposition |
|---|---|
| #359 (stale replay goldens), #394 (release pipeline verify-demo), #466 (test-order dependence) | triage in 5.3 (gate trust): if still present, fold into 5.1 or 5.3 |
| #357 (pip-installed Mesh imports `tooling/`) | with 6.9 |
| #392 (op registry, module sizes, placement maths) | 7.5 for the snap maths; the rest deferred |
| #373 (Windows pytest-fast budget) | check against 5.8 (R1 removes pytest-fast from `verify`) |
| #603, #461, #460, #458, the older HD-2D items (#375, #381, #390, #391, #393, #396, #365), #398, #462, #449, #422 | deferred: feature or visual backlogs, not S1 reliability; #422 and #449 are roadmap trackers that S1 supersedes for their reliability parts |
