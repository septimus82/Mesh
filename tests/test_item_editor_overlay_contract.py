from __future__ import annotations

from types import SimpleNamespace

import pytest

import engine.editor.widgets.panel_primitives as panel_primitives
from engine.inventory import ItemDefinition
from engine.editor.item_editor_model import ItemEditorModel
from engine.ui_overlays.item_editor_overlay import ItemEditorOverlay
from engine.ui_overlays.widgets import TextInput
from tests._dock_stub import make_dock_stub

pytestmark = [pytest.mark.fast]


class _ItemEditorStub:
    def __init__(self, *, edit_mode: bool = False, dirty: bool = False, error: str | None = None) -> None:
        self._edit_mode = edit_mode
        self._dirty = dirty
        self._error = error
        self._id_input = TextInput(text="healing_potion", focused=edit_mode, font_size=12, height=18.0)
        self.button_rects: dict[str, object] = {}

    def is_edit_mode_active(self) -> bool:
        return self._edit_mode

    def is_dirty(self) -> bool:
        return self._dirty

    def last_error_message(self) -> str | None:
        return self._error

    def id_input(self) -> TextInput:
        return self._id_input

    def set_button_rects(self, rects: dict[str, object]) -> None:
        self.button_rects = dict(rects)


def _window_for_tab(right_tab: str, item_editor: object | None = None) -> SimpleNamespace:
    controller = SimpleNamespace(active=True, dock=make_dock_stub(right_tab=right_tab), item_editor=item_editor)
    return SimpleNamespace(width=1280, height=720, editor_controller=controller)


def _model() -> ItemEditorModel:
    return ItemEditorModel(
        items=[
            ItemDefinition(
                id="healing_potion",
                name="Healing Potion",
                description="Restores HP.",
                icon="assets/items/healing_potion.png",
                stackable=True,
                max_stack=5,
                tags=["consumable", "potion"],
                effects={"heal": 25},
            ),
            ItemDefinition(
                id="iron_key",
                name="Iron Key",
                description="",
                icon=None,
                stackable=False,
                max_stack=1,
                tags=[],
                effects={},
            ),
        ]
    )


def _capture_panel_text(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    captured: list[str] = []
    monkeypatch.setattr(panel_primitives, "draw_panel_bg", lambda *args, **kwargs: None)
    monkeypatch.setattr(panel_primitives, "_draw_lrtb_rectangle_outline", lambda *args, **kwargs: None)
    monkeypatch.setattr(panel_primitives, "draw_text_cached", lambda text, *args, **kwargs: captured.append(str(text)))
    return captured


def test_item_editor_overlay_constructs() -> None:
    overlay = ItemEditorOverlay(_window_for_tab("Items"))

    assert overlay is not None


def test_item_editor_overlay_uses_layout_primitives() -> None:
    source = ItemEditorOverlay.draw.__code__.co_names

    assert "EditorPanelBase" in source
    assert "PanelRow" in source
    assert "PanelField" in source
    assert "PanelHeader" in source


def test_item_editor_overlay_hides_when_right_tab_is_not_items(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = ItemEditorOverlay(_window_for_tab("Inspector"))
    overlay._model = _model()

    overlay.draw()

    assert captured == []


def test_item_editor_overlay_renders_selected_item_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = ItemEditorOverlay(_window_for_tab("Items"))
    overlay._model = _model()

    overlay.draw()

    assert "Items" in captured
    assert "Healing Potion (healing_potion)" in captured
    assert "Iron Key (iron_key)" in captured
    assert "Healing Potion" in captured
    assert "healing_potion" in captured
    assert "Description" in captured
    assert "Restores HP." in captured
    assert "Stackable" in captured
    assert "true" in captured
    assert "Effects" in captured
    assert "heal=25" in captured


def test_item_editor_overlay_view_mode_shows_edit_button(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_panel_text(monkeypatch)
    item_editor = _ItemEditorStub(edit_mode=False)
    overlay = ItemEditorOverlay(_window_for_tab("Items", item_editor))
    overlay._model = _model()

    overlay.draw()

    assert "Edit" in captured
    assert "Save" not in captured
    assert "Cancel" not in captured
    assert "edit" in item_editor.button_rects


def test_item_editor_overlay_edit_mode_shows_save_cancel_and_id_input(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_panel_text(monkeypatch)
    item_editor = _ItemEditorStub(edit_mode=True)
    overlay = ItemEditorOverlay(_window_for_tab("Items", item_editor))
    overlay._model = _model()

    overlay.draw()

    assert "Save" in captured
    assert "Cancel" in captured
    assert "Edit" not in captured
    assert "healing_potion" in captured
    assert {"save", "cancel"} <= set(item_editor.button_rects)


def test_item_editor_overlay_dirty_marker_and_error_row(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_panel_text(monkeypatch)
    item_editor = _ItemEditorStub(edit_mode=True, dirty=True, error="id is required")
    overlay = ItemEditorOverlay(_window_for_tab("Items", item_editor))
    overlay._model = _model()

    overlay.draw()

    assert "Items *" in captured
    assert "Error" in captured
    assert "id is required" in captured


def test_item_editor_overlay_renders_empty_database(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = ItemEditorOverlay(_window_for_tab("Items"))
    overlay._model = ItemEditorModel(items=[])

    overlay.draw()

    assert "No items found" in captured
    assert "No item" in captured


def test_item_editor_overlay_renders_load_error(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_panel_text(monkeypatch)

    from engine.editor import item_editor_model

    monkeypatch.setattr(
        item_editor_model.ItemEditorModel,
        "load",
        classmethod(lambda cls: (_ for _ in ()).throw(FileNotFoundError("missing items.json"))),
    )
    overlay = ItemEditorOverlay(_window_for_tab("Items"))

    overlay.draw()

    assert "Unable to load items" in captured
    assert "missing items.json" in captured
