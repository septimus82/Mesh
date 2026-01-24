import unittest
from unittest.mock import MagicMock, patch
from engine.behaviours.ranged_attack_ai import RangedAttackAI
from engine.events import MeshEvent

class TestRangedAttackAI(unittest.TestCase):
    def setUp(self):
        self.entity = MagicMock()
        self.entity.x = 0
        self.entity.y = 0
        self.entity.name = "Enemy"
        
        self.window = MagicMock()
        self.window.event_bus = MagicMock()
        
        self.player = MagicMock()
        self.player.tag = "player"
        self.player.x = 100
        self.player.y = 0
        
        self.window.current_scene.entities = [self.player, self.entity]
        
        self.ai = RangedAttackAI(self.entity, self.window, attack_range=200.0, attack_cooldown=1.0)

    @patch('engine.behaviours.ranged_attack_ai.time.time')
    def test_attack_in_range(self, mock_time):
        mock_time.return_value = 100.0
        # Player is at 100, range is 200. Should attack.
        self.ai.update(0.1)
        
        self.window.event_bus.emit.assert_any_call("projectile_fired", 
            source="Enemy", x=0, y=0, dir_x=1.0, dir_y=0.0, speed=300.0)
        self.window.event_bus.emit.assert_any_call("combat_attack",
            attacker="Enemy", target="Player", type="ranged")

    @patch('engine.behaviours.ranged_attack_ai.time.time')
    def test_no_attack_out_of_range(self, mock_time):
        mock_time.return_value = 100.0
        self.player.x = 300 # Out of range
        self.ai.update(0.1)
        
        self.window.event_bus.emit.assert_not_called()

    @patch('engine.behaviours.ranged_attack_ai.time.time')
    def test_cooldown(self, mock_time):
        mock_time.return_value = 100.0
        # First attack
        self.ai.update(0.1)
        self.window.event_bus.emit.reset_mock()
        
        # Immediate update - should be on cooldown
        mock_time.return_value = 100.5
        self.ai.update(0.1)
        self.window.event_bus.emit.assert_not_called()
        
        # After cooldown
        mock_time.return_value = 101.1
        self.ai.update(0.1)
        self.window.event_bus.emit.assert_called()

