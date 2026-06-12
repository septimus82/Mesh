
from dataclasses import replace
from unittest.mock import Mock, patch

from engine.editor.keybinds_ui_model import KeybindRow, KeybindsState
from engine.ui_overlays.keybinds_provider import get_keybinds_ui_data


class MockController:
    def __init__(self):
        self.state = KeybindsState(visible=True, selected_index=0)
        # 10 test rows
        self.visible_rows = tuple(
            Mock(
                spec=KeybindRow,
                action_id=f"action.{i}",
                title=f"Action {i}",
                scope="global",
                shortcut_effective=f"Ctrl+{i}" if i % 2 == 0 else "",
                shortcut_default="",
                has_conflict=False,
                conflict_ids=[],
                has_override=False
            )
            for i in range(10)
        )

def test_provider_slicing():
    ctrl = MockController()

    # Viewport holds 3 rows (height 100, row 30) -> 3.33 -> 4 rows
    # Overscan 2 -> ~8 rows active
    data = get_keybinds_ui_data(ctrl, viewport_height=90, row_height=30, current_scroll_y=0)

    assert data["rows_total"] == 10
    visible = data["rows_visible"]
    assert len(visible) > 0
    # First row index 0
    assert visible[0]["index"] == 0

def test_provider_auto_scroll_to_selection():
    ctrl = MockController()
    ctrl.state = replace(ctrl.state, selected_index=9) # Last item

    # Viewport 90 (3 rows). Last item is at Y=270.
    # Should scroll down.
    data = get_keybinds_ui_data(ctrl, viewport_height=90, row_height=30, current_scroll_y=0)

    # Target scroll should be non-zero
    assert data["scroll_y"] > 0
    # Approx 270 - 90 + margin?
    # Logic: bottom_y=300. viewport=90. align bottom -> 300 - 90 = 210.

    # Check that visible slice includes the selected item
    visible_indices = [r["index"] for r in data["rows_visible"]]
    assert 9 in visible_indices
    assert data["rows_visible"][-1]["is_selected"]

def test_provider_details_structure():
    ctrl = MockController()
    # Mock row with conflict
    conflict_row = Mock(
        spec=KeybindRow,
        action_id="conflict.action",
        title="Conflict Action",
        scope="global",
        shortcut_effective="Ctrl+C",
        shortcut_default="Ctrl+C",
        has_conflict=True,
        conflict_ids=["other.action"],
        has_override=True
    )
    ctrl.visible_rows = (conflict_row,)
    ctrl.state = replace(ctrl.state, selected_index=0)

    data = get_keybinds_ui_data(ctrl)

    sel = data["selected_item"]
    assert sel["action_id"] == "conflict.action"
    assert sel["has_override"] is True
    assert sel["conflicts"] == ["other.action"]

    assert data["rows_visible"][0]["has_conflict"] is True
    assert data["rows_visible"][0]["has_override"] is True

def test_web_flag_passed():
    ctrl = MockController()

    with patch("engine.editor.editor_actions._is_web_runtime", return_value=True):
        data = get_keybinds_ui_data(ctrl)
        assert data["is_web"] is True
        assert "(Preview Only)" in data["hint_text"]

    with patch("engine.editor.editor_actions._is_web_runtime", return_value=False):
        data = get_keybinds_ui_data(ctrl)
        assert data["is_web"] is False
        assert "(Preview Only)" not in data["hint_text"]
