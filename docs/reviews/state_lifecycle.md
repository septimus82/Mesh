# Runtime state lifecycle (#422)

What happens to a game's runtime state on each transition: a fresh game, New Game, loading a save, a room change,
and Studio's Play and Stop. Each transition was traced through the code and then run on the real engine, in hidden
windows, on a simple project and on a realistically populated one. Three defects were found and fixed. The other
transitions behaved correctly and are now protected by tests.

## Who owns what

| State | Owner (canonical) | Rebuilt from it / derived |
|---|---|---|
| Flags, counters, values (variables), chapter, playtime, level, xp, equipment, perks | `GameStateController.state`, a `GameState` (`engine/game_state_controller.py`); `window.game_state` is a read-only view of it | — |
| Quest progress | `GameState.values["quests"]`; the full `QuestManager` (`engine/quests.py`, installed by `GameWindow`) keeps no state of its own | `QuestManager.reload_from_state` (auto_start quests, awaiting stages) |
| Room memory (objects collected or defeated) | `GameState.values["room_memory"]`, written by `scene_runtime.room_memory.remember_removed` when a room is left or a game is saved | A room's objects, filtered when the room is loaded |
| HUD "shown once" hints, quest-progress toasts | Flags (`hint_shown_*`) and `values["hud_last_quest_progress"]`, so they follow the state | Quest log and quest UI read `list_active_quests()` every draw (no copy) |
| A room's objects and their behaviours | The scene controller, rebuilt on every scene load | — |
| Event-bus listeners | Window-level ones live as long as the window (`engine/game.py`, plugins). A room's behaviours' ones belong to that room. | — |
| Game over | `window.game_over` / `game_over_screen.visible` / `paused` | — |

The lightweight `engine/quest_manager.py` is used only where there is no game window: the `GameStateController`
default, `runtime_only`, and the `plan_tester`, `trace_command` and `replay_script` tools. A `GameWindow` always
replaces it with the full manager. It has no `reload_from_state`, which `replace_state` already tolerates. There is
no evidence that it affects a game, so it is left alone.

## Transitions

| Transition | Game state | Quests | Room loaded | Notes |
|---|---|---|---|---|
| Fresh game (window start) | new `GameState` | definitions loaded, `reload_from_state` | the start room | — |
| New Game (`behaviours/main_menu.py`, `ui_overlays/main_menu_overlay.py`) | `replace_state({})`: a new `GameState` | re-synced (#446) | the start room, through `request_scene_change` | — |
| Studio Play | `replace_state({})` | re-synced (#446) | the edited room, `window.load_scene` | — |
| Studio Stop | `replace_state({})` | re-synced | the edited room again (`_reload`) | — |
| Load a slot (`SaveManager.load_game`) | `import_state` into the same `GameState`: flags, counters and values replaced wholesale | `load_from_dict` (the save's quests) | the save, through `request_scene_change` | a save-slot path isn't recorded in room memory (`is_save_slot`) |
| Room change | unchanged | unchanged | the next room | the room left is recorded in room memory |

## Defects found, and the fixes

**1. A room's behaviours kept listening after the room was gone.**

- **The cause:** behaviours subscribe to `window.event_bus` when they are built, and nothing removed those
  subscriptions when the room unloaded. Every visit to a room added its objects' listeners again, and the old
  objects kept reacting.
- **Measured** (one `IncrementCounterOnEvent` per room):
  - simple project: after 3 round trips, 4 listeners for one event; one event was counted 4 times;
  - in Studio, one `ping` per play-test was counted 3, 5, then 7 times;
  - 9-room project: all listeners grew 7 → 16 → 25 → 34 over three laps, and one event was counted 28 times.
- **The fix** is in `_rebuild_behaviours_for_sprite`, where every object's behaviours are built:
  - the bus records the subscriptions made while they're built (`MeshEventBus.record_subscriptions`);
  - those are tracked as the scene's (`track_scene_subscription`), which the next scene load already ends;
  - rebuilding an object's behaviours (a live edit) ends its previous ones.
- **Unchanged:** window-level listeners are untouched.

**2. New Game, and Studio's Play and Stop, wrote the old game's room memory into the new game.**

- **The cause:** they reset the state (`replace_state`) and then load a room. That load records what was collected
  in the room being left, into the new state.
- **The effect:**
  - a coin collected before New Game stayed gone in the new game, on both New Game paths;
  - after a play-test, Studio's editor hid the objects collected during it.
- **The fix:** a room records its removals only into the game session that loaded it. Scene load remembers the
  `GameState` it loaded the room under (`room_memory.session`), and `remember_removed` writes nothing if
  `replace_state` has replaced it since.
- **Unchanged:** a normal room change and a save still remember the collected coin (tested).

**3. A game over survived New Game and Studio's Play and Stop.**

- **The effect:** after one play-test ended in a game over, every later play-test began on the game-over screen and
  didn't advance.
- **The fix:** `replace_state`, the one call every new game makes, ends a game over the way the restart key does:
  the screen hidden and the game unpaused, and only when the game was over. A pause that isn't a game over is left to
  whoever paused (tested).

## A test that broke later tests' windows

`tests/test_no_gl_in_fast_mode.py` checks that the fast tier never loads `arcade.gl`.

- **What it did:** it removed every `arcade.gl*` module from `sys.modules` and never put them back. A test that
  built a new `GameWindow` later in the same run got a second copy of arcade's GL classes that doesn't match the
  first, and failed with `Can't instantiate abstract class OpenGLArcadeContext`.
- **Why it showed up now:** no earlier test built a real window after it alphabetically. The new
  `tests/test_state_lifecycle.py` is the first.
- **The fix:** it now puts the modules back after its check. The check itself is unchanged.

## Confirmed invariants (now tested)

1. **A fresh game starts with default state:** flags and counters empty, the auto_start quest active at its first
   stage, HUD hint flags set by the HUD. (Probe; `tests/test_state_lifecycle_gpu.py` for each play-test.)
2. **Loading a save restores its state with nothing of the running game:** flags, counters and values from after
   the save are gone, the quest is back where it was saved, and room memory is as saved
   (`test_loading_a_save_brings_back_its_state_and_nothing_of_the_running_game`).
3. **New Game resets flags, counters, values, quests, room memory and game over** (tests 4–6).
4. **Repeated Studio Play / Stop** keeps one listener, starts each play-test as a new game, and leaves the document
   unchanged and the room shown as written after Stop (`tests/test_state_lifecycle_gpu.py`).
5. **Auto-start quests and flag-driven stages work in every play-test** (#446; `tests/test_replace_state_quest_sync.py`
   and the GPU test above).
6. **UI reads canonical state:** the quest log and quest UI read `list_active_quests()` every draw, and the HUD's
   "shown once" hints and progress toasts are kept in the game state.

## Found, not changed (outside this bounded scope)

- **Continue from `savegame.json`** (`savegame.apply_savegame_to_window`, a lightweight `SaveGameV1` format) sets
  flags and merges quests only. Counters and values from a game already running would stay. At start-up the state is
  fresh, so it matters only for a Continue mid-session. It wasn't probed.
- **Loading a slot** uses `import_state`, not `replace_state`. A save written today has every key. An older save
  without `chapter`, `level`, `xp`, `equipment` or `perks` would keep the running game's values.
- **Other runtime state no transition resets**, all by code reading, none probed:
  - the toast queue (cleared only by a slot load);
  - cutscene runner state;
  - `monster_battle_mode_active`;
  - some boss and demo-hint window attributes;
  - the day/night clock (`time_of_day_hours` is saved but never read back).
- **An object removed during play** (collected, defeated) keeps its behaviours' listeners until the room unloads:
  the fix scopes listeners to the room, not to each object.
- **`SetGameStateOnEvent` may receive an event twice** (its own subscription and scene delivery). Not probed.
- **A pack room file carries a saved `state` block** (`packs/core_regions/scenes/Ridge Outpost_hub.json`), which
  replaces flags, counters and values when the room is entered. It's content, not the lifecycle code.
