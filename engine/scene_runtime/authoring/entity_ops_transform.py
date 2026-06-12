from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any, Callable, Dict

if TYPE_CHECKING:
    from ...scene_controller import SceneController


_SNAP_VALID_AXES = frozenset({"x", "y", "xy"})
_SNAP_VALID_MODES = frozenset({"nearest", "floor", "ceil"})
_ROTATE_VALID_ABOUT = frozenset({"self", "primary", "group"})
_MIRROR_VALID_AXES = frozenset({"x", "y"})
_MIRROR_VALID_ABOUT = frozenset({"group", "primary"})


def debug_snap_to_grid(
    controller: "SceneController",
    entity_ids: list[str],
    step: int,
    axes: str = "xy",
    mode: str = "nearest",
    *,
    sorted_dedup_ids: Callable[[list[str] | None], list[str]],
    get_authored_scene_payload: Callable[["SceneController"], Dict[str, Any]],
    debug_apply_authored_scene_payload: Callable[["SceneController", Dict[str, Any]], bool],
    build_entity_index: Callable[[list[Dict[str, Any]]], dict[str, Dict[str, Any]]],
    snap_value: Callable[[float, int, str], float],
) -> dict:
    """Debug-only: snap selected entities to a grid.

    *step* - positive integer grid spacing.
    *axes* - ``"x"``, ``"y"``, or ``"xy"``.
    *mode* - ``"nearest"`` (half-up), ``"floor"``, or ``"ceil"``.

    Returns ``{ok, moved, skipped, step, axes, mode}``.
    """
    from ...entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

    ax = str(axes or "xy").strip().lower()
    md = str(mode or "nearest").strip().lower()
    st = int(step) if isinstance(step, (int, float)) else 0

    fail: dict = {"ok": False, "moved": 0, "skipped": 0, "step": st, "axes": ax, "mode": md}

    if ax not in _SNAP_VALID_AXES:
        return fail
    if md not in _SNAP_VALID_MODES:
        return fail
    if st <= 0:
        return fail

    dedup_ids = sorted_dedup_ids(entity_ids)
    if not dedup_ids:
        return fail

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return fail
    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)
    index = build_entity_index(entities)

    moved = 0
    skipped = 0
    snap_x = "x" in ax
    snap_y = "y" in ax

    for eid in dedup_ids:
        ent = index.get(eid)
        if not isinstance(ent, dict):
            skipped += 1
            continue
        if is_player_entity(ent):
            skipped += 1
            continue
        if "x" not in ent and "y" not in ent:
            skipped += 1
            continue

        changed = False
        if snap_x and "x" in ent:
            new_x = snap_value(float(ent["x"]), st, md)
            if abs(new_x - float(ent["x"])) > 1e-9:
                ent["x"] = new_x
                changed = True
        if snap_y and "y" in ent:
            new_y = snap_value(float(ent["y"]), st, md)
            if abs(new_y - float(ent["y"])) > 1e-9:
                ent["y"] = new_y
                changed = True
        if changed:
            moved += 1

    if moved > 0:
        debug_apply_authored_scene_payload(controller, authored_copy)
    return {"ok": moved > 0, "moved": moved, "skipped": skipped, "step": st, "axes": ax, "mode": md}


def debug_nudge_selection(
    controller: "SceneController",
    entity_ids: list[str],
    dx: float,
    dy: float,
    count: int = 1,
    step: float | None = None,
    *,
    sorted_dedup_ids: Callable[[list[str] | None], list[str]],
    get_authored_scene_payload: Callable[["SceneController"], Dict[str, Any]],
    debug_apply_authored_scene_payload: Callable[["SceneController", Dict[str, Any]], bool],
    build_entity_index: Callable[[list[Dict[str, Any]]], dict[str, Dict[str, Any]]],
) -> dict:
    """Debug-only: nudge selected entities by a deterministic delta.

    *dx*, *dy* - direction / raw delta.
    *count* - repeat multiplier (must be >= 1).
    *step* - if provided (> 0), scales dx/dy as direction multipliers.

    Effective delta:
        If *step* is not None:  eff_dx = dx * step * count
        Else:                   eff_dx = dx * count
    (same for dy.)

    Returns ``{ok, moved, skipped, dx, dy, count, step}``.
    """
    from ...entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

    cnt = int(count) if isinstance(count, (int, float)) else 0
    raw_dx = float(dx)
    raw_dy = float(dy)
    st: float | None = None
    if step is not None:
        st = float(step)

    fail: dict = {"ok": False, "moved": 0, "skipped": 0, "dx": 0.0, "dy": 0.0, "count": cnt, "step": st}

    if cnt < 1:
        return fail
    if st is not None and st <= 0:
        return fail

    if st is not None:
        eff_dx = raw_dx * st * cnt
        eff_dy = raw_dy * st * cnt
    else:
        eff_dx = raw_dx * cnt
        eff_dy = raw_dy * cnt

    result_base: dict = {"ok": True, "moved": 0, "skipped": 0, "dx": eff_dx, "dy": eff_dy, "count": cnt, "step": st}

    if abs(eff_dx) < 1e-9 and abs(eff_dy) < 1e-9:
        return result_base  # no-op, ok=true

    dedup_ids = sorted_dedup_ids(entity_ids)
    if not dedup_ids:
        fail["dx"] = eff_dx
        fail["dy"] = eff_dy
        return fail

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        fail["dx"] = eff_dx
        fail["dy"] = eff_dy
        return fail
    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)
    index = build_entity_index(entities)

    moved = 0
    skipped = 0

    for eid in dedup_ids:
        ent = index.get(eid)
        if not isinstance(ent, dict):
            skipped += 1
            continue
        if is_player_entity(ent):
            skipped += 1
            continue
        if "x" not in ent and "y" not in ent:
            skipped += 1
            continue

        if "x" in ent:
            ent["x"] = float(ent["x"]) + eff_dx
        if "y" in ent:
            ent["y"] = float(ent["y"]) + eff_dy
        moved += 1

    if moved > 0:
        debug_apply_authored_scene_payload(controller, authored_copy)
    return {"ok": moved > 0, "moved": moved, "skipped": skipped, "dx": eff_dx, "dy": eff_dy, "count": cnt, "step": st}


def debug_rotate_selection(
    controller: "SceneController",
    entity_ids: list[str],
    deg: float,
    about: str = "self",
    primary_id: str = "",
    *,
    sorted_dedup_ids: Callable[[list[str] | None], list[str]],
    get_authored_scene_payload: Callable[["SceneController"], Dict[str, Any]],
    debug_apply_authored_scene_payload: Callable[["SceneController", Dict[str, Any]], bool],
    build_entity_index: Callable[[list[Dict[str, Any]]], dict[str, Dict[str, Any]]],
) -> dict:
    """Debug-only: rotate selected entities by *deg* degrees.

    *about* controls pivot behaviour:
    - ``"self"`` - rotate each entity's own ``rotation`` field only.
    - ``"primary"`` - also rotate positions around the primary entity's centre.
    - ``"group"`` - also rotate positions around the group centroid.

    Rotation is clockwise-positive (matching engine coordinate conventions).
    The ``rotation`` field is normalised to [0, 360).

    Returns ``{ok, rotated, moved, skipped, deg, about}``.
    """
    import math  # noqa: PLC0415

    from ...entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

    ab = str(about or "self").strip().lower()
    d = float(deg)

    fail: dict = {"ok": False, "rotated": 0, "moved": 0, "skipped": 0, "deg": d, "about": ab}

    if ab not in _ROTATE_VALID_ABOUT:
        return fail

    if abs(d) < 1e-9:
        return {"ok": True, "rotated": 0, "moved": 0, "skipped": 0, "deg": d, "about": ab}

    dedup_ids = sorted_dedup_ids(entity_ids)
    if not dedup_ids:
        return {"ok": True, "rotated": 0, "moved": 0, "skipped": 0, "deg": d, "about": ab}

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return fail
    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)
    index = build_entity_index(entities)

    # Collect participating entities (skip player / missing position).
    participants: list[tuple[str, dict]] = []
    skipped = 0
    for eid in dedup_ids:
        ent = index.get(eid)
        if not isinstance(ent, dict):
            skipped += 1
            continue
        if is_player_entity(ent):
            skipped += 1
            continue
        participants.append((eid, ent))

    if not participants:
        return {"ok": True, "rotated": 0, "moved": 0, "skipped": skipped, "deg": d, "about": ab}

    # Determine pivot for position rotation.
    pivot: tuple[float, float] | None = None
    if ab == "primary":
        pid = str(primary_id or "").strip()
        if pid:
            pent = index.get(pid)
            if isinstance(pent, dict) and "x" in pent and "y" in pent:
                pivot = (float(pent["x"]), float(pent["y"]))
        if pivot is None:
            return fail
    elif ab == "group":
        xs: list[float] = []
        ys: list[float] = []
        for _eid, ent in participants:
            if "x" in ent and "y" in ent:
                xs.append(float(ent["x"]))
                ys.append(float(ent["y"]))
        if not xs:
            return fail
        pivot = (sum(xs) / len(xs), sum(ys) / len(ys))

    rad = math.radians(d)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)

    rotated = 0
    moved = 0
    for _eid, ent in participants:
        # Rotate the entity's own rotation field.
        old_rot = float(ent.get("rotation", 0.0))
        new_rot = (old_rot + d) % 360.0
        ent["rotation"] = new_rot
        rotated += 1

        # Rotate position around pivot if requested.
        if pivot is not None and "x" in ent and "y" in ent:
            ox = float(ent["x"]) - pivot[0]
            oy = float(ent["y"]) - pivot[1]
            nx = ox * cos_a - oy * sin_a + pivot[0]
            ny = ox * sin_a + oy * cos_a + pivot[1]
            if abs(nx - float(ent["x"])) > 1e-9 or abs(ny - float(ent["y"])) > 1e-9:
                ent["x"] = nx
                ent["y"] = ny
                moved += 1

    if rotated > 0 or moved > 0:
        debug_apply_authored_scene_payload(controller, authored_copy)
    return {"ok": True, "rotated": rotated, "moved": moved, "skipped": skipped, "deg": d, "about": ab}


def debug_mirror_selection(
    controller: "SceneController",
    entity_ids: list[str],
    axis: str,
    about: str = "group",
    primary_id: str = "",
    include_rotation: bool = True,
    *,
    sorted_dedup_ids: Callable[[list[str] | None], list[str]],
    get_authored_scene_payload: Callable[["SceneController"], Dict[str, Any]],
    debug_apply_authored_scene_payload: Callable[["SceneController", Dict[str, Any]], bool],
    build_entity_index: Callable[[list[Dict[str, Any]]], dict[str, Dict[str, Any]]],
) -> dict:
    """Debug-only: mirror / flip selected entities across an axis.

    *axis* = ``"x"`` mirrors across a vertical line (flips left/right):
        ``x' = 2*px - x``
    *axis* = ``"y"`` mirrors across a horizontal line (flips up/down):
        ``y' = 2*py - y``

    *about* = ``"group"`` uses the centroid of participating positions as
    pivot. ``"primary"`` uses the primary entity's position.

    If *include_rotation* is True, entity ``rotation`` fields are mirrored too:
        axis="x": ``new_rot = (360 - rot) % 360``
        axis="y": ``new_rot = (180 - rot) % 360``

    Returns ``{ok, moved, rotated, skipped, axis, about, include_rotation}``.
    """
    from ...entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

    ax = str(axis or "").strip().lower()
    ab = str(about or "group").strip().lower()
    inc_rot = bool(include_rotation)

    fail: dict = {
        "ok": False, "moved": 0, "rotated": 0, "skipped": 0,
        "axis": ax, "about": ab, "include_rotation": inc_rot,
    }

    if ax not in _MIRROR_VALID_AXES:
        return fail
    if ab not in _MIRROR_VALID_ABOUT:
        return fail

    dedup_ids = sorted_dedup_ids(entity_ids)
    if not dedup_ids:
        return {"ok": True, "moved": 0, "rotated": 0, "skipped": 0, "axis": ax, "about": ab, "include_rotation": inc_rot}

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return fail
    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)
    index = build_entity_index(entities)

    # Collect participating entities (have position, not player).
    participants: list[tuple[str, dict]] = []
    skipped = 0
    for eid in dedup_ids:
        ent = index.get(eid)
        if not isinstance(ent, dict):
            skipped += 1
            continue
        if is_player_entity(ent):
            skipped += 1
            continue
        if "x" not in ent or "y" not in ent:
            skipped += 1
            continue
        participants.append((eid, ent))

    if not participants:
        return {"ok": True, "moved": 0, "rotated": 0, "skipped": skipped, "axis": ax, "about": ab, "include_rotation": inc_rot}

    # Determine pivot.
    if ab == "primary":
        pid = str(primary_id or "").strip()
        if not pid:
            return fail
        pent = index.get(pid)
        if not isinstance(pent, dict) or "x" not in pent or "y" not in pent:
            return fail
        pivot = (float(pent["x"]), float(pent["y"]))
    else:
        # group centroid
        xs = [float(ent["x"]) for _eid, ent in participants]
        ys = [float(ent["y"]) for _eid, ent in participants]
        pivot = (sum(xs) / len(xs), sum(ys) / len(ys))

    moved = 0
    rotated = 0

    for _eid, ent in participants:
        ex = float(ent["x"])
        ey = float(ent["y"])

        if ax == "x":
            new_x = 2.0 * pivot[0] - ex
            if abs(new_x - ex) > 1e-9:
                ent["x"] = new_x
                moved += 1
        else:
            new_y = 2.0 * pivot[1] - ey
            if abs(new_y - ey) > 1e-9:
                ent["y"] = new_y
                moved += 1

        if inc_rot:
            old_rot = float(ent.get("rotation", 0.0))
            if ax == "x":
                new_rot = (360.0 - old_rot) % 360.0
            else:
                new_rot = (180.0 - old_rot) % 360.0
            if abs(new_rot - old_rot) > 1e-9:
                ent["rotation"] = new_rot
                rotated += 1

    if moved > 0 or rotated > 0:
        debug_apply_authored_scene_payload(controller, authored_copy)
    return {
        "ok": moved > 0 or rotated > 0 or True,
        "moved": moved, "rotated": rotated, "skipped": skipped,
        "axis": ax, "about": ab, "include_rotation": inc_rot,
    }
