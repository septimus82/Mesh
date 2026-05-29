"""Tests for Tier 2.4b Step B: Dialogue list-row click selection.

Covers:
- EditorDialogueEditorController behaviour (click, text, key handlers)
- DialogueEditorOverlay.row_index_at hit-testing
- DATABASE_FORM_ROUTES Dialogue route registration
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

pytestmark = [pytest.mark.fast]


# ---------------------------------------------------------------------------
# Controller tests
# ---------------------------------------------------------------------------

class _StubOverlay:
    def __init__(self, hit_index: int | None) -> None:
        self._hit_index = hit_index
        self.selected_calls: list[int] = []

    def row_index_at(self, x: float, y: float) -> int | None:  # noqa: ARG002
        return self._hit_index

    def set_selected_index(self, index: int) -> bool:
        self.selected_calls.append(index)
        return True


def _make_controller(hit_index: int | None = None) -> tuple[object, _StubOverlay]:
    from engine.editor.editor_dialogue_editor_controller import EditorDialogueEditorController

    overlay = _StubOverlay(hit_index)
    editor = SimpleNamespace(window=SimpleNamespace(dialogue_editor_overlay=overlay))
    controller = EditorDialogueEditorController(editor)
    return controller, overlay


def test_is_edit_mode_active_returns_false() -> None:
    controller, _ = _make_controller()
    assert controller.is_edit_mode_active() is False


def test_text_handler_returns_false() -> None:
    controller, _ = _make_controller()
    assert controller.handle_dialogue_editor_text_input("hello") is False


def test_key_handler_returns_false() -> None:
    controller, _ = _make_controller()
    assert controller.handle_dialogue_editor_key(65, 0) is False


def test_click_hits_row_calls_set_selected_and_returns_true() -> None:
    controller, overlay = _make_controller(hit_index=2)
    result = controller.handle_dialogue_editor_mouse_click(50.0, 120.0)
    assert result is True
    assert overlay.selected_calls == [2]


def test_click_miss_no_selection_change_returns_true() -> None:
    controller, overlay = _make_controller(hit_index=None)
    result = controller.handle_dialogue_editor_mouse_click(999.0, 999.0)
    assert result is True
    assert overlay.selected_calls == []


def test_click_no_overlay_returns_true() -> None:
    from engine.editor.editor_dialogue_editor_controller import EditorDialogueEditorController

    editor = SimpleNamespace(window=SimpleNamespace(dialogue_editor_overlay=None))
    controller = EditorDialogueEditorController(editor)
    assert controller.handle_dialogue_editor_mouse_click(0.0, 0.0) is True


def test_click_no_window_returns_true() -> None:
    from engine.editor.editor_dialogue_editor_controller import EditorDialogueEditorController

    editor = SimpleNamespace()
    controller = EditorDialogueEditorController(editor)
    assert controller.handle_dialogue_editor_mouse_click(0.0, 0.0) is True


# ---------------------------------------------------------------------------
# Overlay hit-testing tests
# ---------------------------------------------------------------------------

def test_row_index_at_returns_correct_index() -> None:
    from engine.editor.widgets.panel_primitives import PanelField, PanelRow
    from engine.ui.widgets import Rect
    from engine.ui_overlays.dialogue_editor_overlay import DialogueEditorOverlay

    window = SimpleNamespace(width=800, height=600, editor_controller=None, text_cache=None)
    overlay = DialogueEditorOverlay(window)  # type: ignore[arg-type]

    # Build two rows with known rects
    row0 = PanelRow(PanelField("dlg_001", None), height=18.0, padding_x=6.0)
    row1 = PanelRow(PanelField("dlg_002", None), height=18.0, padding_x=6.0)
    row0.layout(Rect(0, 100, 200, 18))
    row1.layout(Rect(0, 82, 200, 18))

    overlay._row_hits = [(0, row0), (1, row1)]  # type: ignore[assignment]

    # Inside row0
    assert overlay.row_index_at(10.0, 109.0) == 0
    # Inside row1
    assert overlay.row_index_at(10.0, 91.0) == 1


def test_row_index_at_outside_returns_none() -> None:
    from engine.editor.widgets.panel_primitives import PanelField, PanelRow
    from engine.ui.widgets import Rect
    from engine.ui_overlays.dialogue_editor_overlay import DialogueEditorOverlay

    window = SimpleNamespace(width=800, height=600, editor_controller=None, text_cache=None)
    overlay = DialogueEditorOverlay(window)  # type: ignore[arg-type]

    row0 = PanelRow(PanelField("dlg_001", None), height=18.0, padding_x=6.0)
    row0.layout(Rect(0, 100, 200, 18))
    overlay._row_hits = [(0, row0)]  # type: ignore[assignment]

    assert overlay.row_index_at(500.0, 500.0) is None


def test_row_index_at_empty_hits_returns_none() -> None:
    from engine.ui_overlays.dialogue_editor_overlay import DialogueEditorOverlay

    window = SimpleNamespace(width=800, height=600, editor_controller=None, text_cache=None)
    overlay = DialogueEditorOverlay(window)  # type: ignore[arg-type]
    assert overlay.row_index_at(0.0, 0.0) is None


# ---------------------------------------------------------------------------
# Route registration test
# ---------------------------------------------------------------------------

def test_database_form_routes_contains_dialogue_route() -> None:
    from engine.editor_runtime.editor_database_form_input import DATABASE_FORM_ROUTES

    tab_names = [r.tab_name for r in DATABASE_FORM_ROUTES]
    assert "Dialogue" in tab_names

    (route,) = [r for r in DATABASE_FORM_ROUTES if r.tab_name == "Dialogue"]
    assert route.controller_attr == "dialogue_editor"
    assert route.text_handler == "handle_dialogue_editor_text_input"
    assert route.key_handler == "handle_dialogue_editor_key"
    assert route.click_handler == "handle_dialogue_editor_mouse_click"
