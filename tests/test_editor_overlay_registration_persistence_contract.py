import types

import pytest

from engine.scene_controller import SceneController
from engine.ui_contract import PERSISTENT_UI_ATTRS
from engine.ui_controller import UIController
from tests._typing import as_any

pytestmark = [pytest.mark.fast]


class _StubPrefabManager:
    def load(self) -> None:
        return


_EDITOR_OVERLAY_ATTRS = (
    "editor_shell_overlay",
    "menu_bar_overlay",
    "context_menu_overlay",
    "entity_panels_overlay",
    "component_inspector_overlay",
    "hd2d_settings_panel_overlay",
    "editor_status_bar_overlay",
    "scene_switcher_overlay",
    "scene_browser_overlay",
    "project_explorer_overlay",
    "asset_browser_overlay",
    "item_editor_overlay",
    "prefab_editor_overlay",
    "quest_editor_overlay",
    "dialogue_editor_overlay",
    "undo_history_overlay",
    "problems_panel_overlay",
    "debug_panels_overlay",
    "find_everything_overlay",
    "light_occluder_overlay",
    "selection_outline_overlay",
    "editor_hover_highlight_overlay",
    "marquee_select_overlay",
    "editor_gizmo_overlay",
    "editor_tooltip_overlay",
    "editor_cursor_hint_overlay",
)


def test_editor_overlays_are_in_persistent_ui_contract() -> None:
    for attr_name in _EDITOR_OVERLAY_ATTRS:
        assert attr_name in PERSISTENT_UI_ATTRS


def test_editor_overlays_persist_across_scene_ui_rebuild(monkeypatch) -> None:
    monkeypatch.setattr("engine.scene_controller.get_prefab_manager", lambda: _StubPrefabManager())

    window = types.SimpleNamespace()
    window.width = 800
    window.height = 600
    window.show_debug = False
    window.engine_config = types.SimpleNamespace()
    window.ui_controller = UIController(as_any(window))
    window.clear_ui_elements = lambda: window.ui_controller.clear_ui_elements()
    window.register_ui_element = lambda element: window.ui_controller.register_ui_element(element)

    editor_overlays = {attr_name: object() for attr_name in _EDITOR_OVERLAY_ATTRS}
    for attr_name, overlay in editor_overlays.items():
        setattr(window, attr_name, overlay)
        window.register_ui_element(overlay)

    controller = SceneController(as_any(window))
    window.scene_controller = controller

    as_any(controller)._rebuild_ui_for_scene()

    for overlay in editor_overlays.values():
        assert overlay in window.ui_controller.ui_elements
        assert window.ui_controller.ui_elements.count(overlay) == 1
