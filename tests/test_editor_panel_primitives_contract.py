from __future__ import annotations

import pytest

from engine.editor.widgets import EditorPanelBase, PanelField, PanelHeader, PanelRow
from engine.ui.widgets import Rect

pytestmark = [pytest.mark.fast]


def test_editor_panel_base_instantiates_with_locked_defaults() -> None:
    panel = EditorPanelBase(Rect(10.0, 20.0, 200.0, 120.0), title="Inspector")

    assert panel.rect.left == 10.0
    assert panel.title == "Inspector"
    assert panel.inner_padding_x == 8.0
    assert panel.panel_bg == (18, 18, 22, 220)
    assert panel.panel_border == (100, 100, 110, 255)


def test_editor_panel_base_adds_rows_and_headers_in_order() -> None:
    panel = EditorPanelBase(Rect(0.0, 0.0, 240.0, 120.0))
    header = panel.add_header(PanelHeader("Transform"))
    row = panel.add_row(PanelRow(PanelField("X", "12.0")))

    assert panel.items == (header, row)


def test_editor_panel_base_layout_stacks_items_vertically() -> None:
    panel = EditorPanelBase(Rect(0.0, 0.0, 240.0, 100.0), item_spacing=4.0)
    header = panel.add_header(PanelHeader("Transform"))
    row = panel.add_row(PanelRow(PanelField("X", "12.0")))

    layout = panel.layout()

    assert [child.rect.height for child in layout.children] == [20.0, 24.0]
    assert header.layout(Rect(8.0, 72.0, 224.0, 20.0), padding_x=0.0).rect.top == 92.0
    assert row.last_rect == Rect(8.0, 44.0, 224.0, 24.0)


def test_editor_panel_base_hover_propagates_to_rows_only_after_layout() -> None:
    panel = EditorPanelBase(Rect(0.0, 0.0, 240.0, 100.0))
    row = panel.add_row(PanelRow(PanelField("Name", "Player")))
    panel.layout()

    panel.handle_hover(12.0, 84.0)

    assert row.is_hovered is True


def test_editor_panel_base_draw_is_safe_with_monkeypatched_draw_functions(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr("engine.editor.widgets.panel_primitives.draw_panel_bg", lambda *args, **kwargs: calls.append("bg"))
    monkeypatch.setattr(
        "engine.editor.widgets.panel_primitives._draw_tb_rectangle_outline",
        lambda *args, **kwargs: calls.append("border"),
    )
    monkeypatch.setattr("engine.editor.widgets.panel_primitives.draw_text_cached", lambda *args, **kwargs: calls.append("text"))

    panel = EditorPanelBase(Rect(0.0, 0.0, 200.0, 80.0), title="Panel")
    panel.add_row(PanelRow(PanelField("Label", "Value")))

    panel.draw()

    assert "bg" in calls
    assert "border" in calls
    assert "text" in calls


def test_panel_row_default_height_and_padding_are_locked() -> None:
    row = PanelRow(PanelField("Name"))

    assert row.preferred_height() == 24.0
    assert row.padding_x == 8.0


def test_panel_row_hover_state_updates_and_emits_hover_background() -> None:
    row = PanelRow(PanelField("Name"))

    row.set_hovered(True)
    layout = row.layout(Rect(0.0, 0.0, 120.0, 24.0))

    assert row.is_hovered is True
    assert layout.instructions[0].kind == "panel_row_bg"
    assert layout.instructions[0].payload["color"] == (90, 140, 200, 70)


def test_panel_row_selection_state_updates_and_selected_wins_over_hover() -> None:
    row = PanelRow(PanelField("Name"))

    row.set_hovered(True)
    row.set_selected(True)
    layout = row.layout(Rect(0.0, 0.0, 120.0, 24.0))

    assert row.is_selected is True
    assert row.background_color() == (90, 140, 200, 140)
    assert layout.instructions[0].payload["selected"] is True


def test_panel_field_label_only_layout_omits_value_instruction() -> None:
    field = PanelField("Visible")

    layout = field.layout(Rect(0.0, 0.0, 120.0, 24.0))

    assert [instruction.kind for instruction in layout.instructions] == ["panel_field_label"]
    assert layout.instructions[0].payload["font_size"] == 11


def test_panel_field_label_and_value_layout_right_aligns_value() -> None:
    field = PanelField("X", "12.0")

    layout = field.layout(Rect(0.0, 0.0, 120.0, 24.0))

    value = layout.instructions[1]
    assert value.kind == "panel_field_value"
    assert value.payload["text"] == "12.0"
    assert value.payload["anchor_x"] == "right"
    assert value.payload["font_size"] == 10


def test_panel_field_click_invokes_callback_once() -> None:
    calls: list[str] = []
    field = PanelField("Apply", on_click=lambda: calls.append("clicked"))

    assert field.click() is True
    assert calls == ["clicked"]


def test_panel_header_title_only_layout_is_decorative() -> None:
    header = PanelHeader("Transform")

    layout = header.layout(Rect(0.0, 0.0, 120.0, 20.0))

    assert header.preferred_height() == 20.0
    assert [instruction.kind for instruction in layout.instructions] == ["panel_header_title"]
    assert not hasattr(header, "is_hovered")
    assert not hasattr(header, "is_selected")


def test_panel_header_title_and_subtitle_layout_is_deterministic() -> None:
    header = PanelHeader("Transform", "World space")

    layout = header.layout(Rect(0.0, 0.0, 120.0, 20.0))

    assert [instruction.kind for instruction in layout.instructions] == [
        "panel_header_title",
        "panel_header_subtitle",
    ]
    assert layout.instructions[0].payload["text"] == "Transform"
    assert layout.instructions[1].payload["text"] == "World space"
