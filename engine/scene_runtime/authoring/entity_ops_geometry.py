from __future__ import annotations

import math
from typing import Any


def _entity_bounds(ent: dict[str, Any]) -> tuple[float, float, float, float] | None:
    """Return (cx, cy, half_w, half_h) from authored entity data, or *None* if no position."""
    raw_x = ent.get("x")
    raw_y = ent.get("y")
    if raw_x is None or raw_y is None:
        return None
    try:
        cx = float(raw_x)
        cy = float(raw_y)
    except (TypeError, ValueError):
        return None
    w_val = ent.get("width", ent.get("w"))
    h_val = ent.get("height", ent.get("h"))
    try:
        hw = float(w_val) / 2.0 if w_val is not None else 16.0
    except (TypeError, ValueError):
        hw = 16.0
    try:
        hh = float(h_val) / 2.0 if h_val is not None else 16.0
    except (TypeError, ValueError):
        hh = 16.0
    return (cx, cy, hw, hh)


def _anchor_value(cx: float, cy: float, hw: float, hh: float, axis: str, mode: str) -> float:
    if axis == "x":
        if mode == "left":
            return cx - hw
        if mode == "right":
            return cx + hw
        return cx  # center
    # axis == "y"
    if mode == "top":
        return cy + hh
    if mode == "bottom":
        return cy - hh
    return cy  # middle


def _snap_value(v: float, step: int, mode: str) -> float:
    """Snap *v* to the grid defined by *step* using *mode*.

    ``nearest`` - deterministic half-up rounding (ties round away from zero).
    ``floor`` - always round toward negative infinity.
    ``ceil``  - always round toward positive infinity.
    """
    s = float(step)
    if mode == "floor":
        return s * math.floor(v / s)
    if mode == "ceil":
        return s * math.ceil(v / s)
    # nearest - half-up (ties away from zero)
    return s * math.copysign(math.floor(abs(v) / s + 0.5), v)
