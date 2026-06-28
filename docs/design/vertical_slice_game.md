# Vertical Slice Game: Sakura Guard

Research slice: design the smallest complete Mesh game and audit the engine primitives needed for a playable intro -> play -> ending loop.

## Minimal Game Design

Working title: **Sakura Guard**.

Goal: a player can start from the title/menu, talk to a guard, clear a small combat arena, return, and see a real ending. The theme uses the existing parallax assets under `assets/bg/` (`parallax_sky.png`, `parallax_far.png`, `parallax_hills.png`) and a compact three-scene world.

### Flow

1. **Title / start**
   - Use the existing main menu entry path. New Game starts the slice world at the courtyard.
   - Player objective: "Speak to the guard."

2. **Scene A: Sakura Courtyard / intro**
   - Background: sakura/parallax sky and hills.
   - Player spawns near a guard NPC.
   - Guard dialogue starts the quest: "Drive the shadows out of the lower path."
   - A transition to the combat area is available after the quest starts.

3. **Scene B: Moonlit Combat Path**
   - One player, 2-3 `chaser_enemy`/enemy prefabs, simple bounds, and a return gate locked until the encounter clears.
   - Player has `Health`, `PlayerController`, and `Combat`.
   - Enemies have `Health`, `EnemyAI`, and contact or melee damage. Win condition: all enemies in this scene are dead.
   - Lose condition: player HP reaches 0, showing the existing game-over overlay.

4. **Scene C: Sakura Conclusion**
   - The guard acknowledges completion.
   - The quest is turned in or already complete.
   - A full-screen or modal victory/end-cap appears with a restart/return-to-title affordance.

### Acceptance Yardstick

The vertical slice is complete when a player can:

- Start a new run.
- Read/advance the guard intro.
- Move to the combat scene.
- Attack enemies and take damage.
- Either die and reach a retry/game-over state, or clear the encounter.
- Return/transition to a conclusion scene.
- See a VICTORY/ending screen and restart or return to title.

## Engine Gap Audit

### Summary Table

| Playable-loop primitive | Status | Evidence / notes |
| --- | --- | --- |
| Scene-to-scene transitions / world graph linking | **Supported** | `WorldController` loads scene keys, paths, links, start scene, and start spawn (`engine/world_controller.py:22`, `engine/world_controller.py:31`, `engine/world_controller.py:53`, `engine/world_controller.py:93`). Runtime scene switching resolves world keys and queues loads (`engine/scene_runtime/transitions.py:14`, `engine/scene_runtime/transitions.py:56`, `engine/scene_runtime/transitions.py:68`). Pending transitions are applied during update (`engine/scene_update_controller.py:21`, `engine/scene_lifecycle_controller.py:81`). `SceneTransition` can fire on interact, touch, or event (`engine/behaviours/scene_transition.py:71`); `SceneExit` can queue a target scene on an event (`engine/behaviours/scene_exit.py:34`). |
| Quest start, objective tracking, and completion detection | **Supported, with coupling caveat** | The real runtime manager is `engine.quests.QuestManager` (`engine/quests.py:39`). `GameWindow` constructs it and aliases it into `game_state_controller.quests` (`engine/game.py:509`, `engine/game.py:513`), even though `GameStateController` still imports the lightweight type. Quest start/progress can be driven by `QuestProgressOnEvent` (`engine/behaviours/quest_progress.py:69`) or direct manager calls (`engine/quests.py:195`, `engine/quests.py:205`, `engine/quests.py:210`). Event matching and flag/counter requirements complete stages (`engine/quest_runtime/progress.py:62`, `engine/quest_runtime/progress.py:307`, `engine/quest_runtime/progress.py:358`). HUD quest progress toasts/objective overlays already read active quests. |
| Quest completion -> trigger | **Partly supported** | Quest completion applies rewards, `set_flags`, counters, gold, XP, and emits `quest_completed` (`engine/quest_runtime/progress.py:209`, `engine/quest_runtime/progress.py:215`, `engine/quest_runtime/progress.py:237`). `SetGameStateOnEvent` can mutate flags/counters on arbitrary events (`engine/behaviours/set_game_state_on_event.py:93`). `SceneTransition` can listen for an event and change scenes (`engine/behaviours/scene_transition.py:71`). Missing: a clean generic "on quest completed, transition/show victory" authoring primitive. Today this is done by composing behaviours/events/flags. |
| Encounter-cleared detection: all enemies dead -> event | **Missing as a reusable primitive** | `Health` emits `combat_death` and `died`, then removes the sprite (`engine/behaviours/health.py:121`, `engine/behaviours/health.py:207`). Existing content handles specific encounters by manually mapping custom events, for example `cv_enemy_dead` in `scenes/combat_vignette_01.json:56` and `ep04_all_enemies_dead` content/tests (`scenes/episode_04_ep04.json:247`, `tests/test_episode_04_ep04_integration.py:528`). I did not find a generic behaviour/service that watches all enemy-tagged sprites in a scene and emits `encounter_cleared` once. This is a real GAME-1a blocker. |
| Player death -> game-over state/screen | **Supported** | `Health` emits `died` on lethal damage (`engine/behaviours/health.py:207`). `GameWindow` subscribes to `died` (`engine/game.py:664`). The death handler checks `actor.mesh_tag == "player"` and sets `window.game_over`, `game_over_screen.visible`, and `paused` (`engine/game_runtime/events.py:44`). `GameOverScreen` renders "YOU DIED" and "Press SPACE to Retry" (`engine/ui_overlays/game_over_screen.py:32`). |
| Victory state/screen | **Partly supported, not general** | `DemoCompleteOverlay` exists (`engine/ui_overlays/demo_complete_overlay.py:22`) and can be shown via `maybe_trigger_demo_complete_endcap` (`engine/ui_overlays/demo_complete_overlay.py:86`), but the current automatic trigger is hard-wired to the `demo.reached_cellar` flag (`engine/game_parts/state_facade.py:206`). Boss reward/victory UX toasts exist for golden-slice content, but not a reusable "VICTORY screen" with restart/return-to-title. This is a real gap for a complete game ending. |
| Restart / return-to-title | **Partly supported** | Game-over retry exists: while `window.game_over` is true, SPACE or attack clears game-over and requests a scene reload (`engine/game_runtime/tick.py:210`, `engine/game_runtime/tick.py:216`). Main menu/New Game flow exists and clears flags in the menu test path (`tests/test_main_menu_new_game_starts_world.py:49`, `tests/test_main_menu_new_game_starts_world.py:52`). `PauseMenu` exists (`engine/ui_overlays/pause_menu.py:21`). Missing: a general victory/restart/return-to-title controller for non-death endings. |
| Player attack and enemy combat | **Supported enough for slice** | `PlayerController` dispatches attack input (`engine/behaviours/player_controller.py:204`), `Combat.attack()` spawns an invisible temporary `Hitbox` (`engine/behaviours/combat.py:77`, `engine/behaviours/combat.py:126`), `Hitbox` applies damage to target-tagged entities with `Health` (`engine/behaviours/hitbox.py:72`, `engine/behaviours/hitbox.py:129`), and `EnemyAI` chases/attacks (`engine/behaviours/enemy_ai.py:92`, `engine/behaviours/enemy_ai.py:266`). |
| Sakura/parallax presentation | **Supported** | The current checkout contains `assets/bg/parallax_sky.png`, `assets/bg/parallax_far.png`, and `assets/bg/parallax_hills.png`. Background/parallax rendering code exists in `engine/background_layers.py:24`, `engine/background_layers.py:70`, `engine/parallax_model.py:111`, and `engine/scene_controller_parts/rendering.py:47`. |

### Surprising Couplings / Risks

- **Two quest-manager modules remain.** `engine/game_state_controller.py` imports the lightweight `engine.quest_manager.QuestManager`, but `GameWindow` replaces that slot with the full `engine.quests.QuestManager` instance. The full runtime path is intended and tested, but the type/import split is still a coupling risk for future gameplay work.
- **Victory is demo-specific.** The existing demo end-cap is valuable, but its automatic trigger is `demo.reached_cellar`, not a general victory state. Reusing it directly would bake the vertical slice into old demo naming.
- **Encounter completion is content-scripted, not systemic.** Existing demos can set flags when a hand-authored custom event fires, but a real combat room needs a general enemy-count/death watcher so AI/authored scenes do not require bespoke event code.
- **Scene links are metadata plus authored transitions.** World links describe adjacency, but the playable door/portal still needs a scene entity with `SceneTransition`/`SceneExit` configured to fire.

## Recommended Build Strategy

Build the game by fixing only the loop gaps that block a real start-to-finish playthrough, then use content slices to dogfood AI/editor authoring.

### Slice GAME-1a: One-Room Combat Loop

Smallest end-to-end playable proof.

Deliverable:
- A single combat scene with player + one enemy.
- Player can damage/kill enemy; enemy can damage/kill player.
- Add a generic `EncounterClearedOnDeath` or equivalent runtime primitive that watches enemy-tagged entities in the current scene and emits `encounter_cleared` once when none remain.
- Show win and lose states in the same scene: player death uses existing game-over; enemy cleared sets a flag/emits an event and shows a temporary "VICTORY" state.

Tests:
- Headless combat test: applying lethal damage to the enemy emits one `encounter_cleared`.
- Death path test: lethal damage to player sets `game_over` and visible game-over screen.
- Victory path test: clear enemy -> victory flag/screen visible; no double-fire on extra ticks.

### Slice GAME-1b: General Victory / End State Overlay

Deliverable:
- Extract or add a reusable `EndStateOverlay`/`VictoryOverlay` instead of using the `demo.reached_cellar` end-cap.
- It supports title, subtitle, retry/restart, and return-to-title/new-game actions.
- It can be triggered by an event or flag.

Tests:
- `victory` event shows overlay and blocks gameplay input.
- Retry reloads or restarts the configured scene/world.
- Return-to-title opens the main menu or queues the main-menu scene without corrupting game state.

### Slice GAME-1c: Three-Scene World Skeleton

Deliverable:
- Add a dedicated vertical-slice world with Scene A/B/C and links.
- Scene A has spawn, guard NPC, quest-start dialogue, and transition to combat.
- Scene B has the combat encounter and a locked/hidden exit that opens on `encounter_cleared`.
- Scene C has conclusion dialogue and victory trigger.

Tests:
- World validates and start scene resolves.
- World links are bidirectional or intentionally one-way with valid `SceneTransition` targets/spawns.
- New Game can target the vertical-slice world without breaking existing `main_world`.

### Slice GAME-1d: Quest Chain Integration

Deliverable:
- Add the vertical-slice quest definition.
- Guard dialogue starts the quest.
- `encounter_cleared` completes the combat objective.
- Entering/turning in at Scene C completes the quest and triggers victory.

Tests:
- Quest starts from dialogue event.
- Encounter clear completes the correct stage.
- Turn-in completes quest, applies completion flag, and shows victory.

### Slice GAME-1e: Sakura Presentation Pass

Deliverable:
- Apply the parallax assets to the three scenes.
- Place lighting, camera framing, collision, clear boundaries, and minimal props.
- Tune enemy positions/HP/damage for a 1-3 minute playthrough.

Tests:
- Scene files validate strictly.
- Parallax/background payload survives serialize/load.
- No missing asset paths.
- Single-player-instance/content smoke test.

### Slice GAME-1f: Playability Polish and Regression Harness

Deliverable:
- Add a deterministic "vertical slice smoke" runner: start world, simulate quest start, simulate combat win/loss, verify end states.
- Add a manual playtest checklist in docs or release notes.
- Lock main menu entry/config for the slice only if product direction wants it as the default demo.

Tests:
- End-to-end headless progression test for victory.
- End-to-end headless progression test for death/retry.
- Save/reload at Scene B keeps player HP, quest state, and encounter state coherent.

## Decision

Proceed with **Sakura Guard** as a three-scene vertical slice, but do not start by making all content. The first implementation slice should fix the engine-level combat-loop gap: a reusable encounter-cleared detector plus a minimal win/lose state in one scene. Without that, Scene B cannot honestly be a game loop; it would rely on bespoke scripted events instead of a primitive the AI/editor can use repeatedly.
