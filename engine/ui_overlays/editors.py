from __future__ import annotations

from typing import TYPE_CHECKING, Any
import engine.optional_arcade as optional_arcade

from .common import (
    UIElement,
    _draw_lrtb_rectangle_outline,
    _draw_rectangle_filled,
)

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow


def format_tile_paint_overlay_lines(payload: dict[str, Any] | None) -> list[str]:
    if not isinstance(payload, dict):
        payload = {}

    if not bool(payload.get("enabled", False)):
        return []

    layer_id = str(payload.get("layer_id") or "-")
    tile_id = payload.get("tile_id")
    tile_text = str(int(tile_id)) if isinstance(tile_id, int) else "-"
    tool = str(payload.get("tool") or "-")

    hover_value = payload.get("hover")
    hover = hover_value if isinstance(hover_value, dict) else {}
    tx = hover.get("tx")
    ty = hover.get("ty")
    wx = hover.get("world_x")
    wy = hover.get("world_y")

    hover_tile = f"({int(tx)},{int(ty)})" if isinstance(tx, int) and isinstance(ty, int) else "(-,-)"
    hover_world = (
        f"({float(wx):.1f},{float(wy):.1f})" if isinstance(wx, (int, float)) and isinstance(wy, (int, float)) else "(-,-)"
    )

    return [
        "TILE PAINT: ON",
        f"layer={layer_id} tile={tile_text}",
        f"tool={tool} hover={hover_tile} world={hover_world}",
    ] + _format_quick_slots_and_recent_lines(
        slots=payload.get("slots"),
        recent=payload.get("recent"),
        recent_limit=6,
    )


def _format_quick_slots_and_recent_lines(*, slots: Any, recent: Any, recent_limit: int) -> list[str]:
    lines: list[str] = []

    if isinstance(slots, dict):
        parts: list[str] = []
        slot_keys = sorted([int(k) for k in slots.keys() if isinstance(k, int) and 1 <= int(k) <= 9])
        for k in slot_keys:
            v = slots.get(k)
            if isinstance(v, int):
                parts.append(f"{k}={int(v)}")
            elif isinstance(v, str) and v.strip():
                parts.append(f"{k}={v.strip()}")
        if parts:
            lines.append("slots: " + " ".join(parts))

    if isinstance(recent, list):
        items: list[str] = []
        for v in recent:
            if isinstance(v, int):
                items.append(str(int(v)))
            elif isinstance(v, str) and v.strip():
                items.append(v.strip())
            if len(items) >= int(recent_limit):
                break
        if items:
            lines.append("recent: " + ",".join(items))

    return lines


class TilePaintOverlay(UIElement):
    def __init__(self, window: "GameWindow", *, provider: Any | None = None) -> None:
        super().__init__(window)
        self.provider = provider

    def get_lines(self) -> list[str]:
        payload = None
        if callable(self.provider):
            try:
                payload = self.provider(self.window)
            except Exception:  # noqa: BLE001
                payload = None
        return format_tile_paint_overlay_lines(payload if isinstance(payload, dict) else None)

    def draw(self) -> None:
        lines = self.get_lines()
        if not lines:
            return

        width = 320.0
        height = max(70.0, 30.0 + 16.0 * float(len(lines)))
        left = 20.0
        bottom = 90.0
        right = left + width
        top = bottom + height

        _draw_rectangle_filled(
            center_x=(left + right) / 2.0,
            center_y=(top + bottom) / 2.0,
            width=width,
            height=height,
            color=(0, 0, 0, 170),
        )
        _draw_lrtb_rectangle_outline(left, right, top, bottom, optional_arcade.arcade.color.SKY_BLUE, 2)

        optional_arcade.arcade.draw_text(
            "\n".join(lines),
            left + 12.0,
            top - 12.0,
            optional_arcade.arcade.color.WHITE,
            12,
            anchor_y="top",
            font_name=("Consolas", "Courier New", "Courier"),
        )


def format_entity_paint_overlay_lines(payload: dict[str, Any] | None) -> list[str]:
    if not isinstance(payload, dict):
        payload = {}
    if not bool(payload.get("enabled", False)):
        return []

    prefab_id = payload.get("prefab_id")
    prefab_text = str(prefab_id) if isinstance(prefab_id, str) and prefab_id.strip() else "-"
    idx = payload.get("prefab_index")
    total = payload.get("prefab_count")
    if isinstance(idx, int) and isinstance(total, int) and total > 0:
        index_text = f"{idx}/{total}"
    else:
        index_text = "-/-"

    filter_mode = payload.get("filter_mode")
    filter_text = str(filter_mode) if isinstance(filter_mode, str) and filter_mode.strip() else "all"

    hover_value = payload.get("hover")
    hover = hover_value if isinstance(hover_value, dict) else {}
    wx = hover.get("world_x")
    wy = hover.get("world_y")
    world_text = (
        f"({float(wx):.1f},{float(wy):.1f})" if isinstance(wx, (int, float)) and isinstance(wy, (int, float)) else "(-,-)"
    )
    tx = hover.get("tx")
    ty = hover.get("ty")
    tile_text = f"({int(tx)},{int(ty)})" if isinstance(tx, int) and isinstance(ty, int) else "-"

    hover_entity_value = payload.get("hover_entity")
    hover_entity = hover_entity_value if isinstance(hover_entity_value, dict) else {}
    hid = hover_entity.get("id")
    hpid = hover_entity.get("prefab_id")
    hname = hover_entity.get("name")
    if any(v not in (None, "") for v in (hid, hpid, hname)):
        id_text = str(hid) if isinstance(hid, str) and hid.strip() else "-"
        prefab_id_text = str(hpid) if isinstance(hpid, str) and hpid.strip() else "-"
        name_text = str(hname) if isinstance(hname, str) and hname.strip() else "-"
        hover_entity_text = f"{id_text}/{prefab_id_text}/{name_text}"
    else:
        hover_entity_text = "none"

    persist_armed = bool(payload.get("persist_armed", False))
    persist_text = "ARMED" if persist_armed else "OFF"

    lines = [
        "ENTITY PAINT: ON",
        f"prefab={prefab_text} (index {index_text}) [filter={filter_text}]",
        f"hover_world={world_text} hover_tile={tile_text}",
        f"hover_entity={hover_entity_text}",
        f"persist={persist_text}",
    ]
    lines.extend(
        _format_quick_slots_and_recent_lines(
            slots=payload.get("slots"),
            recent=payload.get("recent"),
            recent_limit=6,
        )
    )
    return lines


class EntityPaintOverlay(UIElement):
    def __init__(self, window: "GameWindow", *, provider: Any | None = None) -> None:
        super().__init__(window)
        self.provider = provider

    def get_lines(self) -> list[str]:
        payload = None
        if callable(self.provider):
            try:
                payload = self.provider(self.window)
            except Exception:  # noqa: BLE001
                payload = None
        return format_entity_paint_overlay_lines(payload if isinstance(payload, dict) else None)

    def draw(self) -> None:
        lines = self.get_lines()
        if not lines:
            return

        width = 560.0
        height = max(110.0, 30.0 + 16.0 * float(len(lines)))
        left = 20.0
        bottom = 90.0
        right = left + width
        top = bottom + height

        _draw_rectangle_filled(
            center_x=(left + right) / 2.0,
            center_y=(top + bottom) / 2.0,
            width=width,
            height=height,
            color=(0, 0, 0, 170),
        )
        _draw_lrtb_rectangle_outline(left, right, top, bottom, optional_arcade.arcade.color.SKY_BLUE, 2)

        optional_arcade.arcade.draw_text(
            "\n".join(lines),
            left + 12.0,
            top - 12.0,
            optional_arcade.arcade.color.WHITE,
            12,
            anchor_y="top",
            font_name=("Consolas", "Courier New", "Courier"),
        )


def format_entity_select_overlay_lines(payload: dict[str, Any] | None) -> list[str]:
    if not isinstance(payload, dict):
        payload = {}
    if not bool(payload.get("enabled", False)):
        return []

    ids = payload.get("selected_ids")
    if not isinstance(ids, list):
        ids = []
    selected_ids = sorted({str(i).strip() for i in ids if isinstance(i, str) and str(i).strip()})
    dup_count = payload.get("dup_count")
    dup_primary = payload.get("dup_primary")
    show_dup = isinstance(dup_count, int) and dup_count > 0 and isinstance(dup_primary, str) and dup_primary.strip()

    clipboard_count = payload.get("clipboard_count")
    clipboard_primary = payload.get("clipboard_primary")
    show_clipboard = (
        isinstance(clipboard_count, int)
        and clipboard_count > 0
        and isinstance(clipboard_primary, str)
        and clipboard_primary.strip()
    )

    transform_action = payload.get("transform_action")
    transform_count = payload.get("transform_count")
    show_transform = (
        isinstance(transform_action, str)
        and transform_action.strip()
        and isinstance(transform_count, int)
        and transform_count > 0
    )

    props_action = payload.get("props_action")
    props_changed = payload.get("props_changed")
    show_props = (
        isinstance(props_action, str)
        and props_action.strip()
        and isinstance(props_changed, int)
        and props_changed > 0
    )

    config_action = payload.get("config_action")
    config_changed = payload.get("config_changed")
    show_config = (
        isinstance(config_action, str)
        and config_action.strip()
        and isinstance(config_changed, int)
        and config_changed > 0
    )

    dup_count_i = dup_count if isinstance(dup_count, int) else 0
    transform_count_i = transform_count if isinstance(transform_count, int) else 0
    props_changed_i = props_changed if isinstance(props_changed, int) else 0
    config_changed_i = config_changed if isinstance(config_changed, int) else 0
    clipboard_count_i = clipboard_count if isinstance(clipboard_count, int) else 0

    if not selected_ids:
        lines = ["SELECT none"]
        if show_dup:
            lines.append(f"dup={dup_count_i} primary={dup_primary}")
        if show_transform:
            lines.append(f"action={transform_action} count={transform_count_i}")
        if show_props:
            lines.append(f"props={props_action} changed={props_changed_i}")
        if show_config:
            lines.append(f"config={config_action} changed={config_changed_i}")
        if show_clipboard:
            lines.append(f"clipboard={clipboard_count_i} (primary={clipboard_primary})")
        return lines

    primary_id = payload.get("primary_id")
    primary_id = str(primary_id).strip() if isinstance(primary_id, str) and str(primary_id).strip() else selected_ids[0]

    if len(selected_ids) == 1:
        primary_value = payload.get("primary")
        primary = primary_value if isinstance(primary_value, dict) else {}
        entity_id = str(primary.get("id") or primary_id)
        prefab_id = primary.get("prefab_id")
        prefab_text = str(prefab_id) if isinstance(prefab_id, str) and prefab_id.strip() else "-"
        pos_value = primary.get("pos")
        pos = pos_value if isinstance(pos_value, dict) else {}
        x = pos.get("x")
        y = pos.get("y")
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            pos_text = f"({float(x):.1f},{float(y):.1f})"
        else:
            pos_text = "(-,-)"
        lines = [f"SELECT 1 id={entity_id} prefab={prefab_text} pos={pos_text}"]
        if show_dup:
            lines.append(f"dup={dup_count_i} primary={dup_primary}")
        if show_transform:
            lines.append(f"action={transform_action} count={transform_count_i}")
        if show_props:
            lines.append(f"props={props_action} changed={props_changed_i}")
        if show_config:
            lines.append(f"config={config_action} changed={config_changed_i}")
        if show_clipboard:
            lines.append(f"clipboard={clipboard_count_i} (primary={clipboard_primary})")
        return lines

    prefix = ",".join(selected_ids[:5])
    lines = [f"SELECT {len(selected_ids)} primary={primary_id} (first 5: {prefix})"]
    if show_dup:
        lines.append(f"dup={dup_count_i} primary={dup_primary}")
    if show_transform:
        lines.append(f"action={transform_action} count={transform_count_i}")
    if show_props:
        lines.append(f"props={props_action} changed={props_changed_i}")
    if show_config:
        lines.append(f"config={config_action} changed={config_changed_i}")
    if show_clipboard:
        lines.append(f"clipboard={clipboard_count_i} (primary={clipboard_primary})")
    return lines


class EntitySelectOverlay(UIElement):
    def __init__(self, window: "GameWindow", *, provider: Any | None = None) -> None:
        super().__init__(window)
        self.provider = provider

    def get_lines(self) -> list[str]:
        payload = None
        if callable(self.provider):
            try:
                payload = self.provider(self.window)
            except Exception:  # noqa: BLE001
                payload = None
        return format_entity_select_overlay_lines(payload if isinstance(payload, dict) else None)

    def draw(self) -> None:
        lines = self.get_lines()
        if not lines:
            return
        left = 20.0
        top = float(getattr(self.window, "height", 720) or 720) - 40.0
        optional_arcade.arcade.draw_text(
            "\n".join(lines),
            left,
            top,
            optional_arcade.arcade.color.WHITE,
            12,
            anchor_y="top",
            font_name=("Consolas", "Courier New", "Courier"),
        )


def format_capture_overlay_lines(payload: dict[str, Any] | None) -> list[str]:
    if not isinstance(payload, dict):
        payload = {}
    if not bool(payload.get("enabled", False)):
        return []

    mode = str(payload.get("mode") or "STAMP").upper()
    rect_value = payload.get("rect")
    rect = rect_value if isinstance(rect_value, dict) else {}
    x0 = rect.get("x0")
    y0 = rect.get("y0")
    x1 = rect.get("x1")
    y1 = rect.get("y1")
    if isinstance(x0, int) and isinstance(y0, int) and isinstance(x1, int) and isinstance(y1, int):
        w_value = rect.get("w")
        h_value = rect.get("h")
        w = int(w_value) if isinstance(w_value, int) else int(abs(int(x1) - int(x0)) + 1)
        h = int(h_value) if isinstance(h_value, int) else int(abs(int(y1) - int(y0)) + 1)
        rect_text = f"({int(x0)},{int(y0)})-({int(x1)},{int(y1)}) w={int(w)} h={int(h)}"
    else:
        rect_text = "(-,-)-(-,-) w=- h=-"

    layers_count = payload.get("layers")
    layers_text = str(int(layers_count)) if isinstance(layers_count, int) else "-"
    include_entities = bool(payload.get("include_entities", False))
    include_text = "Y" if include_entities else "N"

    persist_armed = bool(payload.get("persist_armed", False))
    persist_text = "ON" if persist_armed else "off"
    persist_status = str(payload.get("persist_status") or "").strip()

    hover_value = payload.get("hover")
    hover = hover_value if isinstance(hover_value, dict) else {}
    tx = hover.get("tx")
    ty = hover.get("ty")
    tile_id = hover.get("tile_id")
    layer_id = hover.get("layer_id")
    if isinstance(tx, int) and isinstance(ty, int):
        hover_tile = f"({tx},{ty})"
    else:
        hover_tile = "(-,-)"
    tile_text = str(int(tile_id)) if isinstance(tile_id, int) else "-"
    layer_text = str(layer_id) if isinstance(layer_id, str) and layer_id else "-"

    lines = [
        f"CAPTURE: ON {mode}",
        f"rect={rect_text}",
        f"layers={layers_text} include_entities={include_text}",
        f"Persist={persist_text}" + (f" {persist_status}" if persist_status else ""),
        f"hover={hover_tile} tile={tile_text} layer={layer_text}",
        "hint: Drag=select Tab=type Shift=entities Enter=copy Esc=close",
    ]
    return lines


class CaptureOverlay(UIElement):
    def __init__(self, window: "GameWindow", *, provider: Any | None = None) -> None:
        super().__init__(window)
        self.provider = provider

    def get_lines(self) -> list[str]:
        payload = None
        if callable(self.provider):
            try:
                payload = self.provider(self.window)
            except Exception:  # noqa: BLE001
                payload = None
        return format_capture_overlay_lines(payload if isinstance(payload, dict) else None)

    def draw(self) -> None:
        lines = self.get_lines()
        if not lines:
            return

        width = 560.0
        height = 110.0
        left = 20.0
        bottom = 170.0
        right = left + width
        top = bottom + height

        _draw_rectangle_filled(
            center_x=(left + right) / 2.0,
            center_y=(top + bottom) / 2.0,
            width=width,
            height=height,
            color=(0, 0, 0, 170),
        )
        _draw_lrtb_rectangle_outline(left, right, top, bottom, optional_arcade.arcade.color.SKY_BLUE, 2)

        optional_arcade.arcade.draw_text(
            "\n".join(lines),
            left + 12.0,
            top - 12.0,
            optional_arcade.arcade.color.WHITE,
            12,
            anchor_y="top",
            font_name=("Consolas", "Courier New", "Courier"),
        )
