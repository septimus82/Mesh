"""Pure parsing/normalization helpers for command-palette action args."""
from __future__ import annotations

from typing import Any, Callable


def parse_align_args(
    arg: str | None,
    *,
    simple_map: dict[str, tuple[str, str]],
) -> dict[str, Any]:
    raw = str(arg or "").strip().lower()
    if not raw:
        return {"ok": False, "reason": "empty_align_arg"}

    axis = ""
    mode = ""
    reference = "primary"

    if "=" in raw:
        for part in raw.split("|"):
            part = part.strip()
            low = part.lower()
            if low.startswith("axis="):
                axis = part[len("axis="):].strip().lower()
            elif low.startswith("mode="):
                mode = part[len("mode="):].strip().lower()
            elif low.startswith("reference=") or low.startswith("ref="):
                eq = part.index("=")
                reference = part[eq + 1:].strip().lower()
    else:
        simple = simple_map.get(raw)
        if simple is None:
            return {"ok": False, "reason": "unknown_align_token", "token": raw}
        axis, mode = simple

    if not axis or not mode:
        return {"ok": False, "reason": "invalid_align_params"}

    return {"ok": True, "axis": axis, "mode": mode, "reference": reference}


def parse_distribute_args(
    arg: str | None,
    *,
    simple_map: dict[str, tuple[str, str]],
) -> dict[str, Any]:
    raw = str(arg or "").strip().lower()
    if not raw:
        return {"ok": False, "reason": "empty_distribute_arg"}

    axis = ""
    mode = ""
    reference = "group"

    if "=" in raw:
        for part in raw.split("|"):
            part = part.strip()
            low = part.lower()
            if low.startswith("axis="):
                axis = part[len("axis="):].strip().lower()
            elif low.startswith("mode="):
                mode = part[len("mode="):].strip().lower()
            elif low.startswith("reference=") or low.startswith("ref="):
                eq = part.index("=")
                reference = part[eq + 1:].strip().lower()
    else:
        simple = simple_map.get(raw)
        if simple is None:
            return {"ok": False, "reason": "unknown_distribute_token", "token": raw}
        axis, mode = simple

    if not axis or not mode:
        return {"ok": False, "reason": "invalid_distribute_params"}

    return {"ok": True, "axis": axis, "mode": mode, "reference": reference}


def parse_snap_args(
    arg: str | None,
    *,
    simple_map: dict[str, tuple[str, str]],
) -> dict[str, Any]:
    raw = str(arg or "").strip().lower()
    if not raw:
        return {"ok": False, "reason": "empty_snap_arg"}

    axes = "xy"
    mode = "nearest"
    step = 0

    if "=" in raw:
        for part in raw.split("|"):
            part = part.strip()
            low = part.lower()
            if low.startswith("step="):
                try:
                    step = int(part[len("step="):])
                except ValueError:
                    return {"ok": False, "reason": "invalid_step_value", "value": part}
            elif low.startswith("axes="):
                axes = part[len("axes="):].strip().lower()
            elif low.startswith("mode="):
                mode = part[len("mode="):].strip().lower()
    else:
        simple = simple_map.get(raw)
        if simple is not None:
            axes, mode = simple
        else:
            try:
                step = int(raw)
            except ValueError:
                return {"ok": False, "reason": "unknown_snap_token", "token": raw}

    if step <= 0:
        return {"ok": False, "reason": "invalid_step"}

    return {"ok": True, "step": int(step), "axes": axes, "mode": mode}


def parse_nudge_args(
    arg: str | None,
    *,
    direction_map: dict[str, tuple[float, float]],
) -> dict[str, Any]:
    raw = str(arg or "").strip()
    if not raw:
        return {"ok": False, "reason": "empty_nudge_arg"}

    dx = 0.0
    dy = 0.0
    count = 1
    step: float | None = None

    if "=" in raw and "|" in raw:
        for part in raw.split("|"):
            part = part.strip()
            low = part.lower()
            if low.startswith("dx="):
                try:
                    dx = float(part[len("dx="):])
                except ValueError:
                    return {"ok": False, "reason": "invalid_dx", "value": part}
            elif low.startswith("dy="):
                try:
                    dy = float(part[len("dy="):])
                except ValueError:
                    return {"ok": False, "reason": "invalid_dy", "value": part}
            elif low.startswith("count="):
                try:
                    count = int(part[len("count="):])
                except ValueError:
                    return {"ok": False, "reason": "invalid_count", "value": part}
            elif low.startswith("step="):
                try:
                    step = float(part[len("step="):])
                except ValueError:
                    return {"ok": False, "reason": "invalid_step", "value": part}
    else:
        tokens = raw.lower().split()
        direction_found = False
        for tok in tokens:
            if tok in direction_map:
                dx, dy = direction_map[tok]
                direction_found = True
            elif tok.startswith("x") and len(tok) > 1:
                try:
                    count = int(tok[1:])
                except ValueError:
                    pass
            elif tok.startswith("count="):
                try:
                    count = int(tok[len("count="):])
                except ValueError:
                    pass
            elif tok.startswith("step="):
                try:
                    step = float(tok[len("step="):])
                except ValueError:
                    pass
        if direction_found and step is None:
            step = 1.0
        if not direction_found:
            return {"ok": False, "reason": "unknown_nudge_token", "token": raw}

    return {"ok": True, "dx": dx, "dy": dy, "count": int(count), "step": step}


def parse_rotate_args(
    arg: str | None,
    *,
    simple_map: dict[str, float],
) -> dict[str, Any]:
    raw = str(arg or "").strip()
    if not raw:
        return {"ok": False, "reason": "empty_rotate_arg"}

    deg = 0.0
    about = "self"

    if "|" in raw or "=" in raw:
        for part in raw.split("|"):
            part = part.strip()
            low = part.lower()
            if low.startswith("deg="):
                try:
                    deg = float(part[len("deg="):])
                except ValueError:
                    return {"ok": False, "reason": "invalid_deg", "value": part}
            elif low.startswith("about="):
                about = part[len("about="):].strip().lower()
    else:
        simple = simple_map.get(raw.lower())
        if simple is not None:
            deg = simple
        else:
            try:
                deg = float(raw)
            except ValueError:
                return {"ok": False, "reason": "unknown_rotate_token", "token": raw}

    return {"ok": True, "deg": float(deg), "about": about}


def parse_toast_and_seconds(
    arg: str | None,
    *,
    parse_float: Callable[[str], float | None],
) -> tuple[str, float | None] | None:
    raw = str(arg or "").strip()
    if not raw:
        return None
    if "|" not in raw:
        return (raw, None)
    toast_part, seconds_part = raw.rsplit("|", 1)
    toast = toast_part.strip()
    seconds_raw = seconds_part.strip()
    if not toast:
        return None
    if not seconds_raw:
        return (toast, None)
    seconds = parse_float(seconds_raw)
    if seconds is None:
        return None
    return (toast, float(seconds))


def parse_planes_toggle_repeat_args(
    arg: str | None,
    *,
    axis_map: dict[str, tuple[str, ...]],
) -> dict[str, Any]:
    raw = str(arg or "").strip().lower()
    if not raw:
        return {"ok": False, "reason": "empty_planes_toggle_repeat_arg"}

    axes = axis_map.get(raw)
    if axes is not None:
        return {"ok": True, "axes": tuple(axes)}

    if "=" in raw:
        for part in raw.split("|"):
            part = part.strip()
            low = part.lower()
            if low.startswith("axis="):
                wanted = part[len("axis="):].strip().lower()
                axes = axis_map.get(wanted)
                if axes is not None:
                    return {"ok": True, "axes": tuple(axes)}
                return {"ok": False, "reason": "unknown_planes_toggle_repeat_axis", "token": wanted}

    return {"ok": False, "reason": "unknown_planes_toggle_repeat_token", "token": raw}


def parse_planes_select_args(
    arg: str | None,
    *,
    mode_map: dict[str, str],
) -> dict[str, Any]:
    raw = str(arg or "").strip()
    if not raw:
        return {"ok": False, "reason": "empty_planes_select_arg"}

    low = raw.lower()
    mapped = mode_map.get(low)
    if mapped is not None:
        return {"ok": True, "mode": mapped}

    if "=" in low:
        for part in raw.split("|"):
            token = part.strip()
            low_token = token.lower()
            if low_token.startswith("mode="):
                wanted = token[len("mode="):].strip().lower()
                mapped = mode_map.get(wanted)
                if mapped is not None:
                    return {"ok": True, "mode": mapped}
                return {"ok": False, "reason": "unknown_planes_select_mode", "token": wanted}
            if low_token.startswith("plane_id="):
                plane_id = token[len("plane_id="):].strip()
                if plane_id:
                    return {"ok": True, "mode": "id", "plane_id": plane_id}
                return {"ok": False, "reason": "empty_plane_id"}

    return {"ok": True, "mode": "id", "plane_id": raw}


def parse_planes_move_to_args(
    arg: str | None,
    *,
    mode_map: dict[str, str],
) -> dict[str, Any]:
    raw = str(arg or "").strip()
    if not raw:
        return {"ok": False, "reason": "empty_planes_move_to_arg"}

    low = raw.lower()
    mapped = mode_map.get(low)
    if mapped is not None:
        return {"ok": True, "mode": mapped}

    if "=" in raw:
        for part in raw.split("|"):
            token = part.strip()
            low_token = token.lower()
            if low_token.startswith("mode="):
                wanted = token[len("mode="):].strip().lower()
                mapped = mode_map.get(wanted)
                if mapped is not None:
                    return {"ok": True, "mode": mapped}
                return {"ok": False, "reason": "unknown_planes_move_to_mode", "token": wanted}
            if low_token.startswith("index="):
                raw_index = token[len("index="):].strip()
                try:
                    index = int(raw_index)
                except ValueError:
                    return {"ok": False, "reason": "invalid_planes_move_to_index", "token": raw_index}
                if index < 0:
                    return {"ok": False, "reason": "invalid_planes_move_to_index", "token": raw_index}
                return {"ok": True, "mode": "index", "index": index}

    try:
        index = int(low)
    except ValueError:
        return {"ok": False, "reason": "unknown_planes_move_to_token", "token": low}
    if index < 0:
        return {"ok": False, "reason": "invalid_planes_move_to_index", "token": raw}
    return {"ok": True, "mode": "index", "index": index}
