from types import SimpleNamespace

import pytest

from engine.game_parts import state_facade

pytestmark = pytest.mark.fast


class _GameStateController:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []

    def get_flag(self, name: str, default: bool = False) -> bool:
        self.calls.append((name, default))
        return name == "enabled"


def test_get_flag_returns_default_when_controller_attribute_is_missing() -> None:
    window = SimpleNamespace()

    assert state_facade.get_flag(window, "missing", default=True) is True
    assert state_facade.get_flag(window, "missing", default=False) is False


def test_get_flag_returns_default_when_controller_is_none() -> None:
    window = SimpleNamespace(game_state_controller=None)

    assert state_facade.get_flag(window, "missing", default=True) is True
    assert state_facade.get_flag(window, "missing", default=False) is False


def test_get_flag_delegates_to_controller_when_available() -> None:
    controller = _GameStateController()
    window = SimpleNamespace(game_state_controller=controller)

    assert state_facade.get_flag(window, "enabled", default=False) is True
    assert controller.calls == [("enabled", False)]
