# M17-L4-2: HD-2D colour grade, vignette and presets (evidence only, never merge)

**What this is:** the evidence for draft PR `feature/m17-l4-2-grade` on `redesign/visual-editor` `5407ff4`.
**Scenes:** the hash-verified scratch copy of the installed Lakeside Village L1b (`dd850648…`); the installed project,
its backup and the L1b scene are untouched. In-suite rooms are the HD-2D template's.
**Machines:** RTX 4070 (Windows 11), and Mesa 26.0.3 llvmpipe loaded locally from CI's pinned archive.

## Pictures

**`sheets/game_<shot>__<time>.png`:** Original / Natural / Golden hour / Moonlight / Interior warm.
- **Shots:** village crossroads, shore, bridge, cottage exterior (day, evening, night with lamps), and the interior.
- **Source:** the game's own frames (`frames_game/`).

**`sheets/studio_<shot>__<time>.png`:** the same, in **Mesh Studio's real editing view**.
- Its canvas region of the window, with its grid lines, aimed at the shot (Studio's camera = the game's).
- Each preset chosen with Studio's own control (`frames_studio_canvas/`).

**`sheets/closeup_<shot>__<time>.png`:** 2× crops per preset of the player sprite, the greenest vegetation, the
darkest region with detail, and (night) the lantern glass.

**`sheets/play_session.png`** (`play/`): a play session with movement.
- The same 180-frame walk (held arrow keys) from the same start, original and graded (Natural by day, Moonlight by
  night), the whole window (world + HUD) every 30 frames.
- The player took the same path; every graded frame went through the composite.
- The player's contrast was kept or slightly raised in every frame (`play/play.json`).

## Game / Studio

The two processes don't draw the same world state:
- the game placed the player for each shot, while Studio draws the room's spawn;
- the game's 120 settle frames advance the wind, while Studio's view holds plants still.

So the originals differ on 1–33% of pixels (`data/matched_report.json`), for those reasons only.

**The grade itself was compared:** on every pixel where the game's and Studio's *originals* agree, the graded frames
agree in **52 / 52 graded frames, 100% of those pixels** (`data/grade_parity.json`). It is one implementation.

**In-suite, in one process:**
- the game's camera path and Studio's path, with the sun's shadow map fitted alike (#485) and play's cutaway off: byte-identical;
- the graded offset canvas equals the same camera at an offscreen target's origin.

## Visual metrics (`data/lakeside_metrics.json`, `data/lakeside_summary.txt`)

**Coverage:** 16 Lakeside frames × 4 presets, each against the original.

| | crushed (+%, max) | clipped (+%, max) | character \|Weber\| change (min) | edge ratio (min) | grass hue (max °) | lamp glass hue (max °) | dark-area mean (min) |
|---|---|---|---|---|---|---|---|
| Natural | 0.323 (night only; day/evening ≤ 0.05) | 0.000 | −0.004 | 0.989 | 0.56 | 1.19 | 0.84 |
| Golden hour | 0.364 (night only; day/evening ≤ 0.06) | 0.000 | −0.008 | 0.981 | 4.0 | 0.60 | 0.83 |
| Moonlight | 0.060 | 0.000 | −0.007 | 0.994 | 8.9 (intended: cooler) | 0.43 | 0.96 |
| Interior warm | 0.025 | 0.000 | −0.006 | 0.999 | 4.7 | 0.46 | 0.99 |

**The first version** (`data/lakeside_metrics_v1_before_clip_limit.json`) added up to 0.17% clipped pixels on the
interior's lamp-lit planks. The no-new-clip limit fixed that (0.000 everywhere).

**In-suite** (template rooms, `data/post_study_first_run.json`):
- lamp glass hue ≤ 1.44°;
- E1 emissive swatches' hue ≤ 3.96° (warm presets);
- no added crush or clipping;
- vignette: centre identical, corners 0.65–0.81×;
- HUD pixels identical.

## Exactness (`exactness/`)

**Method:** `scripts/exact.py` on the scratch Lakeside (village / shore / cottage at authored / evening / night with
lamps, and the interior; each with and without DoF; Studio's canvas with and without its lines), compared against
L4-1's worktree (`ec3ade6`, whose tree is `5407ff4`'s).

| Run | Frames identical | Draw calls / GL objects / live objects |
|---|---|---|
| Off | 22 / 22 | the same |
| A preset at strength 0 | 22 / 22 | the same |

## Performance (`perf/`)

**Final stage alone** (same frame, interleaved, GL timer, RTX at P0):

| | blit | identity | grade |
|---|---|---|---|
| 720p | 0.0072 | 0.0072 | 0.0184 ms |
| 1080p | 0.0133 | 0.0143 | 0.0369 ms |
| llvmpipe 720p | 0.80 | 0.80 | 2.41 ms |

- **DoF chained into the grade:** DoF +0.02 ms (720p), +0.04 ms (1080p).
- **CPU:**
  - `configure()` per frame (unchanged settings): 0.1 µs;
  - on a change (all uniforms set): 24 µs, once per edit;
  - the pass's submission is 0.07 ms in the timing harness, which re-configures every round because it alternates
    modes; in real frames, 0.04 ms.
- **Memory:** the composite's 1 program, plus (with DoF) 1 RGBA8 frame-size target, as L4-1. Nothing when off.
- **Off, L4-1 vs L4-2** (`samemodes_*`, alternating processes, both orders): indistinguishable.
  - RTX GPU: 2.03–2.07 vs 2.01–2.31 ms (the 2.31 was the first run after a llvmpipe process).
  - llvmpipe: 27.67–27.99 vs 27.72–28.00 ms.
  - In base-first rounds L4-2 read ~0.05 ms slower; in L4-2-first rounds it read faster: run order, not code.

## Mutations (`data/mutations.log`)

- 15 caught, out of 14 planned mutations plus one semantic recheck.
- Deleting the highlight-protection line made the uniform unused, so it was caught by a crash, not a behaviour.
  Re-run as a semantic weakening (protection only above 0.995), it was caught by the direct texel test added for it.
