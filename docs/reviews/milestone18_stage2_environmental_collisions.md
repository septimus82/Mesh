# Milestone 18B: precipitation, shelter and surface impacts

- **Branch:** `feature/m18b-weather`.
- **Draft PR:** [#380](https://github.com/septimus82/Mesh/pull/380), into `redesign/visual-editor`.
- **Builds on:** Stage 18A (#377); the plan is `docs/design/milestone18b_environmental_collisions_plan.md` (#379).
- **Not in this stage:** ponds, rivers, dynamic puddles, thunderstorms and the full weather UI.

**Verdict: PASS** (details at the end).

## What changed for a creator

- **Rain and snow stop at roofs, bridge decks, terraces, stairs and the ground.** A raindrop that lands shows a small
  pixel-art splash where it hit; a snowflake settles and fades.
- **Under a roof or the bridge's deck it stays dry,** whatever the camera sees, and that holds when the wind slants
  the rain.
- **Rooms:**
  - Weather is kept inside the room's own rectangle (its map), fading out over the last 0.75 m.
  - A room can be marked indoors (`settings.weather_exposure: "indoor"`), and then shows no rain or snow. Other
    particles it asks for, such as windborne leaves, still show. The starter cottage interior is indoors.
- **Mesh Studio:**
  - The 3D view has a **Preview weather** toggle (on by default when the room has weather). Rain, snow and leaves
    move and land in the editing view as in play.
  - Invalid weather settings, or a precipitation map that can't be made, are reported in the status line, once per
    room visit.
  - The AI proposal panel says what a weather change does, for example
    "Village: weather none -> rain x3000 (wind 0.8 east m/s)". Settings the words leave out are named, for example
    "changes opacity".
- **Authoring:** a new checked operation, `set_weather_exposure`, beside `set_particles`; both are exposed to the
  AI/MCP layer.

## Architecture

### The precipitation map: `engine/hd2d/precipitation.py`

- **What it is:** an orthographic depth map looking along a falling effect's mean fall direction: straight down,
  tilted by its wind.
- **What it is drawn from:** the room's real geometry, meaning the ground plus every structure, including structures
  being dragged in Studio.
- **How it is used:** its depth at a column is the first surface a drop falling along that direction meets.

**Design points:**

- **Independent of the sun.**
  - It borrows only `sun_matrix`'s box fitting and the caster shaders.
  - It has its own matrix, a 1024² resolution (about 6 cm a texel over the village), its own program and its own
    lifecycle.
  - Sun direction, intensity, shadow softness or shadows switched off never change it.
- **Cutaways open no holes.**
  - The cutaway (the see-through roof around the player) is a `discard` in the camera's mesh shader only.
  - The map's caster draws every structure whole, so a cut-away roof still shelters. Independent rendering QA
    verified this behind the cottage with the cutaway open.
- **Billboards are left out:** characters, doors and lamps don't shelter rain (see Limitations).

### The map as a cached resource

| Event | What happens |
|---|---|
| First frame that a falling effect is drawn (game, or Studio previewing) | Its map is made, about 1 ms of CPU to issue (QA measured 0.27 ms of GPU), and cached. |
| Further frames | Cached: a dictionary lookup, 4 µs per frame (QA). |
| Structure edit (`set_live_ids`, `set_live` during a Studio drag) | `invalidate()` frees the maps, and the next frame makes them again (median 1.1 ms). |
| Committed Studio edit, undo/redo, reimport, room change | The room reloads with a new renderer, so a new map. |
| Wind or speed changed (a different fall direction) | The key is the direction quantised to 0.5°, so a different key and a new map; a stale map is never sampled. The old map is freed when no effect uses it, though an effect that is only switched off keeps its map. |
| Two falling effects (rain + snow) | One map each, at most 4. |
| A map fails to build (driver refuses) | What was made is freed. The effect falls as in 18A (no shelter, no impacts), and the reason is kept and shown in Studio. It isn't retried while this renderer lasts (not every frame of a Studio drag either); the room's next load tries again. |
| `release()`, room change, window close | Every map is freed. Maps are counted in `gl_objects()` and `stats()`. |

The quantisation error is at most 0.25° of tilt, so at most 5 cm over the 12 m that rain falls through the box. That
is less than one texel.

### In the particle vertex shader (still stateless)

- **`place(t)`.** 18A's motion became a function `place(t)`, the position at time t, which depends purely on the
  seed.
- **Shelter.**
  - Each falling particle is projected into its map. If it is `s` metres *past* the first surface along the fall
    (`s ≥ 0`), it has landed or is under shelter.
  - A drop below a roof had already landed on that roof, so it is not drawn.
- **Impact along the actual fall.**
  - The surface's height `h` under the drop along its fall comes from the map. For snow, `h` is taken under its path
    without the sway, which moves only slowly.
  - Gusts and sway move a drop across but never up or down, so its fall in height is exact. It met the surface
    `age = (h − z) / fall_speed` seconds ago.
  - Its landing point is `place(t − age)`, where it was then, pushed back onto the surface along the fall.
  - A wind-slanted drop therefore lands where its own slanted path meets the surface, not at the XY where it is now.
  - On a level surface the landing moment, and so the splash's place, is fixed for the impact's whole life.
- **A consistency check.** If the landing point isn't on its column's surface (within 12 cm for rain, 50 cm for snow
  so that sloped roofs pass), the impact isn't shown rather than shown in the wrong place. This happens when a gust
  carried the drop across an edge.
- **What a landed particle shows.**
  - It shows for the preset's impact time:
    - **rain:** 0.15 s, playing three splash frames (3×2, 5×2 and 7×2 px, drawn in code);
    - **snow:** 1.5 s, the flake fading.
  - It is drawn in the same quad and the same instanced draw call. It stands on the surface facing the camera,
    6 cm towards it, and is depth-tested like the drops.
- **Room clipping.**
  - The rectangle is the room's own (its `world_width`/`world_height`, or its map's size). An HD-2D room with neither
    uses what it's built of, and a room with no size and no geometry isn't clipped.
  - Particles fade over the last 0.75 m inside it.
  - A particle not drawn is moved off the picture and costs no fill.
- **Ground hits.** The box reaches below the ground by the fastest drop's speed × its impact time, so a drop landing
  on the ground lives on, unseen, long enough to show its splash.
- **Leaves** (the windborne preset) are carried, not falling: they get clipping but no shelter or impacts.
- **2D rooms.**
  - Splashes and settling flakes appear at ground level (the box's floor).
  - Particles are clipped to the map; for a map in its own file, that happens once it has loaded.
  - There is no roof shelter in 2D; that would need a roof mask.

### Wind, gusts, mixed effects and moving structures

- **Wind direction or speed:** a new fall direction, a new map. Tested: 20 wind changes leave one map, and 72
  directions leave one live map with level GL counts (QA).
- **Gusts:**
  - The map is drawn along the mean direction; gusts move drops across it.
  - The landing is found from the drop's own path, so impacts stay put: at most 3 mm at preset wind, and at most
    2.3 cm during a splash's life at a gusty 4 m/s.
  - A gust can carry a drop past a top edge, such as a stair or a crate, that its mean column hits. About 1% of
    strong-wind splashes then land off their true point, a few rarely by metres (see Limitations).
- **Mixed effects:** each falling effect samples its own map.
- **Moving structures:** Studio drags invalidate the maps each frame, so rain lands on the structure where it is now.
  This costs 3.9 ms per drag frame with two maps (below). The game has no moving structures yet.
- **Failed or out-of-bounds samples:**
  - A sample outside the map, or of empty sky, means "no surface": the drop keeps falling.
  - Room clipping removes those outside the room.
  - A failed map gives 18A behaviour, as above.

## Proof in the actual world (the starter village)

`tooling/m18b_weather_study.py proof OUT` and `pictures OUT` run in hidden windows. The numbers are in
[proof.json](milestone18_stage2_environmental_collisions_evidence/proof.json).

### How shelter is judged

A picture can't tell a drop *stopped* by a roof from one merely *hidden* behind it, so shelter is judged in world
space:

1. **The probe.** It draws the particles top-down into a float target, with the camera's depth test **off**, in the
   shader's diagnostics mode. That mode writes each particle's world position and id, and whether it has landed.
2. **The rays.** Every probed particle is ray-cast along its effect's own fall against the village's actual
   triangles: every structure's model as placed, plus the ground.
   - A falling drop must have nothing above it. "Under shelter" means 5 rays, 12 cm apart, all blocked.
   - A landed one must sit on a surface (a hit within 15 cm along its fall) with nothing above it.
3. **Coverage.** Probes cover the whole room (camera targets every 18 m) at three moments.
4. **Negative control.** The same probes are run with shelter off, which is Stage 18A's behaviour.

### Results

| Effect | Falling probed | Under shelter: 18B | Under shelter: 18A control | Impacts | On a surface | Under shelter |
|---|---|---|---|---|---|---|
| rain (wind 0.8 east) | 33,888 | **0** | 922 | 3,869 | 3,867 (99.9%) | **0** |
| rain, wind (4, 1) m/s | 32,781 | **0** | 877 | 3,753 | 3,753 (100%) | **0** |
| snow | 22,554 | **0** | 724 | 3,550 | 3,530 (99.4%) | **0** |

Where the rain landed (rain, wind 0.8 east), with heights:

| Surface | Impacts | Height (m) |
|---|---|---|
| Ground | 3,033 | 0.00 |
| Path | 276 | 0.00–0.02 |
| Terraces (`platform_4m`) | 298 | 1.35–2.00 (slope to top) |
| Stairs | 62 | 0.25–2.80 |
| Bridge deck and rails (`bridge_6m`) | 48 | 2.00–2.65 |
| Cottage (its roof) | 74 | 2.52–3.76 |
| Shop | 64 | 2.20–3.28 |
| Lamp posts, a fence, crates, barrels | (various) | at their tops |

- **With wind (4, 1),** the cottage also takes hits on its windward wall, from 0.47 m up: slanted rain striking the
  wall.
- **Snow** settles on the roof (2.55–3.80 m), the deck (2.0 m), the terraces (2.0 m) and the ground.
- **Impacts that miss a surface** are within a texel or so of an edge: 2 for rain, 20 (0.6%) for snow, whose
  sloped-roof tolerance is wider.

### The ten checks

| # | Check | Evidence |
|---|---|---|
| 1 | Rain hitting the cottage roof | 74 roof impacts at 2.5–3.8 m; [view_rain_cottage.png](milestone18_stage2_environmental_collisions_evidence/view_rain_cottage.png) (18A left, 18B right) |
| 2 | A genuinely sheltered patch under the eaves | 0 drops under shelter, against 922 in 18A. [topdown_rain.png](milestone18_stage2_environmental_collisions_evidence/topdown_rain.png): the cottage's and the shop's footprints have no drops near the ground in 18B. QA's side-on slab renders through the cottage show 0 drops (only splashes on windward walls), against 2,500–8,900 px in 18A |
| 3 | Rain splashing on the bridge deck | 48 deck and rail impacts at 2.0–2.65 m; [view_rain_bridge.png](milestone18_stage2_environmental_collisions_evidence/view_rain_bridge.png) |
| 4 | No rain through the deck into the underpass | 0 falling under shelter. QA's slab renders under the deck show 0 lit pixels at every moment and wind, against 12,000–16,000 in 18A |
| 5 | Splashes on the ground and the raised terraces | 3,033 on the ground, 298 on terraces; [view_rain_terraces.png](milestone18_stage2_environmental_collisions_evidence/view_rain_terraces.png) |
| 6 | Wind-angled rain striking the correct positions | Wind (4, 1): every impact verified by a ray cast along its own slanted fall, with windward wall hits; [topdown_rain_wind.png](milestone18_stage2_environmental_collisions_evidence/topdown_rain_wind.png). QA at wind (−6, 0): impacts are not at the drop's current XY (median offset 0.45 m), 275 hits on the windward wall, and a dry strip 2.2 m wide on the lee side (about 2.5 m expected) |
| 7 | Snow settling at the correct elevation | Roof 2.55–3.80 m, deck 2.0 m, terraces 2.0 m, ground 0; [view_snow_cottage.png](milestone18_stage2_environmental_collisions_evidence/view_snow_cottage.png), [topdown_snow.png](milestone18_stage2_environmental_collisions_evidence/topdown_snow.png) |
| 8 | A dry cottage interior | Indoor (the template): 0 particle pixels and no layer, with the notice shown. Negative control (told outdoor): 11,070. [interior.png](milestone18_stage2_environmental_collisions_evidence/interior.png) |
| 9 | Camera movement without detached or jumping effects | See the anchoring table below. [rain_camera_pan.webp](milestone18_stage2_environmental_collisions_evidence/rain_camera_pan.webp) |
| 10 | Studio's Preview weather matches play | The same renderer and layer. The GPU test compares the weather pixels of Studio's view and play's from one camera: they overlap above 95%, the rest being play's cutaway. QA found Studio's precipitation map byte-identical to the game's, and 0 particles in sheltered spaces in Studio's own view (16 in 18A). [studio_preview.png](milestone18_stage2_environmental_collisions_evidence/studio_preview.png) |

Anchoring (check 9). The same moment, probed from two camera targets, gives identical impact positions (0.0 m
difference). Each impact was then followed over most of the time it shows:

| Effect | Impacts followed | Median drift | p99 | Max | Over 3 cm |
|---|---|---|---|---|---|
| rain | 543 | 0.2 mm | 2.8 mm | 3.1 mm | 0 |
| rain, strong wind (4, 1) | 537 | 2.7 mm | 1.8 cm | 2.3 cm | 0 |
| snow (over its 1.5 s settle) | 510 | 1.4 mm | 2.8 cm | 2.2 m | 3 |

The snow outliers are at the deck's north edge: a settling flake there can switch to the surface below.

The pictures put 18A (shelter off) on the left and 18B on the right, at the same moment.

## Performance (RTX 4070, GL 4.6; village, 1280×720, shadows on)

`tooling/m18b_weather_study.py perf OUT` ([perf.json](milestone18_stage2_environmental_collisions_evidence/perf.json))
uses 18A's own harness. In one game, for each case, it measures 5 interleaved rounds of 60 frames with the particles
drawn and switched off (medians), first with shelter on (18B), then off (18A's path).

| Case | Particle pass GPU: 18B | 18A path (this run) | 18A accepted (#377) | Added frame, 18B (CPU wall) | Draw calls | Maps / map memory | Map build (CPU) |
|---|---|---|---|---|---|---|---|
| rain 1,000 | 0.005 ms | 0.008 | 0.010 | 0.14 ms | 32 (+1) | 1 / 5.0 MB | 3.2 ms (first: program) |
| rain 5,000 | 0.020 ms | 0.022 | 0.035 | 0.14 ms | 32 | 1 / 5.0 MB | 1.1 ms |
| rain 10,000 | 0.034 ms | 0.035 | 0.062 | 0.20 ms | 32 | 1 / 5.0 MB | 1.2 ms |
| rain 20,000 | **0.060 ms** | 0.065 | 0.105 | 0.23 ms | 32 | 1 / 5.0 MB | 1.1 ms |
| snow 10,000 | 0.025 ms | 0.022 | 0.039 | 0.21 ms | 32 | 1 / 5.0 MB | 1.2 ms |
| rain 10k + snow 5k | 0.041 ms | 0.041 | (n/a) | 0.32 ms | 33 (one per effect) | 2 / 10.0 MB | 1.1 + 1.2 ms |

- **The particle pass:**
  - Shelter adds no measurable GPU time.
  - The target was about 0.2 ms at 20,000; it measures **0.060 ms**.
  - QA measured the four-effect maximum (4 × 20,000) at 0.05–0.14 ms.
  - It is lower than 18A's accepted figure because particles outside the room, and those sheltered or long landed,
    are now moved off the picture and cost no fill. The 18A path in this run shares the room clipping.
- **Added frame time** (CPU wall clock) is 0.14–0.32 ms, the same as 18A's: QA measured 0.10–0.19 ms for 18B against
  0.09–0.27 ms for 18A.
  - A first version cost about 1.8 ms per frame for both, because the renderer recomputed every model's bounds each
    frame to find the map.
  - The box is now worked out once per renderer, and the map's draw list is built only when a map is made.
- **A Studio drag with the preview on** remakes the maps every frame: 13.8 ms against 9.8 ms with the weather off,
  +3.9 ms with two maps.
  - The first version waited for the GPU after each build (`ctx.finish()`, there only for timing) and cost 6–9 ms
    more.
- **Room load and first frame:** 225 ms with rain and snow, against 198 ms without weather. QA attributes about
  6 ms of that to 18B (the maps and the layer); the rest is 18A's seeds for 15,000 particles.
- **GPU memory:** 5 MB per map, which is 1024² of 32-bit depth plus the 1-byte colour target arcade requires, and
  at most 4 maps (20 MB). The particles add 24 B each, as in 18A.

### GPU lifecycle and failure recovery (counted after `ctx.gc()`)

| State | Buffers | Textures | Framebuffers | Programs |
|---|---|---|---|---|
| No weather | 125 | 42 | 6 | 28 |
| Rain + snow (two maps) | 128 | 47 | 8 | 29 |
| After 50 invalidations | 128 | 47 | 8 | 29 |
| After 20 wind changes (one map) | 127 | 45 | 7 | 29 |
| Released | 125 | 42 | 6 | 28 |

- **Room changes:** 20 village↔cottage round trips leave identical counts, with weather (124/47/8/29 before and
  after) and without.
- **Studio Play/Stop** (5 cycles, rain and snow): +1 texture, framebuffer and program on the first Play, then level.
  QA saw the same one-time +1 on 18A, so it predates this stage.
- **Injected failure** (the driver refuses the map's framebuffer):
  - the rain still draws, in one call;
  - the GL counts are unchanged;
  - the error is recorded and shown in Studio;
  - a structure edit doesn't retry it, and the room's next load makes the map, with the error cleared.
- **QA's injected failures** also covered `depth_texture`, `texture` and `program`: 0 objects leaked in each case.

## Tests and gates

- **`tests/test_weather_collisions_gpu.py`** (`MESH_GL_SMOKE=1`, hidden windows, 11 tests):
  - shelter and impacts for rain at two winds and for snow, with the 18A negative control;
  - impacts that stay put;
  - the dry interior;
  - the cache: invalidation, a new wind, freed;
  - failure recovery;
  - room changes;
  - Studio's preview, matching play;
  - Studio's error message;
  - 2D rain landing on the ground and kept on the map.
- **`tests/test_scene_particles.py`** (fast, 30 tests):
  - map keys;
  - fall and impact reach;
  - the splash art;
  - indoor exposure, which is checked even without particles;
  - room rectangles in 2D and HD-2D;
  - the operation;
  - the AI review lines.
- **`tests/test_scene_particles_gpu.py`:** 18A's camera depth-occlusion check now runs with shelter switched off.
  Shelter removes the drops that used to sit behind buildings, and that test measures the camera's depth test on its
  own. Its threshold is unchanged.

Local results (Windows), on the final code:

| Gate | Result |
|---|---|
| Fast tier | 4,647 passed, 6 skipped |
| GPU suites (`MESH_GL_SMOKE=1`): weather, particles, Studio, starter, runtime | 43 passed |
| ruff gate | ok |
| Wheel bundle test (without `PYTHONPATH`) | passed |

- **mypy gate:** no new errors. Its two `tooling/hd2d_lab` numpy errors are the known local ones, also on the base.
- **CI on #380's first push:** green except one Linux run, where the `exception-policy-scan` step exceeded its timing
  budget by 44 ms (3,600 ms against 3,556 ms). The other Linux run of the same commit passed. This is timing-budget
  instability of the kind tracked in #373. It was not rerun.

### Independent QA (Opus, hidden windows, real in-engine output)

**Rendering: CONDITIONAL PASS, its conditions addressed.**
- **Its own methods:**
  - side-on slab renders through the sheltered volumes, with the camera depth test off and every lit pixel ray-cast;
  - a "seen" probe through the game camera's own depth (cutaway open);
  - a NumPy replica of the drop motion.
- **Verified:**
  - shelter under the deck and in the cottage and shop at every wind;
  - the cutaway opening no holes;
  - wind landings and dry strips;
  - crisp splash and flake art;
  - the dry interior, room and 2D clipping;
  - Studio's identical map.
- **Its minors, addressed:**
  - impacts creeping during their life (snowflakes a median 1.5 cm, up to 12 cm): fixed. Landing is now timed from
    heights alone, and snow's surface found under its sway-free path. Re-measured in the table above;
  - a hard pop at the room edge: a 0.75 m fade added.
- **Its minors, left as limitations:** rare edge grazes in strong gusty wind.

**Performance: CONDITIONAL PASS, its condition addressed.**
- **Verified:**
  - the particle pass, under the target even at 4 × 20,000;
  - one draw call per effect;
  - map memory;
  - 72 directions;
  - room changes, Play/Stop, game close;
  - injected failures of four kinds.
- **Its major finding, fixed:** a Studio drag with the preview on cost 6–9 ms per frame, all of it the build's
  `ctx.finish()`. It is now +3.9 ms with two maps.
- **Its minors, fixed:** a failed map retried every drag frame; switching an effect back on remade its map.

**Compatibility: CONDITIONAL PASS, its conditions addressed.**
- **Verified:**
  - 2D and HD-2D rooms without weather are pixel-identical to base `b36fea7` across five templates;
  - the only template change is the cottage's exposure;
  - saves and authoring round trips;
  - Studio's button, undo/redo and Play/Stop;
  - the AI layer's operations.
- **Its major finding, fixed:** an HD-2D room without ground lost its rain, because clipping used only what the
  room is built of. It now uses the room's own rectangle.
- **Its minors, fixed:**
  - the weather error repeated over every edit's message;
  - an invalid exposure was silent in rooms without particles;
  - unclear AI review lines;
  - 2D maps in their own file were not clipped.

## Limitations

- **People don't shelter rain.** Billboards (characters, doors, lamps) aren't in the map; rain falls past them, and
  they get no splashes.
- **Resolution.** The map is 1024² over the room, about 6 cm a texel in the village. Thinner features than that can
  be missed. About 0.1% of rain impacts, and 0.6% of snow's, sit within a texel or so of an edge rather than exactly
  on it.
- **Strong gusty wind.**
  - A gust can carry a drop past a top edge (a stair, a crate) that its mean column hits. About 1% of splashes then
    land off their true point, occasionally on the ground metres beyond (QA).
  - At the presets' winds this is negligible.
- **Snow by an edge.** A settling flake right at the deck's edge can, rarely (3 of 510 followed), switch to the
  surface below during its 1.5 s.
- **A Studio drag with the preview on** costs +3.9 ms per frame with two maps, because they are made again every
  frame.
- **The room's box is worked out once per renderer.** A structure dragged outside the room's original extent isn't
  covered until the room reloads (the next committed edit). The sun's shadow box behaves the same way.
- **Density.** Extending the box below the ground for impacts thins the visible rain by about 14% (snow about 19%)
  at the same count (QA). The counts can simply be raised.
- **No 2D roof shelter.** 2D rooms get ground splashes and map clipping only.
- **Studio's 2D view** has no weather preview; the toggle is in the 3D view.
- **Leaves** are not sheltered: they are carried by the wind.
- **Weather is per room** (`settings.particles`). World-level weather, event transitions, the Weather panel, presets
  and combinations without JSON are later stages, as briefed.

## Known defects, accepted and tracked

The owner accepted 18B with these rare defects tracked rather than fixed now. They are measured by
`py -3.13 tooling/m18b_weather_study.py defects OUT` (hidden windows) on the final shader; the numbers are in
[known_defects/known_defects.json](milestone18_stage2_environmental_collisions_evidence/known_defects/known_defects.json),
so a later fix can be checked against them.

1. **A snowflake switches to a lower surface near bridge edges.**
   - 5 of 2,474 settled flakes followed through their 1.5 s moved more than 3 cm.
   - The worst, particle 2372 (snow, seed 2), settled on the deck's north edge at (23.02, 25.85, 2.0) m and was at
     (23.92, 26.0, 0.0) m 0.9 s later. Before and after:
     [snow_edge_hop.png](milestone18_stage2_environmental_collisions_evidence/known_defects/snow_edge_hop.png).
   - The cause: its sway-free path still drifts with the wind, so its column crosses the deck's edge during the
     settle.
2. **An occasional inaccurate strong-gust impact.**
   - Each splash is compared with where that drop's real gusting path first meets the village's triangles, using a
     NumPy replica of the shader's motion. That replica agrees with the shader to within 1 cm at preset wind.
   - Results for about 480 splashes per wind:

     | Wind (m/s) | Median error | p99 | Over 10 cm |
     |---|---|---|---|
     | (0.8, 0) | 0.9 mm | 7 mm | none |
     | (4, 1) | 4.6 mm | 3.3 cm | 1 (0.2%), the worst 0.26 m |
     | (−6, 0) | 6.1 mm | 8 cm | 1 (0.2%) |

   - The (−6, 0) outlier is particle 2509. Its true first hit is the cottage roof at (7.23, 11.14, 3.31) m, but it
     splashed on the ground at (4.58, 11.14, 0.0) m, 4.24 m away. The gust carried it past the eave that its
     map column (along the mean fall) misses.
3. **Precipitation-map regeneration overhead during Studio drags.**
   - With the preview on, every drag frame makes the maps again: +4.6 ms per frame with one map (21.6 → 26.1 ms) and
     +7.1 ms with two (21.6 → 28.8 ms) in this measurement, against +3.9 ms in the perf run above.
   - Play and ordinary editing are unaffected.
   - Candidate fixes: throttle rebuilds during a drag, or rebuild only the dragged structure's region.

## Next steps (not started)

- **Water stage:** puddles, wet surfaces, ripples, ponds and rivers. The precipitation map can tell them where rain
  lands.
- **World weather:** a world-level weather state with event-driven transitions (opacity and count fades), honouring
  each room's `weather_exposure`.
- **The Studio Weather panel:** visual controls, presets and combinations, built on `set_particles` and
  `set_weather_exposure`.
- **Characters:** optionally include billboards in the map, for umbrellas and porches with people.

## Verdict

**PASS.**

- **Shelter is real, not visual.** In world space, with the camera's depth test off, no falling drop is under the
  cottage, the shop, the terraces or the bridge's deck, for rain, wind-driven rain and snow. 18A's negative control
  finds 724–922.
- **Impacts land where they should.** Every splash and settling flake sits on its real surface, at its height, along
  its own (slanted) fall, and stays put as the camera moves.
- **Stays inside the rooms.** The interior stays dry, and weather stays inside each room.
- **Studio previews it as play shows it.**
- **Performance holds.** The particle pass is 0.060 ms at 20,000, under the 0.2 ms target, with one draw call per
  effect. GPU objects stay level across invalidations, wind changes, room changes, Play/Stop and failures.
- **Independent QA.** All three reviewers' conditions were addressed, and their minors are fixed or listed above.

Stage 18B stops here for the owner's review; nothing is merged.
