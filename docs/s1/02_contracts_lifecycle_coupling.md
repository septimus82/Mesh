# S1-0 part B: runtime contracts, Studio-authored gameplay, lifecycle, duplication and coupling

Checked against **`9d3580b9`** (`redesign/visual-editor`, after #633), on top of part A (`f8efb42a`, `docs/s1/01_audit_reconciliation.md`). Investigation only: no production code changed.

**Method** (same rules as part A):
- Every script ran one at a time with `py -3.13` and `PYTHONPATH=<this worktree>`. Each run printed `engine from Mesh-S10/engine/__init__.py`.
- Real-runtime evidence uses a real GameWindow that is hidden, muted and never activated (`docs/s1/evidence/_hidden_game.py`, from part A). It also uses the real scene loader, interaction path (`engine.interaction.perform_interaction`, what the interact key calls), per-frame update (`window.on_update`), collision mover and save/load.
- Static scans are pure AST or git; they import nothing from the engine.
- Output quoted below is trimmed to the lines that matter. Temp paths are shortened to `<tmp>`.
- **Severity scale:** as in part A. P0 is data loss or a crash on the main path. P1 is a wrong outcome or irreversible loss on a supported path; by the #618/#631 convention, P1 also covers irreversible loss on a reachable non-main path. P2 is a limited path or a recoverable outcome. P3 is latent, cosmetic or developer-only.
- **Classes used:** CONFIRMED, ARCHITECTURAL RISK, SUSPECTED, KNOWN LIMITATION, HISTORICAL, plus DISPROVED for suspects that a real window ruled out.

**No P0 found.** Six new P1 candidates, each in §5:
- NEW-5: DoorLock;
- NEW-6: TriggerZone;
- NEW-7: legacy file ops resolve paths against the CWD;
- T-1, now confirmed end to end;
- the persistence half of NEW-5;
- the #618 re-qualification inside NEW-7.

Already-tracked items are cited, not re-reported: #618–#624, #627, #631, #632, #636 (= part A NEW-1), #637 (= NEW-2), #638 (= NEW-3/NEW-4), #612.

### Evidence scripts (`docs/s1/evidence/`)

| Script | Kind | Exit |
|---|---|---|
| `_contract_scan.py` | helper: AST collectors for production fallbacks, direct reads, window writes and test-fake attributes | — |
| `contract_gaps_real_window.py` | §1: production `getattr`/`hasattr` fallbacks vs a real constructed GameWindow (and five other runtime objects) vs test fakes | 1 (15 fake-only names) |
| `repro_fake_only_window_contracts.py` | §1: HUD, console, plugin API, debug panels, menu overlays on a real window | 1 |
| `repro_legacy_file_ops_wrong_root.py` | §1/§5: legacy editor file ops (NEW-7) | 1 |
| `repro_mcp_cutscene_blocks_start.py` | §2: T-1, from an MCP op to a project that cannot open | 1 |
| `repro_lever_door_studio_puzzle.py` | §2: the "Button" + "Locked until an event" puzzle (NEW-5) | 1 |
| `repro_studio_picker_behaviours.py` | §2: TriggerZone, ToggleSwitch, door transition, Timer, counter | 1 (TriggerZone) |
| `scan_behaviour_test_coverage.py` | §2: which picker behaviours any real-window test names | 0 |
| `scan_instance_only_state.py` | §3: behaviour progress kept only on the instance (#620/#636 pattern) | 0 (candidate list) |
| `probe_event_delivery_semantics.py` | §3: queued delivery latency, room transfer, load | 0 (probe) |
| `repro_two_save_systems.py` | §4: the legacy main menu's Continue | 1 |
| `scan_coupling.py` | §4: size, fan-in/out, co-change | 0 |

Each script makes its own temp folder (removed afterwards), contains no personal paths and changes nothing outside its temp folder. `repro_legacy_file_ops_wrong_root.py` changes directory into its temp folder only for the file-op calls, and changes back.

---

## 1. Real runtime vs test-double contracts

### 1.1 How it was measured

`contract_gaps_real_window.py` works in four steps:
1. It collects, statically, every `getattr(<window-like>, "name", ...)` / `hasattr(...)` in `engine/`, `mesh_net/` and `mesh_cli/`: **1644 reads of 267 names**.
2. It builds a real hidden GameWindow, loads a scene with a player and ticks `on_update` three times.
3. It checks which names the real window has.
4. It cross-references the missing names with what tests give their fakes. The fakes counted are **133 MagicMock windows, 390 SimpleNamespace windows and 255 fake `*Window*` classes in 540 test files**. The counts are higher than the earlier triage's because nested `window=SimpleNamespace(...)` keyword arguments are counted too.

Result:
- The real window lacks **62** of the 267 names.
- Most of those are created lazily on first use (`window.x = ...` somewhere in production), which is fine behind a fallback.
- **15 names are never created on any window by production, yet test fakes supply them.** Each one is a feature that works under test doubles and is off, silently, in the game.
- The same scan over five other runtime objects is at the end of §1.3.

### 1.2 Suspects from the triage: confirmed or disproved against the real window

| Suspect | Real window has it? | Production reads (fallback) | Effect in the real game | Class / Sev |
|---|---|---|---|---|
| `window.player` | **no**. The player comes from `scene_controller._find_player_sprite()` | `hud.py:867` (PlayerHUD `_draw_stats`, every frame), `debug_bundle.py:449`, `interaction.py:396` (last-resort fallback only) | **The HUD health/level panel never builds**, even for a player with Health. `repro_fake_only_window_contracts.py`: `player sprite found by the scene: Hero \| window has 'player': False` / `A) HUD view model after _draw_stats: None`. The per-entity HealthBar (`hud.py:268`) still draws. 4 test files give fakes a `player` | **CONFIRMED, P2 (NEW-8)** |
| `window.editor` | **no** (real: `editor_controller`, which has `.workspace`) | `main_menu_overlay.py:209,247,1211`, `pause_menu.py:147` | The `editor.workspace` branch (recent projects, settings save through the workspace) is dead. The fallback (global recent-projects list, `save_runtime_settings`) is what always runs. Only a fake (1 test file) reaches the other branch | CONFIRMED dead branch, P3 |
| `window.editor_mode_controller` | **no** | `menu_bar_overlay.py:41`, `context_menu_overlay.py:38` | Both overlays are registered on every window (`ui_dispatcher.py:157-163`) and return at once from `draw()`. The legacy editor's `context_menu` modal layer is registered with no draw handler (`editor_panels_controller.py:150`) | CONFIRMED no-op overlays, P3 (legacy editor, #347). The visual consequence in the legacy editor was not checked |
| `window.dialogue_controller` | **no** | `capture_runtime.py:40`, `capture_key_router_handlers_global.py:90`, `providers.py:1219` | Dead check only. The live block comes from `ui_controller.input_blocked` (`ui_controller.py:124`: any UI element with `blocks_input`, the dialogue box included) | **DISPROVED** as a defect (dead code) |
| `window.quest_runner`, `window.cutscene_runner` | **no** (real: `quest_manager`, `cutscene_controller`) | `debug_panels_state.py:26,39,100` | The debug panels' quest diagnostics and cutscene inspector are always empty: `D) debug quest diagnostics: [] \| cutscene state: ({'script_id': '', 'is_running': False, ...` | CONFIRMED, P3 (dev tool) |
| `window.digest_tracker` / `world_digest_tracker` | **no** | `debug_bundle.py:191-192` | The debug bundle has no digest section | CONFIRMED, P3 |
| `window.gameplay_event_bus` | **no**, by design. Only the episode harness (`mesh_cli/episode.py:565`) and `tooling/campaign_replay.py:76` create it | `quest_hook.py:184,191`, `hud.py:984`, `puzzle_behaviours.py:36`, `event_emit.py:43`, debug panels | Code branches on its presence: events go to the GameplayEventBus under the harness and to MeshEventBus in the game. QuestHook documents this (`quest_hook.py:182-183`) | **DISPROVED** as a missing attribute. It is an ARCHITECTURAL RISK as a second runtime (§4.1, D-3) |

Other fake-only names found by the scan (beyond the suspects):

| Name | Production read | Effect | Class / Sev |
|---|---|---|---|
| `repo_root` (15 reads; 6 test files supply it) | `editor_file_ops_controller.py:180,250,489,708,789,967,1030,1121,1132,1216,1283`, `editor_providers_controller.py:57`, `editor_search_controller.py:274,316`, `editor_workspace_controller.py:349` | The legacy editor's file operations either do nothing or work on the **CWD** instead of the project. See **NEW-7** | **CONFIRMED, P1** |
| `console`, `asset_manager` | `plugin_system.py:113,125` (PluginContext properties) | The plugin API's `ctx.console` and `ctx.asset_manager` are always None (real names: `console_controller`, `assets`). Output: `C) PluginContext.console=None (window.console_controller exists: True) \| asset_manager=None (window.assets exists: True)` | CONFIRMED, P3 (the plugin track is parked) |
| `current_scene_key` | `editor_workspace_controller.py:281` | The legacy workspace snapshot always records `scene_id = None` | CONFIRMED, P3 |
| `particle_system`, `particle_seed`, `dialogue_box`, `ui`, `solid_sprites` | fallback chains whose *first* lookup uses the real name (`particle_manager.system`, `engine_config.particle_seed`, `ui_controller.dialogue_box`, `scene_controller.solid_sprites`) | none | **DISPROVED**. `conditional_activator.py:121-122` records that `solid_sprites` *was* this bug ("looking for it on the window (which has none) made hiding a solid object leave it blocking the way"): HISTORICAL |

Plain `window.<attr>` loads (not fallbacks) that the real window lacks: one, `console_runtime/commands.py:335` `c.window.collision_rules`. The dev console's `rules` command raises AttributeError (P3, folded into NEW-9).

### 1.3 QuestManager: the game's vs the tests'

- **Live:** `GameWindow.__init__` builds `engine.quests.QuestManager` and puts it into `game_state_controller.quests` (`game.py:533-537`).
- **Default:** `GameStateController.__init__` itself builds the lightweight `engine.quest_manager.QuestManager` (`game_state_controller.py:97`).
- **So:** every test that builds a GameStateController without a GameWindow (the MagicMock-window pattern) exercises the lightweight manager. About 35 test files reference it (the largest is `test_save_entity_quest_state.py`, 9 sites).

Public API that only the lightweight manager has: `register_quest`, `get_quest`, `get_quests_by_state`, `fail_quest`. Production callers of that API, on the real (full) manager:

| Caller | Effect | Class / Sev |
|---|---|---|
| Console `quest` (lists `q.title`) and `quest active` (`get_quests_by_state`), `console_runtime/handlers.py:149-166` | `B) console 'quest': raised AttributeError: '_QuestStateView' object has no attribute 'title'` / `B) console 'quest active': raised AttributeError: 'QuestManager' object has no attribute 'get_quests_by_state'`. The exception leaves `ConsoleController.execute_command`; no handler was found between the Enter key (`console_controller.py:85-88`, `capture_runtime.py:81-82`) and it (code read) | **CONFIRMED, P2 (NEW-9)** |
| `save_runtime/quest_state.py:364-405` (`get_quest` / `_quests` / `register_quest`) | Falls through to the warning `save.restore.quest_manager_missing_register`. This is triage **T-3** (spurious warnings), now with its cause: the restore code targets the lightweight API | ARCHITECTURAL RISK (code + real-object scan), P3 |
| `ui_overlays/golden_slice.py:818` | The active-quest label is always empty | CONFIRMED by scan, P3 |

### 1.4 Other runtime objects (same scan, real objects from the real window)

| Object | Fallback names read | Missing on the real object | Notes |
|---|---|---|---|
| SceneController | 39 | 10 | All are fallback chains or reads of scene *documents* that share the variable name `scene` (encounter_report). **`find_sprite` (#622 B) is a direct call, not a fallback, so it is not in this table.** #622 is tracked |
| GameStateController | 4 | 0 | — |
| QuestManager (engine.quests) | 9 | 4 | `_quests`, `get_quest`, `register_quest` (T-3 above), `get_quests_by_state` (golden slice) |
| MeshEventBus | 9 | 2 | `get_history`, `get_entity_history` (`editor/behaviour_inspector.py:300,306`): the GameplayEventBus API, so the inspector's event history is empty in the game (P3) |
| player MeshEntitySprite | 10 | 2 | `inventory` (`puzzle_behaviours.py:286` = **#636**), `current_hp` (a monster-battle fallback) |
| Studio (static: `engine/studio*.py`) | 5 | 0 | No fake-only Studio attribute gates production code |

Inventory: three access paths are covered in §4 (D-6). Event bus: the duplicate delivery and room-transfer behaviour are in §3.

### 1.5 Ranking (risk = reachable on a supported path × silent)

1. **`repo_root`** (NEW-7, P1): legacy editor delete/rename/move work on the wrong folder, or do nothing; irreversible.
2. **The `interactor.inventory` family** (#636, tracked): rewards silently lost.
3. **`window.player`** (NEW-8, P2): HUD panel never shows.
4. **Lightweight-only quest API** (NEW-9, P2 and T-3): console exceptions, warnings on every load.
5. **`gameplay_event_bus` branching** (risk): two event routes; the episode-harness "integration" tests take the other one (§4 D-3).
6. Plugin API, debug panels, legacy overlays, workspace scene key (P3).

### 1.6 Smallest set of contract tests or shared fakes that would have caught #619/#620/#622/#636/#637 (and the new ones)

Not thousands of tests: five pieces, each reusing machinery the repo already has (`tests/_game_window_live.py`, `tests/_b01_arena.py`, `tests/test_state_lifecycle.py`, and this folder's `_hidden_game.py`).

1. **One shared real-window fixture** (`real_game(scenes)`: hidden, muted, throwaway scenes, as `_hidden_game.py` does), with three helpers:
   - `interact(window)` → `perform_interaction(window, actor=player)`;
   - `frames(n)` → `window.on_update`;
   - `revisit(room)` → leave and re-enter.
   Today 49 of 2027 test files use a real window at all (`scan_behaviour_test_coverage.py`).
2. **One parametrised "picker behaviour" contract test** over `behaviour_guide.GUIDES`. For each row:
   - author the behaviour through `project_ops` (the Studio path);
   - load it in the real window and drive its trigger (interact, emit, walk, or wait);
   - assert the creator-visible outcome (game state, `solid_sprites`, inventory, the configured event fired);
   - then `revisit` and save → load, and assert the declared persistence rule.

   About 15 rows. It catches:
   - #620 (once-only dialogue), #622 A (ActionList via live delivery), #636 (chest);
   - #619 (Vendor with a full stack);
   - NEW-5 (door still blocks; state lost), NEW-6 (zone event never fires).
3. **One removal contract**, parametrised over every behaviour that subscribes in `__init__` (the list in §3.2): spawn, `remove_from_sprite_lists()`, then assert the bus listener count is back to baseline and an emit changes nothing. It catches #637 and future behaviours, with no per-behaviour test.
4. **Spec'd fakes plus a meta-test.**
   - Replace bare `MagicMock()` windows, entities and interactors with `create_autospec(GameWindow, instance=True)`, `spec=` the real sprite class, or a fake built from a manifest of real attributes.
   - Add `contract_gaps_real_window.py` as a test: fail when production reads `getattr(window, "x")` for an `x` no production code ever creates on a window.

   Spec'd fakes would have made `interactor.inventory` (#636) and `window.repo_root` (NEW-7) raise in the very tests that blessed them (`test_puzzle_behaviours.py:50-62`; the #618 verification's `SimpleNamespace(repo_root=...)`). The meta-test catches NEW-8, the plugin and debug-panel gaps, and the next one.
5. **Two cross-component smoke tests:**
   - `CutsceneController.update` against the real SceneController with a `move_entity` step (catches #622 B);
   - an MCP `apply_ops` cutscene edit followed by `GameWindow(...)` in that project (catches T-1).

   Run the existing quest tests against `engine.quests.QuestManager` (retiring the lightweight manager, internal task #128). That catches NEW-9 and keeps #621 visible.

---

## 2. Studio-authored gameplay: does what Studio offers work at runtime?

Sources walked:
- `engine/behaviour_guide.py` (the picker: 46 guided behaviours plus `ADVANCED`);
- the inspector's toggles (`project_ops.set_conversation/set_choice/set_trigger_zone/set_door/set_solid/set_room_music/set_weather/add_light`, ...);
- the MCP write ops (`engine/mcp_server/tools.py` `_WRITE_SPECS`, `ai_ops.AIOps`).

Column meanings:
- **Live handler:** the runtime code that acts on the authored data exists on the live path and was seen working (run) or read.
- **Persists:** across room re-entry (R) and save → load (S), where the feature implies it should.
- **Real-runtime test:** a test that names the behaviour and uses a real GameWindow (`scan_behaviour_test_coverage.py`; approximate, so a 0 is the signal).

| Feature (Studio name) | Live handler | Persists R / S | Real-runtime test | Status |
|---|---|---|---|---|
| Dialogue lines (Talk / Dialogue tab) | yes (run, part A #620 repro) | n/a | 1 (`test_runtime_diagnose.py`) | works |
| Choices (`set_choice`) | yes | n/a | via the #620 repro only | works |
| "Only once" / "Choice once" (`set_conversation(once)`, `set_choice(once)`) | yes within a visit | **no / no** | 0 | **#620 (tracked, P1)** |
| Shop (Shopkeeper / Vendor) | yes (run, part A) | stock: not checked | 0 | #619 fixed; Vendor removal leak = #637 |
| Treasure chest (RewardChest) | grants nothing | no / no | 0 | **#636 (tracked, P1)** |
| Door to another room (SceneTransition; `set_door`) | yes (run): `door handled=True now in: shed` | n/a | 2 (`test_n1_player_hp_across_rooms.py`) | works |
| Locked until an event (DoorLock; `set_solid`) | unlock fires, but **the door keeps blocking**; "Picture when open" never applied | **no / no** | 0 (unit tests on MagicMock only) | **NEW-5 (P1)** |
| Button (SwitchInteract): "Only once", "Picture once used" | event fires (run) | **"Only once" no / no**; the picture is never applied (`puzzle_behaviours.py:115-119`: a `pass`) | 0 | **NEW-5 (P1, same fix)** |
| Lever or switch (ToggleSwitch) | yes (run): `handled=True state=True switch_toggled=1` | state no / no (allow-listed as "visual") | 1 | works. KNOWN LIMITATION: it always sends the generic `switch_toggled` and the creator can't choose an event |
| React when someone comes near (TriggerZone): "Event it sends" | **the configured event is never sent**. It always sends `entered_zone`, **twice** | n/a | 0 | **NEW-6 (P1)** |
| React when something enters an area (TriggerVolume; Studio's zone tool `set_trigger_zone`) | yes (code; tests 23, real-window 0) | `one_shot` per visit | 0 | works (read); per-visit "once" |
| Give a quest (QuestGiver) | yes (subscribes; teardown on removal B-05) | quest state in game state: yes | 1 | works (read); #621 tracked |
| Quest stages / progress (quests.json, QuestProgressOnEvent, QuestHook) | yes, via `GameStateController.handle_event` (queued) | yes (game state) | 0 for QuestProgressOnEvent/QuestHook | #621 tracked; NEW-3 (#638) self-removal |
| Start a cutscene (CutsceneTrigger) + cutscenes.json | trigger yes; `move_entity`/`camera_focus`/targeted `start_dialogue` raise | n/a | 1 (teardown only) | **#622 B (tracked)** |
| Cutscene authored through MCP (`add_cutscene` / `insert_cutscene_step`) | **writes unvalidated steps; the project then cannot open** | — | 0 | **T-1 CONFIRMED (P1)** |
| Action lists (ActionListRunner) | inert on the live path | — | 0 | **#622 A (tracked)** |
| Set a flag when something happens (SetGameStateOnEvent) | yes | flags yes; `once` per visit (idempotent for flags) | 1 | works; #637 on removal |
| Counters (IncrementCounterOnEvent) | yes (run): `pings counter after one ping: 1.0` | counter yes | 2 | works; #637 on removal |
| Timer | yes (run): `'ding' after 10 frames: 1x` | per visit | 1 | works |
| Room transitions (world links, spawn) | yes (run) | n/a | yes | works |
| Room music (`set_room_music`) | yes (`scene_lifecycle_controller.apply_scene_music`, read) | per room | not scanned | works (read; never played aloud, by rule) |
| Weather / particles (`set_weather`, `set_particles`) | yes (`scene_particles`, renderer; read) | per room | not scanned | not run |
| Room lights (`add_light`, `set_room_lighting`) | yes (LightManager; read) | per room | not scanned | not run |
| Switch the room's lights (ToggleSceneLights) | yes (read; `on_destroy` B-05) | toggled state per visit | 0 | not run |
| Enemies / combat (Health, EnemyAI, Combat, DamageOnTouch, DropTable, GrantExperience) | yes (many real-window tests: Health 9) | defeated enemies stay removed (room memory) | yes | works; #627 drops (tracked) |
| Show only when flags allow (ConditionalActivator) | yes (`solid_sprites` fix is HISTORICAL) | flags yes | 1 | works |

**Broken rows:** #620, #636, #622 A/B and #621 (all tracked), plus three new ones:
- **NEW-5:** DoorLock blocks after unlocking; DoorLock and SwitchInteract forget their state on re-entry and load; two picture settings do nothing.
- **NEW-6:** TriggerZone never sends the creator's event, and sends `entered_zone` twice.
- **T-1:** confirmed end to end.

### 2.1 T-1 end to end (CONFIRMED)

`repro_mcp_cutscene_blocks_start.py`:
1. Creates a project with the real scaffold (`create_project(..., "blank")`).
2. Calls the MCP tool function `engine.mcp_server.tools.apply_ops([{"type": "add_cutscene", "id": "intro", "steps": [{"type": "fade_to_black"}]}], root=project)`.
3. Constructs a real hidden GameWindow with the CWD set to the project, as `mesh play` / `mesh edit` do (`game_launch.py:41-42`).

```
MCP apply_ops ok: True | op: [('add_cutscene', True, "Added cutscene 'intro'")]
MCP validation ok: True
cutscenes.json now: {'cutscenes': [{'id': 'intro', 'steps': [{'type': 'fade_to_black'}]}]}
GameWindow constructor: raised SchemaValidationError: Schema validation failed for 'cutscenes.json' against
'cutscene.schema.json' at '/cutscenes/0/steps/0': 'duration' is a required property
DEFECT REPRODUCED: an MCP cutscene edit that reported success makes the project unopenable
```

Root cause:
- `ai_ops.py:587-604` (`add_or_update_cutscene`) and `:616-636` (`insert_cutscene_step`, which checks only that `"type"` is present) write without schema validation.
- `apply_ops`' validation pass (`tools.py:722-725`, `run_validation`) does not look at `cutscenes.json`.
- `game.py:592-595` catches only `FileNotFoundError`.
- `game_launch._run_owned_editor` (`:82`) constructs the same GameWindow. So by code reading **Studio and the legacy editor cannot open the project either** (the editor launch was not run).
- Side note (ARCHITECTURAL RISK): `load_from_file("cutscenes.json")` is CWD-relative (`cutscene_controller.py:54`), the #623 family. A game started with a CWD that is not the project reads another folder's `cutscenes.json`.

---

## 3. Entity and event lifecycle

### 3.1 Hook map (who calls what on the live path)

| Hook | Defined in behaviours | Called by (engine) | Notes |
|---|---|---|---|
| `__init__` | all | `entity_factory._create_behaviour_instances`, inside `event_bus.record_subscriptions()` (`entity_factory.py:204-213`) | Every bus subscription made here is recorded per sprite (`mesh_behaviour_unsubscribes`) and per scene (`track_scene_subscription`) |
| `on_destroy` | 7 | `entity_factory._end_behaviours` (`:49-65`) on every removal path (part A list) | the only end hook the runtime calls |
| `destroy` | 4 (DoorLock, RewardChest, SetGameStateOnEvent, IncrementCounterOnEvent) | **nobody** (the only `.destroy()` calls in engine are Tk roots: `studio_ui.py:271`, `clipboard.py:49`) | #637 |
| `dispose` | 1 (MessageOnZoneEnter) | **nobody** | #637 |
| `on_added` / `on_removed` | 1 (EventLogger) | **nobody** | #638 (NEW-4) |
| `start` | 6 (DialogueRunner, MainMenu, PatrolPath, SequencePlayer, Timer, Wander) | ActionListRunner (`:418,452`, itself inert, #622 A), CutsceneController `start_dialogue` (`:241`, #622 C) | Timer/Wander/PatrolPath also self-start (`auto_start`) |
| room exit | — | `scene_lifecycle`: `remember_removed` (room memory), then the scene's tracked unsubscribes, then layers cleared | listeners do not multiply (part A) |
| room enter | — | full rebuild from the authored file; `room_memory.removed_ids` filters removed objects | **behaviour state is not carried over** (§3.4) |
| save | `saveable_state` (14 classes) | `save_runtime/entity_state.serialize_entity` (`:370-391`), **current room only** | `extract_saveable_state` / `apply_saveable_state` in `behaviours/saveable.py` have no callers (dead helper API) |
| load | `restore_state` (14) | `entity_state.apply_entity_state` (`:589-596`), current room only | the queue of undelivered events is cleared (§3.3) |
| live edit / hot reload | `on_config_updated` (Dialogue) | authoring live ops (7 callers); `_rebuild_behaviours_for_sprite` runs the old unsubscribes first (`entity_factory.py:203-206`) | F7 reload rebuilds the scene |

### 3.2 Subscribe/unsubscribe pairing, extended beyond #637

AST scan of every `.subscribe(` / `.subscribe_all(` in `engine/behaviours/`:
- **12 behaviours subscribe in `__init__`:** CutsceneTrigger, DropTable, GrantExperience, IncrementCounterOnEvent, MessageOnZoneEnter, DoorLock, RewardChest, QuestGiver, SceneExit, SetGameStateOnEvent, ToggleSceneLights, Vendor. All are recorded by the scene, so the one-loop fix proposed for #637 (run `mesh_behaviour_unsubscribes` in `_end_behaviours`) covers every one of them.
- **Two subscribe outside `__init__`:**
  - `EventLogger.on_added` (never called, #638);
  - `QuestHook._subscribe` (`quest_hook.py:191-196`), which subscribes only to the episode harness's GameplayEventBus and is unrecorded. It can leak under the harness only. P3, ARCHITECTURAL RISK.
- **Window-level subscribers** (`game.py:691-698`, `plugin_system.py:26`, `tooling/trace_command.py:23`) live as long as the window: correct.

No other unpaired live-path subscription found.

### 3.3 Event delivery semantics (`probe_event_delivery_semantics.py`)

One `event_bus.emit` reaches listeners two ways:
1. **Bus subscribers run synchronously** inside `emit()`.
2. **`on_event` behaviours and the quest manager are queued.** `on_any_event` appends to `window._mesh_event_queue` (`game_runtime/events.py:76-78`). The queue is drained on the *next* `on_update`, after the scene update that applies a pending room change (`tick.py:241` then `:269-279`).

```
1) bus events seen after emit / after frame 1 / 2 / 3: [['ping'], ['ping', 'pong'], ['ping', 'pong', 'pang'], ...]
2) now in: shed | events after the transition: ['knock', 'heard_in_shed']
3) knock emitted just before load_game; events after the load: ['knock']
```

- **Latency:** each `on_event` hop costs one frame. That is by design, but a chain of N relays takes N frames, and a self-removing entity misses its own event (#638).
- **Room transfer (CONFIRMED, P3):** an event emitted in the same frame as `queue_scene_change` is delivered to the **new room's** `on_event` behaviours. The room where it happened never sees it.
  - Shown: `heard_in_shed`, never `heard_in_yard`.
  - Only `request_scene_change` / reload clears the queue (`scene_lifecycle_controller.py:173`, `scene_runtime/transitions.py:203`); door changes (`queue_scene_change` → `_perform_scene_change`) do not.
  - The quest manager still receives the event (it is global), so quests are unaffected.
  - Impact: per-room reactions (Dialogue `start_event`, QuestProgressOnEvent filters, EmitEventOnEvent) can fire in the wrong room, or not at all, when the triggering event coincides with a door. Not seen in shipped content; no shipped pattern was searched for.
- **Load:** an event queued just before a load is dropped for everyone, quests included. That is correct: it belonged to the replaced session.
- **Duplicate delivery (CONFIRMED, part of NEW-6):** TriggerZone emits `entered_zone` through `emit_gameplay_event` *and* `window.emit_signal` (`trigger_zone.py:85-104`), so every listener gets it twice (`'entered_zone' delivered 2x for one entry`). It is the only behaviour that emits through both paths (scan).
  - Counters on `entered_zone` count twice.
  - A quest with two consecutive `entered_zone` stages completes both at once (the #621 shape).
  - SetGameStateOnEvent already guards against bus + queue double delivery (`subscribed_event_types`, SL-2), so that path does not double.

### 3.4 State that should persist but lives only on behaviour instances (the #620/#636 pattern)

What persists:
- a room is rebuilt from its file on every entry;
- room memory remembers **only removed authored objects** (`scene_runtime/room_memory.py`);
- flags, counters and vars persist;
- `saveable_state` covers only the room the save was made in.

So any "this already happened" fact kept in `self.<field>` is forgotten on re-entry. It is also forgotten on load when the save was made elsewhere (and, for a class with no `saveable_state`, always). `scan_instance_only_state.py` lists 29 classes that set progress-like fields outside `__init__`. Triaged:

| Class (field) | What is forgotten | Writes game state? | Status |
|---|---|---|---|
| Dialogue (`_has_played`, once) | once-only conversation and choice rewards | rewards yes, the once fact no | **#620 (tracked)** |
| RewardChest (`looted`) | looted | no | **#636 (tracked)** |
| **DoorLock (`locked`)** | unlocked | no (`saveable_state` absent; allow-listed "TODO: add save", `test_save_participation_policy.py:31`) | **CONFIRMED (NEW-5)**: `after leaving and re-entering: door locked: True`; `after loading a save made after the unlock: door locked: True` |
| **SwitchInteract (`activated`, "Only once")** | the press | no (allow-listed as "visual", but it gates `one_shot`) | **CONFIRMED (NEW-5)**: `'Only once' button usable again: True` |
| ToggleSwitch (`state`) | on/off | no | KNOWN LIMITATION (allow-listed "visual") |
| TriggerVolume / TriggerZone (`one_shot`, `_triggered`) | the trigger | no | per-visit by design (Studio's zone "once" re-arms each visit). SUSPECTED surprise when the zone starts a once-only Dialogue (#620 already covers the reward side) |
| SetGameStateOnEvent (`_consumed`, `once`) | the once fact | flags yes | harmless for `set_flags` (idempotent). **SUSPECTED over-count** for `inc_counters` with `once` (re-applied every visit); not run |
| QuestProgressOnEvent (`_fired`), QuestHook (`_triggered/_completed`) | the once fact | quest manager | SUSPECTED harmless (quest progress is idempotent per stage); not run |
| InteractableBehaviour (`_consumed`), Timer (`_completed`), SequencePlayer (`_has_started`), DialogueRunner (`_completed`) | one-shot use / completion | no | per visit (Timer/Interactable have `saveable_state` for the current room only). SUSPECTED for one-shot Interactables that pay out; not run |
| EncounterCleared (`_fired`) | fired | no | safe: on re-entry with the enemies remembered as removed, `_saw_enemies` is False and it does not re-fire (`encounter_cleared.py:64-72`) |
| movement/AI/animation state (Chase/Flee/Patrol*/Wander/EnemyAI/FollowPath/Animator/ParticleEmitter/DamageOnTouch) | transient | — | not a defect |

**Bounded fix direction (one design, several PRs):**
- add a per-entity "facts" record in room memory, keyed by room + entity id (`room_memory` already holds per-room data in game-state vars, so saves carry it);
- let behaviours declare which fields are facts, so `saveable_state`/`restore_state` are applied on room enter from room memory, not only on load;
- DoorLock, SwitchInteract and RewardChest first (with #636), then Dialogue once (#620).

---

## 4. Duplicate implementations and coupling

### 4.1 Competing implementations

| # | Responsibility | Implementations (files) | Live where | Divergence shown | Risk |
|---|---|---|---|---|---|
| D-1 | Quest management | `engine/quests.py` QuestManager (536 lines) vs `engine/quest_manager.py` (187) | full: every GameWindow (`game.py:533-537`); lightweight: GameStateController's default (`game_state_controller.py:97`) and about 35 test files | Console `quest` / `quest active` raise on the real manager (NEW-9). The save restore targets the lightweight API (T-3) | P2. The tests' quest semantics are not the game's |
| D-2 | Hotkeys | `game_runtime/input_dispatch.py` (early plain-key branches, return on match) vs `input_runtime/capture_key_router_model.py` (1456 lines, declarative RouteSpec/KeyCombo) | both, on every key | HISTORICAL, 5+ incidents: MON-0f, MON-2c, GAME-3a F11, Creator Mode F4/F5 (three hotfixes), CREATOR-F5 shadowed Quick Save (memory: input-dispatch-collision-pattern) | P2 recurring. No test asserts a pre-existing binding still fires under a new state |
| D-3 | Event buses / runtimes | MeshEventBus (`events.py`) vs GameplayEventBus (`gameplay_event_bus.py`). Five emit entry points: `event_bus.emit`, `window.emit_event`, `window.emit_signal`, `emit_gameplay_event`, `_emit_puzzle_event` | Game: MeshEventBus. **`mesh episode` harness: a `MagicMock()` window with a GameplayEventBus and MagicMock entities** (`mesh_cli/episode.py:563-573,703`). `test_episode_0[1-4]_integration.py` and `tooling/campaign_replay.py` use it | Production branches on `gameplay_event_bus` (QuestHook, `_emit_puzzle_event`, `emit_gameplay_event`, HUD), so "integration" episodes exercise the *other* route. TriggerZone's two emits (NEW-6) come from mixing them | **ARCHITECTURAL RISK, high**: the owner's "test doubles that invent APIs" at harness scale |
| D-4 | Cutscenes | `cutscene_controller.py` (live) vs `cutscene_runtime/runner.py` CutsceneRunner (753 lines; `mesh cutscene simulate/validate`, episode harness, golden tests) | live: the game; CutsceneRunner: CLI and tests | **Disjoint command sets.** Live (= `cutscene.schema.json`): `add_counter, camera_focus, camera_pan, emit_event, move_entity, set_flag, start_dialogue, wait, wait_dialogue_end`. Runner (`cutscene_runtime/schema.py:37-48`): `wait, emit_event, set_flag, clear_flag, run_actions, start_dialogue, branch_on_flag, goto, label, stop`. The file shapes differ too. #622 B lives only in the live one | ARCHITECTURAL RISK: a cutscene `mesh cutscene validate` accepts uses commands the game's schema refuses (and T-1 makes that fatal at start) |
| D-5 | Saves | SaveManager (`save_manager.py` + `save_runtime/`) vs `savegame.py` SaveGameV1 (`saves/save_1.json`) | SaveManager: F5/F9, pause menu, console (every real window has one). `savegame.py`: the F5 handler's fallback when there is no `save_manager` (test doubles only) **and the legacy main menu's Continue** | `repro_two_save_systems.py`: `SaveManager slots after F5: ['quicksave.json']` / `legacy main menu offers Continue: False` | **CONFIRMED, P2 (NEW-10)**. The legacy main menu cannot continue a saved game |
| D-6 | Inventory access | game-state bucket `inventory.get_or_create_inventory(window.game_state.values)` (8 files) + gold as the `gold` counter (`state_runtime/economy.py`) vs `interactor.inventory.add_item/add_gold` (RewardChest only) vs InventoryHolder (holds items, transfers to the bucket) | bucket: Vendor, pickups, drops, UI | RewardChest's path doesn't exist on real actors (#636); no inventory class has `add_gold` | covered by #636; consolidate on the bucket |
| D-7 | Puzzle gates | engine DoorLock/SwitchInteract (`puzzle_behaviours.py`) vs **mesh_net's own lever/gate rules** (`mesh_net/scene_room.py:8,591-592,983`) | net: authority-side; single-player: engine | The net gate opens and stays open for everyone (`test_mesh_net_scene.py::test_lever_opens_the_gate_once_for_everyone`); the engine door stays solid and relocks (NEW-5) | the net tests prove a different implementation |
| D-8 | Entity removal | legacy `editor_entity_ops_controller.py:56-58`, entity store despawn (`scene_entity_store_controller.py:202-218`), authoring/MCP live removal (`scene_runtime/authoring/entity_ops_parts/_shared.py:260-264`), `remove_from_sprite_lists()` from gameplay | all funnel into `_end_behaviours` (part A); `solid_sprites` removal is repeated per path | none beyond #637 | P3, keep the funnel single |
| D-9 | Placement / snap maths | `scene_runtime/authoring/entity_ops_geometry._snap_value` and a re-export in `entity_ops_parts/_shared.py:276`; `entity_select_mode.snap_world_to_tile_center`; `editor/input_router._snap_world_point`; `editor_light_occluder_ops.snap_world_point`; `creator_mode/creator_add_person.snap_to_grid` | legacy editor / Creator Mode / authoring | not compared (five helpers for one job) | P3 |
| D-10 | Player/camera snapshot | `scene_controller_parts/persistence.py` → `scene_controller_save_load.py` (a pass-through proxy taking the real function as a keyword) → `scene_runtime/persistence.py` | live | pure indirection, no behaviour difference | P3, unclear responsibility (§4.2) |
| D-11 | Legacy editor vs Studio | `engine/editor/` (282 files, 59,182 lines) + 15 `engine/editor_*.py` vs Studio (`studio*.py` + `project_ops`) | Studio is the normal path; the legacy editor is kept off it (#347) **but `EditorModeController` (fan-out 74) is constructed in every GameWindow, games included** (`game.py:539`), and its overlays are registered on every window | NEW-7, the no-op overlays (§1.2) and #631/#632 show the legacy surface is under-tested yet live | P2 maintenance and risk |

### 4.2 Large modules and unclear responsibilities (`scan_coupling.py`, 1110 modules, 294,861 lines)

| Module | Lines | Fan-in | Fan-out | Evidence of coupling |
|---|---|---|---|---|
| `engine/project_ops.py` | 4292 | 13 | 28 | **The change hub.** Over the last 600 non-merge commits it co-changes with `studio_hd2d.py` (27×), `hd2d/renderer.py` (27×), `studio.py` (22×), `authoring.py` (19×), `hd2d/runtime.py` (16×), `hd2d/settings.py` (15×) and `water.py` (15×). Every HD-2D/Studio feature edits 4-6 large files (shotgun surgery) |
| `engine/studio.py` | 3645 | 2 | 24 | co-changes with `studio_hd2d.py` 23× and `project_ops` 22× |
| `engine/studio_hd2d.py` | 2887 | 2 | 27 | as above |
| `engine/game.py` | 1075 | **94** | **60** | god-facade: 41 distinct co-changed files in 7 commits; every UI overlay, behaviour and tool reaches through `window.*`, which is the surface §1 measures |
| `engine/editor_controller.py` | 1287 | 35 | **74** | highest fan-out; built into every game window (D-11) |
| `engine/ui_overlays/providers.py` | 1448 | 5 | 28 | mixes interaction, settings, debug and HUD providers |
| `engine/ui_overlays/hud.py` | 1695 | 1 | 12 | HUD, toasts, quest hints, boss-reward clarity and demo hints in one file (NEW-8 hides here) |
| `engine/input_runtime/capture_key_router_model.py` | 1456 | 1 | 2 | half of D-2 |
| `engine/editor/asset_ops/editor_file_ops_controller.py` | 1429 | 1 | 11 | NEW-7, #618, #631, #632 all live here |
| `mesh_cli/verify.py` / `verify_steps/pipeline.py` | 2880 / 2515 | 5 / 1 | 17 / 23 | #624 B lives here |

**Scene controller sprawl:** 21 top-level `engine/scene_*.py` files (5342 lines), 17 `scene_controller_parts/` files (2406), 27 `scene_runtime/` files (5673). `scene_controller.py` (18 lines) and `scene_controller_impl.py` (15) are shims, and D-10 shows three layers for one function. Responsibility is split by mechanism (parts, runtime, model, controller) rather than by feature, so a lifecycle question (§3) spans about 6 files.

**Most-changed files (last 300 commits):** mesh_net (`world_client` 22, `server` 21, `scene_room` 20, `demo` 18). That is expected churn from M3/M4 inside one subsystem. The cross-area coupling is the Studio/HD-2D cluster above.

### 4.3 Accidental coupling: changes that broke unrelated systems (history and memory)

| Pattern | Evidence | Lesson |
|---|---|---|
| Two hotkey systems shadow each other (D-2) | 5+ incidents (memory input-dispatch-collision-pattern). CREATOR-F5 silently disabled Quick Save | bind keys through one registry; test that the old binding still fires |
| `visible` overloaded (hidden vs no picture) | #419 (`c65a65f1`, `bcca410e`, `0c6ee70b`): an interaction gate meant for ConditionalActivator made every picture-less entity untalkable | a presence predicate (`interaction._present`), not raw `visible` |
| `maximize()` shows hidden windows | memory maximize-shows-hidden-windows; hidden test windows became visible and stole focus (#605 `no_activate`) | guard window-state calls with `visible` |
| DPI awareness | memory dpi-unaware-root-fix (#304, `a5a54d81` "Green board after Creator Mode and DPI merges"): 125% zoom broke input mapping across the editor | process-level setting before pyglet import |
| Fake windows hide wiring | `solid_sprites` on the window (HISTORICAL, `conditional_activator.py:121`); #622 (`on_event` vs `handle_event`, `find_sprite`); #636 (`interactor.inventory`); NEW-7 (`repo_root`); NEW-8 (`player`) | §1.6 items 1, 4 |
| Parallel PRs on one subsystem | memory combined-tree-before-second-merge: #600 + #601 broke 13 tests together | test the merge tree |
| Test runs pollute repo state | #334 (`projects.json`, `MESH_REPO_ROOT` leak) | fixtures restore env/paths (conftest `_repo_projects_json_untouched`) |
| CWD vs project root | #623 (saves), NEW-7 (legacy file ops), `cutscenes.json` read from the CWD (§2.1), `savegame.py` `saves/save_1.json` (D-5) | resolve every project file against one pinned project root |

---

## 5. New confirmed defects: issue-ready writeups

### NEW-5 (P1): "Locked until an event" doors keep blocking after they unlock, and both door and button forget their state

**Title:** DoorLock unlocks but stays solid (it writes `entity.properties["solid"]`, which nothing reads); "Picture when open" / "Picture once used" are never applied; the unlock and the "Only once" button press are lost on room re-entry and on load.

**Severity:** P1, a wrong outcome on Studio's picker ("Locked until an event", "Button") and on shipped content.

**Reachability:**
- Studio picker: DoorLock and SwitchInteract in the Interaction category; `set_solid` in the inspector.
- 22 shipped scenes with DoorLock. The core_regions chapters use the exact pair with `solid: true`: e.g. `Act1_Chapter2_Ambush.json` Ch2AmbushSwitch → Ch2AmbushDoor; also Chapter3 Archive, Chapter4 Bastion, Chapter5 Gauntlet.
- mesh_net scenes are not affected: mesh_net reimplements the gate (D-7).

**Repro:** `docs/s1/evidence/repro_lever_door_studio_puzzle.py`. Real hidden window; the button and the solid gate are configured like the shipped chapters. Output (exit 1):

```
gate is solid at load: True | locked: True
button pressed (interaction handled): True | door locked: False | door_unlocked events: 1
walked right from x=100 to x=136; gate spans x=168..232 | passed through the unlocked gate: False | gate still in
solid_sprites: True | properties['solid']: False
open picture applied: False
after leaving and re-entering: door locked: True | 'Only once' button usable again: True
after loading a save made after the unlock: door locked: True | button usable again: True
DEFECT REPRODUCED: the unlocked door still blocks the player; the unlock and the 'Only once' press are forgotten on
re-entry and on load
```

**Root cause:**
- `engine/behaviours/puzzle_behaviours.py:195-206`. `DoorLock._update_collision` sets `entity.properties["solid"] = False` / `["walkable"] = True`. No code reads `properties["solid"]` (`git grep` finds only this write); solidity is membership of `scene_controller.solid_sprites` (`gameplay_runtime.py:6-35`).
- `open_sprite` (DoorLock) and `active_sprite` (SwitchInteract, `:115-119`, a `pass` with the comment "In a real engine we'd swap the texture") are stored and never used.
- Neither class has `saveable_state`, and neither writes game state. `locked` and `activated` live only on the instance (§3.4). Both are allow-listed in `tests/test_save_participation_policy.py:30-31`, DoorLock with "TODO: add save".

**Missed by tests:**
- `tests/test_puzzle_behaviours.py:36-46` uses a MagicMock window and entity and asserts only `door.locked` and the emitted event;
- `test_puzzle_subscription_lifecycle.py` uses MagicMock;
- no real-window test names DoorLock or SwitchInteract (`scan_behaviour_test_coverage.py`: 0 / 0);
- the only "gate opens" test is mesh_net's separate implementation.

**Bounded fix (one PR plus a persistence PR):**
1. On unlock, remove the sprite from `scene_controller.solid_sprites` (and add it back if it relocks). Apply `open_sprite` / `active_sprite` through the asset manager. Drop the `properties` write.
2. Record "unlocked" / "pressed" as a per-room entity fact (room memory, §3.4), or as a flag derived from the `unlock_event`. Apply it on construction, so re-entry and load restore it. Old saves without the record mean "as authored".

**Regression requirements (real hidden window, `perform_interaction`, the real mover):**
- press, then walk through the gate; the gate leaves `solid_sprites`; the open picture shows;
- re-entry and save → load → revisit keep the gate open and the "Only once" button spent;
- a gate that `starts_locked: false` never blocks;
- the shipped Ch2 Ambush pair passes;
- mutation proof: restoring the `properties` write fails the walk test.

### NEW-6 (P1): "React when someone comes near" never sends the event the creator chose, and sends `entered_zone` twice

**Title:** TriggerZone ignores its `on_trigger` ("Event it sends") and always emits `entered_zone`, through two emit paths, so every listener receives it twice.

**Severity:** P1, a Studio picker setting that silently does nothing (same class as #622).

**Reachability:**
- Studio picker "React when someone comes near" (Interaction; `behaviour_guide.py:72-74` labels `on_trigger` "Event it sends").
- 255 shipped TriggerZones (238 in packs, 17 in `scenes/`) whose `on_trigger` names (e.g. `act1_ch1_clearing_goal`) nothing listens to: dead configuration today.
- The duplicate `entered_zone` affects any counter, quest stage or SetGameStateOnEvent `inc_counters` keyed on `entered_zone`.

**Repro:** `docs/s1/evidence/repro_studio_picker_behaviours.py`. Real window and update loop; the zone's target is the player within its radius. Output (exit 1):

```
[Mesh][Trigger] Zone triggered open_gate
zone     configured event 'open_gate' fired 0x | 'entered_zone' delivered 2x for one entry
DEFECT REPRODUCED: TriggerZone never sends the event the creator chose ('Event it sends')
```

**Root cause:**
- `engine/behaviours/trigger_zone.py:52` reads `event_name` from `on_trigger`, then uses it only in the log line (`:80-81`).
- `:85-104` emits `EVENT_ENTERED_ZONE` via `emit_gameplay_event`, which falls back to `event_bus.emit` in the game, **and** via `window.emit_signal`, which emits on the same bus again.
- Unchanged since the initial import (`git log` on the file: 3 commits, none touching emission).

**Missed by tests:** 30 test files name TriggerZone; none uses a real window (`scan_behaviour_test_coverage.py`).

**Bounded fix:**
1. Emit `on_trigger` when it is set, with the zone/actor payload.
2. Emit `entered_zone` once (drop the `emit_signal` duplicate, as SL-2 did for SetGameStateOnEvent).
3. Keep `entered_zone` for existing listeners.

**Regression requirements (real window):**
- the configured event fires exactly once per entry;
- `entered_zone` is delivered once (a bus subscriber and a queued `on_event` listener each see one);
- a quest with two consecutive `entered_zone` stages advances one stage per entry;
- mutation proof: re-adding `emit_signal` fails the count.

### NEW-7 (P1, legacy editor): legacy file operations resolve paths against the CWD; the "safe" ones never run in the real editor

**Title:** The legacy editor's Delete/Rename/Move read `window.repo_root`, which the real GameWindow never has. The safe (V2) refactors silently return False, and the plain ones act on `./<path>` in the current working directory instead of the project the explorer shows.

**Severity:** P1 by the irreversible-loss rule (#618/#631/#623 convention): Delete unlinks a file in another folder (the engine checkout or another project), with no confirmation and no trash. Legacy editor only (#347).

**Reachability:**
- Legacy editor Edit > Delete with the Project tab focused (`selection_clipboard.py:37` → `delete_selected_paths_if_active` → `delete_selected_paths`), rename and move in the Project Explorer.
- Wrong-folder effect: whenever the CWD is not the project. That is the main-menu "Open project" / create-project switch (`main_menu_overlay._apply_project_root` sets `MESH_REPO_ROOT` without changing directory) and `public_api.run_game(project_root=...)` (the #623 situations).
- `mesh edit` changes directory into the project (`game_launch.py:41-42`), so it gets the right folder but still the inert safe operations.

**Repro:** `docs/s1/evidence/repro_legacy_file_ops_wrong_root.py`. Real hidden window and EditorModeController, with two throwaway folders: the explorer root `project/` and the CWD `launch/`, each holding `assets/sprites/hero.png`. Output (exit 1):

```
window has repo_root: False
explorer / editor root: project
safe delete/rename/move returned: False / False / False | both files intact: True
plain delete returned: True | launch-folder hero.png exists: False | project hero.png exists: True
DEFECT REPRODUCED: the safe (V2) refactor operations silently do nothing in the real window; Delete unlinked the CWD's
file, not the project file the explorer showed
```

**Root cause:**
- `engine/editor/asset_ops/editor_file_ops_controller.py` reads `getattr(self.controller.window, "repo_root", None)` at :180, 250, 489, 708, 789, 967, 1030, 1121, 1132, 1216 and 1283.
  - The V2 entry points (`request_safe_rename_refactor` :1019, `request_safe_move_refactor` :1095, `request_safe_delete_refactor` :1212) return False when it is missing.
  - `delete_selected_paths` (:708, unlink at :743), `_perform_fs_rename` (:967) and the move rollback (:789) fall back to `Path(... or ".")`.
- No production code sets `window.repo_root` (`contract_gaps_real_window.py`: "prod creates False"). The explorer uses `editor._get_repo_root()` → `get_repo_root()` (`editor_controller.py:512-516`, `editor_controller_bootstrap.py:93`).

**Missed by tests:**
- 6 test files give their fake window `repo_root`.
- Part A's #618 verification (`verify_618_rename_toctou.py:30`, `window=SimpleNamespace(repo_root=root, ...)`) has the same blind spot. **#618 should be re-qualified:** the no-clobber logic is right, but in the real window the V2 path is unreachable and the plain rename resolves against the CWD. #631's delete is the CWD-relative unlink here.

**Bounded fix:**
1. Give file ops one root: `self.controller._get_repo_root()`, the root the explorer already uses. Delete the `window.repo_root` reads.
2. Refuse (toast) instead of falling back to `"."`.
3. Land with or before the #631 confirmation/trash fix, so Delete goes through the V2 trash path.

**Regression requirements:**
- real window, CWD ≠ project: delete, rename and move touch only the project's file; the CWD's same-named file is byte-identical afterwards;
- the V2 operations run (return True) in a real window;
- re-run `verify_618_rename_toctou.py` against a real window;
- mutation proof: restoring the `or "."` fallback fails.

### T-1 (P1): an MCP cutscene edit can make a project impossible to open

**Severity:** P1, an irrecoverable-looking failure on the AI-authoring path. No bytes are lost: deleting the bad entry recovers the project.

The repro, output and root cause are in §2.1.

**Missed by tests:** no test writes a cutscene through MCP and then constructs a GameWindow. The cutscene tests use the other runner (D-4).

**Bounded fix:**
1. Validate cutscene payloads against `cutscene.schema.json` in `AIOps.add_or_update_cutscene` / `insert_cutscene_step` / `update_cutscene_step` before writing, and refuse with the schema message.
2. Include `cutscenes.json` in `run_validation`.
3. In `GameWindow.__init__`, catch `SchemaValidationError`: log it, skip the bad file (or the bad cutscene) and show a toast instead of refusing to start.

**Regression requirements:**
- an MCP op with an unknown step type, or a missing required field, is refused and the file is unchanged;
- a hand-broken `cutscenes.json` lets the game and Studio start, with the error reported;
- mutation proof for both halves.

### NEW-8 (P2): the player HUD's health/level panel never draws

- **Title:** PlayerHUD reads `window.player`, which the real GameWindow does not have, so `_draw_stats` returns at once every frame.
- **Reachability:** every game with a player that has Health. Per-entity health bars are unaffected.
- **Repro:** `repro_fake_only_window_contracts.py` A (exit 1): `window has 'player': False` / `A) HUD view model after _draw_stats: None`.
- **Root cause:** `engine/ui_overlays/hud.py:866-869`. The same read is in `editor/debug/debug_bundle.py:449`.
- **Missed by:** 4 test files whose fakes have `player`.
- **Fix:** resolve the player through `scene_controller._find_player_sprite()` (as `interaction._find_actor` does), in one helper used by both readers.
- **Regression:** real window, player with Health → `get_hud_view_model()` reports its hp/max_hp after one draw.

### NEW-9 (P2, developer console): `quest`, `quest active` and `rules` raise AttributeError

- **Root cause:**
  - `console_runtime/handlers.py:149-166` uses the lightweight QuestManager API (`.title`, `get_quests_by_state`) on the real manager;
  - `console_runtime/commands.py:335` reads `window.collision_rules`, which doesn't exist.
- **Repro:** `repro_fake_only_window_contracts.py` B (output in §1.3).
- **Reachability:** the dev console (`` ` ``). The exception leaves `execute_command`; whether a higher frame stops it from ending the game was not checked.
- **Fix:** use `get_all_quests()` views plus `is_quest_active`, and the real collision-rule source (or remove `rules`); wrap `dispatch_command` so one failing command logs instead of raising.
- **Regression:** each console command runs on a real window without raising.

### NEW-10 (P2): the legacy main menu's Continue never sees the game's saves

- **Root cause:** `ui_overlays/main_menu_overlay.py:380-391,661-672` read `savegame.py`'s `saves/save_1.json` (`savegame.py:138`), which only the F5 handler's no-SaveManager fallback writes (`capture_key_router_handlers_global.py:243-253`). That branch is never taken by a real window.
- **Repro:** `repro_two_save_systems.py` (exit 1).
- **Reachability:** MainMenuOverlay is built for every non-editor launch (`ui_dispatcher.py:83-85,239-241`). When it is shown to players was not traced.
- **Fix:** have Continue use SaveManager (most recent slot, or `quicksave`), and retire `savegame.py`'s write path, or keep it as a read-only import.
- **Regression:** F5, then the main menu offers Continue, which loads the quick save.

### P3 bundle (one issue)

The plugin context's `console` / `asset_manager` are always None (§1.2). Also in the bundle:
- the debug panels' quest/cutscene state is empty, and the debug bundle lacks digests;
- MenuBarOverlay and ContextMenuOverlay never draw;
- legacy `purge_trash` never purges, because `repo_root` is missing (`editor_file_ops_controller.py:180`);
- the legacy workspace `current_scene_key` is always None;
- the inspector's event history is empty (`get_history` on MeshEventBus);
- the golden-slice quest label is empty;
- `saveable.extract_/apply_saveable_state` are dead helpers.

The fix pattern is the same everywhere: read the real attribute name, or delete the dead branch. The regression is the §1.6 meta-test.

### Not filed (by instruction, or tracked)

- Queued events in a door frame reach the next room (§3.3): CONFIRMED semantics, P3. File only if a creator-visible case is found.
- The episode harness and CutsceneRunner as parallel runtimes (D-3, D-4): ARCHITECTURAL RISK, for the S1 plan, not an issue.

---

## 6. What I could not check

- **No real key input** (by rule: no visible automation). Interaction went through `perform_interaction`, movement through `move_entity_with_collision`, the console through `execute_command`. Whether NEW-9's exception ends a running game was not observed.
- **Studio / editor launch** for T-1: I constructed the game's GameWindow, not `mesh edit`. That the editor fails too is from code reading (`game_launch.py:82`).
- **The legacy editor's visible UI:** whether its menu bar and context menu are drawn by anything else (the generic overlays are no-ops), and whether the invisible input-blocking `context_menu` layer can actually be opened.
- **Whether a core_regions chapter is impassable** because its DoorLock gate never opens (another route may exist). Routes were not walked.
- **Matrix rows marked "read" or "not run":** music, weather, room lights, ToggleSceneLights, QuestGiver end to end, Vendor stock persistence, and the SUSPECTED rows in §3.4 (SetGameStateOnEvent `inc_counters`+`once`, one-shot Interactables). Room music was never played aloud.
- **`scan_behaviour_test_coverage.py` is approximate:**
  - it counts a file that names a behaviour as covering it;
  - it does not recognise real windows built through other helpers (Studio play-test fixtures, `runtime_play`);
  - so "0" rows deserve a manual second look before being quoted as "untested".
- **Fake-window scan blind spots:** fakes reached through other names (`beh.window`, `ctx`, `owner`) and attribute access through `setattr` with computed names. Studio fakes were checked statically only (no Studio window constructed).
- **Placement-maths divergence (D-9):** not measured numerically.
- **Change coupling:** the last 300/600 non-merge commits of this branch only; commits touching more than 40 production files were skipped as sweeping.
- **Not examined, by instruction:** the #622 fix branch, #612 / PR #634.
