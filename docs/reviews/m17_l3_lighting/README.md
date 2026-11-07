# M17-L3 Stage 1: HD-2D lighting correctness (investigation and scratch prototypes; evidence only, never merged)

**Base:** `redesign/visual-editor` at `18520c3` (M17-L2 merged).

**Scenes:** every frame and number comes from a hidden window, using a **scratch copy** of the installed L1b
`D:\Games\Lakeside Village`. All 67 files were hash-verified before and after copying, and the source was never
written. The scenes:
- **Lakeside:** four kit lamp posts. The L1b scene ships their lights *off*; the scratch variants turn them on.
- **Village:** the template's two lamp posts.
- **Cottage interior:** one lamp, with walls round it.

The variants were made with `project_ops.set_hd2d_sun` (noon / evening / night, as Studio's buttons do), with two
controls each:
- `noshadow`: every lamp has `"shadows": false`.
- `roomoff`: `settings.hd2d.shadows` is false.

**Prototypes:** patched into the running process only (`scripts/protos.py`); no engine file was changed. The
interior, L1b composition, generator, CI thresholds and timing policies are untouched.

## Answers in brief

| # | Defect as reported | Finding at 18520c3 | Class |
|---|---|---|---|
| 1 | Shadow-enabled lamps darken their own light | **Correctly placed lamps do not** (#459 holds everywhere measured). **Near-miss lamps do:** a light 25–30 cm off its lantern centre, or just above its cap, loses 28–99 % of its pool to its own lamp head. **Cause:** #459's fixture match needs the light *inside* a part box (±1 cm). | **Correctness: C1** |
| 2 | Pool intensity differs between shadow-enabled and shadow-disabled lamps | For correctly placed lamps the pools are **identical**: energy ratio 1.000; frame pool luminance equal to 0.1 at noon, evening and night. Differences come only from (a) C1 near-misses, (b) **lamps 3+ ignoring "Casts shadows"** (MAX_SHADOW_LIGHTS = 2): they shine through walls, and Lakeside lamp 4 lights 253 of 253 points that walls should block, and (c) real occluders (the cottage table: −15 %, CPU-confirmed). | **Correctness: C2** |
| 3 | Lamp materials have no visible emission | **No emissive path exists:** `glb.py` drops glTF `emissiveFactor` (and `KHR_materials_emissive_strength`, as a "harmless" extension); `MESH_FS` has no emissive term; the kit's `lantern` material has no emission. Lamp heads read 12 luminance at night. **Both prototypes glow without bloom:** heads reach 43–56, and only lamp-head pixels change. | **Correctness: C4** (material import); **glow: optional O1** |
| 6 | Studio controls that don't match the renderer | **9 of the 14 lighting-panel controls do nothing in an HD-2D room.** The HD-2D frame bypasses the 2D lighting compositor entirely (`game_runtime/tick.py:146`). Table below. | **Correctness: C3** |

**Performance:**
- **Village and cottage:** every prototype is within ±0.02 ms of base.
- **Four shadow lamps (F2):** +0.4–0.9 ms in Lakeside, where two more lamps sample a map.
- **Lamp-driven glow (E2):** +0.6 ms in one Lakeside view and none in the other. Inconclusive on unlocked clocks;
  re-measure before implementing.
- **Reach rule (F1):** works at load time only, so no per-frame cost.
- **glTF emissive (E1) and the distance bias (F3):** no measurable change.

Details are in §5.

## 1. Point-light and shadow pipeline (traced)

- **Lamps** come from the scene's `lights` (`settings.parse_scene_lights`). It keeps the first 8 enabled lamps
  (MAX_LIGHTS), and only the first **2** that ask for shadows get a shadow map (MAX_SHADOW_LIGHTS, silently).
  An `ambient`-type light sets the HD-2D ambient colour.
- **Shadow maps** (`hd2d/lighting.py`):
  - The sun has one orthographic map, every frame.
  - Each shadow lamp has six 512 px faces in one atlas, drawn once per room. `LAMP_CASTER_FS` writes the
    linear distance ÷ radius.
  - **Near plane:** `POINT_NEAR` = 0.05 m. Only geometry within 5 cm of the light is missing from its map, and
    nothing measured is that close.
  - **Bias:** `dist − 0.006 ≤ stored`, i.e. 0.6 % of the **radius** (4.2 cm for a 7 m lamp), plus the receiver
    moved 3 cm along its normal.
  - **Filter:** 1 or 3×3 samples by shadow softness.
- **Own fixture** (#459, `lamp_fixtures`): a structure ≤ 1 m across is left out of that lamp's map only if the
  light lies inside one of its drawn part boxes (+1 cm).
- **Lit shaders:** `light_at` in `LIGHTING_GLSL` (structures, ground, sprites, scatter, water). Lamps fall off
  quadratically to the radius. Shading is diffuse only: no specular, no emission.

## 2. Measurements: are shadows geometrically right?

There are two probes, each using the scene's **own shader functions and shadow maps** (`Lighting.probe`) and
measuring one lamp alone, shadows on against off, checked against CPU rays through the room's real triangles:

- **`pool_probe.py`:** the top surface (ground, floor or table) on a 0.25 m grid inside each lamp's radius, with
  CPU rays on a 0.5 m sub-grid.
- **`surface_probe.py`:**
  - **Lit surfaces:** 6,000 rays from each lamp; the first structure surface each meets is lit by construction.
  - **Shadowed surfaces:** the next surface along the same ray is in shadow by construction.

| Scene (night) | Lamp | Fixture | Floor/ground points (CPU vis / blocked) | False shadow | Leak | Pool energy on/off |
|---|---|---|---|---|---|---|
| Lakeside | 1 | lamp_post | 344 / 0 | 0 | — | 1.000 |
| Lakeside | 2 | lamp_post_2 | 346 / 0 | 0 | — | 1.000 |
| Village | west | lamp_west | 368 / 0 | 0 | — | 1.000 |
| Village | east | lamp_east | 333 / 10 | 0 | 0 | 0.951 (real occluders) |
| Cottage | 1 | — | 89 / 162 | 0 | 0 | 0.657 (walls and the table, CPU-confirmed) |

**Structure surfaces (7 m lamps):**
- **Lit:** 5,152 points, **6 false shadows (0.12 %)**, all on shadow edges at 40–68° incidence.
- **Shadowed:** 686 points, 31 leaks. Of these, 21 are layered faces 5–7 cm behind a wall face (inside the
  bias), 7 are on the cottage table's shadow edge, and 3 are other edge texels.

**Frames:** pool luminance (a 1.5 m disc round each lamp's foot, projected with the frame's own matrix) is
**identical with lamp shadows on and off** in Lakeside and the village, at all three times of day
(`data/frames_base.json`).

**Self-shadowing and acne:** none systematic. The near plane and bias are adequate for the kit's 7 m lamps.

### 2a. The remaining self-darkening: near-miss fixtures (C1)

The village's west lamp, moved off its lantern centre (`make_offsets.py`):

| Light position | #459 fixture found | Pool energy (shadows on ÷ off) | Lit area | **With F1 (reach 0.15 m)** |
|---|---|---|---|---|
| lantern centre … 21 cm off | yes | 1.000 | 79 m² | 1.000 |
| **25 cm off** | **no** | **0.625** | 47 m² | **1.000** |
| **30 cm off** | **no** | **0.716** | 53 m² | **1.000** |
| 40 cm off (outside the lamp head) | no | 0.856 | 63 m² | 0.856 (correct: beside the lantern) |
| 60 cm off | no | 0.955 | 76 m² | 0.955 |
| 2.2 / 2.85 / 1.5 m high, centred | yes | 1.000 | — | 1.000 |
| **3.0 m high** (15 cm above the cap's top) | no | **0.008** (black) | 0 m² | 0.008 (the cap roofs the light: see O4) |

**CPU rays agree in every case.** This is not acne, bias or the near plane: the lamp's own lantern or cap
genuinely sits in the way, because the match is all-or-nothing.

Placements like this happen in practice. Studio's "+ Add light" puts the light where the ground is clicked, at
1.5 m, and clicking a lantern in the 30° view lands about 4 m behind the post. The creator then types X, Y and
Height.

**F1 prototype:** a part box *within 0.15 m* of the light counts, and the size rule (≤ 1 m) is unchanged.
- **#459's own room** (`fixture_suite.py`, the GPU test's evidence) passes every check unchanged: fixtures,
  open ground lit, near wall, the 0.23–0.33 m panel and the far wall still block, and GPU/CPU agree 554–0.
- **Why 0.15 m:** the reach must stay under that panel's 0.23 m.

**In frames** (`sheets/sheet_reach_village.png`, `data/frames_offset25_*.json`), the west lamp's pool luminance
was:

| Time | Before (shadows on) | F1 (shadows on) | Shadows-off control |
|---|---|---|---|
| Noon | 116.0 | 128.5 | 128.5 |
| Evening | 78.2 | 90.7 | 90.8 |
| Night | 65.0 | 77.5 | 77.5 |

Before, the lantern threw a wide dark wedge over the west side of the village.

**Behaviour change:** a light within 15 cm of a small prop's box (a candle on a crate) now stops that prop
shadowing it.

### 2b. Lamps 3+ silently cast no shadows (C2)

Studio shows "Casts shadows: on" for every lamp (the default), but `parse_scene_lights` gives a shadow map to the
first two only. In Lakeside, with lamps on:
- **Lamp 3** lights 5 points walls should block.
- **Lamp 4** lights **253 of 253** blocked points.

**F2 prototype** (`slots4`, four shadow lamps; the face-matrix array goes from 12 to 24): both leaks go to 0.

**But Lakeside's `lamp_post_4` stands 0.2 m inside the cottage's south-east corner** (cottage footprint
±2.8 × ±2.3 m about (19, 20) m; post at (21.2, 18.3) m). With a shadow map its light is walled in: **energy 0.0**
(`who_blocks_lakeside__l3_night_3.json`: the cottage's `wall_south_e_high` and `wall_east_high`).
- It lights today only *because* it has no shadow map.
- This is a content defect inherited from the original Lakeside (not from L1/L1b), harmless while L1b ships the
  lamps off.
- **Raising the budget changes this scene**, so the post would need moving first.

**In frames** (`sheets/sheet_slots4_lakeside.png`), lamp 4's pool goes from 48.3 to **26.2** at night once it
has a map: it is walled in.

**Memory:** 7.5 MB per shadow lamp (35 → 50 MB at four).

### 2c. Bias with large lamps (latent, O3)

The bias is 0.6 % of the radius. Village lamps scaled up:

| Radius | Shadowed points still lit | False shadow on lit points |
|---|---|---|
| 7 m (shipped) | 13 / 78 (mostly 5–7 cm layering) | 2 / 1,719 |
| 14 m | 44 / 365 | 26 / 2,152 |
| 28 m | 96 / 493 | 32 / 2,333 |
| 56 m | 124 / 493 (gaps of 50 cm+) | 19 / 2,333 |

Studio's "Bigger" allows 125 m (a 75 cm bias). **F3 prototype**, a metric bias of 2 cm + 0.8 % of the distance:
- **Large lamps:** leaks drop to 77 (−38 %), but false shadows rise to 40.
- **7 m lamps:** unchanged.

It's a trade, not a clean fix, so it's **optional**. The shipped 7 m lamps don't need it.

## 3. Emission (C4, O1)

**Today:**
- `glb._Reader.materials` keeps only the base colour.
- The import report treats `KHR_materials_*` as harmless and never mentions the lost emission.
- `MESH_FS` computes `albedo × light`.
- The kit's `lantern` material has a texture and no `emissiveFactor`.
- **So a lamp head is lit only from outside** (the lamp inside faces away from every lantern face): at night it
  reads 12 luminance, darker than the ground round it.

**E1, glTF emissive (material-driven):**
- **Reads** `emissiveFactor` × `KHR_materials_emissive_strength`, and adds `albedo × emissive` per draw. Statics
  are batched per material, so this is one uniform per draw.
- **Keeps the pixel art** (the glass panes glow; the iron frame stays dark). `emissiveTexture` is not read.
- **Shown** with a scratch copy of `lamp_post.glb` given `emissiveFactor` [1, 0.8, 0.55] on `lantern`, as Blender
  exports an Emission colour.
- **Applies to** any imported emissive material: windows, crystals, signs.
- **Limit:** a material glows whether its lamp is on or off. L1b's daytime lamps are off, so with E1 alone
  their lanterns would glow at noon.

**E2, lamp-driven glow (no asset change):**
- **What it does:** the drawn part of a lamp's fixture that holds the light (the lantern's box) glows with the
  lamp's colour × intensity × 0.8. A disabled lamp gives no glow, and the colour follows the lamp.
- **Cost:** up to eight box tests per structure fragment.

| Night, lamp head luminance | Before | E2 glow | E1 emissive |
|---|---|---|---|
| Village (both) | 11.9 | 56.5 | 51.1 |
| Lakeside lamps 1/2 | 11.9 / 12.7 | 43.0 / 44.0 | 51.1 / 52.1 |
| Evening, village | 18.5 | 63.0 | 57.6 |
| Noon, village | 27.9 | 72.5 | 67.1 |

**What changes:**
- **Pixels:** 1,192–2,332 a frame, all on the lamp heads. Every pool, wall, character and the cottage frame are
  byte-identical (`data/compare_emissive.json`).
- **Bloom:** none needed. The LDR result reads as a lit lantern against the night.
- **Kit art:** the kit's lantern texture is mostly dark frame, so only its glass strips glow. Brighter glass would
  be a content change.

## 4. Studio lighting controls in an HD-2D room (C3)

Studio offers the full 2D lighting panel in HD-2D rooms (Environment > Lighting..., and the bar). The HD-2D frame
never runs the 2D compositor (`tick.py:146`), and `parse_scene_lights` reads only per-lamp fields plus two room
keys.

| Control | Writes | In HD-2D |
|---|---|---|
| Lighting On / Off / As project | `lighting_enabled` | **No effect** (lamps always lit) |
| Status line "On: dark away from lights" / "Off: everything is fully lit" | reads the 2D compositor | **Wrong** for HD-2D |
| Room light presets, Darker / Brighter | `lighting_ambient_color` | **No effect.** HD-2D uses Sun and sky's ambient and the `ambient` light's colour (Lakeside's `[60, 70, 110]` is inert). |
| Shadows on / off / project | `lighting_shadows_mode` | **No effect** (HD-2D reads `settings.hd2d.shadows`, which Studio doesn't expose) |
| Shadow edges Sharp / Soft / Softer | `lighting_shadow_softness` | Works (PCF 1 / 3×3 / 3×3: Soft and Softer are identical for lamps) |
| Fine-tune: Edge width | `lighting_shadow_edge` | **No effect** |
| Fine-tune: Strength | `lighting_shadow_strength` | Works |
| Fine-tune: Quality | `lighting_shadow_quality` | **No effect** |
| Fine-tune: Characters cast shadows | `lighting_character_shadows` | **No effect** (characters always cast sun shadows; never lamp shadows) |
| Per light: colour, size, X/Y, Height, On | light fields | Works |
| Per light: Casts shadows | `shadows` | **Only the first two lamps**; silent for the rest (C2) |
| Per light: Flicker presets and fields | `flicker_*` | **No effect** (HD-2D lamps are steady; only campfires flicker) |
| Lights list | — | Lists the `ambient` entry as "Light 1: …, size 0" |
| Panel text "Walls on the map block each light…" | — | 2D occluder wording |
| *(missing)* lamp intensity | `intensity` | Read by HD-2D; **no Studio control** |

## 5. Performance (GPU timer query, RTX 4070, unlocked clocks)

Method (`scripts/perf.py`):
- **What's timed:** the renderer's whole draw (`Hd2dRenderer.draw`), at night, 1280×720.
- **Frames:** each shot is settled (clocks reset, 120 updates), then the **same frame is drawn 660 times**,
  discarding the first 60.
- **Framing:** the camera target is identical across all variants (recorded per run).
- **Runs:** one process per variant; three rounds, alternating
  base / reach / glow / emissive / slots4 / bias.
- **Clocks:** not locked, so the GPU drifts between clock states on this light load. The **10th percentile** is
  the steadier figure here, and the medians are recorded too (`data/perf_summary.json`, `data/perf_runs/`).

| p10 ms (range over 3 runs) | Village | Lakeside, lamps 1–2 | Lakeside, lamps 3–4 | Cottage |
|---|---|---|---|---|
| base | 0.291–0.307 | 1.699–1.728 | 0.552–0.613 | 0.124–0.159 |
| F1 reach | 0.285–0.310 | 1.722–1.762 | 0.552–0.591 | 0.115–0.183 |
| F2 slots4 | 0.299–0.322 | **2.071–2.268** | **1.468–1.483** | 0.117–0.154 |
| F3 bias | 0.295–0.317 | 1.705–1.770 | 0.634–0.657 | 0.111–0.182 |
| E1 emissive | 0.295–0.320 | 1.480–1.677 | 0.512–0.609 | 0.116–0.139 |
| E2 glow | 0.302–0.325 | 1.701–1.760 | **1.120–1.187** | 0.116–0.134 |

- **F2 is a real cost:** two more lamps sample a 3×3 shadow filter across the view.
- **F1** works at load time only.
- **F3 and E1:** no measurable change.
- **E2's** +0.6 ms appears in one Lakeside view but not the other, both with the same structures in reach. An
  implementation should measure it with locked clocks before committing, and its fragment cost can be limited to
  the fixture structures' own draws.
- **Shadow-map memory:** 35 MB at 2 lamps, 50 MB at 4 (village and Lakeside).

**Earlier pass, rejected:** an earlier timing pass that updated between draws gave non-deterministic framing
(Lakeside swung by about 1 ms between variants). It is kept only as a record in the scratch folder and isn't used
here.

## 6. Recommended corrections

**Required for correctness:**
1. **C1, fixture reach.** Match a lamp's own fixture within 0.15 m of a small structure's part box (F1). It's one
   function, with a CPU twin already in place (`hd2d_lighting_demo._cpu_lamp` takes the same skip set).
   - **Tests:** the offset series (25 / 30 cm restored, 40 cm still shadowed), #459's panel and walls unchanged,
     and the 15 cm above-cap boundary.
2. **C2, shadow budget honesty.** Either raise MAX_SHADOW_LIGHTS to 4 (F2: about 7.5 MB and +0.4–0.9 ms in Lakeside per extra
   lamp), or keep 2 and have Studio say which lamps actually cast. **Before any raise,** fix Lakeside's
   `lamp_post_4` placement (a content change to the installed project, which needs separate authorisation).
3. **C3, Studio HD-2D lighting panel.** Hide or relabel the nine inert 2D controls in HD-2D rooms. Expose what
   HD-2D reads: room shadows on/off (`settings.hd2d.shadows`), lamp intensity, and an honest per-lamp shadow
   state.
4. **C4, glTF emission.** Read `emissiveFactor` (× `KHR_materials_emissive_strength`) and draw it (E1), and stop
   calling the emissive extension harmless. Otherwise the import report should at least say that emission is
   dropped.

**Optional visual enhancements:**
- **O1:** lamp-driven lantern glow (E2), so kit lanterns light up when their lamp is on, with no asset change.
  Alternatively, E1 plus an emissive kit lantern, which glows even with the lamp off.
- **O2:** brighter glass in the kit's lantern texture (content).
- **O3:** a metric, distance-scaled lamp bias (F3), only if large lamps matter.
- **O4:** Studio aids:
  - "Snap to lamp post" when a light is added on or near one;
  - a warning when a lamp is boxed in (above its cap, inside a building, as Lakeside lamp 4 is).
- **O5:** lamps that follow the time of day. Noon presets leave lamps lit; L1 had to switch Lakeside's off by
  hand.

**Not recommended:** disabling shadows globally. Bloom was not needed for emission and wasn't prototyped.

## 7. Reproduce

The scripts are in `scripts/` (Windows, Python 3.13, the engine at this branch's base). Each takes the scratch
project path, refuses a non-scratch path, and points APPDATA and the Mesh user and projects directories at
scratch folders:
1. `make_variants.py`, `make_offsets.py`
2. `pool_probe.py SCENE`, `surface_probe.py SCENE`, `who_blocks.py SCENE LAMP`
3. `capture.py [--patch P] [--suffix em]`
4. `fixture_suite.py [--patch reach]`
5. `perf.py [--patch P]`

Prototypes are named in `protos.py` (`reach`, `slots4`, `bias`, `emissive`, `glow`, combinable with `+`).
