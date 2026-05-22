"""Read-only Prefab Editor overlay for the editor right dock."""

from __future__ import annotations

from typing import TYPE_CHECKING

from engine.ui_overlays.common import UIElement
from engine.ui_overlays.widgets import Rect, TextInput

if TYPE_CHECKING:  # pragma: no cover
    from engine.game import GameWindow


PREFAB_EDITOR_TEXT_COLOR = (220, 220, 230, 255)
PREFAB_EDITOR_DIM_COLOR = (150, 150, 160, 255)
PREFAB_EDITOR_SELECTED_BG = (90, 140, 200, 140)
PREFAB_EDITOR_ERROR_COLOR = (255, 120, 120, 255)
PREFAB_EDITOR_BUTTON_COLOR = (100, 200, 255, 255)
PREFAB_EDITOR_ROW_HEIGHT = 18.0
PREFAB_EDITOR_ROW_PADDING_X = 6.0
PREFAB_EDITOR_PANEL_GAP = 8.0
PREFAB_EDITOR_EDITABLE_SCALAR_FIELDS = {"id", "display_name", "entity.sprite", "entity.encounter_cost"}
PREFAB_EDITOR_READ_ONLY_COMPLEX_FIELDS = {
    "tags",
    "require_flags",
    "forbid_flags",
    "entity.behaviours",
    "entity.behaviour_config",
    "entity.require_flags",
    "metadata",
}


class PrefabEditorOverlay(UIElement):
    """Read-only prefab database view hosted in the editor right dock."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._model: object | None = None
        self._load_error: str | None = None
        self._widget_rows: dict[str, object] = {}

    def _get_controller(self) -> object | None:
        return getattr(self.window, "editor_controller", None)

    def _is_visible_for_controller(self, controller: object | None) -> bool:
        if controller is None or not getattr(controller, "active", False):
            return False
        dock = getattr(controller, "dock", None)
        snapshot = dock.get_snapshot() if dock is not None and hasattr(dock, "get_snapshot") else dock
        right_tab = getattr(snapshot, "right_tab", "Inspector") or "Inspector"
        return right_tab == "Prefabs"

    def _get_model(self) -> object | None:
        if self._model is not None:
            return self._model
        try:
            from engine.editor.prefab_editor_model import PrefabEditorModel

            self._model = PrefabEditorModel.load()
            self._load_error = None
        except Exception as exc:  # pragma: no cover - defensive runtime path
            self._model = None
            self._load_error = str(exc)
        return self._model

    def reload_model(self) -> None:
        self._model = None
        self._get_model()

    def selected_prefab_dict(self) -> dict[str, object] | None:
        model = self._get_model()
        prefab = model.selected_prefab() if model is not None and hasattr(model, "selected_prefab") else None
        return dict(prefab) if isinstance(prefab, dict) else None

    def all_prefab_dicts(self) -> list[dict[str, object]]:
        model = self._get_model()
        prefabs = model.prefabs() if model is not None and hasattr(model, "prefabs") else []
        return [dict(prefab) for prefab in prefabs if isinstance(prefab, dict)]

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
            width=max(0.0, float(split_x - content_left - (PREFAB_EDITOR_PANEL_GAP * 0.5))),
            height=max(0.0, float(content_top - content_bottom)),
        )
        detail_rect = Rect(
            x=float(split_x + (PREFAB_EDITOR_PANEL_GAP * 0.5)),
            y=float(content_bottom),
            width=max(0.0, float(content_right - split_x - (PREFAB_EDITOR_PANEL_GAP * 0.5))),
            height=max(0.0, float(content_top - content_bottom)),
        )

        model = self._get_model()
        prefab_editor = getattr(controller, "prefab_editor", None)
        edit_mode = bool(prefab_editor is not None and prefab_editor.is_edit_mode_active())
        dirty_marker = " *" if prefab_editor is not None and prefab_editor.is_dirty() else ""
        list_panel = EditorPanelBase(
            list_rect,
            panel_bg=(0, 0, 0, 0),
            panel_border=(0, 0, 0, 0),
            item_spacing=0.0,
            inner_padding_x=0.0,
            inner_padding_y=0.0,
        )
        list_panel.add_header(PanelHeader("Prefabs", str(model.prefab_count) if model is not None else "0"))

        if model is None:
            list_panel.add_row(
                PanelRow(
                    PanelField("Unable to load prefabs", self._load_error, label_color=PREFAB_EDITOR_DIM_COLOR),
                    height=PREFAB_EDITOR_ROW_HEIGHT,
                    padding_x=PREFAB_EDITOR_ROW_PADDING_X,
                )
            )
        elif not model.prefabs():
            list_panel.add_row(
                PanelRow(
                    PanelField("No prefabs found", None, label_color=PREFAB_EDITOR_DIM_COLOR),
                    height=PREFAB_EDITOR_ROW_HEIGHT,
                    padding_x=PREFAB_EDITOR_ROW_PADDING_X,
                )
            )
        else:
            selected_index = model.selected_index()
            for index, (label, prefab_id) in enumerate(model.list_rows()):
                row = PanelRow(
                    PanelField(label, prefab_id, label_color=PREFAB_EDITOR_TEXT_COLOR, value_color=PREFAB_EDITOR_DIM_COLOR),
                    height=PREFAB_EDITOR_ROW_HEIGHT,
                    padding_x=PREFAB_EDITOR_ROW_PADDING_X,
                    selected_bg=PREFAB_EDITOR_SELECTED_BG,
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
        prefab = model.selected_prefab() if model is not None else None
        button_rows: dict[str, object] = {}
        self._widget_rows = {}
        if prefab is None:
            detail_panel.add_header(PanelHeader(f"Prefabs{dirty_marker}", "No prefab"))
        else:
            if edit_mode and prefab_editor is not None:
                self._sync_edit_widgets(prefab_editor)
            prefab_id = str(prefab.get("id", "") or "")
            display_name = str(prefab.get("display_name", "") or prefab_id)
            detail_panel.add_header(PanelHeader(f"{display_name}{dirty_marker}", prefab_id))
            if prefab_editor is not None and prefab_editor.last_error_message():
                detail_panel.add_row(
                    PanelRow(
                        PanelField("Error", prefab_editor.last_error_message(), label_color=PREFAB_EDITOR_ERROR_COLOR),
                        height=PREFAB_EDITOR_ROW_HEIGHT,
                        padding_x=PREFAB_EDITOR_ROW_PADDING_X,
                    )
                )
            for label, value, field_path in model.scalar_detail_rows():
                if edit_mode and field_path in PREFAB_EDITOR_EDITABLE_SCALAR_FIELDS:
                    self._widget_rows[field_path] = detail_panel.add_row(
                        PanelRow(
                            PanelField(label, "", label_color=PREFAB_EDITOR_TEXT_COLOR, value_color=PREFAB_EDITOR_DIM_COLOR),
                            height=PREFAB_EDITOR_ROW_HEIGHT,
                            padding_x=PREFAB_EDITOR_ROW_PADDING_X,
                        )
                    )
                    continue
                detail_panel.add_row(
                    PanelRow(
                        PanelField(label, value, label_color=PREFAB_EDITOR_TEXT_COLOR, value_color=PREFAB_EDITOR_DIM_COLOR),
                        height=PREFAB_EDITOR_ROW_HEIGHT,
                        padding_x=PREFAB_EDITOR_ROW_PADDING_X,
                    )
                )
            complex_rows = model.complex_detail_rows()
            if complex_rows:
                detail_panel.add_header(PanelHeader("Complex fields (read-only)", None, title_color=PREFAB_EDITOR_DIM_COLOR))
                for label, value in complex_rows:
                    detail_panel.add_row(
                        PanelRow(
                            PanelField(label, value, label_color=PREFAB_EDITOR_TEXT_COLOR, value_color=PREFAB_EDITOR_DIM_COLOR),
                            height=PREFAB_EDITOR_ROW_HEIGHT,
                            padding_x=PREFAB_EDITOR_ROW_PADDING_X,
                        )
                    )
            if edit_mode:
                button_rows["save"] = detail_panel.add_row(
                    PanelRow(
                        PanelField("Save", None, label_color=PREFAB_EDITOR_BUTTON_COLOR),
                        height=PREFAB_EDITOR_ROW_HEIGHT,
                        padding_x=PREFAB_EDITOR_ROW_PADDING_X,
                    )
                )
                button_rows["cancel"] = detail_panel.add_row(
                    PanelRow(
                        PanelField("Cancel", None, label_color=PREFAB_EDITOR_BUTTON_COLOR),
                        height=PREFAB_EDITOR_ROW_HEIGHT,
                        padding_x=PREFAB_EDITOR_ROW_PADDING_X,
                    )
                )
            else:
                button_rows["edit"] = detail_panel.add_row(
                    PanelRow(
                        PanelField("Edit", None, label_color=PREFAB_EDITOR_BUTTON_COLOR),
                        height=PREFAB_EDITOR_ROW_HEIGHT,
                        padding_x=PREFAB_EDITOR_ROW_PADDING_X,
                    )
                )
        detail_panel.draw()
        if prefab_editor is not None:
            rects: dict[str, Rect] = {}
            for action, row in button_rows.items():
                rect = getattr(row, "last_rect", None)
                if _is_rect_like(rect):
                    rects[action] = rect
            prefab_editor.set_button_rects(rects)
        if edit_mode and prefab_editor is not None:
            self._draw_edit_widgets(prefab_editor)

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
                color = PREFAB_EDITOR_DIM_COLOR if payload.get("is_placeholder") else PREFAB_EDITOR_TEXT_COLOR
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
                    color=PREFAB_EDITOR_TEXT_COLOR,
                    font_size=int(payload.get("font_size", 12)),
                    anchor_x="left",
                    anchor_y="center",
                )

    def _sync_edit_widgets(self, prefab_editor: object) -> None:
        from engine.editor.editor_prefab_editor_controller import _get_path

        edit_buffer = getattr(prefab_editor, "edit_buffer", None)
        if not isinstance(edit_buffer, dict):
            return
        focused = getattr(prefab_editor, "focused_field", lambda: None)
        focused_field = focused() if callable(focused) else None
        text_inputs = getattr(prefab_editor, "text_inputs", lambda: {})()
        if isinstance(text_inputs, dict):
            for field, widget in text_inputs.items():
                if isinstance(widget, TextInput):
                    value = _get_path(edit_buffer, str(field))
                    widget.text = "" if value is None else str(value)
                    widget.focused = field == focused_field

    def _draw_edit_widgets(self, prefab_editor: object) -> None:
        text_inputs = getattr(prefab_editor, "text_inputs", lambda: {})()
        for field, row in self._widget_rows.items():
            row_rect = getattr(row, "last_rect", None)
            if not _is_rect_like(row_rect):
                continue
            field_rect = Rect(
                x=float(row_rect.left + 92.0),
                y=float(row_rect.bottom + 1.0),
                width=max(0.0, float(row_rect.width - 98.0)),
                height=max(0.0, float(row_rect.height - 2.0)),
            )
            widget = text_inputs.get(field) if isinstance(text_inputs, dict) else None
            if isinstance(widget, TextInput):
                self._draw_text_input(widget, field_rect)

    def try_click_widget(self, x: float, y: float) -> str | None:
        for field, row in self._widget_rows.items():
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
            controller = self._get_controller()
            prefab_editor = getattr(controller, "prefab_editor", None) if controller is not None else None
            text_input = getattr(prefab_editor, "text_input", lambda _field: None)(field) if prefab_editor is not None else None
            if isinstance(text_input, TextInput):
                text_input.on_mouse_press(float(x), float(y))
                return field
        return None


def _is_rect_like(value: object) -> bool:
    return all(hasattr(value, attr) for attr in ("left", "right", "bottom", "top", "width", "height"))

