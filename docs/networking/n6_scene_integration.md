# N6: a Studio-authored scene played cooperatively

Design recorded at integration head `0513d5ac` (after #482 merged as `14e9d4f`), before the client and server were written. This extends the N0–N4 experiment. A normal Mesh scene can now be hosted by the graphics-free authority and played by two ordinary Mesh windows. This is not a general multiplayer mode: one room, one server process, loopback only. The trust limits listed in the [README](README.md) still apply.

## Run it

| Terminal | Command |
|---|---|
| Server | `python -m mesh_net.server --coop --port 46870` |
| First window | `python -m mesh_net.scene_client --port 46870` |
| Second window | `python -m mesh_net.scene_client --port 46870` |

The packaged room is *Co-op Gate*, in `mesh_net/coop/`. A wall with a locked gate divides the room. The lever on the near side opens the gate, and a bandit waits on the far side. Use arrows or WASD to move (eight directions). E pulls a lever in reach, or picks up a drop if one is in reach. Space attacks in the direction you last moved. F2 leaves, R resumes, N rejoins as a new character, and Escape closes the window. The caption shows the gate, the bandit's HP and your loot. Your own avatar is untinted; the other player's is tinted gold.

To host a scene from your own project, run `python -m mesh_net.server --project <folder> --scene packs/core_regions/scenes/<room>.json`. The server reports unsupported content (below) at start instead of running it differently. The window client currently opens only the packaged room.

The room was built by `tooling/make_coop_scene.py` with Mesh's own authoring code. It starts from Studio's New Project (blank template), then applies the `engine.project_ops` edits that Studio's tools perform: painted wall tiles, placed objects, pictures, the "Set up walking" animation, and behaviours with their settings. It keeps Studio's layout: a thin player reference in the room, with the shared `player` prefab in `assets/prefabs.json`. A test rebuilds it and compares it byte for byte. The same room also loads as an ordinary single-player scene (the strict loader keeps every object and behaviour).

## Where each system sits

| System (path) | Owner in N6 | How it connects |
|---|---|---|
| Scene loading: `SceneLoader` (engine/scene_loader.py), `load_scene` (engine/scene_lifecycle_controller.py) | Both | The client loads the room through the unchanged `GameWindow.load_scene`. The server applies the same migrations, schema check, scene/entity defaults and prefab resolution (`SceneLoader.apply_scene_defaults` / `apply_entity_defaults`). It skips behaviour-registry validation, because importing the behaviour modules imports Arcade. The scene's identity is the SHA-256 of that resolved scene. The server sends it in every snapshot; a client running other files refuses the session. The player's shared prefab is part of that identity. **Reused.** |
| Entity identity: `id` (`project_ops.unique_entity_id`), `scene_entity_store_controller` | Both | Authored objects are named by their Studio `id`, which must be unique and present on both sides. The client checks that its loaded sprites are exactly the scene's ids, and that each snapshot names only those. Connected players get server-issued integer ids that are never reused within a process, drawn as sprites named `net_player_<n>`. The scene's own player entity is only a template: the server never simulates it and the client removes it, so no authored player duplicates a networked one. **Adapter** (`mesh_net.scene_client`). |
| Entity lifecycle: `entities.enqueue_spawn/enqueue_despawn`, `_create_sprite`, `_rebuild_behaviours_for_sprite` | Client (presentation), driven by snapshots | Avatars and drops are spawned and despawned through the scene's own entity queue, so they render, sort and light like any scene object. **Reused.** |
| Collision and movement: `engine.physics_model.sweep_axis_separate`, collider shapes, `engine.physics_runtime.move_entity_with_physics` | Server | The pure collider-shape helpers (box, circle, auto footprint, picture box) moved from `physics_runtime` into `physics_model`. `physics_runtime` keeps the old names as aliases, so its behaviour is unchanged. The server builds plain records with the same fields a sprite has and runs the same sweep. Blocking objects are: solid entities, locked `DoorLock` doors, living solid enemies, and painted collision tiles. Tiles come from the scene's inline Studio `tiles` grids, one tile-sized box each at `engine.tilemap`'s positions. A test steps the authority and `move_entity_with_physics` side by side and requires identical positions every tick. A real-window test requires the window's tile collision sprites and object sizes to equal the server's. **Reused; no second collision engine.** |
| Combat rules: `engine.combat_model.resolve_attack`, `Combat`, `Health`, `DropTable` | Server | Damage goes through `resolve_attack`, as single-player's `Health.apply_damage` does. The player's `Combat` settings give damage, range, hitbox size and cooldown (seconds rounded up to ticks). The enemy's `Health` gives max and starting HP. `DropTable` gives drops, rolled once with its seed. **Reused rules; adapter for the hitbox** (below). |
| Behaviours and interactions: `engine/behaviours/*`, `engine.interaction` | Server reads definitions; the client keeps presentation only | The server never instantiates behaviour classes. It reads their authored settings: `PlayerController.speed`, `Combat`, `SwitchInteract` (`event_id`, `one_shot`), `DoorLock` (`unlock_event`, `starts_locked`), `Health`, `DropTable`. A test keeps the server's defaults equal to the classes' `PARAM_DEFS`. The interaction radius is `engine.interaction`'s 72 px cap, or an authored `interact_radius` if smaller. On clients, every behaviour except `Animator` is removed after load. The local avatar also keeps `CameraFollow`. Nothing local can arbitrate a shared outcome. **Adapter.** |
| Camera and rendering: `GameWindow.on_draw` (engine/game_runtime/tick.py), `CameraFollow`, `camera_controller` | Client | Each frame the client places what the snapshot says, runs `scene_controller.update` (Animator, the local avatar's `CameraFollow` with the room's authored settings), updates lighting, and calls the ordinary `on_draw`. Positions on the wire are scene coordinates; the moving camera is entirely the client's. The server imports nothing from the renderer. **Reused.** |
| `GameStateController`, event bus, input: `engine/game_state_controller.py`, `engine/events.py`, `engine/input_controller.py` | Not part of shared play | The client never calls `GameWindow.on_update`. The window's input map, quests, flags, saves, menus and event dispatch stay idle. Its key handler takes the keys first. A lever's event is never put on a local bus. |
| Scene transitions: `SceneTransition`, `scene_flow.request_scene_change` | None | One room per server process. Transition objects are scenery on the server and lose their behaviour on clients. |
| Save/load: `engine/save_manager.py` | None | Room state lives in the server's memory only, as in N4. |

### Authority rules the server enforces

- **Ownership, ordering and quotas.** These are N4's, unchanged: inputs are tied to the connection's entity and to increasing sequence numbers, at most eight frames per tick, with bounded frames and backlog. Replaying a sequence number does nothing. A spent resume credential is refused.
- **Movement.** Each component of the direction is -1, 0 or 1. Diagonals are normalised, as `PlayerController` does. Speed is `PlayerController.speed`, divided across 20 Hz ticks. Input expires after five ticks.
- **Lever.** A player using a lever must be within reach. If several levers are in reach, the nearest one is used. A one-shot lever works once. A gate can only change from locked to open. Players are resolved in entity-id order, so two players pulling in the same tick give one activation.
- **Attack.** An attack is a `hitbox_size` square, `range` ahead of the player in the direction of the last move, tested against each living enemy's collider shape. Two hits in one tick on a dying enemy: the second finds it dead (`resolve_attack`'s rule). Cooldown is counted in ticks.
- **Loot.** A drop appears when an enemy with drops dies. The first `take` within reach claims it, in entity-id order. An offline holder keeps it until it resumes. The loot exists exactly once.
- **Disconnect.** Leaving clears the latched action and movement. An action sent just before disconnecting has no effect. The character is kept for 600 ticks (N4's rule) and comes back with a new entity id.

### Wire changes

The join, welcome, resume and quota rules are N4's protocol version 1. Hosting a scene changes two messages:

- **`input`** may carry the action `use`, and diagonal directions.
- **`scene_state`** replaces `state`. It carries:
  - `tick`
  - `scene` (the identity)
  - `players` as `[entity, x, y, facing]`, with scene coordinates rounded to 0.01 and facing 0–3 (right, up, left, down)
  - `open` (ids of unlocked doors)
  - `used` (ids of used levers)
  - `enemies` as `[id, hp]`
  - `drops` (ids of enemies whose loot is on the ground)
  - `loot` as `[id, holder]` (holder is null while offline)

A room may hold at most 32 networked objects, so a full snapshot fits in one frame. The co-op room's largest full snapshot, with eight players, is 367 bytes.

## Code that changed outside `mesh_net/`

- **engine/physics_model.py and engine/physics_runtime.py.** The collider-shape helpers moved, unchanged, and `physics_runtime` keeps their old names. Nothing else in the engine, Studio, the scene format or saves changed.
- **pyproject.toml.** Ships `mesh_net/coop/*.json`.
- **Tooling.** `tooling/make_coop_scene.py` (the room's build) and `tooling/net_scene_probe.py` (the hidden-window test driver; checkout only, like N4's).
- **Tests.**
  - `tests/test_mesh_net_scene.py` (new)
  - a two-window test added to `tests/test_mesh_net_gpu.py`
  - the wheel test's package list and an installed co-op run in `tests/test_wheel_bundles_engine_data.py`

`mesh_net.demo` gained hooks used by the scene client: pluggable validators, a status line, and an arena factory. The disposable project moved into `mesh_net.scene_room.disposable_project`, with no behaviour change to the N4 demo.

## Stopped short (documented, not simulated differently)

- **HD-2D rooms.** Their floors, heights and ramps (`engine.hd2d.world`) are refused.
- **Collision tiles kept only in a map file.** Studio writes every painted layer into the scene inline, and only those layers are read. Tile flips and tilesets whose tile size differs from the map's are not handled. Studio's tilesets match the map.
- **Frame-list animation (`animations`/`sprite_sheet`) on a blocking object without a box or circle collider.** It is refused, because its drawn size is not known without Arcade. Animator-driven pictures use their starting clip's frame size, and plain pictures use the image size (Pillow).
- **The player template needs a box or circle collider.** Studio characters start with one (an auto footprint). This keeps the runtime on its own collider-shape path, which the server reproduces exactly. Arcade's alpha-trimmed hit boxes cannot run without Arcade.
- **Players do not block each other.** All players spawn at the template's position.
- **The enemy does not move or fight back.** `EnemyAI` and other gameplay behaviours are scenery to the server. Patrols, chasing, projectiles, triggers, dialogue, pickups, quests, transitions and inventory have no multiplayer contract.

## Differences from single-player found on the way (not changed by N6)

1. **A `DoorLock` door stays solid after it unlocks in single-player.** `DoorLock._update_collision` writes `entity.properties["solid"]`, which no collision code reads. The networked gate stops blocking when opened, which is what the behaviour's own comments intend.
2. **Single-player `Combat` aims at `sprite.angle`, or at `change_x/change_y`, which `PlayerController` never sets.** So a player's hitbox always appears to the right. The authority aims along the last movement direction.
3. **Single-player `Hitbox` overlap uses Arcade hit boxes.** For pictures without a collider, those are alpha-trimmed. The authority uses each enemy's collider shape (the co-op bandit's auto footprint).
4. **`project_ops.add_behaviour` on a prefab instance writes a `behaviours` list that replaces the prefab's when it resolves.** Adding `Combat` to an unexpanded player reference drops `PlayerController`. The generator edits the expanded player, as Studio does, so it is unaffected. Whether any Studio path calls it on other prefab instances is unverified.
5. **The client does not update the bandit's `HealthBar` from server HP.** The scene UI registers a bar for the bandit, but the client removed the `Health` behaviour that bar reads, and the client does not feed it the server's HP. The caption shows the server's HP instead.

## Evidence

All on Windows 11 with CPython 3.13.3 and Arcade 3.3.x, at the branch head named in the PR.

| Check | Result |
|---|---|
| `tests/test_mesh_net_scene.py` (12 tests) | The room is a fresh Studio build, and the authority's defaults are the behaviours'. It runs without arcade, pyglet, `engine.game` or `engine.studio`. Identity and entity mapping are consistent, including the identity changing when the shared player changes. Movement matches `move_entity_with_physics` tick for tick across about 220 ticks. The lever opens the gate once under simultaneous and duplicate use. A disconnect during an interaction has no effect. Two players kill the bandit, and loot is exclusive under a race and kept while offline. Inputs and snapshots are validated. Unsupported scenes are refused. Two socket clients share the room, resume without a ghost or duplicate, and a spent credential is refused. The room loads as a single-player scene. |
| `tests/test_mesh_net_gpu.py::test_two_windows_play_the_studio_scene_together` | Two hidden `GameWindow` processes, a real loopback server and the real renderer. Both windows build tile collision equal to the server's and object sizes equal to the server's. Both draw both avatars where the scene camera projects them (pixel difference with and without avatars). The template is gone and only presentation behaviours remain. The camera follows. Movement stops at the locked gate. The lever opens the gate in both windows. Both players strike the bandit, and death, the drop and one owner of the loot are shown in both. Disconnecting and resuming gives one avatar per player in each window, and the loot follows the character. 22 s, together with N4's window test. The Extended `gpu` lanes run it on Ubuntu (xvfb) and Windows, because it is gated on `MESH_GL_SMOKE`. |
| Installed wheel (`tests/test_wheel_bundles_engine_data.py`) | The wheel carries the co-op files. In an isolated venv, from a scratch folder, the installed server hosts the room with pictures from `share/mesh-engine`, loads no graphics, and two socket clients play it. One walks until the locked gate stops it at x 390.5. |
| Authority cost (8 players moving, 2,000 ticks, `perf_counter`) | Step: median 1.98 ms, p95 3.22 ms, maximum 3.80 ms. That is 4% of the 50 ms tick at the median. N4's arena takes 0.003 ms. Snapshot encode: median 0.034 ms, at most 367 bytes. Scene load: 0.32 s. These numbers are descriptive only; no CI threshold is set. Each move scans all 90 colliders, so a spatial index is the upgrade if rooms grow. |

## Rollback

Revert the N6 commits. Nothing persists: there are no settings, save data, scene-format changes or migrations. Studio is unaffected, and existing scenes load as before. If only the engine move must go, restore the helper definitions in `physics_runtime`; nothing outside `mesh_net` imports the new names.
