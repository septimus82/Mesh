from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any, Callable, Dict

from . import entity_ops_geometry as _geometry_helpers

if TYPE_CHECKING:
    from ...scene_controller import SceneController


_ALIGN_X_MODES = frozenset({"left", "center", "right"})
_ALIGN_Y_MODES = frozenset({"top", "middle", "bottom"})
_ALIGN_VALID_AXES = frozenset({"x", "y"})
_ALIGN_VALID_REFS = frozenset({"primary", "group"})
_DISTRIBUTE_VALID_MODES = frozenset({"gap", "center"})


def debug_align_selection(
    controller: "SceneController",
    entity_ids: list[str],
    axis: str,
    mode: str,
    reference: str = "primary",
    primary_id: str = "",
    *,
    sorted_dedup_ids: Callable[[list[str] | None], list[str]],
    get_authored_scene_payload: Callable[["SceneController"], Dict[str, Any]],
    debug_apply_authored_scene_payload: Callable[["SceneController", Dict[str, Any]], bool],
    build_entity_index: Callable[[list[Dict[str, Any]]], dict[str, Dict[str, Any]]],
    entity_bounds: Callable[[dict[str, Any]], tuple[float, float, float, float] | None] | None = None,
    anchor_value: Callable[[float, float, float, float, str, str], float] | None = None,
) -> dict[str, Any]:
    """
    Debug-only: align selected authored entities along *axis* to the anchor
    determined by *mode* and *reference*.

    *reference* = ``"primary"`` uses the entity identified by *primary_id* as
    the alignment target. ``"group"`` computes the anchor from the
    min/max/center of the entire selection.

    Returns ``{ok, moved, skipped, axis, mode, reference}``.
    """
    from ...entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

    bounds_fn = entity_bounds or _geometry_helpers._entity_bounds
    anchor_fn = anchor_value or _geometry_helpers._anchor_value

    ax = str(axis or "").strip().lower()
    md = str(mode or "").strip().lower()
    ref = str(reference or "primary").strip().lower()

    fail = {"ok": False, "moved": 0, "skipped": 0, "axis": ax, "mode": md, "reference": ref}

    if ax not in _ALIGN_VALID_AXES:
        return fail
    valid_modes = _ALIGN_X_MODES if ax == "x" else _ALIGN_Y_MODES
    if md not in valid_modes:
        return fail
    if ref not in _ALIGN_VALID_REFS:
        return fail

    dedup_ids = sorted_dedup_ids(entity_ids)
    if len(dedup_ids) < 2:
        return fail

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return fail
    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)
    index = build_entity_index(entities)

    # Gather bounds for all selected non-player entities.
    bounds_map: dict[str, tuple[float, float, float, float]] = {}
    skipped = 0
    for eid in dedup_ids:
        ent = index.get(eid)
        if not isinstance(ent, dict):
            skipped += 1
            continue
        if is_player_entity(ent):
            skipped += 1
            continue
        b = bounds_fn(ent)
        if b is None:
            skipped += 1
            continue
        bounds_map[eid] = b

    if len(bounds_map) < 2:
        return fail

    # Determine target anchor value.
    pid = str(primary_id or "").strip()
    if ref == "primary" and pid and pid in bounds_map:
        pcx, pcy, phw, phh = bounds_map[pid]
        target = anchor_fn(pcx, pcy, phw, phh, ax, md)
    else:
        # Fall back to group anchor.
        anchors = [anchor_fn(cx, cy, hw, hh, ax, md) for cx, cy, hw, hh in bounds_map.values()]
        if md in ("left", "bottom"):
            target = min(anchors)
        elif md in ("right", "top"):
            target = max(anchors)
        else:
            target = sum(anchors) / len(anchors)  # center / middle

    # Apply moves.
    moved = 0
    for eid in dedup_ids:
        if eid not in bounds_map:
            continue
        cx, cy, hw, hh = bounds_map[eid]
        current_anchor = anchor_fn(cx, cy, hw, hh, ax, md)
        delta = target - current_anchor
        if abs(delta) < 1e-6:
            continue
        ent = index.get(eid)
        if not isinstance(ent, dict):
            continue
        if ax == "x":
            ent["x"] = cx + delta
        else:
            ent["y"] = cy + delta
        moved += 1

    if moved > 0:
        debug_apply_authored_scene_payload(controller, authored_copy)
    return {"ok": True, "moved": moved, "skipped": skipped, "axis": ax, "mode": md, "reference": ref}


def debug_distribute_selection(
    controller: "SceneController",
    entity_ids: list[str],
    axis: str,
    mode: str = "gap",
    reference: str = "group",
    primary_id: str = "",
    *,
    sorted_dedup_ids: Callable[[list[str] | None], list[str]],
    get_authored_scene_payload: Callable[["SceneController"], Dict[str, Any]],
    debug_apply_authored_scene_payload: Callable[["SceneController", Dict[str, Any]], bool],
    build_entity_index: Callable[[list[Dict[str, Any]]], dict[str, Dict[str, Any]]],
    entity_bounds: Callable[[dict[str, Any]], tuple[float, float, float, float] | None] | None = None,
) -> dict[str, Any]:
    """
    Debug-only: distribute selected authored entities evenly along *axis*.

    *mode* = ``"gap"``  - equal spacing between bounding-box edges.
    *mode* = ``"center"`` - equal spacing between entity centres.

    *reference* = ``"group"`` uses the overall min/max of the selection as
    the fixed endpoints. ``"primary"`` uses the primary entity as one
    endpoint and the furthest entity as the other.

    Entities are sorted by their current position on *axis* before spacing
    is computed. The two endpoint entities are kept in place; interior
    entities are redistributed.

    Returns ``{ok, moved, skipped, axis, mode, reference}``.
    """
    from ...entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

    bounds_fn = entity_bounds or _geometry_helpers._entity_bounds

    ax = str(axis or "").strip().lower()
    md = str(mode or "gap").strip().lower()
    ref = str(reference or "group").strip().lower()

    fail = {"ok": False, "moved": 0, "skipped": 0, "axis": ax, "mode": md, "reference": ref}

    if ax not in _ALIGN_VALID_AXES:
        return fail
    if md not in _DISTRIBUTE_VALID_MODES:
        return fail
    if ref not in _ALIGN_VALID_REFS:
        return fail

    dedup_ids = sorted_dedup_ids(entity_ids)
    if len(dedup_ids) < 3:
        return fail

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return fail
    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)
    index = build_entity_index(entities)

    # Gather bounds.
    bounds_map: dict[str, tuple[float, float, float, float]] = {}
    skipped = 0
    for eid in dedup_ids:
        ent = index.get(eid)
        if not isinstance(ent, dict):
            skipped += 1
            continue
        if is_player_entity(ent):
            skipped += 1
            continue
        b = bounds_fn(ent)
        if b is None:
            skipped += 1
            continue
        bounds_map[eid] = b

    if len(bounds_map) < 3:
        return fail

    # Sort participating entities by current center on the chosen axis.
    ax_idx = 0 if ax == "x" else 1  # index into (cx, cy, hw, hh)
    ordered = sorted(bounds_map.keys(), key=lambda e: bounds_map[e][ax_idx])

    first_eid = ordered[0]
    last_eid = ordered[-1]

    if md == "center":
        # Equal spacing between centres.
        first_center = bounds_map[first_eid][ax_idx]
        last_center = bounds_map[last_eid][ax_idx]
        n = len(ordered)
        step = (last_center - first_center) / (n - 1) if n > 1 else 0.0

        moved = 0
        for i, eid in enumerate(ordered):
            target_center = first_center + step * i
            cx, cy, hw, hh = bounds_map[eid]
            current_center = bounds_map[eid][ax_idx]
            delta = target_center - current_center
            if abs(delta) < 1e-6:
                continue
            ent = index.get(eid)
            if not isinstance(ent, dict):
                continue
            if ax == "x":
                ent["x"] = cx + delta
            else:
                ent["y"] = cy + delta
            moved += 1
    else:
        # mode == "gap": equal spacing between bounding-box edges.
        hw_idx = 2 if ax == "x" else 3  # half-width or half-height index
        # Total extent from first left-edge to last right-edge.
        first_left = bounds_map[first_eid][ax_idx] - bounds_map[first_eid][hw_idx]
        last_right = bounds_map[last_eid][ax_idx] + bounds_map[last_eid][hw_idx]
        total_span = last_right - first_left
        total_entity_size = sum(bounds_map[e][hw_idx] * 2.0 for e in ordered)
        total_gap = total_span - total_entity_size
        n_gaps = len(ordered) - 1
        gap = total_gap / n_gaps if n_gaps > 0 else 0.0

        moved = 0
        cursor = first_left
        for eid in ordered:
            cx, cy, hw_val, hh_val = bounds_map[eid]
            entity_half = bounds_map[eid][hw_idx]
            target_center = cursor + entity_half
            current_center = bounds_map[eid][ax_idx]
            delta = target_center - current_center
            cursor = target_center + entity_half + gap
            if abs(delta) < 1e-6:
                continue
            ent = index.get(eid)
            if not isinstance(ent, dict):
                continue
            if ax == "x":
                ent["x"] = cx + delta
            else:
                ent["y"] = cy + delta
            moved += 1

    if moved > 0:
        debug_apply_authored_scene_payload(controller, authored_copy)
    return {"ok": True, "moved": moved, "skipped": skipped, "axis": ax, "mode": md, "reference": ref}
