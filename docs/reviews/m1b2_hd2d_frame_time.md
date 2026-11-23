# M1-B-2: frame time of the M1-B Crossing on reference hardware (report only)

Plan: `docs/plans/hd2d_online_investigation.md` §4, M1-B-2. Owner decision **D5 (provisional)**: smooth 60 FPS at
1280×720 on named reference hardware; target frame time ≈ **16.7 ms**; initial reporting threshold **p95 ≤ 33.3 ms**.
D5 is a development target. **No CI gate or threshold is added here, and nothing fails on timing.**

Raw numbers: [m1b2_hd2d_frame_time.json](m1b2_hd2d_frame_time.json) (two runs in separate processes, 2026-11-23).

## Verdict

| | Target 16.7 ms | Threshold p95 ≤ 33.3 ms |
|---|---|---|
| 7 peers (8 avatars), 10 trials | **met at median, p95 and p99**: median 4.22–5.07 ms, p95 6.78–7.15 ms, p99 7.19–8.38 ms | **met**: worst trial p95 7.15 ms (21% of the threshold) |
| 0 peers (baseline), 4 trials | met: median 4.04–4.39 ms, p95 6.48–6.56 ms | met |
| Worst single frame, all 14 trials | one frame of 17.08 ms (trial 1.1) is over 16.7 ms; every other frame ≤ 15.21 ms | — |

The single frame over target is part of one 5-frame burst (frames 610–614 of trial 1.1, 14.6–17.1 ms each). The GPU's own
time stayed at 0.35 ms through it, while the CPU draw, `finish` and `flip` stages all grew at once. The same spot on the
walk (x 16.9 m, y 13.2 m) is quick in the other 9 seven-peer trials. So this looks like a pause from outside the frame
(see Noise), not a cost in the scene. It is not a sustained problem, so nothing was proposed.

Server tick, `SceneRoom.step` with 8 bodies: **p95 0.80–0.96 ms**, median 0.56–0.58 ms, worst 1.64 ms. A 20 Hz tick
has 50 ms.

## Reference hardware

Gathered by the tool: GL strings, the Windows registry and `GlobalMemoryStatusEx`, `nvidia-smi` and package metadata.

| | |
|---|---|
| GPU | NVIDIA GeForce RTX 4070 (`NVIDIA Corporation NVIDIA GeForce RTX 4070/PCIe/SSE2`) |
| Driver | NVIDIA 610.88 (GL `4.6.0 NVIDIA 610.88`) |
| CPU | AMD Ryzen 7 5700X3D 8-Core Processor, 16 logical cores |
| RAM | 31.9 GiB |
| OS | Windows 11, build 10.0.26300 |
| Software | Python 3.13.3, pyglet 2.1.11, arcade 3.3.3 |
| Picture | 1280 × 720 framebuffer |

## Rendering configuration (as the scene ships)

The Crossing is built by `tooling/hd2d_m1b_scene.py build`, in Mesh Studio with its own input events (M1-B-1), and is
measured unchanged.

| Setting | Value |
|---|---|
| Window | hidden (never shown), **vsync off**, window MSAA samples 0 |
| Sun shadows | on, 2048 px map, `sharp` (no PCF) |
| Lamps | 3: two lamp-post lanterns and one under the deck. **2 cast shadows**, each a 6-face map of 512 px faces |
| Post effects | bloom off, haze off, depth of field off, grade/vignette off. These are the defaults for a new Studio room; the Crossing authors none. Game post-process pipeline: 0 effects. 2D lighting layer: off |
| Camera | perspective, pitch 30°, fov 12°, distance 53.5 m (Studio's outdoor preset), bounded by the room |
| Scene | 12 structures (6 platforms, bridge, 2 stairs, cottage, 2 lamp posts) and the guard (Person) |
| Per frame (7 peers) | 23 draw calls, 942 triangles, 22 shadow draws. With 0 peers: 19, 942, 18 |
| Avatars | own + 7 peers. All 7 peers were in the picture on every measured frame of every trial: projected with the camera's own view-projection, min = max = 7 |

## What was measured

`py -3.13 tooling/hd2d_m1b_scene.py perf OUT` runs three steps:

1. **Server tick (headless).** A `SceneRoom` on the Crossing, with its HD-2D collision World. 8 bodies join and each
   walks a fixed loop through ground, west stairs, west plateau, the bridge deck, east plateau, east stairs, under the
   deck, behind the cottage, into its doorway and back to the start (`ROUTE`, about 22 s a lap). Each body sets off
   0.25 s after the one before. Input frames are sent as a client sends them: one a tick, on one axis at a time.
   After 100 untimed ticks there are 3 trials of 2400 ticks, and only `step()` is timed. All 1696 legs were completed,
   0 stalled.
2. **Client frame (hidden window, 1280 × 720).** This is the real net-client drawing path, `mesh_net.scene_client.SceneView`
   as `mesh_net.world_client` uses it, fed by a local authority instead of a socket. The same loop is walked by
   1 + N bodies on a `SceneRoom`, stepped at its 20 Hz between frames (that is the server's work, so untimed).
   Snapshots go into `Playback`: the peers are drawn two ticks behind and the own avatar where the server last put it.
   The camera follows the own avatar. Each trial is 300 warm-up frames, then 1500 timed frames (25 s of game time,
   over one full lap; the own avatar walked 16 legs, 0 stalled). Each frame is timed from snapshot-in to flip, in
   stages:
   - `net`: the snapshot pushed and the positions interpolated;
   - `sync`: `SceneView.sync`;
   - `update`: scene behaviours, camera and lamps, from `SceneView.draw`;
   - `draw`: `window.on_draw`. CPU time, plus the GPU's own time from a `GL_TIME_ELAPSED` query around it;
   - `finish`: `ctx.finish()`, waiting for the GPU to complete;
   - `flip`: `window.flip()`, the buffer swap plus `ctx.gc()`.

   The trial order is 7, 0, 7, 7, 0, 7, 7 peers in one window, with the room reloaded each time.
3. **Hardware, settings and noise**, as recorded above and below.

Percentiles use the nearest rank. `tests/test_hd2d_m1b_perf_summary.py` (fast) checks the statistics.

## Client frame time, per trial (ms)

GPU is the median of the `on_draw` timer query. "Others CPU" is the machine's busy share minus this process's own share,
in % of all 16 logical cores, during the trial. "GPU util" is `nvidia-smi` before / after the trial (whole GPU, all
programs). "Full screen" means another program's full-screen window was in the foreground before and after the trial.

| Trial | Peers | Peers in view | Median | p95 | p99 | Worst | GPU | Others CPU % | GPU util % | Full screen |
|---|---|---|---|---|---|---|---|---|---|---|
| 1.1 | 7 | 7 | 5.07 | 7.15 | 8.38 | **17.08** | 0.32 | 23 | 65 / 61 | yes |
| 1.2 | 0 | 0 | 4.04 | 6.53 | 6.97 | 7.94 | 0.31 | 15 | 64 / 58 | yes |
| 1.3 | 7 | 7 | 4.72 | 6.85 | 7.27 | 7.57 | 0.34 | 14 | 85 / 56 | yes |
| 1.4 | 7 | 7 | 4.60 | 6.78 | 7.19 | 8.14 | 0.34 | 14 | 76 / 68 | yes |
| 1.5 | 0 | 0 | 4.39 | 6.55 | 7.01 | 7.39 | 0.32 | 17 | 61 / 87 | yes |
| 1.6 | 7 | 7 | 4.36 | 6.93 | 7.51 | 9.98 | 0.34 | 16 | 70 / 60 | yes |
| 1.7 | 7 | 7 | 4.44 | 6.88 | 7.32 | 7.82 | 0.35 | 14 | 78 / 77 | yes |
| 2.1 | 7 | 7 | 4.92 | 6.87 | 7.40 | 8.19 | 0.29 | 13 | 74 / 85 | yes |
| 2.2 | 0 | 0 | 4.13 | 6.48 | 6.92 | 7.54 | 0.32 | 14 | 80 / 86 | yes |
| 2.3 | 7 | 7 | 4.43 | 6.90 | 7.44 | 8.33 | 0.35 | 13 | 77 / 84 | yes |
| 2.4 | 7 | 7 | 4.33 | 6.91 | 7.50 | 8.68 | 0.34 | 12 | 83 / 60 | yes |
| 2.5 | 0 | 0 | 4.11 | 6.56 | 7.03 | 7.64 | 0.33 | 16 | 81 / 61 | yes |
| 2.6 | 7 | 7 | 4.22 | 7.01 | 7.42 | 9.64 | 0.35 | 14 | 60 / 59 | yes |
| 2.7 | 7 | 7 | 4.46 | 6.96 | 7.55 | 8.97 | 0.31 | 15 | 75 / 69 | yes |

**Summary across trials (ms):**

| | Median | p95 | p99 | Worst |
|---|---|---|---|---|
| 7 peers, 10 trials: range (median of trials) | 4.22–5.07 (4.45) | 6.78–7.15 (6.91) | 7.19–8.38 (7.43) | 7.57–17.08 (8.50) |
| 0 peers, 4 trials: range (median of trials) | 4.04–4.39 (4.12) | 6.48–6.56 (6.54) | 6.92–7.03 (6.99) | 7.39–7.94 (7.59) |

Seven peer avatars cost about 0.3 ms at the median and 0.4 ms at p95: 4 more draw calls and 4 more shadow draws.

## Where the time goes (7 peers, median of the 10 trials)

| Stage | Median ms | p95 ms |
|---|---|---|
| net | 0.01 | 0.09 |
| sync | 0.02 | 0.02 |
| update | 0.14 | 0.18 |
| draw, CPU | 2.45 | 3.62 |
| draw, GPU (timer query) | 0.34 | 0.37 |
| finish | 0.80 | 1.54 |
| flip | 0.69 | 1.83 |

The GPU executes the frame in about a third of a millisecond. The frame is mostly the CPU submitting the draw
(Python plus the driver), then the waits in `finish` and `flip`. Those waits are longer than our own 0.34 ms of GPU
work, which fits a GPU shared with a full-screen game (see Noise). That is a likely contributor, not one that was
verified.

The worst frames of the seven-peer trials are spread over the loop, so no place on the walk is slow: ground, stairs,
deck and behind the cottage all appear. The exception is the one burst in trial 1.1 described under Verdict.

Nothing is near threshold, so no change is proposed.

## Noise (privacy-preserving)

- **The owner was playing a full-screen game throughout.** Another program's full-screen window was in the
  foreground before and after every trial. `nvidia-smi` showed the GPU 54–66% busy with our process idle, and 56–87%
  around the trials. The machine's CPU was 13.8–17.8% busy without us; other programs used 12–23% during the trials,
  and this process about 5%. No program was paused or closed.
- **Effect on the numbers.** Trial to trial, the seven-peer p95 varies by 0.37 ms (6.78–7.15) and the median by
  0.85 ms. The two runs agree within that spread. The waits in `finish`/`flip` and the trial-1.1 burst are where
  sharing the machine most plausibly shows. Without the game these numbers would probably be no worse, and likely a
  little better. That is unmeasured, because the game was never stopped.
- An earlier development run of the same harness (same day, the game also running) gave a seven-peer median of
  5.1–5.4 ms and p95 7.0–7.5 ms. That run is not in the JSON, because its tool still had a mislabelled post-effect
  flag. It is in the same range.
- **Foreground monitor** (read-only, `fgmon.py`, run through every GPU/window run): **0 events involving a test
  window**. The tool's hidden window never took foreground, activation or focus. The only changes logged were the
  owner switching between their own programs, outside the measured runs.

## Caveats

- **Hidden window.** The window is never shown, and vsync is off. On a visible window the compositor and vsync would
  pace presentation at the display's rate, and `flip` may cost differently. These are unpaced frame times: the work
  a frame needs, not when it reaches the screen.
- **Local authority, no socket.** The client path is the real one (SceneView, Playback, the renderer), but snapshots
  arrive by function call, not over TCP, and `room.step()` runs in the same process, untimed. Decoding about 1 KB of
  JSON a tick is not counted.
- **Software GL (hosted runners).** The GL timer query is unreliable on Mesa llvmpipe: bimodal in the depth-of-field
  study (#460). Its frame times are not representative (plan R5; `docs/reviews/milestone16_stage6b_ci_timing.md`).
  The tool runs there unchanged and prints numbers, but **no hosted run was added to CI**. Each run builds the Crossing
  in Studio (about 60 s) and then needs about 2 minutes of window time on top of the gpu lane, for report-only output.
  It can be run by hand on a runner if wanted.

## Reproduce

```
py -3.13 tooling/hd2d_m1b_scene.py perf OUT
```

with `PYTHONPATH` set to the checkout. It builds `OUT/game` first if absent, which is the M1-B-1 Studio build (hidden
window). Results go to `OUT/perf.json`. A run takes about 2 minutes after the build. Audio is silent (master volume
0, from the build), and the process installs `tooling.hidden_windows.no_activate` before any window opens.
