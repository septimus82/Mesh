from __future__ import annotations

from types import SimpleNamespace

import pytest

import engine.editor.widgets.panel_primitives as panel_primitives
from engine.editor.item_editor_model import ItemEditorModel
from engine.inventory import ItemDefinition
from engine.ui_overlays.item_editor_overlay import ItemEditorOverlay
from engine.ui_overlays.widgets import TextInput
from tests._dock_stub import make_dock_stub

pytestmark = [pytest.mark.fast]


class _ItemEditorStub:
    def __init__(self, *, edit_mode: bool = False, dirty: bool = False, error: str | None = None) -> None:
        self._edit_mode = edit_mode
        self._dirty = dirty
        self._error = error
        self.edit_buffer = {
            "id": "healing_potion",
            "name": "Healing Potion",
            "description": "Restores HP.",
            "icon": "assets/items/healing_potion.png",
            "stackable": True,
            "max_stack": 5,
            "tags": ["consumable", "potion"],
            "effects": {"heal": 25},
        }
        self._focused_field = "id" if edit_mode else None
        self._text_inputs = {
            "id": TextInput(text="healing_potion", focused=edit_mode, font_size=12, height=18.0),
            "name": TextInput(text="Healing Potion", focused=False, font_size=12, height=18.0),
            "description": TextInput(text="Restores HP.", focused=False, font_size=12, height=18.0),
            "icon": TextInput(text="assets/items/healing_potion.png", focused=False, font_size=12, height=18.0),
            "max_stack": TextInput(text="5", focused=False, font_size=12, height=18.0),
        }
        self.button_rects: dict[str, object] = {}

    def is_edit_mode_active(self) -> bool:
        return self._edit_mode

    def is_dirty(self) -> bool:
        return self._dirty

    def last_error_message(self) -> str | None:
        return self._error

    def id_input(self) -> TextInput:
        return self._text_inputs["id"]

    def text_input(self, field: str) -> TextInput:
        return self._text_inputs[field]

    def text_inputs(self) -> dict[str, TextInput]:
        return dict(self._text_inputs)

    def focused_field(self) -> str | None:
        return self._focused_field

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
    monkeypatch.setattr(panel_primitives, "_draw_tb_rectangle_outline", lambda *args, **kwargs: None)
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


def test_item_editor_model_set_selected_index_alias_selects_item() -> None:
    model = _model()

    assert model.set_selected_index(1) is True
    assert model.selected_index == 1
    assert model.selected_item is not None
    assert model.selected_item.id == "iron_key"

    assert model.set_selected_index(1) is False
    assert model.set_selected_index(999) is False
    assert model.selected_index == 1


def test_item_editor_overlay_tracks_row_hits_and_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    _capture_panel_text(monkeypatch)
    overlay = ItemEditorOverlay(_window_for_tab("Items"))
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


def test_item_editor_overlay_edit_mode_shows_save_cancel_and_scalar_widgets(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_panel_text(monkeypatch)
    item_editor = _ItemEditorStub(edit_mode=True)
    overlay = ItemEditorOverlay(_window_for_tab("Items", item_editor))
    overlay._model = _model()

    overlay.draw()

    assert "Save" in captured
    assert "Cancel" in captured
    assert "Edit" not in captured
    assert "healing_potion" in captured
    assert "Healing Potion" in captured
    assert "Restores HP." in captured
    assert "assets/items/healing_potion.png" in captured
    assert "5" in captured
    assert "[x] stackable" in captured
    assert {"save", "cancel"} <= set(item_editor.button_rects)
    assert "Tags" in captured
    assert "consumable, potion" in captured
    assert "Effects" in captured
    assert "heal=25" in captured


def test_item_editor_overlay_edit_mode_shows_stackable_toggle_when_false(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_panel_text(monkeypatch)
    item_editor = _ItemEditorStub(edit_mode=True)
    item_editor.edit_buffer["stackable"] = False
    overlay = ItemEditorOverlay(_window_for_tab("Items", item_editor))
    overlay._model = _model()
    overlay._model.select_index(1)

    overlay.draw()

    assert "stackable" in overlay._widget_rows
    assert "[ ] stackable" in captured


def test_item_editor_overlay_edit_mode_shows_max_stack_when_default(monkeypatch: pytest.MonkeyPatch) -> None:
    _capture_panel_text(monkeypatch)
    item_editor = _ItemEditorStub(edit_mode=True)
    item_editor.edit_buffer["max_stack"] = 1
    overlay = ItemEditorOverlay(_window_for_tab("Items", item_editor))
    overlay._model = _model()
    overlay._model.select_index(1)

    overlay.draw()

    assert "max_stack" in overlay._widget_rows
    assert item_editor.text_input("max_stack").text == "1"


def test_item_editor_overlay_renders_tag_rows_after_tags_blob(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = ItemEditorOverlay(_window_for_tab("Items"))
    overlay._model = _model()

    overlay.draw()

    tags_index = captured.index("Tags")
    assert captured[tags_index : tags_index + 6] == [
        "Tags",
        "consumable, potion",
        "Tag 0",
        "consumable",
        "Tag 1",
        "potion",
    ]


def test_item_editor_overlay_renders_effect_rows_after_effects_blob(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = ItemEditorOverlay(_window_for_tab("Items"))
    overlay._model = ItemEditorModel(
        items=[
            ItemDefinition(
                id="mixed_item",
                name="Mixed Item",
                description="",
                icon=None,
                stackable=False,
                max_stack=1,
                tags=[],
                effects={"quest_flag": "field_supplies_crate", "heal": 2.0, "tier": 1},
            )
        ]
    )

    overlay.draw()

    effects_index = captured.index("Effects")
    assert captured[effects_index : effects_index + 8] == [
        "Effects",
        "heal=2.0, quest_flag=field_supplies_crate, tier=1",
        "heal",
        "2.0",
        "quest_flag",
        "field_supplies_crate",
        "tier",
        "1",
    ]


def test_item_editor_overlay_edit_mode_renders_complex_entry_rows_read_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    item_editor = _ItemEditorStub(edit_mode=True)
    overlay = ItemEditorOverlay(_window_for_tab("Items", item_editor))
    overlay._model = _model()

    overlay.draw()

    tags_index = captured.index("Tags")
    effects_index = captured.index("Effects")
    assert captured[tags_index : tags_index + 6] == [
        "Tags",
        "consumable, potion",
        "Tag 0",
        "consumable",
        "Tag 1",
        "potion",
    ]
    assert captured[effects_index : effects_index + 4] == ["Effects", "heal=25", "heal", "25"]
    assert "tags" not in overlay._widget_rows
    assert "effects" not in overlay._widget_rows


def test_item_editor_overlay_complex_blob_rows_coexist_with_entry_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = ItemEditorOverlay(_window_for_tab("Items"))
    overlay._model = _model()

    overlay.draw()

    assert "Tags" in captured
    assert "consumable, potion" in captured
    assert "Tag 0" in captured
    assert "consumable" in captured
    assert "Effects" in captured
    assert "heal=25" in captured
    assert "heal" in captured
    assert captured.index("Tags") < captured.index("Tag 0")
    assert captured.index("Effects") < captured.index("heal")


def test_item_editor_overlay_dirty_marker_and_error_row(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_panel_text(monkeypatch)
    item_editor = _ItemEditorStub(edit_mode=True, dirty=True, error="id is required")
    overlay = ItemEditorOverlay(_window_for_tab("Items", item_editor))
    overlay._model = _model()

    overlay.draw()

    assert "Items *" in captured
    assert "Error" in captured
    assert "id is required" in captured


def test_item_editor_overlay_click_text_widget_returns_field(monkeypatch: pytest.MonkeyPatch) -> None:
    _capture_panel_text(monkeypatch)
    item_editor = _ItemEditorStub(edit_mode=True)
    overlay = ItemEditorOverlay(_window_for_tab("Items", item_editor))
    overlay._model = _model()
    overlay.draw()

    row = overlay._widget_rows["name"]
    rect = row.last_rect
    assert rect is not None

    assert overlay.try_click_widget(rect.left + 100.0, rect.center_y) == "name"


def test_item_editor_overlay_click_stackable_toggle_updates_buffer(monkeypatch: pytest.MonkeyPatch) -> None:
    _capture_panel_text(monkeypatch)
    item_editor = _ItemEditorStub(edit_mode=True)
    overlay = ItemEditorOverlay(_window_for_tab("Items", item_editor))
    overlay._model = _model()
    overlay.draw()

    row = overlay._widget_rows["stackable"]
    rect = row.last_rect
    assert rect is not None

    assert overlay.try_click_widget(rect.left + 100.0, rect.center_y) == "stackable"
    assert item_editor.edit_buffer["stackable"] is False


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
