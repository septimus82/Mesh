# M17 audit: HD-2D visual quality and creator experience (investigation only)

**Baseline:** `redesign/visual-editor` at `6861631`. No engine, Studio or asset code was changed.
- **Projects:** scratch copies of `D:\Games\Lakeside Village` and `D:\Games\Lakeside Village - Soundscape`. The originals are untouched, still three scenes each.
- **Captures:** real in-engine frames, from hidden windows (`tooling/scene_snapshot.py`, `tooling/hd2d_demo.HiddenGame`): the real `GameWindow`, scene loader and HD-2D renderer, at the game's own **1280×720**. No mockups.
- **Prototypes:** every `P*` image is a real capture from a **scratch prototype** harness (`tools/proto_post.py`). It adds effects to the game's existing `PostProcessPipeline` at runtime and is clearly not engine behaviour.
- **Naming:** "M17" was also used for the 2026-10 cottage visual pilot (#370–#372). This audit is separate.

**Evidence labels:** **[F]** fact (capture, measurement or code); **[H]** hypothesis.

---

## 1. Screenshots

**Camera settings** (from the scenes):
- **Lakeside** and the **starter village** (`start.json`, the `hd2d_rpg` template room): pitch 30°, fov 12°, distance 53.5 m (11.25 m of world top to bottom), follow player.
- **Cottage interior:** pitch 55°, distance 35.7 m (7.5 m view).
- **Sun:** Mesh's default noon in all three scenes, unless noted.

| # | scene, view | image |
|---|---|---|
| 01 | Lakeside, arrival spot (outdoors, paths, lamps, shop) | ![01](01_lakeside_arrival.png) |
| 02 | Lakeside, bridge, reeds and lake edge | ![02](02_lakeside_shore_bridge.png) |
| 03 | Lakeside, two cottages, props, fence | ![03](03_lakeside_cottages_props.png) |
| 04 | Lakeside, north (sculpted terrain, woodland, rocks) | ![04](04_lakeside_north_hills.png) |
| 05 | Lakeside, the lake. The player is placed on the water by the capture tool (position set without collision), which shows the reflection. | ![05](05_lakeside_east_lake.png) |
| 06 | Cottage interior (indoor camera) | ![06](06_cottage_interior.png) |
| 07 | Starter village (`hd2d_rpg` template), spawn | ![07](07_starter_village_spawn.png) |
| 08 | Starter village, north: plateau walls, stairs, bridge (the only stairs in either project) | ![08](08_starter_village_north_stairs.png) |
| 09 | Lakeside, player behind a cottage: the cutaway at work | ![09](09_lakeside_roof_bite_close.png) |
| 10 | Lakeside, the player **mid-walk** (real key events, frame drawn while the key is held) | ![10](10_walk_frame2.png) |
| 11 | Lakeside with the **evening** sun preset (`set_hd2d_sun(preset="evening")`: scene settings only). The player stands behind a lamp post, which is the correct occlusion. | ![11](11_lakeside_evening_preset.png) |
| 13 | Mesh Studio's edit view of Lakeside (editor orbit camera) | ![13](13_studio_edit_lakeside.png) |
| 15 | Lakeside, **night** preset, as authored | ![15](15_night_baseline.png) |
| 16 | Night, the same scene with the lamps' `shadows: false` | ![16](16_night_lamp_shadows_off.png) |
| 17 | Night, lamps raised 0.5 m (shadows on) | ![17](17_night_lamps_raised_0p5m.png) |
| 18 | Soundscape Lakeside: rain (3,000) + wind | ![18](18_soundscape_rain_wind.png) |
| C1 | 3× nearest-neighbour crop of 02 (pixel density) | ![C1](C1_crop_3x_character_bridge_roof.png) |
| C2 | 3× crop of 09 (the cutaway's edge) | ![C2](C2_crop_3x_cutaway_edge.png) |
| P2 | PROTOTYPE: 02 + tilt-shift + grade + vignette | ![P2](P2_proto_tilt_shore.png) |
| P4 | PROTOTYPE: 07 + the same | ![P4](P4_proto_tilt_starter.png) |
| P5 | PROTOTYPE: 11 (evening) + the same | ![P5](P5_proto_tilt_evening.png) |

**Examples that don't exist, rather than invented:**
- **Stairs:** Lakeside has none (terrain slopes only); the starter village has them (08).
- **Weather:** only the Soundscape copy has any (rain, 18).
- **A second indoor room:** none; the cottage is the only one.

---

## 2. Visual cohesion and renderer quality

**Camera and composition**
- **[F] Telephoto near-orthographic view** (fov 12°, pitch 30° outdoors), framing 11.25 m of world vertically. Scale reads well: about 64 screen px per metre, so each 32 px/m texel is about 2 screen px.
- **[F] Indoor and outdoor differ by design** (presets `indoor` 55°/7.5 m, `outdoor` 30°/11.25 m). Characters appear about 1.5× larger indoors (06 vs 03). That's a defensible choice, but an abrupt jump through a door.
- **[F] Studio's edit view (13)** is a free perspective orbit with a sky and a grid. It is useful for authoring, but it isn't the game's framing; "See it" gives one still frame of the game camera.

**Terrain and environment**
- **[F] Lakeside (01–05) is dense and coherent at close range.** It has painted paths, about 13,400 scatter instances (12 assets) and reeds round the lake.
- **[F] Its meadow is uniformly dense,** with flowers evenly sprinkled everywhere (01, 03): no clearings, no hierarchy, no rest for the eye.
- **[H] Sculpted elevation barely reads** (04). From 30° under noon light the slopes are hidden by grass and the shading is shallow.
- **[F] The starter village (07, 08) is a different quality level altogether:**
  - one tiled grass texture as a flat green carpet;
  - **rectangular dirt "plates"** for paths, with hard straight edges;
  - **no scatter, no terrain paint, no water**;
  - plateau walls in a single flat stone texture.

  Every new HD-2D project starts here.
- **[F] Lakeside's shoreline works** (05): sand ring, reeds, depth gradient, reflections. **[F]** The surface is dark and flat (no sky tint or sun glint).

**Characters and objects**
- **[F] Pixel density is consistent** (C1): character, planks and grass at the same 32 px/m, about 2 screen px per texel. Not a problem.
- **[F] The character art is simpler than the world:** a two-tone face, and a dark outline the environment doesn't use. Grounding is fine: feet at the billboard's bottom edge, a sun shadow, grass in front of the feet (C1, 10).
- **[F] Depth ordering is correct** between billboards and models (11: a lamp nearer the camera hides the player behind it).
- **[F] Cutaway defects** (02, 03, 09, C2):
  - **Over-cutting:** a cutaway roof is cut whenever the camera-to-chest line passes within 1.3 m, even when the roof doesn't cover the character on screen (02, 03: a bite below the player's feet).
  - **The hole itself:** when it is needed (09) it's a hard-edged half-disc with a dark rim.

**Lighting and atmosphere**
- **[F] Every scene ships with the default noon sun.** The existing **evening** preset alone (11) transforms the mood: warm, long shadows.
- **[F] Shadow-casting lamps black out their own light (15–17).** Details in §5 #2.
- **[F] Lamp heads never glow:** `engine/hd2d` has no emissive material support (grep finds none), so lamps are black shapes at night (12, 15).
- **[F] No atmosphere in HD-2D:**
  - no depth of field or tilt-shift, bloom, depth haze or fog, tonemapping or grading in `engine/hd2d`;
  - `fog_*` is a flat 2D overlay rectangle (`game_runtime/tick.py:170`; code inspection, not captured);
  - **[F] the engine's `PostProcessPipeline` wraps every frame** (`game_runtime/tick.py:127, 180`) and ships `Vignette` and `ColorGrading` (`engine/post_processing.py:86, 116`), **but nothing in `engine/` ever adds an effect**. It is a no-op today.
- **[F] Weather doesn't touch light:** rain falls under a hard noon sun (18).

**Overall cohesion**
- **Lakeside at noon is pleasant but generic,** with saturated uniform greens and the far edge as sharp as the foreground.
- **The starter village reads as a prototype.**
- **Closest to the HD-2D target:** the frames that combine mood lighting with presentation (P5).

---

## 3. Creator experience (Studio)

The full inventory, with `file:line` for every claim, is in the evidence folder's notes. Below, **Studio** means a visual control and **ops** means `project_ops`, which `mesh author` and MCP `apply_changes` can do.

**Good**
- **Camera:** presets (outdoor/indoor/close/wide), View, Pitch, Lens, Above-player.
- **Sun:** presets (morning/noon/evening/overcast/night), azimuth, elevation, strength, colour, ambient, sky.
- **Terrain:** sculpt and paint (5 materials, edges).
- **Water:** every field in the inspector.
- **Scatter:** brush with density, clumps, slope and materials.
- **Weather and wind:** presets.
- **Play (F4):** uses the game's own renderer, camera and cutaway.

**Missing or confusing**
1. **2D lighting controls shown for HD-2D rooms do nothing there** [F, `engine/hd2d/settings.py:303-333` reads only `lights` + softness/strength]:
   - "Room light" (`lighting_ambient_color`: Lakeside sets `[60,70,110]` and it is ignored);
   - "Shadows on/off";
   - edge width/quality;
   - "Characters cast shadows" (`cast_shadow`).

   HD-2D's ambient colour comes only from a light of `"type":"ambient"`, which neither Studio nor any op can create (JSON only).
2. **No emissive or "lit" look for fixtures;** no lamp **intensity** field in Studio (the op has it).
3. **No fog, haze, grading, vignette or depth of field:** no scene field, op or Studio control.
4. **Weather and lighting are separate:** choosing rain doesn't suggest the overcast sun (18).
5. **Scatter:** no per-asset tint, no seed or custom mix in Studio (the op has both), and the asset list is built into the engine. Hence uniform meadows.
6. **Ground:** texture and tiling are hard-coded (32×32 tiles, one per metre); `ground.texture` is JSON only.
7. **Structures:** yaw and uniform scale only; no tilt.
8. **Shadows:** `hd2d.shadows` and `shadow_resolution` are JSON only.
9. **Preview:** "See it" is one still frame. Play is the real thing, which is good.

---

## 4. Engine vs content classification

| finding | renderer defect | missing renderer feature | scene configuration | assets | authoring control | Studio workflow |
|---|---|---|---|---|---|---|
| Shadow-casting lamps black out their own light | **✔** | | | | | |
| No emissive / glowing lamp heads | | ✔ | | (lamp model has no emissive) | | |
| No presentation layer (DOF, grade, vignette, haze) | | **✔** (unused Vignette/ColorGrading exist) | | | ✔ | |
| Cutaway over-cuts; hard hole | **✔** | | | | | |
| Default noon everywhere; evening preset unused | | | **✔** | | | ✔ (template defaults) |
| Starter village barren | | | **✔** (template content) | ✔ | | |
| Uniform meadow density | | | ✔ | | ✔ (no tint or variation) | |
| Weather doesn't change light | | | ✔ | | | ✔ |
| 2D lighting controls inert in HD-2D | | | | | | **✔** |
| Character art simpler than world | | | | **✔** | | |
| Elevation hard to read [H] | (shading) | | ✔ | | | |
| Pixel density | consistent: no issue | | | | | |

---

## 5. Top five (ranked by consequence for "does this look good")

### 1. No HD-2D presentation layer (every frame)
- **Reproduce:** any HD-2D frame (01–08). Uniform sharpness top to bottom; no depth of field, vignette, grading, bloom or haze.
- **Evidence:**
  - **[F]** pipeline wired, never populated (`engine/post_processing.py:249-290`, `game_runtime/tick.py:127/180`);
  - **[F]** no such effects in `engine/hd2d`;
  - prototypes P2, P4, P5: grade + vignette + a screen-space tilt-shift.
- **Root cause:** missing renderer functionality; the existing effects are unused.
- **Belongs in:** renderer (+ one scene setting and a Studio toggle).
- **Expected improvement:** high. It's the signature of the look. The prototypes show a modest gain alone and a strong one combined with mood lighting (P5).
- **Complexity:** medium. Grade and vignette are trivial. A proper depth-of-field needs the HD-2D renderer's depth target; the prototype uses screen height in place of depth.
- **Regression risk:** medium.
  - Every frame changes.
  - GPU cost on CI's llvmpipe (gpu lane time).
  - Visual tests and evidence images.
  - Taste: it needs owner defaults (opt-in vs on, and strengths).
- **Priority:** high, as **PR 2**, after decisions on defaults.

### 2. Shadow-casting lamps black out their own light
- **Reproduce:** Lakeside, night preset (15). The two lamps that cast shadows (the first two in `lights`; `MAX_SHADOW_LIGHTS = 2`) light nothing.
  - **Lamp shadows off (16):** their pools appear.
  - **Lamps raised 0.5 m (17):** still dark.
- **Measured** [F] (mean luminance, 120×110 px at each lamp base):

  | area | shadows on (15) | shadows off (16) |
  |---|---|---|
  | lamp A base | 25.6 | 60.4 |
  | lamp B base | 27.5 | 65.6 |
  | far field | 28.6 | 28.6 |

- **Root cause:**
  - **[F]** the lamp's cube shadow map uses `POINT_NEAR = 0.05` m (`engine/hd2d/lighting.py:30, 219`), and the light sits inside the lamp-post lantern;
  - **[H, strongly supported by 15–17]** the lantern's own faces are the nearest occluders in every direction;
  - **[F]** the starter template creates its lamps the same way, with shadows on by default (`engine/hd2d/starter_village.py:148`), so new projects inherit it.
- **Belongs in:** renderer (lighting).
- **Expected improvement:** high for evening and night scenes; none at noon.
- **Complexity:** low.
- **Regression risk:** low. Only lamp shadows change; there's a GPU-vs-CPU agreement test to keep in step.
- **Priority:** **highest. Recommended first PR (§6).**

### 3. The starter village is barren
- **Reproduce:** a new `hd2d_rpg` project (07, 08).
- **Root cause:** template content (`engine/hd2d/starter_village.py`) predates terrain paint, scatter, water and sun presets. Lakeside (01–05) proves the engine can do far better today.
- **Belongs in:** scene and template content, plus the kit's assets. No engine change.
- **Expected improvement:** high for every new creator's first impression.
- **Complexity:** medium (deterministic template, collision and arrival spots, export tests).
- **Regression risk:** low to medium (template tests, `World` walkability).
- **Priority:** high (PR 3).

### 4. Cutaway over-cuts, and its hole is hard-edged
- **Reproduce:** stand 1–2 m north of a cutaway roof's ridge (02, 03): a bite appears below the player though nothing is hidden. Behind a house (09, C2): a hard half-disc with a dark rim.
- **Root cause:** **[F]** `MESH_FS` discards every fragment within `CUTAWAY_RADIUS = 1.3` m of the camera-to-chest line in front of the character (`engine/hd2d/renderer.py:44-55, 265, 1057`), with no test that the fragment covers the character on screen, and a binary discard.
- **Belongs in:** renderer.
- **Expected improvement:** medium. It removes a frequent visible artifact while walking through Lakeside.
- **Complexity:** low to medium (a screen-space overlap test; an ordered-dither edge).
- **Regression risk:** low.
- **Priority:** medium.

### 5. Lighting and atmosphere authoring is disconnected
- **Reproduce:**
  - Studio's Lighting panel in an HD-2D room: Room light, Shadows on/off and Characters cast shadows do nothing (Lakeside's `lighting_ambient_color` is ignored);
  - rain under noon sun (18);
  - no fog, emissive or lamp intensity in Studio;
  - every shipped scene left at noon.
- **Root cause:** 2D lighting controls reused for HD-2D rooms; HD-2D equivalents (the ambient-light colour, lamp intensity) unexposed; weather not linked to sun presets.
- **Belongs in:** Studio (editor), plus a small op for the ambient colour.
- **Expected improvement:** medium. Creators get the moods the engine already supports (11) instead of dead controls.
- **Complexity:** low to medium.
- **Regression risk:** low.
- **Priority:** medium.

**Not in the top five:**
- uniform meadows (content; tint and variation controls would help);
- dark flat water (renderer, low);
- the indoor/outdoor scale jump (design call);
- simple character art (assets);
- elevation readability (hypothesis; needs a terrain-only check).

---

## 6. Recommended first PR: lamps no longer shadowed by their own fixture

**Why this one:** it's a real defect, bounded to one subsystem, measurable, and low risk. It makes the existing evening and night presets work as creators expect (the night lamps in 15 vs 16), in Lakeside and in every new template project. #1 (presentation) has a larger payoff but needs owner decisions on defaults and its CI cost, so it should follow as PR 2.

**Likely files:**
- `engine/hd2d/lighting.py`: the lamp caster pass (`LAMP_CASTER_FS`, `POINT_NEAR`) and the CPU twin used by `Lighting.probe` agreement tests;
- `tests/test_hd2d_lighting_gpu.py` and its CPU-ray model;
- a short note in the lighting docstring.

**Proposed implementation:**
- When drawing a lamp's six-face depth map, ignore caster fragments within a **fixture clearance** of the light (about 0.35 m, a documented constant). A lamp's own lantern no longer blocks it, while walls, buildings and characters farther away still cast lamp shadows exactly as now.
- The CPU reference (`Lighting.probe` / Möller–Trumbore agreement) gets the same rule, so the 100% agreement test stays meaningful.
- No scene-format change and no new setting.

**Acceptance (before/after, the same scratch scenes and capture tool):**
1. **Night:** mean luminance in the 120×110 px window at each **shadow-casting** lamp base rises from about 26 to **≥ 55** (≥ 2×). The far field is unchanged within ±1.
2. **Noon (01, 03):** differences appear only within the shadow-casting lamps' radius (7 m). Everything else is pixel-identical.
3. **A lamp behind a wall** (a new GPU scenario) still leaves the far side of the wall in its shadow. Occluders beyond the clearance keep working.
4. **GPU vs CPU** lamp-visibility agreement stays at 100% (`tests/test_hd2d_lighting_gpu.py`).
5. **The GPU lane** passes on both OSes (Extended), as does required CI, with no change in selection or thresholds.

**Automated regression:** a new GPU test with a lamp inside a closed box fixture of 0.2 m faces, so its light reaches the floor; the wall test from (3); the agreement test updated.

**Must stay unchanged:**
- the sun shadows;
- non-shadow lamps;
- lamp count limits (8, with 2 shadowed);
- attenuation;
- 2D lighting;
- the scene format;
- the starter template's content;
- all thresholds.

---

## 7. Performance and compatibility risks
- **PR 1 (lamps):** negligible cost, one comparison in a pass drawn once per room. The only visible change is brighter pools at shadow-casting lamps, by design.
- **Presentation (PR 2):**
  - **Cost:** 2–4 full-screen passes per frame. On CI's software GL (llvmpipe) that adds to every gpu-lane frame. Measure with #456's calibration, and keep it opt-in, or off in tests that compare pixels.
  - **Depth of field** needs the HD-2D depth target exposed to the post pass. The HUD must stay outside the effect, as it already is (`tick.py`).
- **Template (PR 3):** existing projects are unaffected (templates copy at creation). Export and wheel tests must cover the new content.
- **Cutaway:** shader-only change. Keep `cutaway: true` semantics.

---

*Evidence:*
- **Images and scratch tools:** `docs/reviews/m17_visual_audit/` on branch `review/m17-visual-audit` (evidence only, not for merge).
- **Captures:** made with `tools/capture.py`; scene-preset variants with `tools/variants_and_walk.py`; prototype post effects with `tools/proto_post.py`.

**Stopped after the investigation, for independent review. Nothing implemented, merged or rerun.**
