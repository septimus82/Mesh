# Milestone 18A: 3D particle foundation

Branch `feature/m18a-3d-particles`, a draft PR into `redesign/visual-editor`. Stage 18B (roof shelter, splashes,
collision, weather events, a Studio weather panel) has not been started.

**Verdict: see the end of this document.**

## What was built

A room can ask for environmental particles in its settings:

```json
"particles": [{"preset": "rain", "count": 3000, "wind": [1.2, 0.0]},
              {"preset": "wind", "count": 150, "gust": 0.8, "seed": 4}]
```

| Preset | Look | Defaults | Adjustable |
|---|---|---|---|
| `rain` | fine 1 px streaks, 10 and 14 px long, laid along the fall direction (slanted by the wind) | 3000, 9 m/s, wind 0.8 m/s east, opacity 0.55 | count, speed (fall), wind, gust, opacity, area, seed |
| `snow` | 2 px flakes and 3 px crosses, camera-facing, swaying | 2000, 1.1 m/s | count, speed, wind (drift), gust, opacity, area, seed |
| `wind` | green and amber leaves (5×4), a brown leaf (4×3) and debris flecks; carried horizontally, bobbing, fluttering (mirrored), fading in and out over a lifetime | 400, 3.2 m/s east, gust 0.7, lifetime 6 s | count, speed, wind, gust, lifetime, opacity, area, seed |

- Up to 4 effects per room, each with at most 20,000 particles.
- Everything is validated (`engine.scene_particles.parse_particles`). Unknown keys, presets and out-of-range numbers
  are refused with the reason.
- A room with bad settings still loads, without particles; the error is logged and kept on
  `window.scene_particles_error`.
- They are authored through the same checked edit as every other room setting: the `set_particles(scene, effects)`
  operation in `engine/project_ops.py` is exposed automatically to the AI/MCP authoring layer
  (`engine.authoring.operations()`).
- They are saved in the scene JSON and need no migration: a scene without the key is unchanged.
- No Studio weather panel and no event-driven transitions (as briefed).
- All pictures are procedural: a 32×24 atlas drawn in code at the art's 32 px per metre. No PixelLab calls and no
  new assets.

## Architecture

### Where it sits

| | HD-2D room | 2D room |
|---|---|---|
| Owner | `Hd2dRenderer.particles` (`set_particles`, created on room load and released with the renderer) | `window.scene_particles` (only when the room asks) |
| When drawn | after the sprites, before the screen overlays, in the game view | after the 2D effects (`particle_manager.draw()`), under the world camera and the room's lighting |
| Space | real world metres (x east, y north, z up) | the map: a particle at (x, y, z) is drawn at (x, y + z) |
| Depth | depth-tested against the frame's depth buffer, not writing depth, blended | none (2D has no depth) |

- The room loader (`scene_lifecycle_controller`) calls `scene_particles.configure` after the HD-2D renderer has been
  configured.
- The tick advances both clocks (`scene_particles.update`).
- `MeshGame.close()` frees a 2D room's layer; the renderer's `release()` frees an HD-2D room's.
- The existing 2D particle/effects system (`engine.particles`, `particle_manager`) is untouched.

### Simulation: stateless on the GPU (the CPU vs GPU trade-off)

The options considered were:

1. **CPU simulation.** Python steps every particle every frame and re-uploads a buffer. Simple to reason about, but at
   10,000 particles Python costs milliseconds per frame, plus a buffer upload per frame.
2. **GPU simulation with state.** Transform feedback or compute ping-pong buffers. Fast, but it needs extra GL
   machinery (GL 4.3 compute, or transform-feedback plumbing in arcade) that Mesh does not use anywhere yet.
3. **Stateless GPU particles (chosen).**
   - Each particle is a fixed seed of 6 floats: a place in a box, a phase, a picture and a speed factor.
   - The vertex shader computes where it is at time t from the seed alone, then wraps it into a box that follows the
     camera: `p = box_min + mod(w - box_min, size)`.
   - The CPU uploads the seeds once per room. Each frame it sets a few uniforms and issues one instanced draw call per
     effect.
   - There is nothing to spawn, step, recycle or free while the room runs, so there is no spawn overhead and no
     per-frame allocation.
   - The same seed and time give the same picture, which suits replays and tests.

Option 3 is the simplest that is fast. It costs nothing in new dependencies (it uses arcade's GL wrapper, as the HD-2D
renderer already does).

What it gives up is per-particle interaction (hitting a roof, splashing, being pushed by the player); 18B needs that.
The path is a depth/height-map test in the shader for shelter and splashes. Only if that proves insufficient would a
stateful (option 2) layer be added.

### Key properties

- **World-anchored, not an overlay.**
  - The wrap box only decides which copy of the endless repeating pattern is drawn. A particle keeps its world
    position as the camera moves.
  - The box reaches further south by `height / tan(pitch)`, so high particles still fill the bottom of the picture.
  - Particles fade over the last 1.5 m at the box's sides, so wrapping never pops in view.
  - Rain and snow fade in over the top 1.5 m, where a fallen particle comes back, and vanish at the ground (it reads
    as landing).
  - Leaves stay in a band 0.35 m clear of the floor and the top, and bob within it, so they never wrap vertically.
    Rendering QA found both of these pops; they were fixed and re-checked (see the QA section).
- **Orientation.** Rain streaks lie along their fall vector. Snow and leaves face the camera (its right axis, and the
  up axis the billboards use). Leaves flutter by mirroring.
- **Wind and gusts.** The drift uses the integral of a swelling wind, so the speed stays bounded and there is no
  sawtooth. Leaves get a lifetime: each cycle they turn up at a new hashed place, fade in, drift and fade out.
- **Pixel art.** NEAREST sampling, binary alpha (`discard` below 0.5) and the art's 32 px per metre. The effect's
  opacity is the only translucency.
- **Lighting.** Tinted by the scene's ambient light plus the sun's intensity and colour, so they don't glow at dusk.
  They don't cast shadows, and they don't affect the lighting or shadow passes.
- **GPU objects.** Per layer: one program, one texture (the atlas), one quad buffer, and one seed buffer and
  vertex array per effect. All are freed by `release()`, which runs on every room change, renderer release and window
  close.

## Depth and camera proof: the starter village

The HD-2D RPG template's village is captured in hidden windows by `tooling/m18_particles_study.py proof OUT`. For each
preset and place it renders the frame:

- with particles;
- with them switched off;
- with depth testing disabled (diagnostics only).

From these it derives an occlusion map: cyan for particle pixels drawn, magenta for those hidden by depth, meaning the
particle stands behind something.

| Place | What it shows | Evidence |
|---|---|---|
| In front of a building | rain falling in front of the cottage, over its wall and door | [compare_rain_cottage_front.png](milestone18_stage1_3d_particles_evidence/compare_rain_cottage_front.png) |
| Behind a building | snow behind the cottage hidden by its roof and walls (magenta) | [compare_snow_behind_cottage.png](milestone18_stage1_3d_particles_evidence/compare_snow_behind_cottage.png) |
| Near the player | snowflakes in front of and behind the player | [compare_snow_by_the_player.png](milestone18_stage1_3d_particles_evidence/compare_snow_by_the_player.png) |
| Different elevations | leaves on the hills and the upper terrace, hidden by the terrace wall | [compare_wind_hills.png](milestone18_stage1_3d_particles_evidence/compare_wind_hills.png) |
| In front of the bridge | rain in front of the bridge | [compare_rain_bridge_front.png](milestone18_stage1_3d_particles_evidence/compare_rain_bridge_front.png) |
| Behind and under the bridge | leaves behind and under the bridge, hidden by its deck and posts | [compare_wind_bridge_behind.png](milestone18_stage1_3d_particles_evidence/compare_wind_bridge_behind.png) |
| Following the camera | walks of 18 frames as the player moves | [rain_walk.webp](milestone18_stage1_3d_particles_evidence/rain_walk.webp), [snow_walk.webp](milestone18_stage1_3d_particles_evidence/snow_walk.webp), [wind_walk.webp](milestone18_stage1_3d_particles_evidence/wind_walk.webp) |
| Pixel-art consistency | 4× nearest close-ups beside the cottage door and the player | [rain_close_4x.png](milestone18_stage1_3d_particles_evidence/rain_close_4x.png), [snow_close_4x.png](milestone18_stage1_3d_particles_evidence/snow_close_4x.png), [wind_close_4x.png](milestone18_stage1_3d_particles_evidence/wind_close_4x.png) |
| A 2D room (opt-in) | the blank 2D template without, and with, snow and leaves | [2d_room_snow.png](milestone18_stage1_3d_particles_evidence/2d_room_snow.png) |

The walks are re-encoded lossy, at every other frame, to keep the repository small. The close-ups are lossless.

Measured in [proof.json](milestone18_stage1_3d_particles_evidence/proof.json): every place, for every preset, has
particle pixels both drawn and hidden by depth.

| Preset | Drawn px | Hidden by depth px |
|---|---|---|
| rain | 28,928–33,474 | 633–2,076 |
| snow | 8,682–10,017 | 284–616 |
| wind | 4,255–5,344 | 364–1,163 |

So the particles are genuinely behind the scenery where they should be, not a flat layer.

World anchoring was measured by moving the camera 10 px (5 world pixels at the outdoor scale):

| Preset | Pixels that moved with the world | Pixels that stayed put on screen |
|---|---|---|
| rain | 0.846 | 0.104 |
| snow | 0.955 | 0.033 |
| wind | 1.000 | 0.132 |

- Rain is the lowest because its thin streaks at different depths move by slightly different amounts (perspective
  parallax), so exact pixel overlap is stricter for them.
- The GPU test checks the same thing with 3 px of slack and asserts more than 0.8 against less than 0.3.

## Performance

Measured by `tooling/m18_particles_study.py perf OUT` ([perf.json](milestone18_stage1_3d_particles_evidence/perf.json))
on an NVIDIA GeForce RTX 4070 (GL 4.6) in the village, 1280×720, with shadows on.

Method:
- one game;
- for each case, the renderer's particles are set, then 5 interleaved rounds of 60 frames drawn with the particles
  on, then off;
- the table gives medians;
- the GPU times use GL time queries, timing the whole frame and the particle pass in separate loops.

| Case | Particle pass, GPU | Frame on / off (CPU wall) | Added frame | Draw calls | GPU memory | Layer creation |
|---|---|---|---|---|---|---|
| rain 100 | 0.004 ms | 7.60 / 7.60 ms | 0.00 ms | 32 (+1) | 5.4 KB | 3.0 ms |
| rain 1,000 | 0.010 ms | 5.15 / 5.03 ms | 0.12 ms | 32 | 27 KB | 3.2 ms |
| rain 5,000 | 0.035 ms | 5.04 / 4.99 ms | 0.05 ms | 32 | 123 KB | 8.4 ms |
| rain 10,000 | 0.062 ms | 5.04 / 4.87 ms | 0.17 ms | 32 | 243 KB | 15.6 ms |
| rain 20,000 (maximum) | 0.105 ms | 5.02 / 4.81 ms | 0.21 ms | 32 | 483 KB | 29.2 ms |
| snow 10,000 | 0.039 ms | 4.91 / 4.85 ms | 0.06 ms | 32 | 243 KB | 15.7 ms |
| wind 10,000 | 0.056 ms | 4.94 / 4.81 ms | 0.13 ms | 32 | 243 KB | 15.7 ms |
| all three (6k + 2k + 2k) | 0.054 ms | 5.01 / 4.90 ms | 0.11 ms | 34 (one per effect) | 243 KB | 15.8 ms |

- The frame time is the CPU wall clock per frame; the GPU column is the particle pass alone.
- The frame-time difference is at the noise level (±0.2 ms) for every case.
- "Draw calls" is the renderer's whole frame; the particles add one per effect, whatever the count.

Other measurements:

- **Walking (the camera following the player) with 5,000 raindrops:** 7.335 ms with them on, against 7.225 ms with
  them off. That is within the frame-to-frame noise, which is about 0.2 ms.
- **Lighting and shadows:** particles are not drawn into the shadow pass, so the shadow draws are unchanged with
  particles on. With shadows off, the frame with 5,000 raindrops is 3.65 ms; the particle cost is the same either
  way.
- **Spawn overhead:** zero while running. The one-off cost is building the seed buffer on room load, about 1.5 ms
  per 1,000 particles (pure Python `random`), so 15 ms for 10,000. That fits inside a room transition's fade.
- **No per-particle draw calls and no unbounded allocations:**
  - per effect, one static buffer of 24 bytes per particle;
  - counts are capped at 20,000 per effect and 4 effects per room;
  - nothing is allocated per frame.

### GPU lifecycle

The perf run's `gl_lifecycle` block counts GL objects after a GL garbage collection (`ctx.gc()`):

| State | Buffers | Textures | Framebuffers | Programs |
|---|---|---|---|---|
| no particles | n | 50 | 6 | 27 |
| one layer (rain 5,000) | n + 2 | 51 | 6 | 28 |
| after 200 enable/disable toggles | n + 2 | 51 | 6 | 28 |
| released | n | 50 | 6 | 27 |
| after 20 layers (all three effects) made and released | n | 50 | 6 | 27 |

- The large buffer count in that run (n ≈ 52,000) is not the particles'. It is an existing engine leak: a door's
  per-update collision `SpriteList` (see Limitations). It grows with `on_update` calls, with or without particles.
  220 frames drawn without updates held steady at 421 buffers.
- Room changes (20 round trips between the village and the cottage interior) leave the same GL counts with and
  without particles. The Python heap grew by 6.4 MB with particles against 10.4 MB without, so the growth is the
  engine's own caching, not the particles'.
- `tests/test_scene_particles_gpu.py` asserts the room-change stability and that `set_particles(())` frees every
  object.

### Targets (from the measured hardware)

- A particle pass under 0.15 ms of GPU time at the per-effect maximum of 20,000 particles on this GPU.
- One draw call per effect.
- Zero GL objects left behind after a release.
- Seeds built in under 50 ms on room load at 20,000.

The design has a very large margin on this GPU. On integrated GPUs, expect the fill rate (overdraw of the streaks) to
dominate first; the defaults (3,000 rain, 2,000 snow, 400 leaves) are a fraction of the cap.

## Tests and gates

- **`tests/test_scene_particles.py`** (fast, 19 tests):
  - presets and defaults;
  - every refused setting, with its reason;
  - deterministic seeds;
  - the box geometry;
  - the atlas is pixel art (binary alpha);
  - room-load behaviour: HD-2D vs 2D vs broken settings;
  - the authoring operation.
- **`tests/test_scene_particles_gpu.py`** (integration, `MESH_GL_SMOKE=1`, hidden windows, 4 tests):
  - rain is drawn in one draw call and depth-tested (more than 500 px hidden by scenery), with the same picture for
    the same time;
  - world anchoring as the camera moves;
  - room changes free every GL object;
  - a 2D room draws particles only when it asks, and nothing else in its frame changes.

### Independent QA

Three Opus reviewers each validated the real Mesh output in their own hidden-window renders and measurements,
without access to my conclusions beyond the claims to check.

**Rendering QA.**
- **First pass: CONDITIONAL PASS.** It found two pops at the wrap boundary:
  1. Windborne leaves jumped about 230 px between the floor and the top of their 4 m box, because the bob was
     applied before the wrap.
  2. Rain and snow appeared at full opacity mid-screen, where a fallen particle comes back at the top.

  Both were fixed in the shader.
- **The re-check was done on the GPU, comparing old and new.**
  - The tracked leaves went from 4 jumps of 230 px each to none; the largest move is 3.4 px per frame.
  - Snow appearances went from 5.5 to 1.3 per second, and rain from 31.6 to 9.5.
  - The remaining appearances are particles coming out from behind roof and stair edges, which is correct depth
    behaviour.
  - No leaves end up below the ground, and the fade leaves no visible band.
- **Verified:**
  - no halos around sprites (0 hidden px outside a 1 px-dilated silhouette) and no z-fighting;
  - rain leans 6° from vertical outdoors and 8° indoors, with no slivers;
  - one texel is about 2 screen px at scale 2;
  - no pop when a room loads;
  - nothing glows in a dark room.
- **Updated verdict: PASS.** Its minor findings are listed under Limitations.

**Performance QA: PASS.**
- **Independently measured:**
  - draw calls are 31 with no particles, 32 with one effect at any count, and 35 with four;
  - exactly 24 B per particle plus 3,104 B per layer;
  - 4 × 20,000 particles cost 0.091 ms of GPU time.
- **Lifecycle:**
  - 1,000 toggles leave nothing behind;
  - 100 `set_particles` swaps end with exactly one live layer;
  - 40 room round trips stay level;
  - closing releases everything once.
- **Fixed from its nits:**
  - per-effect uniforms are computed once;
  - with every effect switched off, the layer changes no GL state;
  - `release()` is safe to call twice.
- **Left for later:** numpy seeds (see Limitations).
- **Also traced:** the existing door `SpriteList` leak.

**Compatibility QA: CONDITIONAL PASS, with its conditions now fixed.**
- **2D rooms:** frames are pixel-identical before and after this branch, with no layer and the same GL counts. The
  blank, adventure, starter, monster and hd2d_rpg templates were checked against a `git archive` export of
  `da87d9c`.
- **Scenes, saves and authoring:**
  - old scenes load;
  - the scene schema already accepts any settings key;
  - every save path keeps `particles`;
  - game save slots restore them;
  - bad settings in 2D and HD-2D rooms load the room without particles;
  - the operation appears in `authoring.operations()` and in the MCP listing.
- **Fixed from its findings:**
  - a GL failure while building the particles (for example a driver that can't compile the shader) no longer stops
    the room from loading;
  - the `set_particles` docstring now lists every setting and its range for the AI;
  - removing particles from a room without settings no longer adds an empty `settings` object;
  - unreadable `settings` are refused.
- **Deferred to 18B or Studio work, under Limitations:** the AI review card summary, and showing the error in
  Studio.

### Gates

Local results on Windows, with the final code:

| Gate | Result |
|---|---|
| Fast tier (`pytest -m fast`) | 4632 passed, 6 skipped |
| Particle + HD-2D GPU tests (`MESH_GL_SMOKE=1`, hidden windows): particles, hd2d runtime, starter, Studio | 48 passed |
| All HD-2D GPU test files, before the QA fixes | 81 passed |
| ruff gate | ok |
| Wheel bundle test (without `PYTHONPATH`, `-o addopts=`) | passed |

- **mypy gate:** no new errors from this branch.
  - It reports two errors in `tooling/hd2d_lab/gltf.py` and `lab.py`, which this branch doesn't touch.
  - The same two errors appear on a `git archive` export of the base `da87d9c`, so they come from the local numpy
    (2.4.4) and are not caused by this branch.
- **Linux and Windows CI:** see the PR.

## Limitations (what 18A does not do)

- **No shelter, splashes or collision.** Rain falls through roofs and the bridge deck. It is correctly hidden by
  them from the camera's point of view, but a particle under a roof is still drawn where the camera can see it, for
  example under the bridge. That is 18B.
- **Not drawn in Studio's edit view.** The particles are drawn in the game view only. Studio's HD-2D view passes a
  camera (`studio_hd2d.py`), and its 2D view doesn't draw them either.
- **Bad hand-edited settings are reported only in the log.** The room loads without particles and keeps the reason
  on `window.scene_particles_error`, but Studio doesn't show it yet. The authoring operation refuses bad settings
  up front, so only hand-edited JSON can get there.
- **The AI review card doesn't summarize setting changes.** A particles proposal shows "(no visible change)",
  because `authoring.summarize` ignores settings; `set_room_lighting` has the same gap today.
- **Not clipped to the room.**
  - In a 2D room the particles cover the whole view, including the backdrop beyond the map's edge.
  - In an HD-2D interior such as the cottage, rain or snow fills the dark void around the room and looks like
    stars.
  - Nothing stops an author from putting rain indoors; the presets don't know about ceilings.
- **Very wide screens.** The box is a fixed 30 m across. At 32:9 the outer strips are thinner (about a third of the
  density). 16:9 and 21:9 are fine.
- **Lighting is ambient and sun only.** Particles pick up no shadows and no lamp light, so snow under the bridge is
  as bright as snow in the sun. In a dark room they stay dark; nothing glows.
- **Texel size varies a little with height.** A particle high in the box is up to about 1.5× closer to the camera,
  so a 2 px flake can cover 4×4 to 8×8 screen px at scale 2. Shimmer while panning is low (under 1.5% change).
- **Clock precision.** The time is a float32. After about 4–8 hours idle in one room the positions step by a texel.
  The clock restarts on every room load, and on loading a save.
- **Making a layer at the maximum size is slow.** Seeds are built in pure Python: about 27 ms per 20,000 particles,
  so the extreme room (4 × 20,000) costs about 120 ms on load. numpy would make it under 1 ms, but would change the
  seed patterns. Left as is: the defaults cost 3–5 ms.
- **The same pattern repeats** every `area` metres. At the default 30 × 34 m this isn't noticeable, but a smaller
  area could show it.
- **Timing measured on one GPU** (an RTX 4070). There are no integrated-GPU numbers.

**Found in passing (not from 18A, an existing engine bug):** Performance QA traced a steady GL buffer climb during
the perf runs to `engine/behaviours/scene_transition.py`. A door's update makes a new `arcade.SpriteList` every frame
and appends the player to it, and the player keeps a reference to each list. That adds 5 buffers per update while a
door is in the room; they are freed on room change. It is tracked separately and not fixed on this branch.

## Recommendations for 18B

1. **Shelter.** A top-down height map of roofs and decks, rendered once per room. The vertex shader drops a
   particle that is under cover, and the same map gives splash heights.
2. **Splashes.** A small second effect, keyed to the rain's seed and fall time, at the height map's surface.
3. **Studio.** Draw the layer in the editor camera, behind a toggle. Then add a weather panel built on the
   `set_particles` operation.
4. **Event-driven weather.** Fade the opacity and count in and out (a uniform), driven by events.

## Verdict

**PASS** for Stage 18A, pending the owner's review.

Measured against the acceptance gate ("thousands of reusable, animated particles in genuine 3D space, correctly
depth-tested against buildings, characters and elevated structures, while preserving the traditional 2D
renderer"):

- **Thousands, efficiently.**
  - 10,000 particles cost about 0.06 ms of GPU time per frame on the test GPU; the 20,000 maximum costs 0.105 ms.
  - One draw call per effect.
  - Nothing is allocated per frame, and every GL object is freed on release, room change and close.
- **Reusable and animated.** Three presets (rain, snow, windborne), each tunable through validated room settings and
  authored through a checked operation that the AI layer already exposes.
- **Genuine 3D, depth-tested.** Every place tested in the village shows particles both drawn and hidden by depth:
  in front of and behind the cottage, around the player, on the terraces, and in front of and behind the bridge.
  They stay anchored to the world as the camera moves, and there are no halos or z-fighting.
- **2D preserved.** Rooms without `settings.particles` render pixel-identically to the base branch, and the
  existing 2D effects system is untouched.

What keeps this from being more than a foundation is listed under Limitations: no shelter, splashes or collision
(18B), not visible in Studio's edit view, and no clipping to the room. None of these affects the 18A gate. Stage
18B has not been started and awaits the owner's review.
