from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.editor.dock_tab_registry import DOCK_TAB_TOOLTIPS, RIGHT_DOCK_TABS
from engine.ui_overlays.dialogue_editor_overlay import DialogueEditorOverlay
from tests._dock_stub import make_dock_stub


pytestmark = [pytest.mark.fast]


def _window_for_tab(right_tab: str) -> SimpleNamespace:
    controller = SimpleNamespace(active=True, dock=make_dock_stub(right_tab=right_tab))
    return SimpleNamespace(width=800, height=600, editor_controller=controller, text_cache=None)


def test_dialogue_editor_overlay_constructs() -> None:
    overlay = DialogueEditorOverlay(_window_for_tab("Dialogue"))

    assert overlay is not None


def test_dialogue_editor_overlay_visibility_is_dialogue_tab_only() -> None:
    overlay = DialogueEditorOverlay(_window_for_tab("Dialogue"))

    assert overlay._is_visible_for_controller(overlay.window.editor_controller) is True

    other = DialogueEditorOverlay(_window_for_tab("Quests"))
    assert other._is_visible_for_controller(other.window.editor_controller) is False


def test_dialogue_tab_is_registered_after_quests() -> None:
    assert "Dialogue" in RIGHT_DOCK_TABS
    assert RIGHT_DOCK_TABS.index("Dialogue") == RIGHT_DOCK_TABS.index("Quests") + 1
    assert DOCK_TAB_TOOLTIPS["Dialogue"] == "Dialogue -- Browse dialogue database"
