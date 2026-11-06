# #475 option (b): 16 vs 24 samples — experiment (EVIDENCE ONLY, never merged)

The owner authorised this on #475: compare the current 24-sample cap with a scratch 16-sample cap on the RTX 4070,
measuring the whole HD-2D render. Ship 16 only if it **reliably** gives a 1080p whole-render incremental p95 of
1.0 ms or less **and** keeps the visual quality. Otherwise, stop with the evidence.

**Verdict: 16 samples misses the performance condition, so it is not shipped.** Quality is materially preserved, but
the Lakeside shop and bridge views stay at about 2.0 ms p95 with 16 samples, in both repeat runs. Product code is
unchanged: the cap was switched in scratch processes only (`engine.hd2d.dof.TAPS_MAX`, read at draw time).

Machine: RTX 4070, GL 4.6, Windows 11, hidden windows, product head `265b43a`. Clocks were not locked, and no system
setting was changed. Clock, power and usage telemetry comes from read-only `nvidia-smi` sampling every 100 ms.

## Method (`scripts/ab_timing.py`)

Each view is warmed (90 steps, then 60 discarded cycles). Every one of the 300 cycles draws off, cap A, off, cap B,
alternating which cap goes first. A GL timer wraps the renderer's whole draw: the world, plus the blit or the DoF in
its place. Incremental means on minus the off frame drawn just before it. The script also records steady blocks
(40 frames each: off, 24, off, 16, three times) and the pass redrawn alone after an idle GPU (a lower bound). The
1080p runs were done twice per project (a, b); 1440p is one exploratory run. Raw data is in `reports/timing_*.json`.

## 1080p whole-render incremental, p50 / p95 ms (300 pairs per view)

| View | Run | 24 samples | 16 samples | Pass alone, 24 → 16 (p50) | GPU clock (median) |
|---|---|---|---|---|---|
| Template start | a | 0.38 / 0.40 | 0.25 / 0.27 | 0.40 → 0.28 | 1770 MHz |
| Template start | b | 0.55 / **2.21** | 0.37 / 0.43 | 0.59 → 0.39 | 1245 MHz |
| Template shop | a / b | 0.28 / 0.29 · 0.49 / 0.53 | 0.19 / 0.20 · 0.32 / 0.35 | 0.30 → 0.21 · 0.51 → 0.35 | 2475 / 1365 MHz |
| Template bridge | a / b | 0.28 / 0.30 · 0.50 / 0.56 | 0.19 / 0.20 · 0.33 / 0.37 | 0.30 → 0.21 · 0.53 → 0.36 | 2370 / 1305 MHz |
| Lakeside start | a | 0.99 / **2.10** | 0.62 / **1.77** | 0.91 → 0.62 | 1050 MHz |
| Lakeside start | b | 0.83 / **2.09** | 0.81 / **1.99** | 0.59 → 0.40 | 1230 MHz |
| Lakeside shop | a | 1.81 / **2.18** | 1.65 / **1.97** | 0.57 → 0.40 | 1328 MHz (P0) |
| Lakeside shop | b | 1.86 / **2.25** | 1.62 / **1.98** | 0.57 → 0.39 | 1230 MHz |
| Lakeside bridge | a | 1.82 / **2.26** | 1.65 / **2.10** | 0.55 → 0.38 | 1283 MHz (P0) |
| Lakeside bridge | b | 1.86 / **2.24** | 1.67 / **1.98** | 0.57 → 0.39 | 1275 MHz |
| Cottage (both) | a / b | 0.28–0.50 / 0.50–0.55 | 0.19–0.33 / 0.33–0.37 | ≈ 0.30–0.53 → 0.21–0.36 | — |

**1440p, exploratory (one run).**
- Lakeside: 24 samples gives 2.0–2.3 / 2.6–3.8 ms. 16 samples gives 0.52–0.93 / 0.6–3.1 ms.
- Template: 24 samples gives 0.46–2.14 / 0.57–2.54 ms. 16 samples gives 0.31–1.83 / 0.38–2.17 ms.
- Pass alone: 0.93–0.98 ms at 24 samples, 0.63–0.67 ms at 16.
- The pass alone scales with pixel count (about 1.7×). The same step appears at 1440p, even in the interiors at
  24 samples (2.1 ms, against 0.6 ms at 16).

## What the extra time is (`scripts/bottleneck.py`, `scripts/bubble.py`)

**Samples.** 16 samples cut the pass's own cost by about 32%, in proportion to the sample count. But in Lakeside the
whole-render difference is about 1.2–1.4 ms above the pass alone, at both caps.

**Variants** (Lakeside shop and bridge, 1080p, 200 pairs, each variant twice; see `reports/bottleneck_variants.json`):
- A pass with **no samples**, and a pass that **reads no depth at all** (even with the depth texture unbound): median
  about 0 ms, but **p95 1.34–1.49 ms**. About 10% of frames still pay the step, though nothing is computed.
- The 16-sample pass drawn **twice** in a frame: 2.0 ms median every time.

**In-frame composite and CPU time** (see `reports/in_frame_composite_and_cpu.json`):
- The composite timed alone *inside the frame* takes **1.67–1.90 ms p50 of GPU time** in the step state, against
  0.39–0.57 ms when redrawn after an idle GPU.
- The renderer's CPU time rises by only **0.04–0.10 ms** with DoF on, so the GPU is not left idle waiting on Python.

**The step comes and goes in stretches of hundreds of frames,** independent of the sample count. In one run, the
same view gave 0.47 ms at 16 samples and then 1.90 ms at 24. It occurs at P0 with memory at full clock. In the light
template village, clocks sit in P3 at about 1.1 GHz with memory at half clock; there, the pass itself scales with
clock (0.28 ms at 2.4 GHz, 0.5 ms at 1.3 GHz).

**Likely bottleneck, not proven:** a fixed ~1.2–1.4 ms paid by the GPU inside the full-screen composite when it runs
right after the world is drawn. It doesn't depend on the shader's arithmetic. It is most consistent with a
driver-side render-target-to-texture transition (flush or decompression of the just-drawn attachments) or GPU
scheduling on this shared desktop GPU, and it can't be told apart without deeper GPU tooling. Because of this, (c)
the tile pre-pass and (d) the half-resolution blur would not remove it: both still read the just-drawn attachments
in the frame.

## Visual comparison (`scripts/capstudy.py`, `scripts/compare.py`; 1080p, matched captures)

Raw data is in `reports/quality_24_vs_16.json`.
- **Unchanged at 16 samples:**
  - off, disabled and strength 0 stay bit-identical to off;
  - the player's pixels change 0% (Lakeside bridge: 4.47% at both caps, the lamp post in front);
  - the sharp band changes at most 0.9% at both caps;
  - the HUD's glyphs change at most 2 levels at both caps;
  - still frames are identical;
  - walking frame-to-frame change is 1.32× (template) and 0.95–0.97× (Lakeside), as with 24 samples;
  - interiors are pixel-identical (their blur needs fewer than 16 samples).
- **Studio** (`reports/studio_flow_*.json`): preview line pixels are identical at both caps (22868, 100% the same),
  and the editing view is unchanged without preview.
- **Weaker far blur:**
  - same-row far patches keep 29–50% of their detail at 16 samples, against 18–41% at 24;
  - leftover fine detail in blurred regions is 8–22% higher at 16 samples;
  - 24 and 16 differ by more than 8 levels on 0.02–1.1% of pixels, with a maximum of 41, mostly on small bright
    flowers.
- **Pictures** (`pictures/`, each off | 24 | 16 | difference ×8): no new halos, rings or visible sample pattern. Only
  the brightest small details stay slightly crisper.
