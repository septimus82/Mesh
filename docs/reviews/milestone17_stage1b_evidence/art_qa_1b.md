# M17 Stage 1B: independent art QA

**Reviewer:** an independent art QA agent. It was read-only: no repo edits, no git, no generator calls, and no new renders. Every judgement comes from the supplied renders in `m17b\cottage_final`, `m17b\hero` and `m17b\combined` (combined.json was complete), plus the asset files in `D:\Games\Mesh-m17`.

**Method:** gameplay first. Every hero number below is measured in the 1280×720 **gameplay** frames (art at 2×), using an exact fit of the sheet frame to the render:
- the fit is in `fit.json` and `fit_path.json`;
- the error is 0.4–1.1 per channel at the cottage and centre and 2–4.6 at the path, where lamp light falls;
- the gain is about 0.68.

Close-ups were judged only after that.

**Scripts** (all in this folder):
- `seams.py` makes the 3×3 tilings and seam ranks;
- `hero_frames.py` extracts the 16 frames and their stats;
- `fit.py` finds the sprite in the renders;
- `interior.py` measures the interior, region and face values at 1:1;
- `walkfit.py` identifies the sprite frame in each frame of `hero_walk.webp`;
- `cottage_attr.py` measures the A→B / B→C change.

---

## 1. Defects

| # | Sev | Asset | Defect | Evidence | Fix |
|---|---|---|---|---|---|
| 1 | **major** | H4 | **At the cottage door, the head disappears into the dark timber wall.** The added near-black ring and the dark hair merge with the wall shadow. This contradicts the claim that H4 "beats H0 at every spot": the edge metric only reads the ring. | ΔE (CIELAB) between the head and the local background 2 texels around it: **H4 6.2**, H2 13.1, H0 17.1. The head's mean L* is 18.9 against a wall at 13.6. Of the head-band pixels, 44 % are near-black (L* < 12), against 30 % for H2 and 16 % for H0. See `hero_gameplay_1to1_H0_H2_H3_H4_rgb(_x3view).png`, top row, and the `_grey` version. | Don't put the ring where the background is dark, or use a lighter ring. Better: drop the ring (see #2). |
| 2 | **major** | H4 | **The interior values collapse at gameplay scale.** The figure becomes the darkest object in the village. The doubled outline (original outline plus ring) and the deeper tunic and trousers fuse the legs into one block, filling the 1 px leg gap at (44,16). They also shrink the face's share of the head. | Near-black share of the figure at 1:1 (cottage / path / centre): **H4 40 / 42 / 51 %**, H2 25 / 31 / 42 %, H0 18 / 17 / 18 %. Figure mean L*: H4 18.5 / 17.7 / 14.5; H0 25.8 / 25.6 / 21.9. Skin as a share of the head band: H4 15.8 / 23.0 %, H2 20.0 / 28.7 %, H0 36.1 / 36.1 %. Sheet: 44 % of H4's idle pixels have luma < 40, against 0 % for H2 and 8–17 % for the starter NPCs. | Keep a single outline at about `#392a23`. Gain silhouette contrast with interior value, not with black: a lighter, mid-value tunic and a separate trouser value. |
| 3 | **major** | H1–H4 (not fixed from Stage 1) | **The costume reads worse than H0 everywhere.** The torso barely separates from grass and dirt. | Torso ΔE against the local background, at the cottage / path / centre: **H0 38.2 / 34.1 / 32.9**, H2 23.7 / 27.1 / 11.7, H3 20.0 / 23.3 / 8.7, H4 20.4 / 27.4 / 17.0. | Choose a tunic hue and value away from both grass (L* about 35, green) and dirt (L* about 33, brown). A slate blue or ochre at L* about 45–50 would work; the starter hero's blue reads for exactly this reason. |
| 4 | minor | H3 (and H4) | **The moss tunic lowers torso separation compared with H2 at every spot,** because moss sits next to the grass hue. The tunic is only 9–30 % of the torso-band pixels, so the change barely registers anyway. The edge metric doesn't move at all: H3 equals H2 to 0.1. | The torso row of #3. Tunic share per frame: `right1` 11 % (H3) and 9 % (H4). The README's table shows H3 and H2 identical. | Drop moss. If green is required by design, lift it to L* about 50 with a warm yellow-green. |
| 5 | minor | H2–H4 (cohesion) | **The candidates don't match the starter NPCs' style.** The NPCs (villager, merchant) are blocky, with big flat faces, flat two-tone shading and a soft outline. H4 widens the gap. | Edge luma: H4 **22**, H2 48, H0 39, villager 46, merchant 39. Luma < 40 share: H4 44 %, NPCs 8–17 %. Figure mean luma: H4 64, NPCs 106–120. See `npc_cohesion_2x_x3view.png`. | Either restyle the NPCs to match, or keep the player within the NPCs' outline and value range. |
| 6 | minor | H2–H4 walk | **The front and back walk has no head bob and a frozen upper body,** so it slides. The side-row bob is inconsistent: head-top rows are 5, 6, 5, 5 on the left and 5, 5, 5, 5 on the right. `right1` (east frame 1) keeps a dark back-arm mass; in H4, 113 of 191 torso-band pixels (59 %) are near-black, and the dark block blinks at 2× in the right walk. | `hero_frames.json` (tops), `side_rows_H1_H2_H4_6x.png`, `H3_vs_H4_side_step_10x.png`. `walkfit.json` shows the clip plays the frames 0, 1, 2, 3 evenly, 2 clip frames each, with no wrong frames. | A 1 px body drop on both step frames in every row. Repaint the east-1 back arm as an arm. |
| 7 | minor | H4 | **The ring cuts the visible foot lift in the down/up step frames from 3 rows to 2,** because it closes the gap under the lifted boot. That makes a stiff step stiffer. | ASCII dumps of `down1` and `down3` rows 36–47 (`H2_vs_H4_down_up_6x.png`). | The same fix as #2. |
| 8 | minor | C stone (`stone_b_seamfix`) | **Stage 1's phantom joint at u = 0 is now on the wall.** The new V offset shows rows 11–37 instead of 35–64. Column 0 has a cream bevel (luma 188–198) in rows 0–10 and 12–22, while column 63 next to it is stone body (99–161), with no mortar. It shows in the plinth's top course every 2 m: twice on the south face. At 2× it passes as a joint; at 4× it is a highlight with no joint. | `stone_phantom_C_close4x_x2view.png` (x ≈ 165 and ≈ 1135); the column dump in this review. | Repaint column 0 rows 0–22 as stone body (or a real joint): about 20 px, no generation needed. |
| 9 | minor | C window glass | **The recoloured `window_a` pane keeps its blue-grey inner frame ring,** which shows inside the modelled frame as a second, misregistered frame. There are blue strips above and below the modelled transom. It also lifts the pane value, so the window reads weaker at 2×. | Pane L* (p10 / p50 / p90): **C 17.2 / 22.6 / 27.7**, B 9.0 / 10.4 / 27.7. See `windows_BC_close_x6view.png` (bottom row). | Use B's flat pane, optionally with a 1–2 texel upper-left glint drawn on the pane. |
| 10 | minor | B plinth (starter `cobbles`) | **It is the busiest surface on the house.** It is a perfectly regular dot grid that repeats every 1 m, and it is the kit's ground texture for the porch and stair landing, so the wall reads a little like a floor. Behind the hero's head at the door it is noisier than C (see the combined set). | Plinth L* std **9.1** (B) against 4.2 (A's timber). Combined edge luma step at the cottage: B+H4 36.9 against C+H4 42.8. See `tile3x3_cobbles.png`. | Prefer C's stone after fix #8, or calm the cobbles' value range by one step. |
| 11 | minor (risk) | Roof (starter shingles) | **The cottage roof is now 32 px/m, but the README says the kit's flat projection gives 27.9.** Neighbouring roofs built by the kit (the shop) therefore probably have about 15 % smaller shingles. I did not measure that directly. | README; `cottage_centre.png` shows the shop's roof next to the cottage's. | When the cottage is adopted, re-UV the other kit roofs to 32 px/m. |
| 12 | info | B/C windows | The left window's frame leans at the screen's left. This is the camera's perspective (the walls lean the same way in A), not a modelling error. At 4× it produces some stair-stepping on the stiles. | `posts_window_B_close_x4view.png` | None. |

**No blockers.** Everything checked is crisp and nearest-neighbour:
- no semi-transparent pixels in any hero sheet;
- no isolated stray pixels;
- the feet are on row 47 in every frame of H2–H4;
- no resampling in the renders. The 4× close-ups have uneven 3–5 px texel blocks, which comes from the close camera, not from filtering.

---

## 2. Stage 1 defects: status

| Stage 1 defect | Status | Evidence |
|---|---|---|
| Roof inverted and too bright (`roof_slate`) | **Fixed** (by reverting to the starter shingles) | Orientation test (`..\roof_orientation.py`): texture 1.00 brighter-below; A, B and C renders 0.99. B's orientation is identical to A's and upright. Roof L* mean 24.3 (A) and 24.4 (B/C), against Stage 1's 51 p95. See #11 for the density note. |
| Idle mid-stride | **Fixed** (H2–H4) | down0 and up0 have both feet planted (6× sheets, ASCII dumps). H1's down/up rows had no planted frame at all. |
| Low contrast at gameplay | **Not fixed** in H2/H3. In H4 it is **partly fixed** for the silhouette on light ground (path and centre) and **worse** for the head on the dark wall, the interior and the costume. | #1–#3 |
| Details flickering between frames | **Mostly fixed** | Front/back: one canonical upper body, `down_2`'s face dropped. Side: satchel removed, red removed from the legs and mouth (red pixels on the legs: H1 3, H2 1). Remaining: the east-1 dark mass (#6). |
| The posts' grain | **Fixed** | Vertical grain on the posts, stiles and mullion (`posts_window_B_close_x4view.png`). |
| Window panes | **Fixed in B** (flat dark glass). C only **partly** (#9). | `windows_BC_close_x6view.png` |
| Cut top course of the plinth | **Fixed** | C's top is on mortar row 11 under the sill; B's on cobble gap row 0. The bottom course is cut by the ground, which is natural. |
| Stray highlight line in `stone_b` | **Rows 41–43 fixed.** The **u = 0 phantom joint (Stage 1 #8) is now exposed** (#8). | Column dump; `stone_phantom_C_close4x_x2view.png` |
| (Stage 1 #10) Hidden door jambs | Fixed by removing them. | README / renders |

---

## 3. Findings by question

### 3.1 Clarity at gameplay scale (1:1 in the 2× gameplay frames)
- **Cottage** (`cottage_1to1_ABC.png`, `cottage_wall_1to1_x3view_ABC.png`):
  - **Windows:** they read clearly at 2×. They are the strongest new element.
  - **Framing:** the posts and sill read as an outline that frames the box. Not noise.
  - **Plinth:** it reads. B's cobbles are busy (#10); C's ashlar is calmer and lighter (L* 34 against 23). Its crack scribbles mostly vanish at 2×.
  - **Overall:** B and C both read as a house where A reads as a box. No element turns to mush at 2×.
- **Hero** (`hero_gameplay_1to1_H0_H2_H3_H4_rgb/grey(_x3view).png`):
  - **H0** still reads best at 2×: a big light face block, and a blue torso that separates from both grounds.
  - **H2 and H3** are thin, low-separation figures.
  - **H4** has a crisp dark contour on dirt and grass: a real silhouette gain on light ground. But the gain is bought with black. The figure is 40–51 % near-black, the legs fuse, the face shrinks, and the head is lost on the dark wall.
  - **Verdict:** the metric was flattered. It reads only the outermost ring, which is exactly what H4 darkened. Further evidence of the metric's limits:
    - H3 equals H2 to 0.1, despite a full tunic recolour;
    - H4's cottage number moves from 36.9 to 42.8 when only the wall behind it changes (B to C).

### 3.2 Animation
- **Frames:** the 16 frames of every sheet are in `hero_all_frames_6x.png` and `frames6x_H*.png`.
- **Identity:** stable in H2–H4; the face is identical in all down frames.
- **Feet:** on row 47 everywhere.
- **Idle:** fixed.
- **Rhythm:** even in the down/up rows (stand, step, stand, step).
- **Head bob:** none in the down/up rows; side rows inconsistent (#6).
- **Walk clip:** frame by frame, `hero_walk.webp` plays each sheet frame for 2 clip frames, in order, with no skipped or wrong frames (`walkfit.json`).
- **Side rows:** they keep Stage 1's stride (good) and its east-1 back-arm blob.

### 3.3 Seams, repetition and lighting
| Texture | 3×3 tiling (`tile3x3_*.png`) | Notes |
|---|---|---|
| stone_b_seamfix | The y wrap is a mortar course (intended). x tiles, except the u = 0 phantom (#8). | Bevel upper-left (cream top and left, dark bottom and right): **matches the sun.** |
| cobbles | Seamless | Highlight on top: matches. Very regular grid (#10). |
| plaster | Clean in x. The y "seam" is the baked timber band (intended). | — |
| timber | Clean in x. y is the plank line (intended). | Shading per plank is top light / bottom dark. On the vertical members it becomes side-lit, which is low-contrast and not visible at 2×. |
| shingles | Clean | Face, then mid shadow, then dark gap down the slope: top-lit, upright. |
| window_a_glass | (Not tiled: clamped.) | Blue-grey upper-left ring: matches the light, but misregistered (#9). |

Wall repetition in the renders:
- B's cobbles repeat every 1 m, as an obvious grid.
- C's stone repeats every 2 m. At 5.6 m that is about 2.8 tiles; the crack motifs and the phantom repeat, which is noticeable at 4× only.

### 3.4 Cohesion
- **B:** sits best with the starter village. It uses only kit textures, and its cobbles echo the stair landings literally.
- **C:**
  - its stone is close to the retaining walls in mean value (centre shot: L* 24.4 against 25.8), but busier (std 11.8 against 4.6);
  - it is acceptable, since the plinth is small, but it is the one bevelled surface in a flat village.
- **H4:** does **not** sit with the starter NPCs or the environment. It is darker, more outlined and more detailed than every other character (#5). H2 is closer, but is still a different style.

### 3.5 Attribution (A→B vs B→C), from `cottage_attr.json`
| Region (gameplay 1:1) | A→B mean ΔE / % pixels changed | B→C mean ΔE / % pixels changed |
|---|---|---|
| Whole cottage | **6.61 / 38.9 %** | 1.21 / 7.4 % |
| Plinth | 18.5 / 91.9 % | 13.8 / 76.6 % |
| Upper wall | 12.1 / 41.7 % | 0.8 / 7.4 % |
| Window | 22.9 / 75.7 % | 3.3 / 30.6 % |
| Roof | 7.1 / 51.3 % | 0 / 0 |

- **About 85 % of the visible change, and nearly all of the improvement, is A→B (modelling).**
- **B→C** amounts to:
  - **the plinth material**, a modest gain at 2×: calmer, larger-unit masonry, and the hero's head reads better in front of it (+5.9 edge luma);
  - **the window glass**, a loss at 2× and a mixed result at 4×.
- **Is B→C worth having?** Only the stone, and only after the u = 0 fix. The glass is not.

---

## 4. Adopt / don't adopt

| Element | Recommendation | Reason |
|---|---|---|
| **B geometry** | **ADOPT** | It is the real improvement, and it reads at 2×: windows, plinth, framing, vertical grain, hidden faces removed, collision byte-identical. Pair it with fix #11 for the neighbouring roofs. |
| **C stone** (`stone_b_seamfix`) | **ADOPT after a ~20 px fix (#8)** | It reads as masonry at 2× better than the dotted cobbles, and it gives the hero a cleaner backdrop. Without the fix, a phantom joint shows every 2 m at 4×. |
| **C window glass** (`window_a_glass`) | **DON'T ADOPT** | It is weaker at 2× (pane L* 22.6 against 10.4) and shows a misregistered inner frame at 4×. B's flat dark pane is better; add a glint by hand if wanted. |
| **Roof fix** (starter shingles, slope UV at 32 px/m) | **ADOPT** | Upright (identical in orientation to A), cohesive. Bring the other kit roofs to 32 px/m (#11). |
| **H2** | **ADOPT as the working base only. Don't ship it as the player sprite.** | The repairs are real: idle, rhythm, identity, red cleanup. Its gameplay readability is still below H0 (#3). |
| **H3** | **DON'T ADOPT** | Moss lowers torso separation at every spot (#4). Metrically, it changes nothing. |
| **H4** | **DON'T ADOPT** | Its silhouette gain is real only on light ground. It loses the head on the dark wall (#1), collapses the interior to 40–51 % black (#2), still trails H0 on costume separation (#3) and moves further from the NPC style (#5). By the owner's rule it is worse in gameplay at the cottage spot, so it is rejected. |

---

## 5. Overall art verdict

**Cottage: PASS.** Adopt B's geometry with the starter roof, and C's stone once its one column is fixed. Keep B's dark panes. The gain is modelling: PixelLab contributes one texture, at about 15 % of the visible change.

**Hero: FAIL. No candidate beats H0 at gameplay scale on a fair measure.**
- **H2** is a correct repair of Stage 1's animation and identity defects, and the right base to keep.
- **H4's** "legible" result is mostly the edge metric reading a darker ring. At 1:1 the figure becomes a dark mass:
  - its head vanishes against dark walls;
  - its face and legs lose definition;
  - it leaves the starter NPCs' style further behind.
- **Next step:** fix readability through **value and hue structure**, not outline darkness:
  - a light, distinct tunic, away from grass and dirt;
  - a separate trouser value;
  - a larger or brighter face read;
  - a single `#392a23` outline.

  Then re-measure with region and face contrast, not only edge steps.
