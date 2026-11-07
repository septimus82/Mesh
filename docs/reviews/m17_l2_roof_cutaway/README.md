# M17-L2: HD-2D roof cutaway, investigation and proposed correction (evidence only; no implementation)

**Scope:** Stage 1 investigation, Stage 2 baseline and Stage 3 proposal, as the owner asked. **No engine change.**
The `P` images come from a scratch prototype of the proposed rule. It was patched into the capture process only, and
no engine file was changed.

| | |
|---|---|
| Engine | `redesign/visual-editor` at `f9f1f81` |
| Evidence branch | `review/m17-l2-cutaway` (this folder only; never merged) |
| Project | scratch copy of the installed `D:\Games\Lakeside Village` (L1b; `lakeside.json` sha256 `dd850648…2213`). The original was not modified. |
| Machine | RTX 4070, hidden windows only |

**Recorded discrepancy, not changed in L2:** `tooling/lakeside_village.py` still generates the pre-L1b Lakeside scene.
The installed scene is L1b (`dd850648…`).

## 1. Stage 1: how the cutaway works today

- **Data:** `settings.hd2d.structures[].cutaway: bool` (`engine/hd2d/settings.py:52`), opt-in per structure. It is set
  by `project_ops.set_structure(cutaway=…)` and Studio's "See-through in play" toggle (`studio_hd2d.py:2663`). The
  starter template marks its cottage and shop. Lakeside marks `cottage`, `cottage_2` and `shop`.
- **Render:** `MESH_FS` (`engine/hd2d/renderer.py:42-59`) discards a fragment of a cutaway structure (`u_cut == 1`)
  when all of these hold:
  1. it is above the followed character's floor + 0.05 m;
  2. it is nearer the camera than that character's chest minus 0.2 m, along the camera-to-chest line;
  3. it is within `CUTAWAY_RADIUS` = **1.3 m** of that line. The chest is `CUTAWAY_HEIGHT` = 0.9 m above the feet
     (`renderer.py:266-267`).

  The uniforms are set per frame in `_bind_cutaway` (`renderer.py:1087`), only in play. Studio's edit view and
  non-cutaway structures are never cut. The ground, scatter, characters, shadows (`lighting`), precipitation shelters
  (`precipitation.py:12`) and water are untouched.
- **Shape:** a world-space cylinder round the sight line. On screen it is a disc round the chest: 1.3 m = 83 px
  radius at 720p (64 px/m). The player sprite is 1.0 × 1.5 m (64 × 96 px), so **the hole is 2.6 times the sprite's
  width**. It is centred on the chest, not the sprite's middle.

## 2. Why it removes too much (answering Stage 1 question 3: a combination)

1. **An over-broad cutoff:** the 1.3 m radius is wider than the character on every side.
2. **No screen-space visibility check:** a fragment is cut because it is near the sight line, not because it covers
   the character's pixels. Roof beside a fully visible player is removed (§3: a3, b1, b5, v4, and the indoor-camera
   partly-hidden shot).
3. **A cylinder, not a cone:** at fixed world width, fragments nearer the camera project larger, so the hole grows on
   screen with the occluder's distance in front of the player.
4. **The binary discard** leaves a hard edge and shows the building's dark interior faces as a rim (#458 C2).

World-space proximity alone isn't the cause: the "in front of the player" test is correct. Buildings behind the
player are never cut (a1, d1, d4: 0 px).

## 3. Stage 2: baseline (`before/`, `data/report_before.json`, harness `scripts/cut_capture.py`)

Each shot places the player's feet at a fixed spot (`scripts/shots.json`), resets the wind and water clocks and runs
150 frames. It checks that no door was taken, then saves the frame with the cutaway (`__cut`) and without it
(`__nocut`: what hides the player). It reads the player back drawn flat against the world's depth: unoccluded, with
the cut, and without.

Two separate full runs gave identical figures for every shot. The frames with the cutaway off are byte-identical
between the baseline and prototype runs.

| Shot | What | Visible without cut | Visible with cut | Cut px | Cut px outside the player's box +16 px |
|---|---|---|---|---|---|
| a1 | in front of the cottage | 1.0 | 1.0 | 0 | 0 |
| **a2** | **beside the shop (audit v1)** | 0.33 | 1.0 | 11,288 | **6,842** |
| **a3** | **east of the cottage, level with the roof** | **1.0** | 1.0 | **1,151** | 1,151 |
| b1–b5 | walking behind the cottage, W→E | 1.0 / 0 / 0 / 0 / 1.0 | 1.0 / 1.0 / 1.0 / 0.91\* / 1.0 | 497 / 21,106 / 24,616 / 20,514 / 483 | 497 / 13,354 / 16,864 / 13,354 / 483 |
| c1 / c2 | partly / mostly hidden behind the cottage | 0.15 / 0 | 1.0 / 1.0 | 17,418 / 21,562 | 11,638 / 14,014 |
| d1–d4 | shop: front, doorway, **inside**, out again | 1 / 1 / 0.26 / 1 | 1 / 1 / 1 / 1 | 0 / 4,642 / 15,504 / 0 | 0 / 4,370 / 10,435 / 0 |
| e close | close preset (35°, 7.5 m view): beside / partly / behind | 0.32 / 0.36 / 0 | 1 / 1 / 1 | 25,526 / 36,158 / 56,554 | 18,080 / 28,246 / 43,224 |
| e wide | wide preset (40°, 18 m view) | 0.41 / 0.68 / 0 | 1 / 1 / 1 | 3,509 / 3,922 / 7,998 | 1,679 / 2,032 / 3,948 |
| e indoor | indoor preset (55°, 7.5 m view) | 0.78 / **1.0** / 0.32 | 1 / 1 / 1 | 15,306 / **6,472** / 40,118 | 12,246 / 6,472 / 31,518 |
| v1–v4 | template village: front of the cottage, behind, **inside the shop**, **beside the shop** | 1.0 / 0 / 0.26 / **1.0** | 1 / 1 / 1 / 1 | 0 / 25,089 / 16,625 / **3,352** | 0 / 17,223 / 11,435 / 3,352 |

\* In b4 a lamp post's head, which isn't marked cutaway, stands in front of the player's legs, with or without any
cut.

v1's first spot stood on the village's "Door to Cottage" trigger, so the game entered the cottage while settling. It
was moved clear of the door, and the harness now asserts that the scene is unchanged.

**Findings:**
- Today's cutaway always reveals the player, but it cuts roof that hides nothing in **6 shots** (483–6,472 px).
- Where a cut is needed, **48–80% of the cut lies outside the player's box**.

## 4. Stage 3: proposed correction (smallest architecture-compatible change)

### The rule

A fragment of a structure marked `cutaway` is discarded in play **only if it lies in front of the character inside
the cone from the camera through the character's own on-screen box**. In detail:
1. **In front (unchanged):** nearer the camera than the character along the eye-to-target line, by more than 0.2 m.
2. **Inside the character's on-screen box** (new; replaces the 1.3 m cylinder):
   - The fragment's offset from the sight line is measured across (the camera's right) and up (perpendicular to the
     line), then scaled to the character's distance (`reach / along`). That is exactly the picture's projection, at
     any camera distance or pitch. An orthographic camera uses its forward direction and no scaling.
   - The box is the sprite's own width × height, grown by a **0.25 m margin**, with **0.3 m rounded corners**,
     centred on the billboard's middle. An upright billboard stretched by 1/cos(pitch) projects to exactly its own
     height across the sight line.
3. **Above the character's floor + 0.05 m (unchanged).**

Target: the followed character, as today. Other targets are out of scope.

**Implementation boundary:**
- `engine/hd2d/renderer.py` only:
  - the cutaway block in `MESH_FS`, plus three uniforms (camera right, box half-size, corner radius) and an
    orthographic flag;
  - `_bind_cutaway` sets the box from the followed sprite.
  - `CUTAWAY_RADIUS` and `CUTAWAY_HEIGHT` become `CUTAWAY_MARGIN` = 0.25 and `CUTAWAY_CORNER` = 0.3.
- Wording in `settings.py:51` and the `set_structure` docstring.
- No other file, setting, operation or Studio control changes.

### Prototype evidence (`prototype/`, `data/report_prototype.json`, `data/comparison.json`, `sheets/`)

The prototype is exactly the rule above, patched into the capture process.

| | Today | Proposed |
|---|---|---|
| Player visibility with the cut | as in §3 | **identical in all 27 shots** |
| Cut where nothing hides the player (a3, b1, b5, indoor partly hidden, v4) | 483–6,472 px | **0** |
| Doorway (d2, player not hidden; awning edge and post inside the margin) | 4,642 px | 1,899 px (see limits) |
| Hole size where a cut is needed | | **43–64% smaller** |
| Cut outside the player's box +16 px | | **65–93% less** |
| Camera presets (close, wide, indoor) | | same behaviour: revealed, smaller, confined |

**Sheets:** each shows 1:1 crops, cutaway OFF (what hides the player) | NOW | PROPOSED. For example:
- [a2 beside the shop](sheets/a2_beside_shop.png)
- [b3 behind the cottage](sheets/b3_behind_cottage_x608.png)
- [c1 partly hidden](sheets/c1_partly_hidden.png)
- [d3 inside the shop](sheets/d3_inside_shop.png)
- [d2 doorway](sheets/d2_shop_doorway.png)
- [a3 beside the cottage](sheets/a3_beside_cottage_east.png)
- [close preset](sheets/e_close_behind_cottage.png)
- [wide preset](sheets/e_wide_behind_cottage.png)
- [indoor preset](sheets/e_indoor_behind_cottage.png)

### Effects

- **Silhouettes:** roofs and walls stay whole unless they actually stand between the camera and the character's
  box. When a cut is needed, it is a character-sized window (rounded rectangle) instead of a disc 2.6 times the
  character's width.
- **Movement:** continuous. The window follows the sprite every frame, and its overlap with a roof grows and shrinks
  smoothly as the player walks behind it (b1→b5: 0, window, window, window, 0). There is no popping, because there
  is no on/off decision, only geometry. Entering and leaving a building (d1→d4) behaves the same.
- **Camera angles, distances, building heights, roof types:** the test is per fragment and projection-exact, so it
  doesn't depend on the mesh. It was checked at four camera presets.
- **Indoor/outdoor:** interiors that are separate rooms (`cottage.json`) have no cutaway structures and are
  unaffected. Walk-in buildings in the same room (the shop) work: inside, a narrow window opens through the roof and
  front wall.

### Performance

- About 10 ALU operations more per fragment, on cutaway structures only.
- Three more uniforms per frame.
- No new pass, no read-back, no CPU geometry.

### Compatibility

- No schema or serialized-data change. `cutaway: true` keeps its meaning (the part between the camera and the
  player isn't drawn).
- Existing scenes reveal the player exactly as before. Roofs that hide nothing stay intact, and windows are smaller.
- Studio's edit view is unchanged (never cut).

### Regression tests required

1. **GPU** (`tests/test_hd2d_cutaway_gpu.py`, `MESH_GL_SMOKE`):
   - the four existing spots keep passing, with the reveal tightened to ≥ 0.99 where nothing unmarked is in the way;
   - **new:** beside the shop and at the cottage's corner, where nothing is hidden, the cut changes **0 px**;
   - **new:** behind and inside, **every changed pixel lies inside the player's on-screen box + margin** (+2 px
     tolerance);
   - **new:** the same at the close, wide and indoor presets.
2. **Headless:** a small CPU twin of the rule (Python mirror), unit-tested on simple cases:
   - in front and inside the box: cut;
   - beside: kept;
   - behind the player: kept;
   - below the floor: kept;
   - a near occluder versus a far one: cone scaling.
3. **Unchanged and rerun:** `test_hd2d_cutaway.py` (setting and operation), `test_hd2d_starter_template.py`,
   `test_weather_collisions_gpu.py`, and the full CI and Extended runs.
4. **Acceptance:** this folder's 27 shots, rerun with the implementation:
   - visibility at least today's in every shot;
   - 0 px where nothing hides the player (d2 within the margin residual, or 0 if the margin is tuned);
   - cut outside the box at or below the prototype's figures;
   - frames with the cutaway off byte-identical;
   - owner visual sign-off on the sheets.

### Limits and exclusions

- **The margin's cost:** in d2 the player is fully visible, but the awning edge and front post within 0.25 m of the
  sprite box are still cut (1,899 px). A 0.15 m margin would shrink this; the value is a tuning choice at
  implementation.
- **Unchanged:** the hard edge and dark interior rim (binary discard), because a dithered or soft edge is a separate
  visual decision. Characters other than the followed one stay hidden behind roofs, as today.
- **The sprite box is conservative:** it uses the sprite's full frame, including transparent padding.
- **Excluded:** no new targets, edge softening, interior-rim treatment, settings, authoring, Studio controls, or
  shadow, precipitation or water changes; no scene, asset or generator edits; no broad renderer change.
