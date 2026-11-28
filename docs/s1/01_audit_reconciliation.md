# S1-0 part A: audit reconciliation, new runtime findings, data-integrity sweep

Checked against the integration tip **`9d3580b9`** (`redesign/visual-editor`, after #633). This is investigation only: no production code changed.

**Sources:**
- the coordinator's triage: `audit/deep-audit-triage:docs/audits/deep_audit_2026_11/TRIAGE.md` and its `repro/` scripts (verified there at `a4465258`);
- the owner-supplied independent runtime audit in draft PR #629 (audited at `49686331`);
- issues #618–#624, #627, #631 and #632;
- merged PRs #625 (#619), #628 (#618) and #633 (#624 phase A).

**Method:**
- Every script ran one at a time with `py -3.13` and `PYTHONPATH=<this worktree>`. Every run printed `engine from .../Mesh-S10/engine/__init__.py`.
- Real-runtime evidence uses a real GameWindow that is hidden, muted and never activated (`tooling.hidden_windows.no_activate` with `visible=False`, as `tests/conftest.py` does). It also uses the real scene loader, interaction path, removal path and save/load.
- The triage scripts contain `os.chdir(r"D:\Games\Mesh-audit")`. I re-ran them with that one line pointed at this worktree. They are not copied here; run them from the triage branch with that edit.
- Temp paths in the outputs below are shortened to `<tmp>`.

**Severity scale used:**
- **P0:** data loss or a crash on the main path, with no workaround.
- **P1:** a wrong outcome or an irreversible loss on a supported path (Studio, shipped content, `mesh play`, export). Under the convention set by #618 and #631, this also covers irreversible data loss on a reachable non-main path.
- **P2:** a limited path, a recoverable outcome, or no shipped or standard pattern triggers it.
- **P3:** latent, cosmetic or developer-only.

No P0 was found.

---

## 1. Reconciliation table (both audits plus the filed issues)

| Id | Finding | Source(s) | Status at 9d3580b9 | Reachability | User impact | Sev (recommended) | Evidence at tip |
|---|---|---|---|---|---|---|---|
| #618 | Legacy rename/move `os.replace` onto an existing file | triage; #629 #1 | **HISTORICAL**: fixed by #628. Both an occupied destination and one that appears after the dialog opened are refused; both files stay intact; no reference rewrite. **The issue is still OPEN** (#628 merged into a non-default branch, so it did not auto-close) | Legacy editor (#347) | none now | closed (was P1 by the irreversible-loss rule) | `repro_legacy_rename_overwrite.py` (triage): `[Refactor] Rename refused: assets/villain.png already exists ... nothing was changed.` (the script's assert then fires, which means not reproduced). `docs/s1/evidence/verify_618_rename_toctou.py` exits 0: `hero.png: b'HERO-BYTES' \| villain.png: b'VILLAIN-BYTES' \| scene sprite: assets/hero.png` |
| #619 | Shop charges gold and stock when `add_item` fails | triage; #629 (improvements) | **HISTORICAL**: fixed by #625. **The issue is still OPEN** (same reason) | Shop panel → Vendor; shipped scenes; Studio | none now | closed (was P1) | `repro_shop_charges_without_item.py` exits 0: `potion with full stack: gold 1000.0->1000.0 ... toast="Can't carry any more Healing Potion"`; `second iron_sword: gold 1000.0->1000.0`; `unknown item id: gold 1000.0->1000.0 ... "Can't buy iron_swrod: unknown item"`; `not reproduced []` |
| #620 | "Only once" / "Choice once" dialogue reward repeats after room re-entry or load | triage (P1); #629 #6 (P2) | **CONFIRMED** | Studio-authored dialogue (inspector toggles, `project_ops.set_conversation/set_choice`) | Reward paid again on every re-entry: farmable, and breaks an explicit authoring promise | **P1**: see the reconciliation below | `repro_dialogue_once_reward_repeats.py` exits 1: `visit 1: ... gold now 50.0` / `visit 2: ... gold now 100.0` / `DEFECT REPRODUCED: once-only reward paid twice 100.0` |
| #621 | One event completes two consecutive same-trigger quest stages | triage (P1); #629 #5 (P2) | **CONFIRMED** | Live `engine.quests.QuestManager` via `GameStateController.handle_event`. No shipped quest has the shape (scan: none) | Stage skipped, early quest reward (an over-grant, not a loss) | **P2**: see below | `repro_quest_one_event_two_stages.py` exits 1: `after one kill: {'status': 'completed', ... 'completed_stages': ['first_wolf', 'second_wolf']} gold: 100.0`; `shipped consecutive same-trigger stages: none` |
| #622 A | ActionListRunner never gets live events (`handle_event` only; the runtime delivers via `on_event`) | triage; #629 #4 | **CONFIRMED**. Fix in progress on a separate worker branch (not merged); not duplicated here | 11 repo scenes; Studio | Authored actions inert | P1 (both agree) | `repro_dead_actions_cutscenes.py` exits 1: `A) via the game's event delivery: gate_open = False` / `A) via handle_event (what the tests call): gate_open = True` |
| #622 B | Cutscene `move_entity` / `camera_focus` / targeted `start_dialogue` call the missing `SceneController.find_sprite` | triage; #629 #4 | **CONFIRMED** (same worker) | CutsceneTrigger (Studio can add it); console | AttributeError out of `CutsceneController.update` every frame | P1 | same script: `B) SceneController has find_sprite: False \| has find_entity: True` / `B) CutsceneController.update raised: 'SceneController' object has no attribute 'find_sprite'` |
| #622 C | `entity.behaviours` read where real sprites carry `mesh_behaviours_runtime` | triage | ARCHITECTURAL RISK, code-read (`cutscene_controller.py:236`, `action_list_runner.py:404,438`); covered by the same worker | as A/B | Timer, dialogue and start_dialogue actions silently do nothing | P1 (with #622) | code reference only |
| #623 | Non-exported saves resolve relative to the CWD, not the project | triage (P2); #629 #2 (P1) | **CONFIRMED** | Legacy main-menu project switch (`main_menu_overlay._apply_project_root`); `public_api.run_game(project_root=...)`, which the shipped `examples/template_game/main.py --project-root` uses. Not affected: Studio, `mesh play`, scaffolded `main.py` (it chdirs), exports | Project B's quicksave overwrites project A's slot. A same-version overwrite gets no backup | **P1** (irreversible-loss rule): see below | `repro_saves_follow_cwd.py` exits 1: `project B's quicksave would be written to: <tmp>\project_a\saves\quicksave.json` / `saves follow the CWD, not the project` |
| #624 A | Ruff/mypy gates pass when the tool is missing | triage; #629 #8 | **HISTORICAL**: fixed by #633 | local verify-all | none now | closed | A fresh venv with no pip, ruff or mypy. `python -m tooling.ruff_gate` exits 2: `[ruff-gate] ruff is not available: no ruff module for <venv>\python.exe; install the dev tools`. `python -m tooling.mypy_gate` exits 2: `[mypy-gate] mypy is not available ...` |
| #624 B | mypy baseline-count guard is a no-op on a fresh checkout | triage | ARCHITECTURAL RISK, still present. `mesh_cli/verify_steps/pipeline.py:451-457`: `.mesh/metrics/mypy_baseline_count.txt` is git-ignored (`.gitignore:3`), so when it is missing `previous_count = current_count` | CI ratchet | The baseline can grow unchecked in CI | P1 (safeguard; phase B of #624) | code reference only. `git check-ignore -v` → `.gitignore:3:.mesh/` |
| #624 C/D | Baselines and allow-lists can grow; steps pass when their input is missing | triage | SUSPECTED (not re-checked in part A) | CI | Gates pass without checking | P1/P2 per issue | none new |
| #627 | Granted items silently lost when the inventory can't take them (drops, chest) | #627 (suspected P2) | Chest: superseded by **NEW-1** below (the chest grants nothing at all). Drops (`engine/drop_table.py:119`): SUSPECTED, not run | enemy drops | Item lost when the stack is full | P2 (drops) | not run |
| #631 | Legacy Edit > Delete and palette "Delete Selected" unlink with no confirmation and no trash | #631 | **CONFIRMED** | Legacy editor (#347) | Irreversible file loss | P1 (irreversible-loss rule; agreed) | `repro_legacy_delete_hazards.py <scratch>` (it always exits 0; read the output): `Edit menu 'Delete' (editor.delete): ran=True \| confirm dialog opened = False \| hero.png exists = False \| .mesh_trash exists = False \| bytes anywhere = []`; the palette line is the same |
| #632 | Re-deleting a re-created file overwrites the earlier copy in `.mesh_trash` | #632 | **CONFIRMED** | Legacy editor | The recoverable copy is lost (no live file) | P2 (agreed) | same script: `round 1: op_id=379753a59a13 ... b'HERO-1'` / `round 2: op_id=379753a59a13 ... b'HERO-2'` / `HERO-1 bytes survive anywhere: False` |
| #612 | Replay timing flake | — | open; diagnostic PR #634 in review | CI | flaky gate | (unchanged) | not touched |
| T-1 | MCP cutscene ops write unvalidated steps; the game catches only FileNotFoundError when it loads `cutscenes.json` | triage (read only) | **SUSPECTED, strengthened.** The loader half is reproduced at component level: three malformed shapes (unknown step type, `move_entity` without entity, a step that is not an object) each raise `SchemaValidationError` from `CutsceneController.load_from_file`, which `GameWindow.__init__` (`engine/game.py:592-595`) does not catch. The MCP write half (`ai_ops.add_or_update_cutscene` / `insert_cutscene_step`, no schema check found) is code-read; not driven end to end | MCP / AI authoring | The project may fail to start after an AI edit | P1 candidate | one-off probe (no script kept): `unknown step type -> SchemaValidationError Schema validation failed for '<tmp>\cutscenes.json' against 'cutscene.schema.json' ...` |
| T-2 | Quest `emit_events_on_complete` ignored; `reward.gold/xp` dropped by `normalize_reward` | triage (read only) | SUSPECTED, not re-checked | shipped quests.json (16 uses) | Silent no-op | P2 | — |
| T-3 | Spurious "quest manager cannot register" warnings on every slot load | triage | SUSPECTED, not re-checked | load | Log noise | P3 (triage said P2: the state restores correctly, so this is cosmetic) | — |
| T-4 | Duplicate toast on quickload with no save | triage | SUSPECTED, not re-checked | load | cosmetic | P3 | — |
| NEW-1 | **RewardChest grants nothing even with an EMPTY inventory**, yet marks itself looted and emits `reward_collected` | #629 #3 | **CONFIRMED** through the real GameWindow and interaction path. Details in section 2 | 12 shipped scenes (core_regions dungeons, dev_sandbox); Studio "Treasure chest" in the Interaction picker | Rewards never arrive; the game reports success | **P1** (agrees with #629) | `docs/s1/evidence/repro_reward_chest_grants_nothing.py` exits 1 |
| NEW-2 | **A removed entity keeps handling events** until the room is left | #629 #7 | **CONFIRMED** through the real removal funnel. Room exit/re-entry and save/load end the stale listeners (bounded, not multiplying). Details in section 2 | Any removal mid-room: death, pickup, projectile, DamageOnTouch, editor/authoring delete; 6 behaviours affected | A removed door still unlocks; a removed counter keeps counting; a removed shopkeeper's shop still opens on its event | **P2** (agrees with #629) | `docs/s1/evidence/repro_removed_entity_keeps_listening.py` exits 1 |
| NEW-3 | A self-removing entity's `on_event` behaviours never see the event that removed it (`on_event` delivery is queued to the next tick and only reaches sprites still in the scene) | this investigation | ARCHITECTURAL RISK. `PickupCollectible.on_interact` emits, then `remove_from_sprite_lists()` (`pickup_collectible.py:108-121`). `tick.py:269-279` delivers queued events through `runtime_hooks._deliver_events_to_behaviours`, which iterates `_iter_layered_sprites()`. Shipped example: the Ridge Outpost rusted key's `QuestProgressOnEvent` would never fire; masked because `quests.json` `complete_on` completes the same stage | self-removing pickups/enemies with an `on_event` behaviour | Authored per-entity reactions to its own pickup/death silently do nothing | P3 (latent; masked in shipped content) | code reference only |
| NEW-4 | `EventLogger` subscribes in `on_added` / unsubscribes in `on_removed`; nothing in `engine/` calls either | this investigation | ARCHITECTURAL RISK (`git grep on_added engine` finds only definitions) | Advanced/debug behaviour, used in no shipped scene | The logger logs nothing in a live game | P3 | code reference only |

### Severity reconciliation (explicit)

**#620: P1 (triage) vs P2 (#629). Recommend P1.**
- The defect breaks an explicit promise the creator makes through Studio's own inspector toggle ("Only once" / "Choice once"), on the primary authoring path.
- It repeats without limit: every room re-entry pays again, and so does every load of a save made before the choice, which makes it farmable.
- #629's P2 seems to weigh "not data loss". The scale above treats a wrong outcome on a supported path as P1.

**#621: P1 (triage) vs P2 (#629). Recommend P2.**
- The defect needs two consecutive stages with an identical completion trigger. The scan of shipped quest data finds none.
- The outcome is an early over-grant, with no loss.
- It is real and the fix is bounded, but nothing a player or creator meets today triggers it, so P2. Revisit if Studio gains a quest-stage editor that makes "kill N as N stages" a natural pattern.

**#623: P2 (triage) vs P1 (#629). Recommend P1.**
- By reachability alone it is P2: Studio, `mesh play`, scaffolded projects and exports are unaffected.
- But the outcome is an irreversible overwrite of another project's save slot; a same-version overwrite gets no backup.
- The project already treats reachable irreversible loss as P1 regardless of path: #618 and #631 were both "P2 by reach, treat as P1".
- `public_api.run_game(project_root=)` is also a documented public API (`docs/public_api.md:19`), and the shipped `examples/template_game/main.py` exposes it through `--project-root`.
- For consistency, P1. The fix is small: resolve `DEFAULT_SAVE_DIR` against the game root in `engine/save_runtime/storage.py:97-98`, and keep reading CWD-relative saves that already exist.

**#620/#621 vs #629's grouping.** #629 grouped quest, dialogue and removed-entity cleanup together as one item, "address after the chest and wiring fixes". I keep them separate, because #620 is P1 and the other two are P2.

### Status hygiene for the coordinator
- **#618 and #619 are still OPEN** although #628 and #625 merged. These PRs target `redesign/visual-editor`, so GitHub's "fixes #N" did not close them. They should be closed by hand with links to the evidence above.
- **#627** should be narrowed to drops (and the `vendor.py:107/116` nits). The chest case becomes NEW-1, a confirmed failure that does not depend on the inventory being full.

---

## 2. New findings from #629: issue-ready writeups

### NEW-1: RewardChest reports the reward collected but grants nothing (empty inventory too)

**Title:** RewardChest marks itself looted and emits reward_collected but never grants its item or gold (it grants only through `interactor.inventory`, which players don't have)

**Severity:** P1, a wrong outcome on shipped content and on Studio's "Treasure chest". The game says the reward was collected and the player gets nothing.

**Reachability:**
- **Shipped scenes with a RewardChest behaviour** (12, found by scanning `behaviours` lists including prefabs): `packs/core_regions/scenes/Ashen_dungeon.json`, `Hollow Grove_dungeon.json`, `Ridge Outpost_dungeon.json` and its variants b–i, and `packs/dev_sandbox/scenes/preset_test_dungeon.json`. Configs like Ashen's are `{"gold": 50, "item_id": "", "unlock_event": "ashen_puzzle_unlock"}`.
- **Look-alikes that are not affected:** several root `scenes/*.json` contain an entity *named* "RewardChest" without the behaviour (for example `reward_nook_01`, `combat_tutorial_demo`).
- **Studio:** `engine/behaviour_guide.py:77` lists it as "Treasure chest" in the Interaction category, so the picker offers it, and the inspector edits `unlock_event`, `item_id` and `gold`.
- **Other tooling:** `engine/tooling/plan_executor.py:749` generates RewardChest entities.

**Repro:** `docs/s1/evidence/repro_reward_chest_grants_nothing.py`. It uses a real hidden GameWindow with a scene holding the player and a chest `{unlock_event: vault_open, item_id: healing_potion, gold: 10}`. It emits the unlock event on the game bus, then calls `engine.interaction.perform_interaction`, which is the call PlayerController makes on the interact key. Output (exit 1):

```
player sprite has an 'inventory' attribute: False
before: potions = 0 | gold = 0.0 | inventory empty = True
chest enabled by its unlock event: True
[Puzzle] RewardChest looted! Item: healing_potion, Gold: 10
interaction handled: True | chest looted: True | reward_collected emitted: True
after: potions = 0 | gold = 0.0
after leaving and re-entering: chest looted = False | can be opened again = True
DEFECT REPRODUCED: chest reports the reward collected but granted nothing
```

**Root cause:**
- `engine/behaviours/puzzle_behaviours.py:277-302` (`RewardChest.on_interact`) sets `self.looted = True` first. It then grants only `if hasattr(interactor, "inventory")`, through `interactor.inventory.add_item(...)` and `interactor.inventory.add_gold(...)` (lines 286-290), and emits `reward_collected` regardless.
- Production keeps the inventory in game state, not on the actor: `engine.inventory.get_or_create_inventory(window.game_state.values)` holds items (as Vendor and PickupCollectible use it), and the `gold` counter holds gold (`engine/state_runtime/economy.py:64` `add_gold(state, ...)` / `GameStateController.add_counter("gold", ...)`).
- No `add_gold` method exists on any inventory class (`git grep add_gold` finds only the economy function and this call), so even an actor with an `inventory` would raise AttributeError.

**Secondary (same behaviour):**
- `looted` is not saved or remembered. `tests/test_save_participation_policy.py:32` records `"RewardChest": "Loot state is re-initialised from scene JSON (TODO: add save)"`, and the repro shows `can be opened again = True` after re-entry.
- Today that is harmless. Once the grant works, it becomes a repeatable reward, the #620 class of bug.

**Why tests missed it:**
- `tests/test_puzzle_behaviours.py:50-62` builds the chest with a MagicMock player whose `inventory.add_gold` is asserted to have been called: the test double supplies exactly the interface production lacks.
- `tests/test_puzzle_subscription_lifecycle.py` uses MagicMock windows and entities.
- No test opens a chest through `perform_interaction` with a real player and game state.

**Bounded fix proposal (one PR):**
1. Grant through the production APIs:
   - items via `get_or_create_inventory(window.game_state.values)`, reusing the partial-add pattern of `pickup_collectible._grant_item` / `inventory_holder` (#627);
   - gold via `game_state_controller.add_counter("gold", gold)` or `economy.add_gold`.
2. Decide the full-inventory rule explicitly, consistent with pickups. Recommended: if the item can't be added (`Inventory.can_add` is false, with the item id as a string), don't loot. Leave the chest closed, toast "can't carry", grant no gold, emit nothing.
3. Set `looted` and emit `reward_collected` only after the grant succeeds. Put the actual granted amounts in the payload.
4. Persist `looted`, for example in room memory or a game-state flag keyed by room and entity id. Old saves without the record mean "not yet looted". This can be its own PR, but it must land with or before the grant fix, or the fix creates a farmable reward.

**Regression tests (through a real hidden GameWindow and `perform_interaction`, not a MagicMock actor):**
- empty inventory: the item and gold arrive, then `looted`, then the event;
- full stack and an owned non-stackable item: nothing is granted, the chest is not looted, no event;
- unknown `item_id`: refused the same way;
- gold-only chest (the shipped Ashen config);
- re-entry and save → load → revisit: the chest stays looted and does not pay twice;
- mutation proof: reverting to `interactor.inventory` fails the tests.

### NEW-2: Removed entities keep handling bus events until the room is left

**Title:** Removing an entity doesn't end subscriptions that its behaviours release in `destroy()` / `dispose()` (or never release); a removed door still unlocks and a removed counter keeps counting

**Severity:** P2. The effect is real but bounded:
- the stale listeners end when the room is left, and on load;
- in shipped content only one entity combines an affected behaviour with self-removal (see below), and its handler is filtered to its own pickup, so nothing observable happens there today.

**Reachability:** every removal goes through `entity_factory._end_behaviours`:
- `remove_from_sprite_lists()` from Health death (`health.py:233`), pickups (`collectible.py:71`, `pickup_collectible.py:121`), DamageOnTouch `destroy_on_hit` (`damage_on_touch.py:125`), Hitbox (`hitbox.py:98`) and projectiles (`projectile.py:109,141,149`);
- editor deletion (`editor_entity_ops_controller.py:58`), the entity store's despawn (`scene_entity_store_controller.py:218`), and authoring/MCP live removal (`scene_runtime/authoring/entity_ops_parts/_shared.py:264`).

**Affected behaviours** (subscribe on the event bus in `__init__`, never release on `on_destroy`):

| Behaviour | Subscribes | Releases in | Shipped scenes using it |
|---|---|---|---|
| DoorLock | `puzzle_behaviours.py:173` | `destroy()` :208 | 22 (incl. `mesh_net/coop/scene.json`, `mesh_net/expedition/ruins_1/2.json`) |
| RewardChest | `puzzle_behaviours.py:257` | `destroy()` :271 | 12 |
| SetGameStateOnEvent | `set_game_state_on_event.py:138` | `destroy()` :140 | 74 |
| IncrementCounterOnEvent | `increment_counter_on_event.py:84` | `destroy()` :100 | 1 |
| MessageOnZoneEnter | `message_on_zone_enter.py:46` | `dispose()` :63 | 0 |
| Vendor | `vendor.py:63` | never | 4 |

**Not affected:**
- CutsceneTrigger, DropTable, GrantExperience, QuestGiver, SceneExit, ToggleSceneLights and SoundEmitter: they implement `on_destroy` (B-05, commit `19db914b`).
- Behaviours that use `on_event` delivery, such as QuestHook and QuestProgressOnEvent: a removed sprite is no longer iterated.
- `MainMenu.destroy()` (UI element) is also never called. It is reached only via ActionListRunner `start()`, which is itself inert (#622), so I did not pursue it.

**The one shipped co-occurrence:** `packs/core_regions/scenes/Ridge Outpost_interior.json`, the `RustedKey` entity, which has PickupCollectible (`remove_on_collect`) and SetGameStateOnEvent (filtered to `collectible == RustedKey`).
- Its flag is set correctly today, because `event_bus.emit` is synchronous and runs before the removal (`pickup_collectible.py:108` then `:121`).
- A fix must keep that working.

**Repro:** `docs/s1/evidence/repro_removed_entity_keeps_listening.py`. It uses a real hidden GameWindow and one entity per affected behaviour, removes each one through `remove_from_sprite_lists()`, then checks room exit/re-entry and a save made before removal. Output (exit 1):

```
listeners with the room loaded:         {'lever_pulled': 1, 'ping': 2, 'vault_open': 1, 'open_shop_evidence': 1, 'entered_zone': 1}
one ping while all are present:          tally=1 pings=1
present after removal:                   ['Hero']
listeners after removing all six:        {'lever_pulled': 1, 'ping': 2, 'vault_open': 1, 'open_shop_evidence': 1, 'entered_zone': 1}
ping + lever after removal:              tally=2 pings=2 | removed door unlocked=True door_unlocked events=1
listeners after leaving for the Shed:    {'lever_pulled': 0, 'ping': 0, 'vault_open': 0, 'open_shop_evidence': 0, 'entered_zone': 0}
listeners after re-entering the Yard:    {... all 0 ...} | removed ones stay removed (room memory): ['Hero']
listeners after loading the save made before removal: {'lever_pulled': 1, 'ping': 2, ...} | same as first visit: True
one ping after the load adds exactly one: True
listeners after a further exit + re-entry: {... same as first visit ...} | same as first visit: True
DEFECT REPRODUCED: removed entities still react to their events
```

This agrees with #629: the removal leak is real, and repeated room entry does **not** multiply listeners. Save/load does not multiply them either.

**Root cause:**
- `engine/scene_controller_parts/entity_factory.py:49-65` (`_end_behaviours`) calls only `on_destroy` on each behaviour.
- The six behaviours above release their subscription under other names (`destroy`, `dispose`) or not at all, and nothing in `engine/` calls `destroy()` on a behaviour (`git grep` shows no caller).
- The scene *does* record every subscription a sprite's behaviours make: `entity_factory.py:204-213` stores `sprite.mesh_behaviour_unsubscribes` and also registers each with `track_scene_subscription`. That is why room exit and load clean up, while `_end_behaviours` never uses the per-sprite record.

**Why tests missed it:**
- `tests/test_puzzle_subscription_lifecycle.py` calls `destroy()` directly on behaviours built with a MagicMock window, so it proves that `destroy()` works, not that the runtime calls it.
- B-05's real-window tests (`tests/test_behaviour_teardown_on_entity_removal.py`, `test_behaviour_teardown_on_delete_paths.py`, `test_behaviour_unsubscribe_on_end.py`) cover only the four behaviours that already had `on_destroy`.
- `tests/test_state_lifecycle.py` checks room exit and `_rebuild_behaviours_for_sprite`, but removes only a behaviour-less Coin.

**Bounded fix proposal:**
1. Root cause, in one place: in `_end_behaviours`, after the `on_destroy` calls, run every function in `sprite.mesh_behaviour_unsubscribes` and clear it. The bus's `unsubscribe` is idempotent (`events.py:180-189`). This covers every behaviour that subscribes during construction, including Vendor, whatever its teardown is called, and future behaviours too.
2. Optionally, for behaviours used outside the scene factory: alias `on_destroy = destroy` on DoorLock, RewardChest, SetGameStateOnEvent and IncrementCounterOnEvent, and `on_destroy = dispose` on MessageOnZoneEnter. Do not add a second teardown path.
3. Out of scope, noted: subscriptions made after construction (EventLogger `on_added`, NEW-4) are not in the record. Today nothing makes them.

**Regression tests (real hidden GameWindow, like `test_state_lifecycle.py`):**
- for each of the six behaviours: remove the entity, emit its event, and assert no state change and a listener count of 0;
- the removal paths: `remove_from_sprite_lists` (death or pickup), editor delete, authoring `_debug_remove_sprite`, entity store despawn;
- the Ridge Outpost rusted-key pattern (pickup with a self-filtered SetGameStateOnEvent on the same entity) still sets its flag;
- room re-entry and save → load still give exactly one listener per behaviour;
- mutation proof: removing the new loop fails the tests.

---

## 3. Data-integrity and destructive-operation sweep

**Scope:**
- `git grep` for `os.replace|os.rename|os.remove|unlink(|rmtree|shutil.move|shutil.copy|write_text(|write_bytes(|open(...,'w'|'a')` finds 172 files across `engine/`, `mesh_net/`, `mesh_cli/` and `tooling/`.
- Every runtime/Studio/MCP/legacy-editor/mesh_net site in `engine/` and `mesh_net/` was read. `mesh_cli` was read for project creation and `--force`.
- `tooling/` (about 110 study, acceptance and evidence scripts) was classified by purpose, not line by line (see section 4).
- Prior hardening (F3, F4, F15, R2/R5, #618) was verified by spot reading, not re-audited.

**Shared primitives (`engine/json_io.py`):**
- `write_text_atomic` / `write_json_atomic` write an exclusive unique temp file beside the target, then `os.replace`, with optional fsync (`durable=True`);
- `publish_new` and `write_bytes_new` never replace anything that is already there (Windows `os.rename`; elsewhere `os.link`).

Most writers use these.

| Area / site | Atomic | Collision-checked | Contained (links) | Entry point | Data loss possible? | Classification |
|---|---|---|---|---|---|---|
| Game saves: `save_runtime/io.py` `write_json_pretty_atomic` / `write_snapshot_atomic` | yes, durable | slot names sanitised; pre-v3 slot → verified `.v2.bak`, never replacing an existing backup (`io.py:187-215`) | n/a | GameWindow F5 / menus | **Yes: non-exported saves dir is CWD-relative** (`storage.py:97-98`), so cross-project slot overwrite happens (#623) | CONFIRMED (#623) |
| Exported per-player saves (H9): `storage.resolve` → `<user data>/MeshMind Studios/<game_identity>/saves` | yes | per `game_id` (random per new project, `storage.py:52`) | n/a | exported game | A project folder copied by hand keeps its `game_id`, so two different exported games would share one save folder. Not run | ARCHITECTURAL RISK, P3 |
| Runtime settings: `runtime_settings_storage.save_runtime_settings` | yes | exported game: an unreadable or newer file is set aside (`.invalid[.n]`) before writing. Non-exported (dev/Studio): overwritten | n/a | settings menu | Only settings: a newer-version settings file is overwritten outside exports | ARCHITECTURAL RISK, P3 |
| Studio project save (`project_save`, F3) | staged per file, committed in order, rolled back on errors it sees | base-revision / fingerprint checks (R1, F6) | ownership lock (R2/R5) | Studio Ctrl+S, AI apply | By its own documentation, not crash or power-loss safe (no fsync; files replaced one at a time) | KNOWN LIMITATION |
| Studio new room/map files (F15) | `publish_new` | refuses an existing file, link or folder (`studio_project.py:510-520`) | yes | Studio | no | verified (spot) |
| Studio file release `_remove_if_unchanged` (S4) | move-aside, then compare, then delete or put back | yes | refuses links out of the folder | Studio | no | verified (read) |
| Studio HD-2D kit `ensure_hd2d_kit` (`studio_project.py:522-550`) | plain `copyfile` | copies only if the file is missing, or is a pixel-identical narrower older copy of Mesh's sheet (`_older_sheet`) | not checked for links at the target | Studio HD-2D | negligible (only Mesh's own unmodified sheet is replaced) | OK |
| Studio sound import (`studio_project.py:868-876`) | plain `copyfile` to a new name | dedupe by content plus a unique `_n` name | source inside the project used in place | Studio | no (TOCTOU negligible) | OK |
| HD-2D model import/reimport/kit (`hd2d/catalog._commit`) | staged exclusive temps, swapped in all-or-nothing, restore on failure | import refuses an occupied destination (`catalog.py:350`) | `_inside` checks before any folder is made and again before staging | Studio Models, MCP | no | verified (read) |
| Studio reimport rollback (`studio_hd2d.py:2807-2823`) | **no**: plain `write_bytes`/`unlink` to restore the previous model, preview and catalog when the room can't build | n/a | n/a | Studio reimport of a model the room rejects | Only if the process dies during the restore (a truncated model) | ARCHITECTURAL RISK, P3 |
| Legacy rename/move (#618 → #628) | `_move_no_clobber` (`editor_file_ops_controller.py:1355-1383`) | plan refused whole; re-checked at Confirm | junction-reached scenes refused | legacy editor | no | HISTORICAL (verified, including TOCTOU) |
| Legacy delete: global `editor.delete` and palette (#631) | `unlink()` (`:743`) | no confirmation | — | legacy editor | **yes, irreversible** | CONFIRMED (#631) |
| Legacy safe delete → trash (#632) | `os.replace` into `.mesh_trash/<op_id>` (`:150`) | **no**: same `op_id` overwrites the earlier trashed copy | `.mesh_trash` not excluded from the reference scan | legacy editor | the recoverable copy is lost | CONFIRMED (#632) |
| Legacy trash rollback (`_restore_deletes_from_trash`) | `os.replace` back | no | — | rollback within one failed operation only (callers :158/288/326/364; no undo path) | very narrow window | OK |
| Export (F4) `export_bundle` | journal + token-owned working folders, rename-never-replace (`:702`) | ownership proven by token, not name | `_is_link` checks; `rmtree` only on owned folders (`:664`) | `mesh export` / Studio export | no (spot-read) | verified (spot) |
| New project: `project_scaffold.create_project` | `config.json` atomic; `main.py` and assets plain | all three callers run `validate_new_project_target` / `check_new_project` first (target must be empty) | — | launcher, legacy menu, `mesh new` | no | OK |
| `mesh new --force` (`blank_project._replace_owned`) | rmtree after taking the authoring lock | refuses nested projects and projects owned elsewhere | doesn't follow links (`_is_link`) | CLI, explicit flag | deletes the target by design | KNOWN LIMITATION (by design) |
| MCP/AI direct writes | via `project_save` / ownership | R4/R5 ownership | yes | MCP | no (per R4/R5) | verified (triage) |
| MCP cutscene ops (`ai_ops.add_or_update_cutscene`, `insert_cutscene_step`) | via the writer | **no schema validation** before writing | — | MCP | The project fails to start (`SchemaValidationError` not caught at `game.py:592-595`); no bytes lost | SUSPECTED, P1 candidate (T-1) |
| AI history `.mesh/ai_history.jsonl` (`ai_history.py:11,39`) | append | — | CWD-relative | AI ops | no (an append-only log) | OK |
| Live session bridge file (`live_session_bridge.py:127-141`) | unique temp + replace; delete only if `session_id` matches | yes | — | Studio ↔ MCP | no | OK |
| Editor UI state / persistence_utils / palette thumbs | mkstemp/unique temp + replace | — | — | editor | no | OK |
| Launcher state dump (`launcher.py:487`) | fixed `.tmp` name + replace | no (test hook) | — | launcher test dump | no | OK (P3 nit) |
| mesh_net characters (N8) | SQLite, WAL, `synchronous=FULL`; key file `O_EXCL` 0600, removed only if this command created it | yes | — | `mesh_net` CLI/server | no. Not checked: whether two servers can open one store | verified (read) |
| mesh_net owed journal (`owed.py:166-175`) | fixed `<name>.new`, fsync, replace; tail repair zeroes from the last byte first | no (fixed temp name) | — | net server | only if two processes recreate the same journal at once | ARCHITECTURAL RISK, P3 |
| mesh_net disposable projects / demo (`scene_room.py:304-330`, `demo.py:34`) | plain writes | — | temp folder only | net demo/tests | no | OK |
| tooling/* (studies, acceptance, evidence) | mixed | mixed | write to their own output dirs, `docs/reviews/...` or temp | developer only | possible only for a developer's own artifacts. The #334 projects.json leak is merged | not audited line by line |

**Top data-integrity risks, ranked:**
1. **#623**: CWD-relative save folder for non-exported games. Cross-project overwrite; P1 by the irreversible-loss rule.
2. **#631**: legacy delete with no confirmation and no trash (legacy only; P1 by the same rule).
3. **T-1**: unvalidated MCP cutscene writes can stop a project from starting (P1 candidate; not end to end).
4. **#632**: trash overwrite (P2).
5. **#624 B**: the mypy baseline-count guard is a no-op on a fresh checkout (safeguard).

The rest are P3 or by design: the Studio reimport rollback is non-atomic, a copied project shares its `game_id`, non-exported settings are overwritten, and the owed journal uses a fixed temp name. No new P0.

---

## 4. What I could not check
- No full GameWindow run through real key input (by rule: no visible automation). Interaction was driven through `perform_interaction`, the function the interact key calls.
- #622 C, #624 B and NEW-3/NEW-4 are from code reading only. #624 C/D and triage items T-2 to T-4 were not re-run.
- T-1, end to end: I did not drive the MCP tool to write a bad cutscene into a project and then start that project.
- #627 drops path (`drop_table.py:119`) with a full inventory was not run.
- Two exported games sharing a `game_id` after a hand copy: reasoned, not run. Also unknown whether Studio has a "duplicate project" flow that copies `game_id`.
- Whether two mesh_net servers can open one character store at once (no lock found or ruled out).
- `tooling/` (about 110 files) was classified by purpose, not audited line by line.
- Whether the core_regions dungeons with RewardChest are reachable from a fresh project's start world in normal play. They ship in the pack the scaffold's world points to; the route was not walked.
- #612 (PR #634) and the #622 worker branch were not examined, by instruction.
