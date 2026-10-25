# Milestone 16, Stage 3: Floors, Stairs, Bridges and Height-Aware Movement

**Verdict: PASS.** An ordinary player, moved only by held arrow keys through the ordinary `PlayerController`, can:

- walk the ground;
- climb a staircase onto a platform 2 m up;
- cross a railed bridge;
- come down the other staircase;
- walk under the same bridge.

These are real movement and collision steps against collision authored in Blender. Nothing is teleported, and the
elevation is not just drawn.

- Walls, ledges and railings stop the player, and the bridge deck doesn't block anyone walking underneath.
- Saves keep the character's floor, both on and under the bridge.
- An NPC finds its way between floors by the stairs.
- The camera follows the climb smoothly.

Rooms without floor collision, including every 2D room and Stage 2's outpost, move exactly as before.

Branch `feature/m16-stage3-floors` (from `redesign/visual-editor` at `8067c1c`), with a draft PR to
`redesign/visual-editor`. **Not merged; it is for owner review.**

## Part A: Stage 2 integration

| Step | Result |
|---|---|
| PR #350 contents | 29 files, as reported. Head `2f76899`, two commits (the lab's typing fix, then Stage 2). Mergeable. |
| CI on #350 | Required checks green: `arcade3-canary` and `web-smoke`, both runs. The full `tests` job has **the identical 26 failures as #347**, so nothing new. |
| Integration | Merged as `8067c1c`. `redesign/visual-editor`'s tree equals the PR head exactly (empty diff). |
| #344 / `main` | #344 is still a draft. `main` is untouched (`52d43a4`). |
| Pre-existing failures, tracked separately and not suppressed | **[#351](https://github.com/septimus82/Mesh/issues/351)**: the GPU test `test_background_layers_render_contract` (a hand-built controller lacks `_foreground_layers`; it fails on the base too). **[#352](https://github.com/septimus82/Mesh/issues/352)**: the full CI `tests` job's 26 failures, listed by group. |

## Part B: The model

### What existed

`settings.hd2d.structures` is a list of placed models: `model`, `x`, `y`, `elevation`, `rotation`, `scale`.

- The models have no identity or collision of their own.
- In Stage 2 the player walked around buildings because wall *tiles* had been painted under them.
- Entities have `elevation` (px, HD-2D only), saved with the scene. `depth_z` is 2D draw order.

### Choices

| Question | Chosen | Why (and what I rejected) |
|---|---|---|
| Structure identity | `structures[i].id`: a stable name, unique in the scene, without `/`. When omitted it defaults to `structure<i>`, so Stage 2 scenes still load. | Floors are named `<structure id>/<collider node>`, e.g. `crossing/col_bridge_deck`. That gives every walkable surface a stable, readable identity for saves, tests and later tools. A generated UUID would be unreadable; positional indexes would break when the list is reordered. |
| Where collision comes from | **Authored in Blender.** A separate object carries the custom property `mesh_collision`, which Blender's glTF exporter writes as node `extras` (`export_extras=True`). Collision nodes are never drawn. | Collision is explicit data travelling with the asset, so it is never guessed from the rendered mesh (as the brief asks). The stairs are the proof: drawn as eight steps, they collide as one ramp through the step fronts. A companion JSON file was the fallback, but it would drift from the model. |
| Kinds of collision | `solid`: a walkable top, solid underneath (platforms, stairs). `floor`: a walkable top, open underneath (bridge decks). `wall`: a box that blocks a body within its height range (hut, railings). | Three words cover the brief's cases and are easy to author. Walkable means the collider's upward-facing triangles (slopes up to 60°). |
| Surfaces at different heights, several over the same spot | Each walkable triangle is a plane `z = a·x + b·y + c` with an id. The ground rectangle is the solid floor `ground`. A 2 m spatial index lists what lies over any point. Under the bridge, two surfaces cover one spot: the ground at 0 and the deck at 2. | Real overlapping geometry. A 2D height map can't hold one spot at two heights. |
| Height-aware collision and floor identity | **One rule, `World.stand(x, y, z, footprint)`** (below). It returns `(elevation, floor)` or "can't be here". Movement, NPC navigation and loading all use it. | One definition means the player, NPCs and paths can never disagree about what is walkable. |
| Stairs and ramps | A sloped `solid` collider. Floors connect wherever their surfaces meet within one **step** (0.35 m), and only there. | Connections come from the geometry, so there is no separate portal graph to keep in sync. A platform edge is 2 m, more than a step, so it blocks: no falling, and no jumping up. |
| Bridges above and below | The deck is a `floor` collider, open underneath. Walking under it is allowed when the deck is above head height (body 1.5 m; the deck top is at 2.0 m). The railings are `wall`s only at deck height. | The headroom test is the same rule, so a lower bridge would block automatically. |
| Physical elevation vs `depth_z` | `elevation` is in px, like positions (32 px = 1 m). The world updates it as a character climbs. It is now a "sprite-synced" save field, so the climbed value is what gets saved. `depth_z` is not read anywhere in HD-2D. | It stays one concept: physical height. Draw order is still `depth_z`, for 2D. |

### The rule

A character is its 2D movement footprint (the player's feet box) plus a body 1.5 m tall, standing at an
elevation.

1. **Support.** Find the walkable surface under the footprint's centre that lies within a step (0.35 m) of the
   current elevation. If several do, take the highest. If none does, the character can't be there: a ledge, or the
   world's edge.
2. **Body.** At the centre and the four corners, nothing may be inside the body:
   - no `solid` surface above the feet (more than a step up): that would mean standing inside the solid;
   - no `floor` surface above the feet but below the head: too low to fit under.
3. **Walls.** No `wall` box may overlap the footprint within the body's height range.

`World.move` applies the rule per axis, as the 2D sweep does, so characters slide along walls. The scene's 2D solids
(wall tiles and solid objects) then still apply through the unchanged `move_entity_with_physics`, filtered to the
character's level. The character settles onto the surface it ends on: its elevation and floor are written to
`mesh_entity_data["elevation"]` and `mesh_hd2d_floor`.

### Compatibility

- **2D rooms** have no `window.hd2d_world`, so `PlayerController` takes its unchanged 2D branch. The check is
  `isinstance(…, World)`, so mocked windows can't trip it.
  - The only import a 2D game gains is the light `engine.hd2d.world` (settings only, no GLB reader). A test checks
    that the reader and renderer still aren't loaded.
- **Stage 2 HD-2D rooms** have structures without collision nodes, such as the outpost. They get no world and keep
  their wall-tile collision. The Stage 2 GPU tests pass unchanged.
- **Scenes:** `structures[].id` is optional. Any unknown key in a structure is now refused, with the key named.
- **Saves:** old saves have no runtime elevation, so their authored values are used.

### Toward reusable structures and prefabs (proposed, not built)

1. **Now (Stage 3).** The GLB *is* the reusable unit: the model plus its own collision. A structure instance is
   `{id, model, x, y, elevation, rotation, scale}`. Reusing the crossing anywhere needs no collision work.
2. **Next (no editor needed).** Add a structure catalog, `assets/structures.json`, alongside `prefabs.json`. It maps
   a structure prefab id to its model and defaults: name, footprint preview, allowed rotations.
   - Instances would gain `prefab: "stone_crossing"`, with `model` overridable.
   - Validation, MCP/AI ops and saves would use the catalog. It is the same shape as entity prefabs, but kept
     separate because structures are static and batched, not behaviour-driven sprites.
3. **Stage 5 (Studio).** Place, select and move structures by `id` in a 3D viewport, using the same catalog.
   Nothing in 1–2 depends on the editor.

Structures deliberately stay out of `entities`: the entity schema and runtime are sprite-centric, and turning
static batched geometry into sprites would cost batching. Revisit this if structures ever need behaviours.

## Part C: Playable height-aware movement

### What was added

- **`engine/hd2d/world.py`** (new): the `World` (surfaces, walls, spatial index), `stand`, `move`, the navigation grid
  and `path` (A*).
- **`engine/hd2d/glb.py`**: reads collision nodes into `Model.colliders`, and refuses an unknown kind, a collider
  without geometry, or a `solid`/`floor` collider with nothing to walk on.
- **`engine/hd2d/settings.py`**: structure `id`, and unknown structure keys refused.
- **`engine/hd2d/runtime.py`**: builds `window.hd2d_world` when the room's structures carry collision, and releases
  it with the room.
- **`engine/behaviours/player_controller.py`** (+4 lines): in a room with an HD-2D world it moves through
  `World.move`; otherwise the unchanged 2D path.
- **`engine/scene_runtime/persistence.py`** (+1): `elevation` is sprite-synced, so the climbed elevation is saved.

### The test scene

- **`tooling/hd2d_assets/build_crossing.py`** builds the structure in Blender, headless:
  - two stone platforms 2 m high;
  - an 8-step staircase each;
  - a 6 m railed bridge between them, deck top at 2.0 m and underside at 1.85 m, over an open underpass;
  - a hut with a roof.

  Its collision objects sit beside the art. Output: `stone_crossing.glb` (54 KiB, 45 drawn parts, 10 colliders).
- **`tooling/hd2d_floors_demo.py`**, `build` command: an ordinary blank-template project whose start room is the
  crossing on a 32 × 24 map, with:
  - the template's animated player;
  - the template's person, as the **warden**, on the east platform (elevation 64 px), with the new `FloorRoute`
    behaviour. It walks to the ground below and back, by the stairs.

  Not a launcher template.

Run it:

```
py -3.13 tooling/hd2d_floors_demo.py build "<new folder>"    # then run main.py in that folder to play it
py -3.13 tooling/hd2d_floors_demo.py check "<that folder>" <out dir>
```

## Part D: Collision and navigation

- **The NPC behaviour.** `FloorRoute` (`engine/behaviours/floor_route.py`) is a built-in behaviour, listed under
  Advanced in the behaviour guide as "Walk a route across floors (HD-2D)".
  - Its route is a list of feet points `[x, y, elevation]` in px.
  - Each leg is planned with `World.path` and walked with `World.move`, so it obeys the same rule as the player.
  - It replans when stuck. In a room without floors it does nothing.
- **The navigation grid.** It has 0.5 m cells and is built once, when first needed: 2,944 cells, 20 of them
  two-layered under the bridge.
  - Each cell holds every height the rule allows there.
  - Neighbouring cells connect only within a step, through a mid-point that is itself standable, and never by
    cutting a corner.
  - A* weighs 3D distance.
- **Not built:** pathfinding for the existing 2D behaviours (`Wander`, `FollowPath`) stays 2D. Only `FloorRoute`
  plans across floors.

## Part E: Validation, all in a hidden window

The evidence is in `docs/reviews/milestone16_stage3_evidence/`:
- pictures `01`–`10`;
- `check.json`, which holds every number below.

The player is driven by a script that holds arrow keys (`on_key_press` … `on_key_release` events) until a spot is
reached or the player stops moving. Positions are never set directly.

### Upper route, then lower route

| After | Feet (m) | Elevation | Floor | Visible / total px |
|---|---|---|---|---|
| start | 16.0, 3.0 | 0 | ground | 2672 / 2672 |
| ← to the west stairs' foot | 9.98, 3.0 | 0 | ground | 1935 / 1935 |
| ↑ half way up (`02_stairs.png`) | 9.98, 6.52 | **1.008** | crossing/col_stairs_west | 2651 / 2651 |
| ↑ onto the west platform (`03`) | 9.98, 11.52 | **2.0** | crossing/col_platform_west | 2592 / 2592 |
| → mid-bridge (`04_bridge.png`) | 16.0, 11.52 | 2.0 | **crossing/col_bridge_deck** | 1559 / 1935 (near railing) |
| → onto the east platform (`05`) | 22.0, 11.44 | 2.0 | crossing/col_platform_east | 1935 / 1935 |
| ↓ down the east stairs (`06`) | 21.94, 3.0 | **0** | ground | 2746 / 2746 |
| ← ↑ under the bridge (`07_under_bridge.png`) | 16.0, 12.06 | **0** | **ground** | 2152 / 2594 (deck overhead) |
| ↑ through the underpass (`08`) | 16.0, 18.0 | 0 | ground | 2594 / 2594 |

- Mid-bridge and under the bridge are **the same x, and almost the same y**: the two routes cross at one spot, at
  2 m and at 0 m.
- Walk clips seen while the keys were held: `walk_up`, `walk_down`, `walk_left` and `walk_right`.

### Blocking (`check.json` → `blocked`, all true)

| Pushed | Result |
|---|---|
| North on the bridge, into the railing | Stopped at y 12.61. The railing is at 12.85, minus half the footprint (0.19 m). |
| East off the east platform's edge | Stopped at x 24.98 (the edge is at 25), still at 2.0 m: no falling. |
| East from under the bridge, into the platform's side | Stopped at x 18.66. The side is at 19, minus half the footprint (0.3 m). |

The fast tests also cover:
- walking into a platform from the ground;
- the side of a staircase at mid-height;
- the hut.

### Save and load

The save is made through the game's own save system (`SaveManager`, with its "Game loaded" toast). Before loading,
the player is moved away.

| Slot | Saved | Loaded |
|---|---|---|
| Under the bridge | (16.0, 11.98), 0 m, `ground` | **identical** |
| On the bridge | (16.0, 11.52), 2 m, `crossing/col_bridge_deck` | **identical** |

The same x and y with different heights restore correctly, because the floor is resolved from the saved elevation.

### The NPC and the camera

- **Warden**, over 30 s:
  - **3 trips down and 3 up**, always by the east stairs;
  - elevation spanning 0–2 m;
  - **standable by the rule on every one of 1,800 frames**.

  `10_warden_on_stairs.png` shows it mid-climb. The camera was pointed at it for that one picture, and the player is
  visible on the bridge.
- **Camera** (the vertical follow, over 929 frames of walking):
  - its target height moved from 0.8 to 2.8 m;
  - the largest change in one frame was **0.092 m**, so it is smooth with no jumps.

  Loading a save re-centres the camera by design, so that is excluded.

### Performance (RTX 4070; the 960 × 540 hidden window)

| | |
|---|---|
| `World.move` (player and warden, 2,798 calls) | **50 µs** median, 73 µs p95 |
| World build at room load (16 surfaces, 3 walls) | part of a 129 ms room load (the GLB read dominates) |
| Navigation grid (built once, on first path) | **35 ms**, 2,944 cells |
| One path, ground → east platform | **21 ms**, 24 waypoints. Once per leg, not per frame. |
| Whole game frame (update + draw + `finish`) | **2.95 ms** median, 5.64 ms p95 |
| Renderer | 7 draw calls, 270 triangles |

## Regression

| Check | Result |
|---|---|
| Fast tier (`tooling.test_tiers tier0`, `-W error`) | **4,397 passed, 0 failed** (8 skipped) |
| Targeted (behaviour, player, save, persistence, scene loader, lifecycle, tick, MCP, docs, physics, movement, collision, patrol) | **1,311 passed, 1 failed, then 0 failed.** The one failure was the docs contract that pins the number of built-in behaviours (63). Adding `FloorRoute` makes it 64, so the contract was updated to 64 and now also asserts that `FloorRoute` is documented; it was not loosened. The docs, behaviour guide, import sweep and MCP contract suites were rerun: 35 passed. |
| GPU tier (`MESH_GL_SMOKE=1`, every GL-gated file) | **73 passed, 1 failed, 1 skipped**. The failure is #351, which also fails on the base. The skip is the Stage 1 lab, which skips without NumPy. |
| New tests | `tests/test_hd2d_world.py`: 17, fast. `tests/test_hd2d_floors_gpu.py`: 5, GPU. Stage 2's HD-2D GPU tests: all pass. |
| Type gate / ruff gate / `type: ignore` | ok / ok / 0 |
| `tooling/visual_polish_check.py` (hidden Studio and game render) | **10/10** |
| Docs | `docs/behaviours.md` regenerated (`engine.tooling.generate_docs`). It now includes `FloorRoute`. It also picked up drift that was already on the base: `PictureByFlags` and two Dialogue flag fields were missing from the generated file. |

## Limitations

- **No falling or jumping.** Ledges block, and floors connect only where they meet within a step. A deliberate
  drop-down needs a later "one-way edge" concept.
- **Characters have one standard body** (1.5 m tall), whatever their sprite. Size-aware bodies come later if tall or
  small characters need them.
- **Walls are boxes.** A collider with an arbitrary rotation (not a multiple of 90°) is approximated by its rotated
  bounding box, which is conservative. Walkable surfaces are exact triangles at any rotation.
- **The navigation grid is 0.5 m.** Corridors narrower than about 0.6 m are not planned through, though the player
  can still walk them.
  - A route that passes several tall NPCs may need a replan; FloorRoute replans when stuck.
  - The grid is built per room on first use, in 35 ms.
- **FloorRoute doesn't save its progress through a route**: it restarts at its first point after a load. The NPC's
  own position and elevation are saved.
- **No editor support** (Stage 5): Studio edits the room in 2D. Collision is authored in Blender, and
  `build_crossing.py` shows the convention.
- **Lighting is unchanged** (Stage 4): sprites under the bridge are not shadowed by it.

## What I did not do

- Nothing past Stage 3: no lighting work (Stage 4) and no editor work (Stage 5).
- No merge of Stage 3, and nothing into `main`.
- **Filesystem:**
  - Everything was created in this task's own worktree (`D:\Games\Mesh-hd2d3`) and in named, new folders in the
    session scratchpad.
  - The scene builder refuses to write into an existing folder.
  - The check script only writes into its output folder and never deletes there.
  - Cleanup removed only the exact files this task created, after listing them.
- No visible windows, no OS input, no focus taken.

## Review follow-up (before merge): tunnelling

The owner's review asked whether destination-only height checks can tunnel. **They could. The defect was confirmed
by tests, then fixed.**

- **The defect.** A single long move was checked only at its destination. It passed through:
  - a 5 cm wall, at 3 m and 8 m steps;
  - a 10 cm railing with floor beyond it;
  - a 1 m gap between two platforms of equal height.

  Normal walking moves 2.5 px a frame, so the playthrough never showed it. But the game loop doesn't clamp
  `delta_time`, so a hitch of half a second is a 2.3 m step.
- **The fix**, in `World.move`: long moves are split into steps no longer than half the footprint's smaller side
  (0.19 m for the player). Every wall, railing or gap on the way then either overlaps some step's footprint or leaves
  it without support. A normal frame is still one step, so its cost is unchanged.
- **New `tests/test_hd2d_world_tunnelling.py`** (fast, 16 tests), covering:
  - thin walls at 0.5 / 1 / 3 / 8 m steps;
  - railings and gaps at 1 / 3 m;
  - a 6 m move off a platform edge;
  - standing height where floors overlap (0, 0.3, 1.8, 2.0 m, and 1.0 m refused);
  - characters on different floors at the same x/y: a solid character on the bridge doesn't block one walking
    under it, while one on the same floor does;
  - `PlayerController` using the unchanged 2D sweep when the room has no HD-2D world, or only a mock;
  - `PlayerController` moving through the world in an HD-2D room.
- **Results:** fast tier 4,413 passed, 0 failed. HD-2D GPU tests 10/10, so Stage 2 and Stage 3 are unchanged. Type
  gate and ruff gate ok.
