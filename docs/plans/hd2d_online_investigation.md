# HD-2D Online RPG — foundations implementation plan

> **RECONSTRUCTION — NOT THE ORIGINAL INDEPENDENT REPORT.**
> The independent technical investigation ("HD-2D Online RPG") was produced outside this repository and is **not
> available**. This document was written by the **coordinator** at the owner's request. It is made of:
>
> 1. **The investigator's findings**: four statements, quoted *exactly as the owner supplied them* (section 1).
>    Nothing else here comes from the original report.
> 2. **The coordinator's own verification** of each finding against the source, with a verdict and `file:line`
>    evidence (section 1), plus a read-only headless probe (section 1.5).
> 3. **The coordinator's plan**: architecture map, bounded tasks, gates, risks and owner decisions (sections 2–7).
>    Anything marked *(inferred)* was not proven from source or by a run.
>
> | | Commit |
> |---|---|
> | Investigator's audited baseline | `b24e287ce4f7a92eb0c5e1f3cc3acd1b44a27154` (`b24e287c`) |
> | Tip the coordinator inspected | `7560158436caea52c18cc69f76b1e509c371e7b7` (`75601584`) |
> | Difference | replay tick-sampling test infrastructure only (#588: `docs/replay_suite.md`, `mesh_cli/episode.py`, `mesh_cli/replays.py`, `tests/test_replay_tick_sample_pooling.py`). None of it touches HD-2D or `mesh_net/`. |
>
> All line numbers refer to `75601584`.

## 1. Investigator's findings, with the coordinator's verification

### 1.1 Shared floor solver
> *Investigator (as supplied):* "Shared floor solver: the existing headless solver correctly distinguishes ground at
> 0 m from a bridge deck at 2 m using actor elevation. A lightweight body climbed the stairs. The networking
> authority currently refuses that HD-2D room."

**Verdict: confirmed. One caveat changes how M1-A must be built.**

- **One rule decides where a character stands.** `World.stand` (`engine/hd2d/world.py:282-308`) takes the highest
  walkable surface within `STEP` (0.35 m, `world.py:47`) of the actor's current elevation `z`. It then rejects
  solids, low decks and walls inside the `BODY` (1.5 m, `world.py:48`). The elevation is read from
  `mesh_entity_data["elevation"]` in px (`elevation_of`, `world.py:153-157`). Movement writes it back in
  `_settle` (`world.py:500-510`).
- **Ground at 0 m and the deck at 2 m.** `tests/test_hd2d_world.py:44-45` covers the same x/y: (16, 12, 0) gives
  `(0.0, "ground")` and (16, 12, 2) gives `(2.0, "crossing/col_bridge_deck")`.
- **A lightweight body climbs the stairs.** A `SimpleNamespace` walker climbs to 64 px on `platform_west` and then
  crosses the bridge (`tests/test_hd2d_world.py:59-77`). The underpass is covered at `:80-90`.
- **The authority refuses the room.** `refuse_unsupported` (`mesh_net/scene_room.py:198-203`) raises
  `Unsupported("HD-2D rooms walk on 3D floors; this authority runs 2D collision only")` for any `settings.hd2d`
  value. `SceneRoom.__init__` calls it (`scene_room.py:309`). Every N7 room goes through it (`mesh_net/world.py:138`).
  The test is `tests/test_mesh_net_scene.py:243-285` (`test_unsupported_scenes_are_refused`, which includes an
  empty `{}` hd2d block).
- **Caveat (coordinator's finding):**
  - The solver is headless, but **moving through it is not graphics-free**. `World.move` and `World._step`
    lazily import `engine.physics_runtime` (`world.py:400`, `:427`). That module imports `engine.optional_arcade` (`physics_runtime.py:9`),
    which imports Arcade and pyglet when they are installed. Today the authority is gated as graphics-free by
    `tests/test_mesh_net_scene.py:78-84` and `tests/test_mesh_net_world.py:195`.
  - Single-player also builds `World` from the **renderer's** models (`engine/hd2d/runtime.py:114-122`). Studio does
    the same (`engine/studio_hd2d.py:1153`, `:1270`). There is no GL-free builder.
  - The 2D part of the step goes through `move_entity_with_physics` (`physics_runtime.py:455-567`). The net authority
    has its own Arcade-free twin of that function (`scene_room.move`, `scene_room.py:121-133`).

### 1.2 Renderer
> *Investigator (as supplied):* "Renderer: floors, underpasses, occlusion, lamp shadows, cutaway and billboards have
> real-window coverage. Multiplayer requires explicit local-player camera targeting rather than selecting the first
> player-tagged sprite."

**Verdict: confirmed.**

- **Real-window coverage.** All of these run in a hidden window and are gated by `MESH_GL_SMOKE=1`.
  - Floors and underpass, driven by key events: `tests/test_hd2d_floors_gpu.py:40-72`.
  - Cutaway and occlusion of the player: `tests/test_hd2d_cutaway_gpu.py:82-205`.
  - Lamp fixtures and shadows: `tests/test_hd2d_lamp_fixture_gpu.py:38`.
  - Billboards: `tests/test_hd2d_billboard_camera_gpu.py:291-335`.
- **The camera follows the first tagged sprite.**
  - `Hd2dRenderer.followed()` (`engine/hd2d/renderer.py:1256-1261`) returns the **first** sprite whose `mesh_tag`
    equals `settings.camera.follow`. That tag defaults to `"player"` (`engine/hd2d/settings.py:76`, `:255`). Camera
    target, cutaway and depth-of-field focus all use it (`renderer.py:1266`, `:1291-1307`, `:1508`).
  - The 2D engine has the same pattern: `find_primary_player_sprite` (`engine/scene_entity_store_controller.py:124-138`).
  - The net client spawns every avatar from a copy of the template, tag included (`mesh_net/scene_client.py:71-78`).
    So in an HD-2D room the renderer would follow whichever avatar comes first.

### 1.3 Asset pipeline
> *Investigator (as supplied):* "Asset pipeline: static Blender GLB import and reimport work. Blender 5.2.0 LTS was
> verified locally, and PixelLab account access was checked. Eight-direction sprite animation needs opt-in facing
> selection and Studio import support beyond the current four-direction workflow."

**Verdict: partly confirmed.** The source claims are confirmed. The environment claims were not re-verified.

- **Import and reimport: confirmed.**
  - `engine/hd2d/catalog.py:324` (`import_model`) and `:490` (`plan_reimport`) exist. The collider impact check on
    reimport is at `:436-483`.
  - The review doc `docs/reviews/milestone16_stage5b_blender_asset_pipeline.md` records PASS, with staged and
    rollback-safe writes. `load_glb` (`engine/hd2d/glb.py:355`) needs only PIL.
- **Blender 5.2.0 LTS and PixelLab access: not re-verified.** These are claims about the environment. The coordinator
  ran neither tool (no PixelLab calls without a budget).
  - The repository docs still say "Blender 4" (`docs/hd2d_preview.md:33`; stage 5B doc `:172`).
  - The PixelLab tooling is a spend ledger only (`tooling/pixellab_budget.py`).
- **Four directions only: confirmed.**
  - Animator `directional_mode` accepts `"none"` or `"4-way"` (`engine/behaviours/animator.py:92`, `:188-190`).
    Facing is bucketed into 4 directions (`:228-233`), clip names are built from it (`:309-316`) and `set_facing`
    takes 4 directions (`:318-322`).
  - Studio's sheet setup also uses 4 directions: `DIRECTIONS = ("down", "left", "right", "up")`
    (`engine/project_ops.py:1713`), `character_clips` (`:2020-2040`) and the inspector form
    (`engine/studio_inspector.py:599-600`). So does the player's facing (`engine/behaviours/player_controller.py:186-196`).
  - Online, `FACINGS` has 4 entries (`mesh_net/scene_room.py:47`) and the wire accepts facing 0..3
    (`scene_room.py:556-558`).

### 1.4 Networking
> *Investigator (as supplied):* "Networking: N7/N8 provide shared hubs, party instances, transitions, character
> persistence and loot claims. Movement, combat and interaction checks are currently planar."

**Verdict: confirmed.**

- **Hubs, instances and transitions.**
  - Each room has one shared instance, and expedition rooms get one instance per party (`mesh_net/world.py:1-8`,
    `:225-242`).
  - Doors and arrivals are read from Studio's `SceneTransition` and `spawn_point` (`world.py:127-164`; arrivals x/y only, `:143-146`). Transfer with
    rollback is at `world.py:489-540`.
- **Persistence and claims.**
  - N8 rules: `mesh_net/persistence.py:1-14`.
  - SQLite store with `characters`, `inventory`, `unlocks` and `claims` tables (`mesh_net/characters.py:52-80`). It
    holds **no position or elevation**.
- **Every check is planar.**
  - Movement: `scene_room.move` (`:121-133`) and `SceneRoom.step` (`:416-434`).
  - `_near`: `math.hypot` on x/y (`:436-438`). `_use` radius: `:453`.
  - `_attack`: a 2D `Aabb` hitbox (`:467-477`). `_take` uses `_near` (`:479-483`).
  - Doors: `Door.touches` is a 2D overlap (`world.py:77-81`).
  - The snapshot row is `[eid, x, y, facing]` with no elevation (`scene_room.py:485-494`), and the client checks for
    exactly 4 fields (`:556`).
  - `_door` refuses base-anchored doors and says "HD-2D … refused" (`world.py:174-175`).

### 1.5 Coordinator's headless probe (read-only)
Command: `py -3.13`, `PYTHONPATH=D:\Games\Mesh-HDPLAN`, with `engine.__file__` confirmed to be `D:\Games\Mesh-HDPLAN\engine\__init__.py`.

- `World` was built from `tooling/hd2d_assets/stone_crossing.glb`. `stand(16,12,0)` returned `(0.0, 'ground')` and
  `stand(16,12,2)` returned `(2.0, 'crossing/col_bridge_deck')`.
- A real `mesh_net.scene_room.Body` (not a sprite) walked north for 110 × 2.5 px. It ended at elevation 64 px on
  `crossing/col_platform_west`. **So the net body type already works with the shared solver.**
- Import timing:

  | Point in the probe | Arcade / pyglet loaded? |
  |---|---|
  | After importing `scene_room`, `glb`, `settings`, `world`, `river`, `scatter` | No |
  | After the first move (via `physics_runtime`) | Yes |

## 2. Architecture map (what each milestone touches)

```
                      Studio (engine/studio_hd2d.py)  ── builds World from renderer.models (:1153, :1270)
                                   │
   scene JSON ── engine/hd2d/settings.py (parse_hd2d) ──┐
   GLB files  ── engine/hd2d/glb.py (load_glb, PIL only) ┤
                                                         ▼
                      engine/hd2d/world.py  World: stand / move / _step / path      ◄── THE shared solver
                           │            │ 2D solids per level: engine/physics_runtime (Arcade)  ← M1-A seam
                           │            │                      engine/physics_model  (pure)
           single-player ──┤            └── mesh_net/scene_room.move (pure twin)
 runtime.configure_scene ──┘  (engine/hd2d/runtime.py:72-135; renderer owns models today)
 PlayerController.update  ──► World.move   (engine/behaviours/player_controller.py:112-114)
 FloorRoute (NPCs)        ──► World.stand/path (engine/behaviours/floor_route.py:83-107)
 saves                    ──► "elevation" field (engine/scene_runtime/persistence.py:212,255; saved_world.py:52)

 mesh_net/scene_room.py SceneRoom (N6) ── refuse_unsupported (:198) ── identity (:353-355) ── snapshot (:485)
 mesh_net/world.py World (N7)          ── room_defs → SceneRoom (:138), doors/arrivals (:127-186), identity (:198-199)
 mesh_net/persistence.py, characters.py (N8) ── claims, inventory; no position
 mesh_net/scene_client.py / world_client.py ── client builds SceneRoom from its own files (:123 / :50) and compares identity

 Renderer: engine/hd2d/renderer.py followed() (:1256) ← M3 camera seam
 Animation: engine/behaviours/animator.py, engine/project_ops.py character_clips, engine/studio_inspector.py ← M2 seam
 Assets: engine/hd2d/catalog.py import/reimport, tooling/hd2d_assets/*.py (Blender build scripts) ← M2
```

| Milestone | Touches | Depends on |
|---|---|---|
| M1-A | `engine/hd2d/world.py`, `engine/hd2d/runtime.py` (builder only), `mesh_net/scene_room.py`, `mesh_net/world.py` (arrivals carry elevation), tests | nothing new |
| M1-B | new `tooling/` scene builder, review doc + evidence, one gpu test; **no** renderer changes | existing tools |
| M2 | `tooling/hd2d_assets/` (Blender scripts), `animator.py`, `project_ops.py`, `studio_inspector.py`, catalog evidence | nothing in M1 |
| M3 | `renderer.py` (`followed`), `scene_client.py`/`world_client.py`, `protocol.py` + `scene_room.py` wire, `world.py` doors | **M1-A passed**; uses M1-B's scene |

## 3. M1-A — one floor interpretation in both runtimes

### 3.1 Where the single shared solver lives
- **Keep it in `engine/hd2d/world.py`.** `World` is already the single implementation used by single-player, NPC
  routes, Studio and reimport impact checks (`engine/hd2d/catalog.py:441-483`). Nothing gets copied into `mesh_net/`.
- **Two seams make it usable by the authority:**
  1. **A GL-free builder.** Move the "should this room have a World, and from what?" logic out of
     `runtime.configure_scene` (`runtime.py:114-125`) into a function in `world.py`, for example
     `build_world(hd2d, models, scene_entities) -> World | None`. Single-player keeps passing `renderer.models`.
     The authority passes models read with `load_glb` (PIL only, `glb.py:355`).
  2. **An injectable 2D step.** `World.move` / `_step` take the per-level 2D sweep as an argument. It defaults to
     `physics_runtime.move_entity_with_physics`, so single-player is byte-identical. The authority passes its existing
     pure `scene_room.move` (`scene_room.py:121-133`). Moving that twin into `engine/physics_model.py` is optional
     cleanup and is **not** required.
- **Out of scope:** no new solver, and no rewrite of `stand`.

### 3.2 What the refusal is, and what changes
- **Today.** `scene_room.py:199-200` refuses every `settings.hd2d` room.
- **After M1-A, the authority refuses an HD-2D room only where it would diverge from single-player:**
  - **Room plays 2D in single-player.** Single-player plays the room as 2D when `parse_hd2d(..., lenient=True)` or
    a GLB fails (`runtime.py:126-135`). The authority runs the same parse and builder, and refuses
    (`Unsupported`) if anything was set aside or failed. It never simulates a room that the client would draw
    differently.
  - **Water.** A room with rivers or wade-limited ponds stays refused in M1-A. `World._wade` reads `sprite.bottom`
    (`world.py:413`), which `Body` lacks, and wading events are a single-player side effect. Lifting this is
    **owner decision D4**.
  - **Spawn.** The player template, and every N7 `spawn_point` arrival, must stand: the template's `elevation`
    is used as `z` and `World.stand` must not return `None` there. Otherwise the room is refused, naming the entity.
    Today arrivals are x/y only (`world.py:143-146`), and `SceneRoom.spawn` too (`scene_room.py:319`).
  - Doors on raised floors stay refused until M3: `Door.touches` is planar (`world.py:77-81`).

### 3.3 Geometry/content identity before a client enters
- **Mechanism that already exists:**
  - `SceneRoom.identity = sha256([scene_hash, 2D geometry])` (`scene_room.py:353-355`), where `scene_hash` covers the
    resolved scene JSON (`:136-151`).
  - The client builds the same `SceneRoom` from **its own files** (`scene_client.py:123`; `world_client.py:50`).
    It rejects a mismatch on the first snapshot (`check_state`, `scene_room.py:549-550`) and on the N7 welcome
    (`world.py:198-199`, `check_welcome` `:600`, `world_client.py:183`).
- **Gap.** GLB bytes are **not** part of the identity. Today that does not matter, because HD-2D rooms are refused.
  Once they are accepted, a client whose `stone_crossing.glb` has different collision would enter undetected.
- **Change.** Add `World.collision_digest()`: a sha256 over a canonical dump of the World. It covers surfaces
  (floor id, solid flag, corners rounded to 1e-4 m), walls, terrain heights, the river rules and the `STEP`/`BODY`
  constants. Fold this digest into `SceneRoom.identity`.
- **Effect.** Because the client computes the identity from its own files with the same builder, any
  collision-relevant difference fails at welcome, before the client enters the room. No new message is needed, and
  wire v1 is unchanged. Whether texture-only differences should also be detected is **decision D2**.

### 3.4 Bounded tasks (one PR each)

**M1-A-1 — `World` usable headless and graphics-free** (PR title, for example: `HD-2D: World builds and moves without
the renderer or Arcade`)
- **Scope:**
  - Add `build_world()` to `world.py`, and have `runtime.configure_scene` call it (Studio's two direct `World(...)`
    calls may stay).
  - Make `World.move` / `_step` accept the injectable 2D sweep.
  - Add `World.collision_digest()`.
- **Files:** `engine/hd2d/world.py`, `engine/hd2d/runtime.py`, new `tests/test_hd2d_world_headless.py` (marked
  `fast`, plus one `integration` subprocess test).
- **Acceptance:**
  1. A subprocess builds `World` from `stone_crossing.glb`, walks a `Body` up the stairs and across the bridge with
     the pure sweep, and asserts that `arcade`, `pyglet`, `engine.game` and `engine.studio` are not in
     `sys.modules`. This mirrors `test_mesh_net_scene.py:78-84`.
  2. The digest is stable across processes (distinct `PYTHONHASHSEED`). It changes when a collider triangle moves by
     1 cm, and does not change when only a texture changes.
  3. These still pass unchanged: `test_hd2d_world.py`, `test_hd2d_world_tunnelling.py`,
     `test_hd2d_world_turned_walls.py` and `test_hd2d_floors_gpu.py`.
- **Gates:** CI (pytest matrix, verify, installed, acceptance, **replays: required suite with unchanged goldens**)
  and Extended (extended lane plus **both gpu lanes**, because `runtime.py` changes the play path). Run the GPU tests
  locally with `MESH_GL_SMOKE=1` and `-W error`.

**M1-A-2 — The N6/N7 authority runs HD-2D floors** (`net: HD-2D rooms run on the shared floor solver`)
- **Scope:**
  - `refuse_unsupported` is narrowed as in §3.2.
  - `SceneRoom` builds the World (models via `load_glb`, paths contained as `runtime._contained` does,
    `runtime.py:28-41`).
  - `Body.mesh_entity_data["elevation"]` is seeded from the template, and spawn and arrivals are validated with
    `stand`.
  - `step()` calls `world.move(body, delta, solids, sweep=move)` when a World exists. Otherwise it keeps today's
    `move` path, unchanged.
  - The identity includes `collision_digest()`.
  - Wire v1 is unchanged: elevation stays server-side until M3.
- **Files:** `mesh_net/scene_room.py`, `mesh_net/world.py` (arrival elevation), `tests/test_mesh_net_scene.py`
  (update the HD-2D case at `:243-285`), new `tests/test_mesh_net_hd2d.py`.
- **Acceptance:**
  1. An HD-2D crossing room loads, and the 2D co-op room's identity is unchanged (no regression).
  2. Rooms that single-player would draw 2D are refused with the reason (broken GLB, lenient error, rivers).
  3. A template on an unstandable spot is refused.
  4. A client whose GLB collider differs computes a different identity, and `check_welcome` / `check_state` reject it.
  5. `test_authority_runs_without_graphics_or_studio` passes **with an HD-2D room**.
- **Gates:** CI with replays, plus Extended (the `tests/test_mesh_net_gpu.py` two-window tests live in the gpu lane
  and must stay green).

**M1-A-3 — Parity proof: identical traces in both runtimes** (`HD-2D: single-player and authority produce the same
supported positions`)
- **Scope:**
  - A parity harness drives one Studio-authored crossing (built with `tooling/hd2d_floors_demo.py build`: ground,
    stairs, 2 m deck, underpass, railings) with a scripted input sequence.
  - It runs on (a) the single-player path, `PlayerController` → `World.move` with the default sweep, and (b)
    `SceneRoom.step` with v1 input frames.
  - Per tick it records `(x, y, elevation, floor id, blocked?)`. Both sides use the same per-tick delta
    (`speed / HZ`, `scene_room.py:323`). Single-player is fed a fixed `dt = 1/20`, so frame quantisation is not
    the thing being compared.
- **Files:** new `tests/test_hd2d_net_parity.py` (headless). Optionally one gpu-lane case reusing
  `hd2d_floors_demo.check` and comparing its recorded legs with the authority's trace.
- **Acceptance (the programme's M1-A criteria):**
  1. The trace sequences match to 1e-6 px in x/y. Floor ids and elevations are identical.
  2. Two actors at the same x/y, one under and one on the deck: each keeps its own floor, and neither blocks the other
     through the deck. `_on_level`, `world.py:143-150`, applies to the 2D solids.
  3. Stair up, stair down and bridge-to-platform transitions happen on the same tick in both runtimes.
  4. Railings and ledges block in both.
  5. A changed collider is detected (from M1-A-2).
  6. A grep-style test asserts that `mesh_net/` defines no `stand`/`STEP`/floor solving of its own: **no duplicate
     solver**.
  7. Saves: `test_hd2d_world.py:124` and the floors save legs (`test_hd2d_floors_gpu.py:66`) are unchanged. There is
     no format change (elevation is already saved: `persistence.py:212,255`, `saved_world.py:52`).
- **Gates:** CI with replays, plus Extended with both gpu lanes if the gpu case is included. **The M1-A exit review
  happens here: M3 may start only after this PR merges with all gates green.**

*(inferred, to check in M1-A-3):* single-player spawning does not touch elevation. `engine/scene_runtime/spawn.py`
has no `elevation` handling, so arriving at a raised spawn marker could keep a stale elevation. If parity shows this,
the fix goes into the shared builder/World (one placement helper both runtimes call), not into two places.

## 4. M1-B — one representative HD-2D scene (parallel with M1-A)

**M1-B-1 — The scene, built through Studio** (`HD-2D: representative crossing-and-doorway scene (evidence)`)
- **Scope:**
  - A developer tooling script, modelled on `tooling/hd2d_floors_demo.py` and `tooling/hd2d_room_studio.py`, builds
    one room through **Studio's own events** in a hidden window.
  - The room contains: a walk-in doorway to a small interior (`SceneTransition` + `spawn_point`), stairs, a raised
    bridge, an underpass, scene lights with a lamp, and camera bounds.
  - Existing placeholder assets only: `stone_crossing.glb`, `cottage.glb`, `stairs.glb`, the starter kit
    (`tooling/hd2d_assets/`).
  - No renderer changes, and no disposable art.
- **Files:** `tooling/hd2d_m1b_scene.py`, `docs/reviews/m1b_hd2d_representative_scene.md` plus evidence folder,
  `tests/test_hd2d_m1b_scene_gpu.py`.
- **Acceptance (hidden window, held-key input only):**
  1. Walk in through the doorway and back out.
  2. Climb, cross, descend, and walk under the bridge.
  3. The cutaway reveals the player inside.
  4. Camera bounds hold.
  5. Save and load on the deck and under it.
  6. Screenshots and a JSON record go in the evidence. The room also passes the M1-A-2 authority load (if M1-A-2 has
     merged), so M3 reuses it.
- **Gates:** CI with replays, plus Extended **gpu lanes** (the test is `MESH_GL_SMOKE`-gated).

**M1-B-2 — Performance on identified hardware** (`HD-2D: M1-B scene frame-time report`)
- **Scope:** measure the frame time of the M1-B scene, p50/p95/p99 over a fixed walk, in a hidden window.
  - On the owner's PC, record GPU, driver, CPU, OS and resolution.
  - On hosted runners, report only (Mesa llvmpipe; see `docs/reviews/milestone16_stage6b_ci_timing.md`).
  - Also record server tick cost for 8 bodies on the World (`SceneRoom.step` p95), feeding M3.
- **Files:** a measurement option in the M1-B script, plus the review doc.
- **Acceptance:** numbers recorded with the hardware identity. No hosted gate threshold (decision D5).
- **Gates:** CI. Extended is not needed if only docs and tooling change.

## 5. M2 — Blender building + eight-direction character (investigation/prototype, parallel)

**M2-1 — One Blender building: create and safe reimport** (`assets: Blender building GLB with safe reimport
(evidence)`)
- **Scope:** add one building build script beside `tooling/hd2d_assets/build_cottage.py`, using `blender_kit.py`, with
  collision nodes. Import it through `catalog.import_model` (`catalog.py:324`), place it, then edit it in Blender and
  reimport it through `plan_reimport` (`:490`). The impact report (`:436-483`) must name the moved floor or wall.
  Record provenance in `tooling/hd2d_assets/PROVENANCE.md`.
- **Acceptance:**
  - Placed copies and collision survive the reimport, and rollback works.
  - The Blender version is recorded. Blender runs headless only.
- **Gates:** CI. Add the gpu lane if a Studio hidden-window check is added.

**M2-2 — Rigged character to an 8-direction PNG sheet** (`tooling: render a rigged Blender character to an
8-direction sprite sheet`)
- **Scope:**
  - A headless Blender script renders one rigged character with an orthographic camera at the HD-2D pitch
    (`settings.camera.pitch`, default 32).
  - It renders 8 yaw angles × (idle 1–2 + walk N frames) into one PNG with a documented row order.
  - Output is deterministic, and one character only.
- **Acceptance:** the sheet's dimensions and row order match a JSON sidecar, and a re-run is byte-stable or within a
  documented tolerance.
- **Gates:** CI (the script isn't run in CI; a fast test validates the sidecar format).

**M2-3 — Opt-in eight-direction selection + Studio import** (`animation: opt-in 8-way facing and Studio sheet setup`)
- **Scope:**
  - **Animator.** Add `directional_mode: "8-way"` (`animator.py:92`, `:188-190`). Bucket velocity into 8 sectors at
    `:228-233`. In `_resolve_directional_clip` (`:309-316`), fall back from `walk_up_right` to the nearest 4-way clip,
    then to the base clip. `set_facing` accepts the 8 names.
  - **Studio.** `project_ops.character_clips` gains a `directions` option. `DIRECTIONS` stays the 4-way default
    (`project_ops.py:1713`). The inspector form gets a 4/8 toggle (`studio_inspector.py:599`).
  - **Unchanged:** `"none"` and `"4-way"` behave exactly as today. `PlayerController`'s 4-way interaction facing is
    unchanged (`player_controller.py:186-196`). The Animator derives 8-way facing from velocity on its own.
  - **Out of scope:** network facing (wire 0..3) is M3/M4.
- **Acceptance:**
  1. Sector boundary tests.
  2. Fallback when 8-way clips are missing.
  3. A 4-way project's clips are byte-identical.
  4. A Studio hidden-window test sets up an 8-direction sheet from M2-2 and plays it.
- **Gates:** CI with replays (Animator is play-path), plus Extended gpu lanes.

**M2-4 — PixelLab texture (only where access and budget are approved)**
- **Scope:** one texture for the M2-1 building, requested only under a `tooling/pixellab_budget.py` ledger with an
  owner-approved budget. Responses are sanitised. It is shipped only if the owner approves the art and its licence.
- **Status:** optional. Skip it if access or budget isn't granted.

## 6. M3 and proposed M4–M6

**M3 — two clients in one HD-2D scene** (only after M1-A-3 merges). Reuses N6–N8. Expected PRs:
1. **Explicit local camera target.** The renderer follows an explicitly set sprite when one is set
   (`renderer.py:1256`), falling back to the tag. The client sets its own avatar. Single-player is unchanged.
2. **Wire elevation and floor.** Snapshot rows carry elevation and floor, and clients place avatars at them
   (`scene_room.py:485-494`, `:556`). This is a protocol change (decision D1).
3. **Doors and arrivals on floors.** Elevation-aware `Door.touches` (`world.py:77-81`), and lifting the base-anchored
   door refusal (`:174-175`).
4. **Same-level actions.** `_use`, `_attack` and `_take` require the same supporting floor, or `_on_level`-style
   elevation agreement, so there is no combat or looting through bridge decks (`scene_room.py:436-483`).
5. **Two-window acceptance in the gpu lane,** on the M1-B scene, styled after `tests/test_mesh_net_gpu.py:160`, `:292`.

**PROPOSED by the coordinator — not from the original report; needs owner confirmation:**

| | Proposed content | Depends on |
|---|---|---|
| M4 | Elevation-aware gameplay breadth online: enemy/NPC movement on floors server-side (`FloorRoute` / `World.path`), line-of-sight through decks, 8-direction facing on the wire | M3 |
| M5 | Online persistence of HD-2D state: character room, position, elevation and floor in the N8 store (schema migration), resume onto a standable spot | M3 (M4 optional) |
| M6 | Content production readiness: the M2 pipeline as a documented creator workflow, asset licensing/provenance gate, budgeted PixelLab use, performance budget per scene | M1-B, M2 |

## 7. Dependency order, gates, risks and owner decisions

### 7.1 Order
| Step | Starts when | Parallel with |
|---|---|---|
| M1-A-1 → M1-A-2 → M1-A-3 | now | M1-B, M2 |
| M1-B-1 → M1-B-2 | now (M1-B-1 also checks the M1-A-2 load if merged) | M1-A, M2 |
| M2-1, M2-2 → M2-3 (→ M2-4 optional) | now | M1-A, M1-B |
| M3 | **M1-A-3 merged, all gates green**; M1-B-1 merged | — |
| M4 / M5 (proposed) | M3 | each other |
| M6 (proposed) | M1-B + M2 | M3+ |

### 7.2 Gates every PR in this plan meets
- **CI**, all required:
  - `pytest` matrix
  - `verify`
  - `installed`
  - `acceptance`
  - **`replays`**: the required replay suite, `python -m mesh_cli replays run --suite replays/suite.json`, with
    **no golden updates**. Any golden change needs `replays update-golden --reason` and owner sign-off.
  - the `tests` fan-in
- **Extended:** the `extended` lane on Ubuntu and Windows, plus the **gpu** shards on both OSes. Required for any PR
  that touches the play path (`runtime.py`, `world.py`, Animator, renderer, `mesh_net` gpu tests).
- **Locally:** GPU tests run with `MESH_GL_SMOKE=1` and `-W error`, hidden windows only, audio at master 0.
- **Graphics-free:** `test_mesh_net_scene.py:78-84` and `test_mesh_net_world.py:195` stay green for every `mesh_net`
  change.

### 7.3 Risks
- **R1: lenient vs strict divergence.** Single-player falls back to 2D on a broken HD-2D block or GLB
  (`runtime.py:126-135`). The authority must refuse in exactly those cases, or the two runtimes disagree.
  Covered by M1-A-2 acceptance 2.
- **R2: terrain source.** Single-player swaps in `renderer.terrain` (`runtime.py:124-125`), while a headless World uses
  `Terrain.from_ground`. Parity on a sculpted room must be shown. *(Inferred to be the same data; not proven.)*
- **R3: tick quantisation.** The server moves `speed/20` px per tick, while single-player moves per frame with
  substeps (`world.py:402-407`). M1-A-3 compares at equal deltas. Real play will still differ by frame timing, which
  is an M3 reconciliation concern.
- **R4: server cost.** `World.move` per body per tick (8 bodies × 20 Hz, `protocol.py:13-14`) with wall scans
  (`world.py:301-303`, linear in walls). M1-B-2 measures it.
- **R5: hosted-runner performance.** llvmpipe frame times aren't representative. They stay report-only.
- **R6: assets.** The Blender version drifts (docs say 4, the investigator says 5.2.0 LTS). Rigged-character source
  licence. PixelLab cost/limits and art licence. No PixelLab art has shipped to date.

### 7.4 Owner decisions (unresolved)
- **D1. Protocol.** Wire `VERSION = 1` is checked exactly (`mesh_net/protocol.py:11`, `:30`). M3's elevation/floor
  fields (and 8-way facing later) need either v2, which refuses old clients, or a v1 extension. Recommended: v2,
  because there are no deployed clients to keep.
- **D2. What identity covers.** Collision digest only (recommended: the authority only needs collision), or full model
  bytes, which also catches visual-only drift.
- **D3. Saves.** M1-A changes no save format. Confirm that M5's N8 schema migration (position, elevation, floor) is
  acceptable when it comes.
- **D4. Water online.** Refuse rivers and wade-limited ponds in HD-2D net rooms for M1-A (recommended), or include
  wading in scope.
- **D5. Performance acceptance.** Which machine is the "identified hardware", and is there a frame-time target, or
  record-only?
- **D6. PixelLab.** Budget size, whether access is granted for M2-4, and licence terms for anything kept.
- **D7. M4–M6.** Confirm or replace the coordinator's proposal (§6). It is not from the original report.
