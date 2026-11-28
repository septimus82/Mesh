# M17 Stage 1: independent art QA (HD-2D pilot)

**Reviewer:** an independent QA agent. It changed nothing in the repo, made no PixelLab calls and ran no git. All numbers come from the scripts in this folder:
- `measure.py` writes `measurements.json`;
- `seamzoom.py` makes the seam strips;
- `roof_orient.py` tests the roof orientation;
- `render_regions.json` holds the in-render region statistics (inline script).

Images are in this folder too:
- `tile3x3_*` are 3×3 tilings at 4×;
- `seamzoom_*` are 8× strips across the wrap edges, with the seam marked by red ticks;
- `roof_orientation_evidence.png`, `cottage_wall_close_C.png`, `hero_m17_8x_grid.png`, `sprite_gameplay_strip.png` and `sprite_close_strip.png` are the remaining evidence images.

**Overall verdict: CONDITIONAL PASS as an art direction, not as a set of shippable assets.** The conditions are in the last section.

- **Character:** the PixelLab hero is a real gain at close range. At gameplay distance, readability got worse.
- **Cottage:** the pilot cottage reads as more of a house. Most of that comes from modelling and layout: the windows, plinth split and framing. Only about 3 of the 15 PixelLab textures are used, and one of those (the roof) is mapped upside down and clashes with the village.

---

## 1. Defects

| # | Sev | Asset | Defect | Evidence | Suggested fix |
|---|---|---|---|---|---|
| 1 | **major** | cottage roof (`roof_slate` in `build_cottage_m17.py`) | **The roof texture is mapped upside down.** The slope UV is `v = distance from the ridge`, so v increases toward the eave. Blender's v points up the image, so the image's top lands at the eave. | Rim-highlight test (`roof_orient.py`): in the texture as authored, the cream rims have a dark gap **below** them (88 px vs 9 above). In the render (`C_cottage_close`) the gap is **above** them (1037 vs 93), which matches the vertically flipped texture. `roof_orientation_evidence.png` shows the render on top, then the authored texture and the flipped texture. | Use `v = slope_length - distance`, or negate it, and re-judge. The authored art has its rims on the **bottom** edges, which means light from below and contradicts the upper-left sun. Fixing the UV alone will therefore show a different lighting error. Regenerate the texture (see #2). |
| 2 | **major** | `roof_slate` (style and cohesion) | **It reads as outlined bricks, not overlapping slates, and is much brighter and busier than every other roof in the village.** The cream rim colour `#a6a296` is drawn around single slates in the "tile pad" style. The flip in #1 turns those rims into top-left bevels, which pushes the brick read further. | In-render L*: pilot roof p95 is **51.1** (std 9.3); the starter shingles on the shop **in the same frame** (`C_centre`) reach p95 **32.0** (std 7.3). The roof highlights are brighter than the grass (p95 38.9) and the dirt (37.5). See `C_centre.png`: the pilot roof on the left, the starter shop roof on the right. | Regenerate with overlapping courses: a butt edge with a shadow under each course, no cream outline, highlights taken from the slate ramp (`#6c7890`). Or give every village roof the same treatment so they match. |
| 3 | **major** | `hero_m17` idle | **The idle pose is a mid-stride walk frame. In the down and up rows, one foot is lifted 3 px (about 0.1 m) for as long as the player stands still.** | Foot-bottom rows (left/right foot): `down_0` **47/44**, `up_0` **44/47**. The baseline is 47/47. Visible in `sprite_gameplay_strip.png` (path, down-facing). | Use a frame with both feet down as column 0 (`down_3` is 47/47), generate a matching idle, or hand-edit 3 px. The README's statement "Idle (column 0) is walk frame 0" is the cause. |
| 4 | **major** | `hero_m17` at gameplay distance (2×) | **The silhouette is less readable than the baseline everywhere it was measured, and it sinks into the dirt path.** The grey-brown tunic, brown hair and brown boots sit close to the brown dirt and the dark grass; the red scarf is the only separator. The figure is also thinner. | Sprite masks are exact fits of the sheet frame to the render. The fit error is 0.4-4.6 per channel, so it is pixel-exact. Edge ΔE (sprite edge pixel against its neighbouring background pixel), pilot vs baseline: cottage **25.4 vs 27.4**, path **29.6 vs 33.5**, centre **22.3 vs 25.6**. On-screen pixels: **1420/1860/1996 vs 1728/2392/2392** (17-22 % fewer). The mean opaque pixels per frame are 437 vs 510. Luminance contrast ratio is 1.00-1.33 for **both** heroes, which is poor; neither stands out by value. | Recolour the tunic in the hue or value it was prompted for (moss green, which came out grey-brown), or lighten or cool the tunic or trousers so the body separates from the dirt (L* about 34) and the grass (about 35). |
| 5 | minor | `hero_m17` front/back walk | **The rhythm is irregular.** The foot lifts in the down row go right 3 px, left 3 px, left 1 px, then none. The head-top row goes 5,5,6,5 (down), 4,4,5,5 (up) and 5,5,5,5 (right), so the bob is not two dips per cycle. It looks lopsided in the down and up directions. | `measurements.json` › `sprite`; per-leg foot-bottom rows (inline check). The source south frame 2 already had both feet 1 px off the ground (bbox bottom 49 vs 50), and the per-frame alignment turned that into a head dip. | Hand-correct frames 2 and 3, or regenerate the front and back walk. |
| 6 | minor | `hero_m17` identity | **Details appear and disappear between frames:** <br>• the satchel or pouch shows in some frames only (west 0 and 2, east 1 and 2); <br>• a red mouth or cheek cluster is on every west frame; <br>• there is scarf red on the legs: `left_0` row 43 is `#a84840` at the foot, `right_1` rows up to 42 are `#b07255`, and in `left_1` the whole far leg is maroon; <br>• `down_2` has a different, sterner face; <br>• the back of the hair in the up row has red-brown blotches. | `hero_m17_8x_grid.png`; red pixels below row 31 listed by an inline check; colour-set Jaccard against column 0 drops to 0.86-0.89 in left, up_3 and down. | Clean up by hand with a palette lock: recolour the stray reds, keep the bag in every frame or none. |
| 7 | minor | `roof_slate` tiling | **A partial vertical seam at u = 0.** Slates there are cut and two-toned every 2 m. tiling_report.json calls it "tiles". | The x wrap step is 71.1 against an interior median of 33.5 (stronger than 95 % of interior columns). 59 % of the pixel pairs across the edge jump by more than 60, against 22 % for a typical column. Visible in `seamzoom_roof_slate.png` and `tile3x3_pilot_roof_slate.png` (light patches at x = 256 and 512), and as two-tone slates in `roof_orientation_evidence.png`. | Repair it by inpainting across the wrap, or by hand on columns 63 and 0, or regenerate (#2). |
| 8 | minor | `stone_b` / `stone_b_seamfix` | **A phantom joint at u = 0:** a cream left-bevel highlight runs down the middle of blocks with no mortar beside it, in rows 0-24, and repeats every 2 m. The 10-generation seam fix (99 px) did not touch it. It is invisible on the plinth only because the plinth samples rows 35-64. | `seamzoom_stone_b(_seamfix).png`, left strip (the vertical cream line under the "^"). | Fix column 0 by hand before using it on any wall taller than 0.9 m. |
| 9 | minor | cottage plinth (layout) | **The plinth shows only about 45 % of the 2 m stone tile** (z 0.1-0.9 m maps to rows 35-61, plus the slab edge on 61-64). That gives about 1.3 courses with a cut top course and the same "^" crack motif along the base every 2 m. Its bevel is upper-left, matching the sun, but strong: top/left block edges L* 73.5/67.1 against bottom/right 48.2/50.2. | `cottage_wall_close_C.png`; in-render std **9.9** against **4.4** for the starter timber it replaced and **4.6** for the starter rock walls. It reads as embossed next to the flat village. | Draw a dedicated 0.9 m plinth band texture with whole courses, and soften the bevel by one ramp step. |
| 10 | minor | cottage framing (layout) | **The new door jambs are hidden.** They sit at \|x\| 0.6-0.75 m, entirely behind the starter door sprite, whose opaque area is 48 px = 1.5 m and covers \|x\| ≤ 0.75 m. Only an east-side sliver shows through parallax, so the frame looks lopsided. | `C_cottage_close.png` x ≈ 400-418 (east jamb visible); the west jamb is hidden. Door bbox (8,2)-(56,64) in `assets/sprites/door.png`. | Move the jambs outside 0.75 m, or narrow the door sprite to the 1.2 m opening. |
| 11 | minor | cottage framing (material) | **The corner posts, sill and jambs use the starter `timber`**, which is horizontal weatherboards (4 per metre). On 0.22 m vertical posts it draws horizontal stripes every 0.25 m, so the posts read as stacked blocks. | `cottage_wall_close_C.png`, left post. | Rotate the UVs 90° on the vertical members, or add a vertical-grain beam texture. |
| 12 | minor | `window_a` | **The panes are opaque pale cream or grey rectangles, not glass**, inside three nested frames (tan, blue-grey, dark). Up close (4×) it reads as a framed picture or curtained window. It is fine at 2×. | `cottage_wall_close_C.png`. | Use dark glass `#3a4a58` for the panes, with a single small reflection, and drop one frame ring. |
| 13 | minor | `plaster_a` (unused) | **tiling_report.json says "clean", but two cracks end abruptly on the y wrap edge, at different x.** | The y wrap step is 15.3 against an interior median of 2.5 (rank 0.86). See `seamzoom_plaster_ab_clay.png`. | The report should not rely on edge ratios alone. |
| 14 | minor | evidence | **`walk_compare.webp` is 640×360**, half resolution with three scenes tiled, so the walk can't be judged at pixel level from it. | 37 frames, 640×360, 67 ms per frame. | Add a crop of the hero at 2× and 4× from the engine. |

There were no blockers. Nothing was blurry, resampled, half-resolution or semi-transparent (see §2).

## 2. Measurements

### Pixel density and resolution
- **Density:** every pilot texture is at 32 px per metre as used, checked against `build_cottage_m17.py`.
  - The kit maps 1 tile per metre and the build scales it by 32 / image width. 64-px tiles therefore repeat every 2 m.
  - The roof is UV'd in metres and goes through the same scale loop. Slates measure about 12.5 texels wide in the render, matching the texture.
  - The window is 26×29 px over 0.81×0.91 m, which is 32.1 × 31.9 px/m.
- **Gameplay sprite scale** is exactly 2×: 43 px renders as 86 px and 44 px as 87-88. Close-ups are about 4× (174-176 px).
- **Half-resolution check:** the run-equality of neighbouring pixels at even vs odd phase differs by 0.06 or less in every pilot file. No 2×2 duplication was found.
- **Alpha:** 0 semi-transparent pixels in every pilot texture and in both hero sheets.
- **Mixed resolution in the cottage:** none among the pilot textures. The starter door sprite (48 px opaque = 1.5 m) is also about 32 px/m, but it is wider than the 1.2 m opening (#10).

### Palette (CIELAB ΔE76, each pixel to its nearest colour among the 58 colours of the starter textures)

| Asset | Mean ΔE | p95 ΔE | Share of pixels > 15 | Note |
|---|---|---|---|---|
| stone_b_seamfix | 0.2 | 1.4 | 0 | Sampled from the starter ramps |
| roof_slate | 2.4 | 8.9 | 0 | Hue matches; **value range does not** (L* p5-p95 25.5-66.6 vs shingles 19.1-42.3) |
| window_a | 3.8 | 9.3 | 0 | |
| door_a (unused) | 1.6 | 7.6 | 0 | |
| moss_plaster (unused) | 6.2 | 20.5 | 0.27 | Moss green `#66703e` |
| **hero_m17** | 7.9 | 13.9 | 0.008 | Outliers: `#9c433d` (scarf shadow), skin `#e5c1a7` (S 0.54, L 0.78), `#dab99c` (S 0.46), eye blue `#345385` (S 0.44, 16 px) |
| hd2d_hero (baseline) | 8.4 | 11.9 | 0.004 | |

**Conclusion:** hue cohesion is good. The master palette worked, and the hero's palette is no further from the village than the baseline's. The cohesion problem is **value and contrast structure**, not hue. The pilot roof and stone carry bevel and rim highlights 15-20 L* brighter than anything in the starter village surfaces (§1 #2 and #9). The hero has 30 colours, and its dark outline `#392a23` makes up about a third of its opaque pixels.

### Seams (my own check: the wrap step against the distribution of interior steps, plus 3×3 tilings viewed at 4×)

| Texture | My verdict | Agrees with tiling_report? |
|---|---|---|
| stone_b_seamfix | Tiles on the y axis (the edge is a mortar course). Phantom bevel at u = 0 (#8). | Partly |
| roof_slate | **Partial x seam** (#7) | **No** |
| plaster_a | Cracks cut at the y edge (#13) | **No** |
| plaster_b | Clean | Yes |
| plaster_c, timber_a, timber_b | Seam: edge stronger than 100 % of interior lines | Yes (the README already fails these) |

Repetition at game scale:
- The stone "^" crack motif repeats every 2 m along the plinth base.
- The roof seam column produces a two-tone slate every 2 m.
- The starter plaster (1 m) is unchanged.

### Lighting

| Asset | Measured light direction | Agrees with the sun (upper left / front)? |
|---|---|---|
| stone_b | Top-left: block edges with mortar above are lighter than those with mortar below (73.5 vs 48.2 L*), and left lighter than right (67.1 vs 50.2) | Yes |
| roof_slate as authored | Rims on the **bottom** edges | No (light from below) |
| roof_slate as rendered (flipped) | Rims on the top | Yes, but only through the UV bug |
| hero_m17 (down/up) | Viewer's left half lighter: 40.2 vs 36.8 L* (down), 34.9 vs 33.3 (up). The baseline is 43.1 vs 39.8. | Yes, soft and mostly frontal; no contradiction |
| window_a, door_a | Mild baked frame shading | No strong cast shadows |

The engine renders both heroes at about 0.68× gain (the fitted per-channel gain); that is a scene-lighting effect, not an art one.

### Sprite (hero_m17 vs baseline)
- **Height:** 42-44 px (1.31-1.38 m) vs 40-41. That is 67 % of the 64 px (2.0 m) lintel, and it fits the 1.2 m-wide doorway.
- **Proportions:** the head is about 13 px (rows 5-17), about 3.3 heads tall. This is a stylised short adult in both sheets, not a defect against the baseline.
- **Fit in the frame:**
  - No opaque pixel touches a frame edge.
  - The widest stride is 23 px, at columns 3-25 (`right_1`) and 6-28 (`left_1`). The 32 px frame is enough.
  - The feet are on row 47 in all 16 frames.
  - The horizontal centroid drifts 14.8-16.3 px. Right-facing frames sit about 1 px left of left-facing ones, which is acceptable.
- **Walk:** the side views have real contact and passing poses with an arm swing, far better than the baseline, which has no leg motion. The front and back views are weak and irregular (#5), and the idle frame is mid-stride (#3).

### Silhouette contrast in the renders (gameplay 2×, exact frame fit)

| Spot | Frame | Hero | Sprite L* | Background L* | Contrast ratio | Edge ΔE | Edge share ΔE < 10 |
|---|---|---|---|---|---|---|---|
| cottage | left | baseline | 25.7 | 27.5 | 1.06 | 27.4 | 0.25 |
| cottage | left | pilot | 24.4 | 26.7 | 1.00 | **25.4** | 0.18 |
| path | down | baseline | 25.4 | 32.7 | 1.12 | 33.5 | 0.07 |
| path | down | pilot | 23.6 | 32.6 | 1.21 | **29.6** | 0.15 |
| centre | up | baseline | 22.1 | 32.2 | 1.32 | 25.6 | 0.11 |
| centre | up | pilot | 21.0 | 32.3 | 1.33 | **22.3** | 0.09 |

Close-up fits were less exact (the scale is about 3.95-4.1×, not exactly 4×, with fit error 4-11), so those rows in `measurements.json` › `render_contrast` are indicative only.

## 3. Per-element verdict

| Element | Gameplay distance (2×) | Close-up (4×) | Source of the change |
|---|---|---|---|
| Roof | **Worse.** Brighter and busier than every other roof; reads as bricks. | Same or worse: crisp, but brick-like, mapped upside down (#1) and with a seam. | PixelLab art plus a UV bug |
| Lower wall / plinth | **Better.** Gives the house a base and breaks up the starter's brown box. | Better, with a cut course, a strong bevel and a repeating motif. | Mostly **layout** (the plinth split); the PixelLab stone is a decent addition, since the kit had no stone wall. |
| Windows | **Better.** The biggest single improvement to the house read. | OK; the panes read as cream curtains. | Mostly **layout** (adding windows at all); the window art itself is average. |
| Framing (posts, sill, jambs) | Slightly better: it gives an outline. | Weatherboard posts look like stacked blocks; jambs hidden or lopsided. | **Modelling**, using starter art |
| Plaster, timber, door | Unchanged: the starter art is kept. | Unchanged. | PixelLab plaster, timber and door candidates were not good enough (my checks agree with the README). |
| **Cottage overall** | **Better as a building, worse in roof cohesion.** | Better. | About 70 % layout and modelling, about 30 % PixelLab art (the stone plinth and the window). The roof subtracts. |
| Hero: detail, anatomy, costume | Marginal: the extra detail barely reads at 2×. | **Much better.** Neck, hands, cloak and satchel; a real character instead of a block. | PixelLab art |
| Hero: readability | **Worse** than baseline (§2 table, #4). | Fine. | Palette and value choice (the grey-brown tunic) |
| Hero: animation | Side views **better**; front and back slightly better than the baseline's 1 px bob, but irregular; the idle **regresses** (#3). | Same. | PixelLab art plus the assembly choice (idle = walk frame 0) |
| Hero: consistency | Flicker is barely visible at 2×. | Noticeable: bag, red pixels, face change. | PixelLab art |

### Cohesion
- **Hue:** the pilot cottage and hero share the village hues, as the ΔE table shows.
- **Rendering style:** they do not quite belong to the same world as the rest of the starter village.
  - The cottage now has bevelled, rim-lit "tile-game" surfaces next to a flat, procedural shop, stairs and retaining walls (`C_centre.png`).
  - The hero is a soft-shaded, anatomically drawn sprite next to blocky starter NPCs.
- **With each other:** the pilot hero and pilot cottage sit together reasonably well (generic fantasy-RPG pixel art).
- **The real issue:** the pilot creates a **mixed-style village**. That only resolves if the whole village moves to the new standard.

## 4. Overall art verdict: **CONDITIONAL PASS**

There is a meaningful improvement over the procedural starter, but it is narrower than "PixelLab art is better":
- **Character:** the clearest PixelLab win, at close range.
- **Cottage:** the improvement comes mainly from modelling and layout (windows, plinth, framing). PixelLab contributed the stone plinth and window art. Its roof, plaster, timber, door and moss attempts were not improvements; the roof is a regression in cohesion and is mapped upside down. Texture yield was low: 3 of 15 files are in use.

### Conditions before the pilot assets can be called an improvement or used further
1. **Fix the roof UV orientation (#1)** and replace `roof_slate` with an overlapping-slate texture whose highlights stay inside the slate ramp (#2). Alternatively, keep the starter shingles until all roofs move together.
2. **Fix the hero idle frame (#3)** and **raise its gameplay contrast (#4).** Re-measure the edge ΔE; it should be at least the baseline's (27/33/26) at the three spots.
3. Clean up the walk and identity issues (#5, #6) before the hero becomes the default player sprite.
4. Fix the jambs and the timber grain (#10, #11), or drop them.
5. Report the cottage gain honestly, as coming from layout. The same windows, plinth split and framing with procedural art would capture most of it. A cheap control would be to render that variant (starter-kit textures plus the new layout) before buying more texture generations.
6. Village-wide cohesion is the outstanding risk. The next stage should restyle one whole cluster (roofs, walls and NPCs together), not single assets.
