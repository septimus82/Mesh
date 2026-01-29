# Mesh Engine (Prototype)

Minimal Arcade-based runtime that opens a window, loads a JSON scene, and draws sprites. The current iteration focuses on scene-driven content and sets the stage for future behaviour/input/camera systems.

## Layout

```
Mesh/
|-- main.py
|-- mesh_cli.py
|-- config.json
|-- engine/
|-- mesh_cli/
|-- scenes/
|-- packs/
|-- assets/
`-- tooling/
```

## Architecture

The engine uses a component-based architecture where `GameWindow` acts as a Facade, delegating responsibilities to specialized controllers:

- **GameWindow**: Main entry point and service container.
- **SceneController**: Manages entities, layers, and physics/collisions.
- **CameraController**: Handles camera movement, zoom, shake, and bounds.
- **UIController**: Manages UI overlays (Inventory, Quest Log, Dialogue).
- **GameStateController**: Manages global state (flags, counters, values).
- **InputController**: Handles keyboard and mouse input.
- **ConsoleController**: Manages the developer console.
- **SaveManager**: Handles saving and loading of game state.

## Scene format

Scenes are JSON documents with explicit versioning, settings, layers, and entities. Example (`scenes/test_scene.json`):

```json
{
    "name": "Test Scene",
    "version": 1,
    "description": "A simple test scene with a few entities",
    "settings": {
        "background_color": "dark_blue_gray",
        "world_width": 1600,
        "world_height": 900
    },
    "layers": [
        { "name": "background" },
        { "name": "entities" },
        { "name": "foreground" }
    ],
    "entities": [
        {
            "name": "Player",
            "x": 400,
            "y": 300,
            "sprite": "assets/placeholder.png",
            "scale": 1.0,
            "layer": "entities",
            "behaviours": ["PlayerController", "Animator"],
            "patrol_points": [{"x": 200, "y": 300}, {"x": 600, "y": 300}],
            "follow_target": "Player",
            "animations": {
                "idle": ["assets/player_idle_1.png", "assets/player_idle_2.png"],
                "walk": ["assets/player_walk_1.png", "assets/player_walk_2.png"]
            },
            "animation_state": "idle",
            "trigger_radius": 80,
            "trigger_target": "Player",
            "on_trigger": "SomeCustomEvent"
        }
    ]
}
```

### Scene settings

- `version`: Schema version for future migrations.
- `settings.background_color`: Name of an `arcade.color` constant (case-insensitive, underscores). Defaults to `dark_blue_gray`.
- `settings.world_width` / `settings.world_height`: Optional world bounds. When provided, the camera will be clamped within these limits; otherwise it moves freely.
- `settings.camera`: Advanced camera tuning (lerp speed, padding, zoom defaults, optional bounds, and trigger areas).
- `settings.render_sort_mode`: HD-2D render ordering mode (`"y_sort"` or `"explicit_z"`). See [docs/mesh_scene_spec.md](docs/mesh_scene_spec.md) for details.

### HD-2D Rendering

The engine supports HD-2D style rendering with:

- **Deterministic entity sorting** via `render_layer` and `depth_z` fields on entities.
- **Parallax background planes** (`background_planes`) for layered depth.
- **Sprite drop shadows** that scale with depth (nearer = larger/darker).
- **Depth-based sprite tinting** for atmospheric depth shading (farther = darker/blue-shifted).
- **Faux sprite outlines** (rim light) for readability when enabled.
- **Two sort modes**: `y_sort` (classic top-down) and `explicit_z` (manual depth control).

Press `F3` in-game to toggle the HD-2D debug overlay showing entity render order.

### Layers

Layers are declared up front and mapped to `arcade.SpriteList` instances inside the engine (`background`, `entities`, `foreground`). Entities select a layer via `layer`; unknown layers are auto-created (with a warning) which keeps the format flexible.

### Entities & behaviours

- Required: `x`, `y` coordinates.
- Optional: `sprite`, `scale`, `rotation`, `layer`, `behaviours` (list of strings).
- Optional data helpers for behaviours (all default safely):
    - `patrol_points`, `patrol_speed`
    - `follow_target`, `follow_speed`
    - `animations`, `animation_state`, `animation_frame_rate`
    - `trigger_radius`, `trigger_target`, `on_trigger`
- Behaviours are implemented via `engine/behaviours`. Built-ins include `PlayerController`, `CameraFollow`, `Patrol`, `FollowTarget`, `Animator`, and `TriggerZone`. Unknown behaviour names emit a warning but won't crash the scene.

## Running the engine

```powershell
python -m pip install arcade pillow
python .\tooling\create_placeholder.py   # creates assets/placeholder.png (optional)
python .\main.py
```

On boot, the engine loads `main_menu_scene` if it is set in `config.json`; otherwise it loads `start_scene`. The current config starts in `packs/core_regions/scenes/Ridge Outpost_hub.json`.

The window should display the configured start scene, the player sprite can be moved with WASD, and the camera follows the player (clamped to the scene's world bounds when defined). Press `F3` to toggle debug mode and the FPS/camera overlay.

## Save & Load System

- **Save**: Open the console (`F1`) and type `save <slot>` (e.g., `save 1`). This creates a snapshot of the current scene, player position, and global game state in `saves/slot_<slot>.json`.
- **Load**: Type `load <slot>` (e.g., `load 1`) to restore the state.
- **Main Menu**: If a main menu scene is configured, the "Load Game" option looks for `saves/slot_1.json`.

## Quest & Journal quickstart

- Quest data lives in `assets/data/quests.json`. Each entry defines ordered stages, optional event triggers, and reward payloads that flip flags or increment counters.
- `GameWindow.quest_manager` exposes helpers like `start_quest`, `set_stage`, `complete_stage`, and `get_state_snapshot` so behaviours can manipulate or inspect progress without touching the JSON file. See `docs/quests.md` for the full schema.
- Press `Q` (the default `show_quests` action) to open the Quest Log overlay. It lists every quest plus the active objective text and an `X/Y objectives complete` counter.
- Press `TAB` (the `show_inventory` action) to open the Inventory overlay. It renders `game_state.values.inventory` using `assets/data/items.json`, so you can verify pickup rewards or console tweaks without leaving the scene.
- To try the demo, point `config.json.start_scene` at `scenes/door_field.json`, run `python main.py`, accept FieldWarden's errand, pick up the crate, and turn it in. The overlay, quest events, and reward hooks will update live as you progress.

## CLI Tools

The `mesh` CLI provides tools for running the game, validating scenes, and generating content.

```powershell
# Run the game (defaults to config.start_scene)
python mesh_cli.py play

# Run a specific scene
python mesh_cli.py play scenes/my_scene.json

# Validate a scene file
python mesh_cli.py validate scenes/my_scene.json

# Create a new scene
python mesh_cli.py new-scene level_2 --template topdown

# Create a new behaviour
python mesh_cli.py new-behaviour MyCustomBehaviour

# Rebuild the project index
python mesh_cli.py index

# Regenerate the AI context bundle
python mesh_cli.py ai-bundle
```

By default `index` scans the `scenes/` directory and writes `mesh_index.json` in the repository root. The in-game console also exposes `index [output] [scenes]` so you can rebuild the index without leaving the runtime.

## Contributing

See [AGENT_RULES.md](AGENT_RULES.md) for non-negotiable rules and check instructions.

## Running tests

All JSON CLI commands guarantee stdout is machine-readable JSON; logs and incidental noise go to stderr (or are suppressed during execution).

```powershell
python -m pip install -e ".[dev]"
# When installed, `mesh` is available:
mesh verify-all
mesh verify-all --artifacts artifacts
mesh verify-all --out-dir artifacts
mesh verify-demo
mesh verify-demo -- --maxfail=1
mesh verify-replays

# Fallback when console scripts aren't on PATH (repo checkout):
python -m mesh_cli verify-all
python -m mesh_cli verify-all --out-dir artifacts
python -m mesh_cli verify-all --artifacts artifacts
python -m mesh_cli verify-all -- --maxfail=1
python -m mesh_cli verify-demo
python -m mesh_cli verify-demo -- --maxfail=1
python -m mesh_cli verify-replays

`verify-all --artifacts artifacts` is the canonical CI-friendly mode: it always writes `artifacts/verify_all_summary.json`, and writes other artifacts only when their corresponding step succeeds (and indexing is enabled). If both `--out-dir` and `--artifacts` are provided, `--artifacts` is the canonical sink and indices are not duplicated.

`verify-all` outputs a single deterministic JSON object with:
- `ok`: overall success boolean
- `steps`: ordered step results; each step includes `code`, `error` (empty on success), and `artifact` (path or null). Skipped steps use `code=2` and `error="skipped: previous step failed"`.
- `artifacts`: the artifacts directory and the paths actually written (null when not written)

## Running from any directory (installed wheel)

If you installed the wheel and want to run CLI commands from outside the repo tree, set `MESH_REPO_ROOT` to the repo checkout path.

Precedence (highest -> lowest): explicit `--config` / `--content-root` flags (when a command supports them), then `MESH_REPO_ROOT`, then repo-root discovery (walk up from `cwd` for `pyproject.toml` / `config.json`), then `cwd`.

Examples:
- `MESH_REPO_ROOT=/path/to/repo python -m mesh_cli verify-all --artifacts artifacts`
- `MESH_REPO_ROOT=/path/to/repo python -m mesh_cli list-worlds --out artifacts/worlds_index.json`

Windows (PowerShell):
- `$env:MESH_REPO_ROOT = "D:\\path\\to\\repo"; python -m mesh_cli verify-all --artifacts artifacts`

python -m pytest -q -W error

# Deterministic replay suite (runs all scripts in replays/)
mesh verify-replays
python -m mesh_cli verify-replays

# A smoke replay is included at replays/00_smoke_dump_state.json.
# Add more scripts by dropping additional *.json files into replays/.

# Deterministic debug snapshot (prints JSON or writes to a file)
python -m mesh_cli dump-state --out state_dump.json

# Deterministic replay runner (runs a JSON script and prints/finalizes state)
python -m mesh_cli replay-script path/to/script.json --out final_state.json

Replay scripts can optionally assert final state without writing pytest, via `expect_state` (partial match against the final `dump_state`).

For larger expectation payloads, you can put expectations in a separate file using `expect_state_file`. If the path is relative, it is resolved relative to the replay script file.

```json
{
    "steps": [
        {"emit": "entered_zone", "zone_id": "ZoneOK"},
        {"dump_state": true}
    ],
    "expect_state": {
        "last_zone_id": "ZoneOK",
        "gold": 0,
        "active_quest_ids": []
    }
}
```

```json
{
    "steps": [
        {"dump_state": true}
    ],
    "expect_state_file": "expected_state.json"
}
```

Notes:
- `expect_state` only supports `str`/`int`/`bool` and `list[str]` values.
- `list[str]` uses exact list match (order + contents).
```

## Keymap overrides (editor)

Create `keymap.json` in the project root to override editor shortcuts.
The file format is a flat mapping of `action_id` -> `shortcut` string.
Set a shortcut to `""` (empty) to unbind it.
See `docs/keymap.example.json` for a starter template.
On editor init, unknown action ids and shortcut conflicts are logged once.
