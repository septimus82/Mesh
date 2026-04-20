from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from engine.swallowed_exceptions import _log_swallow


@dataclass
class EntitySelectState:
    selected_ids: list[str] = field(default_factory=list)
    primary_id: str | None = None

    dragging: bool = False
    drag_mode: str = ""  # "move" | "marquee" | ""
    drag_dirty_marked: bool = False
    drag_undo_pushed: bool = False

    drag_anchor_world: tuple[float, float] | None = None
    drag_click_offset: tuple[float, float] | None = None
    drag_start_positions: dict[str, tuple[float, float]] | None = None
    drag_rect_world: tuple[float, float, float, float] | None = None
    drag_rect_moved: bool = False

    selected_prefab_id: str = ""

    def __post_init__(self) -> None:
        self.selected_ids = list(self.selected_ids or [])


def _get_tilemap_dims(window: Any) -> tuple[int, int, int, int] | None:
    sc = getattr(window, "scene_controller", None)
    instance = getattr(sc, "tilemap_instance", None) if sc is not None else None
    if instance is not None:
        mw, mh = getattr(instance, "map_size", (None, None))
        tw, th = getattr(instance, "tile_size", (None, None))
        if isinstance(mw, int) and mw > 0 and isinstance(mh, int) and mh > 0 and isinstance(tw, int) and tw > 0 and isinstance(th, int) and th > 0:
            return mw, mh, tw, th

    getter = getattr(sc, "get_authored_scene_payload", None) if sc is not None else None
    payload = getter() if callable(getter) else None
    tilemap = payload.get("tilemap") if isinstance(payload, dict) and isinstance(payload.get("tilemap"), dict) else None
    mw = tilemap.get("width") if isinstance(tilemap, dict) else None
    mh = tilemap.get("height") if isinstance(tilemap, dict) else None
    tw = tilemap.get("tilewidth") if isinstance(tilemap, dict) else None
    th = tilemap.get("tileheight") if isinstance(tilemap, dict) else None
    if isinstance(mw, int) and mw > 0 and isinstance(mh, int) and mh > 0 and isinstance(tw, int) and tw > 0 and isinstance(th, int) and th > 0:
        return mw, mh, tw, th
    return None


def snap_world_to_tile_center(window: Any, *, world_x: float, world_y: float) -> tuple[float, float] | None:
    dims = _get_tilemap_dims(window)
    if dims is None:
        return None
    map_w, map_h, tile_w, tile_h = dims
    col = int(float(world_x) // float(tile_w))
    row_from_bottom = int(float(world_y) // float(tile_h))
    if col < 0 or row_from_bottom < 0 or col >= map_w or row_from_bottom >= map_h:
        return None
    snapped_x = (float(col) + 0.5) * float(tile_w)
    snapped_y = (float(row_from_bottom) + 0.5) * float(tile_h)
    return snapped_x, snapped_y


def other_authoring_modes_active(window: Any) -> bool:
    if bool(getattr(getattr(window, "tile_paint_state", None), "enabled", False)):
        return True

    try:
        from engine.palette_mode import get_state  # noqa: PLC0415

        if bool(get_state().enabled):
            return True
    except Exception:  # noqa: BLE001  # REASON: optional palette-mode state checks should not block entity selection mode activation
        _log_swallow("ENTI-001", "engine/entity_select_mode.py pass-only blanket swallow")
        pass

    capture_state = getattr(window, "capture_state", None)
    if bool(getattr(capture_state, "enabled", False)):
        return True

    if bool(getattr(getattr(window, "entity_paint_state", None), "enabled", False)):
        return True

    return False


def selection_sorted_unique(ids: list[str]) -> list[str]:
    out = sorted({str(i).strip() for i in ids if isinstance(i, str) and str(i).strip()})
    return out


def set_selection(window: Any, state: EntitySelectState, ids: list[str], *, primary_id: str | None = None) -> None:
    ids = selection_sorted_unique(list(ids or []))
    state.selected_ids = ids
    if primary_id is not None and isinstance(primary_id, str) and primary_id.strip() and primary_id in ids:
        state.primary_id = primary_id
    else:
        state.primary_id = ids[0] if ids else None
    setattr(window, "authoring_selected_entity_id", state.primary_id)
    editor = getattr(window, "editor_controller", None)
    session = getattr(editor, "session", None) if editor is not None else None
    setter = getattr(session, "set_authoring_selected_active", None) if session is not None else None
    if callable(setter):
        setter(bool(state.primary_id))


def toggle_selected(window: Any, state: EntitySelectState, entity_id: str, *, make_primary: bool = True) -> None:
    entity_id = str(entity_id or "").strip()
    if not entity_id:
        return
    ids = list(state.selected_ids or [])
    if entity_id in ids:
        ids = [i for i in ids if i != entity_id]
        set_selection(window, state, ids)
        return
    ids.append(entity_id)
    set_selection(window, state, ids, primary_id=(entity_id if make_primary else None))


def add_selected(window: Any, state: EntitySelectState, entity_id: str, *, make_primary: bool = True) -> None:
    entity_id = str(entity_id or "").strip()
    if not entity_id:
        return
    ids = list(state.selected_ids or [])
    if entity_id not in ids:
        ids.append(entity_id)
    set_selection(window, state, ids, primary_id=(entity_id if make_primary else None))


def clear_drag(state: EntitySelectState) -> None:
    state.dragging = False
    state.drag_dirty_marked = False
    state.drag_undo_pushed = False
    state.drag_mode = ""
    state.drag_anchor_world = None
    state.drag_click_offset = None
    state.drag_start_positions = None
    state.drag_rect_world = None
    state.drag_rect_moved = False


def update_drag_rect(state: EntitySelectState, *, world_x: float, world_y: float) -> None:
    if not state.drag_anchor_world:
        return
    x0, y0 = state.drag_anchor_world
    state.drag_rect_world = (float(x0), float(y0), float(world_x), float(world_y))
    if abs(float(world_x) - float(x0)) > 0.01 or abs(float(world_y) - float(y0)) > 0.01:
        state.drag_rect_moved = True


def iter_entity_ids_in_world_rect(window: Any, rect_world: tuple[float, float, float, float]) -> list[str]:
    sc = getattr(window, "scene_controller", None)
    sprites = getattr(sc, "all_sprites", None) if sc is not None else None
    if not isinstance(sprites, list):
        sprites = list(sprites) if sprites is not None else []

    x0, y0, x1, y1 = rect_world
    left = min(float(x0), float(x1))
    right = max(float(x0), float(x1))
    bottom = min(float(y0), float(y1))
    top = max(float(y0), float(y1))

    ids: list[str] = []
    for sprite in sprites:
        cx = getattr(sprite, "center_x", None)
        cy = getattr(sprite, "center_y", None)
        if not isinstance(cx, (int, float)) or not isinstance(cy, (int, float)):
            continue
        if float(cx) < left or float(cx) > right or float(cy) < bottom or float(cy) > top:
            continue
        entity_data = getattr(sprite, "mesh_entity_data", None)
        entity_id = entity_data.get("id") if isinstance(entity_data, dict) else None
        if isinstance(entity_id, str) and entity_id.strip():
            ids.append(entity_id.strip())
    return selection_sorted_unique(ids)


def get_duplicate_offset(window: Any) -> tuple[float, float]:
    """
    Return (dx, dy) for duplicating entities.

    - Default is (16,16).
    - If snap-to-tile is enabled and tile dims are available, use (tile_w, tile_h).
    """
    default = (16.0, 16.0)
    if not bool(getattr(window, "entity_snap_to_tile", False)):
        return default
    dims = _get_tilemap_dims(window)
    if dims is None:
        return default
    _, _, tile_w, tile_h = dims
    return float(tile_w), float(tile_h)
