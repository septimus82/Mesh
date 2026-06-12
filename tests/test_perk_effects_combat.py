import unittest
from unittest.mock import MagicMock

from engine.config import EngineConfig
from engine.game_state_controller import GameStateController
from engine.perks import Perk, PerkManager


class TestPerkEffectsCombat(unittest.TestCase):
    def setUp(self):
        self.window = MagicMock()
        self.window.engine_config = EngineConfig()
        self.controller = GameStateController(self.window)

        # Mock PerkManager
        self.controller.perk_manager = MagicMock(spec=PerkManager)
        self.controller.perk_manager.get_perk.side_effect = self._get_mock_perk

    def _get_mock_perk(self, perk_id):
        if perk_id == "vitality":
            return Perk("vitality", "Vitality", "", {"max_hp": 20.0})
        if perk_id == "strength":
            return Perk("strength", "Strength", "", {"damage_pct": 0.1})
        return None

    def test_max_hp_bonus(self):
        base_hp = self.window.engine_config.player_base_max_hp

        # No perks
        stats = self.controller.get_player_stats()
        self.assertEqual(stats["max_hp"], base_hp)

        # Add perk
        self.controller.state.perks.append("vitality")
        stats = self.controller.get_player_stats()
        self.assertEqual(stats["max_hp"], base_hp + 20.0)

    def test_damage_bonus(self):
        base_atk = self.window.engine_config.player_base_attack

        # Add perk
        self.controller.state.perks.append("strength")
        stats = self.controller.get_player_stats()

        expected = base_atk * 1.1
        self.assertAlmostEqual(stats["attack"], expected)

if __name__ == "__main__":
    unittest.main()
