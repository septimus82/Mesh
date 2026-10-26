# Milestone 19B: water presentation (water that belongs to its place)

- **Branch:** `feature/m19b-water-presentation`.
- **Draft PR:** [#383](https://github.com/septimus82/Mesh/pull/383), into `redesign/visual-editor`.
- **Builds on:** Stage 19A (#382, merged as `438b509`): puddles and ponds, one batched water pass.
- **Not in this stage:** rivers, waterfalls, swimming, flooding, thunderstorms, fluid simulation, terrain sculpting,
  path or river editors.

**Verdict: PASS** (details at the end).

## What changed for a creator

- **Three new presets**, procedural (no PixelLab or other new assets):

  | Preset | Default size | Look |
  |---|---|---|
  | Muddy puddle | 72 × 44 px | an irregular outline; brown-grey shallow water over the ground it lies on; a ring of wet ground (on a path: wet path; on grass: wet earth) with a pebble here and there; a sky-like mirror |
  | Natural pond | 224 × 150 px | an irregular outline; a grassy earth bank with reeds; clear shallows where the ground shows through, deep blue-green in the middle; the far bank's side visible, so the water sits in the ground |
  | Stone pool | 160 × 112 px | a rectangle with rounded corners; a rim of whole stones lit on their sunward side; stone courses on the far side; steep, quickly deep |

- **Stage 19A's Puddle and Pond** are now named "Simple puddle" and "Simple pond". They keep their look exactly, so
  older rooms don't change (proof below), and they serve as the negative controls.
- **A new Water object starts as a muddy puddle**; one click turns it into a natural pond or stone pool.
- **The Look tab** (every change one checked edit through `project_ops.set_water`: undo, redo, save, reopen):

  | Control | What it does |
  |---|---|
  | Muddy puddle / Natural pond / Stone pool, Simple puddle / Simple pond | The preset |
  | Width / height | Size in px |
  | Round / Square / Natural | The shape; Natural is irregular |
  | Turn (°), −15 / +15 | Rotation (as structures turn in the 3D view) |
  | New natural outline | Another irregular outline (its `seed`) |
  | No bank / Mud / Grass / Stone, bank width | The shoreline treatment and how far it reaches |
  | Depth | How soon it turns from shallow to deep away from its edge |
  | Shallow / deep colour, opacity | Its colours and how see-through it is |
  | Waves / reflection, ripples | Movement, mirror strength, how strongly rain and footsteps ring it |
  | Rippled by rain, Walk through it, Step sound | As in Stage 19A |
  | Mirrors in this room: Full / Half size / Sky only | The room's reflection cost (all its water) |

  The bank, depth, deep colour and ripple strength belong to the three new presets; a simple puddle or pond refuses
  them with a message naming the presets that have them.
- **On a 2D room's map:** the blue outline follows the real (turned, irregular) edge; its corner sizes it in its own
  frame; a new handle beyond its top turns it (in 5° steps).
- **In the 3D view:** click it to select it, drag it to move it; size and turn it in the inspector.
- **AI authoring** uses the same operations: `set_water` gains `rotation`, `seed`, `shore`, `shore_width`,
  `deep_colour`, `depth` and `ripples`, and `set_water_reflections` sets the room's mirrors. The review card says, for
  example, "adds 'Pool' (stone pool water 160 x 112)", "'Pool' water shore: (none) -> 'grass'" or "water reflections
  full -> half".

## 1. The visual problems, studied

All pictures come from the game's own camera at its window size (1280 × 720), cropped 1:1 and never scaled. At this
camera one texel of the art (1/32 m) spans **1.96 screen pixels** at the water, the scale everything below was judged
at. Each comparison shows Stage 19A's water and Stage 19B's at the same place, camera and moment
(`m19b_water_study.py comparisons`), dry and in rain: `compare_pond_*.png`, `compare_puddle_*.png`,
`compare_stone_pool_*.png`.

| Problem in Stage 19A | Cause | Stage 19B |
|---|---|---|
| Flat, elliptical ponds | A perfect ellipse or rectangle | A natural outline: a few low harmonics a seed picks, fitted inside the size's ellipse; any shape can be turned |
| Laid over the grass, not set into it | A uniform light rim all round, one flat tint and no ground edge: a sticker | Clear shallows show the ground beneath; a bank round the edge; the far bank's side seen above the water with its shadow on it, as when water lies a little below the ground; a waterline only on the near edge |
| Puddles like blue decals | A pale blue-grey tint with a soft rim | Brown-grey shallow water, a ring of wet ground that darkens whatever it lies on (path or grass), a ragged per-texel edge, pebbles |
| Reflections overpower the water | A strong mirror (Fresnel 0.85 to 0.35) of everything the ray met, however far | The mirror takes the water's hue, stays under its colour (strongest where deep) and fades to the sky for what stands beyond about 1.2 to 3.5 m. Measured on the same pond and frame, the mirror changes the water by **7.2** levels on average (19A: **15.2**), and **0%** of its pixels by more than 24 (19A: **58%**) |
| Hard or soft transitions to paths and terrain | A soft alpha ramp at the edge, the same on any ground | The bank blends by darkening what lies under it, so the same puddle reads as wet path on a path and wet earth on grass; edges are crisp per texel |
| Smooth, not pixel art | Soft gradients at the rim | Everything is worked out per texel and quantised to flat shades: banks, stones, reeds, the waterline and slow glints are whole texels |

Stage 19A's water is preserved as the negative control: its presets are kept and drawn by their own shader path.

## 2. Shorelines and materials

One fragment shader draws water and bank together, in the same instanced draw (the quad grows by the bank's width).
A signed distance to the edge picks what each texel is. It is in metres: exact for the rounded rectangle, and taken
along the ray from the centre for the ellipse and the natural outline.

- **The bank** (outside the edge, within its width):
  - **Mud:** wet ground in two crisp bands, darkest at the water, drawn as a darkening so it suits any ground, with a
    pebble here and there.
  - **Grass:** an earth lip at the water, then clumps of two or three reed blades rising from their foot (a stroke
    north on the ground stands up on screen), on slightly damp grass.
  - **Stone:** a rim of whole stones from a jittered cell grid (about 0.26 m). A stone is drawn only if its centre
    lies on the bank, so the rim's inner and outer edges are made of stones, each with mortar round it, lit lighter
    on its sunward side and darker away from it.
- **The recess:** the water is taken to lie a little below the ground (mud 3 cm, grass 9 cm, stone 14 cm).
  - For a water texel the view ray is followed down to the water's level. If it would leave the water first, the far
    bank's side is what is seen there: earth, darker and wetter towards the water, or stone courses. Just short of it,
    its shadow darkens the water.
  - This is what makes water read as set into the ground. It costs no geometry and doesn't touch the terrain.
- **The water:**
  - **Colour:** its shallow colour at the edge, where it is see-through (45% of its opacity, so the ground shows),
    turning to its deep colour as soon as its depth says.
  - **Light:** lit by the room (sun, lamps, shadows), as in Stage 19A.
  - **Rings:** rain and footstep rings, times its ripple strength.
  - **Waterline:** a crisp light line on the near edge only.
  - **Glints:** short light dashes drifting over deep water, as many as its waves.
- **Reusable across environments:** the bank and recess are settings, not terrain edits, so the same pond suits a
  meadow, a path or a courtyard. A pond can sit against a cliff or on a plateau unchanged (section 6).

### A recessed basin built in Blender

When a pond needs a real basin (a fountain, a trough, a stone tank, a sunken garden pool), build the basin as a
structure:

1. **Model** the rim and the inside in Blender, exported as glTF binary like every structure (`engine/hd2d/glb.py`).
   Give the rim a `mesh_collision` object of kind `"wall"` if it should stop characters, or `"solid"` if they can
   stand on it.
2. **Place** it as a structure (`settings.hd2d.structures`, or Studio's Models...), noting its x, y and rotation.
3. **Place a Water object** at the same x and y. Set its elevation to the water level in px: below the rim's top,
   above the basin's floor.
4. **Match it to the basin:** the same rotation, and a shape and size just inside the rim, a few px under it so the
   edge hides beneath the rim. Choose No bank (the model is the bank). The Stone pool's depth and colours suit it.
5. **Choose walkability:** set Walk through it off if the rim doesn't already block.

Mesh's ground is one flat textured plane, so a basin can't be cut below it. Lower water has two options:

- **The 19B recess** (above), which suits most ponds.
- **A raised terrain piece:** model the surroundings as a `"solid"` structure with the hollow in it, and put the water
  level between the plane and its top.

No terrain sculpting was added in this stage.

## 3. Shape controls

- **Shapes:** `shape` is "ellipse", "rect" or "natural".
  - Natural is `outline()`: radius `c0 + Σ aₖ cos(kθ + φₖ)` for k = 2 to 5.
  - The amplitudes and phases come from its `seed` (1–9999). They are worked out once per seed and cached.
  - The outline is scaled to fit the ellipse its width and height make, so those still mean its size.
- **Rotation:** `rotation` (degrees) turns any shape.
- **What is walked through is what is drawn:** footsteps (`inside`), Studio's outline (`outline_points`) and 3D
  picking use the same outline as the shader. A test walks the drawn edge for turned natural, rectangle and ellipse
  water: 3% inside counts, 3% outside doesn't.
- **Blocking:** a pond that blocks is solid with a box collider: the box round its outline as turned (`extent`). For
  an unturned round pond that is Stage 19A's box.
- **Compatibility:** Round and Square are unchanged, and the simple presets' outlines are exactly Stage 19A's.
- **Not built:** no path editor and no river system.

## 4. Artistic controls

- **Surface colour and transparency:** shallow colour, deep colour, opacity.
- **Shallow against deep:** depth (0: shallow throughout, 1: deep a few texels in).
- **Reflection intensity:** reflection 0–1 (`reflection.png`: 0, the natural pond's 0.3 and 0.8; the player on the
  far bank appears in it at 0.8).
- **Wave and ripple strength:** waves (movement and glints) and ripples. Measured on the natural pond in rain, the
  rings change its picture by 258k at 1.0, 128k at 0.5 and 0 at 0 (summed per channel; the rings are lit by the
  room, so they don't glow at night).
- **Shoreline treatment:** No bank, Mud, Grass or Stone, and the bank's width.
- **Rain interaction:** Rippled by rain, the ripple strength, and the shelter (Stage 18B's map, as in 19A).
- **Pixel art kept:** all of it is per texel and quantised to flat shades.
- **Procedural only:** no PixelLab calls were made. New PixelLab textures (bank, stone) remain possible later through
  the owner's integration, subject to approval and licence clearance.

## 5. Performance and compatibility

**Still one batched water pass:** all water and its banks are one instanced draw (+1 draw call), as in Stage 19A.

### Reflection settings (the room's `settings.hd2d.water_reflections`)

| Setting | What it mirrors | Frame copy memory at 720p / 1080p / 4K |
|---|---|---|
| Full (default; older rooms) | What stands above the water, from a full-size copy of the frame | 7.4 / 16.6 / 66.4 MB |
| Half size | The same, from a half-size copy (scaled blit, nearest) | 1.8 / 4.1 / 16.6 MB |
| Sky only | The sky's colour; no copy is kept | 0 |

Half size looks almost the same as full: rendering QA measured 236 px of difference on the pond and 143 px on the stone
pool. Sky only differs by about 2,000 px, where reflections of nearby things are lost.

### Measured cost (RTX 4070, OpenGL 4.6, hidden windows; `m19b_water_study.py perf`)

The village in rain (4,000 drops) with the natural pond, the stone pool and two muddy puddles, the camera on the
natural pond. Per resolution one game:
- 300 drawn warm-up frames, then 5 rounds, each measuring all three settings in turn, so all three see the same GPU
  clocks.
- The water pass's GPU time is a timer query round it (its frame copy included); medians, with the range over rounds.

| | Full | Half size | Sky only |
|---|---|---|---|
| 720p | 0.36 ms (0.19–0.51) | 0.19 ms (0.16–0.26) | 0.11 ms (0.08–0.15) |
| 1080p | 0.19 ms (0.10–0.23) | 0.15 ms (0.08–0.18) | 0.08 ms (0.04–0.10) |
| 4K | 0.52 ms (0.35–0.53) | 0.23 ms (0.18–0.23) | 0.13 ms (0.10–0.13) |

- **GPU clocks move between runs**, so differences under about 0.1 ms are noise. The ordering is stable: sky is
  cheapest, then half, then full, and full grows with resolution because of the copy. Performance QA measured the
  same independently (4K: 0.52 / 0.23 / 0.14 ms).
- **CPU, the water step per frame:** 0.23–0.63 ms. Most of it is the fixed lighting bind that Stage 19A has too;
  natural outlines are worked out once per seed. With 50 water objects the per-object layout costs about 3 µs each.
- **Water filling the screen** (performance QA on the final code, 4K, 60% of the picture water; two runs):

  | | Full | Sky only |
  |---|---|---|
  | Stage 19A's pond | 0.96 ms | 0.59 ms |
  | Natural pond | 1.14–1.43 ms | 0.86–0.90 ms |
  | Muddy puddle | 1.14–1.15 ms | 0.77–0.90 ms |
  | Stone pool | 1.03–1.07 ms | 0.65–0.67 ms |

  The new material costs up to about 1.4 ms with full reflections and 0.9 ms with sky only. Skipping the stone lookup
  in deep water made the stone pool 17% cheaper; the even-bank distance added 0.12–0.15 ms on ellipse and natural
  water.
- **Worst case** (performance QA): 42 pools whose 64 px banks cover about 62% of a 4K screen cost up to 1.9 ms full
  and 1.4 ms sky (stone pools; Stage 19A's ponds in the same layout: 0.45 and 0.18 ms). This is fine on this GPU and
  could be several milliseconds on modest hardware. Such rooms should use Half size or Sky only and narrower banks.

### GPU lifecycle (GL objects after `ctx.gc()`)

| Case | Result |
|---|---|
| 10 room changes (village ↔ cottage) | 125 buffers, 47 textures, 8 framebuffers, 30 programs before and after |
| Reflection settings switched 9 times (full → half → sky ×3) | The same counts; the water's memory 7.37 MB, 1.84 MB, 416 bytes |
| Studio: 10 water edits, 3 reflection changes | 48 textures, 9 framebuffers, 31 programs throughout |
| Studio: 5, then 10 Play/Stop | 49 / 10 / 32 after the first Play (the game's own objects, made once, as in Stage 19A), unchanged after 10 |

Performance QA also verified:
- **Memory:** actual video memory freed (from the NVIDIA driver) matches the reported sizes, and 60 setting switches
  and window resizes (including odd sizes) leave nothing behind.
- **Failure paths:** a refused blit, a real `GL_INVALID_OPERATION`, a shader that won't compile and a failed copy
  allocation each turn the room's water off with the reason kept and free exactly its objects. The frame then matches
  one without water, and reloading brings the water back.
- **GL state:** after the half-size blit it is as arcade expects. Pixels outside the water are identical in all three
  settings.

## 6. Acceptance demonstration

Real Mesh renders from hidden windows: the game's camera at 1280 × 720, cropped 1:1. All files are in
`milestone19_stage2_water_presentation_evidence/`.

| # | What | Files |
|---|---|---|
| 1 | Stage 19A's pond beside a natural pond in one picture; and the same place with each | `both_ponds_dry.png`, `both_ponds_rain.png`, `compare_pond_dry.png`, `compare_pond_rain.png` |
| 2 | Muddy puddles on the path (one turned, half on its edge), against Stage 19A's puddle | `puddles_dry.png`, `puddles_rain.png`, `compare_puddle_*.png` |
| 3 | The stone-lined pool | `stone_pool_dry.png`, `stone_pool_rain.png`, `compare_stone_pool_*.png` |
| 4 | Dry and rainy versions | every `_dry` / `_rain` pair; `natural_pond_dry.png`, `natural_pond_rain.png` |
| 5 | Camera movement and reflections | `pond_pan.webp` (a 4 m pan over the natural pond, the player on its far bank, its waves moving; 1:1), `reflection.png` |
| 6 | Studio placement and adjustment | `studio_1_placed.png`, `studio_2_adjusted.png` |
| – | Places (a roof, a cliff, a plateau), a 2D room, long and narrow shapes | `place_roof.png`, `place_cliff.png`, `place_plateau.png`, `two_d_water.png`, `long_shapes.png` |

### Places (`m19b_water_study.py places`)

| Place | Result |
|---|---|
| Near roofs | The natural pond by the bridge draws 40,915 px. A further 4,986 px are hidden behind the shop's roof, counted with its depth test off |
| Beside a terrain edge | A pond whose far side runs into the west plateau's cliff ends cleanly against it. 2,778 px of it lie inside the plateau and are hidden there |
| On an elevated floor | A muddy puddle at the east plateau's top (2 m) draws 4,309 px; the 1,349 hidden are where the Elder stands in it. The same puddle at 0 m is inside the plateau: 0 px drawn, 9,461 hidden |
| Beneath the bridge | Rain rings a muddy puddle on the open path (601–1,107 ripple pixels a frame). Under the deck it gets 70–82, against 516–662 with its shelter switched off (the negative control), an 87% reduction. As in 19A, judged with its depth test off |

### Gameplay kept (`gameplay`, `two_d`)

| Check | Result |
|---|---|
| Footsteps | Walking the path through the muddy puddle: 4 steps, 4 `water_step` events |
| Walkable | Through a natural pond turned 30°: the player reaches its middle (18.54 m) |
| Blocking | The same pond set not walkable stops the player at 16.07 m, at the south edge of the box round its turned outline (16.26 m) |
| Rain ripples | Ring strength as set (section 4); sheltered water stays calm (Places) |
| 2D room | A muddy puddle under the player, a natural pond and a stone pool, in rain: 53,192 water pixels, 0 of the player's pixels changed by it |

### Studio (`studio`; Mesh Studio's own buttons, fields and keys in a hidden window)

| Step | Result |
|---|---|
| Water, then click the ground in the 3D view | A muddy puddle (natural shape, mud bank) |
| Natural pond; width 200, height 128; +15 twice; New natural outline | `natural_pond`, 200 × 128, turned 30°, seed 8, grass bank |
| Stone bank; depth 0.8; deep colour #16324a | All three set |
| Mirrors in this room: Half size | `settings.hd2d.water_reflections` = "half" |
| Drawn and moving in the editing view | 27,034 px change between frames |
| Ctrl+Z twice, Ctrl+Y twice | The reflections back to full and the deep colour back to the preset's, then both restored |
| Click it in the 3D view | It is selected |
| Ctrl+S, then reopen | Saved, and reopened identical (every setting) |
| F4 and F4 | Play with 1 water surface at half-size reflections; back to editing |

### Compatibility

- **Stage 19A's water is pixel-identical to the base (`438b509`).** The m19 study village (puddle and pond) was
  rendered with the base tree and with this branch at two fixed moments, dry and in rain: 0 of 921,600 pixels differ
  in each of the 8 HD-2D pictures. A 2D room (round puddle, square pond) shows 0 of 518,400 pixels different.
- **Saves:** older water keeps every setting; the new keys are optional and default to the preset's. A room without
  `water_reflections` mirrors as before (full).
- **Existing tests updated for the renames:** a Studio test now clicks "Simple pond", and a newly placed Water is a
  muddy puddle.

## 7. QA and gates

Local results (Windows), on the final code:

| Gate | Result |
|---|---|
| Fast tier | 4,696 passed |
| GPU suites (`MESH_GL_SMOKE=1`): water (19A and 19B), weather | 28 passed |
| Fast water tests (`test_water.py`, `test_water_presentation.py`) | 45 passed |
| ruff gate | ok |
| Generated docs verify | passed (`docs/behaviours.md` regenerated) |

- **mypy gate:** no new errors; the two known local `tooling/hd2d_lab` numpy errors are also on the base.
- **Linux and Windows CI:** see #383.

### Independent QA (Opus, hidden windows, real in-engine output)

Each reviewer first gave its verdict on `3d89435`. Their findings were fixed in `ba44745`, and each re-checked them
there: **all three now give PASS.**

**Rendering** (first CONDITIONAL PASS).
- **Major, fixed: long, narrow water.** The edge distance was only right along the shape's axes. At 320 × 48 the bank
  thinned to 3.5 px and a bow-tie seam split the deep middle. It is now the implicit edge over its gradient, with the
  inside bounded by the short half-axis. Re-checked: the bank never falls below about its width on 15 shapes (mean
  error 0.05–0.63 px), six seeds draw 12.8–14.9 px, and the seam is gone (`long_shapes.png`).
- **Minor, fixed:**
  - Turned rectangles were culled while still partly on screen (2,950 px lost); now 0.
  - Rain rings glowed at night (up to 252); they are now lit by the room (pixels brightened over 60 fell from 2,374
    to 81).
- **Nit, fixed:** outer stones were clipped flat; they are now drawn whole. Skipping the stone lookup in deep water
  changes 0 px in 10 cases.
- **Verified:** Stage 19A's look pixel-identical to base (9 of 9 images, 0 px); the recess correct at camera yaw 0, 45,
  90 and 180; roofs, lamp posts and cliffs hide banks correctly; pixel-grid stability while panning; half against
  full differs by only 143–236 px; extreme sizes and settings render; shadows and lamps fall on banks; 2D rooms.
- **Nits kept (Known limits):** reeds also grow on paths, stones cover a texel of feet, banding in dark rooms, and the
  bank widening at the tips of very long shapes.
- **Pre-existing, not 19B:** at camera yaw 180 something unseen hides the near half of a pond, as on the base with
  Stage 19A's pond. Recorded for a later look.

**Performance** (PASS).
- **Verified:** the costs above at three resolutions and all three settings; memory against the driver's own figures;
  no leaks over setting switches, resizes, room changes, Studio edits and Play/Stop; four failure paths turning water
  off cleanly and coming back on reload; GL state after the half-size blit.
- **Its suggestions, done:**
  - The worst-case costs are now published.
  - The stone lookup is skipped in deep water: 17% cheaper.
  - The frame copy is freed while no water is there: 66 MB to 416 bytes at 4K.
- **Re-checked:** the even-bank distance adds 0.12–0.15 ms on ellipse and natural water filling a 4K screen. No
  regressions.

**Compatibility** (first CONDITIONAL PASS).
- **Majors, fixed:**
  - The AI's operation list had lost `set_water`'s presets and settings: its docstring's first paragraph is what AI
    reads. Now 1,227 characters naming all 5 presets and 21 settings.
  - A blocking turned or natural pond stopped the player up to 2.3 m short of the water: its box was the turned
    rectangle's. Now the box round its outline: gaps of 0.6–0.8 m on natural shapes from the south and 6–11 px from
    the west. Stage 19A's unturned ponds keep their exact box.
- **Minor, fixed:** a 2D click inside a turned pond's box but off the water picked the pond. It now picks what is
  there (the bank still counts).
- **Nits, fixed:** typing −1 now says it can't be negative; the behaviour's preset description.
- **Verified:**
  - Rooms saved by Stage 19A open and save byte-identical in Studio.
  - All 30 inspector edits undo and redo exactly, save and reopen, and invalid entries are refused.
  - Preset switches keep size, turn and walkability.
  - 2D handles, 3D picking, footsteps inside what is drawn (0.98 overlap), rain shelter, Show-when flags.
  - AI operations in HD-2D and 2D projects.
  - 4,696 fast and 102 related GPU tests.

## Known limits

- **Blocking is a box.** A blocking pond blocks the box round its outline as turned, so beside its curves (and most at
  45°) the box reaches past the water, as Stage 19A's ellipses did. A polygon collider would follow the outline.
- **3D-view sizing and turning go through the inspector.** The 3D view has no drag handles for them, as for
  structures; 2D maps have both.
- **A natural outline is radial.** It suits ponds and puddles, not long winding shapes (rivers are a later stage).
- **The recess is drawn, not built.** The far bank's side is shaded per texel at the bank's depth. A real hollow needs
  a modelled basin (section 2).
- **Reeds are flat.** They are strokes on the ground that read as standing at the gameplay camera; they don't sway,
  and they grow wherever the bank is, a path included.
- **Small rendering nits** (rendering QA):
  - A stone rim, drawn 3.5 cm above the ground, covers a texel of a character's soles.
  - Dark rooms show the 24-shade banding.
  - At the tips of very long shapes (8:1 and beyond) the bank widens.
- **Worst-case cost on modest GPUs.** Many large banks filling a 4K screen cost up to 1.9 ms on an RTX 4070; on
  modest hardware use Half size or Sky only and narrower banks.

## Verdict

**PASS.**

- **Integrated, not laid on top.** Puddles and ponds now belong to their surroundings at the gameplay camera and pixel
  scale:
  - irregular outlines and turns;
  - mud, grass-and-reed or stone banks;
  - see-through shallows deepening to a deep colour;
  - the far bank's side, which sets the water into the ground;
  - a calmer mirror that no longer overpowers the water (on average half the change, and none of its pixels moved by
    more than 24 levels, where Stage 19A moved 58%).
- **The proven renderer kept.** All of it is one instanced draw on Stage 19A's renderer, procedural, with no terrain
  changes. Stage 19A's own water renders exactly as before, as the negative control.
- **Authoring.** Creators shape, turn, bank and colour water in Studio's inspector (and on 2D maps with handles), with
  undo, redo, save and reopen; AI uses the same checked operations.
- **Cost.** About 0.1–0.5 ms of GPU in a village view on an RTX 4070, up to about 1.4 ms with water filling a 4K
  screen. A room can choose half-size or sky-only reflections, which cut the frame copy's memory to a quarter or to
  nothing.
- **Gameplay and lifecycle kept.** Footsteps, blocking, rain ripples and shelter, Show-when flags and 2D rooms work,
  and GPU objects stay level across loads, edits, setting switches and Play/Stop.
- **Independent QA.** All three reviewers pass it after their findings were fixed.

Stage 19B stops here for owner review. No rivers, waterfalls, swimming, flooding or thunderstorms have been started.
