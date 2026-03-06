from __future__ import annotations

import json
from typing import Any

from ._shared import (
    _get_authored_payload,
    _get_selection_ids_and_primary,
    _parse_align_args,
    _parse_distribute_args,
    _parse_nudge_args,
    _parse_rotate_args,
    _parse_snap_args,
    _set_last_props_action,
)

def action_batch_rename(w: Any, arg: str | None) -> None:
    """Batch rename selected entities with prefix/suffix.

    Argument format: ``prefix=<p>|suffix=<s>`` (either part optional).
    Examples: ``prefix=NPC_``, ``suffix=_v2``, ``prefix=Old_|suffix=_bak``.
    """
    selected_ids, _primary = _get_selection_ids_and_primary(w)
    if not selected_ids:
        print("ENTITY_PROPS noop reason=no_selection")
        return
    raw = str(arg or "").strip()
    if not raw:
        print("ENTITY_PROPS noop reason=empty_rename_arg")
        return
    prefix = ""
    suffix = ""
    for part in raw.split("|"):
        part = part.strip()
        if part.lower().startswith("prefix="):
            prefix = part[len("prefix="):]
        elif part.lower().startswith("suffix="):
            suffix = part[len("suffix="):]
    if not prefix and not suffix:
        print("ENTITY_PROPS noop reason=empty_rename_arg")
        return
    authored = _get_authored_payload(w)
    if authored is None:
        print("ENTITY_PROPS noop reason=no_authored_payload")
        return
    pusher = getattr(w, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_batch_rename")
    sc = getattr(w, "scene_controller", None)
    renamer = getattr(sc, "debug_batch_rename", None) if sc is not None else None
    if not callable(renamer):
        print("ENTITY_PROPS noop reason=no_scene_controller")
        return
    changed, skipped = renamer(selected_ids, prefix=prefix, suffix=suffix)
    if changed <= 0:
        print("ENTITY_PROPS noop reason=no_changes")
        return
    marker = getattr(w, "mark_scene_dirty", None)
    if callable(marker):
        marker("entity_batch_rename")
    _set_last_props_action(w, action="batch_rename", changed=int(changed))
    print(f"ENTITY_PROPS ok action=batch_rename changed={int(changed)} skipped_player={int(skipped)}")


def action_set_names(w: Any, arg: str | None) -> None:
    """Set numbered names on selected entities.

    Argument format: plain ``NPC`` or key/value ``base=NPC|start=1|width=3``.
    """
    selected_ids, _primary = _get_selection_ids_and_primary(w)
    if not selected_ids:
        print("ENTITY_PROPS noop reason=no_selection")
        return
    raw = str(arg or "").strip()
    if not raw:
        print("ENTITY_PROPS noop reason=empty_set_names_arg")
        return
    base = ""
    start = 1
    width = 3
    if "=" in raw:
        for part in raw.split("|"):
            part = part.strip()
            low = part.lower()
            if low.startswith("base="):
                base = part[len("base="):].strip()
            elif low.startswith("start="):
                try:
                    start = int(part[len("start="):])
                except (ValueError, TypeError):
                    pass
            elif low.startswith("width="):
                try:
                    width = int(part[len("width="):])
                except (ValueError, TypeError):
                    pass
    else:
        base = raw
    if not base:
        print("ENTITY_PROPS noop reason=empty_set_names_arg")
        return
    authored = _get_authored_payload(w)
    if authored is None:
        print("ENTITY_PROPS noop reason=no_authored_payload")
        return
    pusher = getattr(w, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_set_names")
    sc = getattr(w, "scene_controller", None)
    setter = getattr(sc, "debug_set_names", None) if sc is not None else None
    if not callable(setter):
        print("ENTITY_PROPS noop reason=no_scene_controller")
        return
    result = setter(selected_ids, base, start=start, width=width)
    ok = result.get("ok", False) if isinstance(result, dict) else False
    renamed = result.get("renamed", 0) if isinstance(result, dict) else 0
    skipped = result.get("skipped", 0) if isinstance(result, dict) else 0
    if not ok or renamed <= 0:
        print(f"ENTITY_PROPS noop reason=no_changes ok={ok}")
        return
    marker = getattr(w, "mark_scene_dirty", None)
    if callable(marker):
        marker("entity_set_names")
    _set_last_props_action(w, action="set_names", changed=int(renamed))
    print(f"ENTITY_PROPS ok action=set_names renamed={renamed} skipped={skipped} base={base} start={start} width={width}")


def action_align_selection(w: Any, arg: str | None) -> None:
    """Align selected entities along an axis.

    Argument format:
    - simple: ``left``, ``center``, ``right``, ``top``, ``middle``, ``bottom``
    - key/value: ``axis=x|mode=left|reference=primary``
    """
    selected_ids, primary = _get_selection_ids_and_primary(w)
    if not selected_ids:
        print("ENTITY_PROPS noop reason=no_selection")
        return
    parsed = _parse_align_args(arg)
    if not bool(parsed.get("ok", False)):
        reason = str(parsed.get("reason", "") or "")
        if reason == "empty_align_arg":
            print("ENTITY_PROPS noop reason=empty_align_arg")
            return
        if reason == "unknown_align_token":
            print(f"ENTITY_PROPS noop reason=unknown_align_token token={parsed.get('token', '')}")
            return
        print("ENTITY_PROPS noop reason=invalid_align_params")
        return
    axis = str(parsed.get("axis", "") or "")
    mode = str(parsed.get("mode", "") or "")
    reference = str(parsed.get("reference", "primary") or "primary")

    authored = _get_authored_payload(w)
    if authored is None:
        print("ENTITY_PROPS noop reason=no_authored_payload")
        return
    pusher = getattr(w, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_align_selection")
    sc = getattr(w, "scene_controller", None)
    aligner = getattr(sc, "debug_align_selection", None) if sc is not None else None
    if not callable(aligner):
        print("ENTITY_PROPS noop reason=no_scene_controller")
        return
    result = aligner(selected_ids, axis, mode, reference=reference, primary_id=primary)
    ok = result.get("ok", False) if isinstance(result, dict) else False
    moved = result.get("moved", 0) if isinstance(result, dict) else 0
    skipped = result.get("skipped", 0) if isinstance(result, dict) else 0
    if not ok or moved <= 0:
        print(f"ENTITY_PROPS noop reason=no_changes ok={ok}")
        return
    marker = getattr(w, "mark_scene_dirty", None)
    if callable(marker):
        marker("entity_align_selection")
    _set_last_props_action(w, action="align_selection", changed=int(moved))
    print(f"ENTITY_PROPS ok action=align_selection moved={moved} skipped={skipped} axis={axis} mode={mode} reference={reference}")


def action_distribute_selection(w: Any, arg: str | None) -> None:
    """Distribute selected entities evenly along an axis.

    Argument format:
    - simple: ``distribute_x_gap``, ``distribute_x_center``, ``distribute_y_gap``, ``distribute_y_center``
    - key/value: ``axis=x|mode=gap|reference=group``
    """
    selected_ids, primary = _get_selection_ids_and_primary(w)
    if not selected_ids:
        print("ENTITY_PROPS noop reason=no_selection")
        return
    parsed = _parse_distribute_args(arg)
    if not bool(parsed.get("ok", False)):
        reason = str(parsed.get("reason", "") or "")
        if reason == "empty_distribute_arg":
            print("ENTITY_PROPS noop reason=empty_distribute_arg")
            return
        if reason == "unknown_distribute_token":
            print(f"ENTITY_PROPS noop reason=unknown_distribute_token token={parsed.get('token', '')}")
            return
        print("ENTITY_PROPS noop reason=invalid_distribute_params")
        return
    axis = str(parsed.get("axis", "") or "")
    mode = str(parsed.get("mode", "") or "")
    reference = str(parsed.get("reference", "group") or "group")

    authored = _get_authored_payload(w)
    if authored is None:
        print("ENTITY_PROPS noop reason=no_authored_payload")
        return
    pusher = getattr(w, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_distribute_selection")
    sc = getattr(w, "scene_controller", None)
    distributor = getattr(sc, "debug_distribute_selection", None) if sc is not None else None
    if not callable(distributor):
        print("ENTITY_PROPS noop reason=no_scene_controller")
        return
    result = distributor(selected_ids, axis, mode, reference=reference, primary_id=primary)
    ok = result.get("ok", False) if isinstance(result, dict) else False
    moved = result.get("moved", 0) if isinstance(result, dict) else 0
    skipped = result.get("skipped", 0) if isinstance(result, dict) else 0
    if not ok or moved <= 0:
        print(f"ENTITY_PROPS noop reason=no_changes ok={ok}")
        return
    marker = getattr(w, "mark_scene_dirty", None)
    if callable(marker):
        marker("entity_distribute_selection")
    _set_last_props_action(w, action="distribute_selection", changed=int(moved))
    print(f"ENTITY_PROPS ok action=distribute_selection moved={moved} skipped={skipped} axis={axis} mode={mode} reference={reference}")


def action_snap_to_grid(w: Any, arg: str | None) -> None:
    """Snap selected entities to a grid.

    Argument format:
    - simple: ``snap_nearest``, ``snap_floor``, ``snap_ceil``, ``snap_x_nearest``, ``snap_y_nearest``
    - key/value: ``step=16|axes=xy|mode=nearest``
    """
    selected_ids, _primary = _get_selection_ids_and_primary(w)
    if not selected_ids:
        print("ENTITY_PROPS noop reason=no_selection")
        return
    parsed = _parse_snap_args(arg)
    if not bool(parsed.get("ok", False)):
        reason = str(parsed.get("reason", "") or "")
        if reason == "empty_snap_arg":
            print("ENTITY_PROPS noop reason=empty_snap_arg")
            return
        if reason == "invalid_step_value":
            print(f"ENTITY_PROPS noop reason=invalid_step value={parsed.get('value', '')}")
            return
        if reason == "unknown_snap_token":
            print(f"ENTITY_PROPS noop reason=unknown_snap_token token={parsed.get('token', '')}")
            return
        print("ENTITY_PROPS noop reason=invalid_step")
        return
    axes = str(parsed.get("axes", "xy") or "xy")
    mode = str(parsed.get("mode", "nearest") or "nearest")
    step = int(parsed.get("step", 0) or 0)

    authored = _get_authored_payload(w)
    if authored is None:
        print("ENTITY_PROPS noop reason=no_authored_payload")
        return
    pusher = getattr(w, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_snap_to_grid")
    sc = getattr(w, "scene_controller", None)
    snapper = getattr(sc, "debug_snap_to_grid", None) if sc is not None else None
    if not callable(snapper):
        print("ENTITY_PROPS noop reason=no_scene_controller")
        return
    result = snapper(selected_ids, step, axes=axes, mode=mode)
    ok = result.get("ok", False) if isinstance(result, dict) else False
    moved = result.get("moved", 0) if isinstance(result, dict) else 0
    skipped = result.get("skipped", 0) if isinstance(result, dict) else 0
    if not ok or moved <= 0:
        print(f"ENTITY_PROPS noop reason=no_changes ok={ok}")
        return
    marker = getattr(w, "mark_scene_dirty", None)
    if callable(marker):
        marker("entity_snap_to_grid")
    _set_last_props_action(w, action="snap_to_grid", changed=int(moved))
    print(f"ENTITY_PROPS ok action=snap_to_grid moved={moved} skipped={skipped} step={step} axes={axes} mode={mode}")


def action_nudge_selection(w: Any, arg: str | None) -> None:
    """Nudge selected entities by a delta.

    Argument format:
    - direction token: ``left``, ``right``, ``up``, ``down``
      optional suffixes: ``xN`` or ``count=N``, ``step=S``
      Example: ``right x3 step=16``
    - key/value: ``dx=1|dy=0|count=3|step=16``
    """
    selected_ids, _primary = _get_selection_ids_and_primary(w)
    if not selected_ids:
        print("ENTITY_PROPS noop reason=no_selection")
        return
    parsed = _parse_nudge_args(arg)
    if not bool(parsed.get("ok", False)):
        reason = str(parsed.get("reason", "") or "")
        if reason == "empty_nudge_arg":
            print("ENTITY_PROPS noop reason=empty_nudge_arg")
            return
        if reason == "invalid_dx":
            print(f"ENTITY_PROPS noop reason=invalid_dx value={parsed.get('value', '')}")
            return
        if reason == "invalid_dy":
            print(f"ENTITY_PROPS noop reason=invalid_dy value={parsed.get('value', '')}")
            return
        if reason == "invalid_count":
            print(f"ENTITY_PROPS noop reason=invalid_count value={parsed.get('value', '')}")
            return
        if reason == "invalid_step":
            print(f"ENTITY_PROPS noop reason=invalid_step value={parsed.get('value', '')}")
            return
        print(f"ENTITY_PROPS noop reason=unknown_nudge_token token={parsed.get('token', '')}")
        return
    dx = float(parsed.get("dx", 0.0) or 0.0)
    dy = float(parsed.get("dy", 0.0) or 0.0)
    count = int(parsed.get("count", 1) or 1)
    step_value = parsed.get("step", None)
    step: float | None = float(step_value) if isinstance(step_value, (int, float)) else None

    authored = _get_authored_payload(w)
    if authored is None:
        print("ENTITY_PROPS noop reason=no_authored_payload")
        return
    pusher = getattr(w, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_nudge_selection")
    sc = getattr(w, "scene_controller", None)
    nudger = getattr(sc, "debug_nudge_selection", None) if sc is not None else None
    if not callable(nudger):
        print("ENTITY_PROPS noop reason=no_scene_controller")
        return
    result = nudger(selected_ids, dx, dy, count=count, step=step)
    ok = result.get("ok", False) if isinstance(result, dict) else False
    moved = result.get("moved", 0) if isinstance(result, dict) else 0
    skipped = result.get("skipped", 0) if isinstance(result, dict) else 0
    eff_dx = result.get("dx", 0) if isinstance(result, dict) else 0
    eff_dy = result.get("dy", 0) if isinstance(result, dict) else 0
    if not ok or moved <= 0:
        print(f"ENTITY_PROPS noop reason=no_changes ok={ok}")
        return
    marker = getattr(w, "mark_scene_dirty", None)
    if callable(marker):
        marker("entity_nudge_selection")
    _set_last_props_action(w, action="nudge_selection", changed=int(moved))
    print(f"ENTITY_PROPS ok action=nudge_selection moved={moved} skipped={skipped} dx={eff_dx} dy={eff_dy}")


def action_rotate_selection(w: Any, arg: str | None) -> None:
    """Rotate selected entities.

    Argument format:
    - simple: ``cw`` (90°), ``ccw`` (-90°), ``180``
    - key/value: ``deg=90|about=group``
    """
    selected_ids, primary = _get_selection_ids_and_primary(w)
    if not selected_ids:
        print("ENTITY_PROPS noop reason=no_selection")
        return
    parsed = _parse_rotate_args(arg)
    if not bool(parsed.get("ok", False)):
        reason = str(parsed.get("reason", "") or "")
        if reason == "empty_rotate_arg":
            print("ENTITY_PROPS noop reason=empty_rotate_arg")
            return
        if reason == "invalid_deg":
            print(f"ENTITY_PROPS noop reason=invalid_deg value={parsed.get('value', '')}")
            return
        print(f"ENTITY_PROPS noop reason=unknown_rotate_token token={parsed.get('token', '')}")
        return
    deg = float(parsed.get("deg", 0.0) or 0.0)
    about = str(parsed.get("about", "self") or "self")

    authored = _get_authored_payload(w)
    if authored is None:
        print("ENTITY_PROPS noop reason=no_authored_payload")
        return
    pusher = getattr(w, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_rotate_selection")
    sc = getattr(w, "scene_controller", None)
    rotator = getattr(sc, "debug_rotate_selection", None) if sc is not None else None
    if not callable(rotator):
        print("ENTITY_PROPS noop reason=no_scene_controller")
        return
    result = rotator(selected_ids, deg, about=about, primary_id=primary)
    ok = result.get("ok", False) if isinstance(result, dict) else False
    rotated = result.get("rotated", 0) if isinstance(result, dict) else 0
    moved_pos = result.get("moved", 0) if isinstance(result, dict) else 0
    skipped = result.get("skipped", 0) if isinstance(result, dict) else 0
    if not ok or (rotated <= 0 and moved_pos <= 0):
        print(f"ENTITY_PROPS noop reason=no_changes ok={ok}")
        return
    marker = getattr(w, "mark_scene_dirty", None)
    if callable(marker):
        marker("entity_rotate_selection")
    _set_last_props_action(w, action="rotate_selection", changed=int(rotated))
    print(f"ENTITY_PROPS ok action=rotate_selection rotated={rotated} moved={moved_pos} skipped={skipped} deg={deg} about={about}")


def action_mirror_selection(w: Any, arg: str | None) -> None:
    """Mirror / flip selected entities across an axis.

    Argument format:
    - simple: ``x``, ``y``, ``x primary``, ``y no-rot``
    - key/value: ``axis=x|about=group|rot=1``
    """
    selected_ids, primary = _get_selection_ids_and_primary(w)
    if not selected_ids:
        print("ENTITY_PROPS noop reason=no_selection")
        return
    raw = str(arg or "").strip()
    if not raw:
        print("ENTITY_PROPS noop reason=empty_mirror_arg")
        return

    axis = ""
    about = "group"
    include_rotation = True

    if "|" in raw:
        # key/value form: axis=x|about=group|rot=1
        for part in raw.split("|"):
            part = part.strip()
            low = part.lower()
            if low.startswith("axis="):
                axis = part[len("axis="):].strip().lower()
            elif low.startswith("about="):
                about = part[len("about="):].strip().lower()
            elif low.startswith("rot="):
                val = part[len("rot="):].strip().lower()
                include_rotation = val not in ("0", "false", "no")
    else:
        # Simple token form: "x", "y", "x primary", "y no-rot"
        tokens = raw.lower().split()
        if tokens:
            axis = tokens[0]
        for tok in tokens[1:]:
            if tok in ("primary", "group"):
                about = tok
            elif tok in ("no-rot", "norot"):
                include_rotation = False

    if axis not in ("x", "y"):
        print(f"ENTITY_PROPS noop reason=invalid_mirror_axis axis={axis}")
        return

    authored = _get_authored_payload(w)
    if authored is None:
        print("ENTITY_PROPS noop reason=no_authored_payload")
        return
    pusher = getattr(w, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_mirror_selection")
    sc = getattr(w, "scene_controller", None)
    mirror_fn = getattr(sc, "debug_mirror_selection", None) if sc is not None else None
    if not callable(mirror_fn):
        print("ENTITY_PROPS noop reason=no_scene_controller")
        return
    result = mirror_fn(selected_ids, axis, about=about, primary_id=primary, include_rotation=include_rotation)
    ok = result.get("ok", False) if isinstance(result, dict) else False
    moved = result.get("moved", 0) if isinstance(result, dict) else 0
    rotated = result.get("rotated", 0) if isinstance(result, dict) else 0
    skipped = result.get("skipped", 0) if isinstance(result, dict) else 0
    if not ok or (moved <= 0 and rotated <= 0):
        print(f"ENTITY_PROPS noop reason=no_changes ok={ok}")
        return
    marker = getattr(w, "mark_scene_dirty", None)
    if callable(marker):
        marker("entity_mirror_selection")
    _set_last_props_action(w, action="mirror_selection", changed=int(moved))
    print(f"ENTITY_PROPS ok action=mirror_selection moved={moved} rotated={rotated} skipped={skipped} axis={axis} about={about}")


def action_group_selection(w: Any, arg: str | None) -> None:
    """Group selected entities into a logical container.

    Argument format:
    - simple: ``Group`` (name base)
    - key/value: ``base=Group|about=primary``
    """
    selected_ids, primary = _get_selection_ids_and_primary(w)
    if not selected_ids:
        print("ENTITY_PROPS noop reason=no_selection")
        return
    raw = str(arg or "").strip()

    name_base = "Group"
    about = "group"

    if "|" in raw:
        for part in raw.split("|"):
            part = part.strip()
            low = part.lower()
            if low.startswith("base="):
                name_base = part[len("base="):].strip() or "Group"
            elif low.startswith("about="):
                about = part[len("about="):].strip().lower()
    elif raw:
        tokens = raw.split()
        name_base = tokens[0] if tokens else "Group"
        for tok in tokens[1:]:
            if tok.lower() in ("primary", "group"):
                about = tok.lower()

    authored = _get_authored_payload(w)
    if authored is None:
        print("ENTITY_PROPS noop reason=no_authored_payload")
        return
    pusher = getattr(w, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_group_selection")
    sc = getattr(w, "scene_controller", None)
    group_fn = getattr(sc, "debug_group_selection", None) if sc is not None else None
    if not callable(group_fn):
        print("ENTITY_PROPS noop reason=no_scene_controller")
        return
    result = group_fn(selected_ids, name_base=name_base, about=about, primary_id=primary)
    ok = result.get("ok", False) if isinstance(result, dict) else False
    linked = result.get("linked", 0) if isinstance(result, dict) else 0
    skipped = result.get("skipped", 0) if isinstance(result, dict) else 0
    group_id = result.get("group_id", "") if isinstance(result, dict) else ""
    group_name = result.get("group_name", "") if isinstance(result, dict) else ""
    if not ok or linked <= 0:
        print(f"ENTITY_PROPS noop reason=no_changes ok={ok}")
        return
    marker = getattr(w, "mark_scene_dirty", None)
    if callable(marker):
        marker("entity_group_selection")
    _set_last_props_action(w, action="group_selection", changed=int(linked))
    print(f"ENTITY_PROPS ok action=group_selection group_id={group_id} group_name={group_name} linked={linked} skipped={skipped} about={about}")


def action_ungroup_selection(w: Any, arg: str | None) -> None:
    """Dissolve a logical group, removing membership links."""
    selected_ids, _primary = _get_selection_ids_and_primary(w)
    if not selected_ids:
        print("ENTITY_PROPS noop reason=no_selection")
        return
    raw = str(arg or "").strip()
    mode = raw if raw else "auto"

    authored = _get_authored_payload(w)
    if authored is None:
        print("ENTITY_PROPS noop reason=no_authored_payload")
        return
    pusher = getattr(w, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_ungroup_selection")
    sc = getattr(w, "scene_controller", None)
    ungroup_fn = getattr(sc, "debug_ungroup_selection", None) if sc is not None else None
    if not callable(ungroup_fn):
        print("ENTITY_PROPS noop reason=no_scene_controller")
        return
    result = ungroup_fn(selected_ids, mode=mode)
    ok = result.get("ok", False) if isinstance(result, dict) else False
    unlinked = result.get("unlinked", 0) if isinstance(result, dict) else 0
    deleted_group = result.get("deleted_group", False) if isinstance(result, dict) else False
    skipped = result.get("skipped", 0) if isinstance(result, dict) else 0
    group_id = result.get("group_id", "") if isinstance(result, dict) else ""
    if not ok:
        print(f"ENTITY_PROPS noop reason=no_changes ok={ok}")
        return
    marker = getattr(w, "mark_scene_dirty", None)
    if callable(marker):
        marker("entity_ungroup_selection")
    _set_last_props_action(w, action="ungroup_selection", changed=int(unlinked))
    print(f"ENTITY_PROPS ok action=ungroup_selection group_id={group_id} unlinked={unlinked} deleted_group={deleted_group} skipped={skipped}")


def action_duplicate_to_grid(w: Any, arg: str | None) -> None:
    """Duplicate selected entities into an NxM grid.

    Argument format (key/value):
        ``rows=3|cols=4|dx=32|dy=32|include=1|name=numbered``
    Shorthand:
        ``3x4 dx=32 dy=32``
    """
    selected_ids, _primary = _get_selection_ids_and_primary(w)
    if not selected_ids:
        print("ENTITY_PROPS noop reason=no_selection")
        return
    raw = str(arg or "").strip()
    if not raw:
        print("ENTITY_PROPS noop reason=empty_grid_arg")
        return

    rows = 1
    cols = 1
    dx = 0.0
    dy = 0.0
    origin = "selection"
    include_original = True
    name_mode = "none"

    if "|" in raw:
        for part in raw.split("|"):
            part = part.strip()
            low = part.lower()
            if low.startswith("rows="):
                try:
                    rows = int(part[len("rows="):])
                except (ValueError, TypeError):
                    pass
            elif low.startswith("cols="):
                try:
                    cols = int(part[len("cols="):])
                except (ValueError, TypeError):
                    pass
            elif low.startswith("dx="):
                try:
                    dx = float(part[len("dx="):])
                except (ValueError, TypeError):
                    pass
            elif low.startswith("dy="):
                try:
                    dy = float(part[len("dy="):])
                except (ValueError, TypeError):
                    pass
            elif low.startswith("origin="):
                origin = part[len("origin="):].strip().lower() or "selection"
            elif low.startswith("include="):
                val = part[len("include="):].strip().lower()
                include_original = val not in ("0", "false", "no")
            elif low.startswith("name="):
                name_mode = part[len("name="):].strip().lower() or "none"
    else:
        import re as _re  # noqa: PLC0415
        tokens = raw.split()
        for tok in tokens:
            low = tok.lower()
            m = _re.match(r"^(\d+)x(\d+)$", low)
            if m:
                rows = int(m.group(1))
                cols = int(m.group(2))
            elif low.startswith("dx="):
                try:
                    dx = float(tok[3:])
                except (ValueError, TypeError):
                    pass
            elif low.startswith("dy="):
                try:
                    dy = float(tok[3:])
                except (ValueError, TypeError):
                    pass
            elif low.startswith("origin="):
                origin = tok[7:].strip().lower() or "selection"
            elif low.startswith("include="):
                val = tok[8:].strip().lower()
                include_original = val not in ("0", "false", "no")
            elif low.startswith("name="):
                name_mode = tok[5:].strip().lower() or "none"
            elif low.startswith("rows="):
                try:
                    rows = int(tok[5:])
                except (ValueError, TypeError):
                    pass
            elif low.startswith("cols="):
                try:
                    cols = int(tok[5:])
                except (ValueError, TypeError):
                    pass

    authored = _get_authored_payload(w)
    if authored is None:
        print("ENTITY_PROPS noop reason=no_authored_payload")
        return
    pusher = getattr(w, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_duplicate_to_grid")
    sc = getattr(w, "scene_controller", None)
    dup_fn = getattr(sc, "debug_duplicate_to_grid", None) if sc is not None else None
    if not callable(dup_fn):
        print("ENTITY_PROPS noop reason=no_scene_controller")
        return
    result = dup_fn(
        selected_ids, rows=rows, cols=cols, dx=dx, dy=dy,
        origin=origin, include_original=include_original,
        name_mode=name_mode,
    )
    ok = result.get("ok", False) if isinstance(result, dict) else False
    created = result.get("created", 0) if isinstance(result, dict) else 0
    skipped = result.get("skipped", 0) if isinstance(result, dict) else 0
    if not ok:
        print(f"ENTITY_PROPS noop reason=invalid_grid_params ok={ok}")
        return
    if created <= 0:
        print(f"ENTITY_PROPS noop reason=no_changes ok={ok} created=0")
        return
    marker = getattr(w, "mark_scene_dirty", None)
    if callable(marker):
        marker("entity_duplicate_to_grid")
    _set_last_props_action(w, action="duplicate_to_grid", changed=int(created))
    print(f"ENTITY_PROPS ok action=duplicate_to_grid created={created} skipped={skipped} rows={rows} cols={cols} dx={dx} dy={dy}")


def action_duplicate_along_path(w: Any, arg: str | None) -> None:
    """Duplicate selected entities along a line segment.

    Argument format (key/value):
        ``from=0,0|to=128,0|count=5|include=1|name=numbered|orient=1``
    Shorthand:
        ``0,0 128,0 5``  (from_x,from_y  to_x,to_y  count)
    """
    selected_ids, _primary = _get_selection_ids_and_primary(w)
    if not selected_ids:
        print("ENTITY_PROPS noop reason=no_selection")
        return
    raw = str(arg or "").strip()
    if not raw:
        print("ENTITY_PROPS noop reason=empty_path_arg")
        return

    from_x = 0.0
    from_y = 0.0
    to_x = 0.0
    to_y = 0.0
    count = 2
    include_original = True
    name_mode = "none"
    orient = False

    if "|" in raw:
        for part in raw.split("|"):
            part = part.strip()
            low = part.lower()
            if low.startswith("from="):
                coords = part[len("from="):].split(",")
                if len(coords) >= 2:
                    try:
                        from_x = float(coords[0])
                        from_y = float(coords[1])
                    except (ValueError, TypeError):
                        pass
            elif low.startswith("to="):
                coords = part[len("to="):].split(",")
                if len(coords) >= 2:
                    try:
                        to_x = float(coords[0])
                        to_y = float(coords[1])
                    except (ValueError, TypeError):
                        pass
            elif low.startswith("count="):
                try:
                    count = int(part[len("count="):])
                except (ValueError, TypeError):
                    pass
            elif low.startswith("include="):
                val = part[len("include="):].strip().lower()
                include_original = val not in ("0", "false", "no")
            elif low.startswith("name="):
                name_mode = part[len("name="):].strip().lower() or "none"
            elif low.startswith("orient="):
                val = part[len("orient="):].strip().lower()
                orient = val in ("1", "true", "yes")
    else:
        import re as _re  # noqa: PLC0415
        tokens = raw.split()
        positional: list[str] = []
        for tok in tokens:
            low = tok.lower()
            if low.startswith("from="):
                coords = tok[len("from="):].split(",")
                if len(coords) >= 2:
                    try:
                        from_x = float(coords[0])
                        from_y = float(coords[1])
                    except (ValueError, TypeError):
                        pass
            elif low.startswith("to="):
                coords = tok[len("to="):].split(",")
                if len(coords) >= 2:
                    try:
                        to_x = float(coords[0])
                        to_y = float(coords[1])
                    except (ValueError, TypeError):
                        pass
            elif low.startswith("count="):
                try:
                    count = int(tok[len("count="):])
                except (ValueError, TypeError):
                    pass
            elif low.startswith("include="):
                val = tok[len("include="):].strip().lower()
                include_original = val not in ("0", "false", "no")
            elif low.startswith("name="):
                name_mode = tok[len("name="):].strip().lower() or "none"
            elif low.startswith("orient="):
                val = tok[len("orient="):].strip().lower()
                orient = val in ("1", "true", "yes")
            else:
                positional.append(tok)
        # Shorthand: "0,0 128,0 5"
        if len(positional) >= 2:
            coord_re = _re.compile(r'^(-?[\d.]+),(-?[\d.]+)$')
            m_from = coord_re.match(positional[0])
            m_to = coord_re.match(positional[1])
            if m_from:
                try:
                    from_x = float(m_from.group(1))
                    from_y = float(m_from.group(2))
                except (ValueError, TypeError):
                    pass
            if m_to:
                try:
                    to_x = float(m_to.group(1))
                    to_y = float(m_to.group(2))
                except (ValueError, TypeError):
                    pass
        if len(positional) >= 3:
            try:
                count = int(positional[2])
            except (ValueError, TypeError):
                pass

    authored = _get_authored_payload(w)
    if authored is None:
        print("ENTITY_PROPS noop reason=no_authored_payload")
        return
    pusher = getattr(w, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_duplicate_along_path")
    sc = getattr(w, "scene_controller", None)
    dup_fn = getattr(sc, "debug_duplicate_along_path", None) if sc is not None else None
    if not callable(dup_fn):
        print("ENTITY_PROPS noop reason=no_scene_controller")
        return
    result = dup_fn(
        selected_ids, from_x=from_x, from_y=from_y,
        to_x=to_x, to_y=to_y, count=count,
        include_original=include_original, name_mode=name_mode,
        orient=orient,
    )
    ok = result.get("ok", False) if isinstance(result, dict) else False
    created = result.get("created", 0) if isinstance(result, dict) else 0
    skipped = result.get("skipped", 0) if isinstance(result, dict) else 0
    if not ok:
        print(f"ENTITY_PROPS noop reason=invalid_path_params ok={ok}")
        return
    if created <= 0:
        print(f"ENTITY_PROPS noop reason=no_changes ok={ok} created=0")
        return
    marker = getattr(w, "mark_scene_dirty", None)
    if callable(marker):
        marker("entity_duplicate_along_path")
    _set_last_props_action(w, action="duplicate_along_path", changed=int(created))
    print(f"ENTITY_PROPS ok action=duplicate_along_path created={created} skipped={skipped} count={count} from={from_x},{from_y} to={to_x},{to_y}")


def action_scatter_selection(w: Any, arg: str | None) -> None:
    """Scatter-duplicate selected entities inside a shape.

    Key/value format:
        ``n=10|shape=circle|radius=128|center=group|seed=123|rot=15|snap=16|include=1|name=numbered``
    Shorthand:
        ``10 seed=123 radius=128``  (positional n, then key=value tokens)
    """
    selected_ids, _primary = _get_selection_ids_and_primary(w)
    if not selected_ids:
        print("ENTITY_PROPS noop reason=no_selection")
        return
    raw = str(arg or "").strip()
    if not raw:
        print("ENTITY_PROPS noop reason=empty_scatter_arg")
        return

    n = 1
    shape = "circle"
    radius = 64.0
    width = 128.0
    height = 128.0
    center = "group"
    seed = 0
    jitter_rot_deg = 0.0
    snap_step: int | None = None
    include_original = True
    name_mode = "none"

    def _parse_kv(key: str, val: str) -> None:
        nonlocal n, shape, radius, width, height, center, seed
        nonlocal jitter_rot_deg, snap_step, include_original, name_mode
        key = key.lower()
        if key == "n":
            try:
                n = int(val)
            except (ValueError, TypeError):
                pass
        elif key == "shape":
            shape = val.strip().lower() or "circle"
        elif key == "radius":
            try:
                radius = float(val)
            except (ValueError, TypeError):
                pass
        elif key == "width":
            try:
                width = float(val)
            except (ValueError, TypeError):
                pass
        elif key == "height":
            try:
                height = float(val)
            except (ValueError, TypeError):
                pass
        elif key == "center":
            center = val.strip().lower() or "group"
        elif key == "seed":
            try:
                seed = int(val)
            except (ValueError, TypeError):
                pass
        elif key == "rot":
            try:
                jitter_rot_deg = float(val)
            except (ValueError, TypeError):
                pass
        elif key == "snap":
            try:
                snap_step = int(val)
            except (ValueError, TypeError):
                pass
        elif key == "include":
            include_original = val.strip().lower() not in ("0", "false", "no")
        elif key == "name":
            name_mode = val.strip().lower() or "none"

    if "|" in raw:
        for part in raw.split("|"):
            part = part.strip()
            if "=" in part:
                k, _, v = part.partition("=")
                _parse_kv(k.strip(), v.strip())
    else:
        tokens = raw.split()
        positional_consumed = False
        for tok in tokens:
            if "=" in tok:
                k, _, v = tok.partition("=")
                _parse_kv(k.strip(), v.strip())
            elif not positional_consumed:
                try:
                    n = int(tok)
                    positional_consumed = True
                except (ValueError, TypeError):
                    pass

    authored = _get_authored_payload(w)
    if authored is None:
        print("ENTITY_PROPS noop reason=no_authored_payload")
        return
    pusher = getattr(w, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_scatter_selection")
    sc = getattr(w, "scene_controller", None)
    scatter_fn = getattr(sc, "debug_scatter_selection", None) if sc is not None else None
    if not callable(scatter_fn):
        print("ENTITY_PROPS noop reason=no_scene_controller")
        return
    result = scatter_fn(
        selected_ids, n=n, shape=shape,
        radius=radius, width=width, height=height,
        center=center, seed=seed,
        jitter_rot_deg=jitter_rot_deg, snap_step=snap_step,
        include_original=include_original,
        name_mode=name_mode,
    )
    ok = result.get("ok", False) if isinstance(result, dict) else False
    created = result.get("created", 0) if isinstance(result, dict) else 0
    skipped = result.get("skipped", 0) if isinstance(result, dict) else 0
    if not ok:
        print(f"ENTITY_PROPS noop reason=invalid_scatter_params ok={ok}")
        return
    if created <= 0:
        print(f"ENTITY_PROPS noop reason=no_changes ok={ok} created=0")
        return
    marker = getattr(w, "mark_scene_dirty", None)
    if callable(marker):
        marker("entity_scatter_selection")
    _set_last_props_action(w, action="scatter_selection", changed=int(created))
    print(f"ENTITY_PROPS ok action=scatter_selection created={created} skipped={skipped} n={n} shape={shape} seed={seed}")
