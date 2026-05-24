"""Read-only Quest Editor overlay for the editor right dock."""

from __future__ import annotations

from typing import TYPE_CHECKING

from engine.ui_overlays.common import UIElement
from engine.ui_overlays.editor_database_form_helpers import (
    FormColors,
    compute_database_form_layout,
)

if TYPE_CHECKING:  # pragma: no cover
    from engine.game import GameWindow


QUEST_EDITOR_TEXT_COLOR = (220, 220, 230, 255)
QUEST_EDITOR_DIM_COLOR = (150, 150, 160, 255)
QUEST_EDITOR_SELECTED_BG = (90, 140, 200, 140)
QUEST_EDITOR_BUTTON_COLOR = (100, 200, 255, 255)
QUEST_EDITOR_ROW_HEIGHT = 18.0
QUEST_EDITOR_ROW_PADDING_X = 6.0
QUEST_EDITOR_PANEL_GAP = 8.0
_QUEST_FORM_COLORS = FormColors(
    text=QUEST_EDITOR_TEXT_COLOR,
    dim=QUEST_EDITOR_DIM_COLOR,
    button=QUEST_EDITOR_BUTTON_COLOR,
)
QUEST_EDITOR_READ_ONLY_COMPLEX_FIELDS = frozenset(
    {"stages", "steps", "reward", "requires_flags", "blocks_flags"}
)


class QuestEditorOverlay(UIElement):
    """Read-only quest database view hosted in the editor right dock."""

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
        return right_tab == "Quests"

    def _get_model(self) -> object | None:
        if self._model is not None:
            return self._model
        try:
            from engine.editor.quest_editor_model import QuestEditorModel

            self._model = QuestEditorModel.load()
            self._load_error = None
        except Exception as exc:  # pragma: no cover - defensive runtime path
            self._model = None
            self._load_error = str(exc)
        return self._model

    def reload_model(self) -> None:
        self._model = None
        self._get_model()

    def selected_quest_dict(self) -> dict[str, object] | None:
        model = self._get_model()
        quest = model.selected_quest() if model is not None and hasattr(model, "selected_quest") else None
        return dict(quest) if isinstance(quest, dict) else None

    def all_quest_dicts(self) -> list[dict[str, object]]:
        model = self._get_model()
        quests = model.quests() if model is not None and hasattr(model, "quests") else []
        return [dict(quest) for quest in quests if isinstance(quest, dict)]

    def draw(self) -> None:
        controller = self._get_controller()
        if not self._is_visible_for_controller(controller):
            return

        from engine.editor.widgets.panel_primitives import EditorPanelBase, PanelField, PanelHeader, PanelRow

        list_rect, detail_rect = compute_database_form_layout(self.window, controller, QUEST_EDITOR_PANEL_GAP)

        model = self._get_model()
        list_panel = EditorPanelBase(
            list_rect,
            panel_bg=(0, 0, 0, 0),
            panel_border=(0, 0, 0, 0),
            item_spacing=0.0,
            inner_padding_x=0.0,
            inner_padding_y=0.0,
        )
        list_panel.add_header(PanelHeader("Quests", str(model.quest_count) if model is not None else "0"))

        if model is None:
            list_panel.add_row(
                PanelRow(
                    PanelField("Unable to load quests", self._load_error, label_color=QUEST_EDITOR_DIM_COLOR),
                    height=QUEST_EDITOR_ROW_HEIGHT,
                    padding_x=QUEST_EDITOR_ROW_PADDING_X,
                )
            )
        elif not model.quests():
            list_panel.add_row(
                PanelRow(
                    PanelField("No quests found", None, label_color=QUEST_EDITOR_DIM_COLOR),
                    height=QUEST_EDITOR_ROW_HEIGHT,
                    padding_x=QUEST_EDITOR_ROW_PADDING_X,
                )
            )
        else:
            selected_index = model.selected_index()
            for index, (title, quest_id) in enumerate(model.list_rows()):
                row = PanelRow(
                    PanelField(title, quest_id, label_color=QUEST_EDITOR_TEXT_COLOR, value_color=QUEST_EDITOR_DIM_COLOR),
                    height=QUEST_EDITOR_ROW_HEIGHT,
                    padding_x=QUEST_EDITOR_ROW_PADDING_X,
                    selected_bg=QUEST_EDITOR_SELECTED_BG,
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
        quest = model.selected_quest() if model is not None else None
        if quest is None:
            detail_panel.add_header(PanelHeader("Quests", "No quest"))
        else:
            quest_id = str(quest.get("id", "") or "")
            title = str(quest.get("title", "") or quest_id)
            detail_panel.add_header(PanelHeader(title, quest_id))
            for label, value, _field_path in model.scalar_detail_rows():
                detail_panel.add_row(
                    PanelRow(
                        PanelField(label, value, label_color=QUEST_EDITOR_TEXT_COLOR, value_color=QUEST_EDITOR_DIM_COLOR),
                        height=QUEST_EDITOR_ROW_HEIGHT,
                        padding_x=QUEST_EDITOR_ROW_PADDING_X,
                    )
                )
            complex_rows = model.complex_detail_rows()
            if complex_rows:
                detail_panel.add_header(PanelHeader("Complex fields (read-only)", None, title_color=QUEST_EDITOR_DIM_COLOR))
                for label, value in complex_rows:
                    detail_panel.add_row(
                        PanelRow(
                            PanelField(label, value, label_color=QUEST_EDITOR_TEXT_COLOR, value_color=QUEST_EDITOR_DIM_COLOR),
                            height=QUEST_EDITOR_ROW_HEIGHT,
                            padding_x=QUEST_EDITOR_ROW_PADDING_X,
                        )
                    )
        detail_panel.draw()
