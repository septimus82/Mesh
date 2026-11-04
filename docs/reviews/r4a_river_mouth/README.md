# Rivers R4A evidence (#461): mouths, round ends, shoreline sinking

This is evidence only and isn't for merge. All frames are real 1280×720 hidden-window renders, of Mesh Studio's 3D view or of Play.

- **Before:** the R3 code at `f552d6f`.
- **After:** R4A at the PR head `51fb208`.
- **Cameras:** each before/after pair uses the same camera.
- **The Lakeside frames** come from a fresh scratch copy of `D:\Games\Lakeside Village`, which is read only and never changed. In that copy:
  - the narrow lake arm ("Puddle 2") is removed;
  - R1's brook course is added, ending inside the main lake at its level (−13.25 px);
  - the brook's bed is carved and its plants cleared with the ops, as Studio's buttons do.
- **After only:** `mouth: "auto"` and `ends: "round_source"` are set.

The tools that made these frames are in `tools/`. Every output path is checked by `tools/scratch_guard.py`.

## A. Lakeside: the brook entering the lake
| Picture | What it shows |
|---|---|
| `A1_lakeside_mouth_angled_before_after.png` | Studio, 40° camera, cropped 2×. **Before:** the brook's square end lies over the lake as a second, lighter layer. **After:** one surface, with the brook easing into the lake's colour. |
| `A2_lakeside_mouth_top_down_before_after.png` | Top-down, cropped 2×. Before, the brook's square end and its overlap inside the lake are visible. After, there is none. |
| `A3_lakeside_play_gameplay_camera_before_after.png` | Play's own follow camera from the bank above the mouth. The lighter overlap patch beside the bridge is gone. |
| `A4_lakeside_source_end_before_after.png` | The brook's source, top-down. Before: a square end, with its carved bank showing as a bare dirt patch past it. After: a half-circle end, carved as a bowl, with no trough past it. |
| `A5_lakeside_mouth_flow_three_frames_half_a_second_apart.png` | Flowing into still water. The renderer drew three frames with the camera held exactly and the water's clock 0.5 s apart. Between frames 1 and 2, **26%** of the brook's pixels upstream change (its current drifts). In the lake only **3.5%** change, which is its slow glints, and about the same changes on the still bridge (4%: the reeds swaying). |
| `A6_lakeside_brook_overview_before_after.png` | The whole brook and lake, 48° camera. |

## B. A pond with a grassy bank (the R4 study village, `tooling/r4_river_mouth_study.py`)
Lakeside's lake uses the sculpted ground as its shore, so it has no drawn bank. This scene shows a pond whose bank is drawn: an earth lip and reeds.
- **Left:** the stream with its mouth off. This is what R3 drew.
- **Right:** with **Into the pond** on.
- **The difference:** with the mouth off, the pond's earth lip runs across the stream and the square end shows inside the pond. With it on, the lip stops at the stream, there's no end inside the pond, and the stream's middle runs on as a deeper channel.

These two frames come from the same code with the mouth off and on. The R3 code can't build this scene, because it has no `ends` setting.

## C. The floating shoreline (R3 follow-up 1)
A stream is drawn 0.25 m above the village's ground, as Studio draws one. Beside it, between two of its points, is a dip about 0.4 m deep. Then **Carve the bed** is run.
- **Before (R3):** sinking measured the ground only at the control points, which are on flat ground. The water was set to −1.6 px and stood over the dip, with no bank: its edge fades onto the grass.
- **After:** sinking checks both sides every 0.25 m. The water goes to −14.17 px, under the dip, and lies within visible earth banks.
- **The cost:** the fix is conservative. The whole stretch is lowered, and every point downstream too, because the level still falls only downstream.

## Measurements (`report.json`)
- **Carving the Lakeside brook:** 187 ms before, 182–185 ms after.
- **Lakeside play frame (median of 60):** 21.1 ms before, 18.6–19.9 ms after. This is the same machine, but not a benchmark.
- **Per frame:** no river buffers are made while drawing. A test checks this.

## Tests (at `51fb208`)
- **`tests/test_river_mouth.py`:** 10 fast tests.
  - joining, and how it's stored;
  - each refusal: no pond, end not wholly in, crossing twice, 0.25 m above or below, flowing out of the pond;
  - an angled join, and two ponds at their own levels;
  - `RiverIndex` agreeing with what is drawn: the pond and the caps;
  - the bowl, and no trough;
  - a dip between points, and a mouth never sunk below its pond;
  - a neighbour's bed not measured;
  - older rivers unchanged, and the mouth limit;
  - a pond moved away.
- **`tests/test_river_mouth_gpu.py`:** 3 real-window tests.
  - **Studio coverage:**
    - one layer in the pond, with the mouth-off control;
    - the pond's bank not drawn where the stream enters;
    - the round source;
    - drawn = `RiverIndex` water at over 400 grid points around the source and the mouth;
    - no river allocation while drawing;
    - the panel buttons, with undo and redo.
  - **Play:** wading down the stream and on into the pond, with no barrier at the shore.
  - **Export parity.**
- **Ten mutations, all caught:**
  - river water drawn in the pond;
  - the pond's bank drawn over the stream;
  - the round cap not drawn;
  - `RiverIndex` keeping water in the pond;
  - sinking only at the points;
  - a neighbour's bed measured;
  - a mouth sunk below its pond;
  - no bowl;
  - a level mismatch not refused;
  - two crossings not refused.
