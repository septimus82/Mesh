"""Read-only Item Editor overlay for the editor right dock."""

from __future__ import annotations

from typing import TYPE_CHECKING

from engine.ui_overlays.common import UIElement
from engine.ui_overlays.editor_database_form_helpers import (
    FormColors,
    add_form_buttons,
    collect_button_rects,
    compute_database_form_layout,
    draw_text_input,
    draw_text_input_rows,
    sync_text_inputs,
    try_click_text_widget,
)
from engine.ui_overlays.widgets import Rect, TextInput, Toggle

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
ITEM_EDITOR_EDITABLE_SCALAR_FIELDS = {"id", "name", "description", "icon", "stackable", "max_stack"}
ITEM_EDITOR_READ_ONLY_COMPLEX_FIELDS = {"tags", "effects"}
_ITEM_FORM_COLORS = FormColors(
    text=ITEM_EDITOR_TEXT_COLOR,
    dim=ITEM_EDITOR_DIM_COLOR,
    button=ITEM_EDITOR_BUTTON_COLOR,
)


class ItemEditorOverlay(UIElement):
    """Read-only item database view hosted in the editor right dock."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._model: object | None = None
        self._load_error: str | None = None
        self._stackable_toggle = Toggle(label="stackable", value=False, height=ITEM_EDITOR_ROW_HEIGHT)
        self._widget_rows: dict[str, object] = {}

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

        from engine.editor.widgets.panel_primitives import EditorPanelBase, PanelField, PanelHeader, PanelRow

        list_rect, detail_rect = compute_database_form_layout(self.window, controller, ITEM_EDITOR_PANEL_GAP)

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
        self._widget_rows = {}
        if item is None:
            detail_panel.add_header(PanelHeader(f"Items{dirty_marker}", "No item"))
        else:
            if edit_mode and item_editor is not None:
                self._sync_edit_widgets(item_editor)
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
                field_name = _field_name_for_label(label)
                if edit_mode and field_name in ITEM_EDITOR_EDITABLE_SCALAR_FIELDS:
                    self._widget_rows[field_name] = detail_panel.add_row(
                        PanelRow(
                            PanelField(label, "", label_color=ITEM_EDITOR_TEXT_COLOR, value_color=ITEM_EDITOR_DIM_COLOR),
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
            button_rows = add_form_buttons(
                detail_panel,
                edit_mode=edit_mode,
                button_color=ITEM_EDITOR_BUTTON_COLOR,
                row_height=ITEM_EDITOR_ROW_HEIGHT,
                padding_x=ITEM_EDITOR_ROW_PADDING_X,
            )
        detail_panel.draw()
        if item_editor is not None:
            item_editor.set_button_rects(collect_button_rects(button_rows))
        if edit_mode and item_editor is not None:
            self._draw_edit_widgets(item_editor)

    def _draw_text_input(self, text_input: TextInput, rect: Rect) -> None:
        draw_text_input(text_input, rect, _ITEM_FORM_COLORS)

    def _sync_edit_widgets(self, item_editor: object) -> None:
        edit_buffer = getattr(item_editor, "edit_buffer", None)
        if not isinstance(edit_buffer, dict):
            return
        focused = getattr(item_editor, "focused_field", lambda: None)
        focused_field = focused() if callable(focused) else None
        text_inputs = getattr(item_editor, "text_inputs", lambda: {})()
        if isinstance(text_inputs, dict):
            sync_text_inputs(
                text_inputs,
                focused_field,
                lambda field: edit_buffer.get(field),
            )
        self._stackable_toggle.value = bool(edit_buffer.get("stackable", False))

    def _draw_edit_widgets(self, item_editor: object) -> None:
        text_inputs = getattr(item_editor, "text_inputs", lambda: {})()
        if isinstance(text_inputs, dict):
            draw_text_input_rows(
                self._widget_rows,
                text_inputs,
                self._draw_text_input,
                skip_fields=("stackable",),
            )
        row = self._widget_rows.get("stackable")
        row_rect = getattr(row, "last_rect", None)
        if _is_rect_like(row_rect):
            field_rect = Rect(
                x=float(row_rect.left + 92.0),
                y=float(row_rect.bottom + 1.0),
                width=max(0.0, float(row_rect.width - 98.0)),
                height=max(0.0, float(row_rect.height - 2.0)),
            )
            self._draw_toggle(self._stackable_toggle, field_rect)

    def _draw_toggle(self, toggle: Toggle, rect: Rect) -> None:
        from engine.editor.widgets import panel_primitives

        layout = toggle.layout(rect)
        for instruction in layout.instructions:
            if instruction.kind != "toggle_text":
                continue
            payload = instruction.payload
            panel_primitives.draw_text_cached(
                str(payload.get("text", "")),
                float(payload.get("x", rect.left)),
                float(payload.get("y", rect.center_y)),
                color=ITEM_EDITOR_TEXT_COLOR,
                font_size=12,
                anchor_x=str(payload.get("anchor_x", "left")),
                anchor_y=str(payload.get("anchor_y", "center")),
            )

    def try_click_widget(self, x: float, y: float) -> str | None:
        controller = self._get_controller()
        item_editor = getattr(controller, "item_editor", None) if controller is not None else None
        if item_editor is not None:
            clicked_field = try_click_text_widget(
                self._widget_rows,
                item_editor,
                x,
                y,
                skip_fields=("stackable",),
            )
            if clicked_field is not None:
                return clicked_field
        for field, row in self._widget_rows.items():
            if field != "stackable":
                continue
            row_rect = getattr(row, "last_rect", None)
            if not _is_rect_like(row_rect):
                continue
            field_rect = Rect(
                x=float(row_rect.left + 92.0),
                y=float(row_rect.bottom + 1.0),
                width=max(0.0, float(row_rect.width - 98.0)),
                height=max(0.0, float(row_rect.height - 2.0)),
            )
            if not field_rect.contains(float(x), float(y)):
                continue
            if self._stackable_toggle.on_mouse_press(float(x), float(y)):
                edit_buffer = getattr(item_editor, "edit_buffer", None) if item_editor is not None else None
                if isinstance(edit_buffer, dict):
                    edit_buffer["stackable"] = bool(self._stackable_toggle.value)
                return "stackable"
            return None
        return None


def _is_rect_like(value: object) -> bool:
    return all(hasattr(value, attr) for attr in ("left", "right", "bottom", "top", "width", "height"))


def _field_name_for_label(label: str) -> str:
    return str(label).strip().lower().replace(" ", "_")
