"""The terrain stroke's enforced performance gate (#422 CI-422A3), which replaced the absolute 60 ms frame median.

The terrain stroke's frame time follows the hosted runner's CPU (llvmpipe draws on it): the same commit measured
31-67 ms on different Windows runners, and Xeon 8370C runners failed the 60 ms median with nothing regressed
(evidence/422a-terrain-timing; Extended 42965042459, both attempts). These measurements cancel or divide out the
runner, from samples ``m20b_sculpt_study`` takes in the same Studio session as the gated stroke:

* ``ratio``: sculpt frame / control frame, per trial, from interleaved trials (ABBA) whose control frames are the
  same path hovered (event, ground pick, brush ring, drawing, read-back; no edit). Needs no calibration.
* ``release_per_cpu``: (release + its next frame - a plain frame) / the runner's ``cpu_ms``
  (``tooling/runner_calibration.py``): what letting go costs (the commit, the panel, a reload if one crept in).
* ``frame_per_cpu``: the gated stroke's frame median / ``cpu_ms``: a backstop for a frame grown slow everywhere.

**Enforced, fail-closed.** ``summarise`` never raises, so a failed measurement still reports what it measured; its
``problems`` list every reason the gate can't pass: a threshold crossed, or a measurement missing, incomplete or
unusable (no calibration, fewer valid trials than required, a trial short of frames or with a non-finite one, a stroke
not committed, the gated stroke's frames cut short, a measurement error). ``verdict`` is ``"PASS"`` only when
``problems`` is empty. The old 60 ms comparison is kept as report-only data (``legacy_60ms``).

Thresholds from the evidence branch's 8 runners and 159 lane runs, where no fault-free run came within 15% of them,
and a week of report-only observation (CI-422A2) in which none crossed. What they can't catch is in
``docs/reviews/ci422a3_terrain_gate.md``.
"""

from __future__ import annotations

import math
import statistics
from typing import Any

THRESHOLDS = {"ratio": 1.6, "release_per_cpu": 8.0, "frame_per_cpu": 3.2}
WARM, TRIALS, STEPS = 1, 6, 10  # interleaved trials in the gated test: ~1.3 s each on a slow runner (EPYC 7763)
GATE_FRAMES = 48  # the gated stroke's drag frames (m20b_sculpt_study.studio)
LEGACY_FRAME_MS = 60.0  # the replaced gate: `frame median < 60`; now reported, never asserted


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _frames(values: Any, steps: int) -> float | None:
    """The median of exactly ``steps`` finite, positive frame times; None for anything less."""
    if not isinstance(values, list) or len(values) != steps:
        return None
    clean = [_number(x) for x in values]
    if any(v is None or v <= 0 for v in clean):
        return None
    return statistics.median(v for v in clean if v is not None)


def summarise(trials: Any, gate_frame_ms: Any, cpu_ms: Any, *, overhead_s: Any = None, error: str | None = None,
              steps: int = STEPS, required_trials: int = TRIALS, gate_frames: Any = None,
              required_gate_frames: int | None = None) -> dict[str, Any]:
    """The gate's measurements and verdict from interleaved ``trials`` (each ``{"control": [ms], "sculpt": [ms],
    "release": ms, "control_release": ms, "committed": bool}``, ``steps`` frames a block), the gated stroke's frame
    median (and, when ``required_gate_frames`` is given, its frame count ``gate_frames``) and the runner's ``cpu_ms``.

    Every trial must be valid and there must be exactly ``required_trials`` of them. Never raises."""
    missing: list[str] = []
    if error:
        missing.append(f"measurement failed: {error}")
    cpu = _number(cpu_ms)
    if cpu is None or cpu <= 0:
        missing.append("runner calibration (cpu_ms)")
        cpu = None
    gate = _number(gate_frame_ms)
    if gate is None or gate <= 0:
        missing.append("gated stroke frame median")
        gate = None
    if required_gate_frames is not None and gate_frames != required_gate_frames:
        missing.append(f"gated stroke: {gate_frames} of {required_gate_frames} frames")
    rows = trials if isinstance(trials, list) else []
    ratios, incrementals, extras, controls, sculpts = [], [], [], [], []
    for k, t in enumerate(rows):
        t = t if isinstance(t, dict) else {}
        c, s = _frames(t.get("control"), steps), _frames(t.get("sculpt"), steps)
        rel, crel = _number(t.get("release")), _number(t.get("control_release"))
        if t.get("committed") is not True:
            missing.append(f"trial {k + 1}: its stroke wasn't committed")
            continue
        if c is None or s is None:
            missing.append(f"trial {k + 1}: not {steps} usable frames a block")
            continue
        if rel is None or crel is None:
            missing.append(f"trial {k + 1}: no release timing")
            continue
        controls.append(c)
        sculpts.append(s)
        ratios.append(s / c)
        incrementals.append(s - c)
        extras.append(rel - crel)
    if len(ratios) != required_trials:
        missing.append(f"{len(ratios)} of {required_trials} interleaved trials valid")

    def med(values: list[float]) -> float | None:
        return statistics.median(values) if values else None

    ratio, extra, sculpt = med(ratios), med(extras), med(sculpts)
    values = {"ratio": ratio,
              "release_per_cpu": extra / cpu if extra is not None and cpu is not None else None,
              "frame_per_cpu": gate / cpu if gate is not None and cpu is not None else None}
    crossed = sorted(name for name, v in values.items() if v is not None and v > THRESHOLDS[name])
    problems = [f"{name} {values[name]:.3f} > {THRESHOLDS[name]}" for name in crossed]
    problems += [f"{name}: not measured" for name, v in values.items() if v is None]
    problems += [f"incomplete: {m}" for m in missing]
    verdict = "PASS" if not problems else "FAIL: " + "; ".join(problems[:4])

    def r(v: float | None, n: int = 3) -> float | None:
        return None if v is None else round(v, n)

    return {"verdict": verdict, "problems": problems, "crossed": crossed, "complete": not missing, "missing": missing,
            "thresholds": dict(THRESHOLDS), **{name: r(v) for name, v in values.items()},
            "trials": len(ratios), "required_trials": required_trials, "cpu_ms": r(cpu, 2), "gate_frame_ms": r(gate, 2),
            "control_ms": r(med(controls), 2), "sculpt_ms": r(sculpt, 2),
            "incremental_ms": r(med(incrementals), 2), "release_extra_ms": r(extra, 1),
            "sculpt_per_cpu": r(sculpt / cpu if sculpt is not None and cpu is not None else None),
            "overhead_s": r(_number(overhead_s), 2),
            "legacy_60ms": {"report_only": True, "limit_ms": LEGACY_FRAME_MS, "frame_median_ms": r(gate, 2),
                            "would_have_failed": None if gate is None else gate >= LEGACY_FRAME_MS}}
