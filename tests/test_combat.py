"""Tests for combat system."""

import pytest
from unittest.mock import MagicMock
import engine.optional_arcade as optional_arcade

from engine.behaviours.combat import Combat
from engine.behaviours.health import Health
from engine.behaviours.hitbox import Hitbox
from engine.config import EngineConfig
from engine.game_state_controller import GameStateController
from engine.events import MeshEventBus
from engine.game import GameWindow

class MockEntity(optional_arcade.arcade.Sprite):
    def __init__(self, name="Mock"):
        super().__init__()
        self.mesh_name = name
        self.mesh_tag = "player"
        self.mesh_behaviours_runtime = []
        self.center_x = 0
        self.center_y = 0


class StatsWindow:
    def __init__(self, enabled: bool = True):
        self.engine_config = EngineConfig()
        self.engine_config.player_stats_enabled = enabled
        self.event_bus = MeshEventBus()
        self.game_state_controller = GameStateController(self)
        self.scene_controller = MagicMock()
        self.audio = MagicMock()

@pytest.fixture
def window():
    win = MagicMock(spec=GameWindow)
    win.scene_controller = MagicMock()
    win.scene_controller.all_sprites = []
    win.audio = MagicMock()
    return win

def test_combat_attack_cooldown(window):
    entity = MockEntity()
    combat = Combat(entity, window, cooldown=1.0)
    
    # First attack should succeed
    assert combat.attack() is True
    
    # Immediate second attack should fail due to cooldown
    assert combat.attack() is False
    
    # Update timer
    combat.update(0.5)
    assert combat.attack() is False
    
    combat.update(0.6)
    assert combat.attack() is True

def test_hitbox_damage(window):
    # Setup attacker hitbox
    hitbox_entity = MockEntity("Hitbox")
    hitbox = Hitbox(hitbox_entity, window, damage=10.0, target_tag="enemy")
    
    # Setup target
    target = MockEntity("Target")
    target.mesh_tag = "enemy"
    health = Health(target, window, max_hp=20.0)
    target.mesh_behaviours_runtime.append(health)
    
    # Mock scene controller to return target
    window.scene_controller.all_sprites = [hitbox_entity, target]
    
    # Mock collision check to return True
    with pytest.MonkeyPatch.context() as m:
        m.setattr(optional_arcade.arcade, "check_for_collision_with_list", lambda s, l: [target])
        
        # Update hitbox
        hitbox.update(0.1)
        
        # Check damage
        assert health.hp == 10.0
        
        # Update again, should not damage again (hit list)
        hitbox.update(0.1)
        assert health.hp == 10.0

def test_health_death(window):
    entity = MockEntity()
    health = Health(entity, window, max_hp=10.0)
    
    # Setup event bus mock
    window.event_bus = MagicMock()
    
    health.apply_damage(5.0)
    assert health.hp == 5.0
    assert not health._dead
    
    health.apply_damage(5.0)
    assert health.hp == 0.0
    assert health._dead
    
    # Verify event emitted
    window.event_bus.emit.assert_called_with("died", actor=entity, name="Mock")


def test_player_defense_applied_when_enabled():
    window = StatsWindow(enabled=True)
    player = MockEntity("Hero")
    player.mesh_tag = "player"
    health = Health(player, window)
    starting_hp = health.hp
    defense = window.game_state_controller.get_player_stats().get("defense", 0)
    health.apply_damage(defense + 3)
    assert health.hp == pytest.approx(starting_hp - 3)


def test_combat_respects_player_stats_toggle():
    window_enabled = StatsWindow(enabled=True)
    player_enabled = MockEntity("HeroAtk")
    combat_enabled = Combat(player_enabled, window_enabled)
    assert combat_enabled.damage == window_enabled.game_state_controller.get_player_stats()["attack"]

    window_disabled = StatsWindow(enabled=False)
    player_disabled = MockEntity("HeroFlat")
    combat_disabled = Combat(player_disabled, window_disabled)
    # When disabled, default damage stays at the default (1.0) because stats are ignored
    assert combat_disabled.damage == 1.0
