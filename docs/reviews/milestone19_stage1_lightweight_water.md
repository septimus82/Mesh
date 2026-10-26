# Milestone 19A: lightweight water surfaces (puddles and ponds)

- **Branch:** `feature/m19a-water`.
- **Draft PR:** [#382](https://github.com/septimus82/Mesh/pull/382), into `redesign/visual-editor`.
- **Builds on:** Stage 18B (#380): rain, its precipitation map and the Studio weather preview.
- **Not in this stage:** rivers, waterfalls, fluid simulation, swimming, full second-scene reflections, flooding, the
  weather UI and thunderstorms.

**Verdict: PASS** (details at the end).

## What a creator gets

- **A Water object** in Studio's Objects list. Click the map (2D) or the ground or a floor (3D view) to place it; it
  starts as a puddle.
- **The inspector's Look tab is the water:**

  | Control | What it does |
  |---|---|
  | Puddle / Pond | The preset |
  | Width / height | Size in px |
  | Colour, opacity | Its tint and how see-through it is |
  | Waves, reflection | How much it moves and how much it mirrors |
  | Round / Square | Its shape |
  | Rippled by rain | Whether the room's rain rings it |
  | Walk through it | Unticked, it blocks the way |
  | Step sound | Played on each step through it |
  | Remove water | Stops the object being water |

  Every change is one checked edit (`project_ops.set_water`), so it undoes, redoes, saves and reopens like any other.
- **Placing and sizing:** in the 2D view a blue corner sizes it and an outline names it. In the 3D view it can be
  clicked and dragged like any object. Its elevation is its water level.
- **Preview:** it moves (waves) while editing. With Studio's Preview weather on (18B), the room's rain ripples it in
  the editing view too.
- **Weather:** with no rain the water is still there, calm or gently moving. Rain in the room rings it, except where
  something above shelters it.
- **Gameplay:** a character walking through water leaves a ring and a few splash pixels at each step, plays the
  water's step sound if it has one, and announces a `water_step` event (who, which water, where) for game logic. A pond
  set not walkable stops characters at its edge.
- **AI authoring** uses the same operations: `place_blank` then `set_water` / `remove_water`, exposed through
  `engine.authoring`. The AI review card says, for example, "adds 'Pond' (pond water 224 x 144)" or "'Pond' water
  width: 224 -> 300".
- **Original procedural look:** no PixelLab or other assets.

| Preset | Default size | Look |
|---|---|---|
| Puddle | 64 × 40 px (2 × 1.25 m) | pale grey-blue, 62% opaque, nearly still, strongly mirror-like |
| Pond | 224 × 144 px (7 × 4.5 m) | deep teal, 84% opaque, gentle waves, darker towards its middle, lighter rim, a softer mirror (0.35) |

Both presets are round by default (Round/Square switches the shape). Rain ripples are on and both are walkable by
default.

## Architecture

### Data

- **The object.** A water surface is an ordinary object (an entity) with the `WaterSurface` behaviour
  (`engine/behaviours/water_surface.py`). Its settings are `behaviour_config["WaterSurface"]`: `preset`, `width`,
  `height` and optionally `colour`, `opacity`, `shape`, `waves`, `reflection`, `rain_ripples`, `walkable` and
  `step_sound`.
- **Checking.** `engine/water.py` checks them with `parse_water` (unknown keys, presets, colours and ranges are
  refused with the reason).
- **No new scene format.** It reuses the object system Studio, saves, flags ("Show when") and the AI already
  understand.
- **Blocking ponds.** A pond that can't be walked through is the same object made solid with a box collider its size,
  so the existing movement and collision code (2D, and HD-2D's level-aware 2D solids) stops characters. No new
  collision code.

### Drawing: `engine/water.py` `WaterLayer`

- **One draw call.** Every water surface of the room goes into one instanced draw call: one instance per surface,
  rewritten only when a surface moves or changes.
- **Order.** HD-2D draws it after the structures and characters, depth-tested and not writing depth, blended, then
  the weather. In 2D it is drawn after the tile layers below the characters and before them.
- **Level.** The surface stands 3.5 cm above its level: over the ground and over the 2 cm path model (at 1.2 cm a
  puddle on a path was hidden by the path; rendering QA).
- **Lighting.** HD-2D water is lit by the room's own lighting (`engine.hd2d.lighting`: ambient, the sun, lamps and
  their shadow maps), so characters' and structures' shadows fall on it. 2D water takes a flat light.
- **On the pixel grid.** Everything is worked out at the centre of a texel of the art's 32 px per metre and quantised
  to a few shades, so the water reads as pixel art. Sampling is nearest.
- **Movement.** Two slow sine wave trains bend the surface normal, stronger on ponds.
- **Colour and depth.** The colour and opacity are the preset's or the creator's. A pond darkens towards its middle
  (`edge distance`) and has a light rim.
- **Reflection (HD-2D): a cheap environmental approximation, not a second render.**
  - Before the water is drawn, the frame so far (colour and depth) is copied: one blit per frame while the room has
    water.
  - The view ray is mirrored at a calmer surface (a quarter of the waves' slope) and marched up to 10 steps across
    that copy.
  - Where it passes behind something on screen that stands more than 30 cm above the water (the cottage, the bridge,
    a character), the water shows it. Elsewhere it shows the sky's colour, and it gives way to the sky over the
    picture's outer 14%.
  - Fresnel-like strength depends on the viewing angle, scaled by the water's `reflection`.
  - 2D rooms get the sky's tint and highlights only.
- **Rain rings.**
  - **Rate.** It comes from the room's rain density: rain drops ÷ 3,000 × speed, capped at 2, and only if the water's
    `rain_ripples` is on.
  - **No CPU work.** Nothing comes back from the GPU's raindrops. The surface is split into 0.5 m cells, and each
    starts rings at hashed places and moments: as stable in the world as the surface, and rain-heavy where the rain
    is heavy.
  - **Shelter.** Water under shelter gets no rings: the shader asks the rain's precipitation map from 18B whether
    anything stands above that point.
  - **Studio.** In Studio the rings follow the weather preview.
- **Footsteps.**
  - Up to 8 recent steps (place and time) are passed as uniforms.
  - Each draws an expanding ring for 1 s and a few hashed splash pixels for its first 0.25 s.
- **Lifecycle.**
  - **Owners.** The HD-2D renderer owns its `WaterLayer` (`renderer.water`) and frees it in `release()`. A 2D room's
    layer is `window.scene_water`, freed on the next room load (`engine.water.reset`) and on window close.
  - **What it owns:** the program, the quad, the instance buffer and the frame copy (colour and depth textures, a
    framebuffer, remade if the frame's size changes).
  - **Failure.** A layer that fails part way frees what it made (tested). A water pass the driver refuses turns water
    off for that room: the reason is kept and shown in Studio, the game draws on, and the room's next load tries
    again. This holds in HD-2D and 2D.
  - **Skipped when unseen.** With no water surface in view, the pass and its frame copy are skipped.
- **Counted.** The renderer's `gl_objects()` and `stats()` count it (`water_surfaces`, `water_bytes`).

### Gameplay: the `WaterSurface` behaviour

- **Registration.** It registers its water with the room (`window.water_bodies`, reset on every room load). It hides
  the object's placeholder picture, because the water is its picture.
- **"Show when."** The object's flags (its `ConditionalActivator`, or older entity-level flags) hide the water and its
  splashes (`engine.water.active`).
- **Placeholders.** A setting holding the behaviour's "the preset's" placeholder ("", 0, −1, as adding the behaviour
  plainly writes) means the preset's for the game, Studio and the AI alike.
- **Bad settings.** A hand-edited setting the game can't use leaves that water off (logged). Studio shows it as its
  preset with the reason, and `set_behaviour_param` refuses such values.
- **A missing step sound** is reported once and the steps go quiet.
- **Steps.** Each update it checks the feet of the characters it names (`target_tags`, the player by default)
  against its shape. Every 14 px walked in the water is a step:
  - a ripple (`engine.water.add_step`);
  - the step sound through `audio.play_world_sfx`, if set;
  - a `water_step` gameplay event.
- **Cost.** 0.005 ms per update for the two water surfaces in the test village.

### A bug found and fixed on the way

- **The failure.** In the first renders the water and the rain both vanished.
- **The cause.** arcade's `ctx.copy_framebuffer` leaves the copy bound for drawing without updating arcade's record
  of the active framebuffer, so the following `fbo.use()` returned early. Everything after it (water, then weather)
  was drawn into the copy.
- **The fix.** `fbo.use(force=True)` after the copy, with a comment explaining why.

## The test environment and real renders

`tooling/m19_water_study.py` builds the starter village with a puddle beside the cottage and a pond near the bridge,
through `project_ops` exactly as Studio and the AI do, at places worked out from where the cottage and bridge stand.
Every picture is from the engine in hidden windows, at its own 2× scale.

| What | Picture or clip |
|---|---|
| The pond in rain: ripples, darker middle, rim; the shop's roof in front of it | [pond_rain.png](milestone19_stage1_lightweight_water_evidence/pond_rain.png) |
| The same, dry | [pond_dry.png](milestone19_stage1_lightweight_water_evidence/pond_dry.png) |
| The puddle beside the cottage mirroring its wall, in rain and dry | [puddle_rain.png](milestone19_stage1_lightweight_water_evidence/puddle_rain.png), [puddle_dry.png](milestone19_stage1_lightweight_water_evidence/puddle_dry.png) |
| The player walking through the puddle: footstep rings | [puddle_walk.webp](milestone19_stage1_lightweight_water_evidence/puddle_walk.webp) (1:1) |
| The camera moving across the pond in rain: water and rings stay put, depth correct | [pond_rain_pan.webp](milestone19_stage1_lightweight_water_evidence/pond_rain_pan.webp) |
| Depth: no water, the pond, the pond with its depth test off | [pond_depth.png](milestone19_stage1_lightweight_water_evidence/pond_depth.png) |
| Rain ripples off and on: puddle, pond, a puddle under the bridge deck, and that one with shelter off | [ripples_puddle.png](milestone19_stage1_lightweight_water_evidence/ripples_puddle.png), [ripples_pond.png](milestone19_stage1_lightweight_water_evidence/ripples_pond.png), [ripples_sheltered.png](milestone19_stage1_lightweight_water_evidence/ripples_sheltered.png), [ripples_sheltered_shelter_off.png](milestone19_stage1_lightweight_water_evidence/ripples_sheltered_shelter_off.png) |
| A 2D room (the blank template): no water, then a puddle under the player and a pond, in rain | [two_d_water.png](milestone19_stage1_lightweight_water_evidence/two_d_water.png) |
| Studio's 3D editing view with a newly placed pond | [studio_water.png](milestone19_stage1_lightweight_water_evidence/studio_water.png) |

## Measured proof ([proof.json](milestone19_stage1_lightweight_water_evidence/proof.json))

| Check | Result |
|---|---|
| Depth-correct | The pond draws 47,818 px. A further 3,254 px are hidden by structures in front of it (the shop's roof), counted against the same frame with the water's depth test off. |
| Moves with the world | The camera moved 0.5 m (the world shifted 31 px): 99.8% of the water's pixels are found where the world moved, against 90.3% unshifted (a large pond overlaps itself). |
| Rain rings open water | Ripple pixels per frame (rings on against off, the rain drawn in both): puddle 1,095–2,204, pond 12,308–15,644 |
| …and not water under shelter | A puddle under the bridge deck, judged with its depth test off so the deck's occlusion doesn't count: 56–132 ripple pixels, against 436–912 with its shelter switched off (the negative control), an 85–90% reduction. Rendering QA found all the remainder on its south rim, at the deck's edge (open sky). |
| Rings stay put as the camera moves | 92.6% of the ring pixels are found shifted with the world (−31 px), against 25.0% unshifted |
| Footsteps | The player walked through the puddle with the arrow keys: 6 steps, 6 `water_step` events, and rings in the clip |
| Walkable or blocking | The player walks north into the pond. Walkable: the feet reach 18.52 m, the pond's centre. Not walkable: they stop at 15.97 m, at its south edge (16.16 m). |
| 2D room | 24,020 water pixels, and 0 of the player's pixels changed by it: drawn under the characters |
| A puddle on a path | Drawn (a GPU test, which fails at the old 1.2 cm lift) |
| Dry weather | Every picture above also exists dry. The water moves without rain, and Studio places water without enabling rain. |

### The Studio workflow

`studio_workflow` drives Mesh Studio through its own buttons, fields and keys, in a hidden window:

| Step | Result |
|---|---|
| Choose Water in the Objects list, click the ground in 3D | "Placed Water on the ground, 0.0 m up. Puddle or pond, size and look: on the right." It is a puddle. |
| Click **Pond**, then type width 180 | A pond 180 px wide |
| Ctrl+Z, then Ctrl+Y | The width goes back to the pond's 224, then returns to 180 |
| Drawn in the editing view | It is 1 water surface, and moving: 26,398 px change between frames with rain previewed |
| Clicked in the 3D view | It is selected |
| Ctrl+S | Nothing unsaved |
| Reopened | A pond, 180 px wide |
| Play (F4), then Stop | In play the water is there; stopping returns to edit mode |

## Performance (RTX 4070, GL 4.6; village, 1280×720, in rain, shadows on)

`tooling/m19_water_study.py perf OUT` ([perf.json](milestone19_stage1_lightweight_water_evidence/perf.json)) times
each case with the water drawn and taken away, in 5 interleaved rounds of 60 frames (medians).

| Case | Water surfaces | Draw calls | Water pass GPU (timer query) | Whole frame GPU, with / without | Water CPU (`_draw_water`) | GPU memory |
|---|---|---|---|---|---|---|
| no water | 0 | 32 | n/a | 1.17 / 1.42 ms (noise) | n/a | 0 |
| puddle only | 1 | 33 | 0.248 ms | 2.14 / 1.81 ms | 0.28 ms | 7.4 MB |
| pond only | 1 | 33 | 0.347 ms | 1.73 / 1.59 ms | 0.28 ms | 7.4 MB |
| both | 2 | 33 | 0.312 ms | 1.84 / 1.42 ms | 0.28 ms | 7.4 MB |

- **The water pass** costs about 0.25–0.35 ms of GPU whether there is one surface or two. Most of it is the
  1280×720 colour+depth copy for reflections and the reflection march, both per frame, not per surface.
  - **Water off screen:** the pass and its copy are skipped: 0 GPU, 0.017 ms CPU (performance QA).
  - **Water filling the screen:** the pass grows with water area. Performance QA measured a pond filling a 1440p
    picture at 0.35 ms dry and 0.64 ms in rain unlit; lit it measured about 1.1–1.2 ms, noisy, with other agents
    rendering.
- **CPU:** 0.28 ms per frame, of which `Lighting.bind` (the shadows on water) is about 0.19 ms; 0.48–0.52 ms at
  1440p.
- **One draw call** for all the water.
- **Memory:** 7.4 MB at 1280×720, almost entirely the frame copy, which costs 8 bytes per pixel. That is 16.6 MB at
  1080p, 29.5 MB at 1440p and about 66 MB at 4K (performance QA). The instances are 64 B per surface.
- **The CPU frame-time differences** (+0.6 to +1.1 ms) are within this machine's run-to-run noise. The no-water case
  measured −0.2 ms; the water step itself is 0.28 ms.

### GPU lifecycle (after `ctx.gc()`)

| Run | Before | After |
|---|---|---|
| 10 round trips village ↔ cottage (water in the village) | 125 / 47 / 8 / 30 (buffers / textures / framebuffers / programs) | 125 / 47 / 8 / 30 |
| Studio: 10 water edits (each reloads the room) | 48 / 9 / 31 (textures / framebuffers / programs) | 48 / 9 / 31 |
| Studio: then 5 Play/Stop | 48 / 9 / 31 | 49 / 10 / 32 (the one-time +1 on the first Play, seen before water existed, then level) |

The GPU tests also release a layer twice, and fail one part way (an injected `ctx.buffer` failure): nothing leaks.

## Tests

- **`tests/test_water.py`** (fast, 17 tests):
  - presets and defaults;
  - every refused setting;
  - shapes (what counts as in the water);
  - the rain rate;
  - `set_water` / `remove_water` (solid and box when blocking, removed when walkable again);
  - preset switches keep a chosen size;
  - the AI path through `authoring.apply`, with its refusal and the review card's words;
  - footsteps through a pond (steps, events, the ripple registry bounded at 8);
  - a room load resetting water;
  - Water in Studio's objects.
- **`tests/test_water_gpu.py`** (`MESH_GL_SMOKE=1`, hidden windows, 8 tests):
  - depth and world anchoring;
  - rain rings on open water and not under shelter (with the negative control);
  - footsteps;
  - walkable against blocking;
  - 2D under characters;
  - room changes and release;
  - the whole Studio workflow;
  - a layer failing part way.
- **`tests/test_generated_docs_freshness_contract.py`:** 65 behaviours, `WaterSurface` among them.
  `docs/behaviours.md` was regenerated.

Local results (Windows), on the final code:

| Gate | Result |
|---|---|
| Fast tier | 4,674 passed |
| GPU suites (`MESH_GL_SMOKE=1`): water, weather, particles, Studio, starter, runtime | 54 passed |
| ruff gate | ok |
| Generated docs verify | passed |

- **mypy gate:** no new errors; the two known local `tooling/hd2d_lab` numpy errors are also on the base.
- **Linux and Windows CI:** see #382.

### Independent QA (Opus, hidden windows, real in-engine output)

Each reviewer first gave a CONDITIONAL PASS. Their conditions were fixed and each re-checked them on the new head:
all three now give **PASS**.

**Rendering.**
- **Its two majors, fixed and re-measured:**
  - A puddle on the path was invisible; it is now drawn.
  - The pond's reflection broke into blotches. False grazing hits fell from 9,234 to 900 px, and the share of pond
    pixels mirroring something is now 0.33–0.41 (a calm mirror of the wall and the player) instead of blotches.
- **Panning flicker:** reflect/sky flips per 0.5 m pan fell from 1.3–1.5% to 0.4–0.5% mid-screen, and from 4.5% to
  0.8–0.9% near the edge.
- **Shadows on water:** now cast by the player, the stairs, the shop and the lamps.
- **No regressions:** depth, ripples, 2D, anchoring.
- **Remaining nit:** water now covers about one texel of the soles of a character standing in it, which reads as
  wading.

**Performance.**
- **Verified:**
  - +1 draw call for 1, 2, 10 or huge water;
  - window resizes reallocate the copy and free the old one;
  - counts level over room changes, 2D rooms, Studio edits, remove/re-add and Play/Stop;
  - everything freed on close.
- **Fixed:**
  - A refused water pass broke every frame; now water goes off for the room, in HD-2D and in 2D.
  - A failed buffer hid the water for good; now it is rebuilt.
  - The frame copy was paid with water off screen; now it is skipped.

**Compatibility.**
- **Verified:**
  - rooms without water are pixel-identical to base `dc8604d` in five templates, before and after walking;
  - saves, Studio save and reopen, and save slots;
  - every inspector control with undo/redo;
  - the 2D corner drag, 3D pick and drag, play;
  - doors, zones and people unaffected;
  - `set_water`/`remove_water` in the AI operations.
- **Its three majors, fixed:**
  - A broken config crashed Studio and the AI review.
  - "Show when" didn't hide water.
  - Water added with plain `add_behaviour` couldn't be edited.
- **Its minors, fixed:** 2D clicks anywhere on water select it; a missing sound is reported once; removal reads
  "stops being water".
- **Results:** 385 relevant tests and 49 GPU tests passed on its re-check.


## Known limitations

- **Simple shapes only:** round (ellipse) or square (rectangle with softened corners). Arbitrary shorelines (polygons,
  painted masks) are future work.
- **The reflection is screen-space.**
  - It shows only what is on screen in the frame so far, so near the picture's edges, or for things off screen, it
    falls back to the sky's colour.
  - The water's own reflection of a character is approximate.
  - It is cheap by design; full planar reflections would need a second render of the scene, which is out of scope.
- **2D water** has no reflections (sky tint only) and no shelter: there is no roof data in 2D.
- **Blocking ponds** block with a box the water's size, so a round pond's corners block too.
- **Footstep ripples** are bounded to the 8 most recent in the room (enough for a few characters walking).
- **Rings under partial shelter.** A water surface partly under shelter is calm only where covered; its rim outside
  still rings (as measured above).
- **The frame copy** costs 8 bytes per pixel: 7.4 MB at 720p, 16.6 MB at 1080p, about 66 MB at 4K.
- **Lighting the water** (shadows on it) costs about 0.19 ms of CPU per frame for `Lighting.bind`, and its GPU cost
  grows with the water's screen area. Binding only on change is a possible later saving.
- **Characters wading.** A character standing in water has about one texel of their soles under it.
- **Validation timing.** The loader doesn't warn about an invalid water preset when validating; the game logs it at
  runtime.
- **Not built (as briefed):** rivers, waterfalls, flowing water, swimming, buoyancy, flooding, and splashes on
  characters.

## Next steps (not started; stop for owner review)

- **Arbitrary shorelines:** painted or polygon water masks; terrain-following edges.
- **Water that responds to the world:** wet surfaces and dynamic puddles from 18B's rain map.
- **Rivers and waterfalls:** flow maps.
- **Characters' reflections:** optionally improved.
- **The weather UI** combining rain, wind and water.

## Verdict

**PASS.**

- **Convincing, cheap water in HD-2D and 2D.** Puddles and ponds are depth-correct in the real starter village and
  stay put as the camera moves. They are lit by the room and its shadows, mirror what stands above them, and are
  rippled by its rain, but not under shelter, using Stage 18B's precipitation map without moving any raindrop to the
  CPU.
- **Gameplay through existing systems.** Footsteps through water splash and announce themselves, and ponds can be
  waded or block the way.
- **Authoring.** Creators place and edit water through Studio's existing Objects list and inspector, with undo, redo,
  save and reopen; the AI uses the same checked operations.
- **Performance.** It costs one draw call and about 0.3 ms of GPU on the RTX 4070, nothing when out of view, and GPU
  objects stay level across room changes, edits, Play/Stop and failures.
- **Independent QA.** All three reviewers pass it after their conditions were fixed.

Stage 19A stops here for owner review. No rivers, waterfalls or complex water effects have been started.
