# Milestone 16, Stage 2: In-Engine HD-2D Rendering

**Verdict: PASS.** Stage 1's renderer now runs inside Mesh, in the real game window, scene loader and update loop:

- A scene opts in with `settings.hd2d`. It then draws depth-tested GLB structures, with the scene's own entities as
  camera-facing billboards.
- The ordinary player controller moves the ordinary animated player. The camera follows in 3D, and the building hides
  the player when they are behind it.
- Saves, input, behaviours, dialogue prompts and the HUD are the same systems as in 2D.
- 2D scenes never load the 3D code.
- Everything here was verified in a hidden window: no visible window, no mouse or keyboard, no focus taken.

Branch `feature/m16-stage2-runtime` (from `redesign/visual-editor` after #349 and #348), with a draft PR to
`redesign/visual-editor`. Not merged; that needs the owner's approval.

## Phase 0: CI and the Stage 1 integration

| Step | Result |
|---|---|
| Arcade 3 canary | It still listed two test files that M13 deleted (`test_hard_shadows_composite_*_fallback.py`). They were replaced by `tests/test_shadow_shapes.py`, which covers the live per-light shadow path. A new contract test fails if the canary ever lists a file that doesn't exist. Runtime replay and installed-wheel replay are unchanged. **PR #349: canary green on GitHub** (both runs), merged as `6c30f09`. |
| Full `tests` job | Still red with **the same 26 failures as #347 before it**: missing golden-slice packs, packaging hygiene, Linux paths. They are pre-existing and cross-platform, nothing new. The one count change is +1 passed, the new contract test. |
| Stage 1 (#348) | Merged as `1a4b8a5`. The tree hash of `tooling/hd2d_lab`, the Stage 1 report, its evidence and its two tests is identical before and after the merge (`c5399858…`). |
| #344 | Still a draft. Nothing went to `main`. |

## Architecture

There is one window, one GL context and one loop; HD-2D only replaces how a scene's world is drawn.

```
scene load ─ scene_lifecycle_controller.load_scene
             └ configure_scene_lighting(...)          (unchanged)
             └ engine.hd2d.runtime.configure_scene    release the old room's renderer; if settings.hd2d:
                                                       parse + validate, read the GLBs, build Hd2dRenderer
on_update ── tick.on_update: scene_controller.update (player controller, behaviours, animation, collision)
             └ window.hd2d_renderer.update(dt)        3D camera follows the "player" tag (smoothed)
on_draw ──── tick.on_draw: post-processing begin, clear
             └ HD-2D room:  hd2d_renderer.draw()      INSTEAD of the 2D world block (lighting + scene + particles)
             └ 2D room:     the 2D world block        (unchanged code path)
             └ fog, render queue, post-processing end, GUI/HUD/UI (unchanged, drawn over both)
close ────── GameWindow.close → engine.hd2d.runtime.release (while the GL context still exists)
```

- **`Hd2dRenderer`** (`engine/hd2d/renderer.py`):
  - It draws into its own off-screen framebuffer, with a colour target and a 24-bit depth texture, then draws that
    into whatever framebuffer was active: the screen, or the post-processing target. That keeps it correct with
    post-processing and leaves arcade's 2D state alone.
  - The target follows the window size (resize).
  - Structures are drawn through a mesh shader with a sun and ambient term.
  - Sprites are alpha-tested billboards (binary alpha: discard plus depth, so nothing needs sorting), with soft ground
    shadows.
  - Coordinates: Mesh px / 32 = metres; x east, y north (map y), z height.
- **Billboards come from the scene's own sprites.**
  - Each sprite's current `texture`, so the Animator's frames show as they change.
  - Placed at its feet (`bottom`): upright, facing the camera, stretched by 1/cos(pitch) so its proportions match the
    2D art.
  - Mirrored when `scale_x < 0`.
  - `elevation` (px) lifts a sprite; `depth_z` is not read, and stays 2D draw order.
- **Moving sprites use one persistent vertex and index buffer**, rewritten each frame and grown (doubled) only when a
  frame needs more. A frame allocates no GPU objects.
  - This matters: arcade frees GL objects only in `flip()`, so per-frame geometry would have leaked in hidden-window
    runs. That was found while building this.
- **Camera** (`Camera`):
  - fixed pitch, looking north;
  - perspective with Stage 1's settings (FOV 30°, pitch 32°, distance 15 m), or `ortho: true` for a parallel
    projection;
  - target = the followed entity's feet + 0.8 m, smoothed frame-rate-independently in `update`;
  - the 2D `window.camera` is untouched.
- **Static batching**:
  - At load, every structure instance is transformed once on the CPU (placement, rotation, scale; normals rotated and
    renormalised).
  - Instances are merged into one vertex and index buffer per texture.
  - Built once, never rebuilt per frame.
  - `batched=False` keeps one shared buffer per model part, drawn once per instance with a model matrix (the
    comparison path).
- **Errors never take the game down.**
  - A scene whose `settings.hd2d` or `.glb` is broken still loads and is drawn 2D.
  - The reason is logged (`[Mesh][HD-2D] this scene is drawn 2D: <file>: <problem>`) and kept on `window.hd2d_error`.
  - Models are read and validated before any GL object is made.

### Scene format

`settings` already allows extra keys, so the scene schema didn't change. The entity schema gains one optional
field.

```json
"settings": {"hd2d": {
  "structures": [{"model": "assets/models/stone_outpost.glb", "x": 384, "y": 256,
                  "elevation": 0, "rotation": 0, "scale": 1.0}],
  "ground": {"texture": "assets/textures/grass.png", "from": [0, 0], "to": [768, 512]},
  "camera": {"pitch": 32, "fov": 30, "distance": 15, "ortho": false, "follow": "player", "height": 0.8},
  "sun": [-0.45, -0.55, 0.7], "ambient": 0.55
}}
entity: {"prefab_id": "person", "x": 426, "y": 272, "elevation": 32}
```

- Paths are project-relative and resolved through Mesh's content roots (`engine.paths.resolve_path`).
- Unknown keys, wrong types and out-of-range numbers are refused with the key named, e.g.
  `settings.hd2d.structures[0].model must be a project-relative .glb path (got 'outpost.obj')`.
- **`elevation`** is HD-2D only.
  - It is in the entity schema, in the scene loader's known fields (no "unknown field" warning) and in the save system's
    authored fields.
  - 2D scenes ignore it.
  - `depth_z` keeps its single meaning: draw order.

## Files

| File | What |
|---|---|
| `engine/hd2d/__init__.py` | The package (opt-in per scene) |
| `engine/hd2d/glb.py` | The GLB reader: pure Python, validates and errors (below) |
| `engine/hd2d/settings.py` | `parse_hd2d`: validated `settings.hd2d`, with `Hd2dSettingsError` naming the key |
| `engine/hd2d/renderer.py` | `Hd2dRenderer`: target, shaders, static batching, billboards, camera, stats, release |
| `engine/hd2d/runtime.py` | `configure_scene` (scene load) and `release` (scene change, close) |
| `engine/game_runtime/tick.py` | +9 lines: the HD-2D renderer draws the world instead of the 2D block; camera update after the scene update |
| `engine/scene_lifecycle_controller.py` | +2: `configure_hd2d_scene` right after `configure_scene_lighting` |
| `engine/game.py` | +4: release on window close |
| `engine/scene_loader.py`, `engine/scene_runtime/persistence.py`, `engine/schemas/entity.schema.json` | `elevation` known, saved and documented |
| `tooling/hd2d_demo.py` | The developer scene: `build`, `check`, `bench` |
| `tests/test_hd2d_glb.py` (fast, 14) | Reader, Z-up, refusals |
| `tests/test_hd2d_settings.py` (fast, 14) | Settings validation; `elevation` known and saved; 2D rooms get no renderer and don't import the 3D code |
| `tests/test_hd2d_runtime_gpu.py` (GPU, 5) | Walk, animation, camera, occlusion, save/load, resize, release, batching |
| `tooling/hd2d_lab/lab.py`, `textures.py` | **Typing only** (5 lines). Stage 1 had 6 type-gate findings I missed when it merged; fixed here so the type gate is back to 0. No behaviour change: the Stage 1 GPU tests still pass. |

## Demo: the developer-only scene

```
py -3.13 tooling/hd2d_demo.py build  "<new folder>"            # an ordinary blank-template project, turned HD-2D
py -3.13 main.py                                                 # from that folder: play it (arrow keys / WASD, E)
py -3.13 tooling/hd2d_demo.py check  "<that folder>" <out dir>   # hidden window: walk it with key events
py -3.13 tooling/hd2d_demo.py bench  "<that folder>" <out dir>   # hidden window: the village benchmark
```

- `build` uses the **blank template's own project**: its player prefab, its 4-direction `starter_hero` Animator clips
  and its controls. The start room becomes the HD-2D outpost:
  - Stage 1's `stone_outpost.glb` at the map centre, on grass (Stage 1's pixel texture, tiled);
  - the template's **person** prefab ("Keeper") on the raised platform with `elevation: 32` (1 m), in front of the hut;
  - wall tiles painted under the platform and steps, so the ordinary 2D collision walks the player around the building.
- It also adds `village.json`: the outpost repeated as 20 separate buildings at four rotations, for the benchmark.
- It is not a launcher template.
- Run `check` and `bench` with `MESH_USER_DIR` / `MESH_PROJECTS_DIR` set, to keep the run out of the owner's
  recent-projects list.
- The playable demo (`main.py`) shows a real window. It is for the owner to run; I didn't.

## Rendering evidence (`docs/reviews/milestone16_stage2_evidence/`)

These are all from the real `GameWindow` in a hidden window. The player was moved by `on_key_press` / `on_key_release`
events through the ordinary `PlayerController`.

| Picture | Shows |
|---|---|
| `01_start.png` | The player in front of the steps, the Keeper on the platform, the game's HUD hint bar over the 3D view |
| `02_beside.png` | East of the platform, facing up. The game's own **"E: Interact: Keeper"** prompt: dialogue proximity works unchanged |
| `03_behind.png` | North of the building: **the player is entirely hidden by the hut and roof** (0 of 1,947 px visible) |
| `04_against.png` | Pressed against the platform's north wall (collision stopped them at y 344): still hidden (0 of 2,697) |
| `05_resized.png` | After resizing to 1280×720: the target follows, no stretching |
| `06a_after_load.png` | After a save, a move, and loading the save: same position, Keeper still on the platform |
| `06_plain_2d.png` | The same room without `hd2d`, after leaving the HD-2D room: ordinary 2D rendering |
| `07_ortho.png` | The orthographic camera option |
| `village_batched.png` | 20 separate buildings, batched |

### Animation and input (`check.json`)

The walk is held arrow keys, recorded after each leg:

| After | Player (px) | Clip | Visible / total px |
|---|---|---|---|
| start | 384, 120 | idle_down | 2672 / 2672 |
| RIGHT ×40 frames | 484, 120 | idle_right | 1947 / 1947 |
| UP ×50 (east of the platform) | 484, 245 | idle_up | 2592 / 2592 |
| UP ×46, LEFT ×40 (north: behind it) | 384, 360 | idle_left | **0 / 1947** |
| DOWN ×20 (against its north wall) | 384, 344 | idle_down | **0 / 2697** |
| round the west side, back in front | 234, 44 | idle_right | 1936 / 1936 |

- While walking right, the player's texture went through **4 distinct walk frames**.
- All four directional idles appeared, so the Animator's 4-way clips drive the billboard.
- The camera target stayed within 1 m of the player on every leg.
- The Keeper (`elevation` 32 px) is fully visible on the platform (≈2,260 px).
- "Visible" counts the sprite's pixels that pass the depth test against the world. "Total" counts them with the
  structures removed.

## GLB loading and errors

- **The NumPy decision: removed from the engine.**
  - `engine/hd2d/glb.py` is pure Python (`struct`, `array`, PIL, which Mesh already declares).
  - On `stone_outpost.glb` it gives output identical to Stage 1's NumPy reader (max difference 0.0, 11 parts).
  - NumPy is not imported anywhere under `engine/` and is not added as a dependency.
  - The Stage 1 lab still uses NumPy, as isolated tooling, and its tests `importorskip` it.
  - Cost: reading is slower in pure Python. Load time is in the benchmark.
- **Supported:**
  - node TRS or matrix transforms, with children;
  - triangle primitives with POSITION, NORMAL, TEXCOORD_0, and u8/u16/u32 indices;
  - normalized accessors and byte strides;
  - base-colour textures embedded in the GLB;
  - samplers: NEAREST/LINEAR, REPEAT/CLAMP;
  - repeated instances, which share one parsed model per file.
- **Refused**, with `GlbError` naming the file and the problem:
  - not a GLB;
  - glTF version ≠ 2;
  - no JSON chunk;
  - skins; animations; morph targets;
  - external `.bin` or image files;
  - non-triangle modes;
  - missing POSITION;
  - indices past the vertex count;
  - accessors running past the binary chunk;
  - undecodable images;
  - no meshes.

  Each of these has a test. One example message: `…/bad.glb: node 'tri' primitive 0 has morph targets (shape keys);
  apply them before exporting`.

## Performance: the village, 20 separate buildings, 1280×720, RTX 4070

| | Batched | Unbatched |
|---|---|---|
| Draw calls per frame | **6** (ground, 3 materials, shadows, sprites) | 223 |
| CPU per frame (submit; median / p95) | **0.80 / 0.97 ms** | 11.95 / 13.51 ms |
| GPU per frame (timer query, median) | 0.022 ms | 0.182 ms |
| Triangles | 1,320 | 1,320 |
| Static vertex + index buffers | 107 KiB | 12 KiB (shared per part) |
| Textures | 22 KiB | 22 KiB |
| Render target (colour + depth) | 7.0 MiB | 7.0 MiB |
| Build at load | 172 ms (Python peak 240 KiB) | 24 ms |

- The camera was pulled out to 40 m so all 20 buildings were in view, the worst case; 300 frames each.
- **Batched and unbatched pictures are pixel-identical** (0 differing pixels), so placement, rotation, materials and
  visibility are preserved.
- Batching is a clear win: 37× fewer draw calls, ~15× less CPU per frame.
  - The unbatched cost is Python plus the driver per draw; the GPU barely notices either.
  - In exchange it holds 9× more vertex data (each instance's own copy) and costs 172 ms at load. That is the
    pure-Python transform, paid once.
- The outpost room itself:
  - 7 draw calls;
  - 66 triangles;
  - 12 KiB of buffers, 28 KiB of textures (structures plus the animation frames seen so far);
  - the 1280×720 target.
- "CPU" is the time to submit the renderer's frame. "GPU" is a `GL_TIME_ELAPSED` query around it. Both were measured
  with the rest of the game frame (HUD, UI) excluded, so they isolate what HD-2D adds.

## Memory and lifecycle

- **GL objects** (`ctx.stats`, created minus freed, after `ctx.gc()`), measured in this order:
  1. the 2D room;
  2. the HD-2D room;
  3. back to the 2D room;
  4. 2D to 2D again.
- **Textures, framebuffers and programs return exactly to the 2D baseline** (5 / 3 / 18) when the HD-2D room is left,
  and `window.hd2d_renderer` is `None`.
- Buffers rose by 10 on leaving the HD-2D room. A plain 2D→2D reload also adds exactly 10, so that comes from the 2D
  room load itself, not from HD-2D. HD-2D leaves none behind. This has a test.
- Window close releases the renderer before arcade tears the context down.
- Save/load rebuilds the room through the normal path, with a fresh renderer and nothing carried over.

## 2D regression results

| Check | Result |
|---|---|
| Fast tier (`python -m tooling.test_tiers tier0`) | **4,380 passed, 0 failed** (8 skipped; `-W error`) |
| Targeted (save, persistence, scene loader, lifecycle, tick, MCP; `-o addopts=`) | **816 passed, 0 failed** (3 skipped) |
| GPU tier (`MESH_GL_SMOKE=1`, every GL-gated test file) | **67 passed, 1 skipped, 1 failed**. The failure is `test_background_layers_render_contract::test_scene_controller_draw_composites_background_layer`, which **fails identically on `redesign/visual-editor` without these changes**: its hand-built controller lacks `_foreground_layers`. It predates this work and is left alone. Now also +5 HD-2D GPU tests, all passing. |
| Type gate / ruff gate / `type: ignore` | ok / ok / 0 |
| `tooling/visual_polish_check.py` (hidden Studio and game render) | **10/10** |
| Studio | It opens the HD-2D room (hidden-window `scene_snapshot --studio`) in its normal 2D edit view, without errors. Play mode goes through `tick`, so it plays in HD-2D. |
| 2D isolation | The HD-2D modules (`renderer`, `glb`) are not imported by 2D games (a test checks this); 2D rooms take the untouched code path. |

## Limitations (Stage 2 scope)

- **Studio has no 3D view.**
  - It edits an HD-2D room as 2D. Structures aren't shown, and the collision under them is ordinary wall tiles,
    painted by `build`.
  - The room plays in HD-2D.
- In an HD-2D room the world is drawn only by the HD-2D renderer. These are not drawn there:
  - the tilemap (the ground is a textured quad);
  - 2D lighting, particles and parallax layers;
  - editor world overlays.

  Fog still draws, in 2D screen space, so leave it off in HD-2D rooms. The HUD, UI and post-processing work.
- **No height physics** (as briefed).
  - `elevation` is visual: the Keeper stands on the platform but is placed, and interacted with, by 2D position.
  - The steps are not climbable; the player walks around the building.
- The camera doesn't clamp to the map: near the map's edge the sky colour shows past the ground.
- Static batching is built in pure Python: 172 ms for 20 buildings. A much larger village would want a faster build,
  e.g. caching the transformed buffers, but that needs no NumPy.
- Sprites are lit by a fixed ambient-plus-sun factor and cast only a soft round ground shadow, not a directional
  shadow onto the geometry.
- GPU timings come from one machine (RTX 4070). The scene is small enough that GPU cost is negligible either way.

## What I did not do

- Nothing past Stage 2.
- No merge of Stage 2, and nothing into `main`.
- No visible windows, no OS input, no focus taken, and `runtime_gate --owner-present` was not run.
