"""Read-only Item Editor overlay for the editor right dock."""

from __future__ import annotations

from typing import TYPE_CHECKING

from engine.ui_overlays.common import UIElement
from engine.ui_overlays.widgets import Rect, TextInput

if TYPE_CHECKING:  # pragma: no cover
    from engine.game import GameWindow


ITEM_EDITOR_TEXT_COLOR = (220, 220, 230, 255)
ITEM_EDITOR_DIM_COLOR = (150, 150, 160, 255)
ITEM_EDITOR_SELECTED_BG = (90, 140, 200, 140)
ITEM_EDITOR_ERROR_COLOR = (255, 120, 120, 255)
ITEM_EDITOR_BUTTON_COLOR = (100, 200, 255, 255)
ITEM_EDITOR_ROW_HEIGHT = 18.0
ITEM_EDITOR_ROW_PADDING_X = 6.0
ITEM_EDITOR_PANEL_GAP = 8.0


class ItemEditorOverlay(UIElement):
    """Read-only item database view hosted in the editor right dock."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._model: object | None = None
        self._load_error: str | None = None

    def _get_controller(self) -> object | None:
        return getattr(self.window, "editor_controller", None)

    def _is_visible_for_controller(self, controller: object | None) -> bool:
        if controller is None or not getattr(controller, "active", False):
            return False
        dock = getattr(controller, "dock", None)
        snapshot = dock.get_snapshot() if dock is not None and hasattr(dock, "get_snapshot") else dock
        right_tab = getattr(snapshot, "right_tab", "Inspector") or "Inspector"
        return right_tab == "Items"

    def _get_model(self) -> object | None:
        if self._model is not None:
            return self._model
        try:
            from engine.editor.item_editor_model import ItemEditorModel

            self._model = ItemEditorModel.load()
            self._load_error = None
        except Exception as exc:  # pragma: no cover - defensive runtime path
            self._model = None
            self._load_error = str(exc)
        return self._model

    def reload_model(self) -> None:
        self._model = None
        self._get_model()

    def selected_item_dict(self) -> dict[str, object] | None:
        model = self._get_model()
        item = getattr(model, "selected_item", None) if model is not None else None
        if item is None:
            return None
        from engine.editor.editor_item_editor_controller import item_definition_to_dict

        return item_definition_to_dict(item)

    def all_item_dicts(self) -> list[dict[str, object]]:
        model = self._get_model()
        items = list(getattr(model, "items", []) or []) if model is not None else []
        from engine.editor.editor_item_editor_controller import item_definition_to_dict

        return [item_definition_to_dict(item) for item in items]

    def draw(self) -> None:
        controller = self._get_controller()
        if not self._is_visible_for_controller(controller):
            return

        from engine.editor.editor_dock_query import get_effective_dock_widths
        from engine.editor.editor_shell_layout import compute_editor_shell_layout
        from engine.editor.widgets.panel_primitives import EditorPanelBase, PanelField, PanelHeader, PanelRow

        window_w = int(getattr(self.window, "width", 1280) or 1280)
        window_h = int(getattr(self.window, "height", 720) or 720)
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
            x=float(content_left),
            y=float(content_bottom),
            width=max(0.0, float(split_x - content_left - (ITEM_EDITOR_PANEL_GAP * 0.5))),
            height=max(0.0, float(content_top - content_bottom)),
        )
        detail_rect = Rect(
            x=float(split_x + (ITEM_EDITOR_PANEL_GAP * 0.5)),
            y=float(content_bottom),
            width=max(0.0, float(content_right - split_x - (ITEM_EDITOR_PANEL_GAP * 0.5))),
            height=max(0.0, float(content_top - content_bottom)),
        )

        model = self._get_model()
        item_editor = getattr(controller, "item_editor", None)
        edit_mode = bool(item_editor is not None and item_editor.is_edit_mode_active())
        dirty_marker = " *" if item_editor is not None and item_editor.is_dirty() else ""
        list_panel = EditorPanelBase(
            list_rect,
            panel_bg=(0, 0, 0, 0),
            panel_border=(0, 0, 0, 0),
            item_spacing=0.0,
            inner_padding_x=0.0,
            inner_padding_y=0.0,
        )
        list_panel.add_header(PanelHeader("Items", str(model.item_count) if model is not None else "0"))

        if model is None:
            list_panel.add_row(
                PanelRow(
                    PanelField("Unable to load items", self._load_error, label_color=ITEM_EDITOR_DIM_COLOR),
                    height=ITEM_EDITOR_ROW_HEIGHT,
                    padding_x=ITEM_EDITOR_ROW_PADDING_X,
                )
            )
        elif not model.items:
            list_panel.add_row(
                PanelRow(
                    PanelField("No items found", None, label_color=ITEM_EDITOR_DIM_COLOR),
                    height=ITEM_EDITOR_ROW_HEIGHT,
                    padding_x=ITEM_EDITOR_ROW_PADDING_X,
                )
            )
        else:
            selected_index = model._clamp_index(model.selected_index)
            for index, label in enumerate(model.list_rows()):
                row = PanelRow(
                    PanelField(label, None, label_color=ITEM_EDITOR_TEXT_COLOR),
                    height=ITEM_EDITOR_ROW_HEIGHT,
                    padding_x=ITEM_EDITOR_ROW_PADDING_X,
                    selected_bg=ITEM_EDITOR_SELECTED_BG,
                )
                row.set_selected(index == selected_index)
                list_panel.add_row(row)
        list_panel.draw()

        detail_panel = EditorPanelBase(
            detail_rect,
            panel_bg=(0, 0, 0, 0),
            panel_border=(0, 0, 0, 0),
            item_spacing=2.0,
            inner_padding_x=0.0,
            inner_padding_y=0.0,
        )
        item = model.selected_item if model is not None else None
        button_rows: dict[str, object] = {}
        id_row: object | None = None
        if item is None:
            detail_panel.add_header(PanelHeader(f"Items{dirty_marker}", "No item"))
        else:
            detail_panel.add_header(PanelHeader(f"Items{dirty_marker}", item.id))
            if item_editor is not None and item_editor.last_error_message():
                detail_panel.add_row(
                    PanelRow(
                        PanelField("Error", item_editor.last_error_message(), label_color=ITEM_EDITOR_ERROR_COLOR),
                        height=ITEM_EDITOR_ROW_HEIGHT,
                        padding_x=ITEM_EDITOR_ROW_PADDING_X,
                    )
                )
            for label, value in model.selected_detail_rows():
                if edit_mode and label == "ID":
                    id_row = detail_panel.add_row(
                        PanelRow(
                            PanelField("ID", "", label_color=ITEM_EDITOR_TEXT_COLOR, value_color=ITEM_EDITOR_DIM_COLOR),
                            height=ITEM_EDITOR_ROW_HEIGHT,
                            padding_x=ITEM_EDITOR_ROW_PADDING_X,
                        )
                    )
                    continue
                detail_panel.add_row(
                    PanelRow(
                        PanelField(label, value, label_color=ITEM_EDITOR_TEXT_COLOR, value_color=ITEM_EDITOR_DIM_COLOR),
                        height=ITEM_EDITOR_ROW_HEIGHT,
                        padding_x=ITEM_EDITOR_ROW_PADDING_X,
                    )
                )
            if edit_mode:
                button_rows["save"] = detail_panel.add_row(
                    PanelRow(
                        PanelField("Save", None, label_color=ITEM_EDITOR_BUTTON_COLOR),
                        height=ITEM_EDITOR_ROW_HEIGHT,
                        padding_x=ITEM_EDITOR_ROW_PADDING_X,
                    )
                )
                button_rows["cancel"] = detail_panel.add_row(
                    PanelRow(
                        PanelField("Cancel", None, label_color=ITEM_EDITOR_BUTTON_COLOR),
                        height=ITEM_EDITOR_ROW_HEIGHT,
                        padding_x=ITEM_EDITOR_ROW_PADDING_X,
                    )
                )
            else:
                button_rows["edit"] = detail_panel.add_row(
                    PanelRow(
                        PanelField("Edit", None, label_color=ITEM_EDITOR_BUTTON_COLOR),
                        height=ITEM_EDITOR_ROW_HEIGHT,
                        padding_x=ITEM_EDITOR_ROW_PADDING_X,
                    )
                )
        detail_panel.draw()
        if item_editor is not None:
            rects: dict[str, Rect] = {}
            for action, row in button_rows.items():
                rect = getattr(row, "last_rect", None)
                if _is_rect_like(rect):
                    rects[action] = rect
            item_editor.set_button_rects(rects)
        if edit_mode and item_editor is not None and id_row is not None:
            row_rect = getattr(id_row, "last_rect", None)
            if _is_rect_like(row_rect):
                field_rect = Rect(
                    x=float(row_rect.left + 42.0),
                    y=float(row_rect.bottom + 1.0),
                    width=max(0.0, float(row_rect.width - 48.0)),
                    height=max(0.0, float(row_rect.height - 2.0)),
                )
                self._draw_text_input(item_editor.id_input(), field_rect)

    def _draw_text_input(self, text_input: TextInput, rect: Rect) -> None:
        from engine.editor.widgets import panel_primitives

        layout = text_input.layout(rect)
        for instruction in layout.instructions:
            payload = instruction.payload
            instr_rect = payload.get("rect")
            if instruction.kind == "text_input_bg" and _is_rect_like(instr_rect):
                bg = (30, 30, 36, 220) if payload.get("focused") else (22, 22, 28, 190)
                border = (100, 200, 255, 180) if payload.get("focused") else (90, 90, 100, 140)
                panel_primitives.draw_panel_bg(instr_rect.left, instr_rect.right, instr_rect.bottom, instr_rect.top, color=bg)
                panel_primitives._draw_lrtb_rectangle_outline(
                    instr_rect.left,
                    instr_rect.right,
                    instr_rect.top,
                    instr_rect.bottom,
                    border,
                    1,
                )
            elif instruction.kind == "text_input_text":
                color = ITEM_EDITOR_DIM_COLOR if payload.get("is_placeholder") else ITEM_EDITOR_TEXT_COLOR
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
                    color=ITEM_EDITOR_TEXT_COLOR,
                    font_size=int(payload.get("font_size", 12)),
                    anchor_x="left",
                    anchor_y="center",
                )


def _is_rect_like(value: object) -> bool:
    return all(hasattr(value, attr) for attr in ("left", "right", "bottom", "top", "width", "height"))
