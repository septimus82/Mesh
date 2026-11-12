# M17-L4-3: atmospheric depth haze, evidence

Evidence for the draft PR on `feature/m17-l4-3-haze`. This branch holds only this folder and is **never to be
merged**. Every picture here is a real engine frame (hidden windows; nothing on screen), drawn by the renderer at
1280×720 on the RTX 4070 unless marked otherwise. Lakeside is the scratch copy of the installed L1b village
(`lakeside.json` sha256 `dd850648…`, byte-identical to `D:\Games\Lakeside Village`, which was never opened for writing),
with the L4A time-of-day variants (evening, night with lamps).

## What it is

`settings.hd2d.haze` (engine/hd2d/haze.py) is off in every room until chosen. When on, each pixel moves toward a haze
colour by **its own depth** from the world's depth texture, measured along the view axis beyond the camera's focus
(the player in play; never within the player's own depth). It runs in the existing final composite, before the
colour grade, in linear light. Where nothing was drawn (the backdrop), and anywhere nearer than the onset, the texel is
kept exactly. The colour is lit by the room's own ambient light and sun.

| Preset | Strength | Colour (daylight) | Start | Falloff |
|---|---|---|---|---|
| Daytime | 0.25 | `#9fb0c4` | 4 m | 30 m |
| Evening | 0.30 | `#d4b4a4` | 4 m | 24 m |

`amount = strength × (1 − e^(−3x²))`, where `x = max(0, depth − onset) / falloff`. There is no corner at the onset,
and the haze is 95% of its strength at start + falloff.

## Pictures (`sheets/`, full frames in `frames/`)

| Sheet | What it shows |
|---|---|
| `lakeside_day_off_vs_daytime.png` | Four Lakeside shots by day: off and Daytime |
| `lakeside_evening_off_vs_evening.png` | The same shots in the evening: off and Evening |
| `lakeside_night_haze_is_dim.png` | At night the same haze is lit by the night: dim, no glow |
| `interior_unchanged.png` | The cottage interior: its camera sees about ±2.5 m of depth, all inside the start, and its dark backdrop is never hazed |
| `depth_maps.png` | Each frame beside the haze amount every pixel gets from its depth: roofs, trees, posts and grass tufts stand out unhazed against the ground behind them |
| `walking.png` | The player walking (the camera following): off and Daytime at three points along the way |
| `combined_day.png`, `combined_evening.png` | Haze, the grade and vignette, depth of field, and all together |
| `template_village.png` | The HD-2D template village (a fresh `mesh new` project) by day and at night: off, Daytime, Evening |
| `studio_vs_game.png` | Mesh Studio's editing view with the Haze section open, its renderer path with the game's camera, and the game's own frame |

`data/frame_changes.txt`: every Lakeside frame with haze off is byte-identical to the baseline captured before any
code change (`frames/baseline/`).

## Correctness (`data/study_report.json`, `data/studio_report.json`)

- **Every pixel's haze is the one its own depth calls for.** The share each pixel moved toward the haze colour (read back
  in linear light) is compared with the formula at that pixel's depth (read from the depth buffer). 99th-percentile
  error is 0.002–0.006 across the template village, Lakeside's cottage and posts, #459's fixture room, a walk and a
  flat camera; the largest single pixel is 0.017 (8-bit rounding). Pixels nearer than the onset are their original
  bytes exactly.
- **Off and strength 0 are the original picture, byte for byte, with nothing allocated.**
- **Characters:** the player is untouched (the onset is never within their depth: with start 0 it moves out to the
  character's depth + 1 m). A villager 6.3 m behind the player keeps 95% of their contrast (edges 94%) with Daytime
  and 89% (edges 88%) with Evening.
- **Known texels:** near depth gives the texel exactly. Far depth gives the linear-light mix (±1 level, alpha kept).
  Haze then grade equals the grade applied to the hazed texel (and differs from the other order).
- **Night:** the template village under Studio's night sun gives a haze light of at most 0.35 (vs 0.82 by day).
- **HUD:** 3,168 HUD pixels identical with the haze on. **Studio's lines** are drawn after the composite at the same
  pixels.
- **Studio and the game:** the game's camera path and Studio's path draw the same picture, byte for byte, with the same
  onset.
- **Driver refusal:** a refused composite program gives the original picture, with the reason kept.
- **Mutations** (`data/mutations.json`): 10 of 10 caught. They were depth replaced by screen height, the mix in sRGB,
  grade before haze, unlit haze, no character rule, uniforms reset every frame, the onset set once, Studio's view not
  updated, the block not read, and a linear ramp with a corner.

## Performance (`data/perf_*.json`, `scripts/perf_l43.py`)

Same settled Lakeside frame; every mode interleaved in one process, order rotated each round, first 10% dropped. RTX:
GL timer query, 300 rounds. llvmpipe (Mesa 26.0.3, CI's pinned build): wall time round `ctx.finish()`, 30 rounds.

| | RTX 720p | RTX 1080p | llvmpipe 720p |
|---|---|---|---|
| Final pass alone: blit → haze composite | 0.027 → 0.039 ms | 0.021 → 0.032 ms | 0.63 → 1.24 ms |
| Grade pass → grade + haze | 0.073 → 0.080 ms | 0.058 → 0.066 ms | 2.00 → 2.37 ms |
| Whole frame, p50: off → haze | 1.73 → 1.75 ms | 2.22 → 2.32 ms | 25.4 → 26.2 ms |
| Whole frame while walking, p50: off → haze | 0.78 → 0.82 ms | 1.31 → 1.36 ms | 26.1 → 27.1 ms |
| CPU per frame: off → haze | 6.31 → 6.29 ms | 6.71 → 6.75 ms | — |

- **New GL objects:** none. The composite holds the same program (and, with the depth of field, the same one chain
  target) whether the haze is on or not. The haze adds no pass, texture or framebuffer.
- **With the depth of field:** turning on haze or the grade over the DoF costs the same existing DoF→composite chain
  (one more full-picture pass, L4-1): +0.20 ms (haze) and +0.39 ms (grade) on the RTX at 720p. This isn't new to L4-3.
- **Software GL:** the haze runs there (+0.8 ms a frame, 3%), unlike the depth of field, which costs ~16 ms there and is
  bypassed. CI's llvmpipe gpu lanes run the haze tests and assert it is on.
- GPU clocks dropped from P0 toward P5 during the light RTX runs (DVFS, #460's finding): the interleaving keeps the
  modes comparable, but absolute milliseconds vary between sessions.

## Limitations and remaining visual defects

1. **At Lakeside's telephoto camera the haze mostly shows in the upper third.** The camera (fov 12°, 53.5 m) sees only
   about 8 m nearer and 12 m farther than the player, so the depth that reaches the haze is at the top of the frame. It
   is genuinely depth-based (the depth maps): tall near objects stay clear against hazed ground behind them. But on
   flat ground, depth and screen height coincide, so it can read as a soft band. That is inherent at this camera, not
   a screen gradient. Wider cameras show more.
2. **Interiors get nothing from the presets.** A small interior's whole depth lies inside the 4 m start, which is
   intended. A creator can lower the start.
3. **Dark pixels lift most** (the mix is in linear light, as real aerial perspective lightens distant shadows). This is
   why the presets start at 4 m.
4. **With the depth of field,** the haze uses the sharp depth on blurred colour. At a depth edge (a near post against
   the far meadow) the blur's halo takes the haze of whichever depth its pixel has. At these strengths it isn't visible
   in the captures.
5. **Water** is drawn without depth, so it hazes as its bed (a few centimetres off the shore beside it). Falling weather,
   embers and smoke haze as what is behind them.
6. **The haze's light** comes from the room's sun and ambient light only: a lamp-lit area at night doesn't brighten the
   haze around it.

## Scripts (`scripts/`)

These are the scratch harnesses used here (not engine code); paths point at the session's scratch folder.
- `capture.py`: Lakeside frames per shot, time and variant.
- `compare.py`: change summaries against off and the baseline.
- `evidence.py`: depth maps, walking, combined.
- `template_and_studio.py`: template village and Studio.
- `perf_l43.py`: timing.
- `mutate.py`: the 10 mutations.
- `chars.py`: per-character readability.
- `sheets.py`: the sheets.
- `mesa_preload.py`: local llvmpipe.
