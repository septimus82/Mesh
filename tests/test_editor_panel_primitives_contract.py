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


# ---------------------------------------------------------------------------
# Truncation tests (Tier 11.0-B)
# ---------------------------------------------------------------------------

def test_panel_field_long_label_and_value_narrow_bounds_both_truncated_no_overlap() -> None:
    """Long label + long value in a narrow panel: both get '...', label x < value x."""
    field = PanelField("A very long quest name here", "quest_with_a_very_long_id_string")

    # 80px wide — both texts overflow at default font sizes
    layout = field.layout(Rect(0.0, 0.0, 80.0, 24.0))

    assert len(layout.instructions) == 2
    label_instr = layout.instructions[0]
    value_instr = layout.instructions[1]
    assert label_instr.kind == "panel_field_label"
    assert value_instr.kind == "panel_field_value"
    # Both were truncated
    assert label_instr.payload["text"].endswith("...")
    assert value_instr.payload["text"].endswith("...")
    # No positional overlap: label is left-anchored, value is right-anchored —
    # label end x must be < value start x
    label_end_x = float(label_instr.payload["x"]) + len(label_instr.payload["text"]) * (11 * 0.6)
    value_start_x = float(value_instr.payload["x"]) - len(value_instr.payload["text"]) * (10 * 0.6)
    assert label_end_x < value_start_x


def test_panel_field_short_label_and_value_wide_bounds_not_truncated() -> None:
    """Short texts in a wide panel: strings are drawn unchanged (fit-first)."""
    field = PanelField("Name", "id")

    layout = field.layout(Rect(0.0, 0.0, 400.0, 24.0))

    label_text = layout.instructions[0].payload["text"]
    value_text = layout.instructions[1].payload["text"]
    assert label_text == "Name"
    assert value_text == "id"


def test_panel_field_short_value_medium_label_fits_label_not_truncated() -> None:
    """Fit-first: when label+gap+value fits, label is drawn full even if a fixed 60%
    split would have cut it."""
    # 30-char label × 6.6px ≈ 198px; 4-char value × 6px ≈ 24px; gap 8px → 230px total
    # A 300px-wide panel comfortably fits both — label must NOT be truncated.
    label = "A medium length quest name ok"   # 29 chars
    value = "id01"                             # 4 chars
    field = PanelField(label, value)

    layout = field.layout(Rect(0.0, 0.0, 300.0, 24.0))

    assert layout.instructions[0].payload["text"] == label
    assert layout.instructions[1].payload["text"] == value


def test_panel_field_value_none_narrow_bounds_label_only_no_raise() -> None:
    """value=None row in a narrow panel: only label instruction emitted, no error."""
    field = PanelField("Some label text that is quite long", value=None)

    layout = field.layout(Rect(0.0, 0.0, 60.0, 24.0))

    kinds = [i.kind for i in layout.instructions]
    assert kinds == ["panel_field_label"]
    # Label may be truncated but must not raise and must be a non-empty string
    assert len(layout.instructions[0].payload["text"]) >= 1


def test_panel_field_overflow_label_gets_majority_of_budget() -> None:
    """On overflow, label_chars >= value_chars (label ≥60% of budget)."""
    field = PanelField("X" * 40, "Y" * 40)

    layout = field.layout(Rect(0.0, 0.0, 120.0, 24.0))

    label_text = layout.instructions[0].payload["text"]
    value_text = layout.instructions[1].payload["text"]
    # Both truncated; label gets the larger share
    assert len(label_text) >= len(value_text)


def test_panel_field_truncation_tighter_at_high_text_scale(monkeypatch) -> None:
    """At text_scale=2.0 the char budget is halved → truncation triggers sooner."""
    import engine.text_draw as _td

    monkeypatch.setattr(_td, "_text_scale", 2.0)

    field = PanelField("Medium length label", "medium_value_id")

    # At scale=1 this fits in 240px; at scale=2 it should overflow and truncate
    layout_scale2 = field.layout(Rect(0.0, 0.0, 240.0, 24.0))

    monkeypatch.setattr(_td, "_text_scale", 1.0)
    layout_scale1 = field.layout(Rect(0.0, 0.0, 240.0, 24.0))

    label_at_scale2 = layout_scale2.instructions[0].payload["text"]
    label_at_scale1 = layout_scale1.instructions[0].payload["text"]
    # At higher scale the rendered label is shorter (tighter budget)
    assert len(label_at_scale2) <= len(label_at_scale1)
