"""Contract tests for editor_tooltips_model module.

Tests tooltip computation as pure functions - headless, no arcade dependency.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.editor_tooltips_model import (
    TooltipHit,
    TooltipLayout,
    DOCK_TAB_TOOLTIPS,
    MENU_TITLE_TOOLTIPS,
    TOP_BAR_CONTROL_TOOLTIPS,
    SPLITTER_TOOLTIP,
    compute_tooltip_text_for_target,
    compute_tooltip_box_layout,
    resolve_editor_tooltip,
    _is_text_input_active_state,
    _is_modal_open_state,
)
from tests._dock_stub import make_dock_stub
from tests._session_stub import make_session_stub
from tests._typing import as_any


def _panels(*, command_palette_open: bool = False, context_menu_open: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        is_command_palette_open=lambda: command_palette_open,
        is_context_menu_open=lambda: context_menu_open,
        is_project_context_menu_open=lambda: False,
        is_keybinds_visible=lambda: False,
        is_confirm_modal_visible=lambda: False,
    )


def _session() -> SimpleNamespace:
    return make_session_stub()


def _dock(left_w: int = 220, right_w: int = 260) -> SimpleNamespace:
    return make_dock_stub(left_w=left_w, right_w=right_w)


# -----------------------------------------------------------------------------
# TooltipHit dataclass
# -----------------------------------------------------------------------------


class TestTooltipHit:
    """Tests for TooltipHit dataclass."""

    def test_create_with_values(self) -> None:
        hit = TooltipHit(kind="dock_tab", id="Scene", text="Scene Browser -- Search + open scenes")
        assert hit.kind == "dock_tab"
        assert hit.id == "Scene"
        assert hit.text == "Scene Browser -- Search + open scenes"

    def test_frozen(self) -> None:
        hit = TooltipHit(kind="dock_tab", id="Scene", text="Test")
        with pytest.raises(AttributeError):
            as_any(hit).kind = "other"

    def test_equality(self) -> None:
        a = TooltipHit(kind="dock_tab", id="Scene", text="Test")
        b = TooltipHit(kind="dock_tab", id="Scene", text="Test")
        assert a == b


# -----------------------------------------------------------------------------
# TooltipLayout dataclass
# -----------------------------------------------------------------------------


class TestTooltipLayout:
    """Tests for TooltipLayout dataclass."""

    def test_create_with_values(self) -> None:
        layout = TooltipLayout(x=100.0, y=200.0, w=150.0, h=24.0)
        assert layout.x == 100.0
        assert layout.y == 200.0
        assert layout.w == 150.0
        assert layout.h == 24.0

    def test_frozen(self) -> None:
        layout = TooltipLayout(x=100.0, y=200.0, w=150.0, h=24.0)
        with pytest.raises(AttributeError):
            as_any(layout).x = 50.0


# -----------------------------------------------------------------------------
# compute_tooltip_text_for_target
# -----------------------------------------------------------------------------


class TestComputeTooltipTextForTarget:
    """Tests for compute_tooltip_text_for_target function."""

    def test_dock_tab_scene(self) -> None:
        text = compute_tooltip_text_for_target("dock_tab", "Scene")
        assert text == DOCK_TAB_TOOLTIPS["Scene"]
        assert "Scene Browser" in text

    def test_dock_tab_project(self) -> None:
        text = compute_tooltip_text_for_target("dock_tab", "Project")
        assert text == DOCK_TAB_TOOLTIPS["Project"]
        assert "Project Explorer" in text

    def test_dock_tab_outliner(self) -> None:
        text = compute_tooltip_text_for_target("dock_tab", "Outliner")
        assert text == DOCK_TAB_TOOLTIPS["Outliner"]
        assert "Outliner" in text

    def test_dock_tab_inspector(self) -> None:
        text = compute_tooltip_text_for_target("dock_tab", "Inspector")
        assert text == DOCK_TAB_TOOLTIPS["Inspector"]
        assert "Inspector" in text

    def test_dock_tab_assets(self) -> None:
        text = compute_tooltip_text_for_target("dock_tab", "Assets")
        assert text == DOCK_TAB_TOOLTIPS["Assets"]
        assert "Assets" in text

    @pytest.mark.integration
    def test_dock_tab_items(self) -> None:
        text = compute_tooltip_text_for_target("dock_tab", "Items")
        assert text == DOCK_TAB_TOOLTIPS["Items"]
        assert text == "Items -- Edit item definitions"

    @pytest.mark.integration
    def test_dock_tab_prefabs(self) -> None:
        text = compute_tooltip_text_for_target("dock_tab", "Prefabs")
        assert text == DOCK_TAB_TOOLTIPS["Prefabs"]
        assert text == "Prefabs -- Edit prefab definitions"

    def test_dock_tab_history(self) -> None:
        text = compute_tooltip_text_for_target("dock_tab", "History")
        assert text == DOCK_TAB_TOOLTIPS["History"]
        assert "History" in text

    def test_dock_tab_problems(self) -> None:
        text = compute_tooltip_text_for_target("dock_tab", "Problems")
        assert text == DOCK_TAB_TOOLTIPS["Problems"]
        assert "Problems" in text

    def test_menu_title_file(self) -> None:
        text = compute_tooltip_text_for_target("menu_title", "File")
        assert text == MENU_TITLE_TOOLTIPS["File"]
        assert "File" in text

    def test_menu_title_edit(self) -> None:
        text = compute_tooltip_text_for_target("menu_title", "Edit")
        assert text == MENU_TITLE_TOOLTIPS["Edit"]
        assert "Edit" in text

    def test_menu_title_view(self) -> None:
        text = compute_tooltip_text_for_target("menu_title", "View")
        assert text == MENU_TITLE_TOOLTIPS["View"]
        assert "View" in text

    def test_splitter(self) -> None:
        text = compute_tooltip_text_for_target("splitter", "left")
        assert text == SPLITTER_TOOLTIP
        assert "Resize" in text

    def test_top_bar_control_left(self) -> None:
        text = compute_tooltip_text_for_target("top_bar_control", "L")
        assert text == TOP_BAR_CONTROL_TOOLTIPS["L"]
        assert "left dock" in text

    def test_top_bar_control_right(self) -> None:
        text = compute_tooltip_text_for_target("top_bar_control", "R")
        assert text == TOP_BAR_CONTROL_TOOLTIPS["R"]
        assert "right dock" in text

    def test_top_bar_control_max(self) -> None:
        text = compute_tooltip_text_for_target("top_bar_control", "M")
        assert text == TOP_BAR_CONTROL_TOOLTIPS["M"]
        assert "viewport" in text

    def test_unknown_kind(self) -> None:
        text = compute_tooltip_text_for_target("unknown_kind", "test")
        assert text is None

    def test_unknown_id(self) -> None:
        text = compute_tooltip_text_for_target("dock_tab", "UnknownTab")
        assert text is None


# -----------------------------------------------------------------------------
# compute_tooltip_box_layout - clamping
# -----------------------------------------------------------------------------


class TestComputeTooltipBoxLayout:
    """Tests for compute_tooltip_box_layout function."""

    def test_basic_positioning(self) -> None:
        layout = compute_tooltip_box_layout(
            mouse_x=400.0,
            mouse_y=300.0,
            text="Test tooltip",
            window_w=800,
            window_h=600,
        )
        assert layout.x > 0
        assert layout.y > 0
        assert layout.w > 0
        assert layout.h > 0

    def test_clamps_to_right_edge(self) -> None:
        layout = compute_tooltip_box_layout(
            mouse_x=780.0,
            mouse_y=300.0,
            text="Test tooltip with longer text",
            window_w=800,
            window_h=600,
        )
        # Should not go past right edge
        assert layout.x + layout.w <= 800

    def test_clamps_to_left_edge(self) -> None:
        layout = compute_tooltip_box_layout(
            mouse_x=5.0,
            mouse_y=300.0,
            text="Test tooltip",
            window_w=800,
            window_h=600,
        )
        # Should not go past left edge
        assert layout.x >= 0

    def test_clamps_to_bottom_edge(self) -> None:
        layout = compute_tooltip_box_layout(
            mouse_x=400.0,
            mouse_y=20.0,
            text="Test tooltip",
            window_w=800,
            window_h=600,
        )
        # Should not go past bottom edge
        assert layout.y >= 0

    def test_clamps_to_top_edge(self) -> None:
        layout = compute_tooltip_box_layout(
            mouse_x=400.0,
            mouse_y=590.0,
            text="Test tooltip",
            window_w=800,
            window_h=600,
        )
        # Should not go past top edge
        assert layout.y + layout.h <= 600

    def test_deterministic_same_inputs(self) -> None:
        layout1 = compute_tooltip_box_layout(400.0, 300.0, "Test", 800, 600)
        layout2 = compute_tooltip_box_layout(400.0, 300.0, "Test", 800, 600)
        assert layout1 == layout2


# -----------------------------------------------------------------------------
# _is_text_input_active_state
# -----------------------------------------------------------------------------


class TestIsTextInputActiveState:
    """Tests for _is_text_input_active_state function."""

    def test_returns_false_when_no_input_active(self) -> None:
        class MockController:
            session = _session()
            palette_filter_active = False
            hierarchy_filter_active = False
            hierarchy_rename_active = False
            animation_edit_active = False
            inspector_edit_active = False
            entity_panels_filter_active = False
            scene_browser_filter_active = False
            asset_browser_filter_active = False
            panels = _panels()

        assert _is_text_input_active_state(MockController()) is False

    def test_returns_true_when_palette_filter_active(self) -> None:
        class MockController:
            session = _session()
            palette_filter_active = True

        assert _is_text_input_active_state(MockController()) is True

    def test_returns_true_when_inspector_edit_active(self) -> None:
        class MockController:
            session = _session()
            inspector_edit_active = True

        assert _is_text_input_active_state(MockController()) is True

    def test_returns_true_when_command_palette_active(self) -> None:
        class MockController:
            session = _session()
            panels = _panels(command_palette_open=True)

        assert _is_text_input_active_state(MockController()) is True


# -----------------------------------------------------------------------------
# _is_modal_open_state
# -----------------------------------------------------------------------------


class TestIsModalOpenState:
    """Tests for _is_modal_open_state function."""

    def test_returns_false_when_no_modal(self) -> None:
        class MockController:
            session = _session()
            _unsaved_changes_pending = False
            scene_browser_active = False

        assert _is_modal_open_state(MockController()) is False

    def test_returns_true_when_unsaved_changes_pending(self) -> None:
        class MockController:
            session = _session()
            _unsaved_changes_pending = True

        assert _is_modal_open_state(MockController()) is True

    def test_returns_true_when_scene_browser_active(self) -> None:
        class MockController:
            session = _session()
            scene_browser_active = True

        assert _is_modal_open_state(MockController()) is True


# -----------------------------------------------------------------------------
# resolve_editor_tooltip - priority
# -----------------------------------------------------------------------------


class TestResolveEditorTooltip:
    """Tests for resolve_editor_tooltip priority."""

    def test_returns_none_when_text_input_active(self) -> None:
        class MockController:
            session = _session()
            inspector_edit_active = True
            _context_menu_open = False
            panels = _panels()
            _menu_active = None
            dock = _dock()

        result = resolve_editor_tooltip(MockController(), 400.0, 300.0, 800, 600)
        assert result is None

    def test_returns_none_when_modal_open(self) -> None:
        class MockController:
            session = _session()
            _unsaved_changes_pending = True
            _context_menu_open = False
            panels = _panels()
            _menu_active = None
            dock = _dock()

        result = resolve_editor_tooltip(MockController(), 400.0, 300.0, 800, 600)
        assert result is None

    def test_top_bar_hover_left_tooltip(self) -> None:
        class MockController:
            session = _session()
            hover = SimpleNamespace(get_hover_top_bar_control_id=lambda: "L")
            _context_menu_open = False
            panels = _panels()
            _menu_active = None
            dock = _dock()
            window = None

        result = resolve_editor_tooltip(MockController(), 400.0, 300.0, 800, 600)
        assert result == TOP_BAR_CONTROL_TOOLTIPS["L"]

    def test_top_bar_hover_right_tooltip(self) -> None:
        class MockController:
            session = _session()
            hover = SimpleNamespace(get_hover_top_bar_control_id=lambda: "R")
            _context_menu_open = False
            panels = _panels()
            _menu_active = None
            dock = _dock()
            window = None

        result = resolve_editor_tooltip(MockController(), 400.0, 300.0, 800, 600)
        assert result == TOP_BAR_CONTROL_TOOLTIPS["R"]

    def test_top_bar_hover_max_tooltip(self) -> None:
        class MockController:
            session = _session()
            hover = SimpleNamespace(get_hover_top_bar_control_id=lambda: "M")
            _context_menu_open = False
            panels = _panels()
            _menu_active = None
            dock = _dock()
            window = None

        result = resolve_editor_tooltip(MockController(), 400.0, 300.0, 800, 600)
        assert result == TOP_BAR_CONTROL_TOOLTIPS["M"]

    def test_top_bar_tooltip_blocked_by_text_input(self) -> None:
        class MockController:
            session = _session()
            hover = SimpleNamespace(get_hover_top_bar_control_id=lambda: "L")
            inspector_edit_active = True
            _context_menu_open = False
            panels = _panels()
            _menu_active = None
            dock = _dock()
            window = None

        result = resolve_editor_tooltip(MockController(), 400.0, 300.0, 800, 600)
        assert result is None

    def test_top_bar_tooltip_blocked_by_modal(self) -> None:
        class MockController:
            session = _session()
            hover = SimpleNamespace(get_hover_top_bar_control_id=lambda: "L")
            _unsaved_changes_pending = True
            _context_menu_open = False
            panels = _panels()
            _menu_active = None
            dock = _dock()
            window = None

        result = resolve_editor_tooltip(MockController(), 400.0, 300.0, 800, 600)
        assert result is None

    def test_menu_bar_hover_wins_over_top_bar(self) -> None:
        class MockWindow:
            pass

        class MockController:
            session = _session()
            hover = SimpleNamespace(get_hover_top_bar_control_id=lambda: "L")
            _context_menu_open = False
            panels = _panels()
            _menu_active = None
            dock = _dock()
            window = MockWindow()

        result = resolve_editor_tooltip(MockController(), 20.0, 590.0, 800, 600)
        assert result == MENU_TITLE_TOOLTIPS["File"]

    def test_returns_splitter_tooltip_on_splitter_hover(self) -> None:
        # Position near left splitter (around x=223 for default 220px left dock)
        class MockController:
            session = _session()
            _context_menu_open = False
            panels = _panels()
            _menu_active = None
            dock = _dock()
            window = None

        result = resolve_editor_tooltip(MockController(), 223.0, 400.0, 800, 600)
        assert result == SPLITTER_TOOLTIP

    def test_deterministic_same_inputs(self) -> None:
        class MockController:
            session = _session()
            _context_menu_open = False
            panels = _panels()
            _menu_active = None
            dock = _dock()
            window = None

        result1 = resolve_editor_tooltip(MockController(), 223.0, 400.0, 800, 600)
        result2 = resolve_editor_tooltip(MockController(), 223.0, 400.0, 800, 600)
        assert result1 == result2


# -----------------------------------------------------------------------------
# Dock tab tooltip tests
# -----------------------------------------------------------------------------


class TestDockTabTooltips:
    """Tests for dock tab tooltip resolution."""

    def test_left_dock_scene_tab_tooltip(self) -> None:
        # Scene tab is in left dock, top portion (around y=window_h - TOP_BAR_HEIGHT - TAB_HEADER_HEIGHT)
        # For 800x600 window, top_bar ends at 600-48=552, tab header is 32px
        # Tab area is roughly y=520-552
        class MockController:
            session = _session()
            _context_menu_open = False
            panels = _panels()
            _menu_active = None
            dock = _dock(320, 320)
            window = None

        from engine.editor.editor_shell_layout import (
            compute_editor_shell_layout,
            compute_dock_tab_rects,
        )

        layout = compute_editor_shell_layout(800, 600, 320, 320)
        tab_rects = compute_dock_tab_rects(layout)
        scene_rect = tab_rects.left_tab_rects["Scene"]

        result = resolve_editor_tooltip(MockController(), scene_rect.center_x, scene_rect.center_y, 800, 600)
        assert result is not None
        assert "Scene Browser" in result

    def test_right_dock_inspector_tab_tooltip(self) -> None:
        class MockController:
            session = _session()
            _context_menu_open = False
            panels = _panels()
            _menu_active = None
            dock = _dock(320, 320)
            window = None

        # Position in right dock tab area (x=800-320+80=560, y=535)
        result = resolve_editor_tooltip(MockController(), 560.0, 535.0, 800, 600)
        assert result is not None
        assert "Inspector" in result


# -----------------------------------------------------------------------------
# Context menu tooltip tests
# -----------------------------------------------------------------------------


class TestContextMenuTooltips:
    """Tests for context menu tooltip resolution."""

    def test_context_menu_item_with_shortcut(self) -> None:
        class MockController:
            session = _session()
            _context_menu_open = True
            panels = _panels(context_menu_open=True)
            _context_menu_hover_id = "ctx_duplicate"
            _context_menu_x = 100
            _context_menu_y = 300
            _menu_active = None
            dock = _dock()
            window = None
            selected_entity = None
            _entity_clipboard = None

        result = resolve_editor_tooltip(MockController(), 150.0, 280.0, 800, 600)
        assert result is not None
        assert "Duplicate" in result
        assert "Ctrl+D" in result

    def test_context_menu_no_hover(self) -> None:
        class MockController:
            session = _session()
            _context_menu_open = True
            panels = _panels(context_menu_open=True)
            _context_menu_hover_id = None  # No hover
            _context_menu_x = 100
            _context_menu_y = 300
            _menu_active = None
            dock = _dock()
            window = None

        # Should fall through to other checks
        result = resolve_editor_tooltip(MockController(), 150.0, 280.0, 800, 600)
        # May or may not find something depending on position


# -----------------------------------------------------------------------------
# ASCII safety tests
# -----------------------------------------------------------------------------


class TestASCIISafety:
    """Tests that all tooltip texts are ASCII-safe."""

    def test_dock_tab_tooltips_are_ascii(self) -> None:
        for tooltip in DOCK_TAB_TOOLTIPS.values():
            assert tooltip.isascii(), f"Non-ASCII in dock tab tooltip: {tooltip}"

    def test_menu_title_tooltips_are_ascii(self) -> None:
        for tooltip in MENU_TITLE_TOOLTIPS.values():
            assert tooltip.isascii(), f"Non-ASCII in menu title tooltip: {tooltip}"

    def test_top_bar_tooltips_are_ascii(self) -> None:
        for tooltip in TOP_BAR_CONTROL_TOOLTIPS.values():
            assert tooltip.isascii(), f"Non-ASCII in top bar tooltip: {tooltip}"

    def test_splitter_tooltip_is_ascii(self) -> None:
        assert SPLITTER_TOOLTIP.isascii()
