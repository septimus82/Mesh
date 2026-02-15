# Mesh Engine - Developer Guide

## Project Structure

The project is organized as follows:

-   `main.py`: The entry point of the application.
-   `config.json`: Global engine configuration.
-   `engine/`: Core engine code.
    -   `behaviours/`: Game logic components (AI, Player, Interactables).
    -   `game.py`: Main game loop and window management.
    -   `scene_controller.py`: Manages entities and scene loading.
        -   Entity access is mediated by `SceneEntityStoreController` (`scene_controller.entities`).
        -   Preferred access: `scene_controller.iter_entities()` / `scene_controller.entities.iter_entities()`.
        -   `scene_controller.entities` remains iterable for legacy callers.
    -   `editor_runtime/input.py`: Editor input entrypoint.
        -   `editor_runtime/editor_input_router.py`: Scoped route table + dispatch.
        -   `editor_runtime/editor_input_legacy_handlers.py`: Legacy key handling (moved out of input.py).
        -   `editor_runtime/editor_input_menu_handlers.py`: Menu/context menu mouse/key helpers.
        -   `editor_runtime/editor_input_transform_handlers.py`: Rotate/scale drag helpers.
        -   `editor_runtime/editor_input_drag_handlers.py`: Mouse drag/release handling.
        -   `editor_runtime/editor_input_click_handlers.py`: Mouse click handling (moved out of input.py).
        -   `editor_runtime/editor_input_text_handlers.py`: Text input routing (moved out of input.py).
        -   `editor_runtime/editor_input_key_handlers.py`: Pre-router key handling (moved out of input.py).
        -   `editor_runtime/editor_input_shortcut_handlers.py`: Shortcut resolution helpers (moved out of input.py).
        -   `editor_runtime/editor_input_dispatch.py`: Keyboard dispatch orchestrator (moved out of input.py).
        -   `editor_runtime/input.py`: Facade only (policy test enforces no inline logic).
    -   `editor/editor_undo_controller.py`: Undo/redo command execution + history snapshot facade.
        -   `editor/editor_undo_model.py`: Pure undo history model (cursor + slicing).
    -   `editor/editor_dock_controller.py`: Dock tabs/collapse/resize state + snapshot.
    -   `ui_overlays/undo_history_overlay.py`: Renders history list from the undo controller snapshot.
    -   `ui.py`: UI elements and overlays.
-   `scenes/`: JSON files defining game levels and menus.
-   `assets/`: Game assets (images, sounds, music, data).
-   `engine/tooling/`: Core tooling logic (CLI, pipelines, generation).
-   `engine/tooling_runtime/`: Runtime-safe tooling components.
-   `docs/`: Documentation.

## Setup

1.  **Install Python 3.11+**
2.  **Install Dependencies**:
    ```bash
    # Editable install
    python -m pip install -e .

    # Editable install with dev tooling (tests/lint/etc.)
    python -m pip install -e ".[dev]"
    ```
    (Prefer `pyproject.toml`-based installs; avoid legacy requirements-file workflows.)

## CLI Tools

The engine includes a command-line interface `mesh_cli.py` for common development tasks.

For CI/dev validation, prefer the first-class `verify-all` pipeline:

```bash
python -m mesh_cli verify-all --artifacts artifacts
```

### pytest-fast durations guard

The `verify-all` pipeline runs `pytest-fast` with `--write-durations` and records per-test timings in:
`.mesh/metrics/pytest_durations_fast.json`. The `pytest-fast-duration-guard` step compares totals against:
- `.mesh/metrics/pytest_fast_total_seconds.txt`
- `.mesh/metrics/pytest_fast_top10_seconds.txt`

It fails only if a baseline regresses by **both** +20s and +15%.

To intentionally refresh baselines:

```bash
python -m tooling.pytest_fast --write-durations
python -m mesh_cli verify-all --artifacts artifacts
```

Baselines are updated on a passing run. Keep them committed (or persisted in CI workspace) for stable gating.
Note: the guard is based on the default serial `pytest-fast` run; avoid `--xdist` when updating baselines.

### Local test tiers (Tier 0/1/2)

Use the lightweight tier runner for fast local feedback:

```bash
python -m tooling.test_tiers tier0
python -m tooling.test_tiers tier1
python -m tooling.test_tiers tier2
```

Tier summary:
- **tier0**: compileall + `pytest -m fast`
- **tier1**: `pytest -m "fast or integration"` + `verify-all`
- **tier2**: full `pytest -q`

Fast vs integration tests (headless contract):
- **fast**: Must be headless-safe and GL-free. No direct `arcade` imports, no `arcade.gl`, no SpriteList/GL context usage.
- **integration**: May use Arcade/GL/runtime. Mark with `@pytest.mark.integration` (and `@pytest.mark.slow` if heavy).
- Any test without an explicit marker defaults to **integration**.

CI runs:
- **fast-headless**: compileall + `pytest -m fast` with Arcade blocked via `MESH_TEST_BLOCK_ARCADE=1`.
- **integration-gl**: `python -m tooling.test_tiers tier1` (fast + integration + verify-all).

> **Windows Note**: If you encounter console buffer crashes or encoding errors when running the full suite (Tier 2) on Windows, use the dedicated hardened runner which redirects output to a file:
> ```bash
> python -m tooling.pytest_full
> ```

Optional xdist (if installed):

```bash
python -m tooling.test_tiers tier1 --xdist
python -m tooling.test_tiers tier2 --xdist --jobs 4
```

> See also: [CI Verify Bundle Pipeline](ci_verify_bundle.md) for GitHub Actions / GitLab CI integration.

## Clean Export

Create a clean source ZIP containing only git-tracked files needed to run/build.
Excludes `.venv/`, `__pycache__/`, `dist/`, `build/`, `.mypy_cache/`, `*.pyc`, `*.pyd`, etc.

```bash
# Default: creates mesh_clean_YYYYMMDD_HHMMSS.zip in current directory
python -m tooling.export_clean

# Custom output path
python -m tooling.export_clean --out release.zip

# Dry-run: list files without creating ZIP
python -m tooling.export_clean --dry-run
```

The packaging hygiene gate (`test_packaging_hygiene_gate.py`) runs as part of `pytest -m fast`
and will fail if forbidden directories (`.venv/`, `dist/`, etc.) exist in the workspace.

## Perf-run (CI)

The `perf-run` CLI produces a lightweight performance snapshot suitable for CI artifacts.

- JSON includes `schema_version` plus `meta.thresholds` and `meta.evaluation`.
- Optional coarse thresholds can fail the command if p95/max times exceed a limit.

Run locally:

```bash
python -m mesh_cli perf-run --replay replays/00_smoke_dump_state.json --frames 300 --warmup 30 --out artifacts/perf.json
```

## Prefab provenance (source + override chain)

### Console (in-game)

Print the winning source for the hovered/inspected prefab:

```text
prefab_source
```

JSON output (machine-readable):

```text
prefab_source --json
prefab_source p_tree --json
prefab_source_chain p_tree --json
```

Example JSON payloads:

```json
{"cmd":"prefab_source","prefab_id":"p_tree","source":"packs/beta/data/prefabs.json","ok":true}
{"cmd":"prefab_source_chain","prefab_id":"p_tree","chain":["assets/prefabs.json","packs/alpha/data/prefabs.json","packs/beta/data/prefabs.json"],"ok":true}
```

### CLI

Explain a prefab, including source and override chain:

```text
python -m mesh_cli prefab explain p_tree
```

JSON mode:

```text
python -m mesh_cli prefab explain p_tree --json
```

### Migrations
Upgrade content files (scenes, saves, etc.) to the latest schema version.
```bash
# Check for needed migrations (dry run)
python mesh_cli.py migrate scenes/my_scene.json --dry-run

# Apply migrations
python mesh_cli.py migrate scenes/my_scene.json
```

### Build Demo
Create a polished demo build in `dist/demo_content`. This command runs quality checks, polishes assets (e.g., removing unused properties), and packages the game.
```bash
python mesh_cli.py build-demo
```

### Scene Editing
Modify scenes directly from the CLI using the Plan system (supports undo/history).

```bash
# Add a transition trigger
python mesh_cli.py edit-scene scenes/town.json --add-transition scenes/dungeon.json --at 100,200 --spawn-id entry

# Update encounter settings
python mesh_cli.py edit-scene scenes/dungeon.json --budget 500 --elite-cap 2

# Place an NPC
python mesh_cli.py place-npc --role merchant --into scenes/town.json --x 300 --y 400

# Add a puzzle
python mesh_cli.py add-puzzle scenes/dungeon.json --prefix dungeon_puzzle --switch-x 100 --switch-y 100 --door-x 200 --door-y 200 --item potion
```

## Configuration

### Content Roots
The engine supports loading assets from multiple directories (e.g., for mods or DLC).
Configure `content_roots` in `config.json`:
```json
{
  "content_roots": [
    "mods/my_expansion",
    "assets"
  ]
}
```
The engine will search for files in the order specified. If a file exists in the first root, it will be used; otherwise, it falls back to subsequent roots.

## Running the Game

Run the game from the project root:
```bash
python main.py
```

## Building the Game

To create a standalone executable:
```bash
python tooling/build_game.py
```
The output will be in the `dist/MeshGame/` directory.

## Web build (Pygbag)

Best-effort WebAssembly build using Pygbag with a deterministic `pygbag.toml`.

Install requirements:
```bash
python -m pip install pygbag
```

Build command (uses `pygbag.toml` automatically):
```bash
python -m pygbag web_main.py
```
Or via tooling helper:
```bash
python -m tooling.build_web web_main.py
```

Output location:
- Configured in `pygbag.toml` (default `build/web/`).

Asset include/exclude:
- `pygbag.toml` includes `packs/**`, `assets/**`, `config.json`, `scenes/**`, `worlds/**`.
- Excludes dev-only paths like `.git/**`, `artifacts/**`, `tests/**`, `__pycache__/**`.

Run locally:
```bash
python -m http.server -d build/web 8000
```

Known limitations:
- Browsers require user interaction before audio playback.
- Filesystem access is sandboxed; keep asset references relative and bundled.
- Performance can vary by browser and device.

## Adding Content

### Creating Scenes
Scenes are defined in JSON files in the `scenes/` directory.
You can use the `Mesh Scene Spec` (`docs/mesh_scene_spec.md`) for reference.

### Adding Behaviours
1.  Create a new Python file in `engine/behaviours/`.
2.  Define a class inheriting from `Behaviour`.
3.  Decorate it with `@register_behaviour("MyBehaviour")`.
4.  Implement `on_update`, `on_event`, etc.

### Adding Items
Edit `assets/data/items.json` to add new items.

### Adding Quests
Edit `assets/data/quests.json` to add new quests.

### Quests (runtime)

- Quests are tracked in `GameStateController.quests` and persisted with saves.
- Quest model: `id`, `title`, `description`, `state` (`inactive`/`active`/`completed`/`failed`), optional `tags`, `requirements` (flags and counters that must be met to auto-complete).
- Behaviour: **QuestGiver** starts a quest when a configured event fires.
  - `quest_id`: quest to start
  - `listen_event`: event name (default `quest_start`)
  - `auto_activate`: if true, start immediately on event
- Quest Log UI: press the `show_quests` action (default `Q`) to toggle the Quest Log overlay showing active/completed quests.
- Console: `quest` lists/starts/completes quests (`quest active`, `quest start <id>`, `quest complete <id>`).
- Time-of-Day Gating: **TimeOfDayGate** enables/disables entities based on hours.
  - `start_hour` / `end_hour` define the active window (wraps across midnight if start > end).
  - `invert`: when true, active outside the window (e.g., night-only).
  - `affect_visibility`: toggles entity visibility.
  - `open_event` / `close_event`: optional events emitted when state changes.
  - Reads time from DayNight cycle or `game_state.variables["time_of_day_hours"]`.
- NPC Schedules: **NpcSchedule** switches an NPC's location or patrol route by time-of-day.
  - `schedules`: list of blocks with `start_hour`, `end_hour`, `mode` (`stand` or `patrol`).
  - `stand`: optional `x`, `y`, `facing` to move/face the NPC.
  - `patrol`: optional `patrol_id` and/or `patrol_points` pushed into the Patrol behaviour.
  - `enter_event`: optional Mesh event emitted when entering a block.
  - Reads time from DayNight or `game_state.variables["time_of_day_hours"]`; wraps across midnight.
- Shops & Vendors: **Vendor** opens a Shop panel and sells items.
  - Config: `currency_counter` (default `gold`), `stock` [{item_id, price, quantity}], optional `listen_event` to open, `buy_sound`/`fail_sound`, `buy_rate`/`sell_rate`, `sell_enabled`, `sell_whitelist`/`sell_blacklist`.
  - Shop UI supports BUY/SELL modes (toggle with Left/Right/Tab), shows prices (rates applied) and player gold; navigation uses arrows/Enter/Esc; player input is blocked while open.
  - Currency uses GameState counters; items go to `game_state.values.inventory`.
  - Example NightMerchant:
    ```json
    {
      "name": "NightMerchant",
      "behaviours": ["TimeOfDayGate", "Vendor"],
      "behaviour_config": {
        "TimeOfDayGate": { "start_hour": 20, "end_hour": 4, "affect_visibility": true },
        "Vendor": {
          "listen_event": "interact",
          "stock": [
            { "item_id": "potion_small", "price": 50, "quantity": 5 },
            { "item_id": "potion_large", "price": 150, "quantity": -1 }
          ]
        }
      }
    }
    ```

## World Data

- Optional `worlds/main_world.json` describes scene metadata and links:
  ```json
  {
    "id": "main",
    "start_scene": "village",
    "start_spawn": "default",
    "scenes": {
      "village": { "path": "scenes/village.json", "label": "Quiet Village" },
      "forest": { "path": "scenes/forest.json", "label": "Haunted Forest" }
    },
    "links": [
      { "from": "village", "to": "forest", "via": "DoorToForest" }
    ]
  }
  ```
- WorldController loads this at startup if `world_file` is set in config (default `worlds/main_world.json`). If missing, startup falls back to the existing `start_scene`/`main_menu_scene` behaviour.
- GameState stores `world_id` and `world_scene_key` when a world is active.
- Console: `world`, `world scenes`, `world neighbors <scene_key>` for quick inspection.

## Scene spawns and transitions

- Scenes may optionally declare named spawns:
  ```json
  "spawns": {
    "default": { "x": 100, "y": 120, "facing": "down" },
    "from_forest": { "x": 300, "y": 80, "facing": "left" }
  }
  ```
  If a spawn is requested and not found, the engine falls back to the `default` entry. Scenes without `spawns` continue to work as before.
- To start a scene at a specific spawn, set `settings.initial_spawn` in the scene JSON or set the `next_spawn_point` via game state/console before loading.
- Behaviour: **SceneExit**
  - Listens for an event (`listen_event`, default `use_exit`) and queues a scene change.
  - `target_scene`: path to the target scene JSON.
  - `target_spawn`: optional spawn id within the target scene.
  - Combine with TriggerZone/Interact to create doors/warps.

## Debugging

-   Press `F3` in-game to see the debug overlay.
-   Use the console (`` ` ``) to execute commands or check logs.
-   Check `mesh_dump.json` for a dump of the current scene state (if generated).

## Editor Mode

The engine includes a lightweight in-game editor for tweaking scenes.

**Note:** Editor Mode is only available when Debug Mode is enabled (toggle with `F3` or set `debug_on_start: true` in `config.json`).

### Controls

| Key | Action |
| :--- | :--- |
| **F4** | Toggle Editor Mode ON/OFF |
| **Left Click** | Select entity (or Place Entity if Palette is open) |
| **Arrow Keys** | Move selected entity (grid snap) |
| **R** | Cycle tool mode (Move -> Path -> Zone) |
| **TAB** | Toggle Property Inspector |
| **P** | Toggle Prefab Palette |
| **1-9** | Select Palette Item |
| **DELETE** | Delete selected entity |
| **CTRL+D** | Duplicate selected entity |
| **SHIFT+Arrow Keys** | With Zone tool active: resize the zone/hitbox |
| **CTRL+R** | With Zone tool active: cycle between zone behaviours |
| **T** | With Zone tool active: toggle between TriggerZone and Hitbox on the selected entity |
| **F6** | Save current scene changes to JSON |

### Editor internals (controllers)

The editor runtime is split into focused controllers to keep `editor_controller.py` lean:

- `EditorPanelsController` owns modal/panel visibility and UI layer registration.
- `EditorProvidersController` builds provider payloads deterministically.
- `EditorDockController` owns dock tabs, widths, collapse/maximize, and focus sync.
- `EditorHoverStateController` owns hover state for highlights/tooltips (menu/title, context, splitter, entity).
- `EditorWorkspaceController` owns workspace/settings load/save + autosave orchestration.
- Consumers should read dock state via the dock snapshot (`get_snapshot()` / `editor_dock_query.get_dock_snapshot`).
- `editor_dock_focus_model` maps dock snapshot + session flags to a focus target.
- `editor_focus_model` derives focus using session + dock snapshots and panel visibility queries (no ad-hoc state dicts).
- Input routing (`editor_input_router`/`editor_input_shortcut_handlers`) derives focus from session+dock snapshots via `derive_focus_target_for_controller(...)`.
- Command palette focus uses `derive_focus_target_for_controller(...)` + dock snapshots (no `collect_editor_state`).
- Command palette command list lives in `editor_commands_registry` (thin facade in `editor_commands.py`).
- Command palette key handling is implemented in `editor_command_palette_controller` (router delegates).
- `collect_editor_state` is legacy and only used inside `editor_focus_model`; new code should not call it.
- Command palette query/index state lives in `EditorSearchController` (`editor.search`).
- Panel search focus + per-panel search text (Outliner/Assets/History/Problems/Project) live in `EditorSearchController`.
- `ProjectExplorerController` handles Project Explorer tree/selection.
- `EditorProjectExplorerActionsController` orchestrates Project Explorer input + activation.
- `EditorSceneBrowseController` orchestrates Scene Switcher/Scene Browser interactions.
- `EditorSceneOpenController` encapsulates scene open/switch orchestration and unsaved-change guard flow.
- `EditorDialogueController` orchestrates Dialogue panel editing/rendering and quest context drawing.
- `EditorDebugOverlayController` encapsulates the editor overlay debug text rendering.
- `EditorOverlayController` orchestrates the editor overlay draw stack.
- `EditorToolController` encapsulates tool mode cycling.
- `EditorAnimationController` orchestrates Animator panel editing/rendering (including active-guarded draw).
- `EditorTileController` orchestrates Tile panel editing/rendering (including active-guarded draw).
- `EditorLightsController` orchestrates Lights/Occluder tools and runtime sync.
- `EditorShapeController` encapsulates path/zone/shape editing logic (input handlers call it directly).
- `EditorPaletteController` encapsulates prefab palette filtering/selection/thumbs, palette overlay drawing, and palette preview rendering.
- `EditorPrefabController` encapsulates prefab overrides + prefab shape promotion/apply.
- `EditorInspectorController` encapsulates inspector component input handling, inspector list/editing flow, focus toggling, selection overlay lines, and behaviour parameter editing (update/remove params, apply config maps, prefab base entity resolution).
- `EditorClipboardController` encapsulates clipboard state and copy/paste operations for entities (including HD2D overrides clipboard).
- `EditorHd2dController` encapsulates HD2D preset preview, commit, auto-apply, and upgrade operations for scene settings.
- `EditorDuplicateController` encapsulates alt-drag duplicate operations: begin, update, end, cancel, reset, and apply command.
- `EditorMarqueeController` encapsulates marquee box selection operations: begin, update, end, cancel, and reset.
- `EditorPlayController` encapsulates play session operations: start, stop, camera handling, and player spawning.
- `EditorKeymapController` encapsulates keymap override loading, parsing, and application.
- `EditorDrawController` encapsulates world-space drawing: selection highlight, tool visuals (patrol paths, zones), shape editing, lights overlay, and asset placement ghost.
- `EditorCursorController` encapsulates cursor state, hints, and gizmo overlay feedback (mouse position tracking, cursor affordance computation, transform gizmo state).
- `EditorProblemsActionsController` encapsulates problems panel actions: jump to problem (load scene, select entity), copy location to clipboard, reveal in project explorer, toast notifications.
- `EditorFindActionsController` encapsulates find/activate actions: activate commands, scenes, entities, assets, and problems from find-everything or command palette.
- `EditorEntityOpsController` encapsulates entity CRUD operations: find by name/id, create, delete, and apply rotate/scale transform commands.
- `EditorCommandDispatchController` encapsulates undo/redo command dispatch: applies and reverts commands by type for all 25+ command types (MoveEntity, AddEntity, EditLight, etc.).
- `EditorAlignController` encapsulates multi-select align and distribute operations: align left/right/top/bottom/center, distribute horizontal/vertical with full undo/redo support.
- `EditorEntityPanelsController` encapsulates outliner/inspector entity panels logic (including toggle open/close).
- `EditorHierarchyController` encapsulates hierarchy panel open/close, list/rename, input handling, and panel drawing.
- `EditorAssetBrowserController` encapsulates asset browser filtering/selection/placement flow.
- `EditorSearchController` encapsulates command palette + find-everything + panel-search orchestration.
- `CommandPaletteController` encapsulates debug command palette prompt/selection handling.
- `ProblemsController` encapsulates Problems panel state, scans, input routing, and preview/solve logic.

### Narrative Editing (Dialogue & Quests)

- Press `D` when a `Dialogue`-enabled entity is selected to open the dialogue panel.
- `UP/DOWN` moves between nodes; `SHIFT+UP/DOWN` moves between choices within a node.
- `TAB`/`LEFT`/`RIGHT` change the active field; `ENTER` edits the field; `ESC` cancels or closes.
- Edits push `EditDialogue` commands onto the undo/redo stack (Ctrl+Z / Ctrl+Y) and write back to `behaviour_config.Dialogue.dialogue`, so `F6` persists them to the scene JSON.
- The quest overlay lists quests from `assets/data/quests.json` and highlights quest IDs referenced by behaviours on the selected entity (e.g., `QuestProgressOnEvent` or set/require flags). Missing dialogue node references are shown as warnings.

### Editing Animations in the In-Engine Editor

- Select an entity that has the `Animator` behaviour and press `A` to open the animation panel.
- `UP/DOWN` changes the selected clip. `TAB`/`LEFT`/`RIGHT` switches fields (mode, fps, frames).
- `ENTER` edits the current field; for frames, type comma-separated values then press `ENTER` to save. `ESC` cancels/ closes the panel.
- Changes are recorded as `EditAnimation` commands (undo/redo with Ctrl+Z / Ctrl+Y) and update `behaviour_config.Animator.animations` immediately; press `F6` to write them back to the scene JSON.

### Tile/Terrain Painting

- Press `G` in Editor Mode to open the Tile panel (requires a scene tilemap).
- `UP/DOWN` pick a tile from the palette; `[` / `]` cycle target tile layers.
- Left Click paints the selected tile at the cursor grid cell; Right Click erases; Ctrl+Z / Ctrl+Y undo/redo.
- Changes are stored in tilemap overrides and saved with `F6` so the scene JSON preserves painted tiles.

### Lighting (v1)

- Scenes can define a top-level `lights` array: each entry `{ "x": 100, "y": 120, "radius": 160, "color": "#ffaa66", "mode": "soft" }`.
- A `LightSource` behaviour can be attached to entities; config fields: `radius`, `color`, `mode`, `offset_x`, `offset_y`, `enabled`.
- Lighting uses Arcade's LightLayer; ambient and enable/disable flags live in `config.json` (`lighting_enabled`, `lighting_ambient_color`).
- Lighting helpers live in `engine/lighting/types.py` (types), `engine/lighting/cookies.py` (light cookies), `engine/lighting/shafts.py` (light shafts), `engine/lighting/shadow_pipeline.py` (shadow rendering), `engine/lighting/shadow_selection.py` (shadow-light selection), `engine/lighting/occluder_utils.py` (occluder parsing), `engine/lighting/occluder_layer_builder.py` (occluder layer rebuild), `engine/lighting/static_light_builder.py` (static/dynamic light rebuild), `engine/lighting/lighting_stats.py` (lighting stats aggregation), `engine/lighting/polygon_raycaster.py` (shadow polygon ray-casting), `engine/lighting/shadowcast_snapshot.py` (shadowcast debug snapshot), and `engine/lighting/lighting_snapshot.py` (lighting state snapshot), all re-exported/used by `engine/lighting/__init__.py`.
- Editor Lights Tool (`L`): toggle lights mode, click empty space to add a light, click/drag to move, `Del` to remove, `Up/Down` (Shift for bigger steps) to change radius, `M` toggles mode, `C` cycles preset colors. Undo/redo works like other tools; save with `F6`.
- Day/Night: global cycle (config flags `day_night_enabled`, `day_length_seconds`, `day_start_hour`) interpolates ambient lighting over 24h. Scenes can override with `settings.time_of_day_hour`, `settings.day_night_enabled`, and `settings.day_night_cycle_length_seconds`. Dev console: `time_of_day`, `set_time_of_day <hour>`, `daynight on|off` (alias `day_night` on/off). Time-of-day persists in game state as `time_of_day_hours`.
- Behaviour: `ToggleSceneLights` listens for an event (`listen_event`) and toggles/forces on/off lights matching a `group` or `indices` in `scene.lights`. Mode options: `toggle`, `on`, `off`. Useful with `ToggleSwitch`/`TriggerZone` to drive torches or alarms.

### Volumetric Fog Overlay (v1)

- Render-only fog layer that tints world space after lighting; HUD/UI are unaffected. Defaults are off, so visuals are unchanged unless explicitly enabled.
- Engine config keys (global defaults): `fog_enabled`, `fog_rgba`, `fog_density`, `fog_noise_speed`, `fog_noise_amount`.
- Scene overrides live in `settings.*` with the same keys.
- Fog `fog_rgba` resolution: scene `settings.fog_rgba` wins; else engine `fog_rgba` (if non-default); otherwise fog inherits ambient tint RGB automatically.

Moonlight fog (scene settings):
```json
{
  "settings": {
    "fog_enabled": true,
    "fog_rgba": [120, 160, 255, 200],
    "fog_density": 0.35,
    "fog_noise_speed": 0.12,
    "fog_noise_amount": 0.20
  }
}
```

Toxic horror fog (scene settings):
```json
{
  "settings": {
    "fog_enabled": true,
    "fog_rgba": [120, 255, 160, 220],
    "fog_density": 0.5,
    "fog_noise_speed": 0.2,
    "fog_noise_amount": 0.35
  }
}
```

### Animator behaviour (auto state + overrides)

- Optional auto state switching (off by default):
  - `enable_auto_state`: switch between `idle_clip` and `walk_clip` based on `speed_threshold`.
  - `idle_clip` (default `idle`), `walk_clip` (default `walk`), `speed_threshold` (default `1.0`).
  - `override_duration` (default `0.2`) default timer for temporary overrides.
  - `directional_mode`: set to `4-way` to use directional clips (`idle_*`/`walk_*` for up/down/left/right). `facing_default` sets the initial facing. PlayerController/EnemyAI update facing automatically so the Animator picks the right clip when directional_mode is enabled.
- Other behaviours can force a temporary clip: `animator.request_state_override("attack", "attack", 0.3)`; after the timer expires, idle/walk resumes based on movement.

### EnemyAI behaviour (state machine)

- States: idle/patrol -> chase -> attack, with optional flee and dead handling.
- Key params: `detection_radius`, `lose_radius`, `attack_radius`, `attack_cooldown`, `repath_interval`, `use_patrol`, `flee_below_health`, `target_tag`, `attack_event`.
- When a target tagged `target_tag` enters `detection_radius`, the enemy chases; within `attack_radius` it attacks (emits `attack_event` and/or calls Combat/Shooter behaviours). If health falls below `flee_below_health` (fraction of max), it flees until clear.

### Workflow
1.  Enable Debug Mode (`F3`).
2.  Enter Editor Mode (`F4`). Game logic will pause.
3.  **Selection**: Click an entity to select it. Move with Arrow Keys.
4.  **Inspector**: Press `TAB` to view/edit properties. Use Arrows to navigate/edit.
5.  **Palette**: Press `P` to open the palette. Select an item (1-9) and Left Click in the world to place it.
6.  **Edit**: Use `DELETE` to remove entities or `CTRL+D` to duplicate them.
7.  Press `F6` to save changes back to the scene file.
8.  Exit Editor Mode (`F4`) to resume gameplay.

### Zone Tool

-   Press `R` until the overlay shows `Tool: ZONE`.
-   Hold `SHIFT` while pressing the Arrow Keys to adjust the zone radius or hitbox size.
-   Press `T` to switch between the TriggerZone and Hitbox components when both are attached to the selected entity. `CTRL+R` still cycles through additional zone behaviours if there are more than two.

### Scene Hierarchy & Search
The editor includes a hierarchy panel to list and filter entities.

| Key | Action |
| :--- | :--- |
| **H** | Toggle Hierarchy Panel |
| **UP/DOWN** | Navigate list |
| **ENTER** | Select highlighted entity |
| **/** or **CTRL+F** | Focus Filter Input |
| **SHIFT+R** | Rename highlighted entity |

**Filtering:**
- Type to filter by entity name.
- Use `@BehaviourName` (e.g., `@Patrol`) to filter by behaviour.
- Unnamed sprites fall back to `Entity#<n>` labels so you can still find and filter them.
- Filters also match prefab display names, entity tags (from `mesh_entity_data["tags"]` or `mesh_tag`), and sprite class names. When nothing matches, the selection index is cleared so typing or deleting never causes errors.
- SHIFT+R enters rename mode for the highlighted entry; type the new name, press **ENTER** to commit, or **ESC** to cancel. Names are written back to `mesh_entity_data["name"]` and reflected immediately in the Inspector.
- Entity tags (from `mesh_entity_data["tags"]` or `mesh_tag`) appear inline, making it easier to identify doors, puzzles, hazards, etc.

### Prefab Palette Data

The Prefab Palette (toggled with **P**) reads from `assets/prefabs.json`. Each entry looks like:

```json
{
    "id": "crate",
    "display_name": "Crate",
    "entity": {
        "name": "Crate",
        "sprite": "assets/sprites/crate.png",
        "layer": "entities",
        "solid": true,
        "behaviours": ["hitbox"]
    }
}
```

Fields:
- `id`: unique identifier for internal lookups.
- `display_name`: text shown in the palette overlay.
- `entity`: the same structure used in scene JSON (`name`, `sprite`, `layer`, `behaviours`, `tag`, etc.). `behaviours` should be an array; leave it empty if none are required.

To add a prefab, append a new object with those fields to `assets/prefabs.json`. The editor automatically reloads the file on the next run--no Python changes needed.

## Diagnostics / SelfTest

- Run quick engine smoke checks (behaviours, scenes, worlds) without the full pytest suite:
  - CLI: `python mesh_cli.py selftest`
  - In-game console: `selftest`
- Output shows how many checks passed and lists any failing behaviours/scenes with their error messages.
- Use this when editing behaviours/scenes to catch obvious breakage before shipping or running the full test suite.
- For the full diagnostics pipeline (verify-all artifacts, debug-report/health-report CLIs, editor debug overlay), see [docs/debug_diagnostics.md](debug_diagnostics.md).

## XP & Player Stats

- Config (defaults in `config.json` / `EngineConfig`):
  - `xp_base`, `xp_per_level`
  - `player_base_max_hp`, `player_base_attack`, `player_base_defense`, `player_base_speed`
  - Per-level growth: `player_hp_per_level`, `player_attack_per_level`, `player_defense_per_level`, `player_speed_per_level`
- Game state:
  - Stored in `GameStateController` (`level`, `xp`), persisted with saves.
  - Derived stats computed from config.
- Behaviour:
  - `GrantExperience`: attach to enemies to award XP on their death event (`died`). Config: `xp`, `event` (default `died`), `target_tag`.
- Console:
  - `xp [get|add <n>|set <n>|level <n>]`
  - `stats` to print derived stats.

## Zero-Hand-Edit Demo Flow

This workflow demonstrates how to build a complete, playable region using only the CLI tools, without manually editing JSON files.

### Steps

1.  **Create Region**:
    ```bash
    mesh wizard region --name demo_region --template hub-interior-dungeon
    ```

2.  **Wire Scenes**:
    ```bash
    # Connect Hub to Interior
    mesh edit-scene scenes/demo_region_hub.json --add-transition demo_region_interior --at 10,10

    # Connect Interior to Dungeon
    mesh edit-scene scenes/demo_region_interior.json --add-transition demo_region_dungeon --at 5,5
    ```

3.  **Add Content**:
    ```bash
    # Add a Quest
    mesh new-quest demo_quest --title 'Explore the Dungeon' --objective 'Enter the dungeon'

    # Add a Vendor NPC
    mesh place-npc --scene scenes/demo_region_hub.json --role vendor --name 'Merchant'

    # Add a Puzzle
    mesh add-puzzle --scene scenes/demo_region_dungeon.json --type switch-door
    ```

4.  **Polish & Validate**:
    ```bash
    # Auto-wire any missing return transitions
    mesh auto-wire-transitions worlds/demo_region.json --apply

    # Polish assets and validate
    mesh polish worlds/demo_region.json
    mesh validate-all worlds/demo_region.json --strict
    ```

This flow ensures that all content is structurally valid and linked correctly.
