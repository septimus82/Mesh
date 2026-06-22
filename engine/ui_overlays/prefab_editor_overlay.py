"""Read-only Prefab Editor overlay for the editor right dock."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from engine.ui_overlays.common import UIElement
from engine.ui_overlays.editor_database_form_helpers import (
    FormColors,
    add_form_buttons,
    collect_button_rects,
    compute_database_form_layout,
    draw_text_input,
    draw_text_input_rows,
    scalar_rows_for_mode,
    sync_text_inputs,
    try_click_text_widget,
)
from engine.ui_overlays.theme import EDITOR_THEME
from engine.ui_overlays.widgets import Rect, TextInput

if TYPE_CHECKING:  # pragma: no cover
    from engine.game import GameWindow


PREFAB_EDITOR_TEXT_COLOR = EDITOR_THEME.text_primary
PREFAB_EDITOR_DIM_COLOR = EDITOR_THEME.text_dim
PREFAB_EDITOR_SELECTED_BG = EDITOR_THEME.selected_row_bg
PREFAB_EDITOR_ERROR_COLOR = EDITOR_THEME.error_text
PREFAB_EDITOR_BUTTON_COLOR = EDITOR_THEME.action_text
PREFAB_EDITOR_ROW_HEIGHT = 18.0
PREFAB_EDITOR_ROW_PADDING_X = 6.0
PREFAB_EDITOR_PANEL_GAP = 8.0
PREFAB_EDITOR_EDITABLE_SCALAR_FIELDS = {"id", "display_name", "entity.sprite", "entity.encounter_cost"}
_PREFAB_FORM_COLORS = FormColors(
    text=EDITOR_THEME.text_primary,
    dim=EDITOR_THEME.text_dim,
    button=EDITOR_THEME.action_text,
)
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
        self._row_hits: list[tuple[int, object]] = []
        self._complex_entry_action_hits: list[tuple[str, Any]] = []
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
        self._row_hits = []
        self._complex_entry_action_hits = []
        controller = self._get_controller()
        if not self._is_visible_for_controller(controller):
            return

        from engine.editor.widgets.panel_primitives import EditorPanelBase, PanelField, PanelHeader, PanelRow

        list_rect, detail_rect = compute_database_form_layout(self.window, controller, PREFAB_EDITOR_PANEL_GAP)

        model = self._get_model()
        prefab_editor = getattr(controller, "prefab_editor", None)
        edit_mode = bool(prefab_editor is not None and prefab_editor.is_edit_mode_active())
        dirty_marker = " *" if prefab_editor is not None and prefab_editor.is_dirty() else ""
        list_panel = EditorPanelBase(
            list_rect,
            panel_bg=EDITOR_THEME.transparent,
            panel_border=EDITOR_THEME.transparent,
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
                self._row_hits.append((index, row))
                list_panel.add_row(row)
        list_panel.draw()

        detail_panel = EditorPanelBase(
            detail_rect,
            panel_bg=EDITOR_THEME.transparent,
            panel_border=EDITOR_THEME.transparent,
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
            from engine.editor.editor_prefab_editor_controller import _get_path  # noqa: PLC0415
            from engine.editor.prefab_editor_model import PREFAB_SCALAR_FIELD_ORDER  # noqa: PLC0415

            for label, value, field_path in scalar_rows_for_mode(
                model=model,
                edit_mode=edit_mode,
                scalar_field_order=PREFAB_SCALAR_FIELD_ORDER,
                selected_record=model.selected_prefab,
                value_for_field=lambda record, field: _get_path(record, field) if isinstance(record, dict) else None,
                label_for_field=_label_for_field,
            ):
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
            from engine.editor.prefab_editor_model import (  # noqa: PLC0415
                PREFAB_LIST_COMPLEX_FIELDS,
                behaviour_config_inner_rows,
                behaviour_config_scalar_value_paths,
                complex_detail_rows_for_prefab,
                complex_entry_rows,
            )

            edit_buffer = getattr(prefab_editor, "edit_buffer", None) if prefab_editor is not None else None
            complex_source = edit_buffer if edit_mode and isinstance(edit_buffer, dict) else prefab
            complex_rows = complex_detail_rows_for_prefab(complex_source)
            behaviour_config_scalar_paths = {
                field_path
                for field_path, _label in behaviour_config_scalar_value_paths(complex_source)
            } if edit_mode else set()
            if complex_rows:
                detail_panel.add_header(PanelHeader("Complex fields (read-only)", None, title_color=PREFAB_EDITOR_DIM_COLOR))

                def add_complex_action(action: str, label: str) -> None:
                    self._complex_entry_action_hits.append(
                        (
                            action,
                            detail_panel.add_row(
                                PanelRow(
                                    PanelField(
                                        label,
                                        "",
                                        label_color=PREFAB_EDITOR_BUTTON_COLOR,
                                        value_color=PREFAB_EDITOR_DIM_COLOR,
                                    ),
                                    height=PREFAB_EDITOR_ROW_HEIGHT,
                                    padding_x=PREFAB_EDITOR_ROW_PADDING_X,
                                )
                            ),
                        )
                    )

                for complex_field_path, label, value in complex_rows:
                    detail_panel.add_row(
                        PanelRow(
                            PanelField(label, value, label_color=PREFAB_EDITOR_TEXT_COLOR, value_color=PREFAB_EDITOR_DIM_COLOR),
                            height=PREFAB_EDITOR_ROW_HEIGHT,
                            padding_x=PREFAB_EDITOR_ROW_PADDING_X,
                        )
                    )
                    for entry_label, entry_value in complex_entry_rows(complex_source, complex_field_path):
                        index_text = entry_label.rsplit(" ", 1)[-1]
                        list_entry_widget_field = f"{complex_field_path}.{index_text}"
                        if edit_mode and complex_field_path in PREFAB_LIST_COMPLEX_FIELDS:
                            entry_index = int(index_text) if index_text.isdigit() else -1
                            entry_count = _list_entry_count(complex_source, complex_field_path)
                            self._widget_rows[list_entry_widget_field] = detail_panel.add_row(
                                PanelRow(
                                    PanelField(
                                        entry_label,
                                        entry_value,
                                        label_color=PREFAB_EDITOR_TEXT_COLOR,
                                        value_color=PREFAB_EDITOR_DIM_COLOR,
                                    ),
                                    height=PREFAB_EDITOR_ROW_HEIGHT,
                                    padding_x=PREFAB_EDITOR_ROW_PADDING_X,
                                )
                            )
                            if complex_field_path == "entity.behaviours" and entry_index > 0:
                                add_complex_action(
                                    f"{complex_field_path}#{index_text}#move_up",
                                    f"Move up behaviour {index_text}",
                                )
                            if complex_field_path == "entity.behaviours" and 0 <= entry_index < entry_count - 1:
                                add_complex_action(
                                    f"{complex_field_path}#{index_text}#move_down",
                                    f"Move down behaviour {index_text}",
                                )
                            action = f"{complex_field_path}#{index_text}#delete"
                            delete_label = f"Delete {entry_label[:1].lower()}{entry_label[1:]}"
                            add_complex_action(action, delete_label)
                            continue
                        if edit_mode and complex_field_path == "metadata":
                            self._widget_rows[f"metadata_key.{entry_label}"] = detail_panel.add_row(
                                PanelRow(
                                    PanelField(
                                        "Metadata key",
                                        "",
                                        label_color=PREFAB_EDITOR_TEXT_COLOR,
                                        value_color=PREFAB_EDITOR_DIM_COLOR,
                                    ),
                                    height=PREFAB_EDITOR_ROW_HEIGHT,
                                    padding_x=PREFAB_EDITOR_ROW_PADDING_X,
                                )
                            )
                        entry_row = detail_panel.add_row(
                            PanelRow(
                                PanelField(
                                    entry_label,
                                    entry_value,
                                    label_color=PREFAB_EDITOR_TEXT_COLOR,
                                    value_color=PREFAB_EDITOR_DIM_COLOR,
                                ),
                                height=PREFAB_EDITOR_ROW_HEIGHT,
                                padding_x=PREFAB_EDITOR_ROW_PADDING_X,
                            )
                        )
                        if edit_mode and complex_field_path == "metadata":
                            self._widget_rows[f"metadata.{entry_label}"] = entry_row
                            add_complex_action(
                                f"{complex_field_path}#{entry_label}#delete",
                                f"Delete metadata {entry_label}",
                            )
                    if complex_field_path == "entity.behaviour_config":
                        for entry_label, entry_value in behaviour_config_inner_rows(complex_source):
                            field_path = f"entity.behaviour_config.{entry_label}"
                            entry_row = detail_panel.add_row(
                                PanelRow(
                                    PanelField(
                                        entry_label,
                                        entry_value,
                                        label_color=PREFAB_EDITOR_TEXT_COLOR,
                                        value_color=PREFAB_EDITOR_DIM_COLOR,
                                    ),
                                    height=PREFAB_EDITOR_ROW_HEIGHT,
                                    padding_x=PREFAB_EDITOR_ROW_PADDING_X,
                                )
                            )
                            if field_path in behaviour_config_scalar_paths:
                                self._widget_rows[field_path] = entry_row
                                behaviour, separator, config_key = entry_label.partition(".")
                                if separator:
                                    add_complex_action(
                                        f"entity.behaviour_config#{behaviour}#{config_key}#delete",
                                        f"Delete behaviour config {entry_label}",
                                    )
                    if edit_mode and complex_field_path in PREFAB_LIST_COMPLEX_FIELDS:
                        add_complex_action(f"{complex_field_path}#add", f"Add {_add_label_for_list_field(complex_field_path)}")
                    if edit_mode and complex_field_path == "metadata":
                        add_complex_action("metadata#add", "Add metadata")
            button_rows = add_form_buttons(
                detail_panel,
                edit_mode=edit_mode,
                button_color=PREFAB_EDITOR_BUTTON_COLOR,
                row_height=PREFAB_EDITOR_ROW_HEIGHT,
                padding_x=PREFAB_EDITOR_ROW_PADDING_X,
            )
        detail_panel.draw()
        if prefab_editor is not None:
            prefab_editor.set_button_rects(collect_button_rects(button_rows))
        if edit_mode and prefab_editor is not None:
            self._draw_edit_widgets(prefab_editor)

    def row_index_at(self, x: float, y: float) -> int | None:
        for index, row in self._row_hits:
            if row.hit_test(float(x), float(y)):
                return index
        return None

    def complex_entry_action_at(self, x: float, y: float) -> str | None:
        for action, row in self._complex_entry_action_hits:
            if row.hit_test(float(x), float(y)):
                return action
        return None

    def set_selected_index(self, index: int) -> bool:
        model = self._get_model()
        setter = getattr(model, "set_selected_index", None)
        return bool(setter(int(index))) if callable(setter) else False

    def _draw_text_input(self, text_input: TextInput, rect: Rect) -> None:
        draw_text_input(text_input, rect, _PREFAB_FORM_COLORS)

    def _sync_edit_widgets(self, prefab_editor: object) -> None:
        edit_buffer = getattr(prefab_editor, "edit_buffer", None)
        if not isinstance(edit_buffer, dict):
            return
        focused = getattr(prefab_editor, "focused_field", lambda: None)
        focused_field = focused() if callable(focused) else None
        text_inputs = getattr(prefab_editor, "text_inputs", lambda: {})()
        if isinstance(text_inputs, dict):
            sync_text_inputs(
                text_inputs,
                focused_field,
                lambda field: _edit_widget_value(edit_buffer, str(field)),
            )

    def _draw_edit_widgets(self, prefab_editor: object) -> None:
        text_inputs = getattr(prefab_editor, "text_inputs", lambda: {})()
        if isinstance(text_inputs, dict):
            draw_text_input_rows(self._widget_rows, text_inputs, self._draw_text_input)

    def try_click_widget(self, x: float, y: float) -> str | None:
        controller = self._get_controller()
        prefab_editor = getattr(controller, "prefab_editor", None) if controller is not None else None
        if prefab_editor is None:
            return None
        return try_click_text_widget(self._widget_rows, prefab_editor, x, y)


def _label_for_field(field_path: str) -> str:
    return {
        "id": "ID",
        "display_name": "Display name",
        "entity.sprite": "Entity sprite",
        "entity.encounter_cost": "Entity encounter cost",
    }.get(field_path, field_path)


def _add_label_for_list_field(field_path: str) -> str:
    return {
        "tags": "tag",
        "require_flags": "require flag",
        "forbid_flags": "forbid flag",
        "entity.behaviours": "behaviour",
        "entity.require_flags": "entity require flag",
    }.get(field_path, field_path)


def _edit_widget_value(edit_buffer: dict[str, Any], field_path: str) -> Any:
    if field_path.startswith("metadata_key."):
        return field_path.removeprefix("metadata_key.")
    if field_path.startswith("metadata."):
        metadata = edit_buffer.get("metadata")
        key = field_path.removeprefix("metadata.")
        return metadata.get(key) if isinstance(metadata, dict) else None
    from engine.editor.editor_prefab_editor_controller import _get_path  # noqa: PLC0415

    return _get_path(edit_buffer, field_path)


def _list_entry_count(prefab: dict[str, Any], field_path: str) -> int:
    current: Any = prefab
    for part in field_path.split("."):
        if not isinstance(current, dict):
            return 0
        current = current.get(part)
    return len(current) if isinstance(current, list) else 0

