# CI-422A: terrain timing reliability (#422). EVIDENCE ONLY, never merge

The functional guard is in draft PR #489 (`ci/422a-terrain-reload-guard`). This branch holds the measurement experiment
and its data. Nothing here changes the 60 ms gate.

## 1. Why the gate flakes (80 Windows and 79 Linux GPU-lane runs, 2026-11-03..10)

`test_studio_sculpts_live_one_stroke_one_undo_step` asserts the median of 48 drag frames is under 60 ms. Each frame
covers Studio's mouse event, the in-place terrain edit, drawing on llvmpipe (on the CPU) and a full-window read-back.
Its time is set mostly by which CPU the hosted runner happens to have:

| Windows runner CPU | runs | calibration `cpu_ms` | frame median min / median / max | gate failures |
|---|---|---|---|---|
| AMD EPYC 9V45 | 12 | 14.0 | 31.6 / 34.5 / 37.2 | 0 |
| AMD EPYC 9V74 | 19 | 19.0 | 44.3 / 46.0 / 62.9 | 1 |
| Intel Xeon 8573C | 6 | 21.0 | 52.0 / 54.4 / 56.4 | 0 |
| AMD EPYC 7763 | 40 | 24.2 | 55.8 / 57.2 / 61.1 | 1 |
| Intel Xeon 8370C | 3 | 23.7 | 61.4 / 64.0 / 65.2 | **3 of 3** |

- The frame median correlates 0.92 with the runner's calibration loop and 0.99 with the terrain-update time.
- Dividing by `cpu_ms` cuts the spread from 17.3% to 6.4% (coefficient of variation).
- `37704ef`'s 62.92 ms failure ran on a 9V74 that measured slow for its type (`cpu_ms` 23.9 against a usual 19.0). Its
  51.98 ms pass ran on an 8573C.
- An 8370C runner fails the gate every time. On a 7763, the most common runner, the margin is about 3 ms.
- Linux medians run 27–55 ms with no failures, so the 60 ms threshold has more room there.

Data: `data/history_gpu_lane_terrain_stroke.json` (`scripts/collect_hist.py`, from the lanes' `pytest_gpu_summary.json`).

## 2. Interleaved control-vs-sculpt measurement (`terrain_ab.py`)

The experiment is one warmed Studio session in the Hills room with the Sculpt tool. Every frame goes through the same
`StudioDriver.frame()` path (drawing, read-back, `ctx.gc()`) with the same camera, viewport and runner. Each trial runs
two blocks, in ABBA order:

- **control:** the cursor hovers along the stroke's path. That is the same event dispatch, ground pick, brush ring,
  drawing and read-back, with no edit. The hover's status-line update ("Ground +0.42 m here."), which a stroke never
  makes, is silenced.
- **sculpt:** press, the same path as drag frames, then release and the next frame.

Each run has 2 warm-up trials and 10 measured, of 16 steps each. Raise and lower alternate. The per-trial medians
give:

- the absolute frame;
- sculpt − control, the incremental cost of sculpting;
- sculpt ÷ control, the ratio;
- the terrain-update time;
- the commit;
- release − control, the extra latency from release to the next visible frame;
- full room reloads.

The evidence workflow (`.github/workflows/evidence-422a.yml`, run 42835508182) put this on **8 hosted Windows runners**
with the CI Mesa setup:

- 6 `windows-latest` and 2 `windows-2022`;
- CPUs: 3× EPYC 7763, 2× EPYC 9V45, 1× EPYC 9V74, 1× Xeon 8370C, 1× Xeon 8573C.

Each job runs no fault, each injected fault (`--mut`), then no fault again. Drift between the two no-fault runs:
sculpt frame 0.97–1.01×, incremental cost 0.95–1.01×.

### Baseline across the 8 runners (no fault)

| measurement | range | spread (CV) | ÷ `cpu_ms` spread |
|---|---|---|---|
| sculpt frame (the gate's metric) | 32.8–59.5 ms | 20.7% | 5.3% |
| control frame | 25.3–45.4 ms | 20.3% | 6.6% |
| sculpt − control | 7.6–14.9 ms | 22.7% | 3.3% |
| **sculpt ÷ control** | **1.30–1.35** | **1.5%** | — |
| terrain update | 6.0–13.7 ms | 28.9% | 9.4% |
| commit | 6.9–12.1 ms | 20.4% | 3.5% |
| release − control | 48–93 ms | 22.7% | 3.8% |

On the same runners, the real gate test gave 32.6–59.6 ms and passed on all eight. The 8370C came within 0.4 ms of
failing.

### What each fault does, judged from one run (16 no-fault runs vs the 8 runners under each fault)

| measurement | no fault | 1. reload on release | 1b. reload every flush | 2. rebuild every chunk | 3a. +5 ms CPU per frame | 3a. +15 ms per frame | 3b. +5 ms CPU per dab |
|---|---|---|---|---|---|---|---|
| reload count | 0 | **10** | **10** | 0 | 0 | 0 | 0 |
| sculpt ÷ control | 1.30–1.36 | 1.29–1.35 | **0.98–0.99** | **1.84–2.00** | 1.25–1.31 | 1.19–1.26 | **1.43–1.51** |
| (sculpt − control) ÷ `cpu_ms` | 0.55–0.63 | 0.56–0.64 | **−0.04–−0.01** | **1.55–1.75** | 0.56–0.63 | 0.55–0.61 | **0.78–0.96** |
| terrain update ÷ `cpu_ms` | 0.42–0.58 | 0.44–0.59 | 0.28–0.33 | **1.46–1.68** | 0.45–0.59 | 0.50–0.58 | 0.45–0.61 |
| (release − control) ÷ `cpu_ms` | 3.4–3.9 | **44.6–51.9** | ~0 | 3.4–4.0 | 3.4–3.9 | 3.3–3.8 | 3.4–3.8 |
| control frame ÷ `cpu_ms` | 1.65–1.98 | 1.66–1.98 | 1.66–1.98 | 1.65–1.97 | 1.85–2.26 | **2.25–3.02** | 1.65–1.96 |
| sculpt frame ÷ `cpu_ms` | 2.22–2.61 | 2.24–2.61 | 1.63–1.95 | **3.30–3.71** | 2.42–2.87 | 2.82–3.60 | 2.43–2.83 |
| absolute sculpt frame (today's gate) | 31.7–59.8 | 32.8–60.0 | 23.9–44.9 | 45.6–85.9 | 36.9–64.8 | 46.8–74.9 | 36.8–65.3 |

Bold marks values that never overlap the no-fault range on any runner.

## 3. Findings

1. **Today's 60 ms gate misses every reload.**
   - A reload on release leaves the drag frames untouched; the frame median stayed at 23 ms locally.
   - A reload during the stroke cancels it, so the frames get *faster*.
   - Rebuilding every chunk (45.6 ms) and extra per-dab work (36.8 ms) both pass it on fast runners.
   - It fails on slow runners whether or not anything regressed.
2. **Reloads:** only the reload count catches them exactly (PR #489). Release − control also catches a reload on
   release, by 12–14×.
3. **Excessive rebuilding and per-step work:**
   - The interleaved **sculpt ÷ control ratio** separates both from the baseline on every runner. It needs no
     calibration: its baseline spread is 1.5% across a 1.8× range of runner speeds.
   - (Sculpt − control) ÷ `cpu_ms` does the same, with more headroom.
4. **Extra work in every frame** (control frames too) cancels out of a ratio by design.
   - Only absolute time divided by runner calibration sees it.
   - 15 ms a frame separates; 5 ms a frame doesn't on any single-run metric. Runner noise is about ±10% after
     calibration, because the Intel CPUs run llvmpipe slower than their `cpu_ms` suggests.
   - That is a general frame-time question, not a terrain one.

## 4. Recommendation (for review: nothing here is implemented)

Replace the absolute 60 ms median, after review and a trial period, with:

1. **Zero full room reloads** on a successful stroke: PR #489. This is the test's original requirement, asserted
   exactly.
2. **Sculpt ÷ control ≤ 1.6**, measured in the same test with interleaved control frames. The baseline is 1.30–1.36,
   so 1.6 sits about 18% above the highest no-fault run. Rebuild-every-chunk gives 1.84 or more. Per-dab work of
   5 ms gives 1.43–1.51 and is caught only at a lower limit (about 1.42), which is too tight for now.
3. **(Release − control) ÷ `cpu_ms` ≤ 8.** No-fault runs give at most 3.9; a reload on release gives 44 or more.
   This is a second guard on the release path.
4. **A catastrophic backstop:** sculpt frame ÷ `cpu_ms` ≤ 3.2, where history peaks at 2.76 and this run at 2.61.
   This needs the runner calibration inside the test, which `tooling/runner_calibration.py` already provides.
   Alternatively, an absolute ceiling far above any runner, such as 120 ms.

Steps 2–4 should first run **report-only** (recorded, not asserted) alongside the unchanged 60 ms gate for a week of
CI and Extended runs. Swap only if no no-fault run crosses the limits. The extra cost is about 6 interleaved trials
inside the existing test: roughly +8–12 s on an EPYC 7763 (each standalone A/B run took about 34 s on one,
including process start and project build).

## Reproduce

```bash
python docs/reviews/ci422a_terrain_timing/terrain_ab.py out.json --mut rebuild_all
python docs/reviews/ci422a_terrain_timing/scripts/collect_hist.py hist/
python docs/reviews/ci422a_terrain_timing/scripts/analyse_ev.py <evidence artifacts dir>
```

`scripts/mut422.py` is the pytest plugin used against the real test (`MUT422=<fault> -p mut422`).
