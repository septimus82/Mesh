# CI-422A3: the terrain gate that replaced the 60 ms frame median (#422)

`tests/test_terrain_gpu.py::test_studio_sculpts_live_one_stroke_one_undo_step` used to assert that the median of the
Studio stroke's 48 drag frames was under 60 ms. That median follows the hosted runner's CPU, because llvmpipe draws on
it. Xeon 8370C runners failed it with nothing regressed: Extended 42965042459 measured 67.09 ms, then 60.33 ms on its
rerun. It also missed every reload (evidence/422a-terrain-timing).

## What is enforced now (`tooling/terrain_advisory.py`)

| Measurement | Enforced limit | Fault-free observed |
|---|---|---|
| sculpt / control frame ratio (6 interleaved ABBA trials) | ≤ 1.6 | 1.288–1.375 |
| (release − plain frame) / `cpu_ms` | ≤ 8.0 | 3.36–4.06 (one 2.22, see limits) |
| gated stroke frame median / `cpu_ms` (backstop) | ≤ 3.2 | 2.25–2.76 (one 1.44) |

**Where it is enforced** (`performance_profile`): only on the profile the thresholds were validated on, which is
GitHub-hosted (`RUNNER_ENVIRONMENT=github-hosted`) Linux or Windows runners with 4 vCPUs drawing with Mesa llvmpipe.

- **Validated CI profile:** all three limits are enforced, fail-closed.
- **CI that doesn't match the profile** (another vCPU count, a self-hosted or macOS runner, a hardware renderer, an
  unreadable renderer, or another CI): the gate fails with `unsupported performance environment (<what didn't match>)`
  and asks for re-measurement. CI enforcement is never silently downgraded.
- **Outside CI** (a developer's machine): every measurement is taken and recorded, but the verdict is
  `NOT VALIDATED`, never a pass and never a fail. There are no alternative thresholds for other core counts.

The functional checks are asserted everywhere.

These stay asserted as before: zero full room reloads (exact count), one undo step per stroke, undo/redo,
save/reopen, the cancellation and recovery cases, and the 200 ms commit guard. The functional checks run first, then
the commit guard, then the gate's verdict. A slow runner can't hide a functional failure.

**Fail-closed.** The verdict is `PASS` only when nothing is in `problems`. Any of these fails it:

- a threshold crossed;
- no usable calibration;
- not exactly 6 valid trials;
- a trial without exactly 10 finite, positive frames per block;
- a stroke not committed (`committed` must be `True`, not just truthy);
- a missing or non-finite release time;
- the gated stroke's median missing, or fewer than 48 frames;
- a measurement error.

`summarise` never raises, so a failed measurement still reports everything it did measure.

**Recorded on every run** (JUnit properties and lane summary), passing or failing:

- `measure.terrain_stroke`: the raw stroke timings.
- `measure.terrain_advisory`: the enforced values, `verdict`, `problems`, measurement validity (`complete`,
  `missing`, `trials` / `required_trials`), and `legacy_60ms`, the old comparison. `legacy_60ms` is report-only: it
  records whether the old gate would have failed.
- `measure.terrain_advisory_detection`: fault-injection outcomes.

The property names are unchanged, so the observation data continues.

## Old gate vs new gate

### Fault-free runs

| Evidence | Old 60 ms gate | New gate |
|---|---|---|
| 159 GPU-lane runs, 2026-11-03..10 (`history_gpu_lane_terrain_stroke.json`) | 5 failures (8370C 3 of 3, one 9V74, one 7763) | backstop peak 2.76 ≤ 3.2 (ratio and release weren't measured then) |
| 8-runner experiment, run 42835508182 | 0 of 8 failed (8370C within 0.4 ms) | ratio 1.30–1.35, release 3.4–3.9, frame 2.22–2.61: 0 of 8 |
| CI-422A2 observation, 13 gated runs (table below) | 2 of 13 failed (both 8370C) | 0 of 13 |

| Run | OS | CPU | 60 ms median | ratio | release | frame | old | new |
|---|---|---|---|---|---|---|---|---|
| 42858598998 | Win | Xeon 8573C | 57.17 | 1.320 | 4.009 | 2.642 | pass | pass |
| 42858598998 | Lin | EPYC 7763 | 48.90 | 1.364 | 3.681 | 2.449 | pass | pass |
| 42871555328 | Lin | Xeon 8370C | 50.78 | 1.324 | 3.478 | 2.630 | pass | pass |
| 42871555328 | Win | Xeon 6973P-C | 49.97 | 1.305 | 4.056 | 2.756 | pass | pass |
| 42886645746 | Win | EPYC 7763 | 56.89 | 1.362 | 3.645 | 2.251 | pass | pass |
| 42886645746 | Lin | EPYC 7763 | 52.75 | 1.375 | 3.968 | 2.628 | pass | pass |
| 42915543045 | Win | EPYC 9V74 | 46.75 | 1.322 | 3.576 | 2.445 | pass | pass |
| 42915543045 | Lin | EPYC 9V74 | 39.02 | 1.338 | 3.364 | 2.454 | pass | pass |
| 42919513624 | Lin | EPYC 7763 | 47.70 | 1.361 | 2.220 | 1.438 | pass | pass |
| 42919513624 | Win | EPYC 7763 | 56.63 | 1.370 | 3.695 | 2.332 | pass | pass |
| 42965042459 | Lin | EPYC 7763 | 49.61 | 1.357 | 3.704 | 2.479 | pass | pass |
| 42965042459 a1 | Win | Xeon 8370C | 67.09 | 1.288 | 3.621 | 2.614 | **fail** | pass |
| 42965042459 a2 | Win | Xeon 8370C | 60.33 | 1.329 | 3.634 | 2.589 | **fail** | pass |

Every row is a fast test case (`tests/test_terrain_advisory.py`).

### Injected regressions

| Fault | Old 60 ms gate | New gate |
|---|---|---|
| reload on release | missed (drag frames untouched) | **fails**: release 41.7–50.4 (Windows), 12.5–14.6 (Linux) > 8, on all 13 detection runs; the zero-reload guard fails too |
| reload on every flush / mid-stroke | missed (frames get faster) | **fails** by the zero-reload guard (exact count). The ratio falls to 0.98, so the ratio alone wouldn't catch it |
| rebuild every terrain chunk | fails only on slow runners (45.6–85.9 ms) | **fails**: ratio 1.816–2.048 on all 13 runs (evidence: 1.84–2.00) |
| every frame slower by 1.5 × `cpu_ms` (new `slow_frames` case) | depends on the runner | **fails**: calibrated frame +1.5 (fault-free 2.26–2.91 in detection runs) |
| +15 ms CPU in every frame (evidence) | 46.8–74.9 ms: depends on the runner | partly: calibrated frame 2.82–3.60 crosses on some runners only |
| +5 ms CPU in every frame (evidence) | 36.9–64.8 ms: depends on the runner | **not caught** |
| +5 ms CPU per dab (evidence) | 36.8–65.3 ms: depends on the runner | **not caught**: ratio 1.43–1.51 < 1.6 |
| missing, corrupt or incomplete measurement | n/a | **fails** (fast tests: 7 kinds of missing calibration, 7 trial-count cases, 11 invalid-trial cases, 6 gated-stroke cases, a measurement error, and a real `_advisory` failure mid-measurement) |
| functional terrain failures | fail | fail, asserted before the timing |

## What it can't reliably detect

1. **Small per-frame regressions everywhere.** Work that slows control and sculpt frames alike cancels out of the
   ratio. Only the backstop sees it. To cross 3.2 from the fault-free 2.25–2.76, a frame needs another 0.44–0.95 ×
   `cpu_ms`, depending on the runner: +16% to +42% frame time. +15 ms a frame crosses on some runners only, and +5 ms on none. That is a general frame-time
   question, not a terrain one.
2. **Moderate extra per-step terrain work.** +5 ms per dab gives a ratio of 1.43–1.51. Catching it would need a limit
   near 1.42, which is too close to the fault-free 1.375.
3. **A calibration that reads slow.** `cpu_ms` is the median of five ~20 ms loops. Once in the 13 gated runs it read
   33.17 against the lane's 19.9 for that runner (42919513624, Linux). The release and backstop values then
   under-read by about 40%. That makes the gate less sensitive; it is never a false failure, since the calibration
   can't read faster than the CPU. On Linux the reload-on-release margin (12.5–14.6 against 8) could fall near the
   limit with such a reading, but reloads are also caught exactly by the zero-reload guard.
4. **Core count.** The thresholds are for the hosted 4-vCPU runners. On a 16-thread desktop the fault-free ratio is
   1.61–1.89: llvmpipe spreads drawing across cores, but not the terrain update. Such a machine is outside the
   validated profile, so its verdict is `NOT VALIDATED` and only the functional checks judge it. If GitHub moved
   `windows-latest` or `ubuntu-latest` to more vCPUs, the gate would fail as an unsupported environment until the
   thresholds are re-measured.
5. **Regressions on a physical GPU only.** CI draws with llvmpipe (unchanged, pre-existing).
