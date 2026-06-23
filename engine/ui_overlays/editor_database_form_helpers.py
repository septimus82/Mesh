from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from engine.ui_overlays.theme import EDITOR_THEME
from engine.ui_overlays.widgets import Rect, TextInput


@dataclass(frozen=True)
class FormColors:
    text: tuple[int, int, int, int]
    dim: tuple[int, int, int, int]
    button: tuple[int, int, int, int]


def compute_database_form_layout(window: Any, controller: Any, panel_gap: float) -> tuple[Rect, Rect]:
    from engine.editor.editor_dock_query import get_effective_dock_widths  # noqa: PLC0415
    from engine.editor.editor_shell_layout import compute_editor_shell_layout  # noqa: PLC0415

    window_w = int(getattr(window, "width", 1280) or 1280)
    window_h = int(getattr(window, "height", 720) or 720)
    left_w, right_w = get_effective_dock_widths(controller, window_w)
    layout = compute_editor_shell_layout(window_w, window_h, left_w, right_w)

    dock = layout.right_dock
    content_top = dock.top - 38.0
    content_bottom = dock.bottom + 10.0
    content_left = dock.left + 8.0
    content_right = dock.right - 8.0
    content_width = max(0.0, content_right - content_left)
    split_x = content_left + max(112.0, content_width * 0.44)
    list_rect = Rect(
        x=float(content_left), y=float(content_bottom),
        width=max(0.0, float(split_x - content_left - (panel_gap * 0.5))), height=max(0.0, float(content_top - content_bottom)),
    )
    detail_rect = Rect(
        x=float(split_x + (panel_gap * 0.5)), y=float(content_bottom),
        width=max(0.0, float(content_right - split_x - (panel_gap * 0.5))), height=max(0.0, float(content_top - content_bottom)),
    )
    return list_rect, detail_rect


def add_form_buttons(
    panel: Any,
    *,
    edit_mode: bool,
    button_color: tuple[int, int, int, int],
    row_height: float,
    padding_x: float,
) -> dict[str, Any]:
    from engine.editor.widgets.panel_primitives import PanelField, PanelRow  # noqa: PLC0415

    actions = ("save", "cancel") if edit_mode else ("edit",)
    button_rows: dict[str, Any] = {}
    for action in actions:
        button_rows[action] = panel.add_row(
            PanelRow(
                PanelField(action.title(), None, label_color=button_color),
                height=row_height,
                padding_x=padding_x,
            )
        )
    return button_rows


def collect_button_rects(button_rows: dict[str, Any]) -> dict[str, Rect]:
    return {
        action: rect
        for action, row in button_rows.items()
        if _is_rect_like(rect := getattr(row, "last_rect", None))
    }


def scalar_rows_for_mode(
    *,
    model: Any,
    edit_mode: bool,
    scalar_field_order: tuple[str, ...],
    selected_record: Callable[[], Any],
    value_for_field: Callable[[Any, str], Any],
    label_for_field: Callable[[str], str],
) -> list[tuple[str, str, str]]:
    """Yield scalar rows, expanding all editable fields in edit mode."""
    if not edit_mode:
        rows = model.scalar_detail_rows() if hasattr(model, "scalar_detail_rows") else []
        return list(rows)
    record = selected_record()
    if record is None:
        return []
    rows: list[tuple[str, str, str]] = []
    for field_path in scalar_field_order:
        value = value_for_field(record, field_path)
        rows.append((label_for_field(field_path), "" if value is None else str(value), field_path))
    return rows


def draw_text_input(
    text_input: TextInput,
    rect: Rect,
    colors: FormColors,
) -> None:
    from engine.editor.widgets import panel_primitives  # noqa: PLC0415

    layout = text_input.layout(rect)
    for instruction in layout.instructions:
        payload = instruction.payload
        instr_rect = payload.get("rect")
        if instruction.kind == "text_input_bg" and _is_rect_like(instr_rect):
            bg = EDITOR_THEME.input_bg_focused if payload.get("focused") else EDITOR_THEME.input_bg
            border = EDITOR_THEME.input_border_focused if payload.get("focused") else EDITOR_THEME.input_border
            panel_primitives.draw_panel_bg(instr_rect.left, instr_rect.right, instr_rect.bottom, instr_rect.top, color=bg)
            panel_primitives._draw_tb_rectangle_outline(
                instr_rect.left, instr_rect.right, instr_rect.top, instr_rect.bottom, border, 1
            )
        elif instruction.kind == "text_input_text":
            color = colors.dim if payload.get("is_placeholder") else colors.text
            panel_primitives.draw_text_cached(
                str(payload.get("text", "")),
                float(payload.get("x", 0.0)),
                float(payload.get("y", 0.0)),
                color=color,
                font_size=int(payload.get("font_size", 12)),
                anchor_x="left",
                anchor_y="center",
            )
        elif instruction.kind == "text_input_caret":
            text = str(payload.get("text", ""))
            panel_primitives.draw_text_cached(
                "|",
                float(payload.get("x", 0.0)) + (len(text) * 7.0),
                float(payload.get("y", 0.0)),
                color=colors.text,
                font_size=int(payload.get("font_size", 12)),
                anchor_x="left",
                anchor_y="center",
            )


def sync_text_inputs(
    text_inputs: dict[str, TextInput],
    focused_field: str | None,
    value_for_field: Callable[[str], Any],
) -> None:
    for field, text_input in text_inputs.items():
        value = value_for_field(field)
        text_input.text = "" if value is None else str(value)
        text_input.focused = field == focused_field


def draw_text_input_rows(
    widget_rows: dict[str, Any],
    text_inputs: dict[str, TextInput],
    draw_text_input_fn: Callable[[TextInput, Rect], None],
    *,
    skip_fields: tuple[str, ...] = (),
) -> None:
    skipped = set(skip_fields)
    for field, row in widget_rows.items():
        if field in skipped:
            continue
        row_rect = getattr(row, "last_rect", None)
        if not _is_rect_like(row_rect):
            continue
        field_rect = _field_rect(row_rect)
        widget = text_inputs.get(field)
        if isinstance(widget, TextInput):
            draw_text_input_fn(widget, field_rect)


def try_click_text_widget(
    widget_rows: dict[str, Any],
    controller: Any,
    x: float,
    y: float,
    *,
    skip_fields: tuple[str, ...] = (),
) -> str | None:
    skipped = set(skip_fields)
    for field, row in widget_rows.items():
        if field in skipped:
            continue
        row_rect = getattr(row, "last_rect", None)
        if not _is_rect_like(row_rect):
            continue
        field_rect = _field_rect(row_rect)
        if not field_rect.contains(float(x), float(y)):
            continue
        text_input = getattr(controller, "text_input", lambda _field: None)(field)
        if isinstance(text_input, TextInput):
            text_input.on_mouse_press(float(x), float(y))
            return field
    return None


def _field_rect(row_rect: Any) -> Rect:
    return Rect(
        x=float(row_rect.left + 92.0), y=float(row_rect.bottom + 1.0),
        width=max(0.0, float(row_rect.width - 98.0)), height=max(0.0, float(row_rect.height - 2.0)),
    )


def _is_rect_like(value: object) -> bool:
    return all(hasattr(value, attr) for attr in ("left", "right", "bottom", "top", "width", "height"))
