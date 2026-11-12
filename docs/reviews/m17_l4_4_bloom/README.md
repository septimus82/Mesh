# M17-L4-4: selective bloom, evidence

Evidence for the draft PR on `feature/m17-l4-4-bloom`. This branch holds only this folder and is **never to be
merged**. Every picture is a real engine frame (hidden windows; nothing on screen), the renderer's final picture
(`draw(read_final=True)`) at 1280×720 on the RTX 4070 unless marked otherwise. Lakeside is the scratch copy of the
installed L1b village (`lakeside.json` sha256 `dd850648…`, byte-identical to `D:\Games\Lakeside Village`, never opened
for writing), with the L4A time-of-day variants and two more made for this milestone (`data/scenes/`):
`lakeside__l4b_evening_lamps` (the evening variant with the night variant's lamps lit: Lakeside ships its lamps off) and
`cottage__l4b_night_hearth` (the cottage interior at night with a campfire placed as a hearth through `project_ops`).

## What it is

`settings.hd2d.bloom` (engine/hd2d/bloom.py) is off in every room until chosen. When on, the world's framebuffer gets a
second colour attachment that every world shader writes its own **emission** into (unclamped, linear; zero for
everything that doesn't emit), and the glow is made from that, never from the 8-bit picture: so a lantern glows and a
white wall, the sky or sunlit grass doesn't. Lamps' light on surfaces is illumination and never glows; nor do the HUD
and Studio's lines (drawn after the picture is made).

| Preset | Strength | Threshold | Spread |
|---|---|---|---|
| Subtle | 1.0 | 0.25 | 0.5 |
| Warm | 2.0 | 0.1 | 0.65 |
| "full" (evidence only: shows everything it does) | 3.0 | 0 | 0.8 |

## Pictures (`sheets/`, full frames in `frames/`, close crops in `sheets/crops/`)

| Sheet | What it shows |
|---|---|
| `lakeside_day_off_vs_warm.png` | Four Lakeside shots by day: off and Warm. **Byte-identical**: nothing emits by day (its lamps are off), and bright sky, walls, paths and grass never glow |
| `lakeside_evening_lamps.png` | Evening, lamps lit: off, Subtle, Warm |
| `lakeside_night_lamps.png` | Night, lamps lit: off, Subtle, Warm, full |
| `interior_hearth.png` | The cottage interior at night with a hearth: off, Subtle, Warm, full. The firelit wall above it, near white, doesn't glow |
| `interior_lamp_light_never_glows.png` | The interior lit by its ceiling lamp (which has no visible emitter): off and Warm, byte-identical |
| `template_village.png` | A fresh HD-2D template village (its two lamp posts lit) by day and at night: off, Subtle, Warm, full |
| `campfire.png` | M23B's clearing at night: a campfire's flames and embers and a torch |
| `emission_maps.png` | Frames beside the world's emission buffer: only lamp glass, flames and embers emit |
| `walking.png` | The player walking (the camera following), off and Warm at four points |
| `combined_evening.png`, `combined_night.png` | Bloom, haze + grade, bloom + haze + grade, depth of field, all four |
| `studio.png` | Mesh Studio's editing view: off, Subtle, typed values, with haze and grade |
| `crops/*.png` | 3× close-ups (nearest) of the strongest glows and of a patch of ordinary materials far from every emitter, off / Subtle / Warm / full |

`data/frame_changes.txt`: per Lakeside frame, how many pixels each look changed. With bloom off every frame is
byte-identical to the baseline captured before L4-3 (13 of 13).

## Correctness (`data/study_report.json`, `data/studio_report.json`: tooling/hd2d_bloom_study.py and _studio.py)

- **The emission is the emitters'**: in the template village at night, 720 emission pixels, every one inside a lamp head's
  box; ground, walls, characters and grass emit nothing. By day with the lamps off, and in the cottage interior (its
  surroundings are the backdrop, where nothing is drawn), the emission is zero everywhere and the picture is byte-identical
  under the strongest glow.
- **Hidden behind what stands in front**: a character (scaled up to cover a lamp head from the game's camera) in front
  of a lamp head: no emission under it; with the character aside, those pixels emit.
- **The prefilter is the CPU's maths**: each emission texel's threshold, soft knee and cap (luminance 4), averaged over
  exactly the texels each 360-line pixel covers, matches the GPU's level within 1-2% (the float target's precision); with
  a strong haze, each texel dimmed by the haze at its own depth, likewise. Lamps twelve times as strong (emission 5.1) are
  capped at 4.
- **The glow holds the light that passed** (0.96-0.99 of it: the float format's rounding), and the picture is its
  original bytes farther than 40% of the picture's height from every emitter. Spread 0.9 puts 64% of the glow farther than
  6 level pixels from an emitter; spread 0.2, 0.7%.
- **Moving camera**: the glow's light over the light that passed stays within 0.975-0.977 over every walking frame;
  repeated frames are identical.
- **Picture size**: the same view at 960×540 and 1920×1080 gives the same glow (correlation 0.988, energy within 4%).
- **Known texels through the real composite**: no glow is the texel exactly; the glow is added in linear light; after the
  haze; before the grade (grade(texel + glow), not grade(texel) + glow); clipped at white.
- **The HUD**: 3,168 opaque HUD pixels identical under the strongest glow. **Studio's lines**: drawn after the composite,
  the same pixels as without bloom (within 1 level: off draws them into the world, on over the picture).
- **Driver refusal** (its program, or its framebuffer): bloom off, the reason kept; with the haze on too, the haze's
  picture exactly.
- **Lifecycle**: nothing made while off; made on the first frame (the emission target and the chain); a new picture size
  remakes them (none leaked); off frees everything of it (the shared composite's program stays, as for the haze).
- **Studio**: the presets and fields, values out of range refused and put back, undo/redo, the game's path drawing Studio's
  view byte for byte, off giving the original view, play, save, reopen, export, and a malformed block shown and repaired.

## Mutations (`data/mutations.json`): 14 of 14 caught

Each realistic defect applied alone (files restored byte for byte after each), the named test failing:

| Mutation | Caught by |
|---|---|
| threshold ignored (everything passes whole) | the prefilter against the CPU's maths |
| ground writes its colour as emission | emission outside the emitters |
| characters drawn without the emission attachment | the emitter behind a character |
| emission not cleared each frame (the sky's colour left there) | the backdrop never glows |
| glow added after the grade | known texels, order |
| glow added in sRGB | known texels |
| haze doesn't dim it | the haze's per-texel dimming |
| one tap instead of the area average | the prefilter against the CPU's maths |
| spread inverted | spread reaches farther |
| no cap | one strong light is capped |
| kept when off | off frees everything |
| strength 0 still runs | strength 0 is the original picture, nothing made |
| Studio's view not updated | Studio glows its view at once |
| a hard-edged knee | the knee is smooth (fast test) |

## Performance (`data/perf_*.json`, `data/diag_*.json`, `scripts/perf_l44.py`, `scripts/perf_diag.py`)

Lakeside at night with its lamps lit, the same settled frame. Every mode interleaved in one process, the order rotated
each round, an untimed frame before every timed one (a mode's first frame after another makes or frees what it needs),
the first 10% dropped. RTX: GL timer query, 300-400 rounds. llvmpipe (Mesa 26.0.3, CI's pinned build): wall time round
`ctx.finish()`, 30 rounds.

| | RTX 720p | RTX 1080p | llvmpipe 720p |
|---|---|---|---|
| Bloom's own pass (prefilter + chain), alone | 0.15 ms | 0.07 ms | 5.0 ms |
| Composite with the glow vs the blit | 0.053 vs 0.031 ms | 0.038 vs 0.022 ms | 1.70 vs 0.62 ms |
| Whole frame, p50 (p95): off | 1.79 (4.36) ms | 1.91 (4.20) ms | 31.9 (33.6) ms |
| Whole frame, p50 (p95): Warm | 3.30 (8.15) ms | 3.48 (7.92) ms | 40.0 (42.6) ms |
| Whole frame, p50 (p95): haze + grade | 2.45 (5.46) ms | 2.52 (5.58) ms | 34.3 (36.1) ms |
| Whole frame, p50 (p95): bloom + haze + grade | 2.11 (5.26) ms | 2.26 (5.50) ms | 40.7 (43.4) ms |
| Whole frame, p50 (p95): bloom + haze + grade + DoF | 3.37 (8.30) ms | 3.53 (8.12) ms | 58.6 (61.2) ms |
| Walking, p50: off → Warm | 1.62 → 2.73 ms | 1.71 → 3.46 ms | 31.9 → 40.1 ms |
| CPU per frame, p50: off → Warm | 3.23 → 3.66 ms | 3.17 → 3.64 ms | (wall = CPU) |
| Turning it on: the first frame (programs compiled, targets made), CPU | 7.3 ms | 7.3 ms | 276 ms |
| Turning it off: the first frame (all freed), CPU | 5.4 ms | 5.2 ms | 32.8 ms |
| Draw calls: off / on / off again | 72 / 72 / 72 | 72 / 72 / 72 | 70 / 70 / 70 |
| GL objects: off / on / off again | 378 / 405 / 378 | 378 / 405 / 378 | 378 / 405 / 378 |
| Bloom's GPU memory: on (off: 0) | 6.1 MB | 10.8 MB | 6.1 MB |

**Where the whole-frame cost goes (RTX 720p, `diag_branch_*.json`, two runs):** off 2.35 / 2.37 ms; the world drawn with
its emission attachment and the composite reading a glow (chain skipped) 2.82 / 2.75 ms; full bloom 3.42 / 3.22 ms. So
about +0.45 ms for the emission attachment and +0.5 ms for the chain in a whole frame: more than the passes measured alone,
because this light scene lets the GPU clock down (P0 2520 MHz at the start of each run, P5 585-1875 MHz by its end:
DVFS, #460's finding). The modes are interleaved, so they share the same clock states: the deltas are comparable, the
absolute milliseconds vary between sessions. The GPU has ample headroom here (a 16.7 ms frame).

**Bloom off costs nothing** (`diag_base_*.json` vs `diag_branchoff_*.json`, alternating processes): the bloom-off frame
on the base (d473245) 5.60 / 5.09 ms, on this branch 4.97 / 4.59 ms (single-mode runs, clocked low: within noise, not
slower). The world programs' extra output is written to no attachment, and only glowing fragments work out an emission.

**Software GL** runs bloom (an explicit decision, as for the haze): +8 ms a frame (25%) on llvmpipe at 720p, of which the
pass is 5 ms and the composite 1.1 ms; turning it on compiles three programs (276 ms, once). The depth of field, at +16
ms, is bypassed on software GL; bloom isn't, because it is opt-in per room and a room should look the same on every
machine. CI's llvmpipe gpu lanes run every bloom test with bloom on.

## Limitations and remaining visual defects

1. **Hot cores shift hue.** An emitter already at full red (orange lamp glass) moves toward yellow-white under Warm and
   full as green and blue rise: the familiar look of an over-bright light, but a colour shift on the emitter's own pixels.
2. **Water doesn't reflect glow.** Water writes no emission (its reflection of a lamp doesn't bloom), and dims the
   emission beneath it by its opacity.
3. **The depth of field blurs the colour, not the glow's source**: an out-of-focus lamp's glow comes from its sharp
   emission (the glow is wide anyway).
4. **Thin emitters at different resolutions** rasterise a little differently (4% less glow at 1080p than at 540p for
   the lamp strips): the chain is resolution-independent, the emitters' coverage isn't exactly.
5. **Emission is display-referred**: Mesh's emitters (lamp heads ~0.5-0.8, flames up to ~0.9 luminance) are near white,
   so the threshold is a fine control over a short range, and strength is a gain (up to 3, capped).
6. **Software GL**: 25% more a frame on llvmpipe (above).

## Scripts (`scripts/`)

Scratch harnesses (not engine code); paths point at the session's scratch folder: `capture.py` (Lakeside frames per
shot, time and look), `evidence.py` (emission maps, walking, template, campfire), `sheets.py` (sheets and crops),
`perf_l44.py` and `perf_diag.py` (timing), `mutate.py` (the 14 mutations), `probe.py` (emission and glow statistics),
`mesa_preload.py` (local llvmpipe).
