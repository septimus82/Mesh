# M17 pilot: PixelLab cottage texture candidates

Candidate textures for one cottage, generated with PixelLab (API v2) under the owner's subscription on 2026-10-25.
This is an art-direction experiment, not a finished set. Nothing here replaces the starter textures in
`tooling/hd2d_assets/textures/`, which were not modified.

- `provenance.json` records, for every file: the endpoint, the request (with image inputs summarised), the prompt, the seed, the job, tile and generation ids, UTC times, the generations used and any post-processing. It also holds the shared palette.
- `tiling_report.json` gives per-file size, colour count, edge-seam metrics, the seam verdict, 2x2-block fractions, lightness and saturation. It also has the same metrics for the starter textures.
- `contact_sheet.png` shows each candidate at 8x with a label and, for tiling candidates, a 3x3 tiling at 4x. The starter plaster, timber, shingles and cobbles are at the bottom for comparison.
- `../raw/textures/<call>/` holds the untouched API outputs and a `record.json` per call (no secrets). It includes all 16 tiles-pro plaster variations.

## Budget

| | Generations |
|---|---|
| Balance at start | 3568.7 of 5000 |
| Balance at end | 3527.7 |
| Used by this task (sum of the per-call `usage` fields) | **35, which is 5 over the 30 cap** |

The balance is shared with the character agent that ran at the same time, so the 41-generation drop includes about 6 of its generations.

Measured costs: `create-tiles-pro` costs 15 per call (it returned 16 variations of 64 px). `create-image-pixflux` and `create-image-bitforge` cost 1 each. `inpaint-v3` costs **10**. The inpaint cost wasn't documented. I tried it with 5 generations left and it took the total to 35. I stopped generating at that point, so the second door, any further seam fixes and a second moss attempt were not made.

## Standards applied

- **Density.** Everything is about 32 px per metre.
  - Plaster, stone, roof and moss tiles are **64x64 (2 m)**. These cover large wall and roof areas, where a 1 m repeat would be obvious, and stones and slates need room to vary.
  - Timber is **32x32 (1 m)**. Beams are only 0.2-0.3 m wide, so a 2 m tile buys nothing.
  - The door is 38x64 (1.2 x 2.0 m) and the windows are 26x29 (0.8 x 0.9 m).
- **Resampling.** No file was resized. Every PNG is at its generated pixel size; files are byte copies, except `stone_b_seamfix` (see below).
- **Mixed resolution.** The 2x2-block check finds no half-resolution drawing: the four grid phases are within 0.1 of each other in every file. The plaster tiles show high uniform fractions (about 0.92) in all phases only because they are large flat areas.
- **Palette.** I used one 35-colour master palette (`provenance.json` > `_palette`). It was sampled from the starter kit textures, clamped to saturation of 0.45 or less and lightness of 0.2-0.75, and extended with clay, moss and glass ramps.
  - Each call was given the subset of ramps it needed: as `target_palette` (tiles-pro, max 12 colours) or as `color_image` swatches (pixflux, bitforge).
  - All outputs stay within saturation 0.45 and lightness 0.21-0.74.
  - Colour counts are low: 4-10 per tile and 15 for the door. The starter textures have 2-7.

## Seamless tiling

I checked tiling two ways. The first is the edge ratio: the mean RGB step across the wrap edge divided by the mean interior step, with a pass at 1.5 or less. The plain ratio fails coursed materials whose mortar or course line falls on the edge; the starter plaster scores 16.5 and the starter shingles 2.9. So a texture also passes when its edge step is no stronger than the strongest line already inside it. I then checked every verdict by eye in the 3x3 previews.

| Candidate | Edge ratio x / y | Verdict |
|---|---|---|
| plaster_a | 0.00 / 2.40 | tiles (by eye: clean) |
| plaster_b | 0.36 / 1.58 | tiles (by eye: clean) |
| plaster_c | 4.48 / 4.42 | **seams**: a clear grid of hard edges |
| stone_a | 0.26 / 1.47 | tiles |
| stone_b | 1.39 / 3.31 | tiles: the edge falls on a mortar course |
| stone_b_seamfix | 1.16 / 3.21 | tiles |
| timber_a | 5.61 / 0.00 | **seams**: a vertical seam every metre |
| timber_b | 2.60 / 1.24 | **seams**: a vertical seam |
| roof_slate | 1.99 / 1.90 | tiles: the edge falls on the slate joints |
| roof_clay | 2.05 / 1.68 | tiles |
| moss_roof_slate | 2.01 / 1.91 | tiles |
| moss_plaster | 1.27 / 0.03 | tiles |

**The seam repair on stone_b was a PixelLab call, not hand painting.**
- I wrapped stone_b by (+32, +32) px with a lossless `ImageChops.offset`, so its original edges met in a central cross.
- `inpaint-v3` regenerated a 6 px white cross mask over that seam. It changed 99 pixels, none outside the mask.
- I wrapped the result back by (-32, -32).

In hindsight stone_b already tiled acceptably, because its edge sits on a mortar course. The repair is barely visible, so it was not worth its 10 generations.

## Candidates and picks

| Material | Files | Pick | Why |
|---|---|---|---|
| Lime plaster | plaster_a, plaster_b, plaster_c | **plaster_b**, with a caveat | It tiles cleanly and is quiet. It is very flat (one base tone plus cracks), and its single bold crack repeats visibly every 2 m. plaster_c has the most weathering (stains, drips) but fails tiling. It is **not clearly better than the starter plaster**; the main gain is that it doesn't bake a timber band into the plaster. |
| Stone plinth | stone_a, stone_b, stone_b_seamfix | **stone_b_seamfix** (stone_b is equivalent) | Readable grey coursed blocks with mortar, and it tiles. It is ashlar-like rather than the irregular rubble I asked for. It has a mild baked bevel: light top-left edges, dark bottom-right joints. stone_a came out as pale cream brick, not grey stone. The starter kit has no stone wall, so this is a real addition. |
| Timber beams | timber_a, timber_b | **neither: keep the starter timber** | Both show seams. timber_a has a clear vertical seam every metre. timber_b is noisy grey-brown and reads as "dirty" more than as oak. |
| Roof | roof_slate, roof_clay | **roof_slate** | It tiles, sits in the same blue-grey family as the starter shingles but with more variation, and its highlights are only mild. The slates read slightly like bricks, with rows not overlapping much. roof_clay reads as a woven grid or basket weave rather than overlapping shingles. |
| Door | door_a | **door_a**, provisional | Vertical oak planks, iron strap hinges and a ring handle, at the right size. It doesn't fill the frame edge to edge: it includes a stone and timber surround, and the bottom corners are noisy. The hinges have some baked highlight. It needs a second attempt or a crop of the frame (the crop would change the density), and the budget ran out first. |
| Window | window_a, window_b | **window_a** | A clear four-pane cross mullion that reads at a distance. The panes contain odd cream rectangles, like curtains or reflections. window_b, with shutters, reads but is noisy at the edges. |
| Moss / wear | moss_roof_slate, moss_plaster | **none usable** | moss_roof_slate (pixflux with roof_slate as init_image) **failed**: there is no visible moss, and it is nearly identical to roof_slate. moss_plaster is a tiles-pro side product: plaster "pads" with moss in the joints. That is the top-down floor-tile look, not wall wear. |

## Honest assessment

- **Not blurry, and no mixed resolution.** All files are crisp, single-scale pixel art on the shared palette.
- **Seams.** timber_a, timber_b and plaster_c don't tile. The others do.
- **Baked lighting.** Lighting is mild overall. stone_b and roof_slate have bevel highlights, and the door hinges are shaded. None has a strong cast shadow.
- **Tile-art bias.** `create-tiles-pro` (square_topdown, top-down) tends to draw game *floor tiles*: bordered pads, a frame around each tile, and a moss-filled grid. About half of its 16 variations are unusable as wall material for that reason (see raw/textures/t01_plaster_64).
- **Prompt drift.** "Rubble" came out as ashlar or brick, "moss" didn't appear, and "clay shingles" came out as a grid.
- **Overall.** PixelLab gives a better stone wall and a somewhat richer slate roof than the procedural kit, plus a usable door and window that the kit lacks. Plaster and timber are **not better than the starter textures**, and moss failed. A second round should:
  - prompt pixflux for plaster;
  - use the inpaint-wrap repair only where the 3x3 preview shows a real seam;
  - make moss with `inpaint-v3` on a masked lower band of stone_b or roof_slate, budgeting 10 generations, instead of using `init_image`.
