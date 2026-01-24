import types
from unittest.mock import MagicMock

from engine.actions import dispatch_action, validate_bound_actions
from engine.config import load_config


class StubEditorController:
    def __init__(self) -> None:
        self.active = True
        self.toggle = MagicMock()
        self.toggle_dialogue_panel = MagicMock()
        self.toggle_animation_panel = MagicMock()
        self.toggle_tile_panel = MagicMock()
        self.toggle_lights_tool = MagicMock()


def test_config_bindings_match_action_registry() -> None:
    cfg = load_config("config.json")
    bindings = cfg.input_bindings
    assert isinstance(bindings, dict)

    unknown, missing = validate_bound_actions(bindings)
    assert not unknown, f"config.json binds unknown action(s): {unknown}"
    assert not missing, f"config.json missing required action(s): {missing}"


def test_dispatch_all_bound_actions_does_not_raise() -> None:
    cfg = load_config("config.json")
    bindings = cfg.input_bindings

    window = types.SimpleNamespace()
    window.editor_controller = StubEditorController()
    window.help_overlay = types.SimpleNamespace(toggle=MagicMock())
    window.inspector_overlay = types.SimpleNamespace(toggle=MagicMock())
    window.toggle_quest_log = MagicMock(return_value=True)
    window.toggle_inventory_overlay = MagicMock(return_value=True)
    window.toggle_character_panel = MagicMock(return_value=True)
    window.emit_signal = MagicMock()

    for action in bindings.keys():
        assert dispatch_action(window, action) is True
