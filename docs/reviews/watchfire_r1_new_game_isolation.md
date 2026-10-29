# Watchfire R1: Fresh-Game State Isolation

A focused reliability fix found by the creator trial *The Last Watchfire* (its report: Major 1). It is not M23E.
Base: `redesign/visual-editor` at `2d3f919`.

## The fault

Start a new game after a session that loaded a save, and the new game carries that save's progress. In the Watchfire
game, after a session that accepted the steward's task, lit the watchfire, saved and loaded that save, the next normal
start began with `task_accepted` and `watchfire_lit` set. The steward greeted a new player with the ending ("The
watchfire burns again"), and the fire was already lit. This happened in the exported build too. The only way out was
deleting `.mesh`.

## Why

The editor's remembered scene became a source of gameplay state:

1. Every game window builds the editor controller (`engine/game.py:537`). Its start-up
   (`engine/editor_controller.py:365`, `EditorWorkspaceController.load_on_startup`) ran for every launch: `main.py`,
   exported games, Studio and the legacy editor alike.
2. That start-up reopens the editor's remembered scene, along two paths:
   - `workspace.json` `last_scene_id` (with `last_camera_center`), in `_apply_workspace_settings`;
   - `.mesh/editor_session_state.json` `last_scene_path` (with its per-scene camera), in `_load_editor_session_state`.
3. The runtime records every scene it loads as the editor's remembered scene. `record_recent_scene` calls
   `window._on_recent_scene_recorded` (`engine/game_runtime/scene_ops.py:32`), which writes `last_scene_path`. Loading a
   save loads its slot as a scene, so `saves/slot_a.json` became the remembered scene.
4. The next start reopened that path inside the window's construction. The save loaded, and its flags, counters and
   values went with it. `main.py` then loaded the start room but never resets the game state, so the new game began
   with the old progress.

Both restoration paths were checked. In the Watchfire reproductions the leak came through
`.mesh/editor_session_state.json`, because Studio had never written a `workspace.json` there (`workspace_last_scene_id`
is `null` in every report). The `workspace.json` path does the same thing when that file names a scene, and it is
fixed and tested too.

One related gap: the main menu overlay's **New Game** (`MainMenuOverlay._handle_start_game_impl`) cleared only the
flags. Counters, values and quest progress from the game just played survived. The other main menu (the `MainMenu`
behaviour) already reset everything.

Pytest never saw the fault. `_should_skip_load_for_tests` turns this restoration off whenever `PYTEST_CURRENT_TEST` is
set, so the real-process tests below remove that variable from the game's environment.

## The fix (two engine files)

**`engine/editor/editor_workspace_controller.py`.** The rule is in one guard, `_reopens_editor_scene`, used by both
restoration paths:

- The remembered scene and its camera reopen in an **editor launch only**: `engine_config._mesh_launch_mode ==
  "editor"`, which `game_launch._run_editor` sets for Mesh Studio and the legacy editor. A game launch (`main.py`, an
  exported build, `mesh play`) starts where the game says, as it always should have.
- **A save slot is never reopened** as the editor's scene, not even in the editor. It is a saved game, not a room
  (`room_memory.is_save_slot`).

Kept as before:

- Recording the remembered scene and camera, and both files, are unchanged. Session persistence is not removed.
- The rest of the workspace (panels, docks, tools, recent scenes) still loads in every launch.
- Safe mode and a scene named on the command line still win as before.

**`engine/ui_overlays/main_menu_overlay.py`.** New Game resets with `game_state_controller.replace_state({})`, the same
as the `MainMenu` behaviour. A new game starts with no flags, counters or values, and with fresh quest progress (it is
kept in the state's values).

Not changed:

- Save files.
- **Load Game**, which loads exactly what was saved.
- `main.py` and the project template.

## Evidence

The trial project was never touched. Every run used a scratch copy of it: the rooms, assets and `main.py`, with no
`.mesh` or `saves`.

`tooling/watchfire_r1_sessions.py` plays two real processes. Each starts the game as a player does, with the project's
own `main.py` in a new process. It uses no test flags, so restoration runs as it does for a player. The windows are
hidden and the sound is muted. The game is played with its own keys, using the trial's player: arrows to walk, E to
talk and choose.

- **Process A:** new game → accept the steward's task → walk to the Old Crossing → strike the flint → save → load that
  save → close the window.
- **Process B:** a normal start, with A's saves and `.mesh` present (the project has no main menu, so no New Game step).
  It checks the new game's flags, talks to the steward (and declines), and walks to the watchfire. Then it explicitly
  loads A's save.

Each report also reopens the project in Mesh Studio and in the legacy editor (`launch_editor`, as `mesh edit` does),
both as left and remembering the Old Crossing.

| Run | Engine | First scene B loads | New game's story flags | Steward's opening | Watchfire | Load restores |
|---|---|---|---|---|---|---|
| Before, source project | 2d3f919 | `saves/slot_a.json` | task_accepted, watchfire_lit | "The watchfire burns again" (ending) | (not reached) | no |
| Before, exported build | the bundle's engine (2d3f919) | `saves/slot_a.json` | task_accepted, watchfire_lit | the ending | (not reached) | no |
| After, source project | fix | start room | none | the introduction, task offered | cold | yes: both flags, fire burning |
| After, exported build | fix (`mesh export build`, 1,065 files) | start room | none | the introduction | cold | yes |
| No previous save, before | 2d3f919 | start room | none | the introduction | cold | (no save) |
| No previous save, after | fix | start room | none | the introduction | cold | (no save) |

In the "before" runs, B stops at the steward: he offers only "Glad to help.", so the fresh path can't be played.

Editor reopen:

- Remembering the Old Crossing, Mesh Studio reopens it first, then its starting room. This is the same before and
  after, including the remembered camera.
- After the fix, Studio does not reopen a remembered save slot. It opens the starting room with its default camera,
  where before it would have loaded the save.

Reports and outputs, in `docs/reviews/watchfire_r1_evidence/` (scratch paths shown as `<scratch>`):

- `before_2d3f919_two_sessions.json`, `before_exported_build_two_sessions.json`, `before_2d3f919_no_previous_save.json`;
- `after_fix_two_sessions.json`, `after_fix_exported_build_two_sessions.json`, `after_fix_no_previous_save.json`;
- `before_fast_tests.txt` and `before_real_process_test.txt`: the new tests run against the 2d3f919 versions of the two
  engine files.

How to rerun:

- The "before" runs on the source project used the `Mesh-m23d` worktree, whose tree is identical to 2d3f919
  (`--engine D:/Games/Mesh-m23d`).
- The exported-build runs used `--bundle`, which plays a scratch copy of the bundle on its own engine copy.

## Tests

**`tests/test_new_game_isolation.py`** (fast; 9 tests):

- A game launch reopens neither the session's remembered room nor a remembered save.
- The editor reopens its room but never a save.
- `workspace.json`'s scene and camera reopen only in the editor, and never a save.
- The main menu's New Game clears flags, counters, values and quests.

Against the 2d3f919 files, **7 fail and 2 pass**. The two that pass are the "editor reopens its room" cases, which
should pass both before and after.

**`tests/test_new_game_isolation_gpu.py`** (the real-process check, GL-gated like the other `_gpu` tests): Mesh's starter
template (`mesh new --template starter`), started by its own generated `main.py` in two processes.

- A sets the story's two flags (as dialogue choices set them), saves, loads and exits.
- B starts normally. No save is loaded before the start room, the new game has no story flags, and loading A's save
  restores them.
- `PYTEST_CURRENT_TEST` is removed from the game's environment rather than any flag being added.

Against 2d3f919, B's start loads `saves/slot_a.json` first and the new game has both flags, so the test **fails**. With
the fix it **passes**.

Four existing editor-restore contract tests built fake windows with no launch mode. They now mark the window as an
editor launch. Their assertions are unchanged.

## Verification

Local (Windows):

- Ruff gate: OK.
- mypy: 73 errors, the baseline.
- Exception-policy and tier-marker ratchets: pass, with no baseline changed.
- Full default selection: 10,103 passed, 249 skipped, 163 deselected.
- GPU tier (`MESH_GL_SMOKE=1`, every GL-gated test): 254 passed, including the real-process test.

The first full run caught three things, all fixed before the PR:

- Two menu tests drive the overlay's New Game with a bare state holder that has no `replace_state`, so New Game keeps
  clearing the flags of such a holder.
- The session tool's catch is now narrow, so the exception-policy ratchet stays at its baseline.
- The new fast tests are marked `fast` for the tier-marker ratchet.

Required CI and its timing advisories are reported on the PR, separately. No budget was changed.

## Out of scope (still on the backlog)

- **The creator trial's other findings:**
  - pictureless objects (campfire, water) can't be interacted with or picked in 3D;
  - dialogue line numbers change after save and reopen;
  - no room rename;
  - Esc after right-click clears the selection;
  - the Evening preset washes out lamps;
  - export is CLI-only.
- **The legacy quest tracker** (`engine/quest_manager.QuestManager`, `game_state_controller.quests`) keeps its own
  `_quests`. `replace_state` doesn't reset it, and a load merges into it. This belongs to the two-QuestManagers
  reconciliation (task #128). Quest progress in the canonical `engine.quests.QuestManager` lives in the game state and
  is reset.
- **Removing the editor's start-up from game windows entirely**, so that a game never builds editor workspace state.
  That is a larger change. This fix draws the ownership line where the remembered scene is reopened.
