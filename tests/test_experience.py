import arcade

from engine.behaviours.grant_experience import GrantExperience
from engine.config import EngineConfig
from engine.events import MeshEvent, MeshEventBus
from engine.game_state_controller import GameStateController


class DummyWindow:
    def __init__(self):
        self.engine_config = EngineConfig()
        self.event_bus = MeshEventBus()
        self.scene_controller = type("SC", (), {"all_sprites": []})()
        self.game_state_controller = GameStateController(self)


def test_add_xp_levels_up():
    window = DummyWindow()
    gs = window.game_state_controller
    result = gs.add_xp(60)
    assert result["level"] == 2
    assert result["xp"] == 10  # 60 - 50 needed
    stats = gs.get_player_stats()
    assert stats["max_hp"] > window.engine_config.player_base_max_hp
    assert stats["xp_to_next"] > 0


def test_grant_experience_on_death_event():
    window = DummyWindow()
    sprite = arcade.Sprite()
    sprite.mesh_tag = "enemy"
    behaviour = GrantExperience(sprite, window, xp=15)
    event = MeshEvent("died", {"actor": sprite})
    window.event_bus.emit("died", **event.payload)
    assert window.game_state_controller.get_xp() >= 15


def test_level_up_event_emitted():
    window = DummyWindow()
    captured = []
    window.event_bus.subscribe("level_up", lambda event: captured.append(event.payload.get("level")))
    window.game_state_controller.add_xp(window.engine_config.xp_base)
    assert captured[-1] == 2
