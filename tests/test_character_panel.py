
from engine.config import EngineConfig
from engine.game_state_controller import GameStateController
from engine.ui import CharacterPanel
from engine.ui_controller import UIController


class StubAudio:
    def play_sound(self, path: str) -> None:  # pragma: no cover - stub
        self.last = path


class StubWindow:
    def __init__(self) -> None:
        cfg = EngineConfig()
        self.engine_config = cfg
        self.width = cfg.width
        self.height = cfg.height
        self.audio = StubAudio()
        self.game_state_controller = GameStateController(self)

    def get_counter(self, name: str, default: float = 0.0):
        return self.game_state_controller.get_counter(name, default)


def test_character_panel_toggle_and_stats_snapshot():
    window = StubWindow()
    window.game_state_controller.set_counter("gold", 42)
    panel = CharacterPanel(window)
    assert panel.visible is False
    panel.toggle()
    assert panel.visible is True
    stats = panel._collect_stats()
    assert stats["gold"] == 42
    assert stats["xp_needed"] >= stats["xp"]


def test_character_panel_blocks_input_via_controller():
    window = StubWindow()
    ui = UIController(window)
    panel = CharacterPanel(window)
    ui.character_panel = panel
    ui.register_ui_element(panel)
    panel.set_visible(True)
    assert ui.character_panel_blocks_input() is True
    assert ui.dialogue_blocks_input() is True
