"""Report-only terrain stroke measurements (#422 CI-422A2): what may one day replace the 60 ms frame median.

The terrain stroke's frame time follows the hosted runner's CPU (llvmpipe draws on it): the same commit measured
31-65 ms on different Windows runners (evidence/422a-terrain-timing). These measurements cancel or divide out the
runner, from samples ``m20b_sculpt_study`` takes in the same Studio session as the gated stroke:

* ``ratio``: sculpt frame / control frame, per trial, from interleaved trials (ABBA) whose control frames are the
  same path hovered (event, ground pick, brush ring, drawing, read-back; no edit). Needs no calibration.
* ``release_per_cpu``: (release + its next frame - a plain frame) / the runner's ``cpu_ms``
  (``tooling/runner_calibration.py``): what letting go costs (the commit, the panel, a reload if one crept in).
* ``frame_per_cpu``: the gated stroke's frame median / ``cpu_ms``: a backstop for a frame grown slow everywhere.

**Advisory only.** ``summarise`` never raises and nothing asserts on its result: a crossing is recorded (``crossed``,
``advisory``) in the lane's JUnit and summary, never failed. Thresholds from the evidence branch's 8 runners and 159
lane runs, where no fault-free run came within 15% of them.
"""

from __future__ import annotations

import math
import statistics
from typing import Any

THRESHOLDS = {"ratio": 1.6, "release_per_cpu": 8.0, "frame_per_cpu": 3.2}
WARM, TRIALS, STEPS = 1, 6, 10  # interleaved trials in the gated test: ~1.3 s each on a slow runner (EPYC 7763)


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _median(values: Any) -> float | None:
    if not isinstance(values, list):
        return None
    clean = [v for v in (_number(x) for x in values) if v is not None]
    return statistics.median(clean) if clean else None


def summarise(trials: Any, gate_frame_ms: Any, cpu_ms: Any, *, overhead_s: Any = None,
              error: str | None = None) -> dict[str, Any]:
    """The advisory measurements from interleaved ``trials`` (each ``{"control": [ms], "sculpt": [ms], "release": ms,
    "control_release": ms, "committed": bool}``), the gated stroke's frame median and the runner's ``cpu_ms``.

    Anything missing or unusable leaves its measurement ``None`` and is listed in ``missing``; ``complete`` is then
    False and ``advisory`` says INCOMPLETE. Never raises."""
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
    rows = trials if isinstance(trials, list) else []
    ratios, incrementals, extras, controls, sculpts = [], [], [], [], []
    for k, t in enumerate(rows):
        t = t if isinstance(t, dict) else {}
        c, s = _median(t.get("control")), _median(t.get("sculpt"))
        rel, crel = _number(t.get("release")), _number(t.get("control_release"))
        if t.get("committed") is not True:
            missing.append(f"trial {k + 1}: its stroke wasn't committed")
            continue
        if c is None or s is None or c <= 0:
            missing.append(f"trial {k + 1}: no usable frames")
            continue
        controls.append(c)
        sculpts.append(s)
        ratios.append(s / c)
        incrementals.append(s - c)
        if rel is None or crel is None:
            missing.append(f"trial {k + 1}: no release timing")
        else:
            extras.append(rel - crel)
    if not rows:
        missing.append("interleaved trials")

    def med(values: list[float]) -> float | None:
        return statistics.median(values) if values else None

    ratio, extra, sculpt = med(ratios), med(extras), med(sculpts)
    values = {"ratio": ratio,
              "release_per_cpu": extra / cpu if extra is not None and cpu is not None else None,
              "frame_per_cpu": gate / cpu if gate is not None and cpu is not None else None}
    crossed = sorted(name for name, v in values.items() if v is not None and v > THRESHOLDS[name])
    complete = not missing
    words = ", ".join(f"{name} {values[name]:.3f} > {THRESHOLDS[name]}" for name in crossed)
    if crossed:
        advisory = f"CROSSED (advisory, not failed): {words}"
    elif complete:
        advisory = "within the advisory thresholds"
    else:
        advisory = "INCOMPLETE (advisory, not failed): " + "; ".join(missing[:3])
    if crossed and not complete:
        advisory += "; INCOMPLETE: " + "; ".join(missing[:3])

    def r(v: float | None, n: int = 3) -> float | None:
        return None if v is None else round(v, n)

    return {"report_only": True, "advisory": advisory, "crossed": crossed, "complete": complete, "missing": missing,
            "thresholds": dict(THRESHOLDS), **{name: r(v) for name, v in values.items()},
            "trials": len(ratios), "cpu_ms": r(cpu, 2), "gate_frame_ms": r(gate, 2),
            "control_ms": r(med(controls), 2), "sculpt_ms": r(sculpt, 2),
            "incremental_ms": r(med(incrementals), 2), "release_extra_ms": r(extra, 1),
            "sculpt_per_cpu": r(sculpt / cpu if sculpt is not None and cpu is not None else None),
            "overhead_s": r(_number(overhead_s), 2)}
