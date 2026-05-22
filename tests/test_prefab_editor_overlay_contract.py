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


def _capture_panel_text(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    captured: list[str] = []
    monkeypatch.setattr(panel_primitives, "draw_panel_bg", lambda *args, **kwargs: None)
    monkeypatch.setattr(panel_primitives, "_draw_lrtb_rectangle_outline", lambda *args, **kwargs: None)
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


def test_prefab_editor_overlay_edit_mode_shows_save_cancel_and_id_widget(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_panel_text(monkeypatch)
    prefab_editor = _PrefabEditorStub(edit_mode=True)
    overlay = PrefabEditorOverlay(_window_for_tab("Prefabs", prefab_editor))
    overlay._model = _model()

    overlay.draw()

    assert "Save" in captured
    assert "Cancel" in captured
    assert "Edit" not in captured
    assert "torch_wisp" in captured
    assert {"save", "cancel"} <= set(prefab_editor.button_rects)
    assert "Display name" in captured
    assert "Torch Wisp" in captured
    assert "Sprite" in captured
    assert "assets/placeholder.png" in captured
    assert "Encounter cost" in captured
    assert "2" in captured
    assert "Complex fields (read-only)" in captured


def test_prefab_editor_overlay_dirty_marker_and_error_row(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_panel_text(monkeypatch)
    prefab_editor = _PrefabEditorStub(edit_mode=True, dirty=True, error="id is required")
    overlay = PrefabEditorOverlay(_window_for_tab("Prefabs", prefab_editor))
    overlay._model = _model()

    overlay.draw()

    assert "Torch Wisp *" in captured
    assert "Error" in captured
    assert "id is required" in captured


def test_prefab_editor_overlay_click_text_widget_returns_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _capture_panel_text(monkeypatch)
    prefab_editor = _PrefabEditorStub(edit_mode=True)
    overlay = PrefabEditorOverlay(_window_for_tab("Prefabs", prefab_editor))
    overlay._model = _model()
    overlay.draw()

    row = overlay._widget_rows["id"]
    rect = row.last_rect
    assert rect is not None

    assert overlay.try_click_widget(rect.left + 100.0, rect.center_y) == "id"


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
