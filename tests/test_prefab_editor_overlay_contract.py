from __future__ import annotations

from types import SimpleNamespace

import pytest

import engine.editor.widgets.panel_primitives as panel_primitives
from engine.editor.prefab_editor_model import PrefabEditorModel
from engine.ui_overlays.prefab_editor_overlay import (
    PREFAB_EDITOR_READ_ONLY_COMPLEX_FIELDS,
    PrefabEditorOverlay,
)
from engine.ui_overlays.widgets import TextInput
from tests._dock_stub import make_dock_stub

pytestmark = [pytest.mark.fast]


class _FakePrefabManager:
    def __init__(self, prefabs: dict[str, dict[str, object]]) -> None:
        self.prefabs = prefabs

    def load(self, *, force: bool = False) -> None:  # noqa: ARG002
        return


class _PrefabEditorStub:
    def __init__(self, *, edit_mode: bool = False, dirty: bool = False, error: str | None = None) -> None:
        self._edit_mode = edit_mode
        self._dirty = dirty
        self._error = error
        self.edit_buffer = {
            "id": "torch_wisp",
            "display_name": "Torch Wisp",
            "entity": {"sprite": "assets/placeholder.png", "encounter_cost": 2},
            "tags": ["enemy", "fire"],
        }
        self._focused_field = "id" if edit_mode else None
        self._text_inputs = {
            "id": TextInput(text="torch_wisp", focused=edit_mode, font_size=12, height=18.0),
            "display_name": TextInput(text="Torch Wisp", focused=False, font_size=12, height=18.0),
            "entity.sprite": TextInput(text="assets/placeholder.png", focused=False, font_size=12, height=18.0),
            "entity.encounter_cost": TextInput(text="2", focused=False, font_size=12, height=18.0),
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


def _window_for_tab(right_tab: str, prefab_editor: object | None = None) -> SimpleNamespace:
    controller = SimpleNamespace(active=True, dock=make_dock_stub(right_tab=right_tab), prefab_editor=prefab_editor)
    return SimpleNamespace(width=1280, height=720, editor_controller=controller)


def _model() -> PrefabEditorModel:
    return PrefabEditorModel.load(
        _FakePrefabManager(
            {
                "torch_wisp": {
                    "id": "torch_wisp",
                    "display_name": "Torch Wisp",
                    "entity": {
                        "sprite": "assets/placeholder.png",
                        "behaviours": ["EnemyAI"],
                        "behaviour_config": {"Health": {"max": 8}},
                        "encounter_cost": 2,
                    },
                    "metadata": {"author": "core"},
                    "tags": ["enemy", "fire"],
                },
                "controller": {
                    "id": "controller",
                    "display_name": "Controller",
                    "entity": {"sprite": None, "behaviours": ["ActionListRunner"]},
                    "tags": ["controller"],
                },
            }
        )
    )


def _complex_prefab() -> dict[str, object]:
    return {
        "id": "complex",
        "display_name": "Complex",
        "entity": {
            "sprite": "assets/placeholder.png",
            "behaviours": ["EnemyAI", "Health"],
            "behaviour_config": {
                "Health": {"max": 8},
                "EnemyAI": {"speed": 1.5},
            },
            "require_flags": ["entity_ready"],
        },
        "metadata": {"zeta": "last", "author": "core"},
        "tags": ["enemy", "fire"],
        "require_flags": ["flag_a", "flag_b"],
        "forbid_flags": ["flag_c"],
    }


def _complex_model() -> PrefabEditorModel:
    return PrefabEditorModel.load(
        _FakePrefabManager(
            {
                "complex": _complex_prefab()
            }
        )
    )


def _capture_panel_text(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    captured: list[str] = []
    monkeypatch.setattr(panel_primitives, "draw_panel_bg", lambda *args, **kwargs: None)
    monkeypatch.setattr(panel_primitives, "_draw_tb_rectangle_outline", lambda *args, **kwargs: None)
    monkeypatch.setattr(panel_primitives, "draw_text_cached", lambda text, *args, **kwargs: captured.append(str(text)))
    return captured


def test_prefab_editor_overlay_constructs() -> None:
    overlay = PrefabEditorOverlay(_window_for_tab("Prefabs"))

    assert overlay is not None


def test_prefab_editor_overlay_uses_layout_primitives() -> None:
    source = PrefabEditorOverlay.draw.__code__.co_names

    assert "EditorPanelBase" in source
    assert "PanelRow" in source
    assert "PanelField" in source
    assert "PanelHeader" in source


def test_prefab_editor_overlay_hides_when_right_tab_is_not_prefabs(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = PrefabEditorOverlay(_window_for_tab("Items"))
    overlay._model = _model()

    overlay.draw()

    assert captured == []


def test_prefab_editor_overlay_renders_selected_prefab_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = PrefabEditorOverlay(_window_for_tab("Prefabs"))
    overlay._model = _model()

    overlay.draw()

    assert "Prefabs" in captured
    assert "Torch Wisp" in captured
    assert "torch_wisp" in captured
    assert "Controller" in captured
    assert "controller" in captured
    assert "ID" in captured
    assert "Display name" in captured
    assert "Sprite" in captured
    assert "assets/placeholder.png" in captured
    assert "Encounter cost" in captured
    assert "2" in captured


def test_prefab_editor_overlay_tracks_row_hits_and_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    _capture_panel_text(monkeypatch)
    overlay = PrefabEditorOverlay(_window_for_tab("Prefabs"))
    overlay._model = _model()

    overlay.draw()

    assert len(overlay._row_hits) == 2
    second_row = overlay._row_hits[1][1]
    rect = second_row.last_rect
    assert rect is not None
    assert overlay.row_index_at(rect.left + 1.0, rect.center_y) == 1
    assert overlay.row_index_at(rect.right + 100.0, rect.top + 100.0) is None

    assert overlay.set_selected_index(1) is True
    assert overlay.set_selected_index(1) is False


def test_prefab_editor_overlay_renders_complex_field_section(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = PrefabEditorOverlay(_window_for_tab("Prefabs"))
    overlay._model = _model()

    overlay.draw()

    assert "Complex fields (read-only)" in captured
    assert "Tags" in captured
    assert "enemy, fire" in captured
    assert "Behaviours" in captured
    assert "EnemyAI" in captured
    assert "Behaviour config" in captured
    assert '{"Health":{"max":8}}' in captured
    assert "Metadata" in captured
    assert '{"author":"core"}' in captured


def test_prefab_editor_overlay_renders_list_entry_rows_after_their_blobs(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = PrefabEditorOverlay(_window_for_tab("Prefabs"))
    overlay._model = _complex_model()

    overlay.draw()

    tags_index = captured.index("Tags")
    assert captured[tags_index : tags_index + 6] == [
        "Tags",
        "enemy, fire",
        "Tag 0",
        "enemy",
        "Tag 1",
        "fire",
    ]
    require_index = captured.index("Require flags")
    assert captured[require_index : require_index + 6] == [
        "Require flags",
        "flag_a, flag_b",
        "Require flag 0",
        "flag_a",
        "Require flag 1",
        "flag_b",
    ]
    forbid_index = captured.index("Forbid flags")
    assert captured[forbid_index : forbid_index + 4] == ["Forbid flags", "flag_c", "Forbid flag 0", "flag_c"]
    behaviour_index = captured.index("Behaviours")
    assert captured[behaviour_index : behaviour_index + 6] == [
        "Behaviours",
        "EnemyAI, Health",
        "Behaviour 0",
        "EnemyAI",
        "Behaviour 1",
        "Health",
    ]
    entity_require_index = captured.index("Entity require flags")
    assert captured[entity_require_index : entity_require_index + 4] == [
        "Entity require flags",
        "entity_ready",
        "Entity require flag 0",
        "entity_ready",
    ]


def test_prefab_editor_overlay_renders_metadata_rows_sorted_after_blob(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = PrefabEditorOverlay(_window_for_tab("Prefabs"))
    overlay._model = _complex_model()

    overlay.draw()

    metadata_index = captured.index("Metadata")
    assert captured[metadata_index : metadata_index + 6] == [
        "Metadata",
        '{"author":"core","zeta":"last"}',
        "author",
        "core",
        "zeta",
        "last",
    ]


def test_prefab_editor_overlay_renders_behaviour_config_rows_after_blob(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = PrefabEditorOverlay(_window_for_tab("Prefabs"))
    overlay._model = _complex_model()

    overlay.draw()

    config_index = captured.index("Behaviour config")
    assert captured[config_index : config_index + 6] == [
        "Behaviour config",
        '{"EnemyAI":{"speed":1.5},"Health":{"max":8}}',
        "EnemyAI",
        '{"speed":1.5}',
        "Health",
        '{"max":8}',
    ]


def test_prefab_editor_overlay_edit_mode_keeps_complex_rows_read_only_and_scalar_widgets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    prefab_editor = _PrefabEditorStub(edit_mode=True)
    prefab_editor.edit_buffer = _complex_prefab()
    overlay = PrefabEditorOverlay(_window_for_tab("Prefabs", prefab_editor))
    overlay._model = _complex_model()

    overlay.draw()

    assert {"id", "display_name", "entity.sprite", "entity.encounter_cost"} <= set(overlay._widget_rows)
    assert "Tag 0" in captured
    assert "Behaviour 0" in captured
    assert "author" in captured
    assert "Health" in captured
    assert {
        "tags.0",
        "tags.1",
        "require_flags.0",
        "require_flags.1",
        "forbid_flags.0",
        "entity.behaviours.0",
        "entity.behaviours.1",
        "entity.require_flags.0",
    } <= set(overlay._widget_rows)
    assert {"metadata.author", "metadata.zeta"} <= set(overlay._widget_rows)
    assert not any(field.startswith("entity.behaviour_config.") for field in overlay._widget_rows)


def test_prefab_editor_overlay_complex_rows_are_read_only_and_do_not_mutate_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _capture_panel_text(monkeypatch)
    model = _complex_model()
    before = model.prefabs()
    overlay = PrefabEditorOverlay(_window_for_tab("Prefabs"))
    overlay._model = model

    overlay.draw()

    assert model.prefabs() == before


def test_prefab_editor_overlay_edit_mode_renders_list_delete_actions_and_hits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    prefab_editor = _PrefabEditorStub(edit_mode=True)
    prefab_editor.edit_buffer = _complex_prefab()
    overlay = PrefabEditorOverlay(_window_for_tab("Prefabs", prefab_editor))
    overlay._model = _complex_model()

    overlay.draw()

    assert "Delete tag 0" in captured
    assert "Delete require flag 0" in captured
    assert "Delete forbid flag 0" in captured
    assert "Delete behaviour 0" in captured
    assert "Delete entity require flag 0" in captured
    actions = {action for action, _row in overlay._complex_entry_action_hits}
    assert {
        "tags#0#delete",
        "require_flags#0#delete",
        "forbid_flags#0#delete",
        "entity.behaviours#0#delete",
        "entity.require_flags#0#delete",
    } <= actions

    hit_rows = dict(overlay._complex_entry_action_hits)
    row = hit_rows["entity.behaviours#1#delete"]
    rect = row.last_rect
    assert rect is not None
    assert overlay.complex_entry_action_at(rect.left + 1.0, rect.center_y) == "entity.behaviours#1#delete"
    assert overlay.complex_entry_action_at(-10.0, -10.0) is None


def test_prefab_editor_overlay_edit_mode_renders_list_add_actions_and_hits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    prefab_editor = _PrefabEditorStub(edit_mode=True)
    prefab_editor.edit_buffer = _complex_prefab()
    overlay = PrefabEditorOverlay(_window_for_tab("Prefabs", prefab_editor))
    overlay._model = _complex_model()

    overlay.draw()

    assert "Add tag" in captured
    assert "Add require flag" in captured
    assert "Add forbid flag" in captured
    assert "Add behaviour" in captured
    assert "Add entity require flag" in captured
    actions = {action for action, _row in overlay._complex_entry_action_hits}
    assert {
        "tags#add",
        "require_flags#add",
        "forbid_flags#add",
        "entity.behaviours#add",
        "entity.require_flags#add",
    } <= actions

    hit_rows = dict(overlay._complex_entry_action_hits)
    row = hit_rows["entity.behaviours#add"]
    rect = row.last_rect
    assert rect is not None
    assert overlay.complex_entry_action_at(rect.left + 1.0, rect.center_y) == "entity.behaviours#add"


def test_prefab_editor_overlay_edit_mode_renders_behaviour_move_actions_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    prefab_editor = _PrefabEditorStub(edit_mode=True)
    prefab_editor.edit_buffer = _complex_prefab()
    overlay = PrefabEditorOverlay(_window_for_tab("Prefabs", prefab_editor))
    overlay._model = _complex_model()

    overlay.draw()

    assert "Move up behaviour 0" not in captured
    assert "Move down behaviour 0" in captured
    assert "Move up behaviour 1" in captured
    assert "Move down behaviour 1" not in captured
    assert not any(text.startswith("Move up tag") or text.startswith("Move down tag") for text in captured)
    assert not any(text.startswith("Move up require flag") or text.startswith("Move down require flag") for text in captured)
    actions = {action for action, _row in overlay._complex_entry_action_hits}
    assert {
        "entity.behaviours#0#move_down",
        "entity.behaviours#1#move_up",
    } <= actions
    assert not any(action.startswith("tags#") and "#move_" in action for action in actions)
    assert not any(action.startswith("metadata#") and "#move_" in action for action in actions)

    hit_rows = dict(overlay._complex_entry_action_hits)
    row = hit_rows["entity.behaviours#1#move_up"]
    rect = row.last_rect
    assert rect is not None
    assert overlay.complex_entry_action_at(rect.left + 1.0, rect.center_y) == "entity.behaviours#1#move_up"

    captured.clear()
    prefab_editor.edit_buffer["entity"]["behaviours"] = ["Health"]
    overlay.draw()

    assert "Move up behaviour 0" not in captured
    assert "Move down behaviour 0" not in captured


def test_prefab_editor_overlay_view_mode_has_no_delete_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = PrefabEditorOverlay(_window_for_tab("Prefabs"))
    overlay._model = _complex_model()

    overlay.draw()

    assert not any(text.startswith("Delete ") for text in captured)
    assert overlay._complex_entry_action_hits == []
    assert overlay.complex_entry_action_at(0.0, 0.0) is None


def test_prefab_editor_overlay_dict_complex_rows_have_no_delete_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    prefab_editor = _PrefabEditorStub(edit_mode=True)
    prefab_editor.edit_buffer = _complex_prefab()
    overlay = PrefabEditorOverlay(_window_for_tab("Prefabs", prefab_editor))
    overlay._model = _complex_model()

    overlay.draw()

    assert "author" in captured
    assert "Health" in captured
    assert "Delete author" not in captured
    assert "Delete Health" not in captured
    assert "Add metadata" not in captured
    assert "Add behaviour config" not in captured
    actions = {action for action, _row in overlay._complex_entry_action_hits}
    assert not any(action.startswith("entity.behaviour_config#") for action in actions)


def test_prefab_editor_overlay_edit_mode_renders_metadata_delete_actions_and_hits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    prefab_editor = _PrefabEditorStub(edit_mode=True)
    prefab_editor.edit_buffer = _complex_prefab()
    overlay = PrefabEditorOverlay(_window_for_tab("Prefabs", prefab_editor))
    overlay._model = _complex_model()

    overlay.draw()

    assert "Delete metadata author" in captured
    assert "Delete metadata zeta" in captured
    actions = {action for action, _row in overlay._complex_entry_action_hits}
    assert {
        "metadata#author#delete",
        "metadata#zeta#delete",
    } <= actions

    hit_rows = dict(overlay._complex_entry_action_hits)
    row = hit_rows["metadata#author#delete"]
    rect = row.last_rect
    assert rect is not None
    assert overlay.complex_entry_action_at(rect.left + 1.0, rect.center_y) == "metadata#author#delete"


def test_prefab_editor_overlay_edit_mode_renders_metadata_value_widgets_with_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    prefab_editor = _PrefabEditorStub(edit_mode=True)
    prefab_editor.edit_buffer = _complex_prefab()
    overlay = PrefabEditorOverlay(_window_for_tab("Prefabs", prefab_editor))
    overlay._model = _complex_model()

    overlay.draw()

    assert {"metadata.author", "metadata.zeta"} <= set(overlay._widget_rows)
    assert "author" in captured
    assert "zeta" in captured
    actions = {action for action, _row in overlay._complex_entry_action_hits}
    assert {"metadata#author#delete", "metadata#zeta#delete"} <= actions


def test_prefab_editor_overlay_metadata_dotted_key_widget_and_behaviour_config_read_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    prefab_editor = _PrefabEditorStub(edit_mode=True)
    prefab_editor.edit_buffer = _complex_prefab()
    prefab_editor.edit_buffer["metadata"] = {"a.b": "literal"}
    overlay = PrefabEditorOverlay(_window_for_tab("Prefabs", prefab_editor))
    overlay._model = _complex_model()

    overlay.draw()

    assert "metadata.a.b" in overlay._widget_rows
    assert "a.b" in captured
    assert not any(field.startswith("entity.behaviour_config.") for field in overlay._widget_rows)
    assert "Health" in captured


def test_prefab_editor_overlay_dict_delete_is_metadata_only_and_edit_mode_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = PrefabEditorOverlay(_window_for_tab("Prefabs"))
    overlay._model = _complex_model()

    overlay.draw()

    assert "Delete metadata author" not in captured
    assert overlay._complex_entry_action_hits == []

    captured.clear()
    prefab_editor = _PrefabEditorStub(edit_mode=True)
    prefab_editor.edit_buffer = _complex_prefab()
    overlay = PrefabEditorOverlay(_window_for_tab("Prefabs", prefab_editor))
    overlay._model = _complex_model()

    overlay.draw()

    actions = {action for action, _row in overlay._complex_entry_action_hits}
    assert not any(action.startswith("entity.behaviour_config#") for action in actions)
    assert not any(action.startswith("tags#") and action.endswith("#delete") and not action.split("#")[1].isdigit() for action in actions)
    assert "Delete Health" not in captured


def test_prefab_editor_overlay_edit_mode_complex_rows_source_live_buffer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    prefab_editor = _PrefabEditorStub(edit_mode=True)
    prefab_editor.edit_buffer = _complex_prefab()
    prefab_editor.edit_buffer["tags"] = ["enemy"]
    prefab_editor.edit_buffer["entity"]["behaviours"] = ["Health"]
    overlay = PrefabEditorOverlay(_window_for_tab("Prefabs", prefab_editor))
    overlay._model = _complex_model()

    overlay.draw()

    tags_index = captured.index("Tags")
    assert captured[tags_index : tags_index + 4] == ["Tags", "enemy", "Tag 0", "enemy"]
    behaviour_index = captured.index("Behaviours")
    assert captured[behaviour_index : behaviour_index + 4] == ["Behaviours", "Health", "Behaviour 0", "Health"]
    assert "Tag 1" not in captured
    assert "EnemyAI, Health" not in captured


def test_prefab_editor_overlay_view_mode_shows_edit_button(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_panel_text(monkeypatch)
    prefab_editor = _PrefabEditorStub(edit_mode=False)
    overlay = PrefabEditorOverlay(_window_for_tab("Prefabs", prefab_editor))
    overlay._model = _model()

    overlay.draw()

    assert "Edit" in captured
    assert "Save" not in captured
    assert "Cancel" not in captured
    assert "edit" in prefab_editor.button_rects


def test_prefab_editor_overlay_edit_mode_shows_save_cancel_and_scalar_widgets(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_panel_text(monkeypatch)
    prefab_editor = _PrefabEditorStub(edit_mode=True)
    overlay = PrefabEditorOverlay(_window_for_tab("Prefabs", prefab_editor))
    overlay._model = _model()

    overlay.draw()

    assert "Save" in captured
    assert "Cancel" in captured
    assert "Edit" not in captured
    assert {"id", "display_name", "entity.sprite", "entity.encounter_cost"} <= set(overlay._widget_rows)
    assert {"save", "cancel"} <= set(prefab_editor.button_rects)
    assert "Complex fields (read-only)" in captured


def test_prefab_editor_overlay_edit_mode_shows_sprite_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _capture_panel_text(monkeypatch)
    prefab_editor = _PrefabEditorStub(edit_mode=True)
    prefab_editor.edit_buffer = {"id": "controller", "display_name": "Controller", "entity": {}}
    overlay = PrefabEditorOverlay(_window_for_tab("Prefabs", prefab_editor))
    overlay._model = _model()
    overlay._model.set_selected_index(1)

    overlay.draw()

    assert "entity.sprite" in overlay._widget_rows
    assert prefab_editor.text_input("entity.sprite").text == ""


def test_prefab_editor_overlay_edit_mode_shows_encounter_cost_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _capture_panel_text(monkeypatch)
    prefab_editor = _PrefabEditorStub(edit_mode=True)
    prefab_editor.edit_buffer = {"id": "controller", "display_name": "Controller", "entity": {}}
    overlay = PrefabEditorOverlay(_window_for_tab("Prefabs", prefab_editor))
    overlay._model = _model()
    overlay._model.set_selected_index(1)

    overlay.draw()

    assert "entity.encounter_cost" in overlay._widget_rows
    assert prefab_editor.text_input("entity.encounter_cost").text == ""


def test_prefab_editor_overlay_syncs_scalar_widget_values_from_nested_buffer(monkeypatch: pytest.MonkeyPatch) -> None:
    _capture_panel_text(monkeypatch)
    prefab_editor = _PrefabEditorStub(edit_mode=True)
    prefab_editor.edit_buffer["entity"]["sprite"] = "assets/changed.png"
    prefab_editor.edit_buffer["entity"]["encounter_cost"] = 9
    overlay = PrefabEditorOverlay(_window_for_tab("Prefabs", prefab_editor))
    overlay._model = _model()

    overlay.draw()

    assert prefab_editor.text_input("id").text == "torch_wisp"
    assert prefab_editor.text_input("display_name").text == "Torch Wisp"
    assert prefab_editor.text_input("entity.sprite").text == "assets/changed.png"
    assert prefab_editor.text_input("entity.encounter_cost").text == "9"


def test_prefab_editor_overlay_dirty_marker_and_error_row(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_panel_text(monkeypatch)
    prefab_editor = _PrefabEditorStub(edit_mode=True, dirty=True, error="id is required")
    overlay = PrefabEditorOverlay(_window_for_tab("Prefabs", prefab_editor))
    overlay._model = _model()

    overlay.draw()

    assert "Torch Wisp *" in captured
    assert "Error" in captured
    assert "id is required" in captured


def test_prefab_editor_overlay_click_text_widget_returns_field_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _capture_panel_text(monkeypatch)
    prefab_editor = _PrefabEditorStub(edit_mode=True)
    overlay = PrefabEditorOverlay(_window_for_tab("Prefabs", prefab_editor))
    overlay._model = _model()
    overlay.draw()

    for field_path in ("id", "display_name", "entity.sprite", "entity.encounter_cost"):
        row = overlay._widget_rows[field_path]
        rect = row.last_rect
        assert rect is not None

        assert overlay.try_click_widget(rect.left + 100.0, rect.center_y) == field_path


def test_prefab_editor_overlay_documents_read_only_complex_fields() -> None:
    assert PREFAB_EDITOR_READ_ONLY_COMPLEX_FIELDS == {
        "tags",
        "require_flags",
        "forbid_flags",
        "entity.behaviours",
        "entity.behaviour_config",
        "entity.require_flags",
        "metadata",
    }


def test_prefab_editor_overlay_renders_empty_database(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = PrefabEditorOverlay(_window_for_tab("Prefabs"))
    overlay._model = PrefabEditorModel.load(_FakePrefabManager({}))

    overlay.draw()

    assert "No prefabs found" in captured
    assert "No prefab" in captured


def test_prefab_editor_overlay_renders_load_error(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_panel_text(monkeypatch)

    from engine.editor import prefab_editor_model

    monkeypatch.setattr(
        prefab_editor_model.PrefabEditorModel,
        "load",
        classmethod(lambda cls: (_ for _ in ()).throw(FileNotFoundError("missing prefabs.json"))),
    )
    overlay = PrefabEditorOverlay(_window_for_tab("Prefabs"))

    overlay.draw()

    assert "Unable to load prefabs" in captured
    assert "missing prefabs.json" in captured
