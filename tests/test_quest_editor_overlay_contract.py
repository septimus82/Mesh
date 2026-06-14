from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import engine.editor.widgets.panel_primitives as panel_primitives
from engine.editor.quest_editor_model import QuestEditorModel
from engine.ui_overlays.quest_editor_overlay import (
    QUEST_EDITOR_READ_ONLY_COMPLEX_FIELDS,
    QuestEditorOverlay,
)
from engine.ui_overlays.widgets import TextInput
from tests._dock_stub import make_dock_stub

pytestmark = [pytest.mark.fast]


class _QuestEditorStub:
    def __init__(self, *, edit_mode: bool = False, dirty: bool = False, error: str | None = None) -> None:
        self._edit_mode = edit_mode
        self._dirty = dirty
        self._error = error
        self.edit_buffer = {
            "id": "showcase_tour",
            "title": "Tour of the Mesh",
            "description": "Visit the demonstration rooms.",
            "type": "tour",
            "start_toast": "Tour started",
            "complete_toast": "Tour complete",
        }
        self._focused_field = "id" if edit_mode else None
        self._text_inputs = {
            "id": TextInput(text="showcase_tour", focused=edit_mode, font_size=12, height=18.0),
            "title": TextInput(text="Tour of the Mesh", focused=False, font_size=12, height=18.0),
            "description": TextInput(text="Visit the demonstration rooms.", focused=False, font_size=12, height=18.0),
            "type": TextInput(text="tour", focused=False, font_size=12, height=18.0),
            "start_toast": TextInput(text="Tour started", focused=False, font_size=12, height=18.0),
            "complete_toast": TextInput(text="Tour complete", focused=False, font_size=12, height=18.0),
        }
        self.button_rects: dict[str, object] = {}

    def is_edit_mode_active(self) -> bool:
        return self._edit_mode

    def is_dirty(self) -> bool:
        return self._dirty

    def last_error_message(self) -> str | None:
        return self._error

    def text_input(self, field: str) -> TextInput:
        return self._text_inputs[field]

    def text_inputs(self) -> dict[str, TextInput]:
        return dict(self._text_inputs)

    def focused_field(self) -> str | None:
        return self._focused_field

    def set_button_rects(self, rects: dict[str, object]) -> None:
        self.button_rects = dict(rects)


def _window_for_tab(right_tab: str, quest_editor: object | None = None) -> SimpleNamespace:
    controller = SimpleNamespace(active=True, dock=make_dock_stub(right_tab=right_tab), quest_editor=quest_editor)
    return SimpleNamespace(width=1280, height=720, editor_controller=controller)


def _quest_path(tmp_path: Path, quests: list[dict[str, object]] | None = None) -> Path:
    path = tmp_path / "assets" / "data" / "quests.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "quests": quests
                if quests is not None
                else [
                    {
                        "id": "showcase_tour",
                        "title": "Tour of the Mesh",
                        "description": "Visit the demonstration rooms.",
                        "type": "tour",
                        "start_toast": "Tour started",
                        "complete_toast": "Tour complete",
                        "stages": [{"id": "intro", "title": "Talk", "text": "Talk to the guide."}],
                        "reward": {"inc_counters": {"developer_badge": 1}},
                        "requires_flags": ["intro_complete"],
                    },
                    {
                        "id": "test_quest",
                        "title": "Test Quest",
                        "steps": [],
                    },
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def _model(tmp_path: Path, quests: list[dict[str, object]] | None = None) -> QuestEditorModel:
    return QuestEditorModel.load(_quest_path(tmp_path, quests))


def _capture_panel_text(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    captured: list[str] = []
    monkeypatch.setattr(panel_primitives, "draw_panel_bg", lambda *args, **kwargs: None)
    monkeypatch.setattr(panel_primitives, "_draw_tb_rectangle_outline", lambda *args, **kwargs: None)
    monkeypatch.setattr(panel_primitives, "draw_text_cached", lambda text, *args, **kwargs: captured.append(str(text)))
    return captured


def test_quest_editor_overlay_constructs() -> None:
    overlay = QuestEditorOverlay(_window_for_tab("Quests"))

    assert overlay is not None


def test_quest_editor_overlay_uses_layout_primitives() -> None:
    source = QuestEditorOverlay.draw.__code__.co_names

    assert "EditorPanelBase" in source
    assert "PanelRow" in source
    assert "PanelField" in source
    assert "PanelHeader" in source


def test_quest_editor_overlay_hides_when_right_tab_is_not_quests(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = QuestEditorOverlay(_window_for_tab("Prefabs"))
    overlay._model = _model(tmp_path)

    overlay.draw()

    assert captured == []


def test_quest_editor_overlay_renders_selected_quest_fields(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = QuestEditorOverlay(_window_for_tab("Quests"))
    overlay._model = _model(tmp_path)

    overlay.draw()

    assert "Quests" in captured
    assert "Tour of the Mesh" in captured
    assert "showcase_tour" in captured
    assert "Test Quest" in captured
    assert "test_quest" in captured
    assert "ID" in captured
    assert "Title" in captured
    assert "Description" in captured
    assert "Visit the demonstration rooms." in captured
    assert "Type" in captured
    assert "tour" in captured
    assert "Start toast" in captured
    assert "Complete toast" in captured


def test_quest_editor_overlay_tracks_row_hits_and_selection(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _capture_panel_text(monkeypatch)
    overlay = QuestEditorOverlay(_window_for_tab("Quests"))
    overlay._model = _model(tmp_path)

    overlay.draw()

    assert len(overlay._row_hits) == 2
    second_row = overlay._row_hits[1][1]
    rect = second_row.last_rect
    assert rect is not None
    assert overlay.row_index_at(rect.left + 1.0, rect.center_y) == 1
    assert overlay.row_index_at(rect.right + 100.0, rect.top + 100.0) is None

    assert overlay.set_selected_index(1) is True
    assert overlay.set_selected_index(1) is False


def test_quest_editor_overlay_renders_complex_field_section(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = QuestEditorOverlay(_window_for_tab("Quests"))
    overlay._model = _model(tmp_path)

    overlay.draw()

    assert "Complex fields (read-only)" in captured
    assert "Stages" in captured
    assert any("Talk to the guide" in text for text in captured)
    assert "Reward" in captured
    assert '{"inc_counters":{"developer_badge":1}}' in captured
    assert "Requires flags" in captured
    assert "intro_complete" in captured


def test_quest_editor_overlay_renders_stage_rows_after_stages_blob(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = QuestEditorOverlay(_window_for_tab("Quests"))
    overlay._model = _model(tmp_path)

    overlay.draw()

    stages_index = captured.index("Stages")
    assert "Talk to the guide" in captured[stages_index + 1]
    assert captured[stages_index + 2] == "intro"
    assert captured[stages_index + 3] == "Talk"


def test_quest_editor_overlay_preserves_multi_stage_row_order(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = QuestEditorOverlay(_window_for_tab("Quests"))
    overlay._model = _model(
        tmp_path,
        [
            {
                "id": "multi_stage",
                "title": "Multi Stage",
                "stages": [
                    {"id": "alpha", "title": "First", "text": "First text."},
                    {"id": "beta", "title": "Second", "text": "Second text."},
                ],
            }
        ],
    )

    overlay.draw()

    alpha_index = captured.index("alpha")
    beta_index = captured.index("beta")
    assert captured[alpha_index + 1] == "First"
    assert captured[beta_index + 1] == "Second"
    assert alpha_index < beta_index


def test_quest_editor_overlay_omits_stage_rows_when_stages_missing_or_empty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = QuestEditorOverlay(_window_for_tab("Quests"))

    for quest in (
        {"id": "missing_stages", "title": "Missing Stages", "reward": {"inc_counters": {"gold": 1}}},
        {"id": "empty_stages", "title": "Empty Stages", "stages": [], "reward": {"inc_counters": {"gold": 1}}},
    ):
        captured.clear()
        overlay._model = _model(tmp_path, [quest])

        overlay.draw()

        assert "Complex fields (read-only)" in captured
        assert "Reward" in captured
        assert "Stages" not in captured
        assert "stage_0" not in captured


def test_quest_editor_overlay_stage_id_at_returns_raw_stage_id() -> None:
    overlay = QuestEditorOverlay(_window_for_tab("Quests"))
    hit_row = SimpleNamespace(hit_test=lambda x, y: x == 10.0 and y == 20.0)
    overlay._stage_row_hits = [("raw_stage", hit_row)]

    assert overlay.stage_id_at(10.0, 20.0) == "raw_stage"
    assert overlay.stage_id_at(1.0, 2.0) is None


def test_quest_editor_overlay_selects_stage_row_without_mutating_quest_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _capture_panel_text(monkeypatch)
    overlay = QuestEditorOverlay(_window_for_tab("Quests"))
    overlay._model = _model(
        tmp_path,
        [
            {
                "id": "multi_stage",
                "title": "Multi Stage",
                "stages": [
                    {"id": "alpha", "title": "First", "text": "First text."},
                    {"id": "beta", "title": "Second", "text": "Second text."},
                ],
            }
        ],
    )
    overlay.draw()
    overlay.set_selected_stage_id("beta")

    overlay.draw()

    assert [index for index, _row in overlay._row_hits] == [0]
    selected_stages = [stage_id for stage_id, row in overlay._stage_row_hits if row.is_selected]
    assert selected_stages == ["beta"]


def test_quest_editor_overlay_renders_selected_stage_detail(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = QuestEditorOverlay(_window_for_tab("Quests"))
    overlay._model = _model(tmp_path)

    overlay.draw()

    selected_index = captured.index("Selected stage")
    assert captured[selected_index + 1] == "intro"
    assert captured[selected_index + 2 : selected_index + 8] == [
        "ID",
        "intro",
        "Title",
        "Talk",
        "Text",
        "Talk to the guide.",
    ]


def test_quest_editor_overlay_resets_selected_stage_when_quest_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _capture_panel_text(monkeypatch)
    overlay = QuestEditorOverlay(_window_for_tab("Quests"))
    overlay._model = _model(
        tmp_path,
        [
            {
                "id": "quest_a",
                "title": "Quest A",
                "stages": [
                    {"id": "a1", "title": "A1", "text": "A1 text."},
                    {"id": "a2", "title": "A2", "text": "A2 text."},
                ],
            },
            {
                "id": "quest_b",
                "title": "Quest B",
                "stages": [{"id": "b1", "title": "B1", "text": "B1 text."}],
            },
        ],
    )

    overlay.draw()
    overlay.set_selected_stage_id("a2")
    assert overlay.set_selected_index(1) is True
    overlay.draw()

    assert overlay._selected_stage_id == "b1"
    assert overlay._selected_quest_id_for_stage == "quest_b"


def test_quest_editor_overlay_omits_selected_stage_when_stages_missing_or_empty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = QuestEditorOverlay(_window_for_tab("Quests"))

    for quest in (
        {"id": "missing_stages", "title": "Missing Stages", "reward": {"inc_counters": {"gold": 1}}},
        {"id": "empty_stages", "title": "Empty Stages", "stages": [], "reward": {"inc_counters": {"gold": 1}}},
    ):
        captured.clear()
        overlay._model = _model(tmp_path, [quest])
        overlay.set_selected_stage_id("stale")

        overlay.draw()

        assert overlay._selected_stage_id is None
        assert "Selected stage" not in captured


def test_quest_editor_overlay_view_mode_shows_edit_button(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured = _capture_panel_text(monkeypatch)
    quest_editor = _QuestEditorStub(edit_mode=False)
    overlay = QuestEditorOverlay(_window_for_tab("Quests", quest_editor))
    overlay._model = _model(tmp_path)

    overlay.draw()

    assert "Edit" in captured
    assert "Save" not in captured
    assert "Cancel" not in captured
    assert "edit" in quest_editor.button_rects


def test_quest_editor_overlay_edit_mode_shows_save_cancel_and_scalar_widgets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    quest_editor = _QuestEditorStub(edit_mode=True)
    overlay = QuestEditorOverlay(_window_for_tab("Quests", quest_editor))
    overlay._model = _model(tmp_path)

    overlay.draw()

    assert "Save" in captured
    assert "Cancel" in captured
    assert "Edit" not in captured
    assert {"id", "title", "description", "type", "start_toast", "complete_toast"} <= set(overlay._widget_rows)
    assert {"save", "cancel"} <= set(quest_editor.button_rects)
    assert "Complex fields (read-only)" in captured


def test_quest_editor_overlay_edit_mode_stage_title_text_widgets_respect_selected_stage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _capture_panel_text(monkeypatch)
    quest_editor = _QuestEditorStub(edit_mode=True)
    quest_editor.edit_buffer["stages"] = [
        {"id": "alpha", "title": "First", "text": "First text."},
        {"id": "beta", "title": "Second"},
    ]
    quest_editor._text_inputs["stages.1.title"] = TextInput(text="Second", focused=False, font_size=12, height=18.0)
    overlay = QuestEditorOverlay(_window_for_tab("Quests", quest_editor))
    overlay._model = _model(
        tmp_path,
        [
            {
                "id": "multi_stage",
                "title": "Multi Stage",
                "stages": [
                    {"id": "alpha", "title": "First", "text": "First text."},
                    {"id": "beta", "title": "Second"},
                ],
            }
        ],
    )
    overlay.draw()
    overlay.set_selected_stage_id("beta")

    overlay.draw()

    assert "ID" not in overlay._widget_rows
    assert "stages.1.title" in overlay._widget_rows
    assert "stages.1.text" not in overlay._widget_rows
    assert {"id", "title", "description", "type", "start_toast", "complete_toast"} <= set(overlay._widget_rows)


def test_quest_editor_overlay_selected_stage_id_is_widget_only_in_edit_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    quest_editor = _QuestEditorStub(edit_mode=True)
    quest_editor.edit_buffer["stages"] = [{"id": "intro", "title": "Talk", "text": "Talk to the guide."}]
    quest_editor._text_inputs["stages.0.id"] = TextInput(text="intro", focused=False, font_size=12, height=18.0)
    quest_editor._text_inputs["stages.0.title"] = TextInput(text="Talk", focused=False, font_size=12, height=18.0)
    quest_editor._text_inputs["stages.0.text"] = TextInput(text="Talk to the guide.", focused=False, font_size=12, height=18.0)
    overlay = QuestEditorOverlay(_window_for_tab("Quests", quest_editor))
    overlay._model = _model(tmp_path)

    overlay.draw()

    assert "stages.0.id" in overlay._widget_rows
    selected_index = captured.index("Selected stage")
    assert captured[selected_index + 1] == "intro"
    assert captured[selected_index + 2 : selected_index + 7 : 2] == ["ID", "Title", "Text"]

    captured.clear()
    view_overlay = QuestEditorOverlay(_window_for_tab("Quests"))
    view_overlay._model = _model(tmp_path)
    view_overlay.draw()

    assert "stages.0.id" not in view_overlay._widget_rows
    selected_index = captured.index("Selected stage")
    assert captured[selected_index + 1 : selected_index + 6] == ["intro", "ID", "intro", "Title", "Talk"]


def test_quest_editor_overlay_edit_mode_stage_add_action_row_hit_tests(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    quest_editor = _QuestEditorStub(edit_mode=True)
    overlay = QuestEditorOverlay(_window_for_tab("Quests", quest_editor))
    overlay._model = _model(tmp_path)

    overlay.draw()

    assert "Add stage" in captured
    add_row = dict(overlay._stage_action_hits)["stage.add"]
    rect = add_row.last_rect
    assert rect is not None
    assert overlay.stage_action_at(rect.left + 1.0, rect.center_y) == "stage.add"
    assert overlay.stage_action_at(rect.right + 100.0, rect.top + 100.0) is None


def test_quest_editor_overlay_edit_mode_delete_stage_action_requires_selection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    quest_editor = _QuestEditorStub(edit_mode=True)
    overlay = QuestEditorOverlay(_window_for_tab("Quests", quest_editor))
    overlay._model = _model(tmp_path)

    overlay.draw()

    assert "Delete stage" in captured
    assert [action for action, _row in overlay._stage_action_hits] == ["stage.add", "stage.delete"]

    captured.clear()
    overlay._model = _model(tmp_path, [{"id": "empty", "title": "Empty", "stages": []}])
    overlay.draw()

    assert "Add stage" in captured
    assert "Delete stage" not in captured
    assert [action for action, _row in overlay._stage_action_hits] == ["stage.add"]


def test_quest_editor_overlay_edit_mode_move_stage_actions_are_boundary_gated(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _capture_panel_text(monkeypatch)
    quest_editor = _QuestEditorStub(edit_mode=True)
    overlay = QuestEditorOverlay(_window_for_tab("Quests", quest_editor))
    overlay._model = _model(
        tmp_path,
        [
            {
                "id": "multi_stage",
                "title": "Multi Stage",
                "stages": [
                    {"id": "alpha", "title": "First"},
                    {"id": "beta", "title": "Second"},
                    {"id": "gamma", "title": "Third"},
                ],
            }
        ],
    )

    overlay.set_selected_stage_id("alpha")
    overlay.draw()
    assert [action for action, _row in overlay._stage_action_hits] == [
        "stage.add",
        "stage.move_down",
        "stage.delete",
    ]

    overlay.set_selected_stage_id("beta")
    overlay.draw()
    assert [action for action, _row in overlay._stage_action_hits] == [
        "stage.add",
        "stage.move_up",
        "stage.move_down",
        "stage.delete",
    ]

    overlay.set_selected_stage_id("gamma")
    overlay.draw()
    assert [action for action, _row in overlay._stage_action_hits] == [
        "stage.add",
        "stage.move_up",
        "stage.delete",
    ]

    overlay._model = _model(tmp_path, [{"id": "single", "title": "Single", "stages": [{"id": "only", "title": "Only"}]}])
    overlay.set_selected_stage_id("only")
    overlay.draw()
    assert [action for action, _row in overlay._stage_action_hits] == ["stage.add", "stage.delete"]


def test_quest_editor_overlay_stage_actions_do_not_pollute_stage_row_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _capture_panel_text(monkeypatch)
    quest_editor = _QuestEditorStub(edit_mode=True)
    overlay = QuestEditorOverlay(_window_for_tab("Quests", quest_editor))
    overlay._model = _model(tmp_path)

    overlay.draw()

    assert [stage_id for stage_id, _row in overlay._stage_row_hits] == ["intro"]
    assert [action for action, _row in overlay._stage_action_hits] == ["stage.add", "stage.delete"]
    add_row = dict(overlay._stage_action_hits)["stage.add"]
    rect = add_row.last_rect
    assert rect is not None
    assert overlay.stage_id_at(rect.left + 1.0, rect.center_y) is None


def test_quest_editor_overlay_edit_mode_shows_optional_fields_when_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _capture_panel_text(monkeypatch)
    quest_editor = _QuestEditorStub(edit_mode=True)
    quest_editor.edit_buffer = {"id": "minimal_quest", "title": "Minimal Quest"}
    overlay = QuestEditorOverlay(_window_for_tab("Quests", quest_editor))
    overlay._model = _model(tmp_path, [{"id": "minimal_quest", "title": "Minimal Quest"}])

    overlay.draw()

    assert {"id", "title", "description", "type", "start_toast", "complete_toast"} <= set(overlay._widget_rows)
    assert quest_editor.text_input("description").text == ""
    assert quest_editor.text_input("type").text == ""
    assert quest_editor.text_input("start_toast").text == ""
    assert quest_editor.text_input("complete_toast").text == ""


def test_quest_editor_overlay_syncs_scalar_widget_values_from_buffer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _capture_panel_text(monkeypatch)
    quest_editor = _QuestEditorStub(edit_mode=True)
    quest_editor.edit_buffer["title"] = "Changed Title"
    quest_editor.edit_buffer["type"] = ""
    overlay = QuestEditorOverlay(_window_for_tab("Quests", quest_editor))
    overlay._model = _model(tmp_path)

    overlay.draw()

    assert quest_editor.text_input("id").text == "showcase_tour"
    assert quest_editor.text_input("title").text == "Changed Title"
    assert quest_editor.text_input("type").text == ""


def test_quest_editor_overlay_dirty_marker_and_error_row(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured = _capture_panel_text(monkeypatch)
    quest_editor = _QuestEditorStub(edit_mode=True, dirty=True, error="title is required")
    overlay = QuestEditorOverlay(_window_for_tab("Quests", quest_editor))
    overlay._model = _model(tmp_path)

    overlay.draw()

    assert "Tour of the Mesh *" in captured
    assert "Error" in captured
    assert "title is required" in captured


def test_quest_editor_overlay_click_text_widget_returns_field_name(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _capture_panel_text(monkeypatch)
    quest_editor = _QuestEditorStub(edit_mode=True)
    overlay = QuestEditorOverlay(_window_for_tab("Quests", quest_editor))
    overlay._model = _model(tmp_path)
    overlay.draw()

    for field in ("id", "title", "description", "type", "start_toast", "complete_toast"):
        row = overlay._widget_rows[field]
        rect = row.last_rect
        assert rect is not None

        assert overlay.try_click_widget(rect.left + 100.0, rect.center_y) == field


def test_quest_editor_overlay_documents_read_only_complex_fields() -> None:
    assert QUEST_EDITOR_READ_ONLY_COMPLEX_FIELDS == frozenset(
        {"stages", "steps", "reward", "requires_flags", "blocks_flags"}
    )


def test_quest_editor_overlay_renders_empty_database(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = QuestEditorOverlay(_window_for_tab("Quests"))
    overlay._model = _model(tmp_path, [])

    overlay.draw()

    assert "No quests found" in captured
    assert "No quest" in captured


def test_quest_editor_overlay_renders_load_error(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_panel_text(monkeypatch)

    from engine.editor import quest_editor_model

    monkeypatch.setattr(
        quest_editor_model.QuestEditorModel,
        "load",
        classmethod(lambda cls: (_ for _ in ()).throw(FileNotFoundError("missing quests.json"))),
    )
    overlay = QuestEditorOverlay(_window_for_tab("Quests"))

    overlay.draw()

    assert "Unable to load quests" in captured
    assert "missing quests.json" in captured
