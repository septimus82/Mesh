import unittest
from unittest.mock import MagicMock

from engine.config import EngineConfig
from engine.game_state_controller import GameStateController
from engine.perks import Perk, PerkManager
from engine.quests import QuestManager


class TestPerkEffectsRewards(unittest.TestCase):
    def setUp(self):
        self.window = MagicMock()
        self.window.engine_config = EngineConfig(xp_base=1000, xp_per_level=1000)
        self.window.game_state_controller = GameStateController(self.window)
        # Mock PerkManager
        self.window.game_state_controller.perk_manager = MagicMock(spec=PerkManager)
        self.window.game_state_controller.perk_manager.get_perk.side_effect = self._get_mock_perk

        # Mock window.game_state property to return controller.state
        self.window.game_state = self.window.game_state_controller.state

        self.quest_manager = QuestManager(self.window, data_path="assets/data/quests.json")
        # Prevent actual loading
        self.quest_manager._definitions = {}

    def _get_mock_perk(self, perk_id):
        if perk_id == "gold_boost":
            return Perk("gold_boost", "Gold Boost", "", {"gold_bonus_pct": 0.5})
        if perk_id == "xp_boost":
            return Perk("xp_boost", "XP Boost", "", {"xp_bonus_pct": 0.5})
        return None

    def test_gold_reward_bonus(self):
        # Add perk
        self.window.game_state_controller.state.perks.append("gold_boost")

        quest = {"id": "q1", "title": "Q1", "reward": {"gold": 100}}
        state = {"status": "active"}

        # Mock values
        self.window.game_state.values = {"gold": 0}

        self.quest_manager._complete_quest(quest, state, source="test")

        # Base 100 + 50% = 150
        self.assertEqual(self.window.game_state.values["gold"], 150)

    def test_xp_reward_bonus(self):
        # Add perk
        self.window.game_state_controller.state.perks.append("xp_boost")

        quest = {"id": "q2", "title": "Q2", "reward": {"xp": 100}}
        state = {"status": "active"}

        self.window.game_state.xp = 0

        self.quest_manager._complete_quest(quest, state, source="test")

        # Base 100 + 50% = 150
        self.assertEqual(self.window.game_state.xp, 150)

if __name__ == "__main__":
    unittest.main()
