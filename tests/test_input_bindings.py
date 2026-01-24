import json

import arcade

from engine.config import EngineConfig
from engine.console_controller import ConsoleController
from engine.input import InputManager
from engine.input_bindings import apply_config_bindings


class DummyWindow:
    def __init__(self, config_path: str) -> None:
        self.engine_config = EngineConfig()
        self.config_path = config_path
        self.input = InputManager()


def test_apply_bindings_from_config() -> None:
    manager = InputManager()
    warnings: list[str] = []

    applied = apply_config_bindings(
        manager,
        {
            "move_up": ["W"],
            "attack": ["SPACE"],
            "unknown_action": ["NOPE"],
        },
        warn=warnings.append,
        arcade_module=arcade,
    )

    assert applied is True
    bindings = manager.get_bindings()
    assert bindings["move_up"] == [arcade.key.W]
    assert bindings["attack"] == [arcade.key.SPACE]
    assert "unknown_action" not in bindings
    assert any("NOPE" in msg for msg in warnings)


def test_console_bind_and_unbind_persist(tmp_path) -> None:
    config_path = tmp_path / "cfg.json"
    window = DummyWindow(str(config_path))
    console = ConsoleController(window)

    console.execute_command("bind attack SPACE")
    attack_bindings = window.input.get_bindings().get("attack")
    assert attack_bindings is not None
    assert arcade.key.SPACE in attack_bindings
    assert window.engine_config.input_bindings["attack"] == ["SPACE"]

    saved = json.loads(config_path.read_text())
    assert saved["input_bindings"]["attack"] == ["SPACE"]

    console.execute_command("unbind attack")
    assert "attack" not in window.input.get_bindings()
    assert "attack" not in window.engine_config.input_bindings
