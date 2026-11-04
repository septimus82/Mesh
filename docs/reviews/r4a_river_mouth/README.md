# Rivers R4A evidence (#461): mouths, round ends, shoreline sinking

This is evidence only and isn't for merge. All frames are real 1280×720 hidden-window renders, of Mesh Studio's 3D view or of Play.

- **Before:** the R3 code at `f552d6f`.
- **After:** R4A, captured at `c25b650`. The final head `277ea54` only removes a refusal (the trench check), so nothing drawn or carved here changes.
- **Cameras:** each before/after pair uses the same camera.
- **The Lakeside frames** come from a fresh scratch copy of `D:\Games\Lakeside Village`. The original is read only and never changed. In that copy:
  - the narrow lake arm ("Puddle 2") is removed;
  - R1's brook course is added, ending inside the main lake at its level (−13.25 px);
  - the brook's bed is carved and its plants cleared with the ops, as Studio's buttons do;
  - after only: `mouth: "auto"` and `ends: "round_source"` are set, then the bed is carved.

The tools are in `tools/`. Every output path is checked by `tools/scratch_guard.py`.

## A. Lakeside: the brook entering the lake
| Picture | What it shows |
|---|---|
| `A1_lakeside_mouth_angled_before_after.png` | Studio, 40° camera, cropped 2×. **Before:** the brook's square end lies over the lake as a second, lighter layer. **After:** one surface, with the brook easing into the lake's colour. |
| `A2_lakeside_mouth_top_down_before_after.png` | Top-down, cropped 2×. Before, the square end and its overlap inside the lake are visible. After, there is none. |
| `A3_lakeside_play_gameplay_camera_before_after.png` | Play's own follow camera, from the bank above the mouth. |
| `A4_lakeside_source_end_before_after.png` | The brook's source, top-down. Before: a square end, with its carved bank showing as a bare dirt patch past it. After: a half-circle end, carved as a bowl, with no trough past it. |
| `A5_lakeside_mouth_flow_three_frames_half_a_second_apart.png` | Flowing into still water. The renderer drew three frames with the camera held and the water's clock 0.5 s apart. Between frames 1 and 2, **24%** of the brook's pixels upstream change (the current drifts). In the lake **3.4%** change, which is its slow glints; on the still bridge 4.7% change (reeds swaying beside it). |
| `A6_lakeside_brook_overview_before_after.png` | The whole brook and lake, 48° camera. |

## B. A pond with a grassy bank (the R4 study village, `tooling/r4_river_mouth_study.py`)
The pond's bed is sculpted 0.4 m deep in the middle.
- **Left:** the stream with its mouth off. Its square end and its water lie over the pond as a second layer, and the pond's earth lip runs across it.
- **Right:** with **Into the pond** on. One surface:
  - the lip stops at the stream;
  - its bed eases to the pond's own depth just inside the shore, so the stream shallows as it meets the pond;
  - nothing is dug into the pond.

Both frames use the same code (the R3 code has no `ends` setting to build this scene with).

## C. The floating shoreline (R3 follow-up 1)
A stream is drawn 0.25 m above the village's ground, as Studio draws one. Beside it, between two of its points, is a dip about 0.4 m deep. Then **Carve the bed** is run.
- **Before (R3):** sinking measured the ground only at the control points, which are on flat ground. The water was set to −1.6 px and stood over the dip, with no bank: its edge fades onto the grass.
- **After:** sinking checks both sides every 0.25 m, half a metre out, at the corners of that terrain cell outside its own water. The water goes to −15.6 px, under the dip, and lies within visible earth banks.
- **The cost:** the fix is conservative. The whole stretch, and every point downstream, is lowered.

## Measurements (`report.json`)
- **Carving the Lakeside brook:** 187 ms before, 204 ms after.
- **Lakeside play frame (median of 60):** 21.1 ms before, 18.7 ms after. This is the same machine, but not a benchmark.
- **Per frame:** no river buffers are made while drawing. A test checks this.

## Independent review (four rounds, fresh agents)
**Round 1 (`51fb208`)** found 2 blockers.
- **The pond's channel was walkable:** the carved bed ran on into the pond as a walkable 0.7 m trench.
- **Carving twice re-sank the river.**
- **Should-fix:**
  - seams at classic ponds and at slanted shores;
  - a bank allowed in the pond before the mouth;
  - a level drop just before the shore that escaped the check;
  - flag-gated ponds;
  - `ponds_of` robustness.

**Round 2 (`de04f50`)** found that round 1's fix for the trench (treating it as deep river water) left a hidden barrier in walkable ponds.
- Now the pond's own rule holds in the pond.
- Carving digs nothing into the pond, and the bed eases to the pond's depth at the shore.
- Sinking reads its own bank, not its bed.
- Also fixed: the dict form of "Show when", and ties between overlapping ponds.

**Round 3 (`adddade`)** found three things, all fixed in `c25b650`:
- a meander with close limbs re-sank at every carve;
- a bed carved before the mouth was turned on stayed in the pond;
- a pale waterline strip at the shore.

**Round 4 (`c25b650`)** found that the check refusing that late mouth also refused uncarved joins into sculpted bowls, Lakeside's size included.
- The check was removed in `277ea54`.
- A bed carved first stays in the pond as deeper pond water, walked by the pond's rule (depth rules for ponds belong to R4B).

## Tests (at `277ea54`)
- **`tests/test_river_mouth.py`:** 18 fast tests.
- **`tests/test_river_mouth_gpu.py`:** 4 real-window tests.
  - **Studio coverage:**
    - one layer in the pond, with a mouth-off control;
    - the pond's bank not drawn where the stream enters, compared point by point against bare ground;
    - the round source;
    - drawn = `RiverIndex` water up to the shore;
    - no river allocation while drawing;
    - the panel buttons, with undo and redo.
  - **A slanted-shore seam test.**
  - **Play:** wading down the stream and on into the pond.
  - **Export parity.**
- **17 mutations, all caught** (`tools/mutate.py`).
- **Local:**
  - `pytest -m fast`: 5402 passed, 8 skipped;
  - river, water, world and scatter suites with GPU: 218 passed;
  - ruff and mypy gates OK.
