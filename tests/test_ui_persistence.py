import types

import pytest

from engine.scene_controller import SceneController
from engine.ui import (
    PERSISTENT_UI_ATTRS,
    GameOverScreen,
    HelpOverlay,
    PauseMenu,
    PlayerHUD,
    missing_persistent_ui_attrs,
)
from engine.ui_controller import UIController
from tests._typing import as_any

pytestmark = [pytest.mark.integration, pytest.mark.slow]


class _StubPrefabManager:
    def load(self) -> None:
        return


def test_persistent_ui_attr_list_includes_help_overlay() -> None:
    missing, has_duplicates = missing_persistent_ui_attrs(PERSISTENT_UI_ATTRS)
    assert missing == []
    assert has_duplicates is False


def test_help_overlay_persists_across_scene_ui_rebuild(monkeypatch) -> None:
    monkeypatch.setattr("engine.scene_controller.get_prefab_manager", lambda: _StubPrefabManager())

    window = types.SimpleNamespace()
    window.width = 800
    window.height = 600
    window.show_debug = False
    window.engine_config = types.SimpleNamespace()
    window.ui_controller = UIController(as_any(window))
    window.clear_ui_elements = lambda: window.ui_controller.clear_ui_elements()
    window.register_ui_element = lambda element, **kwargs: window.ui_controller.register_ui_element(
        element, **kwargs
    )

    window.player_hud = PlayerHUD(as_any(window))
    window.game_over_screen = GameOverScreen(as_any(window))
    window.pause_menu = PauseMenu(as_any(window))
    window.help_overlay = HelpOverlay(as_any(window))

    controller = SceneController(as_any(window))
    window.scene_controller = controller

    controller._rebuild_ui_for_scene()

    assert window.player_hud in window.ui_controller.ui_elements
    assert window.help_overlay in window.ui_controller.ui_elements
    assert window.ui_controller.ui_elements.count(window.help_overlay) == 1
