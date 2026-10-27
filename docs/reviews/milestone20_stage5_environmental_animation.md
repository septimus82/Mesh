# Milestone 20E: environmental animation

- **Branch:** `feature/m20e-env-animation`.
- **Draft PR:** see the PR linked from this branch, into `redesign/visual-editor`.
- **Builds on:** Stage 20D (#387, merged as `1d2501d`).
- **In scope:** a room's wind shared by weather and decoration; GPU sway of scattered plants; animated decoration
  (sprite frames); one small tree; Studio controls; performance and QA.
- **Out of scope:** rivers, waterfalls, biomes, audio; an animation editor; a forest generator; PixelLab or any paid
  generation.
- **Unchanged:** scatter storage, every room made before 20E (pixel for pixel), the terrain, water, precipitation
  physics, collision of everything but the new tree, saves.

**Verdict: PASS** (details at the end).

## Summary

A room now has a **wind** (`settings.wind`: speed, direction it blows toward, gusts), and its decoration can
**move** (`settings.hd2d.motion`). With animation on:

- grass, reeds and flowers lean with the wind and flutter, each out of step with its neighbours; bushes barely move;
  a tree's canopy rocks slowly and late; gusts cross the meadow as waves;
- torches flicker and glow, banners stream downwind (and hang limp in still air), glowcaps glow in the dark,
  bellflowers nod, water drips from the dripping rock;
- rain, snow and windborne leaves fall in the same wind (an effect with its own wind keeps it).

Everything moves on the GPU: the scatter's buffers are built once and never touched as things move; a frame sets a
few uniforms. Off (or in any room made before 20E), the decoration is drawn exactly as Stage 20D drew it.

In Studio, **Wind and motion** in the 3D view's panel: Calm / Breeze / Strong / Gusty, the wind's speed, direction
and gusts, Animation on/off, Sway, Wind, Speed. The view moves while editing (a live preview); every change is one
undo step and appears in the change review.

### Evidence at a glance

| What | Where (`milestone20_stage5_environmental_animation_evidence/`) |
|---|---|
| Five winds, four seconds each (the gusts ten) | `wind_calm.webp`, `wind_breeze.webp`, `wind_strong.webp`, `wind_gusts.webp`, `wind_rain_wind.webp` |
| Wind toward and away from the camera | `wind_toward.webp`, `wind_away.webp` (stills) |
| Playing: walking through it in gusts, and in rain with wind | `walk_gusty.webp`, `walk_rain.webp` |
| The torch's flame at 30 frames a second, lossless | `torch_flame_30fps.webp` |
| Three ways to draw a tree; the camera orbiting them | `trees_compared.webp`, `trees_orbit.webp` |
| Studio | `studio_panel.webp`, `studio_live_preview.webp` |
| Numbers | `identity.json`, `scale.json`, `baseline_20e.json`, `baseline_20d.json`, `winds.json`, `studio.json`, `gameplay.json`, `trees.json` |

Clips are lossy WebP (480 x 270, not scaled) to keep the evidence at 5.2 MB; the flame's strip is lossless.

## Part B: Architecture

### What was reviewed

| Area | Finding |
|---|---|
| Sprite-sheet animation | 2D sprites animate through `engine/animation.py` (per-entity). Scatter needs per-instance phases for thousands of things in one draw: the frame is chosen in the vertex shader (cell offset by time and seed). |
| Scatter batching (20D) | 8 m chunks, one draw a chunk, static buffers. Kept: each vertex gains its part's **motion slot** and its instance's **seed** (9 floats, was 7). |
| Weather particles (18A) | Per-effect `wind` [east, north] m/s and `gust` 0-1, a closed-form drift on the GPU (per-drop gust phase). |
| 2D tilemaps | `TilemapBatcher`: an arcade SpriteList a 16-tile chunk, no animation. Not touched (see Limitations). |
| Shadows | Sun map every frame (structures, characters); lamp maps once. Scatter models cast per 32 m block (20D). |

### The shared wind (`engine/wind.py`)

`settings.wind = {"speed": m/s 0-30, "direction": degrees toward (0 east, 90 north), "gust": 0-1}`; none: calm.

- At a place and time the wind is `speed * (1 + gust * g)`, `g` in [-1, 1] (`gust_wave`): fronts travelling with the
  wind: slow swells (about nine seconds, the particles' own rate) and quick gusts (2.5 s, a few metres apart).
- Particles: an effect without its own `wind` / `gust` takes the room's; one with its own keeps it. A calm room (every
  room before 20E) leaves every effect as it was. Precipitation physics is unchanged: a drop's gust stays its own
  (drops are not tied to a place); the rain's direction and strength are the room's.
- A bad `settings.wind` (hand-edited): still air for the decoration, the rain keeps falling; logged and shown in Studio.

### How a plant moves (`engine/hd2d/motion.py`)

- It **turns about its anchor** (its foot, or for an attached part, where it hangs from), never sliding or
  stretching: the anchor's vertices don't move (measured: a reed's foot pixels identical at every moment).
- **Lean:** `0.6 s^2 / (s^2 + 40)` rad for a fully flexible plant in `s` m/s, times its asset's flex (grass and reeds
  0.85-1, flowers 0.8, bushes 0.1-0.12, a tree's canopy 0.45-0.5), the room's Sway and its per-asset sway.
- **As the camera sees it:** fully across the picture, at most 7 degrees toward or away from the camera (more only
  squashes or stretches a billboard on screen); capped at 46 degrees across. Both caps together keep the tip above
  any slope a plant may stand on (35 degrees).
- **Flutter:** each plant its own rate (0.9-1.7 Hz) and phase from where it stands (a hash), across the picture.
- **Gusts:** felt as the front passes; stiff plants answer later (`lag`: 0.2 s grass .. 0.9 s canopy).
- **Frames:** cells after the sprite's own, at the part's fps (times the room's Speed), looping or ping-pong, out of
  step by the phase variation. A banner's frames turn faster in a stronger wind; in still air it shows a limp cell.
- **Frame-rate independence:** everything is a function of the clock alone (`window.motion_time`, the sum of the
  frames' steps). The GPU clock wraps every hour; every rate is a whole number of turns an hour (also at any Speed),
  so the wrap is seamless.
- The Python twin (`angle`, `frame`) is line for line the shader's, and the tests use it.

### Static versus moving

One shader source compiles twice. A room whose decoration doesn't move draws with the **still** program: Milestone
20D's vertex work exactly (plus a lookup for a flame drawn nearer the camera). Measured: the one-program version cost
a still room's sprite pass about twice 20D's GPU time, because the wind's work ran even when switched off.

### Depth, shadows, collision, lifecycle

| Concern | How |
|---|---|
| Depth | Sprites keep depth-tested, alpha-cut billboards. A torch's flame is drawn 5 cm nearer the camera than its post (it never swaps behind its cup). |
| Shadows | Plants don't cast (as in 20D). A tree's trunk casts as a model; its canopy clusters cast into the sun's map with the same motion (the shadow sways), merged per 32 m block. A canopy takes its light 1.2 m toward the sun, so its own clusters don't darken it. Lamp maps: trunks only. |
| Collision | Decoration is walked through; the small tree blocks (its trunk's wall, as the boulder). The brush keeps a tree's canopy clear of structures and doorways. |
| Culling | Chunk boxes as in 20D; while moving, widened by how far its sprites may lean. Canopy chunks are not distance-culled (their trunks and shadows aren't). |
| Lifecycle | Four programs, the second sheet and the canopy blocks are released with the layer; reloads leave no GPU objects behind (measured). |
| Old rooms | No `motion` block: still. The 20D sheet is byte for byte unchanged (20E's cells are a sheet of their own: a wider sheet moved 20D's texture coordinates by rounding and changed 4-22 pixels a view). |

## Part C: Animated foliage

| Asset | Flex | Lean, strong wind (11 m/s): mean / most | Notes |
|---|---|---|---|
| Grass, tall grass, reeds | 0.85-1.0 | 25 / 32 degrees (a lone reed, measured from the pictures: 25 / 32) | the most; tall things lean further on screen |
| Flowers, bellflowers | 0.8 | | bellflowers also nod (three frames, ping-pong) |
| Bushes | 0.1-0.12 | 3 / 4 degrees | a little |
| A tree's canopy | 0.45-0.5 | 11 / 15 degrees | slow, 0.9 s behind a gust |

Measured from the pictures (`winds.json`, a lone reed ten times a second for six seconds):

| Wind | Lean, mean / most | Height on screen (calm: 103 px) |
|---|---|---|
| Calm | -2 / 4 degrees (an idle stir) | 103 |
| Breeze, 3 m/s | 5 / 12 | 103-105 |
| Strong, 11 m/s | 25 / 32 | 93-104 (leaning over) |
| Gusts, 5 m/s, 0.95 | 15 / 26 (swells and quick gusts) | 98-105 |
| Rain and wind, 8 m/s toward 195 | -24 / 36 (the other way, as the rain) | 83-97 |
| 9 m/s away from the camera | -2 / 8 | 109 |
| 9 m/s toward the camera | -2 / 9 | 95 |

- **Anchored:** the GPU test films a reed in a 12 m/s gusty wind: its foot's pixels are identical at every moment, its
  top moves.
- **Out of step:** two tufts 12 cm apart: correlation of their sway under 0.9 (test); each instance's seed is a hash
  of where it stands.
- **No jitter or popping:** a pure function of the clock; chunk boxes widened by the lean while moving; the clock's
  wrap is seamless.
- **Never through the ground:** the angles are capped so the tip stays above any slope a plant may stand on.
- **GPU only:** no per-instance Python; 0 chunk rebuilds and 0 bytes grown over 600 moving frames, at every scale.

## Part D: Animated decoration

| Asset | Frames | How |
|---|---|---|
| Torch | post + flame: 6 frames, 10 fps, glows | the flame is drawn 5 cm nearer the camera than its post and leans across the picture only; sparks rise |
| Banner | pole + cloth: 4 frames, 6 fps (faster in a stronger wind) | streams downwind (along the camera's right), narrower when the wind blows along the view; hangs limp in still air (its own cell) |
| Dripping rock | 4 frames, 3 fps | a drop forms, swells, falls, splashes into the pool at its foot |
| Glowcaps | 2 frames, 1.5 fps, glow 0.9 | spores drift; they glow at night (their light never drops below a pulsing 0.55-0.9 of full), muted by day |
| Bellflowers | 3 frames, ping-pong, 2 fps | the bells nod as the stems sway |

- **Shared frame data:** frames are cells in one sheet (`foliage_motion.png`, 48 x 48 px, original, drawn by
  `tooling/hd2d_assets/scatter_art.py`); every instance reads its part's row of the motion tables (uniforms), never
  an entity or a sprite of its own.
- **Controls** (per asset, `settings.hd2d.motion.assets`, through `set_motion` / AI): `fps` (1-30), `loop`
  ("loop", "pingpong"), `phase` (0: all together .. 1: each its own), `enabled`, `sway`. Studio shows the room's own;
  per-asset settings are for the ops and AI (one call).
- **2D tilemaps:** unchanged (see Limitations).

## Part E: Weather and wind

The five demonstrations (`wind_*.webp`):

- **Calm:** plants barely stir; banners hang; torches flicker.
- **Breeze:** a gentle lean and flutter.
- **Strong:** grass and reeds well over, the canopy rocking.
- **Gusts:** slow swells with quick gusts crossing the meadow (fronts measured stepping west to east, about 0.15 s a
  metre).
- **Rain with wind:** rain slants the way the grass leans, the banner streams and the flame bends (`rain_wind`: the
  rain's wind was the room's, -7.7, -2.1 m/s).

Frame-rate independence: the clock is the sum of the frames' steps (test: 30, 60 and 144 frames a second for ten
seconds give the same clock to 1e-9 s), and everything is a function of the clock. Precipitation physics and
collision are unchanged.

## Part F: A small tree

`tree_small`: a Blender trunk (headless; tapering, three short limbs inside the canopy, a wall collider, casts) and
four billboard canopy clusters (sway with lag, cast swaying shadows, their light taken 1.2 m toward the sun).

| Approach (`trees_compared.webp`, left to right) | Looks | Moves | Shadows | Under a turning camera |
|---|---|---|---|---|
| All camera-facing planes (trunk sprite + canopy) | pixel art throughout | canopy sways; the trunk can't be 3D | canopy only | a cardboard cut-out: the trunk turns with the view |
| Layered geometry (trunk + low-poly leaf lumps, 3D) | faceted, smooth-shaded: clashes with the pixel-art kit at every angle | still (or the whole mesh sways) | full | solid |
| **3D trunk + animated canopy (shipped)** | pixel-art leaves on a solid trunk | canopy sways, trunk stands | trunk and swaying canopy | trunk solid, canopy clusters keep their places round it |

Art QA chose the shipped one. The brush keeps a tree's canopy (1.1 m) clear of structures and doorways (a canopy
used to cut into the staircase). No forest generator.

## Part G: Studio

**Wind and motion** in the 3D view's panel (`studio_panel.webp`):

| Step (`studio.json`) | Result |
|---|---|
| Breeze (preset button) | one undo step; "Breeze: 3 m/s toward 0 degrees, gusts 0.3." (reloads the room: its rain falls in the wind) |
| Animation on | one undo step, in place (uniforms; no reload): 0.31 s with the panel's rebuild (was 0.65 s with a reload) |
| Live preview | the view moves while editing (3 s of clock in 180 frames); off, it is still |
| Sway 1.6, toward 200 typed | one undo step each |
| "fast" typed | "Type a number."; nothing changed |
| Undo, redo, save, reopen | as typed; the scatter itself untouched |
| Change review | "hills: wind 3 m/s toward 200 degrees, gusts 0.3", "hills: decoration animation on (sway 1.6)" |

Reused: the ops (`set_wind`, `set_motion`), undo/redo, the change review. No animation editor.

## Part H: Performance and QA

### Performance (`scale.json`, `baseline_*.json`; run alone)

Rooms 64 x 64 m with 100, 1,000 and 10,000 instances (mostly swaying plants, 1 % torches, banners and trees) and
128 x 128 m with 10,000, shadows on, gameplay camera, after 600 frames' warm-up; still and moving alternated three
times. GPU time is each scatter pass timed alone (a timer query round 20 draws of it: a query round a whole frame
also counts the GPU waiting on Python).

| Room | Sprite pass GPU, still / moving (ms) | Canopy shadow pass (ms) | Frame wall time, moving minus still (ms) | Draw calls / shadow draws | GPU memory | Over 600 moving frames |
|---|---|---|---|---|---|---|
| 64 m, 100 | 0.008 / 0.009 | 0.001 | +0.03 | 48 / 20 | 0.44 MB | 0 rebuilt, +0 bytes |
| 64 m, 1,000 | 0.09 / 0.22 | 0.003 | +0.19 | 71 / 24 | 0.90 MB | 0 rebuilt, +0 bytes |
| 64 m, 10,000 | 0.26 / 0.38 | 0.016 | -0.09 | 104 / 24 | 5.66 MB | 0 rebuilt, +0 bytes |
| 128 m, 10,000 | 0.40 / 0.69 | 0.007 | +0.05 | 146 / 48 | 5.66 MB | 0 rebuilt, +0 bytes |

- **What motion costs:** at most 0.3 ms of GPU for 10,000 moving instances; the frame's wall time doesn't change
  measurably. A frame sets about 30 uniforms (two programs); nothing is rebuilt or uploaded.
- **What 20E costs a room that doesn't move** (20D's own mix, no motion settings, here and on `1d2501d`):

  | Room | Sprite pass GPU, 20D / 20E (ms) | Draw calls | GPU memory, 20D / 20E |
  |---|---|---|---|
  | 64 m, 10,000 | 0.15 / 0.11 | 108 / 108 | 5.79 / 6.32 MB |
  | 128 m, 10,000 | 0.17 / 0.22 | 151 / 151 | 5.79 / 6.32 MB |

  The same within the timer's noise; +0.5 MB (two more floats a vertex, the second sheet). The first build of 20E
  doubled the still room's sprite pass (its single program ran the wind's vertex work even when off); now a still room
  draws with a still program.
- **Shadows:** canopies cast one draw per 32 m block (one per chunk at first: 69 shadow draws at 64 m, now 24).
- **Lifecycle:** GPU objects identical over reloads; everything freed on release (every room).
- **Load:** unchanged in kind (0.49-1.27 s, as 20D's).

### QA

Three independent reviews, then fixes, then an Art recheck.

| Review | First verdict | What it found (all fixed) | After |
|---|---|---|---|
| Art and animation | ACCEPT WITH FIXES | plants squashed or stretched when the wind blew along the view; the flame swapping behind its cup; a banner flapping in dead calm; gusts not reading as waves; the dripping rock off-style; a tree's canopy in the staircase, a limb below it, a dark blob in it; glowcaps too bright by day; thin flame art; evidence gaps | **ACCEPT** (recheck: 1-8 fixed, polish listed under Limitations) |
| Rendering and compatibility | PASS WITH FIXES | distant trees lost their canopies but kept their shadows; a bad `settings.wind` switched the rain off; the clock's wrap not seamless at Speed other than 1; banners streaming the wrong way in Studio's turned view; `mod` precision on some GPUs; the culling margin ignoring the camera's stretch; a log message that didn't match; a program leak if the second failed to compile | fixed, each with a test or a measurement |
| Performance | PASS WITH FIXES | warm-up too short; the whole-frame GPU query invalid; "still" was 20E with motion off, not 20D; every Studio motion edit reloaded the room; "frame ms" was wall time | method rebuilt (above), a 20D baseline, in-place Studio edits; and the still-room cost it led to (the two programs) |

## Tests and gates

| Gate | Result |
|---|---|
| `tests/test_motion.py` (fast) | 16 passed: wind settings and gust fronts (bounded, travelling, seamless at the wrap); particles take the room's wind only without their own, a calm room as before, a bad wind keeps the rain; motion settings (strict, lenient); a plant still when off, never into the ground; leaning as the camera sees it; neighbours out of step, grass more than the tree, the tree later; frames loop and ping-pong; the wrap seamless at any Speed; the clock at 30/60/144 fps; the motion tables and per-asset settings; every part's frames in the sheets; the ops and their words; a tree's canopy clear of structures |
| `tests/test_motion_gpu.py` | 2 passed: moving without a rebuild or growth, still when off, the tree blocks, reloads leave nothing; a reed turns about its foot |
| Identity | 24 pictures, 0 pixels different from `1d2501d` |
| Fast tier | 4,814 passed |
| GPU suites (every MESH_GL_SMOKE file, water, weather collisions) | 206 passed (21 min) |
| Ruff gate | ok |
| mypy (fresh) | 73 (the baseline) |
| Linux / Windows CI | CI_RESULT |

## Known limitations

- **2D tilemaps don't animate.** Animated decoration is HD-2D scatter; a 2D map's tiles (and Tiled's tile
  animations) are drawn as before. The frame tables would serve a 2D tile layer later.
- **Wind along the view looks calm.** With the depth lean capped (so plants are never squashed on screen), a wind
  blowing straight toward or away from the camera shows mostly flutter.
- **One streaming pose for the banner** (a limp one for still air); a light wind streams it as fully as a strong one,
  only slower.
- **A tree's trunk can show through** a gap as its canopy sways off it in a strong gust.
- **Quick gusts are small** (about 5 degrees); the slow swell carries most of the read.
- **A torch doesn't light its surroundings:** place a lamp beside it.
- **Rain's gusts are its own:** a raindrop's gust is per drop (precipitation physics unchanged); its direction and
  strength are the room's.
- **Lamp shadows** come from trunks, not canopies.
- **Studio's wind edits reload the room** (its rain falls in the wind): about half a second; motion edits don't.
- **No time of day** in the study: the glow at night is shown by the shader's floor, not filmed.

## Verdict

**PASS.** A room has one wind that its weather and its decoration share; its plants, torches, banners and a small
tree move on the GPU with no per-frame rebuilds, at no measurable cost to a room that doesn't move and at most
0.3 ms of GPU for 10,000 moving instances; rooms made before 20E draw exactly as before; Studio sets it with one undo
step a change and previews it live. Art, Rendering and Performance QA's findings are fixed; Art's recheck accepts.

Stop for owner review: not merged.

## Next checkpoint: the Lakeside Village

A composed scene (cottages, a jetty, the pond, meadows and a tree line, torches and banners, a breeze, dusk) to judge
how terrain, water, weather, scatter and motion hold together. Propose terrain work only for a concrete deficiency it
shows.

## Reproduce

```
py -3.13 tooling/m20e_motion_study.py identity OUT   # run here and in a checkout of 1d2501d: the same pictures
py -3.13 tooling/m20e_motion_study.py scale OUT      # alone: timings
py -3.13 tooling/m20e_motion_study.py baseline OUT   # here and on 1d2501d: what 20E costs a room that doesn't move
py -3.13 tooling/m20e_motion_study.py winds OUT
py -3.13 tooling/m20e_motion_study.py gameplay OUT
py -3.13 tooling/m20e_motion_study.py trees OUT      # its own process (registers two comparison trees)
py -3.13 tooling/m20e_motion_study.py studio OUT
blender --factory-startup -noaudio --background --python tooling/hd2d_assets/build_scatter_models.py -- OUT_DIR
py -3.13 tooling/hd2d_assets/scatter_art.py
```
