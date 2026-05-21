from __future__ import annotations

from types import SimpleNamespace

import pytest

import engine.editor.widgets.panel_primitives as panel_primitives
from engine.inventory import ItemDefinition
from engine.editor.item_editor_model import ItemEditorModel
from engine.ui_overlays.item_editor_overlay import ItemEditorOverlay
from tests._dock_stub import make_dock_stub

pytestmark = [pytest.mark.fast]


def _window_for_tab(right_tab: str) -> SimpleNamespace:
    controller = SimpleNamespace(active=True, dock=make_dock_stub(right_tab=right_tab))
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
