# ruff: noqa
# mypy: ignore-errors
from __future__ import annotations

import copy
import math
import random
from typing import TYPE_CHECKING, Any, Dict

import engine.optional_arcade as optional_arcade

from ...index_build import build_scene_index_from_sprites
from ._shared import (
    _build_entity_index,
    _build_used_id_set,
    _debug_iter_authoring_payloads,
    _is_group_entity,
    _next_group_id,
    _next_group_name,
    _next_unique_dup_id,
    _snap_value,
    _sorted_dedup_ids,
    debug_apply_authored_scene_payload,
    get_authored_scene_payload,
)

if TYPE_CHECKING:
    from ....scene_controller import SceneController
_GROUP_VALID_ABOUT = frozenset({"group", "primary"})


_DUPLICATE_GRID_VALID_ORIGINS = frozenset({"selection", "group"})


_DUPLICATE_GRID_VALID_NAME_MODES = frozenset({"none", "numbered"})


_DUP_PATH_VALID_NAME_MODES = frozenset({"none", "numbered"})


_SCATTER_VALID_NAME_MODES = frozenset({"none", "numbered"})


_SCATTER_VALID_SHAPES = frozenset({"circle", "rect"})


_SCATTER_VALID_CENTERS = frozenset({"group", "primary", "origin"})


def debug_duplicate_entities_by_ids(controller: "SceneController", ids: list[str], *, dx: float, dy: float) -> dict[str, str]:
    """
    Debug-only: duplicate selected authored entities deterministically.

    - Operates on the authored payload copy so persist does not bake runtime-only mutations.
    - Attempts to spawn sprites for the duplicates best-effort (no hard failure if sprite creation fails).
    - Returns mapping of orig_id -> new_id for the successfully duplicated entities.
    """
    from ....entity_paint_mode import ensure_entities_list  # noqa: PLC0415

    if not isinstance(ids, list) or not ids:
        return {}

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return {}

    authored_entities = ensure_entities_list(authored)
    by_id: dict[str, Dict[str, Any]] = {}
    for entity in authored_entities:
        if not isinstance(entity, dict):
            continue
        entity_id = entity.get("id")
        if isinstance(entity_id, str) and entity_id.strip():
            by_id[entity_id.strip()] = entity

    used_ids: set[str] = set()
    for payload in _debug_iter_authoring_payloads(controller):
        for entity in ensure_entities_list(payload):
            if not isinstance(entity, dict):
                continue
            eid = entity.get("id")
            if isinstance(eid, str) and eid.strip():
                used_ids.add(eid.strip())

    mapping: dict[str, str] = {}
    created_any = False

    for orig_id in sorted({str(i).strip() for i in ids if isinstance(i, str) and str(i).strip()}):
        orig = by_id.get(orig_id)
        if orig is None:
            continue

        k = 1
        while True:
            candidate = f"{orig_id}__dup{k}"
            if candidate not in used_ids:
                new_id = candidate
                break
            k += 1
        used_ids.add(new_id)

        clone: Dict[str, Any] = dict(orig)
        clone["id"] = new_id
        try:
            clone["x"] = float(clone.get("x", 0.0)) + float(dx)
        except Exception:  # noqa: BLE001
            clone["x"] = float(dx)
        try:
            clone["y"] = float(clone.get("y", 0.0)) + float(dy)
        except Exception:  # noqa: BLE001
            clone["y"] = float(dy)

        authored_entities.append(clone)
        mapping[orig_id] = new_id
        created_any = True

        sprite = None
        try:
            sprite = controller._create_sprite(dict(clone))
        except Exception:  # noqa: BLE001
            sprite = None
        if sprite is not None:
            layer_name = str(clone.get("layer") or "entities")
            if layer_name not in controller.layers:
                controller.layers[layer_name] = optional_arcade.arcade.SpriteList()
            controller.layers[layer_name].append(sprite)

    if created_any:
        controller._scene_index = build_scene_index_from_sprites(controller.all_sprites)
    return mapping


def debug_group_selection(
    controller: "SceneController",
    entity_ids: list[str],
    name_base: str = "Group",
    about: str = "group",
    primary_id: str = "",
) -> dict:
    """Debug-only: create a logical group container for selected entities.

    A new **group entity** is inserted into the scene with ``is_group=True``
    and ``tags=["group"]``.  Each participating member gets a ``group_id``
    field pointing at the new group entity's id.

    *about* controls the group entity's position:
        ``"group"``  ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ centroid of participating entity positions.
        ``"primary"`` ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ primary entity's position (fail if missing).

    Returns ``{ok, group_id, group_name, members, linked, skipped}``.
    """
    from ....entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

    ab = str(about or "group").strip().lower()
    base = str(name_base or "Group").strip() or "Group"

    fail: dict = {
        "ok": False, "group_id": "", "group_name": "",
        "members": [], "linked": 0, "skipped": 0,
    }

    if ab not in _GROUP_VALID_ABOUT:
        return fail

    sorted_ids = _sorted_dedup_ids(entity_ids)
    if not sorted_ids:
        return fail

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return fail
    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)
    index = _build_entity_index(entities)

    # Collect participants (have position, not player, not already grouped).
    participants: list[tuple[str, dict]] = []
    skipped = 0
    for eid in sorted_ids:
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
        if _is_group_entity(ent):
            skipped += 1
            continue
        existing_gid = ent.get("group_id")
        if isinstance(existing_gid, str) and existing_gid.strip():
            # Already belongs to a group ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â refuse nested grouping.
            return fail
        participants.append((eid, ent))

    if len(participants) < 2:
        return fail

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
        xs = [float(ent["x"]) for _eid, ent in participants]
        ys = [float(ent["y"]) for _eid, ent in participants]
        pivot = (sum(xs) / len(xs), sum(ys) / len(ys))

    # Build used-id set for collision avoidance.
    used_ids = _build_used_id_set(entities)

    group_id = _next_group_id(used_ids)
    group_name = _next_group_name(entities, base)

    # Create group entity.
    group_entity: Dict[str, Any] = {
        "id": group_id,
        "name": group_name,
        "x": pivot[0],
        "y": pivot[1],
        "tags": ["group"],
        "is_group": True,
    }
    entities.append(group_entity)

    # Link members.
    linked = 0
    member_ids: list[str] = []
    for eid, ent in participants:
        ent["group_id"] = group_id
        linked += 1
        member_ids.append(eid)

    debug_apply_authored_scene_payload(controller, authored_copy)
    return {
        "ok": True,
        "group_id": group_id,
        "group_name": group_name,
        "members": member_ids,
        "linked": linked,
        "skipped": skipped,
    }


def debug_ungroup_selection(
    controller: "SceneController",
    entity_ids: list[str],
    mode: str = "auto",
) -> dict:
    """Debug-only: dissolve a logical group, removing membership links.

    Target-group resolution:
    1. If any selected entity **is** a group entity, use that group.
    2. Otherwise pick the lexicographically lowest ``group_id`` among
       selected members.

    All entities whose ``group_id`` matches the target are unlinked, and the
    group entity itself is deleted from the scene.

    Returns ``{ok, group_id, unlinked, deleted_group, skipped}``.
    """
    from ....entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

    fail: dict = {
        "ok": False, "group_id": "", "unlinked": 0,
        "deleted_group": False, "skipped": 0,
    }

    sorted_ids = _sorted_dedup_ids(entity_ids)
    if not sorted_ids:
        return fail

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return fail
    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)
    index = _build_entity_index(entities)

    # --- Determine target group_id ---
    target_group_id = ""
    skipped = 0

    # Pass 1: check if any selected entity *is* a group entity.
    for eid in sorted_ids:
        ent = index.get(eid)
        if not isinstance(ent, dict):
            skipped += 1
            continue
        if is_player_entity(ent):
            skipped += 1
            continue
        if _is_group_entity(ent):
            target_group_id = str(ent.get("id", "")).strip()
            break

    # Pass 2: fallback to lowest group_id among selected members.
    if not target_group_id:
        candidate_gids: list[str] = []
        for eid in sorted_ids:
            ent = index.get(eid)
            if not isinstance(ent, dict):
                continue
            gid = ent.get("group_id")
            if isinstance(gid, str) and gid.strip():
                candidate_gids.append(gid.strip())
        if candidate_gids:
            target_group_id = sorted(set(candidate_gids))[0]

    if not target_group_id:
        return fail

    # --- Unlink all members with this group_id ---
    unlinked = 0
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        gid = ent.get("group_id")
        if isinstance(gid, str) and gid.strip() == target_group_id:
            del ent["group_id"]
            unlinked += 1

    # --- Delete the group entity ---
    deleted_group = False
    before_len = len(entities)
    entities[:] = [
        e for e in entities
        if not (isinstance(e, dict) and str(e.get("id", "")).strip() == target_group_id)
    ]
    if len(entities) < before_len:
        deleted_group = True

    if unlinked > 0 or deleted_group:
        debug_apply_authored_scene_payload(controller, authored_copy)

    return {
        "ok": unlinked > 0 or deleted_group,
        "group_id": target_group_id,
        "unlinked": unlinked,
        "deleted_group": deleted_group,
        "skipped": skipped,
    }


def debug_duplicate_to_grid(
    controller: "SceneController",
    entity_ids: list[str],
    rows: int = 1,
    cols: int = 1,
    dx: float = 0.0,
    dy: float = 0.0,
    origin: str = "selection",
    include_original: bool = True,
    name_mode: str = "none",
) -> dict:
    """Debug-only: duplicate selected entities into an NxM grid.

    For each grid cell ``(r, c)`` in row-major order the offset is
    ``(c * dx, r * dy)``.  If *include_original* is True the ``(0, 0)``
    cell is skipped (the originals already occupy that position).

    *origin* controls base positions:
        ``"selection"`` ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â each entity's own position.
        ``"group"``     ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â group centroid (preserves relative offsets).

    *name_mode*:
        ``"none"``      ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â duplicates keep the cloned name.
        ``"numbered"``  ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â duplicates get ``_r{row}_c{col}`` suffix.

    Returns ``{ok, created, skipped, rows, cols, dx, dy,
    include_original, name_mode}``.
    """
    from ....entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

    ori = str(origin or "selection").strip().lower()
    nm = str(name_mode or "none").strip().lower()

    fail: dict = {
        "ok": False, "created": 0, "skipped": 0,
        "rows": int(rows), "cols": int(cols),
        "dx": float(dx), "dy": float(dy),
        "include_original": bool(include_original),
        "name_mode": nm,
    }

    try:
        r_count = int(rows)
        c_count = int(cols)
    except (TypeError, ValueError):
        return fail
    if r_count < 1 or c_count < 1:
        return fail
    if ori not in _DUPLICATE_GRID_VALID_ORIGINS:
        return fail
    if nm not in _DUPLICATE_GRID_VALID_NAME_MODES:
        return fail

    sorted_ids = _sorted_dedup_ids(entity_ids)
    if not sorted_ids:
        return fail

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return fail
    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)
    index = _build_entity_index(entities)

    # Collect participants (have position, not player).
    participants: list[tuple[str, dict]] = []
    skipped = 0
    for eid in sorted_ids:
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
        return {
            "ok": True, "created": 0, "skipped": skipped,
            "rows": r_count, "cols": c_count,
            "dx": float(dx), "dy": float(dy),
            "include_original": bool(include_original),
            "name_mode": nm,
        }

    # If rows==1 cols==1 and include_original -> nothing to create.
    if r_count == 1 and c_count == 1 and include_original:
        return {
            "ok": True, "created": 0, "skipped": skipped,
            "rows": r_count, "cols": c_count,
            "dx": float(dx), "dy": float(dy),
            "include_original": bool(include_original),
            "name_mode": nm,
        }

    # Build used-id set.
    used_ids = _build_used_id_set(entities)

    created = 0

    # Row-major iteration.
    for r in range(r_count):
        for c in range(c_count):
            if include_original and r == 0 and c == 0:
                continue

            cell_dx = float(c) * float(dx)
            cell_dy = float(r) * float(dy)

            for orig_id, orig_ent in participants:
                candidate = _next_unique_dup_id(orig_id, used_ids)

                clone: Dict[str, Any] = copy.deepcopy(orig_ent)
                clone["id"] = candidate

                try:
                    clone["x"] = float(orig_ent["x"]) + cell_dx
                except (TypeError, ValueError):
                    clone["x"] = cell_dx
                try:
                    clone["y"] = float(orig_ent["y"]) + cell_dy
                except (TypeError, ValueError):
                    clone["y"] = cell_dy

                if nm == "numbered":
                    orig_name = orig_ent.get("name")
                    if isinstance(orig_name, str) and orig_name.strip():
                        clone["name"] = f"{orig_name.strip()}_r{r}_c{c}"

                entities.append(clone)
                created += 1

    if created > 0:
        debug_apply_authored_scene_payload(controller, authored_copy)

    return {
        "ok": True,
        "created": created,
        "skipped": skipped,
        "rows": r_count,
        "cols": c_count,
        "dx": float(dx),
        "dy": float(dy),
        "include_original": bool(include_original),
        "name_mode": nm,
    }


def debug_duplicate_along_path(
    controller: "SceneController",
    entity_ids: list[str],
    from_x: float,
    from_y: float,
    to_x: float,
    to_y: float,
    count: int,
    include_original: bool = True,
    origin: str = "selection",
    name_mode: str = "none",
    orient: bool = False,
) -> dict:
    """Debug-only: duplicate selected entities along a line segment.

    Computes *count* points along ``(from_x, from_y)`` ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ ``(to_x, to_y)``
    using linear interpolation.  For each point, each selected entity is
    duplicated at ``base_position + (point_i - from)``.

    If *include_original* the ``i=0`` point is skipped (originals stay).

    *name_mode* ``"numbered"`` appends ``_p{idx:03d}`` to duplicate names.

    *orient* if True sets duplicate ``rotation`` to the segment angle
    (degrees, clockwise-positive from +X).

    Returns ``{ok, created, skipped, count, from, to,
    include_original, name_mode, orient}``.
    """
    import math  # noqa: PLC0415

    from ....entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

    nm = str(name_mode or "none").strip().lower()

    fail: dict = {
        "ok": False, "created": 0, "skipped": 0,
        "count": 0, "from": [float(from_x), float(from_y)],
        "to": [float(to_x), float(to_y)],
        "include_original": bool(include_original),
        "name_mode": nm, "orient": bool(orient),
    }

    try:
        n = int(count)
    except (TypeError, ValueError):
        return fail
    if n < 1:
        return fail
    if nm not in _DUP_PATH_VALID_NAME_MODES:
        return fail

    fx, fy = float(from_x), float(from_y)
    tx, ty = float(to_x), float(to_y)

    sorted_ids = _sorted_dedup_ids(entity_ids)
    if not sorted_ids:
        return fail

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return fail
    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)
    index = _build_entity_index(entities)

    # Collect participants.
    participants: list[tuple[str, dict]] = []
    skipped = 0
    for eid in sorted_ids:
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
        return {
            "ok": True, "created": 0, "skipped": skipped,
            "count": n, "from": [fx, fy], "to": [tx, ty],
            "include_original": bool(include_original),
            "name_mode": nm, "orient": bool(orient),
        }

    # Compute segment angle for orient.
    seg_angle = 0.0
    if orient:
        seg_angle = math.degrees(math.atan2(ty - fy, tx - fx)) % 360.0

    # Build used-id set.
    used_ids = _build_used_id_set(entities)

    created = 0

    for i in range(n):
        if include_original and i == 0:
            continue

        if n == 1:
            t = 0.0
        else:
            t = float(i) / float(n - 1)

        pt_x = fx + t * (tx - fx)
        pt_y = fy + t * (ty - fy)
        offset_x = pt_x - fx
        offset_y = pt_y - fy

        for orig_id, orig_ent in participants:
            candidate = _next_unique_dup_id(orig_id, used_ids)

            clone: Dict[str, Any] = copy.deepcopy(orig_ent)
            clone["id"] = candidate

            try:
                clone["x"] = float(orig_ent["x"]) + offset_x
            except (TypeError, ValueError):
                clone["x"] = offset_x
            try:
                clone["y"] = float(orig_ent["y"]) + offset_y
            except (TypeError, ValueError):
                clone["y"] = offset_y

            if orient:
                clone["rotation"] = seg_angle

            if nm == "numbered":
                orig_name = orig_ent.get("name")
                if isinstance(orig_name, str) and orig_name.strip():
                    clone["name"] = f"{orig_name.strip()}_p{i:03d}"

            entities.append(clone)
            created += 1

    if created > 0:
        debug_apply_authored_scene_payload(controller, authored_copy)

    return {
        "ok": True,
        "created": created,
        "skipped": skipped,
        "count": n,
        "from": [fx, fy],
        "to": [tx, ty],
        "include_original": bool(include_original),
        "name_mode": nm,
        "orient": bool(orient),
    }


def debug_scatter_selection(
    controller: "SceneController",
    entity_ids: list[str],
    n: int,
    shape: str = "circle",
    radius: float = 64.0,
    width: float = 128.0,
    height: float = 128.0,
    center: str = "group",
    seed: int = 0,
    jitter_rot_deg: float = 0.0,
    snap_step: int | None = None,
    include_original: bool = True,
    name_mode: str = "none",
) -> dict:
    """Debug-only: scatter-duplicate selected entities inside a shape.

    Generates *n* scatter points using a deterministic RNG seeded with *seed*.
    Each selected entity is duplicated at each point, preserving the
    selection's internal shape (relative offsets to centroid).

    Returns ``{ok, created, skipped, n, shape, seed, include_original}``.
    """
    import math   # noqa: PLC0415
    import random  # noqa: PLC0415

    from ....entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

    nm = str(name_mode or "none").strip().lower()
    sh = str(shape or "circle").strip().lower()
    ctr = str(center or "group").strip().lower()

    fail: dict = {
        "ok": False, "created": 0, "skipped": 0,
        "n": 0, "shape": sh, "seed": int(seed),
        "include_original": bool(include_original),
    }

    # Validate n.
    try:
        n_val = int(n)
    except (TypeError, ValueError):
        return fail
    if n_val < 1:
        return fail

    # Validate enums.
    if nm not in _SCATTER_VALID_NAME_MODES:
        return fail
    if sh not in _SCATTER_VALID_SHAPES:
        return fail
    if ctr not in _SCATTER_VALID_CENTERS:
        return fail

    # Validate shape dimensions.
    try:
        f_radius = float(radius)
        f_width = float(width)
        f_height = float(height)
    except (TypeError, ValueError):
        return fail
    if sh == "circle" and f_radius <= 0:
        return fail
    if sh == "rect" and (f_width <= 0 or f_height <= 0):
        return fail

    # Collect sorted, deduplicated ids.
    sorted_ids = _sorted_dedup_ids(entity_ids)
    if not sorted_ids:
        return fail

    authored = get_authored_scene_payload(controller)
    if not isinstance(authored, dict):
        return fail
    authored_copy = copy.deepcopy(authored)
    entities = ensure_entities_list(authored_copy)
    index = _build_entity_index(entities)

    # Collect participants.
    participants: list[tuple[str, dict]] = []
    skipped = 0
    for eid in sorted_ids:
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
        return {
            "ok": True, "created": 0, "skipped": skipped,
            "n": n_val, "shape": sh, "seed": int(seed),
            "include_original": bool(include_original),
        }

    # Compute pivot.
    if ctr == "origin":
        pivot_x, pivot_y = 0.0, 0.0
    elif ctr == "primary":
        # Need primary id ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â use first from sorted_ids that is a participant.
        # Caller should ensure primary is in the list; we use the first participant.
        # Actually, use entity_ids[0] if present, or fail.
        primary_id: str | None = None
        for eid in (entity_ids or []):
            if isinstance(eid, str) and eid.strip():
                primary_id = eid.strip()
                break
        if primary_id is None:
            return fail
        pent = index.get(primary_id)
        if not isinstance(pent, dict) or "x" not in pent or "y" not in pent:
            return fail
        try:
            pivot_x = float(pent["x"])
            pivot_y = float(pent["y"])
        except (TypeError, ValueError):
            return fail
    else:
        # group centroid
        sum_x = 0.0
        sum_y = 0.0
        for _eid, ent in participants:
            try:
                sum_x += float(ent["x"])
                sum_y += float(ent["y"])
            except (TypeError, ValueError):
                pass
        pivot_x = sum_x / len(participants)
        pivot_y = sum_y / len(participants)

    # Build used-id set.
    used_ids = _build_used_id_set(entities)

    # Deterministic RNG.
    rng = random.Random(seed)

    # Pre-generate all scatter offsets so ordering is deterministic.
    offsets: list[tuple[float, float]] = []
    for _i in range(n_val):
        if sh == "circle":
            a = rng.uniform(0.0, 2.0 * math.pi)
            u = rng.uniform(0.0, 1.0)
            r = f_radius * math.sqrt(u)
            offsets.append((r * math.cos(a), r * math.sin(a)))
        else:
            ox = rng.uniform(-f_width / 2.0, f_width / 2.0)
            oy = rng.uniform(-f_height / 2.0, f_height / 2.0)
            offsets.append((ox, oy))

    # Pre-generate rotation jitter.
    rot_jitters: list[float] = []
    for _i in range(n_val):
        if jitter_rot_deg > 0:
            rot_jitters.append(rng.uniform(-jitter_rot_deg, jitter_rot_deg))
        else:
            rot_jitters.append(0.0)

    created = 0

    for i in range(n_val):
        if include_original and i == 0:
            continue

        scatter_x = pivot_x + offsets[i][0]
        scatter_y = pivot_y + offsets[i][1]

        for orig_id, orig_ent in participants:
            # Relative offset from centroid.
            try:
                rel_x = float(orig_ent["x"]) - pivot_x
                rel_y = float(orig_ent["y"]) - pivot_y
            except (TypeError, ValueError):
                rel_x, rel_y = 0.0, 0.0

            target_x = scatter_x + rel_x
            target_y = scatter_y + rel_y

            # Snap.
            if snap_step is not None:
                try:
                    ss = int(snap_step)
                    if ss > 0:
                        target_x = _snap_value(target_x, ss, "nearest")
                        target_y = _snap_value(target_y, ss, "nearest")
                except (TypeError, ValueError):
                    pass

            # Unique ID.
            candidate = _next_unique_dup_id(orig_id, used_ids)

            clone: Dict[str, Any] = copy.deepcopy(orig_ent)
            clone["id"] = candidate
            clone["x"] = target_x
            clone["y"] = target_y

            # Rotation jitter.
            jitter_val = rot_jitters[i]
            if jitter_rot_deg > 0:
                try:
                    cur_rot = float(orig_ent.get("rotation", 0.0))
                except (TypeError, ValueError):
                    cur_rot = 0.0
                clone["rotation"] = (cur_rot + jitter_val) % 360.0

            # Naming.
            if nm == "numbered":
                orig_name = orig_ent.get("name")
                if isinstance(orig_name, str) and orig_name.strip():
                    clone["name"] = f"{orig_name.strip()}_s{i:03d}"

            entities.append(clone)
            created += 1

    if created > 0:
        debug_apply_authored_scene_payload(controller, authored_copy)

    return {
        "ok": True,
        "created": created,
        "skipped": skipped,
        "n": n_val,
        "shape": sh,
        "seed": int(seed),
        "include_original": bool(include_original),
    }
