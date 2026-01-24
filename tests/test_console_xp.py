from engine.console_controller import ConsoleController
from engine.config import EngineConfig
from engine.game_state_controller import GameStateController


class DummyWindow:
    def __init__(self):
        self.engine_config = EngineConfig()
        self.console_controller = None
        self.game_state_controller = GameStateController(self)
        self._logged: list[str] = []

    def console_log(self, message: str) -> None:
        self._logged.append(message)


def test_console_xp_get_and_add():
    window = DummyWindow()
    console = ConsoleController(window)
    window.console_controller = console

    console.execute_command("xp")
    assert any("xp=" in line for line in console.lines)

    window.game_state_controller.set_xp(0)
    console.execute_command("xp add 100")
    stats = window.game_state_controller.get_player_stats()
    assert stats["level"] >= 2
    console.execute_command("xp")
    assert any("xp=" in line for line in console.lines)
