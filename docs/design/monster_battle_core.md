# Monster Battle Core Architecture Spike

Task: MON-0.0  
Status: research only  
Date: 2026-06-28

## Summary Decision

Build monster battles as a **runtime battle mode owned by `GameWindow`**, backed by a pure `MonsterBattleController`/state-machine module and rendered through a blocking battle UI overlay. Do not make battles separate scene JSON files, and do not treat them as a lightweight overlay-only feature.

The shape is:

1. An overworld trigger requests a battle with opponent species/level and return context.
2. `GameWindow` starts `battle_mode`, pauses overworld gameplay, and registers/shows a battle overlay.
3. The battle controller runs a strict turn-based state machine with pure data: species, monster instances, moves, type chart, RNG, and battle result.
4. On exit, the result is applied to game state: caught monster, party/box mutation, XP, inventory ball consumption, flags/events.
5. The overlay closes and the overworld resumes in the same scene.

This is sound on Mesh because the runtime already has a pause boundary, UI overlay registration, event delivery, saveable game-state values, and real scene transitions for the overworld. The missing half is the monster-RPG domain model and menu-heavy UI.

## Code Audit: Existing Runtime Primitives

### Scene and Mode Control

`GameWindow` constructs the core runtime services together: `SceneController`, `InputController`, `UIController`, `MeshEventBus`, `GameStateController`, `SaveManager`, `QuestManager`, and `EditorModeController` in `engine/game.py:500` through `engine/game.py:515`. It also owns `paused` and `game_over` flags (`engine/game.py:603` and `engine/game.py:604`) and subscribes the death/gameplay handlers to the event bus at `engine/game.py:664` through `engine/game.py:667`.

The runtime tick already separates game-over, paused, and gameplay update:

- Game-over blocks the normal tick, allows SPACE/attack retry, clears `game_over`, hides the game-over screen, unpauses, and reloads the scene (`engine/game_runtime/tick.py:210` through `engine/game_runtime/tick.py:217`).
- Paused mode updates UI and returns before scene gameplay (`engine/game_runtime/tick.py:219` through `engine/game_runtime/tick.py:221`).
- Normal gameplay updates cutscenes, scene, particles, lighting, UI, day/night, game-state, then consumes events and delivers them to game-state/behaviours (`engine/game_runtime/tick.py:223` through `engine/game_runtime/tick.py:259`).

The scene update model also treats `paused` as an empty gameplay plan: `build_update_plan()` returns no update steps when `inputs.paused` is true (`engine/scene_update_model.py:40` through `engine/scene_update_model.py:47`).

Scene transitions exist and are useful for overworld traversal. `_resolve_scene_path()` maps world scene keys and bare scene stems (`engine/scene_runtime/transitions.py:14` through `engine/scene_runtime/transitions.py:31`), `request_scene_change()` queues a pending scene path (`engine/scene_runtime/transitions.py:56` through `engine/scene_runtime/transitions.py:65`), `queue_scene_change()` supports a spawn id (`engine/scene_runtime/transitions.py:68` through `engine/scene_runtime/transitions.py:76`), and `perform_scene_change()` calls `controller.load_scene(scene_path)` (`engine/scene_runtime/transitions.py:125` through `engine/scene_runtime/transitions.py:130`).

`SceneTransition` is authored as a behaviour with `target_scene`, `spawn_id`, touch/event triggers, and `once` (`engine/behaviours/scene_transition.py:71` through `engine/behaviours/scene_transition.py:84`). When triggered, it emits `scene_transition` and calls `request_scene_change()` (`engine/behaviours/scene_transition.py:195` through `engine/behaviours/scene_transition.py:211`).

### Game State and Save

`GameState` already has open-ended `flags`, `counters`, `values`/`variables`, chapter, quest, level, XP, equipment, and perks (`engine/game_state_controller.py:24` through `engine/game_state_controller.py:35`). The `values` and `variables` maps are intentionally compatible aliases (`engine/game_state_controller.py:37` through `engine/game_state_controller.py:54`).

Player stats are not a general creature system. `get_player_stats()` derives player level, XP, HP, attack, defense, speed, equipment, and perks from engine config and game state (`engine/game_state_controller.py:209` through `engine/game_state_controller.py:241`). The player stat model should remain the overworld action-RPG stat model, not become the monster stat model.

`GameStateController.export_state()` serializes the whole game-state snapshot and quest data (`engine/game_state_controller.py:477` through `engine/game_state_controller.py:482`). Slot saves embed that export under `snapshot["game_state"]` (`engine/save_runtime/payloads.py:474` through `engine/save_runtime/payloads.py:484`) and also write saved entity state and saved quest state (`engine/save_runtime/payloads.py:486` through `engine/save_runtime/payloads.py:501`).

This gives the monster system a place to persist `monster_party`, `monster_box`, `monster_instances`, and battle/capture flags without inventing a parallel save file.

### Events

`MeshEvent` is the existing gameplay event record with a type and payload (`engine/events.py:54` through `engine/events.py:72`). `MeshEventBus` supports typed subscriptions, wildcard subscriptions, history, and error-isolated delivery (`engine/events.py:87` through `engine/events.py:100`). `subscribe()` returns an unsubscribe function (`engine/events.py:141` through `engine/events.py:156`), and `emit()` accepts either a `MeshEvent` or type string plus payload (`engine/events.py:200` through `engine/events.py:213`).

The battle system should reuse this for boundary events such as `monster_battle_started`, `monster_battle_won`, `monster_caught`, and `monster_party_changed`. The internal turn resolver should remain pure and should not depend on the event bus.

### Existing Combat Is Real-Time Only

Mesh has real-time action combat:

- `Health` is a behaviour with `max_hp`, `hp`, and `invulnerable` params (`engine/behaviours/health.py:56` through `engine/behaviours/health.py:65`). For player sprites, it pulls defaults from `GameStateController.get_player_stats()` (`engine/behaviours/health.py:73` through `engine/behaviours/health.py:86`).
- `Health.apply_damage()` subtracts incoming damage, applies player defense, resolves through the pure combat model, and emits hit/damage/death events (`engine/behaviours/health.py:121` through `engine/behaviours/health.py:156`, `engine/behaviours/health.py:169` through `engine/behaviours/health.py:229`).
- `Combat` is a behaviour that spawns a temporary hitbox on attack (`engine/behaviours/combat.py:77` through `engine/behaviours/combat.py:88`, `engine/behaviours/combat.py:126` through `engine/behaviours/combat.py:140`). The spawned hitbox is a scene entity with `Hitbox` behaviour and damage/target tag config (`engine/behaviours/combat.py:207` through `engine/behaviours/combat.py:235`).
- `EnemyAI` is a chase/attack behaviour, not a turn AI (`engine/behaviours/enemy_ai.py:92` through `engine/behaviours/enemy_ai.py:118`).
- `engine/combat_model.py` is pure and deterministic, but it resolves a flat real-time attack spec against target HP (`engine/combat_model.py:1` through `engine/combat_model.py:90`).

Player death already drives game-over. `on_entity_died()` sets `window.game_over = True`, shows the game-over screen, and pauses when the dead actor has `mesh_tag == "player"` (`engine/game_runtime/events.py:41` through `engine/game_runtime/events.py:46`). The game-over screen itself is a blocking overlay (`engine/ui_overlays/game_over_screen.py:15` through `engine/ui_overlays/game_over_screen.py:63`).

There is no creature/species/capture/breeding/type/turn battle subsystem in `engine/`. Searches for monster-RPG concepts only found unrelated editor/input “capture” code and no domain model.

## 1. Where a Battle Lives

### Decision: Battle Mode, Not Battle Scene

Battle should live as a **mode/controller on the running game**, not as a separate scene JSON and not as a passive overlay.

Proposed runtime objects:

- `MonsterBattleController`: pure-ish orchestrator owning the active battle state, side data, selected actions, turn resolution, result, and exit status.
- `MonsterBattleMode`: thin integration object owned by `GameWindow` or a future `ModeController`; starts/stops battle, pauses overworld, blocks gameplay input, and applies result.
- `MonsterBattleOverlay`: UI surface registered through `UIController`, draws HP/status/action menus, and forwards player choices to the battle controller.

Overworld pause/resume:

- On battle start, set `window.paused = True` or a more explicit future pause reason while keeping UI updates alive. This matches the existing tick path where paused mode still calls `window.ui_controller.update(delta_time)` and then returns before scene update (`engine/game_runtime/tick.py:219` through `engine/game_runtime/tick.py:221`).
- Register/show a blocking battle overlay. `UIController.input_blocked` already checks active elements' `blocks_input` (`engine/ui_controller.py:108` through `engine/ui_controller.py:111`).
- On battle end, apply the `BattleResult`, emit events, hide overlay, clear battle mode, and restore the previous paused state.

Result handoff:

```text
BattleResult {
  outcome: "won" | "lost" | "ran" | "caught",
  caught_instance_id?: str,
  defeated_species_ids: list[str],
  xp_awards: list[{monster_id, xp}],
  consumed_items: list[{item_id, count}],
  return_scene_path: str,
  encounter_id?: str,
}
```

The result mutates `GameState.values["monster_party"]`, `GameState.values["monster_box"]`, `GameState.values["monster_instances"]`, inventory values, and flags/counters as needed. It emits boundary events through `MeshEventBus`.

### Rejected: Dedicated Battle Scene

A dedicated battle scene would reuse the existing scene-transition system, but that system loads a scene (`engine/scene_runtime/transitions.py:125` through `engine/scene_runtime/transitions.py:130`). For a monster battle, the important operation is not loading a new authored world; it is temporarily pausing and then resuming the exact overworld state that produced the encounter.

Dedicated scenes create avoidable problems:

- The overworld scene may be hot with NPC state, spawned objects, day/night, camera, particles, and player position.
- Returning to the exact encounter origin needs extra save/restore context beyond the current spawn-id transition pattern.
- Battle logic would be coupled to scene JSON lifecycle and sprite entities even though most turn resolution should be pure data.
- Wild encounters would churn scene loads for a UI-heavy encounter that does not need world simulation.

Battle arenas can still be visually themed with backgrounds and sprites, but they should be assets in the battle overlay/mode, not standalone scene files for phase 0.

### Rejected: Overlay Only

An overlay alone can draw menus and block input, but it is not a good owner for battle state, save integration, XP/capture result application, or pause semantics. Mesh overlays are mostly update/draw/input surfaces; `UIElement` only defines `update`, `on_resize`, `draw`, and `blocks_input` (`engine/ui_overlays/common.py:21` through `engine/ui_overlays/common.py:39`). The overlay should remain a view/controller adapter, not the battle engine.

## 2. Creature Data Model

### Data Files

Use JSON data files parallel to quests/items:

- `assets/data/monster_species.json`
- `assets/data/monster_moves.json`
- `assets/data/monster_type_chart.json`
- later: `assets/data/monster_encounters.json`, `assets/data/monster_breeding.json`

This matches existing content patterns such as quests loading from `assets/data/quests.json` in `QuestManager.__init__()` (`engine/quests.py:39` through `engine/quests.py:47`).

### Species Schema

```json
{
  "id": "sproutling",
  "display_name": "Sproutling",
  "types": ["grass"],
  "base_stats": {
    "hp": 45,
    "attack": 49,
    "defense": 49,
    "sp_attack": 65,
    "sp_defense": 65,
    "speed": 45
  },
  "capture_rate": 190,
  "growth_rate": "medium",
  "learnset": [
    {"level": 1, "move_id": "tackle"},
    {"level": 3, "move_id": "leaf_jab"}
  ],
  "evolution": [
    {"method": "level", "level": 16, "species_id": "sproutlord"}
  ],
  "breed_groups": ["field", "plant"],
  "sprite": "assets/monsters/sproutling.png",
  "battle_scale": 1.0,
  "overworld_prefab_id": "sproutling_encounter"
}
```

### Battle sprite clips (`battle_sprite.clips`)

Species may optionally define a sliced battle sheet plus named animation clips. The loader validates clip names against a fixed vocabulary; missing clips at runtime fall back to `idle` without error.

**Sheet layout** (on `battle_sprite`):

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `sheet` | string | yes | Path to the PNG sprite sheet |
| `columns` | number | yes | Frames per row |
| `rows` | number | yes | Row count |
| `frame_width` | number | yes | Pixel width of one frame |
| `frame_height` | number | yes | Pixel height of one frame |
| `clips` | object | no* | Named clip definitions (*or legacy `idle_frames` + `fps`) |

**Per-clip fields** (each entry under `clips`):

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `frames` | number[] | — | Frame indices into the sliced sheet (0-based) |
| `fps` | number | `6` | Playback speed |
| `loop` | boolean | `true` | Restart after the last frame |
| `sheet` | string | parent `battle_sprite.sheet` | Optional per-clip PNG override |
| `frame_width` | number | parent `battle_sprite.frame_width` | Frame width when using a clip sheet |
| `frame_height` | number | parent `battle_sprite.frame_height` | Frame height when using a clip sheet |
| `columns` | number | parent `battle_sprite.columns` | Frames per row when using a clip sheet |

**Allowed clip names:**

| Clip | When the battle overlay requests it |
|------|-------------------------------------|
| `idle` | Default loop (required when using `clips`) |
| `attack` | Combatant uses a physical offensive move |
| `special` | Combatant uses a special-category move (falls back to `attack`, then `idle`) |
| `defend` | Combatant braces / guards |
| `hurt` | Combatant takes damage |
| `faint` | Combatant faints |
| `cheer` | Companion praised by the trainer |
| `cower` | Companion scolded |
| `flee` | Companion abandons the trainer |
| `victory` | Player-side combatant wins the battle |
| `capture` | Opponent during a Pocket Ball attempt (shake / broke free / Gotcha) |
| `status` | Afflicted combatant at turn start (asleep skip) |

**Worked example** (Shelltide with companion-era clips — art optional; undefined clips idle-fallback):

```json
"battle_sprite": {
  "sheet": "assets/sprites/shelltide.png",
  "columns": 7,
  "rows": 2,
  "frame_width": 128,
  "frame_height": 128,
  "clips": {
    "idle": { "frames": [0, 1, 2, 3, 4, 5, 6], "fps": 6, "loop": true },
    "attack": { "frames": [7, 8, 9], "fps": 10, "loop": false },
    "special": { "frames": [7, 8, 9, 10], "fps": 10, "loop": false },
    "defend": { "frames": [10, 11], "fps": 8, "loop": false },
    "hurt": { "frames": [12], "fps": 4, "loop": false },
    "faint": { "frames": [13, 14], "fps": 6, "loop": false },
    "cheer": { "frames": [15, 16], "fps": 8, "loop": false },
    "cower": { "frames": [17], "fps": 6, "loop": false },
    "flee": { "frames": [18, 19, 20], "fps": 10, "loop": false },
    "victory": { "frames": [21, 22], "fps": 8, "loop": true },
    "capture": { "frames": [23, 24, 25], "fps": 12, "loop": true },
    "status": { "frames": [26, 27], "fps": 4, "loop": true }
  }
}
```

Legacy species with only `idle_frames` continue to load unchanged; the loader synthesizes a single `idle` clip.

### Move Schema

```json
{
  "id": "ember",
  "display_name": "Ember",
  "type": "fire",
  "category": "special",
  "power": 40,
  "accuracy": 100,
  "pp": 25,
  "priority": 0,
  "effects": [
    {"kind": "status_chance", "status": "burn", "chance": 0.1}
  ]
}
```

### Instance Schema

```json
{
  "instance_id": "mon_000001",
  "species_id": "sproutling",
  "nickname": "Momo",
  "level": 5,
  "xp": 135,
  "nature": "brave",
  "ivs": {"hp": 12, "attack": 20, "defense": 8, "sp_attack": 4, "sp_defense": 9, "speed": 3},
  "current_hp": 18,
  "status": null,
  "moves": [
    {"move_id": "tackle", "pp": 35},
    {"move_id": "leaf_jab", "pp": 20}
  ],
  "breed_groups": ["field", "plant"],
  "gender": "female",
  "obtained": {"method": "caught", "scene": "scenes/sakura_grass.json"}
}
```

Derived stats should be computed by a new pure monster stat module, not by `GameStateController.get_player_stats()`. The existing player stats use global config and equipment/perks (`engine/game_state_controller.py:209` through `engine/game_state_controller.py:241`); monster stats need species, IVs, nature, level, status modifiers, and battle stages.

### Save Shape

Persist monsters under `GameState.values`, for example:

```json
{
  "monster_party": ["mon_000001", "mon_000002"],
  "monster_box": {
    "box_1": ["mon_000003"]
  },
  "monster_instances": {
    "mon_000001": { "...": "..." }
  }
}
```

This rides through the existing game-state export/import and slot-save path (`engine/game_state_controller.py:477` through `engine/game_state_controller.py:488`, `engine/save_runtime/payloads.py:474` through `engine/save_runtime/payloads.py:484`). Later, if schema discipline becomes necessary, these keys can graduate from ad hoc `values` into a typed save block.

### Authoring Story

Phase 0 should be hand-authored JSON plus tests. Editor and AI tooling should come after the core schema stabilizes:

1. Hand JSON for species, moves, type chart, and encounters.
2. Thin validators and CLI audit: unknown move ids, bad type ids, impossible learnsets.
3. Editor panels for species/move tables once data volume grows.
4. AI tools that propose species/moves/encounters by editing these JSON files, not by inventing runtime state.

## 3. Battle State Machine

Start strict turn-based. ATB can be a later mode once the pure turn resolver is stable.

### States

```text
idle
start_battle
intro
choose_action
choose_move
choose_item
choose_switch
resolve_turn
apply_player_action
apply_enemy_action
faint_check
forced_switch
capture_attempt
reward
win
lose
exit
```

### Turn Data

```python
BattleState(
    player_side=BattleSide(active_instance_id, party_ids),
    enemy_side=BattleSide(active_instance_id, party_ids),
    phase="choose_action",
    pending_player_action=None,
    pending_enemy_action=None,
    turn_number=1,
    battle_flags={},
    log=[]
)
```

Actions:

```python
MoveAction(actor_id, move_id, target_id)
ItemAction(actor_id, item_id, target_id)
SwitchAction(side, from_id, to_id)
RunAction(side)
```

### Type Chart

`monster_type_chart.json` should be a multiplier table:

```json
{
  "normal": {"rock": 0.5, "ghost": 0.0},
  "fire": {"grass": 2.0, "water": 0.5, "fire": 0.5}
}
```

Missing attacker/defender entries default to `1.0`.

### Damage Formula

Use a simple Pokemon-like formula, implemented as pure Python and tested headlessly:

```text
base = floor((((2 * level / 5 + 2) * power * attack / defense) / 50) + 2)
modifier = stab * type_effectiveness * critical * random_factor * status_modifier
damage = max(1, floor(base * modifier))
```

Where:

- `attack`/`defense` select physical or special stats from the move category.
- `stab = 1.5` if the move type is one of the attacker's species types.
- `type_effectiveness` multiplies across defender types.
- `random_factor` is deterministic in tests, normally sampled from `0.85..1.0`.
- Status, weather, held items, abilities, and multi-hit are later.

Do not reuse `engine/combat_model.py` for this formula. It is clean and pure, but it intentionally resolves flat real-time damage events (`engine/combat_model.py:19` through `engine/combat_model.py:49`) and does not know about species stats, types, moves, PP, status, capture, or turn order.

### Capture Flow

`ItemAction(ball)` enters `capture_attempt` only for wild battles.

Phase-0 catch formula:

```text
hp_factor = (3 * max_hp - 2 * current_hp) / (3 * max_hp)
chance = clamp01((species.capture_rate / 255) * ball_multiplier * hp_factor * status_bonus)
caught = rng.random() < chance
```

On catch:

- Create a monster instance from the wild opponent.
- Add to party if party has fewer than the configured cap, otherwise first available box.
- Consume the ball.
- End battle with outcome `caught`.
- Emit `monster_caught`.

On fail, log the shake/fail message and continue the turn.

### XP and Level

For the proving slice, XP can be basic:

```text
xp = floor(species.base_xp * defeated_level / 7)
```

Then apply to participating party monsters, recalculate level, and learn new moves from the species learnset.

## 4. Integration and Boundary

### Reuse

Reuse these Mesh systems:

- Event bus for boundary events and quest integration.
- `GameState.values` and slot saves for party/box persistence.
- Scene triggers/zones for encounter start.
- UI overlay registration/update/draw/input.
- Inventory values/items for balls, later.
- Scene transitions for overworld map traversal before/after battles, not for battle itself.

### Build Fresh

Build fresh:

- Species/move/type data loaders and validators.
- Monster instance and stat derivation.
- Turn state machine.
- Damage/type/status/capture formulas.
- Battle AI.
- Party/box domain operations.
- Battle UI model.

### Keep Real-Time and Turn-Based Combat Separate

The existing action combat stays as-is for overworld hazards, enemies, bosses, and player death. It is behaviour/sprite/hitbox driven. The monster system is party/instance/turn driven.

Shared events are fine at boundaries:

- `monster_battle_started`
- `monster_battle_turn_resolved`
- `monster_fainted`
- `monster_caught`
- `monster_battle_won`
- `monster_battle_lost`
- `monster_party_changed`

Do not make `Health` represent party monster HP. Do not make `EnemyAI` choose turn actions. Do not spawn `Hitbox` entities for turn moves.

## 5. UI Feasibility and Risk

UI is the #1 risk.

Mesh can carry the proving slice, but it does not yet have the mature menu toolkit a monster RPG needs.

What exists:

- `UIElement` gives overlays update/draw/resize and `blocks_input` (`engine/ui_overlays/common.py:21` through `engine/ui_overlays/common.py:39`).
- `UIController` stores `ui_elements`, registers them, updates/draws each element, and dispatches key presses in reverse order (`engine/ui_controller.py:26` through `engine/ui_controller.py:39`, `engine/ui_controller.py:76` through `engine/ui_controller.py:99`, `engine/ui_controller.py:215` through `engine/ui_controller.py:221`).
- Runtime inventory is a hand-coded text overlay with a selected index, blocking input while visible, arrow-key navigation, Enter/Space/E actions, and manual draw layout (`engine/ui.py:170` through `engine/ui.py:238`, `engine/ui.py:344` through `engine/ui.py:363`).
- There are shared widget primitives: `Rect`, `Padding`, `DrawInstruction`, `LayoutResult`, `Button`, `VStack`, `TextInput`, `Slider`, `Toggle`, and `ScrollList` are re-exported by `engine/ui_overlays/widgets.py:28` through `engine/ui_overlays/widgets.py:55`. The underlying widget code includes hit-testable `Rect` (`engine/ui/widgets.py:7` through `engine/ui/widgets.py:49`), `Button` with `hit_test()` and layout (`engine/ui/widgets.py:124` through `engine/ui/widgets.py:175`), and `TextInput` key/text helpers (`engine/ui/widgets.py:324` through `engine/ui/widgets.py:349`).
- Existing overlays such as main menu, pause menu, settings, quest log, shop, AI chat, and proposal inbox prove that hand-built panels are feasible.

What is missing for a full monster RPG:

- A reusable runtime menu stack with focus ownership and controller/keyboard/mouse parity.
- Grid/list selection for party, box, breeding, move learning, and inventory.
- Virtualized long lists, sortable/filterable tables, tabs, modals, confirmations, and detail panes.
- Data-bound forms for species/move editing if the editor becomes an authoring tool.
- A consistent runtime theme separate from editor-only dock assumptions.

Verdict on UI: **tolerable for MON-0 proving slice, not tolerable for a full monster RPG without a toolkit slice**. The first playable 1v1 battle can be hand-coded. Party summary, boxes, breeding, move learning, and hundreds of species/moves will become a drag unless we invest in reusable menu primitives early.

## 6. Proving-Slice Plan

Each slice should be independently testable and should keep pure battle logic headless.

### MON-0a: One Move and Faint

Smallest proof. Add pure monster battle model with:

- Two hard-coded/test fixture species.
- Two moves.
- One type chart.
- Derived stats.
- `resolve_move()` and `resolve_turn()` for one actor.
- Faint detection.

Tests:

- Normal hit reduces HP deterministically.
- Type effectiveness changes damage.
- A lethal move sets defender fainted.
- No UI, no scene, no save.

### MON-0b: Data Loaders and Validators

Load `monster_species.json`, `monster_moves.json`, and `monster_type_chart.json`.

Tests:

- Valid fixtures load.
- Unknown move ids in learnsets fail validation.
- Unknown types fail validation.
- Duplicate ids fail validation.

### MON-0c: Battle Controller State Machine

Add `MonsterBattleController` with explicit phases and action submission.

Tests:

- Starts in `choose_action`.
- Move action advances to resolution and returns to choice/win/loss.
- Faint moves to win/loss/forced switch as appropriate.
- Invalid action for current phase is rejected.

### MON-0d: Runtime Battle Mode Shell

Integrate with `GameWindow` without encounter triggers yet:

- Start a test battle from code.
- Pause overworld.
- Register/show blocking battle overlay.
- Keep UI updating while scene update is paused.
- End battle and resume overworld.

Tests:

- `scene_controller.update` is not called while battle mode is active.
- Battle overlay blocks gameplay input.
- End result clears battle mode and restores pause state.

### MON-0e: Encounter Trigger

Add an overworld encounter behaviour or zone:

- On player entering grass/zone, roll encounter table.
- Start battle mode with selected wild species/level.
- Carry return context: scene path, zone id, encounter id.

Tests:

- Encounter starts only when eligible.
- No encounter when disabled by flag/cooldown.
- Battle receives expected wild monster data.

### MON-0f: Battle UI Usable Path

Build minimal battle UI:

- HP bars/text.
- Log text.
- Fight / Bag / Run menu.
- Move list with PP and type.
- Throw ball action.

Tests:

- Key routing chooses Fight -> move.
- Bag -> ball enters capture attempt.
- UI blocks overworld inputs.

### MON-0g: Capture and Party Persistence

Implement ball item/catch result:

- Consume ball from inventory.
- Generate monster instance id.
- Add to party or box.
- Save/load preserves party, box, and instances through `game_state`.

Tests:

- Catch adds to party when space exists.
- Catch routes to box when party is full.
- Save payload contains monster data.
- Load restores monster data.

### MON-0h: XP and Level

Add XP and level-up:

- XP calculation.
- Level stat recalculation.
- Learnset move offer or auto-learn policy for phase 0.

Tests:

- Win grants XP.
- Level-up changes derived stats.
- Learnable move is added or queued.

### MON-0i: Menu Toolkit Investment

Before party/box/breeding scale:

- Runtime menu stack.
- Focus model.
- Selectable list/grid.
- Tabs.
- Scroll containers.
- Confirm modal.
- Common draw/input contracts.

Tests:

- Focus/input routing.
- Mouse and keyboard selection.
- Scroll bounds.
- Modal blocks lower menus.

## Verdict

The architecture is sound on Mesh **if battles are a mode with a pure turn-based core**. Mesh already has enough runtime infrastructure: pause boundaries, UI overlays, event bus, game state, saves, quests, scene transitions, and real-time overworld combat that can stay separate.

The real blocker is not battle math or scene integration. The real blocker is **UI/menu volume**. A 1v1 proving slice is practical with current overlays. A real monster-capture/breed RPG will require a runtime menu toolkit before party management, boxes, breeding, move learning, inventory, summaries, and species browsing become maintainable.

Recommendation: proceed with MON-0a through MON-0g only if we accept MON-0i as a required early investment, not a polish task.
