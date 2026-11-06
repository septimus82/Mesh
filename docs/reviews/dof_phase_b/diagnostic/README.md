# #475: what the in-frame "step" is — diagnostic (EVIDENCE ONLY, never merged)

The owner authorised one bounded, measurement-only diagnostic after the 16-vs-24 experiment (`../taps16/`). Product
code is unchanged (head `265b43a`): everything below was patched in scratch processes only.

**Answer: the step is the GPU's clock, not the frame's data.** The composite's GPU time is the same whether it reads
the live attachments, a fresh copy, or runs after the GPU idles, and whether it is the first or the second draw in
the frame. Its time follows the graphics clock the driver picks: about **0.7–0.76 million GPU cycles** per 1080p
frame at 24 samples, i.e. 0.36 ms at 2 GHz and 1.2–1.5 ms at 250–500 MHz. During these light benchmark frames the
GPU is 37–38% busy and its memory sits in the 810 MHz idle state, so the driver often drops the clock. A persistent
frame copy makes things worse: it adds about 0.58 ms.

Machine: RTX 4070, GL 4.6, Windows 11, hidden windows, Lakeside (start, shop, bridge), 1080p, 24 samples (product).
No clock locking or setting changes; read-only `nvidia-smi` sampling every 100 ms.

## Method (`scripts/diag.py`, run twice: `reports/run_a.json`, `run_b.json`)

GL timestamp counters, each recorded once all earlier GPU work has finished:
draw start → world done (just before the blit or the composite) → a mid mark per variant → draw done.
Each of 300 cycles (after 60 warm-up cycles) draws off then on for every variant, in an order rotated each cycle:

| Variant | What the composite does |
|---|---|
| live | the product composite, reading the world's live attachments |
| copy | colour + depth first copied (`glBlitFramebuffer`, as water's reflections do) into a persistent same-size framebuffer; the composite reads the copy |
| stale | the composite reads the copy made in the previous frame (not written this frame), then refreshes it |
| twice | the product composite drawn twice in the frame |
| finish | `glFinish` (GPU idle) just before the product composite: the "pass alone" condition, in the frame |

Every frame is joined to the nearest clock sample (within 150 ms). Correctness: copy, twice and finish give a picture
pixel-identical to live in all 3 views of both runs.

## The composite's GPU time by graphics clock (both runs, all views; frames, p50 ms)

| Graphics clock (bucket) | live | copy | finish | twice (first) | stale | ≈ live cycles |
|---|---|---|---|---|---|---|
| 2000–2250 MHz | 0.360 (103) | 0.361 | 0.361 | 0.360 | 0.743 | 0.76 M |
| 1750 | 0.393 (198) | 0.394 | 0.395 | 0.394 | 0.742 | 0.74 M |
| 1500 | 0.454 (604) | 0.452 | 0.457 | 0.456 | 0.751 | 0.74 M |
| 1250 | 0.531 (350) | 0.538 | 0.535 | 0.533 | 0.752 | 0.73 M |
| 1000 | 0.608 (402) | 0.609 | 0.609 | 0.612 | 0.766 | 0.68 M |
| 750 | 0.828 (21) | 0.834 | 0.830 | 0.836 | 0.847 | 0.72 M |
| 500 | 1.239 (107) | 1.224 | 1.224 | 1.243 | 1.265 | 0.77 M |
| 250 | 1.488 (15) | 1.488 | 1.446 | 1.490 | 1.499 | (coarse) |

- **live = copy = finish = twice** at every clock: freshly drawn inputs, an idle GPU first, or a second draw change
  nothing. The driver-transition / decompression explanation is ruled out.
- The time scales with 1/clock at a near-constant cycle count, so it is fixed work, stretched by low clocks.
- **stale** is flat at ~0.75 ms above 1 GHz: reading data written frames earlier misses the GPU's cache and waits on
  memory at 810 MHz. Reading the live attachments is the *fast* case.
- The world itself also slows at low clocks (off frames' world 1.6 ms at ≥1 GHz, 2.5–2.8 ms at 250–500 MHz); DoF
  doesn't slow the world (live, on − off world: p50 0.00 to +0.07 ms).
- The earlier "in-frame 1.7–1.9 ms vs alone 0.4–0.6 ms" gap was measured in different clock states. At the same
  clock, in-frame and after-idle are equal (finish column).

## Whole-render incremental, p50 / p95 ms (300 pairs per view per run)

| View | Run | live (as shipped) | copy (persistent copy) | the copy alone, p50 |
|---|---|---|---|---|
| start | a / b | 0.48 / 1.54 · 0.46 / 1.64 | 1.02 / 2.13 · 1.12 / 2.37 | 0.59 · 0.59 |
| shop | a / b | 0.47 / 1.24 · 0.48 / 1.20 | 1.03 / 1.87 · 1.04 / 1.89 | 0.58 · 0.58 |
| bridge | a / b | 0.55 / 1.27 · 0.58 / 1.44 | 1.08 / 1.99 · 1.10 / 2.00 | 0.57 · 0.57 |

Telemetry: memory clock 810 MHz (median) in every view; shop and bridge in P5 at 1035–1785 MHz; the start view moved
through P0/P3/P5 with the graphics clock down to 250–570 MHz, and gives the worst p95. The same code gave about
2.0–2.25 ms p95 in the earlier experiment's session: **the p95 follows the clocks the driver chose that session.**

**Desktop idle:** not done. That needs the owner away from the PC; `reports/run_*_nvidia_smi_start.txt` lists the apps
registered on the GPU (overlays, launchers, explorer). As the cost follows clocks *down* when the GPU is less busy, a
quieter desktop is not expected to help.

## Correction to the earlier write-up

`../taps16/README.md` predicted that (c) the tile pre-pass and (d) the half-resolution blur would not remove the step,
because both still read the just-drawn attachments. That is wrong: the step isn't tied to those reads. As the cost is
cycles, anything that cuts the pass's cycles shrinks it in proportion at every clock.

## Options (owner's choice; none started)

1. **How the cost is judged.** At unlocked clocks on a lightly loaded GPU, a millisecond p95 mostly measures the
   driver's clock choice. Judging it in GPU work (≈0.7 M cycles, 0.36 ms at 2 GHz), or under a realistic load where
   the driver keeps clocks up, would change how the target is measured, which is the owner's call alone.
2. **Fewer cycles.** 16 samples cut about 32%. At 500 MHz, a whole-render p95 ≤1.0 ms needs about ≤0.5 M cycles
   (about −35%); at 250 MHz, about ≤0.25 M (−65%). 16 samples alone is borderline; (d) half-resolution blur is the
   likeliest to meet it even at the lowest clocks. Neither is authorised.
3. **Accept** the current cost (24 samples).

A persistent frame copy is not a candidate: it adds ~0.58 ms and changes nothing else.
